#!/usr/bin/env python3
"""脚本名称：test_behavior_evals.py

用途：验证行为 trace eval 能用当前流程契约抓住提前编码、提前 route 等偷懒行为。

核心流程：执行 run_behavior_evals.py 的 JSON 输出，检查场景数量非空且全部通过；同时直接
验证 flow_gate Oracle 对正向和反向 trace 的判断结果。
测试只读取流程仓库文件，不接触真实 Android 项目、设备、网络或模型服务。

职责边界：只验证行为 trace 层和 flow gate Oracle，不评价具体 Android 业务需求实现。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from evals.oracles.contract_loader import default_contract_path, load_contracts
from evals.oracles.flow_gate import TraceEvent, evaluate_flow_gates


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "evals" / "runners" / "run_behavior_evals.py"


class BehaviorEvalTests(unittest.TestCase):
    """验证行为门禁评测可以稳定执行并捕获关键流程越权。"""

    def test_behavior_evals_pass(self) -> None:
        """执行全部行为 trace 场景，并要求当前仓库流程门禁全部符合预期。"""
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
        self.assertEqual("android-delivery-behavior-evals", report["producer"])
        self.assertGreaterEqual(report["summary"]["total"], 3)
        self.assertEqual(0, report["summary"]["failed"])

    def test_flow_gate_blocks_code_before_confirmation(self) -> None:
        """直接验证当前契约会阻断未确认前的编码事件。"""
        contract_set = load_contracts(default_contract_path(REPOSITORY_ROOT))
        trace = (
            TraceEvent(event="user_requirement_changed", index=0),
            TraceEvent(event="requirement_persisted", index=1),
            TraceEvent(event="code_mutation", index=2),
        )
        violations = evaluate_flow_gates(contract_set, trace)
        self.assertIn(
            "required-confirmations-before-route",
            {violation.contract_id for violation in violations},
        )

    def test_flow_gate_allows_code_after_confirmation(self) -> None:
        """直接验证当前契约在需求和计划确认后允许编码。"""
        contract_set = load_contracts(default_contract_path(REPOSITORY_ROOT))
        trace = (
            TraceEvent(event="user_requirement_changed", index=0),
            TraceEvent(event="requirement_persisted", index=1),
            TraceEvent(event="requirement_confirmed", index=2),
            TraceEvent(event="plan_confirmed", index=3),
            TraceEvent(event="code_mutation", index=4),
        )
        self.assertEqual((), evaluate_flow_gates(contract_set, trace))


if __name__ == "__main__":
    unittest.main()
