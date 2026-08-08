#!/usr/bin/env python3
"""Parse the canonical scenario-level BDD format used by delivery gates."""

from __future__ import annotations

import re
from typing import Any


BDD_ID_PATTERN = r"BDD-[0-9]+"
BDD_ID_RE = re.compile(BDD_ID_PATTERN)
BDD_ATOM_KEY_PATTERN = r"[a-z][a-z0-9_-]*"
BDD_ATOM_ID_RE = re.compile(rf"({BDD_ID_PATTERN})\.({BDD_ATOM_KEY_PATTERN})")
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
STEP_LINE_RE = re.compile(r"(?m)^[ \t]*(Given|When|Then)\b[ \t]*(.*)$")
AND_LINE_RE = re.compile(r"(?m)^[ \t]*And(?:\b|[：:])[ \t]*(.*)$")
COMPOUND_THEN_RE = re.compile(
    r"(?:并且|同时|以及|另外|然后|随后|、|；|;|并(?=[允许保留显示支持可禁用隐藏跳转进入保持]))"
)
PENDING_HEADING_RE = re.compile(r"(?m)^##[ \t]+待确认[ \t]*$")
NEXT_MAJOR_HEADING_RE = re.compile(r"(?m)^#{1,2}[ \t]+")


class BddScenarioError(RuntimeError):
    """The requirement file is not ready to become a confirmed BDD baseline."""


def is_bdd_id(value: Any) -> bool:
    """Return whether value is the canonical scenario-level BDD identifier."""
    return isinstance(value, str) and re.fullmatch(BDD_ID_PATTERN, value) is not None


def is_bdd_atom_id(value: Any, *, scenario_id: str | None = None) -> bool:
    """Return whether value is a generated ``BDD-###.key`` atom identifier."""
    if not isinstance(value, str):
        return False
    match = BDD_ATOM_ID_RE.fullmatch(value)
    if match is None:
        return False
    return scenario_id is None or match.group(1) == scenario_id


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


def _scenario_steps(body: str) -> dict[str, list[re.Match[str]]]:
    """Collect Given/When/Then lines without interpreting their business meaning."""
    steps: dict[str, list[re.Match[str]]] = {name: [] for name in STEP_PATTERNS}
    for match in STEP_LINE_RE.finditer(body):
        steps[match.group(1)].append(match)
    return steps


def _structured_then_atoms(
    identifier: str,
    then_match: re.Match[str],
    next_step_start: int | None,
    body: str,
) -> list[dict[str, str]]:
    """Parse ``Then: - key: value`` into machine-stable atom keys."""
    marker = then_match.group(2).strip()
    if marker not in {":", "："}:
        return []
    end = next_step_start if next_step_start is not None else len(body)
    raw_lines = body[then_match.end():end].splitlines()
    atoms: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    in_html_comment = False
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if "<!--" in stripped:
            in_html_comment = "-->" not in stripped
            continue
        atom_match = re.fullmatch(
            rf"-[ \t]*({BDD_ATOM_KEY_PATTERN})[ \t]*[:：][ \t]*(.+?)\s*",
            stripped,
        )
        if atom_match is None:
            raise BddScenarioError(
                f"{identifier} 的结构化 Then 必须使用 `- key: value`，无法解析: {stripped}"
            )
        key, text = atom_match.groups()
        if key in seen_keys:
            raise BddScenarioError(f"{identifier} 的 Then 存在重复验收项 key: {key}")
        if COMPOUND_THEN_RE.search(text):
            raise BddScenarioError(
                f"{identifier}.{key} 仍包含多个结果，请拆成多个结构化验收项"
            )
        seen_keys.add(key)
        atoms.append({
            "id": f"{identifier}.{key}",
            "key": key,
            "text": text.strip(),
        })
    if not atoms:
        raise BddScenarioError(f"{identifier} 的结构化 Then 至少需要一个 `- key: value`")
    return atoms


