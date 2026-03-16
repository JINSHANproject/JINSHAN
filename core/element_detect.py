import cv2
from typing import List, Dict

from config.config import CONFIG
from utils.logger import get_logger
from utils.ocr_helper import (
    parse_ocr_result,
    parse_structure_result,
    get_ocr_instance,
    get_structure_instance,
)

logger = get_logger(__name__)


def _classify_text_type(bbox: List[int], page_height: int) -> str:
    """基于位置与高度粗略区分标题、正文、页眉、页脚（降级回退使用）。"""
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    rel_top = y1 / max(page_height, 1)
    rel_h = h / max(page_height, 1)

    if rel_top < 0.08:
        return "header"
    if y2 / max(page_height, 1) > 0.92:
        return "footer"
    if rel_h > 0.04:
        return "title"
    return "p"


def _detect_elements_ppstructure(page: Dict) -> List[Dict]:
    """使用 PPStructure 进行版面分析，获取完整的元素类型和内容。"""
    image_path = page["image_path"]
    page_num = page["page_num"]

    img = cv2.imread(image_path)
    if img is None:
        logger.error("无法读取图片：%s", image_path)
        return []

    logger.info("开始 PPStructure 版面分析：page=%d", page_num)
    try:
        structure = get_structure_instance()
        result = structure(img)
    except Exception as exc:
        logger.warning("PPStructure 版面分析失败，将降级为纯 OCR：%s", exc)
        return []

    if not result:
        logger.warning("PPStructure 未返回任何结果：page=%d", page_num)
        return []

    elements = parse_structure_result(result)
    for ele in elements:
        ele["page_num"] = page_num

    logger.info(
        "PPStructure 版面分析完成：page=%d，检测到 %d 个区域，展开为 %d 个元素。",
        page_num,
        len(result),
        len(elements),
    )
    return elements


def _detect_elements_ocr_fallback(page: Dict) -> List[Dict]:
    """降级方案：使用纯文本 OCR + 位置规则分类元素。"""
    image_path = page["image_path"]
    page_num = page["page_num"]

    img = cv2.imread(image_path)
    if img is None:
        logger.error("无法读取图片（降级）：%s", image_path)
        return []

    logger.info("降级 OCR 文本行检测：page=%d", page_num)
    ocr = get_ocr_instance()
    result = ocr.ocr(img)
    lines = parse_ocr_result(result)
    page_height = img.shape[0]

    elements = []
    for bbox, text, score in lines:
        elements.append({
            "element_type": _classify_text_type(bbox, page_height),
            "bbox": bbox,
            "content": text,
            "page_num": page_num,
            "extra": {
                "confidence": score,
                "raw_type": "text",
                "ocr_lines": [],
            },
        })
    return elements


def _count_text_elements(elements: List[Dict]) -> int:
    """统计元素列表中含有非空文本内容的文本类元素数量。"""
    text_types = {"p", "title", "header", "footer", "h1", "h2", "h3"}
    return sum(
        1 for e in elements
        if e.get("element_type") in text_types and e.get("content", "").strip()
    )


def _merge_ocr_supplement(
    pp_elements: List[Dict],
    ocr_elements: List[Dict],
    iou_thresh: float = 0.5,
) -> List[Dict]:
    """
    将 OCR 补充元素合并进 PPStructure 结果，去除与已有元素重叠的行。

    对每条 OCR 行，若其 bbox 与已有任一元素的 IoU 超过阈值，则认为已被覆盖，不重复添加。
    """
    def _area(b):
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    def _iou(a, b):
        ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
        ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        return inter / ((_area(a) + _area(b) - inter) or 1)

    existing_bboxes = [e["bbox"] for e in pp_elements]
    merged = list(pp_elements)

    for ocr_ele in ocr_elements:
        ob = ocr_ele["bbox"]
        covered = any(_iou(ob, eb) > iou_thresh for eb in existing_bboxes)
        if not covered:
            merged.append(ocr_ele)
            existing_bboxes.append(ob)

    return merged


def detect_elements(pages: List[Dict]) -> List[Dict]:
    """
    对预处理后的页面进行元素检测与类型分类。

    策略（三级保障）：
    1. USE_PP_STRUCTURE=True 时，调用 PPStructure 版面分析
    2. PPStructure 成功但文本元素数量过少（< MIN_TEXT_FROM_PPSTRUCTURE）时，
       额外运行纯 OCR 补充，并通过 IoU 去重后合并
    3. PPStructure 完全失败（异常或空结果）时，完全降级为纯 OCR
    """
    # PPStructure 版面分析结果中，期望检测到的最少文字行数阈值。
    # 低于此值则认为版面分析质量不足，启动 OCR 补充扫描。
    MIN_TEXT_FROM_PPSTRUCTURE = 3

    all_elements = []

    for page in pages:
        page_num = page["page_num"]
        pp_elements = []

        if CONFIG.USE_PP_STRUCTURE:
            pp_elements = _detect_elements_ppstructure(page)

        text_count = _count_text_elements(pp_elements)

        if not pp_elements:
            # PPStructure 完全无结果，完全降级
            logger.info("page=%d PPStructure 无结果，启用降级 OCR 检测。", page_num)
            all_elements.extend(_detect_elements_ocr_fallback(page))

        elif text_count < MIN_TEXT_FROM_PPSTRUCTURE:
            # PPStructure 有结果但文本内容严重不足，补充 OCR 扫描
            logger.info(
                "page=%d PPStructure 文本元素数 %d < %d，启用 OCR 补充扫描。",
                page_num, text_count, MIN_TEXT_FROM_PPSTRUCTURE,
            )
            ocr_elements = _detect_elements_ocr_fallback(page)
            merged = _merge_ocr_supplement(pp_elements, ocr_elements)
            logger.info(
                "page=%d OCR 补充合并完成：PP=%d，OCR=%d，合并后=%d。",
                page_num, len(pp_elements), len(ocr_elements), len(merged),
            )
            all_elements.extend(merged)

        else:
            # PPStructure 结果质量足够，直接使用
            all_elements.extend(pp_elements)

    logger.info("元素检测完成，共识别 %d 个元素。", len(all_elements))
    return all_elements
