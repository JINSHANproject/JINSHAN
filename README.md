# 文档多模态解析系统（基于 PaddleOCR 3.4）

## 1. 项目介绍

本项目实现了一套 **端到端、高精度、可直接部署** 的多模态文档解析系统，基于 PaddleOCR 3.4 与 PPStructure，支持：

- **输入**：单页/多页 PDF、常见图片格式（PNG/JPG/JPEG/BMP）
- **处理流程**：PDF 转图像 → 图像增强预处理 → 元素级检测（文本/表格/图片/公式/页眉/页脚）→ 内容识别 → 逻辑顺序重建 → 标准化 HTML 输出
- **输出**：结构化的 HTML 字符串，使用 `data-bbox="x1,y1,x2,y2"` 标注每个元素的像素坐标，可直接在浏览器中查看或用于后续下游任务（如向量化、检索、提示构造等）。

核心技术栈：

- **语言**：Python 3.9
- **OCR 引擎**：PaddleOCR 3.4（含 PPStructure 表格/版面分析）
- **深度学习框架**：PaddlePaddle / PaddlePaddle-GPU 2.5.2
- **PDF 处理**：pdf2image 1.16.3
- **图像预处理**：Pillow 9.5.0、OpenCV 4.7.0.72

## 2. 环境搭建

### 2.1 Python 与虚拟环境

1. 安装 Python 3.9（建议从 Python 官网或 Anaconda 获取）。
2. 推荐使用 Conda 创建独立环境：

```bash
conda create -n paddleocr-env python=3.9
conda activate paddleocr-env
```

### 2.2 安装依赖

在项目根目录下（`doc_parser_system/` 同级）执行：

```bash
cd doc_parser_system
pip install -r requirements.txt
```

说明：

- `paddlepaddle-gpu==2.5.2` 适用于已正确安装 CUDA/cuDNN 的 GPU 环境；
- 若无 GPU，可手动卸载 GPU 版并安装 CPU 版：

```bash
pip uninstall -y paddlepaddle-gpu
pip install paddlepaddle==2.5.2
```

### 2.3 PaddleOCR 模型下载

首次运行 PaddleOCR 时会自动下载所需模型（中英文文本检测/识别、PPStructure 表格模型等），确保网络畅通即可；若需要离线部署，可参考 PaddleOCR 官方文档将模型手动下载到本地并在创建 `PaddleOCR` / `PPStructure` 时指定 `det_model_dir`、`rec_model_dir` 等参数。

## 3. 快速使用

### 3.1 运行 demo.py 示例脚本

`demo.py` 提供了一键运行的完整流程示例：

```bash
cd doc_parser_system
python demo.py
```

脚本行为：

1. 自动在 `./test_data/` 目录下查找测试文件：
   - 优先使用 `test.pdf` 或任意 PDF；
   - 若无 PDF，则使用图片（PNG/JPG/JPEG/BMP）；
   - 若目录为空，会自动生成一个简单的 `sample.png` 作为示例。
2. 依次执行：
   - 预处理（PDF 转图像、图像增强、尺寸归一）
   - 元素检测（标题/段落/表格/图片/公式/页眉/页脚）
   - 内容识别（文本 OCR、表格结构识别、公式 LaTeX 识别）
   - 逻辑顺序重建（按页码、纵向、横向排序）
   - 标准化 HTML 生成并保存
3. 运行完成后，在 `./output/result.html` 生成最终 HTML，可直接用浏览器打开查看。

### 3.2 自定义输入文件

你也可以直接调用核心流程，对任意 PDF/图片进行解析：

```python
from core.preprocess import preprocess_input
from core.element_detect import detect_elements
from core.content_recognize import recognize_contents
from core.logic_rebuild import rebuild_logic
from core.output_generator import generate_html

from utils.file_io import save_html

file_path = "your_doc.pdf"  # 或图片路径

pages = preprocess_input(file_path)
elements = detect_elements(pages)
elements = recognize_contents(pages, elements)
elements = rebuild_logic(elements)
html = generate_html(elements, wrap_html=True, title="My Document")
save_html(html, "my_result.html")
```

## 4. 模块说明

项目目录结构：

```text
doc_parser_system/
├── config/
│   └── config.py            # 全局配置（OCR 参数、路径、日志级别等）
├── core/
│   ├── preprocess.py        # 输入预处理：PDF 转图像、图像增强、尺寸归一
│   ├── element_detect.py    # 元素检测：基于 PPStructure 的版面/表格检测
│   ├── content_recognize.py # 内容识别：文本 OCR、表格结构还原、公式 LaTeX
│   ├── logic_rebuild.py     # 逻辑关系重建：根据坐标排序，恢复阅读顺序
│   └── output_generator.py  # 标准化 HTML 输出：data-bbox 标注与模板生成
├── utils/
│   ├── coordinate.py        # 坐标归一化、IoU 计算、元素排序工具
│   ├── file_io.py           # 文件读写、类型检测、HTML 保存、测试文件搜索
│   └── logger.py            # 日志封装，支持控制台 + 文件输出
├── demo.py                  # 一键运行示例脚本
├── requirements.txt         # 依赖版本清单
└── README.md                # 当前说明文档
```

