from html import escape
from typing import Dict, List

from utils.file_io import clean_whitespace


def _bbox_to_attr(bbox: List[int]) -> str:
    x1, y1, x2, y2 = bbox
    return f"{x1},{y1},{x2},{y2}"


def generate_element_html(element: Dict) -> str:
    etype = element.get("element_type")
    bbox = element.get("bbox", [0, 0, 0, 0])
    content = element.get("content", "") or ""
    bbox_attr = _bbox_to_attr(bbox)

    if etype == "h2":
        return f'<h2 data-bbox="{bbox_attr}">{escape(content)}</h2>'
    if etype == "p":
        return f'<p data-bbox="{bbox_attr}">{escape(content)}</p>'
    if etype == "header":
        return f'<div class="header" data-bbox="{bbox_attr}">{escape(content)}</div>'
    if etype == "footer":
        return f'<div class="footer" data-bbox="{bbox_attr}">{escape(content)}</div>'
    # 其他类型（如图片、表格）不会出现，但可保留占位
    return f'<p data-bbox="{bbox_attr}">{escape(content)}</p>'


def generate_html(
    elements: List[Dict], wrap_html: bool = True, title: str = "Document"
) -> str:
    parts = [generate_element_html(ele) for ele in elements]
    body = "\n".join(parts)
    body = clean_whitespace(body)

    if not wrap_html:
        return body

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
</head>
<body>
{body}
</body>
</html>
"""
    return html