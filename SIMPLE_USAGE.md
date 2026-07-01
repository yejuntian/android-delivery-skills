# Android Delivery Skills 最简单用法

## 日常只改一个配置

编辑：

```text
/Users/shareit/work/MyPython/ai-skills/android-delivery-skills/profiles/local.yaml
```

通常只需要改：

- `project_path`：Android 项目路径
- `branch`：目标分支
- `requirement_file`：需求 Word / Markdown / PDF / TXT 文件
- 可选 `ui.links` / `ui.screenshots`
- 可选 `api.links` / `api.files` / `api.status`

## 最短调用

以后可以直接说：

```text
使用 android-delivery-workflow。
```

默认行为：

1. 读取 `profiles/local.yaml`。
2. 读取 `requirement_file` 需求文档。
3. 只做需求理解。
4. 等你确认理解是否正确。
5. 未确认前不进入最终方案、不改代码。

## 确认后继续

如果需求理解正确，你说：

```text
理解正确，继续。
```

然后直接进入编码：

1. 修改前校验项目路径、目标分支和工作区状态。
2. 读取相关代码并复用现有链路。
3. 直接实现需求，不再固定输出一轮前置分析报告。
4. 只有遇到关键资料缺失、高风险改动或分支/工作区异常时才暂停询问。
5. 编码后再执行实际 diff 审查、接口审查、UI 验证、测试、稳定性和代码质量检查。


## 外部链接读取

Figma、YApi、Apifox、Swagger 等链接打不开或需要登录时，不再默认终止流程：

1. 优先读取本地 `requirement_file`、`ui.directory`、`api.files`。
2. 能通过 MCP / API / 浏览器读取就使用。
3. 读不到就记录“外部资料未读取”和剩余风险。
4. 只有该链接是唯一关键资料且没有任何替代资料时，才暂停让你补充资料或授权。

## 单独调用专项 Skill

```text
使用 android-change-review。
使用 android-api-contract-review。
使用 android-ui-verify。
使用 android-test-delivery。
使用 android-stability-review。
使用 android-code-quality-review。
```

默认定位：

- `android-change-review`：编码后审查实际 diff 和影响范围。
- `android-api-contract-review`：编码后审查接口实现是否符合契约。
- `android-ui-verify`：编码后验证 UI 还原、截图和状态。
- `android-test-delivery`：编码后生成并执行测试交付检查。
- `android-stability-review`：编码后扫描稳定性风险。
- `android-code-quality-review`：编码后审查代码质量和架构一致性。

只有用户明确要求“先分析别改”，或继续编码会脑补/误改/高风险破坏时，专项 Skill 才前置使用。
