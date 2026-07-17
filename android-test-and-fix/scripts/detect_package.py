#!/usr/bin/env python3
"""
================================================================================
脚本名称：detect_package.py
用    途：自动嗅探目标 Android 项目的 applicationId（包名）。
         仅作源码阶段诊断；正式运行以实际 APK 中的 applicationId 为准。

局限说明：源码正则无法可靠解析 applicationIdSuffix、productFlavor、约定插件或动态
Gradle 值。正式 Journey 执行必须使用 apkanalyzer/aapt 从最终 APK 读取真实包名。

嗅探优先级（从可靠到兜底）：
1. 各 app 模块 build.gradle(.kts) 中的 applicationId =
2. AndroidManifest.xml 根标签的 package="..." （AGP 8 以下旧写法）
3. 上述都失败 → 退出并报错，绝不瞎猜包名。

支持多 app 模块项目：输出全部 applicationId，并标记 :app 模块为默认。
================================================================================
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def find_gradle_modules(project_path: Path) -> list[Path]:
    """定位项目内所有含 build.gradle(.kts) 的模块目录（排除 build/ 缓存）。"""
    modules = []
    for gradle_file in project_path.rglob("build.gradle*"):
        # 跳过构建产物、.gradle 缓存、buildSrc 输出
        if any(part in {"build", ".gradle", ".idea", "buildSrc"} for part in gradle_file.parts):
            continue
        modules.append(gradle_file.parent)
    return modules


def extract_application_id(gradle_file: Path) -> str | None:
    """从单个 build.gradle(.kts) 中提取 applicationId（仅 app 模块才有）。"""
    try:
        text = gradle_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # 匹配: applicationId "com.xxx" 或 applicationId = "com.xxx"
    match = re.search(r'applicationId\s*[=]?\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else None


def extract_manifest_package(project_path: Path) -> list[str]:
    """兜底:从 AndroidManifest.xml 的 package 属性提取。"""
    packages = []
    for manifest in project_path.rglob("AndroidManifest.xml"):
        if "build" in manifest.parts:
            continue
        try:
            text = manifest.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(r'package\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            packages.append(match.group(1))
    return packages


def detect(project_path: str) -> dict:
    """执行源码级包名嗅探，返回 {default, all, source}，结果仅供诊断。"""
    root = Path(project_path)
    if not root.is_dir():
        return {"error": f"项目路径无效: {project_path}"}

    found: list[tuple[str, str]] = []  # (module_relative, applicationId)
    for module in find_gradle_modules(root):
        app_id = extract_application_id(module / "build.gradle.kts")
        if app_id is None:
            app_id = extract_application_id(module / "build.gradle")
        if app_id:
            rel = module.relative_to(root)
            found.append((str(rel), app_id))

    if found:
        # 默认优先取名为 app 的模块,否则取第一个
        default = next((aid for mod, aid in found if mod == "app"), found[0][1])
        return {
            "default": default,
            "all": [{"module": m, "applicationId": a} for m, a in found],
            "source": "build.gradle applicationId",
        }

    # 兜底:manifest package
    manifest_pkgs = extract_manifest_package(root)
    if manifest_pkgs:
        return {
            "default": manifest_pkgs[0],
            "all": [{"module": "(manifest)", "applicationId": p} for p in manifest_pkgs],
            "source": "AndroidManifest.xml package",
        }

    return {"error": "未嗅探到 applicationId 或 package,请手动在 local.yaml 指定 app_package_name"}


def cmd_detect(args):
    result = detect(args.project_path)
    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    print("=== 包名嗅探结果 ===")
    print(f"📌 来源: {result['source']}")
    print(f"📌 默认 applicationId: {result['default']}")
    if len(result["all"]) > 1:
        print("📦 发现多个 app 模块:")
        for item in result["all"]:
            print(f"  - 模块 {item['module']}: {item['applicationId']}")

    if args.export:
        Path(args.export).write_text(result["default"], encoding="utf-8")
        print(f"✅ 已写入: {args.export}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="嗅探 Android 项目 applicationId")
    parser.add_argument("--project-path", required=True, help="目标 Android 项目根路径")
    parser.add_argument("--export", help="把默认 applicationId 写入指定文件")
    cmd_detect(parser.parse_args())
