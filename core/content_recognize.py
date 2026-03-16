import os
import cv2
import requests
import base64
from pathlib import Path
from typing import List, Dict

from config.config import CONFIG
from utils.logger import get_logger
from utils.ocr_helper import ocr_image, get_structure_instance

logger = get_logger(__name__)


# ─────────────────────────── 表格识别 ───────────────────────────

def _recognize_table_with_ppstructure(crop_img) -> str:
    """使用 PPStructure 对单个表格区域进行结构化识别，返回 HTML 字符串。"""
    try:
        structure = get_structure_instance()
        result = structure(crop_img)
        if not result:
            return ""
        for region in result:
            if region.get("type", "").lower() == "table":
                res = region.get("res", "")
                if isinstance(res, str) and res.strip():
                    return res
                if isinstance(res, dict):
                    return res.get("html", "")
        # 如果未检测到 table 类型，取第一个结果的 res
        res = result[0].get("res", "")
        if isinstance(res, str):
            return res
        if isinstance(res, dict):
            return res.get("html", "")
    except Exception as exc:
        logger.warning("PPStructure 表格识别失败：%s", exc)
    return ""


def _recognize_table_fallback(crop_img) -> str:
    """表格识别降级：对区域做 OCR 后拼接为简单 HTML 表格。"""
    lines = ocr_image(crop_img)
    if not lines:
        return ""
    rows = "\n".join(
        f"    <tr><td>{text}</td></tr>" for _, text, _ in lines if text
    )
    return f"<table>\n{rows}\n</table>"


