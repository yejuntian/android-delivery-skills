# Android Delivery Skills 完整流程图

> 配合 FLOW_OVERVIEW.md 使用，本文件只放流程图（mermaid），帮助可视化。

## 一、五步总览

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

## 二、阶段一：确认需求与基线

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
    H --> ENV{"分支 + 代码工作区检查"}
    ENV -- "否" --> ENVFAIL["说明问题<br/>不自动 stash/commit/clean"]
    ENVFAIL -- "用户处理后" --> H
    ENV -- "代码干净（文档改动已忽略）" --> REV["confirm-requirement-update"]
    REV --> REV2{"修订确认有效？"}
    REV2 -- "待定/冲突" --> REVFIX["修正清单或继续澄清"]
    REVFIX --> C
    REV2 -- "确认（首次确认 / 增量修订）" --> FACTS["机器自动：<br/>✅ 刷新续接指南<br/>✅ 刷新需求修订说明<br/>✅ 刷新测试映射说明<br/>✅ 标 STALE（如有）"]
    FACTS --> STAGE1["阶段一完成：需求事实已确认"]
```

## 三、阶段二：拆分测试、确认计划与实现

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

## 四、阶段三：最终审查与交付

```mermaid
flowchart TD
    J["用户明确要求最终交付"] --> L["delivery.py route"]
    L --> L1{"route 前置校验"}
    L1 -- "计划收据失效" --> L2["重新 confirm-plan"]
    L2 --> L
    L1 -- "通过" --> M["Diff / 质量 / 稳定性 / API 专项"]
    M --> M0{"需要修复？"}
    M0 -- "是" --> FIX["保存证据 + 最小修复一个根因"]
    M0 -- "否" --> N["选择测试层 + 执行完整回归"]
    FIX -- "需求冲突" --> BACK["返回阶段二"]
    FIX -- "代码变化" --> L
    FIX -- "重跑专项" --> M
    FIX -- "重跑测试" --> N
    N --> O["构建 + Lint + JUnit + 变异测试(PIT)<br/>+ Journey 或人工证据"]
    O --> P["生成 delivery-result.json"]
    P --> Q{"delivery_gate.py validate"}
    Q -- "STALE 未回填 / 缺登记 /<br/>变异存活 / sha 不匹配" --> FIX
    Q -- "设备待验" --> DEVICE["LOCAL_PASS_DEVICE_PENDING"]
    Q -- "仍有未完成" --> INCOMPLETE["INCOMPLETE"]
    Q -- "全部通过" --> PASS["FULL_PASS"]
    DEVICE --> COMMIT["用户决定是否提交"]
    INCOMPLETE --> COMMIT
    PASS --> COMMIT
```

## 五、增量闭环（需求增量后全自动）

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

## 六、STALE 联动机制（防改需求不更新测试）

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

## 七、多需求并行（git worktree）

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

## 八、续接旧需求（新目录 + 引用）

```mermaid
flowchart TD
    OLD["上周交付<br/>document/2026-07-20-login/<br/>（原样不动）"]
    NEW["本周续接<br/>document/2026-07-25-login-forgot-pwd/<br/>requirement.md 引用旧需求"]
    NEW --> NEW_ENV["check-env --new-requirement<br/>建当前 HEAD 新基线"]
    NEW_ENV --> NEW_CONFIRM["confirm-requirement-update<br/>全新义务/映射/收据"]
    NEW_CONFIRM --> NEW_DONE["交付完成"]
    NEW_DONE --> VERIFY{"旧目录验证"}
    VERIFY -- "snapshot 未被碰" --> OK["✅ 续接零污染"]
```

## 九、docx → md 事实源切换

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
