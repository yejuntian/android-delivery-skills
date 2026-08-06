#!/usr/bin/env python3
"""脚本名称：test_delivery_gate.py

用途：验证最终交付门禁只接受当前代码上的完整原子义务、专项门禁和真实证据。

覆盖范围：通过报告、中文摘要、最新版义务、route 条件门禁、执行收据、专项/Agent
结果、过期需求语义和未完成结论。测试不运行 Android 构建、不修改真实仓库。
"""

from __future__ import annotations

import sys
import hashlib
import json
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from .. import delivery_gate as delivery_gate_module  # noqa: E402
from ..test_support import patch_module_global  # noqa: E402
from ..delivery_gate import (  # noqa: E402
    DeliveryGateError,
    _changed_paths_for_radius,
    current_context,
    main,
    validate_delivery_result,
)
from ..execution_evidence import RECEIPT_PRODUCER, RECEIPT_VERSION, junit_content_signature, sha256_file  # noqa: E402
from ..fact_inbox import add_fact, resolve_fact  # noqa: E402
from ..git_changes import GitChange, current_delivery_snapshot, write_baseline  # noqa: E402
from ..impact_radius import impact_radius_digest, impact_radius_path  # noqa: E402
from ..requirement_snapshot import (  # noqa: E402
    apply_requirement_revision,
    requirement_summary_digest,
    write_requirement_snapshot,
)
from ..requirement_inputs import requirement_inputs_digest  # noqa: E402
from ..route_impact import build_route_impact, write_route_impact  # noqa: E402
from ..specialist_result import (  # noqa: E402
    API_CONTRACT_SKILL,
    CODE_QUALITY_CHECK_IDS,
    IMPACT_CATEGORIES,
    SPECIALIST_PRODUCER,
    SPECIALIST_RESULT_VERSION,
    STABILITY_STATIC_CHECK_IDS,
)


def no_confirmed_impacts() -> list[dict]:
    """生成默认无语义影响的 Diff Reviewer 机器结论。"""
    return [
        {
            "id": impact_id,
            "applicable": False,
            "basis_files": [],
            "reason": "需求与最终 diff 均未涉及。",
        }
        for impact_id in sorted(IMPACT_CATEGORIES)
    ]


def passing_code_quality_checks() -> list[dict]:
    """生成最终门禁夹具所需的四项代码质量机器检查。"""
    return [
        {
            "id": check_id,
            "required": True,
            "status": "PASS",
            "summary": "已结合最终 diff 逐项检查。",
        }
        for check_id in sorted(CODE_QUALITY_CHECK_IDS)
    ]


def passing_stability_checks() -> list[dict]:
    """生成最终门禁夹具所需的七项静态语义和控制面检查。"""
    return [
        {
            "id": check_id,
            "required": True,
            "status": "PASS",
            "summary": "已结合最终 diff 和必要调用链完成复核。",
        }
        for check_id in sorted(STABILITY_STATIC_CHECK_IDS)
    ]


