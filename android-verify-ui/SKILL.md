---
name: android-verify-ui
description: 手动独立执行的 Android UI 实机、设计与无障碍表现验收闭环。用于涉及 XML、Compose、Adapter、资源、主题、页面状态、交互控件、字体或 semantics 的改动，通过真机截图、Android CLI/adb、TalkBack 或人工对比验证布局、设计还原和 A11y 表现。用户明确要求验收 UI、设计稿、视觉偏差或无障碍体验时使用；不得由交付 route 自动调用，Journey、截图和自动 A11y 测试归 android-test-and-fix。
---

# Android UI 实机与设计验收

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`。

## 职责边界

- **负责**：验证用户实际可见的布局、排版、间距、资源、页面状态、轻交互、设计还原和人工/设备 A11y 表现。
- **执行方式**：用户手动单独调用；总交付流程只能提示，不得自动触发。
- **不负责**：接口、Repository、数据存储、权限、支付、提交等不可由画面证明的业务正确性。
- **验证底线**：没有真实真机截图、设备结果或可对比设计基准时，只能报告 `UNVERIFIED/BLOCKED`，不能声称完成截图级、实机或设计一致性验收。
- **相对独立**：不调用 `android-test-and-fix` 的执行脚本；只读取其报告或截图证据。以后新增的截图采集、布局检查或视觉对比脚本必须放在本 Skill 的 `scripts/` 下。
- **A11y 边界**：本 Skill 检查截图、布局树、TalkBack 和人工体验；Compose/Espresso semantics、AccessibilityChecks 等自动测试仍由 `android-test-and-fix` 定义和执行。

## 内置资源

- `references/`：设计检查表和最终报告模板。

## 输入解析

优先读取并解析以下设计资料（按优先级排序）：

1. **Figma MCP 结构化数据**：优先读取 design context、metadata、variables/styles、component variants、selected frame screenshot 和 asset export information。
2. **本地 Figma 基准截图**：优先读取已登记到 `ui.screenshots`、`ui.directory` 或 `<requirement_dir>/ui/` 的本轮 PNG，也可以读取 `figma_workflow.py fetch` 终端输出的实际路径。截图只提供视觉基准，不得声称包含结构化设计令牌。
3. **设计链接**：Figma、蓝湖、即时设计、摹客、MasterGo。
4. **UI 截图目录**：`ui.directory`，目录内可包含整页截图、局部截图、状态截图或标注图。
5. **截图或设计文件**：PNG、JPG、PDF、SVG、ZIP。
6. **资源文件**：图标、图片、字体、动效。

如果需要从 Figma 链接获取本地视觉基准，可以运行：

```bash
python3 ai-skills/figma-android-xml/scripts/figma_workflow.py fetch "FIGMA_URL" --scale 1
```

该命令只下载 PNG 并输出实际保存路径，不生成结构化标注、HTML 或 XML；多个链接必须在同一次调用中传入，避免后一次执行清理前一次缓存。PNG 只作为视觉比对辅助，最终 UI 结果以 Figma 链接、真机截图/差异图链接和人工结论为准，不要求登记截图 SHA-256 或 APK 身份。结构化数据仍以实际读取到的 Figma MCP 为准；缺少结构化数据时可以进行截图级对比，但不得声称已核对未读取的设计令牌。

## UI 截图目录规则

当用户提供 UI 截图目录时，优先读取目录内截图作为 UI 参考。

- 同时提供设计链接和 UI 截图目录时，设计链接是主要 UI 基准，截图目录用于辅助定位目标页面、区域、状态或标注范围。
- 如果截图与设计链接存在冲突，必须报告冲突并等待确认，不能自行选择。
- 只有未提供设计链接时，才默认按截图本身作为主要 UI 参考。
- 整页截图：按整页 UI 参考。
- 局部截图：默认只改该局部区域。
- 带红框、箭头或标注的截图：只按标注区域处理。
- 多张截图：按文件名、截图内容和状态自动识别，例如 normal、empty、error、loading。
- 无法唯一判断页面、区域或状态时，必须暂停确认，不得自行选择。
- 截图只能表达 UI，不得据此脑补接口、业务规则或真实功能。

## 真机截图与 Figma 比对规则

- Figma Frame 链接是视觉基准；真机截图是当前验收结果，必要时附差异图链接。
- 真机验收开始前必须运行共享设备预检：`adb devices -l` 至少有一个状态为 `device` 的物理设备；多设备时必须指定 `serial`，模拟器不能作为真机视觉 `PASS`。
- 推荐使用 `python3 ai-skills/android-delivery-skills/scripts/device_preflight.py --require-physical --device <serial> --screenshot <path>`，预检会继续校验 `adb get-state` 和 PNG 截图命令是否成功。
- `device_check` 必须直接采用预检脚本输出，不得手工编造；设备连接语义以 [Google adb 设备状态](https://developer.android.com/tools/adb?hl=zh-cn#devicestatus) 和 [Google 硬件设备测试指南](https://developer.android.com/studio/run/device?hl=zh-cn) 为准。
- 固定文案、颜色、图标、布局、间距、圆角和排版按严格视觉对比；默认不把所有动态内容放宽。
- 动态业务内容优先使用固定测试数据；如果只验证布局，使用代表性长文本或空/错误状态。
- 动态业务内容必须使用固定测试数据；系统状态栏、分辨率和方向必须与验收基准一致。无法控制或对齐的区域只能记录为未验证，不能直接忽略后写 `PASS`。
- 动画等待稳定后截图；Figma Frame 与目标真机分辨率/方向不一致时先记录差异，不用跨尺寸截图做像素级结论。
- 不要求 APK hash、versionCode、安装收据、执行人、带时区时间或逐步人工收据；这些不属于 UI 视觉验收的必要输入。

## 设备前置条件

- 设备预检是 UI 真机截图验收的第一步，不是 route、构建或普通单元测试的前置条件。
- 预检结果为 `READY`、设备类型为 `PHYSICAL` 且截图命令成功后，才允许视觉结果写 `PASS`。
- 没有设备、设备未授权、设备离线、多设备未指定或截图失败时，UI 结果写 `UNVERIFIED`/`BLOCKED`，并说明原因；最终交付沿用 `LOCAL_PASS_DEVICE_PENDING`，不伪造 `FULL_PASS`。
- 预检只记录设备序列号、物理/模拟器类型和截图是否成功，不记录 APK hash、versionCode、安装收据或截图 SHA-256。

## 使用边界

- 没有 UI 改动：跳过本 Skill。
- 有 UI 改动但没有设计稿、截图或可对比基准：不能执行设计一致性验收，输出 `UNVERIFIED/BLOCKED` 等待基准；不得用静态 UI 检查替代真机截图对比。
- 有 UI 改动且存在可访问设计稿、截图或可对比基准：使用本 Skill 做 UI 还原验证。
- A11y 自动测试归 `android-test-and-fix`；本 Skill 只在设备上补充布局树、TalkBack 或人工体验，不能用静态语义检查替代视觉验收。

## 项目 UI 事实识别

验收时必须确认：

- 当前项目使用 XML、ViewBinding、DataBinding、Compose 或混合。
- 是否已有 Design System、Theme、Color、Typography、Dimens、公共组件。
- 文案、颜色、尺寸、图片资源应该放在哪里。
- 是否已有 Paparazzi、Roborazzi、Shot 等测试产出的截图证据；只读取结果，不在本 Skill 中定义或执行测试用例。
- 是否有现成页面、组件、Adapter、Composable 可复用。

## Design Spec Gate

在开始验收前，如果实现阶段已有 Design Spec Gate，先读取并核对；没有时根据实际可读资料建立精简验收基准，不生成或修改 XML。优先参考 `references/figma-spec-report.md`，至少覆盖：

1. Target screen：frame 名称、frame 尺寸、Android baseline width、是否包含状态栏/导航栏、是否滚动。
2. Resource tokens：colors、dimensions、typography、radius/stroke/shadow。
3. Layout structure：root 选择、主要区块、列表项、overlay。
4. Component mapping：Figma 组件映射到 Android View / 资源 / 状态。
5. Assets：图片导出格式、VectorDrawable 转换项、`scaleType`。
6. Risks / assumptions：字体缺失、状态缺失、阴影近似、system bars 不确定项。

## UI 还原验收规则

- 检查实现是否优先复用了项目已有主题、组件、颜色、尺寸、文字样式和资源管理方式。
- Figma + XML View 的 UI 生产结果由 `figma-android-xml` 提供；本 Skill 只消费设计基准、生成的 XML/资源和运行截图做验收，不复制其生成步骤或重新生成 UI。
- 当存在可访问设计资料时，以视觉和交互目标为验收基准，并检查实现是否遵守项目已有 Design Token、组件和主题。设计资料与项目体系冲突时报告具体差异，不自行牺牲任一方。
- 文案放入字符串资源或项目既有多语言体系。
- 颜色、字号、间距、圆角、阴影优先使用项目 design token 或资源文件。
- 避免无依据的颜色和尺寸魔法值；优先复用现有 Token。是否抽取新资源服从项目约定和复用价值，不为一次使用制造重复别名。
- 如果设计稿与项目设计体系冲突，必须先报告冲突并等待确认。
- 必须覆盖正常、加载、空数据、错误、禁用、选中、未登录、无权限等状态中与需求相关的状态。

## 重点陷阱

- Figma 导出的图片即使扩展名是 `.png`，也可能实际是 SVG 内容；导入 Android 前必须检查格式，必要时转成 VectorDrawable。
- `ConstraintLayout` 中需要拉伸的子 View 优先用 `0dp` + constraints，不要无意识使用 `match_parent`。
- `LinearLayout` 中带 `layout_weight` 的子 View 使用 `0dp`，不要和 `match_parent` 混用。
- `targetSdk >= 35` 时必须额外检查 edge-to-edge / WindowInsets，避免内容被状态栏遮挡。
- 不要依赖 `duplicateParentState` 处理复杂 tab/button 选中态；状态复杂时优先显式更新图标、文字色和背景。
- 阴影、mask、复杂 blur、alpha mask 这类 Figma 效果在 View XML 中可能只能近似实现；如果需要像素级一致，必须明确记录偏差。

## A11y 表现验收

UI 或交互候选存在时同步检查；视觉结论必须有设计基准和真机画面：

- 非装饰图标、图片、按钮和自定义控件是否有准确语义；装饰元素是否从无障碍树排除。
- 可点击区域、焦点顺序、TalkBack 朗读、选中/禁用/错误/加载状态描述是否符合真实操作。
- 字体缩放后是否截断、重叠或失去操作入口，颜色是否成为唯一状态表达。
- Compose semantics 与 XML 属性是否和屏幕可见含义一致，不用技术类名代替用户语义。
- 引用 `android-test-and-fix` 已执行的 A11y 自动测试；有物理设备时再补布局树、TalkBack 或人工路径。

没有物理设备或截图失败时，不做静态 UI 兜底，动态焦点、TalkBack、触摸体验和视觉一致性统一标为 `UNVERIFIED/BLOCKED`；不得写成设计一致或 A11y 全面通过。

## 资料缺失时

- 没有设计稿但需求已明确：可以继续实现业务和交互，但 UI 专项必须保持 `UNVERIFIED/BLOCKED`；当前范围要求像素级还原却没有可比基准时，暂停视觉验收并请求资料。
- 没有正式接口但需求已明确：UI 依赖稳定领域模型，使用 Preview、Mock 或 debug Fake 展示需求中的正常、空、加载和失败状态；不得直接依赖猜测性正式 DTO 或把临时字段写成已确认接口事实。
- 正式 Figma、截图、资源或接口到达后，优先只调整资源、布局、视觉参数和数据适配；只改变视觉或传输字段时按同一需求局部完善，改变交互或业务语义时才进入需求修订并更新相关测试。
- 没有图片资源：使用占位资源或说明等待设计资源，不擅自从网络下载替代。

## 验证方式

用户单独调用本 Skill 后按以下顺序执行。Journey、Espresso、Compose UI Test 和 UIAutomator 等功能测试由 `android-test-and-fix` 负责；本 Skill 可引用其截图和测试结果作为视觉验收证据，但不得重新定义测试用例。

### Step 0:UI 适用性门禁

先读取需求与实际 diff。满足以下任一条件才进入真机视觉验收：修改 XML/Compose、Activity/Fragment 可见状态、Adapter/列表展示、drawable/color/dimen/string/theme、WindowInsets、动画或用户可见交互。

没有 UI 影响时：

1. 不运行 adb、截图或设计稿比对。
2. 输出 `SKIPPED_NO_UI`，列出判断依据和已检查的 diff。
3. 将构建、业务逻辑、接口和稳定性验证交给对应 Skill。

### 真机截图视觉验证

1. 执行设备预检，确认物理设备、`adb get-state` 和截图命令均成功。
2. 使用真机截图与 Figma/参考截图对比布局、排版、间距、组件、图像和系统栏。
3. 自动 A11y 测试由 `android-test-and-fix` 提供；需要设备体验时补充布局树、TalkBack 或人工路径。
4. 无设备、截图失败或缺少设计基准时，记录 `UNVERIFIED/BLOCKED`，不得输出设计一致或真机通过结论。

```
adb exec-out screencap -p > 当前页.png
  ↓
