#!/usr/bin/env python3
"""脚本名称：test_execution_evidence.py

用途：验证命令执行收据能够绑定代码摘要、结构化测试数、日志和报告文件。

覆盖范围：敏感参数脱敏、JUnit 计数、缺失报告和执行期间源码变化。所有命令只在
临时 Git 仓库运行，不接触真实 Android 项目、设备或网络。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..execution_evidence import (  # noqa: E402
    ExecutionEvidenceError,
    redact_command,
    redact_output,
    run_and_record,
    sha256_file,
    validate_execution_receipt,
)
from ..git_changes import current_delivery_snapshot, write_baseline  # noqa: E402


class ExecutionEvidenceTests(unittest.TestCase):
    """验证收据只接受当前代码上真实运行且报告可复核的命令。"""

    def setUp(self) -> None:
        """建立带忽略构建目录的临时 Git 仓库和当前代码摘要。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Evidence Test"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "evidence@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.repo / "App.kt").write_text("class App\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=self.repo, check=True)
        self.baseline = self.root / "baseline.json"
        baseline = write_baseline(self.repo, self.baseline)
        (self.repo / "App.kt").write_text("class AppChanged\n", encoding="utf-8")
        snapshot = current_delivery_snapshot(self.repo, self.baseline)
        self.context = {
            **snapshot,
            "requirement_id": baseline["id"],
            "requirement_revision": 1,
            "requirement_file_sha256": "b" * 64,
            "result_path": str(self.root / "delivery-result.json"),
        }
        self.receipt_dir = self.root / "receipts"

    def test_redacts_sensitive_values_and_deep_link_queries(self) -> None:
        """验证收据不会泄漏 Token、密码或 DeepLink 查询参数。"""
        command = [
            "tool",
            "--token",
            "secret-value",
            "--password=hunter2",
            "sample://login?code=123",
        ]
        self.assertEqual(
            [
                "tool",
                "--token",
                "<redacted>",
                "--password=<redacted>",
                "sample://login?<redacted>",
            ],
            redact_command(command),
        )
        self.assertNotIn(
            "secret-value",
            redact_output(b"Authorization: Bearer abc.def\ntoken=secret-value\nsample://x?code=1"),
        )
        self.assertIn("sample://x?<redacted>", redact_output("sample://x?code=1"))

    def test_records_fresh_junit_and_validates_receipt(self) -> None:
        """验证真实命令、JUnit 测试数、日志和摘要可以形成有效最终证据。"""
        report = self.repo / "build" / "test-results" / "TEST-sample.xml"
        script = (
            "from pathlib import Path; "
            f"p=Path({str(report)!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_text('<testsuite tests=\"3\" failures=\"0\"/>\\n')"
        )
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-UNIT",
            command=[sys.executable, "-c", script],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(0, exit_code)
        self.assertEqual(3, receipt["executed_tests"])
        self.assertIn("-r1-", receipt_path.parent.name)
        evidence = {
            "id": "E-UNIT",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": 3,
            "report_paths": [receipt["reports"][0]["path"]],
        }
        self.assertEqual(
            [],
            validate_execution_receipt(
                receipt_path,
                sha256_file(receipt_path),
                evidence,
                self.context,
            ),
        )

    def test_missing_report_cannot_become_successful_evidence(self) -> None:
        """验证命令零退出但显式报告不存在时收集器返回证据失败。"""
        _, _, exit_code = run_and_record(
            evidence_id="E-MISSING",
            command=[sys.executable, "-c", "print('ok')"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[self.repo / "build" / "missing.xml"],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(3, exit_code)

    def test_junit_failure_cannot_pass_even_when_command_exits_zero(self) -> None:
        """验证 Gradle ignoreFailures 等零退出设置不能掩盖 JUnit 真实失败。"""
        report = self.repo / "build" / "test-results" / "TEST-failed.xml"
        script = (
            "from pathlib import Path; "
            f"p=Path({str(report)!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_text('<testsuite tests=\"2\" failures=\"1\" errors=\"0\"/>')"
        )
        receipt, _, exit_code = run_and_record(
            evidence_id="E-FAILED-JUNIT",
            command=[sys.executable, "-c", script],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(3, exit_code)
        self.assertEqual(1, receipt["reports"][0]["junit"]["failures"])

    def test_source_change_during_command_invalidates_receipt(self) -> None:
        """验证测试命令若改变受版本控制源码，必须重新 route 后再执行。"""
        script = "from pathlib import Path; Path('App.kt').write_text('class Mutated\\n')"
        receipt, _, exit_code = run_and_record(
            evidence_id="E-MUTATE",
            command=[sys.executable, "-c", script],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(4, exit_code)
        self.assertNotEqual(
            receipt["snapshot_sha256_before"],
            receipt["snapshot_sha256_after"],
        )

    def test_command_start_failure_is_actionable(self) -> None:
        """验证命令不存在时返回明确环境错误而不是 Python traceback。"""
        with self.assertRaisesRegex(ExecutionEvidenceError, "命令无法启动"):
            run_and_record(
                evidence_id="E-NOT-FOUND",
                command=[str(self.repo / "missing-command")],
                cwd=self.repo,
                timeout_seconds=30,
                reports=[],
                context=self.context,
                project_path=self.repo,
                baseline_path=self.baseline,
                receipt_dir=self.receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
