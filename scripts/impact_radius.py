#!/usr/bin/env python3
"""脚本名称：impact_radius.py

用途：校验需求增量后的机器可读影响半径，并判断最终 diff 是否越过已确认范围。

核心流程：读取 ``test-cases/impact-radius.json``，绑定当前需求修订、需求正文摘要和
原子义务摘要；要求最新一轮非 UNCHANGED 义务都有影响记录；最终门禁用 allowed_files
与 allowed_globs 检查基线后的代码文件是否都在已确认范围内。

职责边界：只校验 AI 已物化并经计划确认绑定的影响半径，不推断业务、不读取 Git、
不自动扩展范围、不修改 Android 项目。
"""

from __future__ import annotations

from datetime import datetime
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from .requirement_snapshot import requirement_digest, requirement_summary_digest


IMPACT_RADIUS_VERSION = 1
IMPACT_RADIUS_RELATIVE_PATH = Path("test-cases") / "impact-radius.json"
IMPACT_CHANGE_TYPES = {"ADDED", "CHANGED", "REMOVED", "SUPERSEDED"}
RISK_LEVELS = {"L1", "L2", "L3", "BLOCKED"}


class ImpactRadiusError(RuntimeError):
    """表示影响半径文件缺失、损坏或与当前需求修订不一致。"""


def impact_radius_path(requirement_dir: str | Path) -> Path:
    """返回当前需求固定影响半径路径。"""
    return (Path(requirement_dir).expanduser().resolve() / IMPACT_RADIUS_RELATIVE_PATH).resolve()


def impact_radius_digest(payload: dict[str, Any]) -> str:
    """对影响半径 JSON 做稳定摘要，供计划收据和 route/final 绑定。"""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_text(value: Any, label: str, errors: list[str]) -> str:
    """读取非空字符串字段；错误时返回空串便于继续收集其他问题。"""
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} 必须是非空字符串")
        return ""
    return value.strip()


def _string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    """读取字符串数组并拒绝空值和重复项。"""
    if not isinstance(value, list):
        errors.append(f"{label} 必须是字符串数组")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] 必须是非空字符串")
            continue
        result.append(item.strip().replace("\\", "/"))
    duplicates = sorted({item for item in result if result.count(item) > 1})
    if duplicates:
        errors.append(f"{label} 不得重复: {', '.join(duplicates)}")
    return result


def _repo_path_list(value: Any, label: str, errors: list[str]) -> list[str]:
    """读取 Git 仓库相对路径数组，禁止绝对路径、上跳和 .git。"""
    result = _string_list(value, label, errors)
    for item in result:
        path = Path(item)
        if path.is_absolute() or item.startswith("../") or "/../" in item or item == "..":
            errors.append(f"{label} 只能使用仓库相对路径: {item}")
        if item.startswith(".git/") or item == ".git":
            errors.append(f"{label} 不得指向 .git: {item}")
    return result


def _latest_semantic_changes(snapshot: dict[str, Any]) -> dict[str, str]:
    """返回当前修订最近一轮已确认的语义变化，作为影响半径必须覆盖的集合。"""
    history = snapshot.get("history") or []
    if not history:
        return {}
    latest = history[-1]
    changes = latest.get("changes") if isinstance(latest, dict) else None
    if not isinstance(changes, list):
        return {}
    semantic: dict[str, str] = {}
    for item in changes:
        if not isinstance(item, dict):
            continue
        if item.get("decision") != "CONFIRMED":
            continue
        change_type = item.get("change_type")
        identifier = item.get("id")
        if change_type in IMPACT_CHANGE_TYPES and isinstance(identifier, str):
            semantic[identifier] = change_type
    return semantic


def _validate_impact_item(
    item: Any,
    index: int,
    allowed_files: set[str],
    allowed_globs: list[str],
    expected_changes: dict[str, str],
    errors: list[str],
) -> dict[str, Any] | None:
    """校验单个义务影响项，并确认文件范围没有绕过 allowed 列表。"""
    label = f"impacts[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{label} 必须是 object")
        return None
    allowed_keys = {
        "id",
        "change_type",
        "reason",
        "risk_level",
        "expected_files",
        "expected_tests",
        "affected_modules",
        "no_code_change_reason",
    }
    extra = sorted(set(item) - allowed_keys)
    if extra:
        errors.append(f"{label} 包含未知字段: {', '.join(extra)}")
    identifier = _require_text(item.get("id"), f"{label}.id", errors)
    change_type = item.get("change_type")
    if change_type not in IMPACT_CHANGE_TYPES:
        errors.append(f"{label}.change_type 必须是 {sorted(IMPACT_CHANGE_TYPES)}")
    elif identifier and expected_changes.get(identifier) != change_type:
        errors.append(f"{label} 与最近需求修订类型不一致: {identifier}")
    risk_level = item.get("risk_level")
    if risk_level not in RISK_LEVELS:
        errors.append(f"{label}.risk_level 必须是 {sorted(RISK_LEVELS)}")
    _require_text(item.get("reason"), f"{label}.reason", errors)
    expected_files = _repo_path_list(item.get("expected_files"), f"{label}.expected_files", errors)
    _string_list(item.get("expected_tests"), f"{label}.expected_tests", errors)
    _string_list(item.get("affected_modules"), f"{label}.affected_modules", errors)
    if not expected_files and not isinstance(item.get("no_code_change_reason"), str):
        errors.append(f"{label} 无 expected_files 时必须说明 no_code_change_reason")
    for path in expected_files:
        if path in allowed_files or any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed_globs):
            continue
        errors.append(f"{label}.expected_files 未纳入 allowed_files/allowed_globs: {path}")
    return item if identifier else None


