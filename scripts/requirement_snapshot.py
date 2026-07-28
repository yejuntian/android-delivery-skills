#!/usr/bin/env python3
"""脚本名称：requirement_snapshot.py

用途：保存已确认需求修订、原子验证义务，并生成中途需求变化的确定性文本差异。

职责边界：只管理需求修订文件，不读取 Word、不判断业务语义、不修改 Git，也不执行
测试。AI 负责把用户确认结果写成修订清单；本模块只校验修订连续性并原子持久化。
"""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .atomic_write import write_json_atomic
from .bdd_scenarios import (
    BddScenarioError,
    bdd_ids_in_text,
    extract_bdd_scenarios,
    is_bdd_atom_id,
    is_bdd_id,
    non_bdd_content,
    validate_requirement_readiness,
)


SNAPSHOT_VERSION = 2
MANIFEST_VERSION = 1
CHANGE_TYPES = {"ADDED", "CHANGED", "REMOVED", "UNCHANGED", "SUPERSEDED"}
DECISIONS = {"CONFIRMED", "PENDING", "REJECTED", "CONFLICT"}
REMOVAL_DISPOSITIONS = {
    "REMOVE_IMPLEMENTATION",
    "KEEP_COMPATIBILITY",
    "STOP_UNFINISHED_WORK",
}
UNRESOLVED_DECISIONS = {"PENDING", "CONFLICT"}


class RequirementSnapshotError(RuntimeError):
    """表示需求快照或修订清单损坏、冲突或无法安全读写。"""


