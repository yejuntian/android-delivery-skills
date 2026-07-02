---
name: android-ui-verify
description: Android 编码后的 UI 还原验证流程。适用于 AI 或人工完成涉及 XML、ViewBinding、DataBinding、Compose、Adapter、资源、主题或页面状态的 Android 改动，且存在可访问设计稿、截图、资源文件或其他可对比 UI 基准时，基于设计资料和实际实现审查 UI 状态、资源规范、截图对比和视觉差异；没有设计稿、截图或可对比基准时默认不做设计稿一致性验证，只在关键设计资料缺失且继续编码会误实现时用于编码前阻塞确认。
---

# Android UI 还原验证

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

默认用于编码后处理 UI 链接、截图、设计稿和页面视觉还原，目标是审查实际实现是否符合设计稿和项目设计体系，而不是让 AI 自由发挥。没有设计稿、截图或可对比基准时，不进入设计稿一致性验证，只在变更审查、稳定性审查或代码质量审查中做必要的 UI 基础检查。只有关键设计资料缺失、继续编码会误实现时，才在编码前暂停确认。

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

## 项目 UI 事实识别

验证或实现时必须确认：

- 当前项目使用 XML、ViewBinding、DataBinding、Compose 或混合。
- 是否已有 Design System、Theme、Color、Typography、Dimens、公共组件。
- 文案、颜色、尺寸、图片资源应该放在哪里。
- 是否已有截图测试框架，例如 Paparazzi、Roborazzi、Shot。
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
- 当存在可访问设计稿、截图、UI 目录或标注时，编码阶段必须以“尽量一比一还原”为目标实现 UI，包括布局层级、间距、颜色、字号、圆角、图片、文案和可见状态；不得自由发挥或改成项目通用样式。只有当设计资料缺失、项目资源体系冲突或平台限制导致无法还原时，才允许说明原因后做近似实现。
- 实现顺序默认是：resources → text styles → drawable/selector → layout XML → minimal Kotlin/ViewBinding，不要直接堆完整页面 XML。
- 文案放入字符串资源或项目既有多语言体系。
- 颜色、字号、间距、圆角、阴影优先使用项目 design token 或资源文件。
- **严禁 UI 魔法值底线**：除了全局禁止的硬编码字符串，进一步严禁在 XML/Compose 中写死 Hex 颜色值（如 `#FF0000`）和非标准的硬编码尺寸。必须强制抽取并引用 `colors.xml` / `dimens.xml` 或现有的 Theme Token，代码审查时对魔法值零容忍。
- 如果设计稿与项目设计体系冲突，必须先报告冲突并等待确认。
- 必须覆盖正常、加载、空数据、错误、禁用、选中、未登录、无权限等状态中与需求相关的状态。

## 重点陷阱

- Figma 导出的图片即使扩展名是 `.png`，也可能实际是 SVG 内容；导入 Android 前必须检查格式，必要时转成 VectorDrawable。
- `ConstraintLayout` 中需要拉伸的子 View 优先用 `0dp` + constraints，不要无意识使用 `match_parent`。
- `LinearLayout` 中带 `layout_weight` 的子 View 使用 `0dp`，不要和 `match_parent` 混用。
- `targetSdk >= 35` 时必须额外检查 edge-to-edge / WindowInsets，避免内容被状态栏遮挡。
- 不要依赖 `duplicateParentState` 处理复杂 tab/button 选中态；状态复杂时优先显式更新图标、文字色和背景。
- 阴影、mask、复杂 blur、alpha mask 这类 Figma 效果在 View XML 中可能只能近似实现；如果需要像素级一致，必须明确记录偏差。

## 资料缺失时

- 没有设计稿：如果需求允许低风险实现，可以按项目现有组件风格处理；编码后不得输出“与设计稿一致”。如果要求像素级还原，必须暂停确认。
- 没有接口：只能使用 mock / preview / debug fake 展示状态，不写死正式字段。
- 没有图片资源：使用占位资源或说明等待设计资源，不擅自从网络下载替代。

## 验证方式

按项目能力选择：

- 已有截图测试：优先运行项目现有截图测试命令。
- 无截图测试：可用 emulator / adb 截图辅助人工对比。
- 可用命令示例需以项目实际模块为准，例如构建、安装、启动、`adb exec-out screencap -p`。
- 对比时必须说明设备、分辨率、字体缩放、系统主题、状态栏和导航栏影响。
- 如需静态复核，优先按 `references/xml-review-checklist.md` 逐项过一遍，再决定是否继续大改布局。
- 编码完成后，如存在设计稿、截图或 UI 目录，必须对照设计资料说明 UI 是否已按参考还原；没有实际运行或截图对比时，不得声称“完全一致”，只能说明“按设计资料实现，未做截图级验证”。

## 输出格式

1. UI 资料解析
2. 项目 UI 技术事实
3. 设计状态清单
4. 可复用组件和资源
5. 可先做 / 待确认
6. 实现约束
7. 截图或视觉验证计划
8. UI 差异或潜在差异
9. 是否需要用户确认
