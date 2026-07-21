#!/usr/bin/env python3
"""脚本名称：user_facing_labels.py

用途：把 Android Delivery 机器协议中的稳定枚举转换为面向用户的自然中文。

核心流程：按需求、交付、测试、Journey 和风险等语境提供中文标签，并可在终端错误
或人类报告中替换未解释的机器枚举。

职责边界：只处理呈现文本，不修改机器 JSON、Schema、业务状态、路由结论或退出码。
文件路径、命令、接口路径和代码标识等真实技术信息不在本模块翻译范围内。
"""

from __future__ import annotations

import argparse
import re
from typing import Any, Mapping


CHANGE_TYPE_LABELS = {
    "ADDED": "新增",
    "CHANGED": "修改",
    "REMOVED": "删除",
    "UNCHANGED": "保持不变",
    "SUPERSEDED": "已被新要求替代",
}
DECISION_LABELS = {
    "CONFIRMED": "已确认",
    "PENDING": "等待确认",
    "REJECTED": "已撤回或拒绝",
    "CONFLICT": "存在冲突",
}
SNAPSHOT_STATUS_LABELS = {
    "AWAITING_OBLIGATIONS": "等待生成验收清单",
    "PENDING_CONFIRMATION": "存在等待确认的变化",
    "CONFIRMED": "已确认",
    "UNCONFIRMED_CHANGE": "需求变化尚未确认",
}
REMOVAL_DISPOSITION_LABELS = {
    "REMOVE_IMPLEMENTATION": "整个功能彻底删除",
    "KEEP_COMPATIBILITY": "只删除当前入口，保留兼容能力",
    "STOP_UNFINISHED_WORK": "取消本轮尚未完成的开发",
}
DELIVERY_CONCLUSION_LABELS = {
    "FULL_PASS": "全部验证通过",
    "LOCAL_PASS_DEVICE_PENDING": "本地验证已通过，仍需完成设备验证",
    "INCOMPLETE": "当前需求尚未完成",
    "BLOCKED": "当前条件不足，暂时无法继续",
}
OBLIGATION_STATUS_LABELS = {
    "COVERED_AUTOMATED": "自动测试通过",
    "COVERED_MANUAL": "已完成人工验收",
    "UNVERIFIED": "尚未实际验证",
    "BLOCKED": "当前条件不足，暂时无法继续",
    "NOT_APPLICABLE": "当前需求不涉及",
}
GATE_STATUS_LABELS = {
    "PASS": "通过",
    "FAIL": "未通过",
    "ERROR": "执行错误",
    "SKIPPED": "根据当前范围无需执行",
    "UNVERIFIED": "尚未实际验证",
    "BLOCKED": "当前条件不足，暂时无法继续",
}
EVIDENCE_KIND_LABELS = {
    "AUTOMATED": "自动化执行证据",
    "AGENT": "智能体执行证据",
    "MANUAL": "人工验收证据",
    "REVIEW": "专项审查证据",
}
FAILURE_CLASS_LABELS = {
    "REQUIREMENT_BLOCKED": "需求信息还不完整",
    "ENVIRONMENT_FAILED": "当前环境或工具暂时不可用",
    "TEST_FAILED": "测试或测试环境未通过",
    "IMPLEMENTATION_FAILED": "当前代码与已确认要求不一致",
    "UNKNOWN": "暂时还没有定位到确切原因",
}
WORKFLOW_STATE_LABELS = {
    "SPECIALIST_ACTIVE": "专项能力正在处理",
    "AI_FALLBACK_ACTIVE": "已由通用 AI 接管处理",
    "USER_INPUT_REQUIRED": "需要你补充信息或完成操作",
    "BLOCKED": "当前条件不足，暂时无法继续",
}
JOURNEY_STATUS_LABELS = {
    "PASS": "界面流程测试已执行并通过",
    "PREFLIGHT_PASS": "预检通过，尚未执行界面流程测试",
    "SKIPPED_NO_UI": "当前需求没有界面影响，无需执行界面流程测试",
    "SKIPPED_VISUAL_ONLY": "仅有视觉变化，改用截图或独立视觉验收",
    "APP_ASSERTION_FAILED": "界面断言未通过",
    "HARNESS_UNAVAILABLE": "界面流程测试环境不可用",
    "HARNESS_FAILED": "界面流程测试运行器执行失败",
    "MALFORMED_JOURNEY": "界面流程测试用例格式无效",
    "NO_JOURNEY_FOUND": "尚未生成适用的界面流程测试用例",
    "INITIALIZATION_REQUIRED": "可选界面测试壳尚未初始化",
}
JOURNEY_APPLICABILITY_LABELS = {
    "FULL": "全部界面步骤适用",
    "PARTIAL": "部分界面步骤适用",
    "NONE": "不适用",
}
RISK_LEVEL_LABELS = {
    "L1": "一级风险（局部低风险）",
    "L2": "二级风险（标准业务变化）",
    "L3": "三级风险（高风险边界）",
    "BLOCKED": "关键信息不足，暂时无法安全实现",
}
SEVERITY_LABELS = {
    "P0": "最高严重级别",
    "P1": "高严重级别",
    "P2": "中等严重级别",
    "P3": "低严重级别",
}
GIT_CHANGE_LABELS = {
    "A": "新增文件",
    "M": "修改文件",
    "D": "删除文件",
    "R": "重命名文件",
}
GATE_LABELS = {
    "android-review-diff": "改动范围与回归审查",
    "android-review-code-quality": "代码质量与架构审查",
    "android-audit-stability": "稳定性审查",
    "android-test-and-fix": "自动化测试与修复",
    "android-build": "项目构建",
    "android-lint": "Android 静态检查（Lint）",
    "android-static-analysis": "Kotlin/Java 静态分析",
    "android-static-semantics": "Android 静态生命周期与资源检查",
    "android-verify-api-contract": "接口契约检查",
    "android-data-migration": "数据迁移检查",
    "android-ui-a11y": "界面与无障碍检查",
    "android-security-privacy": "安全与隐私检查",
    "android-dynamic-leak": "动态内存泄漏检查",
    "android-performance": "性能检查",
    "behavior-journey": "界面流程自动化测试",
}