def validate_impact_radius(
    payload: Any,
    snapshot: dict[str, Any],
    requirement_content: str,
) -> list[str]:
    """校验影响半径是否绑定当前需求修订，并覆盖最近一轮语义变化。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["影响半径根节点必须是 object"]
    allowed_keys = {
        "version",
        "generated_at",
        "requirement_id",
        "requirement_revision",
        "requirement_file_sha256",
        "requirement_summary_sha256",
        "allowed_files",
        "allowed_globs",
        "impacts",
        "no_code_change_reason",
    }
    extra = sorted(set(payload) - allowed_keys)
    if extra:
        errors.append("影响半径包含未知字段: " + ", ".join(extra))
    if payload.get("version") != IMPACT_RADIUS_VERSION:
        errors.append(f"影响半径 version 必须为 {IMPACT_RADIUS_VERSION}")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        errors.append("影响半径缺少 generated_at")
    else:
        try:
            datetime.fromisoformat(generated_at)
        except ValueError:
            errors.append("影响半径 generated_at 必须是 ISO 时间")
    if payload.get("requirement_id") != snapshot.get("requirement_id"):
        errors.append("影响半径 requirement_id 与当前需求不一致")
    if payload.get("requirement_revision") != snapshot.get("revision"):
        errors.append("影响半径 requirement_revision 与当前需求修订不一致")
    expected_requirement_sha = requirement_digest(requirement_content)
    if payload.get("requirement_file_sha256") != expected_requirement_sha:
        errors.append("影响半径 requirement_file_sha256 已失效")
    expected_summary_sha = requirement_summary_digest(snapshot)
    if payload.get("requirement_summary_sha256") != expected_summary_sha:
        errors.append("影响半径 requirement_summary_sha256 已失效")

    allowed_files = set(_repo_path_list(payload.get("allowed_files"), "allowed_files", errors))
    allowed_globs = _repo_path_list(payload.get("allowed_globs"), "allowed_globs", errors)
    if not allowed_files and not allowed_globs and not isinstance(payload.get("no_code_change_reason"), str):
        errors.append("影响半径没有允许文件时必须说明 no_code_change_reason")

    expected_changes = _latest_semantic_changes(snapshot)
    impacts = payload.get("impacts")
    if not isinstance(impacts, list) or not impacts:
        errors.append("影响半径 impacts 必须是非空数组")
        impacts = []
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(impacts):
        normalized = _validate_impact_item(
            item,
            index,
            allowed_files,
            allowed_globs,
            expected_changes,
            errors,
        )
        if normalized is None:
            continue
        identifier = str(normalized["id"])
        if identifier in indexed:
            errors.append(f"影响半径 impacts 存在重复 id: {identifier}")
        indexed[identifier] = normalized
    if expected_changes:
        actual_ids = set(indexed)
        expected_ids = set(expected_changes)
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        if missing:
            errors.append("影响半径漏掉本轮语义变化: " + ", ".join(missing))
        if unexpected:
            errors.append("影响半径包含非本轮语义变化: " + ", ".join(unexpected))
    return errors


def load_impact_radius(
    path: str | Path,
    snapshot: dict[str, Any],
    requirement_content: str,
) -> dict[str, Any]:
    """读取并校验影响半径文件。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ImpactRadiusError(f"尚未生成影响半径，请先填写 test-cases/impact-radius.json: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ImpactRadiusError(f"影响半径无法读取: {source}: {exc}") from exc
    errors = validate_impact_radius(payload, snapshot, requirement_content)
    if errors:
        raise ImpactRadiusError("；".join(errors))
    return payload


def path_allowed_by_radius(path: str, payload: dict[str, Any]) -> bool:
    """判断一个仓库相对路径是否落在影响半径允许范围内。"""
    normalized = path.replace("\\", "/")
    allowed_files = set(payload.get("allowed_files") or [])
    if normalized in allowed_files:
        return True
    return any(
        fnmatch.fnmatchcase(normalized, pattern)
        for pattern in payload.get("allowed_globs") or []
    )


def changed_files_outside_radius(
    changed_files: list[str],
    payload: dict[str, Any],
) -> list[str]:
    """返回超出影响半径的最终 diff 文件列表。"""
    return sorted(
        path.replace("\\", "/")
        for path in changed_files
        if not path_allowed_by_radius(path, payload)
    )
