# 多模态文档识别系统

> 基于 PaddleOCR 2.7 / PPStructure 的端到端文档解析与结构化提取系统

---

## 目录

1. [项目简介](#1-项目简介)
2. [核心能力与创新点](#2-核心能力与创新点)
3. [系统架构](#3-系统架构)
4. [目录结构](#4-目录结构)
5. [环境配置](#5-环境配置)
6. [快速开始](#6-快速开始)
7. [命令行参数详解](#7-命令行参数详解)
8. [输出格式说明](#8-输出格式说明)
9. [配置项参考](#9-配置项参考)
10. [模块说明](#10-模块说明)
11. [常见问题排查](#11-常见问题排查)

---

## 1. 项目简介

本系统是一套**端到端、多模态、可直接部署**的文档智能解析引擎。它接收 PDF 或图片形式的文档，经过图像增强、版面分析、内容识别、逻辑重建四个阶段，将文档中各类元素（标题、段落、表格、图片、公式、页眉、页脚、页码）完整提取，并以**结构化 HTML** 和**标准化 JSON** 两种格式输出，每个元素均附带像素级坐标 `data-bbox`，支持与原始文档的精确对位。

**典型使用场景**：
- 文档数字化与归档
- RAG（检索增强生成）知识库构建的文档预处理
- 合同、报告、试卷等专业文档的自动化解析
- 文档可视化标注与审阅工具的后端引擎

---

## 2. 核心能力与创新点

### 2.1 全类型元素检测

系统识别并定位文档中的 **8 类元素**，覆盖文档结构的完整语义层次：

| 元素类型 | 说明 | 输出标签 |
|---|---|---|
| `h1 / h2 / h3` | 多级标题（按字体高度自动推断层级） | `<h1>` ~ `<h3>` |
| `p` | 正文段落（含段落归属 ID） | `<p>` |
| `table` | 表格（PPStructure 结构化还原为 HTML） | `<div class="doc-table-wrap">` |
| `image` | 图片区域（裁切保存，生成 `<img>`） | `<figure class="doc-image">` |
| `formula` | 数学公式（LaTeX 格式，支持 Mathpix） | `<div class="formula">` |
| `header` | 页眉 | `<div class="doc-header">` |
| `footer` | 页脚 | `<div class="doc-footer">` |
| `page_number` | 页码（正则识别，自动分离） | `<span class="page-num">` |

### 2.2 三级保障的双引擎协同架构（创新点一）

系统采用**主引擎（PPStructure）+ 降级引擎（PaddleOCR）**的双引擎设计，并针对版面模型的常见误判场景建立了三级保障机制：

| 级别 | 触发条件 | 处理方式 |
|---|---|---|
| 第一级 | PPStructure 成功且文本元素 ≥ 3 | 直接使用 PPStructure 结果 |
| 第二级 | PPStructure 成功但文本元素 < 3 | OCR 补充扫描，通过 IoU 去重后合并 |
| 第三级 | PPStructure 异常或无结果 | 完全降级为纯 OCR + 位置规则分类 |

此外，PPStructure 对含图标/装饰的信息图、演示文稿截图等场景，容易将文字区域误标为 `figure`（图片）。系统在 `parse_structure_result()` 中对 `figure` 类型进行二次判断：若该区域内含有 ≥ 2 条 OCR 文本行，则自动将每行展开为独立的文本元素（附行级 bbox），确保任何场景下文字内容不丢失。

### 2.3 基于字体高度的动态标题分层（创新点二）

传统方案依赖预设的字体大小阈值。本系统在 `infer_heading_levels()` 中采用**数据自适应分层**：

1. 统计当前页面中所有 `title` 类型元素的 bbox 高度分布
2. 按高度从大到小动态划分 h1 / h2 / h3 三级，无需手工设定阈值
3. 对不同文档、不同排版风格均能准确识别层级关系

### 2.4 多栏布局感知排序（创新点三）

`detect_columns()` 通过分析元素中心 x 坐标的双峰分布，自动判断单栏/双栏布局，并在 `sort_elements_multicolumn()` 中按**栏优先**重排阅读顺序（左栏从上到下读完后再读右栏），而非简单的 y 坐标全局排序——后者会导致双栏文档阅读顺序完全错乱。

### 2.5 段落聚合与语义分组（创新点四）

`assign_paragraph_hierarchy()` 以**行间距自适应阈值**（行高均值 × 1.5）为依据，将连续的文本行自动聚合为逻辑段落，并写入 `paragraph_id`。该信息在 JSON 输出中可直接用于 RAG 的文档分块（chunking）。

### 2.6 公式识别双链路（创新点五）

- **高精度链路**：配置 Mathpix API 后，将公式图像上传云端，返回高质量 LaTeX 字符串，格式为 `$$...$$`
- **本地降级链路**：无 Mathpix 时，使用 PaddleOCR 对公式区域进行文本识别，结果包裹 `$...$`，保留公式的视觉呈现
- 两条链路通过配置项自动切换，无需修改代码

### 2.7 置信度透明化输出

每个元素在 JSON 输出中均携带 `confidence` 字段（0~1），识别质量低于 `MIN_CONFIDENCE` 阈值的元素在 HTML 中通过 `data-low-confidence` 属性标记、视觉上降低透明度（`opacity: 0.6`），使下游系统和审阅人员可快速定位低质量区域。

---

## 3. 系统架构

```
输入 (PDF / 图片)
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  Stage 1: 预处理  (core/preprocess.py)               │
│  PDF → 多页 PNG (300 DPI)                            │
│  图像增强：高斯去噪 + CLAHE 对比度增强               │
│  尺寸归一化（超出 MAX_WIDTH 则等比缩放）             │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Stage 2: 元素检测  (core/element_detect.py)         │
│  主路：PPStructure 版面分析                          │
│    → text / title / table / figure / formula /      │
│      header / footer                                │
│  降级：PaddleOCR 文本行 + 位置规则分类               │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Stage 3: 内容识别  (core/content_recognize.py)      │
│  文本元素：二次 OCR 补充 + 置信度过滤                │
│  表格元素：PPStructure → HTML <table>                │
│  公式元素：Mathpix API / PaddleOCR 降级              │
│  图片元素：裁切保存到 output/images/                 │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Stage 4: 逻辑重建  (core/logic_rebuild.py)          │
│  页码识别与分离                                      │
│  标题层级推断（h1 / h2 / h3）                       │
│  段落聚合（paragraph_id）                            │
│  多栏检测 + 阅读顺序排序                             │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Stage 5: 结构化输出  (core/output_generator.py)     │
│  HTML：完整样式 + data-bbox + 低置信度标记           │
│  JSON：标准化元素结构，含所有语义字段                │
└──────────────────────────┬──────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    output/result.html         output/result.json
    output/images/*.png        (图片区域文件)
```

---

## 4. 目录结构

```
JINSHAN/
├── config/
│   ├── __init__.py
│   └── config.py              # 全局配置类，所有可调参数均在此
├── core/
│   ├── __init__.py
│   ├── preprocess.py          # PDF 转图 + 图像增强
│   ├── element_detect.py      # 版面分析 + 元素检测（双引擎）
│   ├── content_recognize.py   # 文本/表格/公式/图片内容识别
│   ├── logic_rebuild.py       # 逻辑关系重建
│   ├── layout_analysis.py     # PPStructure 版面分析封装
│   └── output_generator.py    # HTML / JSON 生成
├── utils/
│   ├── __init__.py
│   ├── coordinate.py          # 坐标工具：排序/多栏检测/标题分层/段落归属/页码识别
│   ├── file_io.py             # 文件读写（HTML/JSON 保存、目录管理）
│   ├── logger.py              # 日志封装（控制台 + 文件双输出）
│   └── ocr_helper.py          # PaddleOCR / PPStructure 单例管理 + 结果解析
├── output/
│   ├── result.html            # 最新一次输出的 HTML 文件
│   ├── result.json            # 最新一次输出的 JSON 文件
│   ├── doc_parser.log         # 运行日志
│   └── images/                # 图片区域裁切保存目录
├── test_data/                 # 待解析的测试文件（PDF / 图片）
├── tmp/                       # 临时文件（PDF 转图、增强后图像）
├── demo.py                    # 命令行入口
└── requirements.txt           # Python 依赖清单
```

---

## 5. 环境配置

### 5.1 前置要求

| 软件 | 推荐版本 | 说明 |
|---|---|---|
| Python | 3.9 | 其他 3.x 版本未经充分测试 |
| Anaconda / Miniconda | 任意 | 强烈推荐使用 conda 隔离环境 |
| CUDA | 11.x 或 12.x（可选） | 有 GPU 时使用，无 GPU 可全程 CPU 推理 |
| poppler | 任意 | 处理 PDF 文件时必需，见下方说明 |

### 5.2 创建 conda 环境

```bash
conda create -n paddle_ocr python=3.9
conda activate paddle_ocr
```

### 5.3 安装依赖

进入项目根目录后执行：

```bash
cd JINSHAN
pip install -r requirements.txt
```

**GPU 用户**（推荐，速度提升显著）：

`requirements.txt` 中已指定 `paddlepaddle-gpu>=3.0.0`，需确保系统已正确安装 CUDA 和 cuDNN。若安装时报版本冲突，可手动指定：

```bash
# 以 CUDA 11.8 为例
pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

**CPU 用户**（无 GPU 环境）：

```bash
pip uninstall -y paddlepaddle-gpu
pip install paddlepaddle>=3.0.0
```

### 5.4 安装 poppler（PDF 支持）

处理 PDF 文件时，`pdf2image` 依赖本地的 poppler 工具。

**Ubuntu / Debian**：
```bash
sudo apt-get install poppler-utils
```

**CentOS / RHEL**：
```bash
sudo yum install poppler-utils
```

**macOS**：
```bash
brew install poppler
```

**Windows**：
从 [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) 下载，解压后将 `bin/` 目录加入系统 `PATH`。

> 若仅处理图片（JPG/PNG/BMP）而不处理 PDF，可跳过此步骤。

### 5.5 PaddleOCR 模型下载

首次运行时，PaddleOCR 和 PPStructure 会**自动下载**所需模型到 `~/.paddleocr/` 目录。需要确保网络通畅。下载内容包括：
- 文本检测模型（det）
- 文本识别模型（rec）
- 版面分析模型（layout）
- 表格结构识别模型（table）

若需**离线部署**，请参考 [PaddleOCR 官方文档](https://github.com/PaddlePaddle/PaddleOCR) 手动下载模型，并在 `config/config.py` 或初始化 OCR 实例时指定模型路径。

### 5.6 公式识别配置（可选）

若需高精度 LaTeX 公式识别，可配置 [Mathpix API](https://mathpix.com/)：

```bash
export MATHPIX_APP_ID="your_app_id"
export MATHPIX_APP_KEY="your_app_key"
```

未配置时，系统自动降级为 PaddleOCR 对公式区域进行普通文本识别。

---

## 6. 快速开始

### 6.1 使用测试文件一键运行

将待解析的 PDF 或图片文件放入 `test_data/` 目录，然后运行：

```bash
conda activate paddle_ocr
cd JINSHAN
python demo.py
```

系统将自动发现测试文件并完成解析，输出到 `output/` 目录：
- `output/result.html`：带样式的结构化 HTML，可直接用浏览器打开
- `output/result.json`：标准化 JSON，可用于下游系统对接
- `output/images/`：文档中图片区域的裁切文件

若 `test_data/` 目录为空，系统会自动生成一个简单的示例图片进行演示。

### 6.2 指定输入文件

```bash
# 处理指定 PDF 文件
python demo.py --input /path/to/your/document.pdf

# 处理指定图片
python demo.py --input /path/to/your/scan.jpg
```

### 6.3 指定输出格式

```bash
# 只输出 HTML
python demo.py --input document.pdf --format html

# 只输出 JSON
python demo.py --input document.pdf --format json

# 同时输出 HTML 和 JSON（默认）
python demo.py --input document.pdf --format both
```

### 6.4 在代码中直接调用

```python
from core.preprocess import preprocess_input
from core.element_detect import detect_elements
from core.content_recognize import recognize_contents
from core.logic_rebuild import rebuild_logic
from core.output_generator import generate_html, generate_json
from utils.file_io import save_html, save_json

# 处理文件
pages = preprocess_input("your_document.pdf")
elements = detect_elements(pages)
elements = recognize_contents(pages, elements)

page_width = pages[0].get("width", 0) if pages else 0
page_height = pages[0].get("height", 0) if pages else 0
elements = rebuild_logic(elements, page_width=page_width, page_height=page_height)

# 输出 HTML
html = generate_html(elements, wrap_html=True, title="My Document")
save_html(html, "result.html")

# 输出 JSON
json_str = generate_json(elements)
save_json(json_str, "result.json")
```

---

## 7. 命令行参数详解

```
python demo.py [OPTIONS]
```

| 参数 | 简写 | 默认值 | 说明 |
|---|---|---|---|
| `--input FILE` | `-i` | 自动发现 | 输入文件路径（PDF 或图片），不指定则在 `test_data/` 中查找 |
| `--format` | `-f` | `both` | 输出格式，可选 `html` / `json` / `both` |
| `--no-ppstructure` | — | 关闭 | 禁用 PPStructure，强制使用纯 OCR 降级模式（适用于模型未下载时的快速测试） |
| `--output-dir DIR` | — | `output/` | 指定输出目录，默认为项目根目录下的 `output/` |

**示例**：

```bash
# 以纯 OCR 模式快速测试，只输出 JSON，保存到自定义目录
python demo.py -i test_data/sample.jpg --no-ppstructure -f json --output-dir /tmp/results
```

---

## 8. 输出格式说明

### 8.1 HTML 输出

输出文件为带完整样式的独立 HTML，可直接在浏览器中打开查阅。

**关键特性**：
- 每个元素携带 `data-bbox="x1,y1,x2,y2"` 属性，记录像素级坐标，可与原始图像对位
- 低置信度元素标记 `data-low-confidence="true"`，视觉上以半透明显示
- 表格内容为 PPStructure 生成的完整 HTML 表格，支持合并单元格
- 公式以 `$$...$$` 包裹，可配合 MathJax 等前端库渲染为数学公式
- 图片以 `<figure><img src="images/page1_img1.png" /></figure>` 呈现

**HTML 结构示例**：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>文档标题</title>
  <style>/* 内嵌样式 */</style>
</head>
<body>
  <div class="doc-header" data-bbox="0,0,970,40">页眉文字</div>
  <h1 data-bbox="100,50,800,90">一级标题</h1>
  <h2 data-bbox="100,100,600,130">二级标题</h2>
  <p data-bbox="100,140,800,165">正文段落...</p>
  <div class="doc-table-wrap" data-bbox="100,200,800,400">
    <table><tr><td>单元格</td></tr></table>
  </div>
  <div class="formula" data-bbox="100,420,500,460">$$E=mc^2$$</div>
  <figure class="doc-image" data-bbox="100,470,400,650">
    <img src="images/page1_img1.png" alt="图片区域" />
  </figure>
  <span class="page-num" data-bbox="450,950,520,975">1</span>
</body>
</html>
```

### 8.2 JSON 输出

标准化 JSON，适合程序化处理和下游系统对接（如 RAG 知识库构建、数据库存储等）。

**顶层结构**：

```json
{
  "elements": [...],
  "total": 15
}
```

**单个元素结构**：

```json
{
  "index": 3,
  "page_num": 1,
  "element_type": "p",
  "bbox": [100, 140, 800, 165],
  "content": "这是一段正文内容。",
  "confidence": 0.9923,
  "paragraph_id": 2
}
```

**元素类型与附加字段**：

| `element_type` | 附加字段 | 说明 |
|---|---|---|
| `h1` / `h2` / `h3` | — | `content` 为标题文本 |
| `p` | `paragraph_id` | 段落归属 ID，同一段落的多行共享相同 ID |
| `table` | — | `content` 为 HTML 表格字符串 |
| `image` | `image_path` | `content` 为图片相对路径，`image_path` 为绝对路径 |
| `formula` | `formula_engine` | `content` 为 LaTeX 字符串，`formula_engine` 为 `mathpix` 或 `ocr_fallback` |
| `header` / `footer` | — | `content` 为页眉页脚文本 |
| `page_number` | — | `content` 为页码字符串 |
| 任意 | `low_confidence: true` | 置信度低于阈值时出现，提示人工复核 |

---

## 9. 配置项参考

所有配置项集中在 `config/config.py` 的 `Config` 类中，也可通过环境变量覆盖部分配置：

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|---|---|---|---|---|
| `OCR_LANG` | str | `"ch"` | — | OCR 语言，`ch`=中英文，`en`=英文 |
| `OCR_USE_ANGLE_CLS` | bool | `True` | — | 是否启用文字方向分类（适用于旋转文字） |
| `DPI` | int | `300` | — | PDF 转图时的分辨率，越高越清晰但越慢 |
| `MAX_WIDTH` | int | `2000` | — | 图像最大宽度（像素），超出则等比缩放 |
| `USE_PP_STRUCTURE` | bool | `True` | — | 是否启用 PPStructure 版面分析 |
| `MIN_CONFIDENCE` | float | `0.5` | — | 文本识别置信度阈值，低于此值标记为低置信度 |
| `TABLE_STRUCTURE_SCORE_THRESH` | float | `0.5` | — | 表格结构识别置信度阈值 |
| `OUTPUT_FORMAT` | str | `"both"` | `DOC_PARSER_OUTPUT_FORMAT` | 默认输出格式：`html` / `json` / `both` |
| `LOG_LEVEL` | str | `"INFO"` | `DOC_PARSER_LOG_LEVEL` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `MATHPIX_APP_ID` | str / None | `None` | `MATHPIX_APP_ID` | Mathpix App ID（公式识别用） |
| `MATHPIX_APP_KEY` | str / None | `None` | `MATHPIX_APP_KEY` | Mathpix App Key |

**通过环境变量覆盖示例**：

```bash
# 只输出 JSON，开启 DEBUG 日志
export DOC_PARSER_OUTPUT_FORMAT=json
export DOC_PARSER_LOG_LEVEL=DEBUG
python demo.py --input document.pdf
```

---

## 10. 模块说明

### `core/preprocess.py`

- **输入**：PDF 或图片文件路径
- **输出**：`List[Dict]`，每项包含 `page_num`、`image_path`（增强后）、`original_path`（原图）、`width`、`height`
- **功能**：
  - `pdf_to_images()`：使用 pdf2image（300 DPI）将 PDF 转为 PNG，处理透明背景
  - `enhance_image()`：高斯去噪（3×3 核）→ CLAHE 对比度增强（clipLimit=2.0）→ 尺寸归一化

### `core/element_detect.py`

- **输入**：页面列表
- **输出**：`List[Dict]`，每项包含 `element_type`、`bbox`、`content`、`page_num`、`extra`
- **功能（三级保障）**：
  - 第一级：PPStructure 结果质量足够（文本元素 ≥ 3）时直接使用
  - 第二级：PPStructure 有结果但文本稀少时，补充纯 OCR 扫描，通过 `_merge_ocr_supplement()` 计算 IoU 去重后合并
  - 第三级：PPStructure 完全失败时，完全降级为 PaddleOCR 文本行检测 + 位置规则分类

### `core/content_recognize.py`

- **输入**：页面列表 + 元素列表
- **输出**：填充了 `content` 字段的元素列表
- **功能按元素类型分路**：
  - 文本类：二次 OCR 补充空白内容 + 置信度过滤标记
  - 表格类：PPStructure 结构化识别 → HTML 表格（失败则 OCR 降级）
  - 公式类：Mathpix API → LaTeX（失败或未配置则 OCR 降级）
  - 图片类：裁切保存至 `output/images/`，写入相对路径

### `core/logic_rebuild.py`

- **输入**：元素列表 + 页面尺寸
- **输出**：经过逻辑排序和层级标注的元素列表
- **功能**：
  1. 页码识别（正则匹配 + 位置判断）
  2. 标题层级推断（字体高度自适应分层）
  3. 段落聚合（行间距阈值 = 平均行高 × 1.5）
  4. 多栏检测 + 阅读顺序重排

### `core/output_generator.py`

- **输入**：元素列表
- **输出**：HTML 字符串 / JSON 字符串
- **功能**：
  - `generate_html()`：生成带 CSS 样式和 `data-bbox` 属性的完整 HTML
  - `generate_json()`：生成标准化 JSON，含所有语义字段

### `utils/ocr_helper.py`

- `get_ocr_instance()`：PaddleOCR 单例（用于降级回退和局部二次识别）
- `get_structure_instance()`：PPStructure 单例（版面分析主引擎）
- `parse_ocr_result()`：兼容 PaddleOCR 新旧版格式的结果解析
- `parse_structure_result()`：PPStructure 结果统一化解析，含坐标偏移还原；对 `figure` 类型区域做二次判断，含文字的误判区域自动展开为逐行文本元素
- `_region_has_text()`：判断 PPStructure region 的 res 字段是否含有足够的 OCR 文本行
- `_extract_ocr_lines_from_res()`：从 res 字段提取结构化文本行列表

### `utils/coordinate.py`

- `sort_elements()`：基础坐标排序
- `sort_elements_multicolumn()`：多栏感知阅读顺序排序
- `detect_columns()`：页面栏数自动检测
- `infer_heading_levels()`：标题层级自适应推断
- `assign_paragraph_hierarchy()`：段落聚合与 ID 分配
- `identify_page_numbers()`：页码元素识别与类型修正

---

## 11. 常见问题排查

### Q1: 运行报错 `Permission denied: ~/.paddleocr/whl/table`

PPStructure 首次运行时需要将模型下载到 `~/.paddleocr/` 目录。若该目录权限不足，可手动创建并授权：

```bash
mkdir -p ~/.paddleocr/whl/table ~/.paddleocr/whl/layout
chmod -R 755 ~/.paddleocr
```

或指定模型目录到有写权限的路径（需修改 `utils/ocr_helper.py` 中的初始化参数）。

系统会自动降级为纯 OCR 模式，不会崩溃。若只需纯 OCR 功能，可在启动时加上 `--no-ppstructure`。

### Q2: 报错 `(InvalidArgument) Device id must be less than GPU count`

paddle 检测到 GPU 编译支持，但实际无可用 GPU 设备。本系统已在 `Config.use_gpu()` 中同时检查编译支持和设备数量，通常会自动回退 CPU 模式。若仍报错，可强制安装 CPU 版 paddle：

```bash
pip uninstall -y paddlepaddle-gpu
pip install paddlepaddle>=3.0.0
```

### Q3: PDF 转图报错 `pdf2image` 失败

- 确认已安装 poppler，见 [5.4 安装 poppler](#54-安装-poppler-pdf-支持)
- 检查 PDF 文件是否损坏（尝试用 PDF 阅读器打开）
- 可临时将 PDF 转为图片后再处理，绕过此依赖

### Q4: OCR 识别准确率低

- 确认图片分辨率足够（建议不低于 150 DPI，300 DPI 最佳）
- 对于扫描件，尝试调大 `DPI` 配置项（如 400），但会增加处理时间
- 检查图像是否有严重的噪点或模糊，必要时进行外部图像预处理
- 手写体文字识别效果受字迹清晰度影响较大，潦草手写体可能识别率偏低

### Q5: 表格结构还原不正确

- PPStructure 对表格线条清晰度敏感，建议保持表格边框清晰
- 复杂表格（多层表头、大量合并单元格）可能识别不完整，需人工后处理
- 可通过调低 `TABLE_STRUCTURE_SCORE_THRESH` 允许更多候选结果，或调高以过滤低质量结果

### Q6: 多栏文档阅读顺序混乱

若自动双栏检测未能正确识别（如文档宽度特殊），可在 `utils/coordinate.py` 的 `detect_columns()` 中调整参数：
- `margin`：中线两侧的过渡区比例（默认 10%）
- 左右侧元素各占总数的最小比例（默认 25%）

### Q7: 公式识别结果为普通文本

未配置 Mathpix API 时系统使用 OCR 降级，复杂公式可能识别为文字。配置 Mathpix 后可显著提升公式识别质量：

```bash
export MATHPIX_APP_ID="your_app_id"
export MATHPIX_APP_KEY="your_app_key"
python demo.py --input document.pdf
```

### Q8: 信息图、PPT 截图等场景下文字内容丢失

PPStructure 版面模型对含图标、装饰背景的文字区域（如信息图、演示文稿截图）容易误判为 `figure`（图片），导致文字内容被丢弃。

本系统已在 `parse_structure_result()` 中内置修复逻辑：对 `figure` 区域做二次检查，若该区域 OCR 结果中含有 ≥ 2 条文本行，则自动展开为逐行的 `p` 元素。同时 `detect_elements()` 的第二级保障（OCR 补充 + IoU 去重合并）也会进一步兜底，确保文字不遗漏。

若上述自动处理后仍有遗漏，可通过 `--no-ppstructure` 参数完全切换为纯 OCR 模式：

```bash
python demo.py --input document.pdf --no-ppstructure
```

---

## 版本信息

- Python：3.9
- PaddlePaddle：3.x（GPU 推荐）/ 3.x（CPU）
- PaddleOCR：2.7.x
- 最后更新：2026-03
