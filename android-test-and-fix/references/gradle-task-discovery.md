# Gradle 任务发现按需规则

只在 `android-test-and-fix` 需要确认 Gradle task、模块或 variant，且已确认文件仍无法给出命令时读取本文件。总入口、route、gate 和普通业务实现阶段不得加载本文件。

## 先读已有文件

按顺序读取当前需求目录中的事实源：

1. `实施计划.md`
2. `test-cases/impact-radius.json` 的 `expected_tests`
3. `test-cases/test-mapping.json`
4. `test-results/**` 下本轮执行收据和日志
5. CI、README、项目脚本或用户确认信息

这些文件已覆盖当前 `requirement_revision` 且 Gradle/模块/variant 未变化时，直接复用命令；不得重新发现，也不得为了省事改跑全量任务。

## 允许触发发现

只有以下情况才运行项目能力发现器：

- 首次接入项目且没有任何已确认验证命令。
- 本轮修改了 Gradle、模块、variant、CI 或验证脚本，导致前序命令来源失效。
- 老项目存在自定义 flavor、模块或质量任务，CI/README/项目脚本仍无法确认。
- 当前静态门禁必须绑定项目已有 task，但所有已确认文件都缺少来源。

运行命令：

```bash
python3 <android-delivery-skills>/scripts/android_project_capabilities.py --config <配置>
```

该脚本内部会读取 wrapper/settings，并执行目标项目的 Gradle task 列表发现。结果只证明能力存在，不证明任务已经执行或通过。

## 禁止重复浪费

- 如果 `capabilities.json`、实施计划或执行收据已经覆盖当前需求修订，先读文件，不重跑发现。
- 发现器失败、耗时或扫描截断只记录能力损失，不等价于需求失败。
- 不得猜 task 名，不得自动安装工具、添加插件、修改依赖或升级 Gradle/AGP/JDK。
- 发现结果不能替代 `execution_evidence.py` 生成的真实执行证据。
