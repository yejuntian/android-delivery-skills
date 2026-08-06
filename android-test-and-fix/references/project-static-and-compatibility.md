# 项目静态门禁与兼容性测试

## 命令来源

按本次测试/构建配置、已确认计划、影响半径 `expected_tests`、test mapping、CI、README、项目脚本和用户确认选择最小命令。普通单测不先运行全量 task 发现；只有能力无法判断且门禁必须确认时读取 `gradle-task-discovery.md`。

## 静态门禁

1. Kotlin/Java 编译：选择受影响模块最小 compile、test 或 assemble，不猜任务名。
2. Android Lint：执行已有受影响 lint，读取 XML/SARIF Fatal/Error，不能依赖 `abortOnError` 退出码。
3. Kotlin：只执行项目已有 detekt；Java：只执行已有 Error Prone、NullAway、SpotBugs 或 Infer。
4. PMD/Checkstyle 只支持代码质量结论，不冒充稳定性通过。
5. Semgrep/CodeQL 只有 binary、项目配置和规则都已存在时复用，不下载未知规则或新建数据库。
6. 公共 API 变化时执行项目已有 ABI/API validator；没有能力则记录机器兼容未验证。

SARIF 重新统计 Error/Warning 和 baselineState；`new/updated/unknown` Error 即使退出码为零也不能通过，只有明确 `unchanged` 的历史项可记录为非本次阻断。不得自动生成 baseline、批量 suppress 或扩大排除范围。

## 历史债务

把告警分为：

- `NEW`：本次新增，按严重级别关闭。
- `AFFECTED`：旧问题位于本次直接调用链，结合证据处理。
- `PRE_EXISTING`：基线前存在且不在影响面，只记录。
- `UNKNOWN_ORIGIN`：报告不可比，记录能力损失。

无关历史债务不扩大本次修改，但不能掩盖新增问题。

## Java 与混合项目

- 检索 Java/Kotlin Unit、androidTest、变体和自定义 source set，测试代码落项目真实目录，不放需求 `test-cases/`。
- 沿用 JUnit4/5、Robolectric、Mockito、PowerMock、Espresso、runner 和现有任务，不为统一风格迁移框架。
- Mockito/PowerMock 仍优先断言状态和输出，不新增内部调用次数断言。

## Release 与 R8

反射序列化、注解生成、JNI、动态加载、R8/ProGuard、公共 API、Java level、desugaring 或构建配置变化时，执行项目已有且不需要生产签名的 release/minify/consumer-rules/ABI 任务。不升级 AGP、Gradle、JDK，不关闭混淆。无法执行时明确“Debug 已验证，release/R8/目标 Java 兼容未验证”。

## Android 版本兼容

权限、存储、通知、后台任务、前台服务、WebView、FileProvider、DeepLink、WindowInsets、媒体、蓝牙、定位或系统栏变化时，根据项目 `minSdk/targetSdk/compileSdk`、variant 和支持设备设计版本覆盖：

- 低版本安装、启动和相关页面。
- 高版本权限、Manifest、后台和系统限制。
- 权限拒绝、永久拒绝和不支持时降级。
- 通知、存储、媒体、文件 URI、PendingIntent、exported、包可见性和 DeepLink 差异。
- Insets、系统栏、软键盘、暗黑、字体缩放和方向差异。

缺少对应设备时标记未验证并给出建议版本，单一设备不能代表全版本兼容。
