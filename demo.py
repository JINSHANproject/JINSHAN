"""
多模态文档识别系统 - 命令行入口

用法示例：
  # 使用 test_data/ 目录中的测试文件（自动发现）
  python demo.py

  # 指定文件路径
  python demo.py --input your_doc.pdf

  # 指定输出格式（html / json / both）
  python demo.py --input your_doc.pdf --format both

  # 关闭 PPStructure 版面分析，使用纯 OCR 降级模式
  python demo.py --no-ppstructure
"""

import argparse
import os
import time

import cv2
import numpy as np

from config.config import CONFIG
from core.preprocess import preprocess_input
from core.element_detect import detect_elements
from core.content_recognize import recognize_contents
from core.logic_rebuild import rebuild_logic
from core.output_generator import generate_html, generate_json
from utils.file_io import (
    ensure_directories,
    find_test_file,
    save_html,
    save_json,
    detect_file_type,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_sample_test_file(test_dir: str) -> str:
    """若测试目录中不存在文件，则生成一个简单的示例 PNG。"""
    os.makedirs(test_dir, exist_ok=True)
    sample_path = os.path.join(test_dir, "sample.png")
    if os.path.exists(sample_path):
        return sample_path

    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.putText(img, "示例文档标题", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.putText(img, "这是一段示例正文，用于测试 OCR。", (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.imwrite(sample_path, img)
    logger.info("已自动生成示例测试文件：%s", sample_path)
    return sample_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="多模态文档识别系统（基于 PaddleOCR / PPStructure）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        metavar="FILE",
        help="输入文件路径（PDF 或图片）。未指定时自动在 test_data/ 目录下查找。",
    )
    parser.add_argument(
        "--format", "-f",
        type=str,
        default=CONFIG.OUTPUT_FORMAT,
        choices=["html", "json", "both"],
        dest="output_format",
        help="输出格式：html / json / both（默认：%(default)s）",
    )
    parser.add_argument(
        "--no-ppstructure",
        action="store_true",
        default=False,
        help="禁用 PPStructure 版面分析，强制使用纯 OCR 降级模式。",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="指定输出目录（默认：output/）",
    )
    return parser.parse_args()


def _step(name: str, t0: float) -> float:
    """打印步骤耗时并返回当前时间戳。"""
    elapsed = time.time() - t0
    logger.info("  [✓] %s  (%.2fs)", name, elapsed)
    return time.time()


def run_demo(args: argparse.Namespace) -> None:
    total_start = time.time()
    ensure_directories()

    # 覆盖配置项（命令行优先）
    if args.no_ppstructure:
        CONFIG.USE_PP_STRUCTURE = False
        logger.info("已禁用 PPStructure，使用纯 OCR 模式。")
    if args.output_dir:
        CONFIG.OUTPUT_DIR = args.output_dir
        CONFIG.IMAGE_OUTPUT_DIR = os.path.join(args.output_dir, "images")
        os.makedirs(CONFIG.OUTPUT_DIR, exist_ok=True)
        os.makedirs(CONFIG.IMAGE_OUTPUT_DIR, exist_ok=True)

    # ── 确定输入文件 ──────────────────────────────
    test_file = args.input
    if not test_file:
        test_dir = os.path.join(CONFIG.BASE_DIR, "test_data")
        test_file = find_test_file(test_dir)
        if not test_file:
            logger.warning("未找到测试文件，将自动生成示例文件。")
            test_file = _ensure_sample_test_file(test_dir)

    try:
        ftype = detect_file_type(test_file)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("输入文件检测失败：%s", exc)
        return

    logger.info("=" * 60)
    logger.info("开始处理：%s（类型：%s）", test_file, ftype)
    logger.info("输出格式：%s", args.output_format)
    logger.info("PPStructure：%s", "开启" if CONFIG.USE_PP_STRUCTURE else "关闭（纯OCR）")
    logger.info("=" * 60)

    t = time.time()

    # ── Step 1: 预处理 ────────────────────────────
    try:
        pages = preprocess_input(test_file)
    except Exception as exc:
        logger.error("预处理阶段发生错误：%s", exc)
        return
    t = _step("预处理完成", t)

    # ── Step 2: 元素检测 ──────────────────────────
    try:
        elements = detect_elements(pages)
        logger.info("  检测到 %d 个元素", len(elements))
    except Exception as exc:
        logger.error("元素检测阶段发生错误：%s", exc)
        return
    t = _step("元素检测完成", t)

    # ── Step 3: 内容识别 ──────────────────────────
    try:
        elements = recognize_contents(pages, elements)
    except Exception as exc:
        logger.error("内容识别阶段发生错误：%s", exc)
        return
    t = _step("内容识别完成", t)

    # ── Step 4: 逻辑重建 ──────────────────────────
    try:
        # 从第一页获取页面尺寸
        page_width = pages[0].get("width", 0) if pages else 0
        page_height = pages[0].get("height", 0) if pages else 0
        elements = rebuild_logic(elements, page_width=page_width, page_height=page_height)
    except Exception as exc:
        logger.error("逻辑重建阶段发生错误：%s", exc)
        return
    t = _step("逻辑重建完成", t)

    # ── Step 5: 输出 ──────────────────────────────
    try:
        doc_title = os.path.splitext(os.path.basename(test_file))[0]
        output_paths = []

        if args.output_format in ("html", "both"):
            html = generate_html(elements, wrap_html=True, title=doc_title)
            out_path = save_html(html, "result.html")
            output_paths.append(out_path)

        if args.output_format in ("json", "both"):
            json_str = generate_json(elements)
            out_path = save_json(json_str, "result.json")
            output_paths.append(out_path)

    except Exception as exc:
        logger.error("输出生成阶段发生错误：%s", exc)
        return
    t = _step("输出生成完成", t)

    # ── 汇总 ──────────────────────────────────────
    total_elapsed = time.time() - total_start
    logger.info("=" * 60)
    logger.info("处理完成！总耗时：%.2fs", total_elapsed)
    for path in output_paths:
        logger.info("  输出文件：%s", path)

    # 打印元素类型统计
    type_stats: dict = {}
    for ele in elements:
        et = ele.get("element_type", "unknown")
        type_stats[et] = type_stats.get(et, 0) + 1
    logger.info("元素类型统计：%s", type_stats)
    logger.info("=" * 60)


if __name__ == "__main__":
    run_demo(_parse_args())
