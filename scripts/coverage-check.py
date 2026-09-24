# -*- coding: utf-8 -*-
"""Block-level coverage: does every source content block have a destination?

WHY THIS EXISTS
---------------
A batch translator dropped source pages 121-122 entirely (the whole gradient-descent
code body) and every other signal still looked green: no "末尾字符缺失" notes, valid
HTML, contiguous caption numbering, plausible figure count. It was found by hand.

That is the skill's own headline failure mode -- "the output reads well, and only
someone holding the original can tell that whole sentences were dropped". The other
gates measure properties of the OUTPUT (disclaimer count, tag balance, numbering);
none of them measures the source-to-output RELATIONSHIP.

WHY IT DOES NOT MATCH TEXT
--------------------------
The first version tried to find English word n-grams from the source inside the
output. That is impossible by construction: the output is Chinese. It reported 4-26%
coverage on five batches that were all complete, i.e. it was measuring the language
change, not any omission.

The workable signal is COUNT AND ORDER, not identity:
  * how many content-bearing source blocks exist per page, by kind (prose / code /
    formula / caption), and
  * how many output elements of each kind exist, in total and per section.
A page that contributed 8 code blocks and 3 prose blocks but produced zero of either
is a drop, and that shows up without needing to read Chinese.

Run it per batch AND on the assembled document. Treat a large negative residual
(source blocks materially exceeding output elements) as the alarm.

Usage: python coverage-check.py <batchdir|full> [--tolerance 0.25]
"""
import os, re, sys, json, argparse
from collections import Counter

MONO = ("Mono", "Courier", "Consol", "Menlo")
RUNNING_HEADER_GREY = 0xABABAB


def classify_source(pages):
    """Count source content RUNS per kind, excluding non-content.

    The unit is a RUN, not a block. The extractor emits one block per visual line, so a
    20-line code listing arrives as ~20 blocks; counting those against `<pre>` elements
    compares lines to listings and always reports a huge shortfall. A run is a maximal
    sequence of consecutive blocks of the same kind (mono / caption / prose), which is
    what actually corresponds to one output element.
    """
    tot = Counter()
    per_page = {}
    for p in pages:
        kinds = []
        for b in p["blocks"]:
            if b["type"] != "text":
                continue
            spans = b["spans"]
            if not spans:
                continue
            txt = "".join(s["t"] for s in spans)
            if all(s.get("color") == RUNNING_HEADER_GREY for s in spans):
                continue                                   # running header
            if re.fullmatch(r"[\d\s.,:;/\-–—()\[\]]*", txt):
                continue                                   # page number / punctuation
            is_mono = any(k in s["font"] for s in spans for k in MONO)
            # Distinguish a CODE LISTING from INLINE code inside a sentence. A prose
            # sentence that mentions `W = 0.001* np.random.randn(D,H)` carries a mono
            # span, but it is still prose. Counting it as a code run inflated one batch's
            # "code runs" from 9 to 22 and produced a phantom dropped-code alarm.
            mono_chars = sum(len(s["t"]) for s in spans
                             if any(k in s["font"] for k in MONO))
            is_listing = is_mono and mono_chars / max(len(txt), 1) > 0.6
            is_cap = all(round(s["size"], 1) == 11.2 for s in spans)
            nwords = len(re.findall(r"[A-Za-z_]{2,}", txt))
            if is_cap:
                kinds.append("caption")
            elif is_listing:
                kinds.append("code")
            elif nwords < 3:
                kinds.append("frag")
            else:
                kinds.append("prose")

        # collapse consecutive equal kinds into runs
        c = Counter()
        prev = None
        for k in kinds:
            if k in ("caption", "code", "prose") and k != prev:
                c[k] += 1
            prev = k
        if sum(c.values()):
            per_page[p["page"]] = c
            tot.update(c)
    return tot, per_page


