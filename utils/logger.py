import logging
import os
from typing import Optional

from config.config import CONFIG


def get_logger(name: Optional[str] = None) -> logging.Logger:
    logger_name = name or "doc_parser_system"
    logger = logging.getLogger(logger_name)

    if logger.handlers:
        return logger

    level = getattr(logging, CONFIG.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    os.makedirs(CONFIG.OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(CONFIG.OUTPUT_DIR, "doc_parser.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    logger.propagate = False
    logger.debug("Logger initialized with level %s", CONFIG.LOG_LEVEL)
    return logger