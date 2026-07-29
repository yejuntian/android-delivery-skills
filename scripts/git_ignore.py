#!/usr/bin/env python3
"""Register Android Delivery machine state in a repository's local Git exclude.

The requirement documents stay versioned, while ``<requirement_dir>/.state`` is
local workflow state.  Using ``.git/info/exclude`` keeps this setup out of the
project diff and avoids changing a team's committed ``.gitignore`` file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Android Delivery targets Unix hosts.
    fcntl = None  # type: ignore[assignment]

from .git_changes import GitInspectionError, git_common_dir, worktree_root


MANAGED_COMMENT = "# Android Delivery machine state (generated; do not commit)"


class GitIgnoreError(RuntimeError):
    """表示无法登记项目级本地 Git 忽略规则。"""


@dataclass(frozen=True)
class GitExcludeRegistration:
    """描述本次是否新增了需求机器状态的本地排除规则。"""

    exclude_path: Path | None
    pattern: str | None
    added: bool


def _state_pattern(repo_root: Path, requirement_dir: Path) -> str | None:
    """根据需求目录生成只覆盖其机器状态的 Git exclude pattern。"""
    try:
        relative = requirement_dir.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return "/.state/"
    # 并行需求的规范目录是 document/<日期-英文名>/；一条规则覆盖同项目所有需求。
    if relative.parts[0] == "document":
        return "/document/*/.state/"
    return f"/{relative.as_posix()}/.state/"


def _append_pattern(exclude_path: Path, pattern: str) -> bool:
    """在文件锁保护下幂等追加规则，避免并行窗口互相覆盖。"""
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with exclude_path.open("a+", encoding="utf-8") as stream:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.seek(0)
                content = stream.read()
                if pattern in {line.strip() for line in content.splitlines()}:
                    return False
                stream.seek(0, 2)
                if content and not content.endswith(("\n", "\r")):
                    stream.write("\n")
                stream.write(f"{MANAGED_COMMENT}\n{pattern}\n")
                stream.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise GitIgnoreError(f"无法写入 Git 本地忽略文件: {exclude_path}: {exc}") from exc
    return True


def ensure_requirement_state_ignored(
    project_path: str | Path,
    requirement_dir: str | Path,
) -> GitExcludeRegistration:
    """确保当前项目 Git 自动忽略需求目录下的机器状态。

    需求目录位于项目外时不需要登记；项目尚未初始化 Git 时也保持无操作，
    由调用方现有的 Git 环境门禁负责给出更准确的错误。
    """
    project = Path(project_path).expanduser().resolve()
    requirement = Path(requirement_dir).expanduser().resolve()
    try:
        repo_root = worktree_root(project)
        common_dir = git_common_dir(project)
    except GitInspectionError:
        return GitExcludeRegistration(None, None, False)

    pattern = _state_pattern(repo_root, requirement)
    if pattern is None:
        return GitExcludeRegistration(None, None, False)
    exclude_path = common_dir / "info" / "exclude"
    added = _append_pattern(exclude_path, pattern)
    return GitExcludeRegistration(exclude_path, pattern, added)
