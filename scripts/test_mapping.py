#!/usr/bin/env python3
"""脚本名称：test_mapping.py

用途：维护需求义务到测试用例的结构化绑定，堵住“需求增量但测试不更新”的脑补。

核心流程：每个已确认原子义务登记它所验证的义务语义摘要（obligation_sha256）和
测试用例 id；需求修订推进时，脚本把义务 sha256 已变化的登记标记为 STALE；最终
门禁要求 COVERED_AUTOMATED 义务的映射必须为 CURRENT，且 test_ids 与执行收据一致。

职责边界：只校验与维护映射结构，不执行测试、不读取测试代码、不修改需求正文或
Android 代码。义务语义摘要始终来自 requirement_snapshot，本脚本不自行计算语义。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


MAPPING_VERSION = 1
OBLIGATION_ID_PATTERN = "BDD-[0-9]+/T[0-9]+"
MAPPING_STATUSES = {"CURRENT", "STALE"}


class TestMappingError(RuntimeError):
    """表示测试映射缺失、损坏或与当前需求修订不一致。"""


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """以 0600 权限原子写入映射，中断时保留上一份完整记录。"""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise TestMappingError(f"测试映射无法写入: {target}: {exc}") from exc


def _validate_entry(item: Any, index: int) -> dict[str, Any]:
    """校验单个义务测试登记，保留 obligation_sha256 用于需求增量联动。"""
    label = f"mappings[{index}]"
    if not isinstance(item, dict):
        raise TestMappingError(f"{label} 必须是 object")
    import re

    identifier = item.get("obligation_id")
    if not isinstance(identifier, str) or not re.fullmatch(OBLIGATION_ID_PATTERN, identifier):
        raise TestMappingError(f"{label}.obligation_id 必须符合 BDD-###/T#")
    obligation_sha256 = item.get("obligation_sha256")
    # 跳过标记 STALE 的登记：旧摘要可能来自上一修订，不为当前 sha256，属正常待回填状态。
    is_stale = item.get("mapping_status") == "STALE"
    if not is_stale:
        if not isinstance(obligation_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", obligation_sha256):
            raise TestMappingError(f"{label}.obligation_sha256 必须是有效 SHA-256")
    test_ids = item.get("test_ids")
    if not isinstance(test_ids, list) or not all(
        isinstance(case, str) and case.strip() for case in test_ids
    ):
        raise TestMappingError(f"{label}.test_ids 必须是字符串数组")
    if not test_ids:
        if not isinstance(item.get("manual_reason"), str) or not item["manual_reason"].strip():
            raise TestMappingError(f"{label} 无自动测试时必须说明 manual_reason")
    elif len(test_ids) != len(set(test_ids)):
        raise TestMappingError(f"{label}.test_ids 不得重复")
    status = item.get("mapping_status")
    if status not in MAPPING_STATUSES:
        raise TestMappingError(f"{label}.mapping_status 必须是 CURRENT 或 STALE")
    architecture_tests = item.get("architecture_tests")
    if architecture_tests is not None:
        if not isinstance(architecture_tests, list) or not all(
            isinstance(rule, str) and rule.strip() for rule in architecture_tests
        ):
            raise TestMappingError(f"{label}.architecture_tests 必须是字符串数组")
        if len(architecture_tests) != len(set(architecture_tests)):
            raise TestMappingError(f"{label}.architecture_tests 不得重复")
    return {
        "obligation_id": identifier,
        "obligation_sha256": obligation_sha256 if isinstance(obligation_sha256, str) else None,
        "test_ids": list(test_ids),
        "mapping_status": status,
        "manual_reason": item.get("manual_reason") if isinstance(item.get("manual_reason"), str) else None,
        "architecture_tests": [rule for rule in architecture_tests if isinstance(rule, str) and rule.strip()]
        if isinstance(architecture_tests, list) else [],
    }


def validate_test_mapping(
    payload: Any,
    snapshot: dict[str, Any],
) -> list[str]:
    """校验映射覆盖全部当前义务，且没有登记已删除义务。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["测试映射根节点必须是 object"]
    if payload.get("version") != MAPPING_VERSION:
        errors.append(f"测试映射 version 必须为 {MAPPING_VERSION}")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        errors.append("测试映射 mappings 必须是非空数组")
        return errors
    try:
        mappings = [_validate_entry(item, index) for index, item in enumerate(raw_mappings)]
    except TestMappingError as exc:
        errors.append(str(exc))
        return errors
    expected_ids = {item["id"] for item in snapshot.get("obligations", [])}
    expected_sha: dict[str, str] = {
        item["id"]: item["sha256"] for item in snapshot.get("obligations", [])
    }
    seen: set[str] = set()
    for entry in mappings:
        identifier = entry["obligation_id"]
        if identifier in seen:
            errors.append(f"测试映射存在重复义务登记: {identifier}")
            continue
        seen.add(identifier)
        if identifier not in expected_ids:
            errors.append(f"测试映射登记了已删除或非当前的义务: {identifier}")
            continue
        current_sha = expected_sha.get(identifier)
        if entry["mapping_status"] == "STALE" and entry.get("obligation_sha256") == current_sha:
            # 映射声明 STALE 但 sha256 已与当前修订一致，说明 AI 误标，需回填 CURRENT。
            errors.append(f"义务 {identifier} 的测试映射已对齐当前需求但仍标记 STALE")
        if entry["mapping_status"] == "CURRENT" and entry.get("obligation_sha256") != current_sha:
            # 映射声明 CURRENT 但 sha256 与当前修订不符，说明 AI 没有真正同步测试。
            errors.append(
                f"义务 {identifier} 的测试映射声明 CURRENT 但未绑定当前需求语义摘要"
            )
    missing = sorted(expected_ids - seen)
    if missing:
        errors.append("测试映射缺少当前确认义务的登记: " + ", ".join(missing))
    return errors


