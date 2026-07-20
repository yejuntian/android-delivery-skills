# Android Skills 名称、职责与用法

流程维护者先读 `references/open-source-design-rationale.md`；修改 Skill、路由或门禁后用 `android-implement-and-verify/references/delivery-eval-scenarios.md` 做行为评测。日常执行需求不必加载这两份文档。

## 只记一个日常入口

完整实现需求、修复 Bug 或完成迭代时，只调用：

```text
android-implement-and-verify
```

它负责从需求确认推进到测试全绿。其余 6 个是专项能力，由总入口按实际 diff 自动编排；只有明确要求单项检查时才手动调用。

## 个人查阅：常见专业术语

这一节只是给你查阅的中文说明，不是 Skill 执行规则，不参与流程判断，也不会改变脚本中的英文名称和机器字段。

### 需求、代码与接口

| 专业术语 | 中文意思 | 在本流程里是做什么的 |
|---|---|---|
| Skill | AI 能力说明 / 工作流程 | 告诉 AI 在什么情况下做什么，以及哪些事情不能做 |
| UI | 用户界面 | 用户能看到并操作的页面、弹窗、按钮等 |
| API | 接口 | Android 客户端与后端交换数据的通道 |
| Endpoint | 接口地址 | 某项后端能力对应的请求地址和请求方式 |
| Contract | 接口契约 | 接口地址、字段、类型、必填性、枚举和错误码等约定 |
| JSON | 结构化数据格式 | 接口返回数据及部分机器报告采用的文本格式 |
| YAML | 配置文件格式 | `local.yaml` 使用的、便于人工编辑的配置格式 |
| DTO | 接口数据对象 | 严格对应后端接口字段的数据类，不直接代表稳定业务含义 |
| Domain Model | 业务模型 | 客户端内部使用的稳定业务数据，不应被接口字段随意牵动 |
| Mapper | 数据转换器 | 把接口数据对象转换成业务模型，隔离接口变化 |
| Repository | 统一数据入口 / 数据仓库 | 业务层通过它取数据，不必知道数据来自接口、缓存还是临时实现 |
| DataSource | 具体数据来源 | 真正访问网络、数据库、缓存等数据来源的实现 |
| RealRepository | 正式数据实现 | 接入正式后端接口后在生产环境使用的实现 |
| Fake | 可运行的临时替代实现 | 正式接口未发布时，用受控的临时数据先跑通业务流程 |
| Mock | 测试模拟对象 | 测试时指定成功、失败、超时、登录失效等返回结果 |
| sampledata | 示例数据 | 只用于预览、演示或测试的数据，不能混入正式版本 |
| Preview | 界面预览 | 不运行完整应用也能查看页面效果的开发能力 |

`Fake` 和 `Mock` 容易混淆：`Fake` 重点是让尚未接入正式接口的业务可以运行；`Mock` 重点是让测试能够稳定制造各种返回情况。

### 测试、构建与交付

| 专业术语 | 中文意思 | 在本流程里是做什么的 |
|---|---|---|
| Debug | 调试版本 | 开发使用，可以包含调试入口、临时实现和示例数据 |
| Release | 正式发布版本 | 真正交付用户的版本，不能依赖测试数据或调试能力 |
| Unit Test | 单元测试 | 单独验证一个方法、业务规则或组件 |
| Integration Test | 集成测试 | 验证多个组件连接后能否正确协作 |
| E2E | 端到端测试 | 从用户入口到最终结果完整验证一条业务链路 |
| BDD | 业务行为验收描述 | 用具体场景描述需求应该表现出的行为 |
| Given / When / Then | 前提 / 操作 / 预期结果 | BDD 场景的三个组成部分 |
| Journey | 界面流程测试 | 在设备或模拟器上按步骤操作页面并检查可见结果 |
| Maestro | 可选的界面自动化工具 | Journey 不适用且项目允许时，可作为备选界面测试引擎 |
| A11y | 无障碍能力 | 检查 TalkBack、焦点、触摸区域、状态朗读等体验 |
| Lint | 静态代码检查 | 不运行完整业务，直接检查代码和 Android 配置中的常见问题 |
| Gradle | Android 构建工具 | 负责编译、测试、静态检查和打包 |
| R8 / ProGuard | 正式包压缩与混淆 | 减小安装包，也需要防止出现调试正常但正式包失败的问题 |
| CI | 持续集成 | 在服务器上自动执行构建、测试和检查 |
| Gate | 交付门禁 | 必须满足的检查条件；不满足就不能声明交付通过 |
| Evidence | 执行证据 | 本轮真实生成的测试日志、报告和结果文件 |

