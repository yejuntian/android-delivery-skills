#!/usr/bin/env python3
"""脚本名称：implementation_plan.py

用途：校验实施计划并生成绑定当前已确认需求的机器收据。

核心流程：读取固定的 ``实施计划.md``，检查用户需要查看的五类内容；用户明确
确认后保存需求修订、需求摘要和计划摘要。后续编码入口和最终门禁重新校验收据，
需求或计划变化时旧收据自动失效。

职责边界：不生成计划、不判断业务、不修改需求或 Android 代码，也不操作 Git。
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .requirement_snapshot import requirement_digest


PLAN_FILE_NAME = "实施计划.md"
PLAN_RECEIPT_RELATIVE_PATH = Path("test-cases") / "implementation-plan-receipt.json"
PLAN_RECEIPT_VERSION = 1
REQUIRED_PLAN_SECTIONS = (
    "实现范围",
    "已上线业务影响",
    "预计修改文件",
    "测试方案",
    "明确不修改范围",
)


class ImplementationPlanError(RuntimeError):
    """表示实施计划或确认收据缺失、损坏或已经失效。"""


def implementation_plan_path(requirement_dir: str | Path) -> Path:
    """返回用户查看的固定实施计划路径，避免同一需求产生多份方案。"""
    return (Path(requirement_dir).expanduser().resolve() / PLAN_FILE_NAME).resolve()


def plan_confirmation_receipt_path(requirement_dir: str | Path) -> Path:
    """返回计划确认收据路径；机器文件与需求测试资料放在同一工作区。"""
    return (
        Path(requirement_dir).expanduser().resolve() / PLAN_RECEIPT_RELATIVE_PATH
    ).resolve()


def implementation_plan_digest(content: str) -> str:
    """对计划文本做换行和首尾空白规范化后计算稳定摘要。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_implementation_plan(path: str | Path) -> str:
    """读取并校验计划结构，保证用户确认前能看到五类关键边界。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImplementationPlanError(f"尚未生成实施计划: {source}")
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ImplementationPlanError(f"实施计划无法读取: {source}: {exc}") from exc
    if not content.strip():
        raise ImplementationPlanError(f"实施计划不能为空: {source}")

    missing = []
    for section in REQUIRED_PLAN_SECTIONS:
        heading = re.search(
            rf"^\s*#{{1,6}}\s+{re.escape(section)}\s*$",
            content,
            flags=re.MULTILINE,
        )
        if heading is None:
            missing.append(section)
            continue
        body_start = heading.end()
        next_heading = re.search(r"^\s*#{1,6}\s+.+$", content[body_start:], re.MULTILINE)
        body_end = body_start + next_heading.start() if next_heading else len(content)
        if not content[body_start:body_end].strip():
            missing.append(f"{section}（内容为空）")
    if missing:
        raise ImplementationPlanError(
            "实施计划缺少必需内容: " + "、".join(missing)
        )
    return content.strip()


def requirement_summary_digest(snapshot: dict[str, Any]) -> str:
    """摘要当前有效原子义务，防止只绑定修订号却遗漏需求内容变化。"""
    summary = {
        "requirement_id": snapshot.get("requirement_id"),
        "requirement_revision": snapshot.get("revision"),
        "obligations": [
            {
                "id": item.get("id"),
                "text": item.get("text"),
                "required": item.get("required"),
                "sha256": item.get("sha256"),
            }
            for item in snapshot.get("obligations", [])
        ],
    }
    encoded = json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_confirmed_requirement(
    snapshot: dict[str, Any],
    requirement_content: str,
) -> None:
    """确认计划只绑定无待定项且正文摘要一致的正式需求修订。"""
    if snapshot.get("status") != "CONFIRMED" or snapshot.get("pending_changes"):
        raise ImplementationPlanError("需求修订尚未全部确认，不能确认实施计划")
    revision = snapshot.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise ImplementationPlanError("当前需求尚未形成正式修订，不能确认实施计划")
    if snapshot.get("sha256") != requirement_digest(requirement_content):
        raise ImplementationPlanError("requirement_file 已变化，请先确认最新需求修订")
    if not snapshot.get("obligations"):
        raise ImplementationPlanError("当前需求没有有效原子验收项，不能确认实施计划")


def _receipt_context(
    snapshot: dict[str, Any],
    requirement_content: str,
    plan_path: Path,
    plan_content: str,
) -> dict[str, Any]:
    """构造确认和复核共用的最小上下文，避免两条路径计算规则漂移。"""
    _validate_confirmed_requirement(snapshot, requirement_content)
    return {
        "requirement_id": snapshot["requirement_id"],
        "requirement_revision": snapshot["revision"],
        "requirement_file_sha256": requirement_digest(requirement_content),
        "requirement_summary_sha256": requirement_summary_digest(snapshot),
        "implementation_plan_path": str(plan_path.resolve()),
        "implementation_plan_sha256": implementation_plan_digest(plan_content),
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """代理到公共原子写；统一行为与 0600 权限。"""
    from .atomic_write import write_json_atomic
    try:
        write_json_atomic(path, payload)
    except OSError as exc:
        raise ImplementationPlanError(
            f"计划确认收据无法写入: {Path(path).resolve()}: {exc}"
        ) from exc


def confirm_implementation_plan(
    snapshot: dict[str, Any],
    requirement_content: str,
    requirement_dir: str | Path,
) -> tuple[dict[str, Any], Path]:
    """在用户明确确认计划后生成幂等收据，不修改任何业务文件。"""
    plan_path = implementation_plan_path(requirement_dir)
    plan_content = read_implementation_plan(plan_path)
    context = _receipt_context(snapshot, requirement_content, plan_path, plan_content)
    receipt_path = plan_confirmation_receipt_path(requirement_dir)

    if receipt_path.is_file():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            existing = None
        expected_keys = {"version", "confirmed_at", *context.keys()}
        if (
            isinstance(existing, dict)
            and set(existing) == expected_keys
            and existing.get("version") == PLAN_RECEIPT_VERSION
            and isinstance(existing.get("confirmed_at"), str)
            and bool(existing["confirmed_at"])
            and all(existing.get(key) == value for key, value in context.items())
        ):
            return existing, receipt_path

    receipt = {
        "version": PLAN_RECEIPT_VERSION,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        **context,
    }
    _atomic_write(receipt_path, receipt)
    return receipt, receipt_path


def validate_plan_confirmation(
    snapshot: dict[str, Any],
    requirement_content: str,
    requirement_dir: str | Path,
) -> dict[str, str]:
    """复核当前需求与计划仍匹配收据，并返回最终路由需要绑定的摘要。"""
    plan_path = implementation_plan_path(requirement_dir)
    plan_content = read_implementation_plan(plan_path)
    expected = _receipt_context(snapshot, requirement_content, plan_path, plan_content)
    receipt_path = plan_confirmation_receipt_path(requirement_dir)
    if not receipt_path.is_file():
        raise ImplementationPlanError(
            f"实施计划尚未确认，请用户确认后执行 delivery.py confirm-plan: {plan_path}"
        )
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImplementationPlanError(f"计划确认收据无法读取: {receipt_path}: {exc}") from exc
    required_keys = {"version", "confirmed_at", *expected.keys()}
    if not isinstance(payload, dict) or set(payload) != required_keys:
        raise ImplementationPlanError(f"计划确认收据结构无效: {receipt_path}")
    if payload.get("version") != PLAN_RECEIPT_VERSION:
        raise ImplementationPlanError(f"计划确认收据版本无效: {receipt_path}")
    if not isinstance(payload.get("confirmed_at"), str) or not payload["confirmed_at"]:
        raise ImplementationPlanError(f"计划确认收据缺少确认时间: {receipt_path}")
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ImplementationPlanError(
                "需求或实施计划已变化，旧计划确认失效；"
                "请重新展示 实施计划.md 并执行 delivery.py confirm-plan"
            )
    try:
        receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ImplementationPlanError(f"计划确认收据无法读取: {receipt_path}: {exc}") from exc
    return {
        "implementation_plan_sha256": expected["implementation_plan_sha256"],
        "plan_confirmation_receipt_sha256": receipt_sha256,
    }
