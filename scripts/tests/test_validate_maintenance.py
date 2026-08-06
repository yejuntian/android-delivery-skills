#!/usr/bin/env python3
"""脚本名称：test_validate_maintenance.py

用途：验证统一维护验证入口会编排 catalog、规则归属、流程文档同步和 fast eval。

核心流程：检查 planned_commands 的命令列表，并通过 mock subprocess.run 验证成功与失败时的汇总。
测试不运行真实 Android 项目、设备、网络或模型服务。

职责边界：只验证 validate_maintenance.py 的编排职责，不重新执行具体 eval 逻辑。
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import unittest
import sys
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
# 同时支持 IDE 包测试、`python -m` 和直接运行当前测试文件。
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from .. import validate_maintenance as validate_maintenance_module  # noqa: E402
from ..validate_maintenance import planned_commands, run_validation  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ValidateMaintenanceTests(unittest.TestCase):
    """验证统一维护验证入口的固定命令和失败短路行为。"""

    def test_planned_commands_include_all_maintenance_checks(self) -> None:
        """确认维护入口固定接线四项维护检查。"""
        commands = planned_commands()
        joined = [" ".join(command.argv) for command in commands]
        self.assertEqual(
            ["Skill catalog 校验", "规则归属测试", "流程文档同步", "流程 fast eval"],
            [command.name for command in commands],
        )
        self.assertIn("scripts/validate_skill_catalog.py", joined[0])
        self.assertIn("scripts.tests.test_skill_rule_ownership", joined[1])
        self.assertIn("scripts/render_flow_docs.py --check", joined[2])
        self.assertIn("evals/runners/run_evals.py", joined[3])
        self.assertIn("--suite fast", joined[3])

    def test_run_validation_summarizes_success(self) -> None:
        """验证四个命令都成功时汇总为全绿。"""
        with mock.patch.object(
            validate_maintenance_module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0),
        ) as run:
            with redirect_stdout(io.StringIO()):
                report = run_validation(REPOSITORY_ROOT)
        self.assertEqual(4, run.call_count)
        self.assertEqual(0, report["summary"]["failed"])
        self.assertEqual(4, report["summary"]["passed"])

    def test_run_validation_stops_after_first_failure(self) -> None:
        """验证第一个维护命令失败后短路，避免后续结果掩盖失败点。"""
        with mock.patch.object(
            validate_maintenance_module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(args=[], returncode=1),
        ) as run:
            with redirect_stdout(io.StringIO()):
                report = run_validation(REPOSITORY_ROOT)
        self.assertEqual(1, run.call_count)
        self.assertEqual(1, report["summary"]["failed"])
        self.assertEqual(1, report["summary"]["executed"])


if __name__ == "__main__":
    unittest.main()
