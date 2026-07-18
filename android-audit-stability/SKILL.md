---
name: android-audit-stability
description: Android 运行时稳定性、性能、安全隐私与兼容性风险审计。用于实现完成后检查崩溃、内存泄漏、生命周期、协程与 Flow、ANR、性能、资源释放、权限、导出组件、WebView、敏感数据和 Android 版本兼容，也可结合 logcat、Crashlytics、Leak Trace、Heap Dump 或 Perfetto 证据定位风险。任意 Android 业务改动完成后使用，或用户要求排查稳定性、泄漏、性能、安全隐私和兼容性时使用。
---

# Android 运行时稳定性审计

## 共享规则

执行本 Skill 前，必须先遵守 `../_shared/android-global-rules.md`：默认中文输出、动态资料不写死、接口和 UI 不确定时不脑补、不伪造验证结果、发现问题默认先报告不自动修复。

## 定位

用于在实现后扫描稳定性风险。默认 report-only：只报告发现点，不自动修复，除非用户明确要求修复。

## 职责边界

- **负责**：回答“代码运行后是否可能崩溃、泄漏、卡顿、乱序或在特定 Android 版本失效”。
- **调用**：任意实现完成后必跑；崩溃、ANR、泄漏、协程和兼容性问题可单独调用。
- **不负责**：需求范围、通用代码风格、API 字段契约、设计稿还原或完整测试门禁。
- **证据要求**：动态问题优先使用日志、trace、测试或设备证据；不得用通用经验冒充已复现结论。

## 外部证据使用策略

- 静态审查先看代码和项目配置；动态验证再按条件使用 Android CLI、Gradle、adb、logcat、截图或轻量设备操作。
- Android CLI / adb 只用于安装运行、抓取 logcat、截图、兼容验证或复现崩溃；没有设备或命令不可用时标记未验证。
- Firebase MCP 只在涉及 Firebase、Crashlytics、Remote Config、Analytics、AB 实验、线上崩溃、线上配置或埋点分析时使用。
- Crashlytics / logcat / 线上日志只能作为证据来源；无法访问、无权限或数据不足时必须说明，不能伪造线上结论。
- 发现崩溃、内存泄漏、ANR、兼容性或协程风险后默认先报告，不自动修复。
- 没有实体真机时继续静态审查和模拟器可覆盖验证；只把正式性能、厂商兼容、真实硬件或长期动态证据标为未验证，不得终止其他检查。

## 严重级别

- P0：确定会崩溃、ANR、数据丢失、安全风险，必须优先处理。
- P1：高概率线上问题，例如生命周期泄漏、接口异常未兜底、协程异常未处理。
- P2：中风险问题，例如边界不足、重复请求、状态乱序、弱网异常。
- P3：低风险或质量建议，例如测试覆盖不足、局部可读性问题。

## 检查范围

### 崩溃与异常

检查 `NullPointerException`、`IndexOutOfBoundsException`、`ClassCastException`、`IllegalStateException`、`IllegalArgumentException`、`NumberFormatException`、`ConcurrentModificationException`、`ActivityNotFoundException`、`Resources.NotFoundException`、`SecurityException`、`TransactionTooLargeException`、`OutOfMemoryError`。

重点关注：`!!`、未判空调用、数组和列表越界、`first()` / `last()` / `single()` 无兜底、强转 `as`、解析异常、Bundle / Intent extra 类型不一致、Fragment 未 attach 时 `requireContext()`。

### 生命周期与内存泄漏

检查 ViewModel 是否持有 Activity / Fragment / View / Context，单例是否持有短生命周期对象，Handler / Runnable / Timer / Thread 是否清理，Receiver / Listener / Callback / Observer 是否解绑，Fragment view binding 是否在 `onDestroyView` 释放，Dialog / PopupWindow / WebView 是否泄漏 Activity。

#### 动态泄漏条件门禁

- 生命周期、监听器、协程/Flow、Adapter、Dialog、WebView、Camera、Media 等资源释放发生变化，或需求明确排查泄漏时，动态泄漏门禁适用。
- 先静态定位风险，再复用项目已有 LeakCanary、Leak Trace、Heap Dump 或内存分析流程；不自动新增 LeakCanary 依赖。
- 模拟器可以完成基础复现；没有任何设备时继续其他门禁，并写“静态审查完成，动态泄漏未验证”。
- 单次 `dumpsys meminfo`、静态未发现持有关系或页面退出后内存暂未下降，都不能证明无泄漏。
- 修复前后使用相同进入/退出路径和轮次重验，证据记录引用链、报告路径、设备类型和能力损失。

### 协程与 Flow

检查 `GlobalScope`、协程作用域、`launch` 异常、`CancellationException` 误吞、Flow `catch`、`repeatOnLifecycle`、重复 collect、请求乱序、旧数据覆盖新状态、共享状态并发修改。

### ANR 与主线程

检查主线程网络、数据库、文件 IO、大 JSON 解析、Bitmap 解码、大循环、锁等待、`Thread.sleep`、阻塞式 Future、启动阶段重任务、BroadcastReceiver 耗时任务。

#### 性能条件门禁

