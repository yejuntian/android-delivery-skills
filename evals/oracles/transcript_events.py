#!/usr/bin/env python3
"""模块名称：transcript_events.py

用途：从带显式事件标记的对话记录中提取可评测的 AI 行为事件。

核心流程：逐行扫描 transcript，识别 `[event: name]` 或 `<!-- event: name -->` 标记，
按出现顺序转换为 TraceEvent，供 flow_gate Oracle 继续判断是否越过当前流程门禁。

职责边界：只做确定性的事件提取；不理解自然语言、不调用模型、不判断门禁是否通过。
"""

from __future__ import annotations

import re

from evals.oracles.flow_gate import TraceEvent


EVENT_PATTERNS = (
    re.compile(r"\[event:\s*([a-zA-Z0-9_-]+)\s*\]"),
    re.compile(r"<!--\s*event:\s*([a-zA-Z0-9_-]+)\s*-->"),
)


class TranscriptEventError(ValueError):
    """表示 transcript 中没有可评测事件或事件标记格式不合法。"""


def extract_trace_events(transcript: str) -> tuple[TraceEvent, ...]:
    """从 transcript 中提取按顺序出现的事件标记。"""
    if not isinstance(transcript, str) or not transcript.strip():
        raise TranscriptEventError("transcript 必须是非空字符串")
    events: list[TraceEvent] = []
    for line in transcript.splitlines():
        for pattern in EVENT_PATTERNS:
            for match in pattern.finditer(line):
                events.append(TraceEvent(event=match.group(1), index=len(events), detail=line.strip()))
    if not events:
        raise TranscriptEventError("transcript 未包含任何 [event: ...] 或 <!-- event: ... --> 标记")
    return tuple(events)
