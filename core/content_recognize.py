import cv2
from typing import List, Dict

from utils.logger import get_logger
from utils.ocr_helper import ocr_image

logger = get_logger(__name__)


def recognize_text_elements(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """对文本元素进行二次 OCR 补充（如果检测阶段未获取文本）。"""
    page_map = {p["page_num"]: p for p in pages}
    for ele in elements:
        if ele["element_type"] not in ("p", "h2", "header", "footer"):
            continue
        if ele["content"]:   # 已有内容则跳过
            continue

        page = page_map.get(ele["page_num"])
        if not page:
            continue

        # 优先使用原始图像进行识别
        img_path = page.get("original_path", page["image_path"])
        img = cv2.imread(img_path)
        if img is None:
            continue

        x1, y1, x2, y2 = ele["bbox"]
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        ocr_results = ocr_image(crop)
        texts = [t[1] for t in ocr_results]
        ele["content"] = " ".join(texts)
    return elements


def recognize_contents(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    logger.info("开始内容识别补充...")
    elements = recognize_text_elements(pages, elements)
    logger.info("内容识别补充完成")
    return elements