# Android Delivery Skills 完整流程总览

> 本文件是当前流程的完整快照，覆盖所有能力、命令、产物、防脑补机制和压测结论。
> 最后更新：2026-07-25

## 一、仓库结构

```text
android-delivery-skills/
├── 7 个 Skill（各司其职）
│   ├── android-implement-and-verify/   ← 总入口（需求→计划→编码→交付）
│   │   ├── SKILL.md
│   │   ├── templates/                  ← 11 个交付模板
│   │   └── references/                 ← schema/eval/条件门禁
│   ├── android-review-diff/            ← diff 范围审查
│   ├── android-review-code-quality/    ← 代码质量审查
│   ├── android-audit-stability/        ← 稳定性（泄漏/并发/性能/安全）
│   ├── android-test-and-fix/           ← 测试 + 变异测试 + 自修复
│   ├── android-verify-api-contract/    ← 接口契约审查
│   └── android-verify-ui/              ← UI 独立验收
├── _shared/android-global-rules.md     ← 跨 Skill 共享规则（410 行预算）
├── references/
│   ├── open-source-design-rationale.md ← M01-M32 设计决策依据
│   └── conditional-capability-gates.md  ← 条件门禁
├── scripts/                            ← 18 个 Python 脚本 + 202 个单测
├── profiles/                           ← 本机配置（local.yaml + local.example.yaml）
└── SIMPLE_USAGE.md / AI_DELIVERY_WORKFLOW_GUIDELINES.md
```

## 二、五步流程（用户看到的）

```text
① 确认需求
  → ② 拆分测试与确认计划
    → ③ 实现验证
      → ④ 变更后增量循环
        → ⑤ 最终交付
```

- **确认需求**：读取需求和相关代码，置顶展示已上线业务影响；每个已接受答案先写回唯一需求文件，纯确认后进入计划准备。
- **拆分测试与确认计划**：把行为映射为测试，再用一份 Markdown 展示实现范围、旧业务影响、预计文件、测试和不修改范围；确认后才编码。
- **实现验证**：按一个可观察行为完成 Red → 最小实现 → Green，只报告本轮实现和验证结果。
- **变更后增量循环**：需求增量→AI 全自动改代码+改测试+回填+增量回归（见第六节增量闭环铁律）。
- **最终交付**：只有用户明确要求时，才基于最终 diff 执行完整审查、回归、构建、Lint、变异测试(PIT)、条件专项和中文报告。

## 三、内部命令链（AI 执行的）

```bash
# ① 确认需求
delivery.py init --config profiles/local.yaml
# 读需求；docx 自动转写为 <需求名>.md 作事实源；刷新续接指南；打印流程位置

delivery.py check-env --config profiles/local.yaml
# 校验分支+代码工作区干净（文档改动不阻断）；建 Git 基线 + 需求快照到 .state/

# 物化 requirement-revision.json（AI 按 schema 写增改删清单）
delivery.py confirm-requirement-update --config profiles/local.yaml
# 推进版本号（首次确认 → 增量修订）；标 STALE；刷新续接指南/需求修订说明/测试映射说明

# ② 拆测试 + 确认计划
delivery.py confirm-plan --config profiles/local.yaml
# 生成计划确认收据（绑定需求+计划 sha256）；未确认不得编码

delivery.py init-test-mapping --config profiles/local.yaml
# 生成测试映射骨架（STALE）；AI 填 test_ids 后回填 CURRENT

# ③ 实现验证（AI 编码：Red → 最小实现 → Green）
# ④ 增量循环（见第六节）

# ⑤ 最终交付
delivery.py route --config profiles/local.yaml
# 基于真实 diff 路由专项 Skill；保存路由快照

delivery_gate.py validate --config profiles/local.yaml
# 最终门禁：校验义务集合/sha256/STALE/证据/变异测试/traceability 全一致
```

## 四、文档布局（跟项目走，git 跟踪）

