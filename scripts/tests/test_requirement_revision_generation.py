#!/usr/bin/env python3
"""Tests for machine-generated routine requirement revisions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..requirement_snapshot import (  # noqa: E402
    RequirementSnapshotError,
    apply_requirement_revision,
    build_confirmed_revision_manifest,
    write_requirement_snapshot,
)


def requirement(result: str, *, constraint: str = "- 不修改登录接口") -> str:
    return (
        "# 登录错误提示\n\n"
        "## BDD 场景\n\n"
        "### BDD-001 密码错误\n"
        "Given 用户位于登录页\n"
        "When 用户提交错误密码\n"
        f"Then {result}\n\n"
        "## 不修改范围\n\n"
        f"{constraint}\n\n"
        "## 待确认\n\n"
        "- 无\n"
    )


class RequirementRevisionGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.requirement_path = root / "需求说明.md"
        self.snapshot_path = root / "requirement-snapshot.json"

    def _snapshot(self, content: str):
        self.requirement_path.write_text(content, encoding="utf-8")
        return write_requirement_snapshot(
            self.snapshot_path,
            self.requirement_path,
            content,
            requirement_id="requirement-1",
        )

    def test_builds_initial_added_scenario(self) -> None:
        content = requirement("页面显示错误提示")
        snapshot = self._snapshot(content)

        manifest = build_confirmed_revision_manifest(snapshot, content)

        self.assertFalse(manifest["document_changed"])
        self.assertEqual("ADDED", manifest["changes"][0]["change_type"])
        self.assertEqual("BDD-001", manifest["changes"][0]["id"])

    def test_marks_changed_and_unchanged_scenarios(self) -> None:
        original = requirement("页面显示错误提示")
        snapshot = self._snapshot(original)
        snapshot, _ = apply_requirement_revision(
            self.snapshot_path,
            self.requirement_path,
            original,
            build_confirmed_revision_manifest(snapshot, original),
        )

        unchanged = build_confirmed_revision_manifest(snapshot, original)
        changed = build_confirmed_revision_manifest(
            snapshot,
            requirement("页面显示错误提示并保留账号输入"),
        )

        self.assertEqual("UNCHANGED", unchanged["changes"][0]["change_type"])
        self.assertEqual("CHANGED", changed["changes"][0]["change_type"])
        self.assertFalse(changed["document_changed"])

    def test_marks_non_bdd_requirement_change(self) -> None:
        original = requirement("页面显示错误提示")
        snapshot = self._snapshot(original)
        snapshot, _ = apply_requirement_revision(
            self.snapshot_path,
            self.requirement_path,
            original,
            build_confirmed_revision_manifest(snapshot, original),
        )

        manifest = build_confirmed_revision_manifest(
            snapshot,
            requirement("页面显示错误提示", constraint="- 不修改登录接口和 DTO"),
        )

        self.assertTrue(manifest["document_changed"])
        self.assertEqual("UNCHANGED", manifest["changes"][0]["change_type"])

    def test_requires_explicit_manifest_for_deletion(self) -> None:
        original = requirement("页面显示错误提示").replace(
            "## 不修改范围",
            "### BDD-002 网络错误\nGiven 用户位于登录页\nWhen 登录请求失败\n"
            "Then 页面显示重试入口\n\n## 不修改范围",
        )
        snapshot = self._snapshot(original)
        snapshot, _ = apply_requirement_revision(
            self.snapshot_path,
            self.requirement_path,
            original,
            build_confirmed_revision_manifest(snapshot, original),
        )

        with self.assertRaisesRegex(RequirementSnapshotError, "--revision-file"):
            build_confirmed_revision_manifest(snapshot, requirement("页面显示错误提示"))


if __name__ == "__main__":
    unittest.main()
