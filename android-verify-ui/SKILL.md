---
name: android-verify-ui
description: 手动独立执行的 Android UI 实机、设计与无障碍表现验收闭环。用于涉及 XML、Compose、Adapter、资源、主题、页面状态、交互控件、字体或 semantics 的改动，通过截图、Android CLI/adb、静态检查、TalkBack 或人工对比验证布局、设计还原和 A11y 表现。用户明确要求验收 UI、设计稿、视觉偏差或无障碍体验时使用；不得由交付 route 自动调用，Journey、截图和自动 A11y 测试归 android-test-and-fix。
---

# Android UI 实机与设计验收

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

默认用于编码后处理 UI 链接、截图、设计稿、页面视觉还原和人工/设备 A11y 表现，目标是审查实际实现是否符合设计稿、项目设计体系和可访问性要求，而不是让 AI 自由发挥。没有设计稿、截图或可对比基准时不进入设计稿一致性验证，但 A11y 候选仍按静态或设备能力检查。只有关键设计资料缺失、继续编码会误实现时，才在编码前暂停确认。

## 职责边界

- **负责**：验证用户实际可见的布局、排版、间距、资源、页面状态、轻交互、设计还原和人工/设备 A11y 表现。
- **调用**：存在 UI diff 且有设计稿、截图、设备、截图基准，或用户明确要求验收 A11y 表现时。
- **执行方式**：用户手动单独调用；总交付流程只能提示，不得自动触发。
- **不负责**：接口、Repository、数据存储、权限、支付、提交等不可由画面证明的业务正确性。
- **验证底线**：没有真实截图或设备结果时，只能报告静态检查，不能声称完成截图级或实机验收。
- **相对独立**：不调用 `android-test-and-fix` 的执行脚本；只读取其报告或截图证据。以后新增的截图采集、布局检查或视觉对比脚本必须放在本 Skill 的 `scripts/` 下。
- **A11y 边界**：本 Skill 检查截图、布局树、TalkBack 和人工体验；Compose/Espresso semantics、AccessibilityChecks 等自动测试仍由 `android-test-and-fix` 定义和执行。

## 内置资源

- `references/`：设计检查表和最终报告模板。

## 输入解析

优先读取并解析以下设计资料（按优先级排序）：

1. **Figma MCP 结构化数据**：优先读取 design context、metadata、variables/styles、component variants、selected frame screenshot 和 asset export information。
2. **本地 Figma 离线标注**：如果项目下存在由 `ai-skills/figma-android-xml/scripts/export_figma.py` 导出的离线标注数据（如 `ai-skills/tempfile/[file_key]_[node_id]_spec.json` 或 `ai-skills/tempfile/index.html`），读取它作为 MCP 的兜底快照或对照来源。读取前必须先检查 `source.exported_at` 字段：超过 4 小时须对比 Figma `lastModified` 确认是否过期；超过 24 小时须在 Design Spec Gate 标注 `⚠️ 数据可能过期` 并等用户确认。
3. **设计链接**：Figma、蓝湖、即时设计、摹客、MasterGo。
4. **UI 截图目录**：`ui.directory`，目录内可包含整页截图、局部截图、状态截图或标注图。
5. **截图或设计文件**：PNG、JPG、PDF、SVG、ZIP。
6. **资源文件**：图标、图片、字体、动效。

如果 MCP 不可用、链接无法访问且未提供本地离线标注，必须说明缺失项并提示用户运行以下命令生成本地离线标注：

```bash
# 正常运行（自动检查新鲜度，数据未变则跳过下载）
python3 ai-skills/figma-android-xml/scripts/export_figma.py "FIGMA_URL"

# 强制重新拉取（设计师刚改完稿时使用）
python3 ai-skills/figma-android-xml/scripts/export_figma.py "FIGMA_URL" --force
```

可以建议先做 UI 骨架，但不得声称已做到和设计稿一致。

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

## 使用边界

