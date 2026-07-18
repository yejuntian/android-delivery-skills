#!/usr/bin/env python3
"""脚本名称：requirement_snapshot.py

用途：保存已确认需求的本机快照，并生成中途需求变化的确定性文本差异。

职责边界：只处理已经由 delivery.py 提取出的需求正文，不读取 Word、不判断业务语义、
不分配 REQ/BDD ID，也不修改 Git。快照位于用户状态目录，避免污染目标 Android 仓库。
"""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any


class RequirementSnapshotError(RuntimeError):
    """表示需求快照缺失关键字段、损坏或无法安全读写。"""


def requirement_digest(content: str) -> str:
    """对规范化 UTF-8 正文计算摘要，用于快速判断需求是否发生变化。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def write_requirement_snapshot(path: Path, requirement_path: Path, content: str) -> dict[str, Any]:
    """原子写入已确认需求快照，避免进程中断留下半个 JSON 文件。"""
    target = Path(path).expanduser().resolve()
    payload = {
        "version": 1,
        "requirement_path": str(Path(requirement_path).expanduser().resolve()),
        "sha256": requirement_digest(content),
        "content": content.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # 需求正文可能包含未公开业务信息，外部状态文件默认仅允许当前用户读取。
        temporary.chmod(0o600)
        temporary.replace(target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RequirementSnapshotError(f"无法写入需求快照: {target}: {exc}") from exc
    return payload


def load_requirement_snapshot(path: Path) -> dict[str, Any] | None:
    """读取并校验需求快照；文件尚未建立时返回 None，损坏时明确报错。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RequirementSnapshotError(f"需求快照无法读取: {source}: {exc}") from exc
    required = {"version", "requirement_path", "sha256", "content", "created_at"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise RequirementSnapshotError(f"需求快照格式无效: {source}")
    if (
        payload["version"] != 1
        or not isinstance(payload["requirement_path"], str)
        or not isinstance(payload["sha256"], str)
        or not isinstance(payload["content"], str)
        or not isinstance(payload["created_at"], str)
    ):
        raise RequirementSnapshotError(f"需求快照字段类型或版本无效: {source}")
    if payload["sha256"] != requirement_digest(payload["content"]):
        raise RequirementSnapshotError(f"需求快照正文摘要不匹配: {source}")
    return payload


def render_requirement_diff(previous: str, current: str) -> str:
    """输出稳定的逐行差异；业务上的增删改分类仍由 AI 结合语义完成。"""
    before = previous.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    after = current.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(
        difflib.unified_diff(
            before,
            after,
            fromfile="confirmed-requirement",
            tofile="current-requirement",
            lineterm="",
        )
    )
