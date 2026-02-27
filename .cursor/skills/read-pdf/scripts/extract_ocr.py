#!/usr/bin/env python3
"""对 PDF 做 OCR 提取文本并输出到 stdout。适用于扫描件/图片型 PDF。
用法: python extract_ocr.py <path_to.pdf> [--lang LANG]
依赖: pip install pdf2image pytesseract；系统需安装 poppler、tesseract 及中文包(chi_sim)。"""

import sys
from pathlib import Path

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lang = "chi_sim+eng"
    if "--lang" in sys.argv:
        i = sys.argv.index("--lang")
        if i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]

    if len(args) < 1:
        print("用法: python extract_ocr.py <path_to.pdf> [--lang chi_sim+eng]", file=sys.stderr)
        print("依赖: pip install pdf2image pytesseract; macOS: brew install poppler tesseract tesseract-lang", file=sys.stderr)
        sys.exit(1)
    path = Path(args[0]).resolve()
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        sys.exit(1)
    if path.suffix.lower() != ".pdf":
        print("请提供 .pdf 文件", file=sys.stderr)
        sys.exit(1)

    try:
        from pdf2image import convert_from_path
    except ImportError:
        print("请先安装: pip install pdf2image", file=sys.stderr)
        sys.exit(1)
    try:
        import pytesseract
    except ImportError:
        print("请先安装: pip install pytesseract", file=sys.stderr)
        sys.exit(1)

    try:
        images = convert_from_path(str(path), dpi=200)
    except Exception as e:
        print(f"PDF 转图片失败(需安装 poppler): {e}", file=sys.stderr)
        sys.exit(1)

    # 若未安装 chi_sim 则仅用 eng
    use_lang = lang
    if "chi" in lang:
        try:
            langs = pytesseract.get_languages()
            if "chi_sim" not in langs:
                use_lang = "eng"
        except Exception:
            use_lang = "eng"

    for i, img in enumerate(images):
        if i > 0:
            print("\n--- Page", i + 1, "---\n")
        try:
            text = pytesseract.image_to_string(img, lang=use_lang)
        except Exception:
            text = pytesseract.image_to_string(img, lang="eng")
        if text:
            print(text.rstrip())

if __name__ == "__main__":
    main()
