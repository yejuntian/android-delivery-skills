#!/usr/bin/env python3
"""脚本名称：install_maintenance_hook.py

用途：把 Android Delivery Skill 的维护验证接入当前 Git 仓库 pre-commit hook。

核心流程：定位真实 Git hooks/pre-commit 路径，生成调用 maintenance_pre_commit.py 的轻量包装器；
已有非本脚本管理的 hook 默认不覆盖，除非显式传入 --force。

职责边界：只安装或覆盖 pre-commit hook 文件；不判断暂存路径、不运行维护验证、不修改业务代码。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import stat
import subprocess
import sys


HOOK_MARKER = "Android Delivery maintenance pre-commit"


def default_skill_dir() -> Path:
    """返回本脚本所属的 Android Delivery Skill 目录。"""
    return Path(__file__).resolve().parents[1]


def git_hook_path(skill_dir: Path) -> Path:
    """通过 git rev-parse 解析当前仓库真实 hooks/pre-commit 路径。"""
    completed = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks/pre-commit"],
        cwd=skill_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "无法定位 Git hook 路径")
    raw_path = Path(completed.stdout.strip())
    return raw_path if raw_path.is_absolute() else (skill_dir / raw_path).resolve()


def hook_body(skill_dir: Path) -> str:
    """生成可执行 pre-commit hook 内容。"""
    script = skill_dir / "scripts" / "maintenance_pre_commit.py"
    return f'''#!/bin/sh
# {HOOK_MARKER}
exec python3 {str(script)!r} --skill-dir {str(skill_dir)!r} "$@"
'''


def install_hook(skill_dir: Path, force: bool = False) -> Path:
    """安装维护 pre-commit hook，必要时拒绝覆盖用户已有 hook。"""
    hook_path = git_hook_path(skill_dir)
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER not in existing and not force:
            raise RuntimeError(f"pre-commit hook 已存在且不是本脚本管理，请使用 --force: {hook_path}")
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(hook_body(skill_dir), encoding="utf-8")
    current_mode = hook_path.stat().st_mode
    hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Install Android Delivery maintenance pre-commit hook.")
    parser.add_argument("--skill-dir", default=str(default_skill_dir()), help="Android Delivery Skill 目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有非本脚本管理的 pre-commit hook")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """命令入口：安装 hook 并输出安装位置。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    skill_dir = Path(args.skill_dir).expanduser().resolve()
    try:
        hook_path = install_hook(skill_dir, force=args.force)
    except (OSError, RuntimeError) as exc:
        print(f"安装维护 pre-commit hook 失败: {exc}", file=sys.stderr)
        return 1
    print(f"已安装 Android Delivery 维护 pre-commit hook: {hook_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
