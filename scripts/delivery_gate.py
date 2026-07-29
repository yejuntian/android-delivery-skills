#!/usr/bin/env python3
"""脚本名称：delivery_gate.py

用途：校验最终报告是否覆盖最新版 BDD 场景、完整输入、单 gate 收据和专项结果，
并从可信机器结果生成面向用户的中文摘要。

职责边界：读取配置、确认需求修订、Git 基线、当前工作树和最终报告，只写同目录
中文摘要；不运行测试、不调用 Skill、不修代码、不维护流程阶段，也不操作 Git。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import (  # noqa: E402
    baseline_path_for_config,
    delivery_snapshot_exclusions,
    requirement_snapshot_path_for_config,
    resolve_config_paths,
    route_impact_path_for_config,
)
from .bdd_scenarios import is_bdd_id  # noqa: E402
from .atomic_write import write_text_atomic  # noqa: E402
from .delivery import DeliveryError, load_config, read_requirement  # noqa: E402
from .fact_inbox import (  # noqa: E402
    FactInboxError,
    blocking_facts,
    load_fact_inbox,
)
from .execution_evidence import (  # noqa: E402
    KNOWN_EVIDENCE_GATES,
    sha256_file,
    validate_execution_receipt,
)
from .git_changes import GitInspectionError, collect_changed_entries, current_delivery_snapshot  # noqa: E402
from .impact_radius import (  # noqa: E402
    ImpactRadiusError,
    changed_files_outside_radius,
    impact_radius_digest,
    load_impact_radius,
)
from .implementation_plan import (  # noqa: E402
    ImplementationPlanError,
    implementation_plan_path,
    plan_confirmation_receipt_path,
    validate_plan_confirmation,
)
from .requirement_snapshot import (  # noqa: E402
    RequirementSnapshotError,
    load_requirement_snapshot,
    requirement_digest,
)
from .requirement_inputs import requirement_inputs_digest  # noqa: E402
from .test_mapping import (  # noqa: E402
    TestMappingError,
    load_test_mapping,
    validate_test_mapping,
)
from .tdd_cycle import validate_tdd_cycle  # noqa: E402
from .route_impact import RouteImpactError, load_route_impact  # noqa: E402
from .specialist_result import (  # noqa: E402
    JOURNEY_AGENT_SKILL,
    TEST_AND_FIX_SKILL,
    conditional_gates_from_confirmed_impacts,
    validate_specialist_evidence,
)
from .user_facing_labels import (  # noqa: E402
    DELIVERY_CONCLUSION_LABELS,
    GATE_STATUS_LABELS,
    OBLIGATION_STATUS_LABELS,
    ChineseArgumentParser,
    gate_label,
    localize_machine_terms,
    revision_label,
    user_label,
)


PASSING_CONCLUSIONS = {"FULL_PASS", "LOCAL_PASS_DEVICE_PENDING"}
CONCLUSIONS = PASSING_CONCLUSIONS | {"INCOMPLETE", "BLOCKED"}
OBLIGATION_STATUSES = {
    "COVERED_AUTOMATED",
    "COVERED_MANUAL",
    "UNVERIFIED",
    "BLOCKED",
    "NOT_APPLICABLE",
}
GATE_STATUSES = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
EVIDENCE_KINDS = {"AUTOMATED", "AGENT", "MANUAL", "REVIEW"}
SPECIALIST_GATE_SKILLS = {
    "android-review-diff": {"android-review-diff"},
    "android-review-code-quality": {"android-review-code-quality"},
    "android-audit-stability": {"android-audit-stability"},
    "android-verify-api-contract": {"android-verify-api-contract"},
    "android-ui-a11y": {"android-verify-ui"},
    "android-security-privacy": {"android-audit-stability"},
    "android-dynamic-leak": {"android-audit-stability"},
    "android-performance": {"android-audit-stability"},
}
SPECIALIST_GATE_CAPABILITIES = {
    "android-ui-a11y": "android-ui-a11y",
    "android-security-privacy": "android-security-privacy",
    "android-dynamic-leak": "android-dynamic-leak",
    "android-performance": "android-performance",
}
CORE_REQUIRED_GATES = {
    "android-review-diff",
    "android-review-code-quality",
    "android-audit-stability",
    "android-test-and-fix",
    "android-build",
    "android-lint",
}
AUTOMATED_GATE_PROOFS = {
    "android-test-and-fix",
    "android-build",
    "android-lint",
    "android-static-analysis",
    "android-data-migration",
}
MANUAL_GATE_PROOFS = {
    "android-test-and-fix",
    "android-data-migration",
    "android-security-privacy",
    "android-dynamic-leak",
    "android-performance",
}


def _gate_display(gate_id: object) -> str:
    """显示交付门禁的中文语义，并保留机器 ID 便于定位。"""
    return f"{gate_label(gate_id)}（{gate_id}）"
BUSINESS_CHANGE_PREFIX = "【修改已上线业务】"
BUSINESS_PROTECTION_PREFIX = "【保护已上线业务】"


def _business_obligation_prefix(value: Any) -> str | None:
    """识别已上线业务义务的固定前缀，供门禁和中文摘要共用。"""
    text = str(value or "").strip()
    for prefix in (BUSINESS_CHANGE_PREFIX, BUSINESS_PROTECTION_PREFIX):
        if text.startswith(prefix):
            return prefix
    return None


class DeliveryGateError(RuntimeError):
    """表示最终报告、配置或当前交付上下文无法可靠校验。"""


def _fact_blocking_message(facts: list[dict[str, Any]]) -> str:
    """把未物化聊天事实转换成最终门禁可执行的错误信息。"""
    lines = ["存在尚未写回并确认的聊天事实，不能进入最终交付门禁："]
    for fact in facts:
        missing = f"；缺少：{', '.join(fact['missing'])}" if fact.get("missing") else ""
        lines.append(f"- {fact['id']} [{fact['status']}] {fact['text']}{missing}")
    lines.append("请先写回 requirement_file，并重新执行 init 和 confirm-requirement-update。")
    return "\n".join(lines)


def requirement_file_digest(path: Path) -> str:
    """计算提取正文的规范化摘要，避免 DOCX 元数据或换行变化造成误失效。"""
    try:
        return requirement_digest(read_requirement(path))
    except DeliveryError as exc:
        raise DeliveryGateError(str(exc)) from exc


def _path_excluded(path: str, excluded: set[str]) -> bool:
    """判断仓库相对路径是否属于交付文档或最终报告等排除范围。"""
    normalized = path.replace("\\", "/")
    return any(
        normalized == prefix or normalized.startswith(prefix.rstrip("/") + "/")
        for prefix in excluded
    )


def _changed_paths_for_radius(changes: list[Any], excluded: set[str]) -> list[str]:
    """返回影响半径要检查的路径；重命名同时检查旧路径和新路径。"""
    paths: set[str] = set()
    for change in changes:
        for raw_path in (getattr(change, "old_path", None), getattr(change, "path", None)):
            if not raw_path:
                continue
            normalized = str(raw_path).replace("\\", "/")
            if not _path_excluded(normalized, excluded):
                paths.add(normalized)
    return sorted(paths)


def current_context(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """返回最终报告必须绑定的确认修订、有效义务、基线和当前代码摘要。"""
    paths = resolve_config_paths(config, config_path)
    if not paths.project_path or not paths.project_path.is_dir():
        raise DeliveryGateError(f"项目路径无效: {paths.project_path}")
    if not paths.requirement_path or not paths.requirement_path.is_file():
        raise DeliveryGateError(f"需求文件无效: {paths.requirement_path}")
    try:
        requirement_content = read_requirement(paths.requirement_path)
    except DeliveryError as exc:
        raise DeliveryGateError(str(exc)) from exc
    requirement_sha256 = requirement_digest(requirement_content)
    try:
        requirement_snapshot = load_requirement_snapshot(
            requirement_snapshot_path_for_config(config_path)
        )
    except RequirementSnapshotError as exc:
        raise DeliveryGateError(str(exc)) from exc
    if requirement_snapshot is None:
        raise DeliveryGateError("尚未建立需求修订，请先执行 check-env 和 confirm-requirement-update")
    if Path(str(requirement_snapshot["requirement_path"])).resolve() != paths.requirement_path.resolve():
        raise DeliveryGateError("当前 requirement_file 与需求修订记录路径不一致")
    if requirement_snapshot["status"] != "CONFIRMED" or requirement_snapshot["pending_changes"]:
        raise DeliveryGateError("需求修订仍有待定或冲突项，不能进入最终交付门禁")
    if requirement_snapshot["sha256"] != requirement_sha256:
        raise DeliveryGateError("requirement_file 尚未确认为当前需求修订")
    fact_inbox_path = paths.fact_inbox_path
    try:
        fact_inbox = load_fact_inbox(fact_inbox_path)
    except FactInboxError as exc:
        raise DeliveryGateError(str(exc)) from exc
    fact_blockers = blocking_facts(fact_inbox)
    if fact_blockers:
        raise DeliveryGateError(_fact_blocking_message(fact_blockers))
    route_path = route_impact_path_for_config(config_path)
    try:
        route_impact = load_route_impact(route_path)
    except RouteImpactError as exc:
        raise DeliveryGateError(str(exc)) from exc
    try:
        plan_context = validate_plan_confirmation(
            requirement_snapshot,
            requirement_content,
            paths.requirement_dir,
        )
    except ImplementationPlanError as exc:
        raise DeliveryGateError(str(exc)) from exc
    requirement_inputs_sha256 = requirement_inputs_digest(
        config,
        config_path,
        requirement_sha256,
        implementation_plan_sha256=plan_context["implementation_plan_sha256"],
        impact_radius_sha256=plan_context["impact_radius_sha256"],
    )
    try:
        radius_payload = load_impact_radius(
            paths.impact_radius_path,
            requirement_snapshot,
            requirement_content,
        )
    except ImpactRadiusError as exc:
        raise DeliveryGateError(str(exc)) from exc
    if impact_radius_digest(radius_payload) != plan_context["impact_radius_sha256"]:
        raise DeliveryGateError("影响半径已变化，请重新展示实施计划并执行 delivery.py confirm-plan")

    expected_obligations = {
        item["id"]: {
            "text": item["text"],
            "required": item["required"],
            "sha256": item["sha256"],
        }
        for item in requirement_snapshot["obligations"]
    }
    if not expected_obligations:
        raise DeliveryGateError("当前确认修订没有 BDD 场景")
    result_path = (paths.requirement_dir / "test-results" / "delivery-result.json").resolve()
    docs_dir = paths.docs_dir
    summary_path = (docs_dir / "交付结论.md").resolve()
    excluded = delivery_snapshot_exclusions(paths.project_path, paths.requirement_dir)
    try:
        snapshot = current_delivery_snapshot(
            paths.project_path,
            baseline_path_for_config(config_path),
            exclude_paths=excluded,
        )
    except GitInspectionError as exc:
        raise DeliveryGateError(str(exc)) from exc
    try:
        all_changes, _ = collect_changed_entries(
            paths.project_path,
            baseline_path_for_config(config_path),
        )
    except GitInspectionError as exc:
        raise DeliveryGateError(str(exc)) from exc
    changed_files = _changed_paths_for_radius(all_changes, excluded)
    context = {
        **snapshot,
        "project_path": str(paths.project_path.resolve()),
        "requirement_id": requirement_snapshot["requirement_id"],
        "requirement_revision": requirement_snapshot["revision"],
        "requirement_file_sha256": requirement_sha256,
        "requirement_inputs_sha256": requirement_inputs_sha256,
        **plan_context,
        "expected_obligations": expected_obligations,
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "traceability_path": str(
            (docs_dir / "需求测试追溯.md").resolve()
        ),
        "implementation_plan_path": str(implementation_plan_path(paths.requirement_dir)),
        "plan_receipt_path": str(plan_confirmation_receipt_path(paths.requirement_dir)),
        "impact_radius_path": str(paths.impact_radius_path),
        "impact_radius_sha256": plan_context["impact_radius_sha256"],
        "impact_radius": radius_payload,
        "changed_files": sorted(set(changed_files)),
        "test_mapping_path": str(paths.test_mapping_path),
        "tdd_cycle_path": str(paths.tdd_cycle_path),
        "fact_inbox_path": str(fact_inbox_path),
        "fact_inbox": fact_inbox,
    }
    api_config = config.get("api")
    api_status = api_config.get("status") if isinstance(api_config, dict) else None
    context["api_contract_status"] = (
        api_status.strip().lower() if isinstance(api_status, str) and api_status.strip() else "missing"
    )
    testing = config.get("testing")
    context["tdd_required"] = bool(
        not isinstance(testing, dict) or testing.get("tdd_required", True) is not False
    )
    for field in (
        "requirement_id",
        "requirement_revision",
        "requirement_file_sha256",
        "requirement_inputs_sha256",
        "implementation_plan_sha256",
        "impact_radius_sha256",
        "plan_confirmation_receipt_sha256",
        "baseline_id",
        "snapshot_sha256",
    ):
        if route_impact.get(field) != context[field]:
            raise DeliveryGateError(
                f"路由影响快照的 {field} 已失效，请在最终代码上重新执行 delivery.py route"
            )
    context["route_impact_path"] = str(route_path)
    context["required_specialist_tasks"] = route_impact["specialist_tasks"]
    context["expected_conditional_gates"] = sorted(
        candidate["id"] for candidate in route_impact["conditional_gates"]
    )
    # 测试映射是“需求增量后必须同步测试”的机器兜底；缺失时记为缺失，最终校验时拦截。
    test_mapping_path = paths.test_mapping_path
    try:
        if test_mapping_path.is_file():
            test_mapping = load_test_mapping(test_mapping_path)
            mapping_errors = validate_test_mapping(test_mapping, requirement_snapshot)
            if mapping_errors:
                raise DeliveryGateError("；".join(mapping_errors))
            context["test_mapping"] = {
                item["obligation_id"]: item for item in test_mapping.get("mappings", [])
            }
        else:
            context["test_mapping"] = None
    except TestMappingError as exc:
        raise DeliveryGateError(str(exc)) from exc
    return context


def _indexed(items: Any, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    """按 id 建立唯一索引，避免重复证据或义务互相覆盖。"""
    if not isinstance(items, list):
        errors.append(f"{label} 必须是数组")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] 必须是 object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{label}[{index}].id 必须是非空字符串")
            continue
        if identifier in indexed:
            errors.append(f"{label} 存在重复 id: {identifier}")
            continue
        indexed[identifier] = item
    return indexed


def _validate_manual_evidence(identifier: str, item: dict[str, Any]) -> tuple[list[str], bool]:
    """校验已实际执行的人工收据；返回结构错误及所有步骤是否真实通过。"""
    errors: list[str] = []
    if item.get("gate_id") not in KNOWN_EVIDENCE_GATES:
        errors.append(f"人工证据 {identifier} 缺少有效 gate_id")
    for field in ("executor", "environment", "summary"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"人工证据 {identifier} 缺少 {field}")
    try:
        performed_at = datetime.fromisoformat(str(item.get("performed_at")))
        if performed_at.tzinfo is None:
            raise ValueError("timezone required")
    except (TypeError, ValueError):
        errors.append(f"人工证据 {identifier}.performed_at 必须是带时区的 ISO 时间")

    steps = item.get("steps")
    all_passed = isinstance(steps, list) and bool(steps)
    if not isinstance(steps, list) or not steps:
        errors.append(f"人工证据 {identifier}.steps 必须是非空数组")
        steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"人工证据 {identifier}.steps[{index}] 必须是 object")
            all_passed = False
            continue
        for field in ("action", "expected", "actual"):
            if not isinstance(step.get(field), str) or not step[field].strip():
                errors.append(f"人工证据 {identifier}.steps[{index}] 缺少 {field}")
        if step.get("status") not in {"PASS", "FAIL", "BLOCKED"}:
            errors.append(f"人工证据 {identifier}.steps[{index}].status 无效")
        if step.get("status") != "PASS":
            all_passed = False

    artifacts = item.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append(f"人工证据 {identifier}.artifacts 必须是数组")
        artifacts = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"人工证据 {identifier}.artifacts[{index}] 必须是 object")
            continue
        path = Path(str(artifact.get("path", ""))).expanduser()
        expected_sha = artifact.get("sha256")
        if not path.is_file():
            errors.append(f"人工证据 {identifier} 的产物不存在: {path}")
            continue
        try:
            if sha256_file(path) != expected_sha:
                errors.append(f"人工证据 {identifier} 的产物摘要已变化: {path}")
        except OSError as exc:
            errors.append(f"人工证据 {identifier} 的产物无法读取: {exc}")
    if not artifacts and (
        not isinstance(item.get("no_artifact_reason"), str)
        or not item["no_artifact_reason"].strip()
    ):
        errors.append(f"人工证据 {identifier} 无产物时必须说明 no_artifact_reason")
    return errors, all_passed and not errors


def validate_delivery_result(payload: Any, context: dict[str, Any]) -> list[str]:
    """验证报告结构、证据引用、通过结论和当前代码新鲜度，返回全部错误。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["delivery-result.json 根节点必须是 object"]
    if payload.get("version") != 4:
        errors.append("version 必须为 4")
    for field in (
        "requirement_id", "requirement_revision", "baseline_id",
        "requirement_file_sha256", "requirement_inputs_sha256", "snapshot_sha256",
    ):
        if payload.get(field) != context[field]:
            errors.append(f"{field} 与当前需求/代码不一致，旧证据已经失效")
    conclusion = payload.get("conclusion")
    if conclusion not in CONCLUSIONS:
        errors.append(f"conclusion 必须是 {sorted(CONCLUSIONS)} 之一")
    passing = conclusion in PASSING_CONCLUSIONS

    evidence = _indexed(payload.get("evidence"), "evidence", errors)
    obligations = _indexed(payload.get("obligations"), "obligations", errors)
    gates = _indexed(payload.get("gates"), "gates", errors)
    pending_capabilities = _indexed(
        payload.get("pending_capabilities"),
        "pending_capabilities",
        errors,
    )
    expected_obligations = context.get("expected_obligations", {})
    expected_ids = set(expected_obligations)
    actual_ids = set(obligations)
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        if missing:
            errors.append(f"最终报告漏掉当前确认义务: {', '.join(missing)}")
        if unexpected:
            errors.append(f"最终报告包含非当前义务: {', '.join(unexpected)}")

    radius_payload = context.get("impact_radius")
    changed_files = context.get("changed_files", [])
    if isinstance(radius_payload, dict) and isinstance(changed_files, list):
        outside = changed_files_outside_radius(
            [str(path) for path in changed_files],
            radius_payload,
        )
        if outside:
            errors.append(
                "最终 diff 超出已确认影响半径，请更新需求/实施计划/impact-radius 并重新 confirm-plan: "
                + ", ".join(outside)
            )

    specialist_results: dict[str, dict[str, Any]] = {}
    valid_automated: set[str] = set()
    valid_manual: set[str] = set()
    structured_manual: set[str] = set()

    def declared_evidence_refs(item: dict[str, Any]) -> list[str]:
        refs = item.get("evidence_ids")
        return [ref for ref in refs if isinstance(ref, str)] if isinstance(refs, list) else []

    automated_coverage_refs = {
        ref
        for obligation in obligations.values()
        if obligation.get("status") == "COVERED_AUTOMATED"
        for ref in declared_evidence_refs(obligation)
    }
    automated_obligation_ids = {
        identifier
        for identifier, obligation in obligations.items()
        if obligation.get("status") == "COVERED_AUTOMATED"
    }
    tdd_cycle_valid = True
    if passing and context.get("tdd_required") and automated_obligation_ids:
        tdd_cycle_errors = validate_tdd_cycle(
            context.get("tdd_cycle_path", ""),
            context,
            automated_obligation_ids,
        )
        errors.extend(tdd_cycle_errors)
        tdd_cycle_valid = not tdd_cycle_errors
    pass_gate_refs = {
        ref
        for gate in gates.values()
        if gate.get("status") == "PASS"
        for ref in declared_evidence_refs(gate)
    }
    failed_gate_refs = {
        ref
        for gate_id, gate in gates.items()
        if gate.get("status") == "FAIL"
        for ref in declared_evidence_refs(gate)
        if evidence.get(ref, {}).get("gate_id") == gate_id
    }
    for identifier, item in evidence.items():
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            errors.append(f"evidence {identifier} 的 kind 无效")
        if item.get("snapshot_sha256") != context["snapshot_sha256"]:
            errors.append(f"evidence {identifier} 不是当前最终代码上的新鲜证据")
        if kind == "AUTOMATED":
            allow_failure = (
                not passing
                and identifier in failed_gate_refs
                and identifier not in pass_gate_refs
                and identifier not in automated_coverage_refs
            )
            command = item.get("command")
            if not isinstance(command, list) or not command or not all(
                isinstance(part, str) and part for part in command
            ):
                errors.append(f"自动证据 {identifier} 缺少参数数组形式的 command")
            if item.get("exit_code") != 0 and not allow_failure:
                errors.append(f"自动证据 {identifier} 的 exit_code 必须为 0")
            receipt_path = item.get("receipt_path")
            receipt_sha256 = item.get("receipt_sha256")
            if not isinstance(receipt_path, str) or not receipt_path.strip():
                errors.append(f"自动证据 {identifier} 缺少 execution_evidence.py 收据路径")
            elif not isinstance(receipt_sha256, str) or not re.fullmatch(
                r"[a-f0-9]{64}", receipt_sha256
            ):
                errors.append(f"自动证据 {identifier} 缺少有效收据 SHA-256")
            else:
                receipt_errors = validate_execution_receipt(
                    receipt_path,
                    receipt_sha256,
                    item,
                    context,
                    allow_failure=allow_failure,
                )
                errors.extend(receipt_errors)
                if not receipt_errors and not allow_failure:
                    valid_automated.add(identifier)
        elif kind in {"MANUAL", "REVIEW", "AGENT"}:
            if not isinstance(item.get("summary"), str) or not item["summary"].strip():
                errors.append(f"{kind} 证据 {identifier} 缺少实际结果 summary")
            if kind == "MANUAL":
                manual_errors, manual_passed = _validate_manual_evidence(identifier, item)
                errors.extend(manual_errors)
                if not manual_errors:
                    structured_manual.add(identifier)
                    if manual_passed:
                        valid_manual.add(identifier)
            else:
                specialist = item.get("specialist")
                result_path = item.get("specialist_result_path")
                result_sha = item.get("specialist_result_sha256")
                if not isinstance(specialist, str) or not specialist.strip():
                    errors.append(f"{kind} 证据 {identifier} 缺少 specialist")
                elif kind == "AGENT" and specialist != JOURNEY_AGENT_SKILL:
                    errors.append(
                        f"AGENT 证据 {identifier} 只能由 {JOURNEY_AGENT_SKILL} 生成"
                    )
                if not isinstance(result_path, str) or not result_path.strip():
                    errors.append(f"{kind} 证据 {identifier} 缺少统一专项结果路径")
                elif not isinstance(result_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", result_sha):
                    errors.append(f"{kind} 证据 {identifier} 缺少有效专项结果 SHA-256")
                else:
                    specialist_errors, specialist_payload = validate_specialist_evidence(
                        result_path,
                        result_sha,
                        item,
                        context,
                    )
                    errors.extend(specialist_errors)
                    if specialist_payload and not specialist_errors:
                        specialist_results[identifier] = specialist_payload
        obligation_hashes = item.get("obligation_sha256s", {})
        if not isinstance(obligation_hashes, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in obligation_hashes.items()
        ):
            errors.append(f"evidence {identifier}.obligation_sha256s 必须是字符串映射")
            continue
        for obligation_id, digest in obligation_hashes.items():
            expected = expected_obligations.get(obligation_id)
            if not expected:
                errors.append(f"evidence {identifier} 绑定了非当前义务: {obligation_id}")
            elif digest != expected["sha256"]:
                errors.append(f"evidence {identifier} 对 {obligation_id} 的需求证据已失效")

    def validate_refs(owner: str, item: dict[str, Any]) -> list[str]:
        """验证一个义务或门禁引用的证据都真实存在。"""
        refs = item.get("evidence_ids", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            errors.append(f"{owner}.evidence_ids 必须是字符串数组")
            return []
        if len(refs) != len(set(refs)):
            errors.append(f"{owner}.evidence_ids 不得重复")
        missing = [ref for ref in refs if ref not in evidence]
        if missing:
            errors.append(f"{owner} 引用了不存在的证据: {', '.join(missing)}")
        return refs

    def specialist_supports_gate(result: dict[str, Any], gate_id: str) -> bool:
        """确认专项身份及按需 capability 与 gate 完全对应。"""
        accepted_skills = SPECIALIST_GATE_SKILLS.get(gate_id, set())
        if result.get("skill") not in accepted_skills or result.get("conclusion") != "PASS":
            return False
        capability_id = SPECIALIST_GATE_CAPABILITIES.get(gate_id)
        if not capability_id:
            return True
        return any(
            isinstance(capability, dict)
            and capability.get("id") == capability_id
            and capability.get("status") == "PASS"
            for capability in result.get("capabilities", [])
        )

    def evidence_supports_gate(ref: str, gate_id: str) -> bool:
        """只允许专属于当前 gate 的有效自动、人工或专项结果证明通过。"""
        item = evidence.get(ref, {})
        kind = item.get("kind")
        if kind == "AUTOMATED":
            return (
                gate_id in AUTOMATED_GATE_PROOFS
                and ref in valid_automated
                and item.get("gate_id") == gate_id
                and (
                    gate_id != "android-test-and-fix"
                    or not context.get("tdd_required")
                    or not automated_obligation_ids
                    or tdd_cycle_valid
                )
            )
        if kind == "MANUAL":
            return (
                gate_id in MANUAL_GATE_PROOFS
                and ref in valid_manual
                and item.get("gate_id") == gate_id
            )
        if kind == "AGENT":
            return gate_id == "android-test-and-fix" and (
                specialist_results.get(ref, {}).get("skill") == JOURNEY_AGENT_SKILL
                and specialist_results.get(ref, {}).get("conclusion") == "PASS"
            )
        return specialist_supports_gate(specialist_results.get(ref, {}), gate_id)

    # route 只登记必需专项；最终门禁逐项核对对应 gate 是否已有当前版本结果。
    # 这一步不执行 Skill，只防止漏跑专项后仍生成整体通过结论。
    for task in context.get("required_specialist_tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = task.get("id", "未知任务")
        gate_id = task.get("gate_id")
        skill = task.get("skill", "未知专项")
        name = gate_label(gate_id)
        gate = gates.get(gate_id) if isinstance(gate_id, str) else None
        if not isinstance(gate, dict):
            errors.append(
                f"专项任务 {name}（{skill}，{task_id}）未登记对应的交付门禁"
            )
            continue
        refs = gate.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(
                f"专项任务 {name}（{skill}，{task_id}）缺少执行结果"
            )
            continue
        if passing:
            has_current_pass = any(
                evidence_supports_gate(ref, gate_id)
                for ref in refs
                if isinstance(ref, str)
            )
            explicit_skip = (
                gate.get("status") == "SKIPPED"
                and gate.get("required") is False
                and gate_id in set(context.get("expected_conditional_gates", []))
                and isinstance(gate.get("reason"), str)
                and bool(gate["reason"].strip())
            )
            pending_allowed = (
                conclusion == "LOCAL_PASS_DEVICE_PENDING"
                and gate.get("status") == "UNVERIFIED"
                and gate_id in pending_capabilities
            )
            if not has_current_pass and not explicit_skip and not pending_allowed:
                errors.append(
                    f"专项任务 {name}（{skill}，{task_id}）没有当前代码对应的有效通过结果"
                )

    unresolved_specialist_capabilities: dict[str, set[str]] = {}
    for ref, result in specialist_results.items():
        for capability in result.get("capabilities", []):
            if not isinstance(capability, dict):
                continue
            capability_id = capability.get("id")
            if (
                isinstance(capability_id, str)
                and capability_id
                and capability.get("status") in {"UNVERIFIED", "BLOCKED"}
            ):
                unresolved_specialist_capabilities.setdefault(capability_id, set()).add(ref)

    for identifier, item in pending_capabilities.items():
        if not isinstance(item.get("requires_device"), bool):
            errors.append(f"pending capability {identifier}.requires_device 必须是 boolean")
        elif passing and item["requires_device"] is not True:
            errors.append(f"通过结论中的 pending capability {identifier} 必须是真实设备待验证项")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append(f"pending capability {identifier} 必须说明 reason")
        refs = validate_refs(f"pending capability {identifier}", item)
        if not refs:
            errors.append(f"pending capability {identifier} 必须引用环境或专项证据")
            continue
        matching_pending_evidence = any(
            ref in unresolved_specialist_capabilities.get(identifier, set())
            or (
                ref in structured_manual
                and evidence.get(ref, {}).get("gate_id") == identifier
                and any(
                    isinstance(step, dict) and step.get("status") in {"FAIL", "BLOCKED"}
                    for step in evidence.get(ref, {}).get("steps", [])
                )
            )
            for ref in refs
        )
        if not matching_pending_evidence:
            errors.append(
                f"pending capability {identifier} 缺少同能力的 UNVERIFIED/BLOCKED 专项或人工证据"
            )

    for identifier, item in obligations.items():
        if not is_bdd_id(identifier):
            errors.append(f"obligation id 格式无效: {identifier}")
        if not isinstance(item.get("required"), bool):
            errors.append(f"obligation {identifier}.required 必须是 boolean")
        expected = expected_obligations.get(identifier)
        if expected:
            if (
                _business_obligation_prefix(expected.get("text"))
                and expected.get("required") is not True
            ):
                errors.append(
                    f"已上线业务原子验收项 {identifier} 必须 required=true（必需），不能设为可选"
                )
            if item.get("required") != expected["required"]:
                errors.append(f"obligation {identifier}.required 与当前确认修订不一致")
            if item.get("obligation_sha256") != expected["sha256"]:
                errors.append(f"obligation {identifier} 的语义摘要与当前确认修订不一致")
        status = item.get("status")
        if status not in OBLIGATION_STATUSES:
            errors.append(f"obligation {identifier} 的 status 无效")
        refs = validate_refs(f"obligation {identifier}", item)
        required = item.get("required") is True
        if passing and required and status not in {"COVERED_AUTOMATED", "COVERED_MANUAL"}:
            errors.append(f"必需 obligation {identifier} 尚未覆盖，不能使用通过结论")
        if status == "COVERED_AUTOMATED" and not any(
            evidence.get(ref, {}).get("kind") in {"AUTOMATED", "AGENT"}
            and evidence.get(ref, {}).get("obligation_sha256s", {}).get(identifier)
            == (expected or {}).get("sha256")
            and (
                (
                    evidence.get(ref, {}).get("kind") == "AUTOMATED"
                    and ref in valid_automated
                    and bool(
                        evidence.get(ref, {})
                        .get("obligation_test_cases", {})
                        .get(identifier)
                    )
                )
                or (
                    evidence.get(ref, {}).get("kind") == "AGENT"
                    and specialist_results.get(ref, {}).get("conclusion") == "PASS"
                )
            )
            for ref in refs
        ):
            errors.append(f"obligation {identifier} 缺少自动执行证据")
        # 测试映射门禁：COVERED_AUTOMATED 义务的映射必须 CURRENT，且登记的测试 id
        # 必须出现在执行收据里；STALE 映射表示需求已增量但测试未同步，直接阻断。
        test_mapping = context.get("test_mapping")
        if status == "COVERED_AUTOMATED":
            if test_mapping is None:
                errors.append(
                    "缺少当前需求的测试映射，请先执行 delivery.py init-test-mapping"
                )
            else:
                entry = test_mapping.get(identifier)
                if entry is None:
                    errors.append(f"义务 {identifier} 缺少测试映射登记")
                elif entry["mapping_status"] == "STALE":
                    errors.append(
                        f"义务 {identifier} 的测试映射过期：需求已增量但测试未同步"
                    )
                elif not entry.get("test_ids"):
                    errors.append(f"义务 {identifier} 标记自动覆盖但未登记测试 id")
                else:
                    # 一致性只对 AUTOMATED 证据核对；纯 AGENT(Journey) 覆盖由专项结果 PASS 证明，
                    # 不走 junit testcase 收据，无法用 test_ids 交叉核对。
                    receipt_cases: set[str] = set()
                    has_automated = False
                    for ref in refs:
                        if evidence.get(ref, {}).get("kind") != "AUTOMATED":
                            continue
                        has_automated = True
                        receipt_cases.update(
                            evidence.get(ref, {}).get("obligation_test_cases", {}).get(identifier, [])
                        )
                    if has_automated:
                        unmapped = sorted(set(entry["test_ids"]) - receipt_cases)
                        if unmapped:
                            errors.append(
                                f"义务 {identifier} 的测试映射登记了未执行的测试: "
                                + ", ".join(unmapped)
                            )
                        unexpected = sorted(receipt_cases - set(entry["test_ids"]))
                        if unexpected:
                            errors.append(
                                f"义务 {identifier} 的自动证据关联了未登记测试: "
                                + ", ".join(unexpected)
                            )
        if status == "COVERED_AUTOMATED" and not any(
            isinstance(evidence.get(ref, {}).get("executed_tests"), int)
            and evidence.get(ref, {}).get("executed_tests", 0) > 0
            for ref in refs
        ):
            errors.append(f"obligation {identifier} 的自动证据没有实际执行测试")
        if status == "COVERED_MANUAL" and not any(
            evidence.get(ref, {}).get("kind") == "MANUAL"
            and ref in valid_manual
            and evidence.get(ref, {}).get("obligation_sha256s", {}).get(identifier)
            == (expected or {}).get("sha256")
            for ref in refs
        ):
            errors.append(f"obligation {identifier} 缺少实际人工证据")

    for identifier, item in gates.items():
        if not isinstance(item.get("required"), bool):
            errors.append(f"交付门禁 {_gate_display(identifier)}.required 必须是 boolean")
        status = item.get("status")
        if status not in GATE_STATUSES:
            errors.append(f"交付门禁 {_gate_display(identifier)} 的状态无效")
        refs = validate_refs(f"交付门禁 {_gate_display(identifier)}", item)
        if passing and item.get("required") is True and status != "PASS":
            errors.append(f"必需交付门禁 {_gate_display(identifier)} 未通过")
        if status == "PASS" and not refs:
            errors.append(f"交付门禁 {_gate_display(identifier)} 标记通过但没有证据")
        if status == "PASS" and refs and not any(
            evidence_supports_gate(ref, identifier)
            for ref in refs
        ):
            errors.append(
                f"交付门禁 {_gate_display(identifier)} 没有专属于本门禁的有效通过证据"
            )

    if passing and not obligations:
        errors.append("通过结论至少需要一个 BDD 场景 obligation")
    if passing and obligations and not any(item.get("required") is True for item in obligations.values()):
        errors.append("通过结论至少需要一个 required=true 的 BDD 场景 obligation")
    if passing and not gates:
        errors.append("通过结论至少需要一个交付 gate")
    if conclusion == "FULL_PASS" and pending_capabilities:
        errors.append("FULL_PASS 不允许保留 pending_capabilities")
    if conclusion == "LOCAL_PASS_DEVICE_PENDING" and not any(
        item.get("requires_device") is True for item in pending_capabilities.values()
    ):
        errors.append("LOCAL_PASS_DEVICE_PENDING 必须至少记录一个真实设备待验证项")
    unresolved_ids = {
        identifier
        for identifier, item in {**obligations, **gates}.items()
        if item.get("status") in {"UNVERIFIED", "BLOCKED"}
    } | set(unresolved_specialist_capabilities)
    if conclusion == "FULL_PASS" and unresolved_ids:
        errors.append("FULL_PASS 不允许保留 UNVERIFIED/BLOCKED 项: " + ", ".join(sorted(unresolved_ids)))
    if conclusion == "LOCAL_PASS_DEVICE_PENDING":
        missing_pending = sorted(unresolved_ids - set(pending_capabilities))
        if missing_pending:
            errors.append("设备待验结论没有登记全部未验证项: " + ", ".join(missing_pending))
    if passing:
        expected_conditional_gates = set(context.get("expected_conditional_gates", set()))
        diff_gate = gates.get("android-review-diff", {})
        for ref in diff_gate.get("evidence_ids", []):
            result = specialist_results.get(ref, {})
            if result.get("conclusion") == "PASS":
                expected_conditional_gates.update(
                    conditional_gates_from_confirmed_impacts(result)
                )
        for gate_id in sorted(CORE_REQUIRED_GATES):
            gate = gates.get(gate_id)
            if not gate:
                errors.append(f"通过结论缺少核心交付门禁：{_gate_display(gate_id)}")
            elif gate.get("required") is not True or gate.get("status") != "PASS":
                errors.append(
                    f"核心交付门禁 {_gate_display(gate_id)} 必须 required=true 且状态为通过"
                )
        for gate_id in sorted(expected_conditional_gates):
            gate = gates.get(gate_id)
            if not gate:
                errors.append(
                    f"通过结论缺少路由或语义触发的条件交付门禁：{_gate_display(gate_id)}"
                )
                continue
            if gate.get("required") is True:
                if gate.get("status") != "PASS":
                    errors.append(
                        f"适用的条件交付门禁 {_gate_display(gate_id)} 必须状态为通过"
                    )
                continue
            reason = gate.get("reason")
            refs = gate.get("evidence_ids", [])
            conditional_status = gate.get("status")
            pending = pending_capabilities.get(gate_id)
            allowed_pending = (
                conclusion == "LOCAL_PASS_DEVICE_PENDING"
                and conditional_status == "UNVERIFIED"
                and pending is not None
            )
            if conditional_status != "SKIPPED" and not allowed_pending:
                errors.append(
                    f"条件交付门禁 {_gate_display(gate_id)} 非必需时只能标记为跳过，"
                    "设备待验时使用尚未验证并登记待验项"
                )
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"条件交付门禁 {_gate_display(gate_id)} 跳过时必须说明需求与 diff 依据")
            if not isinstance(refs, list) or not refs:
                errors.append(f"条件交付门禁 {_gate_display(gate_id)} 跳过时必须引用实际复核证据")
    return errors


def load_result(path: Path) -> Any:
    """读取最终 JSON；格式损坏时输出可操作错误而不是 Python traceback。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryGateError(f"最终交付报告无法读取: {path}: {exc}") from exc


def _single_line(value: Any) -> str:
    """把机器字段压成适合 Markdown 列表的一行，避免换行破坏中文摘要。"""
    return " ".join(str(value or "").split())


def _strip_business_prefix(text: str) -> str:
    """仅在用户摘要中移除分类标记，保留需求快照中的原始语义和摘要。"""
    prefix = _business_obligation_prefix(text)
    if prefix:
        return text.removeprefix(prefix).strip(" ：:")
    return text


def _render_business_impact_summary(
    obligations: list[dict[str, Any]],
    expected: dict[str, dict[str, Any]],
) -> list[str]:
    """把带固定中文标记的已有业务义务置顶显示，不引入第二套机器协议。"""
    grouped: dict[str, list[tuple[str, str, str, bool]]] = {
        BUSINESS_CHANGE_PREFIX: [],
        BUSINESS_PROTECTION_PREFIX: [],
    }
    for item in obligations:
        identifier = str(item.get("id") or "未知义务")
        text = _single_line(expected.get(identifier, {}).get("text"))
        for prefix in grouped:
            if text.startswith(prefix):
                behavior = _strip_business_prefix(text) or identifier
                raw_status = item.get("status")
                status = user_label(raw_status, OBLIGATION_STATUS_LABELS)
                verified = raw_status in {"COVERED_AUTOMATED", "COVERED_MANUAL"}
                grouped[prefix].append((identifier, behavior, status, verified))
                break

    lines = ["## 已上线业务变更与保护", ""]
    if not any(grouped.values()):
        lines.extend([
            "- 当前确认需求未登记需要修改或重点保护的已上线业务；最终影响仍以实际代码差异审查为准。",
            "",
        ])
        return lines

    headings = {
        BUSINESS_CHANGE_PREFIX: "### 本次明确修改",
        BUSINESS_PROTECTION_PREFIX: "### 必须保持不变",
    }
    for prefix, rows in grouped.items():
        if not rows:
            continue
        lines.extend([headings[prefix], ""])
        for identifier, behavior, status, _ in rows:
            lines.append(f"- `{identifier}` {behavior}（{status}）")
        lines.append("")

    protected = grouped[BUSINESS_PROTECTION_PREFIX]
    verified = sum(is_verified for _, _, _, is_verified in protected)
    lines.extend([
        f"- 已登记旧业务保护项：{len(protected)} 项；已验证 {verified} 项；"
        f"尚未验证或受阻 {len(protected) - verified} 项。",
        "- 详细实现、调用方和测试映射请查看当前需求的 `docs/需求测试追溯.md`。",
        "",
    ])
    return lines


def render_delivery_summary(
    payload: dict[str, Any],
    context: dict[str, Any],
    machine_report_name: str = "delivery-result.json",
) -> str:
    """把已通过结构校验的机器结果转换为不含哈希和证据路径的中文摘要。"""
    obligations = payload.get("obligations", [])
    gates = payload.get("gates", [])
    pending = payload.get("pending_capabilities", [])
    expected = context.get("expected_obligations", {})
    covered = [
        item for item in obligations
        if item.get("status") in {"COVERED_AUTOMATED", "COVERED_MANUAL"}
    ]
    remaining = [
        item for item in obligations
        if item.get("status") in {"UNVERIFIED", "BLOCKED"}
    ]
    not_applicable = [
        item for item in obligations if item.get("status") == "NOT_APPLICABLE"
    ]
    conclusion = payload.get("conclusion", "")
    lines = [
        "# Android 需求交付摘要",
        "",
        f"> 本文件供用户阅读；机器校验附件为 [{machine_report_name}]({machine_report_name})。",
        "",
    ]
    lines.extend(_render_business_impact_summary(obligations, expected))
    lines.extend([
        "## 最终结论",
        "",
        f"**{user_label(conclusion, DELIVERY_CONCLUSION_LABELS)}**",
        "",
        f"- 需求修订：{revision_label(payload.get('requirement_revision', '未知'))}",
        f"- 验收项：共 {len(obligations)} 项，已验证 {len(covered)} 项，"
        f"尚未验证或受阻 {len(remaining)} 项，不适用 {len(not_applicable)} 项",
        "",
        "## 交付门禁",
        "",
    ])
    for item in gates:
        status = item.get("status", "")
        reason = localize_machine_terms(_single_line(item.get("reason")))
        suffix = f" - {reason}" if reason else ""
        lines.append(
            f"- {gate_label(item.get('id'))}："
            f"{user_label(status, GATE_STATUS_LABELS)}{suffix}"
        )

    lines.extend(["", f"## 已验证的需求（{len(covered)} 项）", ""])
    if covered:
        for item in covered:
            identifier = item.get("id", "未知义务")
            text = _strip_business_prefix(
                _single_line(expected.get(identifier, {}).get("text"))
            ) or identifier
            status = user_label(item.get("status"), OBLIGATION_STATUS_LABELS)
            lines.append(f"- `{identifier}` {text}（{status}）")
    else:
        lines.append("- 暂无已验证的需求验收项。")

    lines.extend(["", f"## 尚未完成的需求（{len(remaining)} 项）", ""])
    if remaining:
        for item in remaining:
            identifier = item.get("id", "未知义务")
            text = _strip_business_prefix(
                _single_line(expected.get(identifier, {}).get("text"))
            ) or identifier
            reason = localize_machine_terms(
                _single_line(item.get("reason")) or "机器报告未提供具体原因"
            )
            status = user_label(item.get("status"), OBLIGATION_STATUS_LABELS)
            lines.append(f"- `{identifier}` {text}（{status}）- {reason}")
    else:
        lines.append("- 无。")

    # 未验证项：强制独立段，逼 AI 暴露设备待验、能力缺失等没真正测到的内容。
    unverified = [item for item in obligations if item.get("status") == "UNVERIFIED"]
    lines.extend(["", f"## 未验证项（{len(unverified)} 项）", ""])
    if unverified:
        for item in unverified:
            identifier = item.get("id", "未知义务")
            text = _strip_business_prefix(
                _single_line(expected.get(identifier, {}).get("text"))
            ) or identifier
            reason = localize_machine_terms(
                _single_line(item.get("reason")) or "尚未在实际代码或设备上验证"
            )
            lines.append(f"- `{identifier}` {text} - {reason}")
    else:
        lines.append("- 无。")

    # 残留风险：强制独立段，记录结论通过后仍存在的风险，不粉饰全绿。
    risk_items: list[tuple[str, str]] = []
    for cap in pending:
        name = gate_label(cap.get("id"))
        risk_items.append((name, localize_machine_terms(_single_line(cap.get("reason")) or "等待补充验证证据")))
    for item in remaining:
        identifier = item.get("id", "未知义务")
        risk_items.append((f"`{identifier}`", localize_machine_terms(_single_line(item.get("reason")) or "未在最终代码上完成验证")))
    lines.extend(["", "## 残留风险", ""])
    if risk_items:
        seen_risk: set[tuple[str, str]] = set()
        for name, reason in risk_items:
            if (name, reason) in seen_risk:
                continue
            seen_risk.add((name, reason))
            lines.append(f"- {name}：{reason}")
    else:
        lines.append("- 本结论未保留残留风险项。")

    lines.extend(["", "## 下一步", ""])
    if pending:
        for item in pending:
            name = gate_label(item.get("id"))
            reason = localize_machine_terms(
                _single_line(item.get("reason")) or "等待补充验证证据"
            )
            lines.append(f"- {name}：{reason}")
    elif remaining:
        lines.append("- 完成尚未验证或受阻的必需验收项，并在最终代码上重新生成证据。")
    else:
        lines.append("- 无必需待办；保留本次报告和证据供交付复核。")
    lines.append("")
    return "\n".join(lines)


def write_delivery_summary(
    path: str | Path,
    payload: dict[str, Any],
    context: dict[str, Any],
    machine_report_name: str = "delivery-result.json",
) -> None:
    """原子写入中文摘要，避免中断留下可被用户误读的半份报告。"""
    target = Path(path).expanduser().resolve()
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            render_delivery_summary(payload, context, machine_report_name),
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise DeliveryGateError(f"中文交付摘要无法写入: {target}: {exc}") from exc


def write_generated_traceability(
    path: str | Path,
    payload: dict[str, Any],
    context: dict[str, Any],
) -> None:
    """Refresh the human traceability view after final result validation."""
    from .render_artifacts import render_traceability_md

    snapshot = {
        "requirement_id": context.get("requirement_id"),
        "revision": context.get("requirement_revision"),
        "obligations": [
            {"id": identifier, **item}
            for identifier, item in context.get("expected_obligations", {}).items()
        ],
    }
    mapping_index = context.get("test_mapping")
    mapping = {
        "mappings": list(mapping_index.values())
    } if isinstance(mapping_index, dict) else None
    plan_receipt = None
    receipt_path_value = context.get("plan_receipt_path")
    plan_path = context.get("implementation_plan_path")
    if isinstance(receipt_path_value, str):
        receipt_path = Path(receipt_path_value).resolve()
    elif isinstance(plan_path, str):
        plan_root = Path(plan_path).resolve().parent
        if plan_root.name == "docs":
            plan_root = plan_root.parent
        receipt_path = plan_root / "test-cases" / "implementation-plan-receipt.json"
    else:
        receipt_path = None
    if receipt_path is not None:
        try:
            payload_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload_receipt = None
        if isinstance(payload_receipt, dict):
            plan_receipt = payload_receipt
    try:
        write_text_atomic(
            Path(path).expanduser().resolve(),
            render_traceability_md(snapshot, mapping, payload, plan_receipt),
        )
    except OSError as exc:
        raise DeliveryGateError(f"需求测试追溯表无法写入: {path}: {exc}") from exc


def _summary_path_from_context(context: dict[str, Any], result_path: Path) -> Path:
    """Return the human-readable final report path with compatibility fallback."""
    configured = context.get("summary_path")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve()
    requirement_dir = result_path.resolve().parent.parent
    return (requirement_dir / "docs" / "交付结论.md").resolve()


def main(argv: list[str] | None = None) -> int:
    """输出当前摘要或校验最终报告；返回 0 仅表示最终通过结论真实有效。"""
    parser = ChineseArgumentParser(description="校验 Android 需求交付的最终证据")
    parser.add_argument("command", choices=("snapshot", "validate", "assemble"))
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--result", default=None, help="delivery-result.json 路径")
    parser.add_argument("--manifest", default=None, help="assemble 模式: 产物清单 YAML 路径")
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    try:
        config = load_config(config_path)
        context = current_context(config_path, config)
        if args.command == "snapshot":
            print(json.dumps(context, ensure_ascii=False, indent=2))
            return 0
        if args.command == "assemble":
            return _cmd_assemble(args, config_path, context)
        result_path = Path(args.result).expanduser().resolve() if args.result else Path(context["result_path"])
        payload = load_result(result_path)
        errors = validate_delivery_result(payload, context)
    except (DeliveryError, DeliveryGateError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1

    if errors:
        print("❌ 最终交付门禁未通过:", file=sys.stderr)
        for error in errors:
            print(f"- {localize_machine_terms(error)}", file=sys.stderr)
        return 1
    summary_path = _summary_path_from_context(context, result_path)
    try:
        write_delivery_summary(summary_path, payload, context, result_path.name)
        write_generated_traceability(context["traceability_path"], payload, context)
    except DeliveryGateError as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    print(f"📝 中文交付摘要: {summary_path}")
    if payload["conclusion"] not in PASSING_CONCLUSIONS:
        conclusion = user_label(payload["conclusion"], DELIVERY_CONCLUSION_LABELS)
        print(f"❌ 报告结论：{conclusion}", file=sys.stderr)
        return 2
    print("✅ 最终交付证据与当前需求、Git 基线和代码摘要一致。")
    return 0


def _cmd_assemble(args: argparse.Namespace, config_path: Path, context: dict[str, Any]) -> int:
    """assemble 子命令：从产物清单组装 delivery-result.json 并立即 validate。"""
    from .assemble_result import AssembleError, assemble_delivery_result
    if not args.manifest:
        print("❌ assemble 模式必须提供 --manifest <产物清单 YAML>", file=sys.stderr)
        return 2
    result_path = Path(args.result).expanduser().resolve() if args.result else Path(context["result_path"])
    try:
        payload = assemble_delivery_result(args.manifest, context, result_path)
    except AssembleError as exc:
        print(f"❌ 组装失败: {localize_machine_terms(str(exc))}", file=sys.stderr)
        return 2
    print(f"📦 已组装: {result_path}")
    # 立即 validate
    errors = validate_delivery_result(payload, context)
    if errors:
        print("❌ 组装结果未通过门禁:", file=sys.stderr)
        for error in errors:
            print(f"- {localize_machine_terms(error)}", file=sys.stderr)
        return 1
    summary_path = _summary_path_from_context(context, result_path)
    try:
        write_delivery_summary(summary_path, payload, context, result_path.name)
        write_generated_traceability(context["traceability_path"], payload, context)
    except DeliveryGateError as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    print(f"📝 中文交付摘要: {summary_path}")
    if payload["conclusion"] not in PASSING_CONCLUSIONS:
        conclusion = user_label(payload["conclusion"], DELIVERY_CONCLUSION_LABELS)
        print(f"❌ 报告结论：{conclusion}", file=sys.stderr)
        return 2
    print("✅ assemble + validate 通过")
    return 0
    print("✅ 最终交付证据与当前需求、Git 基线和代码摘要一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
