> ⚠️ **红线检索**：执行前必须结合上下文检索 `00-global-redlines.md`，触碰红线立即回退。

## 阶段 4：基于实际生成的布局，重构并按需抽取复用资源

在上一个阶段，你已经以 100% 内联硬编码的方式生成了完美的 XML 布局代码。现在，我们需要清理代码并消除魔法数字，同时坚决避免抽出只用一次的“孤立资源”。

### 1. 通读代码与重复项盘点
仔细扫描你刚刚写出的 XML 布局文件。寻找以下内容：
- **完全相同的尺寸硬编码**：例如出现多次的 `16dp`（包括 margin, padding, 固定宽高，但不包括 0dp 这种结构尺寸）。
- **完全相同的文本外观组合**：例如出现多次的 `android:textSize="14sp" android:textColor="@color/color_FF111827" android:fontFamily="@font/inter_medium"` 组合。

### 2. 精准抽取 (重构红线)
> 🛑 **【复用 ≥2 次红线】只有当某个尺寸数值或某个文本外观组合，在这个布局（或关联的 item 布局）中实实在在地被使用了至少 2 次，才允许将其抽取！**
> 如果某个字号或边距在整个页面里只出现了一次，**必须让它乖乖留在 XML 里保持内联**，绝对禁止为了所谓的“代码规范”去建立一次性的废弃 `@dimen` 或 `@style`。

**抽取步骤：**
1. **追加 Dimens**：将符合条件的尺寸追加到 `res/values/dimens.xml` 中。
   - 使用语义化命名：`<dimen name="space_16">16dp</dimen>`, `<dimen name="text_size_14">14sp</dimen>`, `<dimen name="radius_8">8dp</dimen>`。
   - 严禁出现碎片化的同义词，相同数值合并抽取。
2. **追加 Styles**：将符合条件的文本外观组合追加到 `res/values/styles.xml` 中。
   - 提取 `<item name="android:textSize">...`
   - 提取 `<item name="android:textColor">...`
   - 提取 `<item name="android:fontFamily">...`
3. **替换内联值**：最后，把刚刚在 XML 布局文件中硬编码的值，全部替换为 `@dimen/...` 和 `@style/...` 引用。

通过这一阶段的独立执行，我们不仅确保了代码的可维护性，还从物理结构上杜绝了你在还没写页面之前瞎猜造成的资源污染。