- 没有 UI 改动：跳过本 Skill。
- 有 UI 改动但没有设计稿、截图或可对比基准：跳过设计稿一致性验证，只在其他后置审查中检查资源规范、明显布局风险和崩溃风险。
- 有 UI 改动且存在可访问设计稿、截图或可对比基准：使用本 Skill 做 UI 还原验证。
- A11y 候选不依赖设计稿；没有视觉基准时仍可执行静态语义检查，用户单独调用后可继续设备/TalkBack 验收。

## 项目 UI 事实识别

验证或实现时必须确认：

- 当前项目使用 XML、ViewBinding、DataBinding、Compose 或混合。
- 是否已有 Design System、Theme、Color、Typography、Dimens、公共组件。
- 文案、颜色、尺寸、图片资源应该放在哪里。
- 是否已有 Paparazzi、Roborazzi、Shot 等测试产出的截图证据；只读取结果，不在本 Skill 中定义或执行测试用例。
- 是否有现成页面、组件、Adapter、Composable 可复用。

## Design Spec Gate

在开始写 XML 前，如果设计资料可读，先输出一份精简 Design Spec Gate。优先参考 `references/figma-spec-report.md`，至少覆盖：

1. Target screen：frame 名称、frame 尺寸、Android baseline width、是否包含状态栏/导航栏、是否滚动。
2. Resource tokens：colors、dimensions、typography、radius/stroke/shadow。
3. Layout structure：root 选择、主要区块、列表项、overlay。
4. Component mapping：Figma 组件映射到 Android View / 资源 / 状态。
5. Assets：图片导出格式、VectorDrawable 转换项、`scaleType`。
6. Risks / assumptions：字体缺失、状态缺失、阴影近似、system bars 不确定项。

## UI 还原规则

- 优先复用项目已有主题、组件、颜色、尺寸、文字样式和资源管理方式。
- 编码阶段如存在可访问设计稿、截图或标注，必须尽量按设计资料实现布局、间距、颜色、字号、资源和状态。
- 当存在可访问设计资料时，以视觉和交互目标为基准，并优先通过项目已有 Design Token、组件和主题实现。设计资料与项目体系冲突时先报告具体差异，不自行牺牲任一方。
- 实现顺序默认是：resources → text styles → drawable/selector → layout XML → minimal Kotlin/ViewBinding，不要直接堆完整页面 XML。
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

UI 或交互候选存在时同步检查，不要求必须有设计稿：

- 非装饰图标、图片、按钮和自定义控件是否有准确语义；装饰元素是否从无障碍树排除。
- 可点击区域、焦点顺序、TalkBack 朗读、选中/禁用/错误/加载状态描述是否符合真实操作。
- 字体缩放后是否截断、重叠或失去操作入口，颜色是否成为唯一状态表达。
- Compose semantics 与 XML 属性是否和屏幕可见含义一致，不用技术类名代替用户语义。
- 优先引用 `android-test-and-fix` 已执行的 A11y 自动测试；有设备时再补布局树、TalkBack 或人工路径。

没有设备时继续静态 A11y 检查并输出 `STATIC_ONLY`，动态焦点、TalkBack 和触摸体验列为未验证；不得因此终止其他 UI 静态检查，也不得写 A11y 全面通过。

## 资料缺失时

- 没有设计稿：如果需求允许低风险实现，可以按项目现有组件风格处理；编码后不得输出“与设计稿一致”。如果要求像素级还原，必须暂停确认。
- 没有接口：只能使用 mock / preview / debug fake 展示状态，不写死正式字段。
- 没有图片资源：使用占位资源或说明等待设计资源，不擅自从网络下载替代。

## 验证方式

用户单独调用本 Skill 后按以下顺序执行。Journey、Espresso、Compose UI Test 和 UIAutomator 等功能测试由 `android-test-and-fix` 负责；本 Skill 可引用其截图和测试结果作为视觉验收证据，但不得重新定义测试用例。

### Step 0:UI 适用性门禁

