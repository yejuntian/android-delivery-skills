#!/usr/bin/env python3
"""脚本名称：test_user_facing_labels.py

用途：验证 Android Delivery 全流程用户出口统一使用自然中文，同时保持机器协议不变。

覆盖范围：需求变化、确认状态、交付结论、验收覆盖、专项状态、失败分类、风险、
Journey 状态、终端需求指令和最终中文摘要。测试不读取真实配置、不修改项目、不访问网络。
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..delivery import print_bdd_instruction  # noqa: E402
from ..delivery_gate import (  # noqa: E402
    CONCLUSIONS,
    GATE_STATUSES,
    OBLIGATION_STATUSES,
    render_delivery_summary,
)
from ..requirement_snapshot import (  # noqa: E402
    CHANGE_TYPES,
    DECISIONS,
    REMOVAL_DISPOSITIONS,
)
from ..specialist_result import (  # noqa: E402
    CAPABILITY_STATUSES,
    SEVERITIES,
    SPECIALIST_CONCLUSIONS,
)
from ..user_facing_labels import (  # noqa: E402
    CHANGE_TYPE_LABELS,
    ChineseArgumentParser,
    DECISION_LABELS,
    DELIVERY_CONCLUSION_LABELS,
    FAILURE_CLASS_LABELS,
    GATE_STATUS_LABELS,
    JOURNEY_APPLICABILITY_LABELS,
    JOURNEY_STATUS_LABELS,
    OBLIGATION_STATUS_LABELS,
    REMOVAL_DISPOSITION_LABELS,
    RISK_LEVEL_LABELS,
    SEVERITY_LABELS,
    SNAPSHOT_STATUS_LABELS,
    WORKFLOW_STATE_LABELS,
    gate_label,
    localize_machine_terms,
    user_label,
)


class UserFacingLabelsTests(unittest.TestCase):
    """验证每类稳定机器状态都能转换，并且未知值不会直接暴露。"""

    def test_core_machine_domains_have_chinese_labels(self) -> None:
        """验证需求、交付、专项和风险协议新增枚举时必须同步中文映射。"""
        self.assertLessEqual(CHANGE_TYPES, set(CHANGE_TYPE_LABELS))
        self.assertLessEqual(DECISIONS, set(DECISION_LABELS))
        self.assertLessEqual(REMOVAL_DISPOSITIONS, set(REMOVAL_DISPOSITION_LABELS))
        self.assertLessEqual(CONCLUSIONS, set(DELIVERY_CONCLUSION_LABELS))
        self.assertLessEqual(OBLIGATION_STATUSES, set(OBLIGATION_STATUS_LABELS))
        self.assertLessEqual(GATE_STATUSES, set(GATE_STATUS_LABELS))
        self.assertLessEqual(SPECIALIST_CONCLUSIONS, set(GATE_STATUS_LABELS))
        self.assertLessEqual(CAPABILITY_STATUSES, set(GATE_STATUS_LABELS))
        self.assertLessEqual(SEVERITIES, set(SEVERITY_LABELS))
        self.assertTrue({"AWAITING_OBLIGATIONS", "PENDING_CONFIRMATION", "CONFIRMED"}
                        <= set(SNAPSHOT_STATUS_LABELS))
        self.assertTrue({"USER_INPUT_REQUIRED", "BLOCKED"} <= set(WORKFLOW_STATE_LABELS))
        self.assertTrue({"REQUIREMENT_BLOCKED", "ENVIRONMENT_FAILED", "TEST_FAILED",
                         "IMPLEMENTATION_FAILED", "UNKNOWN"} <= set(FAILURE_CLASS_LABELS))
        self.assertTrue({"FULL", "PARTIAL", "NONE"} <= set(JOURNEY_APPLICABILITY_LABELS))
        self.assertTrue({"L1", "L2", "L3", "BLOCKED"} <= set(RISK_LEVEL_LABELS))
        self.assertTrue({"PASS", "APP_ASSERTION_FAILED", "HARNESS_FAILED",
                         "NO_JOURNEY_FOUND", "INITIALIZATION_REQUIRED"}
                        <= set(JOURNEY_STATUS_LABELS))

    def test_machine_terms_are_localized_without_changing_technical_identifiers(self) -> None:
        """验证状态转中文，但接口路径、类名和稳定验收编号保持原文。"""
        source = (
            "USER_INPUT_REQUIRED / BLOCKED / FULL_PASS / UNVERIFIED / "
            "APP_ASSERTION_FAILED / L2；POST /jgp/videoPageV2；VideoViewModel；BDD-001/T1"
        )

        result = localize_machine_terms(source)

        for machine_term in (
            "USER_INPUT_REQUIRED", "BLOCKED", "FULL_PASS", "UNVERIFIED",
            "APP_ASSERTION_FAILED", "L2",
        ):
            self.assertNotIn(machine_term, result)
        self.assertIn("需要你补充信息或完成操作", result)
        self.assertIn("POST /jgp/videoPageV2", result)
        self.assertIn("VideoViewModel", result)
        self.assertIn("BDD-001/T1", result)

    def test_command_help_uses_chinese_headings(self) -> None:
        """验证 Python 默认帮助标题不会再次以英文显示给用户。"""
        parser = ChineseArgumentParser(description="测试命令")
        parser.add_argument("input_file", help="输入文件")

        help_text = parser.format_help()

        self.assertIn("用法:", help_text)
        self.assertIn("位置参数:", help_text)
        self.assertIn("可选参数:", help_text)
        self.assertIn("显示帮助并退出", help_text)
        for english_heading in (
            "usage:", "positional arguments:", "optional arguments:",
            "show this help message and exit",
        ):
            self.assertNotIn(english_heading, help_text)

    def test_unknown_status_and_gate_do_not_leak_machine_values(self) -> None:
        """验证未来新增状态未配置映射时显示中文兜底而不是原始值。"""
        status = user_label("FUTURE_MACHINE_STATUS", {})
        gate = gate_label("future-machine-gate")

        self.assertNotIn("FUTURE_MACHINE_STATUS", status)
        self.assertEqual("其他交付检查", gate)

    def test_requirement_instruction_uses_chinese_scenario_terms(self) -> None:
        """验证需求阶段向用户显示前提、操作和预期结果，不泄漏英文流程词。"""
        output = io.StringIO()

        with redirect_stdout(output):
            print_bdd_instruction()

        text = output.getvalue()
        self.assertIn("前提 / 操作 / 预期结果", text)
        self.assertIn("原子验收项", text)
        for machine_term in ("Given", "When", "Then", "BLOCKED", "Red", "Green"):
            self.assertNotIn(machine_term, text)

    def test_final_summary_localizes_statuses_embedded_in_reasons(self) -> None:
        """验证最终摘要连同原因和待办一起中文化，机器报告仍可保留原枚举。"""
        payload = {
            "conclusion": "INCOMPLETE",
            "requirement_revision": 3,
            "obligations": [{
                "id": "BDD-001/T1",
                "status": "UNVERIFIED",
                "reason": "USER_INPUT_REQUIRED：等待设备",
            }],
            "gates": [{
                "id": "android-ui-a11y",
                "status": "SKIPPED",
                "reason": "UNVERIFIED",
            }],
            "pending_capabilities": [{
                "id": "android-ui-a11y",
                "reason": "BLOCKED",
            }],
        }
        context = {
            "expected_obligations": {
                "BDD-001/T1": {"text": "按钮可以被辅助技术识别"},
            },
        }

        summary = render_delivery_summary(payload, context)

        self.assertIn("当前需求尚未完成", summary)
        self.assertIn("需要你补充信息或完成操作", summary)
        self.assertIn("当前条件不足，暂时无法继续", summary)
        for machine_term in ("INCOMPLETE", "UNVERIFIED", "SKIPPED", "BLOCKED"):
            self.assertNotIn(machine_term, summary)

    def test_final_summary_prioritizes_existing_business_changes(self) -> None:
        """验证旧业务修改和保护项在最终中文报告顶部按用户语义分组。"""
        payload = {
            "conclusion": "FULL_PASS",
            "requirement_revision": 2,
            "obligations": [
                {"id": "BDD-001/T1", "status": "COVERED_AUTOMATED"},
                {"id": "BDD-002/T1", "status": "COVERED_MANUAL"},
            ],
            "gates": [],
            "pending_capabilities": [],
        }
        context = {
            "expected_obligations": {
                "BDD-001/T1": {
                    "text": "【修改已上线业务】普通购物车：免运费门槛由 100 元调整为 80 元",
                },
                "BDD-002/T1": {
                    "text": "【保护已上线业务】赠品订单：零金额仍然允许提交",
                },
            },
        }

        summary = render_delivery_summary(payload, context)

        business_section = summary.index("## 已上线业务变更与保护")
        conclusion_section = summary.index("## 最终结论")
        self.assertLess(business_section, conclusion_section)
        self.assertIn("### 本次明确修改", summary)
        self.assertIn("### 必须保持不变", summary)
        self.assertIn("普通购物车：免运费门槛由 100 元调整为 80 元", summary)
        self.assertIn("赠品订单：零金额仍然允许提交", summary)
        self.assertIn("已登记旧业务保护项：1 项；已验证 1 项", summary)
        self.assertNotIn("【修改已上线业务】", summary)
        self.assertNotIn("【保护已上线业务】", summary)


if __name__ == "__main__":
    unittest.main()