def recognize_table_elements(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """对 element_type == 'table' 的元素进行结构化识别，填充 HTML 表格内容。"""
    page_map = {p["page_num"]: p for p in pages}

    for ele in elements:
        if ele["element_type"] != "table":
            continue
        if ele.get("content"):
            continue

        page = page_map.get(ele["page_num"])
        if not page:
            continue

        # 优先使用原始图像裁切，保留颜色信息
        img_path = page.get("original_path", page["image_path"])
        img = cv2.imread(img_path)
        if img is None:
            continue

        x1, y1, x2, y2 = ele["bbox"]
        # 稍微扩大裁切区域，避免边缘截断
        h, w = img.shape[:2]
        pad = 4
        x1c, y1c = max(0, x1 - pad), max(0, y1 - pad)
        x2c, y2c = min(w, x2 + pad), min(h, y2 + pad)
        crop = img[y1c:y2c, x1c:x2c]
        if crop.size == 0:
            continue

        logger.info("识别表格区域：bbox=[%d,%d,%d,%d]，page=%d", x1, y1, x2, y2, ele["page_num"])
        html = _recognize_table_with_ppstructure(crop)
        if not html:
            logger.warning("PPStructure 表格识别无结果，启用降级方案。")
            html = _recognize_table_fallback(crop)

        ele["content"] = html
        ele["extra"]["recognized"] = True

    return elements


# ─────────────────────────── 公式识别 ───────────────────────────

def _recognize_formula_mathpix(crop_img) -> str:
    """调用 Mathpix API 进行公式 LaTeX 识别。"""
    _, buf = cv2.imencode(".png", crop_img)
    img_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    payload = {
        "src": f"data:image/png;base64,{img_b64}",
        "formats": ["latex_simplified"],
        "data_options": {"include_latex": True},
    }
    headers = {
        "app_id": CONFIG.MATHPIX_APP_ID,
        "app_key": CONFIG.MATHPIX_APP_KEY,
        "Content-type": "application/json",
    }
    try:
        resp = requests.post(
            "https://api.mathpix.com/v3/text",
            json=payload,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        latex = data.get("latex_simplified", data.get("text", ""))
        return f"$${latex}$$" if latex else ""
    except Exception as exc:
        logger.warning("Mathpix API 调用失败：%s", exc)
        return ""


def _recognize_formula_ocr_fallback(crop_img) -> str:
    """公式识别降级：普通 OCR 识别后包裹 $ 符号。"""
    lines = ocr_image(crop_img)
    text = " ".join(t for _, t, _ in lines if t).strip()
    return f"${text}$" if text else ""


def recognize_formula_elements(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """对 element_type == 'formula' 的元素进行 LaTeX 公式识别。"""
    page_map = {p["page_num"]: p for p in pages}
    use_mathpix = bool(CONFIG.MATHPIX_APP_ID and CONFIG.MATHPIX_APP_KEY)

    for ele in elements:
        if ele["element_type"] != "formula":
            continue
        if ele.get("content"):
            continue

        page = page_map.get(ele["page_num"])
        if not page:
            continue

        img_path = page.get("original_path", page["image_path"])
        img = cv2.imread(img_path)
        if img is None:
            continue

        x1, y1, x2, y2 = ele["bbox"]
        h, w = img.shape[:2]
        crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            continue

        logger.info("识别公式区域：bbox=[%d,%d,%d,%d]，page=%d", x1, y1, x2, y2, ele["page_num"])
        if use_mathpix:
            latex = _recognize_formula_mathpix(crop)
            if latex:
                ele["content"] = latex
                ele["extra"]["formula_engine"] = "mathpix"
                continue

        # 降级为普通 OCR
        ele["content"] = _recognize_formula_ocr_fallback(crop)
        ele["extra"]["formula_engine"] = "ocr_fallback"

    return elements


# ─────────────────────────── 图片处理 ───────────────────────────

def recognize_image_elements(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """
    对 element_type == 'image' 的元素裁切图片区域并保存到 output/images/ 目录。
    ele["content"] 记录相对于 output/ 的路径，供 HTML 生成使用。
    """
    os.makedirs(CONFIG.IMAGE_OUTPUT_DIR, exist_ok=True)
    page_map = {p["page_num"]: p for p in pages}
    img_counter = {}

    for ele in elements:
        if ele["element_type"] != "image":
            continue

        page = page_map.get(ele["page_num"])
        if not page:
            continue

        img_path = page.get("original_path", page["image_path"])
        img = cv2.imread(img_path)
        if img is None:
            continue

        x1, y1, x2, y2 = ele["bbox"]
        h, w = img.shape[:2]
        crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            continue

        pg = ele["page_num"]
        img_counter[pg] = img_counter.get(pg, 0) + 1
        fname = f"page{pg}_img{img_counter[pg]}.png"
        save_path = os.path.join(CONFIG.IMAGE_OUTPUT_DIR, fname)
        cv2.imwrite(save_path, crop)

        # 存储相对于 OUTPUT_DIR 的路径
        rel_path = os.path.join("images", fname)
        ele["content"] = rel_path
        ele["extra"]["image_saved"] = save_path
        logger.info("图片区域已保存：%s", save_path)

    return elements


# ─────────────────────────── 文本识别（带置信度过滤） ───────────────────────────

def recognize_text_elements(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """
    对文本类元素（p/title/header/footer）进行二次 OCR 补充。
    - content 已有内容则跳过
    - 置信度低于 CONFIG.MIN_CONFIDENCE 的元素标记 low_confidence=True
    """
    page_map = {p["page_num"]: p for p in pages}
    text_types = {"p", "title", "header", "footer"}

    for ele in elements:
        if ele["element_type"] not in text_types:
            continue

        # 置信度过滤标记
        conf = ele.get("extra", {}).get("confidence", 1.0)
        if conf < CONFIG.MIN_CONFIDENCE and ele.get("content"):
            ele["extra"]["low_confidence"] = True
            logger.debug(
                "低置信度元素（%.2f）：%s", conf, ele.get("content", "")[:30]
            )

        # 内容已有则跳过
        if ele["content"]:
            continue

        page = page_map.get(ele["page_num"])
        if not page:
            continue

        # 使用原始图像进行二次识别
        img_path = page.get("original_path", page["image_path"])
        img = cv2.imread(img_path)
        if img is None:
            continue

        x1, y1, x2, y2 = ele["bbox"]
        h, w = img.shape[:2]
        crop = img[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            continue

        ocr_results = ocr_image(crop)
        texts = [t[1] for t in ocr_results if t[1]]
        ele["content"] = " ".join(texts)

    return elements


# ─────────────────────────── 统一入口 ───────────────────────────

def recognize_contents(pages: List[Dict], elements: List[Dict]) -> List[Dict]:
    """按元素类型分路进行内容识别，填充 ele['content'] 字段。"""
    logger.info("开始内容识别...")

    # 1. 文本类二次 OCR + 置信度标记
    elements = recognize_text_elements(pages, elements)
    logger.info("文本识别完成。")

    # 2. 表格结构化识别
    table_count = sum(1 for e in elements if e["element_type"] == "table")
    if table_count > 0:
        logger.info("开始表格识别，共 %d 个表格区域。", table_count)
        elements = recognize_table_elements(pages, elements)
        logger.info("表格识别完成。")

    # 3. 公式识别
    formula_count = sum(1 for e in elements if e["element_type"] == "formula")
    if formula_count > 0:
        logger.info("开始公式识别，共 %d 个公式区域。", formula_count)
        elements = recognize_formula_elements(pages, elements)
        logger.info("公式识别完成。")

    # 4. 图片裁切保存
    image_count = sum(1 for e in elements if e["element_type"] == "image")
    if image_count > 0:
        logger.info("开始图片区域处理，共 %d 个图片区域。", image_count)
        elements = recognize_image_elements(pages, elements)
        logger.info("图片处理完成。")

    logger.info("内容识别全部完成。")
    return elements
