#!/usr/bin/env python3
"""脚本名称：test_eval_contracts.py

用途：验证轻量 Contract/Oracle 评测层可以作为流程维护的稳定约束索引。

核心流程：读取 active-contracts.yaml，检查 active contract 数量、owner/Oracle/场景覆盖
关系，并通过统一 runner 执行 fast suite 的 JSON 输出。
测试只读取流程仓库文件，不接触真实 Android 项目、设备、网络或模型服务。

职责边界：只验证契约层和统一 runner 的接线，不评价具体 Android 业务需求实现。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from evals.oracles.contract_coverage import evaluate_contract_coverage
from evals.oracles.contract_loader import default_contract_path, load_contracts
from evals.runners.run_evals import SUITE_ALIASES


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "evals" / "runners" / "run_evals.py"


class EvalContractTests(unittest.TestCase):
    """验证流程契约文件、覆盖检查和统一 runner 都能稳定运行。"""

    def test_active_contracts_are_loaded(self) -> None:
        """读取当前契约文件，并确认 active contract 保持可维护的最小数量。"""
        contract_set = load_contracts(default_contract_path(REPOSITORY_ROOT))
        self.assertEqual(1, contract_set.version)
        self.assertGreaterEqual(len(contract_set.active()), 10)
        self.assertEqual(0, len(contract_set.retired()))

    def test_contract_coverage_passes(self) -> None:
        """执行契约覆盖检查，要求所有 active contract 都有 owner、Oracle 和场景覆盖。"""
        report = evaluate_contract_coverage(REPOSITORY_ROOT)
        self.assertEqual("android-delivery-contract-evals", report["producer"])
        self.assertEqual(0, report["summary"]["failed"])
        self.assertGreaterEqual(report["summary"]["total"], 10)

    def test_unified_fast_runner_passes(self) -> None:
        """执行统一 fast suite，确认全部已登记的轻量 eval 都被纳入汇总。"""
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--root",
                str(REPOSITORY_ROOT),
                "--suite",
                "fast",
                "--format",
                "json",
            ],
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
        self.assertEqual("android-delivery-evals", report["producer"])
        self.assertEqual("fast", report["suite"])
        self.assertEqual(0, report["summary"]["failed"])
        self.assertEqual(["artifact", "contracts", "behavior", "transcript", "command"], [suite["suite"] for suite in report["suites"]])

    def test_fast_help_matches_registered_suites(self) -> None:
        """确认 CLI 帮助从当前 suite 注册表生成，不保留会过期的手写清单。"""
        completed = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected = f"fast当前包含：{','.join(SUITE_ALIASES['fast'])}"
        self.assertIn(expected, "".join(completed.stdout.split()))


if __name__ == "__main__":
    unittest.main()