### Git、路由与机器文件

| 专业术语 | 中文意思 | 在本流程里是做什么的 |
|---|---|---|
| Git baseline | Git 基线 | 记录需求开始时的代码位置，用来界定本需求改了什么 |
| Diff | 代码差异 | 相对 Git 基线新增、修改或删除的内容 |
| committed | 已提交改动 | 已经写入 Git 提交、但仍属于当前需求基线之后的改动 |
| staged | 已暂存改动 | 已执行 `git add`，但尚未提交的改动 |
| unstaged | 未暂存改动 | 已修改，但尚未执行 `git add` 的改动 |
| untracked | 未跟踪文件 | 新建但尚未纳入 Git 管理的文件 |
| Route | 自动路由 | 根据最终代码差异判断需要调用哪些专项检查 |
| Schema | 数据结构规则 | 规定机器文件必须有哪些字段、字段是什么类型 |
| Snapshot | 当前状态快照 | 固定某一时刻的需求、代码或证据摘要，供后续核对 |
| Hash | 内容指纹 | 用一段固定值判断文件或代码是否在检查后发生变化 |
| P0 / P1 | 严重 / 高优先级问题 | 会阻断交付，需要优先处理的问题级别 |
| `USER_INPUT_REQUIRED` | 需要用户补充资料或授权 | 缺少关键输入，AI 不能安全地继续判断 |
| `BLOCKED` | 当前无法继续 | 存在无法由当前流程自行解除的阻塞条件 |

接口尚未发布时，可以先建立业务模型和统一数据入口，使用 `Fake` 跑通业务与测试；正式接口发布后，再补充 `DTO`、`Mapper` 和正式数据实现，最后重新执行接口、业务、构建与静态检查。流程允许先开发，但不允许把推测字段冒充成正式接口契约。

## 日常只改一个配置

编辑：

```text
/Users/example/work/MyPython/ai-skills/android-delivery-skills/profiles/local.yaml
```

首次使用时，从同目录的 `local.example.yaml` 复制一份并按中文注释填写。`local.yaml` 是本机运行输入，已被 Git 忽略；切换项目、分支或需求资料不会进入 Skill 源码提交。当前需求目录同样是运行工作区，不作为流程源码版本化。

- 仓库只提交不含真实路径和业务资料的 `local.example.yaml`，日常不要修改它。
- 不要使用 `git add -f` 强行提交 `local.yaml`、`current-requirement`、当前需求文档、截图、测试用例或报告；确需长期保存时复制到用户明确指定的归档位置。
- Git 忽略只负责隔离源码提交，不会跳过流程校验：需求正文、UI/API 输入仍会参与摘要，需求变化后旧路由和最终证据仍会失效。

通常只需要改：

- `project_path`：Android 项目路径
- `branch`：目标分支
- `requirement_file`：需求 Word / Markdown / TXT 文件
- `requirement_workspace`：串行需求目录策略，通常保持示例中的 `rotate / 3 个 / 7 天`，不需要每个需求修改
- 可选 `ui.links` / `ui.screenshots`
- 可选 `api.links` / `api.files` / `api.status`

首次使用时，从 `workspace_root` 安装脚本依赖：

```bash
python3 -m pip install -r ai-skills/android-delivery-skills/requirements.txt
```

