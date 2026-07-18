# Android Delivery Workflow 导航

本文档只说明规则来源和流程入口，不再重复定义工程规则。其他模型执行时必须以对应 Skill 文件为准，避免多份规则长期漂移。

## 唯一规则来源

1. `_shared/android-global-rules.md`：所有 Android Skill 共用的最小修改、单一职责、安全和证据规则。
2. `android-implement-and-verify/SKILL.md`：完整需求交付的唯一流程来源，定义需求确认、编码、路由、验证和完成标准。
3. 各专项 `SKILL.md`：只定义本专项的触发条件、职责边界、检查方法和报告格式。
4. `SIMPLE_USAGE.md`：面向使用者的名称与命令速查，不增加 AI 强制规则。
5. `references/open-source-design-rationale.md`：维护流程时使用的设计依据，记录开源参考、采用/拒绝原因和长期不变量。
6. `android-implement-and-verify/references/delivery-eval-scenarios.md`：修改 Skill、路由或门禁后的行为评测集，不是日常需求步骤。
7. `android-implement-and-verify/references/conditional-capability-gates.md`：第二轮六类条件能力和无真机降级的详细边界，仅在候选触发时读取。

规则冲突时按以下顺序处理：目标项目 `AGENTS.md` / `CONTRIBUTING.md` 等更严格规则 → `_shared/android-global-rules.md` → 当前 Skill。无法确定时暂停说明，不自行选择宽松规则。

## 三阶段入口

```text
delivery.py init
  -> 读取当前需求
  -> 输出需求理解、BDD 和最小修改预览
  -> 等待用户确认

delivery.py check-env
  -> 校验项目、分支和干净工作区
  -> 记录当前需求 Git 基线
  -> 允许编码

delivery.py route
  -> 仅收集当前需求基线后的变化
  -> 按真实 diff 路由专项 Skill
  -> 测试、构建、lint 和问题修复形成闭环
```

这三个命令是轻量流程编排器，不是通用状态机。除当前需求 Git 基线外，不维护额外 phase、MVU 或恢复状态。

## 不可覆盖的安全边界

- 不脑补需求、接口字段、枚举、错误码、设计结论或测试结果。
- 不自动切分支、stash、commit、push、reset、checkout 或 clean；Git 写操作必须由用户明确要求。
- 缺少正式接口契约时，不创建未知生产 DTO、Endpoint 或会在正式路径执行的 `TODO()`；用户明确允许后，只能在 debug、fake、sampledata 或测试范围内降级。
- 构建、测试和 lint 命令必须根据实际模块、variant 和项目任务选择，不写死 `assembleDebug` 或 `lintDebug`。
- UI 验收保持手动独立执行。有 UI 基准但尚未运行 `android-verify-ui` 时，只能声明“代码与自动测试完成，UI 验收待执行”。
- 没有实际执行证据时只能标记“未验证”，不得写成通过。

## 维护规则

- 新的跨 Skill 约束只写入 `_shared/android-global-rules.md`。
- 新的完整交付步骤只写入 `android-implement-and-verify/SKILL.md`。
- 专项细节只写入对应 Skill；详细、低频资料放入该 Skill 的 `references/` 或 `assets/`。
- 修改脚本行为时同步修改同职责文档和测试，不在本导航页复制实现细节。
- 修改 Skill、路由或门禁后，按行为评测集做 forward test；新增设计决策时同步记录来源、取舍和边界。
