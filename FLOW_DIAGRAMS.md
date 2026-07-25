# Android Delivery Skills 完整流程图

> 每个阶段 = 简述 + 流程图 + 怎么执行（你做什么/AI 做什么/你看什么/命令），一体看完。

## 角色分工

| 角色 | 干什么 |
|---|---|
| **你（用户）** | 说需求 → 确认需求 → 确认计划 → 要求最终交付 |
| **AI** | 执行脚本命令 → 改代码 → 改测试 → 写文档 → 跑回归 → 报告 |
| **脚本** | 校验门禁 → 刷新 md → 标 STALE → 拦 gate（不合规就拦） |

执行环境：`cd /Users/example/work/MyPython/ai-skills/android-delivery-skills`，每条命令带 `--config profiles/<需求>.yaml`。

---

## 一、五步总览

> 用户始终只看到五步，内部三阶段（需求确认→计划→最终交付）隐藏在后。增量不推倒重来，最终交付只在用户明确要求时触发。

```mermaid
flowchart TD
    S1["① 确认需求<br/>含已上线业务影响"] --> S2["② 拆分测试与确认计划<br/>init-test-mapping + 实施计划"]
    S2 --> S3["③ 实现验证<br/>Red → 最小实现 → Green"]
    S3 --> S4{"下一步？"}
    S4 -- "需求/实现继续变化" --> S1
    S4 -- "需求增量（语义变化）" --> S5["增量闭环（全自动）"]
    S5 --> S3
    S4 -- "最终检查 / 完整交付" --> S6["⑤ 最终交付<br/>route + 全部门禁 + 中文报告"]
    S6 -- "发现技术问题" --> S3
    S6 -- "发现计划外业务影响" --> S1
    S6 --> S7["用户决定是否提交<br/>push / PR 另行授权"]
```

---

## 二、阶段一：确认需求与基线

> 读需求（docx 自动转 md），反复沟通确认（每答案先写回 md），纯确认后建 Git 基线 + 需求快照。confirm 成功后自动刷新续接指南/修订说明/映射说明。

```mermaid
flowchart TD
    A["读取配置和需求资料<br/>profiles/local.yaml"] --> B["delivery.py init"]
    B --> B1{"requirement_file<br/>是 docx？"}
    B1 -- "是，已有 md" --> B2["优先读 md（事实源切换）"]
    B1 -- "是，无 md" --> B3["自动读 docx 转写 <需求名>.md<br/>图片型 → 模板骨架"]
    B1 -- "是 md/txt" --> B4["直接读"]
    B2 --> C
    B3 --> C
    B4 --> C
    C["只读分析相关代码、调用方和已有测试"] --> D["置顶展示已上线业务影响<br/>【修改/保护/待确认/不修改】"]
    D --> E["拆分 REQ / BDD / 原子 Then<br/>每个功能：用户故事→AC→主流程/异常边界"]
    E --> F{"业务含义和验收<br/>是否足以确认？"}
    F -- "否" --> NEED["列出最小缺口并暂停<br/>不脑补"]
    NEED -- "资料补齐" --> A
    F -- "用户有新变化" --> G["分类本轮新增/修改/删除"]
    G --> G1["合并写回 <需求名>.md"]
    G1 --> G2["重新 init 读取"]
    G2 --> G3["展示变化摘要 + 路径"]
    G3 --> C
    F -- "纯确认（无新变化）" --> H["delivery.py check-env"]
    H --> ENV{"分支 + 代码工作区检查<br/>（文档改动已忽略，只检查代码）"}
    ENV -- "否" --> ENVFAIL["说明问题<br/>不自动 stash/commit/clean"]
    ENVFAIL -- "用户处理后" --> H
    ENV -- "代码干净" --> REV["confirm-requirement-update"]
    REV --> REV2{"修订确认有效？"}
    REV2 -- "待定/冲突" --> REVFIX["修正清单或继续澄清"]
    REVFIX --> C
    REV2 -- "确认（首次确认 / 增量修订）" --> FACTS["机器自动：<br/>✅ 刷新续接指南（含波及清单）<br/>✅ 刷新需求修订说明<br/>✅ 刷新测试映射说明<br/>✅ 标 STALE（如有）<br/>✅ 提示建立 traceability.md（如缺失）"]
    FACTS --> STAGE1["阶段一完成：需求事实已确认"]
```

