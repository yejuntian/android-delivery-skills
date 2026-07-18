# Android XML 布局代码审查清单

## 资源 (Resources)
- [ ] 颜色是否优先复用项目 Theme/Design Token；新增资源是否遵循项目现有语义命名方式。
- [ ] 外边距、内边距、控件尺寸、圆角和文字大小是否复用现有资源；新增值是否按项目既有抽取规则处理，未为了单次使用制造重复 token。
- [ ] 用户可见静态文本使用了 `@string/...`；仅预览数据使用 `tools:text`，运行时动态文本由代码或绑定提供。
- [ ] Shape、Selector 和交互状态是否按设计稿及项目组件体系实现，不强制为没有按压态要求的组件新增状态。
- [ ] 彻底复用了颜色和尺寸资源，**没有创建指向已有资源的纯别名**，也没有重复定义相同数值的 dimens。

## 文本与排版 (Text)
- [ ] 字体家族匹配 Figma，或已说明最接近的降级替代方案。
- [ ] 字重(Weight)和样式匹配设计稿。
- [ ] `includeFontPadding` 是否根据项目排版基线和设计稿明确选择，而不是全局强制关闭。
- [ ] 行高(Line height)和字间距(Letter spacing)准确还原或已作说明。
- [ ] 若使用文字阴影，参数是否符合 Android 属性格式、density 表现和项目资源约定，并在目标设备上验证。
- [ ] 多行文本的省略(Ellipsis)和截断行为匹配设计稿。

## 布局 (Layout)
- [ ] 根布局是否选择了满足当前结构且层级最少的布局，不为“复杂”标签强制更换项目已有方案。
- [ ] 在 `ConstraintLayout` 内部，需要拉伸的维度使用了 `0dp`。
- [ ] 避免了不必要的、深层的 `LinearLayout` 嵌套。
- [ ] RecyclerView 等列表项是否沿用项目已有组件和命名方式，并避免复制重复布局。
- [ ] **当图片或容器有固定宽高比要求时，是否使用了 `app:layout_constraintDimensionRatio`？**
- [ ] **浮层或角标（Overlays/badges）是否通过 `FrameLayout` 或约束(Constraints)正确实现？**
- [ ] 预览数据使用 `tools:text`；运行时静态文案和动态绑定分别使用正确来源。

## 图片与图标 (Images and Icons)
- [ ] 所有的 `ImageView` 均显式声明了 `scaleType`。
- [ ] **Figma 中为 Fill 填充模式的图片，是否默认使用了 `centerCrop`（除非另有说明）？**
- [ ] **Figma 中为 Fit 适应模式的图片，是否默认使用了 `fitCenter`（除非另有说明）？**
- [ ] **SVG 图标是否已正确转换为 VectorDrawable 并在预览中无异常？**

## 系统栏与边距 (System Bars & Insets)
- [ ] **状态栏 (Status bar) 和 导航栏 (Navigation bar) 的避让或沉浸是否已明确处理？**
- [ ] 若项目 targetSdk=35+，根布局已处理 Insets (如声明 `fitsSystemWindows="true"` 或使用 Edge-to-Edge 方案)。
