#!/usr/bin/env python3
"""脚本名称：delivery_gate.py

用途：校验最终交付报告是否覆盖全部必需 BDD/Then、专项门禁和新鲜执行证据。

职责边界：只读取配置、Git 基线、当前工作树和 delivery-result.json；不运行测试、
不调用 Skill、不修代码、不维护流程阶段，也不执行任何 Git 写操作。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import baseline_path_for_config, resolve_config_paths  # noqa: E402
from .delivery import DeliveryError, load_config  # noqa: E402
from .git_changes import GitInspectionError, current_delivery_snapshot  # noqa: E402


PASSING_CONCLUSIONS = {"FULL_PASS", "LOCAL_PASS_DEVICE_PENDING"}
CONCLUSIONS = PASSING_CONCLUSIONS | {"INCOMPLETE", "BLOCKED"}
OBLIGATION_STATUSES = {
    "COVERED_AUTOMATED",
    "COVERED_MANUAL",
    "UNVERIFIED",
    "BLOCKED",
    "NOT_APPLICABLE",
}
GATE_STATUSES = {"PASS", "FAIL", "SKIPPED", "UNVERIFIED", "BLOCKED"}
EVIDENCE_KINDS = {"AUTOMATED", "MANUAL", "REVIEW"}
CORE_REQUIRED_GATES = {
    "android-review-diff",
    "android-review-code-quality",
    "android-audit-stability",
    "android-test-and-fix",
    "android-build",
    "android-lint",
}


class DeliveryGateError(RuntimeError):
    """表示最终报告、配置或当前交付上下文无法可靠校验。"""


def requirement_file_digest(path: Path) -> str:
    """计算需求源文件摘要，使需求变化后旧报告自动失效。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DeliveryGateError(f"无法读取需求文件: {path}: {exc}") from exc


def current_context(config_path: Path, config: dict[str, Any]) -> dict[str, str]:
    """返回最终报告必须绑定的需求、基线和当前代码摘要。"""
    paths = resolve_config_paths(config, config_path)
    if not paths.project_path or not paths.project_path.is_dir():
        raise DeliveryGateError(f"项目路径无效: {paths.project_path}")
    if not paths.requirement_path or not paths.requirement_path.is_file():
        raise DeliveryGateError(f"需求文件无效: {paths.requirement_path}")
    result_path = (paths.requirement_dir / "test-results" / "delivery-result.json").resolve()
    excluded: set[str] = set()
    try:
        excluded.add(result_path.relative_to(paths.project_path.resolve()).as_posix())
    except ValueError:
        pass
    try:
        snapshot = current_delivery_snapshot(
            paths.project_path,
            baseline_path_for_config(config_path),
            exclude_paths=excluded,
        )
    except GitInspectionError as exc:
        raise DeliveryGateError(str(exc)) from exc
    return {
        **snapshot,
        "requirement_file_sha256": requirement_file_digest(paths.requirement_path),
        "result_path": str(result_path),
    }


def _indexed(items: Any, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    """按 id 建立唯一索引，避免重复证据或义务互相覆盖。"""
    if not isinstance(items, list):
        errors.append(f"{label} 必须是数组")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] 必须是 object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{label}[{index}].id 必须是非空字符串")
            continue
        if identifier in indexed:
            errors.append(f"{label} 存在重复 id: {identifier}")
            continue
        indexed[identifier] = item
    return indexed