### 怎么执行

**你做什么**：把需求文档（docx/md）放进 `document/<日期-英文名>/` 目录，告诉 AI 开始。补充/纠正需求后等 AI 复述理解，纯确认（不带新变化）后才推进。

**AI 做什么**：
1. 跑 `init` 读需求（docx 自动转 md），读代码分析影响面，输出"当前需求理解"给你看
2. 你补充/纠正 → AI 改 md → 重新 `init` 读 → 再给你看变化摘要
3. 反复直到你纯确认
4. 跑 `check-env`：校验分支 + 代码工作区干净（文档改动不拦）→ 建 Git 基线
5. AI 把你确认的义务写成 `requirement-revision.json` → 跑 `confirm-requirement-update`
6. 机器自动：版本号从"初始"变成"首次确认"，刷新续接指南/需求修订说明/测试映射说明

**你看什么**：终端输出"需求修订已确认：xxx 首次确认"，续接指南显示当前义务清单。

```bash
python3 scripts/delivery.py init --config profiles/<需求>.yaml
python3 scripts/delivery.py check-env --config profiles/<需求>.yaml
python3 scripts/delivery.py confirm-requirement-update --config profiles/<需求>.yaml
```

---

## 三、阶段二：拆分测试、确认计划与实现

> 生成测试映射骨架→AI 填测试→写实施计划（5 必需标题）→confirm-plan 生成收据→编码。编码中需求变了→增量闭环全自动（见第五节）。

```mermaid
flowchart TD
    STAGE1["阶段一输出：需求事实已确认"] --> MAP["init-test-mapping<br/>生成测试映射骨架（STALE）"]
    MAP --> MAP2["AI 填 test_ids<br/>回填 CURRENT"]
    MAP2 --> PC["写实施计划.md<br/>（5 必需标题：实现范围/已上线业务影响/<br/>预计修改文件/测试方案/明确不修改范围）"]
    PC --> PCR["delivery.py confirm-plan<br/>生成收据（三重 sha256 绑定）"]
    PCR --> CODE{"开始编码"}
    CODE -- "首次" --> RED["按原子 Then：<br/>Red → 最小实现 → Green"]
    CODE -- "增量" --> INCR["增量闭环铁律（见第五节）"]
    RED --> J{"编码后下一步？"}
    INCR --> J
    J -- "实现完善（验收不变）" --> W["局部修改 + 受影响测试 + 必要编译"]
    W --> J
    J -- "需求语义变化" --> K["改 <需求名>.md → confirm-requirement-update"]
    K --> K1["机器自动：标 STALE + 刷新所有 md + 旧计划收据失效"]
    K1 --> INCR
```

### 怎么执行

**你做什么**：看计划摘要 → 说"确认" → AI 才开始编码。

**AI 做什么**：
1. 跑 `init-test-mapping` 生成测试映射骨架（每个义务标 STALE）
2. 填 `test_ids`，回填 `CURRENT`
3. 写 `实施计划.md`（必须含 5 个标题：实现范围/已上线业务影响/预计修改文件/测试方案/明确不修改范围）
4. 跑 `confirm-plan` 生成收据（绑定需求+计划 sha256，变了自动失效）
5. 开始编码：按一个原子 Then 做 Red → 最小实现 → Green，做完一个做下一个

**你看什么**：终端输出"实施计划已确认…你已获准开始编码"。

```bash
python3 scripts/delivery.py init-test-mapping --config profiles/<需求>.yaml
# AI 写实施计划.md
python3 scripts/delivery.py confirm-plan --config profiles/<需求>.yaml
# AI 编码 + 回填 CURRENT
```

---

## 四、阶段三：最终审查与交付

