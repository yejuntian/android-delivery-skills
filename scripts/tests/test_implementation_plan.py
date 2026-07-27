#!/usr/bin/env python3
"""脚本名称：test_implementation_plan.py

用途：验证实施计划确认只对当前需求和当前计划有效。

覆盖范围：必需章节、正式需求修订、幂等确认、0600 收据、需求变化和计划变化。
测试仅使用临时目录，不读取真实需求或 Android 项目。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

from ..impact_radius import impact_radius_path
from ..implementation_plan import (
    ImplementationPlanError,
    confirm_implementation_plan,
    implementation_plan_path,
    plan_confirmation_receipt_path,
    validate_plan_confirmation,
)
from ..requirement_snapshot import obligation_digest, requirement_digest, requirement_summary_digest


def valid_plan(extra: str = "") -> str:
    """生成包含用户必须审阅的五类边界的最小计划。"""
    return f"""# 实施计划

## 实现范围
- 修改登录错误提示。{extra}

## 已上线业务影响
- 保持成功登录不变。

## 预计修改文件
- `LoginViewModel.kt`

## 测试方案
- 增加失败分支单元测试。

## 明确不修改范围
- 不修改登录接口契约。
"""


def confirmed_snapshot(requirement: str) -> dict:
    """生成已经形成 R1 且带有效原子义务的需求快照。"""
    text = "登录失败时显示错误"
    return {
        "requirement_id": "requirement-1",
        "revision": 1,
        "status": "CONFIRMED",
        "pending_changes": [],
        "sha256": requirement_digest(requirement),
        "obligations": [{
            "id": "BDD-001/T1",
            "text": text,
            "required": True,
            "sha256": obligation_digest("BDD-001/T1", text, True),
        }],
        "history": [{
            "revision": 1,
            "changes": [{
                "id": "BDD-001/T1",
                "change_type": "ADDED",
                "decision": "CONFIRMED",
                "text": text,
                "required": True,
            }],
        }],
    }


def write_valid_impact_radius(root: Path, snapshot: dict, requirement: str) -> None:
    """生成与当前需求修订一致的最小影响半径。"""
    target = impact_radius_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({
            "version": 1,
            "generated_at": "2026-07-27T00:00:00+00:00",
            "requirement_id": snapshot["requirement_id"],
            "requirement_revision": snapshot["revision"],
            "requirement_file_sha256": requirement_digest(requirement),
            "requirement_summary_sha256": requirement_summary_digest(snapshot),
            "allowed_files": [
                "app/src/main/java/LoginViewModel.kt",
                "app/src/test/java/LoginViewModelTest.kt",
            ],
            "allowed_globs": [],
            "impacts": [{
                "id": "BDD-001/T1",
                "change_type": "ADDED",
                "reason": "登录失败提示只影响 ViewModel 和对应单测。",
                "risk_level": "L1",
                "expected_files": [
                    "app/src/main/java/LoginViewModel.kt",
                    "app/src/test/java/LoginViewModelTest.kt",
                ],
                "expected_tests": ["LoginViewModelTest#failureMessage"],
                "affected_modules": [":app"],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


class ImplementationPlanTests(unittest.TestCase):
    """验证计划确认收据不成为可以跨需求复用的形式化文件。"""

    def setUp(self) -> None:
        """创建每个用例独享的需求工作区和有效实施计划。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.requirement = "登录失败时显示错误"
        self.snapshot = confirmed_snapshot(self.requirement)
        implementation_plan_path(self.root).write_text(valid_plan(), encoding="utf-8")
        write_valid_impact_radius(self.root, self.snapshot, self.requirement)

    def test_confirmation_is_idempotent_and_validates_current_context(self) -> None:
        """验证重复确认不改时间，且收据绑定需求摘要与计划摘要。"""
        first, receipt_path = confirm_implementation_plan(
            self.snapshot, self.requirement, self.root,
        )
        second, second_path = confirm_implementation_plan(
            self.snapshot, self.requirement, self.root,
        )
        context = validate_plan_confirmation(self.snapshot, self.requirement, self.root)

        self.assertEqual(first, second)
        self.assertEqual(receipt_path, second_path)
        self.assertEqual(0o600, stat.S_IMODE(receipt_path.stat().st_mode))
        self.assertEqual(64, len(first["requirement_summary_sha256"]))
        self.assertEqual(64, len(first["impact_radius_sha256"]))
        self.assertEqual(first["implementation_plan_sha256"], context["implementation_plan_sha256"])
        self.assertEqual(first["impact_radius_sha256"], context["impact_radius_sha256"])
        self.assertEqual(
            hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            context["plan_confirmation_receipt_sha256"],
        )

    def test_missing_or_empty_required_section_is_rejected(self) -> None:
        """验证计划不能只给标题，也不能漏掉用户要求查看的范围。"""
        implementation_plan_path(self.root).write_text(
            valid_plan().replace("## 测试方案\n- 增加失败分支单元测试。\n\n", ""),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ImplementationPlanError, "测试方案"):
            confirm_implementation_plan(self.snapshot, self.requirement, self.root)

        implementation_plan_path(self.root).write_text(
            valid_plan().replace("## 明确不修改范围\n- 不修改登录接口契约。", "## 明确不修改范围"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ImplementationPlanError, "内容为空"):
            confirm_implementation_plan(self.snapshot, self.requirement, self.root)

    def test_requirement_or_plan_change_invalidates_old_confirmation(self) -> None:
        """验证需求和计划任一变化后都必须重新展示并获得用户确认。"""
        confirm_implementation_plan(self.snapshot, self.requirement, self.root)

        changed_requirement = self.requirement + "，允许重试"
        changed_snapshot = confirmed_snapshot(changed_requirement)
        changed_snapshot["revision"] = 2
        with self.assertRaisesRegex(ImplementationPlanError, "旧计划确认失效|影响半径"):
            validate_plan_confirmation(changed_snapshot, changed_requirement, self.root)

        implementation_plan_path(self.root).write_text(
            valid_plan("并记录重试入口。"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ImplementationPlanError, "旧计划确认失效"):
            validate_plan_confirmation(self.snapshot, self.requirement, self.root)

    def test_impact_radius_change_invalidates_old_confirmation(self) -> None:
        """验证影响半径变化后也必须重新确认计划。"""
        confirm_implementation_plan(self.snapshot, self.requirement, self.root)
        target = impact_radius_path(self.root)
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["allowed_files"].append("app/src/main/java/Unexpected.kt")
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(ImplementationPlanError, "旧计划确认失效"):
            validate_plan_confirmation(self.snapshot, self.requirement, self.root)

    def test_unconfirmed_requirement_cannot_confirm_plan(self) -> None:
        """验证待确认需求不能通过先确认计划绕过需求门禁。"""
        self.snapshot["status"] = "PENDING_CONFIRMATION"
        with self.assertRaisesRegex(ImplementationPlanError, "需求修订尚未全部确认"):
            confirm_implementation_plan(self.snapshot, self.requirement, self.root)

    def test_validation_requires_receipt_after_plan_is_written(self) -> None:
        """验证仅生成 Markdown 不等于用户已经确认计划。"""
        self.assertFalse(plan_confirmation_receipt_path(self.root).exists())
        with self.assertRaisesRegex(ImplementationPlanError, "实施计划尚未确认"):
            validate_plan_confirmation(self.snapshot, self.requirement, self.root)


if __name__ == "__main__":
    unittest.main()
