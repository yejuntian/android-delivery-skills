#!/usr/bin/env python3
"""Tests for the canonical scenario-level BDD requirement format."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..bdd_scenarios import (  # noqa: E402
    BddScenarioError,
    extract_bdd_scenarios,
    validate_requirement_readiness,
)


def requirement(*scenarios: str, pending: str = "- 无") -> str:
    return "\n\n".join(("# 登录需求", "## BDD 场景", *scenarios, "## 待确认", pending))


class BddScenarioTests(unittest.TestCase):
    def test_accepts_complete_scenario(self) -> None:
        content = requirement(
            "### BDD-001 密码错误\nGiven 用户位于登录页\nWhen 用户提交错误密码\n"
            "Then 页面显示错误提示"
        )

        scenarios = validate_requirement_readiness(content)

        self.assertEqual(["BDD-001"], [item["id"] for item in scenarios])
        self.assertEqual([], scenarios[0]["atoms"])

    def test_generates_atoms_from_structured_then(self) -> None:
        content = requirement(
            "### BDD-001 分类请求失败\nGiven 用户位于分类页\nWhen 分类请求失败\n"
            "Then:\n"
            "- visible_state: 显示失败状态\n"
            "- retry_action: Retry 可点击\n"
            "- content_state: 保留已有列表"
        )

        scenario = extract_bdd_scenarios(content)[0]

        self.assertEqual(
            ["BDD-001.visible_state", "BDD-001.retry_action", "BDD-001.content_state"],
            [item["id"] for item in scenario["atoms"]],
        )

    def test_rejects_compound_free_text_then(self) -> None:
        content = requirement(
            "### BDD-001 分类请求失败\nGiven 用户位于分类页\nWhen 分类请求失败\n"
            "Then 显示失败状态并允许点击 Retry"
        )

        with self.assertRaisesRegex(BddScenarioError, "结构化"):
            extract_bdd_scenarios(content)

    def test_rejects_malformed_structured_then(self) -> None:
        content = requirement(
            "### BDD-001 分类请求失败\nGiven 用户位于分类页\nWhen 分类请求失败\n"
            "Then:\n- 显示失败状态"
        )

        with self.assertRaisesRegex(BddScenarioError, "key: value"):
            extract_bdd_scenarios(content)

    def test_rejects_and_as_hidden_second_result(self) -> None:
        content = requirement(
            "### BDD-001 分类请求失败\nGiven 用户位于分类页\nWhen 分类请求失败\n"
            "Then 显示失败状态\nAnd Retry 可点击"
        )

        with self.assertRaisesRegex(BddScenarioError, "And"):
            extract_bdd_scenarios(content)

    def test_rejects_unstructured_continuation_after_then(self) -> None:
        content = requirement(
            "### BDD-001 分类请求失败\nGiven 用户位于分类页\nWhen 分类请求失败\n"
            "Then 显示失败状态\n- Retry 可点击"
        )

        with self.assertRaisesRegex(BddScenarioError, "未结构化"):
            extract_bdd_scenarios(content)

    def test_extracts_multiple_scenarios(self) -> None:
        content = requirement(
            "### BDD-001 密码错误\nGiven 用户位于登录页\nWhen 用户提交错误密码\n"
            "Then 页面显示错误提示",
            "### BDD-002 登录成功\nGiven 用户位于登录页\nWhen 用户提交有效凭据\n"
            "Then 页面进入首页",
        )

        scenarios = extract_bdd_scenarios(content)

        self.assertEqual(["BDD-001", "BDD-002"], [item["id"] for item in scenarios])

    def test_rejects_duplicate_identifier(self) -> None:
        content = requirement(
            "### BDD-001 场景一\nGiven 前置\nWhen 操作\nThen 结果",
            "### BDD-001 场景二\nGiven 前置\nWhen 操作\nThen 结果",
        )

        with self.assertRaisesRegex(BddScenarioError, "重复"):
            extract_bdd_scenarios(content)

    def test_rejects_missing_required_step(self) -> None:
        content = requirement("### BDD-001 密码错误\nGiven 用户位于登录页\nThen 页面显示错误提示")

        with self.assertRaisesRegex(BddScenarioError, "When"):
            extract_bdd_scenarios(content)

    def test_rejects_legacy_then_identifier(self) -> None:
        content = requirement(
            "### BDD-001/T1 密码错误\nGiven 用户位于登录页\nWhen 用户提交错误密码\n"
            "Then 页面显示错误提示"
        )

        with self.assertRaisesRegex(BddScenarioError, "旧的"):
            extract_bdd_scenarios(content)

    def test_requires_explicit_empty_pending_section(self) -> None:
        scenario = "### BDD-001 密码错误\nGiven 前置\nWhen 操作\nThen 结果"
        with self.assertRaisesRegex(BddScenarioError, "缺少"):
            validate_requirement_readiness("# 需求\n\n" + scenario)
        with self.assertRaisesRegex(BddScenarioError, "仍有待确认"):
            validate_requirement_readiness(requirement(scenario, pending="- 错误码待确认"))

    def test_final_scenario_excludes_later_requirement_sections(self) -> None:
        content = requirement(
            "### BDD-001 密码错误\nGiven 用户位于登录页\nWhen 用户提交错误密码\n"
            "Then 页面显示错误提示\n\n## 边界条件\n\n- 网络断开时保留输入"
        )

        scenario = extract_bdd_scenarios(content)[0]

        self.assertNotIn("边界条件", scenario["text"])
        self.assertNotIn("网络断开", scenario["text"])


if __name__ == "__main__":
    unittest.main()
