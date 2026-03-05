import cv2
import numpy as np
from paddleocr import PaddleOCR
from typing import List, Tuple, Optional, Union

from config.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)

_ocr_instance: Optional[PaddleOCR] = None


def get_ocr_instance() -> PaddleOCR:
    """获取单例 PaddleOCR 实例（文本识别用）"""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(
            use_angle_cls=CONFIG.OCR_USE_ANGLE_CLS,
            lang=CONFIG.OCR_LANG,
        )
    return _ocr_instance


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
            # 优先使用 rec_boxes（矩形框）和 rec_texts
            rec_boxes = item.get('rec_boxes')
            rec_texts = item.get('rec_texts')
            rec_scores = item.get('rec_scores', [])

            if rec_boxes is not None and rec_texts is not None:
                # rec_boxes 可能是 numpy 数组，形状 (N, 4) 或 (N, 4, 2)
                if isinstance(rec_boxes, np.ndarray):
                    if rec_boxes.ndim == 3 and rec_boxes.shape[2] == 2:
                        # 多边形点，转换为矩形
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
                        # 直接是 [x1,y1,x2,y2] 格式
                        for i in range(len(rec_texts)):
                            x1, y1, x2, y2 = rec_boxes[i].tolist()
                            text = rec_texts[i]
                            score = rec_scores[i] if i < len(rec_scores) else 0.0
                            elements.append(([int(x1), int(y1), int(x2), int(y2)], text, score))
                    else:
                        # 未知形状，尝试按列表处理
                        for i, box in enumerate(rec_boxes):
                            if hasattr(box, 'tolist'):
                                box = box.tolist()
                            if len(box) == 4:
                                x1, y1, x2, y2 = map(int, box)
                                text = rec_texts[i] if i < len(rec_texts) else ''
                                score = rec_scores[i] if i < len(rec_scores) else 0.0
                                elements.append(([x1, y1, x2, y2], text, score))
            # 如果没有 rec_boxes，尝试使用 dt_polys（多边形）
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
                        # 将多边形点转换为矩形
                        xs = [pt[0] for pt in box]
                        ys = [pt[1] for pt in box]
                        if xs and ys:
                            x1, y1 = int(min(xs)), int(min(ys))
                            x2, y2 = int(max(xs)), int(max(ys))
                            elements.append(([x1, y1, x2, y2], text, score))

    return elements


def ocr_image(image: Union[str, np.ndarray]) -> List[Tuple[List[int], str, float]]:
    """对图像进行 OCR 识别，返回解析后的元素列表"""
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