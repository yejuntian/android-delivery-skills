#!/usr/bin/env python3
"""脚本名称：static_analysis.py

用途：规范化已有静态工具的 SARIF 报告、生成稳定问题编号，并审计本次需求中
可能削弱静态门禁的配置、基线、排除和抑制变化。

核心流程：只读取显式报告或当前需求 Git 差异，输出确定性的摘要与候选；不选择
扫描工具、不安装规则、不判断业务严重级别，也不修改目标项目或 Git 状态。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import (  # noqa: E402
    baseline_path_for_config,
    delivery_snapshot_exclusions,
    resolve_config_paths,
)
from .delivery import DeliveryError, load_config  # noqa: E402
from .git_changes import (  # noqa: E402
    GitChange,
    GitInspectionError,
    collect_changed_entries,
    current_delivery_snapshot,
    load_baseline,
)
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


FINDING_ID_PATTERN = re.compile(r"^FND-[A-F0-9]{16}$")
CONTROL_ID_PATTERN = re.compile(r"^CTL-[A-F0-9]{16}$")
SARIF_LEVELS = {"error", "warning", "note", "none"}
SARIF_BASELINE_STATES = {"new", "updated", "unchanged", "absent"}
STATIC_CONFIG_EXTENSIONS = {".json", ".properties", ".xml", ".yaml", ".yml"}
STATIC_CONFIG_DIRECTORIES = {".config", "config", "quality"}
CONTROL_AUDIT_PRODUCER = "android-static-control-audit"
STATIC_TOOL_TOKENS = {
    "android-lint": ("lint",),
    "detekt": ("detekt",),
    "error-prone": ("errorprone", "error-prone"),
    "infer": ("infer",),
    "nullaway": ("nullaway",),
    "pmd": ("pmd",),
    "semgrep": ("semgrep",),
    "codeql": ("codeql",),
    "spotbugs": ("spotbugs",),
    "checkstyle": ("checkstyle",),
    "sonar": ("sonar",),
}
SUPPRESSION_PATTERN = re.compile(
    r"(?:@Suppress(?:Warnings|Lint)?\b|//\s*noinspection\b|#\s*nosemgrep\b|//\s*nosemgrep\b)",
    re.IGNORECASE,
)
BASELINE_PATTERN = re.compile(r"\bbaseline\b", re.IGNORECASE)
EXCLUSION_PATTERN = re.compile(
    r"\b(?:disable|exclude|ignoreFailures|abortOnError|warningsAsErrors)\b",
    re.IGNORECASE,
)


class StaticAnalysisError(RuntimeError):
    """表示 SARIF、稳定编号或静态控制面审计无法形成可信结果。"""


def _normalized_text(value: Any) -> str:
    """压缩不影响语义的空白，使同一问题在换行变化后保持相同编号。"""
    return " ".join(str(value or "").split())


def stable_finding_id(
    *,
    tool: str,
    rule_id: str,
    path: str,
    symbol: str = "",
    message: str = "",
    fingerprint: str = "",
) -> str:
    """根据工具、规则、相对路径和语义指纹生成跨行号变化的稳定问题编号。"""
    identity = {
        "tool": _normalized_text(tool).lower(),
        "rule": _normalized_text(rule_id).lower(),
        # Linux 仓库路径大小写敏感；只统一分隔符，不能把两个真实文件合并为同一问题。
        "path": str(path).replace("\\", "/").strip(),
        "symbol": _normalized_text(symbol),
        "evidence": _normalized_text(fingerprint or message),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"FND-{digest}"


def stable_control_id(path: str, kind: str, detail: str) -> str:
    """为静态门禁控制面变化生成稳定编号，供后续修订保持同一审查身份。"""
    raw = json.dumps(
        {
            "path": path.replace("\\", "/"),
            "kind": kind,
            "detail": _normalized_text(detail),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "CTL-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _message_text(result: dict[str, Any]) -> str:
    """读取 SARIF 标准 message.text/markdown，不把正文写入收据摘要。"""
    message = result.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("text") or message.get("markdown") or "")


def _location(result: dict[str, Any], project_root: Path | None) -> tuple[str, int | None, str]:
    """提取首个物理位置和逻辑符号；位置缺失时保持空值而不猜测。"""
    locations = result.get("locations")
    if not isinstance(locations, list) or not locations or not isinstance(locations[0], dict):
        return "", None, ""
    location = locations[0]
    physical = location.get("physicalLocation")
    path = ""
    line: int | None = None
    if isinstance(physical, dict):
        artifact = physical.get("artifactLocation")
        if isinstance(artifact, dict) and isinstance(artifact.get("uri"), str):
            parsed = urlparse(artifact["uri"])
            raw_path = unquote(parsed.path if parsed.scheme == "file" else artifact["uri"])
            candidate = Path(raw_path)
            if project_root and candidate.is_absolute():
                try:
                    path = candidate.resolve().relative_to(project_root.resolve()).as_posix()
                except ValueError:
                    path = candidate.as_posix()
            else:
                path = raw_path.replace("\\", "/")
        region = physical.get("region")
        if isinstance(region, dict) and isinstance(region.get("startLine"), int):
            line = region["startLine"]
    symbol = ""
    logical = location.get("logicalLocations")
    if isinstance(logical, list) and logical and isinstance(logical[0], dict):
        symbol = str(logical[0].get("fullyQualifiedName") or logical[0].get("name") or "")
    return path, line, symbol


def _sarif_fingerprint(result: dict[str, Any]) -> str:
    """优先采用工具提供的 SARIF 指纹；没有时由规则、位置和消息生成稳定编号。"""
    for field in ("partialFingerprints", "fingerprints"):
        values = result.get(field)
        if isinstance(values, dict):
            parts = [f"{key}={values[key]}" for key in sorted(values) if values[key] is not None]
            if parts:
                return "|".join(parts)
    return ""


def summarize_sarif(path: str | Path, project_root: str | Path | None = None) -> dict[str, Any]:
    """解析通用 SARIF 2.x 报告，输出工具、级别、位置和稳定问题编号摘要。"""
    source = Path(path).expanduser().resolve()
    root = Path(project_root).expanduser().resolve() if project_root else None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StaticAnalysisError(f"SARIF 报告无法读取: {source}: {exc}") from exc
    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise StaticAnalysisError(f"SARIF 报告缺少 runs 数组: {source}")

    counts = {level: 0 for level in SARIF_LEVELS}
    error_baselines = {state: 0 for state in (*sorted(SARIF_BASELINE_STATES), "unknown")}
    tools: dict[tuple[str, str], dict[str, str]] = {}
    findings: dict[str, dict[str, Any]] = {}
    total = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        driver = ((run.get("tool") or {}).get("driver") or {})
        if not isinstance(driver, dict):
            driver = {}
        tool_name = str(driver.get("name") or "unknown")
        tool_version = str(driver.get("semanticVersion") or driver.get("version") or "unknown")
        tools[(tool_name, tool_version)] = {"name": tool_name, "version": tool_version}
        rule_levels: dict[str, str] = {}
        rules = driver.get("rules")
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
                    continue
                default = rule.get("defaultConfiguration")
                if isinstance(default, dict) and isinstance(default.get("level"), str):
                    rule_levels[rule["id"]] = default["level"].lower()
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            rule_id = str(result.get("ruleId") or "unknown")
            level = str(result.get("level") or rule_levels.get(rule_id) or "warning").lower()
            level = level if level in SARIF_LEVELS else "warning"
            counts[level] += 1
            raw_baseline_state = str(result.get("baselineState") or "unknown").lower()
            baseline_state = (
                raw_baseline_state if raw_baseline_state in SARIF_BASELINE_STATES else "unknown"
            )
            if level == "error":
                error_baselines[baseline_state] += 1
            total += 1
            result_path, line, symbol = _location(result, root)
            finding_id = stable_finding_id(
                tool=tool_name,
                rule_id=rule_id,
                path=result_path,
                symbol=symbol,
                message=_message_text(result),
                fingerprint=_sarif_fingerprint(result),
            )
            findings.setdefault(finding_id, {
                "id": finding_id,
                "tool": tool_name,
                "rule_id": rule_id,
                "level": level,
                "path": result_path,
                "line": line,
                "baseline_state": baseline_state,
            })
    blocking_errors = (
        error_baselines["new"]
        + error_baselines["updated"]
        + error_baselines["unknown"]
    )
    return {
        "format": "SARIF",
        "tools": sorted(tools.values(), key=lambda item: (item["name"], item["version"])),
        "errors": counts["error"],
        "new_errors": error_baselines["new"],
        "updated_errors": error_baselines["updated"],
        "unchanged_errors": error_baselines["unchanged"],
        "absent_errors": error_baselines["absent"],
        "unknown_errors": error_baselines["unknown"],
        "blocking_errors": blocking_errors,
        "warnings": counts["warning"],
        "notes": counts["note"],
        "none": counts["none"],
        "total": total,
        "findings": sorted(findings.values(), key=lambda item: item["id"]),
    }


def _tools_for_control_file(path: str, patch: str) -> list[str]:
    """根据路径和当前补丁识别静态工具配置；只报告证据，不声明工具已执行。"""
    haystack = f"{path}\n{patch}".lower()
    tools = [
        tool for tool, tokens in STATIC_TOOL_TOKENS.items()
        if any(token in haystack for token in tokens)
    ]
    return sorted(set(tools))


def _static_candidate_file(path: str, tools: list[str]) -> bool:
    """有界识别静态配置候选，兼顾隐藏目录和不带工具名的质量配置。"""
    normalized = path.replace("\\", "/").lower()
    candidate = Path(normalized)
    parts = set(candidate.parts[:-1])
    in_static_config_directory = bool(parts & STATIC_CONFIG_DIRECTORIES)
    return bool(tools) or (
        in_static_config_directory and candidate.suffix in STATIC_CONFIG_EXTENSIONS
    )


def audit_control_changes(changes: Iterable[GitChange]) -> list[dict[str, str]]:
    """找出抑制、基线、排除和静态配置变化，交由稳定性审查逐项说明理由。"""
    candidates: dict[str, dict[str, str]] = {}

    def add(path: str, kind: str, detail: str, summary: str) -> None:
        """按稳定标识合并同一控制面变化，避免重复候选进入专项审查。"""
        identifier = stable_control_id(path, kind, detail)
        candidates[identifier] = {
            "id": identifier,
            "path": path,
            "kind": kind,
            "summary": summary,
        }

    for change in changes:
        tools = _tools_for_control_file(change.path, change.patch)
        lowered_path = change.path.lower()
        is_workflow = lowered_path.startswith(".github/workflows/")
        is_build_file = lowered_path.endswith((".gradle", ".gradle.kts"))
        is_known_config = _static_candidate_file(change.path, tools) and (
            is_workflow
            or is_build_file
            or any(token in lowered_path for token in ("config", "quality", "lint", "baseline"))
            or Path(lowered_path).suffix in STATIC_CONFIG_EXTENSIONS
        )
        if is_known_config:
            add(
                change.path,
                "CONFIG",
                ",".join(tools) or "static-analysis",
                "静态工具配置或持续集成入口发生变化，需要确认扫描范围和门禁没有被削弱。",
            )
        baseline_paths = [*([change.old_path] if change.old_path else []), change.path]
        if any("baseline" in Path(path.lower()).name for path in baseline_paths) and tools:
            add(
                change.path,
                "BASELINE",
                " -> ".join(baseline_paths),
                "静态分析基线发生变化，需要逐项说明新增基线内容及来源。",
            )
        raw_untracked_content = change.status == "A" and not change.patch.startswith("diff --git ")
        for raw_line in change.patch.splitlines():
            if raw_untracked_content:
                line = raw_line.strip()
            else:
                if not raw_line.startswith("+") or raw_line.startswith("+++"):
                    continue
                line = raw_line[1:].strip()
            if not line:
                continue
            if SUPPRESSION_PATTERN.search(line):
                add(
                    change.path,
                    "SUPPRESSION",
                    line,
                    "源码新增静态告警抑制，需要说明对应问题、适用范围和不能直接修复的原因。",
                )
            if is_known_config and BASELINE_PATTERN.search(line):
                add(
                    change.path,
                    "BASELINE",
                    line,
                    "配置新增或修改基线引用，需要确认没有把本次新增问题写入基线。",
                )
            if is_known_config and EXCLUSION_PATTERN.search(line):
                add(
                    change.path,
                    "EXCLUSION",
                    line,
                    "静态检查排除或失败策略发生变化，需要说明是否缩小扫描范围或放宽门禁。",
                )
    return sorted(candidates.values(), key=lambda item: item["id"])


def build_control_audit(
    project: str | Path,
    baseline_path: str | Path,
    *,
    exclude_paths: set[str] | None = None,
) -> dict[str, Any]:
    """生成绑定当前 Git 基线和代码摘要的控制面审计，不写文件或修改仓库。"""
    root = Path(project).expanduser().resolve()
    baseline = load_baseline(root, baseline_path)
    excluded = {str(path).replace("\\", "/").strip("/") for path in (exclude_paths or set())}
    snapshot_before = current_delivery_snapshot(root, baseline_path, exclude_paths=excluded)
    changes, warnings = collect_changed_entries(root, baseline_path)
    if excluded:
        changes = [
            change for change in changes
            if not any(
                change.path.replace("\\", "/") == prefix
                or change.path.replace("\\", "/").startswith(prefix + "/")
                for prefix in excluded
            )
        ]
    snapshot_after = current_delivery_snapshot(root, baseline_path, exclude_paths=excluded)
    if snapshot_before["snapshot_sha256"] != snapshot_after["snapshot_sha256"]:
        raise StaticAnalysisError("控制面审计期间代码发生变化，请在代码稳定后重试")
    return {
        "version": 1,
        "producer": CONTROL_AUDIT_PRODUCER,
        "project_path": str(root),
        "baseline_id": baseline["id"],
        "snapshot_sha256": snapshot_after["snapshot_sha256"],
        "warnings": warnings,
        "control_changes": audit_control_changes(changes),
    }


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    """输出 JSON；显式文件使用原子替换，避免中断后留下半份审计结果。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(text, end="")
        return
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(target)
    print(target)


