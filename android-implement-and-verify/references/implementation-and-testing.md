# 实现、测试与局部迭代

## 编码前

1. 执行 `delivery.py check-env` 建立或复用当前需求 Git 基线。
2. 执行 `confirm-requirement-update`，生成当前修订。
3. 写并展示实施计划和影响半径；`confirm-plan` 成功前保持只读。
4. 执行 `init-test-mapping`，把全部已确认 BDD 绑定到真实测试、Journey XML 或人工验收。
5. 动笔前读取项目规则、相邻实现、调用方和已有测试；优先沿用项目架构和测试范式。

## TDD 切片

- 按一个可观察行为完成 `Red → 最小实现 → Green → 必要重构`，不要先完成全部生产代码再补测试。
- Red 必须由新业务断言失败证明；环境失败、编译错误或空测试不算业务 Red。
- Red/Green 都通过 `execution_evidence.py` 生成收据，再由 `tdd_cycle.py` 绑定 BDD、testcase、代码和测试源码摘要。
- 每个 BDD 选择最低且足够的证据层；Unit、集成、Contract、Journey、截图和人工验收只能证明各自实际断言。
- 代码或测试修复后重跑失败项和受影响回归；禁止删测试、弱化断言、跳任务或用假数据造绿。

## Figma XML

满足 XML View、Figma 可读、需求和计划已确认三个条件时，读取 `figma-android-xml-handoff.md`：

1. 把 Figma 链接、本地基准和资源纳入当前 UI 输入摘要。
2. 调用前用 `scripts/figma_xml_handoff.py snapshot` 保存 Git worktree 文件摘要。
3. 调用 `figma-android-xml` 只生产影响半径内的 layout/drawable/values/font/bitmap。
4. 禁止外部 Skill 写 Kotlin/Java；禁止为了复用它把 Compose 页面改成 XML。
5. 生成 `figma-xml-result.json`，用 `figma_xml_handoff.py validate` 检查前后差异、类型、SHA 和影响半径。
6. 总入口按项目 Design System、I18n、A11y、资源和架构约定接管，补业务连线和测试。
7. build/lint 结果必须有 Delivery 执行收据；Android Studio Preview 和生成报告不等于真机视觉通过。

## 编码后局部迭代

- **验收语义不变**：不运行 `init`、需求确认、route 或全部专项。确认仍在影响半径内，只改必要文件，更新受影响测试并执行最小编译。
- **验收语义变化**：先写回需求，重新确认受影响 BDD、计划和影响半径，再恢复 TDD。
- **影响类别扩大**：数据库迁移、公共 API、支付、鉴权、安全、权限、生命周期等只追加能证明该类别的最小专项。
- **纯 Figma 视觉变化**：不升级需求修订、不改写无关测试；刷新 Figma 交接、资源构建、截图和视觉证据。若完整输入摘要变化，最终交付时重跑必要命令刷新绑定旧输入的专项/执行收据；新增状态、交互或业务语义则按需求变化处理。
- 局部回复只报告本轮文件、测试/编译、结果和剩余风险，不生成新的整体通过结论。

## 故障处理

先分类 `PRODUCT_DEFECT / TEST_DEFECT / ENVIRONMENT / TOOLING / EXTERNAL_BLOCKER`，保存原始证据，再修一个根因并重验。同一根因连续三轮不能关闭才进入 `BLOCKED`，说明命令、退出码、日志、已尝试修改、能力损失和所需输入。
