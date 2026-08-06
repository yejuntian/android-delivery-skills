#!/usr/bin/env python3
"""脚本名称：test_specialist_result.py

用途：验证最小专项结果能够阻断 P0/P1、过期代码、缺失的代码质量核心检查和被修改的可选证据文件。

覆盖范围：普通 Review 最小信封、Diff 语义影响、代码质量结构化检查、按需能力/
命令/artifact 和上下文绑定。测试只使用临时文件，不调用真实项目、设备或网络。
"""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from contextlib import redirect_stdout


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from .. import delivery as delivery_module  # noqa: E402
from .. import delivery_gate as delivery_gate_module  # noqa: E402
from ..test_support import patch_module_global  # noqa: E402
from ..execution_evidence import sha256_file  # noqa: E402
from ..specialist_result import (  # noqa: E402
    API_CONTRACT_CHECK_IDS,
    API_CONTRACT_CAPABILITY_ID,
    API_CONTRACT_SKILL,
    CODE_QUALITY_CHECK_IDS,
    IMPACT_CATEGORIES,
    SPECIALIST_PRODUCER,
    SPECIALIST_RESULT_VERSION,
    STABILITY_STATIC_CHECK_IDS,
    UI_VERIFY_SKILL,
    conditional_gates_from_confirmed_impacts,
    main,
    validate_specialist_result,
)


def no_confirmed_impacts() -> list[dict]:
    """生成 Diff Reviewer 对七类影响均确认不适用的最小有效结果。"""
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
    """生成分层、职责、核心注释和可测试性均通过的代码质量检查。"""
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
    """生成六条静态不变量和控制面审计均已实际复核的机器检查。"""
    return [
        {
            "id": check_id,
            "required": True,
            "status": "PASS",
            "summary": "已结合最终 diff、必要调用链和项目配置完成复核。",
        }
        for check_id in sorted(STABILITY_STATIC_CHECK_IDS)
    ]


def passing_static_analysis(audit_path: Path, audit_sha256: str) -> dict:
    """生成不依赖外部扫描器的最小 Kotlin 静态语义范围摘要。"""
    return {
        "languages": ["KOTLIN"],
        "scope_files": ["app/src/main/java/sample/Feature.kt"],
        "tools": [],
        "control_audit_path": str(audit_path),
        "control_audit_sha256": audit_sha256,
        "control_changes": [],
        "finding_ids": [],
    }


def stability_capabilities() -> list[dict]:
    """生成必需静态能力通过、三项动态能力明确不适用的稳定性能力集。"""
    return [{
        "id": "android-static-semantics",
        "required": True,
        "status": "PASS",
    }] + [
        {
            "id": capability_id,
            "required": False,
            "status": "SKIPPED",
            "reason": "需求与最终 diff 均未涉及。",
        }
        for capability_id in (
            "android-dynamic-leak",
            "android-performance",
            "android-security-privacy",
        )
    ]


