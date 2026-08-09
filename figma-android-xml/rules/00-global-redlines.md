# 真实世界的陷阱与全局红线库 (Global Redlines & Anti-patterns)

这些是曾经导致多轮反复调试的非直观问题。在执行 01 到 06 工作流时，必须时刻在脑海中关联并规避这些陷阱！在用户质问“为什么 X 坏了？”之前，务必提前排查以下每一项。

## 真实世界的陷阱（实战血泪教训）

### 资源格式陷阱

#### 假 PNG (SVG-as-PNG) 陷阱（最常见）
- **症状**：下载的 `.png` 文件以合理的大小存在（700B-2KB），但 `ImageView` 渲染空白，没有错误。
- **原因**：Figma 将矢量节点（具有路径/矩形/圆的组）导出为 **原始 SVG 内容**，即使资产 URL 看起来返回了 PNG。文件扩展名是 `.png`，但字节以 `<svg ...>` 开头。Android 的 `BitmapFactory` 无法解码 SVG → 导致图像默默显示为空白。
- **检测**：每次批量下载后，检查 PNG 魔法字节 (magic bytes)：
  ```python
  with open("downloaded_image.png", 'rb') as f:
      ok = f.read(8) == b'\x89PNG\r\n\x1a\n'
  ```
  或者 `file path.png` 应该报告 `PNG image data`，而不是 `SVG Scalable Vector Graphics image`。
- **修复**：将每个 SVG 转换为 Android `VectorDrawable` XML（处理带 `fillColor`/`strokeColor`/`strokeWidth` 的 `<rect>`/`<line>`/`<circle>`/`<path>`）。将其保存为 `drawable/` 中的 `.xml`，**删掉那个假的 `.png`**（Android 资源系统：`@drawable/foo` 匹配 `.png` 或 `.xml` — 兼有两者将导致重复资源错误）。
- **快速判断准则**：在 Figma 中只要看到是包含形状图元 (shape primitives) 的 `<g id="...">` 分组 → 就要预料到它导出的会是 SVG → 就要预留转换它的步骤。

#### SVG `<filter>` (投影 / 内阴影 / 模糊) 无法转换
- **症状**：转换后的 VectorDrawable 显示形状，但缺少在 Figma 中可见的阴影/发光。
- **原因**：VectorDrawable 不支持 `feGaussianBlur` / `feDropShadow` / `feColorMatrix`。转换期间默默丢弃了 SVG `<filter>` 块。
- **修复**：使用 Android `android:elevation` (Material 投影) 近似阴影，或者对于非矩形卡片使用 `CardView` + `cardElevation`。如果不使用完整的位图渲染（直接用切图），内阴影通常无法在代码层面完美重现。

#### SVG `linearGradient` → 使用 Android shape `<gradient>`
- **症状**：Figma 中具有渐变填充的地方，VectorDrawable 显示为纯色。
- **原因**：通过 `fill="url(#paint0_linear...)"` 引用的 `<linearGradient>` 要求在 `<path>` 内部提供内联的 `<aapt:attr name="android:fillColor">` (API 24+) ，或者将整个资产重写为带 `<gradient>` 的 `shape` drawable。
- **修复**：对于矩形/椭圆上的简单渐变，**优先选择手动编写 `shape` drawable** 配合 `<gradient android:angle="270" startColor="..." endColor="..." />` — 它比处理 VectorDrawable 内联渐变更清晰。

#### SVG `mask group` (alpha 遮罩 / 剪裁路径) 无法在 XML View 系统中运行
- **症状**：Figma 英雄插画被裁剪为特定形状 — Android 显示未裁剪的照片。
- **原因**：Figma 的掩蔽组在光栅图像上使用 alpha 掩蔽。View 系统没有内置的 alpha 掩蔽。Compose 有。`BitmapShader` + 自定义 View 也能做到。
- **修复**：直接使用未掩蔽的源照片资产 (90-95% 的视觉匹配)，或者如果要求像素级完美，请编写一个小型的自定义 `MaskedImageView`。记录该差异。

#### 资源文件名 ↔ 内容的映射往往不可靠
- **症状**：选项卡 a/b 状态的 PNG 会渲染，但选中的选项卡显示错误的图标（例如，点击“设备”导致“我的”变蓝）。
- **原因**：当被早期脚本预下载时，命名约定 (活动用 `_a`，不活动用 `_b`) 可能应用得不一致 — 一个选项卡的 `_a` 是蓝色而另一个的 `_a` 是灰色。
- **修复**：对于状态对 (state-pair) 资产，**读取每个 PNG 一次**，以验证内容与名称是否匹配。然后在磁盘上重命名文件或调整选择器/Java 以匹配实际内容。不要两边同时改，导致错误抵消。

#### Figma 资源 URL 是短期的（7天 TTL）
- **症状**：`curl <figma-mcp-asset-url>` 成功，但下载 0 字节或 HTML 错误。
- **原因**：`get_design_context` 返回的 URL 在调用后约 7 天过期。先前会话中缓存的资产 URL 可能已失效。
- **修复**：在实际执行下载前，必须重新调用 `get_design_context` 获取新鲜的 URL。不要跨会话存储或复用这些 URL。

