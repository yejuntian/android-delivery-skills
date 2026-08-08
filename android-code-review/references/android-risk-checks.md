# Android 风险检查

只审查当前需求、diff 和直接调用链中的候选，不对全仓库做理论扫描。

## 六条不变量

1. **短生命周期不被长生命周期持有**：Activity、Fragment View、ViewBinding、Dialog 和回调不能逃逸到单例、静态字段、长驻缓存或不受控任务。
2. **注册与解绑成对**：Listener、Receiver、Observer、Callback 和 `observeForever` 使用同一实例，并覆盖重复进入、异常和销毁路径。
3. **获取与释放成对**：Cursor、Stream、Socket、WebView、Camera、Media、锁和线程池在正常、异常、取消和提前返回时都能释放。
4. **异步任务不超过宿主**：Coroutine、Flow、RxJava、Handler、Future 和回调有明确所有者，宿主结束后停止更新 UI、导航或写入失效状态。
5. **清理路径真实可达**：cleanup 不能只“存在”，还要在部分初始化、重复关闭、晚到回调和清理自身失败时正确执行。
6. **共享状态有并发纪律**：明确读写线程、所有者和同步策略；检查 check-then-act、旧请求覆盖新状态、集合并发修改、锁顺序和主线程阻塞。

## 条件检查

- Compose：核对 `LaunchedEffect`/`DisposableEffect` key、`rememberCoroutineScope` 所有权和捕获的过期对象。
- Fragment：ViewBinding 生命周期通常截止 `onDestroyView`，不能延长到 Fragment 销毁。
- Java/Kotlin：只在真实混合调用处检查 platform type、Nullability、primitive/boxed、集合可变性、异常和取消传播；不机械添加 JVM 注解。
- RxJava/旧 Android：核对 Disposable、Handler、Timer、Executor、匿名内部类和静态集合的所有者与关闭入口。
- 生成代码、反射、JNI、闭源 SDK：审查手写边界并明确静态证据限制，不猜内部实现、不修改生成文件。
- release/R8：只使用项目已有 variant、mapping、usage 或 ABI/API 任务，不自动关混淆、不加包级通配 keep。

## 证据边界

- 编译、Lint、detekt、SpotBugs、Semgrep 或 CodeQL 无告警，只证明已启用规则未命中，不能证明没有泄漏或竞态。
- 动态泄漏、性能和厂商行为需要对应设备与工具证据；缺少条件时写未验证，不把静态检查冒充动态通过。
- 告警区分本次新增、直接受影响、无关历史和来源不明；不更新 baseline 或批量 suppress 掩盖新增问题，也不为清理历史债务扩大需求。