def count_output(html):
    o = Counter()
    o["prose"] = len(re.findall(r"<p\b", html, re.I)) + len(re.findall(r"<li\b", html, re.I))
    o["code"] = len(re.findall(r"<pre\b", html, re.I))
    o["formula"] = len(re.findall(r'<div class="formula"', html, re.I))
    o["figure"] = len(re.findall(r"<figure\b", html, re.I))
    o["figcaption"] = len(re.findall(r"<figcaption", html, re.I))
    o["heading"] = len(re.findall(r"<h[1-4]\b", html, re.I))
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--tolerance", type=float, default=0.25,
                    help="allowed shortfall as a fraction of source blocks")
    a = ap.parse_args()

    d = a.target
    sp = os.path.join(d, "structure.json")
    bp = os.path.join(d, "body.html")
    for x in (sp, bp):
        if not os.path.exists(x):
            sys.exit(f"missing {x}")

    pages = json.load(open(sp, encoding="utf-8"))
    html = open(bp, encoding="utf-8").read()
    src, per_page = classify_source(pages)
    out = count_output(html)

    print(f"target: {d}")
    print(f"  source pages with content : {len(per_page)}")
    print()
    print(f"  {'kind':<11} {'source':>7} {'output':>7}  note")
    print(f"  {'-'*11} {'-'*7} {'-'*7}  {'-'*40}")

    # prose: Chinese merges sentences, so output <p>+<li> is expected to be SMALLER
    # than source prose blocks (which the extractor splits per visual line).
    print(f"  {'prose':<11} {src['prose']:>7} {out['prose']:>7}  "
          f"output is paragraphs+list-items; source lines are finer-grained")
    print(f"  {'code':<11} {src['code']:>7} {out['code']:>7}  "
          f"{'OK' if out['code'] >= src['code'] * (1 - a.tolerance) else 'SHORT'}")
    print(f"  {'caption':<11} {src['caption']:>7} {out['figcaption']:>7}  "
          f"{'OK' if out['figcaption'] >= src['caption'] * 0.55 else 'SHORT'}")
    print(f"  {'figure(img)':<11} {'-':>7} {out['figure']:>7}  "
          f"cropped figures referenced")
    print(f"  {'heading':<11} {'-':>7} {out['heading']:>7}")
    print()

    print("=== per-page source runs (top 12 by total) ===")
    for pg, c in sorted(per_page.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
        print(f"  p{pg:<5} prose={c['prose']:<4} code={c['code']:<4} caption={c['caption']}")

    print()
    problems = []

    # CODE: a source run is not 1:1 with a <pre> -- a listing interrupted by a prose line,
    # or split across a page break, yields several runs but ONE output block.
    #
    # Calibration measured on five COMPLETE batches of this document: 74%, 82%, 96%, 89%,
    # 78% (mean ~84%). A deliberately damaged copy with half its code listings removed
    # measured 47% and initially SLIPPED PAST a 0.45 floor -- the check was too permissive
    # to catch the very defect it exists for. The floor is therefore set at 0.65, below
    # the healthy band's minimum (74%) and above the damaged case (47%).
    CODE_FLOOR = 0.65
    if src["code"] >= 8 and out["code"] < src["code"] * CODE_FLOOR:
        problems.append(
            f"code: only {out['code']} <pre> for {src['code']} source code runs "
            f"({out['code']/src['code']*100:.0f}%, floor {CODE_FLOOR*100:.0f}%) "
            f"- a page's code was likely dropped")
    elif src["code"] and out["code"] < src["code"]:
        print(f"  note: {out['code']} <pre> for {src['code']} source code runs "
              f"({out['code']/src['code']*100:.0f}%); expected, since one <pre> spans "
              f"several source runs")

    if src["caption"] > 4 and out["figcaption"] == 0:
        problems.append("captions: source has caption text but output has no <figcaption>")

    if not out["prose"] and not out["code"]:
        problems.append("output has no paragraphs and no code blocks at all")

    print()
    if problems:
        print("=== COVERAGE PROBLEMS ===")
        for x in problems:
            print("  - " + x)
        print("\n  A page contributing source blocks but no output is a DROPPED PAGE.")
        print("  Cross-check the pages above against the batch fragment by hand.")
        return 1
    print("=== coverage OK (no block-class shortfall) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
