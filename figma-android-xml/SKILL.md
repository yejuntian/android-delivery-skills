---
name: "figma-android-xml"
description: "从 Figma MCP 提取设计令牌/资源，映射组件，然后使用 ConstraintLayout 生成高保真 Android XML 布局，并通过差异对比修复问题。"
---

# Figma → Android XML 高保真实现

当用户要求根据 Figma 设计稿实现、还原、转换、审查或优化 Android **XML 视图系统** UI 时，尤其是在用户非常看重高视觉还原度时，请使用此技能。

此技能**不是**一个“一把梭”的 Figma 转代码生成器。它强制执行以下 6 步工作流：

1. **阶段 1**：读取和标准化 Figma 设计数据。
2. **阶段 2**：提取组件映射并盘点（输出设计规范报告）。
3. **阶段 3**：优先生成核心基础资源（颜色/形状）并生成纯内联 XML 布局 (Inline-First)。
4. **阶段 4**：基于实际生成的布局，重构并按需抽取复用资源（尺寸/排版）。
5. **阶段 5**：生成辅助布局 (如 `item_*.xml`) 并利用 `tools:` 命名空间完善可视化预览，**绝不编写 Kotlin 业务逻辑**。
6. **阶段 6**：使用 build/lint 进行代码编译验证与人工布局审查（**必须读取并执行 `checklists/xml-review-checklist.md`**）。

除非用户明确要求，否则**不要**切换到 Jetpack Compose。

## 核心原则

- 将 Figma 视为设计规范，而不是绝对定位的代码。
- 优先使用 Android 资源引用，而不是硬编码值。
- 优先使用 `ConstraintLayout` 处理复杂屏幕和浅层视图层级。
- 保留间距、排版、圆角半径、图像缩放类型、组件状态和系统栏假设。
- 永远不要隐瞒不确定性。如果缺少 Figma 数据、资产、字体或状态，请明确指出缺失部分并选择风险最小的实现。
- 在生成设计规范和资源计划之前，不要一次性生成庞大的最终布局代码。

## 执行纪律 (Execution Workflow)

- **全局红线先决**：启动任务必须首发读取 `rules/00-global-redlines.md`，无红线上下文严禁写码。
- **手册懒加载**：严格按 1→6 阶段流转，进新阶段前必读 `rules/0N-*.md`，严禁盲跑。
- **禁阶段性停顿**：1→6 阶段必须连贯执行，严禁因“完成某步”或长输出截断而中断等待。
- **视觉续跑红线**：调用图片查看工具返回后，必须立即通过新工具调用推进流程，绝不可把看图当终点。
- **工具续跑门禁**：阶段 1→6 未全部完成前，任何工具返回后都不得用自然语言收尾；下一条响应必须继续发起工具调用或进入最终验证。尤其是 `view_image`/`view_file` 返回后，下一条必须是工具调用，除非已完成阶段 6 或遇到真阻塞。
- **纯文字停顿禁令**：阶段 1→6 未完成前，严禁单独发送“已完成/继续吗/我将继续/抱歉原因说明”等纯文字作为回合终点；若需要解释，必须同一回合紧跟下一次工具调用。用户被迫发送“继续”即视为流程失败，必须立刻续跑而不是再次解释。
- **真阻塞条件**：仅在外部死锁（无权限、核心资源缺失）且无法自行诊断修复时，才允许停顿求助。

## 🖼️ 自动化拉取与视觉感知 (Figma Fetcher)
如果用户提供了多个 Figma 链接：
1. 您必须在后台静默执行 `python scripts/figma_workflow.py fetch [链接1] [链接2]... --scale 1` 来下载原图。
2. 下载完成后，控制台会输出图片保存的真实路径（如 `.../tempfile/figma-android-xml`）。**您必须主动根据控制台输出的路径，使用 `view_file` 工具读取这些刚下载的 `.png` 图片**，从而真正“看”到设计稿的颜色、渐变和布局细节。
3. 必须将这些导出的图片视为视觉参考和对比 baseline，而不是默认的最终 UI 资产。

## 触发示例 (Invocation Examples)
```text
/figma-android-xml https://www.figma.com/design/... Login screen activity_login.xml
```
```text
/figma-android-xml 请根据当前 Figma Frame 实现 res/layout/fragment_product_detail.xml，仅生成 XML 和相关资源，不要用 Compose。
```
```text
/figma-android-xml 对比 figma.png 和 actual.png，只列出 XML 还原差异并修复必要资源和布局。
```
$ARGUMENTS
