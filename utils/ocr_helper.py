import cv2
import numpy as np
from paddleocr import PaddleOCR, PPStructure
from typing import List, Tuple, Optional, Union, Dict

from config.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)

_ocr_instance: Optional[PaddleOCR] = None
_structure_instance: Optional[PPStructure] = None


def get_ocr_instance() -> PaddleOCR:
    """获取单例 PaddleOCR 实例（纯文本识别，用于降级回退）。"""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(
            use_angle_cls=CONFIG.OCR_USE_ANGLE_CLS,
            lang=CONFIG.OCR_LANG,
            use_gpu=CONFIG.use_gpu(),
            show_log=False,
        )
    return _ocr_instance


def get_structure_instance() -> PPStructure:
    """获取单例 PPStructure 实例（版面分析 + 表格识别）。"""
    global _structure_instance
    if _structure_instance is None:
        _structure_instance = PPStructure(
            table=True,
            ocr=True,
            lang=CONFIG.OCR_LANG,
            use_gpu=CONFIG.use_gpu(),
            show_log=False,
        )
    return _structure_instance


def parse_ocr_result(ocr_result) -> List[Tuple[List[int], str, float]]:
    """
    将 PaddleOCR 返回结果统一解析为 (bbox, text, confidence) 列表。
    兼容两种格式：
    - 新版字典格式：包含 'rec_boxes' 和 'rec_texts' 等字段
    - 旧版列表格式：[[[x1,y1], ...], (text, score)], ...]
    """
    elements = []
    if not isinstance(ocr_result, list):
        return elements

    for item in ocr_result:
        # 处理新版字典格式
        if isinstance(item, dict):
            rec_boxes = item.get('rec_boxes')
            rec_texts = item.get('rec_texts')
            rec_scores = item.get('rec_scores', [])

            if rec_boxes is not None and rec_texts is not None:
                if isinstance(rec_boxes, np.ndarray):
                    if rec_boxes.ndim == 3 and rec_boxes.shape[2] == 2:
                        for i in range(len(rec_texts)):
                            pts = rec_boxes[i]
                            xs = [pt[0] for pt in pts]
                            ys = [pt[1] for pt in pts]
                            x1, y1 = int(min(xs)), int(min(ys))
                            x2, y2 = int(max(xs)), int(max(ys))
                            text = rec_texts[i]
                            score = rec_scores[i] if i < len(rec_scores) else 0.0
                            elements.append(([x1, y1, x2, y2], text, score))
                    elif rec_boxes.ndim == 2 and rec_boxes.shape[1] == 4:
                        for i in range(len(rec_texts)):
                            x1, y1, x2, y2 = rec_boxes[i].tolist()
                            text = rec_texts[i]
                            score = rec_scores[i] if i < len(rec_scores) else 0.0
                            elements.append(([int(x1), int(y1), int(x2), int(y2)], text, score))
                    else:
                        for i, box in enumerate(rec_boxes):
                            if hasattr(box, 'tolist'):
                                box = box.tolist()
                            if len(box) == 4:
                                x1, y1, x2, y2 = map(int, box)
                                text = rec_texts[i] if i < len(rec_texts) else ''
                                score = rec_scores[i] if i < len(rec_scores) else 0.0
                                elements.append(([x1, y1, x2, y2], text, score))
            else:
                dt_polys = item.get('dt_polys')
                rec_texts = item.get('rec_texts')
                rec_scores = item.get('rec_scores', [])
                if dt_polys is not None and rec_texts is not None:
                    for i, poly in enumerate(dt_polys):
                        if isinstance(poly, np.ndarray):
                            poly = poly.tolist()
                        xs = [pt[0] for pt in poly]
                        ys = [pt[1] for pt in poly]
                        x1, y1 = int(min(xs)), int(min(ys))
                        x2, y2 = int(max(xs)), int(max(ys))
                        text = rec_texts[i] if i < len(rec_texts) else ''
                        score = rec_scores[i] if i < len(rec_scores) else 0.0
                        elements.append(([x1, y1, x2, y2], text, score))

        # 处理旧版列表格式
        elif isinstance(item, list):
            for line in item:
                if isinstance(line, (list, tuple)) and len(line) >= 2:
                    box = line[0]
                    text_info = line[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                        text, score = text_info[0], text_info[1]
                        xs = [pt[0] for pt in box]
                        ys = [pt[1] for pt in box]
                        if xs and ys:
                            x1, y1 = int(min(xs)), int(min(ys))
                            x2, y2 = int(max(xs)), int(max(ys))
                            elements.append(([x1, y1, x2, y2], text, score))

    return elements


def _extract_ocr_lines_from_res(res) -> List[Dict]:
    """从 PPStructure region 的 res 字段中提取 OCR 文本行列表。"""
    ocr_lines = []
    if not isinstance(res, list):
        return ocr_lines
    for r in res:
        if not isinstance(r, dict):
            continue
        text = r.get("text", "")
        conf = float(r.get("confidence", 0.0))
        region_box = r.get("text_region", [])
        if text:
            ocr_lines.append({
                "text": text,
                "confidence": conf,
                "text_region": region_box,
            })
    return ocr_lines


def _region_has_text(res, min_lines: int = 2) -> bool:
    """判断一个 PPStructure region 的 res 字段是否含有足够的 OCR 文本行。"""
    if not isinstance(res, list):
        return False
    text_lines = [r for r in res if isinstance(r, dict) and r.get("text", "").strip()]
    return len(text_lines) >= min_lines


def parse_structure_result(
    structure_result: List[Dict],
    page_offset_x: int = 0,
    page_offset_y: int = 0,
) -> List[Dict]:
    """
    将 PPStructure 返回结果解析为统一的元素字典列表。

    关键处理逻辑：
    - PPStructure 有时会将包含大量文字的区域误标为 figure（常见于含图标的信息图、
      演示文稿截图等）。本函数对此类 figure 区域做二次判断：
      若 res 字段中含有 >= 2 条 OCR 文本行，则将该区域视为文本区域，
      把每条 OCR 行展开为独立的 p 元素，而非整块保存为图片。

    每个元素字典包含：
      - element_type: str
      - bbox: [x1, y1, x2, y2]
      - content: str
      - extra: dict
    """
    TYPE_MAP = {
        "text": "p",
        "title": "title",
        "table": "table",
        "figure": "image",
        "figure_caption": "p",
        "reference": "p",
        "equation": "formula",
        "formula": "formula",
        "header": "header",
        "footer": "footer",
    }

    elements = []
    if not structure_result:
        return elements

    for region in structure_result:
        raw_type = region.get("type", "text").lower()
        etype = TYPE_MAP.get(raw_type, "p")

        bbox_raw = region.get("bbox")
        if bbox_raw is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox_raw]
        x1 += page_offset_x
        y1 += page_offset_y
        x2 += page_offset_x
        y2 += page_offset_y

        res = region.get("res", "")

        # ── figure 区域的特殊处理 ──────────────────────────────────────────
        # PPStructure 经常把含有图标/装饰的文字区域误标为 figure。
        # 若该区域内 res 字段包含 2 条及以上 OCR 文本行，则将其展开为逐行独立元素，
        # 放弃整体图片标签，以确保文字内容不丢失。
        if etype == "image" and _region_has_text(res, min_lines=2):
            logger.debug(
                "figure 区域含文字行，展开为文本元素：bbox=[%d,%d,%d,%d]", x1, y1, x2, y2
            )
            ocr_lines = _extract_ocr_lines_from_res(res)
            for line in ocr_lines:
                line_box = line["text_region"]
                # text_region 可能是 [[x,y],[x,y],...] 多边形或 [x1,y1,x2,y2] 矩形
                if line_box and isinstance(line_box[0], (list, tuple)):
                    lxs = [pt[0] for pt in line_box]
                    lys = [pt[1] for pt in line_box]
                    lx1, ly1 = int(min(lxs)) + page_offset_x, int(min(lys)) + page_offset_y
                    lx2, ly2 = int(max(lxs)) + page_offset_x, int(max(lys)) + page_offset_y
                elif len(line_box) == 4:
                    lx1, ly1, lx2, ly2 = (
                        int(line_box[0]) + page_offset_x,
                        int(line_box[1]) + page_offset_y,
                        int(line_box[2]) + page_offset_x,
                        int(line_box[3]) + page_offset_y,
                    )
                else:
                    # 无法解析坐标，使用区域大框
                    lx1, ly1, lx2, ly2 = x1, y1, x2, y2

                elements.append({
                    "element_type": "p",
                    "bbox": [lx1, ly1, lx2, ly2],
                    "content": line["text"],
                    "extra": {
                        "confidence": line["confidence"],
                        "raw_type": "figure_text",
                        "ocr_lines": [line],
                    },
                })
            continue  # 已处理，跳过后续通用逻辑

        # ── 通用处理逻辑 ──────────────────────────────────────────────────
        content = ""
        ocr_lines = []

        if etype == "table":
            if isinstance(res, str):
                content = res
            elif isinstance(res, dict):
                content = res.get("html", "")
        elif etype == "image":
            # 确认是真正的图片（res 中无文字或文字极少），留空等待后续裁切保存
            content = ""
        elif etype == "formula":
            if isinstance(res, list):
                texts = [r.get("text", "") for r in res if isinstance(r, dict)]
                content = " ".join(t for t in texts if t)
            elif isinstance(res, str):
                content = res
        else:
            # 文本类（title / p / header / footer）
            ocr_lines = _extract_ocr_lines_from_res(res)
            texts = [r["text"] for r in ocr_lines if r["text"]]
            content = " ".join(texts)
            if not content and isinstance(res, str):
                content = res

        if ocr_lines:
            avg_conf = sum(r["confidence"] for r in ocr_lines) / len(ocr_lines)
        else:
            avg_conf = 1.0 if content else 0.0

        elements.append({
            "element_type": etype,
            "bbox": [x1, y1, x2, y2],
            "content": content,
            "extra": {
                "confidence": avg_conf,
                "raw_type": raw_type,
                "ocr_lines": ocr_lines,
            },
        })

    return elements


def ocr_image(image: Union[str, np.ndarray]) -> List[Tuple[List[int], str, float]]:
    """对图像进行纯文本 OCR 识别，返回解析后的元素列表。"""
    ocr = get_ocr_instance()
    if isinstance(image, str):
        img = cv2.imread(image)
        if img is None:
            logger.error("无法读取图像：%s", image)
            return []
    else:
        img = image
    result = ocr.ocr(img)
    return parse_ocr_result(result)
