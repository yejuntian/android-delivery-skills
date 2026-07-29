#!/usr/bin/env python3
"""验证需求机器状态由实际项目 Git 自动排除，正式文档仍保持可跟踪。"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..git_ignore import ensure_requirement_state_ignored


def _init_repo(root: Path) -> None:
    """创建带初始提交的临时项目仓库。"""
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    (root / "app").mkdir()
    (root / "app" / "Main.kt").write_text("class Main\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)


class GitIgnoreTests(unittest.TestCase):
    """验证项目级本地 exclude 的幂等性和边界。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        _init_repo(self.root)

    def test_registers_document_state_without_hiding_documents(self) -> None:
        requirement_dir = self.root / "document" / "2026-07-30-login"
        requirement_dir.mkdir(parents=True)

        first = ensure_requirement_state_ignored(self.root, requirement_dir)
        second = ensure_requirement_state_ignored(self.root, requirement_dir)

        self.assertTrue(first.added)
        self.assertFalse(second.added)
        self.assertEqual("/document/*/.state/", first.pattern)
        assert first.exclude_path is not None
        exclude_content = first.exclude_path.read_text(encoding="utf-8")
        self.assertEqual(1, exclude_content.count(first.pattern))

        cache_file = requirement_dir / ".state" / "journey-runtime" / "scope" / "harness-app-build" / "app.apk"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"cache")
        document = requirement_dir / "docs" / "需求说明.md"
        document.parent.mkdir()
        document.write_text("# 登录\n", encoding="utf-8")

        ignored = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", str(cache_file.relative_to(self.root))],
            cwd=self.root,
            check=False,
        )
        visible = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", str(document.relative_to(self.root))],
            cwd=self.root,
            check=False,
        )
        self.assertEqual(0, ignored.returncode)
        self.assertNotEqual(0, visible.returncode)

    def test_external_requirement_directory_needs_no_project_rule(self) -> None:
        result = ensure_requirement_state_ignored(
            self.root,
            self.root.parent / "external-requirement",
        )

        self.assertFalse(result.added)
        self.assertIsNone(result.pattern)


if __name__ == "__main__":
    unittest.main()
