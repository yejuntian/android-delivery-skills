---
name: android-delivery-guide
description: Android Delivery Skills 的人工导航入口。用户不确定 Android 新需求、Bug 修复、测试、Diff 审查、代码质量、接口契约、Figma/XML UI、真机视觉验收或稳定性问题应使用哪个 Skill 时显式调用。只推荐一个主入口和必要后续流程，不修改代码、配置或交付状态，不执行 route、测试或最终门禁。
---

# Android Delivery 导航

只做导航，不执行被推荐 Skill 的工作，也不把导航结论写成需求事实或专项结果。

## 选择流程

1. 识别用户想要完整交付、单项实现、独立审查还是首次接入。
2. 优先推荐一个主 Skill；只有主流程确实包含后续专项时才列出后续 Skill。
3. 说明推荐理由、开始前需要的资料和用户可以直接发送的下一条指令。
4. 用户意图仍有两种合理路径时，只追问会改变主 Skill 的一个问题。

## 路由表

| 用户目标 | 主 Skill | 边界 |
| --- | --- | --- |
| 完成 Android 新需求、需求变更、Bug 修复或完整交付 | `android-implement-and-verify` | 唯一完整交付编排器 |
| 第一次把 Android Delivery 接入项目 | `android-delivery-setup` | 只初始化项目配置和 Agent 说明 |
| 只检查 Git diff、影响范围或业务回归 | `android-review-diff` | 不替代质量、接口、UI 或稳定性专项 |
| 只检查架构、可维护性、依赖边界或重复逻辑 | `android-review-code-quality` | 不判断需求是否实现正确 |
| 生成测试、执行受影响测试或修复测试失败 | `android-test-and-fix` | 单独调用时遵守用户的只测/可修复授权 |
| 核对 endpoint、DTO、Repository、mapper 或 OpenAPI | `android-verify-api-contract` | 需要可读取的正式契约证据 |
| 根据 Figma 实现 XML View 页面 | `figma-android-xml` | 只适用于 XML View；生成后回到完整交付入口接管 |
| 验收 Figma/截图与真机 UI、TalkBack 或 A11y 表现 | `android-verify-ui` | 独立验收，不生成 XML，不执行 Journey |
| 排查崩溃、泄漏、ANR、性能、安全隐私或兼容性 | `android-audit-stability` | 按风险和可用证据执行 |

## Figma 分流

- Figma + XML View 实现：先进入 `android-implement-and-verify` 完成需求和计划确认，再由其调用 `figma-android-xml` 生产布局。
- Figma + Compose：不调用 `figma-android-xml`，沿用项目 Compose 体系实现。
- 已有实现只需视觉验收：调用 `android-verify-ui`。
- 只改变颜色、间距或资源且仍在已确认范围：走同一需求的局部增量；新增状态、交互或业务语义时回到需求修订。

## 输出

固定输出四项：`推荐 Skill`、`理由`、`开始前资料`、`下一条指令`。不要声称已经执行推荐流程。
