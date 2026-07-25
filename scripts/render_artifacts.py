#!/usr/bin/env python3
"""脚本名称：render_artifacts.py

用途：把机器 JSON 产物渲染成人读 md 影子，让用户打开即知"这步对不对"。

核心流程：读取 requirement_snapshot、test-mapping、implementation-plan-receipt、
delivery-result（若存在）等事实源，调用 user_facing_labels 转中文，渲染需求修订说明、
测试映射说明、交付结论和续接指南。md 是主产物（人读），JSON 仍是门禁附件。

职责边界：只读事实源并渲染，不修改 JSON、不校验门禁、不运行测试、不改需求正文。
续接指南是从事实源聚合的状态快照，不是第二事实源。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_write import write_text_atomic
from .requirement_snapshot import load_requirement_snapshot
from .user_facing_labels import (
    CHANGE_TYPE_LABELS,
    DECISION_LABELS,
    GATE_LABELS,
    GATE_STATUS_LABELS,
    OBLIGATION_STATUS_LABELS,
    SNAPSHOT_STATUS_LABELS,
    gate_label,
    localize_machine_terms,
    user_label,
)


def _read_json(path: Any) -> dict[str, Any] | None:
    """读取 JSON；缺失或路径为 None 返回 None，损坏由调用方容错。"""
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _strip_business_prefix(text: str) -> str:
    """在用户摘要里移除分类标记，保留需求快照中的原始语义。"""
    for prefix in ("【修改已上线业务】", "【保护已上线业务】"):
        if text.startswith(prefix):
            return text.removeprefix(prefix).strip(" ：:")
    return text


def _single_line(value: Any) -> str:
    """把多行字段压成一行，避免破坏 markdown 列表。"""
    return " ".join(str(value or "").split())


def render_revision_md(snapshot: dict[str, Any]) -> str:
    """把 requirement_snapshot 渲染成需求修订说明 md 影子。"""
    lines = [
        "# 需求修订说明",
        "",
        f"> 本文件由 `requirement_snapshot.json` 自动渲染；机器事实以同目录 JSON 为准。",
        "",
        f"- 需求集合：`{snapshot.get('requirement_id', '未知')}`",
        f"- 当前修订：第 {snapshot.get('revision', '?')} 版",
        f"- 状态：{user_label(snapshot.get('status'), SNAPSHOT_STATUS_LABELS)}",
        "",
        "## 当前有效原子验收项",
        "",
    ]
    obligations = snapshot.get("obligations") or []
    if not obligations:
        lines.append("- 尚未生成原子验收项；完成首次确认后这里列出每条 Then。")
    for item in obligations:
        required = "必需" if item.get("required") else "可选"
        text = _strip_business_prefix(_single_line(item.get("text"))) or item.get("id", "")
        lines.append(f"- `{item.get('id')}` [{required}] {text}")
    pending = snapshot.get("pending_changes") or []
    if pending:
        lines.extend(["", "## 尚未确认的变化", ""])
        for change in pending:
            ctype = CHANGE_TYPE_LABELS.get(change.get("change_type"), "未知变化")
            decision = DECISION_LABELS.get(change.get("decision"), "未知决定")
            lines.append(f"- `{change.get('id')}` {ctype}（{decision}）")
    history = snapshot.get("history") or []
    if history:
        lines.extend(["", "## 修订历史", ""])
        for record in history:
            lines.append(f"- 第 {record.get('revision')} 版（`{record.get('sha256', '')[:12]}`）")
    lines.append("")
    return "\n".join(lines)


def render_test_mapping_md(
    mapping: dict[str, Any] | None,
    snapshot: dict[str, Any],
) -> str:
    """把 test-mapping.json 渲染成测试映射说明 md（含架构约束栏）。"""
    obligations = {item["id"]: item for item in snapshot.get("obligations", [])}
    mappings = (mapping or {}).get("mappings") if mapping else None
    lines = [
        "# 测试映射说明",
        "",
        "> 本文件由 `test-mapping.json` 自动渲染；门禁仍以 JSON 为准。",
        "",
        "| 义务 | 必需 | 状态 | 测试用例 | 架构约束 |",
        "|---|---|---|---|---|",
    ]
    if not mappings:
        lines.append("| — | — | 未登记 | — | — |")
    for entry in mappings or []:
        identifier = entry.get("obligation_id")
        obligation = obligations.get(identifier, {})
        required = "必需" if obligation.get("required") else "可选"
        status = "待回填" if entry.get("mapping_status") == "STALE" else "已对齐"
        test_ids = ", ".join(entry.get("test_ids") or []) or "—"
        arch = "; ".join(entry.get("architecture_tests") or []) or "—"
        lines.append(f"| `{identifier}` | {required} | {status} | {test_ids} | {arch} |")
    lines.extend([
        "",
        "- `待回填` 表示需求增量使义务语义变化，旧登记自动标 STALE，必须重新登记测试并回填 CURRENT。",
        "- 架构约束由 AI 生成 ArchUnit/反射测试固化到项目 test 源集，进 `android-test-and-fix` 门禁。",
        "",
    ])
    return "\n".join(lines)


def render_resume_guide(
    snapshot: dict[str, Any] | None,
    mapping: dict[str, Any] | None,
    plan_receipt: dict[str, Any] | None,
    delivery_result: dict[str, Any] | None,
    requirement_title: str = "",
    revision_manifest: dict[str, Any] | None = None,
) -> str:
    """聚合各事实源渲染续接指南，是 AI 续做旧需求的第一入口。

    revision_manifest 为本轮需求修订清单（confirm-requirement-update 传入）时，
    额外渲染"本次增量波及清单"，列出受影响的义务及其测试/计划影响半径。
    """
    lines = ["# 续接指南", ""]
    if requirement_title:
        lines.append(f"## {requirement_title}")
        lines.append("")
    if snapshot is None:
        lines.extend([
            "> 尚未建立需求快照。先执行 `delivery.py init` 和 `check-env`。",
            "",
        ])
        return "\n".join(lines)
    revision = snapshot.get("revision", "?")
    status = user_label(snapshot.get("status"), SNAPSHOT_STATUS_LABELS)
    lines.extend([
        f"- 需求集合：`{snapshot.get('requirement_id', '未知')}`",
        f"- 当前修订：第 {revision} 版（{status}）",
    ])
    plan_confirmed = bool(plan_receipt and plan_receipt.get("confirmed_at"))
    lines.append(f"- 实施计划：{'已确认' if plan_confirmed else '尚未确认或已失效'}")
    conclusion = (delivery_result or {}).get("conclusion")
    if conclusion:
        from .user_facing_labels import DELIVERY_CONCLUSION_LABELS
        lines.append(
            f"- 最终结论：{user_label(conclusion, DELIVERY_CONCLUSION_LABELS)}"
        )
    lines.append("")

    obligations = snapshot.get("obligations") or []
    mappings = {(m.get("obligation_id")): m for m in (mapping or {}).get("mappings", [])}
    if obligations:
        lines.extend(["## 验收项状态", ""])
        for item in obligations:
            identifier = item.get("id")
            entry = mappings.get(identifier, {})
            mapping_status = entry.get("mapping_status")
            if mapping_status == "STALE":
                mark = "⏳ 测试待回填"
            elif mapping_status == "CURRENT":
                mark = "✅ 测试已对齐"
            else:
                mark = "—"
            text = _strip_business_prefix(_single_line(item.get("text"))) or identifier
            lines.append(f"- `{identifier}` {text}（{mark}）")

    # 波及清单：本轮修订清单里 CHANGED/ADDED/REMOVED/SUPERSEDED 的义务及其影响半径。
    impacted = _impact_blast_radius(revision_manifest, mappings)
    if impacted:
        lines.extend(["", f"## 本次增量波及清单（第 {revision} 版）", ""])
        for item in impacted:
            lines.append(f"- `{item['id']}` [{item['change']}] {item['effect']}")

    pending = snapshot.get("pending_changes") or []
    stale = [m for m in (mapping or {}).get("mappings", []) if m.get("mapping_status") == "STALE"]
    if pending:
        lines.extend(["", "## 未确认的需求变化", ""])
        for change in pending:
            lines.append(f"- `{change.get('id')}` 待确认或冲突")
    if stale:
        lines.extend(["", "## 测试待回填项（STALE）", ""])
        for entry in stale:
            lines.append(f"- `{entry.get('obligation_id')}` 需求增量后测试未同步，请重新登记。")

    lines.extend([
        "",
        "## 下一步",
        "",
        "- 未确认变化：完成 `confirm-requirement-update`。",
        "- 计划未确认：展示 `实施计划.md` 并 `confirm-plan`。",
        "- STALE 映射：重新登记测试，`mapping_status` 回填 CURRENT。",
        "- 最终结论为通过且无变化：可直接交付；否则按五步流程继续。",
        "",
        "> 本指南由各 JSON 自动聚合，是状态快照而非第二事实源；需求正文以配置的 requirement_file 为准。",
        "",
    ])
    return "\n".join(lines)


_IMPACT_CHANGE_TYPES = {"ADDED", "CHANGED", "REMOVED", "SUPERSEDED"}


def _impact_blast_radius(
    manifest: dict[str, Any] | None,
    mappings: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """把本轮修订清单的非 UNCHANGED 义务映射成"波及项 + 影响半径"。

    单一职责：只读 manifest 和 mapping 派生波及清单，不改任何状态。REMOVED 义务
    不在当前 mapping 中属正常（已被删除），只提示处置方向。
    """
    if not manifest or not isinstance(manifest, dict):
        return []
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, dict):
            continue
        change_type = change.get("change_type")
        if change_type not in _IMPACT_CHANGE_TYPES:
            continue
        identifier = change.get("id")
        if not isinstance(identifier, str) or identifier in seen:
            continue
        seen.add(identifier)
        entry = mappings.get(identifier, {})
        if change_type == "REMOVED":
            effect = "已删除，确认对应实现已处置（删除/保留兼容/停止）"
        elif entry.get("mapping_status") == "STALE":
            effect = "测试映射已标 STALE，需重新登记"
        elif entry:
            effect = "测试映射需核对是否仍 CURRENT"
        else:
            effect = "待登记测试用例"
        rows.append({"id": identifier, "change": change_type, "effect": effect})
    return rows

    lines.extend([
        "",
        "## 下一步",
        "",
        "- 未确认变化：完成 `confirm-requirement-update`。",
        "- 计划未确认：展示 `实施计划.md` 并 `confirm-plan`。",
        "- STALE 映射：重新登记测试，`mapping_status` 回填 CURRENT。",
        "- 最终结论为通过且无变化：可直接交付；否则按五步流程继续。",
        "",
        "> 本指南由各 JSON 自动聚合，是状态快照而非第二事实源；需求正文以配置的 requirement_file 为准。",
        "",
    ])
    return "\n".join(lines)


def write_resume_guide(path: Path, content: str) -> None:
    """原子写入续接指南 md。"""
    write_text_atomic(path, content)
