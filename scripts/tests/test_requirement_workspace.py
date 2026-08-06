#!/usr/bin/env python3
"""脚本名称：test_requirement_workspace.py

用途：验证串行需求独立工作区轮换、中文状态摘要、路径保护和延迟回收策略。

覆盖范围：profiles 策略解析、旧目录迁移、新需求创建、配置注释保留、失败回滚、
并发锁、时间门槛、临时缓存回收和危险路径拒绝。测试只使用临时目录，不操作真实需求或项目。
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from .. import requirement_workspace as requirement_workspace_module  # noqa: E402
from ..config_paths import resolve_config_paths  # noqa: E402
from ..requirement_workspace import (  # noqa: E402
    RequirementWorkspaceError,
    WORKSPACE_LOCK_FILE,
    WorkspacePolicy,
    _prepare_new_workspace,
    _resolve_project_reference,
    _sanitize_title,
    _validate_requirement_source,
    _write_state,
    _write_summary,
    archive_before_reclaim,
    build_reclaim_plan,
    execute_reclaim_plan,
    integrate_channels,
    load_workspace_policy,
    main,
    render_workspace_index,
    rotate_workspace,
    workspace_mutation_lock,
)


class RequirementWorkspaceTests(unittest.TestCase):
    """验证需求轮换不会串用旧资料，也不会回收活动或近期目录。"""

    def setUp(self) -> None:
        """创建与真实 profiles 结构一致的隔离临时工作区。"""
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.project = self.workspace / "android-project"
        self.project.mkdir()
        self.current = self.workspace / "current-requirement"
        self.current.mkdir()
        self.profile_dir = self.workspace / "profiles"
        self.profile_dir.mkdir()
        self.config_path = self.profile_dir / "local.yaml"
        self.config = {
            "project_path": str(self.project),
            "branch": "feature/example",
            "workspace_root": str(self.workspace),
            "requirement_dir": "current-requirement",
            "requirement_file": "requirement.docx",
            "requirement_workspace": {
                "mode": "rotate",
                "root": "requirements-runtime",
                "keep_completed": 3,
                "cache_retention_days": 7,
            },
            "ui": {"links": [], "directory": None, "screenshots": [], "assets": [], "notes": ""},
            "api": {"links": [], "files": [], "status": "unknown", "notes": ""},
            "testing": {"journey_harness": {}},
        }
        self._write_config()

    def tearDown(self) -> None:
        """删除测试自身创建的临时目录。"""
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def _write_config(self) -> None:
        """写入包含顶层路径和可保留注释的测试配置。"""
        self.config_path.write_text(
            "# 必须保留的中文配置注释\n"
            f"project_path: {self.project}\n"
            "branch: feature/example\n"
            f"workspace_root: {self.workspace}\n"
            f"requirement_dir: {self.config['requirement_dir']}\n"
            f"requirement_file: {self.config['requirement_file']}\n"
            "requirement_workspace:\n"
            "  mode: rotate\n"
            "  root: requirements-runtime\n"
            "  keep_completed: 3\n"
            "  cache_retention_days: 7\n"
            "ui: {links: [], directory: null, screenshots: [], assets: [], notes: ''}\n"
            "api: {links: [], files: [], status: unknown, notes: ''}\n"
            "testing: {journey_harness: {}}\n",
            encoding="utf-8",
        )

    def _policy_and_paths(self):
        """按生产代码入口解析当前测试配置。"""
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        return config, *load_workspace_policy(config, self.config_path)

    def test_profiles_policy_resolves_inside_workspace(self) -> None:
        """验证相对根目录、保留数量和缓存目录按 workspace_root 解析。"""
        _, policy, paths = self._policy_and_paths()

        self.assertEqual("rotate", policy.mode)
        self.assertEqual(self.workspace / "requirements-runtime", policy.root)
        self.assertEqual(3, policy.keep_completed)
        self.assertEqual(7, policy.retention_days)
        self.assertEqual(self.workspace / "tempfile", policy.tempfile_dir)
        self.assertEqual(self.current, paths.requirement_dir)

    def test_policy_rejects_workspace_root_as_managed_directory(self) -> None:
        """验证错误配置不能把整个本机工作区变成可回收目标。"""
        self.config["requirement_workspace"]["root"] = str(self.workspace)

        with self.assertRaisesRegex(RequirementWorkspaceError, "不能等于工作区根目录"):
            load_workspace_policy(self.config, self.config_path)

    def test_policy_rejects_directories_overlapping_android_project(self) -> None:
        """验证需求、缓存或回收根目录不能落入 Android 项目或包含项目。"""
        cases = {
            "需求根目录位于项目内": ("requirement_workspace", self.project / "runtime"),
            "当前需求目录位于项目内": ("requirement_dir", self.project / "current"),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label):
                config = dict(self.config)
                config["requirement_workspace"] = dict(
                    self.config["requirement_workspace"]
                )
                if field == "requirement_workspace":
                    config[field]["root"] = str(value)
                else:
                    config[field] = str(value)
                with self.assertRaisesRegex(
                    RequirementWorkspaceError, "不能与 Android 项目路径重叠"
                ):
                    load_workspace_policy(config, self.config_path)

    def test_requirement_source_must_be_outside_active_directory(self) -> None:
        """验证新需求文件不能放在即将迁移的旧工作区中。"""
        source = self.current / "new.docx"
        source.write_bytes(b"new")

        with self.assertRaisesRegex(RequirementWorkspaceError, "必须先放在当前需求目录之外"):
            _validate_requirement_source(source, self.current)

    def test_existing_mutation_lock_is_preserved(self) -> None:
        """验证并发窗口被阻断时不会误删另一个窗口持有的锁。"""
        root = self.workspace / "requirements-runtime"
        root.mkdir()
        lock_path = root / WORKSPACE_LOCK_FILE
        lock_path.write_text("other-window\n", encoding="utf-8")

        with self.assertRaisesRegex(RequirementWorkspaceError, "另一个窗口正在执行"):
            with workspace_mutation_lock(root):
                self.fail("已有锁时不应进入写操作")

        self.assertEqual("other-window\n", lock_path.read_text(encoding="utf-8"))

    def test_rotate_migrates_legacy_workspace_and_preserves_config_comments(self) -> None:
        """验证首次轮换保留旧资料、创建中文目录并只修改两个配置标量。"""
        (self.current / "requirement.docx").write_bytes(b"old")
        (self.current / "api").mkdir()
        (self.current / "api" / "contract.png").write_bytes(b"api")
        source = self.workspace / "new-requirement.md"
        source.write_text("# 新需求", encoding="utf-8")
        config, policy, paths = self._policy_and_paths()
        now = datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc)

        with patch.object(
            requirement_workspace_module, "working_tree_status", return_value=""
        ):
            new_dir, plan = rotate_workspace(
                self.config_path,
                config,
                policy,
                paths,
                "视频下载页登录拦截",
                source,
                "旧视频下载需求",
                "completed",
                now,
            )

        archived = policy.root / "REQ-20260721-001-旧视频下载需求"
        self.assertEqual(
            policy.root / "REQ-20260721-002-视频下载页登录拦截", new_dir
        )
        self.assertTrue((archived / "requirement.docx").is_file())
        self.assertTrue((archived / "api" / "contract.png").is_file())
        self.assertEqual(
            "COMPLETED",
            yaml.safe_load(
                (archived / "requirement-workspace.json").read_text(encoding="utf-8")
            )["status"],
        )
        self.assertTrue((new_dir / "docs" / "视频下载页登录拦截.md").is_file())
        self.assertTrue((new_dir / "docs" / "需求状态.md").is_file())
        for name in ("test-cases", "test-results", ".state"):
            self.assertTrue((new_dir / name).is_dir())
        # 专项资料和扩展 Markdown 目录按需创建，避免每个需求留下空目录。
        for name in ("api", "ui", "config", "issues"):
            self.assertFalse((new_dir / name).exists(), f"不应默认创建按需目录: {name}")
        for name in ("plan", "review", "decisions"):
            self.assertFalse((new_dir / "docs" / name).exists(), f"不应默认创建扩展目录: {name}")
        updated = self.config_path.read_text(encoding="utf-8")
        self.assertIn("# 必须保留的中文配置注释", updated)
        self.assertIn(
            'requirement_dir: "requirements-runtime/REQ-20260721-002-视频下载页登录拦截"',
            updated,
        )
        self.assertIn('requirement_file: "docs/视频下载页登录拦截.md"', updated)
        self.assertEqual((), plan.workspaces)
        self.assertFalse(self.current.exists())

    def test_rotation_failure_restores_config_directory_and_metadata(self) -> None:
        """验证完成状态写入失败时恢复旧目录，并移除本轮新增状态和新目录。"""
        (self.current / "requirement.docx").write_bytes(b"old")
        docs = self.current / "docs"
        docs.mkdir()
        legacy_summary = docs / "需求说明.md"
        legacy_content = "# 原工作区状态\n"
        legacy_summary.write_text(legacy_content, encoding="utf-8")
        source = self.workspace / "new-requirement.md"
        source.write_text("# 新需求", encoding="utf-8")
        config_before = self.config_path.read_text(encoding="utf-8")
        config, policy, paths = self._policy_and_paths()

        def write_summary_with_failure(directory, state):
            """写入真实摘要后注入失败，验证旧文件内容可完整回滚。"""
            result = _write_summary(directory, state)
            if state.get("status") in {"COMPLETED", "CANCELLED"}:
                raise RequirementWorkspaceError("模拟上一需求状态摘要写入后失败")
            return result

        with (
            patch.object(
                requirement_workspace_module, "working_tree_status", return_value=""
            ),
            patch.object(
                requirement_workspace_module,
                "_write_summary",
                side_effect=write_summary_with_failure,
            ),
            self.assertRaisesRegex(
                RequirementWorkspaceError, "模拟上一需求状态摘要写入后失败"
            ),
        ):
            rotate_workspace(
                self.config_path,
                config,
                policy,
                paths,
                "视频下载页登录拦截",
                source,
                "旧视频下载需求",
                "completed",
            )

        self.assertEqual(config_before, self.config_path.read_text(encoding="utf-8"))
        self.assertTrue((self.current / "requirement.docx").is_file())
        self.assertFalse((self.current / "requirement-workspace.json").exists())
        self.assertFalse((self.current / "docs" / "需求状态.md").exists())
        self.assertEqual(legacy_content, legacy_summary.read_text(encoding="utf-8"))
        self.assertFalse(any(item.name.startswith("REQ-") for item in policy.root.iterdir()))

    def test_existing_workspace_keeps_legacy_summary_filename(self) -> None:
        """已有需求说明原位刷新，避免在途需求被强制迁移或留下两份摘要。"""
        docs = self.current / "docs"
        docs.mkdir()
        legacy = docs / "需求说明.md"
        legacy.write_text("# 旧状态\n", encoding="utf-8")

        _write_summary(
            self.current,
            {
                "status": "ACTIVE",
                "title": "登录拦截",
                "requirement_file": "docs/login.md",
            },
        )

        self.assertIn("唯一需求事实源", legacy.read_text(encoding="utf-8"))
        self.assertFalse((docs / "需求状态.md").exists())

    def test_project_bound_workspace_uses_portable_project_reference(self) -> None:
        """跟项目提交的状态和摘要不写入本机绝对项目或工作目录。"""
        project = self.root / "MyApp"
        creating = project / "document" / ".creating-login"
        creating.mkdir(parents=True)
        source = self.root / "login.md"
        source.write_text("# 登录拦截\n", encoding="utf-8")

        _prepare_new_workspace(
            creating,
            "REQ-20260721-001",
            "登录拦截",
            source,
            project,
            "feature/login",
            datetime(2026, 7, 21, tzinfo=timezone.utc),
        )

        state_text = (creating / "requirement-workspace.json").read_text(
            encoding="utf-8"
        )
        state = json.loads(state_text)
        summary = (creating / "docs" / "需求状态.md").read_text(encoding="utf-8")
        self.assertEqual("../..", state["project_path"])
        self.assertNotIn(str(project), state_text)
        self.assertNotIn(str(project), summary)
        self.assertNotIn(str(creating), summary)
        self.assertIn("../..（相对当前需求目录）", summary)

    def test_project_reference_rejects_invalid_json_type(self) -> None:
        """损坏状态不能把对象静默解释成项目路径。"""
        with self.assertRaisesRegex(
            RequirementWorkspaceError, "project_path 必须是字符串路径或空值"
        ):
            _resolve_project_reference(self.current, {"path": str(self.project)})

    def test_reclaim_requires_count_and_age_and_never_deletes_active(self) -> None:
        """验证只有同时超出最近数量和保留天数的已完成目录才会被删除。"""
        policy = WorkspacePolicy(
            mode="rotate",
            root=self.workspace / "requirements-runtime",
            keep_completed=3,
            retention_days=7,
            tempfile_dir=self.workspace / "tempfile",
        )
        policy.root.mkdir()
        active = policy.root / "REQ-20260721-006-当前需求"
        active.mkdir()
        _write_state(active, {"status": "ACTIVE", "title": "当前需求"})
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        completed = []
        for index, age_days in enumerate((1, 2, 3, 10, 20), start=1):
            directory = policy.root / f"REQ-202607{index:02d}-001-历史需求{index}"
            directory.mkdir()
            timestamp = now - timedelta(days=age_days)
            _write_state(directory, {
                "status": "COMPLETED",
                "title": f"历史需求{index}",
                "completed_at": timestamp.isoformat(),
            })
            completed.append(directory)
        policy.tempfile_dir.mkdir()
        old_cache = policy.tempfile_dir / "old-cache"
        recent_cache = policy.tempfile_dir / "recent-cache"
        old_cache.mkdir()
        recent_cache.mkdir()
        damaged = policy.root / "REQ-20260101-001-状态损坏"
        damaged.mkdir()
        (damaged / "requirement-workspace.json").write_text("{", encoding="utf-8")
        old_time = (now - timedelta(days=10)).timestamp()
        recent_time = (now - timedelta(days=1)).timestamp()
        os.utime(old_cache, (old_time, old_time))
        os.utime(recent_cache, (recent_time, recent_time))

        plan = build_reclaim_plan(policy, active, now)

        self.assertEqual(tuple(completed[3:]), plan.workspaces)
        self.assertEqual((old_cache,), plan.cache_entries)
        self.assertEqual((damaged,), plan.protected_workspaces)
        execute_reclaim_plan(policy, plan)
        self.assertTrue(active.is_dir())
        self.assertTrue(all(item.is_dir() for item in completed[:3]))
        self.assertFalse(any(item.exists() for item in completed[3:]))
        self.assertFalse(old_cache.exists())
        self.assertTrue(recent_cache.is_dir())
        self.assertTrue(damaged.is_dir())

    def test_reclaim_archives_human_md_before_delete(self) -> None:
        """回收前把完整 docs/ 归档到 archive/，源目录删除后人读记录仍可查。"""
        policy = WorkspacePolicy(
            mode="rotate",
            root=self.workspace / "requirements-runtime",
            keep_completed=0,
            retention_days=0,
            tempfile_dir=self.workspace / "tempfile",
        )
        policy.root.mkdir()
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        done = policy.root / "REQ-20260701-001-已完成需求"
        done.mkdir()
        (done / "docs").mkdir()
        (done / "docs" / "需求说明.md").write_text("# 历史需求状态", encoding="utf-8")
        (done / "docs" / "续接指南.md").write_text("# 续接", encoding="utf-8")
        (done / "docs" / "决策-2026-07-01-不引库.md").write_text("# 决策", encoding="utf-8")
        (done / "test-cases").mkdir()
        (done / "test-cases" / "requirement-revision.json").write_text("{}", encoding="utf-8")
        _write_state(done, {
            "status": "COMPLETED",
            "title": "已完成需求",
            "completed_at": (now - timedelta(days=10)).isoformat(),
        })

        archive = archive_before_reclaim(done, policy.root)
        self.assertIsNotNone(archive)
        self.assertTrue((archive / "docs" / "需求说明.md").is_file())
        self.assertTrue((archive / "docs" / "续接指南.md").is_file())
        self.assertTrue((archive / "docs" / "决策-2026-07-01-不引库.md").is_file())
        self.assertFalse((archive / "test-cases").exists())

        index = render_workspace_index(policy.root)
        self.assertIn("已完成需求", index)
        self.assertIn("需求总览", index)
        self.assertIn("archive/", index)
        # 并行方案六列总览必须含分支和集成批次列。
        self.assertIn("分支", index)
        self.assertIn("集成批次", index)

    def test_index_command_writes_overview_file(self) -> None:
        """index 子命令端到端：写入 需求总览.md，活动/已完成需求各一行。"""
        policy = WorkspacePolicy(
            mode="rotate",
            root=self.workspace / "requirements-runtime",
            keep_completed=3,
            retention_days=7,
            tempfile_dir=self.workspace / "tempfile",
        )
        policy.root.mkdir()
        active = policy.root / "REQ-20260721-001-进行中需求"
        active.mkdir()
        _write_state(active, {"status": "ACTIVE", "title": "进行中需求", "requirement_id": "REQ-20260721-001"})
        done = policy.root / "REQ-20260701-001-已完成需求"
        done.mkdir()
        _write_state(done, {
            "status": "COMPLETED",
            "title": "已完成需求",
            "requirement_id": "REQ-20260701-001",
            "completed_at": "2026-07-01T00:00:00+00:00",
        })

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["index", "--config", str(self.config_path)])

        self.assertEqual(0, result)
        index_path = policy.root / "需求总览.md"
        self.assertTrue(index_path.is_file())
        content = index_path.read_text(encoding="utf-8")
        self.assertIn("进行中需求", content)
        self.assertIn("已完成需求", content)
        self.assertIn("REQ-20260721-001", content)

    def test_integrate_generates_report_and_marks_merged(self) -> None:
        """integrate 汇总各通道生成交付集成报告，并标 MERGED + 批次号。"""
        # 两个并行通道（模拟两个 worktree 的 requirement_dir）
        project_a = self.workspace / "project-login"
        project_b = self.workspace / "project-pay"
        channel_a = project_a / "document" / "2026-07-25-login"
        channel_b = project_b / "document" / "2026-07-25-pay"
        for channel, project_reference, title, branch, conclusion in [
            (channel_a, "../..", "登录页改造", "feature/req-login", "FULL_PASS"),
            (
                channel_b,
                str(project_b),
                "支付断点续传",
                "feature/req-pay",
                "LOCAL_PASS_DEVICE_PENDING",
            ),
        ]:
            channel.mkdir(parents=True)
            _write_state(channel, {
                "status": "COMPLETED",
                "title": title,
                "branch": branch,
                "requirement_id": channel.name,
                "project_path": project_reference,
            })
            (channel / "test-results").mkdir()
            (channel / "test-results" / "delivery-result.json").write_text(
                json.dumps(
                    {
                        "conclusion": conclusion,
                        "obligations": [],
                        "pending_capabilities": [],
                    }
                ),
                encoding="utf-8",
            )

        main_worktree = self.workspace / "MyApp"
        with patch.object(
            requirement_workspace_module, "release_channel"
        ) as release_channel:
            report = integrate_channels(
                main_worktree, [channel_a, channel_b], "2026-07-25-批次1"
            )
        self.assertTrue(report.is_file())
        content = report.read_text(encoding="utf-8")
        self.assertIn("登录页改造", content)
        self.assertIn("支付断点续传", content)
        self.assertIn("feature/req-login", content)
        self.assertIn("FULL_PASS", content)

        # 各通道 state 被标 MERGED + 批次号。
        state_a = json.loads(
            (channel_a / "requirement-workspace.json").read_text(encoding="utf-8")
        )
        self.assertEqual("MERGED", state_a["status"])
        self.assertEqual("2026-07-25-批次1", state_a["integration_batch"])
        self.assertEqual(2, release_channel.call_count)
        released_projects = {call.args[0] for call in release_channel.call_args_list}
        self.assertEqual({project_a.resolve(), project_b.resolve()}, released_projects)

    def test_integrate_rejects_invalid_project_reference_before_writes(self) -> None:
        """任一通道状态损坏时，不生成报告或改写其他通道状态。"""
        main_worktree = self.workspace / "MyApp"
        channel_a = self.workspace / "channels" / "login"
        channel_b = self.workspace / "channels" / "pay"
        for channel, project_path in (
            (channel_a, str(self.project)),
            (channel_b, {"unexpected": "object"}),
        ):
            channel.mkdir(parents=True)
            _write_state(
                channel,
                {
                    "status": "COMPLETED",
                    "title": channel.name,
                    "project_path": project_path,
                },
            )

        with self.assertRaisesRegex(
            RequirementWorkspaceError, "project_path 必须是字符串路径或空值"
        ):
            integrate_channels(main_worktree, [channel_a, channel_b], "invalid-state")

        for channel in (channel_a, channel_b):
            state = json.loads(
                (channel / "requirement-workspace.json").read_text(encoding="utf-8")
            )
            self.assertEqual("COMPLETED", state["status"])
            self.assertNotIn("integration_batch", state)
        self.assertFalse((main_worktree / "document").exists())

    def test_next_preview_accepts_chinese_outcome_without_modifying_files(self) -> None:
        """验证中文结论能生成准确预览，且未确认时不轮换目录或配置。"""
        source = self.workspace / "new-requirement.md"
        source.write_text("# 新需求", encoding="utf-8")
        old_cache = self.workspace / "tempfile" / "old-cache"
        old_cache.mkdir(parents=True)
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
        os.utime(old_cache, (old_time, old_time))
        config_before = self.config_path.read_text(encoding="utf-8")
        output = io.StringIO()

        with redirect_stdout(output):
            result = main([
                "next",
                "--config",
                str(self.config_path),
                "--title",
                "视频下载页登录拦截",
                "--requirement-file",
                str(source),
                "--previous-title",
                "旧需求",
                "--previous-outcome",
                "已完成",
            ])

        self.assertEqual(0, result)
        self.assertIn("上一需求结论：已经完成", output.getvalue())
        self.assertIn("当前仅预览", output.getvalue())
        self.assertIn("候选也会执行延迟回收", output.getvalue())
        self.assertEqual(config_before, self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(old_cache.is_dir())
        self.assertFalse((self.workspace / "requirements-runtime").exists())

    def test_rotation_reports_cleanup_failure_without_hiding_success(self) -> None:
        """验证轮换成功但回收失败时同时说明已完成范围和可重试动作。"""
        source = self.workspace / "new-requirement.md"
        source.write_text("# 新需求", encoding="utf-8")
        output = io.StringIO()
        error = io.StringIO()

        with (
            patch.object(
                requirement_workspace_module, "working_tree_status", return_value=""
            ),
            patch.object(
                requirement_workspace_module,
                "execute_reclaim_plan",
                side_effect=OSError("权限不足"),
            ),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            result = main([
                "next",
                "--config",
                str(self.config_path),
                "--title",
                "视频下载页登录拦截",
                "--requirement-file",
                str(source),
                "--previous-title",
                "旧需求",
                "--previous-outcome",
                "已完成",
                "--confirm",
            ])

        self.assertEqual(1, result)
        self.assertIn("新需求工作区已创建", output.getvalue())
        self.assertIn("轮换已经成功", error.getvalue())
        self.assertIn("单独执行 requirement_workspace.py prune", output.getvalue())
        self.assertFalse(
            (self.workspace / "requirements-runtime" / WORKSPACE_LOCK_FILE).exists()
        )

    def test_title_sanitization_keeps_chinese_and_blocks_path_separators(self) -> None:
        """验证中文名称可读，同时不能借标题逃逸工作区根目录。"""
        self.assertEqual("视频-下载-页面", _sanitize_title(" 视频/下载:页面 "))


if __name__ == "__main__":
    unittest.main()
