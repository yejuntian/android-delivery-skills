# Figma Android XML 产物交接

## 适用条件

同时满足以下条件时，总入口才调用 `figma-android-xml`：

1. 当前需求已确认，实施计划和影响半径已确认。
2. 用户提供可访问的 Figma 链接、Frame 或结构化设计资料。
3. 目标页面使用 XML View，或混合项目中明确属于 XML 页面。
4. 计划允许修改目标 layout、drawable、values、字体或位图资源路径。

Compose 页面不得为了使用该 Skill 新增 XML/ViewBinding 或改变项目技术栈。

## 职责边界

- `figma-android-xml` 读取设计、生成 XML/资源、执行 XML 级 build/lint 和静态清单，不写 Kotlin/Java 业务逻辑。
- `android-implement-and-verify` 检查产物范围，按项目既有 Design System、I18n、A11y 和架构约定接入业务逻辑。
- `android-test-and-fix` 执行功能、Journey、截图和自动 A11y 测试。
- `android-verify-ui` 使用物理设备截图与 Figma 基准做独立视觉验收。
- 生成成功只表示得到候选实现，不能替代测试或 UI 验收 PASS。

外部 Skill 的局部生成习惯不能覆盖目标项目事实。颜色命名、尺寸资源、ConstraintLayout、Insets、字符串和 selector 规则与项目现有体系冲突时，先遵守项目约定并记录差异；无法兼容时等待用户确认，不静默扩大范围。

外部 Skill 的设计规范、检查表和 walkthrough 只输出在当前会话或需求级 `.state/` 证据目录，不写入目标项目可跟踪路径。若 provider 新增项目内报告、辅助代码或其他未声明文件，前后快照校验必须阻断。

## 执行顺序

1. 从当前配置读取 `ui.links`、本地截图和设计目录，确认 Figma 输入已进入 `requirement_inputs_sha256`。
2. 读取目标项目的 XML、资源、Theme、Design System 和相邻页面，不从 Figma 节点名猜业务语义。
3. 在调用外部 Skill 前执行 `figma_xml_handoff.py snapshot`，记录当前 Git worktree 中全部已跟踪和未忽略文件的摘要。
4. 调用 `figma-android-xml` 完成其阶段流程，只允许修改影响半径内的 XML 和资源。
5. 按 `figma-xml-result.schema.json` 生成 `.state/evidence/.../figma-xml-result.json`。
6. 执行 `figma_xml_handoff.py validate` 校验前后差异、产物类型和影响半径；失败时不得接入业务逻辑。
7. 总入口检查并接管 XML，补业务代码、测试和新鲜执行收据。
8. 最终交付时独立执行 `android-verify-ui`；旧 Figma 报告或 Android Studio Preview 不算真机视觉证据。

交接校验必须传入当前交付上下文，不能从交接 JSON 自证新鲜：

```bash
python3 scripts/figma_xml_handoff.py snapshot \
  --project <Android项目Git-worktree根目录> \
  --output <requirement_dir>/.state/figma-xml-before.json

# 调用 figma-android-xml 并生成交接 JSON 后执行：
python3 scripts/figma_xml_handoff.py validate \
  --result <figma-xml-result.json> \
  --impact-radius <requirement_dir>/test-cases/impact-radius.json \
  --before-snapshot <requirement_dir>/.state/figma-xml-before.json \
  --project <Android项目Git-worktree根目录> \
  --requirement-id <当前requirement_id> \
  --requirement-revision <当前修订号> \
  --requirement-inputs-sha256 <当前输入摘要>
```

脚本同时核对需求编号、修订号、输入摘要、Android `res` 路径、影响半径、项目内真实文件 SHA-256 和调用前后的完整文件变化。provider 产生但未写入交接 JSON 的代码、报告、删除或其他隐藏改动同样阻断；任一不一致都必须重新生成或回到对应增量节点。

## 增量分类

| Figma 变化 | 处理 |
| --- | --- |
| 只补充原有页面视觉基准 | 保留需求修订；影响半径不变时保留计划确认，刷新 XML、构建和 UI 证据 |
| 只改颜色、间距、字号或图片且仍在允许路径内 | 局部调用生成 Skill，重跑受影响 build/lint/截图，不重做无关测试 |
| 新增页面状态、交互、文案语义或业务规则 | 先写回需求事实源，重新确认需求和计划，测试映射进入 STALE 闭环 |
| 产物触及影响半径外文件 | 阻断交接，更新计划和影响半径并等待重新确认 |
| Figma 输入、节点或本地资产变化 | `requirement_inputs_sha256` 变化，旧 route、专项和视觉证据失效 |

## 交接结果

交接 JSON 必须记录设计来源、输入摘要、技术栈、目标模块、产物路径、缺失资料、近似实现、验证命令和语义分类。不得包含 Figma 临时资产 URL、Cookie、Token、密码或其他凭据。
