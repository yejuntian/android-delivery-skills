#!/usr/bin/env python3
"""模块名称：oracle_registry.py

用途：集中登记评测契约可引用的稳定 Oracle 名称。

核心流程：暴露 KNOWN_ORACLES 集合和 is_known_oracle 查询函数，供契约覆盖检查使用。

职责边界：只维护 Oracle 名称注册表；不读取契约、不检查文件、不执行任何断言逻辑。
"""

from __future__ import annotations


KNOWN_ORACLES = frozenset(
    {
        "latest_user_requirement_is_persisted",
        "no_route_before_required_confirmations",
        "stale_mapping_blocks_final",
        "no_fake_green_from_zero_tests",
        "mutation_survivor_blocks_pass",
        "ui_visual_report_required",
        "conditional_gate_union_is_complete",
        "maintenance_evals_are_wired",
        "flow_gates_hold",
        "fresh_evidence_required",
        "impact_radius_blocks_out_of_scope_diff",
        "unverified_is_not_pass",
    }
)


def is_known_oracle(name: str) -> bool:
    """判断契约引用的 Oracle 名称是否已登记。"""
    return name in KNOWN_ORACLES
