# Android Skills 名称、职责与用法

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
- `requirement_file`：需求 Word / Markdown / PDF / TXT 文件
- 可选 `ui.links` / `ui.screenshots`
- 可选 `api.links` / `api.files` / `api.status`

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

## 确认后继续

如果需求理解正确，你说：

```text
理解正确，继续。
```

然后直接进入编码：

1. 修改前校验项目路径、目标分支和工作区状态。
2. 读取相关代码并复用现有链路。
3. 直接实现需求，不再固定输出一轮前置分析报告。
4. 只有遇到关键资料缺失、高风险改动或分支/工作区异常时才暂停询问。
5. 编码后执行 diff、接口、测试、稳定性和代码质量检查；检测到 UI 变更时提示单独运行 UI 验收。

## 整体流程顺序(一图看懂)

```text
① delivery.py init    读需求 → 输出 BDD(Given/When/Then)
   └─ 停,等你确认「理解正确,继续」
                          ↓
② delivery.py check-env   查 Git 分支/工作区 → 物化测试 → 开始编码
   └─ 受影响测试 + assemble + lint;失败自动修复并重跑
                          ↓
③ delivery.py route   按 Git Diff 自动路由审查

   【核心·业务逻辑层】(route 自动逐个调用,必先过)
     1. android-review-diff        ← 必跑:diff 影响范围
     2. android-verify-api-contract  ← 仅当有接口变更才跑
     3. android-review-code-quality  ← 必跑:质量/架构
     4. android-audit-stability     ← 必跑:稳定性/兼容性
     5. android-test-and-fix        ← 必跑:测试闭环/全绿门禁
   【独立·UI 校验】(route 只提示,用户单独调用)
     6. android-verify-ui          ← 截图与设计还原验收,不进自动队列
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

核心原则:**BDD 必须物化为测试;测试或 P0/P1 失败必须修复重跑;必需门禁全绿才可交付**。每个 skill 仍可脱离 route 单独运行。

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
| `android-verify-api-contract` | 核验 endpoint、Request/Response、DTO、mapper、错误码和兼容性 | 产品需求、通用架构、UI 和完整测试门禁 | API、DTO 或网络 Repository 变更时 |
| `android-review-code-quality` | 检查架构一致性、可维护性、依赖边界、重复逻辑和资源规范 | 需求覆盖、API 契约、运行时专项风险和 UI 还原 | 任意代码改动后必跑 |
| `android-audit-stability` | 检查崩溃、泄漏、ANR、生命周期、协程、并发和版本兼容 | diff 范围、通用风格、API 契约和设计还原 | 任意业务改动后必跑 |
| `android-test-and-fix` | 把 BDD 物化为 Unit、仪器或 Journey 测试，执行并修复失败到全绿门禁 | 需求确认、接口契约来源、设计判断和发布 | 完整交付必跑 |
| `android-verify-ui` | 独立验收布局、排版、资源、截图和设计还原 | 功能测试用例、接口、数据存储、支付和提交 | 用户在 UI 变更完成后单独调用 |

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

## Journey UI 测试(壳项目隔离方案)

Journey 测试用例归 `android-test-and-fix`。老项目 AGP 保持不动，只构建并安装 APK；独立 AGP 9 壳通过 `JOURNEYS_CUSTOM_APP_ID` 测试实际包名。`android-verify-ui` 可以复用 Journey 截图做设计还原验收，但不生成或管理测试用例。

当前需求的 Journey XML 默认放在 `<requirement_dir>/test-cases/journeys/`。共享壳中的 `src/main/journeys/` 只是执行暂存目录，脚本每次会替换其中的 XML，避免不同项目串用旧测试用例。

Journey 测试用例由 `android-test-and-fix` 根据已确认需求和 BDD 自动分析并生成，用户不需要提供 XML、action/step 或任务名。只有需求本身缺少前置条件或预期结果时，才需要用户补充业务含义。

并非所有需求都运行 Journey：无 UI 影响返回 `SKIPPED_NO_UI`；只有布局、样式和资源变化返回 `SKIPPED_VISUAL_ONLY`；只有点击、输入、导航或可见状态流转等 UI 行为变化，才生成 Journey。`NO_JOURNEY_FOUND` 只表示“已经需要 Journey，但测试用例尚未成功物化”。

是否调用 Journey 由 `android-test-and-fix` 根据业务需求、已确认 BDD 和实际 diff 自动判断，不需要用户选择。下面的 `--ui-impact` 是 Skill 调用脚本时使用的内部安全参数，用来防止未判断适用性就启动设备和壳流程。

判断采用“两次判断、一次执行”：需求确认后先做候选初判和测试设计，编码后结合实际 diff 做最终判定；只有最终仍适合 Journey 才启动壳。两次结论不一致时以实际 diff 为准，并在测试报告中说明原因。

```bash
# 一键：构建老项目 APK → 读取实际包名 → 指定设备安装 → 注入包名 → 跑 Journey → JSON 结果
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --config ai-skills/android-delivery-skills/profiles/local.yaml \
  --ui-impact behavior

# 已装好 APK 时跳过构建
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/run_journey.py \
  --ui-impact behavior --skip-build

# 单独只嗅探包名（排查用）
python3 ai-skills/android-delivery-skills/android-test-and-fix/scripts/detect_package.py \
  --project-path <项目路径>
```

设备未就绪时只跳过 Journey 等设备测试，本地单测、构建和 lint 仍要执行。首次使用共享壳时，在当前 Android Studio 中执行一次 `New > Journey Test`，让官方模板生成匹配版本的 XML schema、testSuites、依赖和运行配置。退出码：`0` Journey 真实通过 / `1` 环境或壳错误，禁止据此修改目标代码 / `2` 连续两次真实 UI 断言失败，只允许进入根因分析；确认是生产缺陷后才修目标代码。
