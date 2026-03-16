import os
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
from PIL import Image

from config.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_temp_dir() -> str:
    """确保并返回临时目录。"""
    os.makedirs(CONFIG.TEMP_DIR, exist_ok=True)
    return CONFIG.TEMP_DIR


def pdf_to_images(pdf_path: str) -> List[Dict]:
    """将 PDF 文件转换为单页 PNG 图像列表。"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image 未安装，无法处理 PDF 文件。请执行：pip install pdf2image"
        ) from exc

    _ensure_temp_dir()
    try:
        logger.info("开始将 PDF 转换为图片：%s", pdf_path)
        pages = convert_from_path(
            pdf_path,
            dpi=CONFIG.DPI,
            fmt="png",
            transparent=False,
        )
    except Exception as exc:
        logger.error("PDF 转图片失败：%s", exc)
        raise RuntimeError(f"PDF 转图片失败：{exc}") from exc

    results = []
    for idx, img in enumerate(pages, start=1):
        page_path = os.path.join(CONFIG.TEMP_DIR, f"page_{idx}.png")
        # 处理透明背景为白色
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        img.save(page_path)
        width, height = img.size
        logger.debug("生成页面图片：%s, 宽=%d, 高=%d", page_path, width, height)
        results.append({
            "page_num": idx,
            "image_path": page_path,
            "width": width,
            "height": height,
        })

    logger.info("PDF 转图片完成，共 %d 页。", len(results))
    return results


def _resize_if_needed(image) -> Tuple:
    """若图像宽度超过最大限制，则按比例缩放。"""
    h, w = image.shape[:2]
    if w <= CONFIG.MAX_WIDTH:
        return image, w, h
    scale = CONFIG.MAX_WIDTH / float(w)
    new_w = CONFIG.MAX_WIDTH
    new_h = int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    logger.debug("图像缩放：(%d, %d) -> (%d, %d)", w, h, new_w, new_h)
    return resized, new_w, new_h


def enhance_image(image_path: str) -> Tuple[str, int, int]:
    """对图像进行增强处理（去噪、CLAHE），保留彩色信息，不二值化。"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图像文件不存在：{image_path}")

    _ensure_temp_dir()
    logger.info("开始增强图像：%s", image_path)
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(f"无法读取图像：{image_path}")

    # 高斯去噪
    blurred = cv2.GaussianBlur(image, (3, 3), 0)

    # 转为灰度用于 CLAHE
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gray)

    # 将增强后的灰度图转回 BGR（保留三通道）
    enhanced_color = cv2.cvtColor(clahe_img, cv2.COLOR_GRAY2BGR)

    # 缩放（如果需要）
    resized, w, h = _resize_if_needed(enhanced_color)

    enhanced_path = os.path.join(CONFIG.TEMP_DIR, f"enhanced_{Path(image_path).stem}.png")
    cv2.imwrite(enhanced_path, resized)
    logger.info("图像增强完成：%s，宽=%d，高=%d", enhanced_path, w, h)
    return enhanced_path, w, h


def preprocess_input(path: str) -> List[Dict]:
    """根据输入文件类型完成整体预处理流程。返回页面信息，包含增强后图像路径和原始图像路径。"""
    suffix = Path(path).suffix.lower()
    pages = []

    if suffix == ".pdf":
        raw_pages = pdf_to_images(path)
        for page in raw_pages:
            original = page["image_path"]   # pdf2image 生成的 PNG
            enhanced, w, h = enhance_image(original)
            pages.append({
                "page_num": page["page_num"],
                "image_path": enhanced,       # 用于检测
                "original_path": original,    # 用于内容识别（原始未增强）
                "width": w,
                "height": h,
            })
    else:
        enhanced, w, h = enhance_image(path)
        pages.append({
            "page_num": 1,
            "image_path": enhanced,
            "original_path": path,
            "width": w,
            "height": h,
        })

    logger.info("预处理完成，共 %d 页/图像。", len(pages))
    return pages