def validate_delivery_result(payload: Any, context: dict[str, str]) -> list[str]:
    """验证报告结构、证据引用、通过结论和当前代码新鲜度，返回全部错误。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["delivery-result.json 根节点必须是 object"]
    if payload.get("version") != 1:
        errors.append("version 必须为 1")
    for field in ("baseline_id", "requirement_file_sha256", "snapshot_sha256"):
        if payload.get(field) != context[field]:
            errors.append(f"{field} 与当前需求/代码不一致，旧证据已经失效")
    conclusion = payload.get("conclusion")
    if conclusion not in CONCLUSIONS:
        errors.append(f"conclusion 必须是 {sorted(CONCLUSIONS)} 之一")

    evidence = _indexed(payload.get("evidence"), "evidence", errors)
    obligations = _indexed(payload.get("obligations"), "obligations", errors)
    gates = _indexed(payload.get("gates"), "gates", errors)

    for identifier, item in evidence.items():
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            errors.append(f"evidence {identifier} 的 kind 无效")
        if item.get("snapshot_sha256") != context["snapshot_sha256"]:
            errors.append(f"evidence {identifier} 不是当前最终代码上的新鲜证据")
        if kind == "AUTOMATED":
            command = item.get("command")
            if not isinstance(command, list) or not command or not all(
                isinstance(part, str) and part for part in command
            ):
                errors.append(f"自动证据 {identifier} 缺少参数数组形式的 command")
            if item.get("exit_code") != 0:
                errors.append(f"自动证据 {identifier} 的 exit_code 必须为 0")
        elif kind in {"MANUAL", "REVIEW"}:
            if not isinstance(item.get("summary"), str) or not item["summary"].strip():
                errors.append(f"{kind} 证据 {identifier} 缺少实际结果 summary")

    def validate_refs(owner: str, item: dict[str, Any]) -> list[str]:
        """验证一个义务或门禁引用的证据都真实存在。"""
        refs = item.get("evidence_ids", [])
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            errors.append(f"{owner}.evidence_ids 必须是字符串数组")
            return []
        if len(refs) != len(set(refs)):
            errors.append(f"{owner}.evidence_ids 不得重复")
        missing = [ref for ref in refs if ref not in evidence]
        if missing:
            errors.append(f"{owner} 引用了不存在的证据: {', '.join(missing)}")
        return refs

    passing = conclusion in PASSING_CONCLUSIONS
    for identifier, item in obligations.items():
        if not re.fullmatch(r"BDD-[0-9]+/T[0-9]+", identifier):
            errors.append(f"obligation id 格式无效: {identifier}")
        if not isinstance(item.get("required"), bool):
            errors.append(f"obligation {identifier}.required 必须是 boolean")
        status = item.get("status")
        if status not in OBLIGATION_STATUSES:
            errors.append(f"obligation {identifier} 的 status 无效")
        refs = validate_refs(f"obligation {identifier}", item)
        required = item.get("required") is True
        if passing and required and status not in {"COVERED_AUTOMATED", "COVERED_MANUAL"}:
            errors.append(f"必需 obligation {identifier} 尚未覆盖，不能使用通过结论")
        if status == "COVERED_AUTOMATED" and not any(
            evidence.get(ref, {}).get("kind") == "AUTOMATED" for ref in refs
        ):
            errors.append(f"obligation {identifier} 缺少自动执行证据")
        if status == "COVERED_MANUAL" and not any(
            evidence.get(ref, {}).get("kind") == "MANUAL" for ref in refs
        ):
            errors.append(f"obligation {identifier} 缺少实际人工证据")

    for identifier, item in gates.items():
        if not isinstance(item.get("required"), bool):
            errors.append(f"gate {identifier}.required 必须是 boolean")
        status = item.get("status")
        if status not in GATE_STATUSES:
            errors.append(f"gate {identifier} 的 status 无效")
        refs = validate_refs(f"gate {identifier}", item)
        if passing and item.get("required") is True and status != "PASS":
            errors.append(f"必需 gate {identifier} 未通过")
        if status == "PASS" and not refs:
            errors.append(f"gate {identifier} 标记 PASS 但没有证据")

    if passing and not obligations:
        errors.append("通过结论至少需要一个原子 BDD/Then obligation")
    if passing and obligations and not any(item.get("required") is True for item in obligations.values()):
        errors.append("通过结论至少需要一个 required=true 的原子 BDD/Then obligation")
    if passing and not gates:
        errors.append("通过结论至少需要一个交付 gate")
    if passing:
        for gate_id in sorted(CORE_REQUIRED_GATES):
            gate = gates.get(gate_id)
            if not gate:
                errors.append(f"通过结论缺少核心 gate: {gate_id}")
            elif gate.get("required") is not True or gate.get("status") != "PASS":
                errors.append(f"核心 gate {gate_id} 必须 required=true 且状态为 PASS")
    return errors


def load_result(path: Path) -> Any:
    """读取最终 JSON；格式损坏时输出可操作错误而不是 Python traceback。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryGateError(f"最终交付报告无法读取: {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """输出当前摘要或校验最终报告；返回 0 仅表示最终通过结论真实有效。"""
    parser = argparse.ArgumentParser(description="校验 Android Delivery 最终证据")
    parser.add_argument("command", choices=("snapshot", "validate"))
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--result", default=None, help="delivery-result.json 路径")
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    try:
        config = load_config(config_path)
        context = current_context(config_path, config)
        if args.command == "snapshot":
            print(json.dumps(context, ensure_ascii=False, indent=2))
            return 0
        result_path = Path(args.result).expanduser().resolve() if args.result else Path(context["result_path"])
        payload = load_result(result_path)
        errors = validate_delivery_result(payload, context)
    except (DeliveryError, DeliveryGateError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if errors:
        print("❌ 最终交付门禁未通过:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if payload["conclusion"] not in PASSING_CONCLUSIONS:
        print(f"❌ 报告结论为 {payload['conclusion']}，当前交付未完成", file=sys.stderr)
        return 2
    print("✅ 最终交付证据与当前需求、Git 基线和代码摘要一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
