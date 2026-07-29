# Gradle 任务发现（仅诊断）

普通单元测试、局部编译和已有测试不以任务发现为前置步骤。AI 应先根据本次修改、测试目录、Gradle 配置、CI、README 和项目脚本直接选择并执行最小命令。

只有以下情况才读取本文件并运行能力发现器：

1. 当前静态门禁必须确认项目已有 task，但项目资料无法判断。
2. 老项目的自定义模块、flavor 或质量任务无法从测试结构和项目资料确定。
3. 用户明确要求诊断项目的 Gradle 能力。

不因“首次处理项目”或“要做一次单元测试”自动运行发现，也不把发现结果当成测试证据。

运行命令：

```bash
python3 <android-delivery-skills>/scripts/android_project_capabilities.py --config <配置>
```

该脚本只读取 wrapper/settings、Gradle task 和有限的构建/CI 配置，结果只用于诊断和帮助 AI 选择命令，不证明任务已经执行或通过。

发现器失败、耗时或扫描截断只记录能力损失；不得自动安装工具、添加插件、修改依赖或升级 Gradle/AGP/JDK。最终仍由 `execution_evidence.py` 记录实际执行命令和结果。