各模块输入输出简要说明：

- `core/preprocess.py`
  - 输入：PDF/图片路径
  - 输出：页面列表 `List[Dict]`，每项包含 `page_num`、`image_path`、`width`、`height`
- `core/element_detect.py`
  - 输入：页面列表
  - 输出：元素列表 `List[Dict]`，每项包含：
    - `element_type`: `"h2" | "p" | "table" | "image" | "formula" | "header" | "footer"`
    - `bbox`: `[x1, y1, x2, y2]` 像素坐标
    - `content`: 初始为空字符串
    - `page_num`: 页码
- `core/content_recognize.py`
  - 输入：页面列表 + 元素列表
  - 输出：填充了 `content` 字段的元素列表（表格为 `<table>...</table>` HTML，公式为 `$$...$$`）
- `core/logic_rebuild.py`
  - 输入：元素列表
  - 输出：按 `page_num → y1 → x1` 排序后的元素列表
- `core/output_generator.py`
  - 输入：排序后的元素列表
  - 输出：符合规范的 HTML 字符串（可选择是否包裹完整 `<html>` 结构）

## 5. 测试案例示例

假设有一个简单的单页 PDF，内容如下：

- 第一行：大号加粗标题「文档标题」
- 第二行开始：若干段正文文本
- 中间包含一张图片和一个 3x3 的表格
- 底部有页脚「第 1 页 / 共 1 页」

系统解析后，输出 HTML 结构大致类似（仅示意）：

```html
<div class="header" data-bbox="50,10,900,40">...</div>
<h2 data-bbox="100,50,800,100">文档标题</h2>
<p data-bbox="100,110,800,160">这是一段正文...</p>
<div class="image" data-bbox="100,170,800,320"></div>
<div class="table" data-bbox="100,330,800,500">
  <table>
    <thead>
      <tr><td>表头1</td><td>表头2</td><td>表头3</td></tr>
    </thead>
    <tbody>
      <tr><td>单元格1</td><td>单元格2</td><td>单元格3</td></tr>
      <tr><td>...</td><td>...</td><td>...</td></tr>
    </tbody>
  </table>
</div>
<div class="footer" data-bbox="50,850,900,880">第1页 / 共1页</div>
```

你可以根据 `data-bbox` 属性，将 HTML 元素与原始 PDF/图像中的位置一一对应，用于高亮、联动、或后处理。

## 6. 常见问题与排查建议

### 6.1 OCR 识别准确率低

- 确认输入 PDF/图片分辨率是否足够（本项目默认使用 300 DPI 转图像）；
- 检查是否对扫描件做了合适的预处理（当前实现包含去噪、对比度增强、自适应二值化）；
- 对于非常模糊或噪声较多的文档，可尝试：
  - 提高 DPI（如 400DPI），但会增加计算量；
  - 替换为更高质量的扫描版本；
  - 根据业务需要调整预处理参数（高斯核大小、CLAHE 参数等）。

### 6.2 PDF 转图像失败

- 检查是否安装了 `poppler`（某些系统上 `pdf2image` 依赖本地 poppler）；
- 在 Windows 上，可搜索并安装「poppler for windows」，并将其 `bin` 目录加入 `PATH`；
- 若提示文件损坏，可尝试使用其他 PDF 阅读器打开确认是否可读。

### 6.3 运行时报 GPU 相关错误

- 若无 GPU 或 CUDA 环境不完整，建议使用 CPU 版 PaddlePaddle：

```bash
pip uninstall -y paddlepaddle-gpu
pip install paddlepaddle==2.5.2
```

- 或在代码中强制关闭 GPU（本项目已自动根据 `paddle.device.is_compiled_with_cuda()` 进行判断，一般无需修改）。

### 6.4 表格结构还原不正确

- PPStructure 的表格检测对表格线条清晰度较敏感：
  - 避免过度压缩、模糊的截图；
  - 建议保持表格边框清晰、对比度较高；
- 若表格较复杂（多层表头、合并单元格多），可结合业务场景对输出 HTML 进行后处理校正。

### 6.5 公式识别效果不理想

- 若配置了 Mathpix（环境变量 `MATHPIX_APP_ID` 与 `MATHPIX_APP_KEY`），优先使用其 LaTeX 识别结果；
- 否则将退化为 PaddleOCR 的普通文本识别，可能无法完全还原复杂公式；
- 对于公式密集、排版要求很高的场景，推荐接入专门的公式 OCR 服务。

---


