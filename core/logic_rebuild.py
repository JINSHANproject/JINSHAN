from typing import List, Dict

from utils.coordinate import (
    sort_elements_multicolumn,
    infer_heading_levels,
    assign_paragraph_hierarchy,
    identify_page_numbers,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def rebuild_logic(elements: List[Dict], page_width: int = 0, page_height: int = 0) -> List[Dict]:
    """
    对检测到的元素进行逻辑关系重建，恢复文档的正确阅读顺序和层级结构。

    处理步骤：
    1. 页码识别与标记
    2. 标题层级推断（title → h1 / h2 / h3）
    3. 段落归属（连续 p 元素按间距聚合，写入 paragraph_id）
    4. 多栏检测与排序（支持单栏/双栏）
    """
    if not elements:
        return elements

    # 推断 page_width / page_height（取所有元素 bbox 的最大值估算）
    if page_width <= 0:
        xs = [e["bbox"][2] for e in elements if e.get("bbox")]
        page_width = max(xs) if xs else 800
    if page_height <= 0:
        ys = [e["bbox"][3] for e in elements if e.get("bbox")]
        page_height = max(ys) if ys else 1000

    # 1. 标记页码元素
    elements = identify_page_numbers(elements, page_height)
    logger.debug("页码识别完成。")

    # 2. 推断标题层级
    elements = infer_heading_levels(elements)
    logger.debug("标题层级推断完成。")

    # 3. 段落归属
    elements = assign_paragraph_hierarchy(elements)
    logger.debug("段落归属分析完成。")

    # 4. 多栏检测与排序
    elements = sort_elements_multicolumn(elements, page_width)
    logger.info(
        "逻辑重建完成，共 %d 个元素（page_width=%d, page_height=%d）。",
        len(elements), page_width, page_height,
    )

    return elements
