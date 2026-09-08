# Android Delivery Skills 当前流程图

> 本文是 [FLOW_OVERVIEW.md](FLOW_OVERVIEW.md) 的图形索引，只描述当前轻量流程，不代表额外状态机或脚本门禁。

## 目录

0. [陌生项目首次接手](#diagram-onboarding)
1. [完整主流程](#diagram-main)
2. [需求模糊时的决策树前沿](#diagram-clarify)
3. [Figma 与 API 输入](#diagram-inputs)
4. [纵向切片与紧反馈](#diagram-feedback)
5. [增量变化分流](#diagram-incremental)
6. [最终验证路由](#diagram-final)
7. [多需求并行](#diagram-parallel)
   1. [合并规则（git worktree）](#diagram-merge)
8. [新窗口恢复](#diagram-resume)
9. [文档与代码落点](#diagram-layout)

<a id="diagram-onboarding"></a>
## 零、陌生项目首次接手

陌生项目接手是具体需求主流程之前的窄入口，不改变原交付流程。只清理进入当前需求所需的知识缺口；接手结果不能替代需求规格和验收证据。

```mermaid
flowchart TD
    INPUT["收到 Android 工作请求"] --> UNKNOWN{"用户明确表示首次接手、完全不了解或要求摸底？"}
    UNKNOWN -- "否" --> DELIVERY["android-implement-and-verify"]
    UNKNOWN -- "是" --> ONBOARD["android-onboard-existing-project：只读调查与安全验证"]
    ONBOARD --> MAP["项目地图、验证基线、风险与未知项"]
    MAP --> SAVE{"项目事实需要跨需求复用或写入项目文档？"}
    SAVE -- "是" --> CONTEXT["document/project-context/overview.md"]
    SAVE -- "否" --> READY["保留当前接手结论"]
    CONTEXT --> READY
    READY --> REQUEST{"已有具体需求？"}
    REQUEST -- "否" --> END["停止；不修改生产代码"]
    REQUEST -- "是" --> DELIVERY
```

<a id="diagram-main"></a>
## 一、完整主流程

图中展示正常推进路径；任意节点均可进入 [增量闭环](#diagram-incremental)，收拢后回到受影响工作，不必从头重走。

流程说明：

1. 先读取项目、需求配置、Git、代码、测试和 UI/API 来源；已有改动先由用户在原工作区保存、提交或隔离，建立独立干净工作区后才记录基线，缺失引用则让用户决定来源。
2. 只澄清会改变行为、范围或验收的问题；未知清空后才形成一份 `draft spec.md`。
3. 用户确认最新完整规格后改为 `confirmed`，先形成 `SPEC` 边界提交并恢复干净工作区；小需求按 `BDD-##`、复杂需求按 `SLICE-##` 逐个完成纵向切片。
4. 每个切片只跑受影响验证，审查完整工作区后自动形成原子提交。
5. 用户明确要求最终交付时才完整验证并审计 `baseline_commit...HEAD`；推送、集成和发布仍分别需要用户授权。

```mermaid
flowchart TD
    START["收到 Android 需求"] --> FACTS["读取项目、当前需求配置、Git、代码、测试、UI/API 来源"]
    FACTS --> DIRTY{"已有改动或引用缺失需要用户决定？"}
    DIRTY -- "是" --> DECIDE["用户在原工作区保存、提交或隔离已有改动<br/>缺失引用由用户决定来源"]
    DECIDE --> FACTS
    DIRTY -- "否" --> FRONTIER["建立需求决策树并询问当前前沿"]
    FRONTIER --> UNKNOWN{"仍有会改变行为或验收的未知？"}
    UNKNOWN -- "是" --> FRONTIER
    UNKNOWN -- "否" --> SPEC["写一份 draft spec.md：BDD、范围、来源、决策、测试边界"]
    SPEC --> CONFIRM{"用户确认最新完整规格？"}
    CONFIRM -- "否或提出变化" --> FRONTIER
    CONFIRM -- "是" --> CONFIRMED["spec.md = confirmed；自动形成 SPEC 边界提交"]
    CONFIRMED --> SLICE["BDD-## / SLICE-##：失败证据 -> 最小实现 -> 受影响验证 -> 工作区审查"]
    SLICE --> COMMIT["自动形成带稳定 ID 的原子提交并恢复干净工作区"]
    COMMIT --> MORE{"还有已确认切片？"}
    MORE -- "是" --> SLICE
    MORE -- "否" --> FINAL{"用户明确要求最终检查或准备提交？"}
    FINAL -- "否" --> WAIT["以 spec + 切片提交保留可恢复检查点"]
    FINAL -- "是" --> VERIFY["分层审查 baseline...HEAD + 一次适用测试、Lint 和专项"]
    VERIFY --> CHANGED{"修复后代码又变化？"}
    CHANGED -- "是" --> VERIFY
    CHANGED -- "否" --> RESULT["按 BDD 写 docs/result.md 并自动形成结果提交"]
    RESULT --> AUDIT["对最新 HEAD 做最终整体审计并确认工作区干净"]
    AUDIT --> END["交付结论；推送、集成或发布仍需单独授权"]
```

<a id="diagram-clarify"></a>
## 二、需求模糊时的决策树前沿

流程说明：

1. Agent 先查代码、文件和链接，能自行证明的事实不转问用户。
2. 把真正需要产品决定的问题组织成决策树，每轮只处理前置条件已明确的当前前沿。
3. 同一轮列出全部互不依赖问题；用户可以回答其中一个、多个或同时纠正旧需求。
4. 完整吸收本轮变化后重新计算前沿，不重复已解决问题，也不丢失未回答问题。
5. `待确认` 非空时不新增或改写任何 BDD，保留已有且未受影响的 BDD；清空后补齐 BDD 与计划验证，再请求规格确认，确认后才进入实现。

```mermaid
flowchart TD
    INPUT["汇总用户输入、代码事实、Figma/API 和已有实现"] --> TREE["建立会影响行为、范围和验收的决策树"]
    TREE --> FIND["选择前置事实已经明确的问题"]
    FIND --> GROUP["同轮列出全部互不依赖问题：Q1、Q2..."]
    GROUP --> ANSWER["用户回答任意一个或多个问题，也可纠正旧需求"]
    ANSWER --> MERGE["完整吸收所有答案，以最新明确表述替换冲突旧内容"]
    MERGE --> LEFT{"当前前沿还有问题？"}
    LEFT -- "是" --> GROUP
    LEFT -- "否" --> DEPENDENT{"答案是否解锁后续依赖问题？"}
    DEPENDENT -- "是" --> FIND
    DEPENDENT -- "否" --> RESTATE["补齐受影响 BDD 与计划验证<br/>写入 draft spec.md 并复述"]
    RESTATE --> CONFIRM{"用户纯确认最新完整规格？"}
    CONFIRM -- "否" --> TREE
    CONFIRM -- "是" --> BDD["写入 confirmed；此后才允许实现"]
```

<a id="diagram-inputs"></a>
## 三、Figma 与 API 输入

流程说明：

1. 链接、截图、导出文件、文档和聊天都是有效输入，但只记录实际可证明的内容。
2. Figma 输入先确认 XML View 或 Compose；XML 页面在规格确认后调用 `figma-android-xml`。
3. 生成 XML、构建 APK 或页面能打开都不代表 UI 通过，仍需真实截图和交互验收。
4. API 输入立即创建或增量更新唯一 `api/api.md`，并与需要留存的原始资料共置。
5. 来源冲突或未知会改变 DTO、序列化、业务行为或验收时询问用户，不自行猜测。

```mermaid
flowchart TD
    INPUT["链接、截图、导出文件、文档或聊天"] --> READ["读取实际可访问事实并保留来源"]
    READ --> KIND{"资料类型"}
    KIND -- "Figma/UI" --> STACK{"项目是 XML View 还是 Compose？"}
    STACK -- "XML View 且规格已确认" --> XML["调用 figma-android-xml 生成 XML/资源"]
    STACK -- "Compose" --> COMPOSE["沿用项目 Compose 实现，不调用 XML Skill"]
    XML --> UI["真实页面截图、状态、交互和 A11y 验收"]
    COMPOSE --> UI
    KIND -- "API" --> APIMD["创建或增量更新唯一 api/api.md"]
    APIMD --> CONFLICT{"来源冲突或未知会改变实现？"}
    CONFLICT -- "是" --> ASK["询问用户采用决定"]
    CONFLICT -- "否" --> IMPLEMENT["按已证明契约实现并测试"]
    ASK --> APIMD
```

<a id="diagram-feedback"></a>
## 四、纵向切片与紧反馈

流程说明：

1. Agent 根据交付结果、必要上下文和验证边界决定整体交付或显式切片；紧密相关的多条 BDD 可一起交付，需分组或依赖计划时使用 `SLICE-##`，不按数量、行数或累计 Token 判大小。
2. 每个边界内逐条确认测试因缺少目标行为而失败，再编写最小实现使其通过。
3. 当前测试转绿后只追加直接受影响模块测试和必要编译，再审查 staged、unstaged 和 untracked 内容。
4. 自动形成一个中文语义原子提交，工作区重新干净后才能默认进入下一切片；整片取消/替代按增量闭环收拢。
5. 疑难 Bug、偶发故障和性能回归先建立紧反馈入口，再最小化失败；偶发问题用固定轮次统计复现率。
6. 修复前通常列出 2–5 个有依据的可证伪假设；仅有一个合理候选时记录排除依据、不凑数，再用单假设、单变量探针证伪。
7. 无法复现或同一根因连续三轮没有进展时，报告证据和阻塞条件，不猜因修改。

```mermaid
flowchart TD
    BDD["工作区干净；选择 BDD-## / SLICE-##<br/>记录 slice_base_commit = HEAD"] --> BOUNDARY["选择最高可观察且足够快的测试边界"]
    BOUNDARY --> RED["写失败测试并实际确认 Red 原因"]
    RED --> MIN["编写刚好满足行为的最小实现"]
    MIN --> GREEN["重跑当前测试并确认 Green"]
    GREEN --> BEHAVIORS{"当前边界还有待实现 BDD？"}
    BEHAVIORS -- "是" --> BOUNDARY
    BEHAVIORS -- "否" --> IMPACT["运行直接受影响模块测试和必要编译"]
    IMPACT --> SCOPE["审查 staged、unstaged、untracked；只保留当前 Slice"]
    SCOPE --> CHECKPOINT["自动形成带 BDD-## / SLICE-## 的原子提交<br/>并确认工作区干净"]
    CHECKPOINT --> NEXT{"下一个 Slice？"}
    NEXT -- "是" --> BDD
    NEXT -- "否" --> READY["等待最终交付时一次完整验证"]

    BUG["疑难 Bug、偶发故障或性能回归"] --> LOOP{"能建立可重复命中准确症状的紧反馈入口？"}
    LOOP -- "否" --> BLOCK["报告尝试、缺少条件和阻塞；不猜因修改"]
    LOOP -- "是" --> REPRO["最小化 -> 假设排序 -> 单变量证伪 -> 最小修复 -> 受影响回归"]
    REPRO --> PASS{"最小失败与回归通过？"}
    PASS -- "是" --> FIXED["记录根因、证据和验证范围"]
    PASS -- "否" --> PROGRESS{"同一根因三轮内有新证据？"}
    PROGRESS -- "是" --> REPRO
    PROGRESS -- "否" --> BLOCK
```

<a id="diagram-incremental"></a>
## 五、增量变化分流

流程说明：

本图可从任意阶段进入，不受当前检查是否通过限制；只读或授权不足时仅评估并报告。输入提交、同片续接、取消/替代和重验的门禁统一见 [增量闭环](../android-implement-and-verify/references/implement-and-test.md#incremental-loop)。

```mermaid
flowchart TD
    CHANGE["任何阶段收到或发现需求增量"] --> IMPACT["评估最早受影响内容与下游；保留同一 spec 和原基线"]
    IMPACT --> TYPE{"首次确认完成且行为 / 范围 / 契约 / 验收与测试边界未变？"}
    TYPE -- "否" --> DRAFT["draft：澄清并确认最新内容<br/>已确认需求只确认变化部分"]
    TYPE -- "是" --> KEEP["保持 confirmed；补漏或调整细节 / 计划"]
    DRAFT --> CURRENT["核对当前阶段与完整工作区"]
    KEEP --> CURRENT
    CURRENT --> OWNED{"改动归属可信且可隔离提交？"}
    OWNED -- "否" --> STOP["保留现场并报告；不提交半成品或用户改动"]
    OWNED -- "是" --> SPEC["输入有变化时只提交 SPEC<br/>当前切片继续沿用原起点"]
    SPEC --> NEED{"当前有待收拢内容或失效验证？"}
    NEED -- "是" --> FIX["补齐受影响内容或收拢明确取消项<br/>复查原发现点和失效下游检查"]
    NEED -- "否" --> FINAL
    FIX --> VALID{"验证通过且提交范围纯净？"}
    VALID -- "否" --> STOP
    VALID -- "是" --> COMMIT["完成必要边界提交；无实现 diff 不建空提交<br/>工作区干净后进入下一边界"]
    COMMIT --> FINAL{"处于最终交付阶段？"}
    FINAL -- "否" --> CONTINUE["按最新规格继续相应工作"]
    FINAL -- "是" --> RESULT["复用有效证据、补失效检查、更新 RESULT<br/>审计 baseline...最新 HEAD"]
```

<a id="diagram-final"></a>
## 六、最终验证路由

流程说明：

1. 只有用户明确要求最终检查、完整交付或准备提交时才进入最终验证。
2. 先确认基线仍是 `HEAD` 的祖先且工作区干净，再读取 stat、name-status 和提交历史，按 `BDD-##`、`SLICE-##` 或 `MIGRATE-*` 审查；单段仍过大时按模块、文件和 hunk 分块并从清单逐项销账，最后做整体一致性审计。
3. 复用命令、variant/设备环境和被验证输入均未变化的证据，只补缺失或失效的完整测试、构建、Lint 与专项。
4. 修复改变代码后重新执行受影响验证；空测试、全部 skipped 和旧报告不能支持通过。
5. 范围可信、验证实际执行且工作区除结果外干净时，把通过、部分通过或失败如实写入 `docs/result.md` 并形成 `RESULT` 提交，再对最新 `HEAD` 完成最终审计；结果提交不夹带构建产物、原始大日志、敏感信息、本机绝对路径或无关截图。

```mermaid
flowchart TD
    FINAL["用户明确要求最终检查、完整交付或准备提交"] --> CLEAN{"baseline 是 HEAD 祖先且工作区干净？"}
    CLEAN -- "否" --> STOP["停止：处理基线或未提交内容，不产生范围外副作用"]
    CLEAN -- "是" --> DIFF["stat + name-status + log -> 按稳定 ID 审查<br/>过大则按模块 / 文件 / hunk 分块销账 -> 整体审计"]
    DIFF --> TESTS["复用有效证据，只补缺失或失效的测试、构建和 Lint"]
    DIFF --> CODE{"Kotlin/Java、生命周期或工程风险？"}
    DIFF --> API{"endpoint、DTO、mapper 或缓存契约？"}
    DIFF --> UI{"布局、状态、交互、文案或 A11y？"}
    DIFF --> DEVICE{"测试失败、设备回归、Journey 或疑难 Bug？"}
    CODE -- "是" --> REVIEW["android-code-review"]
    API -- "是" --> APICHECK["android-verify-api-contract"]
    UI -- "是" --> UICHECK["android-verify-ui：真实截图证据"]
    DEVICE -- "是" --> FIX["android-test-and-fix"]
    TESTS --> COLLECT["汇总真实命令、测试数量和证据"]
    REVIEW --> COLLECT
    APICHECK --> COLLECT
    UICHECK --> COLLECT
    FIX --> COLLECT
    COLLECT --> TRUSTED{"范围可信、验证实际执行且<br/>工作区除结果外干净？"}
    TRUSTED -- "否" --> STOP
    TRUSTED -- "是" --> RESULT["docs/result.md 记录 verified_head 与真实结论<br/>形成 RESULT 提交"]
    RESULT --> PASS["审计最新 HEAD；工作区干净后<br/>给出通过 / 部分通过 / 失败结论"]
```

<a id="diagram-parallel"></a>
## 七、多需求并行

流程说明：

1. 只有互不冲突且可独立验收的需求进入并行；存在代码写入冲突或业务依赖时顺序完成。
2. 每个并行需求使用独立 worktree、分支、配置和日期格式 `requirement_dir`。
3. 每个窗口维护自己的 `spec.md`、代码和测试结果，不共享 `profiles/local.yaml` 或其他需求证据。
4. 模拟器、真机、账号和不可并发后端数据仍作为共享资源串行使用。
5. 大需求默认保持一份规格，以 `BDD-##` / `SLICE-##` 原子提交作为上下文检查点，不创建第二份 Tickets；宽范围迁移使用带 `MIGRATE-EXPAND`、`MIGRATE-##` 和 `MIGRATE-CONTRACT` 稳定 ID 的 expand-migrate-contract，并在 Contract 前核对实际发布兼容边界。

```mermaid
flowchart TD
    CANDIDATES["多个可独立验收结果"] --> CONFLICT{"代码写入或业务依赖是否冲突？"}
    CONFLICT -- "是" --> SERIAL["在一份规格内按依赖顺序完成"]
    CONFLICT -- "否" --> SPLIT["用户决定作为多个需求并行"]
    SPLIT --> A["需求 A：worktree A + branch A + config A + requirement_dir A"]
    SPLIT --> B["需求 B：worktree B + branch B + config B + requirement_dir B"]
    SPLIT --> C["需求 C：worktree C + branch C + config C + requirement_dir C"]
    A --> RA["独立 spec、代码和测试结果"]
    B --> RB["独立 spec、代码和测试结果"]
    C --> RC["独立 spec、代码和测试结果"]
    RA --> SHARED{"需要共享设备、账号或后端数据？"}
    RB --> SHARED
    RC --> SHARED
    SHARED -- "是" --> RESOURCE["仅共享资源测试阶段串行"]
    SHARED -- "否" --> PARALLEL["各需求继续并行"]
```

<a id="diagram-merge"></a>
### 合并规则（git worktree）

合并规则说明：

1. 各需求先在自己的 worktree、分支和配置中完成实现与验证；用户未授权集成时保持等待。
2. 每次只处理一个需求分支：先把它 rebase 到最新目标分支，不能用旧基线直接合并。
3. 发生冲突时先读取双方规格、相关代码、调用方和测试；兼容意图同时保留，不兼容时由用户决定。
4. rebase 后先跑受影响验证，再在目标 worktree 使用 `git merge --ff-only`；不能 fast-forward 时停止并重新核对目标分支。
5. 每次合入后都在集成代码上重跑受影响验证；还有其他需求时，以更新后的目标分支重复同一流程。
6. 不静默改用 merge commit、改写目标分支历史，也不拿需求分支上的旧结果证明最终集成代码。

```mermaid
flowchart TD
    READY["一个或多个需求分支已独立完成并验证"] --> AUTH{"用户已授权集成？"}
    AUTH -- "否" --> WAIT["保持各 worktree 和分支不变，等待授权"]
    AUTH -- "是" --> PICK["按顺序选择一个待合入需求分支"]
    PICK --> TARGET["确认最新目标分支和当前集成 Git 状态"]
    TARGET --> REBASE["需求分支 rebase 到最新目标分支"]
    REBASE --> CONFLICT{"发生冲突？"}
    CONFLICT -- "是" --> INTENT["读取双方规格、代码、调用方和测试<br/>说明每侧必须保护的行为"]
    INTENT --> COMPATIBLE{"双方意图兼容？"}
    COMPATIBLE -- "是" --> RESOLVE["同时保留兼容意图并完成最小冲突解决"]
    COMPATIBLE -- "否" --> USER["停止并由用户决定采用或放弃的行为"]
    USER --> RESOLVE
    CONFLICT -- "否" --> VERIFY["在 rebased 需求分支运行受影响验证"]
    RESOLVE --> VERIFY
    VERIFY --> PASS{"受影响验证通过？"}
    PASS -- "否" --> FIX["只在已确认范围内修复并重跑"]
    FIX --> VERIFY
    PASS -- "是" --> FF["目标 worktree 执行 git merge --ff-only"]
    FF --> FFOK{"fast-forward 成功？"}
    FFOK -- "否" --> MOVED["停止：目标分支已变化或历史不匹配"]
    MOVED --> TARGET
    FFOK -- "是" --> INTEGRATED["在集成后的目标代码上重跑受影响验证"]
    INTEGRATED --> INTEGRATEDPASS{"集成代码验证通过？"}
    INTEGRATEDPASS -- "否" --> STOP["停止本批次，报告失败和已合入范围<br/>不继续合入下一需求"]
    INTEGRATEDPASS -- "是" --> MORE{"还有待合入需求分支？"}
    MORE -- "是" --> PICK
    MORE -- "否" --> DONE["完成本批次集成并报告最终验证结果"]
```

<a id="diagram-resume"></a>
## 八、新窗口恢复

流程说明：

1. 新窗口先读取本总览、当前需求自己的配置、项目 `AGENTS.md` 和 Git 状态。
2. 配置已有 `requirement_dir` 时直接复用；没有时先复用唯一同名日期目录，多个候选由用户选择，没有匹配才按首次启动日期创建并写回。
3. 优先读取 `docs/spec.md`；旧目录只有唯一 `docs/<requirement_name>.md` 时把它作为兼容规格源，再一并读取 `api/api.md`、已有 `docs/result.md` 和 `baseline_commit..HEAD` 的边界提交。
4. `baseline_commit` 不再是当前历史祖先时停止 diff 比较，由用户决定新的审查起点。
5. 用提交标题中的 `BDD-##`、`SLICE-##` 或 `MIGRATE-*` 定位，核对最新规格、实际代码、后续修复或回退和有效证据后恢复进度；旧 ID 或 RESULT 不能单独证明完成。未提交切片按增量闭环证明归属、授权和原起点后续接。

```mermaid
flowchart TD
    NEW["新窗口接手"] --> GUIDE["读取本总览；规则以对应 Skill 为准"]
    GUIDE --> CONFIG["读取当前需求自己的配置：project_path + requirement_name"]
    CONFIG --> DIR{"配置已有 requirement_dir？"}
    DIR -- "否" --> EXISTING{"已有同名日期目录？"}
    EXISTING -- "唯一一个" --> REUSE["复用旧目录并把绝对路径写回配置"]
    EXISTING -- "多个" --> SELECT["列出候选，由用户选择"]
    SELECT --> REUSE
    EXISTING -- "没有" --> DERIVE["按首次启动日期推导 document/YYYY-MM-DD-需求名<br/>创建目录并把绝对路径写回配置"]
    DIR -- "是" --> PROJECT["复用已写回路径，读取项目 AGENTS.md、分支和 Git 状态"]
    REUSE --> PROJECT
    DERIVE --> PROJECT
    PROJECT --> SPECFILE{"存在 docs/spec.md？"}
    SPECFILE -- "是" --> SPEC["读取 spec.md、api/api.md、已有 result.md<br/>和 BDD / SLICE / MIGRATE 提交历史"]
    SPECFILE -- "否但有唯一 docs/需求名.md" --> LEGACY["把旧文件作为兼容规格源<br/>不复制第二份"]
    LEGACY --> SPEC
    SPEC --> BASELINE{"baseline_commit 仍是当前历史祖先？"}
    BASELINE -- "否" --> ASK["停止 diff 比较，请用户决定新的审查起点"]
    BASELINE -- "是" --> EVIDENCE["核对最新规格、实际代码、后续回退与有效证据"]
    EVIDENCE --> STATUS{"spec 状态与实际完成情况"}
    STATUS -- "draft" --> CLARIFY["继续决策树澄清，不编码"]
    STATUS -- "confirmed 且边界未完成" --> IMPLEMENT["核实并续接当前边界；无未完成改动才开始下一边界"]
    STATUS -- "confirmed 且等待最终交付" --> WAIT["等待用户明确触发最终验证"]
    STATUS -- "已有 result 但代码或验收变化" --> REVERIFY["重跑失效验证并更新最终结果"]
```

<a id="diagram-layout"></a>
## 九、文档与代码落点

流程说明：

1. 陌生项目接手上下文需要持久化时放在 `document/project-context/overview.md`，与日期需求目录并列。
2. 当前需求配置首次只需要 `project_path + requirement_name`，Agent 推导日期目录并写回 `requirement_dir`。
3. 新需求由 `docs/spec.md` 保存唯一需求事实；旧目录可沿用唯一 `docs/<requirement_name>.md`，但不得复制第二份；`docs/result.md` 只保存最终执行结果。
4. API 契约和原始资料放 `api/`，UI 设计导出和验收截图按需放 `ui/`。
5. Journey XML 由 Agent 根据已确认 BDD 创建在 `test-cases/journeys/<作用域>/`。
6. 生产代码、资源和普通自动化测试仍放 Android 项目既有目录，需求目录不保存实现副本。

```mermaid
flowchart TD
    ONBOARD["陌生项目接手结果"] --> PROJECTCONTEXT["document/project-context/overview.md<br/>按需创建的项目级索引"]
    CONFIG["当前需求独立配置<br/>project_path + requirement_name"] --> LOCATE["先复用唯一同名日期目录<br/>没有匹配才按当天创建并写回"]
    LOCATE --> ROOT["requirement_dir"]
    REQUIREMENT["Word、PDF、截图、聊天需求"] --> SPEC["新需求：requirement_dir/docs/spec.md<br/>旧目录：沿用唯一 docs/需求名.md"]
    FIGMA["Figma 链接"] --> SPEC
    FIGMA --> UIEVIDENCE["requirement_dir/ui/<br/>仅按需保存设计导出或验收截图"]
    APIINPUT["API 网页、文件、截图或聊天契约"] --> APIMD["requirement_dir/api/api.md<br/>唯一归一化契约"]
    APIINPUT --> APIRAW["requirement_dir/api/<原始资料><br/>需要留存时与契约共置"]
    BDD["已确认核心 UI BDD"] --> JOURNEY["requirement_dir/test-cases/journeys/<作用域>/<场景>.xml<br/>Agent 自动创建"]

    SPEC --> CODE["Android 项目既有 src/main<br/>生产代码与资源"]
    SPEC --> TEST["Android 项目既有 src/test 或 src/androidTest<br/>自动化测试"]
    ROOT --> SPEC
    ROOT --> APIMD
    ROOT --> UIEVIDENCE
    ROOT --> JOURNEY
    CODE --> REPORT["项目既有 build/report 输出"]
    TEST --> REPORT
    REPORT --> RESULT["requirement_dir/docs/result.md<br/>记录命令、数量、证据路径和结论"]
```