class DeliveryGateTests(unittest.TestCase):
    """验证最终结论不能越过原子义务、门禁和证据新鲜度。"""

    def setUp(self) -> None:
        """建立同一基线和代码摘要下的最小有效交付报告。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.snapshot = "a" * 64
        self.requirement = "b" * 64
        self.requirement_inputs = "c" * 64
        self.obligation = "d" * 64
        self.traceability = self.temp_root / "traceability.md"
        self.traceability.write_text(
            "# 当前需求追溯表\n\n## R2\n\nBDD-001 | 显示错误提示 | TEST-001 | 已覆盖\n",
            encoding="utf-8",
        )
        self.context = {
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "baseline_id": "baseline-1",
            "baseline_head": "head-1",
            "head": "head-2",
            "snapshot_sha256": self.snapshot,
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "expected_obligations": {
                "BDD-001": {
                    "required": True,
                    "sha256": self.obligation,
                    "text": "显示错误提示",
                },
            },
            "expected_conditional_gates": [],
            "result_path": "/tmp/result.json",
            "traceability_path": str(self.traceability),
            "changed_files": [
                "app/src/main/java/sample/Feature.kt",
                "app/src/test/java/sample/FeatureTest.kt",
            ],
            "impact_radius": {
                "allowed_files": [
                    "app/src/main/java/sample/Feature.kt",
                    "app/src/test/java/sample/FeatureTest.kt",
                ],
                "allowed_dirs": [],
                "impacts": [{
                    "id": "BDD-001",
                    "expected_files": [
                        "app/src/main/java/sample/Feature.kt",
                        "app/src/test/java/sample/FeatureTest.kt",
                    ],
                }],
            },
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
        test_command = ["./gradlew", ":app:testDebugUnitTest"]
        test_report = self.temp_root / "TEST-result.xml"
        test_report.write_text(
            '<testsuite tests="2" failures="0" errors="0" skipped="0">'
            '<testcase classname="FeatureTest" name="thenT1"/>'
            '<testcase classname="FeatureTest" name="regression"/>'
            "</testsuite>\n",
            encoding="utf-8",
        )
        lint_report = self.temp_root / "lint-results.xml"
        lint_report.write_text("<issues/>\n", encoding="utf-8")
        control_audit = self.temp_root / "static-control-audit.json"
        control_audit.write_text(json.dumps({
            "version": 1,
            "producer": "android-static-control-audit",
            "project_path": "/tmp/project",
            "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot,
            "warnings": [],
            "control_changes": [],
        }), encoding="utf-8")

        def create_receipt(
            evidence_id: str,
            gate_id: str,
            command: list[str],
            reports: list[dict],
            executed_tests: int | None,
        ) -> Path:
            """生成与当前上下文绑定的测试收据，分别证明单一 gate。"""
            stdout = self.temp_root / f"{evidence_id}.stdout.log"
            stderr = self.temp_root / f"{evidence_id}.stderr.log"
            stdout.write_text("BUILD SUCCESSFUL\n", encoding="utf-8")
            stderr.write_text("", encoding="utf-8")
            receipt = {
                "version": RECEIPT_VERSION,
                "producer": RECEIPT_PRODUCER,
                "id": evidence_id,
                "gate_id": gate_id,
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
                "cwd": "/tmp/project",
                "started_at": "2026-07-19T00:00:00+00:00",
                "finished_at": "2026-07-19T00:00:01+00:00",
                "timeout_seconds": 60,
                "timed_out": False,
                "exit_code": 0,
                "executed_tests": executed_tests,
                "reports": reports,
                "stdout": {
                    "path": str(stdout),
                    "exists": True,
                    "fresh": True,
                    "size": stdout.stat().st_size,
                    "sha256": sha256_file(stdout),
                },
                "stderr": {
                    "path": str(stderr),
                    "exists": True,
                    "fresh": True,
                    "size": stderr.stat().st_size,
                    "sha256": sha256_file(stderr),
                },
            }
            receipt_path = self.temp_root / f"{evidence_id}.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            return receipt_path

        test_report_record = {
            "path": str(test_report),
            "exists": True,
            "fresh": True,
            "size": test_report.stat().st_size,
            "sha256": junit_content_signature(test_report) or sha256_file(test_report),
            "junit": {
                "tests": 2,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "executed": 2,
                "test_cases": [
                    {"id": "FeatureTest#thenT1", "classname": "FeatureTest", "name": "thenT1", "status": "PASS"},
                    {"id": "FeatureTest#regression", "classname": "FeatureTest", "name": "regression", "status": "PASS"},
                ],
            },
        }
        lint_report_record = {
            "path": str(lint_report),
            "exists": True,
            "fresh": True,
            "size": lint_report.stat().st_size,
            "sha256": sha256_file(lint_report),
            "android_lint": {
                "format": "XML",
                "fatal": 0,
                "errors": 0,
                "warnings": 0,
                "information": 0,
                "total": 0,
            },
        }
        receipt_paths = {
            "E-TEST": create_receipt("E-TEST", "android-test-and-fix", test_command, [test_report_record], 2),
            "E-BUILD": create_receipt("E-BUILD", "android-build", ["./gradlew", ":app:assembleDebug"], [], None),
            "E-LINT": create_receipt("E-LINT", "android-lint", ["./gradlew", ":app:lintDebug"], [lint_report_record], None),
        }
        review_evidence = []
        for evidence_id, skill, summary in (
            ("E-DIFF", "android-review-diff", "实际 diff 与需求范围一致，未发现阻断项。"),
            ("E-QUALITY", "android-review-code-quality", "代码职责和项目架构一致，未发现阻断项。"),
            ("E-STABILITY", "android-audit-stability", "稳定性静态审查完成，未发现阻断项。"),
        ):
            specialist_result = {
                "version": SPECIALIST_RESULT_VERSION,
                "producer": SPECIALIST_PRODUCER,
                "id": evidence_id,
                "skill": skill,
                "provenance": {"skill": skill},
                "requirement_id": "baseline-1",
                "requirement_revision": 2,
                "requirement_file_sha256": self.requirement,
                "requirement_inputs_sha256": self.requirement_inputs,
                "baseline_id": "baseline-1",
                "snapshot_sha256": self.snapshot,
                "conclusion": "PASS",
                "summary": summary,
                "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
                "unresolved_findings": [],
                "obligation_sha256s": {},
            }
            if skill == "android-review-diff":
                specialist_result["confirmed_impacts"] = no_confirmed_impacts()
            if skill == "android-review-code-quality":
                specialist_result["checks"] = passing_code_quality_checks()
                specialist_result["executed_checks"] = len(specialist_result["checks"])
            if skill == "android-audit-stability":
                specialist_result["capabilities"] = [{
                    "id": "android-static-semantics",
                    "required": True,
                    "status": "PASS",
                }] + [
                    {
                        "id": capability_id,
                        "required": False,
                        "status": "SKIPPED",
                        "reason": "需求与最终 diff 未涉及。",
                    }
                    for capability_id in (
                        "android-dynamic-leak",
                        "android-performance",
                        "android-security-privacy",
                    )
                ]
                specialist_result["checks"] = passing_stability_checks()
                specialist_result["executed_checks"] = len(specialist_result["checks"])
                specialist_result["static_analysis"] = {
                    "languages": ["KOTLIN"],
                    "scope_files": ["app/src/main/java/sample/Feature.kt"],
                    "tools": [],
                    "control_audit_path": str(control_audit),
                    "control_audit_sha256": sha256_file(control_audit),
                    "control_changes": [],
                    "finding_ids": [],
                }
            specialist_path = self.temp_root / f"{evidence_id}.specialist.json"
            specialist_path.write_text(json.dumps(specialist_result), encoding="utf-8")
            review_evidence.append({
                "id": evidence_id,
                "kind": "REVIEW",
                "snapshot_sha256": self.snapshot,
                "summary": summary,
                "specialist": skill,
                "specialist_result_path": str(specialist_path),
                "specialist_result_sha256": sha256_file(specialist_path),
                "obligation_sha256s": {},
            })
        self.payload = {
            "version": 4,
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "baseline_id": "baseline-1",
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "snapshot_sha256": self.snapshot,
            "conclusion": "FULL_PASS",
            "pending_capabilities": [],
            "obligations": [
                {
                    "id": "BDD-001",
                    "required": True,
                    "obligation_sha256": self.obligation,
                    "status": "COVERED_AUTOMATED",
                    "evidence_ids": ["E-TEST"],
                }
            ],
            "gates": [
                {
                    "id": "android-test-and-fix",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-TEST"],
                },
                {
                    "id": "android-review-diff",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-DIFF"],
                },
                {
                    "id": "android-review-code-quality",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-QUALITY"],
                },
                {
                    "id": "android-audit-stability",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-STABILITY"],
                },
                {
                    "id": "android-build",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-BUILD"],
                },
                {
                    "id": "android-lint",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-LINT"],
                },
            ],
            "evidence": [
                {
                    "id": "E-TEST",
                    "kind": "AUTOMATED",
                    "gate_id": "android-test-and-fix",
                    "snapshot_sha256": self.snapshot,
                    "command": test_command,
                    "exit_code": 0,
                    "executed_tests": 2,
                    "receipt_path": str(receipt_paths["E-TEST"]),
                    "receipt_sha256": sha256_file(receipt_paths["E-TEST"]),
                    "report_paths": [str(test_report)],
                    "obligation_sha256s": {"BDD-001": self.obligation},
                    "obligation_test_cases": {"BDD-001": ["FeatureTest#thenT1"]},
                },
                {
                    "id": "E-BUILD",
                    "kind": "AUTOMATED",
                    "gate_id": "android-build",
                    "snapshot_sha256": self.snapshot,
                    "command": ["./gradlew", ":app:assembleDebug"],
                    "exit_code": 0,
                    "receipt_path": str(receipt_paths["E-BUILD"]),
                    "receipt_sha256": sha256_file(receipt_paths["E-BUILD"]),
                    "report_paths": [],
                    "obligation_sha256s": {},
                    "obligation_test_cases": {},
                },
                {
                    "id": "E-LINT",
                    "kind": "AUTOMATED",
                    "gate_id": "android-lint",
                    "snapshot_sha256": self.snapshot,
                    "command": ["./gradlew", ":app:lintDebug"],
                    "exit_code": 0,
                    "receipt_path": str(receipt_paths["E-LINT"]),
                    "receipt_sha256": sha256_file(receipt_paths["E-LINT"]),
                    "report_paths": [str(lint_report)],
                    "obligation_sha256s": {},
                    "obligation_test_cases": {},
                },
                *review_evidence,
            ],
        }

    def _set_receipt_exit_code(self, evidence_id: str, exit_code: int) -> None:
        """同步修改夹具里的执行收据和自动证据退出码。"""
        evidence = next(item for item in self.payload["evidence"] if item["id"] == evidence_id)
        receipt_path = Path(evidence["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["exit_code"] = exit_code
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        evidence["exit_code"] = exit_code
        evidence["receipt_sha256"] = sha256_file(receipt_path)

    def test_accepts_complete_fresh_result(self) -> None:
        """验证全部必需义务和门禁引用当前代码证据时允许通过。"""
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_failed_receipt_can_prove_matching_fail_gate(self) -> None:
        """验证未完成报告可直接保留与当前 gate 匹配的真实失败收据。"""
        self._set_receipt_exit_code("E-BUILD", 1)
        self.payload["conclusion"] = "INCOMPLETE"
        build_gate = next(gate for gate in self.payload["gates"] if gate["id"] == "android-build")
        build_gate["status"] = "FAIL"

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_success_receipt_cannot_be_relabeled_as_fail(self) -> None:
        """验证干净成功收据不能仅靠 gate 状态改写成失败证据。"""
        self.payload["conclusion"] = "INCOMPLETE"
        build_gate = next(gate for gate in self.payload["gates"] if gate["id"] == "android-build")
        build_gate["status"] = "FAIL"

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("未包含可复核的失败结果" in error for error in errors))

    def test_failed_receipt_cannot_prove_pass_gate_or_bdd_coverage(self) -> None:
        """验证失败收据不能被 PASS gate 或 BDD 自动覆盖借用。"""
        self._set_receipt_exit_code("E-TEST", 1)
        self.payload["conclusion"] = "INCOMPLETE"
        test_gate = next(
            gate for gate in self.payload["gates"] if gate["id"] == "android-test-and-fix"
        )
        test_gate["status"] = "FAIL"

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("exit_code 必须为 0" in error for error in errors))
        self.assertTrue(any("缺少自动执行证据" in error for error in errors))

    def test_out_of_scope_diff_blocks_passing_result(self) -> None:
        """验证最终 diff 超出影响半径时不能声明通过。"""
        self.context["changed_files"].append("app/src/main/java/sample/Unexpected.kt")

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("超出已确认影响半径" in error for error in errors))

    def test_rename_old_path_is_checked_against_radius(self) -> None:
        """验证重命名同时检查旧路径，不能把越界文件搬进允许目录绕过门禁。"""
        paths = _changed_paths_for_radius(
            [
                GitChange(
                    "R",
                    "app/src/main/java/sample/Feature.kt",
                    old_path="app/src/main/java/payment/PaymentRepository.kt",
                )
            ],
            excluded=set(),
        )
        self.context["changed_files"] = paths

        errors = validate_delivery_result(self.payload, self.context)

        self.assertIn("app/src/main/java/payment/PaymentRepository.kt", paths)
        self.assertTrue(any("超出已确认影响半径" in error for error in errors))

    def test_rejects_legacy_self_reported_result_version(self) -> None:
        """验证旧 version 3 报告不能绕过 gate 专属证据和人工收据门禁。"""
        self.payload["version"] = 3
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("version 必须为 4" in error for error in errors))

    def test_rejects_stale_snapshot_and_missing_evidence(self) -> None:
        """验证测试后代码变化或引用不存在时，旧报告不能继续判绿。"""
        self.payload["snapshot_sha256"] = "c" * 64
        self.payload["obligations"][0]["evidence_ids"] = ["E-MISSING"]
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("旧证据已经失效" in error for error in errors))
        self.assertTrue(any("不存在的证据" in error for error in errors))

    def test_requires_matching_manual_evidence(self) -> None:
        """验证计划人工执行不能冒充已经完成的人工覆盖。"""
        obligation = self.payload["obligations"][0]
        obligation["status"] = "COVERED_MANUAL"
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少实际人工证据" in error for error in errors))

    def test_summary_forces_unverified_and_residual_sections(self) -> None:
        """验证交付结论 md 必含'未验证项'与'残留风险'两个强制段，防被悄悄去掉。"""
        from ..delivery_gate import render_delivery_summary

        md_pass = render_delivery_summary(self.payload, self.context)
        self.assertIn("## 未验证项", md_pass)
        self.assertIn("## 残留风险", md_pass)

        # 设备待验场景：未验证项与残留风险必须填入实际内容，而非"无"。
        pending_payload = {
            **self.payload,
            "conclusion": "LOCAL_PASS_DEVICE_PENDING",
            "obligations": [
                {
                    **self.payload["obligations"][0],
                    "status": "UNVERIFIED",
                    "reason": "真机待验",
                }
            ],
            "pending_capabilities": [
                {
                    "id": "android-ui-a11y",
                    "requires_device": True,
                    "reason": "无真机",
                    "evidence_ids": ["E-TEST"],
                }
            ],
        }
        md_pending = render_delivery_summary(pending_payload, self.context)
        self.assertIn("## 未验证项", md_pending)
        self.assertIn("BDD-001", md_pending.split("## 未验证项")[1].split("## 残留风险")[0])
        residual = md_pending.split("## 残留风险")[1]
        self.assertIn("无真机", residual)
        self.assertNotIn("本结论未保留残留风险项", residual)

    def test_requires_exact_latest_obligation_set(self) -> None:
        """验证最终报告少写或多写一个 Then 都不能绕过最新版总需求。"""
        self.context["expected_obligations"]["BDD-002"] = {
            "required": True,
            "sha256": "e" * 64,
        }
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("漏掉当前确认义务: BDD-002" in error for error in errors))

    def test_changed_then_rejects_evidence_bound_to_old_semantics(self) -> None:
        """验证同一 ID 的 Then 文本变化后，旧义务摘要和测试证据不能继续复用。"""
        self.context["expected_obligations"]["BDD-001"]["sha256"] = "f" * 64
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("语义摘要与当前确认修订不一致" in error for error in errors))
        self.assertTrue(any("需求证据已失效" in error for error in errors))
        self.assertTrue(any("缺少自动执行证据" in error for error in errors))

    def test_stale_test_mapping_blocks_pass(self) -> None:
        """验证需求增量后测试映射仍为 STALE 时阻断通过结论。"""
        self.context["test_mapping"]["BDD-001"]["mapping_status"] = "STALE"
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("测试映射过期" in error for error in errors))

    def test_missing_test_mapping_blocks_pass(self) -> None:
        """验证缺少测试映射时 COVERED_AUTOMATED 义务不能通过。"""
        self.context["test_mapping"] = None
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少当前需求的测试映射" in error for error in errors))

    def test_test_mapping_must_match_receipts(self) -> None:
        """验证测试映射登记了未执行的测试时阻断通过。"""
        self.context["test_mapping"]["BDD-001"]["test_ids"] = [
            "FeatureTest#thenT1", "FeatureTest#never"
        ]
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("登记了未执行的测试" in error for error in errors))

    def test_automated_evidence_rejects_unmapped_testcase(self) -> None:
        """验证自动证据不能把同一收据中的无关测试关联给当前 BDD。"""
        self.payload["evidence"][0]["obligation_test_cases"]["BDD-001"].append(
            "FeatureTest#regression"
        )
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("自动证据关联了未登记测试" in error for error in errors))

    def test_automated_coverage_requires_mapped_test_id(self) -> None:
        """验证自动覆盖不能使用空 test_ids 绕过测试映射。"""
        self.context["test_mapping"]["BDD-001"]["test_ids"] = []
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("自动覆盖但未登记测试 id" in error for error in errors))

    def test_requires_every_core_review_build_and_lint_gate(self) -> None:
        """验证 AI 不能通过省略质量、稳定性、构建或 lint 门禁缩短完整交付。"""
        self.payload["gates"] = [
            gate for gate in self.payload["gates"]
            if gate["id"] != "android-review-code-quality"
        ]
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少核心交付门禁" in error and "代码质量与架构审查" in error for error in errors))

    def test_build_and_lint_require_execution_receipts(self) -> None:
        """验证专项审查或人工摘要不能冒充真实构建和 lint 命令。"""
        for gate in self.payload["gates"]:
            if gate["id"] in {"android-build", "android-lint"}:
                gate["evidence_ids"] = ["E-DIFF"]

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("项目构建" in error and "专属于本门禁" in error for error in errors))
        self.assertTrue(any("Android 静态检查（Lint）" in error and "专属于本门禁" in error for error in errors))

    def test_automated_evidence_cannot_cross_gate_boundaries(self) -> None:
        """验证测试收据不能冒充构建、Lint 或迁移专项证据。"""
        for gate in self.payload["gates"]:
            if gate["id"] == "android-build":
                gate["evidence_ids"] = ["E-TEST"]
        self.context["expected_conditional_gates"] = ["android-data-migration"]
        self.payload["gates"].append({
            "id": "android-data-migration",
            "required": True,
            "status": "PASS",
            "evidence_ids": ["E-TEST"],
        })

        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("项目构建" in error and "专属于本门禁" in error for error in errors))
        self.assertTrue(any("数据迁移检查" in error and "专属于本门禁" in error for error in errors))

    def test_empty_test_receipt_cannot_prove_test_gate(self) -> None:
        """验证 gate 标签正确也不能让零报告、零测试命令证明测试门禁。"""
        source = next(item for item in self.payload["evidence"] if item["id"] == "E-BUILD")
        receipt = json.loads(Path(source["receipt_path"]).read_text(encoding="utf-8"))
        command = ["python3", "-c", "pass"]
        receipt.update({
            "id": "E-EMPTY-TEST",
            "gate_id": "android-test-and-fix",
            "command": command,
            "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            "executed_tests": None,
            "reports": [],
        })
        receipt_path = self.temp_root / "E-EMPTY-TEST.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.payload["evidence"].append({
            "id": "E-EMPTY-TEST",
            "kind": "AUTOMATED",
            "gate_id": "android-test-and-fix",
            "snapshot_sha256": self.snapshot,
            "command": command,
            "exit_code": 0,
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256_file(receipt_path),
            "report_paths": [],
            "obligation_sha256s": {},
            "obligation_test_cases": {},
        })
        next(
            gate for gate in self.payload["gates"]
            if gate["id"] == "android-test-and-fix"
        )["evidence_ids"] = ["E-EMPTY-TEST"]

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少实际执行大于零的 JUnit 报告" in error for error in errors))
        self.assertTrue(any("自动化测试与修复" in error and "专属于本门禁" in error for error in errors))

    def test_generic_automated_receipt_cannot_prove_specialist_gate(self) -> None:
        """验证 UI/安全等专项 gate 不能仅凭 AI 填写同名 gate_id 判绿。"""
        source = next(item for item in self.payload["evidence"] if item["id"] == "E-TEST")
        receipt = json.loads(Path(source["receipt_path"]).read_text(encoding="utf-8"))
        receipt.update({"id": "E-UI-AUTO", "gate_id": "android-ui-a11y"})
        receipt_path = self.temp_root / "E-UI-AUTO.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        automated = dict(source)
        automated.update({
            "id": "E-UI-AUTO",
            "gate_id": "android-ui-a11y",
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256_file(receipt_path),
            "obligation_sha256s": {},
            "obligation_test_cases": {},
        })
        self.payload["evidence"].append(automated)
        self.context["expected_conditional_gates"] = ["android-ui-a11y"]
        self.payload["gates"].append({
            "id": "android-ui-a11y",
            "required": True,
            "status": "PASS",
            "evidence_ids": ["E-UI-AUTO"],
        })

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("界面与无障碍检查" in error and "专属于本门禁" in error for error in errors))

    def test_ui_gate_rejects_generic_manual_receipt(self) -> None:
        """UI 门禁只接受 android-verify-ui 专项结果，不接受通用人工收据。"""
        manual = {
            "id": "E-UI-MANUAL",
            "kind": "MANUAL",
            "gate_id": "android-ui-a11y",
            "snapshot_sha256": self.snapshot,
            "summary": "人工确认页面显示正常。",
            "executor": "用户",
            "environment": "Pixel 8",
            "performed_at": "2026-07-19T08:00:00+08:00",
            "steps": [{
                "action": "打开页面",
                "expected": "页面符合设计",
                "actual": "页面符合设计",
                "status": "PASS",
            }],
            "artifacts": [],
            "no_artifact_reason": "UI 结果使用链接记录。",
            "obligation_sha256s": {},
        }
        self.payload["evidence"].append(manual)
        self.payload["gates"].append({
            "id": "android-ui-a11y",
            "required": True,
            "status": "PASS",
            "evidence_ids": ["E-UI-MANUAL"],
        })
        self.context["expected_conditional_gates"] = ["android-ui-a11y"]

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("界面与无障碍检查" in error and "专属于本门禁" in error for error in errors))

    def test_api_contract_gate_rejects_specialist_pass_without_contract_evidence(self) -> None:
        """验证最终门禁不能接受 API 专项空 PASS 冒充契约核验。"""
        summary = "接口实现与契约一致。"
        fake_result = {
            "version": SPECIALIST_RESULT_VERSION,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-API",
            "skill": API_CONTRACT_SKILL,
            "provenance": {"skill": API_CONTRACT_SKILL},
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot,
            "conclusion": "PASS",
            "summary": summary,
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "unresolved_findings": [],
            "obligation_sha256s": {},
        }
        result_path = self.temp_root / "E-API.specialist.json"
        result_path.write_text(json.dumps(fake_result), encoding="utf-8")
        self.payload["evidence"].append({
            "id": "E-API",
            "kind": "REVIEW",
            "snapshot_sha256": self.snapshot,
            "summary": summary,
            "specialist": API_CONTRACT_SKILL,
            "specialist_result_path": str(result_path),
            "specialist_result_sha256": sha256_file(result_path),
            "obligation_sha256s": {},
        })
        self.context["expected_conditional_gates"] = ["android-verify-api-contract"]
        self.payload["gates"].append({
            "id": "android-verify-api-contract",
            "required": True,
            "status": "PASS",
            "evidence_ids": ["E-API"],
        })

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("API 契约专项" in error for error in errors))
        self.assertTrue(any(
            "接口契约检查" in error and "专属于本门禁" in error
            for error in errors
        ))

    def test_requires_route_triggered_conditional_gate(self) -> None:
        """验证 route 检出的条件能力不能被最终报告直接省略。"""
        self.context["expected_conditional_gates"] = ["android-data-migration"]
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少路由或语义触发的条件交付门禁" in error for error in errors))

        self.payload["gates"].append({
            "id": "android-data-migration",
            "required": False,
            "status": "SKIPPED",
            "evidence_ids": ["E-DIFF"],
            "reason": "实际仅修改内存缓存，没有持久化格式或旧数据迁移。",
        })
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_requires_every_route_specialist_task_to_have_a_gate_result(self) -> None:
        """验证 route 必需专项缺结果时，最终门禁用中文专项名称阻断。"""
        self.context["required_specialist_tasks"] = [{
            "id": "TASK-android-review-code-quality",
            "skill": "android-review-code-quality",
            "gate_id": "android-review-code-quality",
            "required": True,
            "status": "PENDING",
            "basis_files": ["app/src/main/java/sample/Feature.kt"],
            "reason": "代码质量专项为默认必需任务。",
        }]
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

        self.payload["gates"] = [
            gate for gate in self.payload["gates"]
            if gate["id"] != "android-review-code-quality"
        ]
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any(
            "代码质量与架构审查" in error and "未登记" in error
            for error in errors
        ))

    def test_ui_specialist_task_cannot_skip_visual_acceptance(self) -> None:
        """验证 UI 专项不能以无设计基准为由跳过真机视觉验收。"""
        self.context["required_specialist_tasks"] = [{
            "id": "TASK-android-verify-ui",
            "skill": "android-verify-ui",
            "gate_id": "android-ui-a11y",
            "required": True,
            "status": "PENDING",
            "basis_files": ["app/src/main/java/sample/Feature.kt"],
            "reason": "UI 候选已登记，等待适用性终判。",
        }]
        self.context["expected_conditional_gates"] = ["android-ui-a11y"]
        self.payload["gates"].append({
            "id": "android-ui-a11y",
            "required": False,
            "status": "SKIPPED",
            "evidence_ids": ["E-DIFF"],
            "reason": "当前没有设计基准，仅保留基础 UI 复核证据。",
        })
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("UI 视觉门禁不能跳过" in error for error in errors))

    def test_requires_diff_review_semantic_conditional_gates(self) -> None:
        """验证正则漏检时，Diff Reviewer 的语义影响仍能强制补齐条件门禁。"""
        evidence = next(item for item in self.payload["evidence"] if item["id"] == "E-DIFF")
        result_path = Path(evidence["specialist_result_path"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for item in result["confirmed_impacts"]:
            if item["id"] == "api":
                item.update({
                    "applicable": True,
                    "basis_files": ["app/src/main/example/Foo.kt"],
                    "reason": "普通文件名中新增 Ktor client.get 请求。",
                })
        result_path.write_text(json.dumps(result), encoding="utf-8")
        evidence["specialist_result_sha256"] = sha256_file(result_path)

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any(
            "android-verify-api-contract" in error and "路由或语义触发" in error
            for error in errors
        ))
        self.assertTrue(any(
            "android-security-privacy" in error and "路由或语义触发" in error
            for error in errors
        ))

    def test_rejects_missing_or_changed_execution_receipt(self) -> None:
        """验证自动证据不能只填写命令和退出码，也不能引用被修改的收据。"""
        evidence = self.payload["evidence"][0]
        evidence.pop("receipt_path")
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少 execution_evidence.py 收据路径" in error for error in errors))

        evidence["receipt_path"] = str(self.temp_root / "E-TEST.json")
        evidence["receipt_sha256"] = "0" * 64
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("执行收据摘要不一致" in error for error in errors))

    def test_automated_obligation_requires_nonzero_test_count(self) -> None:
        """验证构建成功或零测试不能冒充 BDD 场景的自动化覆盖。"""
        self.payload["evidence"][0]["executed_tests"] = 0
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("没有实际执行测试" in error for error in errors))

    def test_automated_obligation_requires_real_testcase_mapping(self) -> None:
        """验证测试总数不能替代 Then 到 JUnit testcase 的明确映射。"""
        self.payload["evidence"][0]["obligation_test_cases"] = {}
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少自动执行证据" in error for error in errors))

    def test_tdd_required_rejects_missing_cycle_even_when_green_receipt_exists(self) -> None:
        """验证开启 TDD 后，最终 Green 收据不能替代独立 Red/Green 周期记录。"""
        self.context["tdd_required"] = True
        self.context["tdd_cycle_path"] = str(self.temp_root / "missing-tdd-cycle.json")

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少 TDD 周期记录" in error for error in errors))
        self.assertTrue(any("自动化测试与修复" in error and "没有专属于本门禁" in error for error in errors))

    def test_manual_coverage_requires_complete_receipt(self) -> None:
        """验证一句人工通过不能覆盖 Then，完整步骤和环境记录才可使用。"""
        manual = {
            "id": "E-MANUAL",
            "kind": "MANUAL",
            "gate_id": "android-test-and-fix",
            "snapshot_sha256": self.snapshot,
            "summary": "人工验证业务结果正确。",
            "executor": "用户",
            "environment": "Pixel 8 / Android 15 / debug",
            "performed_at": "2026-07-19T08:00:00+08:00",
            "steps": [{
                "action": "打开页面并执行保存",
                "expected": "显示保存成功",
                "actual": "显示保存成功",
                "status": "PASS",
            }],
            "artifacts": [],
            "no_artifact_reason": "该业务结果没有可导出的额外产物。",
            "obligation_sha256s": {"BDD-001": self.obligation},
        }
        self.payload["evidence"].append(manual)
        self.payload["obligations"][0].update({
            "status": "COVERED_MANUAL",
            "evidence_ids": ["E-MANUAL"],
        })
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

        manual["steps"] = []
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("steps 必须是非空数组" in error for error in errors))
        self.assertTrue(any("缺少实际人工证据" in error for error in errors))

    def test_device_pending_conclusion_requires_real_pending_item(self) -> None:
        """验证设备待验结论不能作为 FULL_PASS 的空别名。"""
        self.payload["conclusion"] = "LOCAL_PASS_DEVICE_PENDING"
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("至少记录一个真实设备待验证项" in error for error in errors))

        summary = "UI 视觉验收未完成，当前没有设备执行真机截图和 TalkBack 动态验收。"
        specialist = {
            "version": SPECIALIST_RESULT_VERSION,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-UI-PENDING",
            "skill": "android-verify-ui",
            "provenance": {"skill": "android-verify-ui"},
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot,
            "conclusion": "UNVERIFIED",
            "summary": summary,
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "unresolved_findings": [],
            "capabilities": [{
                "id": "android-ui-a11y",
                "required": False,
                "status": "UNVERIFIED",
                "reason": "当前没有可用设备。",
            }],
            "device_check": {
                "status": "UNAVAILABLE",
                "reason": "当前没有可用设备。",
            },
            "obligation_sha256s": {},
        }
        result_path = self.temp_root / "E-UI-PENDING.specialist.json"
        result_path.write_text(json.dumps(specialist), encoding="utf-8")
        self.payload["evidence"].append({
            "id": "E-UI-PENDING",
            "kind": "REVIEW",
            "snapshot_sha256": self.snapshot,
            "summary": summary,
            "specialist": "android-verify-ui",
            "specialist_result_path": str(result_path),
            "specialist_result_sha256": sha256_file(result_path),
            "obligation_sha256s": {},
        })
        self.payload["pending_capabilities"] = [{
            "id": "android-ui-a11y",
            "requires_device": True,
            "reason": "当前没有可用设备，TalkBack 动态体验待验证。",
            "evidence_ids": ["E-UI-PENDING"],
        }]
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

        self.payload["conclusion"] = "FULL_PASS"
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("FULL_PASS 不允许保留" in error for error in errors))

    def test_full_pass_rejects_unverified_optional_specialist_capability(self) -> None:
        """验证可选专项能力未验证时也不能把 FULL_PASS 写成零风险结论。"""
        evidence = next(item for item in self.payload["evidence"] if item["id"] == "E-STABILITY")
        result_path = Path(evidence["specialist_result_path"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        dynamic_leak = next(
            item for item in result["capabilities"]
            if item["id"] == "android-dynamic-leak"
        )
        dynamic_leak.update({
            "status": "UNVERIFIED",
            "reason": "当前没有设备执行动态泄漏验证。",
        })
        result_path.write_text(json.dumps(result), encoding="utf-8")
        evidence["specialist_result_sha256"] = sha256_file(result_path)

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("FULL_PASS 不允许保留 UNVERIFIED/BLOCKED" in error for error in errors))

    def test_pending_capability_requires_matching_unverified_evidence(self) -> None:
        """验证设备待验项不能引用无关 Review 证据或自造 capability 名称。"""
        self.payload["conclusion"] = "LOCAL_PASS_DEVICE_PENDING"
        self.payload["pending_capabilities"] = [{
            "id": "invented-device-check",
            "requires_device": True,
            "reason": "等待设备。",
            "evidence_ids": ["E-DIFF"],
        }]

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少同能力的 UNVERIFIED/BLOCKED" in error for error in errors))

    def test_security_gate_requires_matching_stability_capability(self) -> None:
        """验证安全条件 gate 只能由稳定性结果中的同名 PASS capability 证明。"""
        self.context["expected_conditional_gates"] = ["android-security-privacy"]
        self.payload["gates"].append({
            "id": "android-security-privacy",
            "required": True,
            "status": "PASS",
            "evidence_ids": ["E-STABILITY"],
        })
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("安全与隐私检查" in error and "专属于本门禁" in error for error in errors))

        evidence = next(item for item in self.payload["evidence"] if item["id"] == "E-STABILITY")
        result_path = Path(evidence["specialist_result_path"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        capability = next(
            item for item in result["capabilities"]
            if item["id"] == "android-security-privacy"
        )
        capability.update({"required": True, "status": "PASS"})
        capability.pop("reason", None)
        result_path.write_text(json.dumps(result), encoding="utf-8")
        evidence["specialist_result_sha256"] = sha256_file(result_path)

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_requirement_input_change_invalidates_result(self) -> None:
        """验证 Figma/API 等输入摘要变化后旧交付结果立即失效。"""
        self.context["requirement_inputs_sha256"] = "f" * 64
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("requirement_inputs_sha256" in error for error in errors))

    def test_accepts_agent_journey_with_structured_actions_and_artifact(self) -> None:
        """验证 Android CLI Agent Journey 可凭统一结果覆盖实际断言的 BDD 场景。"""
        screenshot = self.temp_root / "journey-home.png"
        screenshot.write_bytes(b"fake-png-evidence")
        summary = "已执行首页 Journey，点击重试后首页标题可见。"
        agent_result = {
            "version": SPECIALIST_RESULT_VERSION,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-JOURNEY",
            "skill": "android-test-and-fix/journey-agent",
            "provenance": {"skill": "android-test-and-fix/journey-agent"},
            "requirement_id": "baseline-1",
            "requirement_revision": 2,
            "requirement_file_sha256": self.requirement,
            "requirement_inputs_sha256": self.requirement_inputs,
            "baseline_id": "baseline-1",
            "snapshot_sha256": self.snapshot,
            "conclusion": "PASS",
            "summary": summary,
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "unresolved_findings": [],
            "capabilities": [{"id": "journey", "required": True, "status": "PASS"}],
            "commands": [["android", "layout", "--device", "emulator-5554"]],
            "checks": [
                {
                    "id": "action-1",
                    "required": True,
                    "status": "PASS",
                    "summary": "点击重试按钮。",
                },
                {
                    "id": "action-2",
                    "required": True,
                    "status": "PASS",
                    "summary": "首页标题可见。",
                },
            ],
            "artifacts": [{
                "path": str(screenshot),
                "sha256": sha256_file(screenshot),
                "kind": "screenshot",
            }],
            "executed_checks": 2,
            "executed_tests": 1,
            "obligation_sha256s": {"BDD-001": self.obligation},
            "started_at": "2026-07-19T00:00:00+00:00",
            "finished_at": "2026-07-19T00:00:10+00:00",
        }
        result_path = self.temp_root / "E-JOURNEY.specialist.json"
        result_path.write_text(json.dumps(agent_result), encoding="utf-8")
        self.payload["evidence"].append({
            "id": "E-JOURNEY",
            "kind": "AGENT",
            "snapshot_sha256": self.snapshot,
            "summary": summary,
            "specialist": "android-test-and-fix/journey-agent",
            "specialist_result_path": str(result_path),
            "specialist_result_sha256": sha256_file(result_path),
            "executed_tests": 1,
            "obligation_sha256s": {"BDD-001": self.obligation},
        })
        self.payload["obligations"][0]["evidence_ids"] = ["E-JOURNEY"]

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

        agent_result["capabilities"] = []
        result_path.write_text(json.dumps(agent_result), encoding="utf-8")
        self.payload["evidence"][-1]["specialist_result_sha256"] = sha256_file(result_path)
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("必需 Journey 能力" in error for error in errors))

        agent_result["capabilities"] = [{
            "id": "journey",
            "required": True,
            "status": "PASS",
        }]
        result_path.write_text(json.dumps(agent_result), encoding="utf-8")
        self.payload["evidence"][-1]["specialist_result_sha256"] = sha256_file(result_path)

        self.payload["evidence"][-1]["specialist"] = "untrusted-agent"
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("AGENT 证据 E-JOURNEY 只能由" in error for error in errors))

    def test_incomplete_conclusion_is_truthful_but_not_passing(self) -> None:
        """验证未完成报告可以保留缺口，不会被结构校验误写成通过。"""
        self.payload["conclusion"] = "INCOMPLETE"
        self.payload["obligations"][0]["status"] = "UNVERIFIED"
        self.payload["obligations"][0]["evidence_ids"] = []

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_current_context_binds_requirement_and_git_snapshot(self) -> None:
        """验证门禁上下文来自真实需求文件和当前 Git 工作树，而不是报告自行声明。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "gate@example.invalid"],
                cwd=repo,
                check=True,
            )
            (repo / "App.kt").write_text("class App\n", encoding="utf-8")
            subprocess.run(["git", "add", "App.kt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=repo, check=True)
            baseline = root / "baseline.json"
            baseline_payload = write_baseline(repo, baseline)
            (repo / "App.kt").write_text("class AppChanged\n", encoding="utf-8")
            requirement_dir = root / "requirement"
            requirement_dir.mkdir()
            requirement = requirement_dir / "requirement.md"
            requirement.write_text("修改 App\n", encoding="utf-8")
            requirement_snapshot = root / "requirement-snapshot.json"
            write_requirement_snapshot(
                requirement_snapshot,
                requirement,
                "修改 App",
                requirement_id=baseline_payload["id"],
            )
            confirmed, applied = apply_requirement_revision(
                requirement_snapshot,
                requirement,
                "修改 App",
                {
                    "version": 1,
                    "requirement_id": baseline_payload["id"],
                    "base_revision": 0,
                    "scope": "SAME_REQUIREMENT",
                    "changes": [{
                        "id": "BDD-001",
                        "change_type": "ADDED",
                        "decision": "CONFIRMED",
                        "text": "App 行为已修改",
                        "required": True,
                    }],
                },
            )
            self.assertTrue(applied)
            config = {
                "workspace_root": str(root),
                "project_path": str(repo),
                "requirement_dir": str(requirement_dir),
                "requirement_file": str(requirement),
            }
            radius_payload = {
                "version": 1,
                "generated_at": "2026-07-27T00:00:00+00:00",
                "requirement_id": confirmed["requirement_id"],
                "requirement_revision": 1,
                "requirement_file_sha256": confirmed["sha256"],
                "requirement_summary_sha256": requirement_summary_digest(confirmed),
                "allowed_files": ["App.kt"],
                "allowed_dirs": [],
                "impacts": [{
                    "id": "BDD-001",
                    "change_type": "ADDED",
                    "reason": "App 行为修改只影响 App.kt。",
                    "expected_files": ["App.kt"],
                    "expected_tests": ["AppTest#changed"],
                    "affected_modules": [":app"],
                }],
            }
            radius_file = impact_radius_path(requirement_dir)
            radius_file.parent.mkdir(parents=True, exist_ok=True)
            radius_file.write_text(json.dumps(radius_payload, ensure_ascii=False), encoding="utf-8")
            radius_sha = impact_radius_digest(radius_payload)
            inputs_sha256 = requirement_inputs_digest(
                config,
                root / "local.yaml",
                confirmed["sha256"],
                implementation_plan_sha256="d" * 64,
                impact_radius_sha256=radius_sha,
            )
            git_snapshot = current_delivery_snapshot(repo, baseline)
            route_path = root / "route-impact.json"
            write_route_impact(
                route_path,
                build_route_impact(
                    {
                        **git_snapshot,
                        "requirement_id": confirmed["requirement_id"],
                        "requirement_revision": 1,
                        "requirement_file_sha256": confirmed["sha256"],
                        "requirement_inputs_sha256": inputs_sha256,
                        "implementation_plan_sha256": "d" * 64,
                        "impact_radius_sha256": radius_sha,
                        "plan_confirmation_receipt_sha256": "e" * 64,
                    },
                    {category: [] for category in (
                        "ui", "api", "data", "system", "build", "architecture", "tests",
                    )},
                    {
                        "openapi": False,
                        "migration": False,
                        "ui_a11y": False,
                        "security_privacy": False,
                    },
                ),
            )
            fact_inbox = requirement_dir / ".state" / "fact-inbox.json"
            fact = add_fact(fact_inbox, "还要支持空数组")
            with (
                patch_module_global(delivery_gate_module, "baseline_path_for_config", return_value=baseline),
                patch_module_global(delivery_gate_module, "requirement_snapshot_path_for_config",
                    return_value=requirement_snapshot,
                ),
                patch_module_global(delivery_gate_module, "validate_plan_confirmation",
                    return_value={
                        "implementation_plan_sha256": "d" * 64,
                        "impact_radius_sha256": radius_sha,
                        "plan_confirmation_receipt_sha256": "e" * 64,
                    },
                ),
                patch_module_global(delivery_gate_module, "route_impact_path_for_config", return_value=route_path),
            ):
                with self.assertRaisesRegex(DeliveryGateError, "聊天事实"):
                    current_context(root / "local.yaml", config)
                resolve_fact(fact_inbox, fact["id"], "DISCUSSION")
                context = current_context(root / "local.yaml", config)
                blocked_route = json.loads(route_path.read_text(encoding="utf-8"))
                blocked_route["convergence_status"] = "BLOCKED"
                blocked_route["route_round"] = blocked_route["max_route_rounds"] + 1
                write_route_impact(route_path, blocked_route)
                with self.assertRaisesRegex(DeliveryGateError, "路由收敛已阻断"):
                    current_context(root / "local.yaml", config)
                blocked_route["convergence_status"] = "INITIAL"
                blocked_route["route_round"] = 1
                write_route_impact(route_path, blocked_route)
                (repo / "App.kt").write_text("class AppChangedAgain\n", encoding="utf-8")
                with self.assertRaisesRegex(DeliveryGateError, "路由影响快照.*已失效"):
                    current_context(root / "local.yaml", config)

        self.assertEqual(baseline_payload["id"], context["baseline_id"])
        self.assertEqual(64, len(context["snapshot_sha256"]))
        self.assertEqual(64, len(context["requirement_file_sha256"]))
        self.assertEqual(64, len(context["requirement_inputs_sha256"]))
        self.assertEqual("d" * 64, context["implementation_plan_sha256"])
        self.assertEqual(radius_sha, context["impact_radius_sha256"])
        self.assertEqual(confirmed["requirement_id"], context["requirement_id"])
        self.assertEqual(1, context["requirement_revision"])
        self.assertIn("BDD-001", context["expected_obligations"])
        self.assertEqual(str(fact_inbox.resolve()), context["fact_inbox_path"])

    def test_current_context_blocks_unconfirmed_requirement_update(self) -> None:
        """验证需求文件变化或待定修订存在时，最终门禁不能生成可通过上下文。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "gate@example.invalid"], cwd=repo, check=True,
            )
            (repo / "App.kt").write_text("class App\n", encoding="utf-8")
            subprocess.run(["git", "add", "App.kt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=repo, check=True)
            baseline = root / "baseline.json"
            baseline_payload = write_baseline(repo, baseline)
            requirement = root / "requirement.md"
            requirement.write_text("初始需求\n", encoding="utf-8")
            snapshot = root / "snapshot.json"
            write_requirement_snapshot(
                snapshot, requirement, "初始需求", requirement_id=baseline_payload["id"],
            )
            config = {
                "workspace_root": str(root),
                "project_path": str(repo),
                "requirement_dir": str(root),
                "requirement_file": str(requirement),
            }
            with (
                patch_module_global(delivery_gate_module, "baseline_path_for_config", return_value=baseline),
                patch_module_global(delivery_gate_module, "requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
            ):
                with self.assertRaisesRegex(DeliveryGateError, "待定或冲突"):
                    current_context(root / "local.yaml", config)

    def test_cli_validate_accepts_fresh_report(self) -> None:
        """验证 CLI 通过机器门禁后同步生成不含哈希的中文摘要。"""
        with tempfile.TemporaryDirectory() as raw_root:
            result = Path(raw_root) / "delivery-result.json"
            result.write_text(
                json.dumps(self.payload, ensure_ascii=False),
                encoding="utf-8",
            )
            self.context["expected_obligations"]["BDD-001"]["text"] = "点击重试后恢复"
            with (
                patch_module_global(delivery_gate_module, "load_config", return_value={}),
                patch_module_global(delivery_gate_module, "current_context", return_value=self.context),
                redirect_stdout(io.StringIO()),
            ):
                exit_code = main([
                    "validate",
                    "--config", str(Path(raw_root) / "local.yaml"),
                    "--result", str(result),
                ])
            summary = (result.parent.parent / "docs" / "交付结论.md").read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("全部验证通过", summary)
        self.assertIn("当前确认需求未登记需要修改或重点保护的已上线业务", summary)
        self.assertIn("点击重试后恢复", summary)
        self.assertIn("自动测试通过", summary)
        self.assertNotIn(self.snapshot, summary)

    def test_cli_incomplete_still_writes_readable_summary(self) -> None:
        """验证未完成结论返回退出码 2，但仍向用户提供中文待办报告。"""
        self.payload["conclusion"] = "INCOMPLETE"
        self.payload["obligations"][0].update({
            "status": "UNVERIFIED",
            "reason": "需要合适设备完成点击验证。",
        })
        self.context["expected_obligations"]["BDD-001"]["text"] = "点击重试后恢复"
        with tempfile.TemporaryDirectory() as raw_root:
            result = Path(raw_root) / "delivery-result.json"
            result.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            with (
                patch_module_global(delivery_gate_module, "load_config", return_value={}),
                patch_module_global(delivery_gate_module, "current_context", return_value=self.context),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                exit_code = main([
                    "validate",
                    "--config", str(Path(raw_root) / "local.yaml"),
                    "--result", str(result),
                ])
            summary = (result.parent.parent / "docs" / "交付结论.md").read_text(encoding="utf-8")

        self.assertEqual(2, exit_code)
        self.assertIn("尚未完成", summary)
        self.assertIn("点击重试后恢复", summary)
        self.assertIn("需要合适设备完成点击验证", summary)

    def test_unverified_existing_business_protection_blocks_passing(self) -> None:
        """验证已确认的旧业务保护 Then 缺少证据时复用现有义务门禁阻断通过。"""
        self.context["expected_obligations"]["BDD-001"]["text"] = (
            "【保护已上线业务】赠品订单：零金额仍然允许提交"
        )
        self.payload["obligations"][0].update({
            "status": "UNVERIFIED",
            "evidence_ids": [],
        })

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("尚未覆盖" in error for error in errors))

    def test_optional_existing_business_protection_cannot_bypass_gate(self) -> None:
        """验证另有必需项通过时，旧业务保护项仍不能设为可选并标记不适用。"""
        self.context["expected_obligations"]["BDD-004"] = {
            "required": False,
            "sha256": "e" * 64,
            "text": "【保护已上线业务】赠品订单：零金额仍然允许提交",
        }
        self.payload["obligations"].append({
            "id": "BDD-004",
            "required": False,
            "obligation_sha256": "e" * 64,
            "status": "NOT_APPLICABLE",
            "evidence_ids": [],
        })

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("必须 required=true" in error for error in errors))

    def test_traceability_markdown_is_not_an_independent_gate_input(self) -> None:
        """追溯表是机器生成视图，缺失或过期不能替代 JSON 事实参与判定。"""
        self.traceability.unlink()
        self.context["traceability_path"] = str(self.traceability)

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_cli_snapshot_outputs_json_serializable_route_context(self) -> None:
        """验证 route 条件门禁上下文可以直接供 AI 读取并生成最终报告。"""
        output = io.StringIO()
        with (
            patch_module_global(delivery_gate_module, "load_config", return_value={}),
            patch_module_global(delivery_gate_module, "current_context", return_value=self.context),
            redirect_stdout(output),
        ):
            exit_code = main(["snapshot", "--config", str(self.temp_root / "local.yaml")])

        self.assertEqual(0, exit_code)
        self.assertEqual([], json.loads(output.getvalue())["expected_conditional_gates"])


if __name__ == "__main__":
    unittest.main()
