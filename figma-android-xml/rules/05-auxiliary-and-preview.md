> ⚠️ **红线检索**：执行前必须结合上下文检索 `00-global-redlines.md`，触碰红线立即回退。

## 阶段 5：生成辅助布局与 Tools 预览 (Auxiliary XML & Previews)

**核心准则（红线）：**
- **绝对禁止编写任何 Kotlin/Java 业务代码！** 严禁创建 Adapter、Activity、Fragment 或任何 `.kt` 文件。
- 本技能的最终交付物必须是 100% 纯净的 XML 布局和资源文件。

本阶段的唯一目标是：通过补全辅助 XML 文件（如列表 Item）并大量使用 `tools:` 命名空间，让最终生成的 UI 在 Android Studio 的预览窗口中达到与真实运行完全一致的视觉效果。

### 处理列表 (RecyclerView) 与辅助布局：
- **提取并生成 Item**：如果 Figma 原图中包含列表元素（如多张商品卡片），**必须**将单张卡片剥离出来，单独创建对应的 `item_*.xml` 布局文件。
- **伪造列表连线**：在主布局的 `<androidx.recyclerview.widget.RecyclerView>` 中，强制使用 `tools:listitem="@layout/item_..."` 关联您刚生成的子布局，并使用 `tools:itemCount="5"` 设置预览数量。**严禁编写 Kotlin Adapter 去连线！**

### 绑定样本数据 (Dummy Data)：
- 如果用户没有提供真实数据，**绝对不要**在 XML 里写死 `android:text` 或 `android:src`（除了极少数固定的静态文案如“登录”按钮）。
- 强制使用 `tools:` 属性来填充假数据以供预览：
  - 文本：`tools:text="这是一段占位长文本"` 
  - 图像：`tools:src="@tools:sample/avatars"` 或 `@tools:sample/backgrounds/scenic`

### 沉浸式状态栏与 WindowInsets：
- 不要编写 Kotlin 代码去应用 WindowInsets。请在 XML 根布局中使用 `android:fitsSystemWindows="true"` 或依靠适当的内边距来适配系统状态栏。
