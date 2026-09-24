# -*- coding: utf-8 -*-
"""Add the internal TOC jump links to the rendered PDF.

WHY THIS EXISTS
---------------
Chrome's headless `--print-to-pdf` exports EXTERNAL uri annotations (a link to
http://... survives) but it does NOT emit same-document anchors: `<a href="#id">` is
rendered as plain text with no link at all. The delivered PDF therefore had 66 external
links and ZERO internal ones, so the chapter TOCs the user asked to be navigable were
still dead.

So the GOTO annotations are added here, after rendering:

  * for each TOC group (from jump-map.json), find the page holding the most of that
    group's labels -- that is the TOC's own page. Searching a label globally is not
    enough: "小结" occurs as a heading in earlier chapters too.
  * locate each label's rectangle on that page
  * locate the target heading's page (prefer a hit rendered at heading size)
  * add a LINK_GOTO from the label rect to the target page

Usage: python add-internal-links.py <pdf>
"""
import json, os, sys
import pymupdf

R = os.path.dirname(os.path.abspath(__file__))
PDF = sys.argv[1] if len(sys.argv) > 1 else r"D:\Download\Google\cs231n斯坦福CNN_中文翻译.pdf"
JM = os.path.join(R, "jump-map.json")

if not os.path.exists(JM):
    sys.exit(f"missing {JM} - run resolve-jumps.py first")
groups = json.load(open(JM, encoding="utf-8"))

d = pymupdf.open(PDF)

# Idempotent: drop any internal GOTO links a previous run added, so re-running cannot
# stack duplicates or leave a stale (wrong) target behind. External URI links come from
# Chrome and are left alone.
stale = 0
for page in d:
    for lk in list(page.get_links()):
        if lk.get("kind") == pymupdf.LINK_GOTO:
            page.delete_link(lk)
            stale += 1
if stale:
    print(f"removed {stale} pre-existing internal link(s) before re-adding")

# body font size, used to tell a heading hit from a prose mention
sizes = {}
for p in d:
    for b in p.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if len(s["text"].strip()) > 12:
                    sizes[round(s["size"], 1)] = sizes.get(round(s["size"], 1), 0) + len(s["text"])
body_size = max(sizes, key=sizes.get) if sizes else 10.5
HEAD_MIN = body_size + 0.9          # headings are clearly above body
print(f"body size ~{body_size}pt   heading threshold >= {HEAD_MIN:.1f}pt")


def hits(text):
    """All (page_index, rect, size) for a string, including single-line search."""
    out = []
    for i, page in enumerate(d):
        for r in page.search_for(text):
            # what size is the text inside this rect?
            sz = 0.0
            for b in page.get_text("dict", clip=r)["blocks"]:
                if b.get("type") != 0:
                    continue
                for l in b["lines"]:
                    for s in l["spans"]:
                        sz = max(sz, s["size"])
            out.append((i, r, sz))
    return out


added = 0
missed = []

# Frequency of every label across the document. A label that occurs dozens of times
# ("小结", "延伸阅读") says nothing about where the TOC is; a label that occurs once
# ("线性分类导论") pins the page. Weighting by inverse frequency is what stops the TOC page
# from being mis-identified as some later chapter that merely repeats the same words.
label_freq = {}
for items in groups.values():
    for it in items:
        lab = it["label"]
        if lab not in label_freq:
            label_freq[lab] = len(hits(lab))

for gi, items in sorted(groups.items(), key=lambda kv: int(kv[0])):
    labels = [it["label"] for it in items]

    # --- locate the TOC's own page by inverse-frequency-weighted score -----------
    page_score = {}
    for lab in labels:
        w = 1.0 / max(label_freq.get(lab, 1), 1)
        for i, r, sz in hits(lab):
            page_score[i] = page_score.get(i, 0.0) + w
    if not page_score:
        missed.append((gi, labels, "no label found anywhere"))
        continue
    toc_page = max(page_score, key=page_score.get)
    toc_set = {toc_page}
    # Bounding box of the whole TOC list on its page. Target hits inside this box are TOC
    # ENTRIES, not the sections they name -- without this, 小结 matched the "小结" inside
    # the longer entry "小结：在实践中应用 kNN" and linked to its own page.
    lab_rects = []
    for it in items:
        for hh in hits(it["label"]):
            if hh[0] == toc_page:
                lab_rects.append(hh[1])
    if lab_rects:
        toc_box = lab_rects[0]
        for r in lab_rects[1:]:
            toc_box |= r
        toc_box = pymupdf.Rect(toc_box.x0 - 4, toc_box.y0 - 4,
                               toc_box.x1 + 4, toc_box.y1 + 4)
    else:
        toc_box = None
    print(f"\n--- TOC group {gi}: {len(labels)} entries, TOC page p{toc_page + 1} "
          f"(score {page_score[toc_page]:.2f}) ---")

    for it in items:
        lab, target = it["label"], it["target"]
        lab_hit = next((h for h in hits(lab) if h[0] in toc_set), None)
        if lab_hit is None:
            missed.append((gi, lab, "label rect not found on TOC page"))
            continue
        if not target:
            missed.append((gi, lab, "no target heading text"))
            continue

        # Target: the heading must come at or AFTER the TOC entry, and the EARLIEST such
        # hit wins; size only breaks ties.
        #
        # Two traps, both hit in practice:
        #   * preferring heading size first skipped `h3.runin` sections (10.8pt) and
        #     matched a later chapter's identically-named heading -- it sent 动机 48 pages
        #     forward;
        #   * searching the target text without excluding the TOC's own line matched the
        #     TOC ENTRY itself whenever label == target (最近邻分类器 -> itself), which
        #     after the fix above made half the entries point at their own page.
        # So a candidate must be strictly later in reading order than the label.
        def after_label(hh):
            if hh[0] > lab_hit[0]:
                return True
            if hh[0] < lab_hit[0]:
                return False
            # same page: must be below the TOC block, not inside it
            if toc_box is not None and toc_box.intersects(hh[1]):
                return False
            return hh[1].y0 > lab_hit[1].y1 + 2

        th = hits(target)
        pool = [h for h in th if after_label(h)] or th
        tpage = min(h[0] for h in pool)
        same_page = [h for h in pool if h[0] == tpage]
        head_hits = [h for h in same_page if h[2] >= HEAD_MIN]
        chosen = (head_hits or same_page)[0]
        tpage, trect, tsize = chosen
        # h3.runin renders at 10.8pt, just under the heading threshold; accept it when it
        # is at least a size step above body
        matched_heading = bool(head_hits) or tsize > body_size

        link = {
            "kind": pymupdf.LINK_GOTO,
            "from": lab_hit[1],
            "page": tpage,
            "to": pymupdf.Point(0, 0),
            "zoom": 0,
        }
        d[lab_hit[0]].insert_link(link)
        added += 1
        flag = "" if matched_heading else "  <- matched prose, verify"
        print(f"    {lab[:22]:<24} -> p{tpage + 1} (target {target[:24]!r}, "
              f"size {tsize:.1f}){flag}")

print()
print(f"internal GOTO links added: {added}")
if missed:
    print(f"NOT LINKED ({len(missed)}):")
    for gi, what, why in missed:
        print(f"    group {gi}: {what!r} - {why}")

tmp = PDF + ".tmp"
d.save(tmp, garbage=3, deflate=True)
d.close()
os.replace(tmp, PDF)
print(f"wrote {PDF}")
