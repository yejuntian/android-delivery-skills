#!/usr/bin/env python3
"""模块名称：contract_coverage.py

用途：检查当前有效流程契约是否拥有真实来源和至少一个评测覆盖点。

核心流程：读取契约、扫描 evals/scenarios 下的场景 ID，逐条验证 active contract 的
owner 文件存在、Oracle 已登记、covered_by 引用的场景存在，并生成可汇总的检查结果。

职责边界：只评估契约覆盖关系；不解析具体场景断言、不运行 artifact/command/model
评测，也不判断 Android 业务流程是否正确。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evals.oracles.contract_loader import Contract, ContractError, default_contract_path, load_contracts
from evals.oracles.oracle_registry import is_known_oracle


@dataclass(frozen=True)
class ContractCheckResult:
    """保存单条契约覆盖检查结果。"""

    contract_id: str
    passed: bool
    messages: tuple[str, ...]


def read_yaml_object(path: Path) -> dict[str, Any]:
    """读取场景 YAML 并要求根节点是 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractError(f"无法读取场景 YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"场景 YAML 根节点必须是 object: {path}")
    return data


def load_scenario_ids(root: Path) -> set[str]:
    """扫描 evals/scenarios 下全部 YAML 场景并返回场景 ID 集合。"""
    scenario_dir = root / "evals" / "scenarios"
    ids: set[str] = set()
    for path in sorted(scenario_dir.rglob("*.yaml")):
        data = read_yaml_object(path)
        scenario_id = data.get("id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ContractError(f"场景缺少 id: {path}")
        ids.add(scenario_id.strip())
    if not ids:
        raise ContractError(f"未发现评测场景: {scenario_dir}")
    return ids


def owner_file_errors(root: Path, contract: Contract) -> list[str]:
    """检查契约声明的 owner 文件是否存在且位于仓库内。"""
    errors: list[str] = []
    root_resolved = root.resolve()
    for owner in contract.owner_files:
        owner_path = (root / owner).resolve()
        if not owner_path.is_relative_to(root_resolved):
            errors.append(f"owner 越出仓库: {owner}")
        elif not owner_path.is_file():
            errors.append(f"owner 文件不存在: {owner}")
    return errors


def coverage_errors(contract: Contract, scenario_ids: set[str]) -> list[str]:
    """检查契约 covered_by 引用的场景 ID 是否存在。"""
    errors: list[str] = []
    for suite, covered_ids in contract.covered_by.items():
        for scenario_id in covered_ids:
            if scenario_id not in scenario_ids:
                errors.append(f"{suite} 覆盖场景不存在: {scenario_id}")
    return errors


def oracle_errors(contract: Contract) -> list[str]:
    """检查契约引用的 Oracle 名称是否已登记。"""
    if contract.oracle is None or is_known_oracle(contract.oracle):
        return []
    return [f"Oracle 未登记: {contract.oracle}"]


def evaluate_contract(root: Path, contract: Contract, scenario_ids: set[str]) -> ContractCheckResult:
    """评估单条 active contract 的来源、Oracle 和场景覆盖。"""
    messages = [
        *owner_file_errors(root, contract),
        *oracle_errors(contract),
        *coverage_errors(contract, scenario_ids),
    ]
    return ContractCheckResult(
        contract_id=contract.id,
        passed=not messages,
        messages=tuple(messages),
    )


def evaluate_contract_coverage(root: Path) -> dict[str, Any]:
    """执行全部 active contract 覆盖检查并返回结构化报告。"""
    contract_set = load_contracts(default_contract_path(root))
    scenario_ids = load_scenario_ids(root)
    checks = [evaluate_contract(root, contract, scenario_ids) for contract in contract_set.active()]
    passed = sum(1 for check in checks if check.passed)
    return {
        "producer": "android-delivery-contract-evals",
        "version": 1,
        "contract_file": str(contract_set.path),
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "retired": len(contract_set.retired()),
        },
        "checks": [
            {
                "contract_id": check.contract_id,
                "passed": check.passed,
                "messages": list(check.messages),
            }
            for check in checks
        ],
    }
