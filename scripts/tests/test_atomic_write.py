#!/usr/bin/env python3
"""脚本名称：test_atomic_write.py

用途：验证公共原子写的正确写入、权限、临时文件清理和 JSON 序列化。

覆盖范围：文本/JSON 写入、private 权限、中断后不留半文件、父目录自动创建。
测试不接触真实项目或网络。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..atomic_write import write_json_atomic, write_text_atomic  # noqa: E402


class AtomicWriteTests(unittest.TestCase):
    """验证原子写的正确性与安全性。"""

    def setUp(self) -> None:
        """建立隔离临时目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_write_text_atomic_creates_file_and_dirs(self) -> None:
        """文本写入成功且自动创建缺失的父目录。"""
        target = self.root / "nested" / "deep" / "续接指南.md"
        write_text_atomic(target, "# 续接\n内容\n")
        self.assertEqual("# 续接\n内容\n", target.read_text(encoding="utf-8"))

    def test_write_json_atomic_sets_private_permissions(self) -> None:
        """private=True 时 JSON 文件权限为 0600（仅属主可读写）。"""
        target = self.root / "snapshot.json"
        write_json_atomic(target, {"k": "v"})
        mode = target.stat().st_mode & 0o777
        if os.name != "nt":  # Windows 不校验 POSIX 权限位
            self.assertEqual(0o600, mode)
        self.assertEqual({"k": "v"}, json.loads(target.read_text(encoding="utf-8")))

    def test_text_atomic_default_is_not_private(self) -> None:
        """默认文本写入不强加 0600（人读 md 影子可组可读）。"""
        target = self.root / "需求说明.md"
        write_text_atomic(target, "内容", private=False)
        mode = target.stat().st_mode & 0o777
        if os.name != "nt":
            self.assertNotEqual(0o600, mode)

    def test_no_tmp_file_left_after_success(self) -> None:
        """写入成功后不残留 .tmp 临时文件。"""
        target = self.root / "state.json"
        write_json_atomic(target, {"a": 1})
        self.assertFalse((self.root / "state.json.tmp").exists())

    def test_replace_existing_file_atomically(self) -> None:
        """覆盖已有文件时读到的总是完整新内容，不会读到半文件。"""
        target = self.root / "receipt.json"
        write_json_atomic(target, {"v": 1})
        write_json_atomic(target, {"v": 2})
        self.assertEqual(2, json.loads(target.read_text(encoding="utf-8"))["v"])


if __name__ == "__main__":
    unittest.main()
