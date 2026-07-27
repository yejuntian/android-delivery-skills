#!/usr/bin/env python3
"""脚本名称：test_impact_radius.py

用途：验证需求增量影响半径能绑定当前修订，并阻断范围外 diff。

覆盖范围：当前修订摘要绑定、本轮语义变化覆盖、allowed 文件匹配和越界文件识别。
测试只使用内存夹具，不读取真实 Android 项目。
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..impact_radius import changed_files_outside_radius, validate_impact_radius  # noqa: E402
from ..requirement_snapshot import (  # noqa: E402
    obligation_digest,
    requirement_digest,
    requirement_summary_digest,
)


def snapshot() -> dict:
    """生成 R2 中只修改一个原子义务的需求快照。"""
    text = "登录失败显示新的错误提示"
    return {
        "requirement_id": "requirement-1",
        "revision": 2,
        "obligations": [{
            "id": "BDD-001/T1",
            "text": text,
            "required": True,
            "sha256": obligation_digest("BDD-001/T1", text, True),
        }],
        "history": [{
            "revision": 2,
            "changes": [{
                "id": "BDD-001/T1",
                "change_type": "CHANGED",
                "decision": "CONFIRMED",
                "text": text,
                "required": True,
            }],
        }],
    }


def payload(snapshot_payload: dict, requirement: str) -> dict:
    """生成与快照匹配的影响半径。"""
    return {
        "version": 1,
        "generated_at": "2026-07-27T00:00:00+00:00",
        "requirement_id": snapshot_payload["requirement_id"],
        "requirement_revision": snapshot_payload["revision"],
        "requirement_file_sha256": requirement_digest(requirement),
        "requirement_summary_sha256": requirement_summary_digest(snapshot_payload),
        "allowed_files": ["app/src/main/java/LoginViewModel.kt"],
        "allowed_globs": ["app/src/test/java/**"],
        "impacts": [{
            "id": "BDD-001/T1",
            "change_type": "CHANGED",
            "reason": "只调整登录失败提示和对应测试。",
            "risk_level": "L1",
            "expected_files": [
                "app/src/main/java/LoginViewModel.kt",
                "app/src/test/java/LoginViewModelTest.kt",
            ],
            "expected_tests": ["LoginViewModelTest#failureMessage"],
            "affected_modules": [":app"],
        }],
    }


class ImpactRadiusTests(unittest.TestCase):
    """验证影响半径机器协议。"""

    def test_valid_radius_passes_and_allows_matching_files(self) -> None:
        """验证合法影响半径通过，且 glob 覆盖测试文件。"""
        requirement = "登录失败显示新的错误提示"
        snap = snapshot()
        radius = payload(snap, requirement)

        self.assertEqual([], validate_impact_radius(radius, snap, requirement))
        self.assertEqual(
            [],
            changed_files_outside_radius([
                "app/src/main/java/LoginViewModel.kt",
                "app/src/test/java/LoginViewModelTest.kt",
            ], radius),
        )

    def test_missing_changed_obligation_is_rejected(self) -> None:
        """验证本轮变更义务没有进入 impacts 时阻断确认。"""
        requirement = "登录失败显示新的错误提示"
        snap = snapshot()
        radius = payload(snap, requirement)
        radius["impacts"] = []

        errors = validate_impact_radius(radius, snap, requirement)

        self.assertTrue(any("impacts 必须是非空数组" in error for error in errors))

    def test_outside_file_is_reported(self) -> None:
        """验证最终 diff 触达非影响半径文件时可被门禁识别。"""
        requirement = "登录失败显示新的错误提示"
        snap = snapshot()
        radius = payload(snap, requirement)

        outside = changed_files_outside_radius([
            "app/src/main/java/LoginViewModel.kt",
            "app/src/main/java/PaymentRepository.kt",
        ], radius)

        self.assertEqual(["app/src/main/java/PaymentRepository.kt"], outside)


if __name__ == "__main__":
    unittest.main()
