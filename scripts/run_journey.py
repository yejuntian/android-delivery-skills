#!/usr/bin/env python3
"""
================================================================================
脚本名称：run_journey.py
用    途：Journey 自动化运行编排器。让"老项目也能用 AGP 9 的 Journey 测 UI"。

核心机制(方法一：隔离壳项目)：
  老项目的 AGP 版本一点不动，Journey 跑在一个独立的 AGP 9 壳项目里，
  通过环境变量 JOURNEYS_CUSTOM_APP_ID 把测试目标"重定向"到老项目的包名。

完整闭环：
  1. 嗅探老项目 applicationId（调 detect_package.detect）
  2. 用老项目自己的 AGP 构建 debug APK（assembleDebug）
  3. adb 安装该 APK 到设备
  4. 在壳项目里设置 JOURNEYS_CUSTOM_APP_ID=<老项目包名>
  5. 跑壳项目的 journeysTest Gradle task（AGP 9 驱动 Journey 执行）
  6. 解析结果：收集每步的 pass/fail + 失败截图 + Reasoning
  7. 失败时输出自修复线索（哪步挂、截图在哪、AI 据此重调布局）

前置依赖：
  - android CLI（用于设备/SDK 能力；可用 `android update` 升级）
  - adb + 在线设备/模拟器
  - JDK 17+
  - 壳项目已初始化（journey-harness/，含 AGP 9 + testSuites）
  - 老项目能 `./gradlew assembleDebug` 通过

退出码语义：
  0 = 全部 Journey 通过
  1 = 环境错误（无设备/无包名/构建失败）—— 不应进入自修复循环
  2 = 有 Journey 失败 —— 应进入自修复循环（读 stdout 的失败线索）
================================================================================
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from detect_package import detect  # noqa: E402


def run(cmd: list[str], cwd: str | None = None, env: dict | None = None,
        check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    """统一命令执行器。capture=False 时实时打印输出(适合长任务)。"""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, env=env, check=check,
                          text=True, capture_output=capture)


def check_device() -> str | None:
    """检查是否有在线设备,返回第一个设备 serial;没有返回 None。"""
    try:
        out = subprocess.check_output(["adb", "devices"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.splitlines()[1:]:
        line = line.strip()
        if line.endswith("\tdevice"):
            return line.split("\t")[0]
    return None


def build_target_apk(project_path: str, module: str, variant: str) -> Path | None:
    """用老项目自己的 AGP 构建 debug APK。返回 APK 路径或 None。"""
    gradlew = "./gradlew" if os.path.isfile(f"{project_path}/gradlew") else "gradlew"
    task = f":{module}:assemble{variant.capitalize()}"
    result = run([gradlew, task], cwd=project_path, check=False, capture=False)
    if result.returncode != 0:
        print(f"❌ 老项目构建失败: {task}")
        return None
    # 定位产物
    pattern = f"{project_path}/{module}/build/outputs/apk/{variant.lower()}/*.apk"
    import glob
    apks = glob.glob(pattern)
    return Path(apks[0]) if apks else None


def install_apk(apk: Path) -> bool:
    """adb 安装 APK 到设备(-r 覆盖安装)。"""
    result = run(["adb", "install", "-r", str(apk)], capture=False)
    return result.returncode == 0


def run_journeys(harness_dir: Path, target_package: str, device: str | None) -> int:
    """在壳项目里跑 journeysTest,通过环境变量重定向到老项目包名。"""
    env = os.environ.copy()
    env["JOURNEYS_CUSTOM_APP_ID"] = target_package
    if device:
        env["ANDROID_SERIAL"] = device
    # 文档要求关闭配置缓存(gradle.properties 已设,这里双保险)
    env["ORG_GRADLE_PROJECT_org.gradle.configuration-cache"] = "false"

    gradlew = "./gradlew" if (harness_dir / "gradlew").exists() else "gradlew"
    # AGP 9 的 journeysTest task 名
    result = run([gradlew, ":harness-app:testDebugJourneysTest"],  # task 名以实际为准
                 cwd=str(harness_dir), env=env, capture=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Journey 自动化运行(壳项目隔离方案)")
    parser.add_argument("--config", default="profiles/local.yaml")
    parser.add_argument("--harness-dir",
                        default=str(SCRIPT_DIR.parent / "journey-harness"))
    parser.add_argument("--module", default="app", help="老项目的 app 模块名")
    parser.add_argument("--variant", default="debug")
    parser.add_argument("--skip-build", action="store_true",
                        help="跳过构建+安装,假设老项目 APK 已装好")
    args = parser.parse_args()

    # --- 1. 读配置 ---
    import yaml
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    project_path = config.get("project_path")
    explicit_pkg = config.get("app_package_name")  # 允许手动覆盖
    if not project_path:
        print("❌ local.yaml 缺少 project_path")
        return 1

    harness_dir = Path(args.harness_dir)
    if not harness_dir.is_dir():
        print(f"❌ 壳项目不存在: {harness_dir}")
        print("   请确认 journey-harness/ 已初始化(含 AGP 9 + testSuites)")
        return 1

    # --- 2. 检查设备 ---
    device = check_device()
    if not device:
        print("❌ 没有在线设备/模拟器,adb devices 无 device 项。")
        print("   请先启动模拟器或连接真机。Journey 无法在无设备时运行。")
        return 1
    print(f"✅ 设备在线: {device}")

    # --- 3. 嗅探或读取包名 ---
    if explicit_pkg:
        target_package = explicit_pkg
        print(f"📌 包名(来自配置覆盖): {target_package}")
    else:
        result = detect(project_path)
        if "error" in result:
            print(f"❌ {result['error']}")
            return 1
        target_package = result["default"]
        print(f"📌 包名(自动嗅探,来源 {result['source']}): {target_package}")

    # --- 4. 构建 + 安装老项目 ---
    if not args.skip_build:
        print("\n=== 构建老项目 APK(使用老项目自己的 AGP)===")
        apk = build_target_apk(project_path, args.module, args.variant)
        if not apk:
            print("❌ 未找到构建产物 APK。请检查 module/variant。")
            return 1
        print(f"✅ APK: {apk}")
        print("\n=== 安装到设备 ===")
        if not install_apk(apk):
            print("❌ 安装失败。请检查设备状态、签名冲突等。")
            return 1

    # --- 5. 在壳项目跑 Journey ---
    print(f"\n=== 在壳项目跑 Journey(目标包: {target_package}) ===")
    rc = run_journeys(harness_dir, target_package, device)

    # --- 6. 结果判定 ---
    print("\n=== Journey 结果 ===")
    if rc == 0:
        print("✅ 全部 Journey 步骤通过。")
        print("👉 AI 指令: UI 验证通过,可继续后续审查或交付。")
        return 0
    else:
        print("❌ 有 Journey 步骤失败。")
        print("👉 AI 指令: 进入自修复循环——")
        print("  1. 读取上方 Gradle/Journey 输出的失败 step、Action Taken、Reasoning。")
        print("  2. 读取失败截图(通常在壳项目 build/ 或设备 pull)。")
        print("  3. 对照 BDD 的 Then 断言,定位是布局/资源/状态/逻辑哪一层挂了。")
        print("  4. 修改老项目代码,重跑: python3 run_journey.py")
        print("  5. 连续失败超 3 次必须暂停,向用户报告失败详情和截图。")
        return 2


if __name__ == "__main__":
    sys.exit(main())
