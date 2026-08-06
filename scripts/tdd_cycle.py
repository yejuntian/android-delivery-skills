#!/usr/bin/env python3
"""脚本名称：tdd_cycle.py

用途：把一次 BDD 测试先行闭环保存为结构化 Red/Green 证据，并复核它仍属于当前需求、
测试映射和最终代码。

职责边界：只生成和校验 ``tdd-cycle.json``；不运行测试、不修改需求或 Android 代码。
测试命令仍由 ``execution_evidence.py`` 执行，本文档只消费它生成的收据。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .atomic_write import write_json_atomic  # noqa: E402
from .config_paths import (  # noqa: E402
    resolve_config_paths,
)
from .delivery import DeliveryError, load_config  # noqa: E402
from .execution_evidence import (  # noqa: E402
    ExecutionEvidenceError,
    load_execution_receipt,
    sha256_file,
    validate_execution_receipt,
)
from .bdd_scenarios import is_bdd_id  # noqa: E402
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


TDD_CYCLE_VERSION = 1
TDD_CYCLE_PRODUCER = "android-delivery-tdd-cycle"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TEST_SOURCE_DIR_NAMES = {"test", "androidTest", "testFixtures"}
TEST_SOURCE_SUFFIXES = {
    ".java",
    ".kt",
    ".kts",
    ".groovy",
    ".scala",
    ".xml",
    ".json",
    ".properties",
}


class TddCycleError(RuntimeError):
    """表示 TDD 周期缺失、失效或无法安全保存。"""


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_files(project_path: str | Path) -> list[dict[str, str]]:
    """收集 Android 常见测试源集，稳定保存相对路径和内容摘要。"""
    root = Path(project_path).expanduser().resolve()
    records: dict[str, str] = {}
    try:
        children = sorted(path for path in root.rglob("*") if path.is_file())
    except OSError as exc:
        raise TddCycleError(f"项目测试源码无法读取: {root}: {exc}") from exc
    for path in children:
        try:
            relative_path = path.relative_to(root)
        except ValueError as exc:
            raise TddCycleError(f"测试源码路径无法规范化: {path}: {exc}") from exc
        if path.suffix.lower() not in TEST_SOURCE_SUFFIXES:
            continue
        if any(part in {"build", ".gradle", ".git"} for part in relative_path.parts):
            continue
        if not TEST_SOURCE_DIR_NAMES.intersection(relative_path.parts):
            continue
        try:
            relative = relative_path.as_posix()
            records[relative] = sha256_file(path)
        except OSError as exc:
            raise TddCycleError(f"测试源码无法摘要: {path}: {exc}") from exc
    return [
        {"path": path, "sha256": digest}
        for path, digest in sorted(records.items())
    ]


def _source_digest(files: list[dict[str, str]]) -> str:
    return _json_digest(files)


def _mapping_digest(path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise TddCycleError(f"测试映射不存在: {target}")
    try:
        return sha256_file(target)
    except OSError as exc:
        raise TddCycleError(f"测试映射无法摘要: {target}: {exc}") from exc


def _mapping_obligations(context: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = context.get("test_mapping")
    if not isinstance(mapping, dict):
        raise TddCycleError("缺少当前需求测试映射，不能建立 TDD 周期")
    obligations: list[dict[str, Any]] = []
    for identifier, entry in sorted(mapping.items()):
        if not isinstance(entry, dict):
            raise TddCycleError(f"测试映射 {identifier} 格式无效")
        test_ids = entry.get("test_ids")
        if not isinstance(test_ids, list) or not all(
            isinstance(test_id, str) and test_id.strip() for test_id in test_ids
        ):
            raise TddCycleError(f"测试映射 {identifier} 的 test_ids 格式无效")
        if not test_ids:
            continue
        if not is_bdd_id(identifier):
            raise TddCycleError(f"测试映射包含无效 BDD id: {identifier}")
        if entry.get("mapping_status") != "CURRENT":
            raise TddCycleError(f"测试映射 {identifier} 不是 CURRENT，不能建立 TDD 周期")
        if not _valid_sha(entry.get("obligation_sha256")):
            raise TddCycleError(f"测试映射 {identifier} 缺少有效 obligation_sha256")
        obligations.append({
            "id": identifier,
            "obligation_sha256": entry["obligation_sha256"],
            "test_ids": sorted(set(test_ids)),
        })
    if not obligations:
        raise TddCycleError("当前需求没有可自动执行的测试映射")
    return obligations


def _receipt_test_cases(receipt: dict[str, Any]) -> dict[str, str]:
    cases: dict[str, str] = {}
    reports = receipt.get("reports")
    if not isinstance(reports, list):
        return cases
    for report in reports:
        if not isinstance(report, dict) or not isinstance(report.get("junit"), dict):
            continue
        for case in report["junit"].get("test_cases", []):
            if not isinstance(case, dict):
                continue
            identifier = case.get("id")
            status = case.get("status")
            if isinstance(identifier, str) and identifier and isinstance(status, str):
                cases[identifier] = status
    return cases


def _receipt_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    reports = receipt.get("reports")
    report_paths = [
        report.get("path")
        for report in reports or []
        if isinstance(report, dict) and isinstance(report.get("path"), str)
    ]
    return {
        "id": receipt.get("id"),
        "gate_id": receipt.get("gate_id"),
        "command": receipt.get("command"),
        "exit_code": receipt.get("exit_code"),
        "executed_tests": receipt.get("executed_tests"),
        "report_paths": report_paths,
        "obligation_test_cases": {},
    }


def _validate_receipt(
    receipt_path: Path,
    receipt: dict[str, Any],
    context: dict[str, Any],
    *,
    allow_failure: bool,
) -> list[str]:
    if receipt.get("gate_id") != "android-test-and-fix":
        return [f"TDD 收据 {receipt_path} 必须属于 android-test-and-fix gate"]
    snapshot = receipt.get("snapshot_sha256_before")
    if not _valid_sha(snapshot):
        return [f"TDD 收据 {receipt_path} 缺少有效 snapshot_sha256_before"]
    phase_context = dict(context)
    phase_context["snapshot_sha256"] = snapshot
    return validate_execution_receipt(
        receipt_path,
        sha256_file(receipt_path),
        _receipt_evidence(receipt),
        phase_context,
        allow_failure=allow_failure,
    )


def _validate_phase_semantics(
    receipt: dict[str, Any],
    obligations: list[dict[str, Any]],
    phase: str,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    cases = _receipt_test_cases(receipt)
    mapped_ids = sorted({test_id for item in obligations for test_id in item["test_ids"]})
    if not cases:
        errors.append(f"TDD {phase} 收据没有可复核的 JUnit testcase")
    missing = sorted(set(mapped_ids) - set(cases))
    if missing:
        errors.append(f"TDD {phase} 未执行当前映射测试: {', '.join(missing)}")
    mapped_cases = {identifier: cases.get(identifier) for identifier in mapped_ids}
    skipped = sorted(identifier for identifier, status in mapped_cases.items() if status == "SKIPPED")
    errored = sorted(identifier for identifier, status in mapped_cases.items() if status == "ERROR")
    if skipped:
        errors.append(f"TDD {phase} 存在跳过的映射测试: {', '.join(skipped)}")
    if errored:
        errors.append(f"TDD {phase} 存在测试执行错误，不能当作业务断言: {', '.join(errored)}")

    reports = receipt.get("reports") if isinstance(receipt.get("reports"), list) else []
    junit_reports = [
        report["junit"]
        for report in reports
        if isinstance(report, dict) and isinstance(report.get("junit"), dict)
    ]
    if not junit_reports:
        errors.append(f"TDD {phase} 缺少 JUnit 汇总，不能排除编译或环境失败")
    def positive_count(report: dict[str, Any], field: str) -> bool:
        value = report.get(field, 0)
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    if phase == "RED":
        if receipt.get("exit_code") == 0:
            errors.append("TDD Red 命令必须以失败退出")
        if any(positive_count(report, "errors") for report in junit_reports):
            errors.append("TDD Red 含 JUnit ERROR，不能归类为业务断言失败")
        failed_ids = sorted(
            identifier for identifier, status in mapped_cases.items() if status == "FAIL"
        )
        if not failed_ids:
            errors.append("TDD Red 必须至少包含一个映射测试的业务断言 FAIL")
        if not any(positive_count(report, "failures") for report in junit_reports):
            errors.append("TDD Red 缺少 JUnit assertion failure")
        failure_kind = "ASSERTION" if not errors and failed_ids else None
        phase_data = {
            "executed_test_ids": sorted(identifier for identifier, status in cases.items() if status != "SKIPPED"),
            "failed_test_ids": failed_ids,
            "failure_kind": failure_kind,
        }
    else:
        if receipt.get("exit_code") != 0:
            errors.append("TDD Green 命令必须以 0 退出")
        if any(
            positive_count(report, "failures") or positive_count(report, "errors")
            for report in junit_reports
        ):
            errors.append("TDD Green 的 JUnit 仍存在失败或执行错误")
        not_passed = sorted(
            identifier for identifier, status in mapped_cases.items() if status != "PASS"
        )
        if not_passed:
            errors.append(f"TDD Green 映射测试未全部 PASS: {', '.join(not_passed)}")
        phase_data = {
            "executed_test_ids": sorted(identifier for identifier, status in cases.items() if status != "SKIPPED"),
            "passed_test_ids": sorted(identifier for identifier, status in mapped_cases.items() if status == "PASS"),
        }
    return errors, phase_data


def _phase_payload(
    receipt_path: Path,
    receipt: dict[str, Any],
    source_files: list[dict[str, str]],
    semantic: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_id": receipt.get("id"),
        "command_sha256": receipt.get("command_sha256"),
        "snapshot_sha256_before": receipt.get("snapshot_sha256_before"),
        "snapshot_sha256_after": receipt.get("snapshot_sha256_after"),
        "started_at": receipt.get("started_at"),
        "finished_at": receipt.get("finished_at"),
        "test_source_sha256": _source_digest(source_files),
        "test_source_files": source_files,
        **semantic,
    }
    return payload


def _base_cycle(context: dict[str, Any], obligations: list[dict[str, Any]], mapping_sha: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": TDD_CYCLE_VERSION,
        "producer": TDD_CYCLE_PRODUCER,
        "cycle_id": None,
        "status": "RED",
        "requirement_id": context.get("requirement_id"),
        "requirement_revision": context.get("requirement_revision"),
        "requirement_file_sha256": context.get("requirement_file_sha256"),
        "requirement_inputs_sha256": context.get("requirement_inputs_sha256"),
        "test_mapping_sha256": mapping_sha,
        "obligations": obligations,
        "red": None,
        "green": None,
        "created_at": now,
        "completed_at": None,
    }


def _write_cycle(path: Path, payload: dict[str, Any]) -> None:
    try:
        write_json_atomic(path, payload)
    except OSError as exc:
        raise TddCycleError(f"TDD 周期无法写入: {path}: {exc}") from exc


def record_red(
    receipt_path: str | Path,
    cycle_path: str | Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    """校验 Red 收据并生成未完成的 TDD 周期。"""
    receipt_target = Path(receipt_path).expanduser().resolve()
    cycle_target = Path(cycle_path).expanduser().resolve()
    try:
        receipt = load_execution_receipt(receipt_target)
        receipt_errors = _validate_receipt(receipt_target, receipt, context, allow_failure=True)
    except (OSError, ExecutionEvidenceError, TddCycleError) as exc:
        raise TddCycleError(str(exc)) from exc
    obligations = _mapping_obligations(context)
    semantic_errors, semantic = _validate_phase_semantics(receipt, obligations, "RED")
    errors = receipt_errors + semantic_errors
    source_files = _source_files(context.get("project_path", ""))
    if not source_files:
        errors.append("TDD Red 找不到测试源码，不能证明测试先于实现")
    if errors:
        raise TddCycleError("；".join(errors))
    mapping_sha = _mapping_digest(context["test_mapping_path"])
    payload = _base_cycle(context, obligations, mapping_sha)
    payload["cycle_id"] = f"TDD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{receipt['id']}"
    payload["red"] = _phase_payload(receipt_target, receipt, source_files, semantic)
    _write_cycle(cycle_target, payload)
    return payload


def _iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def _validate_source_manifest(phase: dict[str, Any], label: str, errors: list[str]) -> None:
    files = phase.get("test_source_files")
    if not isinstance(files, list) or not all(isinstance(item, dict) for item in files):
        errors.append(f"TDD {label} 缺少结构化测试源码快照")
        return
    normalized: list[dict[str, str]] = []
    for item in files:
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path or not _valid_sha(digest):
            errors.append(f"TDD {label} 测试源码快照字段无效")
            continue
        normalized.append({"path": path, "sha256": digest})
    if _valid_sha(phase.get("test_source_sha256")) and _source_digest(normalized) != phase["test_source_sha256"]:
        errors.append(f"TDD {label} 测试源码快照摘要不一致")


def validate_tdd_cycle_payload(
    payload: Any,
    context: dict[str, Any],
    required_obligation_ids: set[str] | None = None,
) -> list[str]:
    """校验完整 GREEN 周期；返回全部阻断原因。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["tdd-cycle.json 根节点必须是 object"]
    if payload.get("version") != TDD_CYCLE_VERSION or payload.get("producer") != TDD_CYCLE_PRODUCER:
        errors.append("tdd-cycle.json version 或 producer 无效")
    if payload.get("status") != "GREEN":
        errors.append("TDD 周期必须完成 Red -> Green，当前不是 GREEN")
    for field in (
        "requirement_id",
        "requirement_revision",
        "requirement_file_sha256",
        "requirement_inputs_sha256",
    ):
        if payload.get(field) != context.get(field):
            errors.append(f"TDD 周期的 {field} 已过期")
    if not _valid_sha(payload.get("test_mapping_sha256")):
        errors.append("TDD 周期缺少有效 test_mapping_sha256")
    mapping_path = context.get("test_mapping_path")
    if not isinstance(mapping_path, str) or not mapping_path:
        errors.append("当前上下文缺少测试映射路径")
    else:
        try:
            if _mapping_digest(mapping_path) != payload.get("test_mapping_sha256"):
                errors.append("TDD 周期绑定的测试映射已变化")
        except TddCycleError as exc:
            errors.append(str(exc))

    try:
        expected_obligations = _mapping_obligations(context)
    except TddCycleError as exc:
        errors.append(str(exc))
        expected_obligations = []
    actual_obligations = payload.get("obligations")
    if not isinstance(actual_obligations, list):
        errors.append("TDD 周期 obligations 必须是数组")
        actual_obligations = []
    raw_actual_ids = [
        item.get("id")
        for item in actual_obligations
        if isinstance(item, dict)
    ]
    actual_ids = [identifier for identifier in raw_actual_ids if isinstance(identifier, str)]
    if len(actual_ids) != len(raw_actual_ids):
        errors.append("TDD 周期 obligations 存在无效 BDD id")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("TDD 周期 obligations 存在重复 BDD id")
    expected_by_id = {item["id"]: item for item in expected_obligations}
    actual_by_id = {
        item.get("id"): item
        for item in actual_obligations
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(actual_by_id) != set(expected_by_id):
        errors.append("TDD 周期的 BDD/testcase 关系未覆盖当前全部自动化映射")
    for identifier, expected in expected_by_id.items():
        actual = actual_by_id.get(identifier)
        if actual is None:
            continue
        if actual.get("obligation_sha256") != expected["obligation_sha256"]:
            errors.append(f"TDD 周期的 {identifier} 需求语义摘要已过期")
        actual_test_ids = actual.get("test_ids")
        if not isinstance(actual_test_ids, list) or not all(
            isinstance(test_id, str) and test_id.strip() for test_id in actual_test_ids
        ):
            errors.append(f"TDD 周期的 {identifier} test_ids 格式无效")
        elif sorted(actual_test_ids) != expected["test_ids"]:
            errors.append(f"TDD 周期的 {identifier} 测试关系已变化")
    if required_obligation_ids and not required_obligation_ids.issubset(set(actual_by_id)):
        errors.append("TDD 周期缺少最终报告声明的自动化 BDD")

    red = payload.get("red")
    green = payload.get("green")
    if not isinstance(red, dict) or not isinstance(green, dict):
        errors.append("TDD 周期必须同时保存 red 和 green receipt")
        return errors
    for label, phase in (("Red", red), ("Green", green)):
        receipt_path = phase.get("receipt_path")
        receipt_sha = phase.get("receipt_sha256")
        if not isinstance(receipt_path, str) or not receipt_path:
            errors.append(f"TDD {label} 缺少 receipt_path")
            continue
        target = Path(receipt_path).expanduser().resolve()
        if not _valid_sha(receipt_sha):
            errors.append(f"TDD {label} 缺少有效 receipt_sha256")
            continue
        try:
            if sha256_file(target) != receipt_sha:
                errors.append(f"TDD {label} receipt 摘要已变化")
            receipt = load_execution_receipt(target)
            receipt_errors = _validate_receipt(
                target,
                receipt,
                context,
                allow_failure=(label == "Red"),
            )
            errors.extend(receipt_errors)
            if phase.get("receipt_id") != receipt.get("id"):
                errors.append(f"TDD {label} receipt_id 与收据不一致")
            if phase.get("command_sha256") != receipt.get("command_sha256"):
                errors.append(f"TDD {label} command_sha256 与收据不一致")
            if phase.get("snapshot_sha256_before") != receipt.get("snapshot_sha256_before"):
                errors.append(f"TDD {label} 代码快照起点与收据不一致")
            if phase.get("snapshot_sha256_after") != receipt.get("snapshot_sha256_after"):
                errors.append(f"TDD {label} 代码快照终点与收据不一致")
            semantic_errors, semantic = _validate_phase_semantics(
                receipt,
                expected_obligations,
                label.upper(),
            )
            errors.extend(semantic_errors)
            for field in ("executed_test_ids", "failed_test_ids", "passed_test_ids", "failure_kind"):
                if field in semantic and phase.get(field) != semantic[field]:
                    errors.append(f"TDD {label} 的 {field} 与收据实际结果不一致")
        except (OSError, ExecutionEvidenceError, TddCycleError) as exc:
            errors.append(str(exc))
        _validate_source_manifest(phase, label, errors)

    if isinstance(red.get("test_source_files"), list) and isinstance(green.get("test_source_files"), list):
        if red["test_source_files"] != green["test_source_files"]:
            errors.append("Red 与 Green 之间测试源码发生变化，Green 不能证明同一测试")
    project_path = context.get("project_path")
    if isinstance(project_path, str) and project_path:
        try:
            current_files = _source_files(project_path)
            if current_files != green.get("test_source_files"):
                errors.append("Green 之后测试源码发生变化，旧 TDD 周期已失效")
        except TddCycleError as exc:
            errors.append(str(exc))

    if red.get("snapshot_sha256_before") != red.get("snapshot_sha256_after"):
        errors.append("TDD Red 执行期间代码发生变化")
    if green.get("snapshot_sha256_before") != green.get("snapshot_sha256_after"):
        errors.append("TDD Green 执行期间代码发生变化")
    if red.get("snapshot_sha256_after") == green.get("snapshot_sha256_before"):
        errors.append("Red 与 Green 之间没有可证明的生产代码变化")
    if red.get("test_source_sha256") != green.get("test_source_sha256"):
        errors.append("Red 与 Green 的测试源码摘要不一致")
    if red.get("command_sha256") != green.get("command_sha256"):
        errors.append("Red 与 Green 没有使用同一测试命令")
    if red.get("failure_kind") != "ASSERTION":
        errors.append("TDD Red failure_kind 必须是 ASSERTION")
    red_finished = _iso(red.get("finished_at"))
    green_started = _iso(green.get("started_at"))
    if red_finished is None or green_started is None or green_started < red_finished:
        errors.append("TDD Green 没有发生在 Red 之后")
    if context.get("snapshot_sha256") != green.get("snapshot_sha256_after"):
        errors.append("TDD Green 未绑定当前最终代码快照")
    return errors


def validate_tdd_cycle(
    path: str | Path,
    context: dict[str, Any],
    required_obligation_ids: set[str] | None = None,
) -> list[str]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return [f"缺少 TDD 周期记录: {target}，不能仅凭最终 Green 放行"]
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"TDD 周期无法读取: {target}: {exc}"]
    return validate_tdd_cycle_payload(payload, context, required_obligation_ids)