#### 图标脑补与资产兜底陷阱 (Icon Hallucination & Asset Fallback Trap)
- **症状**：生成的矢量图标与设计稿不符；不同节点的同名图标被强行共用；或缺失矢量数据时界面毫无反馈。
- **原因**：大模型凭语义名称默写 SVG（脑补）；基于"名字相同"而非物理尺寸去重（过度泛化）；遇到缺失数据时静默造假。
- **强制五级决策树（严禁跳级、严禁脑补）**：
  1. **有 `fillGeometry.path`** → 逐字节拷贝 pathData → VectorDrawable；`android:width/height` 必须按 `scale` 折算 dp，禁止照抄 viewport 数字。
  2. **有 SVG 导出文件** → 解析 `<path d="...">` 转 VectorDrawable，等同级别 1。
  3. **有位图可下载** → `android:src` 引用真实 drawable；动态加载的 ImageView 必须用 `tools:src` 标注语义意图；只下载设计基准分辨率，放入对应 `drawable-xxdpi/` 目录。
  4. **图层名与 Material Icons / Google Fonts Icons 精确匹配** → 目视确认视觉一致后引用，并注释 `<!-- MATERIAL_ICON: 待设计确认 -->`。
  5. **以上全部不可用** → `android:src` 留空；`tools:src` 引用 `@tools:sample/*`（如 `@tools:sample/backgrounds/scenic`）做预览占位；打注释 `<!-- TODO: 缺失真实切图，待设计提供 -->`。严禁凭空默写路径！
- **物理级去重红线**：不同 `Node-ID` 的图标即便同名（如右侧 Share 和底部 Tab Share），除非 `pathData` 与宽高字节级 100% 一致，否则必须独立生成资源文件，严禁基于语义概念合并。
- **Drawable 资源通用红线**：① VectorDrawable `fillColor`/`strokeColor` 严禁引用 `@color/`，内联 hex 或 `?attr/`；② `<selector>` 具体状态置顶、default `<item>` 置底，缺一不可；③ 可点击元素 background 必须用 `<ripple>` 包裹，严禁裸 `<selector>`；④ `<gradient>` `angle` 只支持 45 整数倍，Figma 任意角度就近取整；⑤ 四角独立圆角必须还原为 `topLeftRadius` 等独立属性，严禁统一成单一 `radius`；⑥ 纯色背景直接 `android:background="@color/..."`，严禁为此创建只有 `<solid>` 的 shape 文件。

### 布局 / 内边距陷阱

#### 紧凑排列被打散陷阱 (Packed Elements Spread Trap)
- **症状**：Figma 中紧凑包裹 (Hug contents) 的元素（如“头像+名字+按钮”），在 XML 中被强行扯开，首尾相隔巨大空隙。
- **原因**：大模型习惯性地用霸占余量的属性（如 `0dp`、`weight="1"` 或锚定 `parent` 边缘）去处理中间文本，把“紧密包裹”变成了“两端对齐 (Space-between)”。
- **通用修复红线（严禁打散紧凑组）**：
  - **通用法则**：只要 Figma 里是紧凑挨着的，**绝对严禁**将其末尾元素约束到父容器边缘，也严禁盲目给中间元素加 `0dp` 或 `weight`。
  - **ConstraintLayout 方案**：首尾相接约束。若需防止中间长文本把末尾按钮顶飞，中间文本用 `wrap_content` + `app:layout_constrainedWidth="true"`，并让全组形成 `chainStyle="packed"` (配合 `bias="0.0"`)。
  - **LinearLayout (水平) 方案**：所有元素保持 `wrap_content`，仅通过 `margin` 隔开。若需防止中间文本过长导致末尾按钮被挤出屏幕外，可将中间文本设为 `layout_width="0dp"` + `layout_weight="1"`，但前提是**外层必须有一个 `wrap_content` 的容器包裹它们**，或者直接改用 ConstraintLayout。

#### 根布局强加 tools 宽高陷阱 (Root Tools Dimension Trap)
- **症状**：XML 预览直接报错（例如 `String types not allowed (at 'layout_height' with value '1066.67dp')`），或者预览界面完全扭曲/罢工。
- **原因**：大模型在生成 XML 时，盲目把 Figma 画板的绝对尺寸（往往带有小数，如 `1066.67`）照搬塞进了根布局的 `tools:layout_width` 和 `tools:layout_height` 中。Android XML 解析器对带有小数点的 `dp` 尺寸（尤其是用在 `tools:layout` 上）支持极差，会导致致命解析错误。
- **修复（强制红线）**：**绝对严禁在根节点（如最外层的 ConstraintLayout）上使用 `tools:layout_width` 和 `tools:layout_height`！** 根节点必须老老实实写 `match_parent`。如果非要改变预览设备尺寸，那是人类开发者在 IDE 顶部的 Device 选单里自己去调的事，代码里绝不准强写带有小数点的 device 尺寸！

#### ID 惰性缺失陷阱 (ID Omission Trap)
- **症状**：因为本工作流严禁编写 Kotlin 业务代码，大模型在生成纯 XML 布局时，极易产生惰性，不再为按钮、输入框等交互元素分配 `android:id`。
- **后果**：虽然视觉完美，但后续人类开发者接手写 Kotlin 时，无法通过 ViewBinding 找到控件，导致需要全部返工加 ID。
- **修复（强制红线）**：**必须为所有具备交互潜力的元素（Button, ImageView 按钮, EditText, RecyclerView, 动态 TextView）强制生成高语义化的 `android:id`！这是不可妥协的底线，为人类开发者预留接口！**

