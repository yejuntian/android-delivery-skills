#!/usr/bin/env python3
"""脚本名称：test_render_artifacts.py

用途：验证 JSON→md 影子渲染正确，以及续接指南聚合各事实源。

覆盖范围：需求修订说明、测试映射说明（含架构约束栏）、续接指南状态汇总、
交付结论强制未验证项/残留风险段。测试不运行 Android 构建或设备任务。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..render_artifacts import (  # noqa: E402
    execution_progress_items,
    render_resume_guide,
    render_revision_md,
    render_test_mapping_md,
)


def make_snapshot(revision: int = 2) -> dict:
    """构造已确认的最小需求快照。"""
    return {
        "requirement_id": "REQ-20260724-001",
        "revision": revision,
        "status": "CONFIRMED",
        "obligations": [
            {"id": "BDD-001/T1", "text": "显示错误提示", "required": True, "sha256": "a" * 64},
            {"id": "BDD-002/T1", "text": "跳转主页", "required": True, "sha256": "b" * 64},
        ],
        "pending_changes": [],
    }


class RenderArtifactsTests(unittest.TestCase):
    """验证人读 md 影子从 JSON 正确渲染。"""

    def test_revision_md_lists_obligations(self) -> None:
        """需求修订说明列出每条义务及其必需性。"""
        md = render_revision_md(make_snapshot())
        self.assertIn("增量修订（第 1 次）", md)
        self.assertIn("`BDD-001/T1`", md)
        self.assertIn("[必需]", md)

    def test_test_mapping_md_shows_architecture_column(self) -> None:
        """测试映射说明含架构约束栏，STALE 标记为待回填。"""
        mapping = {
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["TEST-001"],
                    "mapping_status": "CURRENT",
                    "architecture_tests": ["埋点只在统一出口"],
                },
                {
                    "obligation_id": "BDD-002/T1",
                    "obligation_sha256": "b" * 64,
                    "test_ids": [],
                    "mapping_status": "STALE",
                    "architecture_tests": [],
                },
            ],
        }
        md = render_test_mapping_md(mapping, make_snapshot())
        self.assertIn("架构约束", md)
        self.assertIn("埋点只在统一出口", md)
        self.assertIn("待回填", md)

    def test_resume_guide_flags_stale_and_next_steps(self) -> None:
        """续接指南标记 STALE 映射，并列出下一步。"""
        mapping = {"mappings": [
            {"obligation_id": "BDD-001/T1", "mapping_status": "CURRENT", "test_ids": ["t1"]},
            {"obligation_id": "BDD-002/T1", "mapping_status": "STALE", "test_ids": []},
        ]}
        guide = render_resume_guide(
            make_snapshot(), mapping, {"confirmed_at": "2026-07-24"}, None, "登录页"
        )
        self.assertIn("登录页", guide)
        self.assertIn("当前执行进度", guide)
        self.assertIn("测试待回填", guide)
        self.assertIn("STALE", guide)
        self.assertIn("下一步", guide)

    def test_execution_progress_without_snapshot_is_requirement_confirmation(self) -> None:
        """无快照时只提示确认需求，不创建任何新状态。"""
        items = execution_progress_items(None, None, None, None)

        self.assertIn("◉ 确认需求", items[0])
        self.assertTrue(any("实施计划.md" in item for item in items))

    def test_execution_progress_requires_plan_after_confirmed_requirement(self) -> None:
        """需求已确认但计划未确认时，当前步骤是实施计划确认。"""
        items = execution_progress_items(make_snapshot(), None, None, None)

        self.assertIn("✓ 确认需求", items[0])
        self.assertIn("⏳ 确认实施计划", items[1])
        self.assertIn("confirm-plan", items[1])

    def test_execution_progress_marks_stale_mapping_as_current_step(self) -> None:
        """测试映射 STALE 时，当前步骤是回填测试映射。"""
        mapping = {"mappings": [
            {"obligation_id": "BDD-002/T1", "mapping_status": "STALE", "test_ids": []},
        ]}

        items = execution_progress_items(
            make_snapshot(), mapping, {"confirmed_at": "2026-07-24"}, None
        )

        self.assertIn("✓ 确认实施计划", items[1])
        self.assertIn("⏳ 测试映射", items[2])
        self.assertIn("BDD-002/T1", items[2])

    def test_execution_progress_translates_delivery_conclusion(self) -> None:
        """最终报告结论使用中文语义展示，不裸露机器枚举。"""
        mapping = {"mappings": [
            {"obligation_id": "BDD-001/T1", "mapping_status": "CURRENT", "test_ids": ["t1"]},
        ]}

        items = execution_progress_items(
            make_snapshot(),
            mapping,
            {"confirmed_at": "2026-07-24"},
            {"conclusion": "FULL_PASS"},
        )

        self.assertIn("全部验证通过", items[-1])
        self.assertNotIn("FULL_PASS", "\n".join(items))

    def test_resume_guide_without_snapshot(self) -> None:
        """无快照时续接指南提示先建基线，不抛异常。"""
        guide = render_resume_guide(None, None, None, None, "")
        self.assertIn("尚未建立需求快照", guide)
        self.assertIn("当前执行进度", guide)
        self.assertIn("◉ 确认需求", guide)

    def test_resume_guide_lists_impact_blast_radius(self) -> None:
        """传入修订清单时，续接指南列出本次增量波及义务及影响半径。"""
        snapshot = make_snapshot(revision=3)
        mapping = {"mappings": [
            {"obligation_id": "BDD-001/T1", "mapping_status": "STALE", "test_ids": []},
            {"obligation_id": "BDD-002/T1", "mapping_status": "CURRENT", "test_ids": ["t2"]},
        ]}
        manifest = {"changes": [
            {"id": "BDD-001/T1", "change_type": "CHANGED", "decision": "CONFIRMED"},
            {"id": "BDD-002/T1", "change_type": "UNCHANGED", "decision": "CONFIRMED"},
            {"id": "BDD-003/T1", "change_type": "ADDED", "decision": "CONFIRMED"},
            {"id": "BDD-009/T1", "change_type": "REMOVED", "decision": "CONFIRMED"},
        ]}
        guide = render_resume_guide(snapshot, mapping, None, None, "", manifest)
        self.assertIn("本次增量波及清单（增量修订（第 2 次））", guide)
        self.assertIn("`BDD-001/T1` [CHANGED]", guide)
        self.assertIn("测试映射已标 STALE", guide)
        self.assertIn("`BDD-003/T1` [ADDED]", guide)
        self.assertIn("待登记测试用例", guide)
        self.assertIn("`BDD-009/T1` [REMOVED]", guide)
        # UNCHANGED 不进波及清单。
        self.assertNotIn("[UNCHANGED]", guide)

    def test_resume_guide_without_manifest_has_no_blast_radius(self) -> None:
        """不传 manifest（init 场景）时不渲染波及清单段。"""
        guide = render_resume_guide(make_snapshot(), None, None, None, "")
        self.assertNotIn("波及清单", guide)


if __name__ == "__main__":
    unittest.main()
