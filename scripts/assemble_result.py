#!/usr/bin/env python3
"""脚本名称：assemble_result.py

用途：根据 agent 提供的产物清单（YAML）自动组装 delivery-result.json，
消除 agent 手动对齐 sha/字段/obligation_test_cases 的摩擦。

核心流程：读取产物清单 → 调 delivery_gate snapshot 拿当前 context →
从执行收据/专项结果/junit 报告自动填充所有指纹与映射 → 输出 delivery-result.json。
agent 只声明"哪些收据/哪些专项/哪个义务由哪个证据覆盖"等业务事实，
所有 sha256、obligation_test_cases、receipt 引用由脚本计算。

职责边界：只组装结构、读已有产物算指纹；不运行测试、不调用 Skill、不做语义判断、
不校验最终结论（校验交给 delivery_gate validate）。obligation→evidence 业务映射
仍由 agent 提供（机器推断不准）。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .execution_evidence import (  # noqa: E402
    junit_content_signature,
    load_execution_receipt,
    sha256_file,
)
from .specialist_result import (  # noqa: E402
    SPECIALIST_PRODUCER,
    SPECIALIST_RESULT_VERSION,
)


DELIVERY_RESULT_VERSION = 4
ASSEMBLE_PRODUCER = "android-delivery-assemble"
SPECIALIST_GATE_ALIASES = {"android-verify-ui": "android-ui-a11y"}
OBLIGATION_STATUSES = {
    "COVERED_AUTOMATED",
    "COVERED_MANUAL",
    "UNVERIFIED",
    "BLOCKED",
    "NOT_APPLICABLE",
}


class AssembleError(RuntimeError):
    """表示产物清单格式错误或引用的产物不可读。"""


@dataclass(frozen=True)
class EvidenceDecl:
    """产物清单里一条证据声明。"""

    id: str
    kind: str  # AUTOMATED / MANUAL
    gate: str
    receipt: str | None  # AUTOMATED 必填
    # MANUAL 字段
    summary: str | None
    executor: str | None
    environment: str | None
    performed_at: str | None
    steps: list[dict[str, Any]] | None
    artifacts: list[dict[str, Any]] | None


def _require_str(value: Any, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssembleError(f"{where}: {field} 必须是非空字符串")
    return value.strip()


def _read_manifest(path: Path) -> dict[str, Any]:
    """读取 YAML 产物清单并要求根节点为 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AssembleError(f"无法读取产物清单: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AssembleError(f"产物清单根节点必须是 object: {path}")
    return data


def _parse_evidence(raw: Any, index: int) -> EvidenceDecl:
    """解析产物清单里一条 evidence 声明。"""
    if not isinstance(raw, dict):
        raise AssembleError(f"evidence[{index}] 必须是 object")
    eid = _require_str(raw.get("id"), "id", f"evidence[{index}]")
    kind = str(raw.get("kind", "AUTOMATED")).upper()
    if kind not in {"AUTOMATED", "MANUAL"}:
        raise AssembleError(f"evidence {eid}: kind 必须是 AUTOMATED 或 MANUAL")
    gate = _require_str(raw.get("gate"), "gate", f"evidence {eid}")
    if kind == "MANUAL" and gate == "android-ui-a11y":
        raise AssembleError(
            f"evidence {eid}: UI 视觉验收请使用 specialists 中的 android-verify-ui 结果，"
            "不要填写通用 MANUAL 收据"
        )
    receipt = raw.get("receipt")
    if kind == "AUTOMATED":
        if not isinstance(receipt, str) or not receipt.strip():
            raise AssembleError(f"evidence {eid}: AUTOMATED 必须提供 receipt 路径")
        receipt = receipt.strip()
    else:
        receipt = None
    return EvidenceDecl(
        id=eid,
        kind=kind,
        gate=gate,
        receipt=receipt,
        summary=raw.get("summary"),
        executor=raw.get("executor"),
        environment=raw.get("environment"),
        performed_at=raw.get("performed_at"),
        steps=raw.get("steps"),
        artifacts=raw.get("artifacts"),
    )


def _build_automated_evidence(
    decl: EvidenceDecl,
    base_dir: Path,
    snapshot_sha256: str,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """从执行收据构造 AUTOMATED 证据，返回 (evidence 对象, obligation→testcase 映射)。

    obligation→testcase 映射留给调用方按 agent 声明的 obligations 裁剪，
    这里先返回该收据 junit 报告里的全部 testcase（按 classname#name）。
    """
    receipt_path = (base_dir / decl.receipt).resolve() if not Path(decl.receipt).is_absolute() else Path(decl.receipt).resolve()
    if not receipt_path.is_file():
        raise AssembleError(f"evidence {decl.id}: 执行收据不存在: {receipt_path}")
    try:
        receipt = load_execution_receipt(receipt_path)
    except Exception as exc:  # noqa: BLE001 - 转成 AssembleError
        raise AssembleError(f"evidence {decl.id}: 执行收据无法读取: {exc}") from exc
    if receipt.get("id") != decl.id:
        raise AssembleError(
            f"evidence {decl.id}: 清单 id 与执行收据 id 不一致: {receipt.get('id')}"
        )
    receipt_sha256 = sha256_file(receipt_path)
    reports = receipt.get("reports", [])
    report_paths = [r.get("path", "") for r in reports if isinstance(r, dict)]
    command = receipt.get("command", [])
    exit_code = receipt.get("exit_code")
    executed_tests = receipt.get("executed_tests")

    # 从 junit 报告提取所有 testcase（classname#name），并组装 obligation_test_cases 候选。
    all_test_cases: list[str] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        junit = report.get("junit")
        if not isinstance(junit, dict):
            continue
        for case in junit.get("test_cases", []):
            if isinstance(case, dict):
                cid = case.get("id") or f"{case.get('classname','')}#{case.get('name','')}"
                if isinstance(cid, str) and cid.strip():
                    all_test_cases.append(cid.strip())

    evidence = {
        "id": decl.id,
        "kind": "AUTOMATED",
        "gate_id": decl.gate,
        "snapshot_sha256": snapshot_sha256,
        "command": command,
        "exit_code": exit_code,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "report_paths": report_paths,
        "obligation_test_cases": {},  # 由 assemble_result 按 obligations 裁剪填入
        "obligation_sha256s": {},  # 由 assemble_result 填入
        "summary": f"由 {ASSEMBLE_PRODUCER} 从执行收据自动组装",
    }
    if executed_tests is not None:
        evidence["executed_tests"] = executed_tests
    return evidence, {decl.id: all_test_cases}


def _build_manual_evidence(
    decl: EvidenceDecl,
    snapshot_sha256: str,
) -> dict[str, Any]:
    """构造 MANUAL 证据对象。"""
    if not isinstance(decl.summary, str) or not decl.summary.strip():
        raise AssembleError(f"evidence {decl.id}: MANUAL 必须提供 summary")
    evidence: dict[str, Any] = {
        "id": decl.id,
        "kind": "MANUAL",
        "gate_id": decl.gate,
        "snapshot_sha256": snapshot_sha256,
        "summary": decl.summary,
        "executor": decl.executor or "",
        "environment": decl.environment or "",
        "performed_at": decl.performed_at or "",
        "obligation_sha256s": {},
        "steps": decl.steps or [],
        "artifacts": [],
    }
    if decl.artifacts:
        for art in decl.artifacts:
            if isinstance(art, dict) and isinstance(art.get("path"), str):
                p = Path(art["path"])
                if p.is_file():
                    evidence["artifacts"].append({
                        "path": art["path"],
                        "sha256": sha256_file(p),
                        "kind": art.get("kind", "artifact"),
                    })
    if not evidence["artifacts"]:
        evidence["no_artifact_reason"] = "MANUAL 证据未声明产物文件"
    return evidence


def _build_specialist_evidence(
    raw: Any,
    index: int,
    base_dir: Path,
    snapshot_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """读 specialist JSON，返回 (evidence 对象, specialist payload)。"""
    if not isinstance(raw, dict):
        raise AssembleError(f"specialists[{index}] 必须是 object 或包含 path")
    path_value = raw.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise AssembleError(f"specialists[{index}] 必须提供 path")
    spath = (base_dir / path_value).resolve() if not Path(path_value).is_absolute() else Path(path_value).resolve()
    if not spath.is_file():
        raise AssembleError(f"specialists[{index}]: 结果文件不存在: {spath}")
    try:
        payload = json.loads(spath.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssembleError(f"specialists[{index}]: 结果文件无法读取: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssembleError(f"specialists[{index}]: 结果文件根节点必须是 object")
    sid = payload.get("id") or f"specialist-{index}"
    skill = payload.get("skill", "")
    evidence = {
        "id": sid,
        "kind": "REVIEW",
        "gate_id": SPECIALIST_GATE_ALIASES.get(skill, skill),
        "snapshot_sha256": snapshot_sha256,
        "summary": payload.get("summary", f"{skill} 专项结果"),
        "specialist": skill,
        "specialist_result_path": str(spath),
        "specialist_result_sha256": sha256_file(spath),
        "obligation_sha256s": {},  # 由 assemble_result 填入
    }
    return evidence, payload


def assemble_delivery_result(
    manifest_path: str | Path,
    context: dict[str, Any],
    result_path: str | Path,
) -> dict[str, Any]:
    """根据产物清单组装 delivery-result.json 并写出，返回组装后的 payload。"""
    manifest_path = Path(manifest_path).expanduser().resolve()
    result_path = Path(result_path).expanduser().resolve()
    base_dir = manifest_path.parent
    manifest = _read_manifest(manifest_path)

    snapshot_sha256 = context["snapshot_sha256"]
    expected_obligations: dict[str, Any] = context.get("expected_obligations", {})
    test_mapping: dict[str, Any] = context.get("test_mapping") or {}

    # 1. 解析 evidence 声明
    raw_evidence = manifest.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise AssembleError("产物清单缺少 evidence 数组")
    decls = [_parse_evidence(item, i) for i, item in enumerate(raw_evidence)]

    # 2. 解析 specialists 声明
    raw_specialists = manifest.get("specialists") or []
    if not isinstance(raw_specialists, list):
        raise AssembleError("产物清单 specialists 必须是数组")

    # 3. 解析 obligations 业务映射（agent 声明哪个义务由哪些证据覆盖）
    raw_obligations = manifest.get("obligations")
    if not isinstance(raw_obligations, dict) or not raw_obligations:
        raise AssembleError("产物清单缺少 obligations 映射（义务→证据 id 列表）")
    obligation_map: dict[str, dict[str, Any]] = {}
    for oid, declaration in raw_obligations.items():
        if not isinstance(oid, str) or not oid.strip():
            raise AssembleError(f"obligations 存在空 key")
        if isinstance(declaration, list):
            refs = [str(ref).strip() for ref in declaration if str(ref).strip()]
            if not refs:
                raise AssembleError(f"obligation {oid} 必须引用至少一个证据 id")
            obligation_map[oid.strip()] = {"status": None, "refs": refs, "reason": None}
            continue
        if not isinstance(declaration, dict):
            raise AssembleError(f"obligation {oid} 必须是证据 id 数组或状态 object")
        unknown = sorted(set(declaration) - {"status", "evidence", "reason"})
        if unknown:
            raise AssembleError(f"obligation {oid} 包含未知字段: {', '.join(unknown)}")
        status = declaration.get("status", "UNVERIFIED")
        if status not in OBLIGATION_STATUSES:
            raise AssembleError(f"obligation {oid} 的 status 无效")
        raw_refs = declaration.get("evidence", [])
        if not isinstance(raw_refs, list):
            raise AssembleError(f"obligation {oid}.evidence 必须是证据 id 数组")
        refs = [str(ref).strip() for ref in raw_refs if str(ref).strip()]
        reason = declaration.get("reason")
        if status in {"COVERED_AUTOMATED", "COVERED_MANUAL"} and not refs:
            raise AssembleError(f"obligation {oid} 标记覆盖时必须引用证据")
        if status in {"UNVERIFIED", "BLOCKED"} and (
            not isinstance(reason, str) or not reason.strip()
        ):
            raise AssembleError(f"obligation {oid} 标记 {status} 时必须说明 reason")
        obligation_map[oid.strip()] = {"status": status, "refs": refs, "reason": reason}

    # 4. 构造 evidence 对象
    evidence_objs: dict[str, dict[str, Any]] = {}
    evidence_test_cases: dict[str, list[str]] = {}  # evidence_id → 全部 testcase
    for decl in decls:
        if decl.kind == "AUTOMATED":
            obj, tc_map = _build_automated_evidence(decl, base_dir, snapshot_sha256)
            evidence_objs[decl.id] = obj
            evidence_test_cases.update(tc_map)
        else:
            evidence_objs[decl.id] = _build_manual_evidence(decl, snapshot_sha256)

    for i, raw_sp in enumerate(raw_specialists):
        obj, _payload = _build_specialist_evidence(raw_sp, i, base_dir, snapshot_sha256)
        evidence_objs[obj["id"]] = obj

    # 5. 填充 obligations + 给 evidence 回填 obligation_sha256s / obligation_test_cases
    obligation_list: list[dict[str, Any]] = []
    for oid, declaration in obligation_map.items():
        expected = expected_obligations.get(oid)
        if expected is None:
            raise AssembleError(f"obligation {oid} 不在当前确认义务集合中")
        sha = expected.get("sha256")
        required = expected.get("required")
        refs = declaration["refs"]
        status = declaration["status"]
        if status is None:
            kinds = {evidence_objs.get(ref, {}).get("kind") for ref in refs}
            if kinds and kinds <= {"AUTOMATED", "AGENT"}:
                status = "COVERED_AUTOMATED"
            elif kinds == {"MANUAL"}:
                status = "COVERED_MANUAL"
            else:
                status = "UNVERIFIED"
        ob_entry: dict[str, Any] = {
            "id": oid,
            "required": required,
            "obligation_sha256": sha,
            "status": status,
            "evidence_ids": refs,
        }
        if isinstance(declaration.get("reason"), str):
            ob_entry["reason"] = declaration["reason"]
        obligation_list.append(ob_entry)
        # 回填每个被引用证据的 obligation_sha256s 和 obligation_test_cases
        mapping = test_mapping.get(oid)
        mapped_test_ids = set(mapping.get("test_ids", [])) if isinstance(mapping, dict) else set()
        for ref in refs:
            ev = evidence_objs.get(ref)
            if ev is None:
                raise AssembleError(f"obligation {oid} 引用了不存在的证据: {ref}")
            ev.setdefault("obligation_sha256s", {})[oid] = sha
            # 只关联当前义务登记且本次实际执行的 testcase。
            if ev.get("kind") == "AUTOMATED":
                executed = evidence_test_cases.get(ref, [])
                matched = list(dict.fromkeys(case for case in executed if case in mapped_test_ids))
                ev.setdefault("obligation_test_cases", {})[oid] = matched

    # 6. 推导 gates
    raw_gates = manifest.get("gates")
    gate_overrides: dict[str, dict[str, Any]] = {}
    if isinstance(raw_gates, dict):
        for gid, ginfo in raw_gates.items():
            if isinstance(ginfo, dict):
                gate_overrides[gid] = ginfo

    def evidence_for_gate(gate_id: str) -> list[str]:
        return [eid for eid, ev in evidence_objs.items() if ev.get("gate_id") == gate_id]

    gate_ids = set()
    for ev in evidence_objs.values():
        if ev.get("gate_id"):
            gate_ids.add(ev["gate_id"])
    # 核心必需 gate 必出现
    core_required = {
        "android-review-diff", "android-review-code-quality", "android-audit-stability",
        "android-test-and-fix", "android-build", "android-lint",
    }
    gate_ids |= core_required

    gates: list[dict[str, Any]] = []
    for gid in sorted(gate_ids):
        refs = evidence_for_gate(gid)
        override = gate_overrides.get(gid, {})
        required = override.get("required", gid in core_required)
        status = override.get("status", "PASS" if refs else "UNVERIFIED")
        entry: dict[str, Any] = {
            "id": gid,
            "required": required,
            "status": status,
            "evidence_ids": refs,
        }
        if "reason" in override:
            entry["reason"] = override["reason"]
        elif not refs:
            entry["reason"] = "无对应证据，待补"
        gates.append(entry)

    # 7. 组装顶层
    conclusion = manifest.get("conclusion", "INCOMPLETE")
    pending = manifest.get("pending_capabilities") or []
    payload = {
        "version": DELIVERY_RESULT_VERSION,
        "requirement_id": context["requirement_id"],
        "requirement_revision": context["requirement_revision"],
        "baseline_id": context["baseline_id"],
        "requirement_file_sha256": context["requirement_file_sha256"],
        "requirement_inputs_sha256": context["requirement_inputs_sha256"],
        "snapshot_sha256": snapshot_sha256,
        "conclusion": conclusion,
        "pending_capabilities": pending,
        "obligations": obligation_list,
        "gates": gates,
        "evidence": list(evidence_objs.values()),
    }

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
