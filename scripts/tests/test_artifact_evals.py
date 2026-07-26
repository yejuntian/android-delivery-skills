#!/usr/bin/env python3
"""脚本名称：test_artifact_evals.py

用途：验证本地 artifact Evals runner 能执行全部流程不变量场景。

核心流程：以仓库根目录运行 evals/runners/run_artifact_evals.py 的 JSON 输出，检查
命令成功、场景数量非空且全部通过。
测试只读取流程仓库文件，不接触真实 Android 项目、设备或网络。

职责边界：只验证 Evals runner 与场景配置可用，不评价 Android 业务需求实现。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "evals" / "runners" / "run_artifact_evals.py"


class ArtifactEvalRunnerTests(unittest.TestCase):
    """验证 artifact Evals 作为流程维护门禁可以稳定运行。"""

    def test_artifact_evals_pass(self) -> None:
        """执行全部 artifact Evals，并要求当前仓库不变量全部通过。"""
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
        self.assertEqual("android-delivery-artifact-evals", report["producer"])
        self.assertGreaterEqual(report["summary"]["total"], 10)
        self.assertEqual(0, report["summary"]["failed"])


if __name__ == "__main__":
    unittest.main()
