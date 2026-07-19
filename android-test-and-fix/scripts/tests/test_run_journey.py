#!/usr/bin/env python3
"""
================================================================================
脚本名称：test_run_journey.py
用    途：验证 Journey 壳执行器的安全边界和关键确定性逻辑。

覆盖范围：
1. 拒绝零用例、空用例和无有效步骤造成的假绿。
2. 正确定位指定 variant APK，并按需求作用域隔离用例与报告。
3. 用结构化结果区分环境故障与真实 UI 断言，拒绝零测试假绿。
4. 重试前置、skip-build、截图过滤、超时和敏感命令脱敏。
5. 同步当前需求用例时清理壳暂存 XML，避免串用缓存。
6. Gradle 用户缓存、项目缓存、壳构建输出和兜底报告位于 Skill 目录外，并支持显式环境变量覆盖。
7. Journey 初始化缺失、确认需求修订、FULL/PARTIAL 适用性和原子证据不会被静默忽略。

隔离说明：所有目录和文件均位于临时目录；测试不连接设备、不运行 Gradle、
不安装 APK，也不修改真实 Android 项目。
================================================================================
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_journey.py"
# 动态加载被测脚本，避免要求 Journey 目录成为可安装 Python 包。
SPEC = importlib.util.spec_from_file_location("run_journey", SCRIPT)
run_journey = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run_journey
SPEC.loader.exec_module(run_journey)

# Journey 目录名包含连字符，无法作为常规 Python 包导入；沿用被测脚本已建立的
# Skill 根目录，通过动态模块对象访问修订工具，避免 IDE 把跨目录静态导入误报为缺失。
REQUIREMENT_SNAPSHOT: Any = importlib.import_module("scripts.requirement_snapshot")
apply_requirement_revision = REQUIREMENT_SNAPSHOT.apply_requirement_revision
write_requirement_snapshot = REQUIREMENT_SNAPSHOT.write_requirement_snapshot


class RunJourneyTest(unittest.TestCase):
    """覆盖 Journey 适用性、用例校验、失败归因和证据输出。"""

    def make_harness(self, journey: str | None = None) -> Path:
        """创建最小临时 Journey 目录，绝不接触共享壳的真实用例。"""
        root = Path(tempfile.mkdtemp())
        directory = root / "harness-app" / "src" / "main" / "journeys"
        directory.mkdir(parents=True)
        if journey is not None:
            (directory / "sample.xml").write_text(journey, encoding="utf-8")
        return directory

    def test_rejects_zero_journeys(self):
        """验证空用例目录不能以零测试结果冒充 Journey 通过。"""
        files, count, error = run_journey.validate_journeys(self.make_harness())
        self.assertEqual([], files)
        self.assertEqual(0, count)
        self.assertIn("0 个测试", error)

    def test_counts_actions_and_steps(self):
        """验证 action 与 step 都计入有效执行规模，供零测试门禁使用。"""
        harness = self.make_harness(
            "<journey><actions><action>Tap Home</action><step>Verify Home</step></actions></journey>"
        )
        files, count, error = run_journey.validate_journeys(harness)
        self.assertEqual(1, len(files))
        self.assertEqual(2, count)
        self.assertIsNone(error)

    def test_rejects_empty_journey(self):
        """验证只有根节点而没有有效步骤的 Journey 被明确拒绝。"""
        _, count, error = run_journey.validate_journeys(self.make_harness("<journey/>"))
        self.assertEqual(0, count)
        self.assertIn("不包含有效", error)

    def test_variant_task_suffix_preserves_camel_case(self):
        """验证组合 variant 保留驼峰语义，并拒绝可注入非法任务字符的名称。"""
        self.assertEqual("DemoDebug", run_journey.variant_task_suffix("demoDebug"))
        with self.assertRaises(ValueError):
            run_journey.variant_task_suffix("demo-debug")

    def test_harness_runtime_paths_stay_outside_skill_and_support_override(self):
        """验证依赖/项目缓存、构建和兜底报告不写入 Skill，并允许私有覆盖。"""
        root = Path(tempfile.mkdtemp())
        harness = root / "skill" / "assets" / "journey-harness"
        cache_root = root / "cache"
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache_root)}, clear=True):
            default_home = run_journey.resolve_harness_gradle_user_home(harness)
            default_build = run_journey.resolve_harness_build_root(harness)
            project_cache = run_journey.resolve_harness_project_cache(harness)
            fallback_report = run_journey.resolve_fallback_result_path(harness)

        resolved_cache_root = cache_root.resolve()
        self.assertTrue(default_home.is_relative_to(resolved_cache_root))
        self.assertTrue(default_build.is_relative_to(resolved_cache_root))
        self.assertTrue(project_cache.is_relative_to(resolved_cache_root))
        self.assertTrue(fallback_report.is_relative_to(resolved_cache_root))
        self.assertFalse(default_home.is_relative_to(harness))
        self.assertFalse(default_build.is_relative_to(harness))
        self.assertFalse(project_cache.is_relative_to(harness))
        self.assertFalse(fallback_report.is_relative_to(harness))

        explicit_home = root / "private-gradle-home"
        explicit_build = root / "private-build-root"
        with mock.patch.dict(
            os.environ,
            {
                run_journey.JOURNEY_GRADLE_HOME_ENV: str(explicit_home),
                run_journey.JOURNEY_BUILD_ROOT_ENV: str(explicit_build),
            },
            clear=True,
        ):
            self.assertEqual(explicit_home.resolve(), run_journey.resolve_harness_gradle_user_home(harness))
            self.assertEqual(explicit_build.resolve(), run_journey.resolve_harness_build_root(harness))

    def test_environment_errors_never_trigger_app_repair(self):
        """验证只有明确 UI 断言才可进入应用分析，环境故障始终归壳失败。"""
        self.assertEqual(
            run_journey.HARNESS_FAILED,
            run_journey.classify_failure("Task ':harness-app:nope' not found"),
        )
        self.assertEqual(
            run_journey.APP_ASSERTION_FAILED,
            run_journey.classify_failure("Journey failed: assertion failed"),
        )
        self.assertEqual(
            run_journey.APP_ASSERTION_FAILED,
            run_journey.classify_failure("Gemini reasoning: assertion failed on Home screen"),
        )
        self.assertEqual(
            run_journey.HARNESS_FAILED,
            run_journey.classify_failure("Gradle test failed without an assertion signal"),
        )

    def test_reads_apk_from_output_metadata(self):
        """验证优先使用 AGP 元数据精确定位指定 variant 的 APK。"""
        root = Path(tempfile.mkdtemp())
        output = root / "app" / "build" / "outputs" / "apk" / "demo" / "debug"
        output.mkdir(parents=True)
        apk = output / "app-demo-debug.apk"
        apk.write_bytes(b"apk")
        (output / "output-metadata.json").write_text(
            json.dumps({"variantName": "demoDebug", "elements": [{"outputFile": apk.name}]}),
            encoding="utf-8",
        )
        self.assertEqual(apk, run_journey.find_apk_from_metadata(root, "app", "demoDebug"))

    def test_fallback_apk_never_crosses_variant(self):
        """验证元数据缺失时仍只选择目标 variant，不拿更新的其他 APK 兜底。"""
        root = Path(tempfile.mkdtemp())
        debug = root / "app" / "build" / "outputs" / "apk" / "demo" / "debug" / "app-demo-debug.apk"
        release = root / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
        debug.parent.mkdir(parents=True)
        release.parent.mkdir(parents=True)
        debug.write_bytes(b"debug")
        release.write_bytes(b"release")
        now = time.time()
        os.utime(debug, (now - 10, now - 10))
        os.utime(release, (now, now))

        self.assertEqual(debug, run_journey.find_newest_apk(root, "app", "demoDebug"))
        self.assertIsNone(run_journey.find_newest_apk(root, "app", "paidDebug"))

    def test_writes_json_and_markdown_reports(self):
        """验证同一次结果同时生成机器 JSON 与人类可读 Markdown 证据。"""
        output = Path(tempfile.mkdtemp()) / "result.json"
        result = run_journey.JourneyResult(
            run_journey.PASS,
            "verified",
            0,
            device="device-1",
            journey_files=["home.xml"],
            action_count=2,
            executed_tests=2,
            applicability="PARTIAL",
            covered_then_ids=["BDD-001/T1"],
            uncovered_then_ids=["BDD-001/T2"],
            baseline_id="baseline-1",
            snapshot_sha256="a" * 64,
        )
        run_journey.write_result(result, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("PASS", payload["status"])
        self.assertEqual(["BDD-001/T1"], payload["covered_then_ids"])
        report = output.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("Journey Harness 执行报告", report)
        self.assertIn("device-1", report)
        self.assertIn("BDD-001/T2", report)

    def test_distinguishes_uninitialized_harness_from_task_ambiguity(self):
        """验证可选壳缺任务时建议默认 Agent，多个任务仍归发现异常。"""
        empty = run_journey.CommandResult(["gradlew", "tasks"], 0, "assembleDebug - build")
        ambiguous = run_journey.CommandResult(
            ["gradlew", "tasks"],
            0,
            "journeyTest - first\ntestJourneyDebug - second",
        )

        self.assertEqual(run_journey.INITIALIZATION_REQUIRED, run_journey.missing_task_status(empty)[0])
        self.assertIn("默认 Android CLI Agent", run_journey.missing_task_status(empty)[1])
        self.assertEqual(run_journey.HARNESS_UNAVAILABLE, run_journey.missing_task_status(ambiguous)[0])

    def test_reports_initialization_before_requiring_device(self):
        """验证共享壳未初始化时不先要求设备，避免真正根因被环境提示遮蔽。"""
        root = Path(tempfile.mkdtemp())
        harness = root / "harness"
        harness.mkdir()
        (harness / "gradlew").write_text("", encoding="utf-8")
        journeys = root / "journeys"
        journeys.mkdir()
        (journeys / "home.xml").write_text(
            "<journey><step>打开首页并看到标题</step></journey>",
            encoding="utf-8",
        )
        result_path = root / "result.json"
        discovery = run_journey.CommandResult(["gradlew", "tasks"], 0, "assembleDebug - build")
        with (
            mock.patch.object(run_journey, "load_config", return_value={}),
            mock.patch.object(run_journey, "resolve_result_path", return_value=result_path),
            mock.patch.object(run_journey, "resolve_journeys_dir", return_value=journeys),
            mock.patch.object(run_journey, "resolve_android_sdk", return_value="/sdk"),
            mock.patch.object(
                run_journey,
                "discover_journey_task",
                return_value=(None, discovery),
            ),
            mock.patch.object(run_journey, "choose_device") as choose_device,
        ):
            exit_code = run_journey.main([
                "--config", str(root / "local.yaml"),
                "--harness-dir", str(harness),
                "--journeys-dir", str(journeys),
                "--ui-impact", "behavior",
                "--applicability", "FULL",
                "--covered-then", "BDD-001/T1",
            ])

        self.assertEqual(1, exit_code)
        self.assertEqual(
            run_journey.INITIALIZATION_REQUIRED,
            json.loads(result_path.read_text(encoding="utf-8"))["status"],
        )
        choose_device.assert_not_called()

    def test_resolves_cases_under_requirement_directory(self):
        """验证默认 Journey 用例位于当前需求目录而非共享壳源码。"""
        config_path = Path(tempfile.mkdtemp()) / "local.yaml"
        config = {"workspace_root": str(config_path.parent), "requirement_dir": "requirement"}
        resolved = run_journey.resolve_journeys_dir(config_path, config, {}, None)
        expected = (
            config_path.parent / "requirement" / "test-cases" / "journeys" / "standalone"
        ).resolve()
        self.assertEqual(expected, resolved)

    def test_requirement_scope_isolates_cases_and_reports(self):
        """验证需求正文或 Git 基线变化会产生独立作用域，防止串用报告。"""
        root = Path(tempfile.mkdtemp())
        config_path = root / "profiles" / "local.yaml"
        config_path.parent.mkdir()
        requirement = root / "requirement" / "requirement.md"
        requirement.parent.mkdir()
        requirement.write_text("first requirement", encoding="utf-8")
        config = {
            "workspace_root": str(root),
            "requirement_dir": "requirement",
            "requirement_file": "requirement.md",
        }

        first_scope = run_journey.requirement_scope_id(config_path, config)
        first_report = run_journey.resolve_result_path(config_path, config)
        requirement.write_text("second requirement", encoding="utf-8")
        second_scope = run_journey.requirement_scope_id(config_path, config)

        self.assertNotEqual(first_scope, second_scope)
        self.assertIn(first_scope, str(first_report))

        baseline = root / "baseline.json"
        baseline.write_text(json.dumps({"id": "run-123"}), encoding="utf-8")
        with mock.patch.object(run_journey, "baseline_path_for_config", return_value=baseline):
            scoped = run_journey.requirement_scope_id(config_path, config)
        self.assertTrue(scoped.startswith("run-123-"))

    def test_confirmed_revision_keeps_unconfirmed_cases_out_of_scope(self):
        """验证用例目录只随确认修订变化，编辑中的候选需求不会污染当前 Journey。"""
        root = Path(tempfile.mkdtemp())
        config_path = root / "profiles" / "local.yaml"
        config_path.parent.mkdir()
        requirement = root / "requirement" / "requirement.md"
        requirement.parent.mkdir()
        requirement.write_text("显示错误", encoding="utf-8")
        snapshot = root / "snapshot.json"
        baseline = root / "baseline.json"
        baseline.write_text(json.dumps({"id": "run-123"}), encoding="utf-8")
        write_requirement_snapshot(
            snapshot, requirement, "显示错误", requirement_id="run-123",
        )
        apply_requirement_revision(
            snapshot,
            requirement,
            "显示错误",
            {
                "version": 1,
                "requirement_id": "run-123",
                "base_revision": 0,
                "scope": "SAME_REQUIREMENT",
                "changes": [{
                    "id": "BDD-001/T1",
                    "change_type": "ADDED",
                    "decision": "CONFIRMED",
                    "text": "显示错误",
                    "required": True,
                }],
            },
        )
        config = {
            "workspace_root": str(root),
            "requirement_dir": "requirement",
            "requirement_file": "requirement.md",
        }
        with (
            mock.patch.object(run_journey, "baseline_path_for_config", return_value=baseline),
            mock.patch.object(
                run_journey, "requirement_snapshot_path_for_config", return_value=snapshot,
            ),
        ):
            confirmed_scope = run_journey.requirement_scope_id(config_path, config)
            requirement.write_text("显示错误并允许重试", encoding="utf-8")
            apply_requirement_revision(
                snapshot,
                requirement,
                "显示错误并允许重试",
                {
                    "version": 1,
                    "requirement_id": "run-123",
                    "base_revision": 1,
                    "scope": "SAME_REQUIREMENT",
                    "changes": [
                        {
                            "id": "BDD-001/T1",
                            "change_type": "UNCHANGED",
                            "decision": "CONFIRMED",
                        },
                        {
                            "id": "BDD-001/T2",
                            "change_type": "ADDED",
                            "decision": "PENDING",
                            "text": "允许重试",
                            "required": True,
                            "reason": "等待产品确认",
                        },
                    ],
                },
            )
            unconfirmed_scope = run_journey.requirement_scope_id(config_path, config)

        self.assertEqual(confirmed_scope, unconfirmed_scope)
        self.assertIn("-r1-", confirmed_scope)

    def test_behavior_journey_blocks_unconfirmed_requirement(self):
        """验证需求候选仍待确认时不生成或执行行为型 Journey。"""
        root = Path(tempfile.mkdtemp())
        harness = root / "harness"
        with (
            mock.patch.object(run_journey, "load_config", return_value={}),
            mock.patch.object(
                run_journey,
                "delivery_context",
                return_value={"requirement_status": "PENDING_CONFIRMATION"},
            ),
            mock.patch.object(run_journey, "resolve_journeys_dir") as resolve_cases,
        ):
            exit_code = run_journey.main([
                "--config", str(root / "local.yaml"),
                "--harness-dir", str(harness),
                "--ui-impact", "behavior",
                "--applicability", "FULL",
                "--covered-then", "BDD-001/T1",
            ])

        self.assertEqual(1, exit_code)
        resolve_cases.assert_not_called()
        result = json.loads(
            run_journey.resolve_fallback_result_path(harness).read_text(encoding="utf-8")
        )
        self.assertEqual(run_journey.HARNESS_UNAVAILABLE, result["status"])
        self.assertIn("尚未全部确认", result["message"])

    def test_stages_only_current_journeys(self):
        """验证同步当前用例前清除旧 XML，避免上一需求残留被执行。"""
        source = Path(tempfile.mkdtemp())
        current = source / "current.xml"
        current.write_text("<journey><action>Verify current</action></journey>", encoding="utf-8")
        harness = Path(tempfile.mkdtemp())
        target = harness / "harness-app" / "src" / "main" / "journeys"
        target.mkdir(parents=True)
        (target / "stale.xml").write_text("<journey/>", encoding="utf-8")

        run_journey.stage_journeys([current], harness)

        self.assertFalse((target / "stale.xml").exists())
        self.assertEqual(current.read_text(encoding="utf-8"),
                         (target / "current.xml").read_text(encoding="utf-8"))

    def test_collects_only_structured_results_and_journey_screenshots(self):
        """验证只收集本轮结构化结果和 Journey 证据目录，排除普通资源。"""
        harness = Path(tempfile.mkdtemp())
        build_root = Path(tempfile.mkdtemp())
        result = build_root / "test-results" / "journey" / "TEST-home.xml"
        result.parent.mkdir(parents=True)
        result.write_text('<testsuite tests="2" failures="0" errors="0"/>', encoding="utf-8")
        icon = build_root / "intermediates" / "res" / "icon.png"
        screenshot = build_root / "reports" / "journey" / "screenshots" / "home.png"
        icon.parent.mkdir(parents=True)
        screenshot.parent.mkdir(parents=True)
        icon.write_bytes(b"icon")
        screenshot.write_bytes(b"screen")

        with mock.patch.dict(
            os.environ,
            {run_journey.JOURNEY_BUILD_ROOT_ENV: str(build_root)},
            clear=False,
        ):
            summary = run_journey.collect_structured_results(harness, time.time())
            screenshots = run_journey.collect_screenshots(harness, time.time())

        self.assertEqual(2, summary.executed)
        self.assertEqual([str(result.resolve())], summary.files)
        self.assertEqual([str(screenshot.resolve())], screenshots)

    def test_retries_reapply_precondition_before_counting_assertions(self):
        """验证每次真实断言重试都会重置应用并重新应用 Given 前置。"""
        harness = Path(tempfile.mkdtemp())
        (harness / "gradlew").write_text("", encoding="utf-8")

        def fake_run(command, **_):
            """模拟 force-stop 成功、Journey 断言失败的外部命令结果。"""
            if "force-stop" in command:
                return run_journey.CommandResult(command, 0, "")
            return run_journey.CommandResult(command, 1, "assertion failed")

        structured = run_journey.StructuredTestResult(
            executed=1, failures=1, files=["TEST-home.xml"]
        )
        with (
            mock.patch.object(run_journey, "run", side_effect=fake_run),
            mock.patch.object(run_journey, "apply_precondition", return_value=(True, [], "")) as prepare,
            mock.patch.object(run_journey, "collect_structured_results", return_value=structured),
            mock.patch.object(run_journey, "collect_screenshots", return_value=[]),
        ):
            result = run_journey.run_harness(
                harness, ":harness-app:journeyTest", "com.example", "device", 2, "/sdk", {}
            )

        self.assertEqual(run_journey.APP_ASSERTION_FAILED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertEqual(2, prepare.call_count)
        gradle_commands = [command for command in result.commands if "gradlew" in command[0]]
        self.assertTrue(gradle_commands)
        self.assertTrue(all("--project-cache-dir" in command for command in gradle_commands))

    def test_success_exit_without_structured_result_is_not_pass(self):
        """验证 Gradle 零退出但缺少本轮 JUnit 证据时仍拒绝判绿。"""
        harness = Path(tempfile.mkdtemp())
        (harness / "gradlew").write_text("", encoding="utf-8")

        def fake_run(command, **_):
            """模拟只有 BUILD SUCCESSFUL 文本、没有测试结果的空成功。"""
            return run_journey.CommandResult(command, 0, "BUILD SUCCESSFUL")

        with (
            mock.patch.object(run_journey, "run", side_effect=fake_run),
            mock.patch.object(run_journey, "apply_precondition", return_value=(True, [], "")),
            mock.patch.object(
                run_journey,
                "collect_structured_results",
                return_value=run_journey.StructuredTestResult(),
            ),
            mock.patch.object(run_journey, "collect_screenshots", return_value=[]),
        ):
            result = run_journey.run_harness(
                harness, ":harness-app:journeyTest", "com.example", "device", 2, "/sdk", {}
            )

        self.assertEqual(run_journey.HARNESS_FAILED, result.status)

    def test_skip_build_does_not_require_source_project(self):
        """验证已安装 APK 模式无需源码目录，但仍校验包名、设备和测试证据。"""
        root = Path(tempfile.mkdtemp())
        harness = root / "harness"
        (harness / "harness-app" / "src" / "main" / "journeys").mkdir(parents=True)
        (harness / "gradlew").write_text("", encoding="utf-8")
        journeys = root / "cases"
        journeys.mkdir()
        (journeys / "home.xml").write_text(
            "<journey><action>Verify Home</action></journey>", encoding="utf-8"
        )
        result_path = root / "result.json"
        config = {
            "project_path": str(root / "missing-project"),
            "testing": {"journey_harness": {"app_package_name": "com.example"}},
        }
        harness_result = run_journey.HarnessRunResult(
            run_journey.PASS, 1, [], [], "", executed_tests=1, result_files=["TEST-home.xml"]
        )
        with (
            mock.patch.object(run_journey, "load_config", return_value=config),
            mock.patch.object(run_journey, "resolve_result_path", return_value=result_path),
            mock.patch.object(run_journey, "resolve_journeys_dir", return_value=journeys),
            mock.patch.object(run_journey, "resolve_android_sdk", return_value="/sdk"),
            mock.patch.object(run_journey, "choose_device", return_value=("device", None)),
            mock.patch.object(
                run_journey,
                "discover_journey_task",
                return_value=(":harness-app:journeyTest", None),
            ),
            mock.patch.object(run_journey, "verify_installed", return_value=(True, ["adb"])),
            mock.patch.object(run_journey, "run_harness", return_value=harness_result),
        ):
            exit_code = run_journey.main([
                "--config", str(root / "local.yaml"),
                "--harness-dir", str(harness),
                "--journeys-dir", str(journeys),
                "--ui-impact", "behavior",
                "--applicability", "FULL",
                "--covered-then", "BDD-001/T1",
                "--skip-build",
            ])

        self.assertEqual(0, exit_code)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(run_journey.PASS, payload["status"])
        self.assertEqual("FULL", payload["applicability"])
        self.assertEqual(["BDD-001/T1"], payload["covered_then_ids"])

    def test_redacts_deep_links_and_returns_timeout_as_environment_failure(self):
        """验证超时返回环境失败码，且命令与输出都不会泄漏 DeepLink 参数。"""
        command = ["adb", "shell", "am", "start", "-d", "sample://login?token=secret"]
        expired = subprocess.TimeoutExpired(command, timeout=1, output="sample://login?token=secret")
        with mock.patch.object(run_journey.subprocess, "run", side_effect=expired):
            result = run_journey.run(command, timeout=1)

        self.assertEqual(124, result.returncode)
        self.assertNotIn("secret", " ".join(result.command))
        self.assertNotIn("secret", result.output)

    def test_skips_journey_when_ui_is_not_applicable(self):
        """验证无 UI 与纯视觉需求在接触设备前返回对应跳过状态。"""
        no_ui = run_journey.skip_result("none")
        visual = run_journey.skip_result("visual")
        self.assertEqual(run_journey.SKIPPED_NO_UI, no_ui.status)
        self.assertEqual(run_journey.SKIPPED_VISUAL_ONLY, visual.status)
        self.assertEqual(0, no_ui.exit_code)
        self.assertEqual(0, visual.exit_code)
        self.assertIsNone(run_journey.skip_result("behavior"))


if __name__ == "__main__":
    unittest.main()
