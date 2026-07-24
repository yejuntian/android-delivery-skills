#!/usr/bin/env python3
"""脚本名称：atomic_write.py

用途：为外部状态、机器收据和人读 md 影子提供统一的原子写入。

核心流程：写入同目录临时文件、按需设置 0600 权限，再 ``replace`` 替换目标，
中断时只留上一份完整记录而不是半文件。失败时清理临时文件。

职责边界：只负责安全写入，不校验内容、不解释 JSON 或 md 语义，也不决定写哪里。
各业务脚本仍各自决定路径和权限；本模块统一此前散落在多处的重复实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_text_atomic(
    path: Path | str,
    content: str,
    *,
    private: bool = False,
    encoding: str = "utf-8",
) -> None:
    """原子写入文本文件；private=True 时把文件权限设为仅属主可读写。

    用同目录 ``.tmp`` 临时文件再 ``replace``，避免中途中断留下半文件。成功后清理
    临时文件；失败时尝试删除临时文件再抛出原异常，由调用方决定如何回滚。
    """
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(content, encoding=encoding)
        if private:
            temporary.chmod(0o600)
        temporary.replace(target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def write_json_atomic(
    path: Path | str,
    payload: Any,
    *,
    private: bool = True,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """原子写入 JSON 文件，默认 0600 权限，保持各收据和快照的私密性。

    序列化失败时不在磁盘留下任何痕迹；写入失败时清理临时文件。
    """
    text = json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent) + "\n"
    write_text_atomic(path, text, private=private)
