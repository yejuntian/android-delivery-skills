#!/usr/bin/env python3
"""脚本名称：specialist_result.py

用途：校验 Android 专项审查的最小机器信封、Diff 语义影响、代码质量核心检查，
以及按需附加的动态/Agent 证据。专项结果必须绑定实际自动化测试证据，不能用主观等级替代。

核心流程：统一核对上下文、结论、P0-P3 和稳定未关闭项；Diff Reviewer 逐项确认七类
工程影响，代码质量固定确认四项质量检查，稳定性固定确认静态语义、工具范围和控制面。

职责边界：不执行专项 Skill、不生成审查结论、不运行工程命令、不修代码，只定位
项目外结果目录并验证其他执行者已经产出的结构化结果及其证据文件。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import specialist_directory_for_config  # noqa: E402
from .bdd_scenarios import is_bdd_id  # noqa: E402
from .execution_evidence import redact_command, sha256_file  # noqa: E402
from .static_analysis import (  # noqa: E402
    CONTROL_AUDIT_PRODUCER as STATIC_CONTROL_AUDIT_PRODUCER,
)
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


SPECIALIST_PRODUCER = "android-delivery-specialist-result"
SPECIALIST_RESULT_VERSION = 4
SPECIALIST_CONCLUSIONS = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
CAPABILITY_STATUSES = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
SPECIALIST_FIELDS = {
    "version",
    "producer",
    "id",
    "skill",
    "provenance",
    "requirement_id",
    "requirement_revision",
    "requirement_file_sha256",
    "requirement_inputs_sha256",
    "baseline_id",
    "snapshot_sha256",
    "conclusion",
    "summary",
    "findings",
    "unresolved_findings",
    "static_analysis",
    "confirmed_impacts",
    "capabilities",
    "commands",
    "checks",
    "artifacts",
    "visual_review",
    "device_check",
    "executed_checks",
    "executed_tests",
    "obligation_sha256s",
    "started_at",
    "finished_at",
}
JOURNEY_AGENT_SKILL = "android-test-and-fix/journey-agent"
UI_VERIFY_SKILL = "android-verify-ui"
STABILITY_SKILL = "android-audit-stability"
TEST_AND_FIX_SKILL = "android-test-and-fix"
DIFF_REVIEW_SKILL = "android-review-diff"
CODE_QUALITY_SKILL = "android-review-code-quality"
API_CONTRACT_SKILL = "android-verify-api-contract"
API_CONTRACT_CAPABILITY_ID = "api-contract"
API_CONTRACT_CHECK_IDS = {
    "contract-source",
    "operation-schema",
    "implementation-mapping",
}
# 允许声明产出来源的 Skill 白名单：provenance.skill 必须在此集合内，
# 防止 AI 编造一个不存在的 Skill 名冒充原生专项产出。
KNOWN_SPECIALIST_SKILLS = {
    JOURNEY_AGENT_SKILL,
    STABILITY_SKILL,
    TEST_AND_FIX_SKILL,
    DIFF_REVIEW_SKILL,
    CODE_QUALITY_SKILL,
    API_CONTRACT_SKILL,
    UI_VERIFY_SKILL,
}
CODE_QUALITY_CHECK_IDS = {
    "architecture-layering",
    "responsibility-cohesion",
    "source-documentation",
    "dependency-testability",
}
IMPACT_CATEGORIES = {"ui", "api", "data", "system", "build", "architecture", "tests"}
IMPACT_CONDITIONAL_GATES = {
    "ui": {"android-ui-a11y"},
    "api": {"android-verify-api-contract", "android-security-privacy"},
    "data": {"android-data-migration", "android-security-privacy"},
    "system": {"android-security-privacy"},
}
STABILITY_CAPABILITIES = {
    "android-static-semantics",
    "android-dynamic-leak",
    "android-performance",
    "android-security-privacy",
}
STABILITY_STATIC_CHECK_IDS = {
    "static-short-lifetime-ownership",
    "static-registration-pairing",
    "static-resource-pairing",
    "static-async-lifetime",
    "static-cleanup-reachability",
    "static-concurrency-discipline",
    "static-control-changes",
}
FINDING_ID_PATTERN = re.compile(r"FND-[A-F0-9]{16}")
CONTROL_ID_PATTERN = re.compile(r"CTL-[A-F0-9]{16}")
STATIC_LANGUAGES = {"KOTLIN", "JAVA", "MIXED", "NONE"}
STATIC_TOOL_MODES = {
    "COMPILER", "TYPE_RESOLVED", "SYNTAX_ONLY", "BYTECODE", "DATAFLOW", "UNKNOWN",
}
STATIC_CONTROL_KINDS = {"SUPPRESSION", "BASELINE", "EXCLUSION", "CONFIG"}
STATIC_CONTROL_DECISIONS = {"JUSTIFIED", "REMOVED", "BLOCKING"}

class SpecialistResultError(RuntimeError):
    """表示专项结果文件无法读取或不符合统一结果契约。"""


def _project_relative_path(value: Any) -> bool:
    """专项范围只接受项目相对路径，避免报告绑定其他机器上的任意位置。"""
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _has_unique_values(value: Any) -> bool:
    """安全判断数组唯一性，畸形 object/list 元素只返回失败而不抛出异常。"""
    if not isinstance(value, list):
        return False
    try:
        return len(value) == len(set(value))
    except TypeError:
        return False


def _validate_visual_review(value: Any, conclusion: Any) -> list[str]:
    """校验 UI 专项的轻量视觉结果，不绑定 APK 或本地截图摘要。"""
    errors: list[str] = []
    if value is None:
        if conclusion == "PASS":
            errors.append("android-verify-ui PASS 必须提供 visual_review")
        return errors
    if not isinstance(value, dict):
        return ["visual_review 必须是 object"]
    allowed = {"design_links", "screenshot_links", "diff_links", "dynamic_notes"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append("visual_review 包含未知字段: " + ", ".join(unknown))
    for field in ("design_links", "screenshot_links", "diff_links"):
        links = value.get(field, [])
        if not isinstance(links, list) or not all(
            isinstance(link, str) and link.strip() for link in links
        ):
            errors.append(f"visual_review.{field} 必须是非空字符串数组")
    if conclusion == "PASS":
        for field in ("design_links", "screenshot_links"):
            if not value.get(field):
                errors.append(f"android-verify-ui PASS 必须提供 visual_review.{field}")
    notes = value.get("dynamic_notes")
    if notes is not None and (not isinstance(notes, str) or not notes.strip()):
        errors.append("visual_review.dynamic_notes 必须是非空字符串")
    return errors


def _validate_device_check(value: Any, conclusion: Any) -> list[str]:
    """UI PASS 必须来自可用物理设备，并且真机截图命令已成功。"""
    errors: list[str] = []
    if value is None:
        if conclusion == "PASS":
            errors.append(f"android-verify-ui {conclusion} 必须提供 device_check")
        return errors
    if not isinstance(value, dict):
        return ["device_check 必须是 object"]
    allowed = {"status", "serial", "kind", "screenshot_ok", "reason"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append("device_check 包含未知字段: " + ", ".join(unknown))
    status = value.get("status")
    if status not in {"READY", "UNAVAILABLE", "BLOCKED"}:
        errors.append("device_check.status 必须是 READY、UNAVAILABLE 或 BLOCKED")
        return errors
    if status == "READY":
        if not isinstance(value.get("serial"), str) or not value["serial"].strip():
            errors.append("device_check READY 必须提供 serial")
        if value.get("kind") != "PHYSICAL":
            errors.append("android-verify-ui READY 必须使用 PHYSICAL 设备")
        if value.get("screenshot_ok") is not True:
            errors.append("android-verify-ui READY 必须确认真机截图成功")
    else:
        if not isinstance(value.get("reason"), str) or not value["reason"].strip():
            errors.append(f"device_check {status} 必须说明 reason")
        if conclusion == "PASS":
            errors.append("android-verify-ui PASS 不允许使用未就绪的 device_check")
    return errors


def _validate_static_analysis(
    value: Any,
    conclusion: str,
    unresolved: list[Any],
    context: dict[str, Any],
) -> list[str]:
    """校验稳定性专项的语言范围、工具覆盖、控制面处置和稳定问题编号。"""
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["稳定性专项缺少 static_analysis 机器摘要"]
    expected_fields = {
        "languages",
        "scope_files",
        "tools",
        "control_audit_path",
        "control_audit_sha256",
        "control_changes",
        "finding_ids",
    }
    if set(value) != expected_fields:
        errors.append(
            "static_analysis 必须只包含 languages、scope_files、tools、control_audit_path、"
            "control_audit_sha256、control_changes、finding_ids"
        )

    languages = value.get("languages")
    if (
        not isinstance(languages, list)
        or not languages
        or not _has_unique_values(languages)
        or any(language not in STATIC_LANGUAGES for language in languages)
        or ("NONE" in languages and len(languages) != 1)
    ):
        errors.append("static_analysis.languages 必须是有效且不重复的 Kotlin/Java/混合/无代码范围")
        languages = []
    scope_files = value.get("scope_files")
    if not _has_unique_values(scope_files) or not all(
        _project_relative_path(path) for path in scope_files
    ):
        errors.append("static_analysis.scope_files 必须是唯一的项目相对路径")
        scope_files = []
    if languages and languages != ["NONE"] and not scope_files:
        errors.append("存在 Kotlin/Java 静态范围时必须记录 scope_files")
    if languages == ["NONE"] and scope_files:
        errors.append("languages=NONE 时 scope_files 必须为空")

    tools = value.get("tools")
    if not isinstance(tools, list):
        errors.append("static_analysis.tools 必须是数组")
        tools = []
    seen_tools: set[str] = set()
    allowed_tool_fields = {
        "id", "status", "version", "mode", "scope", "cross_file",
        "reason", "evidence_path", "evidence_sha256",
    }
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            errors.append(f"static_analysis.tools[{index}] 必须是 object")
            continue
        if not set(tool).issubset(allowed_tool_fields):
            errors.append(f"static_analysis.tools[{index}] 包含未知字段")
        tool_id = tool.get("id")
        if not isinstance(tool_id, str) or not tool_id.strip():
            errors.append(f"static_analysis.tools[{index}] 缺少 id")
        elif tool_id in seen_tools:
            errors.append(f"static_analysis.tools 存在重复工具: {tool_id}")
        else:
            seen_tools.add(tool_id)
        status = tool.get("status")
        if status not in CAPABILITY_STATUSES:
            errors.append(f"static_analysis.tools[{index}].status 无效")
        if not isinstance(tool.get("version"), str) or not tool["version"].strip():
            errors.append(f"static_analysis.tools[{index}] 缺少 version，未知时显式写 unknown")
        if tool.get("mode") not in STATIC_TOOL_MODES:
            errors.append(f"static_analysis.tools[{index}].mode 无效")
        scope = tool.get("scope")
        if not _has_unique_values(scope) or not all(
            isinstance(item, str) and item.strip() for item in scope
        ):
            errors.append(f"static_analysis.tools[{index}].scope 必须是唯一字符串数组")
        if tool.get("cross_file") is not None and not isinstance(tool.get("cross_file"), bool):
            errors.append(f"static_analysis.tools[{index}].cross_file 必须是 boolean 或 null")
        if status == "PASS":
            evidence_path = Path(str(tool.get("evidence_path", ""))).expanduser()
            digest = tool.get("evidence_sha256")
            if not evidence_path.is_file() or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                errors.append(f"static_analysis.tools[{index}] 通过时缺少有效证据文件和摘要")
            else:
                try:
                    if sha256_file(evidence_path) != digest:
                        errors.append(f"static_analysis.tools[{index}] 证据文件摘要已变化")
                except OSError as exc:
                    errors.append(f"static_analysis.tools[{index}] 证据文件无法读取: {exc}")
        elif not isinstance(tool.get("reason"), str) or not tool["reason"].strip():
            errors.append(f"static_analysis.tools[{index}] 非通过时必须说明能力损失")

    controls = value.get("control_changes")
    if not isinstance(controls, list):
        errors.append("static_analysis.control_changes 必须是数组")
        controls = []
    seen_controls: set[str] = set()
    for index, control in enumerate(controls):
        if not isinstance(control, dict) or set(control) != {"id", "path", "kind", "decision", "reason"}:
            errors.append(f"static_analysis.control_changes[{index}] 结构无效")
            continue
        identifier = control.get("id")
        if not isinstance(identifier, str) or not CONTROL_ID_PATTERN.fullmatch(identifier):
            errors.append(f"static_analysis.control_changes[{index}].id 无效")
        elif identifier in seen_controls:
            errors.append(f"static_analysis.control_changes 存在重复 id: {identifier}")
        else:
            seen_controls.add(identifier)
        if not _project_relative_path(control.get("path")):
            errors.append(f"static_analysis.control_changes[{index}].path 必须是项目相对路径")
        if control.get("kind") not in STATIC_CONTROL_KINDS:
            errors.append(f"static_analysis.control_changes[{index}].kind 无效")
        if control.get("decision") not in STATIC_CONTROL_DECISIONS:
            errors.append(f"static_analysis.control_changes[{index}].decision 无效")
        if not isinstance(control.get("reason"), str) or not control["reason"].strip():
            errors.append(f"static_analysis.control_changes[{index}] 必须说明处置理由")
        if conclusion == "PASS" and control.get("decision") == "BLOCKING":
            errors.append(f"静态控制面变化 {identifier or index} 仍阻断时不能标记 PASS")

    audit_path_value = value.get("control_audit_path")
    audit_digest = value.get("control_audit_sha256")
    audit_path = Path(str(audit_path_value or "")).expanduser()
    audit_payload: Any = None
    if (
        not isinstance(audit_path_value, str)
        or not audit_path_value.strip()
        or not audit_path.is_absolute()
        or not isinstance(audit_digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", audit_digest)
        or not audit_path.is_file()
    ):
        errors.append("static_analysis 缺少有效的控制面审计文件和摘要")
    else:
        try:
            if sha256_file(audit_path) != audit_digest:
                errors.append("static_analysis 控制面审计文件摘要已变化")
            audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"static_analysis 控制面审计文件无法读取: {exc}")

    if isinstance(audit_payload, dict):
        expected_audit_fields = {
            "version",
            "producer",
            "project_path",
            "baseline_id",
            "snapshot_sha256",
            "warnings",
            "control_changes",
        }
        if set(audit_payload) != expected_audit_fields:
            errors.append("static_analysis 控制面审计字段不完整或包含未知字段")
        if (
            audit_payload.get("version") != 1
            or audit_payload.get("producer") != STATIC_CONTROL_AUDIT_PRODUCER
        ):
            errors.append("static_analysis 控制面审计来源或版本无效")
        if audit_payload.get("baseline_id") != context.get("baseline_id"):
            errors.append("static_analysis 控制面审计不属于当前 Git 基线")
        if audit_payload.get("snapshot_sha256") != context.get("snapshot_sha256"):
            errors.append("static_analysis 控制面审计不是基于当前代码摘要")
        project_path = context.get("project_path")
        if project_path and Path(str(audit_payload.get("project_path", ""))).resolve() != Path(
            str(project_path)
        ).resolve():
            errors.append("static_analysis 控制面审计不属于当前 Android 项目")
        warnings = audit_payload.get("warnings")
        if not isinstance(warnings, list) or any(
            not isinstance(warning, str) for warning in warnings
        ):
            errors.append("static_analysis 控制面审计 warnings 无效")
        elif conclusion == "PASS" and warnings:
            errors.append("static_analysis 控制面审计存在未解决的 Git 收集警告")

        audited_controls = audit_payload.get("control_changes")
        audited_identity: set[tuple[str, str, str]] = set()
        if not isinstance(audited_controls, list):
            errors.append("static_analysis 控制面审计缺少 control_changes")
        else:
            for index, candidate in enumerate(audited_controls):
                if not isinstance(candidate, dict) or set(candidate) != {
                    "id", "path", "kind", "summary",
                }:
                    errors.append(f"控制面审计候选[{index}] 结构无效")
                    continue
                identity = (
                    str(candidate.get("id", "")),
                    str(candidate.get("path", "")),
                    str(candidate.get("kind", "")),
                )
                if (
                    not CONTROL_ID_PATTERN.fullmatch(identity[0])
                    or not _project_relative_path(identity[1])
                    or identity[2] not in STATIC_CONTROL_KINDS
                    or not isinstance(candidate.get("summary"), str)
                    or not candidate["summary"].strip()
                ):
                    errors.append(f"控制面审计候选[{index}] 内容无效")
                if identity in audited_identity:
                    errors.append(f"控制面审计候选重复: {identity[0]}")
                audited_identity.add(identity)
            reported_identity = {
                (str(item.get("id", "")), str(item.get("path", "")), str(item.get("kind", "")))
                for item in controls
                if isinstance(item, dict)
            }
            if audited_identity != reported_identity:
                errors.append("static_analysis.control_changes 与控制面审计候选不一致")
    elif audit_payload is not None:
        errors.append("static_analysis 控制面审计根节点必须是 object")

    finding_ids = value.get("finding_ids")
    if not _has_unique_values(finding_ids) or not all(
        isinstance(identifier, str) and FINDING_ID_PATTERN.fullmatch(identifier)
        for identifier in finding_ids
    ):
        errors.append("static_analysis.finding_ids 必须是唯一的稳定问题编号数组")
        finding_ids = []
    unresolved_ids = {
        item.get("id") for item in unresolved
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    missing_ids = sorted(unresolved_ids - set(finding_ids))
    if missing_ids:
        errors.append("static_analysis.finding_ids 缺少未关闭问题: " + ", ".join(missing_ids))
    return errors


def conditional_gates_from_confirmed_impacts(payload: dict[str, Any]) -> set[str]:
    """把 Diff Reviewer 确认的语义影响映射为最终必须出现的条件门禁。"""
    if payload.get("skill") != DIFF_REVIEW_SKILL:
        return set()
    required_gates: set[str] = set()
    for item in payload.get("confirmed_impacts", []):
        if isinstance(item, dict) and item.get("applicable") is True:
            required_gates.update(IMPACT_CONDITIONAL_GATES.get(item.get("id"), set()))
    return required_gates


def load_specialist_result(path: str | Path) -> dict[str, Any]:
    """读取专项结果 JSON，拒绝损坏文件和非 object 根节点。"""
    target = Path(path).expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpecialistResultError(f"专项结果无法读取: {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecialistResultError(f"专项结果根节点必须是 object: {target}")
    return payload


def validate_specialist_result(
    payload: Any,
    context: dict[str, Any] | None = None,
) -> list[str]:
    """验证统一结果结构、阻断发现和证据摘要；可选绑定当前交付上下文。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["专项结果根节点必须是 object"]
    unknown_fields = sorted(set(payload) - SPECIALIST_FIELDS)
    if unknown_fields:
        errors.append("专项结果包含未知字段: " + ", ".join(unknown_fields))
    if (
        payload.get("version") != SPECIALIST_RESULT_VERSION
        or payload.get("producer") != SPECIALIST_PRODUCER
    ):
        errors.append("专项结果版本或 producer 无效")
    for field in ("id", "skill", "summary"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"专项结果缺少 {field}")
    # provenance（产出来源）：堵"凭空捏造 JSON 不声明来源""张冠李戴""编造假 Skill 名"。
    provenance = payload.get("provenance")
    top_skill = payload.get("skill")
    if not isinstance(provenance, dict):
        errors.append("专项结果缺少 provenance 产出来源声明")
    else:
        prov_skill = provenance.get("skill")
        if not isinstance(prov_skill, str) or not prov_skill.strip():
            errors.append("provenance.skill 必须声明产出该结果的 Skill")
        else:
            if prov_skill not in KNOWN_SPECIALIST_SKILLS:
                errors.append(
                    f"provenance.skill 声明了未知 Skill: {prov_skill}，不允许编造产出来源"
                )
            if (
                isinstance(top_skill, str)
                and top_skill.strip()
                and prov_skill != top_skill
            ):
                errors.append(
                    f"provenance.skill({prov_skill}) 与顶层 skill({top_skill})不一致，"
                    "产出来源与专项声明必须一致"
                )
    for field in ("started_at", "finished_at"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"专项结果 {field} 必须是非空字符串")
    for field in (
        "requirement_id",
        "requirement_file_sha256",
        "requirement_inputs_sha256",
        "baseline_id",
        "snapshot_sha256",
    ):
        if not isinstance(payload.get(field), str) or not payload[field]:
            errors.append(f"专项结果缺少 {field}")
    if not isinstance(payload.get("requirement_revision"), int) or payload["requirement_revision"] < 1:
        errors.append("专项结果 requirement_revision 必须是正整数")
    conclusion = payload.get("conclusion")
    if conclusion not in SPECIALIST_CONCLUSIONS:
        errors.append(f"专项结果 conclusion 必须是 {sorted(SPECIALIST_CONCLUSIONS)} 之一")
    if payload.get("skill") == UI_VERIFY_SKILL:
        errors.extend(_validate_visual_review(payload.get("visual_review"), conclusion))
        errors.extend(_validate_device_check(payload.get("device_check"), conclusion))
    else:
        if payload.get("visual_review") is not None:
            errors.append("只有 android-verify-ui 可以输出 visual_review")
        if payload.get("device_check") is not None:
            errors.append("只有 android-verify-ui 可以输出 device_check")

    findings = payload.get("findings")
    if not isinstance(findings, dict) or set(findings) != SEVERITIES or not all(
        isinstance(count, int) and count >= 0 for count in findings.values()
    ):
        errors.append("专项结果 findings 必须完整记录 P0-P3 非负数量")
        findings = {}
    unresolved = payload.get("unresolved_findings")
    if not isinstance(unresolved, list):
        errors.append("专项结果 unresolved_findings 必须是数组")
        unresolved = []
    for index, item in enumerate(unresolved):
        if not isinstance(item, dict):
            errors.append(f"unresolved_findings[{index}] 必须是 object")
            continue
        if item.get("severity") not in SEVERITIES:
            errors.append(f"unresolved_findings[{index}].severity 无效")
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            errors.append(f"unresolved_findings[{index}] 缺少 summary")
    for severity in SEVERITIES:
        unresolved_count = sum(
            1 for item in unresolved
            if isinstance(item, dict) and item.get("severity") == severity
        )
        if findings and findings.get(severity, 0) < unresolved_count:
            errors.append(f"专项结果 findings.{severity} 小于未关闭项数量")
    if conclusion == "PASS":
        if findings.get("P0", 0) or findings.get("P1", 0):
            errors.append("专项结果存在 P0/P1 时不能标记 PASS")
        if any(item.get("severity") in {"P0", "P1"} for item in unresolved if isinstance(item, dict)):
            errors.append("专项结果仍有未关闭 P0/P1 时不能标记 PASS")

    confirmed_impacts = payload.get("confirmed_impacts")
    if payload.get("skill") == DIFF_REVIEW_SKILL:
        if not isinstance(confirmed_impacts, list):
            errors.append("Diff Reviewer 必须逐项输出 confirmed_impacts")
            confirmed_impacts = []
        seen_impacts: set[str] = set()
        for index, item in enumerate(confirmed_impacts):
            if not isinstance(item, dict):
                errors.append(f"confirmed_impacts[{index}] 必须是 object")
                continue
            if set(item) != {"id", "applicable", "basis_files", "reason"}:
                errors.append(
                    f"confirmed_impacts[{index}] 必须只包含 id、applicable、basis_files、reason"
                )
                continue
            impact_id = item.get("id")
            if impact_id not in IMPACT_CATEGORIES:
                errors.append(f"confirmed_impacts[{index}].id 无效")
            elif impact_id in seen_impacts:
                errors.append(f"confirmed_impacts 存在重复 id: {impact_id}")
            else:
                seen_impacts.add(impact_id)
            applicable = item.get("applicable")
            if not isinstance(applicable, bool):
                errors.append(f"confirmed_impacts[{index}].applicable 必须是 boolean")
            basis_files = item.get("basis_files")
            if not isinstance(basis_files, list) or not all(
                isinstance(path, str) and path.strip() for path in basis_files
            ):
                errors.append(f"confirmed_impacts[{index}].basis_files 必须是字符串数组")
                basis_files = []
            elif len(basis_files) != len(set(basis_files)):
                errors.append(f"confirmed_impacts[{index}].basis_files 不得重复")
            else:
                for path in basis_files:
                    candidate = Path(path)
                    if candidate.is_absolute() or ".." in candidate.parts:
                        errors.append(
                            f"confirmed_impacts[{index}].basis_files 必须使用项目相对路径"
                        )
            if applicable is True and not basis_files:
                errors.append(f"confirmed_impacts[{index}] 适用时必须提供依据文件")
            if applicable is False and basis_files:
                errors.append(f"confirmed_impacts[{index}] 不适用时 basis_files 必须为空")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append(f"confirmed_impacts[{index}] 必须说明 reason")
        missing_impacts = sorted(IMPACT_CATEGORIES - seen_impacts)
        if missing_impacts:
            errors.append("confirmed_impacts 缺少影响类别: " + ", ".join(missing_impacts))
    elif confirmed_impacts is not None:
        errors.append("只有 android-review-diff 可以输出 confirmed_impacts")

    capabilities = payload.get("capabilities", [])
    seen_capabilities: set[str] = set()
    if not isinstance(capabilities, list):
        errors.append("专项结果 capabilities 必须是数组")
        capabilities = []
    else:
        for index, item in enumerate(capabilities):
            if not isinstance(item, dict):
                errors.append(f"capabilities[{index}] 必须是 object")
                continue
            capability_id = item.get("id")
            if not isinstance(capability_id, str) or not capability_id:
                errors.append(f"capabilities[{index}] 缺少 id")
            elif capability_id in seen_capabilities:
                errors.append(f"capabilities 存在重复 id: {capability_id}")
            else:
                seen_capabilities.add(capability_id)
            if item.get("status") not in CAPABILITY_STATUSES:
                errors.append(f"capabilities[{index}].status 无效")
            if not isinstance(item.get("required"), bool):
                errors.append(f"capabilities[{index}].required 必须是 boolean")
            if item.get("status") != "PASS" and (
                not isinstance(item.get("reason"), str) or not item["reason"].strip()
            ):
                errors.append(f"capabilities[{index}] 非通过状态必须说明 reason")
            if conclusion == "PASS" and item.get("required") is True and item.get("status") != "PASS":
                errors.append(f"必需能力 {capability_id or index} 未通过时专项结果不能标记 PASS")
    if payload.get("skill") == STABILITY_SKILL:
        missing_capabilities = sorted(STABILITY_CAPABILITIES - seen_capabilities)
        if missing_capabilities:
            errors.append(
                "稳定性专项缺少能力适用性结论: " + ", ".join(missing_capabilities)
            )
        static_capability = next(
            (
                item for item in capabilities
                if isinstance(item, dict) and item.get("id") == "android-static-semantics"
            ),
            None,
        )
        if not static_capability or static_capability.get("required") is not True:
            errors.append("稳定性专项必须把 android-static-semantics 标记为必需能力")

    commands = payload.get("commands", [])
    if not isinstance(commands, list) or not all(
        isinstance(command, list)
        and command
        and all(isinstance(part, str) and part for part in command)
        for command in commands
    ):
        errors.append("专项结果 commands 必须是参数数组列表")
    else:
        for index, command in enumerate(commands):
            if redact_command(command) != command:
                errors.append(f"专项结果 commands[{index}] 包含未脱敏参数或 URL 查询")
    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        errors.append("专项结果 checks 必须是数组")
        checks = []
    seen_checks: set[str] = set()
    for index, item in enumerate(checks):
        if not isinstance(item, dict):
            errors.append(f"checks[{index}] 必须是 object")
            continue
        check_id = item.get("id")
        if not isinstance(check_id, str) or not check_id:
            errors.append(f"checks[{index}] 缺少 id")
        elif check_id in seen_checks:
            errors.append(f"checks 存在重复 id: {check_id}")
        else:
            seen_checks.add(check_id)
        if not isinstance(item.get("required"), bool):
            errors.append(f"checks[{index}].required 必须是 boolean")
        if item.get("status") not in CAPABILITY_STATUSES:
            errors.append(f"checks[{index}].status 无效")
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            errors.append(f"checks[{index}] 缺少 summary")
        if conclusion == "PASS" and item.get("required") is True and item.get("status") != "PASS":
            errors.append(f"必需检查 {check_id or index} 未通过时专项结果不能标记 PASS")
    executed_checks = payload.get("executed_checks")
    if executed_checks is not None and (
        not isinstance(executed_checks, int) or executed_checks < 0
    ):
        errors.append("专项结果 executed_checks 必须是非负整数")
    elif checks and executed_checks is None:
        errors.append("专项结果包含 checks 时必须填写 executed_checks")
    elif isinstance(executed_checks, int) and executed_checks != len(checks):
        errors.append("专项结果 executed_checks 与 checks 数量不一致")
    if payload.get("skill") == CODE_QUALITY_SKILL:
        missing_quality_checks = sorted(CODE_QUALITY_CHECK_IDS - seen_checks)
        if missing_quality_checks:
            errors.append(
                "代码质量专项缺少必需检查: " + ", ".join(missing_quality_checks)
            )
    if payload.get("skill") == STABILITY_SKILL:
        for index, item in enumerate(unresolved):
            if isinstance(item, dict) and (
                not isinstance(item.get("id"), str)
                or not FINDING_ID_PATTERN.fullmatch(item["id"])
            ):
                errors.append(
                    f"稳定性 unresolved_findings[{index}].id 必须是稳定问题编号 FND-加16位十六进制"
                )
        missing_static_checks = sorted(STABILITY_STATIC_CHECK_IDS - seen_checks)
        if missing_static_checks:
            errors.append(
                "稳定性专项缺少静态语义检查: " + ", ".join(missing_static_checks)
            )
        for item in checks:
            if (
                isinstance(item, dict)
                and item.get("id") in STABILITY_STATIC_CHECK_IDS
                and item.get("required") is not True
            ):
                errors.append(f"稳定性静态语义检查 {item.get('id')} 必须 required=true")
        errors.extend(
            _validate_static_analysis(
                payload.get("static_analysis"),
                str(conclusion),
                unresolved,
                context or payload,
            )
        )
    executed_tests = payload.get("executed_tests")
    if executed_tests is not None and (
        not isinstance(executed_tests, int) or executed_tests < 0
    ):
        errors.append("专项结果 executed_tests 必须是非负整数或 null")

    obligation_hashes = payload.get("obligation_sha256s")
    if not isinstance(obligation_hashes, dict) or not all(
        is_bdd_id(identifier)
        and isinstance(digest, str)
        and re.fullmatch(r"[a-f0-9]{64}", digest)
        for identifier, digest in obligation_hashes.items()
    ):
        errors.append("专项结果 obligation_sha256s 必须是有效 BDD 场景摘要映射")

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("专项结果 artifacts 必须是数组")
    else:
        if payload.get("skill") == UI_VERIFY_SKILL and artifacts:
            errors.append(
                "android-verify-ui 使用 visual_review 链接，不再要求截图或布局文件 SHA-256"
            )
        for index, item in enumerate(artifacts):
            if not isinstance(item, dict):
                errors.append(f"artifacts[{index}] 必须是 object")
                continue
            path = Path(str(item.get("path", ""))).expanduser()
            expected_sha = item.get("sha256")
            if not path.is_file():
                errors.append(f"专项证据文件不存在: {path}")
                continue
            try:
                if sha256_file(path) != expected_sha:
                    errors.append(f"专项证据文件摘要已变化: {path}")
            except OSError as exc:
                errors.append(f"专项证据文件无法读取: {path}: {exc}")

    if payload.get("skill") == API_CONTRACT_SKILL:
        api_contract_capability = next(
            (
                item for item in capabilities
                if isinstance(item, dict) and item.get("id") == API_CONTRACT_CAPABILITY_ID
            ),
            None,
        )
        if not api_contract_capability or api_contract_capability.get("required") is not True:
            errors.append("API 契约专项必须把 api-contract 标记为必需能力")
        api_checks_by_id = {
            item.get("id"): item
            for item in checks
            if isinstance(item, dict) and item.get("id") in API_CONTRACT_CHECK_IDS
        }
        missing_api_checks = sorted(API_CONTRACT_CHECK_IDS - seen_checks)
        if missing_api_checks:
            errors.append(
                "API 契约专项缺少必需检查: " + ", ".join(missing_api_checks)
            )
        for check_id, item in sorted(api_checks_by_id.items()):
            if item.get("required") is not True:
                errors.append(f"API 契约专项检查 {check_id} 必须 required=true")
        if conclusion == "PASS":
            api_status = context.get("api_contract_status") if context else None
            if api_status is not None and api_status != "confirmed":
                errors.append(
                    f"API 契约资料状态为 {api_status}，只有 profile api.status=confirmed 才能标记 PASS"
                )
            if not api_contract_capability or api_contract_capability.get("status") != "PASS":
                errors.append("API 契约专项 PASS 必须有已通过的 api-contract 能力")
            if missing_api_checks:
                errors.append("API 契约专项 PASS 必须完成契约来源、operation/schema 和实现映射检查")
            for check_id, item in sorted(api_checks_by_id.items()):
                if item.get("status") != "PASS":
                    errors.append(f"API 契约专项 PASS 必须通过检查 {check_id}")
            if not artifacts:
                errors.append("API 契约专项 PASS 必须附带正式契约或核对结果 artifact")
            elif any(
                isinstance(item, dict)
                and any(marker in str(item.get("kind", "")).lower() for marker in ("mock", "fake"))
                for item in artifacts
            ):
                errors.append("API 契约专项 PASS 不能使用 mock/fake artifact 作为正式契约证据")

    if payload.get("skill") == JOURNEY_AGENT_SKILL:
        if not any(
            isinstance(item, dict)
            and item.get("id") == "journey"
            and item.get("required") is True
            and item.get("status") == "PASS"
            for item in capabilities
        ):
            errors.append("Journey Agent 缺少已通过的必需 Journey 能力")
        if not commands or not checks or not artifacts:
            errors.append("Journey Agent 缺少命令、action 检查或布局/截图产物")
        if (
            not isinstance(executed_tests, int)
            or executed_tests <= 0
            or not isinstance(executed_checks, int)
            or executed_checks <= 0
        ):
            errors.append("Journey Agent 没有真实 Journey 或 action 执行数量")
        if not payload.get("started_at") or not payload.get("finished_at"):
            errors.append("Journey Agent 缺少执行起止时间")

    if context:
        for field in (
            "requirement_id",
            "requirement_revision",
            "requirement_file_sha256",
            "requirement_inputs_sha256",
            "baseline_id",
            "snapshot_sha256",
        ):
            if payload.get(field) != context.get(field):
                errors.append(f"专项结果 {field} 与当前需求或代码不一致")
    return errors


