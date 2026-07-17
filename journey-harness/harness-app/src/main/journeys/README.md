# Journey 放置目录

把每次需求生成的 Journey XML 文件放在这里。命名建议:
`[需求编号或页面名].xml`,例如 `login_flow.xml`、`cart_checkout.xml`。

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

所以一条 BDD = 一个 Journey step(操作 + 断言)。
