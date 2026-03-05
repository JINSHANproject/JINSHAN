import cv2
from typing import List, Dict

from config.config import CONFIG
from utils.logger import get_logger
from utils.ocr_helper import parse_ocr_result, get_ocr_instance

logger = get_logger(__name__)


def _classify_text_type(bbox: List[int], page_height: int) -> str:
    """基于位置与高度粗略区分标题、正文、页眉、页脚。"""
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    rel_top = y1 / max(page_height, 1)
    rel_h = h / max(page_height, 1)

    if rel_top < 0.1:
        return "header"
    if y2 / max(page_height, 1) > 0.9:
        return "footer"
    if rel_h > 0.04:  # 高度较大的行视为标题
        return "h2"
    return "p"


def detect_elements(pages: List[Dict]) -> List[Dict]:
    """对预处理后的页面进行文本行检测与简单类型分类。"""
    ocr = get_ocr_instance()
    all_elements = []

    for page in pages:
        page_num = page["page_num"]
        image_path = page["image_path"]  # 增强后的图像
        img = cv2.imread(image_path)
        if img is None:
            logger.error("无法读取图片：%s", image_path)
            continue

        logger.info("开始文本行检测：page=%d", page_num)
        result = ocr.ocr(img)
        lines = parse_ocr_result(result)
        page_height = img.shape[0]

        for bbox, text, score in lines:
            element = {
                "element_type": _classify_text_type(bbox, page_height),
                "bbox": bbox,
                "content": text,
                "page_num": page_num,
                "extra": {"confidence": score}
            }
            all_elements.append(element)

    logger.info("文本行检测完成，共识别 %d 个元素。", len(all_elements))
    return all_elements