## 最短调用

以后可以直接说：

```text
使用 android-implement-and-verify。
```

默认行为：

1. 读取 `profiles/local.yaml`。
2. 读取 `requirement_file` 需求文档。
3. 只做需求理解。
4. 等你确认理解是否正确。
5. 未确认前不进入最终方案、不改代码。

同一需求编码中途修改了 `requirement_file` 时，可以再次执行 `delivery.py init`。它不会删除 Git 基线，而是对比最近确认修订和现有追溯表，输出增改删、替代及逐项确认状态。用户确认后由 AI 更新 `<requirement_dir>/test-cases/requirement-revision.json`，再执行 `confirm-requirement-update`；下次变化从最近确认版本继续比较。

修订规则：`PENDING/CONFLICT` 不推进版本，`REJECTED` 不进入总需求；删除项必须选择删除实现、保留兼容或停止未完成工作。只在聊天中补充的内容必须先同步到 `requirement_file`。

`requirement-revision.json` 由 AI 根据已经确认的 BDD 自动生成，用户不需要手写 JSON、修订号或 Then 摘要；用户只确认业务变化和删除处置。文件结构以 `android-implement-and-verify/references/requirement-revision.schema.json` 为准。

英文枚举只属于 `requirement-revision.json` 的机器协议。AI 给用户展示需求修订时必须转换为中文，例如“修改 / 已确认”“新增 / 已确认”“未变化 / 已确认”；待确认、冲突、撤回和删除处置也必须使用中文，不能要求用户理解英文状态。

### 开始下一个独立需求

`requirement_workspace.mode` 推荐保持 `rotate`：每个串行需求使用独立目录，机器编号负责稳定隔离，后面的中文名称负责让人看懂，例如 `REQ-20260721-001-视频下载页登录拦截`。目录内的 `需求说明.md` 给用户阅读，`requirement-workspace.json` 供脚本判断活动、完成或取消状态。

只有你明确说“上一需求已经完成/取消，开始下一个需求”时才轮换。同一需求中途补充、修改、删除或只重跑测试时不轮换。先把新需求文件放到当前需求目录之外，再执行预览：

```bash
python3 ai-skills/android-delivery-skills/scripts/requirement_workspace.py next \
  --title "视频下载页登录拦截" \
  --requirement-file /path/to/new-requirement.docx \
  --previous-title "上一需求中文名称" \
  --previous-outcome 已完成
```

预览不会修改文件。确认名称、上一需求结论和路径正确后，给同一命令追加 `--confirm`。轮换要求目标 Android 项目没有未提交修改；脚本不会自动提交、暂存或清理代码。两个窗口同时确认时只有获得单写锁的窗口执行，另一个窗口会停止，不会删除或覆盖前者的目录。完成后的固定顺序是：

1. `delivery.py init` 读取新需求。
2. 你确认新需求理解。
3. `delivery.py check-env --new-requirement` 建立新需求 Git 基线。

查看当前活动需求和回收候选：

```bash
python3 ai-skills/android-delivery-skills/scripts/requirement_workspace.py status
```

历史需求不会在每次交付后立即删除。只有“不是当前活动需求、状态已经完成或取消、超出最近 `keep_completed` 个、并超过 `cache_retention_days` 天”四项同时满足才成为候选；`tempfile` 使用相同时间门槛。`next` 预览会列出本次候选，追加 `--confirm` 表示同时确认轮换和这些候选的延迟回收；也可以单独运行 `prune` 预览，确认后再执行 `prune --confirm`。如果轮换已经成功但旧缓存因权限等原因回收失败，新需求仍可正常使用；修复原因后只重试 `prune`，不要再次执行 `next`。

### 需求文件读取失败时

读取逻辑保持单一职责，不自行搜索其他文件或推测需求：

