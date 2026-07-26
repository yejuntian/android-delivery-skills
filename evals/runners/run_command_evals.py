#!/usr/bin/env python3
"""脚本名称：run_command_evals.py

用途：执行 Android Delivery 流程维护中的命令级 Evals。

核心流程：读取 evals/scenarios/command/*.yaml，按场景声明运行本仓库的最小命令，
再用 exit_code、stdout/stderr 包含或排除断言判断结果是否符合预期。

职责边界：只负责编排命令和断言命令输出；不理解 Android 业务语义、不实现交付门禁、
不生成 fixture，也不调用模型或设备。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


@dataclass(frozen=True)
class CommandResult:
    """保存单条命令检查的结果和失败信息。"""

    name: str
    passed: bool
    messages: list[str]
    exit_code: int


class CommandEvalError(RuntimeError):
    """表示命令评测场景配置不合法。"""


def default_repository_root() -> Path:
    """返回脚本所在仓库根目录，允许从任意 cwd 调用。"""
    return Path(__file__).resolve().parents[2]


def read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件并要求根节点为 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CommandEvalError(f"无法读取 YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CommandEvalError(f"YAML 根节点必须是 object: {path}")
    return data


def require_text(value: Any, field: str, path: Path) -> str:
    """读取必填字符串字段，空白字符串视为配置错误。"""
    if not isinstance(value, str) or not value.strip():
        raise CommandEvalError(f"{path}: {field} 必须是非空字符串")
    return value.strip()


def string_list(value: Any, field: str, path: Path) -> list[str]:
    """读取可选字符串数组字段。"""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CommandEvalError(f"{path}: {field} 必须是字符串数组")
    return value


def command_list(value: Any, field: str, path: Path) -> list[str]:
    """读取命令参数数组，禁止 shell 字符串以降低维护风险。"""
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise CommandEvalError(f"{path}: {field} 必须是非空字符串数组")
    return value


def resolve_cwd(root: Path, raw_cwd: Any, path: Path) -> Path:
    """解析命令工作目录，默认使用仓库根目录且不得越出仓库。"""
    cwd = root if raw_cwd is None else (root / require_text(raw_cwd, "cwd", path)).resolve()
    root_resolved = root.resolve()
    if not cwd.is_relative_to(root_resolved):
        raise CommandEvalError(f"{path}: cwd 越出仓库: {cwd}")
    if not cwd.is_dir():
        raise CommandEvalError(f"{path}: cwd 不存在: {cwd}")
    return cwd


def run_check(root: Path, scenario_path: Path, check: dict[str, Any]) -> CommandResult:
    """运行单条 command check 并执行输出断言。"""
    name = require_text(check.get("name"), "check.name", scenario_path)
    command = command_list(check.get("command"), "check.command", scenario_path)
    cwd = resolve_cwd(root, check.get("cwd"), scenario_path)
    timeout = check.get("timeout_seconds", 60)
    if not isinstance(timeout, int) or timeout <= 0:
        raise CommandEvalError(f"{scenario_path}: timeout_seconds 必须是正整数")
    expect = check.get("expect")
    if not isinstance(expect, dict):
        raise CommandEvalError(f"{scenario_path}: check.expect 必须是 object")
    expected_exit = expect.get("exit_code", 0)
    if not isinstance(expected_exit, int):
        raise CommandEvalError(f"{scenario_path}: expect.exit_code 必须是整数")

    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    messages: list[str] = []
    if completed.returncode != expected_exit:
        messages.append(f"退出码期望 {expected_exit}，实际 {completed.returncode}")
    stdout = completed.stdout
    stderr = completed.stderr
    combined = stdout + "\n" + stderr
    for needle in string_list(expect.get("stdout_contains"), "expect.stdout_contains", scenario_path):
        if needle not in stdout:
            messages.append(f"stdout 缺少文本: {needle}")
    for needle in string_list(expect.get("stderr_contains"), "expect.stderr_contains", scenario_path):
        if needle not in stderr:
            messages.append(f"stderr 缺少文本: {needle}")
    for needle in string_list(expect.get("combined_contains"), "expect.combined_contains", scenario_path):
        if needle not in combined:
            messages.append(f"输出缺少文本: {needle}")
    for needle in string_list(expect.get("combined_not_contains"), "expect.combined_not_contains", scenario_path):
        if needle in combined:
            messages.append(f"输出出现禁用文本: {needle}")

    return CommandResult(
        name=name,
        passed=not messages,
        messages=messages,
        exit_code=completed.returncode,
    )


def load_rubric_ids(root: Path) -> set[str]:
    """读取 evals/rubrics 下的 rubric id，用于防止场景引用不存在的评分口径。"""
    rubric_dir = root / "evals" / "rubrics"
    ids: set[str] = set()
    for path in sorted(rubric_dir.glob("*.yaml")):
        data = read_yaml(path)
        rubric_id = data.get("id")
        if not isinstance(rubric_id, str) or not rubric_id.strip():
            raise CommandEvalError(f"rubric 缺少 id: {path}")
        ids.add(rubric_id)
    if not ids:
        raise CommandEvalError(f"未发现 rubric: {rubric_dir}")
    return ids


def evaluate_scenario(root: Path, scenario_path: Path, rubric_ids: set[str]) -> dict[str, Any]:
    """执行单个命令场景并返回结构化结果。"""
    scenario = read_yaml(scenario_path)
    scenario_id = require_text(scenario.get("id"), "id", scenario_path)
    title = require_text(scenario.get("title"), "title", scenario_path)
    if scenario.get("type") != "command":
        raise CommandEvalError(f"{scenario_path}: type 必须是 command")
    rubric = require_text(scenario.get("rubric"), "rubric", scenario_path)
    if rubric not in rubric_ids:
        raise CommandEvalError(f"场景引用了不存在的 rubric: {scenario_path}: {rubric}")
    checks = scenario.get("checks")
    if not isinstance(checks, list) or not checks or any(not isinstance(item, dict) for item in checks):
        raise CommandEvalError(f"{scenario_path}: checks 必须是非空 object 数组")
    check_results = [run_check(root, scenario_path, check) for check in checks]
    return {
        "id": scenario_id,
        "title": title,
        "rubric": rubric,
        "passed": all(item.passed for item in check_results),
        "checks": [
            {
                "name": item.name,
                "passed": item.passed,
                "messages": item.messages,
                "exit_code": item.exit_code,
            }
            for item in check_results
        ],
    }


def run_evals(root: Path) -> dict[str, Any]:
    """执行全部 command 场景并汇总总数、通过数和失败数。"""
    scenario_dir = root / "evals" / "scenarios" / "command"
    scenario_paths = sorted(scenario_dir.glob("*.yaml"))
    if not scenario_paths:
        raise CommandEvalError(f"未发现命令评测场景: {scenario_dir}")
    rubric_ids = load_rubric_ids(root)
    scenarios = [evaluate_scenario(root, path, rubric_ids) for path in scenario_paths]
    passed = sum(1 for item in scenarios if item["passed"])
    return {
        "producer": "android-delivery-command-evals",
        "version": 1,
        "root": str(root.resolve()),
        "summary": {"total": len(scenarios), "passed": passed, "failed": len(scenarios) - passed},
        "scenarios": scenarios,
    }


def print_text_report(report: dict[str, Any]) -> None:
    """输出面向维护者的简洁中文命令评测结果。"""
    summary = report["summary"]
    print(f"Command Evals: {summary['passed']}/{summary['total']} 通过，失败 {summary['failed']}")
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
    parser = argparse.ArgumentParser(description="Run command evals for Android Delivery Skills.")
    parser.add_argument("--root", default=str(default_repository_root()), help="仓库根目录")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：执行命令评测并按失败数设置退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_evals(Path(args.root).expanduser().resolve())
    except (CommandEvalError, subprocess.TimeoutExpired) as exc:
        print(f"Command Evals 配置错误: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