> route 路由专项→构建/Lint/JUnit/变异测试/证据→delivery_gate 全量校验→出结论（FULL_PASS/LOCAL_PASS/INCOMPLETE/BLOCKED）。

```mermaid
flowchart TD
    J["用户明确要求最终交付"] --> L["delivery.py route"]
    L --> L1{"route 前置校验<br/>（sha256 → 计划收据 → route 快照 → 完整输入摘要）"}
    L1 -- "计划收据失效" --> L2["重新 confirm-plan"]
    L2 --> L
    L1 -- "全部通过" --> M["Diff / 质量 / 稳定性 / API 专项"]
    M --> M0{"需要修复？"}
    M0 -- "是" --> FIX["保存证据 + 最小修复一个根因"]
    M0 -- "否" --> N["选择测试层 + 执行完整回归"]
    FIX -- "需求冲突" --> BACK["返回阶段二"]
    FIX -- "代码变化" --> L
    FIX -- "重跑专项" --> M
    FIX -- "重跑测试" --> N
    N --> O["构建 + Lint + JUnit + 变异测试(PIT)<br/>+ Journey 或人工证据"]
    O --> P["生成 delivery-result.json"]
    P --> Q{"delivery_gate.py validate<br/>（义务集合/sha256/STALE/变异/traceability 全校验）"}
    Q -- "STALE 未回填 / 缺登记 /<br/>变异存活 / sha 不匹配 /<br/>traceability 缺义务 /<br/>计划收据失效" --> FIX
    Q -- "设备待验" --> DEVICE["LOCAL_PASS_DEVICE_PENDING"]
    Q -- "仍有未完成" --> INCOMPLETE["INCOMPLETE"]
    Q -- "全部通过" --> PASS["FULL_PASS"]
    DEVICE --> COMMIT["用户决定是否提交"]
    INCOMPLETE --> COMMIT
    PASS --> COMMIT
```

### 怎么执行

**你做什么**：说"最终检查"或"完整交付"或"准备提交"。

**AI 做什么**：
1. 跑 `route`：基于真实 diff 路由专项审查（Diff/质量/稳定性/API/UI）
2. 跑构建 + Lint + JUnit + 变异测试(PIT) + Journey 或人工证据
3. 跑 `delivery_gate validate`：全量校验义务集合/sha256/STALE/变异/traceability
4. 输出中文交付结论（FULL_PASS / LOCAL_PASS / INCOMPLETE / BLOCKED）

**你看什么**：终端输出结论 + `交付结论.md`（强制含"未验证项"和"残留风险"段）。

```bash
python3 scripts/delivery.py route --config profiles/<需求>.yaml
python3 scripts/delivery_gate.py validate --config profiles/<需求>.yaml
```

---

## 五、增量闭环（需求增量后全自动）

> 你/AI 改需求→confirm 一个命令→机器自动标 STALE+刷新 md+旧计划失效→AI 自动改代码+改测试+回填+增量回归+报告。整个过程不用你发额外命令。

```mermaid
flowchart TD
    CHANGE["用户/AI 改了需求<br/>（往 <需求名>.md 追加/修改）"]
    CHANGE --> CONFIRM["confirm-requirement-update<br/>（一个命令）"]
    CONFIRM --> AUTO{"机器自动"}
    AUTO --> A1["版本号 +1<br/>（首次确认 → 增量修订第N次）"]
    AUTO --> A2["义务 sha256 变化 → 标 STALE"]
    AUTO --> A3["刷新续接指南<br/>（含波及清单）"]
    AUTO --> A4["刷新需求修订说明"]
    AUTO --> A5["刷新测试映射说明"]
    AUTO --> A6["旧计划收据失效"]

    A1 --> AI{"AI 自动闭环<br/>（不等用户）"}
    A2 --> AI
    A3 --> AI
    A4 --> AI
    A5 --> AI
    A6 --> AI

    AI --> B1["① 改实现代码<br/>只改波及清单里的文件"]
    B1 --> B2["② 改测试代码<br/>STALE/新义务加断言"]
    B2 --> B3["③ init-test-mapping<br/>回填 CURRENT"]
    B3 --> B4["④ 增量回归<br/>跑受影响模块全量测试<br/>含旧测试，确认无回归"]
    B4 --> B5["⑤ 报告完成<br/>改了哪些文件/测试通过/有无回归"]
    B5 --> DONE["增量完成，回到实现验证"]
```

