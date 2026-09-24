# -*- coding: utf-8 -*-
"""Stage 1.5 - detect text the SOURCE PDF lost before it ever reached extraction.

Usage:
    python detect-truncation.py <input.pdf> [--emit-tasks] [--json OUT] [--debug]

Why this exists
---------------
A born-digital PDF printed from HTML with `overflow: hidden` on its <pre> silently
drops every character past the clip. The characters are NOT in the content stream,
so PyMuPDF cannot return them and `extract.py` is not at fault. Without this check
the damage stays invisible until a reader holds the upstream original, and the
model's natural response is to annotate it per site -- which turns a repairable
document into one littered with "text missing in source" notes.

How it detects, and why not the obvious way
-------------------------------------------
The tempting signal is "many lines stop at the same x". Measured on the CS231n
lecture PDF that flagged **5,272** lines against 298 real truncations: right-aligned
page numbers, TOC dot-leaders and short display labels all share an x-coordinate.
Even adding "the last token looks severed" only got it to 2,066 -- TOC entries like
`Understanding and Visualizing Convolutional Neural Networks` end on a plausible
word and land near the same edge.

The reliable signal is **containment**. A code block in these PDFs is a *drawn
filled rectangle* (on the CS231n source: `(53.0, 102.7) -> (544.0, 604.9)`). Inside
that rect the text is laid out to a fixed width and then clipped. So:

    a line is truncated  <=>  it is monospace, it sits inside a code-block rect,
                              its right edge falls short of that rect's right
                              border, AND it ends mid-token

TOC lines and page numbers are not inside a code rect, so they cannot qualify.
That is the discriminator, and it is geometric rather than statistical.

`--debug` prints every code rect and the lines inside, which is what you want when
tuning this for a new document family.
"""
import sys, os, json, re, argparse
from collections import defaultdict

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf missing - pip install pymupdf")

MONO_HINT = ("Mono", "Courier", "Consol", "Menlo", "mono")

# A finished token: prose punctuation, a page number, a dot-leader, a bracket.
FINISHED = re.compile(r"([.!?。！？：:；;)\]）】」』\"'’”]|\.{2,}|\d|-{3,}|\s)$")


def code_rects(page, min_w=120, min_h=40):
    """Filled rectangles that could be code/pre panels.

    Filtered to roughly-text-column width so page backgrounds and full-bleed
    decorations are excluded; a code panel is wide and tall-ish.
    """
    out = []
    for dr in page.get_drawings():
        if dr.get("fill") is None:
            continue
        r = dr["rect"]
        if r.width < min_w or r.height < min_h:
            continue
        # a panel leaf: do not keep a rect that merely contains another candidate
        # (the CS231n source draws each panel twice, once as fill and once as fs)
        if r.width > page.rect.width - 20:
            continue
        out.append(r)
    # drop near-duplicates
    uniq = []
    for r in out:
        if not any(abs(r.x0 - u.x0) < 2 and abs(r.y0 - u.y0) < 2 and
                   abs(r.x1 - u.x1) < 2 and abs(r.y1 - u.y1) < 2 for u in uniq):
            uniq.append(r)
    return uniq


def is_cut(t):
    """Line ends inside a word (severed), not at a token boundary."""
    if FINISHED.search(t):
        return False
    m = re.search(r"[A-Za-z_][A-Za-z0-9_]*$", t)
    return bool(m) and len(m.group(0)) >= 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--emit-tasks", action="store_true")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--slack", type=float, default=8.0,
                    help="how far short of the panel's right border a line may "
                         "end and still count as clipped (pt)")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    clipped, panels_total = [], 0
    per_page_panels = {}

    for pno, page in enumerate(doc):
        panels = code_rects(page)
        per_page_panels[pno + 1] = len(panels)
        panels_total += len(panels)

        rows = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b.get("lines", []):
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                rows.append({
                    "page": pno + 1,
                    "y": round(l["bbox"][1], 1),
                    "x0": round(min(s["bbox"][0] for s in spans), 1),
                    "x1": round(max(s["bbox"][2] for s in spans), 1),
                    "mono": any(h in s["font"] for s in spans for h in MONO_HINT),
                    "text": "".join(s["text"] for s in spans),
                })

        for r in rows:
            if not r["mono"]:
                continue
            for p in panels:
                # line must sit vertically inside the panel and start inside it
                if not (p.y0 - 2 <= r["y"] <= p.y1):
                    continue
                if not (p.x0 - 2 <= r["x0"] <= p.x1):
                    continue
                # ...and stop short of the panel's right border, severed
                gap = p.x1 - r["x1"]
                if 0 <= gap <= a.slack and is_cut(r["text"].rstrip()):
                    r["panel_right"] = round(p.x1, 1)
                    r["gap"] = round(gap, 1)
                    clipped.append(r)
                    break

        if a.debug:
            print(f"--- page {pno+1}: {len(panels)} panel(s) ---")
            for p in panels:
                print(f"    panel ({p.x0:.1f},{p.y0:.1f})-({p.x1:.1f},{p.y1:.1f})")
    doc.close()

    per_page = defaultdict(list)
    for r in clipped:
        per_page[r["page"]].append(r)

    print(f"file        : {a.pdf}")
    print(f"code panels : {panels_total} drawn panel(s)")
    print()
    print("=" * 68)
    if not clipped:
        print("RESULT: no truncation detected. Source text layer looks intact.")
        print("=" * 68)
        return 0

    print(f"RESULT: {len(clipped)} truncated lines across {len(per_page)} pages")
    print("=" * 68)
    print()
    for p in sorted(per_page):
        print(f"--- page {p}  ({len(per_page[p])} line(s), panel right "
              f"{per_page[p][0]['panel_right']}) ---")
        for r in per_page[p]:
            print(f"   gap={r['gap']:5.1f}  {r['text'][-72:]!r}")
        print()

    print("NEXT: recover these. Preference order --")
    print("  1. fetch the upstream original (public lecture page / arXiv), restore verbatim")
    print("  2. reconstruct from code grammar when the missing span is unambiguous")
    print("  3. only then keep the fragment and mark it ONCE (footnote), not per line")
    print("  Never emit a per-site 'text missing in source' note for each occurrence.")

    if a.json_out:
        json.dump({"panels": per_page_panels, "clipped": clipped},
                  open(a.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nwrote {a.json_out}")

    if a.emit_tasks:
        out = os.path.splitext(a.pdf)[0] + ".truncation-tasks.md"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("# Truncated-source recovery checklist\n\n")
            fh.write(f"Source: `{a.pdf}`\n\n")
            fh.write(f"**{len(clipped)} lines across {len(per_page)} pages.** "
                     "Restore each from the upstream original; tick as you go.\n\n")
            for p in sorted(per_page):
                fh.write(f"## page {p}\n\n")
                for r in per_page[p]:
                    fh.write(f"- [ ] `{r['text']}`\n")
                fh.write("\n")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
