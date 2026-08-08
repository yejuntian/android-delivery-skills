#!/usr/bin/env python3
"""核对 Android 交付规格状态与 JUnit XML 结果，防止空测试和旧报告假绿。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


STATUS_PATTERN = re.compile(r"(?m)^status:\s*([a-zA-Z_-]+)\s*$")
SOURCE_SUFFIXES = {
    ".gradle",
    ".java",
    ".kt",
    ".kts",
    ".properties",
    ".toml",
    ".xml",
}


class VerificationError(RuntimeError):
    """表示最终结果缺失、过期或不满足非假绿要求。"""


@dataclass
class TestTotals:
    """汇总一组 JUnit XML 报告中的测试结果。"""

    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    files: int = 0


def _confirmed_spec(path: Path) -> None:
    """确认规格存在且 frontmatter 中的状态为 confirmed。"""
    if not path.is_file():
        raise VerificationError(f"规格文件不存在: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise VerificationError(f"规格缺少 YAML frontmatter: {path}")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    match = STATUS_PATTERN.search(frontmatter)
    if not match or match.group(1).lower() != "confirmed":
        raise VerificationError(f"规格尚未确认: {path}")


def _git_output(project: Path, *args: str) -> str:
    """在 Android 项目中执行只读 Git 查询并返回文本。"""
    result = subprocess.run(
        ["git", *args],
        cwd=project,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise VerificationError(result.stderr.strip() or "Git 查询失败")
    return result.stdout


def _latest_input_time(project: Path, spec: Path) -> float:
    """计算当前提交、未提交源码和规格中的最新修改时间。"""
    if not (project / ".git").exists():
        raise VerificationError(f"不是 Git 项目: {project}")
    head_time = float(_git_output(project, "show", "-s", "--format=%ct", "HEAD").strip())
    latest = max(head_time, spec.stat().st_mtime)
    status = _git_output(project, "status", "--porcelain=v1", "-z")
    entries = [entry for entry in status.split("\0") if entry]
    for entry in entries:
        relative = entry[3:].split(" -> ")[-1]
        path = project / relative
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
            latest = max(latest, path.stat().st_mtime)
    return latest


def _report_files(paths: list[Path]) -> list[Path]:
    """展开用户提供的报告文件或目录并去重。"""
    reports: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".xml":
            reports.add(path.resolve())
        elif path.is_dir():
            reports.update(item.resolve() for item in path.rglob("*.xml") if item.is_file())
        else:
            raise VerificationError(f"测试报告路径不存在: {path}")
    if not reports:
        raise VerificationError("没有找到 JUnit XML 测试报告")
    return sorted(reports)


def _integer(node: ET.Element, name: str) -> int:
    """读取 JUnit 数字属性，缺失时按零处理。"""
    value = node.attrib.get(name, "0")
    try:
        return int(value)
    except ValueError as exc:
        raise VerificationError(f"JUnit 属性不是整数: {name}={value}") from exc


def _summarize(reports: list[Path], latest_input: float) -> TestTotals:
    """汇总报告并拒绝早于当前规格或代码的结果。"""
    totals = TestTotals()
    for report in reports:
        if report.stat().st_mtime < latest_input:
            raise VerificationError(f"测试报告早于当前代码或规格: {report}")
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError as exc:
            raise VerificationError(f"JUnit XML 无法解析: {report}: {exc}") from exc
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        if not suites:
            raise VerificationError(f"JUnit XML 不含 testsuite: {report}")
        totals.files += 1
        for suite in suites:
            totals.tests += _integer(suite, "tests")
            totals.failures += _integer(suite, "failures")
            totals.errors += _integer(suite, "errors")
            totals.skipped += _integer(suite, "skipped")
    if totals.tests <= 0:
        raise VerificationError("测试数量为零，不能支持通过结论")
    if totals.tests - totals.skipped <= 0:
        raise VerificationError("所有测试均被跳过，不能支持通过结论")
    if totals.failures or totals.errors:
        raise VerificationError(
            f"测试未通过: tests={totals.tests}, failures={totals.failures}, errors={totals.errors}"
        )
    return totals


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析项目、规格和一个或多个 JUnit 报告路径。"""
    parser = argparse.ArgumentParser(description="核对已确认规格和当前 JUnit 测试结果")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--report", required=True, action="append", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """执行只读核验并输出简短中文结果。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    project = args.project.expanduser().resolve()
    spec = args.spec.expanduser().resolve()
    try:
        _confirmed_spec(spec)
        latest_input = _latest_input_time(project, spec)
        totals = _summarize(_report_files(args.report), latest_input)
    except (OSError, VerificationError) as exc:
        print(f"最终测试结果核验失败: {exc}", file=sys.stderr)
        return 2
    print(
        "最终测试结果核验通过: "
        f"reports={totals.files}, tests={totals.tests}, skipped={totals.skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