### 怎么执行

**你做什么**：说"加一个 xxx 功能"或"改一下 xxx"。

**AI 做什么**：
1. 改 `<需求名>.md`（写回需求）
2. 物化修订清单 → 跑 `confirm-requirement-update`（一个命令）
3. 机器自动：版本号+1 → 变化义务标 STALE → 刷新所有 md → 旧计划失效
4. AI 自动闭环（不等用户）：① 改实现代码 ② 改测试代码 ③ 回填 CURRENT ④ 跑增量回归（含旧测试） ⑤ 报告

**你看什么**：续接指南"波及清单"显示改了哪些义务，AI 报告增量完成。

```bash
# AI 改 <需求名>.md + 物化修订清单后
python3 scripts/delivery.py confirm-requirement-update --config profiles/<需求>.yaml
# 后面 AI 全自动完成，不用你再发命令
```

---

## 六、STALE 联动机制（防改需求不更新测试）

> 需求改了某个义务→它的 sha256 变了→机器自动标 STALE→续接指南/映射说明同步→gate 拦不放行。AI 看到后自动改测试+回填→gate 放行。这就是"防 AI 改需求不更新测试"的机器兜底。

```mermaid
flowchart LR
    REQ["需求改了<br/>BDD-002 加了深色模式"] --> CONFIRM2["confirm-requirement-update"]
    CONFIRM2 --> HASH["义务 sha256 变化<br/>BDD-002: aaa → bbb"]
    HASH --> STALE["test-mapping.json<br/>BDD-002 标 STALE"]
    STALE --> GUIDE["续接指南<br/>⏳ BDD-002 测试待回填"]
    STALE --> MAP_MD["测试映射说明<br/>BDD-002 状态：待回填"]
    STALE --> GATE["delivery_gate<br/>拦！STALE 未回填不放行"]

    GUIDE --> AI_FIX["AI 自动改测试代码<br/>加深色模式断言"]
    AI_FIX --> AI_FILL["回填 CURRENT"]
    AI_FILL --> GATE_PASS["gate 通过 ✅"]
```

### 怎么执行

这个机制是**自动触发的**，你不需要做任何事。它发生在阶段二/五的 `confirm-requirement-update` 之后，机器自动标 STALE，AI 自动改测试+回填。你只在续接指南里看到"⏳ 测试待回填"→ AI 改完后变成"✅ 测试已对齐"。

---

## 七、多需求并行（git worktree）

> 每个需求一个 worktree + 独立分支 + 独立 profile + 独立 document 目录。各窗口独立闭环互不干扰。合并用 merge --no-ff。integrate 汇总结论到主工作树总览。

```mermaid
flowchart TD
    subgraph 主工作树
        MAIN["MyApp/<br/>master 分支"]
        MAIN_INDEX["document/需求总览.md<br/>（全局六列表）"]
    end

    subgraph 需求A
        WTA["MyApp-req-login/<br/>feature/req-login"]
        WTA_DOC["document/2026-07-25-login/<br/>login.md + .state/"]
    end

    subgraph 需求B
        WTB["MyApp-req-pay/<br/>feature/req-pay"]
        WTB_DOC["document/2026-07-25-pay/<br/>pay.md + .state/"]
    end

    MAIN --> WTA
    MAIN --> WTB
    WTA --> WTA_DOC
    WTB --> WTB_DOC

    WTA -- "独立闭环" --> WTA_DONE["需求A 交付"]
    WTB -- "独立闭环" --> WTB_DONE["需求B 交付"]
    WTA_DONE --> MERGE["git merge --no-ff<br/>（线性主干 + merge commit）"]
    WTB_DONE --> MERGE
    MERGE --> INTEGRATE["integrate 集成报告<br/>汇总两需求结论"]
    INTEGRATE --> MAIN_INDEX
```