def requirement_digest(content: str) -> str:
    """对规范化 UTF-8 正文计算摘要，忽略换行格式和首尾空白差异。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def obligation_digest(
    identifier: str,
    text: str,
    required: bool,
    atoms: list[dict[str, str]] | None = None,
) -> str:
    """计算场景及结构化验收项摘要，使原子结果变化自动失效。"""
    normalized = {
        "id": identifier,
        "text": text.replace("\r\n", "\n").replace("\r", "\n").strip(),
        "required": required,
    }
    if atoms:
        normalized["atoms"] = [
            {
                "id": atom["id"],
                "key": atom["key"],
                "text": atom["text"].strip(),
            }
            for atom in atoms
        ]
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def requirement_summary_digest(snapshot: dict[str, Any]) -> str:
    """摘要当前有效原子义务，供计划和影响半径共同绑定需求语义。"""
    summary = {
        "requirement_id": snapshot.get("requirement_id"),
        "requirement_revision": snapshot.get("revision"),
        "obligations": [
            {
                "id": item.get("id"),
                "text": item.get("text"),
                "required": item.get("required"),
                "sha256": item.get("sha256"),
                "atoms": item.get("atoms") or [],
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


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """代理到公共原子写；统一行为与 0600 权限。"""
    from .atomic_write import write_json_atomic
    try:
        write_json_atomic(path, payload)
    except OSError as exc:
        raise RequirementSnapshotError(
            f"无法写入需求快照: {Path(path).resolve()}: {exc}"
        ) from exc


def _new_snapshot(
    requirement_path: Path,
    content: str,
    requirement_id: str | None,
) -> dict[str, Any]:
    """建立尚待确认 BDD 场景的初始修订，Git 基线 ID 优先作为需求集合 ID。"""
    now = datetime.now(timezone.utc).isoformat()
    digest = requirement_digest(content)
    return {
        "version": SNAPSHOT_VERSION,
        "requirement_id": requirement_id or f"REQSET-{digest[:16]}",
        "requirement_path": str(Path(requirement_path).expanduser().resolve()),
        "initial_sha256": digest,
        "initial_content": content.strip(),
        "sha256": digest,
        "content": content.strip(),
        "created_at": now,
        "confirmed_at": now,
        "revision": 0,
        "status": "AWAITING_OBLIGATIONS",
        "obligations": [],
        "pending_changes": [],
        "proposed_sha256": None,
        "history": [],
    }


def write_requirement_snapshot(
    path: Path,
    requirement_path: Path,
    content: str,
    *,
    requirement_id: str | None = None,
) -> dict[str, Any]:
    """原子写入当前需求起点；修订确认不会修改与它配对的 Git 基线。"""
    payload = _new_snapshot(requirement_path, content, requirement_id)
    _atomic_write(path, payload)
    return payload


def _upgrade_v1(payload: dict[str, Any]) -> dict[str, Any]:
    """把旧版单快照映射为待补义务的 v2 视图，避免升级后丢失正在执行的需求。"""
    digest = str(payload["sha256"])
    return {
        "version": SNAPSHOT_VERSION,
        "requirement_id": f"REQSET-{digest[:16]}",
        "requirement_path": payload["requirement_path"],
        "initial_sha256": digest,
        "initial_content": payload["content"],
        "sha256": digest,
        "content": payload["content"],
        "created_at": payload["created_at"],
        "confirmed_at": payload["created_at"],
        "revision": 0,
        "status": "AWAITING_OBLIGATIONS",
        "obligations": [],
        "pending_changes": [],
        "proposed_sha256": None,
        "history": [],
    }


def _validate_obligation(item: Any, label: str) -> dict[str, Any]:
    """校验一个 BDD 场景及其结构化验收项，补充稳定语义摘要。"""
    if not isinstance(item, dict):
        raise RequirementSnapshotError(f"{label} 必须是 object")
    identifier = item.get("id")
    text = item.get("text")
    required = item.get("required")
    if not is_bdd_id(identifier):
        raise RequirementSnapshotError(f"{label}.id 必须符合 BDD-###")
    if not isinstance(text, str) or not text.strip():
        raise RequirementSnapshotError(f"{label}.text 必须是非空 BDD 场景描述")
    if not isinstance(required, bool):
        raise RequirementSnapshotError(f"{label}.required 必须是 boolean")
    normalized = {"id": identifier, "text": text.strip(), "required": required}
    atoms = item.get("atoms")
    if atoms is not None:
        if not isinstance(atoms, list) or not atoms:
            raise RequirementSnapshotError(f"{label}.atoms 必须是非空数组")
        normalized_atoms: list[dict[str, str]] = []
        seen_atom_ids: set[str] = set()
        for atom_index, atom in enumerate(atoms):
            atom_label = f"{label}.atoms[{atom_index}]"
            if not isinstance(atom, dict):
                raise RequirementSnapshotError(f"{atom_label} 必须是 object")
            atom_id = atom.get("id")
            key = atom.get("key")
            atom_text = atom.get("text")
            if not is_bdd_atom_id(atom_id, scenario_id=identifier):
                raise RequirementSnapshotError(
                    f"{atom_label}.id 必须符合 {identifier}.key"
                )
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", key):
                raise RequirementSnapshotError(f"{atom_label}.key 格式无效")
            if not isinstance(atom_text, str) or not atom_text.strip():
                raise RequirementSnapshotError(f"{atom_label}.text 必须是非空字符串")
            if atom_id in seen_atom_ids:
                raise RequirementSnapshotError(f"{label}.atoms 存在重复 id: {atom_id}")
            seen_atom_ids.add(atom_id)
            normalized_atoms.append({
                "id": atom_id,
                "key": key,
                "text": atom_text.strip(),
            })
        normalized["atoms"] = normalized_atoms
    normalized["sha256"] = obligation_digest(
        identifier,
        normalized["text"],
        required,
        normalized.get("atoms"),
    )
    return normalized


def _validate_snapshot(payload: Any, source: Path) -> dict[str, Any]:
    """校验 v2 快照的核心字段和义务摘要，拒绝损坏状态继续传播。"""
    if not isinstance(payload, dict):
        raise RequirementSnapshotError(f"需求快照格式无效: {source}")
    if payload.get("version") == 1:
        required_v1 = {"requirement_path", "sha256", "content", "created_at"}
        if not required_v1.issubset(payload):
            raise RequirementSnapshotError(f"需求快照格式无效: {source}")
        payload = _upgrade_v1(payload)
    required = {
        "version", "requirement_id", "requirement_path", "initial_sha256",
        "initial_content", "sha256", "content", "created_at", "confirmed_at",
        "revision", "status", "obligations", "pending_changes", "history",
    }
    if payload.get("version") != SNAPSHOT_VERSION or not required.issubset(payload):
        raise RequirementSnapshotError(f"需求快照版本或字段无效: {source}")
    string_fields = (
        "requirement_id", "requirement_path", "initial_sha256", "initial_content",
        "sha256", "content", "created_at", "confirmed_at", "status",
    )
    if any(not isinstance(payload[field], str) for field in string_fields):
        raise RequirementSnapshotError(f"需求快照字段类型无效: {source}")
    if not payload["requirement_id"].strip():
        raise RequirementSnapshotError(f"需求快照 requirement_id 无效: {source}")
    if not isinstance(payload["revision"], int) or payload["revision"] < 0:
        raise RequirementSnapshotError(f"需求快照 revision 无效: {source}")
    if payload["status"] not in {"AWAITING_OBLIGATIONS", "PENDING_CONFIRMATION", "CONFIRMED"}:
        raise RequirementSnapshotError(f"需求快照 status 无效: {source}")
    if payload["sha256"] != requirement_digest(str(payload["content"])):
        raise RequirementSnapshotError(f"需求快照当前正文摘要不匹配: {source}")
    if payload["initial_sha256"] != requirement_digest(str(payload["initial_content"])):
        raise RequirementSnapshotError(f"需求快照初始正文摘要不匹配: {source}")
    if (
        not isinstance(payload["obligations"], list)
        or not isinstance(payload["pending_changes"], list)
        or not isinstance(payload["history"], list)
    ):
        raise RequirementSnapshotError(f"需求快照修订记录格式无效: {source}")
    obligations = [_validate_obligation(item, f"obligations[{index}]")
                   for index, item in enumerate(payload["obligations"])]
    identifiers = [item["id"] for item in obligations]
    if len(identifiers) != len(set(identifiers)):
        raise RequirementSnapshotError(f"需求快照存在重复 obligation id: {source}")
    payload = dict(payload)
    payload["obligations"] = obligations
    payload.setdefault("proposed_sha256", None)
    return payload


def load_requirement_snapshot(path: Path) -> dict[str, Any] | None:
    """读取并校验需求修订；文件尚未建立时返回 None，旧版自动兼容为 v2 视图。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RequirementSnapshotError(f"需求快照无法读取: {source}: {exc}") from exc
    return _validate_snapshot(payload, source)


