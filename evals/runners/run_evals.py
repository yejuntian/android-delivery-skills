#!/usr/bin/env python3
"""脚本名称：run_evals.py

用途：统一编排 Android Delivery 流程维护用的轻量本地 Evals。

核心流程：按 suite 参数调用单一职责的评测模块；artifact suite 复用既有
run_artifact_evals.py，contracts suite 检查 active-contracts.yaml 的来源、Oracle 和场景覆盖，
最后汇总为 text 或 JSON 报告并用退出码表示是否通过。

职责边界：只负责编排和汇总；不直接解析契约细节、不实现具体 Oracle 判断、不运行
Android 构建、设备、真实项目交付或模型评测。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    # 支持直接以脚本路径运行，而不要求调用方设置 PYTHONPATH。
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evals.oracles.contract_coverage import evaluate_contract_coverage  # noqa: E402
from evals.oracles.contract_loader import ContractError  # noqa: E402
from evals.runners import run_artifact_evals, run_behavior_evals, run_command_evals  # noqa: E402


SUITE_ALIASES = {
    "artifact": ("artifact",),
    "behavior": ("behavior",),
    "command": ("command",),
    "contracts": ("contracts",),
    "fast": ("artifact", "contracts", "behavior", "command"),
    "all": ("artifact", "contracts", "behavior", "command"),
}


class EvalRunnerError(RuntimeError):
    """表示 suite 名称或底层评测执行结果不合法。"""


def default_repository_root() -> Path:
    """返回脚本所在仓库根目录，允许从任意 cwd 调用。"""
    return REPOSITORY_ROOT


def expand_suite_alias(alias: str) -> tuple[str, ...]:
    """把用户传入的 suite 名称展开成实际执行的 suite 列表。"""
    try:
        return SUITE_ALIASES[alias]
    except KeyError as exc:
        raise EvalRunnerError(f"未知 suite: {alias}") from exc


def run_suite(root: Path, suite: str) -> dict[str, Any]:
    """运行一个具体 suite，并返回标准化结构。"""
    if suite == "artifact":
        report = run_artifact_evals.run_evals(root)
    elif suite == "contracts":
        report = evaluate_contract_coverage(root)
    elif suite == "behavior":
        report = run_behavior_evals.run_evals(root)
    elif suite == "command":
        report = run_command_evals.run_evals(root)
    else:
        raise EvalRunnerError(f"未实现 suite: {suite}")
    summary = report.get("summary")
    if not isinstance(summary, dict) or "failed" not in summary or "total" not in summary:
        raise EvalRunnerError(f"suite 报告缺少 summary: {suite}")
    return {"suite": suite, "report": report}


def run_selected_suites(root: Path, suite_alias: str) -> dict[str, Any]:
    """执行 suite 别名对应的全部评测并生成统一报告。"""
    suites = [run_suite(root, suite) for suite in expand_suite_alias(suite_alias)]
    total = sum(int(item["report"]["summary"]["total"]) for item in suites)
    failed = sum(int(item["report"]["summary"]["failed"]) for item in suites)
    return {
        "producer": "android-delivery-evals",
        "version": 1,
        "root": str(root.resolve()),
        "suite": suite_alias,
        "summary": {
            "total": total,
            "passed": total - failed,
            "failed": failed,
        },
        "suites": suites,
    }


def print_text_report(report: dict[str, Any]) -> None:
    """输出面向维护者的简洁中文统一评测结果。"""
    summary = report["summary"]
    print(f"Android Delivery Evals: {summary['passed']}/{summary['total']} 通过，失败 {summary['failed']}")
    for suite_result in report["suites"]:
        suite = suite_result["suite"]
        suite_report = suite_result["report"]
        suite_summary = suite_report["summary"]
        print(
            f"- {suite}: {suite_summary['passed']}/{suite_summary['total']} 通过，"
            f"失败 {suite_summary['failed']}"
        )
        if suite == "artifact":
            print_artifact_failures(suite_report)
        elif suite == "contracts":
            print_contract_failures(suite_report)
        elif suite == "behavior":
            print_behavior_failures(suite_report)
        elif suite == "command":
            print_command_failures(suite_report)


def print_artifact_failures(report: dict[str, Any]) -> None:
    """输出 artifact suite 的失败场景，成功场景保持折叠。"""
    for scenario in report.get("scenarios", []):
        if scenario.get("passed"):
            continue
        print(f"  - FAIL {scenario.get('id')} {scenario.get('title')}")
        for check in scenario.get("checks", []):
            if check.get("passed"):
                continue
            print(f"    - {check.get('name')}")
            for message in check.get("messages", []):
                print(f"      - {message}")


def print_contract_failures(report: dict[str, Any]) -> None:
    """输出 contract suite 的失败契约，成功契约保持折叠。"""
    for check in report.get("checks", []):
        if check.get("passed"):
            continue
        print(f"  - FAIL {check.get('contract_id')}")
        for message in check.get("messages", []):
            print(f"    - {message}")


def print_behavior_failures(report: dict[str, Any]) -> None:
    """输出 behavior suite 的失败场景，成功场景保持折叠。"""
    for scenario in report.get("scenarios", []):
        if scenario.get("passed"):
            continue
        print(f"  - FAIL {scenario.get('id')} {scenario.get('title')}")
        for check in scenario.get("checks", []):
            if check.get("passed"):
                continue
            print(f"    - {check.get('name')}")
            for message in check.get("messages", []):
                print(f"      - {message}")


def print_command_failures(report: dict[str, Any]) -> None:
    """输出 command suite 的失败场景，成功场景保持折叠。"""
    for scenario in report.get("scenarios", []):
        if scenario.get("passed"):
            continue
        print(f"  - FAIL {scenario.get('id')} {scenario.get('title')}")
        for check in scenario.get("checks", []):
            if check.get("passed"):
                continue
            print(f"    - {check.get('name')}")
            for message in check.get("messages", []):
                print(f"      - {message}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Run Android Delivery local eval suites.")
    parser.add_argument("--root", default=str(default_repository_root()), help="仓库根目录")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITE_ALIASES),
        default="fast",
        help="评测套件：fast=artifact+contracts",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：执行指定 suite 并按失败数设置退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_selected_suites(Path(args.root).expanduser().resolve(), args.suite)
    except (
        ContractError,
        EvalRunnerError,
        run_artifact_evals.ArtifactEvalError,
        run_behavior_evals.BehaviorEvalError,
        run_command_evals.CommandEvalError,
    ) as exc:
        print(f"Android Delivery Evals 配置错误: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
