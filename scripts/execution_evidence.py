#!/usr/bin/env python3
"""脚本名称：execution_evidence.py

用途：执行一条 Android 交付命令并生成可复核的机器收据。

核心流程：在当前确认需求和最新 route 快照上运行命令，把标准输出、错误输出、
退出码、测试数、报告摘要和执行前后代码摘要写到目标项目之外；最终门禁重新校验收据。

职责边界：只执行用户或 Skill 已经选择的命令，不选择 Gradle task、不判断业务、
不修代码、不调用其他 Skill，也不执行 Git 写操作。退出码沿用命令结果；证据缺失返回 3，
执行期间代码摘要变化返回 4，超时返回 124。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
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


RECEIPT_PRODUCER = "android-delivery-execution-evidence"
RECEIPT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(token|password|passwd|secret|api[-_]?key|authorization|cookie)"
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|password|passwd|secret|api[-_]?key|authorization|cookie)\s*[:=]\s*[^\s,;]+"
)
URL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>]+")


class ExecutionEvidenceError(RuntimeError):
    """表示命令无法安全启动、收据无法写入或收据内容不可验证。"""


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
        redacted.append(_redact_url(part))
    return redacted


def redact_output(raw: bytes | str | None) -> str:
    """脱敏外部命令输出后再落盘，避免工具回显凭据或 DeepLink 查询参数。"""
    if raw is None:
        return ""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer <redacted>", text)
    text = SENSITIVE_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), text)


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


def _junit_summary(path: Path) -> dict[str, int] | None:
    """从 JUnit XML 汇总测试、失败、错误和跳过数，防止 ignoreFailures 造绿。"""
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
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        try:
            summary["tests"] += int(suite.attrib["tests"])
            summary["failures"] += int(suite.attrib.get("failures", "0"))
            summary["errors"] += int(suite.attrib.get("errors", "0"))
            summary["skipped"] += int(suite.attrib.get("skipped", "0"))
        except (KeyError, ValueError):
            return None
    summary["executed"] = max(0, summary["tests"] - summary["skipped"])
    return summary


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """原子写入最终收据，命令中断时不会留下可被门禁误认的半文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
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
    if receipt.get("version") != 1 or receipt.get("producer") != RECEIPT_PRODUCER:
        errors.append(f"自动证据 {evidence.get('id')} 的执行收据来源无效")
    if receipt.get("id") != evidence.get("id"):
        errors.append(f"自动证据 {evidence.get('id')} 与执行收据 id 不一致")
    for field in (
        "requirement_id",
        "requirement_revision",
        "requirement_file_sha256",
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
    receipt_test_count = receipt.get("executed_tests")
    if isinstance(receipt_test_count, int) and (
        junit_records == 0 or junit_executed != receipt_test_count
    ):
        errors.append(f"自动证据 {evidence.get('id')} 的测试数没有匹配的 JUnit 汇总")

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


def run_and_record(
    *,
    evidence_id: str,
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
    )
    if not RECEIPT_ID_PATTERN.fullmatch(evidence_id):
        raise ExecutionEvidenceError("证据 id 只能使用字母、数字、点、下划线和短横线，最长 80 位")
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
    stdout_path = receipt_dir / f"{evidence_id}.stdout.log"
    stderr_path = receipt_dir / f"{evidence_id}.stderr.log"
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
        raise ExecutionEvidenceError(f"命令无法启动: {command[0]}: {exc}") from exc
    try:
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
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
        report_records.append(record)
    executed_tests = sum(test_counts) if test_counts else None
    redacted_command = redact_command(command)
    receipt = {
        "version": 1,
        "producer": RECEIPT_PRODUCER,
        "id": evidence_id,
        "requirement_id": context["requirement_id"],
        "requirement_revision": context["requirement_revision"],
        "requirement_file_sha256": context["requirement_file_sha256"],
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
    receipt_path = receipt_dir / f"{evidence_id}.json"
    _write_json_atomic(receipt_path, receipt)

    collector_exit = exit_code
    if exit_code == 0 and any(
        not record.get("exists") or not record.get("fresh") for record in report_records
    ):
        collector_exit = 3
    if exit_code == 0 and junit_invalid:
        collector_exit = 3
    if exit_code == 0 and after_snapshot != context["snapshot_sha256"]:
        collector_exit = 4
    return receipt, receipt_path, collector_exit


def main(argv: list[str] | None = None) -> int:
    """解析命令、校验当前交付上下文并输出收据位置与最终状态。"""
    parser = argparse.ArgumentParser(description="执行 Android 交付命令并生成机器收据")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--id", required=True, help="最终报告引用的自动证据 id")
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
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(f"$ {shlex.join(receipt['command'])}")
    print(f"执行收据: {receipt_path}")
    print(f"收据 SHA-256: {sha256_file(receipt_path)}")
    print(f"命令退出码: {receipt['exit_code']}")
    if receipt["executed_tests"] is not None:
        print(f"结构化测试数: {receipt['executed_tests']}")
    if exit_code == 3:
        print("❌ 显式报告缺失或不是本轮生成，不能作为最终证据", file=sys.stderr)
    elif exit_code == 4:
        print("❌ 命令执行期间代码摘要发生变化，请重新 route 并重跑", file=sys.stderr)
    elif exit_code == 124:
        print("❌ 命令执行超时", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
