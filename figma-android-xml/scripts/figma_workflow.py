#!/usr/bin/env python3
"""
=============================================================================
Figma to Android XML - 智能编排与视觉资源引擎 (Figma Workflow Orchestrator)
=============================================================================

【设计初衷】
本脚本作为 `figma-android-xml` AI 技能的核心中枢。它专门负责处理网络请求与多模态资源下载。
（已废弃容易导致 AI 死锁的 plan/run 指令注入架构，回归纯粹的 fetch 职能。）

【核心能力】
1. 🖼️ 多模态视觉桥梁 (Fetch 命令)
   - 自动解析用户贴入的 Figma 网页链接，精准提取 File Key 和 Node ID。
   - 调用 Figma 官方 REST API，将设计稿节点原汁原味地导出为高清切图（根据 .env 动态设置 scale）。
   - 彻底解决 AI "看不见本地图片" 造成的界面脑补问题，为高保真还原提供像素级参考。

2. 📂 拔插式缓存管理与分层隔离 (Standalone Ready & Layering)
   - 每次执行彻底清理旧缓存，防止冗余数据堆积干扰 AI。
   - 智能分层隔离：按 `file_key` 和 `node_id` 生成专属独立子目录，多 Frame 下载绝不互相覆盖。
   - 支持通过 `.env` 独立运行或向后兼容 `local.yaml` 读取统一路径。

3. 🚀 极限网络并发加速 (Performance Turbo)
   - 多线程提速：内部集成 ThreadPoolExecutor，多图拉取性能提升数倍。
=============================================================================
"""

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
import shutil
import concurrent.futures
from pathlib import Path
from urllib.error import HTTPError

SKILL_ROOT = Path(__file__).resolve().parent.parent

def find_project_root():
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / "gradlew").exists():
            return p
    return cwd

PROJECT_ROOT = find_project_root()

def load_env():
    """
    加载环境变量配置 (读取 .env 文件)。
    用于获取 FIGMA_TOKEN，以及解耦技能作为独立使用的 CACHE_DIR 等敏感或个性化配置。
    """
    env_vars = {}
    for env_file in [SKILL_ROOT / ".env", PROJECT_ROOT / ".env"]:
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def get_cache_dir():
    """
    获取缓存根目录。
    优先使用 skill 自带 .env 的 CACHE_DIR；缺失时兼容系统环境变量，最后回退到 /tmp。
    """
    env_vars = load_env()
    configured_dir = (
        env_vars.get("CACHE_DIR")
        or os.environ.get("FIGMA_ANDROID_XML_CACHE_DIR")
        or os.environ.get("CACHE_DIR")
        or "/tmp"
    )
    return Path(configured_dir).expanduser()

# 核心工作目录 (动态读取配置)
BASE_DIR = get_cache_dir() / "figma-android-xml"
UI_REQ_DIR = BASE_DIR

def parse_figma_url(url):
    """
    从 Figma 分享链接中解析 file_key 与 node_id。
    支持 node-id 出现在任意 query 参数位置，例如 ?timeline=...&node-id=811-174。
    """
    parsed = urllib.parse.urlparse(url)
    path_match = re.search(r"/(?:design|file)/([^/?#]+)", parsed.path)
    if not path_match:
        path_match = re.search(r"(?:design|file)/([^/?#]+)", url)

    query = urllib.parse.parse_qs(parsed.query)
    node_values = query.get("node-id") or query.get("node_id")

    if not node_values:
        node_match = re.search(r"(?:[?&#]|^)node-id=([^&#]+)", url)
        node_values = [node_match.group(1)] if node_match else []

    if not path_match or not node_values:
        return None

    file_key = urllib.parse.unquote(path_match.group(1))
    node_id_raw = urllib.parse.unquote(node_values[0]).strip()
    node_id = node_id_raw.replace("-", ":")
    return file_key, node_id

def cmd_fetch(urls, scale_override=None):
    """
    根据用户提供的 Figma URL 列表，批量提取设计文件和 Node ID。
    调用 Figma REST API 下载高清 (根据 .env 动态 scale) PNG 切图，存入统一配置的缓存目录中。
    """
    env_vars = load_env()
    token = env_vars.get("FIGMA_TOKEN")
    if not token:
        print("❌ 错误: 在 .env 文件中未找到 FIGMA_TOKEN")
        exit(1)

    UI_REQ_DIR.mkdir(parents=True, exist_ok=True)

    # 恢复每次执行彻底清理：清空 UI_REQ_DIR 下的所有内容（无冗余数据）
    for item in UI_REQ_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # 核心解析逻辑：从 Figma 网页端链接中提取 file_key 和 node_id
    # file_key -> list of node_ids
    file_nodes = {}

    for url in urls:
        parsed = parse_figma_url(url)
        if parsed:
            file_key, node_id = parsed
            if file_key not in file_nodes:
                file_nodes[file_key] = []
            file_nodes[file_key].append(node_id)
        else:
            print(f"⚠️ 警告: 无法解析 Figma URL: {url}")

    if not file_nodes:
        print("❌ 错误: 没有成功解析出任何有效的 Figma 链接。")
        exit(1)

    def _download_task(nid, img_url, f_key):
        if not img_url: return
        safe_name = nid.replace(":", "-")
        node_dir = UI_REQ_DIR / f_key / safe_name
        node_dir.mkdir(parents=True, exist_ok=True)
        save_path = node_dir / f"frame_{safe_name}.png"
        print(f"⬇️ 开始下载 {nid}...")
        try:
            with urllib.request.urlopen(urllib.request.Request(img_url), timeout=60) as res, open(save_path, "wb") as f:
                f.write(res.read())
            print(f"✅ 下载完成 {nid} -> {save_path.name}")
        except Exception as e:
            print(f"❌ 下载 {nid} 失败: {e}")

    env_vars = load_env()
    target_density = env_vars.get("TARGET_BITMAP_DENSITY", "xxhdpi").lower()
    density_to_scale = {
        "mdpi": 1,
        "hdpi": 1.5,
        "xhdpi": 2,
        "xxhdpi": 3,
        "xxxhdpi": 4
    }
    if scale_override is not None:
        target_scale = scale_override
    else:
        target_scale = density_to_scale.get(target_density, 3) # default to xxhdpi (3x) if unknown

    print(f"开始并发拉取 Figma 高清切图 (目标密度: {target_density}, scale={target_scale})...")
    for file_key, node_ids in file_nodes.items():
        ids_str = ",".join(node_ids)
        api_url = f"https://api.figma.com/v1/images/{file_key}?ids={ids_str}&format=png&scale={target_scale}"

        req = urllib.request.Request(api_url)
        req.add_header("X-Figma-Token", token)

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode("utf-8"))
                images = data.get("images", {})

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(_download_task, nid, url, file_key) for nid, url in images.items()]
                    concurrent.futures.wait(futures)
        except HTTPError as e:
            print(f"❌ 请求失败 (HTTP {e.code}): 请检查 Token 是否有权限访问文件 {file_key}")
            exit(1)
        except Exception as e:
            print(f"❌ 发生未知错误: {str(e)}")
            exit(1)

    print(f"\n✅ 所有高清切图已保存至: {UI_REQ_DIR}")
    print("👉 请 AI 主动使用 view_file 工具读取上述目录中的 .png 图片。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Figma to XML 视觉资产拉取工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="从 Figma 链接批量下载节点高清截图")
    fetch_parser.add_argument("urls", nargs="+", help="Figma 分享链接列表")
    fetch_parser.add_argument("--scale", type=float, help="覆盖 .env 设定的缩放比例 (如 1)")

    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(args.urls, getattr(args, 'scale', None))
