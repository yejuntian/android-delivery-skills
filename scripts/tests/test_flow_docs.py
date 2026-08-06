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


if __name__ == "__main__":
    unittest.main()