def main(argv: list[str] | None = None) -> int:
    """提供 SARIF 摘要、稳定问题编号和当前需求控制面审计三个独立子命令。"""
    parser = ChineseArgumentParser(description="生成 Android 静态分析机器证据")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    sarif_parser = subparsers.add_parser("sarif", help="规范化一个 SARIF 报告")
    sarif_parser.add_argument("--report", required=True, help="SARIF 报告路径")
    sarif_parser.add_argument("--project", default=None, help="用于生成相对路径的项目根目录")
    sarif_parser.add_argument("--output", default=None, help="可选输出 JSON 路径")

    id_parser = subparsers.add_parser("finding-id", help="生成稳定问题编号")
    id_parser.add_argument("--tool", required=True, help="工具或 android-audit-stability")
    id_parser.add_argument("--rule", required=True, help="规则或不变量编号")
    id_parser.add_argument("--path", required=True, help="项目相对路径")
    id_parser.add_argument("--symbol", default="", help="类、方法或资源符号")
    id_parser.add_argument("--message", default="", help="稳定语义摘要")
    id_parser.add_argument("--fingerprint", default="", help="工具已有指纹，优先于摘要")

    audit_parser = subparsers.add_parser("audit-controls", help="审计当前需求的静态门禁控制面变化")
    audit_parser.add_argument("--config", default=None, help="本机配置文件路径")
    audit_parser.add_argument("--output", default=None, help="可选输出 JSON 路径")
    args = parser.parse_args(argv)

    try:
        if args.command_name == "sarif":
            payload = summarize_sarif(args.report, args.project)
            _write_json(Path(args.output) if args.output else None, payload)
            return 0
        if args.command_name == "finding-id":
            print(stable_finding_id(
                tool=args.tool,
                rule_id=args.rule,
                path=args.path,
                symbol=args.symbol,
                message=args.message,
                fingerprint=args.fingerprint,
            ))
            return 0

        config_path = Path(args.config).expanduser().resolve() if args.config else (
            Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
        )
        config = load_config(config_path)
        paths = resolve_config_paths(config, config_path)
        if not paths.project_path:
            raise StaticAnalysisError("配置缺少 project_path")
        baseline_path = baseline_path_for_config(config_path)
        excluded = delivery_snapshot_exclusions(paths.project_path, paths.requirement_dir)
        payload = build_control_audit(
            paths.project_path,
            baseline_path,
            exclude_paths=excluded,
        )
        _write_json(Path(args.output) if args.output else None, payload)
        return 0
    except (DeliveryError, GitInspectionError, OSError, StaticAnalysisError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