1. 路径固定按 `workspace_root → requirement_dir → requirement_file` 解析，并输出最终绝对路径。
2. 支持 `.docx`、`.md`、`.markdown`、`.txt`；PDF 可作为 UI 资料，但作为需求正文时需先转换为支持格式。
3. DOCX 使用 Python 标准库读取 OOXML 正文，不要求 IDE 额外安装文档解析库。
4. 文件为空、损坏或格式不支持时，脚本会说明原因并停止；修正路径、重新导出 Word 或转换格式后重试。

完整交付不需要维护 `base_branch`。`check-env` 会在干净工作区记录本需求开始时的 HEAD 和需求起点；重复执行只复用原起点，不会隐藏中途已经提交的改动。只有你明确结束上一需求并开始新的串行需求后，AI 才使用 `check-env --new-requirement` 建立新起点。需求修订确认不会更新 Git 基线。`route` 只收集该基线之后的 committed、staged、unstaged 和 untracked 变化，并保留 `A/M/D/R` 状态与真实修改片段。工作区不干净时会停止，由你决定如何处理，脚本不会自动 stash、提交或清理。

同一 `local.yaml` 同时只允许一个活动交付窗口推进状态；其他窗口可以只读检查，但不要同时执行 `check-env`、需求确认、`route` 或最终证据命令。远程设计/API 资料用于正式通过时应登记本地导出、截图或明确版本摘要；整个需求取消时不生成空验收集合或交付通过，先由你决定代码撤销和兼容处置。

## 确认后继续

如果需求理解正确，你说：

```text
理解正确，继续。
```

然后直接进入编码：

1. 修改前校验项目路径、目标分支和干净工作区，并记录当前需求 Git 基线。
2. 物化全部已确认 Then 的需求修订清单并执行 `confirm-requirement-update`。
3. 读取相关代码并复用现有链路。
4. 直接实现需求，不再固定输出一轮前置分析报告。
5. 只有遇到关键资料缺失、高风险改动或分支/工作区异常时才暂停询问。
6. 首次编码后先运行受影响测试和必要编译；后续完善、修改、删除或修复继续使用同一局部循环，不自动执行完整 route。
7. 只有你当前或最初明确要求最终检查、完整交付或准备提交时，才执行接口、测试、稳定性和代码质量完整门禁；检测到 UI 变更时提示单独运行 UI 验收。
8. 有 UI 基准但尚未完成独立 UI 验收时，只能报告“代码与自动测试完成，UI 验收待执行”。

## 编码后怎么说

你说“这个点再完善一下”“修改这段逻辑”“删除这个实现”或“修复这个问题”时，AI 自动进入局部迭代：验收语义不变就不重读需求、不运行全部 Reviewer，只做最小修改、受影响测试和必要编译；删除生产代码时额外检查调用方。

你说“业务要求改成……”时，AI 只确认受影响的需求修订，再进入同一个局部测试循环。你说“最终检查”“完整交付”或“准备提交”时，AI 才基于最终代码完整执行一次 route 和门禁。已生成最终报告后代码再次变化，旧报告会失效，但完善期间不需要每次立即重跑完整流程。

## 你会看到什么

需求、变更、阶段提示、测试结果、失败原因、授权请求和最终报告全部使用自然中文。需求场景显示“前提 / 操作 / 预期结果”，不会要求你理解机器内部英文状态；失败时会同时说明原因、已完成范围、未完成范围、解除条件和你下一步需要做什么。

`REQ-001`、`BDD-001/T1`、文件路径、Gradle 命令、类名和接口路径属于稳定技术标识，可以保留并附中文说明。`requirement-revision.json`、`delivery-result.json` 等机器附件继续使用英文枚举供脚本解析，但最终回复只优先展示中文摘要，不会把机器 JSON 正文直接交给你阅读。

## 整体流程顺序(一图看懂)

