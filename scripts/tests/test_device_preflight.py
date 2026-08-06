"""验证共享 Android 设备预检的状态解析和选择边界。"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from .. import device_preflight  # noqa: E402
from ..test_support import patch_module_global  # noqa: E402


ADB_DEVICES = """List of devices attached
R5CT123456\tdevice product:panther model:Pixel_7 device:panther
emulator-5554\tdevice product:sdk_gphone_x86_64 model:sdk_gphone_x86_64 device:generic_x86_64
offline-device\toffline product:unknown model:unknown device:unknown
"""


class DevicePreflightTests(unittest.TestCase):
    """设备预检只选择 adb 在线设备，并对 UI 真机要求物理设备。"""

    def test_parse_devices_classifies_online_physical_and_emulator(self) -> None:
        devices = device_preflight.parse_devices(ADB_DEVICES)
        self.assertEqual(
            [
                {"serial": "R5CT123456", "status": "device", "kind": "PHYSICAL"},
                {"serial": "emulator-5554", "status": "device", "kind": "EMULATOR"},
                {"serial": "offline-device", "status": "offline", "kind": "PHYSICAL"},
            ],
            devices,
        )

    def test_choose_device_requires_serial_when_multiple_devices_exist(self) -> None:
        with patch_module_global(device_preflight, "_run", return_value=(0, ADB_DEVICES)):
            serial, error = device_preflight.choose_device(None)
            self.assertIsNone(serial)
            self.assertIn("多个设备", error)

            serial, error = device_preflight.choose_device(
                "R5CT123456",
                require_physical=True,
            )
            self.assertEqual("R5CT123456", serial)
            self.assertIsNone(error)

    def test_preflight_requires_successful_physical_screenshot(self) -> None:
        with (
            patch_module_global(
                device_preflight,
                "_run",
                side_effect=[(0, ADB_DEVICES), (0, "device\n")],
            ),
            patch_module_global(
                device_preflight,
                "_capture_screenshot",
                return_value=(True, None),
            ),
        ):
            result = device_preflight.preflight_device(
                "R5CT123456",
                require_physical=True,
                screenshot_path=Path("screen.png"),
            )
        self.assertEqual(
            {
                "status": "READY",
                "serial": "R5CT123456",
                "kind": "PHYSICAL",
                "screenshot_ok": True,
            },
            result,
        )

    def test_preflight_rejects_emulator_for_physical_ui_acceptance(self) -> None:
        with patch_module_global(device_preflight, "_run", return_value=(0, ADB_DEVICES)):
            result = device_preflight.preflight_device(
                "emulator-5554",
                require_physical=True,
            )
        self.assertEqual("UNAVAILABLE", result["status"])
        self.assertIn("不是物理设备", result["reason"])


if __name__ == "__main__":
    unittest.main()
