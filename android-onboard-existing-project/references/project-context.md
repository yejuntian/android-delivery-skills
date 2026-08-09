# 项目上下文

仅在需要持久化陌生项目接手结果时使用。所有接手文档保存到 `<project_path>/document/project-context/`；沿用项目已有等价文档，不复制第二份事实源。

## 最小结构

默认只创建：

```text
document/
└── project-context/
    └── overview.md
```

只有内容已经独立且继续放在 `overview.md` 会降低可读性时，才按需拆分：

```text
document/project-context/
├── overview.md
├── glossary.md
├── architecture.md
├── verification-baseline.md
├── risks-and-unknowns.md
└── adr/
    └── NNNN-<decision>.md
```

- `glossary.md`：只记录已确认的业务术语、关系和边界；不从类名推断，不写实现。
- `architecture.md`：记录模块职责、依赖方向、入口和代表性链路。
- `verification-baseline.md`：记录实际命令、环境、数量、结果和证据边界。
- `risks-and-unknowns.md`：记录影响安全修改、验证或交付的风险、未知和解除条件。
- `adr/`：仅记录难撤销、缺少背景会令人意外且经过真实取舍的决定。

不得创建空文件。项目已有文档覆盖某项职责时，从 `overview.md` 链接该来源。

## overview.md

```markdown
---
observed_commit: <完整提交 SHA>
observed_at: <ISO-8601 时间>
---

# 项目上下文

## 目录
1. [项目定位](#project-purpose)
2. [证据范围](#project-evidence)
3. [模块与入口](#project-modules)
4. [核心链路](#project-journeys)
5. [验证基线](#project-verification)
6. [风险与未知](#project-risks)
7. [进入需求流程](#project-readiness)

<a id="project-purpose"></a>
## 项目定位

<a id="project-evidence"></a>
## 证据范围

| 结论 | 证据类型 | 来源 | 可信边界 |
| --- | --- | --- | --- |

<a id="project-modules"></a>
## 模块与入口

<a id="project-journeys"></a>
## 核心链路

<a id="project-verification"></a>
## 验证基线

| 命令 | 环境 | 结果 | 数量或产物 | 未覆盖边界 |
| --- | --- | --- | --- | --- |

<a id="project-risks"></a>
## 风险与未知

| 类型 | 事项 | 证据 | 影响 | 解除条件 |
| --- | --- | --- | --- | --- |

### 需要原维护者确认

| 问题 | 接收角色 | 无法从项目证明的原因 | 影响 | 回答用途 |
| --- | --- | --- | --- | --- |

<a id="project-readiness"></a>
## 进入需求流程
```

删除无内容章节并同步目录；不要保留占位符。详细内容拆出后，`overview.md` 只保留摘要和相对链接。

## 更新规则

- 每条关键结论附文件、命令、提交或外部来源；不记录密钥值。
- 代码或配置事实不写成生产环境已验证；文档声明和推断不得升级为事实。
- `observed_commit` 和 `observed_at` 只标记本次调查发生的版本与时间；逐项可信范围仍由正文证据声明。
- 后续需求发现稳定项目事实时最小更新对应章节；需求 BDD、实现进度和验收结果仍留在日期需求目录。
- 文档与当前代码、Gradle 或 CI 冲突时，保留来源并纠正失效结论，不为维持文档一致而修改代码。
