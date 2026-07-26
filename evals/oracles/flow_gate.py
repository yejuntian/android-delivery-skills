#!/usr/bin/env python3
"""模块名称：flow_gate.py

用途：根据当前 active contract 的 gate 声明，检查 AI 行为事件是否提前越过流程门禁。

核心流程：顺序读取 trace 事件；遇到 reset_by 事件时清空对应契约的满足状态，遇到
satisfied_by 事件时记录满足项，遇到 blocks 事件时检查该契约要求的前置项是否全部满足，
缺失则生成违反记录。

职责边界：只判断“动作发生前当前契约门禁是否满足”；不读取 YAML 文件、不运行命令、
不判断自然语言 transcript，也不决定哪些 contract 应该存在。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evals.oracles.contract_loader import ContractSet


@dataclass(frozen=True)
class TraceEvent:
    """保存一条可评测的 AI 行为事件。"""

    event: str
    index: int
    detail: str | None = None


@dataclass(frozen=True)
class GateViolation:
    """保存一次流程门禁违规。"""

    contract_id: str
    event: str
    index: int
    missing: tuple[str, ...]


def parse_trace(raw_trace: Any) -> tuple[TraceEvent, ...]:
    """把场景 YAML 中的 trace 数组转换成 TraceEvent。"""
    if not isinstance(raw_trace, list) or not raw_trace:
        raise ValueError("trace 必须是非空数组")
    events: list[TraceEvent] = []
    for index, raw_event in enumerate(raw_trace):
        if not isinstance(raw_event, dict):
            raise ValueError(f"trace[{index}] 必须是 object")
        event = raw_event.get("event")
        if not isinstance(event, str) or not event.strip():
            raise ValueError(f"trace[{index}].event 必须是非空字符串")
        detail = raw_event.get("detail")
        if detail is not None and not isinstance(detail, str):
            raise ValueError(f"trace[{index}].detail 必须是字符串")
        events.append(TraceEvent(event=event.strip(), index=index, detail=detail))
    return tuple(events)


def evaluate_flow_gates(contract_set: ContractSet, trace: tuple[TraceEvent, ...]) -> tuple[GateViolation, ...]:
    """按当前 active contract 的 gate 声明评估 trace 是否提前越权。"""
    gated_contracts = [contract for contract in contract_set.active() if contract.gate is not None]
    satisfied: dict[str, set[str]] = {contract.id: set() for contract in gated_contracts}
    violations: list[GateViolation] = []

    for event in trace:
        for contract in gated_contracts:
            gate = contract.gate
            if gate is None:
                continue
            if event.event in gate.reset_by:
                satisfied[contract.id].clear()
            if event.event in gate.satisfied_by:
                satisfied[contract.id].add(event.event)
            if event.event in gate.blocks:
                missing = tuple(item for item in gate.satisfied_by if item not in satisfied[contract.id])
                if missing:
                    violations.append(
                        GateViolation(
                            contract_id=contract.id,
                            event=event.event,
                            index=event.index,
                            missing=missing,
                        )
                    )
    return tuple(violations)
