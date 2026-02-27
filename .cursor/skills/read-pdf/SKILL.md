---
name: read-pdf
description: 从 PDF 文件中提取文本与表格（含 OCR 扫描件），供后续分析、摘要或入库。当用户提到 PDF、需要读取/解析 PDF、扫描件、或 @ 了 .pdf 文件时使用。
---

# 读取 PDF 文档

当用户需要读取、解析或分析 PDF 内容时，先提取文本再基于文本作答。

## 何时使用

- 用户提到「读这个 PDF」「解析/提取 PDF」「PDF 里写的是什么」
- 用户 @ 了 `.pdf` 文件或给出 PDF 路径
- 需要从 PDF 中摘录、摘要、答题或写入知识库

## 操作步骤

1. **确认 PDF 路径**：从用户消息或 @ 的文件中取得 PDF 的绝对或相对路径。
2. **优先直接提取**：在项目根目录执行文本提取；若有虚拟环境请用其 Python。
   ```bash
   python .cursor/skills/read-pdf/scripts/extract_text.py "path/to/file.pdf"
   ```
3. **若正文几乎为空（仅页脚/水印）**：改用 OCR 脚本（适用于扫描件/图片型 PDF）。
   ```bash
   python .cursor/skills/read-pdf/scripts/extract_ocr.py "path/to/file.pdf"
   ```
4. **使用结果**：根据用户需求对提取出的文本做摘要、问答、摘录或按模板输出。

## 依赖

| 方式 | 依赖 | 安装 |
|------|------|------|
| 直接提取 | `pypdf` | `pip install pypdf` |
| OCR 提取 | `pdf2image`、`pytesseract`，系统需 **poppler**、**tesseract** | 见下 |

**OCR 依赖安装：**

```bash
# Python 包
pip install pdf2image pytesseract

# macOS（Homebrew）
brew install poppler tesseract tesseract-lang   # tesseract-lang 含中文 chi_sim

# Ubuntu/Debian
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-chi-sim
```

## 输出说明

- 两个脚本均按页顺序输出纯文本，页与页之间用 `\n--- Page N ---\n` 分隔。
- 先试 `extract_text.py`；若每页只有少量重复文字（如水印），再试 `extract_ocr.py`。

## OCR 脚本说明

- `extract_ocr.py` 默认使用 `chi_sim+eng`（简体中文+英文）；仅英文可用 `--lang eng`。
- OCR 较慢且占内存，仅在对扫描件/图片型 PDF 或直接提取几乎无正文时使用。

## 可选：表格较多的 PDF

若用户明确需要表格且提取不理想，可改用 `pdfplumber` 再提取表格：

```bash
pip install pdfplumber
python -c "
import pdfplumber
with pdfplumber.open('path/to/file.pdf') as pdf:
    for i, p in enumerate(pdf.pages):
        for t in p.extract_tables():
            print(t)
"
```

优先使用本 skill 自带脚本；仅在表格提取不足时再建议安装并使用 pdfplumber。