def load_revision_manifest(path: Path) -> dict[str, Any]:
    """读取 AI 物化且用户已审阅的需求修订清单，业务字段由后续函数严格校验。"""
    source = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RequirementSnapshotError(f"需求修订清单无法读取: {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RequirementSnapshotError(f"需求修订清单根节点必须是 object: {source}")
    return payload


def build_confirmed_revision_manifest(
    snapshot: dict[str, Any],
    content: str,
) -> dict[str, Any]:
    """Build the routine confirmed manifest; deletions still require explicit disposition."""
    try:
        scenarios = validate_requirement_readiness(content)
    except BddScenarioError as exc:
        raise RequirementSnapshotError(str(exc)) from exc
    previous = {item["id"]: item for item in snapshot.get("obligations", [])}
    current_ids = {item["id"] for item in scenarios}
    removed = sorted(set(previous) - current_ids)
    if removed:
        raise RequirementSnapshotError(
            "检测到已确认 BDD 场景被删除或改号: "
            + ", ".join(removed)
            + "；请使用 --revision-file 明确删除处置或替代关系"
        )

    changes: list[dict[str, Any]] = []
    for scenario in scenarios:
        identifier = scenario["id"]
        text = scenario["text"]
        old = previous.get(identifier)
        if old is None:
            change = {
                "id": identifier,
                "change_type": "ADDED",
                "decision": "CONFIRMED",
                "text": text,
                "required": True,
            }
            if scenario.get("atoms"):
                change["atoms"] = scenario["atoms"]
            changes.append(change)
        elif obligation_digest(identifier, text, True, scenario.get("atoms")) != old.get("sha256"):
            change = {
                "id": identifier,
                "change_type": "CHANGED",
                "decision": "CONFIRMED",
                "text": text,
                "required": True,
            }
            if scenario.get("atoms"):
                change["atoms"] = scenario["atoms"]
            changes.append(change)
        else:
            changes.append({
                "id": identifier,
                "change_type": "UNCHANGED",
                "decision": "CONFIRMED",
            })

    return {
        "version": MANIFEST_VERSION,
        "requirement_id": snapshot["requirement_id"],
        "base_revision": snapshot["revision"],
        "scope": "SAME_REQUIREMENT",
        "document_changed": (
            requirement_digest(non_bdd_content(content))
            != requirement_digest(non_bdd_content(str(snapshot.get("content", ""))))
        ),
        "changes": changes,
    }


def write_revision_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Persist a generated revision manifest atomically."""
    try:
        write_json_atomic(path, manifest)
    except OSError as exc:
        raise RequirementSnapshotError(
            f"无法写入需求修订清单: {Path(path).resolve()}: {exc}"
        ) from exc


def _normalize_change(item: Any, index: int) -> dict[str, Any]:
    """校验单项增改删决策，保留恢复和删除处置所需的最小字段。"""
    label = f"changes[{index}]"
    if not isinstance(item, dict):
        raise RequirementSnapshotError(f"{label} 必须是 object")
    identifier = item.get("id")
    change_type = item.get("change_type")
    decision = item.get("decision")
    if not is_bdd_id(identifier):
        raise RequirementSnapshotError(f"{label}.id 必须符合 BDD-###")
    if change_type not in CHANGE_TYPES:
        raise RequirementSnapshotError(f"{label}.change_type 无效")
    if decision not in DECISIONS:
        raise RequirementSnapshotError(f"{label}.decision 无效")
    normalized: dict[str, Any] = {
        "id": identifier,
        "change_type": change_type,
        "decision": decision,
    }
    for field in ("text", "disposition", "replacement_id", "reason", "atoms"):
        if field in item:
            normalized[field] = item[field]
    if "required" in item:
        normalized["required"] = item["required"]
    if change_type in {"ADDED", "CHANGED"}:
        validated = _validate_obligation(
            {
                "id": identifier,
                "text": item.get("text"),
                "required": item.get("required"),
                "atoms": item.get("atoms"),
            },
            label,
        )
        if "atoms" in validated:
            normalized["atoms"] = validated["atoms"]
    if decision in {"PENDING", "REJECTED", "CONFLICT"}:
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise RequirementSnapshotError(f"{label}.reason 必须说明待定、拒绝或冲突原因")
    if change_type == "UNCHANGED" and decision != "CONFIRMED":
        raise RequirementSnapshotError(f"{label} 的 UNCHANGED 只能是 CONFIRMED")
    if change_type == "REMOVED" and decision == "CONFIRMED":
        if item.get("disposition") not in REMOVAL_DISPOSITIONS:
            raise RequirementSnapshotError(f"{label}.disposition 缺少明确删除处置")
    if change_type == "SUPERSEDED" and decision == "CONFIRMED":
        replacement = item.get("replacement_id")
        if not is_bdd_id(replacement):
            raise RequirementSnapshotError(f"{label}.replacement_id 无效")
    return normalized


def _validate_manifest(
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
    content: str,
) -> list[dict[str, Any]]:
    """验证修订清单绑定当前需求和版本，防止旧 AI 产物覆盖新需求。"""
    if manifest.get("version") != MANIFEST_VERSION:
        raise RequirementSnapshotError("需求修订清单 version 必须为 1")
    if manifest.get("scope") == "NEW_SERIAL_REQUIREMENT":
        raise RequirementSnapshotError(
            "检测到新的串行需求：请确认当前需求已经结束，并在干净工作区执行 "
            "check-env --new-requirement"
        )
    if manifest.get("scope") != "SAME_REQUIREMENT":
        raise RequirementSnapshotError("需求修订清单 scope 必须为 SAME_REQUIREMENT")
    if "format_only" in manifest and not isinstance(manifest["format_only"], bool):
        raise RequirementSnapshotError("需求修订清单 format_only 必须是 boolean")
    if "document_changed" in manifest and not isinstance(manifest["document_changed"], bool):
        raise RequirementSnapshotError("需求修订清单 document_changed 必须是 boolean")
    if manifest.get("requirement_id") != snapshot["requirement_id"]:
        raise RequirementSnapshotError("需求修订清单 requirement_id 与当前需求不一致")
    if manifest.get("base_revision") != snapshot["revision"]:
        raise RequirementSnapshotError(
            f"需求修订清单 base_revision 已过期，当前为 {snapshot['revision']}"
        )
    raw_changes = manifest.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        raise RequirementSnapshotError("需求修订清单 changes 必须是非空数组")
    changes = [_normalize_change(item, index) for index, item in enumerate(raw_changes)]
    if manifest.get("format_only") is True and not all(
        item["change_type"] == "UNCHANGED" and item["decision"] == "CONFIRMED"
        for item in changes
    ):
        raise RequirementSnapshotError("format_only 只能用于全量 UNCHANGED 清单")
    identifiers = [item["id"] for item in changes]
    if len(identifiers) != len(set(identifiers)):
        raise RequirementSnapshotError("需求修订清单存在重复 change id")
    try:
        mentioned_ids = bdd_ids_in_text(content)
    except BddScenarioError as exc:
        raise RequirementSnapshotError(str(exc)) from exc
    missing_mentioned = sorted(mentioned_ids - set(identifiers))
    if missing_mentioned:
        raise RequirementSnapshotError(
            "需求正文中已列出的 BDD 场景未进入修订清单: "
            + ", ".join(missing_mentioned)
        )

    active_ids = {item["id"] for item in snapshot["obligations"]}
    prior_pending_ids = {item["id"] for item in snapshot["pending_changes"]}
    missing = (active_ids | prior_pending_ids) - set(identifiers)
    if missing:
        raise RequirementSnapshotError(
            f"需求修订清单没有处理既有义务: {', '.join(sorted(missing))}"
        )
    for item in changes:
        identifier = item["id"]
        if identifier in active_ids and item["change_type"] == "ADDED":
            raise RequirementSnapshotError(f"既有义务不能标记 ADDED: {identifier}")
        if identifier not in active_ids and item["change_type"] != "ADDED":
            raise RequirementSnapshotError(f"新义务必须标记 ADDED: {identifier}")
    return changes


def _normalized_text_for_grounding(value: str) -> str:
    """压缩空白用于判断漏拆补录是否已经写在 requirement_file 里。"""
    return re.sub(r"\s+", "", value).strip()


def _confirmed_changes_grounded_in_content(
    changes: list[dict[str, Any]],
    content: str,
) -> bool:
    """允许补录已写入需求正文的漏拆 BDD，继续阻断聊天脑补的新语义。"""
    grounded = _normalized_text_for_grounding(content)
    semantic_changes = [
        item for item in changes
        if item["decision"] == "CONFIRMED" and item["change_type"] != "UNCHANGED"
    ]
    if not semantic_changes:
        return True
    for item in semantic_changes:
        if item["change_type"] not in {"ADDED", "CHANGED"}:
            return False
        text = item.get("text")
        if not isinstance(text, str) or _normalized_text_for_grounding(text) not in grounded:
            return False
    return True


def _apply_changes(
    snapshot: dict[str, Any],
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把全部已解决决策应用到当前义务集合，拒绝项不会改变已确认总需求。"""
    active = {item["id"]: dict(item) for item in snapshot["obligations"]}
    confirmed_added: set[str] = set()
    replacements: list[tuple[str, str]] = []
    for item in changes:
        identifier = item["id"]
        decision = item["decision"]
        change_type = item["change_type"]
        if decision == "REJECTED":
            continue
        if decision != "CONFIRMED":
            raise RequirementSnapshotError("待定或冲突修订不能应用")
        if change_type == "UNCHANGED":
            continue
        if change_type in {"ADDED", "CHANGED"}:
            active[identifier] = _validate_obligation(
                {
                    "id": identifier,
                    "text": item.get("text"),
                    "required": item.get("required"),
                    "atoms": item.get("atoms"),
                },
                f"change {identifier}",
            )
            if change_type == "ADDED":
                confirmed_added.add(identifier)
        elif change_type == "REMOVED":
            active.pop(identifier, None)
        elif change_type == "SUPERSEDED":
            active.pop(identifier, None)
            replacements.append((identifier, str(item["replacement_id"])))
    for old_id, replacement_id in replacements:
        if replacement_id not in confirmed_added or replacement_id not in active:
            raise RequirementSnapshotError(
                f"SUPERSEDED {old_id} 的 replacement_id 必须是同轮已确认 ADDED 义务"
            )
    if not active:
        raise RequirementSnapshotError("确认后的需求至少需要一个有效 BDD 场景")
    return [active[key] for key in sorted(active)]


def apply_requirement_revision(
    snapshot_path: Path,
    requirement_path: Path,
    content: str,
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """记录或确认一次需求修订；有待定/冲突时不覆盖上一确认版本。"""
    snapshot = load_requirement_snapshot(snapshot_path)
    if snapshot is None:
        raise RequirementSnapshotError("尚未建立需求快照，请先在干净工作区执行 check-env")
    resolved_requirement = Path(requirement_path).expanduser().resolve()
    if Path(str(snapshot["requirement_path"])).resolve() != resolved_requirement:
        raise RequirementSnapshotError("当前 requirement_file 与需求快照路径不一致")
    changes = _validate_manifest(snapshot, manifest, content)
    current_digest = requirement_digest(content)
    unresolved = [item for item in changes if item["decision"] in UNRESOLVED_DECISIONS]
    if unresolved:
        proposal = dict(snapshot)
        proposal["status"] = "PENDING_CONFIRMATION"
        proposal["pending_changes"] = changes
        proposal["proposed_sha256"] = current_digest
        _atomic_write(snapshot_path, proposal)
        return proposal, False

    semantic_confirmed = manifest.get("document_changed") is True or any(
        item["decision"] == "CONFIRMED" and item["change_type"] != "UNCHANGED"
        for item in changes
    )
    if manifest.get("format_only") is True:
        if snapshot["revision"] == 0 or not all(
            item["change_type"] == "UNCHANGED" and item["decision"] == "CONFIRMED"
            for item in changes
        ):
            raise RequirementSnapshotError("format_only 只能用于已有需求的全量 UNCHANGED 清单")
        if current_digest == snapshot["sha256"]:
            return snapshot, True
        updated = dict(snapshot)
        updated.update({
            "sha256": current_digest,
            "content": content.strip(),
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "status": "CONFIRMED",
            "pending_changes": [],
            "proposed_sha256": None,
        })
        _atomic_write(snapshot_path, updated)
        return updated, True
    if snapshot["revision"] > 0 and semantic_confirmed and current_digest == snapshot["sha256"]:
        if (
            snapshot.get("proposed_sha256") != current_digest
            and not _confirmed_changes_grounded_in_content(changes, content)
        ):
            raise RequirementSnapshotError(
                "需求语义已变化但 requirement_file 未更新；请先同步最新完整需求"
            )
    if not semantic_confirmed and current_digest != snapshot["sha256"]:
        raise RequirementSnapshotError(
            "没有已确认语义变化，但 requirement_file 与上一确认版本不同"
        )
    if manifest.get("document_changed") is not True and all(
        item["change_type"] == "UNCHANGED" and item["decision"] == "CONFIRMED"
        for item in changes
    ):
        # 重复确认完全相同的总需求是幂等操作，避免无意义修订使最终报告失效。
        return snapshot, True

    obligations = _apply_changes(snapshot, changes)
    now = datetime.now(timezone.utc).isoformat()
    revision = snapshot["revision"] + 1
    updated = dict(snapshot)
    updated.update({
        "sha256": current_digest,
        "content": content.strip(),
        "confirmed_at": now,
        "revision": revision,
        "status": "CONFIRMED",
        "obligations": obligations,
        "pending_changes": [],
        "proposed_sha256": None,
    })
    history = list(snapshot["history"])
    history.append({
        "revision": revision,
        "sha256": current_digest,
        "confirmed_at": now,
        "changes": changes,
    })
    updated["history"] = history
    _atomic_write(snapshot_path, updated)
    return updated, True


def render_requirement_diff(previous: str, current: str) -> str:
    """输出稳定逐行差异；业务上的增删改分类仍由 AI 结合语义完成。"""
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
