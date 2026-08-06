---
name: android-implement-and-verify
description: |
  Android 需求实现与闭环验证总入口。适用于完整完成 Android 新需求、需求变更、Bug 修复和功能迭代。五步：确认需求 → 拆分测试与确认计划 → 实现验证 → 变更后增量循环 → 最终交付。
  固定保护 requirement_file 事实源、需求/计划确认、影响半径、SHA-256、新鲜证据、STALE 测试映射和非零测试。自动化测试按 BDD、实际 diff 和影响类别选择；Figma + XML View 在计划确认后可调用 figma-android-xml 生产布局，再由本 Skill 接管业务接入、测试和独立 UI 验收。
  首次编码前确认 BDD、基线、计划和影响半径；编码后只跑受影响测试和必要编译；只有用户明确要求最终交付时才按最终 diff 执行 route、专项和完整门禁。仅需单项审查时改用对应专项 Skill。
---

# Android 需求实现与闭环验证

## 共享规则

执行前必须遵守 `../_shared/android-global-rules.md`。本 Skill 是唯一完整交付编排器，并在已确认需求范围内获得最小自修复和重验授权；不自动发布、推送、上线、操作生产数据或提交 Git。

## 按需读取

不要一次加载全部资料，只读取当前阶段需要的直接 reference：

| 当前任务 | 必读资料 |
| --- | --- |
| 澄清需求、BDD、计划、影响半径或事实收件箱 | `references/requirement-and-plan.md` |
| 多来源文档、表格、截图、术语、需求冲突或需用原型澄清 | `references/document-and-requirement-understanding.md`，再按需读取上一行 |
| TDD、局部迭代、测试选择或 Figma XML 实现 | `references/implementation-and-testing.md`；Figma XML 另读 `references/figma-android-xml-handoff.md` |
| route、专项、自修复、assemble、最终结论 | `references/final-delivery.md` |
| 多需求 worktree、轮换、合并或跨上下文续接 | `references/parallel-and-resume.md` |
| 接口、设计或设备资料缺失 | `references/input-degradation.md` |
| 条件能力、Schema 或维护流程 | 对应 `references/*.schema.json`、`references/conditional-capability-gates.md`、`../references/delivery-flow.yaml` |

维护本流程时读取 `../references/open-source-design-rationale.md` 和 `references/delivery-eval-scenarios.md`，并执行维护验证和 artifact eval。详细资料不是每次需求的固定上下文。

## 用户可见五步

始终向用户收敛为 `确认需求 → 拆分测试与确认计划 → 实现验证 → 变更后增量循环 → 最终交付`：

1. **确认需求**：先综合已知资料，不重复询问；把每个已接受答案写回唯一 `requirement_file`，展示最新变更摘要、已上线业务影响和待确认点。
2. **拆分测试与确认计划**：把已确认行为映射为 BDD、测试和影响半径；只有跨会话或多条独立验收链路的复杂需求才在同一计划中拆纵向切片，小需求一行直通。用户仍只确认一次计划。
3. **实现验证**：逐个可观察行为完成 Red、最小实现、Green 和受影响验证。
4. **变更后增量循环**：这是任意阶段都能触发的回退路径，不是可跳过的线性尾声。
5. **最终交付**：仅在用户明确要求时执行最终 route、专项、完整门禁和中文报告；提交仍需单独授权。

默认不向用户展开脚本、JSON、Schema 或哈希；只有用户询问，或授权、阻塞和故障处理需要时才展示必要细节。

## 不可变状态规则

- 聊天只是草稿。最新需求没有写回 `requirement_file` 并重新 `init` 时，不得确认、编码、route 或最终交付。
- 需求修订必须先确认；实施计划和 `<requirement_dir>/test-cases/impact-radius.json` 必须再单独确认。`confirm-plan` 成功前不得修改生产代码。
- 影响半径必须登记当前需求基线以来的 ADDED/CHANGED/REMOVED/SUPERSEDED；最终 diff 中出现不在已确认 `impact-radius.json` 的代码文件时必须阻断。
- 需求义务变化后，受影响测试映射自动进入 `STALE`。回填 `CURRENT`、重测并刷新证据前，不得支持最终通过。
- 需求、计划、影响半径、UI/API 输入或代码变化后，旧 route、专项结果和最终证据按绑定摘要失效，不得复用。
- route 只登记专项任务，不直接调用 Skill；最终门禁逐项检查当前结果。

