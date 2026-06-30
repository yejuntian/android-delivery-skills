---
name: android-test-delivery
description: Android 需求测试用例生成、测试矩阵评估、Android CLI、Gradle 构建、单元测试、lint、仪器测试、截图测试、adb 验证和交付报告流程。适用于 AI 完成或准备完成 Android 需求后，自动评估测试覆盖、选择可执行验证命令、运行可运行测试并报告无法验证项。
---

# Android 测试交付

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

用于把需求转成测试用例矩阵，并尽量使用当前项目已有 Android CLI、Gradle、adb 和测试框架执行验证。

## Android CLI / Gradle / adb 使用策略

- 只在需要真实构建、安装运行、自动测试、截图、logcat 或设备兼容验证时调用。
- 先识别本机是否存在 Android CLI、`./gradlew`、`adb`、可用模拟器或真机；不可用时如实报告。
- 优先使用项目已有 Gradle task 和测试框架；Android CLI 能提供更稳定的设备、SDK、模拟器或测试能力时再使用。
- 不得在需求理解阶段用 CLI 代替需求确认；测试命令只能验证实现结果，不能替代产品、设计或后端确认。
- 涉及清数据、卸载、Monkey、真实支付、真实删除、生产环境接口或破坏性操作时，必须用户明确同意。
- 每次执行后记录命令、退出码、关键日志、失败原因和剩余风险；没有实际执行不得写成已通过。

## 测试用例生成

实现前或实现后必须按需求生成测试用例，至少考虑：

- 正常路径。
- 空数据、空列表、空对象。
- 异常数据：null、缺字段、空字符串、未知枚举、类型异常。
- 网络异常：无网络、超时、服务端错误、登录过期。
- 权限异常：拒绝、永久拒绝、降级展示。
- 生命周期：返回、旋转、后台切前台、页面销毁后回调。
- 列表场景：快速滑动、分页、刷新、重复点击、复用错位、请求乱序。
- 本地数据：旧缓存、清缓存、迁移失败、默认值。
- UI 状态：加载、成功、失败、空态、禁用、选中。
- 灰度开关：开启、关闭、默认值缺失。
- Android 版本兼容：项目 `minSdk` 到目标 `targetSdk` 范围内的权限、存储、通知、后台任务、系统组件和 UI 行为差异。
- 回归影响：相关入口、详情页、搜索、筛选、推送、DeepLink。

每条用例标注：用例名、前置条件、步骤、预期结果、自动化类型、是否本次必须执行。

## 自动化类型

- Unit：ViewModel、UseCase、Repository、mapper、工具函数。
- UI：Compose UI Test、Espresso、UIAutomator。
- Screenshot：Paparazzi、Roborazzi、Shot 或项目已有截图方案。
- CLI：Gradle 构建、lint、adb 安装、截图、logcat。
- Manual：需要人工确认的设计稿、复杂交互、第三方环境、真实后端数据。

## 命令选择规则

不得写死命令。先识别项目模块和已有命令，再选择最小验证：

- 环境识别：例如 `which adb`、`adb devices`、`./gradlew tasks --all`、Android CLI 可用性检查。
- 构建：例如 `./gradlew :app:assembleDebug`。
- 单测：例如 `./gradlew :app:testDebugUnitTest`。
- 指定测试：例如 `--tests "完整类名"`。
- Lint：例如 `./gradlew :app:lintDebug`。
- 仪器测试：例如 `./gradlew :app:connectedDebugAndroidTest`。
- 设备：`adb devices`、`adb logcat`、`adb exec-out screencap -p`。

如果没有设备、没有测试框架或命令失败，必须说明原因和剩余风险。

## Android 版本兼容测试

当需求涉及系统 API、权限、存储、通知、后台任务、前台服务、WebView、FileProvider、DeepLink、WindowInsets、相册、蓝牙、定位、媒体、软键盘、状态栏或导航栏时，测试用例矩阵必须包含 Android 版本兼容项。

测试设计必须基于当前项目：

- `minSdk`
- `targetSdk`
- `compileSdk`
- 目标 build variant
- 当前项目已支持的设备范围
- CI 或本地可用的模拟器 / 真机

重点覆盖：

- 低版本设备是否能正常安装、启动和进入相关页面。
- 高版本设备是否触发新权限、新限制或 Manifest 配置要求。
- 权限拒绝、永久拒绝、系统版本不支持权限时的降级体验。
- 通知渠道、通知权限、后台任务、前台服务、Alarm、WorkManager 的版本差异。
- 分区存储、相册/媒体权限、FileProvider、文件 URI 的版本差异。
- `PendingIntent`、`android:exported`、包可见性、DeepLink 的版本差异。
- WindowInsets、状态栏、导航栏、软键盘、暗黑模式、字体缩放导致的 UI 差异。

如果没有对应 Android 版本设备或模拟器，必须把该项标记为“未验证”，并给出建议测试版本和原因。不得把单一设备通过当作全版本兼容通过。

## 禁止事项

- 不得伪造测试结果。
- 不得因为测试失败就直接忽略。
- 不得为了测试擅自新增重型依赖。
- 不得在生产环境运行破坏性测试。
- Monkey、清数据、真实支付、真实删除等操作必须用户明确同意。

## 输出格式

1. 测试范围
2. 测试用例矩阵
3. 自动化可执行项
4. 需要人工验证项
5. 执行命令和结果
6. 失败项分析
7. 未验证项和剩余风险
8. 是否建议继续修复