```text
<project_path>/document/<日期-英文名>/
├── <需求名>.md                    ← 唯一事实源（docx 自动转写，以后增量都在 md）
├── 续接指南.md                    ← AI 续做第一眼（每次 init/confirm 自动刷新）
├── 实施计划.md                    ← 用户确认后才能编码
├── 协作待办.md                    ← blocker/待确认/草稿消息（AI 手写）
├── api/                           ← 接口证据
├── ui/                            ← UI 截图 + design-notes.md
├── config/                        ← 非密配置元数据
├── issues/                        ← 问题台账（每问题一 md）
├── plan/                          ← AI 手写计划补充
├── review/                        ← 变更审查.md（Diff+Context 双表）
├── decisions/                     ← 决策记录（MADR 轻量版）
├── test-cases/
│   ├── test-mapping.json          ← 义务↔测试绑定（STALE/CURRENT 联动）
│   ├── requirement-revision.json  ← 修订清单（增改删+决策）
│   ├── implementation-plan-receipt.json ← 计划确认收据
│   ├── traceability.md            ← 追溯表
│   ├── 需求修订说明.md             ← 自动渲染（从 snapshot）
│   └── 测试映射说明.md             ← 自动渲染（从 test-mapping）
├── test-results/
│   ├── delivery-result.json       ← 最终机器报告
│   └── 交付结论.md                 ← 自动渲染（强制未验证项+残留风险段）
└── .state/                        ← 机器状态（不进 git，跟需求走）
    ├── baseline.json              ← Git 基线
    ├── requirement-snapshot.json  ← 需求快照（sha256 + 义务 + 版本）
    ├── route-impact.json          ← 路由快照
    └── evidence/                  ← 执行收据/日志/专项结果
```

## 五、三层防脑补

| 层 | 机制 | 强度 | 业界对照 |
|---|---|---|---|
| **SHA-256 哈希链** | 需求/计划/代码/证据全绑定，改了不重读就拦 | 机器强制 | 比业界更强 |
| **STALE 联动** | 需求增量→义务 sha256 变→测试自动标 STALE→gate 拦 | 机器强制 | PIT 变异测试补充 |
| **变异测试** | 篡改生产代码看断言是否真约束行为，survived=0 才 PASS | 机器强制 | 业界标准 PIT |
| **架构测试** | ArchUnit/反射测试固化"不绕统一出口"等约束 | AI 生成+机器校验 | 业界标准 ArchUnit |

## 六、增量闭环铁律（需求增量后 AI 全自动）

confirm-requirement-update 成功后，如果续接指南有 STALE 或新增义务，AI 必须立即自动完成全部后续，不等用户指示：

1. **改实现代码**：只改增量需求涉及的文件（看续接指南波及清单），不动已交付逻辑。
2. **改测试代码**：为 STALE/新增义务加断言，不删旧测试、不弱化旧断言。
3. **回填映射**：init-test-mapping + 把 STALE 回填 CURRENT，登记新义务的 test_ids。
4. **增量回归**：跑受影响模块的全量测试（含旧测试），确认已交付功能无回归；旧测试失败必须修到通过。
5. **报告完成**：改了哪些文件、哪些测试通过、有无回归，一句话给用户。

唯一需要等用户的是：需求还没确认（待定/冲突），或用户还没说"开始编码"。

## 七、版本号（已中文化）

| 机器值（JSON） | 用户看到（终端/md） |
|---|---|
| 0 | 初始（尚未确认需求） |
| 1 | 首次确认 |
| 2 | 增量修订（第 1 次） |
| 3 | 增量修订（第 2 次） |
| N | 增量修订（第 N-1 次） |

## 八、多需求并行

```text
一个需求 = 一个 git worktree + 独立分支 + 独立 profiles/<需求>.yaml + 独立 document/<日期-英文名>/
```

- 不冲突的需求（改不同文件）各窗口独立闭环，全程自带 `--config`。
- 合并用 `git merge --no-ff`（线性主干 + merge commit 标记需求边界 + 提交 hash 保留，证据链不断）。
- 续接旧需求 = 新建 `document/<新日期>-<需求名>/` + 引用旧需求 + `check-env --new-requirement` 建当前 HEAD 基线。
- 全局总览在主工作树 `document/需求总览.md`（六列：目录/中文标题/分支/状态/集成批次/最后修订）。

## 九、docx → md 事实源切换

- `requirement_file` 配 docx 时，init 自动读取 docx 正文转写为 `<需求名>.md`。
- 以后所有增量、修订、门禁都以 md 为准，docx 仅作初始记录保留。
- 图片型 docx（无文本正文）：用模板骨架建空 md，AI 在后续沟通中填充。
- 所有命令统一"有 md 优先 md"（config_paths 自动切换，无断裂）。

## 十、11 个交付模板

