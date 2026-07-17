# Journey 执行暂存目录

Journey 的适用场景、禁用场景、完整流程、配置和故障处理请先阅读 [`JOURNEY_USAGE.md`](../../../../JOURNEY_USAGE.md)。

先在当前 Android Studio 中使用 `New > Journey Test` 生成首个官方模板，确保 Studio 自动写入匹配当前版本的 XML schema、testSuites 和 Run Configuration。

本目录只是共享壳的执行暂存区，不是测试用例的事实来源。每次需求的 Journey XML 默认放在 `<requirement_dir>/test-cases/journeys/`，`run_journey.py` 执行前会清除这里的旧 XML，再同步当前用例集，避免切换项目后误跑旧用例。不要手工长期维护本目录中的 `.xml`。

Journey XML 应由 `android-test-and-fix` 根据用户已经确认的需求和 BDD 自动生成。不得要求用户理解或手写 XML；只有需求没有说明前置条件或预期结果时，才向用户确认业务含义。

运行前 `run_journey.py` 会拒绝 0 个 `.xml`、无法解析的 XML 和没有 action/step 的 Journey，避免空测试假绿。`.xml.example` 仅作结构参考，不会被执行或清理。

## Journey XML 结构说明

> ⚠️ Journey 是 AGP 9.0+ 的 **Studio Labs 预览功能**,确切 XML schema 以你本机 AGP 版本为准。
> 以下结构基于官方文档描述(step = 操作 + 断言)。首次创建建议用 Android Studio 的
> `New > Journey Test` 模板生成一个权威骨架,再把 AI 生成的步骤填进去。

一个 Journey 由若干 **step** 组成,每个 step 包含:
- **操作描述**:希望执行的点按 / 输入 / 滑动(自然语言,明确具体)。
- **断言(Then)**:期望看到的界面状态(成功条件),作为 step 的一部分。

编写原则(摘自官方):
1. 假设被测应用已在前台 —— 不要把"启动应用"作为步骤。
2. 语言要明确(用"点按'关闭'"而非"选择关闭按钮")。
3. 把成功条件写进步骤("点按提交按钮发送邮件,应关闭邮件并返回收件箱")。
4. 复杂步骤拆成更具体的离散步骤,提高可复现性。

## 与 BDD 的对应

需求的 BDD 验收标准(Given/When/Then)直接映射:
- `Given` → Journey 的前置(由 testSuites 自动启动应用保证)
- `When` → Journey step 的操作
- `Then` → Journey step 的断言

不要把 `Given` 当成“自动启动应用”：必须另行准备登录、数据、权限、DeepLink、语言、主题、字体和方向。`When` 拆成独立 action，`Then` 写成独立 verify/check action。
