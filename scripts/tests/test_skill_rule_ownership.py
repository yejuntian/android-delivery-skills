#!/usr/bin/env python3
"""脚本名称：test_skill_rule_ownership.py

用途：验证 Android Delivery 各 Skill 的运行时规则保持唯一归属，防止维护时复制粘贴同一套约束。

核心流程：扫描仓库级 AI 约束、共享规则、各 Skill 和设计依据，检查维护命令接线、
共享规则引用、关键章节归属、五步流程唯一来源及文件行数预算；同时拒绝跨运行时文件完全相同的长规则行。
测试只读取当前仓库文档，不接触真实 Android 项目、设备或网络。

职责边界：只防止明确的规则重复和上下文继续膨胀，不判断业务语义相似度，也不改变任何运行时流程。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_AGENT_RULES = REPOSITORY_ROOT.parent / ".agents" / "AGENTS.md"
SHARED_RULES = REPOSITORY_ROOT / "_shared" / "android-global-rules.md"
SKILL_FILES = sorted(REPOSITORY_ROOT.glob("*/SKILL.md"))
RUNTIME_RULE_FILES = [SHARED_RULES, *SKILL_FILES]
SHARED_RULE_REFERENCE = "../_shared/android-global-rules.md"
FIVE_STEP_FLOW = "确认需求 → 拆分测试与确认计划 → 实现验证 → 变更后增量循环 → 最终交付"
DOCUMENTATION_SYNC_RULE = "职责对应的运行时来源、设计依据和测试"
LEGACY_CONSTRAINT_PROTECTION_RULE = "旧约束保护清单"
MAINTENANCE_GATE_COMMAND = "python3 scripts/validate_maintenance.py"
MAINTENANCE_HOOK_INSTALL_COMMAND = "python3 scripts/install_maintenance_hook.py"
FAST_EVAL_COMMAND = "python3 evals/runners/run_evals.py --suite fast"
DOCUMENTATION_SYNC_GUIDES = [
    REPOSITORY_ROOT / "references" / "open-source-design-rationale.md",
]
MAINTENANCE_GUIDES = [*DOCUMENTATION_SYNC_GUIDES]
SECTION_OWNERS = {
    "## 用户可见五步": "android-implement-and-verify/SKILL.md",
    "## 工作模式": "android-test-and-fix/SKILL.md",
    "## Journey UI 测试": "android-test-and-fix/SKILL.md",
    "## Kotlin / Java / Android 静态语义路由": "android-audit-stability/SKILL.md",
}


def read_text(path: Path) -> str:
    """以 UTF-8 读取规则文件，保持测试错误直接指向真实文档。"""
    return path.read_text(encoding="utf-8")


def normalized_long_rule_lines(path: Path) -> list[str]:
    """提取代码块、表格和短句之外的长规则，用于发现完全相同的跨文件复制。"""
    rules: list[str] = []
    in_code_block = False
    for raw_line in read_text(path).splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block or not stripped or stripped.startswith(("|", "---")):
            continue
        normalized = re.sub(r"\s+", " ", stripped)
        # 只比较足够长的完整规则，避免标题和通用短语产生误报。
        if len(normalized) >= 80:
            rules.append(normalized)
    return rules


class SkillRuleOwnershipTests(unittest.TestCase):
    """验证 AI 维护入口、规则单一来源和脚本职责说明保持同步。"""

    def test_every_skill_reads_shared_rules_once(self) -> None:
        """验证每个 Skill 仍且只引用一次跨 Skill 共享规则。"""
        self.assertTrue(SKILL_FILES, "未发现任何 SKILL.md")
        for skill_file in SKILL_FILES:
            with self.subTest(skill=skill_file.parent.name):
                self.assertEqual(1, read_text(skill_file).count(SHARED_RULE_REFERENCE))

    def test_five_step_flow_has_one_runtime_owner(self) -> None:
        """验证用户可见五步只由总入口定义，不在共享规则中复制。"""
        owners = [
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in RUNTIME_RULE_FILES
            if FIVE_STEP_FLOW in read_text(path)
        ]
        self.assertEqual(["android-implement-and-verify/SKILL.md"], owners)

    def test_documentation_sync_is_a_shared_default(self) -> None:
        """验证文档主动同步要求由共享规则统一约束，无需用户重复提醒。"""
        self.assertIn(DOCUMENTATION_SYNC_RULE, read_text(SHARED_RULES))

    def test_llm_coding_error_reduction_stays_in_shared_rules(self) -> None:
        """验证降低 AI 编程错误率的通用准则只落在共享编程规则。"""
        shared_rules = read_text(SHARED_RULES)
        required_rules = [
            "AI 编码十二条强制约束",
            "适用于总入口、专项 Skill、独立调用、自修复和测试补齐",
            "用户不需要重复提醒",
            "CODING-01 先思考再编码",
            "CODING-02 简单优先",
            "CODING-03 只改任务相关代码",
            "CODING-04 只说最终验收标准",
            "CODING-05 只做判断不写死逻辑",
            "CODING-06 严格控制 token 消耗",
            "CODING-07 代码冲突先读源码不妥协",
            "CODING-08 拒绝假测试",
            "CODING-09 分阶段设检查点",
            "CODING-10 遵守原有代码风格",
            "CODING-11 有问题不隐瞒",
            "CODING-12 遇不合理结构主动说明",
            "必须遵守的强制门禁",
            "关键假设和可验证成功标准",
            "生产逻辑只表达已确认业务规则和项目事实",
            "增加未请求抽象/配置化或处理不可能场景",
            "每行改动都应能追溯到用户请求、已确认计划或失败证据",
            "用户只需确认业务目标、验收标准和边界，不要求指定技术实现",
        ]
        for rule in required_rules:
            self.assertIn(rule, shared_rules)
            for skill_file in SKILL_FILES:
                with self.subTest(rule=rule, skill=skill_file.parent.name):
                    self.assertNotIn(rule, read_text(skill_file))

    def test_documentation_sync_policy_is_explained(self) -> None:
        """验证整体说明和设计依据均已解释文档同步边界。"""
        for guide in DOCUMENTATION_SYNC_GUIDES:
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertIn(DOCUMENTATION_SYNC_RULE, read_text(guide))

    def test_rule_changes_preserve_existing_constraints(self) -> None:
        """验证新增规则目标不会覆盖既有约束保护要求。"""
        required_shared_rules = [
            "本次新增目标",
            LEGACY_CONSTRAINT_PROTECTION_RULE,
            "不得因只关注新增目标而删弱",
            "无法确认旧约束是否仍适用时先保留并说明",
        ]
        shared_rules = read_text(SHARED_RULES)
        for rule in required_shared_rules:
            self.assertIn(rule, shared_rules)

        for guide in DOCUMENTATION_SYNC_GUIDES:
            guide_text = read_text(guide)
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertIn("本次新增目标", guide_text)
                self.assertIn(LEGACY_CONSTRAINT_PROTECTION_RULE, guide_text)
                self.assertIn("不得为适配新增目标删弱旧约束", guide_text)

    def test_repository_ai_rules_require_project_validation(self) -> None:
        """验证仓库级 AI 约束要求执行子项目声明的验证命令。"""
        agent_rules = read_text(REPOSITORY_AGENT_RULES)
        self.assertIn("执行项目指定的验证命令", agent_rules)
        self.assertIn("验证未执行或失败时不得声明维护完成", agent_rules)

    def test_maintenance_gate_is_wired_and_documented(self) -> None:
        """验证共享规则和设计依据都声明统一维护验证命令。"""
        self.assertIn(MAINTENANCE_GATE_COMMAND, read_text(SHARED_RULES))
        self.assertIn(MAINTENANCE_HOOK_INSTALL_COMMAND, read_text(SHARED_RULES))
        for guide in MAINTENANCE_GUIDES:
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertIn(MAINTENANCE_GATE_COMMAND, read_text(guide))
                self.assertIn(MAINTENANCE_HOOK_INSTALL_COMMAND, read_text(guide))

    def test_fast_evals_are_wired_through_maintenance_entrypoint(self) -> None:
        """验证 fast eval 由统一维护入口接线，避免维护者记多条命令。"""
        validator = read_text(REPOSITORY_ROOT / "scripts" / "validate_maintenance.py")
        self.assertIn("scripts.tests.test_skill_rule_ownership", validator)
        self.assertIn("evals/runners/run_evals.py", validator)
        self.assertIn("--suite", validator)
        self.assertIn("fast", validator)
        self.assertIn(FAST_EVAL_COMMAND, "python3 evals/runners/run_evals.py --suite fast")

    def test_pre_commit_hook_install_is_available(self) -> None:
        """验证 pre-commit 自动验证安装脚本和检查入口存在。"""
        installer = read_text(REPOSITORY_ROOT / "scripts" / "install_maintenance_hook.py")
        checker = read_text(REPOSITORY_ROOT / "scripts" / "maintenance_pre_commit.py")
        self.assertIn("hooks/pre-commit", installer)
        self.assertIn("maintenance_pre_commit.py", installer)
        self.assertIn('"diff"', checker)
        self.assertIn("--cached", checker)
        self.assertIn("scripts/validate_maintenance.py", checker)


    def test_specialized_sections_stay_with_declared_owner(self) -> None:
        """验证关键专业章节只存在于其主责 Skill。"""
        for heading, expected_owner in SECTION_OWNERS.items():
            with self.subTest(heading=heading):
                owners = [
                    path.relative_to(REPOSITORY_ROOT).as_posix()
                    for path in RUNTIME_RULE_FILES
                    if heading in read_text(path)
                ]
                self.assertEqual([expected_owner], owners)

    def test_runtime_documents_stay_within_context_budget(self) -> None:
        """验证共享规则停止膨胀，且每个 Skill 保持在建议的五百行以内。"""
        self.assertLessEqual(len(read_text(SHARED_RULES).splitlines()), 410)
        for skill_file in SKILL_FILES:
            with self.subTest(skill=skill_file.parent.name):
                self.assertLessEqual(len(read_text(skill_file).splitlines()), 500)

    def test_runtime_files_do_not_copy_identical_long_rules(self) -> None:
        """验证不同运行时文件之间没有完全相同的长规则行。"""
        locations: dict[str, list[str]] = defaultdict(list)
        for path in RUNTIME_RULE_FILES:
            relative_path = path.relative_to(REPOSITORY_ROOT).as_posix()
            for rule in set(normalized_long_rule_lines(path)):
                locations[rule].append(relative_path)

        duplicates = {
            rule: owners for rule, owners in locations.items() if len(owners) > 1
        }
        self.assertEqual({}, duplicates)


if __name__ == "__main__":
    unittest.main()