#### 图标容器压扁与尺寸污染陷阱 (Icon Container Flattening & Size Contamination)
- **症状**：Figma 里 48x48 的 Frame 包裹 40x36 的实际图标。大模型要么把它们压扁成一层，要么虽然写了嵌套，但**发生了严重的尺寸污染**：把里层真实图形的 XML 宽高，错误地写成了外层大容器的尺寸（例如里外都写成了 48px 换算后的 32dp，导致内层的 `android:width` 跟 `viewportWidth` 完全不符）。
- **原因**：大模型在遍历 Figma 节点树时，错误地让子节点继承或套用了父容器的物理宽高。
- **修复**：**必须精确还原嵌套，且严格隔离内外尺寸！**
  1. **外层热区**（`<FrameLayout>`）：严格只取外层透明容器的尺寸（如 48px）按 `scale` 缩放。
  2. **内层视觉**（`ImageView` 及 `<vector>` 资源本身）：**必须强行读取内层真实图形节点（如 Like 40x36）的独立尺寸！** 绝对禁止把外层尺寸“下穿”套用给内层！内层生成的任何代码，都只能基于它自己那个 40x36 的边界来计算。

#### LinearLayout 中 `match_parent` 组合 `weight=1` 的冲突
- **症状**：出现带权重的子级时，兄弟视图（选项卡栏、页脚）被推出屏幕。
- **原因**：在 `layout_weight="1"` 的子级上设置 `layout_height="match_parent"`，会导致某些 Android 版本在应用权重之前为子级分配完整的父级高度，吞噬留给固定大小兄弟视图的空间。
- **修复**：使用 `layout_height="0dp"` + `layout_weight="1"` (经典的 LinearLayout 权重模式)。对于水平也一样：`layout_width="0dp"` + `layout_weight`。

#### Android 15 (`targetSdk=35+`) 强制全屏 (Edge-to-edge)
- **症状**：屏幕顶部（返回按钮、标题）隐藏在系统状态栏后面。
- **原因**：Android 15 (`targetSdk=35`) 默认使应用程序窗口全屏显示，忽略主题设置。Activity 必须显式处理 Insets。
- **修复**：若 `targetSdk=35+`，Activity 根布局必须处理 Insets（如声明 `android:fitsSystemWindows="true"`），除非有明确的全屏沉浸式设计。

#### Figma 的绝对 Y 坐标假设“0 = 状态栏底部”
- **症状**：使用 Figma Y 值定位的内容在 Android 上显得太低。
- **原因**：Figma 375×812 框架假定顶部有 50dp iPhone 状态栏。Figma `y=110` 表示“在状态栏下方 60dp”——但在 Android 上，`marginTop=110dp` 距离屏幕顶部就是 110dp，它包含任何 Android 状态栏。
- **修复**：在 `fitsSystemWindows="true"` 消耗 inset 之后，映射到 Android marginTop 时减去 Figma 状态栏高度 (50dp)。或者使用 48dp 的 Android 工具栏并在其下方开始测量。

#### PingFang SC 是 iOS 系统独占字体
- **症状**：Android 上的中文字符与 Figma 相比在细节上看起来不对。
- **原因**：Figma 使用 PingFang SC (iOS 系统中文字体)。Android 退回使用 Noto Sans CJK / 鸿蒙 Sans / OEM 特定字体。
- **修复**：要么在包内捆绑 PingFang 及其近似字体（会导致 APK 增加 5-10MB），要么直接接受系统默认回退。对于特殊的展示字体（如汉仪字库等）→ 为了视觉保真，捆绑字体文件是不可避免的。

### 换算与精度陷阱 (Conversion & Precision Traps)

#### 大模型四舍五入强迫症 (12.67sp -> 13sp)
- **症状**：本应是 12.67sp 的字号或 14.33dp 的边距，被直接写成了 `13sp` 或 `14dp`。
- **原因**：大模型有一种“自作聪明”的强迫症，喜欢把 UI 尺寸四舍五入成整数。在移动端开发中，微小的像素堆叠误差会导致整个布局错位。
- **修复**：**尺寸精度红线**！在处理任何尺寸的计算结果时，绝对严禁人为四舍五入抹除小数。只要除不尽，必须原样保留两位小数（如 17.33sp）。
- **【多 Frame 提取重灾区/防呆红线】带有小数的尺寸严禁使用下划线！**
  当您需要将带小数的具体尺寸抽离为 `dimen` 时（尤其在多层 Frame 批量合并提取时），大模型极易受底层编程惯性误导，擅自把小数点改成下划线。**这是绝对的红线！**
  不仅数值本身必须原样保留，**其 XML `name` 属性也必须严格保留小数点 `.`，绝对严禁使用下划线 `_` 替代！**
  - ❌ 错误示例：`<dimen name="text_size_17">17.33sp</dimen>` (名字与实际值割裂)
  - ❌ 错误示例：`<dimen name="text_size_17_33">17.33sp</dimen>` (多 Frame 常见误区：画蛇添足使用下划线)
  - ✅ 正确强制规范：`<dimen name="text_size_17.33">17.33sp</dimen>` (名字和内容必须完全一致包含小数点)

