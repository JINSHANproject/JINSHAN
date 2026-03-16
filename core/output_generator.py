import json
from html import escape
from typing import Dict, List

from utils.file_io import clean_whitespace

# ─────────────────────────── HTML 生成 ───────────────────────────

_HTML_CSS = """
  <style>
    body {
      font-family: "Noto Serif CJK SC", "Source Han Serif CN", serif;
      font-size: 15px;
      line-height: 1.8;
      color: #1a1a1a;
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 24px;
      background: #fff;
    }
    h1 { font-size: 2em; margin: 1em 0 0.4em; }
    h2 { font-size: 1.5em; margin: 0.9em 0 0.35em; }
    h3 { font-size: 1.2em; margin: 0.8em 0 0.3em; }
    p  { margin: 0.4em 0 0.6em; text-align: justify; }
    .doc-header, .doc-footer {
      font-size: 0.82em;
      color: #888;
      border-bottom: 1px solid #e0e0e0;
      padding-bottom: 4px;
      margin-bottom: 10px;
    }
    .doc-footer {
      border-top: 1px solid #e0e0e0;
      border-bottom: none;
      padding-top: 4px;
      margin-top: 10px;
    }
    .page-num {
      display: block;
      text-align: center;
      font-size: 0.8em;
      color: #aaa;
      margin: 6px 0;
    }
    .formula {
      display: block;
      font-family: "Cambria Math", "STIX Two Math", serif;
      font-size: 1.1em;
      background: #f9f9f9;
      border-left: 3px solid #ccc;
      padding: 8px 14px;
      margin: 10px 0;
      overflow-x: auto;
    }
    figure.doc-image {
      display: block;
      margin: 16px auto;
      text-align: center;
    }
    figure.doc-image img {
      max-width: 100%;
      border: 1px solid #e0e0e0;
      border-radius: 4px;
    }
    .doc-table-wrap {
      overflow-x: auto;
      margin: 14px 0;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 0.9em;
    }
    table td, table th {
      border: 1px solid #ccc;
      padding: 6px 10px;
      vertical-align: top;
    }
    table tr:nth-child(even) { background: #f7f7f7; }
    [data-low-confidence] {
      opacity: 0.6;
    }
  </style>
"""


def _bbox_to_attr(bbox: List[int]) -> str:
    x1, y1, x2, y2 = bbox
    return f"{x1},{y1},{x2},{y2}"


def generate_element_html(element: Dict) -> str:
    """根据元素类型生成对应的 HTML 片段。"""
    etype = element.get("element_type", "p")
    bbox = element.get("bbox", [0, 0, 0, 0])
    content = element.get("content", "") or ""
    bbox_attr = _bbox_to_attr(bbox)
    extra = element.get("extra", {})

    # 低置信度标记
    low_conf_attr = ' data-low-confidence="true"' if extra.get("low_confidence") else ""

    if etype == "h1":
        return f'<h1 data-bbox="{bbox_attr}"{low_conf_attr}>{escape(content)}</h1>'

    if etype == "h2":
        return f'<h2 data-bbox="{bbox_attr}"{low_conf_attr}>{escape(content)}</h2>'

    if etype == "h3":
        return f'<h3 data-bbox="{bbox_attr}"{low_conf_attr}>{escape(content)}</h3>'

    if etype == "p":
        return f'<p data-bbox="{bbox_attr}"{low_conf_attr}>{escape(content)}</p>'

    if etype == "header":
        return f'<div class="doc-header" data-bbox="{bbox_attr}">{escape(content)}</div>'

    if etype == "footer":
        return f'<div class="doc-footer" data-bbox="{bbox_attr}">{escape(content)}</div>'

    if etype == "page_number":
        return f'<span class="page-num" data-bbox="{bbox_attr}">{escape(content)}</span>'

    if etype == "formula":
        # content 已含 $...$ 或 $$...$$ 标记，直接输出（不转义数学符号）
        safe_content = content.replace("<", "&lt;").replace(">", "&gt;")
        return f'<div class="formula" data-bbox="{bbox_attr}">{safe_content}</div>'

    if etype == "table":
        # content 是 PPStructure 生成的 HTML <table>...</table>，直接嵌入
        if content.strip().startswith("<"):
            inner = content
        else:
            inner = f"<table><tr><td>{escape(content)}</td></tr></table>"
        return (
            f'<div class="doc-table-wrap" data-bbox="{bbox_attr}">'
            f'{inner}'
            f'</div>'
        )

    if etype == "image":
        # content 存放相对于 output/ 的图片路径
        src = escape(content) if content else ""
        alt = f"图片区域 {bbox_attr}"
        if src:
            img_tag = f'<img src="{src}" alt="{alt}" loading="lazy" />'
        else:
            img_tag = f'<img alt="{alt}" />'
        return (
            f'<figure class="doc-image" data-bbox="{bbox_attr}">'
            f'{img_tag}'
            f'</figure>'
        )

    # 未知类型，降级为段落
    return f'<p data-bbox="{bbox_attr}"{low_conf_attr}>{escape(content)}</p>'


def generate_html(
    elements: List[Dict],
    wrap_html: bool = True,
    title: str = "Document",
) -> str:
    """
    将元素列表渲染为 HTML 字符串。

    Args:
        elements: 经过逻辑重建后的元素列表。
        wrap_html: 若 True，包裹完整的 <!DOCTYPE html> 结构（含 CSS）。
        title: HTML 页面标题。

    Returns:
        HTML 字符串。
    """
    parts = [generate_element_html(ele) for ele in elements]
    body = "\n".join(parts)
    body = clean_whitespace(body)

    if not wrap_html:
        return body

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(title)}</title>
{_HTML_CSS}
</head>
<body>
{body}
</body>
</html>
"""
    return html


# ─────────────────────────── JSON 生成 ───────────────────────────

def generate_json(elements: List[Dict]) -> str:
    """
    将元素列表序列化为标准化 JSON 字符串。

    每个元素的输出字段：
    - index: 排序后的序号（0-based）
    - page_num: 页码
    - element_type: 元素类型
    - bbox: [x1, y1, x2, y2]
    - content: 识别内容
    - confidence: 置信度
    - low_confidence: 是否低置信度
    - paragraph_id: 段落 ID（文本类有效）
    - formula_engine: 公式识别引擎（公式类有效）
    """
    output = []
    for idx, ele in enumerate(elements):
        extra = ele.get("extra", {})
        item: Dict = {
            "index": idx,
            "page_num": ele.get("page_num", 1),
            "element_type": ele.get("element_type", "p"),
            "bbox": ele.get("bbox", [0, 0, 0, 0]),
            "content": ele.get("content", ""),
            "confidence": round(float(extra.get("confidence", 1.0)), 4),
        }
        if extra.get("low_confidence"):
            item["low_confidence"] = True
        if "paragraph_id" in extra:
            item["paragraph_id"] = extra["paragraph_id"]
        if "formula_engine" in extra:
            item["formula_engine"] = extra["formula_engine"]
        if "image_saved" in extra:
            item["image_path"] = extra["image_saved"]
        output.append(item)

    return json.dumps(
        {"elements": output, "total": len(output)},
        ensure_ascii=False,
        indent=2,
    )
