> ⚠️ **红线检索**：执行前必须结合上下文检索 `00-global-redlines.md`，触碰红线立即回退。

## 阶段 1：读取和标准化 Figma 设计 (必需的第一步)

在编辑任何文件之前，必须先审查项目环境和 Figma 输入。

### 项目审查
检查以下项目（如存在）：
- Gradle 模块和 Android 插件设置。
- 屏幕是否使用 Activity、Fragment、ViewBinding、DataBinding 或传统的按 ID 绑定。
- 现有的 `res/values/colors.xml`、`dimens.xml`、`styles.xml`、`themes.xml`、`strings.xml`。
- 现有的自定义控件、基础布局、适配器、可绘制对象命名约定和排版资源。
- ConstraintLayout、RecyclerView、AppCompat 和 Material Components 的可用性。
- minSdk、targetSdk 以及是否已经存在边到边 (edge-to-edge) / WindowInsets 处理。

### Figma 审查与视觉感知 (获取高清参照图)
为了实现“一比一”的高保真还原，您必须首先“看到”原图：

1. **执行下载脚本**：在审查任何 MCP 信息前，必须先在后台执行 `python3 scripts/figma_workflow.py fetch [用户提供的Figma链接] --scale 1`（必须附加 `--scale 1` 强制以 1 倍图拉取根 Frame 供视觉参考，防止大图超时）。
2. **读取本地高清图**：脚本执行成功后，会在控制台输出图片保存的真实路径。您必须主动使用 `view_file` 工具读取该目录下生成的 `.png` 图片，以获取真实的颜色、光影、排版等视觉基准。
3. **补充数据审查**：结合本地高清图，如果配置了 Figma MCP 工具，请优先使用并进一步读取辅助信息：
   - 设计上下文
   - 元数据
   - 变量 (variables) / 样式 (styles)
   - 组件名称和变体 (variants)
   - 资产导出信息
4. **缺失兜底**：如果 Figma MCP 不可用或不完整，请使用提供的任何截图/规范，并将缺失的值标记为假设。当确切的颜色、字体或尺寸不可用且无法从图像中推断时，不要凭空编造，请明确列出缺失。

### Frame 类型预处理（仅提供多个 Figma 链接时执行，单链接跳过）

> 📋 规则详见：[checklists/frame-classification.md](../checklists/frame-classification.md)