class SpecialistResultTests(unittest.TestCase):
    """验证自然语言专项报告必须同时满足机器阻断和证据完整性。"""

    def setUp(self) -> None:
        """建立当前交付上下文和一个不含动态扩展的最小 Review PASS。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.artifact = self.root / "diff.txt"
        self.artifact.write_text("diff evidence\n", encoding="utf-8")
        self.context = {
            "requirement_id": "requirement-1",
            "requirement_revision": 1,
            "requirement_file_sha256": "b" * 64,
            "requirement_inputs_sha256": "e" * 64,
            "baseline_id": "baseline-1",
            "snapshot_sha256": "a" * 64,
        }
        self.control_audit = self.root / "static-control-audit.json"
        self._write_control_audit()
        self.payload = {
            "version": SPECIALIST_RESULT_VERSION,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-DIFF",
            "skill": "android-review-diff",
            "provenance": {"skill": "android-review-diff"},
            **self.context,
            "conclusion": "PASS",
            "summary": "范围与需求一致。",
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "unresolved_findings": [],
            "confirmed_impacts": no_confirmed_impacts(),
            "obligation_sha256s": {},
        }

    def _write_control_audit(self, controls: list[dict] | None = None) -> str:
        """写入绑定当前基线和代码摘要的确定性控制面候选。"""
        payload = {
            "version": 1,
            "producer": "android-static-control-audit",
            "project_path": str(self.root),
            "baseline_id": self.context["baseline_id"],
            "snapshot_sha256": self.context["snapshot_sha256"],
            "warnings": [],
            "control_changes": controls or [],
        }
        self.control_audit.write_text(json.dumps(payload), encoding="utf-8")
        return sha256_file(self.control_audit)

    def _passing_static_analysis(self) -> dict:
        """引用当前测试已写入且摘要未变化的控制面审计文件。"""
        return passing_static_analysis(self.control_audit, sha256_file(self.control_audit))

    def test_accepts_current_pass_result(self) -> None:
        """验证普通 Review 只填写公共阻断字段也能形成有效结果。"""
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_ui_pass_requires_ready_physical_device(self) -> None:
        """UI PASS 只保留轻量视觉链接，但必须确认物理设备截图成功。"""
        self.payload["skill"] = UI_VERIFY_SKILL
        self.payload["provenance"] = {"skill": UI_VERIFY_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = [{
            "id": "android-ui-a11y",
            "required": True,
            "status": "PASS",
        }]
        self.payload["visual_review"] = {
            "design_links": ["https://figma.example/file/design?node-id=1-2"],
            "screenshot_links": ["https://evidence.example/ui/login.png"],
            "diff_links": ["https://evidence.example/ui/login-diff.png"],
            "dynamic_notes": "状态栏时间忽略，用户名使用固定测试数据。",
        }
        self.payload["device_check"] = {
            "status": "READY",
            "serial": "R5CT123456",
            "kind": "PHYSICAL",
            "screenshot_ok": True,
        }

        self.assertEqual([], validate_specialist_result(self.payload, self.context))

        self.payload["conclusion"] = "UNVERIFIED"
        self.assertEqual([], validate_specialist_result(self.payload, self.context))
        self.payload["conclusion"] = "PASS"

        self.payload.pop("visual_review")
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("visual_review" in error for error in errors))

    def test_ui_pass_rejects_missing_device_check(self) -> None:
        """UI PASS 不能只凭链接声称完成真机验收。"""
        self.payload["skill"] = UI_VERIFY_SKILL
        self.payload["provenance"] = {"skill": UI_VERIFY_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["visual_review"] = {
            "design_links": ["https://figma.example/file/design"],
            "screenshot_links": ["https://evidence.example/ui/login.png"],
        }
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("device_check" in error for error in errors))

    def test_ui_pass_rejects_emulator_or_failed_screenshot(self) -> None:
        """模拟器和失败截图都不能冒充真机视觉 PASS。"""
        self.payload["skill"] = UI_VERIFY_SKILL
        self.payload["provenance"] = {"skill": UI_VERIFY_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["visual_review"] = {
            "design_links": ["https://figma.example/file/design"],
            "screenshot_links": ["https://evidence.example/ui/login.png"],
        }
        self.payload["device_check"] = {
            "status": "READY",
            "serial": "emulator-5554",
            "kind": "EMULATOR",
            "screenshot_ok": False,
        }
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("PHYSICAL" in error for error in errors))
        self.assertTrue(any("截图成功" in error for error in errors))

    def test_ui_result_rejects_file_artifact_hash_contract(self) -> None:
        """UI 专项不再把本地截图文件 SHA 当作视觉验收前置条件。"""
        self.payload["skill"] = UI_VERIFY_SKILL
        self.payload["provenance"] = {"skill": UI_VERIFY_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["visual_review"] = {
            "design_links": ["https://figma.example/file/design"],
            "screenshot_links": ["https://evidence.example/ui/login.png"],
        }
        self.payload["artifacts"] = [{
            "path": str(self.artifact),
            "sha256": sha256_file(self.artifact),
            "kind": "screenshot",
        }]

        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("不再要求截图或布局文件 SHA-256" in error for error in errors))

    def test_pass_rejects_unclosed_p1(self) -> None:
        """验证自然语言写 PASS 不能覆盖仍未关闭的 P1。"""
        self.payload["findings"]["P1"] = 1
        self.payload["unresolved_findings"] = [{
            "id": "FND-0123456789ABCDEF",
            "severity": "P1",
            "summary": "公共 API 行为不兼容。",
        }]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("存在 P0/P1" in error for error in errors))
        self.assertTrue(any("未关闭 P0/P1" in error for error in errors))

    def test_rejects_legacy_version_three_result(self) -> None:
        """验证新增静态机器门禁后，旧 v3 专项结果不能继续通过。"""
        self.payload["version"] = 3

        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("版本或 producer 无效" in error for error in errors))

    def test_provenance_missing_blocked(self) -> None:
        """验证不声明产出来源的凭空捏造 JSON 被拦截。"""
        self.payload.pop("provenance")
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("provenance" in error for error in errors))

    def test_provenance_unknown_skill_blocked(self) -> None:
        """验证 provenance 声明白名单外的假 Skill 名被拦截。"""
        self.payload["provenance"] = {"skill": "android-super-reviewer"}
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("未知 Skill" in error for error in errors))

    def test_provenance_skill_mismatch_blocked(self) -> None:
        """验证 provenance.skill 与顶层 skill 不一致的张冠李戴被拦截。"""
        self.payload["skill"] = "android-review-code-quality"
        # 故意不改 provenance，保持 review-diff，制造不一致
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("不一致" in error for error in errors))

    def test_diff_review_requires_complete_confirmed_impacts(self) -> None:
        """验证 Diff Reviewer 不能漏写类别、重复类别或用空依据声明适用。"""
        self.payload["confirmed_impacts"] = self.payload["confirmed_impacts"][:-1]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("缺少影响类别" in error for error in errors))

        self.payload["confirmed_impacts"] = no_confirmed_impacts()
        self.payload["confirmed_impacts"][0].update({
            "applicable": True,
            "reason": "发现接口行为变化。",
        })
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("适用时必须提供依据文件" in error for error in errors))

    def test_maps_semantic_impacts_to_conditional_gates(self) -> None:
        """验证框架无关的 AI 语义影响能够映射到现有条件门禁。"""
        impacts = no_confirmed_impacts()
        for item in impacts:
            if item["id"] in {"api", "data", "system", "ui"}:
                item.update({
                    "applicable": True,
                    "basis_files": [f"app/src/main/example/{item['id']}.kt"],
                    "reason": "真实 diff 证明该影响适用。",
                })
        self.payload["confirmed_impacts"] = impacts

        self.assertEqual([], validate_specialist_result(self.payload, self.context))
        self.assertEqual(
            {
                "android-verify-api-contract",
                "android-data-migration",
                "android-ui-a11y",
                "android-security-privacy",
            },
            conditional_gates_from_confirmed_impacts(self.payload),
        )

    def test_code_quality_requires_structured_core_checks(self) -> None:
        """验证代码质量审查不能省略分层、职责、核心注释和可测试性结论。"""
        self.payload["skill"] = "android-review-code-quality"
        self.payload["provenance"] = {"skill": "android-review-code-quality"}
        self.payload.pop("confirmed_impacts")

        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("代码质量专项缺少必需检查" in error for error in errors))

        self.payload["checks"] = passing_code_quality_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_api_contract_pass_requires_machine_contract_fields(self) -> None:
        """验证接口契约专项不能只写自然语言 PASS。"""
        self.payload["skill"] = API_CONTRACT_SKILL
        self.payload["provenance"] = {"skill": API_CONTRACT_SKILL}
        self.payload.pop("confirmed_impacts")

        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("api-contract" in error for error in errors))
        self.assertTrue(any("缺少必需检查" in error for error in errors))
        self.assertTrue(any("artifact" in error for error in errors))

    def test_accepts_api_contract_pass_with_contract_checks_and_artifact(self) -> None:
        """验证有契约来源、operation/schema 和实现映射证据时 API PASS 可通过。"""
        contract = self.root / "api-contract.md"
        contract.write_text("GET /user/list response schema\n", encoding="utf-8")
        self.payload["skill"] = API_CONTRACT_SKILL
        self.payload["provenance"] = {"skill": API_CONTRACT_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = [{
            "id": API_CONTRACT_CAPABILITY_ID,
            "required": True,
            "status": "PASS",
        }]
        self.payload["checks"] = [
            {
                "id": check_id,
                "required": True,
                "status": "PASS",
                "summary": "已核对正式契约、operation/schema 和实现映射。",
            }
            for check_id in sorted(API_CONTRACT_CHECK_IDS)
        ]
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["artifacts"] = [{
            "path": str(contract),
            "sha256": sha256_file(contract),
            "kind": "api-contract",
        }]

        self.assertEqual([], validate_specialist_result(self.payload, self.context))
        self.payload["artifacts"][0]["kind"] = "mock-only"
        mock_errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("mock/fake" in error for error in mock_errors))
        self.payload["artifacts"][0]["kind"] = "api-contract"
        self.payload["checks"][0]["required"] = False
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("required=true" in error for error in errors))

    def test_api_contract_pass_requires_complete_profile_status(self) -> None:
        """正式契约资料仍为 partial 时，结构完整的 API 结果也不能 PASS。"""
        contract = self.root / "api-contract.md"
        contract.write_text("GET /user/list response schema\n", encoding="utf-8")
        self.payload["skill"] = API_CONTRACT_SKILL
        self.payload["provenance"] = {"skill": API_CONTRACT_SKILL}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = [{
            "id": API_CONTRACT_CAPABILITY_ID,
            "required": True,
            "status": "PASS",
        }]
        self.payload["checks"] = [
            {
                "id": check_id,
                "required": True,
                "status": "PASS",
                "summary": "已核对正式契约。",
            }
            for check_id in sorted(API_CONTRACT_CHECK_IDS)
        ]
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["artifacts"] = [{
            "path": str(contract),
            "sha256": sha256_file(contract),
            "kind": "api-contract",
        }]
        partial_context = {**self.context, "api_contract_status": "partial"}

        errors = validate_specialist_result(self.payload, partial_context)

        self.assertTrue(any("api.status=confirmed" in error for error in errors))

    def test_rejects_stale_context_and_changed_artifact(self) -> None:
        """验证代码变化或证据文件被改写后旧专项结果立即失效。"""
        stale_context = copy.deepcopy(self.context)
        stale_context["snapshot_sha256"] = "c" * 64
        self.payload["artifacts"] = [{
            "path": str(self.artifact),
            "sha256": sha256_file(self.artifact),
            "kind": "diff",
        }]
        self.artifact.write_text("changed evidence\n", encoding="utf-8")
        errors = validate_specialist_result(self.payload, stale_context)
        self.assertTrue(any("摘要已变化" in error for error in errors))
        self.assertTrue(any("snapshot_sha256" in error for error in errors))

    def test_rejects_unredacted_specialist_command(self) -> None:
        """验证专项结果不能把 DeepLink 查询参数或敏感值写入机器报告。"""
        self.payload["commands"] = [["adb", "shell", "am", "start", "sample://x?token=secret"]]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("未脱敏" in error for error in errors))

    def test_optional_checks_require_matching_execution_count(self) -> None:
        """验证只有声明逐项检查时才要求执行数量，且数量必须精确匹配。"""
        self.payload["checks"] = [{
            "id": "scope-check",
            "required": True,
            "status": "PASS",
            "summary": "实际 diff 与需求范围一致。",
        }]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("必须填写 executed_checks" in error for error in errors))

        self.payload["executed_checks"] = 1
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_journey_agent_requires_dynamic_extension(self) -> None:
        """验证 Journey Agent 不能只提交普通 Review 的最小信封。"""
        self.payload["skill"] = "android-test-and-fix/journey-agent"
        self.payload["provenance"] = {"skill": "android-test-and-fix/journey-agent"}
        self.payload.pop("confirmed_impacts")
        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("必需 Journey 能力" in error for error in errors))
        self.assertTrue(any("action 检查" in error for error in errors))
        self.assertTrue(any("执行起止时间" in error for error in errors))

    def test_pass_rejects_required_unverified_capability(self) -> None:
        """验证必需动态能力未验证时，专项自然语言结论不能仍写 PASS。"""
        self.payload["capabilities"] = [{
            "id": "dynamic-leak",
            "required": True,
            "status": "UNVERIFIED",
            "reason": "当前没有设备和 Leak Trace。",
        }]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("必需能力 dynamic-leak" in error for error in errors))

    def test_stability_requires_all_capability_decisions(self) -> None:
        """验证稳定性 PASS 必须记录静态语义和三项条件能力，并逐项执行固定检查。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload["provenance"] = {"skill": "android-audit-stability"}
        self.payload.pop("confirmed_impacts")
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("稳定性专项缺少能力适用性结论" in error for error in errors))
        self.assertTrue(any("稳定性专项缺少静态语义检查" in error for error in errors))

        self.payload["capabilities"] = stability_capabilities()
        self.payload["checks"] = passing_stability_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["static_analysis"] = self._passing_static_analysis()
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_stability_rejects_blocking_static_control_change(self) -> None:
        """验证新增抑制或排除尚未解释完成时，稳定性摘要不能写成通过。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload["provenance"] = {"skill": "android-audit-stability"}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = stability_capabilities()
        self.payload["checks"] = passing_stability_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["static_analysis"] = self._passing_static_analysis()
        audit_candidate = {
            "id": "CTL-0123456789ABCDEF",
            "path": "config/detekt/detekt.yml",
            "kind": "EXCLUSION",
            "summary": "静态检查排除发生变化，需要确认没有缩小范围。",
        }
        self.payload["static_analysis"]["control_audit_sha256"] = self._write_control_audit(
            [audit_candidate]
        )
        self.payload["static_analysis"]["control_changes"] = [{
            "id": "CTL-0123456789ABCDEF",
            "path": "config/detekt/detekt.yml",
            "kind": "EXCLUSION",
            "decision": "BLOCKING",
            "reason": "尚未确认为什么排除本次修改目录。",
        }]

        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("仍阻断时不能标记 PASS" in error for error in errors))

    def test_stability_rejects_omitted_or_stale_control_audit_candidates(self) -> None:
        """验证模型不能漏写候选，也不能复用其他代码摘要上的审计结果。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload["provenance"] = {"skill": "android-audit-stability"}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = stability_capabilities()
        self.payload["checks"] = passing_stability_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        candidate = {
            "id": "CTL-0123456789ABCDEF",
            "path": "config/detekt/detekt.yml",
            "kind": "CONFIG",
            "summary": "静态工具配置发生变化。",
        }
        audit_sha = self._write_control_audit([candidate])
        self.payload["static_analysis"] = passing_static_analysis(self.control_audit, audit_sha)

        omitted = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("审计候选不一致" in error for error in omitted))

        audit_payload = json.loads(self.control_audit.read_text(encoding="utf-8"))
        audit_payload["snapshot_sha256"] = "c" * 64
        self.control_audit.write_text(json.dumps(audit_payload), encoding="utf-8")
        self.payload["static_analysis"]["control_audit_sha256"] = sha256_file(self.control_audit)
        stale = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("不是基于当前代码摘要" in error for error in stale))

    def test_stability_tool_coverage_requires_unchanged_evidence(self) -> None:
        """验证声明工具通过时必须绑定版本、模式、真实范围和未变化的证据文件。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload["provenance"] = {"skill": "android-audit-stability"}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = stability_capabilities()
        self.payload["checks"] = passing_stability_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["static_analysis"] = self._passing_static_analysis()
        self.payload["static_analysis"]["tools"] = [{
            "id": "detekt",
            "status": "PASS",
            "version": "2.0.0",
            "mode": "TYPE_RESOLVED",
            "scope": [":app/main"],
            "cross_file": False,
            "evidence_path": str(self.artifact),
            "evidence_sha256": sha256_file(self.artifact),
        }]

        self.assertEqual([], validate_specialist_result(self.payload, self.context))
        self.artifact.write_text("changed static evidence\n", encoding="utf-8")
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("证据文件摘要已变化" in error for error in errors))

    def test_unresolved_finding_requires_stable_id(self) -> None:
        """验证换模型或需求修订后，未关闭问题不能继续使用临时顺序编号。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload["provenance"] = {"skill": "android-audit-stability"}
        self.payload.pop("confirmed_impacts")
        self.payload["capabilities"] = stability_capabilities()
        self.payload["checks"] = passing_stability_checks()
        self.payload["executed_checks"] = len(self.payload["checks"])
        self.payload["static_analysis"] = self._passing_static_analysis()
        self.payload["findings"]["P2"] = 1
        self.payload["unresolved_findings"] = [{
            "id": "F-1",
            "severity": "P2",
            "summary": "清理路径无法确认。",
        }]

        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("稳定问题编号" in error for error in errors))

    def test_path_command_uses_current_requirement_scope(self) -> None:
        """验证专项结果目录按当前需求、修订和代码摘要隔离。"""
        import yaml as _yaml
        output = io.StringIO()
        requirement_dir = self.root / "req"
        requirement_dir.mkdir()
        config_path = self.root / "local.yaml"
        config_path.write_text(
            _yaml.safe_dump({"project_path": str(self.root), "requirement_dir": str(requirement_dir)}),
            encoding="utf-8",
        )
        with (
            patch_module_global(delivery_module, "load_config", return_value={}),
            patch_module_global(delivery_gate_module, "current_context", return_value=self.context),
            redirect_stdout(output),
        ):
            exit_code = main(["path", "--config", str(config_path)])

        path = Path(output.getvalue().strip())
        self.assertEqual(0, exit_code)
        self.assertEqual("specialists", path.name)
        self.assertIn("-r1-", path.parent.name)

    def test_unknown_extension_field_is_rejected(self) -> None:
        """专项结果只接受统一协议字段，未知扩展不能绕过结构校验。"""
        payload = dict(self.payload)
        payload["legacy_extension"] = {}

        errors = validate_specialist_result(payload, self.context)

        self.assertTrue(any("未知字段" in error and "legacy_extension" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
