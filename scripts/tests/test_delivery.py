#!/usr/bin/env python3
"""
================================================================================
脚本名称：test_delivery.py
用    途：验证 Android Delivery 核心脚本的确定性行为和职责边界。

覆盖范围：
1. 配置中的绝对/相对路径解析。
2. Word、Markdown、TXT 需求正文读取及明确失败行为。
3. 七类工程影响、第二轮条件能力候选、route 外部快照和输出，不把模糊子串当成业务结论。
4. 当前需求 Git 基线、连续需求修订、部分确认、撤回、删除处置和重复 init 安全性。
5. 重复 check-env 复用且校验配对起点，需求和计划未确认时不放行编码，只有明确的新串行需求才允许更换起点。
6. 四类 Git 变化、增删改状态、真实片段、最终代码摘要和独立 JSON 输出。

测试原则：
- 所有文件和 Git 仓库均创建在临时目录，不读取或修改真实项目状态。
- 只验证公开行为，不绑定脚本内部实现细节。
================================================================================
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
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
    classify_conditional_gate_candidates,
    classify_route_files,
    classify_route_impacts,
    cmd_check_env,
    cmd_confirm_plan,
    cmd_confirm_requirement_update,
    cmd_init,
    cmd_init_test_mapping,
    cmd_route,
    format_requirement_change,
    load_config,
    print_bdd_instruction,
    print_environment_rules,
    print_route_instructions,
    read_requirement,
    resolve_config_paths,
)
from ..fact_inbox import add_fact, load_fact_inbox, resolve_fact  # noqa: E402
from ..config_paths import (  # noqa: E402
    baseline_path_for_config,
    capabilities_path_for_config,
    delivery_snapshot_exclusions,
    evidence_directory_for_config,
    requirement_snapshot_path_for_config,
    route_impact_path_for_config,
    specialist_directory_for_config,
)
from ..git_changes import (  # noqa: E402
    GitChange,
    GitInspectionError,
    collect_changed_entries,
    collect_changed_files,
    current_delivery_snapshot,
    current_branch,
    current_head,
    load_baseline,
    write_baseline,
    working_tree_status,
)
from ..implementation_plan import (  # noqa: E402
    ImplementationPlanError,
    implementation_plan_path,
    plan_confirmation_receipt_path,
)
from ..impact_radius import impact_radius_path  # noqa: E402
from ..requirement_snapshot import (  # noqa: E402
    RequirementSnapshotError,
    apply_requirement_revision,
    load_requirement_snapshot,
    obligation_digest,
    requirement_digest,
    requirement_summary_digest,
    render_requirement_diff,
    write_requirement_snapshot,
)


def bdd_requirement(
    identifier: str = "BDD-001",
    title: str = "已确认需求",
    result: str = "系统展示预期结果",
) -> str:
    """Build the smallest canonical requirement accepted by command-level tests."""
    return (
        f"# {title}\n\n## BDD 场景\n\n### {identifier} {title}\n"
        f"Given 用户位于目标页面\nWhen 用户执行目标操作\nThen {result}\n\n"
        "## 待确认\n\n- 无\n"
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

    def test_delivery_snapshot_exclusions_are_shared(self) -> None:
        """验证 route 和 final 共用同一组交付文档排除路径。"""
        project = self.root / "project"
        requirement_dir = project / "document" / "2026-07-27-login"
        requirement_dir.mkdir(parents=True)

        excluded = delivery_snapshot_exclusions(project, requirement_dir)

        self.assertIn("document", excluded)
        self.assertIn("document/2026-07-27-login/test-results/delivery-result.json", excluded)
        self.assertIn("document/2026-07-27-login/test-results/delivery-summary.md", excluded)

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

    def test_external_state_keeps_baseline_and_derived_evidence_separate(self) -> None:
        """验证基线、需求、路由、能力和证据使用独立路径，且都在 requirement_dir/.state 下。"""
        import yaml as _yaml
        requirement_dir = self.root / "req"
        requirement_dir.mkdir()
        cfg = {"project_path": str(self.root), "requirement_dir": str(requirement_dir)}
        self.config_path.write_text(_yaml.safe_dump(cfg), encoding="utf-8")

        baseline = baseline_path_for_config(self.config_path)
        snapshot = requirement_snapshot_path_for_config(self.config_path)
        route = route_impact_path_for_config(self.config_path)
        capabilities = capabilities_path_for_config(self.config_path)
        evidence = evidence_directory_for_config(self.config_path)
        specialists = specialist_directory_for_config(
            self.config_path,
            "requirement-1",
            2,
            "a" * 64,
            "b" * 64,
        )

        # 所有状态都在 requirement_dir/.state 下，跟需求走。
        state_root = (requirement_dir / ".state").resolve()
        self.assertEqual(baseline.parent, state_root)
        self.assertEqual(baseline.name, "baseline.json")
        self.assertEqual(snapshot.name, "requirement-snapshot.json")
        self.assertEqual(route.name, "route-impact.json")
        self.assertEqual(capabilities.name, "capabilities.json")
        self.assertEqual(evidence.parent, state_root)
        self.assertEqual(evidence, specialists.parents[1])
        self.assertEqual("specialists", specialists.name)
        self.assertEqual(5, len({baseline, snapshot, route, capabilities, evidence}))


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


class UserInstructionTests(unittest.TestCase):
    """验证终端交给其他 AI 的需求阶段指令与主流程保持一致。"""

    def test_bdd_instruction_includes_existing_business_safety_rules(self) -> None:
        """验证确认前只读检查和基线复用等核心约束仍在精简指令中。"""
        output = io.StringIO()

        with redirect_stdout(output):
            print_bdd_instruction()

        text = output.getvalue()
        self.assertIn("先形成初步需求理解", text)
        self.assertIn("BDD-001", text)
        self.assertIn("Given/When/Then", text)
        self.assertIn("确认后不得编码", text)

    def test_bdd_instruction_converges_changes_before_first_confirmation(self) -> None:
        """验证首次确认前多轮增删改先汇总到文件的核心约束仍在精简指令中。"""
        output = io.StringIO()

        with redirect_stdout(output):
            print_bdd_instruction()

        text = output.getvalue()
        self.assertIn("先展示本轮变化摘要", text)
        self.assertIn("合并写回 requirement_file", text)
        self.assertIn("重新 init 读取", text)
        self.assertIn("纯确认", text)
        self.assertIn("先写实施计划和影响半径等待确认", text)
        self.assertIn("不得编码", text)

    def test_route_instruction_excludes_business_decisions_from_auto_fix(self) -> None:
        """验证 P0/P1 自动修复授权不会越过未确认的旧业务处置。"""
        output = io.StringIO()

        with redirect_stdout(output):
            print_route_instructions(["android-review-diff"])

        text = output.getvalue()
        self.assertIn("已确认范围内的 P0/P1 技术问题", text)
        self.assertIn("计划外旧业务影响", text)
        self.assertIn("必须先询问用户", text)
        self.assertIn("不得自动修复", text)


class RequirementSnapshotTests(unittest.TestCase):
    """验证已确认需求可以安全保存、比较，重复 init 不会破坏 Git 基线。"""

    def setUp(self) -> None:
        """创建需求、追溯表和外部状态文件，所有内容在测试结束后自动清理。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.requirement_dir = self.root / "requirement"
        self.requirement_dir.mkdir()
        self.requirement = self.requirement_dir / "requirement.md"
        self.requirement.write_text("登录失败显示错误\n", encoding="utf-8")
        self.snapshot = self.root / "requirement-snapshot.json"
        self.baseline = self.root / "delivery-baseline.json"

    def test_snapshot_round_trip_and_diff(self) -> None:
        """验证快照摘要可校验，并为中途新增内容生成稳定差异。"""
        write_requirement_snapshot(self.snapshot, self.requirement, "登录失败显示错误")
        payload = load_requirement_snapshot(self.snapshot)
        diff = render_requirement_diff(
            str(payload["content"]),
            "登录失败显示错误\n允许点击重试",
        )

        self.assertEqual(self.requirement.resolve(), Path(payload["requirement_path"]))
        self.assertIn("+允许点击重试", diff)
        self.assertEqual(0o600, stat.S_IMODE(self.snapshot.stat().st_mode))

    def test_init_rejects_incomplete_requirement_without_receipt(self) -> None:
        """一句话需求不能生成 init 收据或进入后续确认。"""
        self.requirement.write_text("失败时可重试\n", encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            self.assertRaises(DeliveryError),
        ):
            cmd_init(SimpleNamespace(config=str(self.root / "local.yaml")))

        self.assertFalse(
            (self.requirement_dir / ".state" / "requirement-init-receipt.json").exists()
        )

    def test_pending_chat_fact_blocks_requirement_confirmation(self) -> None:
        """行为性聊天补充必须先解决，不能凭聊天继续需求确认。"""
        content = bdd_requirement(result="显示错误")
        self.requirement.write_text(content, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        add_fact(self.requirement_dir / ".state" / "fact-inbox.json", "还要支持空数组")

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            self.assertRaisesRegex(DeliveryError, "聊天事实"),
        ):
            cmd_confirm_requirement_update(SimpleNamespace(
                config=str(self.root / "local.yaml"), revision_file=None,
            ))

    def test_confirmed_chat_fact_is_bound_only_after_new_requirement_revision(self) -> None:
        """确认事实后仍需写回需求并产生新 revision，随后才解除事实门禁。"""
        original = bdd_requirement(result="显示错误")
        changed = bdd_requirement(result="显示空数组时显示空状态")
        self.requirement.write_text(original, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot, self.requirement, original, requirement_id="baseline-1",
        )
        fact_path = self.requirement_dir / ".state" / "fact-inbox.json"
        fact = add_fact(fact_path, "还要支持空数组")
        resolve_fact(fact_path, fact["id"], "CONFIRMED", clear_missing=True)
        self.requirement.write_text(changed, encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        args = SimpleNamespace(config=str(self.root / "local.yaml"), revision_file=None)
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            self.assertRaises(DeliveryError),
        ):
            cmd_confirm_requirement_update(args)

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(io.StringIO()),
        ):
            cmd_init(SimpleNamespace(config=args.config))
            self.assertEqual(0, cmd_confirm_requirement_update(args))

        current = load_fact_inbox(fact_path)["facts"][0]
        self.assertEqual(1, current["materialized_revision"])
        self.assertEqual(requirement_digest(changed), current["materialized_requirement_sha256"])

    def test_changed_requirement_confirmation_requires_matching_init(self) -> None:
        """需求变化后跳过 init 时不能直接确认，读取同一 SHA 后才放行。"""
        original = bdd_requirement(result="显示错误")
        changed = bdd_requirement(result="显示重试入口")
        write_requirement_snapshot(
            self.snapshot, self.requirement, original, requirement_id="baseline-1",
        )
        self.requirement.write_text(changed, encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        args = SimpleNamespace(config=str(self.root / "local.yaml"), revision_file=None)
        patches = (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
        )
        with patches[0], patches[1], patches[2], self.assertRaises(DeliveryError):
            cmd_confirm_requirement_update(args)

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(io.StringIO()),
        ):
            cmd_init(SimpleNamespace(config=args.config))
            result = cmd_confirm_requirement_update(args)

        self.assertEqual(0, result)
        self.assertEqual(1, load_requirement_snapshot(self.snapshot)["revision"])

    def test_default_revision_manifest_is_not_silently_overwritten(self) -> None:
        """确认命令必须校验调用前清单，不能静默补回被删掉的义务。"""
        content = bdd_requirement(result="显示错误").replace(
            "\n## 待确认",
            "\n### BDD-002 重试\nGiven 页面显示错误\nWhen 用户点击重试\n"
            "Then 系统重新请求\n\n## 待确认",
        )
        self.requirement.write_text(content, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(io.StringIO()),
        ):
            cmd_init(SimpleNamespace(config=str(self.root / "local.yaml")))

        revision_file = self.requirement_dir / "test-cases" / "requirement-revision.json"
        manifest = json.loads(revision_file.read_text(encoding="utf-8"))
        manifest["changes"] = [
            item for item in manifest["changes"] if item["id"] != "BDD-002"
        ]
        revision_file.write_text(json.dumps(manifest), encoding="utf-8")

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            self.assertRaises(RequirementSnapshotError),
        ):
            cmd_confirm_requirement_update(SimpleNamespace(
                config=str(self.root / "local.yaml"), revision_file=None,
            ))

    def test_requirement_change_is_presented_in_chinese(self) -> None:
        """验证用户看到中文变化、确认状态和删除处置，不需要理解内部英文枚举。"""
        text = format_requirement_change({
            "id": "BDD-002",
            "change_type": "REMOVED",
            "decision": "CONFIRMED",
            "disposition": "KEEP_COMPATIBILITY",
        })

        self.assertEqual(
            "BDD-002：删除，已确认：只删除当前入口，保留兼容能力",
            text,
        )

    def test_environment_rules_separate_local_iteration_from_final_delivery(self) -> None:
        """验证需求确认后的终端提示不会把每次局部完善带回完整门禁。"""
        output = io.StringIO()

        with redirect_stdout(output):
            print_environment_rules()

        text = output.getvalue()
        self.assertIn("局部迭代", text)
        self.assertIn("不自动 route 或全量审查", text)
        self.assertIn("重新读取已确认的 requirement_file、需求快照/修订清单、实施计划、影响半径和测试映射", text)
        self.assertIn("追溯表只是机器生成视图", text)
        self.assertIn("旧聊天理解、旧总结或旧方案不得作为执行依据", text)
        self.assertIn("最终交付", text)
        self.assertIn("最终检查、完整交付或准备提交", text)
        self.assertNotIn("编译后：", text)

    def test_legacy_snapshot_upgrades_without_losing_confirmed_text(self) -> None:
        """验证已有 v1 外部快照可继续使用，并在下一次确认时安全升级。"""
        content = "登录失败显示错误"
        self.snapshot.write_text(json.dumps({
            "version": 1,
            "requirement_path": str(self.requirement.resolve()),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
            "created_at": "2026-07-19T00:00:00+00:00",
        }), encoding="utf-8")

        upgraded = load_requirement_snapshot(self.snapshot)

        self.assertEqual(2, upgraded["version"])
        self.assertEqual(content, upgraded["content"])
        self.assertEqual(0, upgraded["revision"])
        self.assertEqual("AWAITING_OBLIGATIONS", upgraded["status"])

    def _manifest(self, revision: int, changes: list[dict[str, object]]) -> dict[str, object]:
        """构造绑定当前需求集合的修订清单，减少各场景无关样板。"""
        return {
            "version": 1,
            "requirement_id": "baseline-1",
            "base_revision": revision,
            "scope": "SAME_REQUIREMENT",
            "changes": changes,
        }

    @staticmethod
    def _change(
        identifier: str,
        change_type: str,
        decision: str = "CONFIRMED",
        **extra: object,
    ) -> dict[str, object]:
        """生成一个原子需求变化，额外字段用于文本、原因和删除处置。"""
        return {
            "id": identifier,
            "change_type": change_type,
            "decision": decision,
            **extra,
        }

    def test_confirmed_revisions_compare_from_latest_version(self) -> None:
        """验证 R1→R2 确认后，下一次变化从 R2 而不是最初 R1 比较。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            requirement_id="baseline-1",
        )
        first, confirmed = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            self._manifest(0, [
                self._change(
                    "BDD-001", "ADDED", text="显示登录错误", required=True,
                ),
            ]),
        )
        self.assertTrue(confirmed)
        self.assertEqual(1, first["revision"])

        content_v2 = "登录失败显示错误\n允许点击重试"
        second, confirmed = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content_v2,
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", text="点击重试后重新请求", required=True,
                ),
            ]),
        )

        self.assertTrue(confirmed)
        self.assertEqual(2, second["revision"])
        diff = render_requirement_diff(second["content"], content_v2 + "\n重试失败仍显示错误")
        self.assertNotIn("+允许点击重试", diff)
        self.assertIn("+重试失败仍显示错误", diff)

    def test_pending_or_conflict_does_not_advance_confirmed_revision(self) -> None:
        """验证部分确认和冲突只保存候选，最近确认正文、义务和版本保持不变。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            requirement_id="baseline-1",
        )
        confirmed, _ = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            self._manifest(0, [
                self._change(
                    "BDD-001", "ADDED", text="显示登录错误", required=True,
                ),
            ]),
        )
        candidate_content = "登录失败显示错误\n允许点击重试"
        pending, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            candidate_content,
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", "PENDING",
                    text="点击重试后重新请求", required=True, reason="重试次数待确认",
                ),
            ]),
        )

        self.assertFalse(applied)
        self.assertEqual(confirmed["revision"], pending["revision"])
        self.assertEqual(confirmed["sha256"], pending["sha256"])
        self.assertEqual("PENDING_CONFIRMATION", pending["status"])
        self.assertEqual("BDD-002", pending["pending_changes"][1]["id"])

    def test_resolves_pending_and_preserves_rejected_items_outside_total(self) -> None:
        """验证待定项解决后推进修订，而明确拒绝的新义务不会进入有效集合。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            self._manifest(0, [
                self._change(
                    "BDD-001", "ADDED", text="显示登录错误", required=True,
                ),
            ]),
        )
        candidate_content = "登录失败显示错误\n允许点击重试"
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            candidate_content,
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", "PENDING",
                    text="点击重试后重新请求", required=True, reason="等待确认",
                ),
            ]),
        )
        resolved, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            candidate_content,
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", text="点击重试后重新请求", required=True,
                ),
                self._change(
                    "BDD-003", "ADDED", "REJECTED",
                    text="失败后无限重试", required=True, reason="会造成请求风暴",
                ),
            ]),
        )

        self.assertTrue(applied)
        self.assertEqual(2, resolved["revision"])
        self.assertEqual(["BDD-001", "BDD-002"], [
            item["id"] for item in resolved["obligations"]
        ])

    def test_withdrawn_pending_change_keeps_previous_total(self) -> None:
        """验证用户撤回待定补充后，旧总需求保留且候选义务不会进入有效集合。"""
        write_requirement_snapshot(
            self.snapshot, self.requirement, "显示错误", requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误\n允许重试",
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", "PENDING",
                    text="允许重试", required=True, reason="用户尚未决定",
                ),
            ]),
        )
        restored, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", "REJECTED",
                    text="允许重试", required=True, reason="用户撤回补充",
                ),
            ]),
        )

        self.assertTrue(applied)
        self.assertEqual(["BDD-001"], [item["id"] for item in restored["obligations"]])
        self.assertEqual("显示错误", restored["content"])

    def test_init_prints_resume_brief_and_flow_position(self) -> None:
        """续接旧需求时，init 打印续接摘要块和当前流程位置（半状态驱动）。"""
        content = bdd_requirement(result="显示错误")
        self.requirement.write_text(content, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
            config_path=str(self.root / "local.yaml"),
            test_mapping_path=self.requirement_dir / "test-cases" / "test-mapping.json",
            resume_guide_path=self.requirement_dir / "续接指南.md",
        )
        output = io.StringIO()
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(output),
        ):
            cmd_init(SimpleNamespace(config=str(self.root / "local.yaml")))
        text = output.getvalue()
        # 优化1：续接摘要块强制 AI 第一眼进入状态。
        self.assertIn("续接旧需求", text)
        self.assertIn("计划：尚未确认或已失效", text)
        # 优化2：流程位置指示器。
        self.assertIn("当前流程位置", text)
        self.assertIn("confirm-plan", text)

    def test_conflict_and_new_serial_requirement_are_blocked(self) -> None:
        """验证业务冲突不推进版本，新串行需求不能混入当前 Git 基线。"""
        write_requirement_snapshot(
            self.snapshot, self.requirement, "显示错误", requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        conflict, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误\n自动重试",
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "ADDED", "CONFLICT",
                    text="自动重试", required=True, reason="与禁止重复请求冲突",
                ),
            ]),
        )
        self.assertFalse(applied)
        self.assertEqual(1, conflict["revision"])

        serial = self._manifest(1, [self._change("BDD-001", "UNCHANGED")])
        serial["scope"] = "NEW_SERIAL_REQUIREMENT"
        with self.assertRaisesRegex(
            RequirementSnapshotError,
            "check-env --new-requirement",
        ):
            apply_requirement_revision(
                self.snapshot, self.requirement, "显示错误", serial,
            )

    def test_superseded_obligation_requires_confirmed_replacement(self) -> None:
        """验证被替代的旧 Then 只有在同轮新增替代义务时才能退出有效集合。"""
        write_requirement_snapshot(
            self.snapshot, self.requirement, "显示错误", requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        with self.assertRaisesRegex(RequirementSnapshotError, "同轮已确认 ADDED"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                "显示可重试错误",
                self._manifest(1, [
                    self._change(
                        "BDD-001", "SUPERSEDED", replacement_id="BDD-002",
                    ),
                ]),
            )

        updated, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示可重试错误",
            self._manifest(1, [
                self._change(
                    "BDD-001", "SUPERSEDED", replacement_id="BDD-002",
                ),
                self._change(
                    "BDD-002", "ADDED", text="显示错误并允许重试", required=True,
                ),
            ]),
        )
        self.assertTrue(applied)
        self.assertEqual(["BDD-002"], [item["id"] for item in updated["obligations"]])

    def test_chat_only_semantic_change_and_interrupted_write_are_safe(self) -> None:
        """验证未同步需求文件和确认写入中断都不会覆盖最近确认修订。"""
        write_requirement_snapshot(
            self.snapshot, self.requirement, "显示错误", requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        manifest = self._manifest(1, [
            self._change(
                "BDD-001", "CHANGED", text="显示错误并允许重试", required=True,
            ),
        ])
        with self.assertRaisesRegex(RequirementSnapshotError, "requirement_file 未更新"):
            apply_requirement_revision(
                self.snapshot, self.requirement, "显示错误", manifest,
            )

        before = self.snapshot.read_bytes()
        with (
            mock.patch(
                "scripts.requirement_snapshot._atomic_write",
                side_effect=RequirementSnapshotError("write interrupted"),
            ),
            self.assertRaisesRegex(RequirementSnapshotError, "write interrupted"),
        ):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                "显示错误并允许重试",
                manifest,
            )
        self.assertEqual(before, self.snapshot.read_bytes())

    def test_manifest_must_cover_bdd_ids_written_in_requirement_file(self) -> None:
        """验证需求正文已列出的 Then ID 不能被修订清单遗漏。"""
        content = "BDD-001 显示错误\nBDD-002 允许重试"
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )

        with self.assertRaisesRegex(RequirementSnapshotError, "未进入修订清单"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                content,
                self._manifest(0, [
                    self._change("BDD-001", "ADDED", text="显示错误", required=True),
                ]),
            )

    def test_can_backfill_omitted_bdd_when_text_already_in_requirement_file(self) -> None:
        """验证漏拆补录只要来自既有需求正文，就不会被误判为聊天脑补。"""
        content = "登录失败显示错误\n允许点击重试"
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="登录失败显示错误", required=True),
            ]),
        )

        updated, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change("BDD-002", "ADDED", text="允许点击重试", required=True),
            ]),
        )

        self.assertTrue(applied)
        self.assertEqual(["BDD-001", "BDD-002"], [
            item["id"] for item in updated["obligations"]
        ])

    def test_rejects_ungrounded_bdd_backfill_without_requirement_update(self) -> None:
        """验证未写入需求正文的新语义仍必须先同步 requirement_file。"""
        content = "登录失败显示错误\n允许点击重试"
        write_requirement_snapshot(
            self.snapshot, self.requirement, content, requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="登录失败显示错误", required=True),
            ]),
        )

        with self.assertRaisesRegex(RequirementSnapshotError, "requirement_file 未更新"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                content,
                self._manifest(1, [
                    self._change("BDD-001", "UNCHANGED"),
                    self._change("BDD-002", "ADDED", text="失败后自动重试三次", required=True),
                ]),
            )

    def test_removal_requires_disposition_and_updates_active_obligations(self) -> None:
        """验证删除已实现需求必须声明处置，确认后才从最终义务集合移除。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "显示错误并允许重试",
            requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误并允许重试",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
                self._change("BDD-002", "ADDED", text="允许重试", required=True),
            ]),
        )
        with self.assertRaisesRegex(RequirementSnapshotError, "删除处置"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                "只显示错误",
                self._manifest(1, [
                    self._change("BDD-001", "UNCHANGED"),
                    self._change("BDD-002", "REMOVED"),
                ]),
            )

        updated, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "只显示错误",
            self._manifest(1, [
                self._change("BDD-001", "UNCHANGED"),
                self._change(
                    "BDD-002", "REMOVED", disposition="KEEP_COMPATIBILITY",
                ),
            ]),
        )
        self.assertTrue(applied)
        self.assertEqual(["BDD-001"], [item["id"] for item in updated["obligations"]])

    def test_stale_or_incomplete_manifest_cannot_overwrite_revision(self) -> None:
        """验证旧版本清单和漏掉既有义务的清单都会被阻断。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "显示错误",
            requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        with self.assertRaisesRegex(RequirementSnapshotError, "base_revision 已过期"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                "显示错误",
                self._manifest(0, [self._change("BDD-001", "UNCHANGED")]),
            )
        with self.assertRaisesRegex(RequirementSnapshotError, "没有处理既有义务"):
            apply_requirement_revision(
                self.snapshot,
                self.requirement,
                "显示错误\n新增入口",
                self._manifest(1, [
                    self._change("BDD-004", "ADDED", text="显示入口", required=True),
                ]),
            )

    def test_obligation_digest_changes_with_then_semantics(self) -> None:
        """验证同一 Then ID 的文本或必需性变化会使旧证据摘要失效。"""
        before = obligation_digest("BDD-001", "显示错误", True)
        after = obligation_digest("BDD-001", "显示错误并允许重试", True)
        optional = obligation_digest("BDD-001", "显示错误", False)

        self.assertNotEqual(before, after)
        self.assertNotEqual(before, optional)

    def test_reconfirming_unchanged_total_is_idempotent(self) -> None:
        """验证重复确认同一总需求不会制造空修订或使现有报告无意义失效。"""
        write_requirement_snapshot(
            self.snapshot, self.requirement, "显示错误", requirement_id="baseline-1",
        )
        first, _ = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示错误", required=True),
            ]),
        )
        repeated, applied = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误",
            self._manifest(1, [self._change("BDD-001", "UNCHANGED")]),
        )

        self.assertTrue(applied)
        self.assertEqual(first["revision"], repeated["revision"])
        self.assertEqual(first["history"], repeated["history"])

    def test_format_only_update_keeps_semantic_revision(self) -> None:
        """验证用户确认的纯排版变化只同步正文摘要，不改变 Then 或语义修订号。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "显示错误\n允许重试",
            requirement_id="baseline-1",
        )
        first, _ = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "显示错误\n允许重试",
            self._manifest(0, [
                self._change(
                    "BDD-001", "ADDED", text="显示错误并允许重试", required=True,
                ),
            ]),
        )
        manifest = self._manifest(1, [self._change("BDD-001", "UNCHANGED")])
        manifest["format_only"] = True
        formatted, applied = apply_requirement_revision(
            self.snapshot, self.requirement, "显示错误\n\n允许重试", manifest,
        )

        self.assertTrue(applied)
        self.assertEqual(first["revision"], formatted["revision"])
        self.assertEqual(first["obligations"], formatted["obligations"])

    def test_repeated_init_reports_change_without_deleting_baseline(self) -> None:
        """验证编码中重复读取需求会输出增量上下文，并完整保留原 Git 基线。"""
        original = bdd_requirement(result="显示登录错误")
        changed = bdd_requirement(result="显示登录重试入口")
        self.requirement.write_text(changed, encoding="utf-8")
        write_requirement_snapshot(self.snapshot, self.requirement, original)
        traceability = self.requirement_dir / "test-cases" / "traceability.md"
        traceability.parent.mkdir()
        traceability.write_text("BDD-001 | COVERED_AUTOMATED\n", encoding="utf-8")
        self.baseline.write_text('{"id":"keep-me"}\n', encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        output = io.StringIO()
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(output),
        ):
            cmd_init(SimpleNamespace(config=str(self.root / "local.yaml")))

        self.assertEqual('{"id":"keep-me"}\n', self.baseline.read_text(encoding="utf-8"))
        text = output.getvalue()
        self.assertIn("需求变化候选", text)
        self.assertIn("+Then 显示登录重试入口", text)
        self.assertIn("BDD-001", text)
        self.assertNotIn("COVERED_AUTOMATED", text)
        self.assertIn("当前正文：存在未确认变化", text)
        self.assertNotIn("可直接进入编码", text)
        self.assertIn("新增、修改、删除、未变化", text)
        self.assertIn("check-env --new-requirement", text)

    def test_confirm_command_never_changes_git_baseline(self) -> None:
        """验证独立需求确认只更新修订快照，不覆盖当前需求 Git 起点。"""
        content = bdd_requirement(result="显示登录错误")
        self.requirement.write_text(content, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            content,
            requirement_id="baseline-1",
        )
        revision_file = self.requirement_dir / "test-cases" / "requirement-revision.json"
        revision_file.parent.mkdir(exist_ok=True)
        revision_file.write_text(json.dumps(self._manifest(0, [
            self._change("BDD-001", "ADDED", text="显示登录错误", required=True),
        ])), encoding="utf-8")
        self.baseline.write_text('{"id":"keep-me"}\n', encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        output = io.StringIO()
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(output),
        ):
            result = cmd_confirm_requirement_update(SimpleNamespace(
                config=str(self.root / "local.yaml"),
                revision_file=str(revision_file),
            ))

        self.assertEqual(0, result)
        self.assertEqual('{"id":"keep-me"}\n', self.baseline.read_text(encoding="utf-8"))
        text = output.getvalue()
        self.assertIn("你主要看:", text)
        self.assertIn("需求文件:", text)
        self.assertIn(str(self.requirement), text)
        self.assertIn("本轮变化摘要: 新增 1 项", text)
        self.assertIn("拆分测试并生成实施计划和影响半径前必须重新读取", text)
        self.assertIn("AI 执行前必须读取（只展示路径，不展示正文）", text)
        self.assertIn("需求修订清单:", text)
        self.assertIn("requirement-revision.json", text)
        self.assertIn("机器生成追溯视图（只读辅助）:", text)
        self.assertIn("traceability.md", text)
        self.assertIn("进入计划阶段", text)
        self.assertIn("实施计划.md", text)
        self.assertIn("等待确认", text)
        self.assertNotIn("已获准开始编码", text)
        self.assertNotIn("显示登录错误", text)
        self.assertNotIn("内容摘要", text)
        self.assertIn("确认前旧聊天理解、旧总结或旧方案不得作为执行依据", text)
        # 补丁A：确认需求修订后应自动刷新续接指南等 人读 md。
        self.assertTrue((self.requirement.parent / "续接指南.md").is_file())
        resume = (self.requirement.parent / "续接指南.md").read_text(encoding="utf-8")
        self.assertIn("续接指南", resume)
        # 补丁B：本轮 manifest 的波及清单应写进续接指南。
        self.assertIn("波及清单", resume)

    def test_confirm_plan_is_the_only_step_that_authorizes_coding(self) -> None:
        """验证需求确认只进入只读计划，用户确认计划后才输出编码授权。"""
        content = bdd_requirement(result="显示登录错误")
        self.requirement.write_text(content, encoding="utf-8")
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            content,
            requirement_id="baseline-1",
        )
        manifest = self._manifest(0, [
            self._change("BDD-001", "ADDED", text="显示登录错误", required=True),
        ])
        applied_snapshot, _ = apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            manifest,
        )
        implementation_plan_path(self.requirement_dir).write_text(
            """# 实施计划

## 实现范围
- 修改错误提示。
## 已上线业务影响
- 成功登录保持不变。
## 预计修改文件
- `LoginViewModel.kt`
## 测试方案
- 增加失败分支测试。
## 影响半径摘要
- 允许文件：LoginViewModel.kt。
- 允许目录前缀：无。
## 明确不修改范围
- 不修改接口。
""",
            encoding="utf-8",
        )
        impact_radius_path(self.requirement_dir).parent.mkdir(parents=True, exist_ok=True)
        impact_radius_path(self.requirement_dir).write_text(
            json.dumps({
                "version": 1,
                "generated_at": "2026-07-27T00:00:00+00:00",
                "requirement_id": applied_snapshot["requirement_id"],
                "requirement_revision": applied_snapshot["revision"],
                "requirement_file_sha256": requirement_digest(content),
                "requirement_summary_sha256": requirement_summary_digest(applied_snapshot),
                "allowed_files": ["LoginViewModel.kt"],
                "allowed_dirs": [],
                "impacts": [{
                    "id": "BDD-001",
                    "change_type": "ADDED",
                    "reason": "只修改登录错误提示。",
                    "risk_level": "L1",
                    "expected_files": ["LoginViewModel.kt"],
                    "expected_tests": ["LoginViewModelTest#failure"],
                    "affected_modules": [":app"],
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        paths = SimpleNamespace(
            project_path=self.root / "project",
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
        )
        output = io.StringIO()
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(output),
        ):
            result = cmd_confirm_plan(SimpleNamespace(config=str(self.root / "local.yaml")))

        self.assertEqual(0, result)
        self.assertTrue(plan_confirmation_receipt_path(self.requirement_dir).is_file())
        text = output.getvalue()
        self.assertIn("实施计划已确认", text)
        self.assertIn("影响半径已确认", text)
        self.assertIn("先建立测试映射并用业务断言得到 Red", text)
        self.assertIn("已确认实施计划", text)

        implementation_plan_path(self.requirement_dir).write_text(
            implementation_plan_path(self.requirement_dir).read_text(encoding="utf-8")
            + "\n- 新增实现步骤。\n",
            encoding="utf-8",
        )
        changed_output = io.StringIO()
        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            redirect_stdout(changed_output),
        ):
            cmd_init(SimpleNamespace(config=str(self.root / "local.yaml")))

        changed_text = changed_output.getvalue()
        self.assertIn("计划：尚未确认或已失效", changed_text)
        self.assertIn("展示实施计划.md 并 confirm-plan", changed_text)
        self.assertNotIn("可直接进入编码", changed_text)

    def test_test_mapping_rejects_unconfirmed_requirement_content(self) -> None:
        """需求正文变化但未确认时，独立 mapping validate 也必须阻断。"""
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            "登录失败显示错误",
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示登录错误", required=True),
            ]),
        )
        self.requirement.write_text("登录失败显示错误\n允许点击重试\n", encoding="utf-8")
        paths = SimpleNamespace(
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
            test_mapping_path=self.requirement_dir / "test-cases" / "test-mapping.json",
        )

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            self.assertRaisesRegex(DeliveryError, "尚未确认为最新修订"),
        ):
            cmd_init_test_mapping(SimpleNamespace(
                config=str(self.root / "local.yaml"),
                validate=True,
            ))

    def test_test_mapping_requires_current_plan_confirmation(self) -> None:
        """测试映射必须位于计划确认之后，防止跳过影响半径和不修改范围。"""
        content = "登录失败显示错误"
        write_requirement_snapshot(
            self.snapshot,
            self.requirement,
            content,
            requirement_id="baseline-1",
        )
        apply_requirement_revision(
            self.snapshot,
            self.requirement,
            content,
            self._manifest(0, [
                self._change("BDD-001", "ADDED", text="显示登录错误", required=True),
            ]),
        )
        paths = SimpleNamespace(
            requirement_path=self.requirement,
            requirement_dir=self.requirement_dir,
            test_mapping_path=self.requirement_dir / "test-cases" / "test-mapping.json",
        )

        with (
            mock.patch("scripts.delivery.load_config", return_value={}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=self.snapshot,
            ),
            self.assertRaisesRegex(ImplementationPlanError, "尚未生成实施计划"),
        ):
            cmd_init_test_mapping(SimpleNamespace(
                config=str(self.root / "local.yaml"),
                validate=False,
            ))


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

    def test_ignores_document_and_test_text_for_production_impacts(self) -> None:
        """验证审计文档和测试文本不触发 data/system 生产专项。"""
        files = [
            "document/audit/DatabaseMigration.md",
            "app/src/test/java/example/DatabaseServiceTest.kt",
        ]
        impacts = classify_route_impacts(
            files,
            route_signals={
                files[0]: "Migration( and NotificationManager are audit keywords",
                files[1]: "// Migration( and NotificationManager are test text\n",
            },
        )

        self.assertEqual([], impacts["data"])
        self.assertEqual([], impacts["system"])
        self.assertEqual([files[1]], impacts["tests"])

    def test_maps_engineering_impacts_to_conditional_gates(self) -> None:
        """验证第二轮只映射确定候选，泄漏和性能始终保留给 AI 语义终判。"""
        gates = classify_conditional_gate_candidates({
            "ui": ["HomeScreen.kt"],
            "api": ["UserApi.kt"],
            "data": ["UserDao.kt"],
            "system": [],
        })

        self.assertTrue(gates["openapi"])
        self.assertTrue(gates["migration"])
        self.assertTrue(gates["ui_a11y"])
        self.assertTrue(gates["security_privacy"])
        self.assertIsNone(gates["dynamic_leak"])
        self.assertIsNone(gates["performance"])

        no_candidates = classify_conditional_gate_candidates({
            "ui": [], "api": [], "data": [], "system": [],
        })
        self.assertFalse(no_candidates["openapi"])
        self.assertFalse(no_candidates["migration"])
        self.assertFalse(no_candidates["ui_a11y"])
        self.assertFalse(no_candidates["security_privacy"])


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
        self.write(
            "app/src/main/java/example/Client.kt",
            '@GET("users")\nfun users(): String\n',
        )
        self.write("app/src/main/java/example/LegacyWorker.kt", "class LegacyWorker\n")
        self.git("add", "baseline.txt")
        self.git("add", "app/src/main/java/example/Client.kt")
        self.git("add", "app/src/main/java/example/LegacyWorker.kt")
        self.git("commit", "-q", "-m", "baseline")
        self.git("checkout", "-q", "-b", "feature")

        # 需求基线建立在编码前，后续 commit 和工作区变化都应归入本次范围。
        self.baseline = Path(self.temp_dir.name) / "delivery-baseline.json"
        write_baseline(self.repo, self.baseline)

        # 删除和重命名必须保留旧片段/旧路径，不能因当前文件不存在而漏掉路由。
        (self.repo / "app/src/main/java/example/Client.kt").unlink()
        self.git(
            "mv",
            "app/src/main/java/example/LegacyWorker.kt",
            "app/src/main/java/example/RenamedWorker.kt",
        )

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

    def test_collects_delete_rename_patch_and_updates_snapshot(self) -> None:
        """验证删除/重命名状态与旧代码片段可供路由使用，代码变化使摘要失效。"""
        before = current_delivery_snapshot(self.repo, self.baseline)["snapshot_sha256"]
        changes, warnings = collect_changed_entries(self.repo, self.baseline)
        by_path = {change.path: change for change in changes}

        self.assertEqual([], warnings)
        deleted = by_path["app/src/main/java/example/Client.kt"]
        renamed = by_path["app/src/main/java/example/RenamedWorker.kt"]
        self.assertEqual("D", deleted.status)
        self.assertIn('@GET("users")', deleted.patch)
        self.assertEqual("R", renamed.status)
        self.assertEqual("app/src/main/java/example/LegacyWorker.kt", renamed.old_path)
        impacts = classify_route_impacts(
            list(by_path),
            project_root=self.repo,
            route_signals={path: change.patch for path, change in by_path.items()},
        )
        self.assertIn("app/src/main/java/example/Client.kt", impacts["api"])

        self.write("delivery-result.json", "self report\n")
        excluded = current_delivery_snapshot(
            self.repo,
            self.baseline,
            exclude_paths={"delivery-result.json"},
        )["snapshot_sha256"]
        self.assertEqual(before, excluded)

        self.write("another.txt", "changes snapshot\n")
        after = current_delivery_snapshot(self.repo, self.baseline)["snapshot_sha256"]
        self.assertNotEqual(before, after)

    def test_reports_branch_and_working_tree_without_modifying_them(self) -> None:
        """验证只读 Git 辅助方法能报告分支和脏状态且不改变仓库。"""
        self.assertEqual(current_branch(self.repo), "feature")
        status = working_tree_status(self.repo)
        self.assertIn("Mixed.kt", status)
        self.assertIn("app/src/main/res/", status)
        expanded_status = working_tree_status(self.repo, untracked_files="all")
        self.assertIn("app/src/main/res/layout/untracked.xml", expanded_status)
        with self.assertRaisesRegex(GitInspectionError, "untracked_files"):
            working_tree_status(self.repo, untracked_files="invalid")

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
        requirement = Path(self.temp_dir.name) / "requirement.md"
        content = bdd_requirement()
        requirement.write_text(content, encoding="utf-8")
        check_baseline = Path(self.temp_dir.name) / "check-env-baseline.json"
        snapshot = Path(self.temp_dir.name) / "requirement-snapshot.json"
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )
        patches = (
            mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
            mock.patch("scripts.delivery.resolve_paths", return_value=paths),
            mock.patch("scripts.delivery.baseline_path_for_config", return_value=check_baseline),
            mock.patch(
                "scripts.delivery.requirement_snapshot_path_for_config",
                return_value=snapshot,
            ),
        )
        old_cwd = Path.cwd()
        try:
            with patches[0], patches[1], patches[2], patches[3], redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(DeliveryError, "无法建立不串需求的基线"):
                    cmd_check_env(args)

            self.git("add", ".")
            self.git("commit", "-q", "-m", "current requirement prepared")
            with patches[0], patches[1], patches[2], patches[3], redirect_stdout(io.StringIO()):
                cmd_check_env(args)
            self.assertEqual(current_branch(self.repo), load_baseline(self.repo, check_baseline)["branch"])
            self.assertEqual(content.strip(), load_requirement_snapshot(snapshot)["content"])
        finally:
            os.chdir(old_cwd)

    def test_check_env_rejects_requirement_without_atomic_bdd(self) -> None:
        """不完整需求不能建立 Git 基线或需求快照。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare clean tree")
        requirement = Path(self.temp_dir.name) / "incomplete-requirement.md"
        requirement.write_text("需求还没确认，边界条件待补。\n", encoding="utf-8")
        baseline = Path(self.temp_dir.name) / "incomplete-baseline.json"
        snapshot = Path(self.temp_dir.name) / "incomplete-snapshot.json"
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )

        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DeliveryError, "BDD-001 场景名称"),
            ):
                cmd_check_env(SimpleNamespace(
                    config=str(Path(self.temp_dir.name) / "local.yaml"),
                    new_requirement=False,
                ))
        finally:
            os.chdir(old_cwd)

        self.assertFalse(baseline.exists())
        self.assertFalse(snapshot.exists())

    def test_check_env_allows_current_document_evidence_without_code_dirty(self) -> None:
        """验证任一 document/<需求>/ 的交付证据都不阻断代码基线。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare clean tree")
        requirement_dir = self.repo / "document" / "2026-07-28-login"
        requirement_dir.mkdir(parents=True)
        requirement = requirement_dir / "需求说明.md"
        content = bdd_requirement()
        requirement.write_text(content, encoding="utf-8")
        (requirement_dir / "issues.md").write_text("审计记录\n", encoding="utf-8")
        other_requirement = self.repo / "document" / "2026-07-27-other"
        other_requirement.mkdir(parents=True)
        (other_requirement / "审计记录.md").write_text("其他需求记录\n", encoding="utf-8")
        baseline = Path(self.temp_dir.name) / "document-baseline.json"
        snapshot = Path(self.temp_dir.name) / "document-snapshot.json"
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement_dir,
        )
        args = SimpleNamespace(
            config=str(Path(self.temp_dir.name) / "local.yaml"),
            new_requirement=False,
        )
        output = io.StringIO()
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
                redirect_stdout(output),
            ):
                cmd_check_env(args)
        finally:
            os.chdir(old_cwd)

        self.assertIn("交付文档改动已忽略", output.getvalue())
        self.assertEqual(content.strip(), load_requirement_snapshot(snapshot)["content"])
        self.assertEqual(current_head(self.repo), load_baseline(self.repo, baseline)["head"])

    def test_check_env_reuses_existing_start_after_intermediate_commit(self) -> None:
        """验证中途提交后重复检查只复用原起点，不隐藏已经提交的需求改动。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare clean tree")
        requirement = Path(self.temp_dir.name) / "requirement.md"
        requirement.write_text(bdd_requirement(title="同一需求"), encoding="utf-8")
        baseline = Path(self.temp_dir.name) / "check-env-reuse-baseline.json"
        snapshot = Path(self.temp_dir.name) / "check-env-reuse-snapshot.json"
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )
        args = SimpleNamespace(
            config=str(Path(self.temp_dir.name) / "local.yaml"),
            new_requirement=False,
        )
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch(
                    "scripts.delivery.load_config",
                    return_value={"branch": "feature"},
                ),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
                redirect_stdout(io.StringIO()),
            ):
                cmd_check_env(args)
                original_baseline = baseline.read_bytes()
                original_snapshot = snapshot.read_bytes()
                original_head = load_baseline(self.repo, baseline)["head"]

                self.write("app/src/main/java/example/Later.kt", "class Later\n")
                self.git("add", ".")
                self.git("commit", "-q", "-m", "intermediate requirement work")
                output = io.StringIO()
                with redirect_stdout(output):
                    cmd_check_env(args)

            self.assertIn("复用且不重建基线", output.getvalue())
            self.assertIn(
                "未成功执行 confirm-requirement-update 前不得编码",
                output.getvalue(),
            )
            self.assertNotIn("继续当前需求的编码或局部迭代", output.getvalue())
            self.assertEqual(original_baseline, baseline.read_bytes())
            self.assertEqual(original_snapshot, snapshot.read_bytes())
            self.assertEqual(original_head, load_baseline(self.repo, baseline)["head"])
            self.assertNotEqual(original_head, current_head(self.repo))
        finally:
            os.chdir(old_cwd)

    def test_check_env_rejects_mismatched_baseline_and_requirement_snapshot(self) -> None:
        """验证两份状态各自合法但需求 ID 不配对时停止，不拼接成错误起点。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare clean tree")
        requirement = Path(self.temp_dir.name) / "requirement.md"
        requirement.write_text("同一需求\n", encoding="utf-8")
        baseline = Path(self.temp_dir.name) / "check-env-mismatch-baseline.json"
        snapshot = Path(self.temp_dir.name) / "check-env-mismatch-snapshot.json"
        write_baseline(self.repo, baseline)
        write_requirement_snapshot(
            snapshot,
            requirement,
            "同一需求",
            requirement_id="another-requirement",
        )
        original_baseline = baseline.read_bytes()
        original_snapshot = snapshot.read_bytes()
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )
        args = SimpleNamespace(
            config=str(Path(self.temp_dir.name) / "local.yaml"),
            new_requirement=False,
        )
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch(
                    "scripts.delivery.load_config",
                    return_value={"branch": "feature"},
                ),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
                redirect_stdout(io.StringIO()),
            ):
                with self.assertRaisesRegex(DeliveryError, "不属于同一需求"):
                    cmd_check_env(args)
        finally:
            os.chdir(old_cwd)
        self.assertEqual(original_baseline, baseline.read_bytes())
        self.assertEqual(original_snapshot, snapshot.read_bytes())

    def test_check_env_replaces_start_only_for_explicit_new_requirement(self) -> None:
        """验证明确的新串行需求可以在干净工作区安全建立新起点。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare first requirement")
        requirement = Path(self.temp_dir.name) / "requirement.md"
        requirement.write_text(bdd_requirement(title="第一个需求"), encoding="utf-8")
        baseline = Path(self.temp_dir.name) / "check-env-new-baseline.json"
        snapshot = Path(self.temp_dir.name) / "check-env-new-snapshot.json"
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )
        args = SimpleNamespace(
            config=str(Path(self.temp_dir.name) / "local.yaml"),
            new_requirement=False,
        )
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=snapshot,
                ),
                redirect_stdout(io.StringIO()),
            ):
                cmd_check_env(args)
                original_id = load_baseline(self.repo, baseline)["id"]
                self.write("app/src/main/java/example/FirstDone.kt", "class FirstDone\n")
                self.git("add", ".")
                self.git("commit", "-q", "-m", "finish first requirement")
                second_content = bdd_requirement("BDD-004", "第二个需求")
                requirement.write_text(second_content, encoding="utf-8")
                args.new_requirement = True
                cmd_check_env(args)

            updated = load_baseline(self.repo, baseline)
            self.assertNotEqual(original_id, updated["id"])
            self.assertEqual(current_head(self.repo), updated["head"])
            self.assertEqual(second_content.strip(), load_requirement_snapshot(snapshot)["content"])
        finally:
            os.chdir(old_cwd)

    def test_check_env_restores_previous_baseline_when_snapshot_fails(self) -> None:
        """验证需求快照写入失败时恢复旧基线，不能让一次环境故障破坏当前起点。"""
        self.git("add", ".")
        self.git("commit", "-q", "-m", "prepare clean tree")
        previous = b'{"id":"previous-baseline"}\n'
        self.baseline.write_bytes(previous)
        requirement = Path(self.temp_dir.name) / "requirement.md"
        requirement.write_text(bdd_requirement(), encoding="utf-8")
        paths = SimpleNamespace(
            project_path=self.repo,
            requirement_path=requirement,
            requirement_dir=requirement.parent,
        )
        args = SimpleNamespace(
            config=str(Path(self.temp_dir.name) / "local.yaml"),
            new_requirement=True,
        )
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value={"branch": "feature"}),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=self.baseline),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=self.baseline.with_name("requirement-snapshot.json"),
                ),
                mock.patch(
                    "scripts.delivery.write_requirement_snapshot",
                    side_effect=RequirementSnapshotError("snapshot failed"),
                ),
                redirect_stdout(io.StringIO()),
            ):
                with self.assertRaisesRegex(DeliveryError, "snapshot failed"):
                    cmd_check_env(args)
        finally:
            os.chdir(old_cwd)

        self.assertEqual(previous, self.baseline.read_bytes())


class RouteCommandTests(unittest.TestCase):
    """验证 route 最终输出真实候选对应的专项 Skill。"""

    def setUp(self) -> None:
        """为路由输出用例创建隔离项目目录。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.requirement = self.root / "requirement.md"
        self.requirement.write_text("修改首页、用户接口和本地数据。\n", encoding="utf-8")

    def _run_route_with_changes(
        self,
        changes: list[GitChange],
        *,
        requirement_dir: Path | None = None,
        config: dict | None = None,
        allowed_files: list[str] | None = None,
    ) -> tuple[str, dict]:
        """执行一次隔离 route，返回终端输出和写出的 route-impact。"""
        args = SimpleNamespace(config=str(self.root / "local.yaml"))
        output = io.StringIO()
        paths = SimpleNamespace(
            project_path=self.root,
            requirement_path=self.requirement,
            requirement_dir=requirement_dir or self.root,
        )
        route_path = self.root / "route-impact.json"
        requirement_sha = hashlib.sha256(
            "修改首页、用户接口和本地数据。".encode("utf-8")
        ).hexdigest()
        old_cwd = Path.cwd()
        try:
            with (
                mock.patch("scripts.delivery.load_config", return_value=config or {}),
                mock.patch("scripts.delivery.resolve_paths", return_value=paths),
                mock.patch("scripts.delivery.current_branch", return_value="feature"),
                mock.patch("scripts.delivery.baseline_path_for_config", return_value=self.root / "baseline.json"),
                mock.patch(
                    "scripts.delivery.requirement_snapshot_path_for_config",
                    return_value=self.root / "requirement-snapshot.json",
                ),
                mock.patch("scripts.delivery.route_impact_path_for_config", return_value=route_path),
                mock.patch(
                    "scripts.delivery.load_requirement_snapshot",
                    return_value={
                        "requirement_id": "requirement-1",
                        "revision": 1,
                        "status": "CONFIRMED",
                        "pending_changes": [],
                        "sha256": requirement_sha,
                        "requirement_path": str(self.requirement.resolve()),
                        "obligations": [{"id": "BDD-001", "sha256": "b" * 64}],
                    },
                ),
                mock.patch(
                    "scripts.delivery.current_delivery_snapshot",
                    return_value={
                        "baseline_id": "requirement-1",
                        "baseline_head": "head-1",
                        "head": "head-2",
                        "snapshot_sha256": "a" * 64,
                    },
                ),
                mock.patch(
                    "scripts.delivery.validate_plan_confirmation",
                    return_value={
                        "implementation_plan_sha256": "d" * 64,
                        "impact_radius_sha256": "f" * 64,
                        "plan_confirmation_receipt_sha256": "e" * 64,
                    },
                ),
                mock.patch(
                    "scripts.delivery.load_impact_radius",
                    return_value={
                        "allowed_files": allowed_files
                        if allowed_files is not None
                        else [
                            path
                            for change in changes
                            for path in (change.old_path, change.path)
                            if path
                        ],
                        "allowed_dirs": [],
                        "impacts": [],
                    },
                ),
                mock.patch("scripts.delivery.get_diff_changes", return_value=(changes, [])),
                redirect_stdout(output),
            ):
                cmd_route(args)
        finally:
            os.chdir(old_cwd)

        return output.getvalue(), json.loads(route_path.read_text(encoding="utf-8"))

    def test_route_prints_api_and_manual_ui_selection(self) -> None:
        """验证 API 自动入队、UI 保持手动，并输出其他工程影响关注点。"""
        files = [
            "app/src/main/java/example/HomeScreen.kt",
            "app/src/main/java/example/UserMapper.kt",
            "app/src/main/java/example/UserDao.kt",
            "gradle/libs.versions.toml",
        ]
        text, route_payload = self._run_route_with_changes([
            GitChange("M", path) for path in files
        ])
        self.assertIn("你主要看:", text)
        self.assertIn("需求文件:", text)
        self.assertIn("route、专项审查和最终报告前必须重新读取", text)
        self.assertIn("AI 执行前必须读取（只展示路径，不展示正文）", text)
        self.assertIn("requirement-revision.json", text)
        self.assertIn("traceability.md", text)
        self.assertIn("实施计划.md", text)
        self.assertIn("android-verify-api-contract", text)
        self.assertIn("[建议单独执行] android-verify-ui", text)
        self.assertIn("数据存储 | 检测到", text)
        self.assertIn("构建配置 | 检测到", text)
        self.assertIn("架构依赖 | 检测到", text)
        self.assertIn("schema、迁移、旧数据和回滚", text)
        self.assertIn("OpenAPI 契约: 候选适用", text)
        self.assertIn("数据迁移: 候选适用", text)
        self.assertIn("UI/A11y: 候选适用", text)
        self.assertIn("无真机时继续其他门禁", text)
        self.assertIn("动态能力未验证不得写成通过", text)
        self.assertNotIn("impacts", route_payload)
        self.assertEqual("d" * 64, route_payload["implementation_plan_sha256"])
        self.assertEqual("f" * 64, route_payload["impact_radius_sha256"])
        route_gates = {
            item["id"]: item for item in route_payload["conditional_gates"]
        }
        self.assertIn("android-verify-api-contract", route_gates)
        self.assertIn("android-data-migration", route_gates)
        self.assertIn(
            "app/src/main/java/example/UserMapper.kt",
            route_gates["android-verify-api-contract"]["basis_files"],
        )

    def test_route_ignores_document_only_changes(self) -> None:
        """验证交付文档变化不会触发代码影响面或专项 gate。"""
        requirement_dir = self.root / "document" / "2026-07-28-login"
        requirement_dir.mkdir(parents=True)

        text, route_payload = self._run_route_with_changes(
            [GitChange("A", "document/2026-07-28-login/审计总结.md")],
            requirement_dir=requirement_dir,
        )

        self.assertIn("未检测到任何代码变更", text)
        self.assertNotIn("android-verify-api-contract", text)
        self.assertEqual([], route_payload["conditional_gates"])

    def test_route_detects_http_url_connection_api_basis_from_source(self) -> None:
        """验证 ApiClient/HttpURLConnection 变更触发接口契约且依据是源码路径。"""
        api_path = "app/src/main/java/example/TikTokApiClient.java"
        patch = (
            "@@ public class TikTokApiClient {\n"
            "+  private static final String API_BASE_URL = \"https://example.invalid\";\n"
            "+  HttpURLConnection conn = (HttpURLConnection) new URL(API_BASE_URL).openConnection();\n"
        )

        _, route_payload = self._run_route_with_changes([
            GitChange("M", api_path, patch=patch)
        ])

        route_gates = {
            item["id"]: item for item in route_payload["conditional_gates"]
        }
        self.assertIn("android-verify-api-contract", route_gates)
        self.assertEqual(
            [api_path],
            route_gates["android-verify-api-contract"]["basis_files"],
        )

    def test_route_rejects_diff_outside_confirmed_radius(self) -> None:
        """route 发现 Manifest 越界时立即失败且不写 route 文件。"""
        with self.assertRaisesRegex(DeliveryError, "超出已确认影响半径"):
            self._run_route_with_changes(
                [GitChange("M", "app/src/main/AndroidManifest.xml")],
                allowed_files=["app/src/main/java/example/HomeScreen.kt"],
            )

        self.assertFalse((self.root / "route-impact.json").exists())

    def test_route_includes_profile_declared_api_source(self) -> None:
        """即使 diff 未命中 API 文件，profile 契约声明也必须触发 API gate。"""
        _, route_payload = self._run_route_with_changes(
            [GitChange("M", "app/src/main/java/example/HomeScreen.kt")],
            config={"api": {"files": ["api/openapi.json"]}},
        )

        route_gates = {item["id"]: item for item in route_payload["conditional_gates"]}
        self.assertIn("android-verify-api-contract", route_gates)
        self.assertIn(
            "api/openapi.json",
            route_gates["android-verify-api-contract"]["basis_files"],
        )


if __name__ == "__main__":
    unittest.main()
