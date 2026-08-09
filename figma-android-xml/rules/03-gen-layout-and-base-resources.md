> ⚠️ **红线检索**：执行前必须结合上下文检索 `00-global-redlines.md`，触碰红线立即回退。

## 阶段 3：优先生成核心基础资源并编写纯内联 XML 布局

本阶段采用 **先内联，后重构 (Inline-First Paradigm)** 的策略，旨在彻底解决提前盲目抽取资源导致的“单次使用资源污染”问题。

### 1. 优先生成必定全局复用的基础资源
在编写页面 XML 之前，先创建或更新以下基础资源：
- `res/values/colors.xml`
- `res/values/strings.xml`（仅限需要静态字符串时）
- `res/drawable/bg_*.xml` 形状可绘制对象 (shape drawables)
- `res/drawable/selector_*.xml` 状态选择器
- `res/drawable/ic_*.xml` 矢量可绘制对象 (图标可用时)

规则：
- 所有颜色都必须通过 `@color/...` 引用。
- 所有布局尺寸、外边距 (margins)、内边距 (paddings)、图标大小、圆角半径和文本大小，**只有在多个组件中重复使用时**，才必须通过 `@dimen/...` 引用并抽取。对于仅出现一次的孤立尺寸，**必须直接硬编码在布局 XML 中**，严禁抽取。
- 使用清晰的 token 名称，而不是 Figma 图层名称。
- 如果语义上等效，请重用现有资源。
- **绝对禁止**创建纯别名颜色引用（如 `<color name="btn_white">@color/white</color>`）或对同一语义重复定义相同数值的 dimens（如两处 12dp 的边距应统一提取为 `space_12`，严禁产生冗余碎片）。

- **颜色命名强制使用十六进制字面量格式**：`color_` + 大写的 HEX 色值（如 `<color name="color_FFFF86FC">#FFFF86FC</color>`）。绝对禁止使用语义化命名（如 `color_bg_page`）。
- **色彩无脑复用**：得益于十六进制字面量命名，只要以后遇到相同的 HEX 色值，**必须直接无脑复用**已有的 `color_HEX` 资源，严禁为了不同组件（如按钮、边框）去重复定义数值相同的颜色。

强制的命名规范 (Mandatory Naming Convention)：
```xml
<color name="color_FFFFFFFF">#FFFFFFFF</color>
<color name="color_FF111827">#FF111827</color>
<color name="color_FF6B7280">#FF6B7280</color>
<color name="color_FF2563EB">#FF2563EB</color>
```
```xml
<dimen name="space_4">4dp</dimen>
<dimen name="space_8">8dp</dimen>
<dimen name="space_12">12dp</dimen>
<dimen name="space_16">16dp</dimen>
<dimen name="radius_12">12dp</dimen>
<dimen name="height_button_48">48dp</dimen>
<dimen name="text_size_16">16sp</dimen>
<dimen name="line_height_24">24sp</dimen>
```

### 2. 文本样式
如果项目没有既定规范，请在 `styles.xml` 中定义文本样式。
- **按需抽取 Style**：只有当同一种文本外观在页面中**被多次重复使用时**，才将其抽取到 `styles.xml`（如 `TextAppearance.App.*`）。
- 对于仅出现一次的孤立文本样式，**必须直接将属性（如 `textSize`、`textColor`）内联写在布局 XML 中**，严禁制造无用的单次使用 Style。

