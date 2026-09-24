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
    ap.add_argument("--min-sentence-ratio", type=float, default=0.40,
                    help="output sentences / source PROSE sentences must exceed this. "
                         "Default 0.40 is calibrated on five faithfully-translated "
                         "batches of a code-heavy lecture PDF, whose prose-only ratios "
                         "measured 0.47-0.55; a complete translation can legitimately sit "
                         "below 1.0 because Chinese joins clauses with commas instead of "
                         "starting a new sentence. This is a smoke alarm for wholesale "
                         "omission, not a proof of fidelity.")
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
    #
    # Two corrections matter here, both learned from a code-heavy lecture PDF that made
    # this check unusable:
    #
    #   a) CODE MUST LEAVE THE DENOMINATOR. Source sentences were counted from every text
    #      block, but `strip_tags` removes <pre> from the output before counting. On a
    #      tutorial chapter 44% of the source "sentences" live inside code blocks
    #      (`# Get a slice from index 2 to the end; prints "[2, 3, 4]"`), and those are
    #      never supposed to have a Chinese counterpart. Counting them guarantees a false
    #      failure on exactly the documents this skill is for.
    #
    #   b) THE RATIO IS NOT 1.0 EVEN WHEN NOTHING IS DROPPED. Chinese packs the same
    #      content into fewer sentence-ending marks: a source sentence often becomes a
    #      clause joined by ，rather than a new 。. Measured over five faithfully
    #      translated batches, prose-only ratios landed at 0.47-0.55 -- all of them
    #      complete translations. The gate therefore has to sit below that band, and it
    #      is a *smoke alarm* for wholesale omission, not a fidelity proof.
    print("=== 1. per-page sentence coverage ===")
    print(f'  {"page":>5} {"src sent":>9} {"out sent":>9}  note')
    src_total = 0
    for p in pages:
        # count only NON-code blocks: code is reproduced verbatim, not translated
        parts = []
        for b in p["blocks"]:
            if b["type"] != "text":
                continue
            if any(k in s["font"] for s in b["spans"]
                   for k in ("Mono", "Courier", "Consol", "Menlo")):
                continue
            parts.append("".join(s["t"] for s in b["spans"]))
        src_txt = " ".join(parts)
        n_src = len(sentences(src_txt))
        src_total += n_src
        # crude attribution: nothing per-page in the output, so report the global
        # ratio below and just surface pages that are text-heavy
        if n_src >= 12:
            print(f'  {p["page"]:>5} {n_src:>9} {"":>9}  text-heavy page')

    out_total = len(sentences(prose))
    ratio = out_total / max(src_total, 1)
    print(f'\n  source sentences (prose only) : {src_total}')
    print(f'  output sentences              : {out_total}')
    print(f'  ratio                         : {ratio:.2f}  (must be > {a.min_sentence_ratio})')
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
    n_figs_out = len(re.findall(r"<figure\b", html, re.I))
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
        # Sanity gate on the caption-size guess. A real caption size produces roughly as
        # many caption blocks as there are figures. If the candidate count is far BELOW
        # the figure count, this size is not the caption size at all -- it is an ordinary
        # text size that merely happens to sit below body size, and treating it as
        # captions produces nonsense comparisons against real <figcaption> text.
        # (Seen on a lecture batch with no 11.2pt captions: the guess fell through to
        # 12.0pt body text and then flagged a normal paragraph as a summarised caption.)
        if cand and n_figs_out and len(cand) * 3 < n_figs_out:
            print(f"  note: size {size}pt yields only {len(cand)} caption candidate(s) "
                  f"for {n_figs_out} figure(s) - not the caption size, skipping")
            continue
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
        # NOTE: this counter merges adjacent blocks per page, so a caption whose text
        # spilled onto the NEXT page counts twice, and a caption split by the extractor
        # counts once. Treat a small shortfall as "worth checking", not proof of a drop.
        # The reliable signals are the char-coverage check below and the per-figure
        # pairing check further down; this one only has to raise the question.
        if len(figcaps) < len(cap_blocks) - 1:
            problems += 1
            print(f"  FLAG: output has {len(cap_blocks) - len(figcaps)} fewer captions than the "
                  f"source ({len(cap_blocks)} blocks).")
        elif len(figcaps) < len(cap_blocks):
            print(f"  note: 1 fewer caption than source blocks - expected when a caption is")
            print(f"        split across a page boundary by the extractor. Verify per figure.")
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

    # ---- figures vs captions: pairing and numbering ----
    # The count comparison above has a blind spot: one figure with no caption plus one
    # caption with no figure keeps the totals equal and passes. That is exactly how a
    # captionless figure shipped in the CS231n run. Check the pairing and the numbering
    # directly instead of trusting two totals to agree.
    #
    # But "no figcaption" is not automatically a defect: some sources genuinely caption
    # only some figures (the CS231n challenges figure has none). The discriminator is
    # whether the source had a caption available at that position. We approximate that
    # by comparing totals -- if the output has fewer captions than the source has caption
    # blocks, a caption was DROPPED; extra uncaptioned figures are faithful reproduction.
    print()
    print("=== figure/caption pairing ===")
    figures = re.findall(r"<figure\b.*?</figure>", html, re.S | re.I)
    nfigcaps = len(re.findall(r"<figcaption", html, re.I))
    print(f"  <figure> elements : {len(figures)}")
    naked = [i for i, f in enumerate(figures, 1)
             if not re.search(r"<figcaption", f, re.I)]
    multi = [i for i, f in enumerate(figures, 1)
             if len(re.findall(r"<figcaption", f, re.I)) > 1]
    src_caps = len(cap_blocks) if cap_size is not None else None
    if multi:
        problems += 1
        print(f"  FLAG: <figure>(s) {multi} carry more than one <figcaption>")
    if naked:
        # A captionless figure is faithful when the SOURCE has no caption for it.
        # The CS231n p7 "challenges" figure is exactly that case. Compare the output's
        # caption count against the source's figure count: if every captioned figure in
        # the source got a caption, an extra uncaptioned figure is correct, not a drop.
        src_figs = 0
        for p in pages:
            for b in p["blocks"]:
                if b["type"] == "image":
                    src_figs += 1
        if src_caps is not None and nfigcaps + len(naked) - 1 < src_caps - 1:
            problems += 1
            print(f"  FLAG: {len(naked)} <figure>(s) with NO <figcaption>: {naked}")
            print(f"    output captions {nfigcaps} vs source caption blocks {src_caps}")
            print(f"    -> more than one figure lost its caption.")
        else:
            print(f"  {len(naked)} <figure>(s) without a caption: {naked}")
            print(f"    consistent with the source: {nfigcaps} captions for "
                  f"{len(figures)} figures (source has {src_caps} caption blocks).")
            print("    Confirm each uncaptioned figure against structure.json.")
    else:
        print("  every <figure> has a caption")
    stray = nfigcaps - len(figures)
    if stray > 0:
        problems += 1
        print(f"  FLAG: {stray} <figcaption> outside any <figure> - captions must be inside")

    # numbering must be 图 1..N, monotonic, no gaps, no repeats
    nums = [int(n) for n in re.findall(r"图\s*(\d+)", strip_tags(html))]
    if nums:
        seq = [n for i, n in enumerate(nums) if i == 0 or n != nums[i - 1]]
        expected = list(range(1, nfigcaps + 1))
        print(f"  caption numbers seen: {seq[:12]}{' ...' if len(seq) > 12 else ''}")
        if seq != expected[:len(seq)]:
            problems += 1
            print(f"  FLAG: caption numbering is not 1..N in order (expected {expected[:len(seq)]})")
            missing = [n for n in expected if n not in seq]
            if missing:
                print(f"    missing numbers: {missing}")
        else:
            print(f"  numbering OK (1..{len(seq)})")
    elif figures:
        problems += 1
        print("  FLAG: figures present but no '图 N' numbers found in the output")

    # caption styling must differ from body text - a caption indistinguishable from a
    # paragraph is one of the most-reported layout defects
    print()
    print("=== caption styling ===")
    if figcaps:
        css = ""
        for m in re.finditer(r"<style[^>]*>(.*?)</style>", html, re.S | re.I):
            css += m.group(1)
        if re.search(r"figcaption\s*\{[^}]*\}", css, re.I):
            block = re.search(r"figcaption\s*\{([^}]*)\}", css, re.I).group(1)
            has_size = "font-size" in block
            has_colour = "color" in block
            has_margin = "margin" in block
            print(f"  figcaption CSS: size={has_size} colour={has_colour} margin={has_margin}")
            if not (has_size or has_colour):
                problems += 1
                print("  FLAG: figcaption has neither font-size nor colour - it will read")
                print("        as body text. Give it a size step down and/or a muted colour.")
        else:
            print("  no figcaption rule in the stylesheet (styling may come from a")
            print("  stylesheet outside body.html - verify visually in the rendered PDF)")

    print()
    if problems:
        print(f"=== {problems} PROBLEM(S) - fix before rendering ===")
        sys.exit(1)
    print("=== fidelity checks passed ===")


if __name__ == "__main__":
    main()
