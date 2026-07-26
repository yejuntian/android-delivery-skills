#!/usr/bin/env python3
"""脚本名称：maintenance_pre_commit.py

用途：作为 Git pre-commit hook 的流程维护变更检测入口。

核心流程：读取当前 Git 暂存文件列表，判断是否命中 Android Delivery Skill 流程维护路径；
命中时调用 validate_maintenance.py，未命中时快速跳过。

职责边界：只做暂存路径判断和维护验证命令编排；不安装 hook、不修改文件、不实现具体 eval、
不运行 Android 构建、设备、真实项目交付或模型服务。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Sequence


MAINTENANCE_PATH_PATTERNS = (
    "_shared/",
    "evals/",
    "references/open-source-design-rationale.md",
    "requirements.txt",
    "scripts/",
    "android-implement-and-verify/references/",
    "android-implement-and-verify/templates/",
)


@dataclass(frozen=True)
class HookDecision:
    """保存 pre-commit 是否需要运行维护验证的判断结果。"""

    should_validate: bool
    matched_paths: tuple[str, ...]


def default_skill_dir() -> Path:
    """返回本脚本所属的 Android Delivery Skill 目录。"""
    return Path(__file__).resolve().parents[1]


def git_root(cwd: Path) -> Path:
    """读取当前 Git 仓库根目录，兼容从 worktree 子目录调用。"""
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "当前目录不是 Git 仓库")
    return Path(completed.stdout.strip()).resolve()


def staged_paths(root: Path) -> tuple[str, ...]:
    """返回 Git 暂存区中新增、复制、修改或重命名后的路径。"""
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "无法读取 Git 暂存文件")
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def skill_prefix(root: Path, skill_dir: Path) -> str:
    """返回 skill_dir 相对 Git 根目录的 POSIX 前缀，用于匹配暂存路径。"""
    resolved_skill = skill_dir.resolve()
    try:
        relative = resolved_skill.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Skill 目录不在 Git 仓库内: {resolved_skill}") from exc
    prefix = relative.as_posix().rstrip("/")
    return f"{prefix}/" if prefix else ""


def is_skill_file(path: str, prefix: str) -> str | None:
    """如果暂存路径属于当前 Skill，返回去掉仓库前缀后的 Skill 内路径。"""
    if prefix:
        if not path.startswith(prefix):
            return None
        return path[len(prefix) :]
    return path


def is_maintenance_path(skill_path: str) -> bool:
    """判断 Skill 内路径是否属于流程维护敏感范围。"""
    if skill_path.endswith("/SKILL.md") or skill_path == "SKILL.md":
        return True
    if skill_path.startswith("android-") and skill_path.endswith("/SKILL.md"):
        return True
    if skill_path.startswith("android-") and "/references/" in skill_path:
        return True
    return any(skill_path == pattern.rstrip("/") or skill_path.startswith(pattern) for pattern in MAINTENANCE_PATH_PATTERNS)


def decide_validation(paths: Sequence[str], root: Path, skill_dir: Path) -> HookDecision:
    """根据暂存路径决定是否运行维护验证，并返回命中的 Skill 内路径。"""
    prefix = skill_prefix(root, skill_dir)
    matched: list[str] = []
    for path in paths:
        skill_path = is_skill_file(path, prefix)
        if skill_path and is_maintenance_path(skill_path):
            matched.append(skill_path)
    return HookDecision(should_validate=bool(matched), matched_paths=tuple(sorted(set(matched))))


def run_maintenance_validation(skill_dir: Path) -> int:
    """运行统一维护验证命令，返回其退出码。"""
    return subprocess.run(
        [sys.executable, "scripts/validate_maintenance.py"],
        cwd=skill_dir,
        check=False,
    ).returncode


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数，测试可通过 --skill-dir 指向临时副本。"""
    parser = argparse.ArgumentParser(description="Run Android Delivery maintenance pre-commit check.")
    parser.add_argument("--skill-dir", default=str(default_skill_dir()), help="Android Delivery Skill 目录")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：命中维护路径时运行统一验证，未命中时跳过。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    skill_dir = Path(args.skill_dir).expanduser().resolve()
    try:
        root = git_root(skill_dir)
        decision = decide_validation(staged_paths(root), root, skill_dir)
    except RuntimeError as exc:
        print(f"维护 pre-commit 检查失败: {exc}", file=sys.stderr)
        return 2
    if not decision.should_validate:
        print("Android Delivery 维护验证：未检测到流程维护暂存改动，跳过。")
        return 0
    print("Android Delivery 维护验证：检测到流程维护暂存改动：")
    for path in decision.matched_paths:
        print(f"- {path}")
    return run_maintenance_validation(skill_dir)


if __name__ == "__main__":
    raise SystemExit(main())
