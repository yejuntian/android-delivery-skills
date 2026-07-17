# Android XML 布局代码审查清单

## 资源 (Resources)
- [ ] 颜色是否全部提取为资源，且严格遵守了“十六进制字面量命名”？（如 `@color/color_FFFF86FC`，严禁使用语义命名）
- [ ] 外边距(Margins)、内边距(Paddings)、控件尺寸、圆角和文字大小是否遵守了“按需抽取”？复用≥2次的抽取了 `@dimen`，孤立尺寸一律直接内联硬编码。
- [ ] 静态文本使用了 `@string/...`，**预览用的假数据只硬编码在 `tools:text` 中，绝对没有污染到 `strings.xml`**。
- [ ] 形状(Shape)和选择器(Selector)命名清晰，**按钮等交互组件必须使用带有按下态的 Selector**。
- [ ] 彻底复用了颜色和尺寸资源，**没有创建指向已有资源的纯别名**，也没有重复定义相同数值的 dimens。

## 文本与排版 (Text)
- [ ] 字体家族匹配 Figma，或已说明最接近的降级替代方案。
- [ ] 字重(Weight)和样式匹配设计稿。
- [ ] **严格确保在必要处添加了 `android:includeFontPadding="false"`**。
- [ ] 行高(Line height)和字间距(Letter spacing)准确还原或已作说明。
- [ ] 若使用了文字阴影，`android:shadowDx` / `android:shadowDy` / `android:shadowRadius` 是否都直接写成了裸数字，而不是 `@dimen/...` 或 `dp/sp` 单位字符串。
- [ ] 多行文本的省略(Ellipsis)和截断行为匹配设计稿。

## 布局 (Layout)
- [ ] 复杂的页面根节点使用了 `ConstraintLayout`。
- [ ] 在 `ConstraintLayout` 内部，需要拉伸的维度使用了 `0dp`。
- [ ] 避免了不必要的、深层的 `LinearLayout` 嵌套。
- [ ] **对于 RecyclerView 等列表，重复的内容是否已提取到独立的 `item_*.xml` 文件中？**
- [ ] **当图片或容器有固定宽高比要求时，是否使用了 `app:layout_constraintDimensionRatio`？**
- [ ] **浮层或角标（Overlays/badges）是否通过 `FrameLayout` 或约束(Constraints)正确实现？**
- [ ] 动态数据仅使用 `tools:text`，未混用 `android:text`。

## 图片与图标 (Images and Icons)
- [ ] 所有的 `ImageView` 均显式声明了 `scaleType`。
- [ ] **Figma 中为 Fill 填充模式的图片，是否默认使用了 `centerCrop`（除非另有说明）？**
- [ ] **Figma 中为 Fit 适应模式的图片，是否默认使用了 `fitCenter`（除非另有说明）？**
- [ ] **SVG 图标是否已正确转换为 VectorDrawable 并在预览中无异常？**

## 系统栏与边距 (System Bars & Insets)
- [ ] **状态栏 (Status bar) 和 导航栏 (Navigation bar) 的避让或沉浸是否已明确处理？**
- [ ] 若项目 targetSdk=35+，根布局已处理 Insets (如声明 `fitsSystemWindows="true"` 或使用 Edge-to-Edge 方案)。
