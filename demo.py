"""
快速开始：
1. 确保已安装依赖：pip install -r requirements.txt
2. 确保当前目录为 doc_parser_system，准备测试文件：将 test.pdf 或图片放入 ./test_data/ 目录
3. 运行脚本：python demo.py
4. 输出结果：./output/result.html
"""

import os
import cv2
import numpy as np

from config.config import CONFIG
from core.preprocess import preprocess_input
from core.element_detect import detect_elements
from core.content_recognize import recognize_contents
from core.logic_rebuild import rebuild_logic
from core.output_generator import generate_html
from utils.file_io import ensure_directories, find_test_file, save_html, detect_file_type
from utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_sample_test_file(test_dir: str) -> str:
    """若测试目录中不存在文件，则生成一个简单的示例 PNG。"""
    os.makedirs(test_dir, exist_ok=True)
    sample_path = os.path.join(test_dir, "sample.png")
    if os.path.exists(sample_path):
        return sample_path

    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    cv2.putText(
        img,
        "示例文档标题",
        (50, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 0),
        2,
    )
    cv2.putText(
        img,
        "这是一段示例正文，用于测试 OCR。",
        (50, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 0, 0),
        2,
    )
    cv2.imwrite(sample_path, img)
    logger.info("已自动生成示例测试文件：%s", sample_path)
    return sample_path


def run_demo() -> None:
    ensure_directories()
    test_dir = os.path.join(CONFIG.BASE_DIR, "test_data")
    test_file = find_test_file(test_dir)

    if not test_file:
        logger.warning("未找到测试文件，将自动生成示例文件。")
        test_file = _ensure_sample_test_file(test_dir)

    try:
        ftype = detect_file_type(test_file)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("测试文件检测失败：%s", exc)
        return

    logger.info("开始处理文件：%s（类型：%s）", test_file, ftype)

    try:
        pages = preprocess_input(test_file)
    except Exception as exc:
        logger.error("预处理阶段发生错误：%s", exc)
        return

    try:
        elements = detect_elements(pages)
        elements = recognize_contents(pages, elements)
        logger.info("内容识别完成。")
    except Exception as exc:
        logger.error("内容识别阶段发生错误：%s", exc)
        return

    try:
        elements = rebuild_logic(elements)
    except Exception as exc:
        logger.error("逻辑重建阶段发生错误：%s", exc)
        return

    try:
        html = generate_html(elements, wrap_html=True, title="Demo Document")
        out_path = save_html(html, "result.html")
        logger.info("处理完成，结果已输出到：%s", out_path)
    except Exception as exc:
        logger.error("输出生成阶段发生错误：%s", exc)
        return


if __name__ == "__main__":
    run_demo()