# assemble 产物清单格式

> 本文件是 `android-implement-and-verify` 最终交付阶段"方式一：assemble 自动组装"的详细说明。
> SKILL.md 只保留命令和边界，字段细节以此为准。

## 用途

跑完测试/审查后，agent 只写一份 YAML 产物清单（只声明业务事实，不算指纹），由 `delivery_gate.py assemble` 自动组装 `delivery-result.json` 并立即 `validate`。所有 `sha256`、`obligation_test_cases`、`receipt` 引用由脚本从执行收据/专项结果/junit 报告自动计算，消除手填字段摩擦。

## 命令

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py assemble \
  --config <配置> --manifest <产物清单.yaml>
```

`--result` 可选，缺省写到 `<requirement_dir>/test-results/delivery-result.json`。

## 完整产物清单示例

```yaml
conclusion: FULL_PASS          # 或 LOCAL_PASS_DEVICE_PENDING / INCOMPLETE
evidence:                       # 自动证据：声明 id/gate/receipt 路径
  - id: build
    gate: android-build
    receipt: .state/evidence/.../build/attempt-001/receipt.json
  - id: unit
    gate: android-test-and-fix
    receipt: .state/evidence/.../unit/attempt-001/receipt.json
specialists:                     # 专项结果：声明 specialist JSON 路径
  - path: .state/evidence/.../specialists/android-review-diff.json
  - path: .state/evidence/.../specialists/android-verify-ui.json
obligations:                     # 逐义务声明覆盖状态；未验证项不得伪装成自动覆盖
  BDD-001:
    status: COVERED_AUTOMATED
    evidence: [unit]
  BDD-005:
    status: UNVERIFIED
    evidence: []
    reason: 尚未执行设备验证
gates:                           # 可选：覆盖 gate 的 required/status/reason
  android-ui-a11y: {required: false, reason: 无 UI 影响}
```

## 字段职责分工（关键边界）

**agent 必须提供（业务事实，机器判不准）：**

- `conclusion`：交付结论。
- `evidence[].receipt`：AUTOMATED 证据的执行收据路径（脚本读它算 sha）。
- `evidence[]`（MANUAL）：仅用于需要逐步人工执行的业务/迁移/安全等覆盖；UI 视觉验收使用 `specialists` 中的 `android-verify-ui` 结果。
- `android-verify-ui` 专项：`device_check` 记录物理设备预检和截图命令结果，`visual_review` 只记录 Figma 设计链接、真机截图/差异图链接和动态区域说明；不填写 APK、versionCode、安装收据或截图 SHA-256。
- `specialists[].path`：专项结果 JSON 路径。
- `obligations`：逐义务填写 `status`、`evidence`，`UNVERIFIED/BLOCKED` 还要填写 `reason`；缺少 `status` 时保守组装为 `UNVERIFIED`。

**脚本自动计算（agent 不填，填了也以脚本为准）：**

- `snapshot_sha256`、各 `obligation_sha256`：从当前 delivery_gate context 取。
- `receipt_sha256`、`report_paths`、`command`、`exit_code`、适用时的 `executed_tests`：从执行收据读；清单 id 必须与收据 id 一致。
- `obligation_test_cases`：从收据里的 junit 报告按 `classname#name` 自动提取。
- `specialist_result_sha256`：算 specialist JSON 文件 sha；UI 专项的截图和设计链接不单独计算文件摘要。
- `gates`：默认按 evidence 的 gate 自动推导；agent 可在 `gates` 段覆盖 `required`/`status`/`reason`。

junit 报告用内容签名（剥离可变 timestamp），重跑收据不再失效。

## 错误回显

assemble 组装完会立即 validate，失败时直接列出具体字段错误，例如：

```
❌ 组装结果未通过门禁:
- 场景 BDD-001 的测试映射登记了未执行的测试: ...
- gate android-ui-a11y 没有专属于本 gate 的有效通过证据
```

按错误修正产物清单或补产物后重跑即可。

## 简写格式

`BDD-001: [unit]` 列表格式可用于当前场景；只有引用的证据全是自动/Agent 证据时才推导为 `COVERED_AUTOMATED`，不能确定时保守记为 `UNVERIFIED`。assemble 是可选加速，手写结果也必须通过同一个 validate。
