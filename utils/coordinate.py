import re
from typing import List, Dict, Tuple, Optional


def sort_elements(elements: list) -> list:
    """按 (page_num, y1, x1) 对元素排序，恢复基本阅读顺序。"""
    def _key(e: dict) -> Tuple[int, int, int]:
        x1, y1, x2, y2 = e.get("bbox", [0, 0, 0, 0])
        return int(e.get("page_num", 1)), y1, x1
    return sorted(elements, key=_key)


def detect_columns(elements: List[Dict], page_width: int) -> int:
    """
    通过元素 bbox 的 x 坐标分布，估计页面栏数（1 / 2）。

    策略：
    - 取所有文本/标题元素的中点 x 坐标
    - 若大多数元素中点集中在页面两侧（左半 / 右半）且分布明显，则判定为双栏
    - 否则视为单栏
    """
    if page_width <= 0:
        return 1

    text_types = {"p", "title", "header", "footer", "formula"}
    midpoints = []
    for e in elements:
        if e.get("element_type") not in text_types:
            continue
        x1, y1, x2, y2 = e.get("bbox", [0, 0, 0, 0])
        midpoints.append((x1 + x2) / 2.0)

    if len(midpoints) < 4:
        return 1

    center = page_width / 2.0
    margin = page_width * 0.1  # 中线两侧 10% 为过渡区，不计入判断
    left_count = sum(1 for x in midpoints if x < center - margin)
    right_count = sum(1 for x in midpoints if x > center + margin)
    total = len(midpoints)

    # 两侧元素均占总数 25% 以上，视为双栏
    if left_count / total >= 0.25 and right_count / total >= 0.25:
        return 2
    return 1


def sort_elements_multicolumn(
    elements: List[Dict], page_width: int
) -> List[Dict]:
    """
    双栏布局的排序：先按页码，在每页内先左栏后右栏，每栏内按 y 坐标排序。
    单栏则等同 sort_elements。
    """
    if not elements:
        return elements

    # 按页码分组
    pages: Dict[int, List[Dict]] = {}
    for e in elements:
        pg = int(e.get("page_num", 1))
        pages.setdefault(pg, []).append(e)

    result = []
    center = page_width / 2.0

    for pg in sorted(pages.keys()):
        page_elements = pages[pg]
        col_count = detect_columns(page_elements, page_width)

        if col_count == 2:
            left = [e for e in page_elements if (e["bbox"][0] + e["bbox"][2]) / 2 <= center]
            right = [e for e in page_elements if (e["bbox"][0] + e["bbox"][2]) / 2 > center]
            left.sort(key=lambda e: e["bbox"][1])
            right.sort(key=lambda e: e["bbox"][1])
            result.extend(left)
            result.extend(right)
        else:
            page_elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))
            result.extend(page_elements)

    return result


def infer_heading_levels(elements: List[Dict]) -> List[Dict]:
    """
    根据 bbox 高度（字体大小的近似值）自动区分标题层级。

    规则：
    - element_type 为 "title" 的元素，按文字高度从大到小分为 h1 / h2 / h3
    - 最大高度段为 h1，次大为 h2，其余为 h3
    - 保留非 title 类型元素不变
    """
    title_elements = [e for e in elements if e.get("element_type") == "title"]
    if not title_elements:
        return elements

    heights = sorted(
        set(int(e["bbox"][3] - e["bbox"][1]) for e in title_elements),
        reverse=True,
    )

    # 最多划分三级
    level_map: Dict[int, str] = {}
    for i, h in enumerate(heights):
        if i == 0:
            level_map[h] = "h1"
        elif i == 1:
            level_map[h] = "h2"
        else:
            level_map[h] = "h3"

    for e in elements:
        if e.get("element_type") == "title":
            h = int(e["bbox"][3] - e["bbox"][1])
            e["element_type"] = level_map.get(h, "h2")

    return elements


def _is_page_number(element: Dict) -> bool:
    """
    判断某元素是否为页码：
    - 内容为纯数字（可含空格），或如 "1/5"、"第1页" 等常见格式
    - bbox 高度相对较小（< 30px）
    - 位于页面底部或顶部附近（由调用方判断）
    """
    content = (element.get("content") or "").strip()
    if not content:
        return False

    # 纯数字
    if re.fullmatch(r"\d+", content):
        return True
    # "数字/数字" 或 "数字-数字"
    if re.fullmatch(r"\d+\s*[/\-]\s*\d+", content):
        return True
    # 第N页 / 第N页共M页
    if re.search(r"第\s*\d+\s*页", content):
        return True
    # "Page N" / "- N -"
    if re.fullmatch(r"[-\s]*\d+[-\s]*", content):
        return True

    return False


def assign_paragraph_hierarchy(elements: List[Dict]) -> List[Dict]:
    """
    将连续的 'p' 类型元素按垂直间距聚合为段落组，
    在 extra 中写入 paragraph_id 字段。

    两个相邻 'p' 元素的间距超过平均行高 * 1.5，则视为新段落。
    """
    para_id = 0
    prev_p: Optional[Dict] = None
    avg_line_height = None

    # 先计算所有 p 元素的平均行高
    p_elements = [e for e in elements if e.get("element_type") == "p"]
    if p_elements:
        heights = [int(e["bbox"][3] - e["bbox"][1]) for e in p_elements]
        avg_line_height = sum(heights) / len(heights)

    for ele in elements:
        if ele.get("element_type") != "p":
            prev_p = None
            continue

        if prev_p is None or avg_line_height is None:
            para_id += 1
            ele.setdefault("extra", {})["paragraph_id"] = para_id
            prev_p = ele
            continue

        # 计算与上一个 p 元素的垂直间距
        gap = ele["bbox"][1] - prev_p["bbox"][3]
        if gap > avg_line_height * 1.5:
            para_id += 1

        ele.setdefault("extra", {})["paragraph_id"] = para_id
        prev_p = ele

    return elements


def identify_page_numbers(elements: List[Dict], page_height: int = 0) -> List[Dict]:
    """
    识别并标记页码元素（element_type 改为 'page_number'）。

    判定条件（满足其中之一）：
    1. 内容匹配页码正则，且 bbox 在页面顶部 8% 或底部 8% 区域
    2. 内容匹配页码正则，且 bbox 高度 < 30px 且宽度 < 80px
    """
    for ele in elements:
        if ele.get("element_type") not in ("p", "header", "footer"):
            continue

        x1, y1, x2, y2 = ele.get("bbox", [0, 0, 0, 0])
        height = y2 - y1
        width = x2 - x1

        if not _is_page_number(ele):
            continue

        # 条件1：位于页面边缘区域
        in_top_zone = page_height > 0 and y2 < page_height * 0.08
        in_bottom_zone = page_height > 0 and y1 > page_height * 0.92

        # 条件2：小尺寸文本块
        is_small = height < 30 and width < 100

        if in_top_zone or in_bottom_zone or is_small:
            ele["element_type"] = "page_number"

    return elements
