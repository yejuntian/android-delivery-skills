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
2. 校验项目路径和目标分支。
3. 读取 `requirement_file` 需求文档。
4. 只做需求理解。
5. 等你确认理解是否正确。
6. 未确认前不进入最终方案、不改代码。

## 确认后继续

如果需求理解正确，你说：

```text
理解正确，继续。
```

然后再进入：

- 正式影响范围分析
- 技术方案
- 测试用例
- 风险检查
- 是否执行代码修改

## 单独调用专项 Skill

```text
使用 android-ui-verify。
使用 android-api-contract-review。
使用 android-test-delivery。
使用 android-stability-review。
使用 android-code-quality-review。
```

这些专项 Skill 也默认遵守中文输出、动态资料不脑补、发现问题先报告不自动修复的共享规则。
