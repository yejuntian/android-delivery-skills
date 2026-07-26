#!/usr/bin/env python3
"""模块名称：contract_loader.py

用途：读取 Android Delivery 评测契约文件，并把 YAML 转成稳定的 Contract 对象。

核心流程：定位 evals/contracts/active-contracts.yaml，校验最小结构、状态枚举、
ID 唯一性和 active/retired 必填字段，再返回不可变数据对象供其他 Oracle 使用。

职责边界：只负责契约文件的读取与结构校验；不判断 owner 文件是否存在、不检查场景
覆盖关系，也不执行任何 Skill、脚本或模型评测。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


VALID_STATUSES = {"active", "retired"}


class ContractError(RuntimeError):
    """表示契约 YAML 缺失、格式错误或字段不满足最小约束。"""


@dataclass(frozen=True)
class GateSpec:
    """保存一条契约的顺序门禁：哪些动作会被哪些前置事件阻断。"""

    blocks: tuple[str, ...]
    satisfied_by: tuple[str, ...]
    reset_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class Contract:
    """保存一条当前流程契约的最小机器可读信息。"""

    id: str
    status: str
    title: str
    kind: str
    oracle: str | None
    owner_files: tuple[str, ...]
    applies_to: tuple[str, ...]
    covered_by: dict[str, tuple[str, ...]]
    gate: GateSpec | None = None
    retired_reason: str | None = None
    replaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractSet:
    """保存契约文件版本和全部契约，便于 Runner 汇总报告。"""

    version: int
    path: Path
    contracts: tuple[Contract, ...]

    def active(self) -> tuple[Contract, ...]:
        """返回当前仍生效的契约。"""
        return tuple(contract for contract in self.contracts if contract.status == "active")

    def retired(self) -> tuple[Contract, ...]:
        """返回已退休的契约。"""
        return tuple(contract for contract in self.contracts if contract.status == "retired")


def default_contract_path(root: Path) -> Path:
    """根据仓库根目录返回默认契约文件路径。"""
    return root / "evals" / "contracts" / "active-contracts.yaml"


def read_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件并要求根节点是 object。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractError(f"无法读取契约 YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"契约 YAML 根节点必须是 object: {path}")
    return data


def require_text(value: Any, field: str, path: Path) -> str:
    """读取必填字符串字段，空白字符串视为配置错误。"""
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}: {field} 必须是非空字符串")
    return value.strip()


def optional_text(value: Any, field: str, path: Path) -> str | None:
    """读取可选字符串字段，缺失时返回 None。"""
    if value is None:
        return None
    return require_text(value, field, path)


def require_text_list(value: Any, field: str, path: Path) -> tuple[str, ...]:
    """读取必填字符串数组字段，并要求至少包含一个元素。"""
    if not isinstance(value, list) or not value:
        raise ContractError(f"{path}: {field} 必须是非空字符串数组")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(require_text(item, f"{field}[{index}]", path))
    return tuple(items)


def optional_text_list(value: Any, field: str, path: Path) -> tuple[str, ...]:
    """读取可选字符串数组字段，缺失时返回空元组。"""
    if value is None:
        return ()
    return require_text_list(value, field, path)


def require_coverage(value: Any, path: Path) -> dict[str, tuple[str, ...]]:
    """读取 covered_by 字段，并保持 suite 到场景 ID 的映射。"""
    if not isinstance(value, dict) or not value:
        raise ContractError(f"{path}: covered_by 必须是非空 object")
    coverage: dict[str, tuple[str, ...]] = {}
    for suite, scenario_ids in value.items():
        suite_name = require_text(suite, "covered_by.<suite>", path)
        coverage[suite_name] = require_text_list(scenario_ids, f"covered_by.{suite_name}", path)
    return coverage


def optional_gate(value: Any, contract_id: str, path: Path) -> GateSpec | None:
    """读取可选 gate 字段，缺失时表示该契约不参与行为顺序门禁。"""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ContractError(f"{path}: {contract_id}.gate 必须是 object")
    return GateSpec(
        blocks=require_text_list(value.get("blocks"), f"{contract_id}.gate.blocks", path),
        satisfied_by=require_text_list(
            value.get("satisfied_by"), f"{contract_id}.gate.satisfied_by", path
        ),
        reset_by=optional_text_list(value.get("reset_by"), f"{contract_id}.gate.reset_by", path),
    )


def parse_contract(raw: Any, index: int, path: Path) -> Contract:
    """把单条 YAML object 转成 Contract，并校验 active/retired 必填字段。"""
    if not isinstance(raw, dict):
        raise ContractError(f"{path}: contracts[{index}] 必须是 object")
    contract_id = require_text(raw.get("id"), f"contracts[{index}].id", path)
    status = require_text(raw.get("status"), f"contracts[{index}].status", path)
    if status not in VALID_STATUSES:
        raise ContractError(f"{path}: {contract_id}.status 必须是 active 或 retired")

    title = require_text(raw.get("title"), f"{contract_id}.title", path)
    kind = require_text(raw.get("kind"), f"{contract_id}.kind", path)
    oracle = optional_text(raw.get("oracle"), f"{contract_id}.oracle", path)
    owner_files = tuple(raw.get("owner_files") or [])
    applies_to = tuple(raw.get("applies_to") or [])
    covered_by_raw = raw.get("covered_by")
    gate = optional_gate(raw.get("gate"), contract_id, path)
    retired_reason = optional_text(raw.get("retired_reason"), f"{contract_id}.retired_reason", path)

    if status == "active":
        oracle = require_text(oracle, f"{contract_id}.oracle", path)
        owner_files = require_text_list(raw.get("owner_files"), f"{contract_id}.owner_files", path)
        applies_to = require_text_list(raw.get("applies_to"), f"{contract_id}.applies_to", path)
        covered_by = require_coverage(covered_by_raw, path)
    else:
        covered_by = {} if covered_by_raw is None else require_coverage(covered_by_raw, path)
        if retired_reason is None:
            raise ContractError(f"{path}: {contract_id}.retired_reason 必须说明删除原因")

    return Contract(
        id=contract_id,
        status=status,
        title=title,
        kind=kind,
        oracle=oracle,
        owner_files=owner_files,
        applies_to=applies_to,
        covered_by=covered_by,
        gate=gate,
        retired_reason=retired_reason,
        replaces=optional_text_list(raw.get("replaces"), f"{contract_id}.replaces", path),
    )


def load_contracts(path: Path) -> ContractSet:
    """读取契约文件并返回 ContractSet。"""
    data = read_yaml(path)
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise ContractError(f"{path}: version 必须是正整数")
    raw_contracts = data.get("contracts")
    if not isinstance(raw_contracts, list) or not raw_contracts:
        raise ContractError(f"{path}: contracts 必须是非空数组")

    contracts = tuple(parse_contract(raw, index, path) for index, raw in enumerate(raw_contracts))
    ids = [contract.id for contract in contracts]
    duplicates = sorted({contract_id for contract_id in ids if ids.count(contract_id) > 1})
    if duplicates:
        raise ContractError(f"{path}: contract id 重复: {', '.join(duplicates)}")
    return ContractSet(version=version, path=path, contracts=contracts)
