# 并行需求、轮换与续接

## 上下文续接

- 需求澄清到计划确认尽量保持同一上下文，避免在事实尚未物化时丢失决策依据。
- 计划确认后允许清理或压缩上下文；恢复时先读 `<requirement_dir>/docs/续接指南.md`，再验证当前需求、计划收据、映射和 Git 状态，不依赖聊天摘要。
- 续接指南展示当前修订、CURRENT/STALE、计划确认、最终结论和下一步；机器 JSON 是门禁附件，不能替代人读追溯。

## 并行通道

- 一个需求使用一个 git worktree、独立分支、独立 channel 配置和独立 `requirement_dir`；同通道内串行。
- `check-env` 原子占用当前物理 worktree 路径；同一 worktree 的第二个活动需求阻断，不同 worktree 即使属于同一 Git 仓库也允许并行。
- 后续 `route` 会复核占用身份，最终 gate 继续复核 route 快照、Git 基线和当前代码摘要；完成、取消或集成后释放通道。
- 项目内 worktree 通道把文档放 `<project>/document/<日期-英文名>/` 并随代码提交；项目外串行轮换通道由 `requirement_workspace.py next` 创建到 `requirements-runtime/REQ-*`，不进入目标项目 Git。两者内部职责相同，`.state/` 都是不进 Git 的需求级机器状态；`document/` 不参与代码 diff 和代码摘要，但目录之外的真实代码不能借此绕过门禁。
- 项目内 `requirement-workspace.json` 只保存相对需求目录的项目引用，状态摘要不展开本机绝对目录；历史绝对引用和项目外轮换目录继续兼容。
- 共享真机、模拟器和账号仍需串行使用。

## 合并

- 私有需求分支集成前一次 `git rebase` 到最新主分支；共享分支不 rebase，不使用 cherry-pick 作为默认集成方式。
- 发生冲突时先读取双方需求、相关提交说明、调用方和测试，分别说明每侧改动要保护的行为，不按 ours/theirs、新旧时间或代码行表面选择。
- 两侧意图兼容时同时保留；不兼容时服从当前集成目标和已确认需求，明确记录放弃哪项及原因。不得借解决冲突发明未确认的新行为或顺手重构。
- 主工作树使用 `git merge --ff-only` 保持线性历史。
- rebase 或合并后旧分支证据不再证明最终主干代码；在最终代码上重跑受影响门禁。
- `requirement_workspace.py integrate` 只汇总结论、批次和释放通道，不替代 Git 合并或最终复验。

## 下一个串行需求

只有用户明确完成/取消上一需求并要求开始新需求时才运行 `requirement_workspace.py next`。先预览，再由用户确认后追加 `--confirm`；随后重新 `delivery.py init` 并在需求确认后使用 `check-env --new-requirement` 建新基线。旧目录、BDD、映射和证据保持原样。

回收同样先预览后确认；轮换成功但回收失败时保留新需求，不重复执行 next。状态不明、活动中或未超过保留数量/天数的需求不得回收。
