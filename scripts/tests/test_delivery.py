#!/usr/bin/env python3
"""
================================================================================
脚本名称：test_delivery.py
用    途：验证 Android Delivery 核心脚本的确定性行为和职责边界。

覆盖范围：
1. 配置中的绝对/相对路径解析。
2. Word、Markdown、TXT 需求正文读取及明确失败行为。
3. UI/API/数据/系统/构建/架构/测试影响候选和 route 输出，不把模糊子串当成业务结论。
4. 当前需求 Git 基线、四类变化收集、脏工作区门禁和独立 JSON 输出。

测试原则：
- 所有文件和 Git 仓库均创建在临时目录，不读取或修改真实项目状态。
- 只验证公开行为，不绑定脚本内部实现细节。
================================================================================
"""

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
# 同时支持 IDE 包测试、`python -m` 和直接运行当前测试文件。
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..delivery import (  # noqa: E402
    DeliveryError,
    classify_route_files,
    classify_route_impacts,
    cmd_check_env,
    cmd_route,
    load_config,
    read_requirement,
    resolve_config_paths,
)
from ..git_changes import (  # noqa: E402
    collect_changed_files,
    current_branch,
    load_baseline,
    write_baseline,
    working_tree_status,
)


class RequirementPathTests(unittest.TestCase):
    """验证配置路径只按已声明的层级解析，不搜索或猜测其他目录。"""

    def setUp(self) -> None:
        """为每个路径用例创建独立配置目录，避免测试之间共享状态。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.config_path = self.root / "config" / "local.yaml"
        self.config_path.parent.mkdir()

    def test_relative_paths_follow_workspace_and_requirement_dir(self) -> None:
        """验证相对项目和需求文件分别基于 workspace 与 requirement_dir 解析。"""
        workspace = self.root / "workspace"
        config = {
            "workspace_root": str(workspace),
            "project_path": "android-app",
            "requirement_dir": "current-requirement",
            "requirement_file": "requirement.md",
        }

        project, requirement = resolve_config_paths(config, self.config_path)

        self.assertEqual(project, (workspace / "android-app").resolve())
        self.assertEqual(
            requirement, (workspace / "current-requirement" / "requirement.md").resolve()
        )

    def test_absolute_paths_are_not_rebased(self) -> None:
        """验证绝对路径保持原意，不被配置文件或工作区目录重复拼接。"""
        project = self.root / "absolute-project"
        requirement = self.root / "absolute-requirement.docx"
        config = {
            "workspace_root": str(self.root / "unused"),
            "project_path": str(project),
            "requirement_dir": "unused",
            "requirement_file": str(requirement),
        }

        resolved_project, resolved_requirement = resolve_config_paths(config, self.config_path)

        self.assertEqual(resolved_project, project.resolve())
        self.assertEqual(resolved_requirement, requirement.resolve())


class RequirementReaderTests(unittest.TestCase):
    """验证支持格式可以读取，缺失、空白、损坏和未知格式明确失败。"""

    def setUp(self) -> None:
        """为需求文件读取用例创建自动清理的临时目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_reads_utf8_markdown_and_text(self) -> None:
        """验证三种声明支持的 UTF-8 文本格式返回去除首尾空白的正文。"""
        for suffix in (".md", ".markdown", ".txt"):
            with self.subTest(suffix=suffix):
                path = self.root / f"requirement{suffix}"
                path.write_text("登录后展示中文标题\n", encoding="utf-8")
                self.assertEqual(read_requirement(path), "登录后展示中文标题")

    def test_reads_docx_paragraphs(self) -> None:
        """验证标准 OOXML 段落按原顺序提取，不依赖第三方 Word 解析库。"""
        path = self.root / "requirement.docx"
        # 构造最小 OOXML 正文，避免测试依赖第三方 Word 解析库。
        document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>第一条需求</w:t></w:r></w:p>
    <w:p><w:r><w:t>第二条需求</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", document_xml)

        self.assertEqual(read_requirement(path), "第一条需求\n第二条需求")

    def test_rejects_missing_empty_unsupported_and_corrupt_files(self) -> None:
        """验证不可用需求资料明确报错，禁止搜索替代文件或返回猜测正文。"""
        missing = self.root / "missing.md"
        with self.assertRaisesRegex(DeliveryError, "需求文件不存在"):
            read_requirement(missing)

        empty = self.root / "empty.txt"
        empty.write_text("  \n", encoding="utf-8")
        with self.assertRaisesRegex(DeliveryError, "未提取到正文"):
            read_requirement(empty)

        unsupported = self.root / "requirement.pdf"
        unsupported.write_bytes(b"%PDF")
        with self.assertRaisesRegex(DeliveryError, "不支持的需求文件格式"):
            read_requirement(unsupported)

        corrupt = self.root / "corrupt.docx"
        corrupt.write_bytes(b"not-a-docx")
        with self.assertRaisesRegex(DeliveryError, "DOCX 文件损坏"):
            read_requirement(corrupt)