AI 视觉模型 + BDD 的 Then(验收标准) 作为断言 prompt
  ↓
输出: pass/fail + 哪个元素/状态不对 + 失败截图
  ↓
失败 → 先报告证据；用户明确要求修复后才改最小布局 → 重新截图 → 再验
```

- 对比时记录设备与分辨率，便于复看；这些信息不参与 APK/构建身份校验。
- 编码完成后,如存在设计稿、截图或 UI 目录,必须对照设计资料说明 UI 是否已按参考还原。如果没有实际运行截图,只能说明未做截图级验证。
  - **截图核心比对维度(按优先级)**:1. 布局结构 (根内边距/偏移/滚动区);2. 排版 (字重/字号/行高/基线);3. 间距 (内外/图文);4. 组件 (圆角/描边/背景);5. 图像 (裁剪比例);6. 系统栏沉浸式留白。

## 输出格式

每次调用都必须使用 `references/implementation-summary.md` 输出报告：

- 有 UI：包含 Figma/截图基准、真机截图或差异图链接、动态区域说明、偏差和结论；可引用 `android-test-and-fix` 的 Journey 报告作为功能辅助结果。
- 有 A11y 影响：增加语义、触摸区域、焦点、TalkBack、字体缩放、自动测试证据和未验证项。
- 无 UI：输出最小 `SKIPPED_NO_UI` 报告，不启动验证工具。
- 结论只能是 `PASS`、`FAIL`、`UNVERIFIED`、`SKIPPED_NO_UI` 或 `BLOCKED`；没有真机截图和可对比设计基准不得写 `PASS`，适用且必需的动态 A11y 没有证据时也不得写 `PASS`。

输出被完整交付引用时，同时按 `../android-implement-and-verify/references/specialist-result.schema.json` 写统一专项结果：`android-ui-a11y` capability 记录适用性和未验证原因，`device_check` 记录设备预检和截图命令结果，`visual_review` 记录 Figma 链接、真机截图/差异图链接和动态区域说明。UI 专项不使用通用 `MANUAL` 收据，也不绑定 APK、versionCode 或截图 SHA-256。`UNVERIFIED`、`SKIPPED_NO_UI` 分别表示未完成验证、无 UI 影响；二者都不得冒充动态 UI `PASS`。
