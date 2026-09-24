# -*- coding: utf-8 -*-
"""Extract every link annotation from the source PDF together with its anchor text.

Without this the translation silently loses the navigation: a course-notes PDF can carry
hundreds of URI annotations and a first delivery may emit the *text* of a Further Reading
item with no `<a href>` around it. Write the inventory out, hand it to whoever writes each
fragment of the body, and restore afterwards with `restore-links.py`.

Paper titles, URLs and identifiers survive translation verbatim; translated prose does not.
The `anchor` field is the text found inside the link rectangle, which for a block-level
annotation can be a whole printed line -- see the caveats in SKILL.md.

Usage:
    python extract-source-links.py <input.pdf> [out.json]

    out.json defaults to <input-stem>-links.json beside the input.

Exact duplicates are collapsed: one source page can carry the same URI with the same
anchor text twice (an image and its caption link, say). The script prints both the raw
annotation count and the unique one -- quote the UNIQUE count and say which you mean,
because the ledger has to add up.
"""
import json, os, re, sys
import pymupdf

if len(sys.argv) < 2:
    sys.exit(__doc__.strip())
SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(SRC)[0] + "-links.json"

doc = pymupdf.open(SRC)
records = []
for i, page in enumerate(doc):
    words = page.get_text("words")           # x0,y0,x1,y1,word,block,line,wordno
    for lk in page.get_links():
        uri = lk.get("uri")
        if not uri:
            continue
        r = pymupdf.Rect(lk["from"])
        # gather words whose centre falls inside the link rect
        hits = []
        for w in words:
            wr = pymupdf.Rect(w[:4])
            cx, cy = (wr.x0 + wr.x1) / 2, (wr.y0 + wr.y1) / 2
            if r.x0 - 1 <= cx <= r.x1 + 1 and r.y0 - 1 <= cy <= r.y1 + 1:
                hits.append((w[1], w[0], w[4]))
        hits.sort()
        anchor = " ".join(h[2] for h in hits).strip()
        records.append({"page": i + 1, "uri": uri, "anchor": anchor,
                        "rect": [round(v, 1) for v in r]})
doc.close()

# dedupe identical (page, uri, anchor)
seen, uniq = set(), []
for r in records:
    k = (r["page"], r["uri"], r["anchor"])
    if k in seen:
        continue
    seen.add(k)
    uniq.append(r)

json.dump(uniq, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"source link annotations: {len(records)}  (unique {len(uniq)})")
print(f"wrote {OUT}")
print()

# group by page for inspection
from collections import defaultdict
by = defaultdict(list)
for r in uniq:
    by[r["page"]].append(r)
for pg in sorted(by):
    if len(by[pg]) < 2:
        continue
    print(f"--- p{pg} ({len(by[pg])} links) ---")
    for r in by[pg][:6]:
        print(f"    {r['anchor'][:60]!r:<64} -> {r['uri'][:56]}")
