# Android Skills 名称、职责与用法

流程维护者先读 `references/open-source-design-rationale.md`；修改 Skill、路由或门禁后用 `android-implement-and-verify/references/delivery-eval-scenarios.md` 做行为评测。日常执行需求不必加载这两份文档。

## 只记一个日常入口

完整实现需求、修复 Bug 或完成迭代时，只调用：

```text
android-implement-and-verify
```

它负责从需求确认推进到测试全绿。其余 6 个是专项能力，由总入口按实际 diff 自动编排；只有明确要求单项检查时才手动调用。

## 日常只改一个配置

编辑：

```text
/Users/example/work/MyPython/ai-skills/android-delivery-skills/profiles/local.yaml
```

通常只需要改：

- `project_path`：Android 项目路径
- `branch`：目标分支
- `requirement_file`：需求 Word / Markdown / TXT 文件
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

### 需求文件读取失败时

读取逻辑保持单一职责，不自行搜索其他文件或推测需求：

1. 路径固定按 `workspace_root → requirement_dir → requirement_file` 解析，并输出最终绝对路径。
2. 支持 `.docx`、`.md`、`.markdown`、`.txt`；PDF 可作为 UI 资料，但作为需求正文时需先转换为支持格式。
3. DOCX 使用 Python 标准库读取 OOXML 正文，不要求 IDE 额外安装文档解析库。
4. 文件为空、损坏或格式不支持时，脚本会说明原因并停止；修正路径、重新导出 Word 或转换格式后重试。

完整交付不需要维护 `base_branch`。`check-env` 会在干净工作区记录本需求开始时的 HEAD 和需求起点；需求修订确认不会更新 Git 基线。`route` 只收集该基线之后的 committed、staged、unstaged 和 untracked 变化，并保留 `A/M/D/R` 状态与真实修改片段。工作区不干净时会停止，由你决定如何处理，脚本不会自动 stash、提交或清理。

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
6. 编码后只对基线后的 diff 执行接口、测试、稳定性和代码质量检查；检测到 UI 变更时提示单独运行 UI 验收。
7. 有 UI 基准但尚未完成独立 UI 验收时，只能报告“代码与自动测试完成，UI 验收待执行”。

## 整体流程顺序(一图看懂)

```text
① delivery.py init    读需求 → 输出 BDD(Given/When/Then)
   └─ 停,等你确认「理解正确,继续」
                          ↓
② delivery.py check-env   查 Git 分支/干净工作区 → 记录 Git 基线和需求起点
③ delivery.py confirm-requirement-update   确认最新总需求和全部 Then → 开始编码
   └─ 受影响测试 + assemble + lint;失败自动修复并重跑
                          ↓
④ delivery.py route   按当前需求基线后的 Git Diff 自动路由审查并保存条件门禁快照

   【核心·业务逻辑层】(route 自动逐个调用,必先过)
     1. android-review-diff        ← 必跑:diff 影响范围
     2. android-verify-api-contract  ← 仅当有接口变更才跑
     3. android-review-code-quality  ← 必跑:质量/架构
     4. android-audit-stability     ← 必跑:稳定性/兼容性
     5. android-test-and-fix        ← 必跑:测试闭环/全绿门禁
   【独立·UI 校验】(route 只提示,用户单独调用)
     6. android-verify-ui          ← 截图与设计还原验收,不进自动队列

⑤ delivery_gate.py validate
   └─ 核对确认修订、最终代码、route 条件门禁、执行收据和专项结果；退出码 0 才可声明通过
```

脚本职责保持分离：

- `scripts/delivery.py`：只编排需求读取、修订确认、环境检查和专项 Skill 路由。
- `scripts/git_changes.py`：只读检查分支、工作区、四类 Git 变化、`A/M/D/R`、真实片段和最终摘要，不判断业务或路由。
- `scripts/requirement_snapshot.py`：只校验和保存连续需求修订、有效义务及文本差异，不判断业务语义或修改 Git。
- `scripts/delivery_gate.py`：只校验最终报告和证据新鲜度，不运行测试、不修改代码。
- `scripts/android_project_capabilities.py`：首次处理项目、构建配置变化或 task 未知时，只读发现模块、variant 和 Gradle task；普通业务修改不必重复运行。
- `scripts/execution_evidence.py`：只执行已经选择的命令并记录日志、测试数和报告摘要。
- `scripts/specialist_result.py`：只校验专项统一结果、P0/P1 和证据文件摘要。

最终报告写入 `<requirement_dir>/test-results/delivery-result.json`。当前契约为 version 3，旧的 AI 自报命令结果不能继续通过。AI 先用 `snapshot` 获取当前摘要，按 `android-implement-and-verify/references/delivery-result.schema.json` 生成报告，再校验：

```bash
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py snapshot
python3 ai-skills/android-delivery-skills/scripts/delivery_gate.py validate
```

第二条命令退出码为 `0` 才表示最终通过证据仍与当前需求和代码一致；它不会自动提交 Git。

