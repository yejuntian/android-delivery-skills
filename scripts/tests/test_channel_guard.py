#!/usr/bin/env python3
"""验证需求通道只隔离同一物理 worktree，允许不同 worktree 并行。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..channel_guard import (  # noqa: E402
    ChannelGuardError,
    assert_channel,
    channel_lock_path,
    claim_channel,
    release_channel,
)
from ..delivery import DeliveryError, cmd_check_env  # noqa: E402


class ChannelGuardTests(unittest.TestCase):
    """验证并行通道的最小占用、复用、冲突和释放行为。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Channel Guard Test")
        self.git("config", "user.email", "channel-guard@example.invalid")
        (self.repo / "README.md").write_text("baseline\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "baseline")
        self.git("branch", "-M", "main")
        self.requirement_a = self.root / "requirement-a"
        self.requirement_b = self.root / "requirement-b"
        self.requirement_a.mkdir()
        self.requirement_b.mkdir()
        self.config_a = self.root / "login.yaml"
        self.config_b = self.root / "payment.yaml"
        self.config_a.write_text("project_path: repo\n", encoding="utf-8")
        self.config_b.write_text("project_path: repo\n", encoding="utf-8")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()

    def test_same_worktree_is_exclusive_but_same_channel_is_idempotent(self) -> None:
        payload, created = claim_channel(
            self.repo,
            self.requirement_a,
            self.config_a,
        )
        self.assertTrue(created)
        reused, reused_created = claim_channel(
            self.repo,
            self.requirement_a,
            self.config_a,
        )
        self.assertFalse(reused_created)
        self.assertEqual(payload["channel_id"], reused["channel_id"])

        with self.assertRaisesRegex(ChannelGuardError, "已被其他需求通道占用"):
            claim_channel(self.repo, self.requirement_b, self.config_b)

    def test_different_worktrees_can_run_in_parallel(self) -> None:
        other = self.root / "repo-payment"
        self.git("worktree", "add", "-q", str(other), "-b", "feature/payment")
        _, created_a = claim_channel(self.repo, self.requirement_a, self.config_a)
        _, created_b = claim_channel(other, self.requirement_b, self.config_b)

        self.assertTrue(created_a)
        self.assertTrue(created_b)
        self.assertNotEqual(channel_lock_path(self.repo), channel_lock_path(other))

    def test_assert_and_release_bind_the_requirement_directory_and_branch(self) -> None:
        claim_channel(self.repo, self.requirement_a, self.config_a)
        self.assertEqual(
            str(self.requirement_a.resolve()),
            assert_channel(self.repo, self.requirement_a)["requirement_dir"],
        )

        with self.assertRaisesRegex(ChannelGuardError, "已被其他需求通道占用"):
            assert_channel(self.repo, self.requirement_b)

        self.git("switch", "-c", "feature/changed")
        with self.assertRaisesRegex(ChannelGuardError, "当前分支已变化"):
            assert_channel(self.repo, self.requirement_a)

        self.git("switch", "main")
        self.assertTrue(release_channel(self.repo, self.requirement_a))
        self.assertFalse(release_channel(self.repo, self.requirement_a))

    def test_check_env_blocks_two_configs_on_one_worktree(self) -> None:
        """验证两个不同配置不能在代码开始前同时占用同一物理 worktree。"""
        for requirement_dir, config_path, title in (
            (self.requirement_a, self.config_a, "登录需求"),
            (self.requirement_b, self.config_b, "支付需求"),
        ):
            docs = requirement_dir / "docs"
            docs.mkdir()
            (docs / "requirement.md").write_text(
                f"# {title}\n\n## BDD 场景\n\n### BDD-001 {title}\n"
                "Given 用户位于目标页面\nWhen 用户执行目标操作\nThen 系统展示预期结果\n\n"
                "## 待确认\n\n- 无\n",
                encoding="utf-8",
            )
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "project_path": str(self.repo),
                        "branch": "main",
                        "workspace_root": str(self.root),
                        "requirement_dir": str(requirement_dir),
                        "requirement_file": "docs/requirement.md",
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

        old_cwd = Path.cwd()
        try:
            cmd_check_env(SimpleNamespace(config=str(self.config_a), new_requirement=False))
            with self.assertRaisesRegex(DeliveryError, "已被其他需求通道占用"):
                cmd_check_env(SimpleNamespace(config=str(self.config_b), new_requirement=False))
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