### 怎么执行

**你做什么**：开多个 Claude Code 窗口，每个窗口一个需求。

**AI 做什么**：每个窗口独立走阶段一→二→三，各用各的 profile + worktree。完成后合并到主分支。

```bash
# 每个窗口各自
python3 scripts/delivery.py init --config profiles/req-login.yaml
# ... 独立走完全流程 ...

# 全部交付后合并
git merge --no-ff feature/req-login -m "集成：req-login"
git merge --no-ff feature/req-pay -m "集成：req-pay"
# 汇总结论
python3 scripts/requirement_workspace.py integrate \
  --main-worktree MyApp --channels <req-a-dir>,<req-b-dir> --batch 2026-07-25-批次1
```

---

## 八、续接旧需求（新目录 + 引用）

> 续接不往旧目录塞内容（会冲突）。新建独立目录 + 引用旧需求 + 建当前 HEAD 新基线。旧目录原样不动，零污染。

```mermaid
flowchart TD
    OLD["上周交付<br/>document/2026-07-20-login/<br/>（原样不动）"]
    NEW["本周续接<br/>document/2026-07-25-login-forgot-pwd/<br/><需求名>.md 注明'关联需求：续接旧目录'"]
    NEW --> NEW_ENV["check-env --new-requirement<br/>建当前 HEAD 新基线"]
    NEW_ENV --> NEW_CONFIRM["confirm-requirement-update<br/>全新义务/映射/收据"]
    NEW_CONFIRM --> NEW_DONE["交付完成"]
    NEW_DONE --> VERIFY{"旧目录验证"}
    VERIFY -- "snapshot 未被碰" --> OK["✅ 续接零污染"]
```

### 怎么执行

**你做什么**：说"继续做 xxx 需求，加 yyy"。

**AI 做什么**：
1. 新建 `document/<新日期>-<英文名>/` 目录（不碰旧目录）
2. `<需求名>.md` 顶部注明"关联需求：续接 <旧目录>"
3. 跑 `init` + `check-env --new-requirement`（建当前 HEAD 新基线，不复用旧基线）
4. 后续和正常需求一样走

**你看什么**：旧目录原样不动（零污染），新目录全新独立。

```bash
python3 scripts/delivery.py init --config profiles/<新需求>.yaml
python3 scripts/delivery.py check-env --new-requirement --config profiles/<新需求>.yaml
```

---

## 九、docx → md 事实源切换

> 用户给 docx→init 自动转写为 <需求名>.md→以后所有命令统一读 md（config_paths 自动切换，无断裂）。图片型 docx 用模板骨架建空 md。docx 原样保留仅作初始记录。

```mermaid
flowchart TD
    DOCX["requirement.docx<br/>（用户给的初始需求）"]
    DOCX --> INIT["delivery.py init"]
    INIT --> CHECK{"docx 有正文？"}
    CHECK -- "有（文本型）" --> WRITE_MD["自动转写为 <需求名>.md"]
    CHECK -- "无（图片型）" --> SKELETON["用模板骨架建空 md<br/>AI 后续填充"]
    WRITE_MD --> ALL["所有后续命令统一读 md<br/>（config_paths 自动切换）"]
    SKELETON --> ALL
    ALL --> CMD["check-env / confirm / route / gate<br/>全部绑定 md 的 sha256"]
    CMD --> DOCX_KEEP["docx 原样保留<br/>仅作初始记录"]
```

### 怎么执行

**你做什么**：把 docx 放进 `document/<日期-英文名>/` 目录，配 profile 的 `requirement_file: requirement.docx`。

**AI 做什么**：跑 `init` 时自动读 docx 正文，转写成 `<需求名>.md`。以后所有命令（check-env/confirm/route/gate）自动读 md（config_paths 统一切换）。图片型 docx 用模板骨架建空 md，AI 在后续沟通中填充。

**你看什么**：终端输出"已自动读取 docx 并转写为 xxx.md（事实源）"，后续增量都在 md 上改。
