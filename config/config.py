import os
from typing import Optional


class Config:
    """全局配置类。"""

    # 环境与 OCR 参数
    OCR_LANG: str = "ch"
    OCR_USE_ANGLE_CLS: bool = True

    # PDF / 图像预处理参数
    DPI: int = 300
    MAX_WIDTH: int = 2000

    # 路径配置 - 修正为项目根目录
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMP_DIR: str = os.path.join(BASE_DIR, "tmp")
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "output")

    # 日志
    LOG_LEVEL: str = os.getenv("DOC_PARSER_LOG_LEVEL", "INFO")

    # 公式识别（可选，当前未使用）
    MATHPIX_APP_ID: Optional[str] = os.getenv("MATHPIX_APP_ID")
    MATHPIX_APP_KEY: Optional[str] = os.getenv("MATHPIX_APP_KEY")

    @staticmethod
    def use_gpu() -> bool:
        """是否使用 GPU。"""
        try:
            import paddle
            return bool(paddle.device.is_compiled_with_cuda())
        except Exception:
            return False


CONFIG = Config()