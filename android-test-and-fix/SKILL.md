---
name: android-test-and-fix
description: 为 Android 改动选择并执行受影响测试，建立紧反馈循环并在已确认范围内诊断修复。用于单测、Instrumentation、AI Journey、构建、Lint、设备回归失败、疑难 Bug、偶发故障、性能回归，或最终交付需要测试验证时；支持在不升级老项目 AGP 的前提下由 Agent 自动测试已安装 APK，不创建自定义 Journey Harness。
---

# Android 测试与修复

读取当前需求自己的配置、已确认 `spec.md`、项目 `AGENTS.md`、Gradle 配置、CI 和相邻测试，先定位 `requirement_dir`，再确认真实模块、variant、包名与设备状态。上下文没有给出需求目录时，使用 `android-implement-and-verify` 的定位规则：复用配置路径；否则复用唯一同名日期目录、让用户选择多个候选，或在没有匹配时按当天创建并写回。旧目录只有唯一 `docs/<requirement_name>.md` 时把它作为兼容规格源，不创建第二份。不得把示例任务当成项目事实，也不自动安装工具、升级构建或修改 baseline。

## 选择最小测试

- 实现循环：当前测试类、受影响模块测试和必要编译。
- UI 行为：优先项目已有 Instrumentation、UIAutomator 和截图测试；核心端到端路径可使用 AI Journey，人工结果必须与自动化证据明确区分。
- 数据/API：优先 mapper、Repository、序列化和集成边界测试。
- 最终交付：在局部测试稳定后执行一次适用的完整测试、构建和 Lint。

测试必须验证用户可观察行为。记录实际命令、variant、设备、测试数量、失败数量和关键输出；测试数量为零、命令未运行或报告属于旧代码时均视为未验证。

## AI Journey 自动化

对已确认且前置可安全准备的核心端到端 UI 路径，由 Agent 创建 `<requirement_dir>/test-cases/journeys/<需求作用域>/<场景名>.xml`，把 BDD 转为官方 Journey XML，并自动构建、准备设备、安装和启动应用、逐步操作、判断可见结果及输出证据。该目录保存需求级 Journey 事实，不要求用户预建。每个 `<action>` 只写一个明确 UI 动作或一个以 `Check`、`Verify` 开头的可见结果；应用由执行器启动，不写“启动应用”步骤。

```xml
<journey name="用户路径">
  <description>说明要验证的用户意图</description>
  <actions>
    <action>Tap the visible target.</action>
    <action>Verify that the expected result is visible.</action>
  </actions>
</journey>
```

需求级 Journey XML 始终以 `requirement_dir` 中的文件为准；业务项目支持官方 Journey Test 时复用项目执行配置，不把唯一用例迁成项目内另一份事实源。项目低于 AGP 9.0.0 时不得为测试升级构建系统：沿用原 Gradle 任务生成 APK，优先使用 Android CLI 对已安装应用执行 Journey；创建 Journey XML 不等于创建自定义 Harness、Schema 或运行脚本。Android CLI 不可用时改用项目已有 Instrumentation 或 UIAutomator，仍无法自动执行则报告阻塞，不降级为人工通过。

Agent 按 XML 顺序执行每个 action，以布局树、截图、应用状态和日志判断结果；动作无法完成、应用退出、崩溃、卡死或断言不满足时立即失败，未执行步骤标记跳过。仅将 Journey 用于当前稳定支持的点击、输入和滑动/滚动；双击、长按、多指、旋转、计数、条件分支和精确耗时改用确定性自动测试。

## 失败闭环

疑难 Bug、偶发故障或性能回归先建立紧反馈循环：确定一个已经实际运行、能命中用户准确症状、足够快速稳定且 Agent 可重复执行的命令或测试入口。无法建立时，报告已尝试方式和缺少的环境或证据，停止猜因和修复。

1. 复现最小失败并区分代码缺陷、测试缺陷、环境缺失和历史问题。
2. 只修复已确认范围内的根因；需求语义不明确时返回主 Skill 澄清。
3. 先重跑失败测试，再跑直接受影响回归。
4. 同一根因连续三轮没有进展时停止，报告证据、尝试和解除条件。

不得为通过测试删除业务断言、扩大超时、吞掉异常或把 Fake 放入 release 路径。设备被其他应用抢占、离线、权限或签名不匹配时，先报告环境事实，不把它写成产品失败。

最终固定输出四项：结论、实际命令与测试数量、失败或发现、未验证项与剩余风险。结论区分“通过”“失败”“未验证”和“不适用”。用户未要求修改时只诊断，不自动修复。