## 增量闭环

任何阶段发现变化都先分类，再选择最小合法回退：

### 需求语义变化

新增或改变页面状态、交互、业务规则、文案语义、接口含义或验收结果时：

1. 写回需求事实源并重新 `init`，等待用户确认。
2. 执行 `confirm-requirement-update`，使受影响映射进入 `STALE`。
3. 更新同一份实施计划和影响半径，展示并重新 `confirm-plan`。
4. 重建测试映射，先观察 Red，再做最小实现、Green、受影响回归和证据刷新。
5. 回到发现变化前的阶段继续；未变化的 BDD、代码和测试不重做。

### 计划或范围变化

需求语义不变但预计文件、测试、模块或允许路径变化时，保留需求修订，更新计划和影响半径并重新确认；旧计划收据、route 和下游证据失效。

### 实现细节或纯视觉变化

仍在已确认影响半径内且验收语义不变时，不重复需求确认或完整流程。只做最小修改、更新受影响测试、运行必要编译并刷新相关证据。Figma 只改变颜色、间距、字号或图片时按此处理；Figma 新增状态、交互或业务语义时必须回到“需求语义变化”。

需要等待用户的节点只有需求确认、计划确认、route 新会话授权或缺少不可替代事实；其他实现和重验自动推进。

## 实现与测试门禁

计划确认后、route 前必须完成：

1. **先建立测试清单**：执行 `init-test-mapping`，让每个 BDD 绑定真实测试代码、Journey XML 或可复现人工验收。
2. **先写失败测试**：逐个 BDD 补业务断言并观察 Red；实现前已通过时检查断言是否真的覆盖新行为。
3. **再写最少实现**：只改影响半径内代码使测试 Green，再做必要重构。
4. **保存 TDD 周期**：Red/Green 收据、代码和测试源码摘要必须绑定当前 BDD/testcase。
5. **按影响补证据**：根据 BDD、实际 diff 和影响类别选择 Unit、集成、构建、安装、Journey、截图、日志或人工证据，不机械执行同一串命令。
6. **诚实回填**：每个场景标记 `PASS/FAIL/UNVERIFIED`；自动化测试按 BDD、实际 diff 和影响类别选择，每个适用类别必须有当前版本的执行证据。

发现需求漏洞立即进入增量闭环，不能用修测试或改断言绕过需求修订。

## Figma XML 实现

已确认计划包含 Figma + XML View 时，读取 `references/figma-android-xml-handoff.md`：

- 先确认项目确实是 XML View 或混合项目中的 XML 页面；Compose 不调用 XML Skill。
- `figma-android-xml` 只生成 XML 和资源，不写 Kotlin/Java，不进入专项 PASS 白名单。
- 生成结果必须通过 `scripts/figma_xml_handoff.py` 和影响半径校验，再由本 Skill 接管业务接入。
- build/lint、功能测试和 `android-verify-ui` 真机视觉结果必须另行产生新鲜证据；生成成功不等于交付通过。

## 最终交付

只有用户明确要求最终检查、完整交付或准备提交时：

1. 确认所有场景已有诚实结果，执行 `delivery.py route`。
2. 先执行 `android-review-diff`，合并脚本候选和七类 `confirmed_impacts`。
3. 按 `specialist_tasks` 逐项执行质量、稳定性、测试、API 和独立 UI 等适用专项。
4. 修复改变 diff 后重新 route；相同输入复用，变化超过默认三轮时阻断，人工确认后才可 `route --new-session`。
5. 基于最后一次修复后的代码重跑必需命令，优先用 `delivery_gate.py assemble --manifest` 组装并立即 validate。
6. 输出 `FULL_PASS`、`LOCAL_PASS_DEVICE_PENDING`、`INCOMPLETE` 或 `BLOCKED` 对应的中文结论和剩余风险。

存在 UI 变更和可对比基准时，必须附上独立 `android-verify-ui` 报告或用户明确豁免；否则只能说明“代码与自动测试完成，UI 验收待执行”。

## 完成条件

只有当前需求和计划已确认、影响半径未越界、所有必需 BDD 有 CURRENT 映射和新鲜证据、非零测试真实通过、适用专项已完成、P0/P1 已关闭且最终 gate 通过时，才可声明交付完成。设备或外部条件缺失必须保留未验证项；任一必需门禁未满足时只能声明“未完成/受阻”。
