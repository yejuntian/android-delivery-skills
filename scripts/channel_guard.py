#!/usr/bin/env python3
"""保护一个物理 Git worktree 只被一个需求通道使用。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .git_changes import GitInspectionError, current_branch, git_common_dir, worktree_root


CHANNEL_GUARD_VERSION = 1
CHANNEL_LOCK_ROOT = Path("codex-delivery") / "worktree-locks"


class ChannelGuardError(RuntimeError):
    """表示当前 worktree 已被其他需求占用或身份已经漂移。"""


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _channel_id(worktree_path: Path, requirement_dir: Path) -> str:
    raw = f"{worktree_path}\0{requirement_dir}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _identity(project_path: str | Path) -> tuple[Path, Path, str]:
    project = _resolve(project_path)
    try:
        root = worktree_root(project)
        common_dir = git_common_dir(project)
        branch = current_branch(project)
    except GitInspectionError as exc:
        raise ChannelGuardError(str(exc)) from exc
    if root != project:
        raise ChannelGuardError(
            "project_path 必须指向 Git worktree 根目录，不能指向其中的子目录: "
            f"{project}（实际根目录: {root}）"
        )
    return root, common_dir, branch


def channel_lock_path(project_path: str | Path) -> Path:
    """返回当前 worktree 的私有锁路径，不把锁文件写进工作树。"""
    root, common_dir, _ = _identity(project_path)
    name = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:32] + ".json"
    return common_dir / CHANNEL_LOCK_ROOT / name


def _read_lock(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ChannelGuardError(f"项目通道锁无法读取: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != CHANNEL_GUARD_VERSION:
        raise ChannelGuardError(f"项目通道锁格式无效，拒绝覆盖: {path}")
    return payload


def _conflict_message(payload: dict[str, Any], path: Path) -> str:
    return (
        "当前 Git worktree 已被其他需求通道占用，不能并行使用同一份物理代码目录。\n"
        f"项目目录: {payload.get('project_path', '未知')}\n"
        f"分支: {payload.get('branch') or 'detached HEAD'}\n"
        f"需求目录: {payload.get('requirement_dir', '未知')}\n"
        f"配置文件: {payload.get('config_path', '未知')}\n"
        f"占用时间: {payload.get('created_at', '未知')}\n"
        f"锁文件: {path}\n"
        "请使用独立 git worktree，或在确认原需求已结束后释放该通道。"
    )


def claim_channel(
    project_path: str | Path,
    requirement_dir: str | Path,
    config_path: str | Path,
    *,
    requirement_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """原子占用 worktree；同一需求重复进入幂等。"""
    root, _, branch = _identity(project_path)
    requirement = _resolve(requirement_dir)
    config = _resolve(config_path)
    path = channel_lock_path(root)
    channel_id = _channel_id(root, requirement)
    payload = {
        "version": CHANNEL_GUARD_VERSION,
        "channel_id": channel_id,
        "project_path": str(root),
        "branch": branch,
        "config_path": str(config),
        "requirement_dir": str(requirement),
        "requirement_id": requirement_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = _read_lock(path)
            if (
                existing.get("channel_id") == channel_id
                and existing.get("project_path") == str(root)
                and existing.get("requirement_dir") == str(requirement)
            ):
                return existing, False
            raise ChannelGuardError(_conflict_message(existing, path))
        content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        os.write(descriptor, content)
        os.close(descriptor)
        descriptor = None
        return payload, True
    except OSError as exc:
        raise ChannelGuardError(f"项目通道锁无法创建: {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def assert_channel(
    project_path: str | Path,
    requirement_dir: str | Path,
) -> dict[str, Any]:
    """确认当前 worktree、分支和需求目录仍属于已占用通道。"""
    root, _, branch = _identity(project_path)
    requirement = _resolve(requirement_dir)
    path = channel_lock_path(root)
    if not path.is_file():
        raise ChannelGuardError(
            f"当前 Git worktree 尚未被需求通道占用: {root}；请先执行 check-env。"
        )
    payload = _read_lock(path)
    if payload.get("project_path") != str(root):
        raise ChannelGuardError(f"项目通道锁与当前 worktree 不一致: {path}")
    if payload.get("requirement_dir") != str(requirement):
        raise ChannelGuardError(_conflict_message(payload, path))
    if payload.get("branch", "") != branch:
        raise ChannelGuardError(
            f"当前分支已变化，项目通道锁属于 {payload.get('branch') or 'detached HEAD'}，"
            f"当前为 {branch or 'detached HEAD'}；请回到原 worktree/分支后重试。"
        )
    return payload


def release_channel(project_path: str | Path, requirement_dir: str | Path) -> bool:
    """释放当前需求通道；锁属于其他需求时拒绝删除。"""
    root, _, branch = _identity(project_path)
    requirement = _resolve(requirement_dir)
    path = channel_lock_path(root)
    if not path.exists():
        return False
    payload = _read_lock(path)
    if payload.get("channel_id") != _channel_id(root, requirement):
        raise ChannelGuardError(_conflict_message(payload, path))
    if payload.get("branch", "") != branch:
        raise ChannelGuardError(
            f"当前分支已变化，不能释放属于 {payload.get('branch') or 'detached HEAD'} 的项目通道。"
        )
    try:
        path.unlink()
    except OSError as exc:
        raise ChannelGuardError(f"项目通道锁无法释放: {path}: {exc}") from exc
    return True
