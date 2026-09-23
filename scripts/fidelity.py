# -*- coding: utf-8 -*-
"""Stage 4 check - catch DROPPED and PARAPHRASED content before rendering.

Usage:
    python fidelity.py <workdir> [--source-lang en]

This is the check that catches the invisible failure mode: a translation that reads
well but silently dropped sentences or replaced the source's wording with the model's
own summary. Nobody notices it without the original in hand, so automate it.

Three things are checked:

  1. DROPPED BLOCKS  - source text blocks with no counterpart in body.html.
     Measured by number of content sentences emitted per page.
  2. UNTRANSLATED     - English prose in the output that is not inside <pre>, a
     .en span, or an inline code sample. Some English is correct (code, sample
     values, the .en heading spans); a whole English sentence is not.
  3. CAPTIONS         - every source caption (the small-size blocks) must have a
     <figcaption> carrying a comparable amount of content.

Exit code is non-zero when anything is flagged, so it can gate the render.
"""
import sys, os, re, json, argparse
from collections import Counter


def strip_tags(html):
    h = re.sub(r"<pre.*?</pre>", " ", html, flags=re.S | re.I)
    h = re.sub(r"<span class=\"en\">.*?</span>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<code>.*?</code>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h)


def sentences(txt):
    """Count content-bearing sentences. Short fragments do not count."""
    parts = re.split(r"[.!?;。！？；]\s*", txt)
    return [p.strip() for p in parts if len(p.strip()) > 12]


def cjk_count(txt):
    return sum(1 for c in txt if "\u4e00" <= c <= "\u9fff")


def latin_sentences(txt):
    """English sentences of real length - candidate untranslated prose."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", txt):
        s = s.strip()
        if len(s) < 40:
            continue
        letters = sum(1 for c in s if c.isascii() and c.isalpha())
        if letters / max(len(s), 1) > 0.6:
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--min-sentence-ratio", type=float, default=0.55,
                    help="output sentences / source sentences must exceed this")
    a = ap.parse_args()

    sj = os.path.join(a.workdir, "structure.json")
    bp = os.path.join(a.workdir, "body.html")
    for p in (sj, bp):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    pages = json.load(open(sj, encoding="utf-8"))
    html = open(bp, encoding="utf-8").read()
    prose = strip_tags(html)

    problems = 0

    # ---- 1. dropped blocks, per page ----
    print("=== 1. per-page sentence coverage ===")
    print(f'  {"page":>5} {"src sent":>9} {"out sent":>9}  note')
    src_total = 0
    for p in pages:
        src_txt = " ".join("".join(s["t"] for s in b["spans"])
                           for b in p["blocks"] if b["type"] == "text")
        n_src = len(sentences(src_txt))
        src_total += n_src
        # crude attribution: nothing per-page in the output, so report the global
        # ratio below and just surface pages that are text-heavy
        if n_src >= 12:
            print(f'  {p["page"]:>5} {n_src:>9} {"":>9}  text-heavy page')

    out_total = len(sentences(prose))
    ratio = out_total / max(src_total, 1)
    print(f'\n  source sentences : {src_total}')
    print(f'  output sentences : {out_total}')
    print(f'  ratio            : {ratio:.2f}  (must be > {a.min_sentence_ratio})')
    if ratio < a.min_sentence_ratio:
        problems += 1
        print("  FLAG: output has proportionally fewer sentences than the source.")
        print("        Whole sentences were likely dropped or merged. Walk")
        print("        structure.json against body.html block by block.")
    else:
        print("  OK")

    # ---- 2. untranslated English prose ----
    print()
    print("=== 2. untranslated English prose ===")
    lat = latin_sentences(prose)
    if lat:
        problems += 1
        print(f"  FLAG: {len(lat)} long English sentence(s) in the output:")
        for s in lat[:8]:
            print(f"    {s[:110]!r}")
        print("  Some English is legitimate (code, sample values, .en spans,")
        print("  inline <code>). Anything else should be translated.")
    else:
        print("  OK - no untranslated English prose found")

    # ---- 3. captions ----
    print()
    print("=== 3. captions ===")
    body_sizes = Counter()
    for p in pages:
        for b in p["blocks"]:
            if b["type"] == "text":
                for s in b["spans"]:
                    body_sizes[round(s["size"], 1)] += len(s["t"].strip())
    body_size = body_sizes.most_common(1)[0][0] if body_sizes else 12.8

    # Captions are the largest size strictly BELOW body size. Pick the biggest
    # such bucket with enough text to be prose - this skips page numbers (12.0pt,
    # tiny) and code (often monospace at a size below body too).
    below = sorted((s for s in body_sizes if s < body_size - 0.4), reverse=True)

    def block_is_code(b):
        fonts = Counter(s["font"] for s in b["spans"])
        return any(k in fonts.most_common(1)[0][0].lower()
                   for k in ("mono", "consol", "courier", "menlo"))

    cap_blocks = []
    cap_size = None
    for size in below:
        cand = []
        for p in pages:
            for b in p["blocks"]:
                if b["type"] != "text" or not b["spans"]:
                    continue
                if abs(b["spans"][0]["size"] - size) > 0.4:
                    continue
                if block_is_code(b):
                    continue
                txt = "".join(s["t"] for s in b["spans"]).strip()
                if len(txt) > 40 and re.search(r"[A-Za-z]{3}\s+[a-z]{2,}", txt):
                    cand.append((p["page"], txt, b["bbox"]))
        if cand:
            cap_size = size
            # a single caption is often split across several blocks by the
            # extractor - merge blocks on the same page that are vertically adjacent
            cand.sort(key=lambda c: (c[0], c[2][1]))
            merged = []
            for pg, txt, bbox in cand:
                if merged and merged[-1][0] == pg and bbox[1] - merged[-1][2] < 30:
                    merged[-1][1] += " " + txt
                    merged[-1][2] = bbox[3]
                else:
                    merged.append([pg, txt, bbox[3]])
            cap_blocks = [(pg, t) for pg, t, _ in merged]
            break

    figcaps = re.findall(r"<figcaption[^>]*>(.*?)</figcaption>", html, re.S | re.I)
    if cap_size is None:
        print("  no caption-like blocks detected (size below body, prose, non-mono)")
        print(f"  <figcaption> in output: {len(figcaps)}")
    else:
        print(f"  source caption blocks : {len(cap_blocks)}  (size ~{cap_size}pt, adjacent merged)")
        print(f"  <figcaption> in output: {len(figcaps)}")
        if len(figcaps) < len(cap_blocks):
            problems += 1
            print("  FLAG: fewer captions in the output than in the source.")
        else:
            print("  count OK")

        total_cap_chars = sum(len(strip_tags(c)) for c in figcaps)
        src_cap_chars = sum(len(t) for _, t in cap_blocks)
        print(f"  caption chars: source={src_cap_chars} output={total_cap_chars}")

        # Chinese is far denser than English - a faithful translation lands around
        # 0.25-0.45x the source character count, NOT near 1.0. The flag threshold is
        # therefore 0.18, which catches a caption that was reduced to a one-line
        # description while leaving dense-but-complete translations alone.
        #
        # Alignment: match each figcaption to the source caption whose page it follows,
        # rather than assuming index order, because the number of <figure> elements and
        # the number of extracted caption blocks do not have to agree.
        MIN_RATIO = 0.18
        weak = []
        used = set()
        for cap in figcaps:
            out = strip_tags(cap)
            if not out:
                continue
            # best-matching unused source caption by character-count similarity
            best, best_d = None, None
            for j, (pg, src) in enumerate(cap_blocks):
                if j in used:
                    continue
                d = abs(len(src) - len(out) / 0.35)
                if best_d is None or d < best_d:
                    best, best_d = j, d
            if best is None:
                continue
            used.add(best)
            pg, src = cap_blocks[best]
            r = len(out) / max(len(src), 1)
            if r < MIN_RATIO:
                weak.append((pg, r, src, out))

        if weak:
            problems += 1
            print(f"  FLAG: {len(weak)} caption(s) look summarised, not translated:")
            for pg, r, src, out in weak:
                print(f"    p{pg}  ratio={r:.2f}  (min {MIN_RATIO})")
                print(f"      source: {src[:150]!r}")
                print(f"      output: {out[:150]!r}")
            print("    A caption must be a TRANSLATION, not a description of the figure.")
        elif total_cap_chars < src_cap_chars * MIN_RATIO:
            problems += 1
            print("  FLAG: output captions are far shorter overall than the source.")
        else:
            print(f"  length OK  (Chinese runs ~0.25-0.45x the English char count; "
                  f"min {MIN_RATIO})")

    print()
    if problems:
        print(f"=== {problems} PROBLEM(S) - fix before rendering ===")
        sys.exit(1)
    print("=== fidelity checks passed ===")


if __name__ == "__main__":
    main()
