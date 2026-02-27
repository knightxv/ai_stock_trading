#!/usr/bin/env python3
"""从 PDF 提取文本并输出到 stdout。用法: python extract_text.py <path_to.pdf>"""

import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("用法: python extract_text.py <path_to.pdf>", file=sys.stderr)
        sys.exit(1)
    path = Path(sys.argv[1]).resolve()
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        sys.exit(1)
    if path.suffix.lower() != ".pdf":
        print("请提供 .pdf 文件", file=sys.stderr)
        sys.exit(1)

    try:
        from pypdf import PdfReader
    except ImportError:
        print("请先安装: pip install pypdf", file=sys.stderr)
        sys.exit(1)

    reader = PdfReader(str(path))
    for i, page in enumerate(reader.pages):
        if i > 0:
            print("\n--- Page", i + 1, "---\n")
        text = page.extract_text()
        if text:
            print(text, end="")

if __name__ == "__main__":
    main()
