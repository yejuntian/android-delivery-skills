#!/usr/bin/env python3
"""脚本名称：test_skill_rule_ownership.py

用途：验证 Android Delivery 各 Skill 的运行时规则保持唯一归属，防止维护时复制粘贴同一套约束。

核心流程：扫描仓库级 AI 约束、共享规则、各 Skill、生产脚本和维护说明，检查维护命令接线、脚本职责表、
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
FIVE_STEP_FLOW = "确认需求 → 拆分测试 → 实现验证 → 变更后增量循环 → 最终交付"
DOCUMENTATION_SYNC_RULE = "职责对应的运行时来源、整体说明、使用导航、设计依据和测试"
MAINTENANCE_GATE_COMMAND = "python3 -m unittest scripts.tests.test_skill_rule_ownership -q"
DOCUMENTATION_SYNC_GUIDES = [
    REPOSITORY_ROOT / "AI_DELIVERY_WORKFLOW_GUIDELINES.md",
    REPOSITORY_ROOT / "references" / "open-source-design-rationale.md",
]
MAINTENANCE_GUIDES = [REPOSITORY_ROOT / "SIMPLE_USAGE.md", *DOCUMENTATION_SYNC_GUIDES]
AI_WORKFLOW_GUIDE = REPOSITORY_ROOT / "AI_DELIVERY_WORKFLOW_GUIDELINES.md"
SCRIPT_TABLE_START = "## 四、脚本职责划分"
SCRIPT_TABLE_END = "## 五、端到端交付流程"
DIRECT_SUPPORT_SCRIPTS = {
    "../figma-android-xml/scripts/figma_workflow.py",
    "scripts/tests/test_skill_rule_ownership.py",
}
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


def production_script_paths() -> set[str]:
    """返回本仓库全部非测试生产脚本，排除仅声明包的 ``__init__.py``。"""
    candidates = list((REPOSITORY_ROOT / "scripts").glob("*.py"))
    for scripts_dir in REPOSITORY_ROOT.glob("*/scripts"):
        candidates.extend(scripts_dir.glob("*.py"))
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in candidates
        if path.name != "__init__.py"
    }


def documented_script_paths() -> set[str]:
    """读取 AI 接管说明中的脚本职责表，避免从其他章节误收集示例命令。"""
    guide = read_text(AI_WORKFLOW_GUIDE)
    table = guide.split(SCRIPT_TABLE_START, 1)[1].split(SCRIPT_TABLE_END, 1)[0]
    return set(re.findall(r"^\| `([^`]+\.py)` \|", table, flags=re.MULTILINE))


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

    def test_documentation_sync_policy_is_explained(self) -> None:
        """验证整体说明和设计依据均已解释文档同步边界。"""
        for guide in DOCUMENTATION_SYNC_GUIDES:
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertIn(DOCUMENTATION_SYNC_RULE, read_text(guide))

    def test_repository_ai_rules_require_project_validation(self) -> None:
        """验证仓库级 AI 约束要求执行子项目声明的验证命令。"""
        agent_rules = read_text(REPOSITORY_AGENT_RULES)
        self.assertIn("执行项目指定的验证命令", agent_rules)
        self.assertIn("验证未执行或失败时不得声明维护完成", agent_rules)

    def test_maintenance_gate_is_wired_and_documented(self) -> None:
        """验证共享规则声明真实维护门禁，相关说明均提供同一命令。"""
        self.assertIn(MAINTENANCE_GATE_COMMAND, read_text(SHARED_RULES))
        for guide in MAINTENANCE_GUIDES:
            with self.subTest(guide=guide.relative_to(REPOSITORY_ROOT).as_posix()):
                self.assertIn(MAINTENANCE_GATE_COMMAND, read_text(guide))

    def test_script_responsibility_table_covers_all_production_scripts(self) -> None:
        """验证 AI 接管说明完整登记本仓库生产脚本，且没有保留已删除路径。"""
        documented_production = {
            path
            for path in documented_script_paths()
            if not path.startswith("../") and "/tests/" not in path
        }
        self.assertEqual(production_script_paths(), documented_production)

    def test_script_responsibility_table_covers_direct_support_scripts(self) -> None:
        """验证外部 Figma 下载和 Skill 维护门禁也有明确职责说明。"""
        self.assertTrue(DIRECT_SUPPORT_SCRIPTS.issubset(documented_script_paths()))

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
