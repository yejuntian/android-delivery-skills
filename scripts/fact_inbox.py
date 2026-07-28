#!/usr/bin/env python3
"""脚本名称：fact_inbox.py

用途：记录聊天中可能影响业务的事实，并把“讨论、待细化、已确认、已拒绝”与需求事实源
分开。聊天本身不是正式需求；只有需求修订成功后，确认事实才绑定当前 revision。

职责边界：只维护事实收件箱，不判断业务语义是否正确、不修改 requirement.md、不执行
需求修订。AI 负责把聊天中的行为性补充登记为候选，并只追问缺失的范围或验收结果。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .atomic_write import write_json_atomic  # noqa: E402
from .config_paths import resolve_config_paths  # noqa: E402
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


FACT_INBOX_VERSION = 1
FACT_ID_PATTERN = re.compile(r"FACT-(\d{3,})$")
FACT_STATUSES = {"DISCUSSION", "PENDING", "CONFIRMED", "REJECTED"}
FACT_MEANINGS = {"CLEAR", "AMBIGUOUS"}
RESOLUTION_STATUSES = {"DISCUSSION", "CONFIRMED", "REJECTED"}


class FactInboxError(RuntimeError):
    """表示事实收件箱损坏、状态非法或无法安全写入。"""


def empty_fact_inbox() -> dict[str, Any]:
    """返回一个没有聊天候选的初始收件箱。"""
    return {"version": FACT_INBOX_VERSION, "facts": []}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactInboxError(f"{label} 必须是非空字符串")
    return value.strip()


def _normalize_missing(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise FactInboxError(f"{label} 必须是字符串数组")
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        raise FactInboxError(f"{label} 不得重复")
    return normalized


def _normalize_fact(item: Any, index: int) -> dict[str, Any]:
    label = f"facts[{index}]"
    if not isinstance(item, dict):
        raise FactInboxError(f"{label} 必须是 object")
    identifier = _require_text(item.get("id"), f"{label}.id")
    if not FACT_ID_PATTERN.fullmatch(identifier):
        raise FactInboxError(f"{label}.id 必须符合 FACT-###")
    text = _require_text(item.get("text"), f"{label}.text")
    source = _require_text(item.get("source", "chat"), f"{label}.source")
    status = item.get("status")
    if status not in FACT_STATUSES:
        raise FactInboxError(f"{label}.status 无效")
    meaning = item.get("meaning", "CLEAR")
    if meaning not in FACT_MEANINGS:
        raise FactInboxError(f"{label}.meaning 无效")
    created_at = _require_text(item.get("created_at"), f"{label}.created_at")
    updated_at = _require_text(item.get("updated_at", created_at), f"{label}.updated_at")
    missing = _normalize_missing(item.get("missing", []), f"{label}.missing")
    materialized_revision = item.get("materialized_revision")
    if materialized_revision is not None and (
        not isinstance(materialized_revision, int)
        or isinstance(materialized_revision, bool)
        or materialized_revision < 0
    ):
        raise FactInboxError(f"{label}.materialized_revision 无效")
    materialized_sha = item.get("materialized_requirement_sha256")
    if materialized_sha is not None and (
        not isinstance(materialized_sha, str)
        or not re.fullmatch(r"[a-f0-9]{64}", materialized_sha)
    ):
        raise FactInboxError(f"{label}.materialized_requirement_sha256 无效")
    if materialized_revision is None and materialized_sha is not None:
        raise FactInboxError(f"{label} 缺少与 materialized_requirement_sha256 对应的 revision")
    if status != "CONFIRMED" and (materialized_revision is not None or materialized_sha is not None):
        raise FactInboxError(f"{label} 只有 CONFIRMED 才能绑定需求 revision")
    return {
        "id": identifier,
        "text": text,
        "source": source,
        "status": status,
        "meaning": meaning,
        "missing": missing,
        "created_at": created_at,
        "updated_at": updated_at,
        "materialized_revision": materialized_revision,
        "materialized_requirement_sha256": materialized_sha,
    }


def validate_fact_inbox(payload: Any) -> list[str]:
    """校验收件箱结构，返回全部错误而不静默丢弃聊天事实。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["事实收件箱根节点必须是 object"]
    if payload.get("version") != FACT_INBOX_VERSION:
        errors.append(f"事实收件箱 version 必须为 {FACT_INBOX_VERSION}")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        return errors + ["事实收件箱 facts 必须是数组"]
    seen: set[str] = set()
    for index, item in enumerate(facts):
        try:
            normalized = _normalize_fact(item, index)
        except FactInboxError as exc:
            errors.append(str(exc))
            continue
        identifier = normalized["id"]
        if identifier in seen:
            errors.append(f"事实收件箱存在重复 id: {identifier}")
        seen.add(identifier)
    return errors