- 只有明确性能验收，或最终 diff 影响启动、列表、图片、数据库、序列化、主线程、锁、ANR/卡顿敏感路径时才适用。
- 阈值必须来自需求、项目既有标准或修改前基线；不得自行发明毫秒、帧率、CPU 或内存阈值。
- 复用项目已有 Benchmark、Macrobenchmark、Perfetto 或性能任务，保持设备、系统、variant、数据和操作路径一致并记录多轮结果。
- 模拟器结果只用于调通或趋势参考；正式性能结论原则上需要固定真机。没有真机、基线或 Trace 时标为未验证，但继续其他门禁。
- 工具只提供指标与 Trace，根因必须落到真实调用栈、线程、slice 或 SQL 证据后才能修改代码。

### Android 版本兼容

检查废弃 API、隐式 Intent 未加 export、前台服务权限不足、PendingIntent 未加 flag、大图导致 Binder 崩溃、Target 34+ BroadcastReceiver flag。

### 安全合规与隐私底线

- **隐私日志脱敏底线**：优先复用项目日志封装；无论使用何种日志 API，都不得明文记录密码、手机号、Token 等个人敏感信息（PII）。确认存在敏感信息泄漏时按 P0 报告。
- 当 diff 涉及权限、Manifest 导出组件、DeepLink、WebView、网络安全配置、Token/Cookie、用户数据、本地文件、日志或埋点时，安全隐私门禁适用。
- 检查 exported 组件与 Intent 输入、DeepLink 参数、WebView JS Bridge/文件访问/混合内容、明文 HTTP、本地敏感存储、release 调试入口和最小权限。
- 记录数据来源、存储、传输、日志/埋点、生命周期、信任边界和导出入口；资料不足时不得猜测敏感等级。
- 优先执行项目已有 lint、detekt、Semgrep、MobSF 或安全任务；不自动安装工具，也不得把静态检查写成渗透测试通过。
- 缺少后端、证书、生产配置或真机时记录未验证范围；这不停止其他检查，确认敏感信息泄漏仍按 P0 处理。

### 列表和 Adapter

检查 adapter position 是否可能为 `NO_POSITION`，数据刷新后旧 position 是否过期，快速滑动和分页时是否越界，DiffUtil / stableId / item key 是否正确，异步回调回来后列表是否已变化。

### 资源释放

检查 Cursor、Stream、File、Socket、Camera、MediaPlayer、ExoPlayer、Location、Sensor、WebView、WorkManager、Service、PendingIntent、权限降级。

#### 版本范围核验

继续检查本次改动在项目 `minSdk`、`targetSdk`、`compileSdk` 支持范围内的系统行为差异。

重点检查：

- 是否调用高版本 API，但没有 `Build.VERSION.SDK_INT` 判断、`@RequiresApi` 约束或兼容替代方案。
- 是否使用低版本不可用的类、方法、常量、资源属性、Manifest 配置或主题属性。
- 是否涉及运行时权限差异，例如相机、定位、蓝牙、通知、相册、媒体文件、存储、后台定位。
- 是否涉及系统行为变化，例如 Android 6 运行时权限、Android 8 通知渠道和后台服务限制、Android 10 分区存储、Android 11 包可见性、Android 12 `android:exported` 和 `PendingIntent` mutability、Android 13 通知权限和照片/视频权限、Android 14 前台服务类型和后台启动限制。
- Android 15、Android 16 及后续版本行为变化必须以当前项目 `targetSdk`、`compileSdk` 和官方文档为准，不得凭记忆断言兼容。
- 是否涉及 ForegroundService、WorkManager、Alarm、BroadcastReceiver、Notification、PendingIntent、FileProvider、DeepLink、WebView、WindowInsets、软键盘、状态栏、导航栏、暗黑模式、字体缩放。
- 是否存在 targetSdk 升级后的行为变更风险。
- 是否需要在低版本设备、高版本设备、不同屏幕尺寸设备上分别验证。

如果无法确认 Android 版本兼容性，必须列出需要测试的系统版本、设备类型和具体场景，不得直接认为兼容。

版本兼容发现点必须包含：

- 涉及的 Android API、Manifest 配置或系统能力。
- 受影响的 Android 版本范围。
- 当前代码是否已有版本判断或兼容分支。
- 建议补充的兼容方案。
- 建议测试的模拟器或真机版本。
- 剩余风险。

## 动态验证

按项目条件选择：Android CLI、Gradle 构建、单测、lint、仪器测试、adb logcat、截图、轻量 monkey。Monkey、清数据、真实后端破坏性操作必须用户确认。

logcat 重点搜索：`FATAL EXCEPTION`、`AndroidRuntime`、`ANR`、`NullPointerException`、`IndexOutOfBoundsException`、`IllegalStateException`、`OutOfMemoryError`、`StrictMode`、`CoroutineException`、`NetworkOnMainThreadException`、`TransactionTooLargeException`。

Firebase / Crashlytics 重点关注：崩溃堆栈、非致命异常、受影响版本、设备型号、Android 版本、用户比例、最近发布时间、Remote Config 或 AB 实验开关状态。无法访问 Firebase 时输出“未验证线上数据”。

## 输出格式

每个发现点包含：

- 严重级别
- 类型
- 位置：文件、类、方法、行号
- 触发条件
- 影响后果
- 证据：代码、日志、测试失败或推理依据
- 修复建议
- 是否建议立即修复

最后汇总：已检查项；动态泄漏、性能和安全隐私的适用性、工具与新鲜证据；设备类型和降级能力；未验证项；剩余风险；是否等待用户确认修复。详细状态边界见 `../android-implement-and-verify/references/conditional-capability-gates.md`。
