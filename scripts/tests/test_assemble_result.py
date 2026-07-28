#!/usr/bin/env python3
"""脚本名称：test_assemble_result.py

用途：验证 assemble 命令能从产物清单自动组装出可过 validate 的 delivery-result.json。

覆盖范围：YAML 产物清单解析、AUTOMATED/MANUAL/specialist 证据自动填充、
obligation→evidence 映射、gate 自动推导，以及组装结果通过 delivery_gate validate。
测试只使用临时文件，不接触真实项目、设备或网络。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..assemble_result import AssembleError, assemble_delivery_result  # noqa: E402
from ..delivery_gate import validate_delivery_result  # noqa: E402
from ..execution_evidence import sha256_file  # noqa: E402
from ..specialist_result import (  # noqa: E402
    SPECIALIST_PRODUCER,
    SPECIALIST_RESULT_VERSION,
)


def no_confirmed_impacts() -> list[dict]:
    """生成 Diff Reviewer 对七类影响均确认不适用的最小有效结果。"""
    return [
        {"id": cid, "applicable": False, "basis_files": [], "reason": "未涉及。"}
        for cid in ("ui", "api", "data", "system", "build", "architecture", "tests")
    ]


def passing_code_quality_checks() -> list[dict]:
    return [
        {"id": "architecture-layering", "required": True, "status": "PASS", "summary": "ok"},
        {"id": "responsibility-cohesion", "required": True, "status": "PASS", "summary": "ok"},
        {"id": "source-documentation", "required": True, "status": "PASS", "summary": "ok"},
        {"id": "dependency-testability", "required": True, "status": "PASS", "summary": "ok"},
    ]


def passing_stability_checks() -> list[dict]:
    ids = [
        "static-short-lifetime-ownership", "static-registration-pairing",
        "static-resource-pairing", "static-async-lifetime",
        "static-cleanup-reachability", "static-concurrency-discipline",
        "static-control-changes",
    ]
    return [{"id": i, "required": True, "status": "PASS", "summary": "ok"} for i in ids]


class AssembleResultTests(unittest.TestCase):
    """验证 assemble 自动组装消除手填摩擦，且结果可过 validate。"""

    def setUp(self) -> None:
        """建立临时目录、模拟 context 和真实执行收据/专项产物。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

        self.snapshot = "a" * 64
        self.requirement = "b" * 64
        self.requirement_inputs = "c" * 64
        self.obligation = "d" * 64
        self.traceability = self.root / "traceability.md"
        self.traceability.write_text(
            "# 当前需求追溯表\n\n## R2\n\nBDD-001 | 显示错误提示 | TEST-001 | 已覆盖\n",
            encoding="utf-8",
        )
        self.context = {
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot,
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "expected_obligations": {
                "BDD-001": {"required": True, "sha256": self.obligation, "text": "显示错误提示"},
            },
            "expected_conditional_gates": [],
            "result_path": str(self.root / "delivery-result.json"),
            "traceability_path": str(self.traceability),
            "test_mapping": {
                "BDD-001": {
                    "obligation_id": "BDD-001",
                    "obligation_sha256": self.obligation,
                    "test_ids": ["FeatureTest#thenT1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            },
        }
        self._write_receipts()
        self._write_specialists()

    def _write_receipts(self) -> None:
        """写测试/构建/lint 三份执行收据。"""
        test_report = self.root / "TEST-result.xml"
        test_report.write_text(
            '<testsuite tests="2" failures="0" errors="0" skipped="0">'
            '<testcase classname="FeatureTest" name="thenT1"/>'
            '<testcase classname="FeatureTest" name="regression"/>'
            "</testsuite>\n",
            encoding="utf-8",
        )
        lint_report = self.root / "lint-results.xml"
        lint_report.write_text("<issues/>\n", encoding="utf-8")

        from ..execution_evidence import junit_content_signature

        def receipt(eid: str, gate: str, command: list[str], reports: list, executed: int | None) -> Path:
            stdout = self.root / f"{eid}.stdout.log"
            stdout.write_text("ok\n", encoding="utf-8")
            stderr = self.root / f"{eid}.stderr.log"
            stderr.write_text("", encoding="utf-8")
            import hashlib
            payload = {
                "version": 3,
                "producer": "android-delivery-execution-evidence",
                "id": eid,
                "gate_id": gate,
                "attempt": 1,
                "requirement_id": "baseline-1",
                "requirement_revision": 2,
                "requirement_file_sha256": self.requirement,
                "requirement_inputs_sha256": self.requirement_inputs,
                "baseline_id": "baseline-1",
                "snapshot_sha256_before": self.snapshot,
                "snapshot_sha256_after": self.snapshot,
                "command": command,
                "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                "cwd": str(self.root),
                "started_at": "2026-07-27T00:00:00+00:00",
                "finished_at": "2026-07-27T00:00:01+00:00",
                "timeout_seconds": 60,
                "timed_out": False,
                "exit_code": 0,
                "executed_tests": executed,
                "reports": reports,
                "stdout": {"path": str(stdout), "exists": True, "fresh": True, "size": 3, "sha256": sha256_file(stdout)},
                "stderr": {"path": str(stderr), "exists": True, "fresh": True, "size": 0, "sha256": sha256_file(stderr)},
            }
            p = self.root / f"{eid}.receipt.json"
            p.write_text(json.dumps(payload), encoding="utf-8")
            return p

        test_report_record = {
            "path": str(test_report),
            "exists": True, "fresh": True,
            "size": test_report.stat().st_size,
            "sha256": junit_content_signature(test_report) or sha256_file(test_report),
            "junit": {
                "tests": 2, "failures": 0, "errors": 0, "skipped": 0, "executed": 2,
                "test_cases": [
                    {"id": "FeatureTest#thenT1", "classname": "FeatureTest", "name": "thenT1", "status": "PASS"},
                    {"id": "FeatureTest#regression", "classname": "FeatureTest", "name": "regression", "status": "PASS"},
                ],
            },
        }
        lint_report_record = {
            "path": str(lint_report),
            "exists": True, "fresh": True,
            "size": lint_report.stat().st_size,
            "sha256": sha256_file(lint_report),
            "android_lint": {"format": "XML", "fatal": 0, "errors": 0, "warnings": 0, "information": 0, "total": 0},
        }
        self.receipt_paths = {
            "E-TEST": receipt("E-TEST", "android-test-and-fix", ["./gradlew", ":app:testDebugUnitTest"], [test_report_record], 2),
            "E-BUILD": receipt("E-BUILD", "android-build", ["./gradlew", ":app:assembleDebug"], [], None),
            "E-LINT": receipt("E-LINT", "android-lint", ["./gradlew", ":app:lintDebug"], [lint_report_record], None),
        }

    def _write_specialists(self) -> None:
        """写三份专项结果(diff/quality/stability)。"""
        control_audit = self.root / "control-audit.json"
        control_audit.write_text(json.dumps({
            "version": 1, "producer": "android-static-control-audit",
            "project_path": str(self.root), "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot, "warnings": [], "control_changes": [],
        }), encoding="utf-8")
        self.specialist_paths = {}
        for sid, skill in (("E-DIFF", "android-review-diff"),
                           ("E-QUALITY", "android-review-code-quality"),
                           ("E-STABILITY", "android-audit-stability")):
            sp = {
                "version": SPECIALIST_RESULT_VERSION, "producer": SPECIALIST_PRODUCER,
                "id": sid, "skill": skill, "provenance": {"skill": skill},
                "requirement_id": "baseline-1", "requirement_revision": 2,
                "requirement_file_sha256": self.requirement,
                "requirement_inputs_sha256": self.requirement_inputs,
                "baseline_id": "baseline-1", "snapshot_sha256": self.snapshot,
                "conclusion": "PASS", "summary": f"{skill} ok",
                "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
                "unresolved_findings": [], "obligation_sha256s": {},
            }
            if skill == "android-review-diff":
                sp["confirmed_impacts"] = no_confirmed_impacts()
            elif skill == "android-review-code-quality":
                sp["checks"] = passing_code_quality_checks()
                sp["executed_checks"] = 4
            elif skill == "android-audit-stability":
                sp["capabilities"] = [{"id": "android-static-semantics", "required": True, "status": "PASS"}] + [
                    {"id": c, "required": False, "status": "SKIPPED", "reason": "未涉及"}
                    for c in ("android-dynamic-leak", "android-performance", "android-security-privacy")
                ]
                sp["checks"] = passing_stability_checks()
                sp["executed_checks"] = 7
                sp["static_analysis"] = {
                    "languages": ["KOTLIN"], "scope_files": ["app/src/main/java/sample/Feature.kt"],
                    "tools": [], "control_audit_path": str(control_audit),
                    "control_audit_sha256": sha256_file(control_audit),
                    "control_changes": [], "finding_ids": [],
                }
            p = self.root / f"{sid}.specialist.json"
            p.write_text(json.dumps(sp), encoding="utf-8")
            self.specialist_paths[sid] = p

    def _write_manifest(self) -> Path:
        """写产物清单 YAML（agent 只声明事实，不算指纹）。"""
        manifest = f"""\
conclusion: FULL_PASS
evidence:
  - id: E-TEST
    gate: android-test-and-fix
    receipt: E-TEST.receipt.json
  - id: E-BUILD
    gate: android-build
    receipt: E-BUILD.receipt.json
  - id: E-LINT
    gate: android-lint
    receipt: E-LINT.receipt.json
specialists:
  - path: E-DIFF.specialist.json
  - path: E-QUALITY.specialist.json
  - path: E-STABILITY.specialist.json
obligations:
  BDD-001: [E-TEST]
"""
        p = self.root / "manifest.yaml"
        p.write_text(manifest, encoding="utf-8")
        return p

    def test_assemble_produces_validatable_result(self) -> None:
        """验证 assemble 组装的 delivery-result.json 能直接通过 validate。"""
        manifest = self._write_manifest()
        result_path = self.root / "delivery-result.json"
        payload = assemble_delivery_result(manifest, self.context, result_path)

        # 组装结果应能过 validate（0 错误）
        errors = validate_delivery_result(payload, self.context)
        self.assertEqual([], errors, f"assemble 结果未通过 validate: {errors}")

        # 文件真实写出
        self.assertTrue(result_path.is_file())
        written = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(written["conclusion"], "FULL_PASS")

        # 证据自动填充了 receipt_sha256（agent 没填，脚本算的）
        test_ev = next(e for e in written["evidence"] if e["id"] == "E-TEST")
        self.assertTrue(test_ev["receipt_sha256"])
        self.assertEqual(test_ev["executed_tests"], 2)
        build_ev = next(e for e in written["evidence"] if e["id"] == "E-BUILD")
        self.assertNotIn("executed_tests", build_ev)

        # obligation_test_cases 只保留当前义务映射的 testcase
        self.assertIn("BDD-001", test_ev["obligation_test_cases"])
        self.assertEqual(
            test_ev["obligation_test_cases"]["BDD-001"],
            ["FeatureTest#thenT1"],
        )

        # specialist 证据自动算了 sha
        diff_ev = next(e for e in written["evidence"] if e["id"] == "E-DIFF")
        self.assertTrue(diff_ev["specialist_result_sha256"])

    def test_assemble_splits_shared_receipt_by_test_mapping(self) -> None:
        """同一收据覆盖多个 BDD 时，每项只关联自己的测试。"""
        self.context["expected_obligations"]["BDD-002"] = {
            "required": True,
            "sha256": "e" * 64,
            "text": "保留回归行为",
        }
        self.context["test_mapping"]["BDD-002"] = {
            "obligation_id": "BDD-002",
            "obligation_sha256": "e" * 64,
            "test_ids": ["FeatureTest#regression"],
            "mapping_status": "CURRENT",
            "manual_reason": None,
        }
        manifest = self._write_manifest()
        manifest.write_text(
            manifest.read_text(encoding="utf-8") + "  BDD-002: [E-TEST]\n",
            encoding="utf-8",
        )

        payload = assemble_delivery_result(manifest, self.context, self.root / "result.json")
        test_evidence = next(item for item in payload["evidence"] if item["id"] == "E-TEST")

        self.assertEqual(["FeatureTest#thenT1"], test_evidence["obligation_test_cases"]["BDD-001"])
        self.assertEqual(["FeatureTest#regression"], test_evidence["obligation_test_cases"]["BDD-002"])
        self.assertEqual([], validate_delivery_result(payload, self.context))

    def test_assemble_preserves_failed_receipt_for_fail_gate(self) -> None:
        """未完成报告可把失败收据直接绑定到对应 FAIL gate。"""
        receipt_path = self.receipt_paths["E-BUILD"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["exit_code"] = 1
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        manifest = self._write_manifest()
        manifest.write_text(
            manifest.read_text(encoding="utf-8")
            .replace("conclusion: FULL_PASS", "conclusion: INCOMPLETE")
            .replace(
                "obligations:\n",
                "gates:\n  android-build:\n    status: FAIL\n    required: true\nobligations:\n",
            ),
            encoding="utf-8",
        )

        payload = assemble_delivery_result(manifest, self.context, self.root / "result.json")

        self.assertEqual([], validate_delivery_result(payload, self.context))
        build_gate = next(item for item in payload["gates"] if item["id"] == "android-build")
        self.assertEqual("FAIL", build_gate["status"])

    def test_assemble_rejects_missing_manifest(self) -> None:
        """验证缺 evidence 数组时报清晰错误。"""
        bad = self.root / "bad.yaml"
        bad.write_text("conclusion: FULL_PASS\n", encoding="utf-8")
        with self.assertRaises(AssembleError):
            assemble_delivery_result(bad, self.context, self.root / "r.json")

    def test_assemble_rejects_obligation_referencing_missing_evidence(self) -> None:
        """验证 obligation 引用不存在的证据 id 时报错。"""
        manifest = self._write_manifest()
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text.replace("BDD-001: [E-TEST]", "BDD-001: [E-NONE]"), encoding="utf-8")
        with self.assertRaises(AssembleError) as ctx:
            assemble_delivery_result(manifest, self.context, self.root / "r.json")
        self.assertIn("E-NONE", str(ctx.exception))

    def test_assemble_rejects_manifest_id_different_from_receipt(self) -> None:
        """清单证据 id 与真实收据 id 不一致时在组装阶段立即失败。"""
        receipt = self.receipt_paths["E-BUILD"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["id"] = "OTHER-BUILD"
        receipt.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(AssembleError, "清单 id 与执行收据 id 不一致"):
            assemble_delivery_result(
                self._write_manifest(),
                self.context,
                self.root / "r.json",
            )

    def test_assemble_maps_ui_specialist_to_ui_a11y_gate(self) -> None:
        """android-verify-ui 专项证据归入条件 gate android-ui-a11y。"""
        ui_result = self.root / "E-UI.specialist.json"
        ui_result.write_text(json.dumps({
            "id": "E-UI",
            "skill": "android-verify-ui",
            "summary": "模拟器 UI 核验完成。",
        }), encoding="utf-8")
        manifest = self._write_manifest()
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "  - path: E-STABILITY.specialist.json\n",
                "  - path: E-STABILITY.specialist.json\n  - path: E-UI.specialist.json\n",
            ),
            encoding="utf-8",
        )

        result = assemble_delivery_result(manifest, self.context, self.root / "r.json")
        ui_evidence = next(item for item in result["evidence"] if item["id"] == "E-UI")
        self.assertEqual("android-ui-a11y", ui_evidence["gate_id"])
        self.assertIn("android-ui-a11y", {item["id"] for item in result["gates"]})

    def test_obligation_without_coverage_status_defaults_to_unverified(self) -> None:
        """对象格式未声明覆盖状态时不能被组装器自动标成已覆盖。"""
        manifest = self._write_manifest()
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "conclusion: FULL_PASS",
                "conclusion: INCOMPLETE",
            ).replace(
                "  BDD-001: [E-TEST]",
                "  BDD-001:\n    evidence: []\n    reason: 尚未执行设备验证",
            ),
            encoding="utf-8",
        )

        result = assemble_delivery_result(manifest, self.context, self.root / "r.json")
        self.assertEqual("UNVERIFIED", result["obligations"][0]["status"])
        self.assertEqual([], result["obligations"][0]["evidence_ids"])


if __name__ == "__main__":
    unittest.main()