先读取需求与实际 diff。满足以下任一条件才进入 L1-L4：修改 XML/Compose、Activity/Fragment 可见状态、Adapter/列表展示、drawable/color/dimen/string/theme、WindowInsets、动画或用户可见交互。

没有 UI 影响时：

1. 不运行 adb、截图或设计稿比对。
2. 输出 `SKIPPED_NO_UI`，列出判断依据和已检查的 diff。
3. 将构建、业务逻辑、接口和稳定性验证交给对应 Skill。

### 能力分层(自动嗅探,缺哪层降哪层)

| 层 | 能力 | 依赖 | 老项目可用 |
|---|---|---|---|
| L1 | 已有截图证据对比 | 测试报告、基准图和本次截图 | 视证据 |
| L2 | **Android CLI 设备验收** | `android layout/screen` + adb + 视觉模型 | ✅ |
| L3 | 静态 XML/Compose 检查 | 源码、设计基准 | ✅ 无设备兜底 |
| L4 | 人工截图对比 | 设备截图 + 人工确认 | ✅ 最终兜底 |

**固定顺序**：L1 → L2 → L3 → L4。环境失败时记录原因并降级，不得把工具或设备错误当成目标应用视觉缺陷。

### L1-L4:视觉验证

- L1：优先复用 `android-test-and-fix` 或项目已有流程产出的截图和基准图；不在本 Skill 中运行 Paparazzi、Roborazzi、Shot 或重新设计测试用例。
- L2：使用 `android layout --device` 获取结构，使用 `android screen capture` 或 adb 截图，再对照设计稿、截图基准和可见的 BDD Then 判断视觉结果。
- L3：无设备时执行 XML/Compose、资源、TextView、Insets 和状态覆盖静态检查，只能标记“静态通过”。
- L4：自动能力不覆盖的复杂视觉或交互状态，输出人工步骤、设备条件和预期视觉结果。

```
adb exec-out screencap -p > 当前页.png
  ↓
AI 视觉模型 + BDD 的 Then(验收标准) 作为断言 prompt
  ↓
输出: pass/fail + 哪个元素/状态不对 + 失败截图
  ↓
失败 → 先报告证据；用户明确要求修复后才改最小布局 → 重新截图 → 再验
```

- L2/L4 对比时必须记录设备、API、分辨率、density、字体缩放、语言、主题、方向、状态栏和导航栏。
- 如需静态复核,优先按 `references/xml-review-checklist.md` 逐项过一遍,再决定是否继续大改布局。
  - XML 涉及文本时，按需列出本次改动的 TextView 文本来源；Compose 则检查 stringResource、运行时状态和 Preview 数据。只审查受影响节点，不要求输出全页面控件清单。
- 编码完成后,如存在设计稿、截图或 UI 目录,必须对照设计资料说明 UI 是否已按参考还原。如果没有实际运行截图,只能说明未做截图级验证。
  - **截图核心比对维度(按优先级)**:1. 布局结构 (根内边距/偏移/滚动区);2. 排版 (字重/字号/行高/基线);3. 间距 (内外/图文);4. 组件 (圆角/描边/背景);5. 图像 (裁剪比例);6. 系统栏沉浸式留白。

## 输出格式

每次调用都必须使用 `references/implementation-summary.md` 输出报告：

- 有 UI：包含基准、环境、引擎降级链、命令、截图、偏差、自修复、未验证项和结论；可引用 `android-test-and-fix` 的 Journey 报告作为辅助证据。
- 有 A11y 影响：增加语义、触摸区域、焦点、TalkBack、字体缩放、自动测试证据和未验证项。
- 无 UI：输出最小 `SKIPPED_NO_UI` 报告，不启动验证工具。
- 结论只能是 `PASS`、`STATIC_ONLY`、`SKIPPED_NO_UI` 或 `BLOCKED`；没有实机/截图证据不得写 `PASS`，适用且必需的动态 A11y 没有证据时也不得写 `PASS`。