`android-lint` 默认只执行目标项目自己的 Android Gradle Lint task，并引用项目生成的 XML/HTML/SARIF；当前流程不安装或强制外部自定义 Lint。项目已有插件时保持现状，但不单独声明自定义规则覆盖。

首次处理项目、构建配置变化或 task 未知时先发现真实能力；普通业务修改直接使用已确认 task。最终命令通过收据执行，不要手填退出码和测试数：

```bash
python3 ai-skills/android-delivery-skills/scripts/android_project_capabilities.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml

python3 ai-skills/android-delivery-skills/scripts/execution_evidence.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --id E-UNIT \
  --report app/build/test-results/testDebugUnitTest/TEST-example.xml \
  -- ./gradlew :app:testDebugUnitTest

python3 ai-skills/android-delivery-skills/scripts/specialist_result.py path \
  --config ai-skills/android-delivery-skills/profiles/local.yaml
python3 ai-skills/android-delivery-skills/scripts/specialist_result.py validate <专项结果.json>
```

`route`、收据、日志和专项结果均放在配置对应的外部状态目录，不修改 Android 项目；最终报告只引用路径和 SHA-256。

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
2. 能通过 MCP / API / 浏览器读取就使用。
3. 读不到就记录“外部资料未读取”和剩余风险。
4. 只有该链接是唯一关键资料且没有任何替代资料时，才暂停让你补充资料或授权。

## Figma UI 最短路径

如果会话已接入 Figma MCP，UI 相关需求默认优先走：

1. Figma MCP 读取 design context / metadata / variables / screenshot。
2. 先输出一份精简 Design Spec Gate。
3. 调用 `figma-android-xml` 专注生成纯净的 resources → styles → drawables → XML 与 tools 预览（**此阶段绝对禁止编写 Kotlin**）。
4. UI 骨架生成完毕后，再由主流程接管，单独补充必要的 Kotlin ViewBinding 和业务连线代码。
5. 编码后如有 UI 变更，主流程只提示用户单独调用 `android-verify-ui` 做截图或视觉验证。

如果 MCP 当前不可用，但你有 Figma Token，也可以先导出本地离线标注：

```bash
# 正常运行（自动检查新鲜度，数据未变则跳过下载）
python3 ai-skills/figma-android-xml/scripts/export_figma.py \
  "https://www.figma.com/design/FILE_KEY/NAME?node-id=471-131"

# 强制重新拉取（设计师刚改完稿时使用）
python3 ai-skills/figma-android-xml/scripts/export_figma.py \
  "https://www.figma.com/design/FILE_KEY/NAME?node-id=471-131" --force
```

脚本会生成（按 `[file_key]_[node_id]` 动态命名，多节点不相互覆盖）：

- `ai-skills/tempfile/[file_key]_[node_id]_spec.json`
- `ai-skills/tempfile/[file_key]_[node_id].png`
- `ai-skills/tempfile/[file_key]_[node_id]_preview.html`
- `ai-skills/tempfile/index.html`（汇总画廊）

## Skill 职责总表

| Skill | 负责什么 | 不负责什么 | 默认调用时机 |
| --- | --- | --- | --- |
| `android-implement-and-verify` | 确认需求、BDD、生成测试、编码、动态路由、自修复、重验和交付门禁 | 发布上线、生产数据、未授权 Git 提交 | 完整需求、Bug 或迭代的唯一入口 |
| `android-review-diff` | 检查是否改对、改多、漏改，以及无关 diff 和业务回归 | 通用代码质量、API 字段、UI 像素和测试执行 | 任意代码改动后必跑 |
| `android-verify-api-contract` | 核验 OpenAPI、endpoint、Request/Response、DTO、mapper、错误码和兼容性 | 产品需求、通用架构、UI 和完整测试门禁 | API、DTO 或网络 Repository 变更时 |
| `android-review-code-quality` | 检查架构一致性、可维护性、依赖边界、重复逻辑和资源规范 | 需求覆盖、API 契约、运行时专项风险和 UI 还原 | 任意代码改动后必跑 |
| `android-audit-stability` | 检查崩溃、动态泄漏、性能、安全隐私、ANR、协程和版本兼容 | diff 范围、通用风格、API 契约和设计还原 | 任意业务改动后必跑，专项按条件执行 |
| `android-test-and-fix` | 把 BDD 物化为 Unit、迁移、A11y、仪器或 Journey 测试，执行并修复失败 | 需求确认、接口契约来源、设计判断和发布 | 完整交付必跑 |
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

当前需求的 Journey XML 默认放在 `<requirement_dir>/test-cases/journeys/<需求作用域>/`。完整流程使用 Git 基线 ID 与需求正文哈希，单独调用时使用需求正文哈希；默认 Agent 直接读取当前作用域，可选壳中的 `src/main/journeys/` 只是执行暂存目录，因此串行需求不会复用旧测试用例。

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
