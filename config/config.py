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
    IMAGE_OUTPUT_DIR: str = os.path.join(BASE_DIR, "output", "images")

    # 日志
    LOG_LEVEL: str = os.getenv("DOC_PARSER_LOG_LEVEL", "INFO")

    # 版面分析与元素检测
    USE_PP_STRUCTURE: bool = True           # 是否启用 PPStructure 版面分析
    MIN_CONFIDENCE: float = 0.5             # 文本识别置信度阈值
    TABLE_STRUCTURE_SCORE_THRESH: float = 0.5  # 表格结构识别置信度阈值

    # 输出格式："html" / "json" / "both"
    OUTPUT_FORMAT: str = os.getenv("DOC_PARSER_OUTPUT_FORMAT", "both")

    # 公式识别（可选：配置 Mathpix 环境变量后启用高精度 LaTeX 识别）
    MATHPIX_APP_ID: Optional[str] = os.getenv("MATHPIX_APP_ID")
    MATHPIX_APP_KEY: Optional[str] = os.getenv("MATHPIX_APP_KEY")

    @staticmethod
    def use_gpu() -> bool:
        """是否使用 GPU（需要编译支持且至少有一个 CUDA 设备）。"""
        try:
            import paddle
            return (
                bool(paddle.device.is_compiled_with_cuda())
                and paddle.device.cuda.device_count() > 0
            )
        except Exception:
            return False


CONFIG = Config()