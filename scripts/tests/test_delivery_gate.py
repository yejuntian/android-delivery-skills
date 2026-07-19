#!/usr/bin/env python3
"""脚本名称：test_delivery_gate.py

用途：验证最终交付门禁只接受当前代码上的完整原子义务、专项门禁和真实证据。

覆盖范围：通过报告、最新版义务、route 条件门禁、执行收据、专项/Agent 结果、过期
需求语义和未完成结论。测试不运行 Android 构建、不修改真实仓库。
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
from contextlib import redirect_stdout
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..delivery_gate import (  # noqa: E402
    DeliveryGateError,
    current_context,
    main,
    validate_delivery_result,
)
from ..execution_evidence import RECEIPT_PRODUCER, sha256_file  # noqa: E402
from ..git_changes import current_delivery_snapshot, write_baseline  # noqa: E402
from ..requirement_snapshot import (  # noqa: E402
    apply_requirement_revision,
    write_requirement_snapshot,
)
from ..requirement_inputs import requirement_inputs_digest  # noqa: E402
from ..route_impact import build_route_impact, write_route_impact  # noqa: E402
from ..specialist_result import SPECIALIST_PRODUCER  # noqa: E402


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
                "BDD-001/T1": {"required": True, "sha256": self.obligation},
            },
            "expected_conditional_gates": [],
            "result_path": "/tmp/result.json",
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
                "version": 2,
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
            "sha256": sha256_file(test_report),
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
                "version": 2,
                "producer": SPECIALIST_PRODUCER,
                "id": evidence_id,
                "skill": skill,
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
            if skill == "android-audit-stability":
                specialist_result["capabilities"] = [
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
                    "id": "BDD-001/T1",
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
                    "obligation_sha256s": {"BDD-001/T1": self.obligation},
                    "obligation_test_cases": {"BDD-001/T1": ["FeatureTest#thenT1"]},
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

    def test_accepts_complete_fresh_result(self) -> None:
        """验证全部必需义务和门禁引用当前代码证据时允许通过。"""
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

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

    def test_requires_exact_latest_obligation_set(self) -> None:
        """验证最终报告少写或多写一个 Then 都不能绕过最新版总需求。"""
        self.context["expected_obligations"]["BDD-001/T2"] = {
            "required": True,
            "sha256": "e" * 64,
        }
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("漏掉当前确认义务: BDD-001/T2" in error for error in errors))

    def test_changed_then_rejects_evidence_bound_to_old_semantics(self) -> None:
        """验证同一 ID 的 Then 文本变化后，旧义务摘要和测试证据不能继续复用。"""
        self.context["expected_obligations"]["BDD-001/T1"]["sha256"] = "f" * 64
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("语义摘要与当前确认修订不一致" in error for error in errors))
        self.assertTrue(any("需求证据已失效" in error for error in errors))
        self.assertTrue(any("缺少自动执行证据" in error for error in errors))

    def test_requires_every_core_review_build_and_lint_gate(self) -> None:
        """验证 AI 不能通过省略质量、稳定性、构建或 lint 门禁缩短完整交付。"""
        self.payload["gates"] = [
            gate for gate in self.payload["gates"]
            if gate["id"] != "android-review-code-quality"
        ]
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少核心 gate: android-review-code-quality" in error for error in errors))

    def test_build_and_lint_require_execution_receipts(self) -> None:
        """验证专项审查或人工摘要不能冒充真实构建和 lint 命令。"""
        for gate in self.payload["gates"]:
            if gate["id"] in {"android-build", "android-lint"}:
                gate["evidence_ids"] = ["E-DIFF"]

        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("gate android-build 没有专属于本 gate" in error for error in errors))
        self.assertTrue(any("gate android-lint 没有专属于本 gate" in error for error in errors))

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
        self.assertTrue(any("gate android-build 没有专属于本 gate" in error for error in errors))
        self.assertTrue(any("gate android-data-migration 没有专属于本 gate" in error for error in errors))

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
        self.assertTrue(any("gate android-test-and-fix 没有专属于本 gate" in error for error in errors))

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

        self.assertTrue(any("gate android-ui-a11y 没有专属于本 gate" in error for error in errors))

    def test_requires_route_triggered_conditional_gate(self) -> None:
        """验证 route 检出的条件能力不能被最终报告直接省略。"""
        self.context["expected_conditional_gates"] = ["android-data-migration"]
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少路由触发的条件 gate" in error for error in errors))

        self.payload["gates"].append({
            "id": "android-data-migration",
            "required": False,
            "status": "SKIPPED",
            "evidence_ids": ["E-DIFF"],
            "reason": "实际仅修改内存缓存，没有持久化格式或旧数据迁移。",
        })
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

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
        """验证构建成功或零测试不能冒充原子 Then 的自动化覆盖。"""
        self.payload["evidence"][0]["executed_tests"] = 0
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("没有实际执行测试" in error for error in errors))

    def test_automated_obligation_requires_real_testcase_mapping(self) -> None:
        """验证测试总数不能替代 Then 到 JUnit testcase 的明确映射。"""
        self.payload["evidence"][0]["obligation_test_cases"] = {}
        errors = validate_delivery_result(self.payload, self.context)
        self.assertTrue(any("缺少自动执行证据" in error for error in errors))

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
            "obligation_sha256s": {"BDD-001/T1": self.obligation},
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

        summary = "静态 UI 检查完成，当前没有设备执行 TalkBack 动态验收。"
        specialist = {
            "version": 2,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-UI-PENDING",
            "skill": "android-verify-ui",
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
        result["capabilities"][0].update({
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
        self.assertTrue(any("gate android-security-privacy 没有专属于本 gate" in error for error in errors))

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
        """验证 Android CLI Agent Journey 可凭统一结果覆盖实际断言的原子 Then。"""
        screenshot = self.temp_root / "journey-home.png"
        screenshot.write_bytes(b"fake-png-evidence")
        summary = "已执行首页 Journey，点击重试后首页标题可见。"
        agent_result = {
            "version": 2,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-JOURNEY",
            "skill": "android-test-and-fix/journey-agent",
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
            "obligation_sha256s": {"BDD-001/T1": self.obligation},
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
            "obligation_sha256s": {"BDD-001/T1": self.obligation},
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
                        "id": "BDD-001/T1",
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
            inputs_sha256 = requirement_inputs_digest(
                config,
                root / "local.yaml",
                confirmed["sha256"],
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
            with (
                mock.patch("scripts.delivery_gate.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery_gate.requirement_snapshot_path_for_config",
                    return_value=requirement_snapshot,
                ),
                mock.patch("scripts.delivery_gate.route_impact_path_for_config", return_value=route_path),
            ):
                context = current_context(root / "local.yaml", config)
                (repo / "App.kt").write_text("class AppChangedAgain\n", encoding="utf-8")
                with self.assertRaisesRegex(DeliveryGateError, "路由影响快照.*已失效"):
                    current_context(root / "local.yaml", config)

        self.assertEqual(baseline_payload["id"], context["baseline_id"])
        self.assertEqual(64, len(context["snapshot_sha256"]))
        self.assertEqual(64, len(context["requirement_file_sha256"]))
        self.assertEqual(64, len(context["requirement_inputs_sha256"]))
        self.assertEqual(confirmed["requirement_id"], context["requirement_id"])
        self.assertEqual(1, context["requirement_revision"])
        self.assertIn("BDD-001/T1", context["expected_obligations"])

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
                mock.patch("scripts.delivery_gate.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery_gate.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
            ):
                with self.assertRaisesRegex(DeliveryGateError, "待定或冲突"):
                    current_context(root / "local.yaml", config)

    def test_cli_validate_accepts_fresh_report(self) -> None:
        """验证 CLI 能读取结果文件并以退出码 0 表达机器门禁通过。"""
        with tempfile.TemporaryDirectory() as raw_root:
            result = Path(raw_root) / "delivery-result.json"
            result.write_text(
                json.dumps(self.payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                mock.patch("scripts.delivery_gate.load_config", return_value={}),
                mock.patch("scripts.delivery_gate.current_context", return_value=self.context),
                redirect_stdout(io.StringIO()),
            ):
                exit_code = main([
                    "validate",
                    "--config", str(Path(raw_root) / "local.yaml"),
                    "--result", str(result),
                ])

        self.assertEqual(0, exit_code)

    def test_cli_snapshot_outputs_json_serializable_route_context(self) -> None:
        """验证 route 条件门禁上下文可以直接供 AI 读取并生成最终报告。"""
        output = io.StringIO()
        with (
            mock.patch("scripts.delivery_gate.load_config", return_value={}),
            mock.patch("scripts.delivery_gate.current_context", return_value=self.context),
            redirect_stdout(output),
        ):
            exit_code = main(["snapshot", "--config", str(self.temp_root / "local.yaml")])

        self.assertEqual(0, exit_code)
        self.assertEqual([], json.loads(output.getvalue())["expected_conditional_gates"])


if __name__ == "__main__":
    unittest.main()
