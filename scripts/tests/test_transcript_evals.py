#!/usr/bin/env python3
"""脚本名称：test_transcript_evals.py

用途：验证 transcript replay eval 能把真实或模拟对话中的显式事件标记回放为流程门禁检查。

核心流程：执行 run_transcript_evals.py 的 JSON 输出，要求合规记录通过、偷懒记录命中当前
active contract；测试只读取本仓库场景，不接触真实 Android 项目、设备、网络或模型服务。

职责边界：只验证 transcript replay 层接线，不解析自然语言语义，也不重新实现 flow gate。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from evals.oracles.transcript_events import extract_trace_events


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "evals" / "runners" / "run_transcript_evals.py"


class TranscriptEvalTests(unittest.TestCase):
    """验证 transcript replay 评测套件稳定执行。"""

    def test_transcript_evals_pass(self) -> None:
        """执行全部 transcript replay 场景，并要求当前流程门禁全部符合预期。"""
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
        self.assertEqual("android-delivery-transcript-evals", report["producer"])
        self.assertEqual(0, report["summary"]["failed"])
        self.assertGreaterEqual(report["summary"]["total"], 3)

    def test_event_extractor_accepts_supported_markers(self) -> None:
        """验证事件提取只依赖显式标记，不需要自然语言推理。"""
        events = extract_trace_events(
            "用户补充需求 [event: user_requirement_changed]\n"
            "<!-- event: requirement_persisted -->\n"
        )
        self.assertEqual(
            ["user_requirement_changed", "requirement_persisted"],
            [event.event for event in events],
        )


if __name__ == "__main__":
    unittest.main()
