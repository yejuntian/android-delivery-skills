#!/usr/bin/env python3
"""脚本名称：test_git_changes.py

用途：验证 current_delivery_snapshot 的目录级排除（document/ 不污染门禁摘要）。

覆盖范围：排除 document/ 后文档变化不改变 snapshot；不排除时变化；排除不误伤真实代码变化。
测试用真实临时 git 仓库，不接触真实 Android 项目或网络。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..git_changes import current_delivery_snapshot, write_baseline  # noqa: E402


def _init_repo(root: Path) -> None:
    """初始化一个带一次提交的临时 git 仓库。"""
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "app").mkdir()
    (root / "app" / "Foo.java").write_text("class Foo {}", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)


class DeliverySnapshotExclusionTests(unittest.TestCase):
    """验证并行方案的 document/ 排除不污染也不误伤。"""

    def setUp(self) -> None:
        """建临时仓库和基线。"""
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil", fromlist=["rmtree"]).rmtree(self.root, ignore_errors=True))
        _init_repo(self.root)
        self.baseline = self.root / ".baseline.json"
        write_baseline(self.root, self.baseline)

    def test_document_excluded_does_not_change_snapshot(self) -> None:
        """document/ 下文档变化不改变 snapshot（排除生效）。"""
        before = current_delivery_snapshot(self.root, self.baseline)["snapshot_sha256"]
        (self.root / "document" / "2026-07-25-login").mkdir(parents=True)
        (self.root / "document" / "2026-07-25-login" / "需求说明.md").write_text(
            "# 登录", encoding="utf-8"
        )
        after = current_delivery_snapshot(
            self.root, self.baseline, exclude_paths={"document"}
        )["snapshot_sha256"]
        self.assertEqual(before, after)

    def test_document_not_excluded_changes_snapshot(self) -> None:
        """不排除 document/ 时文档变化应改变 snapshot（证明排除是真起作用）。"""
        before = current_delivery_snapshot(self.root, self.baseline)["snapshot_sha256"]
        (self.root / "document").mkdir()
        (self.root / "document" / "notes.md").write_text("# 笔记", encoding="utf-8")
        after = current_delivery_snapshot(self.root, self.baseline)["snapshot_sha256"]
        self.assertNotEqual(before, after)

    def test_document_exclusion_does_not_swallow_code_changes(self) -> None:
        """排除 document/ 不应吞掉真实代码变化（不误伤）。"""
        base = current_delivery_snapshot(
            self.root, self.baseline, exclude_paths={"document"}
        )["snapshot_sha256"]
        (self.root / "app" / "Foo.java").write_text(
            "class Foo { /* changed */ }", encoding="utf-8"
        )
        after = current_delivery_snapshot(
            self.root, self.baseline, exclude_paths={"document"}
        )["snapshot_sha256"]
        self.assertNotEqual(base, after)


if __name__ == "__main__":
    unittest.main()