```text
① delivery.py init    读需求 → 输出 BDD（前提/操作/预期结果）
   └─ 停,等你确认「理解正确,继续」
                          ↓
② delivery.py check-env   查 Git 分支/干净工作区 → 记录 Git 基线和需求起点
③ delivery.py confirm-requirement-update   确认最新总需求和全部原子验收项 → 开始编码
   └─ 首次编码
                          ↓
④ 编码后局部迭代（可以重复多次）
   ├─ 实现完善：最小修改 + 受影响测试 + 必要编译
   └─ 需求语义变化：只确认受影响修订，再回到局部迭代
                          ↓ 你要求最终检查 / 完整交付 / 准备提交
⑤ delivery.py route   按当前需求基线后的最终 Git Diff 自动路由审查并保存条件门禁快照

   【核心·业务逻辑层】(route 自动逐个调用,必先过)
     1. android-review-diff        ← 必跑:diff 影响范围
     2. android-verify-api-contract  ← 仅当有接口变更才跑
     3. android-review-code-quality  ← 必跑:质量/架构
     4. android-audit-stability     ← 必跑:稳定性/兼容性
     5. android-test-and-fix        ← 必跑:测试闭环/全绿门禁
   【独立·UI 校验】(route 只提示,用户单独调用)
     6. android-verify-ui          ← 截图与设计还原验收,不进自动队列

⑥ delivery_gate.py validate
   └─ 核对确认修订、最终代码、route 条件门禁、执行收据和专项结果；退出码 0 才可声明通过
```

脚本职责保持分离：

- `scripts/delivery.py`：只编排需求读取、修订确认、环境检查和专项 Skill 路由。
- `scripts/git_changes.py`：只读检查分支、工作区、四类 Git 变化、`A/M/D/R`、真实片段和最终摘要，不判断业务或路由。
- `scripts/requirement_snapshot.py`：只校验和保存连续需求修订、有效义务及文本差异，不判断业务语义或修改 Git。
- `scripts/requirement_inputs.py`：只对需求正文及配置声明的 UI/API 链接和本地资料生成输入摘要，不访问网络或判断业务。
- `scripts/delivery_gate.py`：校验最终机器报告和证据新鲜度，并生成同目录中文摘要；不运行测试、不修改代码。
- `scripts/android_project_capabilities.py`：首次处理项目、构建配置变化或 task 未知时，只读发现模块、variant 和 Gradle task；普通业务修改不必重复运行。
- `scripts/execution_evidence.py`：只执行已经选择的单 gate 命令，按 attempt 保留日志、testcase 和报告摘要。
- `scripts/specialist_result.py`：只校验专项统一结果、P0/P1 和证据文件摘要。

最终机器报告写入 `<requirement_dir>/test-results/delivery-result.json`。当前契约为 version 4，旧的跨 gate 收据、空人工说明和无待验项的设备待验结论不能继续通过。AI 先用 `snapshot` 获取当前摘要，按 `android-implement-and-verify/references/delivery-result.schema.json` 生成报告，再校验：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py snapshot
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py validate
```

第二条命令会同步生成 `<requirement_dir>/test-results/delivery-summary.md`。用户只需阅读中文摘要；JSON、哈希和证据路径属于机器附件。退出码为 `0` 才表示最终通过证据仍与当前需求和代码一致；未完成或受阻也会生成摘要，但不能写成通过。该命令不会自动提交 Git。

`android-lint` 默认只执行目标项目自己的 Android Gradle Lint task。最终机器证据必须引用本轮 XML 或 SARIF；HTML 可保留给人查看。报告中的 Fatal/Error 即使因 `abortOnError=false` 得到零退出也会阻断。当前流程不安装或强制外部自定义 Lint，项目已有插件时保持原状。

首次处理项目、构建配置变化或 task 未知时先发现真实能力；普通业务修改直接使用已确认 task。最终命令通过收据执行，不要手填退出码和测试数：

```bash
python3 ai-skills/android-delivery-skills/scripts/android_project_capabilities.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml

