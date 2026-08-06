#!/usr/bin/env python3
"""脚本名称：validate_maintenance.py

用途：作为 Android Delivery Skill 流程维护的统一本地验证入口。

核心流程：从仓库根目录依次运行 Skill catalog、规则归属、流程文档同步和 fast eval，确保
共享规则、Skill、流程契约、行为回放与命令门禁仍然接线且全绿；任一命令失败时返回非零退出码。

职责边界：只负责编排维护验证命令和汇总结果；不实现具体评测逻辑、不修改文件、不运行
Android 构建、设备、真实项目交付或模型服务。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


@dataclass(frozen=True)
class MaintenanceCommand:
    """保存一条维护验证命令及其中文用途。"""

    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class MaintenanceResult:
    """保存一条维护验证命令的执行结果。"""

    name: str
    exit_code: int
    command: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """判断命令是否成功完成。"""
        return self.exit_code == 0


def default_repository_root() -> Path:
    """返回脚本所在仓库根目录，允许从任意 cwd 调用。"""
    return Path(__file__).resolve().parents[1]


def planned_commands() -> tuple[MaintenanceCommand, ...]:
    """返回维护验证固定命令列表；具体评测逻辑由各自脚本负责。"""
    return (
        MaintenanceCommand(
            name="Skill catalog 校验",
            argv=(sys.executable, "scripts/validate_skill_catalog.py"),
        ),
        MaintenanceCommand(
            name="规则归属测试",
            argv=(sys.executable, "-m", "unittest", "scripts.tests.test_skill_rule_ownership", "-q"),
        ),
        MaintenanceCommand(
            name="流程文档同步",
            argv=(sys.executable, "scripts/render_flow_docs.py", "--check"),
        ),
        MaintenanceCommand(
            name="流程 fast eval",
            argv=(sys.executable, "evals/runners/run_evals.py", "--suite", "fast"),
        ),
    )


def run_validation(root: Path, commands: tuple[MaintenanceCommand, ...] | None = None) -> dict[str, Any]:
    """执行维护验证命令并返回结构化汇总。"""
    selected = commands or planned_commands()
    results: list[MaintenanceResult] = []
    for command in selected:
        print(f"==> {command.name}: {' '.join(command.argv)}", flush=True)
        completed = subprocess.run(command.argv, cwd=root, check=False)
        results.append(
            MaintenanceResult(
                name=command.name,
                exit_code=completed.returncode,
                command=command.argv,
            )
        )
        if completed.returncode != 0:
            # 维护验证按顺序短路，避免后续结果掩盖第一个真实失败点。
            break
    passed = sum(1 for result in results if result.passed)
    return {
        "producer": "android-delivery-maintenance-validation",
        "version": 1,
        "root": str(root.resolve()),
        "summary": {
            "total": len(selected),
            "executed": len(results),
            "passed": passed,
            "failed": len(results) - passed,
        },
        "results": [
            {
                "name": result.name,
                "exit_code": result.exit_code,
                "passed": result.passed,
                "command": list(result.command),
            }
            for result in results
        ],
    }


def print_text_report(report: dict[str, Any]) -> None:
    """输出面向维护者的简洁中文维护验证结果。"""
    summary = report["summary"]
    print(
        f"维护验证: {summary['passed']}/{summary['total']} 通过，"
        f"已执行 {summary['executed']}，失败 {summary['failed']}"
    )
    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"- {status} {result['name']} (exit={result['exit_code']})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Run Android Delivery maintenance validation.")
    parser.add_argument("--root", default=str(default_repository_root()), help="仓库根目录")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：执行维护验证并按失败数设置退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).expanduser().resolve()
    report = run_validation(root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
