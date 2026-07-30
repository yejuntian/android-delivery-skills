#!/usr/bin/env python3
"""脚本名称：implementation_plan.py

用途：校验实施计划与影响半径，并生成绑定当前已确认需求的机器收据。

核心流程：读取固定的 ``实施计划.md``，检查用户需要查看的六类内容；用户明确
确认后保存需求修订、需求摘要、计划摘要和影响半径摘要。后续编码入口和最终门禁
重新校验收据，需求、计划或影响半径变化时旧收据自动失效。

职责边界：不生成计划、不判断业务、不修改需求或 Android 代码，也不操作 Git。
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .impact_radius import (
    ImpactRadiusError,
    impact_radius_digest,
    impact_radius_path,
    load_impact_radius,
)
from .requirement_snapshot import requirement_digest, requirement_summary_digest


PLAN_FILE_NAME = "实施计划.md"
PLAN_RECEIPT_RELATIVE_PATH = Path("test-cases") / "implementation-plan-receipt.json"
PLAN_RECEIPT_VERSION = 1
REQUIRED_PLAN_SECTIONS = (
    "实现范围",
    "已上线业务影响",
    "预计修改文件",
    "测试方案",
    "影响半径摘要",
    "明确不修改范围",
)
BDD_ID_PATTERN = re.compile(r"(?<![\w-])BDD-[0-9]+(?![\w-])")


class ImplementationPlanError(RuntimeError):
    """表示实施计划或确认收据缺失、损坏或已经失效。"""


def implementation_plan_path(requirement_dir: str | Path) -> Path:
    """返回用户查看的固定实施计划路径，避免同一需求产生多份方案。"""
    return (
        Path(requirement_dir).expanduser().resolve() / "docs" / PLAN_FILE_NAME
    ).resolve()


def plan_confirmation_receipt_path(requirement_dir: str | Path) -> Path:
    """返回计划确认收据路径；机器文件与需求测试资料放在同一工作区。"""
    return (
        Path(requirement_dir).expanduser().resolve() / PLAN_RECEIPT_RELATIVE_PATH
    ).resolve()


def implementation_plan_digest(content: str) -> str:
    """对计划文本做换行和首尾空白规范化后计算稳定摘要。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _extract_plan_sections(content: str) -> dict[str, str]:
    """提取并校验固定章节，保持结构检查与语义检查使用同一份切片。"""
    sections: dict[str, str] = {}
    missing: list[str] = []
    for section in REQUIRED_PLAN_SECTIONS:
        heading = re.search(
            rf"^\s*#{{1,6}}\s+{re.escape(section)}(?:[（(（].*?[)））])?\s*$",
            content,
            flags=re.MULTILINE,
        )
        if heading is None:
            missing.append(section)
            continue
        body_start = heading.end()
        next_heading = re.search(
            r"^\s*#{1,6}\s+.+$",
            content[body_start:],
            re.MULTILINE,
        )
        body_end = body_start + next_heading.start() if next_heading else len(content)
        body = content[body_start:body_end].strip()
        if not body:
            missing.append(f"{section}（内容为空）")
            continue
        sections[section] = body
    if missing:
        raise ImplementationPlanError(
            "实施计划缺少必需内容（必须是精确标题，可带括号说明）: " + "、".join(missing)
        )
    return sections


