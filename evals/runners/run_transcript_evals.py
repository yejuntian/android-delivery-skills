#!/usr/bin/env python3
"""脚本名称：run_transcript_evals.py

用途：执行基于对话记录回放的 Android Delivery 流程门禁 Evals。

核心流程：读取 evals/scenarios/transcript/*.yaml，从 transcript 中提取显式事件标记，
再复用 flow_gate Oracle 按当前 active-contracts.yaml 判断是否越过流程门禁。

职责边界：只编排 transcript 回放场景；不调用模型、不解析自然语言语义、不运行 Android
构建或真实 delivery 命令。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evals.oracles.contract_loader import ContractError, default_contract_path, load_contracts  # noqa: E402
from evals.oracles.flow_gate import evaluate_flow_gates  # noqa: E402
from evals.oracles.transcript_events import TranscriptEventError, extract_trace_events  # noqa: E402


class TranscriptEvalError(RuntimeError):
    """表示 transcript 评测场景或期望配置不合法。"""


def default_repository_root() -> Path:
    """返回脚本所在仓库根目录，允许从任意 cwd 调用。"""
    return REPOSITORY_ROOT


def read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件并要求根节点为 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise TranscriptEvalError(f"无法读取 YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TranscriptEvalError(f"YAML 根节点必须是 object: {path}")
    return data


def require_text(value: Any, field: str, path: Path) -> str:
    """读取必填字符串字段，空白字符串视为配置错误。"""
    if not isinstance(value, str) or not value.strip():
        raise TranscriptEvalError(f"{path}: {field} 必须是非空字符串")
    return value


def load_rubric_ids(root: Path) -> set[str]:
    """读取 evals/rubrics 下的 rubric id，防止场景引用不存在的评分口径。"""
    ids: set[str] = set()
    for path in sorted((root / "evals" / "rubrics").glob("*.yaml")):
        data = read_yaml(path)
        rubric_id = data.get("id")
        if not isinstance(rubric_id, str) or not rubric_id.strip():
            raise TranscriptEvalError(f"rubric 缺少 id: {path}")
        ids.add(rubric_id)
    if not ids:
        raise TranscriptEvalError("未发现 rubric")
    return ids


def evaluate_check(contract_set: Any, check: dict[str, Any], scenario_path: Path) -> dict[str, Any]:
    """执行单条 transcript check，并核对实际门禁结果是否符合 expect。"""
    name = require_text(check.get("name"), "check.name", scenario_path)
    transcript = require_text(check.get("transcript"), "check.transcript", scenario_path)
    expect = check.get("expect")
    if not isinstance(expect, dict):
        raise TranscriptEvalError(f"{scenario_path}: check.expect 必须是 object")
    expected_passed = expect.get("passed")
    if not isinstance(expected_passed, bool):
        raise TranscriptEvalError(f"{scenario_path}: check.expect.passed 必须是 bool")
    try:
        trace = extract_trace_events(transcript)
    except TranscriptEventError as exc:
        raise TranscriptEvalError(f"{scenario_path}: {exc}") from exc

    violations = evaluate_flow_gates(contract_set, trace)
    actual_passed = not violations
    violation_contracts = sorted({violation.contract_id for violation in violations})
    messages: list[str] = []
    if actual_passed != expected_passed:
        messages.append(f"期望 passed={expected_passed}，实际 passed={actual_passed}")
    expected_contracts = expect.get("violation_contracts", [])
    if not isinstance(expected_contracts, list) or any(
        not isinstance(item, str) for item in expected_contracts
    ):
        raise TranscriptEvalError(f"{scenario_path}: violation_contracts 必须是字符串数组")
    missing = sorted(set(expected_contracts) - set(violation_contracts))
    if missing:
        messages.append(f"未命中期望违规契约: {', '.join(missing)}")

    return {
        "name": name,
        "passed": not messages,
        "messages": messages,
        "actual_passed": actual_passed,
        "events": [event.event for event in trace],
        "violation_contracts": violation_contracts,
    }


def evaluate_scenario(root: Path, scenario_path: Path, rubric_ids: set[str]) -> dict[str, Any]:
    """执行单个 transcript 场景并返回结构化结果。"""
    scenario = read_yaml(scenario_path)
    scenario_id = require_text(scenario.get("id"), "id", scenario_path)
    title = require_text(scenario.get("title"), "title", scenario_path)
    if scenario.get("type") != "transcript_replay":
        raise TranscriptEvalError(f"{scenario_path}: type 必须是 transcript_replay")
    rubric = require_text(scenario.get("rubric"), "rubric", scenario_path)
    if rubric not in rubric_ids:
        raise TranscriptEvalError(f"场景引用了不存在的 rubric: {scenario_path}: {rubric}")
    checks = scenario.get("checks")
    if not isinstance(checks, list) or not checks or any(not isinstance(item, dict) for item in checks):
        raise TranscriptEvalError(f"{scenario_path}: checks 必须是非空 object 数组")
    contract_set = load_contracts(default_contract_path(root))
    check_results = [evaluate_check(contract_set, check, scenario_path) for check in checks]
    return {
        "id": scenario_id,
        "title": title,
        "rubric": rubric,
        "passed": all(item["passed"] for item in check_results),
        "checks": check_results,
    }


def run_evals(root: Path) -> dict[str, Any]:
    """执行全部 transcript 场景并汇总总数、通过数和失败数。"""
    scenario_dir = root / "evals" / "scenarios" / "transcript"
    scenario_paths = sorted(scenario_dir.glob("*.yaml"))
    if not scenario_paths:
        raise TranscriptEvalError(f"未发现 transcript 评测场景: {scenario_dir}")
    rubric_ids = load_rubric_ids(root)
    scenarios = [evaluate_scenario(root, path, rubric_ids) for path in scenario_paths]
    passed = sum(1 for item in scenarios if item["passed"])
    return {
        "producer": "android-delivery-transcript-evals",
        "version": 1,
        "root": str(root.resolve()),
        "summary": {"total": len(scenarios), "passed": passed, "failed": len(scenarios) - passed},
        "scenarios": scenarios,
    }


def print_text_report(report: dict[str, Any]) -> None:
    """输出面向维护者的简洁中文 transcript 评测结果。"""
    summary = report["summary"]
    print(f"Transcript Evals: {summary['passed']}/{summary['total']} 通过，失败 {summary['failed']}")
    for scenario in report["scenarios"]:
        status = "PASS" if scenario["passed"] else "FAIL"
        print(f"- {status} {scenario['id']} {scenario['title']}")
        for check in scenario["checks"]:
            if check["passed"]:
                continue
            print(f"  - {check['name']}")
            for message in check["messages"]:
                print(f"    - {message}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数，默认以当前脚本定位仓库根目录。"""
    parser = argparse.ArgumentParser(description="Run transcript replay evals for Android Delivery Skills.")
    parser.add_argument("--root", default=str(default_repository_root()), help="仓库根目录")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：执行 transcript 评测并按失败数设置退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_evals(Path(args.root).expanduser().resolve())
    except (TranscriptEvalError, ContractError) as exc:
        print(f"Transcript Evals 配置错误: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
