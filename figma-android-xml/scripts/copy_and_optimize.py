#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
图片压缩搬运工 (Asset Porter)
=============================================================================

【脚本简介】
这是一个专门为 AI 大模型设计的图片资产搬运拦截器。
在 Android 自动化切图流转中，禁止使用原生 `cp` 命令，必须通过本脚本将 Figma 导出的图片
搬运到 Android 工程的 `res/drawable-xxhdpi` 等目录下。

【核心功能】
1. 主动瘦身与多级自愈降级：
   - [优先] 尝试使用 Pillow 库将图片无损转换为 WebP 格式。
   - [自愈] 若未安装 Pillow，则自动调用 `pip install Pillow` 进行静默安装。
   - [系统级兜底] 若安装失败或无网络，自动降级调用 macOS 原生 `sips` 或跨平台 `cwebp` 命令。
   - [最低保障] 若以上全线溃败，退化为原生 `cp` 复制。
2. 柔性拦截：设置 100KB 绝对红线。如果压缩后的体积仍 >= 100KB，为了防止撑爆 APK 体积，
   本脚本将拒绝复制动作，防止大图污染 Android 工程。
3. AI 友好输出：永远返回 exit(0) 以防止打断 AI 工作流，而是通过特定的控制台打印前缀
   （[SUCCESS] 或 [SKIPPED]）来指导 AI 助理在 XML 中的下一步操作。

【使用方法】
python3 scripts/copy_and_optimize.py <原始文件路径> <目标文件路径>