class ChineseArgumentParser(argparse.ArgumentParser):
    """让命令参数保持稳定，同时把 Python 默认帮助标题转换为中文。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """初始化解析器并把 argparse 默认分组及帮助入口转换为中文。"""
        super().__init__(*args, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "可选参数"
        for action in self._actions:
            if action.dest == "help":
                action.help = "显示帮助并退出"

    def format_help(self) -> str:
        """生成中文帮助页；命令名、参数名和 choices 继续保持机器兼容。"""
        return super().format_help().replace("usage: ", "用法: ", 1)

# 通用替换只处理机器协议枚举；语境敏感的完整标题仍使用上方专用映射。
MACHINE_TERM_LABELS = {
    **CHANGE_TYPE_LABELS,
    **DECISION_LABELS,
    **SNAPSHOT_STATUS_LABELS,
    **REMOVAL_DISPOSITION_LABELS,
    **FAILURE_CLASS_LABELS,
    **WORKFLOW_STATE_LABELS,
    **JOURNEY_STATUS_LABELS,
    **JOURNEY_APPLICABILITY_LABELS,
    **RISK_LEVEL_LABELS,
    **SEVERITY_LABELS,
    **EVIDENCE_KIND_LABELS,
    "FULL_PASS": DELIVERY_CONCLUSION_LABELS["FULL_PASS"],
    "LOCAL_PASS_DEVICE_PENDING": DELIVERY_CONCLUSION_LABELS["LOCAL_PASS_DEVICE_PENDING"],
    "INCOMPLETE": DELIVERY_CONCLUSION_LABELS["INCOMPLETE"],
    "COVERED_AUTOMATED": OBLIGATION_STATUS_LABELS["COVERED_AUTOMATED"],
    "COVERED_MANUAL": OBLIGATION_STATUS_LABELS["COVERED_MANUAL"],
    "UNVERIFIED": OBLIGATION_STATUS_LABELS["UNVERIFIED"],
    "NOT_APPLICABLE": OBLIGATION_STATUS_LABELS["NOT_APPLICABLE"],
    "PASS": GATE_STATUS_LABELS["PASS"],
    "FAIL": GATE_STATUS_LABELS["FAIL"],
    "ERROR": GATE_STATUS_LABELS["ERROR"],
    "SKIPPED": GATE_STATUS_LABELS["SKIPPED"],
    "BLOCKED": WORKFLOW_STATE_LABELS["BLOCKED"],
    "NEW_SERIAL_REQUIREMENT": "新的串行需求",
    "SAME_REQUIREMENT": "当前同一需求",
}
_MACHINE_TERM_PATTERN = re.compile(
    r"(?<![A-Z0-9_])(" + "|".join(
        re.escape(item) for item in sorted(MACHINE_TERM_LABELS, key=len, reverse=True)
    ) + r")(?![A-Z0-9_])"
)


def user_label(
    value: object,
    labels: Mapping[str, str],
    unknown_label: str = "当前状态暂时无法识别，请检查流程版本",
) -> str:
    """返回指定语境的中文标签；未知机器值不直接暴露给用户。"""
    return labels.get(str(value), unknown_label)


def localize_machine_terms(value: object) -> str:
    """替换用户文本中的已知机器枚举，同时保留路径、命令和代码标识。"""
    text = str(value or "")
    return _MACHINE_TERM_PATTERN.sub(
        lambda match: MACHINE_TERM_LABELS[match.group(1)],
        text,
    )


def gate_label(value: object) -> str:
    """返回交付检查项的中文名称，未知标识统一显示为其他交付检查。"""
    return GATE_LABELS.get(str(value), "其他交付检查")
