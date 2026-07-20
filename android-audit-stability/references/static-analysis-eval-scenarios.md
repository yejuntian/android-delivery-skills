# Kotlin / Java / Android 静态语义评测样例

本文用于更换 AI、修改静态规则或升级机器契约后的行为评测，不是日常审查时需要加载的泄漏清单。评测者只接收每个场景的“输入代码和任务”，评分者在评测完成后再读取“预期判断”，避免把答案泄漏给被测模型。

## 目录

1. [评测方法](#评测方法)
2. [场景一：Kotlin 单例捕获 Activity](#场景一kotlin-单例捕获-activity)
3. [场景二：Kotlin 单例不持有页面](#场景二kotlin-单例不持有页面)
4. [场景三：callbackFlow 取消后未解绑](#场景三callbackflow-取消后未解绑)
5. [场景四：Compose Effect 使用错误清理实例](#场景四compose-effect-使用错误清理实例)
6. [场景五：Java Handler 与任务超过 Activity](#场景五java-handler-与任务超过-activity)
7. [场景六：Java 资源在所有出口关闭](#场景六java-资源在所有出口关闭)
8. [场景七：Java 与 Kotlin 空值边界](#场景七java-与-kotlin-空值边界)
9. [场景八：闭源 SDK 的持有契约未知](#场景八闭源-sdk-的持有契约未知)
10. [场景九：静态门禁控制面被放宽](#场景九静态门禁控制面被放宽)
11. [场景十：控制面审计候选被漏写](#场景十控制面审计候选被漏写)
12. [场景十一：SARIF 历史债务与来源不明](#场景十一sarif-历史债务与来源不明)
13. [评分规则](#评分规则)

## 评测方法

1. 给被测模型提供一个场景的输入代码和任务，不提供预期判断。
2. 要求它按照 `android-audit-stability` 输出适用不变量、必要调用链、资源所有权和有边界的结论。
3. 问题存在时使用 `scripts/static_analysis.py finding-id` 生成稳定 `FND-...` 编号；不得用行号或本轮顺序作为身份。
4. 安全场景必须避免误报；证据不足场景必须写“静态证据不足”，不能强行判定安全或泄漏。
5. 评分只看是否找到真实所有者、持有关系和清理契约，不按是否背出某个 API 名称给分。

## 场景一：Kotlin 单例捕获 Activity

### 输入代码和任务

```kotlin
object ClickRegistry {
    private var callback: (() -> Unit)? = null

    fun register(activity: FeedActivity) {
        callback = {
            activity.findViewById<View>(R.id.feed).visibility = View.VISIBLE
        }
    }
}
```

任务：判断页面退出后是否存在静态可证明的生命周期风险。

### 预期判断

- 适用“短生命周期对象不能被长生命周期对象持有”。
- `object` 经 `callback` 的闭包强引用 `FeedActivity`；代码中没有释放入口。
- 结论是明确静态问题，不需要等待设备才承认该持有链。
- 修复方向是纠正所有权或增加与真实注册边界对应的清理，不是机械改成 `WeakReference`。

## 场景二：Kotlin 单例不持有页面

### 输入代码和任务

```kotlin
object FeedRouteRegistry {
    private var route: String? = null

    fun update(route: String) {
        this.route = route
    }

    fun clear() {
        route = null
    }
}
```

任务：判断看到 `object` 和缓存字段后是否应报告内存泄漏。

### 预期判断

- 字符串不属于 Activity、Fragment、View 或需要主动释放的资源。
- 只凭 `object`、缓存和 `clear()` 关键词不能报告泄漏。
- 可以检查缓存是否无界或语义是否正确，但本代码没有可证明的页面引用泄漏。
- 该场景用于防止模型把“单例”机械等同于泄漏。

## 场景三：callbackFlow 取消后未解绑

### 输入代码和任务

```kotlin
fun locations(client: LocationClient): Flow<Location> = callbackFlow {
    val listener = LocationListener { location -> trySend(location) }
    client.register(listener)
}
```

任务：分析 Flow 收集取消后的资源和回调关系。

### 预期判断

- 适用“注册/解绑成对”“异步任务不超过宿主”“清理路径可达”。
- 注册的 `listener` 可能继续被 `client` 持有，取消后没有可见解绑路径。
- 不能只因为缺少 `awaitClose` 字样就结束分析；还要核对 `register` 返回值和客户端正式注销契约。
- 确认没有框架托管清理后，报告明确静态问题并建议取消行为测试。

## 场景四：Compose Effect 使用错误清理实例

### 输入代码和任务

```kotlin
@Composable
fun SessionEvents(sessionId: String, client: SessionClient) {
    DisposableEffect(Unit) {
        client.register(SessionListener(sessionId))
        onDispose {
            client.unregister(SessionListener(sessionId))
        }
    }
}
```

任务：判断重组、`sessionId` 变化和离开组合时的清理是否正确。

### 预期判断

- 固定 key 没有表达 `sessionId` 的注册边界。
- 注册和注销创建了两个不同 Listener，若 API 要求同一实例则无法解绑。
- 必须核对 `SessionClient` 的正式契约；契约要求同一实例时是明确问题，契约未知时是证据不足。
- 不能只看到 `onDispose` 就判定安全。

## 场景五：Java Handler 与任务超过 Activity

### 输入代码和任务

```java
final class FeedActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            findViewById(R.id.feed).setVisibility(View.VISIBLE);
        }
    };

    void schedule() {
        handler.postDelayed(refresh, 60_000L);
    }
}
```

任务：判断 Activity 退出后的引用和任务生命周期。

### 预期判断

- 匿名 `Runnable` 隐式持有外部 Activity，消息队列在一分钟内持有 Runnable。
- 没有 `removeCallbacks(refresh)` 或等价生命周期清理。
- 适用短生命周期持有、异步任务和清理可达三项不变量。
- 不能只把内部类改成 `static`；还必须关闭任务和晚到回调路径。

## 场景六：Java 资源在所有出口关闭

### 输入代码和任务

```java
String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

任务：判断正常返回和异常路径是否存在文件资源泄漏。

### 预期判断

- `try-with-resources` 覆盖正常返回和异常退出。
- 当前片段满足获取/释放成对与清理路径可达。
- 不应因为出现 `BufferedReader`、`return` 或 `throws` 就报告资源泄漏。
- 如果调用链还有返回的流或异步使用，再按真实边界扩展；本片段本身没有明确问题。

## 场景七：Java 与 Kotlin 空值边界

### 输入代码和任务

Java：

```java
public final class LegacyUserRepository {
    public String displayName() {
        return cache.get("display_name");
    }
}
```

Kotlin：

```kotlin
fun title(repository: LegacyUserRepository): String {
    return repository.displayName().trim()
}
```

任务：判断混合语言边界的运行时风险。

### 预期判断

- Java 返回值没有空值契约，在 Kotlin 中形成平台类型。
- `cache.get` 可以返回 null 时，直接调用 `trim()` 可能崩溃。
- 这是混合语言空值和公开契约问题，不是内存泄漏。
- 必须在最窄边界明确真实语义；不能随意返回空字符串或批量补注解。

## 场景八：闭源 SDK 的持有契约未知

### 输入代码和任务

```kotlin
override fun onStart() {
    super.onStart()
    analyticsSdk.observe(viewLifecycleOwner) { event -> render(event) }
}
```

任务：SDK 没有本地源码，也没有文档说明 `observe` 是否自动解绑，判断是否泄漏。

### 预期判断

- Lambda 捕获 Fragment/View 是候选，但参数中存在 `viewLifecycleOwner`，不能忽略可能的框架托管。
- 没有 SDK 契约、源码或动态证据时，结论应为“静态证据不足”。
- 列出需要的正式文档、封装实现、Leak Trace 或重复进入退出复现。
- 禁止无依据判为安全，也禁止直接改成弱引用。

## 场景九：静态门禁控制面被放宽

### 输入代码和任务

```diff
+@Suppress("StaticFieldLeak")
 class FeedCache {
 }

-abortOnError = true
+abortOnError = false
```

任务：判断这类变化如何进入最终稳定性结论。

### 预期判断

- 使用 `scripts/static_analysis.py audit-controls` 生成 `CTL-...` 候选。
- 抑制和失败策略变化本身不是生产缺陷，但必须逐项说明原因和扫描范围影响。
- 未说明或确认用于隐藏本次新增问题时标记 `BLOCKING`，稳定性不能通过。
- 合理的局部抑制可以 `JUSTIFIED`，但必须绑定真实问题、范围和替代证据。

## 场景十：控制面审计候选被漏写

### 输入代码和任务

机器审计文件绑定当前 Git 基线和代码摘要，并列出 `CTL-A`、`CTL-B`；模型输出的 `static_analysis.control_changes` 只包含 `CTL-A`。

任务：判断稳定性结果能否通过。

### 预期判断

- 不能通过；候选不是供模型自由挑选的提示，而是必须逐项处置的机器集合。
- 校验审计文件摘要、基线、代码摘要以及候选 id/path/kind 全集。
- 代码在审计后变化时旧文件同样失效，必须在最终代码上重跑。
- 不允许用“另一个候选不重要”的自然语言替代结构化处置。

## 场景十一：SARIF 历史债务与来源不明

### 输入代码和任务

老项目 SARIF 包含三个 Error：一个 `baselineState=unchanged`、一个 `baselineState=new`，另一个没有 `baselineState`。

任务：判断哪些问题阻断本次增量需求。

### 预期判断

- 三个问题和稳定编号全部保留在机器收据中。
- 明确 `unchanged` 的问题作为历史债务记录，不要求借当前需求清理。
- `new` 和缺少可靠基线的来源不明问题保持阻断。
- 不得把全部 Error 一刀切成阻断，也不得由模型自行把来源不明问题降为历史问题。

## 评分规则

每个场景按以下五项各 0 至 2 分，总分 10 分：

| 评分项 | 0 分 | 1 分 | 2 分 |
|---|---|---|---|
| 所有权 | 未识别真实持有者 | 只提到对象或关键词 | 明确创建者、持有者和生命周期 |
| 调用链 | 没有路径 | 只描述正常路径 | 覆盖正常、异常、取消或退出路径 |
| 契约 | 凭经验断言 | 提到 API 但未核对 | 区分项目事实、官方契约和未知边界 |
| 结论边界 | 把候选写成确定结论 | 结论正确但表述模糊 | 明确问题、未发现、证据不足或动态未验证 |
| 修复纪律 | 直接弱引用、迁移或扩大范围 | 方向基本正确 | 最小修复所有权并要求相应测试/证据 |

单个场景低于 8 分，或在安全场景误报、未知场景强行下结论时，本次 Skill/模型评测不通过。评测失败只修改规则或模型提示，不修改目标 Android 项目来迎合样例。
