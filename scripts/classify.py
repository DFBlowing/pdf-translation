# -*- coding: utf-8 -*-
"""Stage 3 - classify blocks: which spans are MATH, which blocks are HEADINGS / CODE.

Usage:
    python classify.py <workdir>/structure.json [--body-size 12.8]

The math report is the important half. It groups math spans into formula runs and
prints each run WITH its geometry, so the model can read the formula's structure
off the bounding boxes and re-emit it as KaTeX. A span below a big-operator glyph
is its lower limit; a span above a base's baseline is a superscript; two spans on
one base are two-level scripts.
"""
import sys, json, argparse
from collections import Counter


MATH_FONT_HINTS = ("Type3", "Cambria", "Math", "Symbol", "MSAM", "MSBM", "STIX",
                   "Euclid", "CMSY", "CMR", "CMEX", "LatinModernMath")
BIG_OPS = {"\u2211", "\u220f", "\u222b", "\u222c", "\u222d", "\u2210", "\u222e",
           "\u22c3", "\u22c2", "\u22c0", "\u22c1", "\u221a"}


def is_math_span(s):
    if any(h in s["font"] for h in MATH_FONT_HINTS):
        return True
    # a span consisting mostly of math symbols
    t = s["t"]
    if not t.strip():
        return False
    sym = sum(1 for c in t if c in BIG_OPS or
              (0x2200 <= ord(c) <= 0x22FF) or   # math operators
              (0x2A00 <= ord(c) <= 0x2AFF) or   # supplemental operators
              (0x1D400 <= ord(c) <= 0x1D7FF))   # math alphanumerics
    return sym > 0 and sym >= len(t.strip()) * 0.6


def group_runs(spans, gap=60.0, y_tol=20.0):
    """Group math spans on the same line into formula runs.

    Formula glyphs sit on one baseline but their scripts swing well above and
    below it, so the y tolerance has to be generous, and the x gap has to span
    the whitespace a typesetter puts around operators. Both defaults are tuned
    on a real formula (an L1-distance display equation) - do not tighten them
    without re-checking that the run still comes back as ONE formula.
    """
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: s["bbox"][0])
    runs, cur = [], [spans[0]]
    for s in spans[1:]:
        cur_y = [x["bbox"][1] for x in cur]
        y_ok = min(cur_y) - y_tol <= s["bbox"][1] <= max(cur_y) + y_tol
        x_ok = s["bbox"][0] - max(x["bbox"][2] for x in cur) <= gap
        if y_ok and x_ok:
            cur.append(s)
        else:
            runs.append(cur); cur = [s]
    runs.append(cur)

    out = []
    for r in runs:
        x0 = min(s["bbox"][0] for s in r)
        y0 = min(s["bbox"][1] for s in r)
        x1 = max(s["bbox"][2] for s in r)
        y1 = max(s["bbox"][3] for s in r)
        out.append({"spans": sorted(r, key=lambda s: s["bbox"][0]),
                    "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure")
    ap.add_argument("--body-size", type=float, default=None,
                    help="body font size; inferred as the most common size if omitted")
    a = ap.parse_args()

    pages = json.load(open(a.structure, encoding="utf-8"))

    # ---- infer body size = most common text size ----
    sizes = Counter()
    for p in pages:
        for b in p["blocks"]:
            if b["type"] != "text":
                continue
            for s in b["spans"]:
                sizes[s["size"]] += len(s["t"].strip())
    body = a.body_size or (sizes.most_common(1)[0][0] if sizes else 12.0)
    print(f"inferred body size : {body}pt")
    print(f"size histogram     : {sizes.most_common(8)}")
    print()

    # ---- headings: sizes above body. Collapse near-identical sizes into one level,
    #      otherwise 20.8 / 20.0 / 19.2 come back as three levels when they are one.
    raw_sizes = sorted({s for s in sizes if s > body + 0.4}, reverse=True)
    heading_sizes = []
    for s in raw_sizes:
        if heading_sizes and abs(heading_sizes[-1] - s) <= 1.6:
            continue                      # same visual level
        heading_sizes.append(s)

    print("=== heading level map ===")
    if heading_sizes:
        for lvl, s in enumerate(heading_sizes, 1):
            tag = "H%d" % min(lvl, 6)
            # fold the near-duplicates this level swallowed
            members = [x for x in raw_sizes if abs(x - s) <= 1.6]
            chars = sum(sizes[x] for x in members)
            extra = f"  (merged {members})" if len(members) > 1 else ""
            print(f"  {tag}  {s:6.1f}pt   {chars:6d} chars{extra}")
        print(f"  body  {body:6.1f}pt   {sizes.get(body, 0):6d} chars")
        print(f"\n  -> use these {len(heading_sizes)} levels for h1/h2/h3 in body.html")
    else:
        print("  no sizes above body - headings may be distinguished by BOLD only")
        for f, n in Counter({k: v for k, v in
                             [(s["font"], len(s["t"])) for p in pages
                              for b in p["blocks"] if b["type"] == "text"
                              for s in b["spans"]]}).most_common(6):
            if "Bold" in f:
                print(f'    bold font: {f}  ({n} chars)')
    print()

    # ---- math ----
    print("=== MATH: formula runs (read structure off the geometry) ===")
    total_math = 0
    for p in pages:
        runs = []
        for b in p["blocks"]:
            if b["type"] != "text":
                continue
            ms = [s for s in b["spans"] if is_math_span(s)]
            runs.extend(group_runs(ms))
        if not runs:
            continue
        for r in runs:
            total_math += len(r["spans"])
            print(f"\n  --- p{p['page']}  bbox={r['bbox']}  ({len(r['spans'])} spans) ---")
            base_y = Counter(round(s["bbox"][1], 0) for s in r["spans"]).most_common(1)[0][0]
            for s in r["spans"]:
                y = s["bbox"][1]
                role = ""
                if any(c in s["t"] for c in BIG_OPS):
                    role = "BIG-OP(its lower limit sits below)"
                elif y > base_y + 6:
                    role = "BELOW baseline -> subscript / lower limit"
                elif y < base_y - 4:
                    role = "ABOVE baseline -> superscript / upper limit"
                print(f'      {s["font"][:24]:24} sz={s["size"]:5.1f} '
                      f'x={s["bbox"][0]:6.1f} y={y:6.1f}  {s["t"]!r}  {role}')

    print()
    if total_math == 0:
        print("  NO math detected. Either the PDF has no formulas, or they are flat")
        print("  Unicode text (no math font). Check for U+2211-sum / U+222B-integral")
        print("  in the body text and treat those runs as formulas by hand.")
    else:
        print(f"  {total_math} math spans total.")
        print("  Re-emit each run as KaTeX ($...$ inline, $$...$$ display).")

    # ---- code ----
    print()
    print("=== CODE: monospace blocks ===")
    for p in pages:
        for b in p["blocks"]:
            if b["type"] != "text":
                continue
            f = Counter(s["font"] for s in b["spans"]).most_common(1)[0][0]
            if any(k in f.lower() for k in ("mono", "consol", "courier", "menlo")):
                txt = "".join(s["t"] for s in b["spans"])[:70]
                print(f'  p{p["page"]} {f} :: {txt!r}')


if __name__ == "__main__":
    main()
