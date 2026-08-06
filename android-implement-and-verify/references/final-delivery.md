# 最终路由、专项与交付门禁

## 进入条件

只有用户明确要求最终检查、完整交付或准备提交，且所有 BDD 已有诚实结果时进入。代码写完本身不触发最终交付。

## Route

执行 `delivery.py route`。它校验计划收据和影响半径，只分析当前需求 Git 基线后的真实代码 diff，并绑定需求正文、计划、影响半径、UI/API 输入、本地资料和最终代码摘要。

- 最终 diff 超出已确认影响半径时立即阻断，只能更新并重新确认范围或移除无关改动。
- 先执行 `android-review-diff`，要求 UI、API、数据、系统、构建、架构和测试七类 `confirmed_impacts`。
- 脚本候选与语义影响取并集；route 只写 `specialist_tasks`，不直接调用 Skill。
- route 记录 `route_input_sha256`、轮次、会话和收敛状态。相同输入复用；变化超过默认三轮时 `BLOCKED`，人工确认后才可 `route --new-session`。
- 修复改变 diff 后必须重新 route；只补同一代码下缺失证据时局部重验即可。

## 专项

按 route 清单逐项执行：

- `android-review-diff`：范围、旧业务影响和七类语义影响。
- `android-review-code-quality`：架构、职责、文档和可测试性。
- `android-audit-stability`：静态语义、生命周期、泄漏、性能、安全和兼容性。
- `android-test-and-fix`：按 BDD、映射和最终 diff 选择完整回归。
- `android-verify-api-contract`：只在 API/DTO/Repository/mapper/缓存契约变化时执行。
- `android-verify-ui`：独立物理设备预检、Figma 与真机截图视觉验收；不得由 Figma XML 生成报告替代。

最终汇总必须并列保留两条结论：`android-review-diff` 的“需求轴”回答是否做对、做全、越界和破坏旧业务；`android-review-code-quality` 的“工程轴”回答是否符合项目规范、架构和可维护性。两轴不能合并抵消，一轴失败时不得因另一轴通过而建议交付。

范围或需求问题进入增量闭环；已确认范围内 P0/P1 技术问题最小修复并重验。适用但缺设备、契约或基准时标记 `UNVERIFIED/BLOCKED`，不影响其他可执行门禁继续。

## 执行证据

- 最终命令通过 `execution_evidence.py` 执行，一份收据只证明一个 gate；同 ID 重跑保留独立 attempt。
- 自动测试和迁移收据必须包含本轮实际执行数大于零的报告；零测试、忽略失败或缺失 JUnit 不能判通过。
- 每个 BDD 只关联 CURRENT mapping 中登记且本次真实通过的 testcase。
- 普通构建或 Unit 收据不能代替接口、UI、安全、泄漏或性能专项。
- 失败收据只能支持对应 FAIL/INCOMPLETE/BLOCKED，不能绑定自动覆盖或 PASS。

## 结果组装

优先写 YAML 产物清单并执行：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py assemble \
  --config <配置> --manifest <产物清单.yaml>
```

assemble 自动计算代码、义务、收据和专项摘要并立即 validate。只有特殊字段无法表达时才按 schema 手写 `delivery-result.json` 后执行 validate。

核心 gate 包含 diff、质量、稳定性、测试、build 和 lint；接口、迁移、UI/A11y、安全等条件 gate 来自 route 与 `confirmed_impacts` 并集。UI 视觉使用 `android-verify-ui` 的 `device_check` 和 `visual_review`，不使用通用人工收据或 Figma 生成结果。

## Definition of Done

- 需求为 CONFIRMED，无 PENDING/CONFLICT；计划收据与当前需求、计划和影响半径一致。
- 所有必需 BDD 有 CURRENT 映射和真实通过证据；未执行不得写 PASS。
- 必需命令在最后一次修复后执行，记录命令、退出码、测试数和报告路径。
- 所有适用条件能力记录适用性、工具、证据、能力损失和残留风险；P0/P1 已关闭。
- UI 有可比基准时必须有独立 `android-verify-ui` 报告或用户明确豁免，否则为 UI 验收待执行。
- 最终报告、需求、计划、影响半径、输入、Git 基线、代码摘要和引用证据仍一致。
- `delivery-result.json` 通过独立最终门禁，并生成向用户展示的 `docs/交付结论.md`。

不满足任一必需项时只能输出 `LOCAL_PASS_DEVICE_PENDING`、`INCOMPLETE` 或 `BLOCKED` 的对应中文结论。Git 提交不是完成条件，仍需用户单独授权。
