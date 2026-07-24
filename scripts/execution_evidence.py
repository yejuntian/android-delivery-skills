#!/usr/bin/env python3
"""脚本名称：execution_evidence.py

用途：执行一条 Android 交付命令并生成可复核的机器收据。

核心流程：在当前确认需求和最新 route 快照上为一个 gate 运行命令，把标准输出、
错误输出、testcase、Lint/通用 SARIF 报告和代码摘要写到不可覆盖 attempt；最终门禁重新校验收据。

职责边界：只执行用户或 Skill 已经选择的命令，不选择 Gradle task、不判断业务、
不修代码、不调用其他 Skill，也不执行 Git 写操作。退出码沿用命令结果；证据缺失返回 3，
执行期间代码摘要变化返回 4，超时返回 124。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import (  # noqa: E402
    baseline_path_for_config,
    evidence_directory_for_config,
    evidence_scope_directory,
    resolve_config_paths,
)
from .delivery import DeliveryError, load_config  # noqa: E402
from .git_changes import GitInspectionError, current_delivery_snapshot  # noqa: E402
from .static_analysis import StaticAnalysisError, summarize_sarif  # noqa: E402
from .user_facing_labels import (  # noqa: E402
    ChineseArgumentParser,
    gate_label,
    localize_machine_terms,
)


RECEIPT_PRODUCER = "android-delivery-execution-evidence"
RECEIPT_VERSION = 3
RECEIPT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
KNOWN_EVIDENCE_GATES = {
    "android-test-and-fix",
    "android-build",
    "android-lint",
    "android-static-analysis",
    "android-verify-api-contract",
    "android-data-migration",
    "android-ui-a11y",
    "android-security-privacy",
    "android-dynamic-leak",
    "android-performance",
}
JUNIT_REQUIRED_GATES = {
    "android-test-and-fix",
    "android-data-migration",
}
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(token|password|passwd|secret|api[-_]?key|authorization|cookie|credential|private[-_]?key|jwt)"
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<prefix>[\"']?(?:access[-_]?token|refresh[-_]?token|id[-_]?token|client[-_]?secret|"
    r"private[-_]?key|api[-_]?key|authorization|proxy[-_]?authorization|password|passwd|"
    r"secret|cookie|credential|jwt|token)[\"']?\s*[:=]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\"'\s,;}]+)(?P=quote)"
)
SENSITIVE_HEADER_PATTERN = re.compile(
    r"(?im)^(?P<prefix>\s*(?:authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|x-auth-token)\s*:\s*).+$"
)
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
URL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>]+")


class ExecutionEvidenceError(RuntimeError):
    """表示命令无法安全启动、收据无法写入或收据内容不可验证。"""


def _is_sarif_report(path: Path) -> bool:
    """识别常见 ``.sarif`` 与 ``.sarif.json``，不根据文件正文猜测格式。"""
    lowered_name = path.name.lower()
    return lowered_name.endswith(".sarif") or lowered_name.endswith(".sarif.json")


def sha256_file(path: str | Path) -> str:
    """流式计算文件摘要，避免大型测试报告或日志一次性读入内存。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_url(value: str) -> str:
    """移除 URL 查询参数和用户信息，避免 DeepLink、Token 或密码进入收据。"""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or (not parsed.netloc and "?" not in value):
        return value
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "<redacted>" if parsed.query else "", ""))


def redact_command(command: list[str]) -> list[str]:
    """保留可复现命令结构，同时遮蔽敏感选项值和 URL 查询参数。"""
    redacted: list[str] = []
    hide_next = False
    for part in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        if "://" in part:
            redacted.append(_redact_url(part))
            continue
        if part.startswith("--") and "=" in part:
            key, value = part.split("=", 1)
            if SENSITIVE_KEY_PATTERN.search(key):
                redacted.append(f"{key}=<redacted>")
                continue
            redacted.append(f"{key}={_redact_url(value)}")
            continue
        if part.startswith("--") and SENSITIVE_KEY_PATTERN.search(part):
            redacted.append(part)
            hide_next = True
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            if SENSITIVE_KEY_PATTERN.search(key):
                redacted.append(f"{key}=<redacted>")
                continue
            redacted.append(f"{key}={_redact_url(value)}")
            continue
        redacted.append(redact_output(_redact_url(part)))
    return redacted


