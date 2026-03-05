from typing import Dict, List

from utils.coordinate import sort_elements


def rebuild_logic(elements: List[Dict]) -> List[Dict]:
    """根据页面及空间位置重建阅读顺序。"""
    return sort_elements(elements)