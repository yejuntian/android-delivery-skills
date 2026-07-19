#!/usr/bin/env python3
"""脚本名称：test_specialist_result.py

用途：验证最小专项结果能够阻断 P0/P1、过期代码和被修改的可选证据文件。

覆盖范围：普通 Review 最小信封、按需能力/命令/artifact、上下文绑定。测试只使用
临时文件，不调用真实 Skill、Android 项目、设备或网络。
"""

from __future__ import annotations

import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..execution_evidence import sha256_file  # noqa: E402
from ..specialist_result import (  # noqa: E402
    IMPACT_CATEGORIES,
    SPECIALIST_PRODUCER,
    SPECIALIST_RESULT_VERSION,
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
        self.payload = {
            "version": SPECIALIST_RESULT_VERSION,
            "producer": SPECIALIST_PRODUCER,
            "id": "E-DIFF",
            "skill": "android-review-diff",
            **self.context,
            "conclusion": "PASS",
            "summary": "范围与需求一致。",
            "findings": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            "unresolved_findings": [],
            "confirmed_impacts": no_confirmed_impacts(),
            "obligation_sha256s": {},
        }

    def test_accepts_current_pass_result(self) -> None:
        """验证普通 Review 只填写公共阻断字段也能形成有效结果。"""
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_pass_rejects_unclosed_p1(self) -> None:
        """验证自然语言写 PASS 不能覆盖仍未关闭的 P1。"""
        self.payload["findings"]["P1"] = 1
        self.payload["unresolved_findings"] = [{
            "id": "F-1",
            "severity": "P1",
            "summary": "公共 API 行为不兼容。",
        }]
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("存在 P0/P1" in error for error in errors))
        self.assertTrue(any("未关闭 P0/P1" in error for error in errors))

    def test_rejects_legacy_version_two_result(self) -> None:
        """验证新增语义影响契约后，旧 v2 专项结果不能继续通过。"""
        self.payload["version"] = 2

        errors = validate_specialist_result(self.payload, self.context)

        self.assertTrue(any("版本或 producer 无效" in error for error in errors))

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
        """验证稳定性 PASS 必须记录泄漏、性能和安全隐私适用性。"""
        self.payload["skill"] = "android-audit-stability"
        self.payload.pop("confirmed_impacts")
        errors = validate_specialist_result(self.payload, self.context)
        self.assertTrue(any("稳定性专项缺少能力适用性结论" in error for error in errors))

        self.payload["capabilities"] = [
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
        self.assertEqual([], validate_specialist_result(self.payload, self.context))

    def test_path_command_uses_current_requirement_scope(self) -> None:
        """验证专项结果目录按当前需求、修订和代码摘要隔离。"""
        output = io.StringIO()
        config_path = self.root / "local.yaml"
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery_gate.current_context", return_value=self.context),
            mock.patch.dict("os.environ", {"XDG_STATE_HOME": str(self.root / "state")}),
            redirect_stdout(output),
        ):
            exit_code = main(["path", "--config", str(config_path)])

        path = Path(output.getvalue().strip())
        self.assertEqual(0, exit_code)
        self.assertEqual("specialists", path.name)
        self.assertIn("-r1-", path.parent.name)


if __name__ == "__main__":
    unittest.main()
