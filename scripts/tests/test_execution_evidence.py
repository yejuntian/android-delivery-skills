#!/usr/bin/env python3
"""脚本名称：test_execution_evidence.py

用途：验证单 gate 命令收据能够绑定代码摘要、testcase、Lint、日志和报告文件。

覆盖范围：敏感参数脱敏、JUnit 映射、Lint 报告、不可覆盖 attempt、缺失报告和执行
期间源码变化。所有命令只在临时 Git 仓库运行，不接触真实 Android 项目、设备或网络。
"""

from __future__ import annotations

import json
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
            "requirement_inputs_sha256": "c" * 64,
            "result_path": str(self.root / "delivery-result.json"),
            "project_path": str(self.repo),
        }
        self.receipt_dir = self.root / "receipts"

    def _record_clean_lint(self, evidence_id: str) -> tuple[dict, Path, dict]:
        """使用忽略目录中的假 Gradle wrapper 生成干净 Lint XML 和对应证据。"""
        build_dir = self.repo / "build"
        build_dir.mkdir(exist_ok=True)
        wrapper = build_dir / "gradlew"
        wrapper.write_text(
            "#!/bin/sh\n"
            "mkdir -p reports\n"
            "printf '<issues><issue id=\"W\" severity=\"Warning\"/></issues>' "
            "> reports/lint-results.xml\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        report = build_dir / "reports" / "lint-results.xml"
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id=evidence_id,
            gate_id="android-lint",
            command=["./gradlew", ":app:lintDebug"],
            cwd=build_dir,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(0, exit_code)
        evidence = {
            "id": evidence_id,
            "gate_id": "android-lint",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": None,
            "report_paths": [receipt["reports"][0]["path"]],
            "obligation_test_cases": {},
        }
        return receipt, receipt_path, evidence

    def _write_static_sarif(
        self,
        level: str,
        baseline_state: str | None = None,
        filename: str = "static.sarif",
    ) -> Path:
        """写入模拟 detekt/Semgrep/CodeQL 均可采用的最小 SARIF 报告。"""
        report = self.repo / "build" / "reports" / filename
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {"name": "detekt", "version": "2.0.0"}},
                "results": [{
                    "ruleId": "LifecycleLeak",
                    "level": level,
                    "message": {"text": "Lifecycle ownership issue"},
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": (self.repo / "App.kt").as_uri()},
                            "region": {"startLine": 1},
                        }
                    }],
                    **({"baselineState": baseline_state} if baseline_state else {}),
                }],
            }],
        }), encoding="utf-8")
        return report

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
        structured = redact_output(
            '{"access_token":"abc123","client_secret":"secret-value"}\n'
            "PRIVATE_KEY=-----BEGIN_PRIVATE_KEY-----"
        )
        self.assertNotIn("abc123", structured)
        self.assertNotIn("secret-value", structured)
        self.assertNotIn("BEGIN_PRIVATE_KEY", structured)

    def test_records_fresh_junit_and_validates_receipt(self) -> None:
        """验证真实命令、JUnit 测试数、日志和摘要可以形成有效最终证据。"""
        report = self.repo / "build" / "test-results" / "TEST-sample.xml"
        script = (
            "from pathlib import Path; "
            f"p=Path({str(report)!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_text('<testsuite tests=\"3\" failures=\"0\">'"
            "'<testcase classname=\"RulesTest\" name=\"caseA\"/>'"
            "'<testcase classname=\"RulesTest\" name=\"caseB\"/>'"
            "'<testcase classname=\"RulesTest\" name=\"caseC\"/>'"
            "'</testsuite>\\n')"
        )
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-UNIT",
            gate_id="android-test-and-fix",
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
        self.assertIn("-r1-", str(receipt_path))
        evidence = {
            "id": "E-UNIT",
            "gate_id": "android-test-and-fix",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": 3,
            "report_paths": [receipt["reports"][0]["path"]],
            "obligation_test_cases": {},
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
            gate_id="android-test-and-fix",
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

    def test_junit_signature_stable_across_timestamp_change(self) -> None:
        """验证 junit 报告仅 timestamp 变化时内容签名稳定，重跑收据不误失效（P7）。"""
        from ..execution_evidence import junit_content_signature
        report = self.repo / "TEST-sample.xml"
        base = (
            '<testsuite tests="2" failures="0" errors="0" skipped="0"'
            ' timestamp="{ts}" hostname="h" time="0.001">'
            '<testcase classname="T" name="caseA" time="0.0"/>'
            '<testcase classname="T" name="caseB" time="0.0"/>'
            '</testsuite>\n'
        )
        report.write_text(base.format(ts="2026-07-26T10:00:00"), encoding="utf-8")
        sig1 = junit_content_signature(report)
        # 重跑：仅 timestamp 不同
        report.write_text(base.format(ts="2026-07-26T10:00:05"), encoding="utf-8")
        sig2 = junit_content_signature(report)
        self.assertIsNotNone(sig1)
        self.assertEqual(sig1, sig2)

    def test_junit_signature_detects_testcase_tamper(self) -> None:
        """验证篡改 testcase（删用例/改状态/改名）时内容签名变化，仍能抓篡改。"""
        from ..execution_evidence import junit_content_signature
        report = self.repo / "TEST-tamper.xml"
        original = (
            '<testsuite tests="2" failures="0" errors="0" skipped="0"'
            ' timestamp="2026-07-26T10:00:00">'
            '<testcase classname="T" name="caseA"/>'
            '<testcase classname="T" name="caseB"/>'
            '</testsuite>\n'
        )
        report.write_text(original, encoding="utf-8")
        sig_original = junit_content_signature(report)

        # 篡改1：删掉一个 testcase
        report.write_text(original.replace('<testcase classname="T" name="caseB"/>', ''), encoding="utf-8")
        self.assertNotEqual(sig_original, junit_content_signature(report))

        # 篡改2：改名
        report.write_text(original.replace("caseA", "caseX"), encoding="utf-8")
        self.assertNotEqual(sig_original, junit_content_signature(report))

    def test_test_gate_requires_nonzero_junit_report(self) -> None:
        """验证普通成功命令不能在没有 JUnit 执行结果时证明测试 gate。"""
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-EMPTY-TEST",
            gate_id="android-test-and-fix",
            command=[sys.executable, "-c", "pass"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        evidence = {
            "id": "E-EMPTY-TEST",
            "gate_id": "android-test-and-fix",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": None,
            "report_paths": [],
            "obligation_test_cases": {},
        }

        self.assertEqual(3, exit_code)
        errors = validate_execution_receipt(
            receipt_path,
            sha256_file(receipt_path),
            evidence,
            self.context,
        )
        self.assertTrue(any("缺少实际执行大于零的 JUnit 报告" in error for error in errors))

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
            gate_id="android-test-and-fix",
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
            gate_id="android-test-and-fix",
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

    def test_document_receipts_do_not_pollute_code_snapshot(self) -> None:
        """验证写入 document/<需求>/ 的收据和日志不改变代码摘要。"""
        wrapper = self.repo / "gradlew"
        wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        wrapper.chmod(0o700)
        requirement_dir = self.repo / "document" / "2026-07-28-login"
        result_path = requirement_dir / "test-results" / "delivery-result.json"
        requirement_dir.mkdir(parents=True)
        context = {
            **self.context,
            "result_path": str(result_path),
            "snapshot_sha256": current_delivery_snapshot(self.repo, self.baseline)["snapshot_sha256"],
        }

        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-BUILD-DOC",
            gate_id="android-build",
            command=["./gradlew", ":app:assembleDebug"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[],
            context=context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=requirement_dir / ".state" / "evidence",
        )

        self.assertEqual(0, exit_code)
        self.assertIn("document/2026-07-28-login", str(receipt_path))
        self.assertEqual(receipt["snapshot_sha256_before"], receipt["snapshot_sha256_after"])

    def test_zero_test_under_document_fails_as_evidence_not_snapshot_pollution(self) -> None:
        """验证缺少 JUnit 报告时返回证据失败，而不是被 document 收据误判代码变化。"""
        requirement_dir = self.repo / "document" / "2026-07-28-zero-test"
        result_path = requirement_dir / "test-results" / "delivery-result.json"
        requirement_dir.mkdir(parents=True)
        context = {
            **self.context,
            "result_path": str(result_path),
            "snapshot_sha256": current_delivery_snapshot(self.repo, self.baseline)["snapshot_sha256"],
        }

        receipt, _, exit_code = run_and_record(
            evidence_id="E-EMPTY-DOC",
            gate_id="android-test-and-fix",
            command=[sys.executable, "-c", "pass"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[],
            context=context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=requirement_dir / ".state" / "evidence",
        )

        self.assertEqual(3, exit_code)
        self.assertEqual(receipt["snapshot_sha256_before"], receipt["snapshot_sha256_after"])

    def test_command_start_failure_is_recorded(self) -> None:
        """验证命令无法启动也保留不可覆盖收据，而不是只抛出 traceback。"""
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-NOT-FOUND",
            gate_id="android-test-and-fix",
            command=[str(self.repo / "missing-command")],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(127, exit_code)
        self.assertEqual(127, receipt["exit_code"])
        self.assertTrue(receipt_path.is_file())

    def test_same_evidence_id_keeps_immutable_attempts(self) -> None:
        """验证同一证据重跑分配新 attempt，首次失败和日志不会被覆盖。"""
        results = [
            run_and_record(
                evidence_id="E-RETRY",
                gate_id="android-test-and-fix",
                command=[sys.executable, "-c", "raise SystemExit(1)" if index == 0 else "print('ok')"],
                cwd=self.repo,
                timeout_seconds=30,
                reports=[],
                context=self.context,
                project_path=self.repo,
                baseline_path=self.baseline,
                receipt_dir=self.receipt_dir,
            )
            for index in range(2)
        ]
        self.assertEqual([1, 2], [result[0]["attempt"] for result in results])
        self.assertNotEqual(results[0][1], results[1][1])
        self.assertEqual(1, results[0][0]["exit_code"])
        self.assertEqual(0, results[1][0]["exit_code"])
        self.assertTrue(all(result[1].is_file() for result in results))

    def test_lint_report_errors_fail_zero_exit_command(self) -> None:
        """验证 Android Lint 即使被配置为零退出，报告中的 Error 仍阻断证据。"""
        report = self.repo / "build" / "reports" / "lint-results.xml"
        script = (
            "from pathlib import Path; "
            f"p=Path({str(report)!r}); p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_text('<issues><issue id=\"X\" severity=\"Error\"/></issues>')"
        )
        receipt, _, exit_code = run_and_record(
            evidence_id="E-LINT",
            gate_id="android-lint",
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
        self.assertEqual(1, receipt["reports"][0]["android_lint"]["errors"])

    def test_clean_lint_report_produces_valid_gate_receipt(self) -> None:
        """验证真实 lint task 加本轮无 Error 的 XML 可以形成有效单 gate 收据。"""
        _, receipt_path, evidence = self._record_clean_lint("E-LINT-CLEAN")

        self.assertEqual(
            [],
            validate_execution_receipt(
                receipt_path,
                sha256_file(receipt_path),
                evidence,
                self.context,
            ),
        )

    def test_static_sarif_produces_stable_machine_receipt(self) -> None:
        """验证项目已有静态工具可以通过统一 SARIF 形成独立、可复核的自动证据。"""
        report = self._write_static_sarif("warning")
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-STATIC",
            gate_id="android-static-analysis",
            command=[sys.executable, "-c", "print('static analysis complete')"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        evidence = {
            "id": "E-STATIC",
            "gate_id": "android-static-analysis",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": None,
            "report_paths": [receipt["reports"][0]["path"]],
            "obligation_test_cases": {},
        }

        self.assertEqual(0, exit_code)
        self.assertEqual(1, receipt["reports"][0]["static_analysis"]["warnings"])
        self.assertTrue(receipt["reports"][0]["static_analysis"]["findings"][0]["id"].startswith("FND-"))
        self.assertEqual([], validate_execution_receipt(
            receipt_path,
            sha256_file(receipt_path),
            evidence,
            self.context,
        ))

    def test_static_sarif_error_blocks_zero_exit_command(self) -> None:
        """验证静态工具即使命令返回零，SARIF 中的 Error 仍会让证据收集失败。"""
        report = self._write_static_sarif("error")
        receipt, _, exit_code = run_and_record(
            evidence_id="E-STATIC-ERROR",
            gate_id="android-static-analysis",
            command=[sys.executable, "-c", "pass"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )

        self.assertEqual(3, exit_code)
        self.assertEqual(1, receipt["reports"][0]["static_analysis"]["errors"])
        self.assertEqual(1, receipt["reports"][0]["static_analysis"]["blocking_errors"])

    def test_unchanged_historical_error_does_not_block_static_gate(self) -> None:
        """验证明确 unchanged 的旧 Error 进入记录，但不阻断本次增量交付。"""
        report = self._write_static_sarif(
            "error",
            baseline_state="unchanged",
            filename="static.sarif.json",
        )
        receipt, receipt_path, exit_code = run_and_record(
            evidence_id="E-STATIC-HISTORY",
            gate_id="android-static-analysis",
            command=[sys.executable, "-c", "pass"],
            cwd=self.repo,
            timeout_seconds=30,
            reports=[report],
            context=self.context,
            project_path=self.repo,
            baseline_path=self.baseline,
            receipt_dir=self.receipt_dir,
        )
        evidence = {
            "id": "E-STATIC-HISTORY",
            "gate_id": "android-static-analysis",
            "command": receipt["command"],
            "exit_code": 0,
            "executed_tests": None,
            "report_paths": [receipt["reports"][0]["path"]],
            "obligation_test_cases": {},
        }

        self.assertEqual(0, exit_code)
        self.assertEqual(1, receipt["reports"][0]["static_analysis"]["unchanged_errors"])
        self.assertEqual(0, receipt["reports"][0]["static_analysis"]["blocking_errors"])
        self.assertEqual([], validate_execution_receipt(
            receipt_path,
            sha256_file(receipt_path),
            evidence,
            self.context,
        ))

    def test_malformed_lint_summary_returns_error_instead_of_crashing(self) -> None:
        """验证畸形 Lint 计数字段只会阻断证据，不会让最终门禁异常退出。"""
        receipt, receipt_path, evidence = self._record_clean_lint("E-LINT-MALFORMED")
        receipt["reports"][0]["android_lint"]["errors"] = "not-an-integer"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        errors = validate_execution_receipt(
            receipt_path,
            sha256_file(receipt_path),
            evidence,
            self.context,
        )

        self.assertTrue(any("Android Lint 汇总字段无效: errors" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
