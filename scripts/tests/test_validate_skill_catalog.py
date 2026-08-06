#!/usr/bin/env python3
"""Tests for strict Skill catalog and agent metadata validation."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..validate_skill_catalog import validate_catalog  # noqa: E402


class ValidateSkillCatalogTests(unittest.TestCase):
    def test_missing_agent_metadata_is_rejected(self) -> None:
        """目录存在但 agents/openai.yaml 缺失时不得跳过调用策略校验。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            references = root / "references"
            references.mkdir()
            catalog = {
                "version": 1,
                "skills": [{
                    "id": "sample-skill",
                    "role": "guide",
                    "invocation": "user",
                    "runtime": False,
                }],
            }
            (references / "skill-catalog.yaml").write_text(
                yaml.safe_dump(catalog, sort_keys=False),
                encoding="utf-8",
            )
            skill = root / "sample-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Sample.\n---\n",
                encoding="utf-8",
            )

            errors = validate_catalog(root)

        self.assertTrue(any("缺少 agents/openai.yaml" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