def record_green(
    receipt_path: str | Path,
    cycle_path: str | Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    """校验 Green 收据，补全并保存 GREEN TDD 周期。"""
    cycle_target = Path(cycle_path).expanduser().resolve()
    try:
        payload = json.loads(cycle_target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TddCycleError(f"Red TDD 周期无法读取: {cycle_target}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "RED" or not isinstance(payload.get("red"), dict):
        raise TddCycleError("必须先记录有效的 TDD Red")
    receipt_target = Path(receipt_path).expanduser().resolve()
    try:
        receipt = load_execution_receipt(receipt_target)
    except (OSError, ExecutionEvidenceError, TddCycleError) as exc:
        raise TddCycleError(str(exc)) from exc
    receipt_errors = _validate_receipt(receipt_target, receipt, context, allow_failure=False)
    obligations = _mapping_obligations(context)
    semantic_errors, semantic = _validate_phase_semantics(receipt, obligations, "GREEN")
    source_files = _source_files(context.get("project_path", ""))
    errors = receipt_errors + semantic_errors
    if not source_files:
        errors.append("TDD Green 找不到测试源码")
    if errors:
        raise TddCycleError("；".join(errors))
    payload["status"] = "GREEN"
    payload["green"] = _phase_payload(receipt_target, receipt, source_files, semantic)
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    errors = validate_tdd_cycle_payload(payload, context)
    if errors:
        raise TddCycleError("；".join(errors))
    _write_cycle(cycle_target, payload)
    return payload


def _load_context(config_path: Path) -> tuple[Path, dict[str, Any]]:
    config = load_config(config_path)
    paths = resolve_config_paths(config, config_path)
    from .delivery_gate import current_context
    context = current_context(config_path, config)
    context["test_mapping_path"] = str(paths.test_mapping_path)
    return paths.tdd_cycle_path, context


def main(argv: list[str] | None = None) -> int:
    parser = ChineseArgumentParser(description="记录和校验 BDD 测试先行 Red/Green 周期")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("record-red", "校验 Red 收据并保存 TDD 周期"),
        ("record-green", "校验 Green 收据并完成 TDD 周期"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--config", default=None, help="配置文件路径")
        subparser.add_argument("--receipt", required=True, help="execution_evidence.py 收据路径")
        subparser.add_argument("--cycle", default=None, help="TDD 周期路径，默认当前需求 .state/tdd-cycle.json")
    args = parser.parse_args(argv)
    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    try:
        default_cycle, context = _load_context(config_path)
        cycle_path = Path(args.cycle).expanduser().resolve() if args.cycle else default_cycle
        if args.command == "record-red":
            payload = record_red(args.receipt, cycle_path, context)
        else:
            payload = record_green(args.receipt, cycle_path, context)
    except (DeliveryError, TddCycleError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    print(f"✅ TDD {payload['status']}: {cycle_path}")
    print(f"周期 ID: {payload['cycle_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
