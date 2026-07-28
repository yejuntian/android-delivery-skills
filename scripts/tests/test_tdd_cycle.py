#!/usr/bin/env python3
"""验证 TDD 周期只接受真实业务断言 Red 和同一测试源码的 Green。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..execution_evidence import RECEIPT_PRODUCER, RECEIPT_VERSION, junit_content_signature, sha256_file
from ..tdd_cycle import (
    TDD_CYCLE_PRODUCER,
    TDD_CYCLE_VERSION,
    TddCycleError,
    record_green,
    record_red,
    validate_tdd_cycle,
)


class TddCycleTests(unittest.TestCase):
    """使用 app/src/test 目录模拟 Android 模块的 Red -> Green 闭环。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.test_source = self.project / "app/src/test/java/sample/FeatureTest.kt"
        self.test_source.parent.mkdir(parents=True)
        self.test_source.write_text("class FeatureTest\n", encoding="utf-8")
        self.mapping_path = self.root / "test-mapping.json"
        self.mapping_path.write_text(
            json.dumps({"version": 1, "mappings": [{
                "obligation_id": "BDD-001",
                "obligation_sha256": "d" * 64,
                "test_ids": ["FeatureTest#showsError"],
                "mapping_status": "CURRENT",
            }]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
        )
        self.old_snapshot = "a" * 64
        self.new_snapshot = "b" * 64
        self.context = {
            "project_path": str(self.project),
            "requirement_id": "REQ-001",
            "requirement_revision": 2,
            "requirement_file_sha256": "c" * 64,
            "requirement_inputs_sha256": "e" * 64,
            "baseline_id": "baseline-001",
            "snapshot_sha256": self.old_snapshot,
            "test_mapping_path": str(self.mapping_path),
            "test_mapping": {
                "BDD-001": {
                    "obligation_id": "BDD-001",
                    "obligation_sha256": "d" * 64,
                    "test_ids": ["FeatureTest#showsError"],
                    "mapping_status": "CURRENT",
                },
            },
        }

    def _receipt(
        self,
        name: str,
        snapshot: str,
        *,
        failed: bool,
        reports: bool = True,
        command: list[str] | None = None,
    ) -> Path:
        command = command or ["./gradlew", ":app:testDebugUnitTest"]
        report_records = []
        if reports:
            status_xml = (
                '<failure message="expected"/>'
                if failed else ""
            )
            report = self.root / f"{name}-TEST.xml"
            report.write_text(
                f'<testsuite tests="1" failures="{1 if failed else 0}" errors="0" skipped="0">'
                f'<testcase classname="FeatureTest" name="showsError">{status_xml}</testcase>'
                "</testsuite>\n",
                encoding="utf-8",
            )
            report_records.append({
                "path": str(report),
                "exists": True,
                "fresh": True,
                "size": report.stat().st_size,
                "sha256": junit_content_signature(report),
                "junit": {
                    "tests": 1,
                    "failures": 1 if failed else 0,
                    "errors": 0,
                    "skipped": 0,
                    "executed": 1,
                    "test_cases": [{
                        "id": "FeatureTest#showsError",
                        "classname": "FeatureTest",
                        "name": "showsError",
                        "status": "FAIL" if failed else "PASS",
                    }],
                },
            })
        stdout = self.root / f"{name}.stdout.log"
        stderr = self.root / f"{name}.stderr.log"
        stdout.write_text("test output\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        receipt = {
            "version": RECEIPT_VERSION,
            "producer": RECEIPT_PRODUCER,
            "id": name,
            "gate_id": "android-test-and-fix",
            "attempt": 1,
            "requirement_id": "REQ-001",
            "requirement_revision": 2,
            "requirement_file_sha256": "c" * 64,
            "requirement_inputs_sha256": "e" * 64,
            "baseline_id": "baseline-001",
            "snapshot_sha256_before": snapshot,
            "snapshot_sha256_after": snapshot,
            "command": command,
            "command_sha256": hashlib.sha256(
                json.dumps(command, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "cwd": str(self.project),
            "started_at": "2026-07-29T00:00:00+00:00" if failed else "2026-07-29T00:00:02+00:00",
            "finished_at": "2026-07-29T00:00:01+00:00" if failed else "2026-07-29T00:00:03+00:00",
            "timeout_seconds": 60,
            "timed_out": False,
            "exit_code": 1 if failed else 0,
            "executed_tests": 1 if reports else None,
            "reports": report_records,
            "stdout": {
                "path": str(stdout), "exists": True, "fresh": True,
                "size": stdout.stat().st_size, "sha256": sha256_file(stdout),
            },
            "stderr": {
                "path": str(stderr), "exists": True, "fresh": True,
                "size": stderr.stat().st_size, "sha256": sha256_file(stderr),
            },
        }
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        return path

    def _complete_cycle(self) -> Path:
        cycle_path = self.root / "tdd-cycle.json"
        red = self._receipt("TDD-RED", self.old_snapshot, failed=True)
        record_red(red, cycle_path, self.context)
        self.context["snapshot_sha256"] = self.new_snapshot
        green = self._receipt("TDD-GREEN", self.new_snapshot, failed=False)
        record_green(green, cycle_path, self.context)
        return cycle_path

    def test_records_red_and_green_receipts_and_relation(self) -> None:
        cycle_path = self._complete_cycle()
        payload = json.loads(cycle_path.read_text(encoding="utf-8"))

        self.assertEqual(TDD_CYCLE_VERSION, payload["version"])
        self.assertEqual(TDD_CYCLE_PRODUCER, payload["producer"])
        self.assertEqual("GREEN", payload["status"])
        self.assertEqual(["FeatureTest#showsError"], payload["red"]["failed_test_ids"])
        self.assertEqual(["FeatureTest#showsError"], payload["green"]["passed_test_ids"])
        self.assertEqual([], validate_tdd_cycle(cycle_path, self.context, {"BDD-001"}))

    def test_rejects_compile_failure_as_red(self) -> None:
        receipt = self._receipt("TDD-COMPILE", self.old_snapshot, failed=True, reports=False)

        with self.assertRaisesRegex(TddCycleError, "JUnit"):
            record_red(receipt, self.root / "tdd-cycle.json", self.context)

    def test_gate_rejects_test_source_changed_after_green(self) -> None:
        cycle_path = self._complete_cycle()
        self.test_source.write_text("class FeatureTestChanged\n", encoding="utf-8")

        errors = validate_tdd_cycle(cycle_path, self.context, {"BDD-001"})

        self.assertTrue(any("测试源码发生变化" in error for error in errors))

    def test_gate_rejects_missing_cycle(self) -> None:
        errors = validate_tdd_cycle(self.root / "missing.json", self.context, {"BDD-001"})

        self.assertTrue(any("缺少 TDD 周期记录" in error for error in errors))

    def test_rejects_green_without_production_code_change(self) -> None:
        red = self._receipt("TDD-RED", self.old_snapshot, failed=True)
        cycle_path = self.root / "tdd-cycle.json"
        record_red(red, cycle_path, self.context)
        green = self._receipt("TDD-GREEN", self.old_snapshot, failed=False)

        with self.assertRaisesRegex(TddCycleError, "没有可证明的生产代码变化"):
            record_green(green, cycle_path, self.context)

    def test_rejects_different_red_and_green_commands(self) -> None:
        cycle_path = self.root / "tdd-cycle.json"
        red = self._receipt("TDD-RED", self.old_snapshot, failed=True)
        record_red(red, cycle_path, self.context)
        green = self._receipt(
            "TDD-GREEN-OTHER",
            self.new_snapshot,
            failed=False,
            command=["./gradlew", ":app:testDebugUnitTest", "--tests", "FeatureTest#showsError"],
        )
        self.context["snapshot_sha256"] = self.new_snapshot

        with self.assertRaisesRegex(TddCycleError, "同一测试命令"):
            record_green(green, cycle_path, self.context)

    def test_rejects_changed_test_mapping(self) -> None:
        cycle_path = self._complete_cycle()
        self.mapping_path.write_text(
            self.mapping_path.read_text(encoding="utf-8").replace("showsError", "showsChanged"),
            encoding="utf-8",
        )

        errors = validate_tdd_cycle(cycle_path, self.context, {"BDD-001"})

        self.assertTrue(any("测试映射已变化" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
