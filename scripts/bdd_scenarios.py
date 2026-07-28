#!/usr/bin/env python3
"""Parse the canonical scenario-level BDD format used by delivery gates."""

from __future__ import annotations

import re
from typing import Any


BDD_ID_PATTERN = r"BDD-[0-9]+"
BDD_ID_RE = re.compile(BDD_ID_PATTERN)
BDD_HEADING_RE = re.compile(
    rf"(?m)^(#{{2,6}})[ \t]+({BDD_ID_PATTERN})[ \t]+([^\r\n]+?)\s*$"
)
HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+[^\r\n]+$")
LEGACY_THEN_ID_RE = re.compile(r"\bBDD-[0-9]+/T[0-9]+\b")
STEP_PATTERNS = {
    "Given": re.compile(r"(?m)^[ \t]*Given\b"),
    "When": re.compile(r"(?m)^[ \t]*When\b"),
    "Then": re.compile(r"(?m)^[ \t]*Then\b"),
}
PENDING_HEADING_RE = re.compile(r"(?m)^##[ \t]+待确认[ \t]*$")
NEXT_MAJOR_HEADING_RE = re.compile(r"(?m)^#{1,2}[ \t]+")


class BddScenarioError(RuntimeError):
    """The requirement file is not ready to become a confirmed BDD baseline."""


def is_bdd_id(value: Any) -> bool:
    """Return whether value is the canonical scenario-level BDD identifier."""
    return isinstance(value, str) and re.fullmatch(BDD_ID_PATTERN, value) is not None


def bdd_ids_in_text(content: str) -> set[str]:
    """Return scenario IDs mentioned in text without accepting legacy /T suffixes."""
    if LEGACY_THEN_ID_RE.search(content):
        raise BddScenarioError("需求仍使用旧的 BDD-###/T# 编号，请改为场景级 BDD-###")
    return set(BDD_ID_RE.findall(content))


def _scenario_ranges(content: str) -> list[tuple[re.Match[str], int]]:
    """Return each BDD heading and the end of its Markdown section."""
    matches = list(BDD_HEADING_RE.finditer(content))
    ranges: list[tuple[re.Match[str], int]] = []
    for match in matches:
        heading_level = len(match.group(1))
        end = len(content)
        for heading in HEADING_RE.finditer(content, match.end()):
            if len(heading.group(1)) <= heading_level:
                end = heading.start()
                break
        ranges.append((match, end))
    return ranges


def non_bdd_content(content: str) -> str:
    """Return requirement content outside BDD scenario sections."""
    ranges = _scenario_ranges(content)
    if not ranges:
        return content
    parts: list[str] = []
    cursor = 0
    for match, end in ranges:
        parts.append(content[cursor:match.start()])
        cursor = end
    parts.append(content[cursor:])
    return "".join(parts)


def extract_bdd_scenarios(content: str) -> list[dict[str, str]]:
    """Extract unique Markdown BDD headings and require Given/When/Then in each block."""
    if LEGACY_THEN_ID_RE.search(content):
        raise BddScenarioError("需求仍使用旧的 BDD-###/T# 编号，请改为场景级 BDD-###")
    ranges = _scenario_ranges(content)
    if not ranges:
        raise BddScenarioError(
            "需求事实源至少需要一个 `### BDD-001 场景名称`，并包含 Given/When/Then"
        )
    scenarios: list[dict[str, str]] = []
    seen: set[str] = set()
    for match, end in ranges:
        identifier = match.group(2)
        if identifier in seen:
            raise BddScenarioError(f"需求存在重复 BDD 场景编号: {identifier}")
        seen.add(identifier)
        body = content[match.end():end].strip()
        missing = [name for name, pattern in STEP_PATTERNS.items() if not pattern.search(body)]
        if missing:
            raise BddScenarioError(
                f"{identifier} 缺少标准 BDD 步骤: {', '.join(missing)}"
            )
        scenarios.append({
            "id": identifier,
            "title": match.group(3).strip(),
            "text": f"{match.group(0).lstrip('#').strip()}\n{body}".strip(),
        })
    return scenarios


def validate_requirement_readiness(content: str) -> list[dict[str, str]]:
    """Require complete scenarios and an explicit empty pending section before confirmation."""
    scenarios = extract_bdd_scenarios(content)
    pending_match = PENDING_HEADING_RE.search(content)
    if not pending_match:
        raise BddScenarioError("需求缺少 `## 待确认`；确认前请明确写为 `- 无`")
    tail = content[pending_match.end():]
    next_heading = NEXT_MAJOR_HEADING_RE.search(tail)
    pending = tail[:next_heading.start()] if next_heading else tail
    normalized = re.sub(r"[\s\-。.]", "", pending)
    if normalized != "无":
        raise BddScenarioError("需求仍有待确认内容，不能建立或确认需求版本")
    return scenarios
