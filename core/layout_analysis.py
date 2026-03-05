import cv2
from paddleocr import PPStructure
from typing import List, Dict

from config.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


def _classify_text_type(bbox: List[int], page_height: int, layout_type: str) -> str:
    """结合布局类型和位置细化元素类型"""
    x1, y1, x2, y2 = bbox
    rel_top = y1 / max(page_height, 1)
    rel_bottom = y2 / max(page_height, 1)

    # 页眉页脚检测（基于位置）
    if rel_top < 0.1:
        return "header"
    if rel_bottom > 0.9:
        return "footer"

    # 根据布局类型映射
    if layout_type == "title":
        return "h2"
    elif layout_type == "text":
        return "p"
    elif layout_type == "figure":
        return "image"
    elif layout_type == "table":
        return "table"
    elif layout_type == "formula":
        return "formula"
    else:
        return "p"   # 默认


def analyze_layout(pages: List[Dict]) -> List[Dict]:
    """使用 PPStructure 进行版面分析，返回元素列表"""
    structure = PPStructure(
        table=True,          # 启用表格识别
        ocr=True,            # 启用文本识别
        lang=CONFIG.OCR_LANG,
        show_log=False
    )

    all_elements = []
    for page in pages:
        page_num = page["page_num"]
        image_path = page["image_path"]
        img = cv2.imread(image_path)
        if img is None:
            logger.error("无法读取图片：%s", image_path)
            continue

        logger.info("版面分析：page=%d", page_num)
        result = structure(img)
        page_height = img.shape[0]

        for region in result:
            bbox = region.get('bbox')
            if not bbox or len(bbox) != 4:
                continue
            bbox_int = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
            layout_type = region.get('type', 'text')
            element_type = _classify_text_type(bbox_int, page_height, layout_type)

            # 提取内容
            content = ""
            res = region.get('res', {})
            if layout_type == 'table':
                content = res.get('html', '')
            elif layout_type in ('text', 'title'):
                content = res.get('text', '')
            # 对于 figure、formula，可能没有文本内容，留空后续补充

            element = {
                "element_type": element_type,
                "bbox": bbox_int,
                "content": content,
                "page_num": page_num,
                "extra": res
            }
            all_elements.append(element)

    logger.info("版面分析完成，共识别 %d 个元素", len(all_elements))
    return all_elements