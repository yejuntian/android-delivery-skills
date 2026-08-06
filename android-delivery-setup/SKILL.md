---
name: android-delivery-setup
description: 为 Android 项目首次接入或重新配置 Android Delivery Skills。用户明确要求初始化、安装、迁移旧 profile、发现 Gradle 模块/变体/UI 技术栈，或检查 Figma XML 集成能力时使用。先只读探索并展示拟写内容，用户确认后才生成项目侧 `.android-delivery/` 配置和 `docs/agents/android-delivery.md`；不修改业务代码、不执行需求交付或最终门禁。
---

# Android Delivery 项目初始化

这是用户显式调用的一次性设置流程。先探索、再展示、后确认、最后写入；不得把示例值冒充项目事实。

## 1. 探索

运行只读检查：

```bash
python3 android-delivery-setup/scripts/setup_project.py inspect --project <Android项目根目录>
```

同时读取已有 `AGENTS.md`、`CLAUDE.md`、`.android-delivery/`、`document/` 和旧 `profiles/*.yaml`。确认：

- Git 根、Gradle wrapper、settings 文件、模块和常见变体。
- XML View、Compose 或混合技术栈，以及现有 Design System。
- Unit、Instrumentation、Lint、截图测试和 Journey 能力。
- `figma-android-xml` 是否已安装并可发现；它只是 XML 项目的可选实现能力。
- 项目已有构建、测试和文档约定，绝不把示例命令写成已验证命令。

## 2. 展示并确认

向用户展示发现结果、缺失项和拟创建/更新的文件。至少明确：

- `.android-delivery/project.yaml`：无密钥的项目能力快照。
- `.android-delivery/channel.example.yaml`：与现有 `delivery.py --config` 兼容的需求通道示例。
- `docs/agents/android-delivery.md`：项目侧消费规则。
- 对现有 `AGENTS.md` 或 `CLAUDE.md` 的最小指针块；没有这两个文件时先询问创建哪一个。

没有用户确认不得执行 apply。不得写 Token、Cookie、密码、私钥、生产数据或 Figma 临时资产 URL。

## 3. 写入

确认后执行：

```bash
python3 android-delivery-setup/scripts/setup_project.py apply \
  --project <Android项目根目录> --confirm
```

已有文件内容不同则停止并展示差异；只有用户明确同意替换生成文件时才使用 `--force`。脚本不自动修改 `AGENTS.md`/`CLAUDE.md`，由当前 Agent 使用带标记的最小块更新现有文件，避免覆盖周边内容。

## 4. 验证

1. 重新运行 `inspect`，确认输出与落盘配置一致。
2. 用复制后的实际 channel 配置执行 `delivery.py init`，只验证配置可解析；没有真实需求时不启动交付。
3. XML + Figma 项目若缺少可调用的 `figma-android-xml`，标记可选能力未安装，不阻塞非 Figma 需求。
4. 告知用户生成了哪些文件、哪些命令尚未真实验证以及如何开始第一个需求。

## 项目侧指针

项目 Agent 文件只保留短指针：完整 Android 需求使用 `android-implement-and-verify`；首次配置使用 `android-delivery-setup`；项目约定读取 `docs/agents/android-delivery.md`。不要复制整套运行时规则。