def redact_output(raw: bytes | str | None) -> str:
    """脱敏外部命令输出后再落盘，避免工具回显凭据或 DeepLink 查询参数。"""
    if raw is None:
        return ""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = PRIVATE_KEY_PATTERN.sub("<redacted-private-key>", text)
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer <redacted>", text)
    text = SENSITIVE_HEADER_PATTERN.sub(
        lambda match: f"{match.group('prefix')}<redacted>",
        text,
    )
    text = SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}<redacted>{match.group('quote')}",
        text,
    )
    return URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), text)


def _write_text_private(path: Path, content: str) -> None:
    """以仅当前用户可读写的权限落盘日志，避免多用户机器泄露测试输出。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(content)
    except Exception:
        # fdopen 接管 descriptor；异常时由上下文负责关闭。
        raise


def _file_record(path: Path, started_epoch: float | None = None) -> dict[str, Any]:
    """记录文件位置、大小、摘要与新鲜度；文件不存在时保留失败事实。"""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return {"path": str(resolved), "exists": False, "fresh": False}
    stat = resolved.stat()
    # 文件系统时间戳可能只有秒级精度，允许两秒误差但不接受明显旧报告。
    fresh = started_epoch is None or stat.st_mtime >= started_epoch - 2
    return {
        "path": str(resolved),
        "exists": True,
        "fresh": fresh,
        "size": stat.st_size,
        "sha256": sha256_file(resolved),
    }


def _junit_summary(path: Path) -> dict[str, Any] | None:
    """汇总 JUnit 数量与真实 testcase 标识，供 Then 建立可复核映射。"""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "testsuite":
        suites = [root]
    elif tag == "testsuites":
        suites = [child for child in root if child.tag.rsplit("}", 1)[-1] == "testsuite"]
        if all(field in root.attrib for field in ("tests", "failures", "errors")):
            suites = [root]
    else:
        return None
    summary: dict[str, Any] = {
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "test_cases": [],
    }
    for suite in suites:
        try:
            summary["tests"] += int(suite.attrib["tests"])
            summary["failures"] += int(suite.attrib.get("failures", "0"))
            summary["errors"] += int(suite.attrib.get("errors", "0"))
            summary["skipped"] += int(suite.attrib.get("skipped", "0"))
        except (KeyError, ValueError):
            return None
    summary["executed"] = max(0, summary["tests"] - summary["skipped"])
    seen_ids: set[str] = set()
    for testcase in root.iter():
        if testcase.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        name = testcase.attrib.get("name", "").strip()
        classname = testcase.attrib.get("classname", "").strip()
        if not name:
            continue
        base_id = f"{classname}#{name}" if classname else name
        identifier = base_id
        suffix = 2
        while identifier in seen_ids:
            identifier = f"{base_id}#{suffix}"
            suffix += 1
        seen_ids.add(identifier)
        child_tags = {child.tag.rsplit("}", 1)[-1] for child in testcase}
        status = (
            "ERROR" if "error" in child_tags
            else "FAIL" if "failure" in child_tags
            else "SKIPPED" if "skipped" in child_tags
            else "PASS"
        )
        summary["test_cases"].append({
            "id": identifier,
            "classname": classname,
            "name": name,
            "status": status,
        })
    return summary


def _android_lint_summary(path: Path) -> dict[str, Any] | None:
    """解析 Android Lint XML 或 SARIF，防止 ``abortOnError=false`` 隐藏真实错误。"""
    try:
        if _is_sarif_report(path):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
                return None
            levels = {"error": 0, "warning": 0, "note": 0, "none": 0}
            total = 0
            for run in payload["runs"]:
                if not isinstance(run, dict):
                    continue
                rule_levels: dict[str, str] = {}
                driver = ((run.get("tool") or {}).get("driver") or {})
                for rule in driver.get("rules", []) if isinstance(driver, dict) else []:
                    if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
                        continue
                    default = rule.get("defaultConfiguration") or {}
                    if isinstance(default, dict) and isinstance(default.get("level"), str):
                        rule_levels[rule["id"]] = default["level"].lower()
                results = run.get("results", [])
                if not isinstance(results, list):
                    continue
                for result in results:
                    if not isinstance(result, dict):
                        continue
                    level = str(result.get("level") or rule_levels.get(str(result.get("ruleId")), "warning")).lower()
                    levels[level if level in levels else "warning"] += 1
                    total += 1
            return {
                "format": "SARIF",
                "fatal": 0,
                "errors": levels["error"],
                "warnings": levels["warning"],
                "information": levels["note"] + levels["none"],
                "total": total,
            }

        root = ET.parse(path).getroot()
    except (OSError, UnicodeError, json.JSONDecodeError, ET.ParseError):
        return None
    if root.tag.rsplit("}", 1)[-1] != "issues":
        return None
    counts = {"fatal": 0, "errors": 0, "warnings": 0, "information": 0}
    total = 0
    for issue in root.iter():
        if issue.tag.rsplit("}", 1)[-1] != "issue":
            continue
        severity = issue.attrib.get("severity", "Warning").strip().lower()
        if severity == "fatal":
            counts["fatal"] += 1
        elif severity == "error":
            counts["errors"] += 1
        elif severity == "warning":
            counts["warnings"] += 1
        else:
            counts["information"] += 1
        total += 1
    return {"format": "XML", **counts, "total": total}


def _gradle_tasks(command: list[str]) -> list[str]:
    """提取直接 Gradle 调用中的 task 参数；不解析 shell 字符串或猜测别名。"""
    if not command:
        return []
    executable = Path(command[0]).name.lower()
    if executable not in {"gradle", "gradlew", "gradlew.bat"}:
        return []
    return [
        part
        for part in command[1:]
        if not part.startswith("-") and re.fullmatch(r"(?::?[A-Za-z0-9_.-]+)+", part)
    ]


def _gate_command_errors(gate_id: str, command: list[str]) -> list[str]:
    """对可确定的构建/Lint gate 校验 Gradle task，其余语义由报告和专项证据证明。"""
    if gate_id not in {"android-build", "android-lint"}:
        return []
    tasks = _gradle_tasks(command)
    prefixes = ("assemble", "bundle") if gate_id == "android-build" else ("lint",)
    if any(task.rsplit(":", 1)[-1].lower().startswith(prefixes) for task in tasks):
        return []
    expected = "assemble/bundle" if gate_id == "android-build" else "lint"
    return [f"{gate_id} 必须直接执行目标项目真实的 {expected} Gradle task"]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """代理到公共原子写；统一行为与 0600 权限。"""
    from .atomic_write import write_json_atomic
    try:
        write_json_atomic(path, payload)
    except OSError as exc:
        raise ExecutionEvidenceError(f"执行收据无法写入: {path}: {exc}") from exc


def load_execution_receipt(path: str | Path) -> dict[str, Any]:
    """读取执行收据；损坏或非 object 内容作为门禁错误返回。"""
    target = Path(path).expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionEvidenceError(f"执行收据无法读取: {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExecutionEvidenceError(f"执行收据根节点必须是 object: {target}")
    return payload


def validate_execution_receipt(
    path: str | Path,
    expected_sha256: str,
    evidence: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    """复核收据、日志和报告摘要，确保自动证据属于当前需求和最终代码。"""
    errors: list[str] = []
    target = Path(path).expanduser().resolve()
    try:
        actual_receipt_sha = sha256_file(target)
        receipt = load_execution_receipt(target)
    except (OSError, ExecutionEvidenceError) as exc:
        return [str(exc)]
    if actual_receipt_sha != expected_sha256:
        errors.append(f"自动证据 {evidence.get('id')} 的执行收据摘要不一致")
    if receipt.get("version") != RECEIPT_VERSION or receipt.get("producer") != RECEIPT_PRODUCER:
        errors.append(f"自动证据 {evidence.get('id')} 的执行收据来源无效")
    if receipt.get("id") != evidence.get("id"):
        errors.append(f"自动证据 {evidence.get('id')} 与执行收据 id 不一致")
    gate_id = receipt.get("gate_id")
    if gate_id not in KNOWN_EVIDENCE_GATES:
        errors.append(f"自动证据 {evidence.get('id')} 的收据 gate_id 无效")
    if gate_id != evidence.get("gate_id"):
        errors.append(f"自动证据 {evidence.get('id')} 的 gate_id 与收据不一致")
    if not isinstance(receipt.get("attempt"), int) or receipt["attempt"] < 1:
        errors.append(f"自动证据 {evidence.get('id')} 的 attempt 无效")
    for field in (
        "requirement_id",
        "requirement_revision",
        "requirement_file_sha256",
        "requirement_inputs_sha256",
        "baseline_id",
    ):
        if receipt.get(field) != context.get(field):
            errors.append(f"自动证据 {evidence.get('id')} 的收据 {field} 已失效")
    if receipt.get("snapshot_sha256_before") != context.get("snapshot_sha256"):
        errors.append(f"自动证据 {evidence.get('id')} 不是在当前 route 代码上启动")
    if receipt.get("snapshot_sha256_after") != context.get("snapshot_sha256"):
        errors.append(f"自动证据 {evidence.get('id')} 执行后代码摘要已变化")
    if receipt.get("command") != evidence.get("command"):
        errors.append(f"自动证据 {evidence.get('id')} 的 command 与收据不一致")
    if isinstance(gate_id, str):
        errors.extend(
            f"自动证据 {evidence.get('id')}: {message}"
            for message in _gate_command_errors(gate_id, receipt.get("command", []))
        )
    if receipt.get("exit_code") != evidence.get("exit_code"):
        errors.append(f"自动证据 {evidence.get('id')} 的 exit_code 与收据不一致")
    if receipt.get("executed_tests") != evidence.get("executed_tests"):
        errors.append(f"自动证据 {evidence.get('id')} 的 executed_tests 与收据不一致")
    if not isinstance(receipt.get("command_sha256"), str) or not re.fullmatch(
        r"[a-f0-9]{64}", receipt["command_sha256"]
    ):
        errors.append(f"自动证据 {evidence.get('id')} 的原始命令摘要无效")
    if receipt.get("timed_out") is not False or receipt.get("exit_code") != 0:
        errors.append(f"自动证据 {evidence.get('id')} 的命令未正常完成")
    if not isinstance(receipt.get("timeout_seconds"), int) or receipt["timeout_seconds"] <= 0:
        errors.append(f"自动证据 {evidence.get('id')} 的 timeout_seconds 无效")
    try:
        started_at = datetime.fromisoformat(str(receipt.get("started_at")))
        finished_at = datetime.fromisoformat(str(receipt.get("finished_at")))
        if finished_at < started_at:
            errors.append(f"自动证据 {evidence.get('id')} 的执行时间顺序无效")
    except (TypeError, ValueError):
        errors.append(f"自动证据 {evidence.get('id')} 的执行时间格式无效")
    project_path = context.get("project_path")
    if project_path:
        try:
            Path(str(receipt.get("cwd", ""))).resolve().relative_to(Path(project_path).resolve())
        except ValueError:
            errors.append(f"自动证据 {evidence.get('id')} 的 cwd 不在当前 Android 项目内")

    receipt_reports = receipt.get("reports", [])
    if not isinstance(receipt_reports, list):
        errors.append(f"自动证据 {evidence.get('id')} 的收据 reports 无效")
        receipt_reports = []
    expected_report_paths = [item.get("path") for item in receipt_reports if isinstance(item, dict)]
    if evidence.get("report_paths", []) != expected_report_paths:
        errors.append(f"自动证据 {evidence.get('id')} 的 report_paths 与收据不一致")
    junit_executed = 0
    junit_records = 0
    passed_test_cases: set[str] = set()
    lint_records = 0
    lint_blocking = 0
    static_records = 0
    static_blocking = 0
    for record in receipt_reports:
        if not isinstance(record, dict):
            errors.append(f"自动证据 {evidence.get('id')} 包含无效报告记录")
            continue
        report_path = Path(str(record.get("path", ""))).expanduser()
        if not record.get("exists") or not report_path.is_file():
            errors.append(f"自动证据 {evidence.get('id')} 的报告不存在: {report_path}")
            continue
        if not record.get("fresh"):
            errors.append(f"自动证据 {evidence.get('id')} 的报告早于本次命令: {report_path}")
        try:
            if sha256_file(report_path) != record.get("sha256"):
                errors.append(f"自动证据 {evidence.get('id')} 的报告摘要已变化: {report_path}")
        except OSError as exc:
            errors.append(f"自动证据 {evidence.get('id')} 的报告无法读取: {exc}")
        junit = record.get("junit")
        if isinstance(junit, dict):
            junit_records += 1
            executed = junit.get("executed")
            if isinstance(executed, int):
                junit_executed += executed
            if (
                junit.get("failures", 0) > 0
                or junit.get("errors", 0) > 0
                or not isinstance(executed, int)
                or executed <= 0
            ):
                errors.append(f"自动证据 {evidence.get('id')} 的 JUnit 报告存在失败或零执行: {report_path}")
            actual_junit = _junit_summary(report_path)
            if actual_junit != junit:
                errors.append(f"自动证据 {evidence.get('id')} 的 JUnit 汇总与报告不一致: {report_path}")
            for testcase in junit.get("test_cases", []):
                if isinstance(testcase, dict) and testcase.get("status") == "PASS":
                    identifier = testcase.get("id")
                    if isinstance(identifier, str) and identifier:
                        passed_test_cases.add(identifier)
        lint = record.get("android_lint")
        if isinstance(lint, dict):
            lint_records += 1
            actual_lint = _android_lint_summary(report_path)
            if actual_lint != lint:
                errors.append(f"自动证据 {evidence.get('id')} 的 Android Lint 汇总与报告不一致: {report_path}")
            lint_counts: dict[str, int] = {}
            for field in ("fatal", "errors", "warnings", "information", "total"):
                value = lint.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(
                        f"自动证据 {evidence.get('id')} 的 Android Lint 汇总字段无效: {field}"
                    )
                    continue
                lint_counts[field] = value
            if "fatal" in lint_counts and "errors" in lint_counts:
                lint_blocking += lint_counts["fatal"] + lint_counts["errors"]
        static_analysis = record.get("static_analysis")
        if isinstance(static_analysis, dict):
            static_records += 1
            try:
                actual_static = summarize_sarif(report_path, project_path)
            except StaticAnalysisError as exc:
                errors.append(f"自动证据 {evidence.get('id')} 的 SARIF 报告无法复核: {exc}")
                actual_static = None
            if actual_static != static_analysis:
                errors.append(f"自动证据 {evidence.get('id')} 的静态分析汇总与报告不一致: {report_path}")
            blocking = static_analysis.get("blocking_errors")
            if not isinstance(blocking, int) or isinstance(blocking, bool) or blocking < 0:
                errors.append(f"自动证据 {evidence.get('id')} 的静态分析 blocking_errors 字段无效")
            else:
                static_blocking += blocking
    receipt_test_count = receipt.get("executed_tests")
    if isinstance(receipt_test_count, int) and (
        junit_records == 0 or junit_executed != receipt_test_count
    ):
        errors.append(f"自动证据 {evidence.get('id')} 的测试数没有匹配的 JUnit 汇总")
    if gate_id in JUNIT_REQUIRED_GATES and (
        junit_records == 0
        or not isinstance(receipt_test_count, int)
        or isinstance(receipt_test_count, bool)
        or receipt_test_count <= 0
    ):
        errors.append(
            f"自动证据 {evidence.get('id')} 的 {gate_id} gate 缺少实际执行大于零的 JUnit 报告"
        )
    obligation_test_cases = evidence.get("obligation_test_cases", {})
    if not isinstance(obligation_test_cases, dict):
        errors.append(f"自动证据 {evidence.get('id')}.obligation_test_cases 必须是映射")
    else:
        for obligation_id, testcase_ids in obligation_test_cases.items():
            if not isinstance(obligation_id, str) or not re.fullmatch(r"BDD-[0-9]+/T[0-9]+", obligation_id):
                errors.append(f"自动证据 {evidence.get('id')} 包含无效 obligation_test_cases key")
                continue
            if not isinstance(testcase_ids, list) or not testcase_ids or not all(
                isinstance(testcase_id, str) and testcase_id for testcase_id in testcase_ids
            ):
                errors.append(f"自动证据 {evidence.get('id')} 对 {obligation_id} 缺少具体 testcase")
                continue
            missing_cases = sorted(set(testcase_ids) - passed_test_cases)
            if missing_cases:
                errors.append(
                    f"自动证据 {evidence.get('id')} 对 {obligation_id} 引用了未通过或不存在的 testcase: "
                    + ", ".join(missing_cases)
                )
    if gate_id == "android-lint":
        if lint_records == 0:
            errors.append(f"自动证据 {evidence.get('id')} 缺少 Android Lint XML/SARIF 机器报告")
        if lint_blocking > 0:
            errors.append(f"自动证据 {evidence.get('id')} 的 Android Lint 报告仍有 Fatal/Error")
    if gate_id == "android-static-analysis":
        if static_records == 0:
            errors.append(f"自动证据 {evidence.get('id')} 缺少可解析的 SARIF 机器报告")
        if static_blocking > 0:
            errors.append(
                f"自动证据 {evidence.get('id')} 的静态分析报告仍有新增、更新或来源不明 Error"
            )

    for log_name in ("stdout", "stderr"):
        record = receipt.get(log_name)
        if not isinstance(record, dict):
            errors.append(f"自动证据 {evidence.get('id')} 缺少 {log_name} 日志记录")
            continue
        log_path = Path(str(record.get("path", ""))).expanduser()
        try:
            if not log_path.is_file() or sha256_file(log_path) != record.get("sha256"):
                errors.append(f"自动证据 {evidence.get('id')} 的 {log_name} 日志缺失或已变化")
        except OSError as exc:
            errors.append(f"自动证据 {evidence.get('id')} 的 {log_name} 日志无法读取: {exc}")
    return errors


def _resolve_reports(raw_paths: list[str], cwd: Path) -> list[Path]:
    """按命令目录解析显式报告路径，不搜索或猜测其他构建产物。"""
    reports: list[Path] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (cwd / candidate).resolve()
        if resolved not in reports:
            reports.append(resolved)
    return reports


def _allocate_attempt_directory(receipt_root: Path, evidence_id: str) -> tuple[int, Path]:
    """原子分配递增 attempt 目录，确保失败重跑永不覆盖上一轮证据。"""
    evidence_root = receipt_root / evidence_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_root.chmod(0o700)
    for attempt in range(1, 10000):
        candidate = evidence_root / f"attempt-{attempt:03d}"
        try:
            candidate.mkdir(mode=0o700)
        except FileExistsError:
            continue
        return attempt, candidate
    raise ExecutionEvidenceError(f"证据 {evidence_id} 的 attempt 数量异常，拒绝覆盖历史收据")


def run_and_record(
    *,
    evidence_id: str,
    gate_id: str,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
    reports: list[Path],
    context: dict[str, Any],
    project_path: Path,
    baseline_path: Path,
    receipt_dir: Path,
) -> tuple[dict[str, Any], Path, int]:
    """运行命令并落盘收据；返回收据、路径和收集器最终退出码。"""
    cwd = cwd.expanduser().resolve()
    project_path = project_path.expanduser().resolve()
    baseline_path = baseline_path.expanduser().resolve()
    receipt_dir = receipt_dir.expanduser().resolve()
    receipt_dir = evidence_scope_directory(
        receipt_dir,
        str(context["requirement_id"]),
        int(context["requirement_revision"]),
        str(context["snapshot_sha256"]),
        str(context["requirement_inputs_sha256"]),
    )
    if not RECEIPT_ID_PATTERN.fullmatch(evidence_id):
        raise ExecutionEvidenceError("证据 id 只能使用字母、数字、点、下划线和短横线，最长 80 位")
    if gate_id not in KNOWN_EVIDENCE_GATES:
        raise ExecutionEvidenceError(f"未知 gate_id: {gate_id}")
    if not command:
        raise ExecutionEvidenceError("缺少需要执行的命令；请在 -- 后提供参数数组")
    if timeout_seconds <= 0:
        raise ExecutionEvidenceError("timeout 必须大于 0 秒")
    try:
        cwd.relative_to(project_path)
    except ValueError as exc:
        raise ExecutionEvidenceError(f"命令目录必须位于 Android 项目内: {cwd}") from exc
    if not cwd.is_dir():
        raise ExecutionEvidenceError(f"命令目录不存在: {cwd}")

    receipt_dir.mkdir(parents=True, exist_ok=True)
    attempt, attempt_dir = _allocate_attempt_directory(receipt_dir, evidence_id)
    stdout_path = attempt_dir / "stdout.log"
    stderr_path = attempt_dir / "stderr.log"
    started_epoch = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout_text = redact_output(completed.stdout)
        stderr_text = redact_output(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_text = redact_output(exc.stdout)
        stderr_text = redact_output(exc.stderr)
    except OSError as exc:
        exit_code = 127
        stdout_text = ""
        stderr_text = redact_output(f"命令无法启动: {command[0]}: {exc}")
    try:
        _write_text_private(stdout_path, stdout_text)
        _write_text_private(stderr_path, stderr_text)
    except OSError as exc:
        raise ExecutionEvidenceError(f"命令日志无法写入外部证据目录: {exc}") from exc
    finished_at = datetime.now(timezone.utc).isoformat()

    excluded: set[str] = set()
    result_path = Path(str(context["result_path"]))
    try:
        excluded.add(result_path.relative_to(project_path).as_posix())
    except ValueError:
        pass
    try:
        after_snapshot = current_delivery_snapshot(
            project_path,
            baseline_path,
            exclude_paths=excluded,
        )["snapshot_sha256"]
    except GitInspectionError as exc:
        raise ExecutionEvidenceError(str(exc)) from exc

    report_records = []
    test_counts: list[int] = []
    junit_invalid = False
    for path in reports:
        record = _file_record(path, started_epoch)
        if record.get("exists") and record.get("fresh"):
            junit = _junit_summary(path)
            if junit is not None:
                record["junit"] = junit
                test_counts.append(junit["executed"])
                junit_invalid = junit_invalid or (
                    junit["failures"] > 0
                    or junit["errors"] > 0
                    or junit["executed"] <= 0
                )
            lint = _android_lint_summary(path)
            if lint is not None:
                record["android_lint"] = lint
            if _is_sarif_report(path):
                try:
                    record["static_analysis"] = summarize_sarif(path, project_path)
                except StaticAnalysisError:
                    # 显式静态 gate 会在下方因缺少可解析报告而失败；其他 gate 保留原始文件证据。
                    pass
        report_records.append(record)
    executed_tests = sum(test_counts) if test_counts else None
    redacted_command = redact_command(command)
    receipt = {
        "version": RECEIPT_VERSION,
        "producer": RECEIPT_PRODUCER,
        "id": evidence_id,
        "gate_id": gate_id,
        "attempt": attempt,
        "requirement_id": context["requirement_id"],
        "requirement_revision": context["requirement_revision"],
        "requirement_file_sha256": context["requirement_file_sha256"],
        "requirement_inputs_sha256": context["requirement_inputs_sha256"],
        "baseline_id": context["baseline_id"],
        "snapshot_sha256_before": context["snapshot_sha256"],
        "snapshot_sha256_after": after_snapshot,
        "command": redacted_command,
        "command_sha256": hashlib.sha256(
            json.dumps(command, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "executed_tests": executed_tests,
        "reports": report_records,
        "stdout": _file_record(stdout_path),
        "stderr": _file_record(stderr_path),
    }
    receipt_path = attempt_dir / "receipt.json"
    _write_json_atomic(receipt_path, receipt)

    collector_exit = exit_code
    if exit_code == 0 and any(
        not record.get("exists") or not record.get("fresh") for record in report_records
    ):
        collector_exit = 3
    if exit_code == 0 and junit_invalid:
        collector_exit = 3
    if exit_code == 0 and gate_id in JUNIT_REQUIRED_GATES and (
        not isinstance(executed_tests, int) or executed_tests <= 0
    ):
        collector_exit = 3
    if exit_code == 0 and _gate_command_errors(gate_id, redacted_command):
        collector_exit = 3
    if exit_code == 0 and gate_id == "android-lint":
        lint_summaries = [
            record["android_lint"]
            for record in report_records
            if isinstance(record.get("android_lint"), dict)
        ]
        if not lint_summaries or any(
            summary.get("fatal", 0) > 0 or summary.get("errors", 0) > 0
            for summary in lint_summaries
        ):
            collector_exit = 3
    if exit_code == 0 and gate_id == "android-static-analysis":
        static_summaries = [
            record["static_analysis"]
            for record in report_records
            if isinstance(record.get("static_analysis"), dict)
        ]
        if not static_summaries or any(
            summary.get("blocking_errors", 0) > 0 for summary in static_summaries
        ):
            collector_exit = 3
    if exit_code == 0 and after_snapshot != context["snapshot_sha256"]:
        collector_exit = 4
    return receipt, receipt_path, collector_exit


def main(argv: list[str] | None = None) -> int:
    """解析命令、校验当前交付上下文并输出收据位置与最终状态。"""
    parser = ChineseArgumentParser(description="执行 Android 交付命令并生成机器收据")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--id", required=True, help="最终报告引用的自动证据 id")
    parser.add_argument(
        "--gate",
        required=True,
        choices=sorted(KNOWN_EVIDENCE_GATES),
        help="该命令唯一负责的交付检查项，禁止一份收据跨用途复用",
    )
    parser.add_argument("--cwd", default=None, help="命令目录，默认 Android 项目根目录")
    parser.add_argument("--timeout", type=int, default=1800, help="命令超时秒数")
    parser.add_argument("--report", action="append", default=[], help="本次命令生成的报告文件")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- 后的命令参数数组")
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        config = load_config(config_path)
        paths = resolve_config_paths(config, config_path)
        if not paths.project_path or not paths.project_path.is_dir():
            raise ExecutionEvidenceError(f"项目路径无效: {paths.project_path}")
        project_path = paths.project_path.resolve()
        cwd = Path(args.cwd).expanduser().resolve() if args.cwd else project_path
        # 延迟导入避免最终门禁加载收据校验器时形成模块循环。
        from .delivery_gate import current_context

        context = current_context(config_path, config)
        reports = _resolve_reports(args.report, cwd)
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id=args.id,
            gate_id=args.gate,
            command=command,
            cwd=cwd,
            timeout_seconds=args.timeout,
            reports=reports,
            context=context,
            project_path=project_path,
            baseline_path=baseline_path_for_config(config_path),
            receipt_dir=evidence_directory_for_config(config_path),
        )
    except (DeliveryError, ExecutionEvidenceError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1

    print(f"$ {shlex.join(receipt['command'])}")
    print(f"证据用途: {gate_label(receipt['gate_id'])}")
    print(f"执行轮次: 第 {receipt['attempt']} 次")
    print(f"执行收据: {receipt_path}")
    print(f"收据 SHA-256: {sha256_file(receipt_path)}")
    print(f"命令退出码: {receipt['exit_code']}")
    if receipt["executed_tests"] is not None:
        print(f"结构化测试数: {receipt['executed_tests']}")
    if exit_code == 3:
        print("❌ 显式报告缺失、过期、失败或零测试，不能作为最终证据", file=sys.stderr)
    elif exit_code == 4:
        print("❌ 命令执行期间代码发生变化，请重新分析最终影响并执行验证", file=sys.stderr)
    elif exit_code == 124:
        print("❌ 命令执行超时", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
