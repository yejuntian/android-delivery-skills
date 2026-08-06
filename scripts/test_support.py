"""测试专用的模块全局替换，避免 Mock 目标与 IDE 解析漂移。"""

from __future__ import annotations

from types import ModuleType
from typing import Any
from unittest import mock


_MISSING = object()


class _ModuleGlobalPatch:
    """可重复进入的模块全局 patcher，与 unittest.mock patcher 行为一致。"""

    def __init__(
        self,
        module: ModuleType,
        name: str,
        replacement: Any,
        mock_options: dict[str, Any],
    ) -> None:
        self.module = module
        self.name = name
        self.replacement = replacement
        self.mock_options = mock_options
        self._active_patches: list[Any] = []

    def __enter__(self) -> Any:
        namespace = vars(self.module)
        if self.name not in namespace:
            raise AttributeError(
                f"{self.module.__name__} 没有可替换的全局名称: {self.name}"
            )
        replacement = (
            mock.Mock(**self.mock_options)
            if self.replacement is _MISSING
            else self.replacement
        )
        active_patch = mock.patch.dict(namespace, {self.name: replacement})
        self._active_patches.append(active_patch)
        active_patch.__enter__()
        return replacement

    def __exit__(self, *exc_info: Any) -> Any:
        if not self._active_patches:
            return None
        active_patch = self._active_patches.pop()
        return active_patch.__exit__(*exc_info)


def patch_module_global(
    module: ModuleType,
    name: str,
    replacement: Any = _MISSING,
    **mock_options: Any,
) -> _ModuleGlobalPatch:
    """构造可重复使用的模块全局 patcher。"""
    if replacement is not _MISSING and mock_options:
        raise TypeError("提供 replacement 时不能再传 Mock 配置")
    return _ModuleGlobalPatch(module, name, replacement, mock_options)