def validate_specialist_evidence(
    path: str | Path,
    expected_sha256: str,
    evidence: dict[str, Any],
    context: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    """校验最终报告引用的专项文件，并返回其内容供 gate 核对负责 Skill。"""
    target = Path(path).expanduser().resolve()
    try:
        actual_sha = sha256_file(target)
        payload = load_specialist_result(target)
    except (OSError, SpecialistResultError) as exc:
        return [str(exc)], None
    errors = validate_specialist_result(payload, context)
    if actual_sha != expected_sha256:
        errors.append(f"专项证据 {evidence.get('id')} 的结果文件摘要不一致")
    if payload.get("id") != evidence.get("id"):
        errors.append(f"专项证据 {evidence.get('id')} 与结果文件 id 不一致")
    if payload.get("skill") != evidence.get("specialist"):
        errors.append(f"专项证据 {evidence.get('id')} 的 specialist 与结果文件不一致")
    if payload.get("summary") != evidence.get("summary"):
        errors.append(f"专项证据 {evidence.get('id')} 的 summary 与结果文件不一致")
    if payload.get("obligation_sha256s") != evidence.get("obligation_sha256s", {}):
        errors.append(f"专项证据 {evidence.get('id')} 的义务映射与结果文件不一致")
    if evidence.get("kind") == "AGENT":
        if payload.get("executed_tests") != evidence.get("executed_tests"):
            errors.append(f"Agent 证据 {evidence.get('id')} 的 executed_tests 与专项结果不一致")
    return errors, payload


def main(argv: list[str] | None = None) -> int:
    """输出外部结果目录，或独立校验一个专项结果及其证据摘要。"""
    parser = ChineseArgumentParser(description="管理 Android 专项统一结果")
    subparsers = parser.add_subparsers(dest="command", required=True)
    path_parser = subparsers.add_parser("path", help="输出当前配置的外部专项结果目录")
    path_parser.add_argument("--config", default=None, help="配置文件路径")
    validate_parser = subparsers.add_parser("validate", help="校验专项结果")
    validate_parser.add_argument("result", help="specialist-result.json 路径")
    args = parser.parse_args(argv)
    if args.command == "path":
        config_path = Path(args.config).expanduser().resolve() if args.config else (
            Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
        )
        # 延迟导入避免最终门禁加载专项校验器时形成模块循环。
        from .delivery import DeliveryError, load_config
        from .delivery_gate import DeliveryGateError, current_context

        try:
            context = current_context(config_path, load_config(config_path))
            directory = specialist_directory_for_config(
                config_path,
                str(context["requirement_id"]),
                int(context["requirement_revision"]),
                str(context["snapshot_sha256"]),
                str(context["requirement_inputs_sha256"]),
            )
            directory.mkdir(parents=True, exist_ok=True)
        except (DeliveryError, DeliveryGateError, OSError) as exc:
            print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
            return 1
        print(directory)
        return 0
    try:
        payload = load_specialist_result(args.result)
        errors = validate_specialist_result(payload)
    except SpecialistResultError as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    if errors:
        print("❌ 专项结果无效:", file=sys.stderr)
        for error in errors:
            print(f"- {localize_machine_terms(error)}", file=sys.stderr)
        return 1
    print("✅ 专项结果结构、阻断发现和证据文件有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
