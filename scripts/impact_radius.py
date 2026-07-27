#!/usr/bin/env python3
"""脚本名称：impact_radius.py

用途：校验需求增量后的机器可读影响半径，并判断最终 diff 是否越过已确认范围。

核心流程：读取 ``test-cases/impact-radius.json``，绑定当前需求修订、需求正文摘要和
原子义务摘要；要求最新一轮非 UNCHANGED 义务都有影响记录；最终门禁用 allowed_files
（精确路径）与 allowed_dirs（目录前缀，/ 结尾）检查基线后的代码文件是否都在
已确认范围内。两套语义均确定性强匹配，不允许通配符（``*`` ``?``），
避免 ``**/*.kt`` 这类无锚点通配放行整个仓库使门禁失效。

职责边界：只校验 AI 已物化并经计划确认绑定的影响半径，不推断业务、不读取 Git、
不自动扩展范围、不修改 Android 项目。
"""

from __future__ import annotations

from datetime import datetime
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


def _allowed_dirs(value: Any, errors: list[str]) -> list[str]:
    """读取并校验 allowed_dirs：必须是 ``/`` 结尾、无通配符、无上跳的目录前缀。

    弃用 fnmatch 通配后，allowed_dirs 用目录前缀（startswith）放行目录下全部文件。
    强制 ``/`` 结尾消除歧义（``src`` 会同时放行 ``src_new``），禁止 ``*`` ``?``
    防止误把通配符当字面量或残留旧 ``allowed_globs`` 习惯。
    """
    label = "allowed_dirs"
    raw = _string_list(value, label, errors)
    result: list[str] = []
    for item in raw:
        path = Path(item)
        if path.is_absolute() or item.startswith("../") or "/../" in item or item == "..":
            errors.append(f"{label} 只能使用仓库相对路径: {item}")
        if item.startswith(".git/") or item == ".git":
            errors.append(f"{label} 不得指向 .git: {item}")
        if any(ch in item for ch in "*?["):
            errors.append(f"{label} 不得包含通配符，请改用具体目录前缀: {item}")
        if not item.endswith("/"):
            errors.append(f"{label} 必须以 / 结尾表示目录前缀: {item}")
        result.append(item)
    return result


def _confirmed_semantic_changes(snapshot: dict[str, Any]) -> dict[str, str]:
    """返回当前需求基线以来的已确认语义变化，作为累计影响半径覆盖集合。"""
    history = snapshot.get("history") or []
    semantic: dict[str, str] = {}
    for revision in history:
        changes = revision.get("changes") if isinstance(revision, dict) else None
        if not isinstance(changes, list):
            continue
        for item in changes:
            if not isinstance(item, dict):
                continue
            if item.get("decision") != "CONFIRMED":
                continue
            change_type = item.get("change_type")
            identifier = item.get("id")
            if change_type in IMPACT_CHANGE_TYPES and isinstance(identifier, str):
                # 同一义务多次变化时以最近一次语义变化类型为准。
                semantic[identifier] = change_type
    return semantic


def _latest_semantic_changes(snapshot: dict[str, Any]) -> dict[str, str]:
    """兼容旧调用名；当前影响半径按需求基线以来的累计语义变化校验。"""
    return _confirmed_semantic_changes(snapshot)


def _expected_paths_from_impacts(impacts: Any) -> set[str]:
    """提取每个 impact 明确解释的文件或目录前缀。"""
    expected: set[str] = set()
    if not isinstance(impacts, list):
        return expected
    for item in impacts:
        if not isinstance(item, dict):
            continue
        for path in item.get("expected_files") or []:
            if isinstance(path, str) and path.strip():
                expected.add(path.strip().replace("\\", "/"))
    return expected


def _path_explained_by_expected(path: str, expected_paths: set[str]) -> bool:
    """确认路径是否被某个 impact.expected_files 精确解释或目录前缀解释。"""
    normalized = path.replace("\\", "/")
    if normalized in expected_paths:
        return True
    return any(
        expected.endswith("/") and normalized.startswith(expected)
        for expected in expected_paths
    )


def _validate_impact_item(
    item: Any,
    index: int,
    allowed_files: set[str],
    allowed_dirs: list[str],
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
        normalized = path.replace("\\", "/")
        if normalized in allowed_files or any(normalized.startswith(d) for d in allowed_dirs):
            continue
        errors.append(f"{label}.expected_files 未纳入 allowed_files/allowed_dirs: {path}")
    normalized_item = dict(item)
    normalized_item["expected_files"] = expected_files
    return normalized_item if identifier else None


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
        "allowed_dirs",
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
    allowed_dirs = _allowed_dirs(payload.get("allowed_dirs"), errors)
    if not allowed_files and not allowed_dirs and not isinstance(payload.get("no_code_change_reason"), str):
        errors.append("影响半径没有允许文件时必须说明 no_code_change_reason")

    expected_changes = _confirmed_semantic_changes(snapshot)
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
            allowed_dirs,
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
            errors.append(
                "影响半径漏掉本轮语义变化（当前累计半径必须覆盖所有已确认语义变化）: "
                + ", ".join(missing)
            )
        if unexpected:
            errors.append("影响半径包含非当前累计语义变化: " + ", ".join(unexpected))
    expected_paths = _expected_paths_from_impacts(list(indexed.values()))
    unexplained_files = sorted(
        path for path in allowed_files
        if not _path_explained_by_expected(path, expected_paths)
    )
    if unexplained_files:
        errors.append(
            "allowed_files 存在未被任何 impacts.expected_files 解释的路径: "
            + ", ".join(unexplained_files)
        )
    unexplained_dirs = sorted(
        directory for directory in allowed_dirs
        if not any(
            expected == directory or expected.startswith(directory)
            for expected in expected_paths
        )
    )
    if unexplained_dirs:
        errors.append(
            "allowed_dirs 存在未被任何 impacts.expected_files 解释的目录前缀: "
            + ", ".join(unexplained_dirs)
        )
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
    """判断一个仓库相对路径是否落在影响半径允许范围内。

    匹配语义只有两种，均确定性、无通配歧义：
    - allowed_files：精确路径命中。
    - allowed_dirs：目录前缀匹配（必须是 ``/`` 结尾的目录，放行其下所有文件）。
    弃用 fnmatch 通配符：``**/*.kt`` 这类无锚点通配会放行整个仓库任意 .kt，
    让"防越界"门禁失效。
    """
    normalized = path.replace("\\", "/")
    allowed = normalized in set(payload.get("allowed_files") or []) or any(
        normalized.startswith(directory)
        for directory in payload.get("allowed_dirs") or []
    )
    if not allowed:
        return False
    expected_paths = _expected_paths_from_impacts(payload.get("impacts") or [])
    return not expected_paths or _path_explained_by_expected(normalized, expected_paths)


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
