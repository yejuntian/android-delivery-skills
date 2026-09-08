# Android Delivery Skills

一套为个人 Android 开发与交付实践打造并开源的 Skill 组合。它将需求澄清、
功能实现、测试修复、代码审查、UI 验收和 API 契约核验拆分为职责明确的
Skill，使 Agent 只在需要时加载对应流程，减少无关上下文对当前任务的干扰。

## 包含的 Skill

- `android-implement-and-verify`：Android 新功能、需求变更和 Bug 修复的总入口。
- `android-onboard-existing-project`：以实际证据为基础接手陌生 Android 项目。
- `android-test-and-fix`：执行测试、诊断失败并完成最小范围修复。
- `android-code-review`：对照已确认需求审查 Android 代码改动。
- `android-verify-api-contract`：核验 API 契约与客户端实现是否一致。
- `android-verify-ui`：通过真实截图验收 UI、交互和无障碍表现。
- `figma-android-xml`：将 Figma 设计转换为 Android XML 和相关资源。

## 当前状态

本仓库由个人 Skill 工作区独立迁移而来，现有 Skill 行为保持不变。目前仍在补充
开源发布所需的打包方式、安装说明、许可证、可移植性检查和公开文档。

本地使用时，请从 `profiles/local.example.yaml` 复制个人配置。不要提交或发布
真实的 `profiles/local.yaml`、`.env`、访问令牌或其他敏感信息。
