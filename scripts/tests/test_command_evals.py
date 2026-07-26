#!/usr/bin/env python3
"""脚本名称：test_command_evals.py

用途：验证命令级 Evals 可以运行真实脚本/单测门禁，补足 artifact 和 behavior eval 的盲区。

核心流程：执行 run_command_evals.py 的 JSON 输出，要求命令场景全部通过，并确认覆盖了计划确认、
STALE 测试映射、零测试假绿和条件 gate 并集四类硬门禁。
测试只运行本仓库最小 unittest 命令，不接触真实 Android 项目、设备、网络或模型服务。

职责边界：只验证 command eval runner 和场景接线，不重新实现具体门禁判断。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "evals" / "runners" / "run_command_evals.py"


class CommandEvalTests(unittest.TestCase):
    """验证命令级评测套件稳定执行。"""

    def test_command_evals_pass(self) -> None:
        """执行全部命令场景，并要求四类高价值硬门禁全部被覆盖。"""
        completed = subprocess.run(
            [sys.executable, str(RUNNER), "--root", str(REPOSITORY_ROOT), "--format", "json"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            0,
            completed.returncode,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        report = json.loads(completed.stdout)
        self.assertEqual("android-delivery-command-evals", report["producer"])
        self.assertEqual(0, report["summary"]["failed"])
        scenario_ids = {scenario["id"] for scenario in report["scenarios"]}
        self.assertGreaterEqual(
            scenario_ids,
            {
                "command-001-plan-confirmation-gate",
                "command-002-stale-mapping-blocks-final",
                "command-003-zero-test-fake-green-blocked",
                "command-004-conditional-gate-union",
            },
        )


if __name__ == "__main__":
    unittest.main()
