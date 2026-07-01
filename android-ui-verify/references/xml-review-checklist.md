# XML Fidelity Review Checklist

## Resources
- [ ] No hardcoded colors in layout XML unless project convention requires it.
- [ ] Margins, paddings, sizes, radii, and text sizes use `@dimen/...`.
- [ ] Static strings use `@string/...` or design-time `tools:text` where appropriate.
- [ ] Shape and selector drawables are named clearly.
- [ ] Existing resources are reused where semantically equivalent.

## Text
- [ ] Font family matches or nearest fallback is documented.
- [ ] Weight/style matches Figma.
- [ ] `includeFontPadding=false` is applied where needed.
- [ ] Line height and letter spacing are represented or documented.
- [ ] Multi-line and ellipsis behavior matches the design.

## Layout
- [ ] Complex root uses `ConstraintLayout` or project-approved equivalent.
- [ ] Constrained stretch dimensions use `0dp` inside `ConstraintLayout`.
- [ ] No unnecessary deep `LinearLayout` nesting.
- [ ] Repeated content is extracted into `item_*.xml` for RecyclerView.
- [ ] Image aspect ratios use `layout_constraintDimensionRatio` when applicable.
- [ ] Overlays/badges are implemented with `FrameLayout` or constraints.

## Images and icons
- [ ] Every `ImageView` has explicit `scaleType`.
- [ ] Figma Fill images use `centerCrop` unless otherwise specified.
- [ ] Figma Fit images use `fitCenter` unless otherwise specified.
- [ ] SVG icons are converted to VectorDrawable and checked visually.

## System bars
- [ ] Status bar inclusion/exclusion is known.
- [ ] Navigation bar inclusion/exclusion is known.
- [ ] WindowInsets / edge-to-edge behavior is handled or explicitly not needed.

## Validation
- [ ] Resource names compile.
- [ ] Layout renders in preview or device/emulator.
- [ ] Gradle build/lint run where practical.
- [ ] Screenshot comparison differences are listed before revisions.