def _scenario_atoms(identifier: str, body: str) -> list[dict[str, str]]:
    """Return generated atoms, rejecting obvious compound free-text outcomes."""
    steps = _scenario_steps(body)
    then_matches = steps["Then"]
    if len(then_matches) != 1:
        raise BddScenarioError(f"{identifier} 必须只有一个 Then 步骤")
    then_match = then_matches[0]
    next_step_start = next(
        (match.start() for match in STEP_LINE_RE.finditer(body, then_match.end())),
        None,
    )
    then_end = next_step_start if next_step_start is not None else len(body)
    if AND_LINE_RE.search(body[then_match.start():then_end]):
        raise BddScenarioError(
            f"{identifier} 不得用 And 隐藏多个 Then 结果，请改用结构化验收项"
        )
    atoms = _structured_then_atoms(identifier, then_match, next_step_start, body)
    if atoms:
        return atoms
    trailing_lines = body[then_match.end():then_end].splitlines()
    in_html_comment = False
    for line in trailing_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if "<!--" in stripped:
            in_html_comment = "-->" not in stripped
            continue
        raise BddScenarioError(
            f"{identifier} 的 Then 后存在未结构化内容，请改用 `Then: - key: value`"
        )
    text = then_match.group(2).strip()
    if not text:
        raise BddScenarioError(f"{identifier} 的 Then 结果不能为空")
    if COMPOUND_THEN_RE.search(text):
        raise BddScenarioError(
            f"{identifier} 的 Then 包含多个结果；请拆成多个 BDD 场景，或改写为"
            "结构化 `Then: - key: value`"
        )
    return [{"id": identifier, "key": "result", "text": text}]


def extract_bdd_scenarios(content: str) -> list[dict[str, Any]]:
    """Extract unique Markdown BDD headings and require Given/When/Then in each block."""
    if LEGACY_THEN_ID_RE.search(content):
        raise BddScenarioError("需求仍使用旧的 BDD-###/T# 编号，请改为场景级 BDD-###")
    ranges = _scenario_ranges(content)
    if not ranges:
        raise BddScenarioError(
            "当前需求事实源还没有 BDD；这不是继续拆分的许可。\n"
            "👉 必须先完成需求澄清：AI 先根据已读资料列出已查明事实、产品级歧义和缺失事实，"
            "一次只询问当前最高优先级问题，并停止等待用户回答。\n"
            "用户回答后，先写回 requirement_file 并重新执行 init；只有产品行为、范围和验收口径"
            "均已确认，且 `## 待确认` 为 `- 无` 时，AI 才能生成 `BDD-001`（Given/When/Then）。"
        )
    scenarios: list[dict[str, str]] = []
    seen: set[str] = set()
    for match, end in ranges:
        identifier = match.group(2)
        if identifier in seen:
            raise BddScenarioError(f"需求存在重复 BDD 场景编号: {identifier}")
        seen.add(identifier)
        body = content[match.end():end].strip()
        steps = _scenario_steps(body)
        missing = [name for name in STEP_PATTERNS if not steps[name]]
        if missing:
            raise BddScenarioError(
                f"{identifier} 缺少标准 BDD 步骤: {', '.join(missing)}"
            )
        atoms = _scenario_atoms(identifier, body)
        scenarios.append({
            "id": identifier,
            "title": match.group(3).strip(),
            "text": f"{match.group(0).lstrip('#').strip()}\n{body}".strip(),
            # Plain Then keeps the scenario-level id for backward compatibility;
            # structured Then receives stable machine-generated atom ids.
            "atoms": atoms if len(atoms) > 1 or atoms[0]["id"] != identifier else [],
        })
    return scenarios


def validate_requirement_readiness(content: str) -> list[dict[str, Any]]:
    """Require complete scenarios and an explicit empty pending section before confirmation.

    待确认分级交给 agent 判断（见 SKILL/global-rules），机器只保证“有显式空待确认段”：
    含实现级待确认时由 AI 主动清空或标注，不靠关键词猜测，避免误判。
    """
    scenarios = extract_bdd_scenarios(content)
    pending_match = PENDING_HEADING_RE.search(content)
    if not pending_match:
        raise BddScenarioError(
            "需求缺少 `## 待确认`；确认前请明确写为 `- 无`\n"
            "👉 待确认分级由 AI 判断：需求级（产品行为/范围/验收）必须解决，"
            "实现级（命名/实现方式/数据结构）可写明并推迟到计划阶段，确认时写 `- 无`。"
        )
    tail = content[pending_match.end():]
    next_heading = NEXT_MAJOR_HEADING_RE.search(tail)
    pending = tail[:next_heading.start()] if next_heading else tail
    normalized = re.sub(r"[\s\-。.]", "", pending)
    if normalized != "无":
        raise BddScenarioError(
            "需求仍有待确认内容，不能建立或确认需求版本。\n"
            "👉 请由 AI 判断每一项：需求级（产品行为/范围/验收）必须先与用户解决；"
            "实现级（实现方式/命名/数据结构等）可推迟到计划阶段——确认时把待确认段写为 `- 无`，"
            "实现级细节移到实施计划或代码注释，不留在需求事实源阻断确认。"
        )
    return scenarios
