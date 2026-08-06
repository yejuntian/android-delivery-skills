#!/usr/bin/env python3
"""Tests for the generated flow-contract blocks in the human design docs."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..render_flow_docs import check_documents, render_documents


class FlowDocsTests(unittest.TestCase):
    def test_current_design_docs_match_structured_contract(self) -> None:
        rendered = render_documents()
        self.assertEqual([], check_documents(rendered))

    def test_generated_blocks_include_incremental_and_figma_transitions(self) -> None:
        rendered = render_documents()
        combined = "\n".join(rendered.values())
        self.assertIn("需求语义变化", combined)
        self.assertIn("Figma 只改变已确认范围内的视觉资料", combined)
        self.assertIn("DRAFT_REQUIREMENT", combined)

    def test_flow_docs_do_not_freeze_volatile_test_counts(self) -> None:
        """验证文档保留验证入口，不手写会随测试增长而过期的计数。"""
        rendered = render_documents()
        combined = "\n".join(rendered.values())
        self.assertNotIn("最近验证：核心单测", combined)
        self.assertNotIn("当前验证基线：核心单测", combined)
        self.assertNotRegex(combined, r"当前自动化验证[^\n]*\d+/\d+")

    def test_flow_docs_distinguish_project_and_local_document_channels(self) -> None:
        """文档明确两种保存分支，并把日常入口与机器附件分层展示。"""
        rendered = render_documents()
        combined = "\n".join(rendered.values())
        required = [
            "项目内 worktree 通道",
            "本机串行轮换通道",
            "requirements-runtime/REQ-",
            "日常只需要关注四个人工入口",
            "需求状态.md",
            "同一需求的补充仍走增量闭环，不运行 next",
        ]
        for phrase in required:
            self.assertIn(phrase, combined)
        self.assertNotIn("文档布局（跟项目走，git 跟踪）", combined)


if __name__ == "__main__":
    unittest.main()
