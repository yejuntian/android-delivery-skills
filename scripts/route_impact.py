#!/usr/bin/env python3
"""脚本名称：route_impact.py

用途：保存和校验最近一次 ``delivery.py route`` 产生的最小条件门禁快照。

核心流程：只保存四类条件门禁及直接依据文件，并绑定当前需求修订、Git 基线和代码
摘要；七类完整影响继续用于当次终端路由，不在机器快照中重复持久化。

职责边界：不读取 Git、不判断业务是否真的适用、不执行 Skill 或测试，也不修改项目。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
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


class RouteImpactError(RuntimeError):
    """表示路由影响快照缺失、损坏或已不属于当前交付上下文。"""


def build_route_impact(
    context: dict[str, Any],
    impacts: dict[str, list[str]],
    conditional_candidates: dict[str, bool | None],
) -> dict[str, Any]:
    """构造稳定快照；只保存候选事实，不把路径命中写成最终业务结论。"""
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
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requirement_id": context["requirement_id"],
        "requirement_revision": context["requirement_revision"],
        "requirement_file_sha256": context["requirement_file_sha256"],
        "baseline_id": context["baseline_id"],
        "snapshot_sha256": context["snapshot_sha256"],
        "conditional_gates": conditional_gates,
    }


def validate_route_impact(payload: Any) -> list[str]:
    """校验最小上下文和四类条件门禁，拒绝未知键或无效依据。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["路由影响快照根节点必须是 object"]
    if payload.get("version") != 1:
        errors.append("路由影响快照 version 必须为 1")
    for field in (
        "requirement_id",
        "requirement_file_sha256",
        "baseline_id",
        "snapshot_sha256",
        "generated_at",
    ):
        if not isinstance(payload.get(field), str) or not payload[field]:
            errors.append(f"路由影响快照缺少 {field}")
    if not isinstance(payload.get("requirement_revision"), int) or payload["requirement_revision"] < 1:
        errors.append("路由影响快照 requirement_revision 必须是正整数")

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
