#!/usr/bin/env python3
"""Render canonical Android Delivery flow summaries into the human design docs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml


START = "<!-- android-delivery-flow:generated:start -->"
END = "<!-- android-delivery-flow:generated:end -->"


class FlowRenderError(RuntimeError):
    """Raised when the flow contract or generated document block is invalid."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise FlowRenderError(f"无法读取流程契约: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FlowRenderError(f"流程契约根节点必须是 object: {path}")
    return payload


def load_contracts(root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = root or skill_root()
    return (
        _read_yaml(base / "references" / "delivery-flow.yaml"),
        _read_yaml(base / "references" / "skill-catalog.yaml"),
    )


def contract_digest(flow: dict[str, Any], catalog: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"flow": flow, "catalog": catalog},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _overview_block(flow: dict[str, Any], catalog: dict[str, Any]) -> str:
    digest = contract_digest(flow, catalog)
    steps = " → ".join(item["label"] for item in flow.get("user_steps", []))
    lines = [
        START,
        "## 自动同步的流程契约摘要",
        "",
        f"> 由 `ai-skills/android-delivery-skills/references/delivery-flow.yaml` 生成；契约摘要 `{digest}`。",
        "",
        f"**用户流程**：{steps}",
        "",
        "| 阶段 | 主要命令 | 用户确认 |",
        "| --- | --- | --- |",
    ]
    for item in flow.get("user_steps", []):
        checkpoint = item.get("human_checkpoint")
        labels = {True: "需要", False: "不需要", "conditional": "语义/范围变化时需要", "explicit-trigger": "用户明确触发"}
        lines.append(f"| {item['label']} | `{item['command']}` | {labels.get(checkpoint, checkpoint)} |")
    lines.extend(["", "**失效与回退**", "", "| 事件 | 保留 | 失效 | 回到 |", "| --- | --- | --- | --- |"])
    for event in flow.get("invalidation_events", []):
        preserves = "；".join(event.get("preserves") or ["无"])
        invalidates = "；".join(event.get("invalidates") or ["无"])
        lines.append(f"| {event['label']} | {preserves} | {invalidates} | `{event['resumes_at']}` |")
    lines.extend(["", END])
    return "\n".join(lines)


def _diagram_block(flow: dict[str, Any], catalog: dict[str, Any]) -> str:
    digest = contract_digest(flow, catalog)
    lines = [
        START,
        "## 自动同步的状态机",
        "",
        f"> 由结构化流程契约生成；契约摘要 `{digest}`。增量更新是跨阶段回退，不是可跳过的线性尾声。",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for transition in flow.get("transitions", []):
        source = transition["from"]
        target = transition["to"]
        trigger = str(transition["trigger"]).replace('"', "'")
        lines.append(f'    {source}["{source}"] -->|"{trigger}"| {target}["{target}"]')
    for event in flow.get("invalidation_events", []):
        event_id = str(event["id"]).replace("-", "_").upper()
        label = str(event["label"]).replace('"', "'")
        target = event["resumes_at"]
        lines.append(f'    {event_id}{{"{label}"}} -.-> {target}')
    lines.extend(["```", "", END])
    return "\n".join(lines)


def _replace_block(content: str, block: str) -> str:
    if START in content or END in content:
        if content.count(START) != 1 or content.count(END) != 1:
            raise FlowRenderError("生成块标记必须各出现一次")
        start = content.index(START)
        end = content.index(END, start) + len(END)
        return content[:start] + block + content[end:]
    lines = content.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise FlowRenderError("流程文档必须以一级标题开始")
    return "\n".join([lines[0], "", block, "", *lines[1:]]).rstrip() + "\n"


def render_documents(root: Path | None = None) -> dict[Path, str]:
    """从结构化流程契约渲染 FLOW 文档的自动同步区块。

    文档基准以 skill 仓为准：FLOW 文档跟 skill 绑定，放在 skill 仓的 docs/ 下，
    不放在多 skill 共用的仓库根 doc/。
    """
    delivery_root = skill_root()
    flow, catalog = load_contracts(delivery_root)
    targets = {
        delivery_root / "docs" / "FLOW_OVERVIEW.md": _overview_block(flow, catalog),
        delivery_root / "docs" / "FLOW_DIAGRAMS.md": _diagram_block(flow, catalog),
    }
    rendered: dict[Path, str] = {}
    for path, block in targets.items():
        if not path.is_file():
            raise FlowRenderError(f"流程文档不存在: {path}")
        rendered[path] = _replace_block(path.read_text(encoding="utf-8"), block)
    return rendered


def write_documents(rendered: dict[Path, str]) -> None:
    for path, content in rendered.items():
        path.write_text(content, encoding="utf-8")


def check_documents(rendered: dict[Path, str]) -> list[Path]:
    return [path for path, expected in rendered.items() if path.read_text(encoding="utf-8") != expected]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or check Android Delivery flow docs.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repo-root", default=str(repository_root()))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        rendered = render_documents(Path(args.repo_root).expanduser().resolve())
        if args.write:
            write_documents(rendered)
            for path in rendered:
                print(f"已同步: {path}")
            return 0
        changed = check_documents(rendered)
    except (OSError, FlowRenderError) as exc:
        print(f"流程文档同步失败: {exc}", file=sys.stderr)
        return 2
    if changed:
        print("流程文档与结构化契约不同步：", file=sys.stderr)
        for path in changed:
            print(f"- {path}", file=sys.stderr)
        return 1
    print("流程文档与结构化契约一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