python3 ai-skills/android-delivery-skills/scripts/execution_evidence.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --id E-UNIT \
  --gate android-test-and-fix \
  --report app/build/test-results/testDebugUnitTest/TEST-example.xml \
  -- ./gradlew :app:testDebugUnitTest

python3 ai-skills/android-delivery-skills/scripts/specialist_result.py path \
  --config ai-skills/android-delivery-skills/profiles/local.yaml
python3 ai-skills/android-delivery-skills/scripts/specialist_result.py validate <专项结果.json>
```

`route`、收据、日志和专项结果均放在配置对应的外部状态目录，不修改 Android 项目；同一证据 ID 重跑会生成 `attempt-001/002` 等不可覆盖记录。测试/迁移收据必须包含本轮实际执行数大于零的 JUnit；最终报告只引用选定收据路径和 SHA-256，并把每个自动覆盖的 Then 映射到真实通过的 testcase。接口由对应专项证明；UI/A11y、安全、泄漏和性能由对应专项或允许的完整人工证据证明，不能用任意成功命令占位。

人工覆盖不能只写“人工通过”：必须记录执行人、带时区时间、设备/环境、逐步操作、预期、实际结果以及产物；确实没有产物时说明原因。使用 `LOCAL_PASS_DEVICE_PENDING` 时，`pending_capabilities` 至少包含一个真实设备待验项，并引用同能力的 `UNVERIFIED/BLOCKED` 专项或人工证据；`FULL_PASS` 不允许保留待验项或专项能力中的 `UNVERIFIED/BLOCKED`。

需要单独排查 Git 收集结果时可以运行：

```bash
python3 ai-skills/android-delivery-skills/scripts/git_changes.py \
  --repo <Android项目路径> --base-branch <可选对比分支>
```

### 自动 vs 手动 速查

| Skill | route 自动触发 | 可单独「使用」 |
| --- | --- | --- |
| android-review-diff | ✅ 必跑 | ✅ |
| android-verify-api-contract | ✅ 有接口变更才跑 | ✅ |
| android-review-code-quality | ✅ 必跑 | ✅ |
| android-verify-ui | ❌ 只提示，不自动执行 | ✅ 手动独立调用 |
| android-audit-stability | ✅ 必跑 | ✅ |
| android-test-and-fix | ✅ 必跑 | ✅ |

核心原则：**在已确认范围内最小修改；每个 Skill 恪守单一职责；BDD 必须物化为测试；测试或 P0/P1 失败必须修复重跑；必需门禁全绿才可交付**。每个 Skill 仍可脱离 route 单独运行。

第二轮条件能力不是每次全跑：接口变化查 OpenAPI，持久化变化查迁移，生命周期/热路径按语义判断泄漏和性能，UI 检查 A11y，权限/WebView/用户数据检查安全隐私。没有真机时继续构建、单测、lint、契约、静态审查和模拟器可执行项；真机专项写“未验证”，不能冒充通过，也不因此停止其他流程。

## 外部链接读取

Figma、YApi、Apifox、Swagger 等链接打不开或需要登录时，不再默认终止流程：

1. 优先读取本地 `requirement_file`、`ui.directory`、`api.files`。
2. 当前需求涉及已配置的 `api.links` 时，先尝试复用本机 Chrome 登录状态读取真实接口页面。
3. 如果只看到登录页、401/403 或无权限，AI 必须请你在 Chrome 登录或授权；你不需要提供账号、密码、Cookie 或 Token，登录后只需回复“已经登录”。
4. 等待登录时暂停依赖该契约的代码；不能因为存在旧截图就静默跳过。只有你明确选择“使用现有本地证据”“跳过链接”或“先 mock/fake”后才降级。
5. 读取成功后 AI 主动把导出 JSON/OpenAPI/Postman、完整截图或结构化摘要保存到 `<requirement_dir>/api/` 并登记到 `api.files`，下次换 AI 或登录失效仍可核验。
6. 与当前需求无关的接口链接不触发登录询问；在线页面和本地证据冲突时保持待确认，不自行选一个答案。

## Figma UI 最短路径

如果会话已接入 Figma MCP，UI 相关需求默认优先走：

1. Figma MCP 读取 design context / metadata / variables / screenshot。
2. 先确认目标项目使用 XML View、Compose 还是混合实现，并输出精简 Design Spec Gate；不能因为有 Figma 链接就切换技术栈。
3. 只有 XML View 部分调用 `figma-android-xml`，由它生成 XML、Drawable、Color、Dimen 和预览资源；Delivery 不复制它的内部生成规则。
4. UI 资源和 XML 生成完毕后，主流程先检查固定文案资源化、动态 `tools:text`、装饰/功能图片语义和项目资源复用，再接管必要的 Kotlin/Java、ViewBinding/DataBinding、Adapter、状态和业务连线。Compose 部分直接沿用项目现有结构。
5. `android-test-and-fix` 验证业务行为；编码后如有 UI 变更，主流程提示用户单独调用 `android-verify-ui` 消费设计基准、生成结果和运行截图做视觉/A11y 验收。

如果需要把 Figma 节点保存为本地视觉基准，使用当前真实入口：

```bash
python3 ai-skills/figma-android-xml/scripts/figma_workflow.py fetch \
  "https://www.figma.com/design/FILE_KEY/NAME?node-id=471-131" \
  --scale 1
