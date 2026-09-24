# -*- coding: utf-8 -*-
"""Stage 2 - extract text blocks (with bbox/font/size) and crop figures at 300 dpi.

Usage:
    python extract.py <input.pdf> <workdir> [--pages 1-10] [--dpi 300]

Writes:
    <workdir>/structure.json   all blocks, in reading order, with geometry
    <workdir>/figs/*.png       figure regions, merged and cropped

ALWAYS start with a 10-page range. Rendering a sample before committing to the
whole document is the discipline this pipeline is built around.
"""
import sys, os, json, argparse

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


def crop_figures(page, figs_dir, pno, dpi):
    """Merge image bboxes that overlap or sit close together, then crop each region.

    A single figure is often split across many tiny image tiles; the merge pass
    reassembles them. Degenerate regions are dropped.
    """
    boxes = [pymupdf.Rect(b["bbox"])
             for b in page.get_text("dict")["blocks"] if b["type"] == 1]
    if not boxes:
        return []

    # iteratively merge boxes that overlap in x and are within 14pt in y
    boxes.sort(key=lambda r: (r.y0, r.x0))
    changed = True
    while changed:
        changed = False
        out = []
        for r in boxes:
            hit = None
            for m in out:
                x_ok = not (r.x1 < m.x0 - 2 or r.x0 > m.x1 + 2)
                y_ok = not (r.y1 < m.y0 - 14 or r.y0 > m.y1 + 14)
                if x_ok and y_ok:
                    hit = m
                    break
            if hit is None:
                out.append(pymupdf.Rect(r))
            else:
                hit |= r
                changed = True
        boxes = out

    saved = []
    for i, u in enumerate(sorted(boxes, key=lambda r: r.y0), 1):
        u = u & page.rect
        if u.is_empty or u.width < 12 or u.height < 12:
            continue
        pix = page.get_pixmap(dpi=dpi, clip=u)
        if pix.width < 8 or pix.height < 8:
            continue
        name = f"fig_p{pno}_{i}.png"
        pix.save(os.path.join(figs_dir, name))
        saved.append({"name": name, "rect": [round(v, 1) for v in u],
                      "px": [pix.width, pix.height], "dpi": dpi})
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("workdir")
    ap.add_argument("--pages", default=None, help="e.g. 1-10  (STRONGLY recommended)")
    ap.add_argument("--dpi", type=int, default=300)
    a = ap.parse_args()

    figs_dir = os.path.join(a.workdir, "figs")
    os.makedirs(figs_dir, exist_ok=True)

    doc = pymupdf.open(a.pdf)
    first, last = parse_range(a.pages, doc.page_count)
    if a.pages is None:
        print("WARNING: no --pages given, extracting the WHOLE document.")
        print("         The sample-first rule says start with 10 pages.\n")

    pages, figures = [], {}
    for pno in range(first, last):
        page = doc[pno]
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] == 0:
                spans = [{"t": s["text"], "size": round(s["size"], 1),
                          "font": s["font"],
                          "color": s.get("color"),
                          "bbox": [round(v, 1) for v in s["bbox"]]}
                         for l in b.get("lines", []) for s in l["spans"]
                         if s["text"].strip()]
                if spans:
                    blocks.append({"type": "text",
                                   "bbox": [round(v, 1) for v in b["bbox"]],
                                   "spans": spans})
            else:
                blocks.append({"type": "image",
                               "bbox": [round(v, 1) for v in b["bbox"]]})
        pages.append({"page": pno + 1, "w": page.rect.width,
                      "h": page.rect.height, "blocks": blocks})
        f = crop_figures(page, figs_dir, pno + 1, a.dpi)
        if f:
            figures[pno + 1] = f

    sj = os.path.join(a.workdir, "structure.json")
    with open(sj, "w", encoding="utf-8") as fh:
        json.dump(pages, fh, ensure_ascii=False, indent=1)
    fj = os.path.join(a.workdir, "figs.json")
    with open(fj, "w", encoding="utf-8") as fh:
        json.dump(figures, fh, ensure_ascii=False, indent=1)

    nfig = sum(len(v) for v in figures.values())
    print(f"pages      : {len(pages)} ({first+1}-{last})")
    print(f"figures    : {nfig} cropped at {a.dpi} dpi")
    for p, f in sorted(figures.items()):
        names = ", ".join(f'{x["name"]} {x["px"][0]}x{x["px"][1]}' for x in f)
        print(f"  p{p}: {names}")
    print(f"\nwrote      : {sj}")
    print(f"wrote      : {fj}")
    print(f"figures dir: {figs_dir}")
    print("\n  next: python classify.py <%s>" % sj)


if __name__ == "__main__":
    main()
