#!/usr/bin/env python3
"""共享 Android 设备预检，供 Journey 和 UI 真机验收复用。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ADB_TIMEOUT_SECONDS = 30
DEVICE_READY = "READY"
DEVICE_UNAVAILABLE = "UNAVAILABLE"
DEVICE_BLOCKED = "BLOCKED"


def _run(command: list[str]) -> tuple[int, str]:
    """运行不含用户输入的 adb 查询命令，并返回退出码和脱敏前的短输出。"""
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=ADB_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return 127, "adb 未安装或不在 PATH 中"
    except subprocess.TimeoutExpired:
        return 124, "adb 命令超时"
    return completed.returncode, completed.stdout or ""


def _device_kind(serial: str, attributes: dict[str, str]) -> str:
    """按 adb 标识识别模拟器；其余在线目标按物理设备处理。"""
    model = attributes.get("model", "").lower()
    product = attributes.get("product", "").lower()
    if (
        serial.startswith("emulator-")
        or "emulator" in model
        or product.startswith(("sdk_", "sdk_gphone", "generic"))
    ):
        return "EMULATOR"
    return "PHYSICAL"


def parse_devices(output: str) -> list[dict[str, str]]:
    """解析 ``adb devices -l``，只保留可定位的设备行。"""
    devices: list[dict[str, str]] = []
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) < 2 or fields[0] == "List":
            continue
        serial, status = fields[0], fields[1]
        attributes: dict[str, str] = {}
        for field in fields[2:]:
            if ":" in field:
                key, value = field.split(":", 1)
                attributes[key] = value
        devices.append({
            "serial": serial,
            "status": status,
            "kind": _device_kind(serial, attributes),
        })
    return devices


def _online_devices() -> tuple[list[dict[str, str]], str | None]:
    """查询在线设备；错误原因用于 UI 的未验证说明。"""
    exit_code, output = _run(["adb", "devices", "-l"])
    if exit_code != 0:
        return [], output.strip() or "adb devices 执行失败"
    online = [item for item in parse_devices(output) if item["status"] == "device"]
    return online, None


def list_devices() -> list[str]:
    """返回 adb 状态为 ``device`` 的在线设备序列号。"""
    devices, _ = _online_devices()
    return [item["serial"] for item in devices]


def _choose_from_devices(
    devices: list[dict[str, str]],
    explicit: str | None,
    *,
    require_physical: bool,
) -> tuple[str | None, str | None]:
    """从一次查询结果中选择设备，避免预检期间重复扫描 adb。"""
    if explicit:
        selected = next((item for item in devices if item["serial"] == explicit), None)
        if selected is None:
            return None, f"指定设备不在线: {explicit}"
        if require_physical and selected["kind"] != "PHYSICAL":
            return None, f"指定设备不是物理设备: {explicit}"
        return explicit, None
    if not devices:
        return None, "adb devices 没有在线设备"
    if len(devices) > 1:
        return None, "检测到多个设备，请用 --device 指定: " + ", ".join(
            item["serial"] for item in devices
        )
    if require_physical and devices[0]["kind"] != "PHYSICAL":
        return None, "在线设备是模拟器，UI 真机验收需要物理设备"
    return devices[0]["serial"], None


def choose_device(
    explicit: str | None,
    *,
    require_physical: bool = False,
) -> tuple[str | None, str | None]:
    """选择设备；多设备时拒绝猜测，UI 真机验收可要求物理设备。"""
    devices, query_error = _online_devices()
    if query_error:
        return None, query_error
    return _choose_from_devices(
        devices,
        explicit,
        require_physical=require_physical,
    )


def _capture_screenshot(serial: str, target: Path) -> tuple[bool, str | None]:
    """捕获 PNG 并检查文件头，避免只凭命令退出码判定截图成功。"""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"截图目录无法创建: {exc}"
    try:
        with target.open("wb") as output:
            completed = subprocess.run(
                ["adb", "-s", serial, "exec-out", "screencap", "-p"],
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
                timeout=ADB_TIMEOUT_SECONDS,
            )
    except FileNotFoundError:
        return False, "adb 未安装或不在 PATH 中"
    except subprocess.TimeoutExpired:
        return False, "adb 截图命令超时"
    except OSError as exc:
        return False, f"截图文件无法写入: {exc}"
    if completed.returncode != 0:
        return False, (completed.stderr or b"").decode("utf-8", errors="replace").strip() or "截图命令失败"
    try:
        header = target.read_bytes()[:8]
    except OSError as exc:
        return False, f"截图文件无法读取: {exc}"
    if header != b"\x89PNG\r\n\x1a\n":
        return False, "截图产物不是有效 PNG"
    return True, None


def preflight_device(
    explicit: str | None = None,
    *,
    require_physical: bool = False,
    screenshot_path: Path | None = None,
) -> dict[str, Any]:
    """执行设备预检，可选地验证真机截图命令。"""
    devices, query_error = _online_devices()
    if query_error:
        return {"status": DEVICE_UNAVAILABLE, "reason": query_error}
    selected_serial, choose_error = _choose_from_devices(
        devices,
        explicit,
        require_physical=require_physical,
    )
    if choose_error or selected_serial is None:
        return {"status": DEVICE_UNAVAILABLE, "reason": choose_error or "没有可用设备"}
    selected = next(item for item in devices if item["serial"] == selected_serial)

    state_code, state_output = _run(["adb", "-s", selected_serial, "get-state"])
    if state_code != 0 or state_output.strip() != "device":
        return {
            "status": DEVICE_UNAVAILABLE,
            "serial": selected_serial,
            "kind": selected["kind"],
            "reason": "设备未处于可执行状态",
        }

    result: dict[str, Any] = {
        "status": DEVICE_READY,
        "serial": selected_serial,
        "kind": selected["kind"],
    }
    if screenshot_path is not None:
        screenshot_ok, screenshot_error = _capture_screenshot(selected_serial, screenshot_path)
        result["screenshot_ok"] = screenshot_ok
        if not screenshot_ok:
            result.update({"status": DEVICE_BLOCKED, "reason": screenshot_error or "截图失败"})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 Android 设备并可选捕获真机截图")
    parser.add_argument("--device", default=None, help="多设备时指定 adb serial")
    parser.add_argument("--require-physical", action="store_true", help="拒绝模拟器")
    parser.add_argument("--screenshot", type=Path, default=None, help="成功连接后保存 PNG")
    args = parser.parse_args(argv)
    result = preflight_device(
        args.device,
        require_physical=args.require_physical,
        screenshot_path=args.screenshot,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == DEVICE_READY and (
        args.screenshot is None or result.get("screenshot_ok") is True
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