#### 颜色透明度 (Alpha) 的十进制混淆陷阱
- **症状**：Figma 里 50% 透明度的白色，写成了 `#50FFFFFF`，导致颜色比设计稿淡很多。
- **原因**：大模型误把百分号直接当成了十六进制的 alpha 通道。十六进制的 50 转换成十进制其实只有 31% 的透明度！
- **修复**：**绝对禁止直接拼凑百分比**！必须进行十六进制换算：50% 对应 80，80% 对应 CC。真实的 50% 白必须写为 `#80FFFFFF`。

#### 字间距 (Letter Spacing) 单位错乱陷阱
- **症状**：Figma 里 `2%` 或 `0.5px` 的字间距，导致 Android 上文字飞出屏幕。
- **原因**：大模型照抄数字写成 `android:letterSpacing="2"`。Android 接收的是基于 `em` 的 Float 相对倍数。
- **修复**：**字间距换算公式**！`android:letterSpacing = Figma的百分比数值 ÷ 100`（不能带任何单位）。比如 2% 必须写为 `0.02`。

### 排版、行高与文本属性陷阱 (Typography, Line Height & Text Attributes)

<a id="trap-11-line-height"></a>
#### 极紧凑行高导致单行文字（按钮/标签）被严重裁剪与压扁
- **症状**：按钮文字被上下截断（字母 'g', 'p' 下半部分消失），或者明明设置了 `gravity="center"`，文字却严重偏上/偏下。
- **原因**：大模型盲目将 Figma 中极度紧凑的行高（如 `13sp` 字号配 `14sp` 行高）照搬到 Android 的 `app:lineHeight` 上，配合 `includeFontPadding="false"` 会彻底破坏单行文本的原生测量边界 (Bounds)。
- **修复**：对于 Button、Tab、Badge 等**单行居中文本**，**绝对严禁添加 `app:lineHeight` 属性**！必须让 Android 按照字体原生 metrics 计算高度，仅依靠父容器的 `paddingTop/Bottom` 或固定 `layout_height` + `gravity="center"` 来撑开点击区域。只有**多行段落文本**才需要忠实还原 Figma 的行高。

<a id="trap-shadow-floats"></a>
#### 提取 Style 资源时，将 Float 纯数值属性（如 shadow, weight）无脑抽为 `@dimen` 导致崩溃
- **症状**：页面或 `<style>` 在 inflate 阶段直接闪退，日志中报错 `NumberFormatException`，内容类似 `For input string: "1.0dip"`。
- **原因**：大模型在生成复用的 `<style>` 或整理尺寸资源时，有一种“看到数字就想往 `dimens.xml` 里塞”的强迫症。但对于 Android 底层类型为 **Float** 的属性（例如文本阴影 `shadowDx/Dy/Radius`、行距倍数 `lineSpacingMultiplier`、约束偏移 `bias` 等），一旦被抽出为 `@dimen`，系统在展开时就会追加单位（如 `1.0dip`），导致抛出类型异常。
- **修复**：**类型抽取红线**！只有真正的物理尺寸（宽/高/边距/字号等）才可以提 `@dimen`。所有 Float 数值属性**绝对严禁抽取**，也严禁带单位，必须且只能在 `<style>` 或布局中**直接内联硬编码纯数字**（例如 `<item name="android:shadowDx">0</item>`）。

### 状态管理陷阱

#### 交互状态静态化陷阱 (Missing State Selectors)
- **症状**：Figma 原图中有“普通态”和“选中态”，但因为禁止写 Kotlin，大模型直接把颜色写死了，生成了一个静态无交互的死控件。
- **修复（强制红线）**：绝不许使用 Kotlin 代码切换状态！遇到具备变体状态（Checked, Selected, Pressed, Disabled）的元素，**必须强制使用纯 XML 状态机（如 `res/color/xxx_selector.xml` 或 `res/drawable/xxx_state.xml`）来接管状态展示。**

#### `duplicateParentState=true` 配合状态列表选择器在国产 ROM (MIUI/EMUI) 上非常脆弱
- **症状**：选项卡/按钮状态切换在某些设备上有效，而在另一些上无效。图标不交换，文本不改色，尽管调用了 parent 的 `setSelected(true)`。
- **原因**：依赖于 `View.setSelected` 通过 `dispatchSetSelected` 级联到子项，子项通过 `duplicateParentState` 读取父状态，然后状态列表选择器解析出正确的 drawable/颜色。经历了太多框架跳转，每次跳转都随 ROM 不同而变化。
- **修复**：对于选项卡栏和类似控件，**使用显式的 Java 辅助代码** 更可靠：
  ```kotlin
  fun selectTab(index: Int) {
      tab1.setSelected(index == 0)
      iv1.setImageResource(if (index == 0) R.drawable.tab_a else R.drawable.tab_b)
      tv1.setTextColor(if (index == 0) selectedColor else unselectedColor)
      // ... 每个选项卡重复
  }
  ```
  保持单一事实来源 (Single source of truth)。在这种场景下，不需要再写 selector 也不需要 `duplicateParentState`。