def read_implementation_plan(path: str | Path) -> str:
    """读取并校验计划结构，保证用户确认前能看到六类关键边界。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImplementationPlanError(f"尚未生成实施计划: {source}")
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ImplementationPlanError(f"实施计划无法读取: {source}: {exc}") from exc
    if not content.strip():
        raise ImplementationPlanError(f"实施计划不能为空: {source}")

    _extract_plan_sections(content)
    return content.strip()


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


def _reference_present(
    body: str,
    reference: str,
    all_references: list[str] | None = None,
) -> bool:
    """按确定性文本匹配检查计划是否提到一个机器清单引用。"""
    normalized_body = body.replace("\\", "/")
    normalized_reference = reference.strip().replace("\\", "/")
    if normalized_reference in normalized_body:
        return True
    # 兼容计划只写文件名的旧习惯；同名文件不唯一时要求完整路径。
    if "/" not in normalized_reference or normalized_reference.endswith("/"):
        return False
    filename = normalized_reference.rsplit("/", 1)[-1]
    if all_references:
        if sum(
            candidate.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] == filename
            for candidate in all_references
            if isinstance(candidate, str) and candidate.strip()
        ) > 1:
            return False
    return bool(
        re.search(
            rf"(?<![\w.\-/]){re.escape(filename)}(?![\w.\-/])",
            normalized_body,
        )
    )


def _validate_plan_semantics(
    plan_content: str,
    radius_payload: dict[str, Any],
) -> None:
    """低成本校验计划中的关键引用与影响半径一致，不解析完整 Markdown 语义。"""
    sections = _extract_plan_sections(plan_content)
    scope = sections["实现范围"]
    file_scope = "\n".join(
        (sections["预计修改文件"], sections["影响半径摘要"]),
    )
    test_scope = sections["测试方案"]
    errors: list[str] = []
    impacts = radius_payload.get("impacts") or []
    expected_files = [
        path
        for item in impacts
        if isinstance(item, dict)
        for path in item.get("expected_files") or []
        if isinstance(path, str) and path.strip()
    ]
    impact_ids = {
        item["id"]
        for item in impacts
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    mentioned_ids = set(BDD_ID_PATTERN.findall(scope))
    for identifier in sorted(impact_ids - mentioned_ids):
        errors.append(f"实现范围缺少影响半径 BDD: {identifier}")
    for identifier in sorted(mentioned_ids - impact_ids):
        errors.append(f"实现范围包含非当前影响半径 BDD: {identifier}")
    for item in impacts:
        if not isinstance(item, dict):
            continue
        for path in item.get("expected_files") or []:
            if (
                isinstance(path, str)
                and path.strip()
                and not _reference_present(file_scope, path, expected_files)
            ):
                errors.append(f"计划未引用预期文件: {path}")
        for test_id in item.get("expected_tests") or []:
            if (
                isinstance(test_id, str)
                and test_id.strip()
                and not _reference_present(test_scope, test_id)
            ):
                errors.append(f"测试方案未引用预期测试: {test_id}")
    if errors:
        raise ImplementationPlanError("实施计划与影响半径不一致: " + "；".join(errors))


def _receipt_context(
    snapshot: dict[str, Any],
    requirement_content: str,
    requirement_dir: str | Path,
    plan_path: Path,
    plan_content: str,
) -> dict[str, Any]:
    """构造确认和复核共用的最小上下文，避免两条路径计算规则漂移。"""
    _validate_confirmed_requirement(snapshot, requirement_content)
    radius_path = impact_radius_path(requirement_dir)
    try:
        radius_payload = load_impact_radius(radius_path, snapshot, requirement_content)
    except ImpactRadiusError as exc:
        raise ImplementationPlanError(str(exc)) from exc
    _validate_plan_semantics(plan_content, radius_payload)
    return {
        "requirement_id": snapshot["requirement_id"],
        "requirement_revision": snapshot["revision"],
        "requirement_file_sha256": requirement_digest(requirement_content),
        "requirement_summary_sha256": requirement_summary_digest(snapshot),
        "implementation_plan_path": str(plan_path.resolve()),
        "implementation_plan_sha256": implementation_plan_digest(plan_content),
        "impact_radius_path": str(radius_path),
        "impact_radius_sha256": impact_radius_digest(radius_payload),
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
    context = _receipt_context(snapshot, requirement_content, requirement_dir, plan_path, plan_content)
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
    expected = _receipt_context(snapshot, requirement_content, requirement_dir, plan_path, plan_content)
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
                "需求或实施计划已变化，旧计划确认失效；影响半径变化同样需要重新确认；"
                "请重新展示 实施计划.md 并执行 delivery.py confirm-plan"
            )
    try:
        receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ImplementationPlanError(f"计划确认收据无法读取: {receipt_path}: {exc}") from exc
    return {
        "implementation_plan_sha256": expected["implementation_plan_sha256"],
        "impact_radius_sha256": expected["impact_radius_sha256"],
        "plan_confirmation_receipt_sha256": receipt_sha256,
    }
