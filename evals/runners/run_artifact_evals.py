#!/usr/bin/env python3
"""脚本名称：run_artifact_evals.py

用途：执行 Android Delivery 流程仓库的本地确定性 Evals。

核心流程：读取 evals/scenarios/*.yaml 中声明的文件存在、字符串和正则检查，
验证那些不需要真实 Android 项目也能机器判断的流程不变量，例如 FLOW 总览不进入
运行时规则、docx 首次输入后切换 md、测试按用例驱动、STALE 映射阻断和防假绿门禁。

职责边界：只检查本仓库流程资产，不调用模型、不运行 Android 构建、不读取用户真实
requirement_dir，也不替代人工/多 Agent forward test。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


@dataclass(frozen=True)
class CheckResult:
    """保存单条 artifact check 的执行结果，便于生成 JSON 报告。"""

    name: str
    passed: bool
    messages: list[str]


class ArtifactEvalError(RuntimeError):
    """表示评测场景、rubric 或目标文件配置不合法。"""


def default_repository_root() -> Path:
    """返回脚本所在仓库根目录，允许从任意 cwd 调用。"""
    return Path(__file__).resolve().parents[2]


def read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件并要求根节点为 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ArtifactEvalError(f"无法读取 YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactEvalError(f"YAML 根节点必须是 object: {path}")
    return data


def ensure_string_list(value: Any, field: str, scenario_path: Path) -> list[str]:
    """把可选字段校验为字符串数组，缺失时返回空数组。"""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ArtifactEvalError(f"{scenario_path}: {field} 必须是字符串数组")
    return value


def load_rubric_ids(root: Path) -> set[str]:
    """读取 evals/rubrics 下的 rubric id，用于防止场景引用不存在的评分口径。"""
    rubric_dir = root / "evals" / "rubrics"
    ids: set[str] = set()
    for path in sorted(rubric_dir.glob("*.yaml")):
        data = read_yaml(path)
        rubric_id = data.get("id")
        if not isinstance(rubric_id, str) or not rubric_id.strip():
            raise ArtifactEvalError(f"rubric 缺少 id: {path}")
        ids.add(rubric_id)
    if not ids:
        raise ArtifactEvalError(f"未发现 rubric: {rubric_dir}")
    return ids


def expand_check_paths(root: Path, check: dict[str, Any], scenario_path: Path) -> list[Path]:
    """解析 check 中的 path/paths/globs，返回去重后的仓库内文件路径。"""
    raw_paths: list[str] = []
    single_path = check.get("path")
    if single_path is not None:
        if not isinstance(single_path, str):
            raise ArtifactEvalError(f"{scenario_path}: check.path 必须是字符串")
        raw_paths.append(single_path)
    raw_paths.extend(ensure_string_list(check.get("paths"), "check.paths", scenario_path))

    resolved: list[Path] = []
    for raw_path in raw_paths:
        candidate = (root / raw_path).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ArtifactEvalError(f"{scenario_path}: path 越出仓库: {raw_path}")
        resolved.append(candidate)

    for pattern in ensure_string_list(check.get("globs"), "check.globs", scenario_path):
        matches = sorted(root.glob(pattern))
        if not matches:
            raise ArtifactEvalError(f"{scenario_path}: glob 没有匹配文件: {pattern}")
        for match in matches:
            candidate = match.resolve()
            if candidate.is_file() and candidate.is_relative_to(root.resolve()):
                resolved.append(candidate)

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in resolved:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    if not unique:
        raise ArtifactEvalError(f"{scenario_path}: check 必须提供 path、paths 或 globs")
    return unique


def read_check_text(paths: list[Path]) -> tuple[str, list[str]]:
    """读取 check 涉及的所有文件并拼接文本，返回文本和错误。"""
    chunks: list[str] = []
    errors: list[str] = []
    for path in paths:
        if not path.is_file():
            errors.append(f"文件不存在: {path}")
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            errors.append(f"文件无法读取: {path}: {exc}")
    return "\n".join(chunks), errors


def evaluate_check(root: Path, check: dict[str, Any], scenario_path: Path) -> CheckResult:
    """执行单条 check，支持 contains/not_contains/regex/not_regex。"""
    name = check.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ArtifactEvalError(f"{scenario_path}: check.name 必须是非空字符串")
    paths = expand_check_paths(root, check, scenario_path)
    text, messages = read_check_text(paths)

    for needle in ensure_string_list(check.get("contains"), "check.contains", scenario_path):
        if needle not in text:
            messages.append(f"缺少文本: {needle}")
    for needle in ensure_string_list(check.get("not_contains"), "check.not_contains", scenario_path):
        if needle in text:
            messages.append(f"出现禁用文本: {needle}")
    for pattern in ensure_string_list(check.get("regex"), "check.regex", scenario_path):
        if re.search(pattern, text, flags=re.MULTILINE) is None:
            messages.append(f"正则未匹配: {pattern}")
    for pattern in ensure_string_list(check.get("not_regex"), "check.not_regex", scenario_path):
        if re.search(pattern, text, flags=re.MULTILINE) is not None:
            messages.append(f"禁用正则被匹配: {pattern}")

    return CheckResult(name=name, passed=not messages, messages=messages)


def evaluate_scenario(root: Path, scenario_path: Path, rubric_ids: set[str]) -> dict[str, Any]:
    """执行单个场景文件并返回结构化结果。"""
    scenario = read_yaml(scenario_path)
    scenario_id = scenario.get("id")
    title = scenario.get("title")
    rubric = scenario.get("rubric")
    checks = scenario.get("checks")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ArtifactEvalError(f"场景缺少 id: {scenario_path}")
    if not isinstance(title, str) or not title.strip():
        raise ArtifactEvalError(f"场景缺少 title: {scenario_path}")
    if not isinstance(rubric, str) or rubric not in rubric_ids:
        raise ArtifactEvalError(f"场景引用了不存在的 rubric: {scenario_path}: {rubric}")
    if not isinstance(checks, list) or not checks or any(not isinstance(item, dict) for item in checks):
        raise ArtifactEvalError(f"场景 checks 必须是非空 object 数组: {scenario_path}")

    check_results = [evaluate_check(root, check, scenario_path) for check in checks]
    return {
        "id": scenario_id,
        "title": title,
        "rubric": rubric,
        "passed": all(item.passed for item in check_results),
        "checks": [
            {"name": item.name, "passed": item.passed, "messages": item.messages}
            for item in check_results
        ],
    }


def run_evals(root: Path) -> dict[str, Any]:
    """执行全部 artifact eval 场景并汇总总数、通过数和失败数。"""
    scenario_dir = root / "evals" / "scenarios"
    scenario_paths = sorted(scenario_dir.glob("*.yaml"))
    if not scenario_paths:
        raise ArtifactEvalError(f"未发现评测场景: {scenario_dir}")
    rubric_ids = load_rubric_ids(root)
    scenarios = [evaluate_scenario(root, path, rubric_ids) for path in scenario_paths]
    passed = sum(1 for item in scenarios if item["passed"])
    return {
        "producer": "android-delivery-artifact-evals",
        "version": 1,
        "root": str(root.resolve()),
        "summary": {
            "total": len(scenarios),
            "passed": passed,
            "failed": len(scenarios) - passed,
        },
        "scenarios": scenarios,
    }


def print_text_report(report: dict[str, Any]) -> None:
    """输出面向维护者的简洁中文评测结果。"""
    summary = report["summary"]
    print(
        f"Artifact Evals: {summary['passed']}/{summary['total']} 通过，"
        f"失败 {summary['failed']}"
    )
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
    parser = argparse.ArgumentParser(description="Run local artifact evals for Android Delivery Skills.")
    parser.add_argument("--root", default=str(default_repository_root()), help="仓库根目录")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：执行评测并按失败数设置退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_evals(Path(args.root).expanduser().resolve())
    except ArtifactEvalError as exc:
        print(f"Artifact Evals 配置错误: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
