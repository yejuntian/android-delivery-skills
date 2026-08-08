# 最终交付

最终验证只在用户明确要求“最终检查”“完整交付”或“准备提交”时开始，并以开始时的当前 Git diff 为准。

## 1. 审查范围

- 对照 `spec.md` 检查行为、范围、UI/API 来源和不在范围项。
- 使用 `baseline_commit` 到当前 `HEAD` 的 diff，并合并未提交改动，检查是否漏实现、过度修改、破坏受保护旧业务或混入无关改动。
- 规格不是 `confirmed`、仍有产品未知或出现范围外高风险改动时停止并询问用户。

## 2. 一次完整验证

先使用项目已有命令，按实际影响选择：

- 相关模块完整 Unit/Instrumentation 测试；
- 必要构建和 Lint；
- API 改动调用 `android-verify-api-contract`；
- 可见 UI 改动调用 `android-verify-ui`；
- Kotlin/Java 改动调用 `android-code-review`；
- 测试失败或需要设备回归时调用 `android-test-and-fix`。

按需求和实际 diff 选择条件检查：

| 触发变化 | 必查范围 |
| --- | --- |
| endpoint、DTO、请求响应或缓存契约 | API 契约与相关测试 |
| Room、DataStore、SharedPreferences 或持久化格式 | 旧数据迁移、兼容与恢复；缺旧样本时标未验证 |
| Activity/Fragment、监听器、协程、Flow、WebView、Camera、Media | 生命周期静态审查；项目已有能力时补动态泄漏验证 |
| 启动、列表、图片、数据库、主线程、锁或明确性能验收 | 使用需求阈值或已有基线做 Trace/Benchmark；不发明指标 |
| 布局、状态、控件、文案、图标或语义 | UI 截图对比、交互和 A11y |
| 权限、导出组件、DeepLink、WebView、Token、日志或用户数据 | 安全隐私、信任边界和敏感信息检查 |
| Gradle、依赖、签名、混淆或 release 行为 | 项目已有构建、依赖树、release/R8 检查 |

性能、迁移、安全、真机和厂商 ROM 等检查仅在需求或 diff 触发时执行。不适用写明依据；适用但缺少工具、设备、契约、旧数据或基准时标记“未验证”，继续执行其他可用检查。

可以使用 `scripts/verify_results.py` 检查 JUnit XML 测试总数非零、至少一个测试实际执行、失败数为零且报告不早于当前代码和规格；全部 skipped 不能支持通过。它只核对结果，不决定需求、专项或生成流程状态。

## 3. 变化后重验

修复导致代码变化时，先跑直接受影响测试；最终结论前重新执行被变化影响的完整检查。没有变化的外部事实不重复抓取，但旧测试报告不能证明新代码。

## 4. 记录结果

最终阶段创建或更新 `<requirement_dir>/docs/result.md`。它是输出，不是新的需求事实源；不得为了填写结果修改已确认规格。

```markdown
# 交付结果

## 目录
1. [版本与范围](#result-version)
2. [BDD 验证](#result-bdd)
3. [执行命令](#result-commands)
4. [专项检查](#result-specialists)
5. [未验证项与剩余风险](#result-risks)

<a id="result-version"></a>
## 版本与范围
- baseline_commit:
- current_head:
- 未提交改动:

<a id="result-bdd"></a>
## BDD 验证
| BDD | 实际自动测试或人工步骤 | 结果 | 证据 |
| --- | --- | --- | --- |

<a id="result-commands"></a>
## 执行命令

<a id="result-specialists"></a>
## 专项检查

<a id="result-risks"></a>
## 未验证项与剩余风险
```

规格中的每个 BDD 必须在结果表中恰好出现一次。结果只使用“通过 / 失败 / 未验证”；人工步骤只有实际执行并记录环境与观察结果后才能写通过。
目录必须与实际章节同步；没有内容的专项写明“不适用”及依据，不保留空标题。

## 5. 中文结论

最终回复包含：

- 实现了哪些已确认行为；
- 实际执行的命令、测试数量和结果；
- 代码、UI、API 等适用专项结论；
- 历史问题与本次新增问题的区分；
- 未执行、失败或受环境限制的验证；
- 当前是否可以提交，以及剩余风险。

只有每个 BDD、全部适用专项和必需验证真实通过，且没有未关闭高风险问题时才写“已通过”。缺少设备或外部资料时可以写“本地通过，专项待验证”，不能写成完整通过。

提交、推送、发布仍需用户分别授权；提交信息遵守项目 `AGENTS.md`。