文本保真度规则：
- 设置 `android:includeFontPadding="false"`，除非项目规范或设计确实需要默认的字体内边距。
- 当 Figma 中提供了对应属性时，请务必还原 `fontFamily`、`textSize`、`textColor`、`textStyle` 和 `letterSpacing`。
- **关于行高 (`lineHeight`)**：只有多行段落文本才允许还原行高；**单行居中文本（如按钮、标签）严禁添加 `lineHeight`**（会导致文字被裁剪或无法居中，[见全局红线：单行文字行高陷阱](00-global-redlines.md#trap-11-line-height)）。
- **关于文字阴影 (`shadowDx/shadowDy/shadowRadius`)**：这 3 个属性在 Android 中读取的是 float，**必须直接写数字字面量**（如 `0`、`1`、`2`）。**严禁引用 `@dimen/...`**，也严禁写成 `1dp` / `2sp`，否则可能在 inflate 时触发 `NumberFormatException`（[见 shadow 浮点陷阱](00-global-redlines.md#trap-shadow-floats)）。
- 如果缺少确切的字体文件，请使用最接近的可用字体，并明确报告该偏差 (gap)。
- 对于多行文本，如果指定了行高和最大行数，请保留。

示例：
```xml
<style name="TextAppearance.App.Title20">
    <item name="android:fontFamily">@font/inter_semibold</item>
    <item name="android:textSize">@dimen/text_size_20</item>
    <item name="android:textColor">@color/color_FF111827</item>
    <item name="android:includeFontPadding">false</item>
</style>
```

若需要阴影，请写成：
```xml
<item name="android:shadowDx">0</item>
<item name="android:shadowDy">1</item>
<item name="android:shadowRadius">2</item>
```

### 3. Drawable 和 Selector 资源
对于 Figma 的填充 (fills)、描边 (strokes) 和圆角 (corners)，创建 shape drawables：
```xml
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/color_FFFFFFFF" />
    <corners android:radius="@dimen/radius_16" />
    <stroke
        android:width="@dimen/stroke_1"
        android:color="@color/color_FFD1D5DB" />
</shape>
```

对于按钮和有状态的组件，**必须使用选择器 (selectors) 并提供 `state_pressed` 状态，严禁用静态 `<shape>` 敷衍**，也不要用代码进行运行时控制 (runtime hacks)：
- `selector_button_primary.xml`
- `selector_input_border.xml`
- `selector_card_background.xml`

谨慎地近似还原 Figma 的阴影效果。XML View 系统的阴影能力有限；使用 `elevation` 实现类似 Material 风格的阴影，使用多层 drawable 实现简单阴影。如果确切的阴影需要自定义 drawable/view，请在文档中注明。

### 4. 位图切图的搬运与拦截机制 (Asset Porter)
当需要从临时目录（如 Figma 插件下载的图片）复制 `.png` 或 `.webp` 等位图切图到 Android 项目时，**绝对禁止使用 `cp` 或 `mv` 命令**。
- **目标目录强制推导**：请回顾 `00-global-redlines.md` 中的【位图资源目录陷阱】。严禁大模型自行猜测或计算密度！
  必须从 `.env` 中读取 `TARGET_BITMAP_DENSITY`（如 `xxhdpi`）：
  - **对于普通切图**：传入 `res/drawable-{TARGET_BITMAP_DENSITY}/`。
  - **对于桌面启动图标**：传入 `res/mipmap-{TARGET_BITMAP_DENSITY}/`。
- **强制指令**：必须执行 `python3 scripts/copy_and_optimize.py <原始图片路径> <计算出的目标工程路径/xxx.png>`。
- **动态 XML 编写依据**：执行后，你必须仔细阅读控制台（stdout）打印的字眼：
  - 若包含 `[SUCCESS]`：说明压缩通过，请在 XML 中正常使用 `android:src="@drawable/..."`。
  - 若包含 `[SKIPPED]`：说明该图片超出了 100KB 红线被拦截。你**不能**在 XML 中使用 `@drawable/` 引用它，**必须**改为使用 `tools:src="@tools:sample/backgrounds/scenic"` 占位，并在你最终的 `walkthrough.md` 报告中明确通知用户：“因图片过大被拦截，请改用网络加载”。

### 5. 其次生成 XML 布局

将 `ConstraintLayout` 作为复杂界面的默认根布局。

#### 1. 布局规则：
- 根屏幕：通常是 `android:layout_width="match_parent"` 和 `android:layout_height="match_parent"`。
- 在 `ConstraintLayout` 内部，对于应该在约束之间拉伸的尺寸使用 `0dp`。除非有特定的项目原因，否则 `ConstraintLayout` 内部子视图不要使用 `match_parent`。
- 文本高度应使用 `wrap_content`，除非设计明确要求固定高度。
- 避免将 Figma 上的绝对 x/y 坐标生硬转换为一大堆固定的 margins。
- 避免过深的 `LinearLayout` 嵌套。
- 仅对于简单垂直/水平组（能提高清晰度时）使用 `LinearLayout`。
- 将 `FrameLayout` 用于覆盖层、角标、遮罩或堆叠内容。
- 将 `RecyclerView` 用于重复内容，并创建单独的 `item_*.xml` 文件。
- 仅当整个页面滚动并且没有大的/重复的列表时才使用 `NestedScrollView`。
- 文本必须遵守严格启发式分类：**纯数字**(如 3970)、**动态实体名词**(如 jiangyuanjian)、**长句段落**(字符长度≥10) 必须且只能使用 `tools:text`。只有确定的**不可变短标签**(如 Follow, Cancel) 才允许使用 `android:text`。绝对严禁混用。
- 保持 ID 含义明确：`titleText`、`primaryButton`、`bannerImage`、`contentRecyclerView`。

#### 2. 约束规则：
- 将各个区块锚定到其兄弟视图或父视图的约束上，而不是任意的坐标定位。
- 对于固定比例的图像/卡片使用 `app:layout_constraintDimensionRatio`。
- 对于需要均匀分布的水平或垂直项，使用 ConstraintLayout 的 Chain。
- 当长动态文本影响对齐时使用屏障 (barriers)。
- 仅当设计确实基于固定百分比，或者需要多个视图共享同一条对齐基准线时，才使用 Guideline。

#### 3. Figma 到 XML 转换规则
除非项目约定覆盖它们，否则使用这些映射：

| Figma Concept (Figma 概念) | Android XML Implementation (实现) |
|---|---|
| Vertical Auto Layout | 简单组使用 `LinearLayout vertical`；复杂组使用 `ConstraintLayout` |
| Horizontal Auto Layout | 简单组使用 `LinearLayout horizontal`；自适应对齐使用 `ConstraintLayout` |
| Fill container | `0dp` + 约束，或根节点 `match_parent` |
| Hug contents | `wrap_content` |
| Fixed size | 命名的 `@dimen/...`（孤立尺寸硬编码。⚠️严禁将横向弹性文本宽度写死，必须用 `0dp` 配合约束或 `weight=1`） |
| Gap | Margin 或父级 Padding（按需抽取：复用≥2次才引用 `@dimen/...`，孤立尺寸直接硬编码） |
| Padding | 来自 `@dimen/...` 的父级 `android:padding*`（按需抽取：复用≥2次才引用，孤立尺寸直接硬编码） |
| Overlay / Badge | `FrameLayout` 或带约束的叠加层 |
| Figma image Fill | `ImageView android:scaleType="centerCrop"` |
| Figma image Fit | `ImageView android:scaleType="fitCenter"` |
| Small Icon (尺寸≤48dp 或含 `ic_` 命名) | `ImageView` 强制写明 `scaleType="fitCenter"` 或 `"centerInside"` |
| Small Icon with Transparent Frame (如 48px 包裹 38px) | 必须使用最轻量 `<FrameLayout>` 取大尺寸作热区，嵌套 `ImageView` 取小尺寸并 `layout_gravity="center"`。严禁拍扁，严禁使用 RelativeLayout！ |
| Icon SVG | 转换为 VectorDrawable XML |
| Button variants | `style` + `<selector>` (background) + `<selector>` (text color) |
| Input variants | `<selector>` (background/border) + helper/error text |

#### 4. 系统栏 (System bars) 和内边距 (insets)
- 首先必须判断 Figma frame 是否把状态栏和导航栏也画进去了。
- 如果 Figma frame 包含系统栏，请不要在 XML 中重复它们的空间。
- 如果 Figma frame 不包含系统栏，请确保 Activity/Fragment 正确处理了 WindowInsets 或遵循了现有项目的 edge-to-edge 规范。
- 如果 targetSdk 是 35 或更高版本，请显式检查 edge-to-edge 行为是否影响屏幕。
- 不要擅自添加顶部/底部的 padding，必须解释清楚它是为了系统栏避让、工具栏高度还是纯粹的内容间距。
