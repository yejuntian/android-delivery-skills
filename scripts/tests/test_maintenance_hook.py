#!/usr/bin/env python3
"""脚本名称：test_maintenance_hook.py

用途：验证 Android Delivery 维护 pre-commit hook 的路径判定与安装逻辑。

核心流程：用纯函数测试暂存路径是否触发维护验证，用临时目录和 mock git 命令测试安装脚本
生成 hook、拒绝覆盖用户已有 hook 以及 force 覆盖行为。
测试不修改真实 Git hook、不运行真实维护验证、不接触 Android 项目或设备。

职责边界：只验证 hook 判定和安装职责，不重新实现 validate_maintenance.py 或 eval 逻辑。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ..install_maintenance_hook import HOOK_MARKER, install_hook
from ..maintenance_pre_commit import decide_validation


class MaintenancePreCommitTests(unittest.TestCase):
    """验证 pre-commit hook 只在流程维护路径变更时触发。"""

    def test_decision_skips_unrelated_paths(self) -> None:
        """暂存文件不属于当前 Skill 或不在维护范围时跳过。"""
        root = Path("/repo")
        skill_dir = root / "ai-skills" / "android-delivery-skills"
        decision = decide_validation(
            [
                "other-project/README.md",
                "ai-skills/android-delivery-skills/profiles/local.example.yaml",
            ],
            root,
            skill_dir,
        )
        self.assertFalse(decision.should_validate)
        self.assertEqual((), decision.matched_paths)

    def test_decision_matches_skill_and_eval_changes(self) -> None:
        """暂存 Skill、共享规则、eval 或脚本改动时触发维护验证。"""
        root = Path("/repo")
        skill_dir = root / "ai-skills" / "android-delivery-skills"
        decision = decide_validation(
            [
                "ai-skills/android-delivery-skills/android-test-and-fix/SKILL.md",
                "ai-skills/android-delivery-skills/android-audit-stability/references/kotlin-java-static-analysis.md",
                "ai-skills/android-delivery-skills/evals/contracts/active-contracts.yaml",
                "ai-skills/android-delivery-skills/scripts/delivery_gate.py",
            ],
            root,
            skill_dir,
        )
        self.assertTrue(decision.should_validate)
        self.assertEqual(
            (
                "android-audit-stability/references/kotlin-java-static-analysis.md",
                "android-test-and-fix/SKILL.md",
                "evals/contracts/active-contracts.yaml",
                "scripts/delivery_gate.py",
            ),
            decision.matched_paths,
        )


class InstallMaintenanceHookTests(unittest.TestCase):
    """验证安装脚本只负责安全写入 pre-commit hook。"""

    def setUp(self) -> None:
        """创建临时 Skill 目录和 fake Git hook 路径。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.skill_dir = self.root / "ai-skills" / "android-delivery-skills"
        (self.skill_dir / "scripts").mkdir(parents=True)
        (self.skill_dir / "scripts" / "maintenance_pre_commit.py").write_text("", encoding="utf-8")
        self.hook_path = self.root / ".git" / "hooks" / "pre-commit"

    def _mock_git_path(self):
        """返回 mock 对象，让安装脚本把 hook 写入临时路径。"""
        return mock.patch(
            "scripts.install_maintenance_hook.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=str(self.hook_path),
                stderr="",
            ),
        )

    def test_install_creates_managed_hook(self) -> None:
        """安装脚本会创建带管理标记且可执行的 hook。"""
        with self._mock_git_path():
            installed = install_hook(self.skill_dir)
        self.assertEqual(self.hook_path, installed)
        text = self.hook_path.read_text(encoding="utf-8")
        self.assertIn(HOOK_MARKER, text)
        self.assertIn("maintenance_pre_commit.py", text)
        self.assertTrue(self.hook_path.stat().st_mode & 0o111)

    def test_install_refuses_unmanaged_existing_hook(self) -> None:
        """已有非本脚本管理的 hook 时默认拒绝覆盖。"""
        self.hook_path.parent.mkdir(parents=True)
        self.hook_path.write_text("#!/bin/sh\necho user hook\n", encoding="utf-8")
        with self._mock_git_path(), self.assertRaises(RuntimeError):
            install_hook(self.skill_dir)

    def test_install_force_overwrites_existing_hook(self) -> None:
        """显式 force 时允许覆盖已有 hook。"""
        self.hook_path.parent.mkdir(parents=True)
        self.hook_path.write_text("#!/bin/sh\necho user hook\n", encoding="utf-8")
        with self._mock_git_path():
            install_hook(self.skill_dir, force=True)
        self.assertIn(HOOK_MARKER, self.hook_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