| 模板 | 用途 |
|---|---|
| requirement.md | 需求事实源骨架（用户故事→AC→主流程/异常边界） |
| plan.md | 实施计划（AC×步骤×文件×职责表） |
| review.md | 变更审查（逐文件清单 + Diff + Context 双表） |
| test.md | 测试结果（AC×场景×用例×结果表） |
| result.md | 交付结论（强制未验证项 + 残留风险段） |
| decision.md | 决策记录（MADR：Status 流转 + superseded） |
| communications.md | 协作待办（4 表：待确认/阻塞/已发送/低风险） |
| api.md | 接口说明（接口清单 + 错误码 + Mock） |
| issue.md | 问题台账（现象/根因/处置/证据） |
| config-note.md | 配置说明（key 名/环境/owner/安全边界） |
| design-note.md | 设计说明（页面状态/交互/资源对照） |

## 十一、压测验证

| 轮次 | 方式 | 发现 | 结果 |
|---|---|---|---|
| 单需求端到端 | 手动 8 场景 | 5 个 bug（hash 漂移/跨项目残留/docx 增量/document 脏/docx 全链路断裂） | 全修 |
| 5 窗口并行 | 5 个无上下文 agent | 10 个问题（route 崩溃/破坏性重写/正则不一致/硬编码/gitignore/校验顺序/错误聚合/噪音/traceability/STALE 文案） | 全修 |
| **10 窗口并行** | **10 个无上下文 agent** | **0 个新 bug** | **10/10 全通过** |

核心防脑补机制（STALE 联动 + gate 拦截 + sha256 绑定 + 计划收据失效）15/15 全验证通过。

## 十二、业界对照（10 维度）

| 能力 | 业界最强 | 本流程 | 排名 |
|---|---|---|---|
| 需求唯一事实源 + 增量修订 | Spec Kit（单向写回） | SHA 双向校验 | 更强 |
| 防测试不更新 | PIT（多数项目没有） | 变异测试 + STALE 映射 | 业界顶尖 |
| 防假断言 | ArchUnit（少有人配两层） | ArchUnit + 变异 | 业界顶尖 |
| 防脑补（最终） | Spec Kit coverage | obligation_sha256 强等 | 更强 |
| plan 唯一 + 确认收据 | Spec Kit spec/plan 分离 | 固定文件名 + 三重 sha | 持平 |
| 续接旧需求 | Spec Kit spec continuity | 续接指南 + 波及清单 | 持平 |
| plan 自动进入 | codex 状态驱动 | 流程位置指示器 + 命令驱动 | 持平 |
| 多需求维护 | XDG/Gradle 回收 | 总览 + 归档 + 独立目录 | 持平 |
| 人读产物 | shareit docs | md 影子体系 | 持平 |
| 交互轻量度 | Spec Kit constitution 几十行 | description 浓缩铁律 + 410 行正文 | 持平 |

## 十三、机器状态隔离

- 状态文件在 `<requirement_dir>/.state/`（跟需求走，不写全局 `~/.local/state/`）。
- 换需求即换目录，物理隔离，无跨需求残留。
- document/ git 跟踪可 commit；check-env 只检查代码工作区，文档改动不阻断。
- delivery_gate 代码摘要排除 document/，文档变化不污染 snapshot_sha256。

## 十四、关键脚本职责

| 脚本 | 职责 |
|---|---|
| delivery.py | 总编排器（init/check-env/confirm-*/route/init-test-mapping） |
| delivery_gate.py | 最终门禁校验（义务/sha256/STALE/证据/变异/traceability） |
| config_paths.py | 路径解析 + docx→md 自动切换 + requirement_dir 派生 |
| requirement_snapshot.py | 需求快照（sha256 + 义务 + 版本 + 修订历史） |
| implementation_plan.py | 计划校验（5 必需标题）+ 收据生成（三重 sha 绑定） |
| test_mapping.py | 测试映射（STALE 联动 + CURRENT 校验 + 保留未变化登记） |
| route_impact.py | 路由快照（8 字段绑定需求/计划/代码） |
| execution_evidence.py | 执行收据（单 gate 不可覆盖） |
| specialist_result.py | 专项结果校验（P0-P3 + 变异测试 + capability） |
| render_artifacts.py | JSON→md 渲染（续接指南/修订说明/映射说明/集成报告/波及清单） |
| atomic_write.py | 公共原子写（0600 权限，收敛 5+ 处重复） |
| requirement_workspace.py | 工作区轮换 + 回收 + index 总览 + integrate 集成报告 |
| user_facing_labels.py | 机器枚举→中文（含 revision_label 版本号中文化） |
| git_changes.py | Git 只读收集（分支/基线/diff/patch/snapshot） |
