import os
from pathlib import Path
from typing import List, Optional

from config.config import CONFIG
from utils.logger import get_logger

logger = get_logger(__name__)


def ensure_directories() -> None:
    os.makedirs(CONFIG.TEMP_DIR, exist_ok=True)
    os.makedirs(CONFIG.OUTPUT_DIR, exist_ok=True)


def find_test_file(test_dir: str) -> Optional[str]:
    exts_priority = [
        [".pdf"],
        [".png", ".jpg", ".jpeg", ".bmp"],
    ]
    base = Path(test_dir)
    if not base.exists():
        logger.warning("测试目录不存在：%s", test_dir)
        return None

    for group in exts_priority:
        for ext in group:
            for p in sorted(base.glob(f"*{ext}")):
                logger.info("发现测试文件：%s", p)
                return str(p.resolve())
    logger.warning("未在目录 %s 中找到可用测试文件。", test_dir)
    return None


def save_html(html: str, filename: str = "result.html") -> str:
    ensure_directories()
    out_path = os.path.join(CONFIG.OUTPUT_DIR, filename)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("HTML 已保存到：%s", out_path)
        return out_path
    except OSError as exc:
        logger.error("保存 HTML 失败：%s", exc)
        raise


def detect_file_type(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"输入文件不存在：{path}")

    ext = p.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".png", ".jpg", ".jpeg", ".bmp"}:
        return "image"
    raise ValueError(f"暂不支持的文件格式：{ext}")


def clean_whitespace(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)