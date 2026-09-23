# -*- coding: utf-8 -*-
"""Measure any two PDFs against each other - run this BEFORE choosing a plan.

Usage:
    python compare.py <mine.pdf> <reference.pdf> [more.pdf ...]

Prints pages, char count, math-font char count, Type3 char count, embedded
images, size, and the producer/creator string for each file.

TWO FACTS FALL OUT IMMEDIATELY, and both should change your plan:

  * Same producer string  => the rendering ENGINE is not the difference.
    Do not rewrite the pipeline. Look at content instead.

  * Reference has far more math-font chars => the difference is FORMULA
    TYPESETTING. That is stage 4's job. No amount of extractor-shopping fixes it.

Read 'producer' before you believe anything anyone said about "better tools".
"""
import sys, os
from collections import Counter

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf missing - pip install pymupdf")

MATH_HINTS = ("KaTeX", "Math", "CMSY", "CMR", "CMEX", "MSAM", "MSBM", "STIX")


def stats(path):
    d = pymupdf.open(path)
    fonts = Counter()
    for i in range(d.page_count):
        for b in d[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["text"].strip():
                        fonts[s["font"]] += len(s["text"])
    total = sum(fonts.values())
    math_chars = sum(v for k, v in fonts.items() if any(h in k for h in MATH_HINTS))
    t3 = sum(v for k, v in fonts.items() if k.startswith("Type3"))
    imgs = sum(len(d[i].get_images(full=True)) for i in range(d.page_count))
    md = d.metadata or {}
    return {
        "path": path,
        "pages": d.page_count,
        "chars": total,
        "math": math_chars,
        "type3": t3,
        "images": imgs,
        "mb": os.path.getsize(path) / 1e6,
        "producer": md.get("producer", ""),
        "creator": (md.get("creator", "") or "")[:60],
        "title": (md.get("title", "") or "")[:46],
    }


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rows = [stats(p) for p in sys.argv[1:]]

    hdr = (f'{"file":30} {"pages":>6} {"chars":>8} {"math":>7} '
           f'{"Type3":>7} {"imgs":>5} {"MB":>7}')
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        name = os.path.basename(r["path"])[:29]
        print(f'{name:30} {r["pages"]:>6} {r["chars"]:>8} {r["math"]:>7} '
              f'{r["type3"]:>7} {r["images"]:>5} {r["mb"]:>7.2f}')

    print()
    for r in rows:
        print(f'{os.path.basename(r["path"])[:29]:30} producer={r["producer"]!r}')
        print(f'{"":30} title={r["title"]!r}')

    # ---- the two conclusions ----
    print()
    print("=== READING ===")
    producers = {r["producer"] for r in rows if r["producer"]}
    if len(producers) == 1:
        print("  * SAME producer across all files -> the engine is NOT the difference.")
        print("    Do not rewrite the render pipeline; compare CONTENT instead.")
    elif len(producers) > 1:
        print("  * producers DIFFER -> engine choice is in play:")
        for p in producers:
            print(f"      {p!r}")

    if len(rows) >= 2:
        mine, ref = rows[0], rows[-1]
        print()
        print(f"  math-font chars: mine={mine['math']}  reference={ref['math']}")
        if ref["math"] > max(mine["math"] * 3, 50):
            print("  * reference has FAR more vector math -> the difference is")
            print("    FORMULA TYPESETTING (stage 4). Re-typeset with KaTeX; do not")
            print("    crop formulas to bitmaps and do not emit flat Unicode.")
        elif mine["math"] > 0 and ref["math"] == 0:
            print("  * MINE has more vector math than the reference - good sign.")
        if ref["pages"] > mine["pages"] * 3:
            print("  * reference covers far more pages - compare a MATCHED range,")
            print("    not the whole document, or the numbers are not comparable.")


if __name__ == "__main__":
    main()