def load_fact_inbox(path: str | Path) -> dict[str, Any]:
    """读取当前需求收件箱；文件不存在表示还没有聊天候选。"""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return empty_fact_inbox()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FactInboxError(f"事实收件箱无法读取: {target}: {exc}") from exc
    errors = validate_fact_inbox(payload)
    if errors:
        raise FactInboxError("；".join(errors))
    return payload


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    errors = validate_fact_inbox(payload)
    if errors:
        raise FactInboxError("；".join(errors))
    try:
        write_json_atomic(Path(path).expanduser().resolve(), payload)
    except OSError as exc:
        raise FactInboxError(f"事实收件箱无法写入: {Path(path).resolve()}: {exc}") from exc


def _next_id(facts: list[dict[str, Any]]) -> str:
    numbers = []
    for item in facts:
        match = FACT_ID_PATTERN.fullmatch(str(item.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"FACT-{(max(numbers, default=0) + 1):03d}"


def add_fact(
    path: str | Path,
    text: str,
    *,
    status: str = "PENDING",
    source: str = "chat",
    meaning: str = "CLEAR",
    missing: list[str] | None = None,
) -> dict[str, Any]:
    """登记一条聊天事实；默认按待细化候选处理，不直接进入正式需求。"""
    if status not in {"DISCUSSION", "PENDING"}:
        raise FactInboxError("新增事实只能是 DISCUSSION 或 PENDING")
    if meaning not in FACT_MEANINGS:
        raise FactInboxError("meaning 必须是 CLEAR 或 AMBIGUOUS")
    payload = load_fact_inbox(path)
    now = _now()
    fact = {
        "id": _next_id(payload["facts"]),
        "text": _require_text(text, "text"),
        "source": _require_text(source, "source"),
        "status": status,
        "meaning": meaning,
        "missing": _normalize_missing(missing or [], "missing"),
        "created_at": now,
        "updated_at": now,
        "materialized_revision": None,
        "materialized_requirement_sha256": None,
    }
    payload["facts"].append(fact)
    _write(path, payload)
    return fact


def resolve_fact(
    path: str | Path,
    identifier: str,
    status: str,
    *,
    missing: list[str] | None = None,
    clear_missing: bool = False,
) -> dict[str, Any]:
    """更新事实讨论状态；CONFIRMED 仍须等需求修订成功才算物化。"""
    if status not in RESOLUTION_STATUSES:
        raise FactInboxError("事实状态只能是 DISCUSSION、CONFIRMED 或 REJECTED")
    payload = load_fact_inbox(path)
    for fact in payload["facts"]:
        if fact["id"] != identifier:
            continue
        fact["status"] = status
        if missing is not None:
            fact["missing"] = _normalize_missing(missing, "missing")
        elif clear_missing:
            fact["missing"] = []
        fact["updated_at"] = _now()
        fact["materialized_revision"] = None
        fact["materialized_requirement_sha256"] = None
        _write(path, payload)
        return fact
    raise FactInboxError(f"不存在的事实 id: {identifier}")


def blocking_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """返回会阻断需求/计划/编码/gate 的事实。"""
    return [
        fact for fact in payload.get("facts", [])
        if fact.get("status") == "PENDING"
        or (
            fact.get("status") == "CONFIRMED"
            and (
                fact.get("missing")
                or fact.get("materialized_revision") is None
            )
        )
    ]


def pending_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """返回尚未获得用户确认的聊天候选。"""
    return [fact for fact in payload.get("facts", []) if fact.get("status") == "PENDING"]


def confirmed_not_ready_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """返回用户已确认方向但仍缺范围/验收条件的事实。"""
    return [
        fact for fact in payload.get("facts", [])
        if fact.get("status") == "CONFIRMED" and fact.get("missing")
    ]


def materialize_confirmed_facts(
    path: str | Path,
    revision: int,
    requirement_sha256: str,
) -> list[str]:
    """需求修订成功后，把已确认候选绑定到当前 revision 和需求摘要。"""
    if not isinstance(revision, int) or revision < 0:
        raise FactInboxError("revision 无效")
    if not re.fullmatch(r"[a-f0-9]{64}", requirement_sha256):
        raise FactInboxError("requirement_sha256 无效")
    payload = load_fact_inbox(path)
    updated: list[str] = []
    for fact in payload["facts"]:
        if fact["status"] != "CONFIRMED":
            continue
        if fact.get("missing"):
            raise FactInboxError(
                f"事实 {fact['id']} 仍缺少: {', '.join(fact['missing'])}"
            )
        if fact.get("materialized_revision") is None:
            fact["materialized_revision"] = revision
            fact["materialized_requirement_sha256"] = requirement_sha256
            fact["updated_at"] = _now()
            updated.append(fact["id"])
    if updated:
        _write(path, payload)
    return updated


def _fact_path_from_config(config_path: Path) -> Path:
    from .delivery import DeliveryError, load_config

    try:
        config = load_config(config_path)
        return resolve_config_paths(config, config_path).fact_inbox_path
    except DeliveryError:
        raise
    except Exception as exc:
        raise FactInboxError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    from .delivery import DeliveryError

    parser = ChineseArgumentParser(description="维护聊天事实收件箱")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add = subparsers.add_parser("add", help="登记聊天事实候选")
    add.add_argument("--config", default=None, help="配置文件路径")
    add.add_argument("--text", required=True, help="聊天中的行为性事实")
    add.add_argument("--status", choices=("PENDING", "DISCUSSION"), default="PENDING")
    add.add_argument("--meaning", choices=sorted(FACT_MEANINGS), default="CLEAR")
    add.add_argument("--source", default="chat")
    add.add_argument("--missing", action="append", default=[])

    resolve = subparsers.add_parser("resolve", help="确认、转讨论或拒绝事实")
    resolve.add_argument("--config", default=None, help="配置文件路径")
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--status", choices=sorted(RESOLUTION_STATUSES), required=True)
    resolve.add_argument("--missing", action="append", default=None)
    resolve.add_argument("--clear-missing", action="store_true")

    validate = subparsers.add_parser("validate", help="校验当前收件箱")
    validate.add_argument("--config", default=None, help="配置文件路径")

    args = parser.parse_args(argv)
    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    try:
        path = _fact_path_from_config(config_path)
        if args.command == "add":
            fact = add_fact(
                path,
                args.text,
                status=args.status,
                source=args.source,
                meaning=args.meaning,
                missing=args.missing,
            )
            print(f"✅ 已登记 {fact['id']}: {path}")
            return 0
        if args.command == "resolve":
            fact = resolve_fact(
                path,
                args.id,
                args.status,
                missing=args.missing,
                clear_missing=args.clear_missing,
            )
            print(f"✅ 已更新 {fact['id']} -> {fact['status']}: {path}")
            return 0
        payload = load_fact_inbox(path)
        blockers = blocking_facts(payload)
        if blockers:
            print(f"❌ 当前有 {len(blockers)} 条事实会阻断流程:")
            for fact in blockers:
                missing = f"；缺少：{', '.join(fact['missing'])}" if fact.get("missing") else ""
                print(f"- {fact['id']} [{fact['status']}] {fact['text']}{missing}")
            return 1
        print(f"✅ 事实收件箱有效且无阻断事实: {path}")
        return 0
    except (DeliveryError, FactInboxError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
