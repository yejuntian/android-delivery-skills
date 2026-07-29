#!/usr/bin/env python3
"""脚本名称：route_impact.py

用途：保存和校验最近一次 ``delivery.py route`` 产生的最小条件门禁快照。

核心流程：保存专项任务清单、四类条件门禁及直接依据文件，并绑定当前需求修订、
影响半径、Git 基线和代码摘要；本模块只登记任务，不执行专项 Skill。

职责边界：不读取 Git、不判断业务是否真的适用、不执行 Skill 或测试，也不修改项目。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


CONDITIONAL_GATE_IDS = {
    "openapi": "android-verify-api-contract",
    "migration": "android-data-migration",
    "ui_a11y": "android-ui-a11y",
    "security_privacy": "android-security-privacy",
}
CONDITIONAL_GATE_BASIS = {
    "openapi": ("api",),
    "migration": ("data",),
    "ui_a11y": ("ui",),
    "security_privacy": ("api", "data", "system"),
}
ROUTE_IMPACT_VERSION = 5
ROUTE_TASK_STATUSES = {"PENDING"}
ROUTE_SPECIALIST_TASKS = {
    "android-review-diff": "android-review-diff",
    "android-review-code-quality": "android-review-code-quality",
    "android-audit-stability": "android-audit-stability",
    "android-test-and-fix": "android-test-and-fix",
    "android-verify-api-contract": "android-verify-api-contract",
    "android-verify-ui": "android-ui-a11y",
}


class RouteImpactError(RuntimeError):
    """表示路由影响快照缺失、损坏或已不属于当前交付上下文。"""


def build_specialist_tasks(
    impacts: dict[str, list[str]],
    diff_files: list[str] | None = None,
) -> list[dict[str, Any]]:
    """根据 route 候选登记必需专项；只生成任务，不执行任何专项。"""
    if diff_files is not None and not diff_files:
        return []
    all_files = sorted({
        path
        for category_files in impacts.values()
        for path in category_files
    })
    if diff_files:
        all_files = sorted(set(diff_files))
    if not all_files:
        return []

    tasks: list[dict[str, Any]] = []

    def add_task(
        skill: str,
        gate_id: str,
        reason: str,
        basis_files: list[str] | None = None,
    ) -> None:
        tasks.append({
            "id": f"TASK-{skill}",
            "skill": skill,
            "gate_id": gate_id,
            "required": True,
            "status": "PENDING",
            "basis_files": sorted(set(basis_files or all_files)),
            "reason": reason,
        })

    add_task(
        "android-review-diff",
        "android-review-diff",
        "默认审查实际 diff、需求边界和回归范围。",
    )
    add_task(
        "android-review-code-quality",
        "android-review-code-quality",
        "默认审查代码职责、架构边界和可维护性。",
    )
    add_task(
        "android-audit-stability",
        "android-audit-stability",
        "默认审查稳定性、生命周期、并发和兼容性风险。",
    )
    add_task(
        "android-test-and-fix",
        "android-test-and-fix",
        "默认执行受影响测试、证据收集和失败修复闭环。",
    )
    if impacts.get("api"):
        add_task(
            "android-verify-api-contract",
            "android-verify-api-contract",
            "检测到接口候选，必须完成接口契约审查。",
            impacts["api"],
        )
    if impacts.get("ui"):
        add_task(
            "android-verify-ui",
            "android-ui-a11y",
            "检测到 UI 候选，必须完成独立界面与无障碍验收。",
            impacts["ui"],
        )
    return tasks


def build_route_impact(
    context: dict[str, Any],
    impacts: dict[str, list[str]],
    conditional_candidates: dict[str, bool | None],
    diff_files: list[str] | None = None,
) -> dict[str, Any]:
    """构造稳定快照；候选只形成待执行任务，不直接视为专项结论。"""
    conditional_gates = []
    for candidate_id, gate_id in CONDITIONAL_GATE_IDS.items():
        if not conditional_candidates.get(candidate_id):
            continue
        basis_files = []
        for category in CONDITIONAL_GATE_BASIS[candidate_id]:
            for path in impacts.get(category, []):
                if path not in basis_files:
                    basis_files.append(path)
        conditional_gates.append({
            "id": gate_id,
            "basis_files": basis_files,
        })
    return {
        "version": ROUTE_IMPACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requirement_id": context["requirement_id"],
        "requirement_revision": context["requirement_revision"],
        "requirement_file_sha256": context["requirement_file_sha256"],
        "requirement_inputs_sha256": context["requirement_inputs_sha256"],
        "implementation_plan_sha256": context["implementation_plan_sha256"],
        "impact_radius_sha256": context["impact_radius_sha256"],
        "plan_confirmation_receipt_sha256": context["plan_confirmation_receipt_sha256"],
        "baseline_id": context["baseline_id"],
        "snapshot_sha256": context["snapshot_sha256"],
        "specialist_tasks": build_specialist_tasks(impacts, diff_files),
        "conditional_gates": conditional_gates,
    }


def validate_route_impact(payload: Any) -> list[str]:
    """校验最小上下文和四类条件门禁，拒绝未知键或无效依据。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["路由影响快照根节点必须是 object"]
    if payload.get("version") != ROUTE_IMPACT_VERSION:
        errors.append(f"路由影响快照 version 必须为 {ROUTE_IMPACT_VERSION}")
    for field in (
        "requirement_id",
        "requirement_file_sha256",
        "requirement_inputs_sha256",
        "implementation_plan_sha256",
        "impact_radius_sha256",
        "plan_confirmation_receipt_sha256",
        "baseline_id",
        "snapshot_sha256",
        "generated_at",
    ):
        if not isinstance(payload.get(field), str) or not payload[field]:
            errors.append(f"路由影响快照缺少 {field}")
    for field in (
        "requirement_file_sha256",
        "requirement_inputs_sha256",
        "implementation_plan_sha256",
        "impact_radius_sha256",
        "plan_confirmation_receipt_sha256",
        "snapshot_sha256",
    ):
        value = payload.get(field)
        if isinstance(value, str) and value and not re.fullmatch(r"[a-f0-9]{64}", value):
            errors.append(f"路由影响快照 {field} 必须是 SHA-256")
    if not isinstance(payload.get("requirement_revision"), int) or payload["requirement_revision"] < 1:
        errors.append("路由影响快照 requirement_revision 必须是正整数")

    tasks = payload.get("specialist_tasks")
    if not isinstance(tasks, list):
        errors.append("路由影响快照 specialist_tasks 必须是数组")
    else:
        seen_task_ids: set[str] = set()
        for index, task in enumerate(tasks):
            if not isinstance(task, dict) or set(task) != {
                "id", "skill", "gate_id", "required", "status", "basis_files", "reason"
            }:
                errors.append(
                    f"specialist_tasks[{index}] 必须只包含 id、skill、gate_id、required、status、basis_files、reason"
                )
                continue
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id.startswith("TASK-"):
                errors.append(f"specialist_tasks[{index}].id 必须以 TASK- 开头")
            elif task_id in seen_task_ids:
                errors.append(f"specialist_tasks 存在重复 id: {task_id}")
            else:
                seen_task_ids.add(task_id)
            skill = task.get("skill")
            if skill not in ROUTE_SPECIALIST_TASKS:
                errors.append(f"specialist_tasks[{index}].skill 不是允许的专项 Skill")
            elif task.get("gate_id") != ROUTE_SPECIALIST_TASKS[skill]:
                errors.append(f"specialist_tasks[{index}].gate_id 与 skill 不匹配")
            if task.get("required") is not True:
                errors.append(f"specialist_tasks[{index}].required 必须为 true")
            if task.get("status") not in ROUTE_TASK_STATUSES:
                errors.append(f"specialist_tasks[{index}].status 必须为 PENDING")
            basis_files = task.get("basis_files")
            if (
                not isinstance(basis_files, list)
                or not basis_files
                or not all(isinstance(path, str) and path for path in basis_files)
            ):
                errors.append(f"specialist_tasks[{index}].basis_files 必须是非空字符串数组")
            elif len(basis_files) != len(set(basis_files)):
                errors.append(f"specialist_tasks[{index}].basis_files 不得重复")
            if not isinstance(task.get("reason"), str) or not task["reason"].strip():
                errors.append(f"specialist_tasks[{index}].reason 必须说明触发依据")

    gates = payload.get("conditional_gates")
    if not isinstance(gates, list):
        errors.append("路由影响快照 conditional_gates 必须是数组")
        return errors
    seen_gate_ids: set[str] = set()
    for index, item in enumerate(gates):
        if not isinstance(item, dict) or set(item) != {"id", "basis_files"}:
            errors.append(f"conditional_gates[{index}] 必须只包含 id 和 basis_files")
            continue
        gate_id = item.get("id")
        if gate_id not in CONDITIONAL_GATE_IDS.values():
            errors.append(f"conditional_gates[{index}].id 无效")
        elif gate_id in seen_gate_ids:
            errors.append(f"conditional_gates 存在重复 id: {gate_id}")
        else:
            seen_gate_ids.add(gate_id)
        basis_files = item.get("basis_files")
        if not isinstance(basis_files, list) or not basis_files or not all(
            isinstance(path, str) and path for path in basis_files
        ):
            errors.append(f"conditional_gates[{index}].basis_files 必须是非空字符串数组")
        elif len(basis_files) != len(set(basis_files)):
            errors.append(f"conditional_gates[{index}].basis_files 不得重复")
    return errors


def write_route_impact(path: str | Path, payload: dict[str, Any]) -> None:
    """校验后原子写入快照，避免中断留下可被门禁误读的半文件。"""
    errors = validate_route_impact(payload)
    if errors:
        raise RouteImpactError("；".join(errors))
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise RouteImpactError(f"路由影响快照无法写入: {target}: {exc}") from exc


def load_route_impact(path: str | Path) -> dict[str, Any]:
    """读取并校验路由影响快照；调用方再核对它是否属于当前代码。"""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise RouteImpactError(f"尚未生成路由影响快照，请先执行 delivery.py route: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteImpactError(f"路由影响快照无法读取: {target}: {exc}") from exc
    errors = validate_route_impact(payload)
    if errors:
        raise RouteImpactError("；".join(errors))
    return payload