class ConfigReaderTests(unittest.TestCase):
    """验证配置读取失败时给出明确原因，不依赖真实用户配置。"""

    def setUp(self) -> None:
        """为配置异常用例创建自动清理的隔离目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_rejects_missing_config_before_loading_yaml(self) -> None:
        """验证配置不存在时优先报告路径问题，而不是误报 YAML 依赖问题。"""
        with self.assertRaisesRegex(DeliveryError, "配置文件不存在"):
            load_config(self.root / "missing.yaml")

    def test_reports_missing_pyyaml(self) -> None:
        """验证缺少 PyYAML 时返回仓库依赖安装提示。"""
        path = self.root / "local.yaml"
        path.write_text("project_path: app\n", encoding="utf-8")
        with mock.patch.dict(sys.modules, {"yaml": None}):
            with self.assertRaisesRegex(DeliveryError, "缺少 PyYAML"):
                load_config(path)

    def test_rejects_non_object_yaml_root(self) -> None:
        """验证列表等非 object 配置被拒绝，避免后续按字典读取产生歧义。"""
        path = self.root / "local.yaml"
        path.write_text("- item\n", encoding="utf-8")
        fake_yaml = SimpleNamespace(YAMLError=Exception, safe_load=lambda _: ["item"])
        with mock.patch.dict(sys.modules, {"yaml": fake_yaml}):
            with self.assertRaisesRegex(DeliveryError, "配置根节点必须"):
                load_config(path)


class ClassificationTests(unittest.TestCase):
    """验证语义路由覆盖七类候选，同时保持原 UI/API 接口兼容。"""

    def setUp(self) -> None:
        """为内容信号识别创建隔离项目根目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def write(self, relative_path: str, content: str) -> None:
        """创建内容信号测试文件，不读取真实 Android 项目。"""
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_classifies_only_existing_ui_and_api_routes(self) -> None:
        """验证原 UI/API 二元返回接口继续兼容既有调用方。"""
        files = [
            "app/src/main/java/example/HomeComposable.kt",
            "app/src/main/java/example/UserApi.kt",
            "app/src/main/java/example/UserUseCase.kt",
        ]

        ui_files, api_files = classify_route_files(files)

        self.assertEqual(ui_files, [files[0]])
        self.assertEqual(api_files, [files[1]])

    def test_covers_documented_routes_without_substring_false_positives(self) -> None:
        """验证明确路径和类型命中，同时避免 Capitalization 之类子串误判。"""
        files = [
            "app/src/main/java/example/HomeScreen.kt",
            "app/src/main/java/example/UserMapper.kt",
            "app/src/main/java/example/RemoteDataSource.kt",
            "app/src/main/res/navigation/nav_graph.xml",
            "app/src/main/java/example/Capitalization.kt",
        ]

        ui_files, api_files = classify_route_files(files)

        self.assertEqual(ui_files, [files[0], files[3]])
        self.assertEqual(api_files, [files[1], files[2]])

    def test_classifies_data_system_build_architecture_and_tests(self) -> None:
        """验证 Manifest、Room、Proto、Gradle、DI 和测试文件进入对应候选。"""
        files = [
            "app/src/main/AndroidManifest.xml",
            "app/src/main/java/example/SyncService.kt",
            "gradle/libs.versions.toml",
            "app/src/main/java/example/UserDao.kt",
            "app/schemas/example.AppDatabase/2.json",
            "core/model/src/main/proto/user.proto",
            "app/src/main/java/example/di/AppModule.kt",
            "app/src/test/java/example/UserRepositoryTest.kt",
        ]

        impacts = classify_route_impacts(files, project_root=self.root)

        self.assertEqual(impacts["system"], [files[0], files[1]])
        self.assertNotIn(files[1], impacts["api"])
        self.assertEqual(impacts["build"], [files[2]])
        self.assertIn(files[2], impacts["architecture"])
        self.assertIn(files[6], impacts["architecture"])
        self.assertEqual(impacts["data"], [files[3], files[4], files[5]])
        self.assertEqual(impacts["tests"], [files[7]])

    def test_uses_retrofit_content_signal_for_nonstandard_filename(self) -> None:
        """验证非标准 Client 文件可由真实 Retrofit 注解补充为 API 候选。"""
        path = "app/src/main/java/example/Client.kt"
        self.write(path, 'interface Client { @GET("users") suspend fun users(): List<String> }\n')

        impacts = classify_route_impacts([path], project_root=self.root)

        self.assertEqual(impacts["api"], [path])

    def test_does_not_treat_ambiguous_substrings_as_impact(self) -> None:
        """验证模糊英文子串不能单独触发 API、数据或架构结论。"""
        files = [
            "app/src/main/java/example/Capitalization.kt",
            "app/src/main/java/example/DatabaseHelperText.kt",
            "app/src/main/java/example/ModularizationGuide.kt",
        ]

        impacts = classify_route_impacts(files, project_root=self.root)

        self.assertTrue(all(path not in impacts["api"] for path in files))
        self.assertTrue(all(path not in impacts["data"] for path in files))
        self.assertTrue(all(path not in impacts["architecture"] for path in files))