```

该命令只下载 PNG，并在终端输出实际保存路径；它不会生成 `spec.json`、preview HTML 或 XML。Figma MCP 提供结构化数据，完整 XML 生产由 `figma-android-xml` Skill 执行，二者职责不同。

脚本每次运行会清理上次缓存，因此多个 Figma 链接必须放在同一条 `fetch` 命令中。把本轮采用的 PNG 保存到 `<requirement_dir>/ui/`，或将实际路径登记到 `ui.screenshots` / `ui.directory`；需求输入摘要才会绑定图片 SHA-256，避免同一 URL 更新后继续复用旧证据。

## Skill 职责总表

| Skill | 负责什么 | 不负责什么 | 默认调用时机 |
| --- | --- | --- | --- |
| `android-implement-and-verify` | 确认需求、BDD、生成测试、编码、动态路由、自修复、重验和交付门禁 | 发布上线、生产数据、未授权 Git 提交 | 完整需求、Bug 或迭代的唯一入口 |
| `android-review-diff` | 检查是否改对、改多、漏改，以及无关 diff 和业务回归 | 通用代码质量、API 字段、UI 像素和测试执行 | 最终交付必跑；局部迭代仅在范围不清或用户明确要求时调用 |
| `android-verify-api-contract` | 核验 OpenAPI、endpoint、Request/Response、DTO、mapper、错误码和兼容性 | 产品需求、通用架构、UI 和完整测试门禁 | API、DTO 或网络 Repository 变更时 |
| `android-review-code-quality` | 检查架构一致性、可维护性、依赖边界、重复逻辑和资源规范 | 需求覆盖、API 契约、运行时专项风险和 UI 还原 | 最终交付必跑；局部迭代只在架构或职责边界变化时调用 |
| `android-audit-stability` | 检查崩溃、动态泄漏、性能、安全隐私、ANR、协程和版本兼容 | diff 范围、通用风格、API 契约和设计还原 | 最终交付必跑；局部迭代只在对应高风险变化时调用 |
| `android-test-and-fix` | 把 BDD 物化为 Unit、迁移、A11y、仪器或 Journey 测试，执行并修复失败 | 需求确认、接口契约来源、设计判断和发布 | 局部迭代执行受影响测试；最终交付执行完整门禁 |
| `android-verify-ui` | 独立验收布局、截图、设计还原和人工/设备 A11y 表现 | 自动测试用例、接口、数据存储、支付和提交 | 用户在 UI/A11y 变更完成后单独调用 |

### 单独调用示例

```text
使用 android-review-diff，只检查这次 diff，不修改代码。
使用 android-verify-api-contract，核验接口实现是否符合文档。
使用 android-review-code-quality，检查架构和可维护性。
使用 android-audit-stability，排查崩溃、泄漏和协程风险。
使用 android-test-and-fix，补齐测试并修复到通过门禁。
使用 android-verify-ui，对照设计稿验收实际页面。
```

单独调用审查型 Skill 默认只报告。只有用户明确要求“先分析别改”，或继续编码会脑补、误改或高风险破坏时，专项 Skill 才前置使用。

## Journey UI 测试(Android CLI Agent 优先)

Journey 测试用例归 `android-test-and-fix`。老项目 AGP 保持不动，只构建并安装 APK；默认由当前 AI 会话使用 Android CLI/adb 严格执行 XML action。独立 AGP 9 壳只作为已经初始化后的可选回退。`android-verify-ui` 可以复用 Journey 截图做设计还原验收，但不生成或管理测试用例。

当前需求的 Journey XML 默认放在 `<requirement_dir>/test-cases/journeys/<需求作用域>/`。完整流程使用 Git 基线 ID、确认修订及需求/UI/API 输入摘要，单独调用时使用当前输入摘要；默认 Agent 直接读取当前作用域，可选壳中的 `src/main/journeys/` 只是执行暂存目录，因此串行需求或外部资料变化不会复用旧测试用例。

Journey 测试用例由 `android-test-and-fix` 根据已确认需求和 BDD 自动分析并生成，用户不需要提供 XML、action/step 或任务名。只有需求本身缺少前置条件或预期结果时，才需要用户补充业务含义。

并非所有需求都运行 Journey：无 UI 影响返回 `SKIPPED_NO_UI`；只有布局、样式和资源变化返回 `SKIPPED_VISUAL_ONLY`。涉及 UI 行为时再按原子 Then 聚合 `FULL/PARTIAL/NONE`，只为稳定可覆盖部分生成 Journey。`NO_JOURNEY_FOUND` 只表示“已有 Then 分配给 Journey，但测试用例尚未成功物化”。

是否调用 Journey 由 `android-test-and-fix` 根据业务需求、已确认 BDD 和实际 diff 自动判断，不需要用户选择。下面的 `--ui-impact` 只属于可选壳脚本，用来防止未判断适用性就启动设备和壳流程。

判断采用“两次判断、一次执行”：需求确认后先做候选初判和测试设计，编码后结合实际 diff 做最终判定；只有最终仍适合 Journey 才启动默认 Agent 或可选壳。两次结论不一致时以实际 diff 为准，并在测试报告中说明原因。

```bash
# 可选壳：只有默认 Agent 不可用且壳已经初始化时才执行
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --ui-impact behavior \
  --applicability PARTIAL \
  --covered-then BDD-001/T1 \
  --uncovered-then BDD-001/T2

# 已装好 APK 时跳过构建
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --ui-impact behavior \
  --applicability FULL \
  --covered-then BDD-001/T1 \
  --skip-build

# 单独只嗅探包名（排查用）
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/detect_package.py \
  --project-path <项目路径>
```

`--skip-build` 只要求设备中存在 `app_package_name`，不要求目标源码目录有效。设备未就绪时只跳过 Journey 等设备测试，本地单测、构建和 lint 仍要执行。默认 Agent 不要求 Android Studio 初始化；只有用户决定长期使用可选壳时，才执行一次 `New > Journey Test`。

Journey 只有在 Gradle 成功且本轮存在测试数大于 0 的结构化 JUnit XML 时才返回 `PASS`；普通构建图片不会被当成截图证据。报告按需求作用域保存到 `<requirement_dir>/test-results/journey-harness/<需求作用域>/result.json` 和 `result.md`。退出码：`0` 真实通过、明确跳过或仅预检 / `1` 环境、壳或证据不足 / `2` 连续两次结构化 UI 断言失败。`PREFLIGHT_PASS` 只代表预检通过，不代表测试通过。