def build_initial_mapping(snapshot: dict[str, Any]) -> dict[str, Any]:
    """为在途需求生成骨架；已确认义务默认 STALE，由 AI 填测试后回填 CURRENT。"""
    return {
        "version": MAPPING_VERSION,
        "mappings": [
            {
                "obligation_id": item["id"],
                "obligation_sha256": item["sha256"],
                "test_ids": [],
                "mapping_status": "STALE",
                "manual_reason": "在途需求尚未登记测试用例",
            }
            for item in snapshot.get("obligations", [])
        ],
    }


def mark_stale_after_revision(
    mapping_path: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """需求修订推进后，把义务 sha256 已变化的登记置为 STALE，其余保持不动。"""
    resolved = Path(mapping_path).expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TestMappingError(f"测试映射无法读取: {resolved}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("mappings"), list):
        raise TestMappingError(f"测试映射损坏: {resolved}")
    expected_sha = {
        item["id"]: item["sha256"] for item in snapshot.get("obligations", [])
    }
    updated = False
    for entry in payload["mappings"]:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("obligation_id")
        current_sha = expected_sha.get(identifier)
        if current_sha is None:
            continue
        if entry.get("obligation_sha256") != current_sha:
            # 义务语义已变化：强制刷新声明的摘要并标记待重新登记测试。
            entry["obligation_sha256"] = current_sha
            entry["mapping_status"] = "STALE"
            updated = True
    payload["version"] = MAPPING_VERSION
    if updated:
        _atomic_write(resolved, payload)
    return payload


def load_test_mapping(path: Path) -> dict[str, Any]:
    """读取测试映射；文件缺失或损坏时抛错，不静默跳过机器门禁。"""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise TestMappingError(f"尚未生成测试映射，请先执行 delivery.py init-test-mapping: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TestMappingError(f"测试映射无法读取: {resolved}: {exc}") from exc
    return payload
