#!/usr/bin/env python3
"""脚本名称：specialist_result.py

用途：校验 Android 专项审查的最小机器信封、Diff 语义影响、代码质量核心检查，
以及按需附加的动态/Agent 证据。

核心流程：统一核对上下文、结论、P0-P3 和未关闭项；Diff Reviewer 逐项确认七类
工程影响，代码质量审查固定确认分层、职责、核心注释和可测试性，其他专项按需扩展。

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
from .execution_evidence import redact_command, sha256_file  # noqa: E402
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


SPECIALIST_PRODUCER = "android-delivery-specialist-result"
SPECIALIST_RESULT_VERSION = 3
SPECIALIST_CONCLUSIONS = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
CAPABILITY_STATUSES = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
JOURNEY_AGENT_SKILL = "android-test-and-fix/journey-agent"
STABILITY_SKILL = "android-audit-stability"
DIFF_REVIEW_SKILL = "android-review-diff"
CODE_QUALITY_SKILL = "android-review-code-quality"
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
    "android-dynamic-leak",
    "android-performance",
    "android-security-privacy",
}


class SpecialistResultError(RuntimeError):
    """表示专项结果文件无法读取或不符合统一结果契约。"""


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
    if (
        payload.get("version") != SPECIALIST_RESULT_VERSION
        or payload.get("producer") != SPECIALIST_PRODUCER
    ):
        errors.append("专项结果版本或 producer 无效")
    for field in ("id", "skill", "summary"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"专项结果缺少 {field}")
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
    executed_tests = payload.get("executed_tests")
    if executed_tests is not None and (
        not isinstance(executed_tests, int) or executed_tests < 0
    ):
        errors.append("专项结果 executed_tests 必须是非负整数或 null")

    obligation_hashes = payload.get("obligation_sha256s")
    if not isinstance(obligation_hashes, dict) or not all(
        isinstance(identifier, str)
        and re.fullmatch(r"BDD-[0-9]+/T[0-9]+", identifier)
        and isinstance(digest, str)
        and re.fullmatch(r"[a-f0-9]{64}", digest)
        for identifier, digest in obligation_hashes.items()
    ):
        errors.append("专项结果 obligation_sha256s 必须是有效 BDD/Then 摘要映射")

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("专项结果 artifacts 必须是数组")
    else:
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