#### 多状态 ColorStateList 触摸时产生文本颜色闪烁
- **症状**：点击选项卡会短暂使文本变为蓝色 (或其他"选中"颜色)，然后恢复。
- **原因**：如果 ColorStateList 中 `state_pressed` 写在前面被优先匹配 → 在手指按下瞬间就会显示选中色，甚至早于点击事件触发设置真实的 selected 状态。
- **修复**：移除 `state_pressed` 条目或接受闪烁。对于选项卡栏，首选单一颜色 + 显式的 Java 状态更改 (参见 #11)。

#### 小屏溢出陷阱 (横向弹性文本截断/重叠)
- **症状**：中间文本（如 Banner）在大屏正常，小屏覆盖图标或被截断。
- **原因**：错误翻译 Figma 绝对宽度，导致宽度硬编码（如 `180dp`），或 `wrap_content` 悬空一侧边界。
- **修复**：弹性居中文字严禁固定宽度或单边约束。必须添加兜底属性 (`ellipsize="end"` 与 `maxLines`)，并严格匹配父布局自适应法则：
  - **ConstraintLayout**：宽度 `0dp`，强制双侧锚点 `constraintStart_toEndOf` 与 `constraintEnd_toStartOf`。
  - **LinearLayout (水平)**：宽度 `0dp`，强制设置 `android:layout_weight="1"`。

#### 无障碍属性滥用陷阱 (彻底封杀 contentDescription)
- **症状**：大模型随意猜测图标含义，并向 `strings.xml` 写入大量无意义的 `@string/desc_xxx`。
- **原因**：大模型无法精准判断业务语境，过度迎合 Lint 警告反而导致代码库污染。
- **修复**：为了彻底杜绝此问题，**强制全面剥夺大模型的描述推断权**：
  - **所有 ImageView**：无脑强制写入 `android:contentDescription="@null"`，不准猜测！
  - **所有容器 (FrameLayout 等)**：绝对严禁添加 `contentDescription` 属性。
  - **严禁**因为任何借口向 `strings.xml` 写入与描述 (description) 相关的词条。

### Figma 权限与访问陷阱

#### 文件访问 ≠ 节点访问
- **症状**：`get_metadata` / `get_design_context` 返回“无法访问此 figma 文件” (`could not be accessed`)。
- **原因**：具有 MCP 身份验证的帐户没有此文件的查看权限。
- **修复**：用户必须 (a) 将认证帐户邮箱邀请为查看者，(b) 将共享更改为"拥有链接的任何人——可以查看"，或者 (c) 在文件所有者的帐户下重新认证 Figma MCP。当访问失败时，**始终首先运行 `whoami`**。

#### Figma 中的 Section vs Frame
- **症状**：即使使用有效的 `nodeId`，对节点执行 `get_design_context` 返回“您当前未选中任何内容”。
- **原因**：该节点是 Figma 的 **Section (章节)**（一个容器，不是 Frame）。Section 不支持 `get_design_context`（没有渲染代码）。
- **修复**：使用 `get_screenshot(<sectionId>)` 来识别其内部内容，然后让用户提供单独的 **frame** URL 以便调用 `get_design_context`。Frame 的格式也是 `node-id=NN-MM`，但它们代表一个分立的屏幕。

#### `get_metadata(0:1)` 截断大文件
- **症状**：在 metadata XML 中搜索已知的节点 ID 什么也不返回，即使该节点存在。
- **原因**：大型文件的 metadata 响应上限约为 89K-100K 字符。较深的子 frame 会在末尾被丢弃。
- **修复**：不要依赖文件根元数据来枚举一切。直接通过 `get_design_context` 或 `get_screenshot` 拉取特定的节点 ID。向用户询问 URLs。

#### 将 Figma 文件保存为副本 (Copy) 可能会重新生成所有节点 ID
- **症状**：用户分享了一个源自原始文件的 URL（如 `node-id=34-335`），但相同的 node-id 不存在于他们的 Copy (副本) 文件中。
- **原因**：Figma 复制文件的行为不一致 — 有时保留 ID，有时重新生成。
- **修复**：从副本文件工作时，始终重新调用 `get_design_context` 以验证节点在预期 ID 处是否仍然存在。如果不存在，请要求用户直接从副本文件重新导出 URL。

### 构建陷阱

#### 多渠道 (Multi-channel) 编译很慢；请务必指定单个 flavor 进行开发迭代
- **原因**：具有多个市场风味版本 (小米、华为、Oppo、Vivo、应用宝等) 的项目运行 `./gradlew assembleDebug` 时，将构建每个 flavor。超过 5 分钟的构建扼杀了迭代速度。
- **修复**：只为迭代构建一个 flavor：`./gradlew assembleXiaomiDebug` (或取决于测试设备安装了什么)。只在最后运行完整的多渠道构建。

#### `dimens.xml` 的 `dp_NN` token 序列存在断层
- **症状**：在引用了看似标准的 Figma 值后，构建失败并出现 `error: resource dimen/dp_378 not found`。
- **原因**：现有项目的 `dimens.xml` 有 `dp_1`..`dp_360`，然后跳到了 `dp_365`、`dp_370`、`dp_400`、`dp_410`、`dp_472`、`dp_500` 等 —— 缺少常见的如 378、395、486 这样的值。
- **修复**：根据需要将缺失条目添加到 `dimens.xml`。不要假设 dp_NN 序列是密集的。

### 自定义视图陷阱

#### 使用 Canvas 自定义绘制的组件往往达不到 Figma 中丰富渐变 PNG 的视觉效果
- **症状**：通过 `Canvas.drawCircle/drawArc/drawText` 绘制表盘 / 指示器的 `View` 子类，与 Figma 的多层渐变设计相比，显得“扁平”。
- **原因**：通过代码手写的 Paint 平面填充，根本无法复刻 Figma 渲染出的多色标渐变 + 柔和阴影 + 高斯模糊层。
- **修复**：将 Figma 导出的背景图 (PNG 或 VectorDrawable) 垫底，然后将你的 Custom View 设置为透明，仅仅作为接收触摸事件的 Overlay。（空的 `onDraw`，保留 `onTouchEvent`）。调用者组合模式：`FrameLayout` { 拨盘背景 + 箭头覆盖层 + 中心文本 + 自定义方向盘视图 }。

#### ColorStateList 资源的存放位置规范
- **注意**：带有 `<item android:color>`（而不是 `android:drawable`）的 `<selector>` 文件通常放在 `res/color/` 中，而不是 `res/drawable/`。尽管两者都可以用于 `android:textColor="@drawable/foo"` 引用，但 `res/color/` 是惯用的位置，并避免了混淆。

### 工作流与验证陷阱

#### 多 Frame 并行陷阱 (Multi-Frame Parallel Trap)
- **症状**：用户提供多个 Figma 链接，大模型把每个 Frame 当独立任务并发处理，导致共享颜色、dimen、drawable 重复定义多次，弹窗等衍生屏被错误生成为 `activity_xxx.xml`。
- **原因**：大模型跳过了预处理步骤，未按规矩识别基础屏与衍生屏的从属派生关系。
- **修复（强制红线）**：多链接场景下必须严格执行 `checklists/frame-classification.md`。必须按顺序串行执行：基础屏必须优先且完整走完阶段 3 和阶段 4，派生 Frame 后续生成时**强制复用**基础屏已生成的资源与 `include` 组件，**严禁并行独立生成**。

#### 原生 cp 命令搬运陷阱 (Native cp Command Trap)
- **症状**：未经压缩的大尺寸 PNG 被直接拷贝进 `res/drawable`，导致 APK 体积膨胀甚至 OOM。
- **原因**：大模型习惯性使用系统 `cp` 或 `mv` 命令搬运 Figma 切图。
- **修复（强制红线）**：绝对禁止使用原生 `cp` 或 `mv` 搬运图片资源。必须强制调用 `python3 scripts/copy_and_optimize.py <src> <dest>` 进行搬运，并根据其打印的 `[SUCCESS]` 或 `[SKIPPED]` 日志，动态决定在 XML 中是使用 `android:src` 正常引用，还是使用 `tools:src` 进行占位。

#### 位图资源目录陷阱 (Bitmap Resource Directory Trap)
- **症状**：大模型将位图（PNG/WebP/JPG）直接放入 `res/drawable/`，导致 Android 在不同密度的设备上无法正确缩放图片，引发模糊或内存激增。
- **原因**：没有区分 XML drawable 和位图 (bitmap) drawable 的存放规则。
- **修复（强制红线）**：
  1. 所有 **常规 XML 资源**（shape, selector, vector）放 `res/drawable/`。（**特例**：Adaptive Icon 的 XML 描述文件如 `ic_launcher.xml` 必须放 `res/mipmap-anydpi-v26/`）。
  2. 所有 **位图资源**（PNG/WebP/JPG）**严禁**放无后缀的 `res/drawable/` 或 `res/mipmap/`，必须放入带分辨率后缀的目录！
  3. **强制区分与目录推导：**
     - **普通图片/切图** -> 放入 `res/drawable-{density}/`
     - **桌面启动图标 (Launcher Icons)** -> 放入 `res/mipmap-{density}/`
       **如何决定 {density} 后缀？**
       严禁大模型自行计算或猜测！必须强制读取 `.env` 文件中的 `TARGET_BITMAP_DENSITY` 配置项（如 `xxhdpi`、`xhdpi`）。
       - 如果配置了 `xxhdpi`，则图片放入 `res/drawable-xxhdpi/`，启动图标放入 `res/mipmap-xxhdpi/`。
       - 如果读取不到该配置，则**默认强制降级为 `-nodpi` 目录**。

#### 阶段性停顿陷阱（误把内部检查点当成用户确认点）
- **症状**：读取红线、读取阶段手册、fetch 截图、查看图片或扫描项目后，单独回复“继续吗/我将继续/已完成某步”，等待用户再发“继续”。
- **原因**：把 6 阶段懒加载工作流误解成逐步审批流程；实际它只是要求“进入每个阶段前先读取对应规则”，并不要求用户逐阶段确认。
- **修复（强制红线）**：必须自主、连贯地跑完整个阶段 1 → 6。除非遇到不可自行解决的真实阻塞（权限、凭据、目标不明、外部设备等），否则不允许阶段性停止或请求继续。工具失败时先自行诊断、修脚本或调整输入后重试。

#### 视觉工具返回后停顿陷阱（把看图当成流程终点）
- **症状**：`view_file` / `view_image` / 截图工具成功显示 Figma 原图后，没有继续扫描项目、读取阶段 2 或修改文件，而是隐式等待用户发“继续”。
- **原因**：把视觉感知步骤误当成阶段完成汇报；实际看图只是阶段 1 的内部输入采集动作。
- **修复（强制红线）**：视觉工具返回后必须立即继续发起下一条工具调用或进入下一阶段。除非图像无法读取且无任何兜底资料，否则不得停止。

#### 工具长输出后停顿陷阱（把截断输出当成流程终点）
- **症状**：扫描项目或读取规则后输出很长、被截断，然后停止等待用户指出“又停下了”。
- **原因**：把“输出截断/信息很多”误判为阶段结束；实际只需要缩小范围继续采集必要信息。
- **修复（强制红线）**：阶段 6 未完成前，任何工具返回后都必须继续自检并发起下一步工具调用。长输出时用 `rg`、`sed`、脚本摘要等方式缩小范围继续推进，禁止自然语言收尾。

#### 批量下载后绝对不要在同一回合 (turn) 中 `Read (读取)` 大量 drawable文件 — 这会直接触发 API 崩溃硬错误
- **症状（真实观察到的）**：在下载了约 13 个以上的图像资产并依次 `Read` 它们以“验证内容”后，Anthropic API 返回：
  ```
  API Error: 400 {"type":"error","error":{"type":"invalid_request_error","message":"Could not process image"}}
  ```
  这个回合被**阻塞**了 —— 你不能继续，必须回滚。这跟你的上下文窗口用量没关系，这是大模型上游的图像处理服务崩了。
- **原因**：Anthropic 的图像处理有每个回合的限制（数量和/或累积大小）。批量 `Read` 许多 PNG（特别是 100KB+ 范围内的照片）会超出此限制。SVG-as-PNG 文件在约 700B-2KB 时也不会作为图像解码，这也可能引发这种错误模式。
- **修复**：在批量下载后，**使用 `ls -lhS`** 验证文件大小是否合理：
  - 小图标：彩色的光栅图预期 ≥1KB，矢量图预期 ≥500B
  - 照片 / 插画：预期 ≥50KB
  - 任何小于 300B 的都是可疑的 (可能是碎片或 HTML 错误页)
  
  然后，每个回合最多只使用 `view_file` 或读取 1~2 张图像，并且仅在你需要解决视觉歧义时才看（比如，你需要判断 `tab_a/b` 哪个是蓝色选中态、哪个是灰色未选中态）。绝对禁止试图用 `Read` 去遍历整个下载的文件列表。
- **具体预算**：如果需要比较 6 对以上的状态对图像，跨多个回合执行 (混合照片时每回合最多 3 个)，或者跳过视觉验证，相信构建会大声失败。

#### 当源文件格式本身就是错的时，做 `MD5 校验` 没有任何意义
- **原因**：用户建议"重新下载并进行 MD5 比较以验证"。但是，如果 Figma 导出的格式错误 (SVG 而不是 PNG)，其字节将与现有的损坏文件相同 —— MD5 会匹配。
- **修复**：在 MD5 之前，运行 **格式检查** (PNG 头魔法字节)。如果格式不对，MD5 校验就失去意义 —— 你必须换一种资产获取方式（比如手动转 VectorDrawable，或者在 Figma 选中另一个节点再导，或者直接手写 Android shape）。

## 绝对禁止的反模式 (Anti-patterns)

- 还没提取任何资源，就上来直接手写页面 XML。
- 在整个布局代码中满天飞地硬编码 `#RRGGBB`、`16dp` 或 `14sp`。
- 在需要使用 `0dp` 约束的情况下，在 `ConstraintLayout` 子级中使用 `match_parent`。
- 生搬硬套地把 Figma 里的绝对坐标直接转换成写死的 margin。
- 为了实现复杂页面，嵌套出十八层 `LinearLayout`。
- 忽略 `includeFontPadding`、字体粗细或字间距。对于多行段落忽略行高。
- **在单行居中文本（如按钮、标签）上盲目照搬 Figma 的行高（`app:lineHeight`），导致文字被上下裁剪或无法垂直居中（请参阅 [单行文字行高陷阱](#trap-11-line-height)）**。
- **将 `android:shadowDx` / `android:shadowDy` / `android:shadowRadius` 写成 `@dimen/...` 或带单位的 `dp/sp` 字符串，导致 `TextView` 在 inflate 时因 float 解析失败而崩溃（请参阅 [Float 抽取红线陷阱](#trap-shadow-floats)）**。
- 漏写 `ImageView` 的 `scaleType`（含小 Icon）。
- 直接使用 Material 默认的按钮/文本框/卡片样式，而不覆盖内边距、形状、颜色和状态以匹配 Figma。
- **文本审查红线：将预览用假数据（如纯数字、用户名、长段落占位符）写入 `android:text`。必须应用强制量化分类：长度≥10、包含数字或动态名词的文本，只允许使用 `tools:text`。只有短小的死文案标签（如"Cancel"）才允许用 `android:text`。**
- 默认静默假设系统栏是包含的还是排除的。
- **从 Figma 下载后，盲目信任 `.png` 扩展名而不去检查底层的魔法字节 (magic bytes)**（请参阅 [假 PNG (SVG-as-PNG) 陷阱](#假-png-svg-as-png-陷阱最常见)）。
- **在 LinearLayout 中混用 `match_parent` + `weight=1`**（请参阅 [LinearLayout match_parent 陷阱](#linearlayout-中-match_parent-组合-weight1-的冲突)）。
- **依赖于 `duplicateParentState` 处理选项卡/按钮状态更改**（请参阅 [状态列表 duplicateParentState 陷阱](#duplicateparentstatetrue-配合状态列表选择器在国产-rom-miuiemui-上非常脆弱)）。
- **批量下载一堆文件后，为了所谓的“验证内容”而去读取每一个 drawable（这会让大模型崩溃，见 [API 崩溃硬错误陷阱](#批量下载后绝对不要在同一回合-turn-中-read-读取-大量-drawable文件--这会直接触发-api-崩溃硬错误)）**。
- **将按钮等交互式组件实现为静态 `<shape>` 而不是带有按下态的 `<selector>`**。
- **将用于预览的假数据（如用户名、点赞数、长段占位文本）污染进 `strings.xml`（预览假数据必须仅硬编码存在于 XML 布局的 `tools:text` 中）**。
- **创建纯别名颜色（如 `<color name="my_white">@color/white</color>`）或定义数值完全相同但碎片化的 dimens（必须直接复用底色或合并为高阶语义 Token，如 `space_12`）**。
- **给颜色起语义化的名字（如 `color_bg`、`color_text`）。颜色命名必须被强制锁定为十六进制字面量格式（如 `color_FFFF86FC`）**。
- **VectorDrawable 尺寸折算丢失陷阱**：在生成 `<vector>` 图标资源时，错误地直接把 `viewportWidth` 的原图像素值当成了 dp（例如 viewport 是 38，就无脑写死 `android:width="38dp"`），这会导致图标在手机上异常巨大！**防呆措施（强制红线）：VectorDrawable 的 `android:width` 和 `android:height` 绝对不能照抄 viewport 的数字！它们必须和布局里的其它元素一样，严格按照您在阶段 2 算出的公式（`dp = Figma 原像素值 × scale`）进行同比例的数学折算！**
- **为仅使用一次的文本外观无脑抽取 `style`。防呆措施：阶段3写 XML 时强制 100% 内联。必须在独立的阶段4，扫描自己写的XML，确认被复用 ≥2 次才允许抽取。只用1次必须保持内联。**
- **为仅使用一次的尺寸无脑抽取 `dimen`。防呆措施：与上方相同，阶段3写 XML 时强制 100% 内联。必须在阶段4扫描确认完全相同的尺寸复用 ≥2 次才允许抽取。**
- **不按规范使用清晰的语义化 Token（严禁使用 Figma 导出的无意义图层名作为尺寸资源名，必须使用如 `space_12`, `radius_16` 等标准的语义化维度命名）**。
- **禁止使用整页切图充当 UI（严禁将包含多个文本、按钮或子组件的整个页面/大块面板作为单一图片资源，如 `@drawable/ig_reel_content`，直接赋给 `ImageView`。容器必须用 XML 组件化拼装，图片资源仅限用于不可拆分的单张真实照片或纯图标）**。
- **【尺寸换算基准偷换】用行业惯性值（360dp、375dp 等）替代 `.env` 中 `ANDROID_BASE_WIDTH` 配置的实际值，导致所有 dp 值系统性偏移。防呆措施：阶段2必须先用文件读取工具读 `.env` 获取 `ANDROID_BASE_WIDTH`，再明文展示 `scale = ANDROID_BASE_WIDTH ÷ Figma画板宽度 = ___`，写出后才能开始尺寸换算。**
- **【尺寸精度红线】大模型自作聪明地对尺寸进行四舍五入（把 12.67dp 抹除小数写成 13dp）。只要换算除不尽，必须强制保留两位小数。**
- **【透明度换算红线】将 Figma 的百分比透明度直接当成十六进制写进颜色里（如 50% 白写成 `#50FFFFFF`）。必须查表转换（50% = 80）。**
- **【字间距换算红线】直接照抄 Figma 的字间距数字。必须套用公式 `letterSpacing = 百分比数值 ÷ 100`。**
- **【图标资产红线】凭图层名默写 SVG 路径（脑补）；不同 Node-ID 同名图标强行复用同一文件；缺失矢量数据时静默填充近似图形。必须严格走五级决策树，无真实数据时 `android:src` 留空 + `tools:src` 占位 + TODO 注释，绝不造假。**
- **【Drawable 资源通用红线】① VectorDrawable 的 `fillColor`/`strokeColor` 严禁引用 `@color/`，必须内联 hex 字面量或 `?attr/` 主题属性；② `<selector>` 具体状态必须置顶，default 兜底 `<item>` 必须置底，缺一不可；③ 可点击元素的 background 必须用 `<ripple>` 包裹，严禁裸 `<selector>`；④ `<gradient>` 的 `angle` 只支持 45 的整数倍，Figma 任意角度必须就近取整；⑤ Figma 四角独立圆角必须还原为 `topLeftRadius` 等独立属性，严禁统一成单一 `radius`；⑥ 纯色背景直接用 `android:background="@color/..."` ，严禁为此创建只有 `<solid>` 的 shape 文件。**
