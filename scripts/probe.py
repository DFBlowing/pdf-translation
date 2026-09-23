# -*- coding: utf-8 -*-
"""Stage 1 - probe a PDF: is it born-digital, and what is its typographic structure?

Usage:
    python probe.py <input.pdf> [--pages 1-10]

Reports page count, page size, per-page block counts, the font-size histogram
(which yields the heading hierarchy) and the font families in use.
"""
import sys, argparse
from collections import Counter

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf missing - pip install pymupdf")


def parse_range(s, total):
    if not s:
        return 0, total
    if "-" in s:
        a, b = s.split("-", 1)
        return max(0, int(a) - 1), min(total, int(b))
    n = int(s)
    return max(0, n - 1), min(total, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default=None, help="e.g. 1-10 (default: whole file)")
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    first, last = parse_range(a.pages, doc.page_count)

    p0 = doc[0].rect
    print(f"file       : {a.pdf}")
    print(f"pages      : {doc.page_count}")
    print(f"page size  : {p0.width:.1f} x {p0.height:.1f} pt")
    print(f"inspecting : pages {first+1}-{last}")
    print()

    # ---- collect spans over the inspected range ----
    sizes = Counter()          # size -> char count
    fonts = Counter()          # font -> char count
    pages = []
    for pno in range(first, last):
        page = doc[pno]
        blocks = page.get_text("dict")["blocks"]
        ntxt = sum(1 for b in blocks if b["type"] == 0)
        nimg = sum(1 for b in blocks if b["type"] == 1)
        chars = 0
        per_size = Counter()
        for b in blocks:
            if b["type"] != 0:
                continue
            for l in b.get("lines", []):
                for s in l["spans"]:
                    t = s["text"].strip()
                    if not t:
                        continue
                    chars += len(t)
                    k = round(s["size"], 1)
                    sizes[k] += len(t)
                    per_size[k] += len(t)
                    fonts[s["font"]] += len(t)
        pages.append((pno + 1, ntxt, nimg, chars, per_size))

    # ---- font-size histogram = heading hierarchy ----
    print("=== font-size histogram (size : chars) ===")
    for size, n in sizes.most_common(14):
        bar = "#" * min(60, n // 20)
        print(f"  {size:6.1f}pt  {n:6d}  {bar}")
    print()

    print("=== font families (chars) ===")
    for f, n in fonts.most_common(14):
        tag = ""
        if f.startswith("Type3"):
            tag = "  <- Type3 glyph procs (may be math, OR a non-embeddable CJK font)"
        elif "Bold" in f:
            tag = "  <- bold (heading candidate)"
        print(f"  {f:38} {n:6d}{tag}")
    print()

    # ---- per-page summary ----
    print("=== per page ===")
    for pno, ntxt, nimg, chars, per_size in pages:
        big = [s for s in per_size if per_size[s] > 0]
        head = f"  sizes={sorted(big, reverse=True)[:3]}"
        print(f"  p{pno:<4} text_blocks={ntxt:<4} images={nimg:<4} chars={chars:<6}{head}")

    # ---- born-digital judgement ----
    print()
    total_chars = sum(sizes.values())
    cjk = 0
    for pno in range(first, last):
        t = doc[pno].get_text()
        cjk += sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
    print("=== judgement ===")
    if total_chars > 200:
        print(f"  text layer is present ({total_chars} chars) -> likely BORN-DIGITAL.")
        print( "  => PyMuPDF get_text('dict') is sufficient; no OCR needed.")
        print( "  => Do NOT reach for MinerU/Marker. Go straight to extract.py.")
    else:
        print(f"  almost no text ({total_chars} chars) -> likely SCANNED.")
        print( "  => this HTML+KaTeX route is WRONG. Use an OCR-capable extractor instead.")
    if cjk:
        print(f"  NOTE: {cjk} CJK chars already present - this file may be partially translated.")
    print()
    print("  next: python extract.py <pdf> <workdir> --pages N-M")


if __name__ == "__main__":
    main()