class GitDiffCollectionTests(unittest.TestCase):
    """在隔离仓库中验证所有 Git 变化来源及安全降级。"""

    def setUp(self) -> None:
        """建立独立 Git 仓库和需求基线，准备四类变化且不接触真实仓库。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("branch", "-M", "main")
        self.git("config", "user.name", "Delivery Test")
        self.git("config", "user.email", "delivery-test@example.invalid")

        self.write("baseline.txt", "baseline\n")
        self.git("add", "baseline.txt")
        self.git("commit", "-q", "-m", "baseline")
        self.git("checkout", "-q", "-b", "feature")

        # 需求基线建立在编码前，后续 commit 和工作区变化都应归入本次范围。
        self.baseline = Path(self.temp_dir.name) / "delivery-baseline.json"
        write_baseline(self.repo, self.baseline)

        # feature commit 用于验证相对 main 的 committed 差异。
        self.write("app/src/main/java/example/Committed.kt", "class Committed\n")
        self.git("add", "app/src/main/java/example/Committed.kt")
        self.git("commit", "-q", "-m", "feature commit")

        # 同一路径先暂存再修改，可同时覆盖 staged、unstaged 和去重行为。
        mixed = "app/src/main/java/example/Mixed.kt"
        self.write(mixed, "class MixedV1\n")
        self.git("add", mixed)
        self.write(mixed, "class MixedV2\n")
        # 单独保留一个未跟踪文件，验证 untracked 不会被 `git diff` 漏掉。
        self.write("app/src/main/res/layout/untracked.xml", "<FrameLayout />\n")

    def git(self, *args: str) -> None:
        """执行测试仓库准备命令，失败立即终止当前测试。"""
        subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write(self, relative_path: str, content: str) -> None:
        """在隔离仓库中创建测试文件并自动补齐父目录。"""
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_collects_committed_staged_unstaged_and_untracked_once(self) -> None:
        """验证四类 Git 变化均被收集，同一路径只返回一次。"""
        files, warnings = collect_changed_files(self.repo, "main")

        self.assertEqual(warnings, [])
        self.assertIn("app/src/main/java/example/Committed.kt", files)
        self.assertIn("app/src/main/java/example/Mixed.kt", files)
        self.assertIn("app/src/main/res/layout/untracked.xml", files)
        self.assertEqual(files.count("app/src/main/java/example/Mixed.kt"), 1)

    def test_requirement_baseline_collects_only_changes_after_start(self) -> None:
        """验证当前需求基线隔离开始前内容，只收集需求开始后的变化。"""
        files, warnings = collect_changed_files(self.repo, baseline_path=self.baseline)

        self.assertEqual(warnings, [])
        self.assertIn("app/src/main/java/example/Committed.kt", files)
        self.assertIn("app/src/main/java/example/Mixed.kt", files)
        self.assertNotIn("baseline.txt", files)
        self.assertEqual(self.repo.resolve(), Path(load_baseline(self.repo, self.baseline)["repo"]))

    def test_reports_branch_and_working_tree_without_modifying_them(self) -> None:
        """验证只读 Git 辅助方法能报告分支和脏状态且不改变仓库。"""
        self.assertEqual(current_branch(self.repo), "feature")
        status = working_tree_status(self.repo)
        self.assertIn("Mixed.kt", status)
        self.assertIn("app/src/main/res/", status)

    def test_standalone_git_script_outputs_json(self) -> None:
        """验证独立 Git 脚本输出可供其他编排器消费的结构化 JSON。"""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "git_changes.py"),
                "--repo",
                str(self.repo),
                "--base-branch",
                "main",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["branch"], "feature")
        self.assertIn("app/src/main/java/example/Committed.kt", payload["changed_files"])

    def test_missing_base_does_not_guess_or_hide_worktree_changes(self) -> None:
        """验证指定基准不存在时明确降级，仍保留可确认的工作区变化。"""
        files, warnings = collect_changed_files(self.repo, "missing-base")

        self.assertTrue(any("base_branch 不存在" in warning for warning in warnings))
        self.assertNotIn("app/src/main/java/example/Committed.kt", files)
        self.assertIn("app/src/main/java/example/Mixed.kt", files)
        self.assertIn("app/src/main/res/layout/untracked.xml", files)

    def test_missing_upstream_uses_only_worktree_with_warning(self) -> None:
        """验证没有 upstream 时不猜主分支，只报告工作区变化与能力损失。"""
        files, warnings = collect_changed_files(self.repo)

        self.assertTrue(any("没有 upstream" in warning for warning in warnings))
        self.assertNotIn("app/src/main/java/example/Committed.kt", files)
        self.assertIn("app/src/main/java/example/Mixed.kt", files)

    def test_check_env_rejects_dirty_start_and_writes_clean_baseline(self) -> None:
        """验证脏工作区阻断新需求，清洁后才允许建立需求基线。"""
        args = SimpleNamespace(config=str(Path(self.temp_dir.name) / "local.yaml"))
        patches = (
            mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
            mock.patch("scripts.delivery.resolve_config_paths", return_value=(self.repo, None)),
            mock.patch("scripts.delivery.baseline_path_for_config", return_value=self.baseline),
        )
        old_cwd = Path.cwd()
        try:
            with patches[0], patches[1], patches[2], redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(DeliveryError, "无法建立不串需求的基线"):
                    cmd_check_env(args)

            self.git("add", ".")
            self.git("commit", "-q", "-m", "current requirement prepared")
            with patches[0], patches[1], patches[2], redirect_stdout(io.StringIO()):
                cmd_check_env(args)
            self.assertEqual(current_branch(self.repo), load_baseline(self.repo, self.baseline)["branch"])
        finally:
            os.chdir(old_cwd)


class RouteCommandTests(unittest.TestCase):
    """验证 route 最终输出真实候选对应的专项 Skill。"""

    def setUp(self) -> None:
        """为路由输出用例创建隔离项目目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_route_prints_api_and_manual_ui_selection(self) -> None:
        """验证 API 自动入队、UI 保持手动，并输出其他工程影响关注点。"""
        args = SimpleNamespace(config=str(self.root / "local.yaml"))
        files = [
            "app/src/main/java/example/HomeScreen.kt",
            "app/src/main/java/example/UserMapper.kt",
            "app/src/main/java/example/UserDao.kt",
            "gradle/libs.versions.toml",
        ]
        output = io.StringIO()
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value={}),
                mock.patch("scripts.delivery.resolve_config_paths", return_value=(self.root, None)),
                mock.patch("scripts.delivery.current_branch", return_value="feature"),
                mock.patch("scripts.delivery.get_diff_files", return_value=(files, [])),
                redirect_stdout(output),
            ):
                cmd_route(args)
        finally:
            os.chdir(old_cwd)

        text = output.getvalue()
        self.assertIn("android-verify-api-contract", text)
        self.assertIn("[建议单独执行] android-verify-ui", text)
        self.assertIn("数据存储 | 检测到", text)
        self.assertIn("构建配置 | 检测到", text)
        self.assertIn("架构依赖 | 检测到", text)
        self.assertIn("schema、迁移、旧数据和回滚", text)


if __name__ == "__main__":
    unittest.main()
