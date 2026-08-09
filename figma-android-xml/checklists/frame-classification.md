# Frame 类型预处理（仅提供多个 Figma 链接时执行，单链接跳过）

> ⚠️ **红线检索**：执行前必须结合上下文检索 `rules/00-global-redlines.md`，触碰红线立即回退。

下载所有截图后，必须先完成以下分类，再进入阶段 2，严禁直接跳入生成：

## 1. Frame 类型分类（输出一张表，严禁凭感觉乱映射）

| Figma Frame 特征 | 类型 | Android 输出 |
|----------------|------|-------------|
| 完整独立页面 | 基础屏 | `activity_xxx.xml` / `fragment_xxx.xml` |
| 同屏结构基本一致，仅有局部状态/组件变化 (包含如"Loading/Empty/Error/Banner/Active/Hover/Variant/状态/变体"等，或肉眼辨别其为主屏衍生) | 状态变体 | **同一 XML 文件**，新增对应状态 View 并控制 `android:visibility`（同时必须添加 `tools:visibility="visible"` 供工具预览），严禁生成新文件 |
| 同屏，名称含"深色/Dark/Night" | 深色主题 | **不新建布局文件**，仅在 `res/values-night/colors.xml` 覆盖颜色 token |
| 浮层居中覆盖基础屏 | 弹窗 Dialog | `dialog_xxx.xml` |
| 从底部上滑的浮层 | Bottom Sheet | `bottomsheet_xxx.xml` |
| 从侧边滑入的浮层 | Side Sheet | `layout_xxx_side_sheet.xml` |
| 锚定在某 View 旁的气泡/下拉菜单 | PopupWindow | `layout_xxx_popup.xml` |
| RecyclerView 列表项（含各状态变体） | 列表项 | `item_xxx.xml`；状态变体合并进同一文件用 selector，结构差异大才拆 `item_xxx_yyy.xml` |
| 同名 XML 但尺寸对应手机横屏/平板/折叠屏 | 响应式适配 | 同名 XML 放 `layout-land/` / `layout-sw600dp/` / `layout-sw720dp/`，严禁改文件名 |
| 多个 Tab 页（含父容器 Frame） | ViewPager2 | 父容器 → `activity_xxx.xml`（含 `ViewPager2`+`TabLayout`）；每个 Tab 页 → `fragment_xxx_tab.xml` |

> ⚠️ 以下第 2、3 条仅在提供**多个 Figma 链接**时执行：

## 2. 执行顺序规划（多链接专属）

基础屏必须优先完整走完阶段 3-4，派生 Frame（弹窗/变体/主题）强制复用已生成资源，严禁多 Frame 并行独立生成。

## 3. 共享组件识别与 `<merge>` 规则（多链接专属）

跨 Frame 重复出现的结构（如底部导航栏、顶部栏）在基础屏阶段 3 生成时抽为独立文件，通过 `<include>` 引用。
* **放宽 `<merge>` 限制**：对于自闭环的复杂组件（如底部导航栏），**建议抽取为 `LinearLayout` 或 `ConstraintLayout`**。仅当抽取内容直接嵌入父容器且为了减少层级时才使用 `<merge>`。
* **严禁绝对坐标硬编码**：无论是否使用 `<merge>`，**严禁将 Figma 绝对 X/Y 坐标转换为 `layout_marginStart` 等固定 margin**。对于并排元素，必须使用带有 `layout_weight` 的 `LinearLayout` 或带有 `Chains` 的 `ConstraintLayout`，确保响应式布局。

## 4. 弹窗与浮层剥离规则（Dialog / BottomSheet）
* **蒙层处理**：如果 Figma 设计稿中存在黑色半透明蒙层，**允许在根节点生成全屏 `match_parent` 容器并手动设置黑色半透明背景**，并将真正的弹窗卡片实体作为其子节点放入其中。
* **禁绝对定位**：严禁在弹窗实体卡片上使用 `layout_marginTop` / `layout_marginStart` 等进行生硬的绝对定位。
* **强制显式对齐**：严禁假设系统会自动处理对齐！Dialog 的卡片实体必须明确通过 `android:layout_gravity="center"` 或约束链使其在屏幕居中；BottomSheet 的卡片实体必须明确通过 `android:layout_gravity="bottom"` 或约束链使其贴靠屏幕底部。
