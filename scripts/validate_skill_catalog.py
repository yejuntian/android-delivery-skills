#!/usr/bin/env python3
"""Validate Android Delivery skill roles, invocation policy, and shared-rule ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SHARED_RULE_REFERENCE = "../_shared/android-global-rules.md"


class CatalogError(RuntimeError):
    """Raised when the skill catalog and on-disk skills disagree."""


def default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CatalogError(f"无法读取 YAML: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CatalogError(f"YAML 根节点必须是 object: {path}")
    return payload


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        raise CatalogError(f"SKILL.md 缺少 frontmatter: {path}")
    try:
        payload = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CatalogError(f"SKILL.md frontmatter 无效: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CatalogError(f"SKILL.md frontmatter 必须是 object: {path}")
    return payload


def validate_catalog(root: str | Path) -> list[str]:
    base = Path(root).expanduser().resolve()
    errors: list[str] = []
    catalog = _yaml(base / "references" / "skill-catalog.yaml")
    entries = catalog.get("skills")
    if not isinstance(entries, list) or not entries:
        return ["skill-catalog.yaml 的 skills 必须是非空数组"]

    indexed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"skills[{index}] 必须是 object")
            continue
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"skills[{index}].id 必须是非空字符串")
            continue
        if identifier in indexed:
            errors.append(f"catalog Skill 重复: {identifier}")
        indexed[identifier] = entry
        if entry.get("invocation") not in {"user", "model"}:
            errors.append(f"{identifier}.invocation 必须是 user 或 model")
        if not isinstance(entry.get("runtime"), bool):
            errors.append(f"{identifier}.runtime 必须是 boolean")

    disk_ids = {path.parent.name for path in base.glob("*/SKILL.md")}
    if disk_ids != set(indexed):
        missing = sorted(disk_ids - set(indexed))
        stale = sorted(set(indexed) - disk_ids)
        if missing:
            errors.append("catalog 漏登 Skill: " + ", ".join(missing))
        if stale:
            errors.append("catalog 登记了不存在的 Skill: " + ", ".join(stale))

    for identifier, entry in indexed.items():
        skill_path = base / identifier / "SKILL.md"
        agent_path = base / identifier / "agents" / "openai.yaml"
        if not skill_path.is_file() or not agent_path.is_file():
            continue
        frontmatter = _frontmatter(skill_path)
        if set(frontmatter) != {"name", "description"}:
            errors.append(f"{identifier} frontmatter 只能包含 name 和 description")
        if frontmatter.get("name") != identifier:
            errors.append(f"{identifier} frontmatter.name 不一致")
        if "TODO" in skill_path.read_text(encoding="utf-8"):
            errors.append(f"{identifier} 仍包含 TODO 占位")

        agent = _yaml(agent_path)
        policy = agent.get("policy") if isinstance(agent.get("policy"), dict) else {}
        implicit = policy.get("allow_implicit_invocation", True)
        expected_implicit = entry.get("invocation") == "model"
        if implicit is not expected_implicit:
            errors.append(
                f"{identifier} allow_implicit_invocation 应为 {str(expected_implicit).lower()}"
            )
        default_prompt = (agent.get("interface") or {}).get("default_prompt")
        if not isinstance(default_prompt, str) or f"${identifier}" not in default_prompt:
            errors.append(f"{identifier} default_prompt 必须显式引用 ${identifier}")

        shared_count = skill_path.read_text(encoding="utf-8").count(SHARED_RULE_REFERENCE)
        expected_count = 1 if entry.get("runtime") else 0
        if shared_count != expected_count:
            errors.append(
                f"{identifier} 共享运行时规则引用应为 {expected_count} 次，实际 {shared_count} 次"
            )

    integrations = catalog.get("integrations") or []
    for entry in integrations:
        if not isinstance(entry, dict):
            errors.append("integrations 每项必须是 object")
            continue
        if entry.get("id") in disk_ids:
            errors.append(f"外部 integration 不得冒充本仓库 Skill: {entry.get('id')}")
        if entry.get("id") == "figma-android-xml" and entry.get("role") != "implementation-provider":
            errors.append("figma-android-xml 必须保持 implementation-provider 角色")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Android Delivery skill catalog.")
    parser.add_argument("--root", default=str(default_root()))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        errors = validate_catalog(args.root)
    except CatalogError as exc:
        errors = [str(exc)]
    if args.format == "json":
        print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("Skill catalog 校验失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print("Skill catalog 校验通过。")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