示例:
python3 scripts/copy_and_optimize.py /tmp/figma_cache/icon.png ./app/src/main/res/drawable-xxhdpi/icon.png
=============================================================================
"""

import sys
import os
import shutil
import subprocess

# 体积红线：超过 100KB 将被无情拦截
MAX_SIZE_KB = 100.0

def _try_pillow_compression(src_path, dest_path):
    """
    尝试使用 Pillow 库将 PNG 转换为无损 WebP 格式。
    
    【核心逻辑】
    - 判断目标后缀是否为 .png。如果是，则将其替换为 .webp，并调用 Image.save(..., 'WEBP', lossless=True)。
    - 如果不是 .png (例如本身就是 webp 或 jpg)，则退化为直接复制。
    
    Args:
        src_path (str): 原始切图的绝对路径。
        dest_path (str): 目标写入路径。
        
    Returns:
        tuple[str, bool]: (最终保存的文件路径, 是否执行了压缩逻辑)
    """
    from PIL import Image
    if dest_path.lower().endswith(".png"):
        final_dest_path = dest_path[:-4] + ".webp"
        with Image.open(src_path) as img:
            img.save(final_dest_path, "WEBP", lossless=True)
        return final_dest_path, True
    else:
        shutil.copy2(src_path, dest_path)
        return dest_path, False

def _try_system_commands(src_path, dest_path):
    """
    尝试使用操作系统底层的原生命令进行图片压缩转换 (无依赖兜底方案)。
    
    【防线机制】
    - 方案 A (macOS原生): 尝试调用 macOS 自带的 `sips` 命令，无缝将图片转为 webp。这是零依赖的杀手锏。
    - 方案 B (跨平台工具): 尝试调用标准的 `cwebp` 命令行工具。
    
    Args:
        src_path (str): 原始切图的绝对路径。
        dest_path (str): 目标写入路径。
        
    Returns:
        tuple[str, bool]: (最终保存的文件路径, 是否执行了压缩逻辑)
        
    Raises:
        RuntimeError: 当所有底层命令行工具 (sips, cwebp) 均不可用时抛出。
    """
    if not dest_path.lower().endswith(".png"):
        shutil.copy2(src_path, dest_path)
        return dest_path, False

    final_dest_path = dest_path[:-4] + ".webp"
    
    # 方案 A: macOS 专属，系统自带零依赖
    try:
        subprocess.run(['sips', '-s', 'format', 'webp', src_path, '--out', final_dest_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return final_dest_path, True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 方案 B: 跨平台 cwebp (如有安装)
    try:
        subprocess.run(['cwebp', '-lossless', src_path, '-o', final_dest_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return final_dest_path, True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 全部失败
    raise RuntimeError("系统原生压缩命令不可用")

def _optimize_image(src_path, dest_path):
    """
    负责执行图片压缩优化，并返回最终的目标路径与是否经过了压缩的标志。
    
    【多级自愈降级策略】
    1. 正常执行 `_try_pillow_compression`。
    2. 若触发 `ImportError`，则在后台静默执行 `pip install Pillow`，安装成功后重试第 1 步。
    3. 若安装依然失败 (如无网络/无权限)，退化调用 `_try_system_commands` 寻求系统原生工具协助。
    4. 若原生工具全部失效或发生未知崩溃，捕获最顶层的 `Exception`，退化为系统原生复制 (`shutil.copy2`)，保证工作流不中断。
    
    Args:
        src_path (str): 原始切图的绝对路径。
        dest_path (str): 期望的目标路径。
        
    Returns:
        tuple[str, bool]: (最终落地在系统中的文件路径, 是否经过了压缩)
    """
    final_dest_path = dest_path
    
    try:
        return _try_pillow_compression(src_path, dest_path)
    except ImportError:
        print("[INFO] 检测到未安装 Pillow，正在为您自动安装以实现图片无损压缩...")
        try:
            # 自动安装 Pillow 自愈
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return _try_pillow_compression(src_path, dest_path)
        except Exception as e:
            print(f"[WARNING] 自动安装 Pillow 失败，尝试调用系统原生命令兜底...")
            try:
                return _try_system_commands(src_path, dest_path)
            except Exception:
                # 最终退化为原生复制
                shutil.copy2(src_path, dest_path)
                return dest_path, False
    except Exception:
        # 其他所有未知异常兜底 (例如图片格式损毁引发的 IOError)
        if os.path.exists(final_dest_path) and final_dest_path != dest_path:
            os.remove(final_dest_path)
        shutil.copy2(src_path, dest_path)
        return dest_path, False

def _enforce_size_redline(final_dest_path, used_compression):
    """
    执行 100KB 体积红线检测，并根据结果向大模型输出下一步的行动指南 (Action Guide)。
    
    【核心逻辑】
    - 计算传入的文件最终落地体积。
    - 若 >= 100KB: 触发物理阻断 (强行删除已生成的文件)，并打印 [SKIPPED] 警告，强制大模型在 XML 中改用 tools:src 占位。
    - 若 < 100KB: 放行，并打印 [SUCCESS] 成功日志，允许大模型在 XML 中正常使用 android:src (针对静态UI)。
    
    Args:
        final_dest_path (str): 最终保存在磁盘上的图片路径。
        used_compression (bool): 该图片是否经过了 WebP 转换压缩。
    """
    try:
        file_size_bytes = os.path.getsize(final_dest_path)
        file_size_kb = file_size_bytes / 1024.0

        if file_size_kb >= MAX_SIZE_KB:
            # 物理阻断：超标大图无情删除，绝不入库
            os.remove(final_dest_path)
            print(f"[SKIPPED] 警告：文件过大 ({file_size_kb:.2f}KB >= {MAX_SIZE_KB}KB 阈值)！")
            print(f"说明：出于防 APK 膨胀红线，该图已被系统拦截并未拷入 Android 工程。")
            print(f"行动指南：大模型，请在 XML 中改用 tools:src=\"@tools:sample/backgrounds/scenic\" 占位，并在报告中通知用户需通过服务器网络动态加载。")
        else:
            # 成功放行
            comp_msg = "已转换为无损 WebP" if used_compression else "未压缩原生复制"
            print(f"[SUCCESS] 资源已优化 ({file_size_kb:.2f}KB, {comp_msg}) 并复制成功。")
            res_type = "mipmap" if "mipmap" in final_dest_path else "drawable"
            print(f"行动指南：请使用 android:src=\"@{res_type}/{os.path.splitext(os.path.basename(final_dest_path))[0]}\" 正常引用。")
    except Exception as e:
        print(f"[SKIPPED] 处理目标文件体积时发生异常: {e}")

def main():
    if len(sys.argv) < 3:
        print("用法: python3 copy_and_optimize.py <src_path> <dest_path>")
        sys.exit(0)  # 防御性编程：永远返回 0 避免打断大模型

    src_path = sys.argv[1]
    dest_path = sys.argv[2]

    if not os.path.exists(src_path):
        print(f"[SKIPPED] 错误：源文件不存在 {src_path}")
        sys.exit(0)

    # 尝试创建目标文件夹
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # 职责1：压缩转换
    final_dest_path, used_compression = _optimize_image(src_path, dest_path)
    
    # 职责2：体积拦截与结果输出
    _enforce_size_redline(final_dest_path, used_compression)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
