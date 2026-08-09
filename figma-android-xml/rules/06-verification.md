> ⚠️ **红线检索**：执行前必须结合上下文检索 `00-global-redlines.md`，触碰红线立即回退。

## 阶段 6：使用 build/lint 进行验证

实施后，尽可能按此顺序验证：

1. **XML 资源语法和重复名称**。
2. **Gradle 构建或至少模块资源合并 (merge)**：
   - `./gradlew assembleDebug`
   - 或尽可能小范围的相关 Gradle 任务（以节省时间）。
3. **Lint 或 Android Studio 警告**（可用时）。
4. **【强制审查门限】执行 XML 手动布局审查**：
   - 您**必须**先使用工具读取 `checklists/xml-review-checklist.md` 文件。
   - **【反幻觉屏障：强制证据提取】**在打勾之前，您必须先在报告中输出一个 Markdown 表格，列出刚刚生成的 XML 中所有的 `<TextView>`，以及它们对应的文本内容和使用的是 `android:text` 还是 `tools:text`，并判断其是否符合量化启发式规则（如长度≥10必须是 tools）。
   - 提取完证据表格后，您才能将清单中的所有检查项输出并逐一打勾验证。若有未通过项，立即退回代码修改。

如果不具备运行 Gradle 的条件，请在报告中声明验证受限，并对 XML 代码进行静态审查。
