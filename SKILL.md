---
name: pdf-translation
description: 把英文 PDF 文献（论文、讲义、教材）翻译成排版精美的中文 PDF，保留图片位置、代码块与公式。当用户说「翻译这篇 PDF」「把这份文献翻成中文」「PDF 翻译」，或要在翻译里保留公式与图片时使用。走 HTML + KaTeX + headless Chrome，公式重新排版而不是裁图。
---

> **输出语言**：面向用户的回复、提问、汇报、审批请求一律用**中文**（内部推理可用英文）。代码、路径、命令保持英文原词。术语按「中文（English）」给出首次出现。

# PDF Translation

Turn an English PDF into a **Chinese PDF that looks like a published book** — figures kept in place, code blocks intact, and formulas **re-typeset as real math**, not cropped to bitmaps or flattened to Unicode.

## What this skill is built on

Two decisions, and everything else follows from them.

**1. The engine is HTML + CSS → headless Chrome.** Not LaTeX. Both reference samples that
this skill was distilled from (`Skia/PDF m153` + `HeadlessChrome/153`) came out of exactly
this route, and it beats pandoc+xelatex on this job for three concrete reasons: design
iteration is a CSS edit (seconds, not a MiKTeX bootstrap), CJK line-breaking and font
fallback are the browser's problem rather than xeCJK's, and what you see is what prints.
LaTeX is for math-dense academic typesetting where you control the whole document; here you
are rebuilding someone else's layout, and CSS is the cheaper instrument.

**2. Formulas get re-typeset with KaTeX.** This is the whole point of the skill.

The trap is a false dichotomy: **"the extractor gives me no LaTeX, so I must either emit flat
Unicode or crop the formula to an image."** Both destroy already-typeset math. The source PDF
of the reference case had `∑` with a real lower limit and `I₁ᵖ` with genuine two-level scripts —
and both failure modes threw that away. Flat Unicode loses the fraction bars, radical
extensions and script placement; a cropped bitmap cannot scale, cannot share a baseline with
the surrounding Chinese, and looks pasted.

KaTeX renders to **vector glyphs in embeddable font subsets** (`KaTeX_Math-Italic`,
`KaTeX_Main-Regular`, `KaTeX_Size2-Regular` for large operators). That is the target.

> **Why not the document-parsing tools?** `pi-docparser` is a Pi-only package whose
> `document_parse` exposes only `text` and `json` — no markdown — and it merely projects
> `@llamaindex/liteparse`. LiteParse, MinerU, Marker, Docling and miyo are all *extractors*:
> they answer "how do I get text out", which is the wrong question. On a born-digital PDF
> (`lit is-complex` → `isComplex: false`) the text layer is already clean and **PyMuPDF's
> `get_text("dict")` is sufficient and faster**. Reach for an extractor only when
> `is-complex` says the page needs OCR. The dependency that actually matters here is the
> **math typesetting chain** (`katex`, or `temml` / `mathml-to-latex`), not the parser.

## The pipeline

Six stages. `scripts/` holds the mechanical ones as runnable programs; translate and verify
are the model's own work.

```
0. ask        → ASK: Markdown only, or a typeset PDF? which column layout? (with a cost quote)
1. probe      → is this PDF born-digital? which pages need OCR?
1.5 truncation→ did the SOURCE lose text to HTML clipping? (recover it later, in stage 4)
2. extract    → text blocks + bbox + font/size/COLOUR per page, figures cropped at 300 dpi
3. classify   → which spans are math, which blocks are headings / code / captions
4. translate  → the MODEL writes the Chinese, into a structured body file.
                Inventory the source's links FIRST (extract-source-links.py) and put that
                inventory in every batch brief; splice them back afterwards
                (restore-links.py).
5. verify     → four gates, run in this order, each one a hard stop:
                  fidelity.py        no dropped sentences, no summarised captions
                  coverage-check.py  no source run left untranslated
                  links-audit.py     every source annotation accounted for
                  check-markup.py    the <a> splices did not corrupt the HTML
6. typeset    → HTML + KaTeX → headless Chrome → PDF, stamp header/footer, then
                add-internal-links.py puts the TOC jumps into the rendered PDF

Markdown-only deliverable: stop after stage 5 and emit body.md. Skip 6 entirely.
```

### Stage 0 — ask for the output format and the layout. Do not infer either.

**Ask the user these three questions, in Chinese, before any extraction or translation:**

1. **只要翻译后的 Markdown，还是也要排版好的 PDF？**
2. **正文要单栏还是双栏？**（仅当要 PDF）
3. **图片要单栏还是双栏？**（仅当要 PDF）

For question 1, **quote the cost first**. Run the estimator and put its numbers in the
question — the user is choosing between a cheap and an expensive deliverable, and cannot
choose without the price:

```bash
python "<skill-dir>/scripts/estimate.py" "<input.pdf>"
```

It measures the real document (pages, English words, numbered equations, image objects) and
applies coefficients calibrated on the reference case — **汉字数 ≈ 英文词数 × 0.94**, measured
9,336 predicted against 9,329 actual. It reports an estimated CJK character count, input and
output tokens, and wall-clock minutes, and it flags **formula-heavy** documents (≥ 4 numbered
equations per page), which iterate far more and therefore cost more.

> **On a handout, read the CJK estimate as a floor.** That 0.94 came from a formula-dense journal
> paper. On a prose-and-code lecture PDF it ran 1.45× low — 50,529 words produced 73,288 CJK, not
> the 47.5k it predicted. The cause has not been attributed item by item; the direction has, so do
> not quote the low number as a ceiling.

Ask in this shape, with the real numbers substituted:

> 这份 PDF 共 **14 页 / 9,932 个英文词 / 72 个编号公式**（公式密集）。
> - **只出 Markdown**：约 **15–25 分钟**，**2 万–4 万 token**（跳过排版与迭代）
> - **出排版好的 PDF**：约 **60–100 分钟**，**4 万–7 万 token**
>
> 要哪一种？要 PDF 的话，正文和图片分别要单栏还是双栏？

**The Markdown-only path is a real path, not a consolation prize.** It skips stages 5–6
entirely: no KaTeX, no Chrome, no overflow loop, no column architecture. The output is
`body.md` with `$...$` math left as LaTeX and figures referenced by filename. Recommend it
when the user only wants to *read* the paper, and say so — it is roughly a quarter of the
cost. Recommend PDF when the output is going to be kept, printed, or shared.

If the answer is PDF and two-column, also confirm whether figures should **span both
columns** (as a journal sets them) or sit **inside a single column**.

This is a gate, not a preference. The format and column decisions change which stages run,
the CSS architecture, the figure markup, and the formula-overflow criterion — all expensive
to retrofit. Never default to what the source PDF does, and never default to PDF because the
rest of this file describes one.

If the source is a **two-column journal paper** (IEEE / ACM / Elsevier), read
[`references/two-column-paper.md`](references/two-column-paper.md) before stage 6 — it carries
the measured column geometry, the per-run multicol architecture, the overflow criterion and
its traps, and the figure/table span rules.

### Stage 1 — probe before you commit

```bash
python "<skill-dir>/scripts/probe.py" "<input.pdf>"
```

Reports page count, page size, per-page text/image block counts, and the **font-size
histogram** — which is what tells you the heading hierarchy and where body text sits.
It also reports the **(size, colour)** profile, which is what actually separates headings
from list items (see stage 4). Run `lit is-complex` if LiteParse is available; if pages
come back complex, this route is wrong and you want an OCR-capable extractor instead.

**Also probe for source truncation before you translate a word:**

```bash
python "<skill-dir>/scripts/detect-truncation.py" "<input.pdf>" --emit-tasks
```

Born-digital PDFs printed from HTML routinely clip `<pre>` blocks, and the missing
characters are absent from the content stream — extraction cannot be blamed and cannot
help. Finding this *now* tells you the recovery workload before translation starts, rather
than after you have already produced a document full of apology notes. Stage 4 says what to
do with the list.

### Stage 2 — extract

```bash
python "<skill-dir>/scripts/extract.py" "<input.pdf>" "<workdir>" --pages 1-10
```

Writes `<workdir>/structure.json` (all blocks with bbox/font/size) and `<workdir>/figs/*.png`
(figure regions merged from image bboxes and cropped at 300 dpi). **Always start with a
10-page range**, never the whole document — see "Sample first" below.

### Stage 3 — classify

```bash
python "<skill-dir>/scripts/classify.py" "<workdir>/structure.json"
```

Three jobs, all mechanical:

- **Math detection.** Spans whose font is `Type3 (...)` or a math font, or whose size differs
  from body text within a formula-shaped line run, are math. Report their bboxes and the
  reconstructed run so the model can read the formula off the geometry (see below).
- **Heading detection, by SIZE AND COLOUR.** The script prints a `(size, colour)` table with
  example strings, then the rules for reading it. Do **not** take the size-ordered "H1…H5"
  map as the tag assignment — that map is a stub for locating candidates, and on a document
  where list items share a size with headings it is actively misleading. See
  "Heading levels" in stage 4.
- **Colour is a first-class signal.** `extract.py` records each span's colour, because on
  many documents — lecture notes especially — a heading and a list item are the *same
  concept* separated only by colour, not size.

### Stage 4 — translate

The model writes the Chinese into `body.html` (a fragment — cover, TOC, then `<section>` per
chapter). Rules that are not optional:

- **Fidelity comes before fluency. Translate the source, do not summarise it.**
  This is the failure mode that matters most, because it is invisible: the output reads
  well, and only someone holding the original can tell that whole sentences were dropped or
  rewritten from memory. Concretely:

  - **Every sentence in the source gets a sentence in the output.** If the source says
    "In this example, the cat image is 248 pixels wide… consists of 248 x 400 x 3 numbers,
    or a total of 297,600 numbers", the output says all three facts — not a tidied-up
    "the image is a big array of numbers".
  - **Inline enumerations stay inline.** The source's `(e.g. cat)`, `{cat, dog, hat, mug}`,
    `"airplane, automobile, bird, etc"` are content, not decoration. Keep the braces and
    the English sample values; do not convert a source example into your own gloss.
  - **Do not invent a heading the source does not have**, and do not drop one it does.
    The source's section labels are `Motivation.`, `Example.`, `Challenges.`,
    `Data-driven approach.`, `The image classification pipeline.` — those become
    `<h3>动机 <span class="en">Motivation</span></h3>` and so on. A run-in bold lead
    (`Motivation.`) is a heading; promote it and keep the English in a `.en` span.
  - **A Table of Contents in the body is a list to translate, not a summary to write.**
    Source `The Table of Contents: Intro to Image Classification, data-driven approach,
    pipeline / Nearest Neighbor Classifier / k-Nearest Neighbor / …` becomes a real `<ul>`
    with one `<li>` per item, in order, all of them. Never compress it, never reword it.
  - **Captions are translated verbatim.** A `figcaption` is a translation of the source
    caption text, word for word. It is **not** a description of what you think the figure
    shows. Compare against `structure.json` — captions are the `11.2pt` blocks, body text
    is `12.8pt`, which is how you find them.
  - **When the source is truncated, the deliverable is the RECOVERED text, not a note
    about the damage.** Extraction sometimes returns a line that stops mid-word, with no
    continuation anywhere on the page. That text is genuinely absent from the PDF's
    content stream, and it is *not* your problem to report — it is your problem to fix.
    Do **not** invent an ending, and do **not** paper over it either. Recover it (below).

  **Before rendering, walk `structure.json` page by page and tick off each block against
  your `body.html`.** Any source block with no counterpart is a dropped sentence. This
  check is cheap and it is the one that catches the defect above.

### Truncated source text — detect it, then recover it

A PDF whose text layer stops mid-word is a **damaged source**, and damaged sources are
normal, not exceptional. The usual cause is a born-digital PDF printed from HTML with
`overflow: hidden` on `<pre>`: the code block was wider than its window, so the characters
past the clip were never written into the content stream at all. PyMuPDF is not failing —
there is nothing there to extract.

**Detect it mechanically before translating anything:**

```bash
python "<skill-dir>/scripts/detect-truncation.py" "<input.pdf>"
```

It flags monospace lines that end flush against a common right-hand edge (a clip
boundary, not a natural line ending) and reports the count, the pages, and the exact
truncated strings. Run it in stage 1 or 2, and put the resulting count in your own
working notes — it sets your recovery workload. Anything from a handful of lines to
several hundred is plausible; the CS231n lecture case reported **73 lines across 42 pages**.

**Those are candidates, not verdicts.** The detector's rule is geometric — a line ending
flush against the clip boundary — so a line that happens to end exactly on a complete word
is flagged too. Read the list before you cost a recovery pass: on the CS231n document 3 of
the 73 needed nothing.

**Then recover, in this order of preference:**

1. **Find the upstream original.** A lecture PDF is almost always a print of a public web
   page, and a paper may have an arXiv version. Fetch the source text and restore the
   truncated lines *verbatim* from it. This is the strong path: it is exact, and it costs
   one fetch. `detect-truncation.py --emit-tasks` writes a checklist you fill in.
2. **Reconstruct from the code's own grammar**, when no upstream exists and the missing
   span is unambiguous — an unbalanced bracket that one `)` closes, a string literal whose
   terminator is implied.
3. **Only if neither works**, keep the fragment and mark it once, in a footnote or a
   single bracketed `[…]`. A per-line disclaimer repeated 43 times is not disclosure, it
   is a broken document.

**Two rules that keep recovery honest:**

- **Restore the revision the PDF actually printed, not the latest one.** Upstream drifts.
  The CS231n notes now say `NearestNeighbor(object)` and `range(num_test)`; the 2016-era
  PDF printed `NearestNeighbor` and `xrange`, and its surrounding prose is Python 2
  (`print 'accuracy: %f'`). Recovery must match the **printed** revision — cross-check
  against the un-truncated code on the same page before you accept a substitution.
  This matters because a "recovered" block that switches dialect mid-listing is worse
  than the truncation it replaced.
- **Then apply stage 5's `fidelity.py` as usual.** A recovered block must still be
  *translated* as a code block is translated: identifiers untouched, comments rendered in
  Chinese in full, per the rule below.

**The disclaimers are a deliverable defect, not a disclosure.** If you find yourself
writing "末尾字符缺失" / "cut off in the original" more than a couple of times, stop: you
have misread a repairable source as an unrepairable one, and the output will read as a
document that gave up. Recovery is the default; annotating is the exception.

**How to verify recovery actually landed — and how not to.** Comparing the source's
severed fragment against the output is the obvious check and it is wrong three ways, all
of which were hit in practice on a 73-site document:

1. **Substring matching reports success as failure.** The fragment `# a magic func` is a
   *prefix* of the recovered `# a magic function we provide`, so a naive `in` test finds
   the fragment and concludes nothing was fixed.
2. **Searching for the severed token can never succeed.** By definition the token was cut
   mid-word, so it does not exist in the output. A check built that way reported 49
   already-recovered sites as missing.
3. **Exact whitespace anchoring fails on reflowed code.** The source prints `32*32*3` and
   `*0.0001# generate`; the re-typeset output may space them differently.

The check that works has two steps, and the second one is the one that makes it sound.
**First: anchor on the last word that was INTACT in the source and ask whether the output
continues past it.** If the source stopped after `... using the sigmoid gradient derivatio`
and the output reads `... using the sigmoid gradient derivation`, the output continues and
the cut was healed; if the output stops in the same place, it survived. **Second: confirm
the continuation is text the source does not contain.** Without that step every line that
simply *fit* counts as recovered, because the text following the anchor is then just the
next source line — and a complete line is exactly what the detector over-reports.

Measured on the CS231n document: 73 candidates. Step one alone called 72 of them recovered.
Adding step two cut it to **65 provably healed**, 3 that were never truncated, and 4 whose
anchor would not resolve — all 4 of which turned out on inspection to be healed as well
(`# get the gradi` → `# get the gradient`). **Zero sites survived.** The two obvious checks
both fail: matching the severed fragment as a substring reports success as failure
everywhere, and searching for the severed token itself reported 49 already-recovered sites
as missing, since that token by definition does not exist in the output.

Corollary worth stating plainly: **"found / not found" is not a valid drop test. Compare
where the source stops against whether the output continues — and whether that continuation
exists in the source at all.**

- **First occurrence of a technical term gets `中文（English）`**, e.g.
  `视角变化（Viewpoint variation）`. Subsequent uses are Chinese only.
- **Code blocks keep their English code; comments get translated.** Never translate identifiers.
  Keep the source's comments in full — do not shorten `# and now print the classification
  accuracy, which is the average # of examples that are correctly predicted (i.e. label
  matches)` to `# 打印准确率`.

- **Formulas become KaTeX.** Read them off the source geometry and re-emit them as `$...$`
  (inline) or `$$...$$` (display). A formula's structure is recoverable from its span bboxes:
  a span sitting **below** a `∑` is its lower limit, a span **above** the baseline of an `I` is
  a superscript, a span **below** it is a subscript, and two spans sharing one base are
  two-level scripts.

  Reference case, read straight off `structure.json`:
  `d` + `₁` + `(I₁, I₂) = ∑` with `p` beneath + `|I` + `1`(sub) + `p`(sup) + `−` + `I` + `2`(sub) + `p`(sup) + `|`
  → `$$d_1(I_1, I_2) = \sum_{p} \left| I_1^p - I_2^p \right|$$`

- **Figures go in reading order**, each with a real numbered caption. The caption is part
  of the figure, not an afterthought — get all four of these right, because they are the
  first thing a reader notices and the first thing they report:

  1. **Placement: always directly BELOW its figure**, centred or flush-left as the design
     dictates, never above it and never beside it. A caption that floats to the right of a
     figure, or wraps around it, reads as broken body text.
  1b. **A caption belongs to a caption BLOCK, not to each image.** Source PDFs very often
     place two or more images side by side under a single caption whose text says
     "Left: … Right: …". That is **one** figure with **one** caption and **one** number —
     do not give each half its own copy of the text, and do not number the halves
     separately. Group them inside a single `<figure>`:

     ```html
     <figure class="fig-pair">
       <div class="pair-row">
         <img src="figs/a.png"><img src="figs/b.png">
       </div>
       <figcaption><span class="fignum">图 1</span> 左侧……右侧……</figcaption>
     </figure>
     ```

     Detect the grouping from the source geometry, not by eye: if two image rects sit at
     roughly the same `y` and a **single** caption block begins below both of them, they
     are one captioned figure. If the caption blocks are separated (different `y`, each
     under its own image), they are two figures with two captions. In the CS231n run a
     naive per-image pass produced the **same caption printed on two figures with the same
     number**, and the numbering then jumped (圖 8 → 图 13) — both defects came from
     ignoring the block grouping.
  2. **Numbering: every figure gets `图 N`, monotonically, with no gaps.** A figure that
     ends up without a caption is a defect even when the image itself rendered fine —
     the CS231n run shipped one figure with no caption at all, and it was the single most
     visible problem in the document. Number them as you emit, and check the sequence.
  3. **`figcaption` carries real typographic separation from body text** — a size step
     down, a colour change, or both: e.g. `10.1pt` against `12.8pt` body, in a muted
     grey/navy, with `margin-top` binding it to the figure (`figure { break-inside:avoid }`
     so the two never separate across a page or column break).
  4. **The caption box is constrained to the figure's width**, not the text column's. If
     the figure is narrower than the column, a caption stretched to full width looks
     detached from it.

  In the source, captions are the small-size blocks — find them by size and colour in
  `structure.json` and translate each **verbatim**. Never write a caption that describes
  what you think the figure shows, and never silently drop one because the image was
  small or the caption looked redundant.

- **Figures must also fit the page.** Cap their height (`max-height` in the CSS) and let
  them break to the next page rather than overflowing the bottom margin. A figure that
  runs past the text block is worse than a figure that starts a page late.

### Links and navigation are content — do not drop them

Three things get lost silently here, and a reader reported each one before any
automated check caught it.

**1. The source's links.** A born-digital PDF carries URI annotations; a course-notes or
reference PDF often carries hundreds (the CS231n source: **251**). The first delivery
emitted the *text* of the Further Reading items but none of the `<a href>`, so the reader
could not follow a single reference. Extract them with their anchor text:

```bash
python "<skill-dir>/scripts/extract-source-links.py" "<input.pdf>"   # -> source-links.json
```

**Give the inventory to whoever writes each fragment, before they write it.** The second
delivery still lost **184 of 251** — because the first 30 pages were hand-written with the
links inline while the remaining five fragments were written in parallel from a brief that
never mentioned links. Splitting the work splits the context, and any fact you forget to
put in the brief is a fact the fragment will not have.

**Separate chrome from content.** The same site footer repeated on 16 pages
(`github.com/cs231n`, `twitter.com/cs231n`, `mailto:…`, plus the chapter-title link
`cs231n.github.io/` at each chapter head) is 66 of the 251 — drop it, exactly as you drop
the grey running header. A translation is not a website. Everything else is content.

**Then splice them back into the assembled body.** The restorer locates each annotation in
the translated prose and wraps the matching span. Nothing is written without `--apply`, and
`--review` prints every restored match with its context so the placement can be checked:

```bash
python "<skill-dir>/scripts/extract-source-links.py" "<input.pdf>" "<workdir>/source-links.json"
python "<skill-dir>/scripts/restore-links.py" --body "<workdir>/body.html" \
       --links "<workdir>/source-links.json" --review     # dry run, every match shown
python "<skill-dir>/scripts/restore-links.py" --body "<workdir>/body.html" \
       --links "<workdir>/source-links.json" --apply      # rewrite the body
python "<skill-dir>/scripts/check-markup.py"  "<workdir>/body.html"   # must print MARKUP OK
python "<skill-dir>/scripts/links-audit.py" --body "<workdir>/body.html" \
       --links "<workdir>/source-links.json"
```

**Locating a link in translated prose is the hard part.** Both documents share a reading
order, and Latin-script material (paper titles, author names, API names) survives
verbatim — `《深度网络真的需要深吗？》（Do Deep Nets Really Need to be Deep?）`. Four
approaches were tried; the first three failed in instructive ways:

- **Forward cursor over the output**: one wrong match poisons the cursor and everything
  after it is skipped. It also died on its *first* element, because the hand-written front
  matter ordered the links differently from the source — a greedy walk cannot survive a
  local reordering. Restored 14 of 136.
- **LCS over the URI sequence**: handles the reordering, but windows built from its pins
  *collapse* when a recurring URI (the per-chapter title link) is matched late-source to
  early-output. 46 pinned, 3 restored.
- **Interpolated expected position**: right idea, and it restored 0 because of a silent
  parity bug — `re.split(r"(<[^>]+>)", html)` leaves text at even indices only while the
  file does not begin with a tag, and the loop tested parity the wrong way round, so it
  searched the **markup**. It found `figure` inside `<figure class=…>` and would have
  spliced `<a>` into the tag. Detect a tag by `s.startswith("<")`, never by parity, and
  assert the markup afterwards (`check-markup.py`: balanced `<a>`, no `<a>` nested in a
  tag, no empty anchors).
- **What works**: interpolate the expected position on the **source page**, not on the
  annotation index (a page is a fixed amount of output; an index is not, since pages carry
  very different numbers of links), extrapolate past the last pin instead of clamping, and
  **bootstrap** — the links placed in one round become pins for the next, which tightens
  the prior across regions the fragments left link-free. Without the bootstrap the middle
  100 annotations sit under a prior that is off by up to 14 kB.

Accuracy rules, in priority order:

1. **Try the whole anchor phrase first.** It is unambiguous and it is the span a reader
   wants. Token matching alone put three different source links on one phrase, because
   `Nets` occurs in several paper titles.
2. **Scale the evidence to the ambiguity.** A rare string can be placed by proximity; a
   common word needs a *second distinctive token from the same anchor* nearby. Without
   this, the token `Networks` — drawn from a whole printed line — matched a table of
   contents reading "Convolutional Networks".
3. **One output span carries at most one link.** Otherwise later inserts nest inside
   earlier ones.
4. **Ignore tokens from anchors longer than ~60 characters.** Those are block-level
   extractions of an entire line, and their token set is mostly ordinary words.

**~27% cannot be placed at all, and must be reported rather than guessed.** Their visible
text was translated with no Latin trace left: `in the documentation.` → `在文档中`,
`here.`, `review`, `FAQ`. String matching cannot find them and ordinal matching is unsafe
because the counts do not agree. Report them; a wrong link is worse than a missing one.

**Check the count** and state the policy, so the gap is a decision rather than an
omission: `251 annotations = 66 dropped as chrome + 52 already present + 66 restored +
67 unplaceable`. Note which count you are quoting: this source carries **253** URI
annotations and 2 of them are exact duplicates of another, so the inventory — and the
ledger — is **251**. `extract-source-links.py` prints both numbers; quote the unique one
and say so.

Report the **per-annotation ledger**, not "how many distinct URLs appear". The two differ
and the second one lies: an annotation counts as present as soon as its URI occurs
*somewhere*, so three citations of the Dropout paper collapse into one and a missing link
looks present. `links-audit.py` prints the URI-presence view for a quick signal; the
authoritative numbers come from aligning each annotation to its own output occurrence.

**2. The chapter-opening table of contents.** Many sources open each chapter with a short
`Table of Contents:` list of that chapter's sections. It is *content*, not chrome: the
first delivery omitted the Linear Classification chapter's entire nine-entry list while
faithfully translating the surrounding prose. Emit it as a list right after the chapter
heading, and make each entry jump to its section.

**3. Chrome does not export same-document anchors.** `--print-to-pdf` writes external
`uri` annotations but **not** `#anchor` links: a TOC built entirely from `<a href="#id">`
renders as dead text, with zero link annotations in the PDF. Verify by counting:

```python
# external links survive, internal ones do not
print(sum(1 for p in doc for l in p.get_links() if l.get("uri")))
print(sum(1 for p in doc for l in p.get_links() if l.get("kind") == pymupdf.LINK_GOTO))
```

Internal jumps therefore have to be added to the rendered PDF as `LINK_GOTO` annotations
in a post-pass. Two traps when locating the targets, both hit in practice:

- **Do not prefer heading *size* when picking the target page.** Sections rendered as
  run-in headings can sit just above body size, so a size filter skips them and matches a
  later chapter's identically-named heading — it sent one link 48 pages forward.
- **Exclude the TOC block's own bounding box from the search.** Otherwise a label that is
  a prefix of a longer entry matches the TOC itself (`小结` inside
  `小结：在实践中应用 kNN`) and every entry ends up pointing at its own page.

The working rule is: the target is the first hit **after** the label in reading order,
excluding hits inside the TOC block; earliest page wins, and size only breaks ties.

### Heading levels: derive them from the source, never from size order

Size alone does not tell you what is a heading. The CS231n lecture PDF is the case that
proves it: `Assignments` and `Module 0: Preparation` are **19.2pt in Stanford red
(`#8c1515`)** and are section headings — but `Assignment #1: Image Classification, kNN,
SVM, Softmax` is **14.4pt in near-black (`#333333`)** and is a plain **list item**. An
earlier run levelled purely by descending size, promoted all of them, and produced giant
`<h1>` headings — with `justify` stretching them to one character per span
(`作 业 #1 ： 图 像 分 类`). The source's real hierarchy, measured:

| size | colour | role | tag |
|---|---|---|---|
| 25.6pt | black | chapter | `h1` |
| 20.8pt | black | section | `h2` |
| 16.8pt | black | subsection | `h3` |
| 16.0pt | black | sub-subsection | `h4` |
| 19.2pt | `#8c1515` red | special section | `h1`/`h2` by context |
| 14.4pt | `#333333` | **list item — NOT a heading** | `<li>` |
| 20.8pt | `#ababab` grey | **running header — DROP** | — |

So before assigning any tag, run `classify.py` and read the **size + colour** table it now
prints. Then decide per group, using these rules:

- **A colour that appears only on short, standalone lines is a heading colour.** A muted
  grey repeating on every page at the same y is a running header — delete it, never
  translate it into a heading.
- **A size that also carries long prose is not a heading level.** If 14.4pt lines run to
  60+ characters, that size is body-ish and belongs in `<p>`/`<li>`.
- **Siblings sharing a prefix are a list, not headings.** `Assignment #1/#2/#3`,
  `(a)/(b)/(c)`, `Part I/II` — emit one `<ul>` with an `<li>` each.
- **Never promote a TOC entry to a heading.** A contents list is a list, at every level,
  in every part of the document — including a per-chapter contents block embedded in the
  body. The CS231n front matter was a TOC, and rendering its entries as `<h1>` produced
  the letter-spaced monstrosity above.
- **Do not let a heading be stretched by `justify`.** Headings take
  `text-align:left; text-justify:auto` — CJK justification belongs to body paragraphs
  only. One character per span in a rendered heading is the signature of this bug.

- **A body heading must not be the only child of its own section.** If a heading is
  immediately followed by another heading, one of them is not a heading (usually the
  parent is a list label). Check for orphan `<h1>`s before rendering.

### Stage 5 — verify, then stage 6 — typeset

```bash
python "<skill-dir>/scripts/fidelity.py" "<workdir>"        # GATE - must exit 0 first
python "<skill-dir>/scripts/coverage-check.py" "<workdir>"  # GATE - catches dropped pages
python "<skill-dir>/scripts/check-markup.py" "<workdir>/body.html"     # GATE - markup intact
python "<skill-dir>/scripts/links-audit.py" --body "<workdir>/body.html" \
       --links "<workdir>/source-links.json"                            # GATE - link coverage
python "<skill-dir>/scripts/typeset.py" "<workdir>"
python "<skill-dir>/scripts/add-internal-links.py" "<rendered.pdf>"     # stage 6, on the PDF
```

`typeset.py` builds `doc.html` from `body.html` + the design system + local KaTeX, prints
to PDF with headless Chrome, then stamps running header/footer and metadata. It reports the
measurement block you verify against (`KaTeX font char count`, `overflow spans`, `pages`).

`add-internal-links.py` runs on the **rendered PDF**, never on the HTML, because Chrome does
not export same-document anchors — see the links section above. Run it last, or the TOC
jumps will be missing from the file you deliver.

**Run `fidelity.py` first and treat a non-zero exit as a hard stop.** It measures three
things that are otherwise invisible: source sentences with no counterpart in the output,
untranslated English prose, and captions that were summarised instead of translated. The
caption check is the one that earns its keep — it compares each `figcaption` against the
matching source caption and flags anything under ~0.18x the source length (Chinese runs
0.25–0.45x English normally, so the floor is low enough not to cry wolf).

**Then run `coverage-check.py`, which catches what `fidelity.py` structurally cannot.**
`fidelity.py` measures properties of the *output* (disclaimer count, caption ratios,
numbering). None of those can see *a whole page that never got translated*: such a
document is well-formed, carries no disclaimer, numbers its figures contiguously, and
passes every output-side check. This actually happened — a batch translator dropped two
source pages (an entire gradient-descent code body), and the only thing that found it was
a human reading the recovery list.

`coverage-check.py` measures the source-to-output **relationship** by counting
content-bearing source *runs* per kind (prose / code / caption) and comparing them against
output elements. It does **not** try to match text, because the output is Chinese and the
source is English — a text-matching version of this check reported 4–26% coverage on five
complete translations, i.e. it was measuring the language change. Calibration:

| batch | code runs | `<pre>` | ratio |
|---|---|---|---|
| complete | 19 | 14 | 74% |
| complete | 11 | 9 | 82% |
| complete | 26 | 25 | 96% |
| complete | 19 | 17 | 89% |
| complete | 59 | 46 | 78% |
| **damaged copy** | 19 | 9 | **47%** ← must fail |

The floor is **0.65**: below the healthy band's minimum, above the damaged case. Verify
that calibration holds if you apply this to a new document family — and note the check
only works at all once source *runs* (maximal consecutive same-kind blocks) are counted
rather than raw blocks, and once inline code inside a prose sentence is not mistaken for a
code listing.

**Chrome must be locatable.** The script probes the standard install paths; set
`CHROME_PATH` if it is somewhere else. KaTeX is installed into `<workdir>` on first run.

### Environment

`<skill-dir>` in every command above is this skill's own directory — the folder containing
`SKILL.md`. Resolve it to an absolute path before running anything; the scripts take only their
documented arguments and read no configuration file of their own.

**No API key is needed.** The translation is written by the host agent's model, so the
credential lives in the host agent, never in this skill. The only optional
environment variables are:

| Variable | When |
|---|---|
| `CHROME_PATH` | Chrome/Edge is not in a standard install location |
| `PDF_TRANSLATION_SERIF` | body CJK font stack (e.g. `Songti SC`, `Noto Serif CJK SC`) |
| `PDF_TRANSLATION_SANS` | heading CJK font stack (e.g. `PingFang SC`, `Noto Sans CJK SC`) |
| `PDF_TRANSLATION_FONT_DIR` | where the *stamped* header/footer font file lives |

**Fonts are the one platform-specific default.** The bundled CSS asks for `STSong`/`SimSun`
(body) and `Microsoft YaHei` (headings) — Windows names. On macOS or Linux, set the two
variables above rather than editing `scripts/typeset.py`: the CSS keeps a single `--serif` /
`--sans` definition each, so overriding them is a complete fix. Nothing else in the pipeline
is platform-dependent.

**The Python dependency is `pymupdf` alone** (`pip install pymupdf`). Chrome/Edge is the only
other external requirement.

## Sample first — the rule this skill exists to enforce

**Never extract-and-translate the whole document before rendering anything.**

Render **10 pages** (or 10%, whichever is smaller), show the user that PDF, and get a verdict
on the **formula** and the **overall layout** before committing to the rest. Cost is trivial —
the reference run rendered in **6.4 s** — while the cost of being wrong is the entire document.

The failure this prevents is real and specific: discovering at the end of a full-document run
that formulas should have been typeset rather than cropped, when the feedback loop is now too
long to act on. If the user has a reference sample they consider good, **measure it first**
(see below) so the target is defined before any work starts.

## If the user names a good sample, measure it before anything else

```bash
python "<skill-dir>/scripts/compare.py" "<mine.pdf>" "<reference.pdf>"
```

Prints page count, char count, math-font char count, embedded image count, PDF size, and the
**producer/creator string** for each. Two facts fall out immediately and both change the plan:

- **Same producer string ⇒ the engine is not the difference.** Do not rewrite the pipeline.
- **A far higher math-font count in the reference ⇒ the difference is formula typesetting.**
  That is stage 4's problem, and no amount of extractor-shopping will fix it.

Read `producer` before you read anything else the user said about "better tools".

This is the PDF instance of `/calibrate`'s first move (measure the target shape before choosing
a method). Run `/calibrate` at the start of any translation job, not just when things go wrong.

## Verification — what to check before delivering

Run `typeset.py` and read its report. All four must hold:

| Check | Target | Means |
|---|---|---|
| `KaTeX_*` font chars | **> 0** | math is vector-set, not flat text |
| `overflow spans` | **0** | nothing past the page edge |
| page count | > 0, sane | Chrome actually rendered |
| CJK chars in text layer | present | fonts embedded, not tofu |

Then confirm the formulas specifically: the extracted text of a display-formula line should
come back **fragmented** (`d`, `(I`, `, I`, `) =`, `∑`, detached `1`/`p` runs). That
fragmentation is the **signature of correct math layout** — scripts are positioned, not
concatenated. Flat Unicode extracts as a single tidy run, which is how you recognise the
failure mode.

**`Type3` glyphs are a warning sign, not a goal.** Some CJK variable fonts degrade to Type3
glyph procedures in Chrome and **cannot be embedded**. Prefer `STSong`/`SimSun` for body CJK
and `Microsoft YaHei` for headings; they subset cleanly.

## Layout facts worth not rediscovering

- **Body CJK `10.5pt` / line-height `1.85`** reads like a textbook at A4. Headings
  `Microsoft YaHei` bold in a dark navy (`#1f4e79`), body `STSong`.
- `@page{ size:A4; margin:20mm 18mm 17mm 18mm; }` with `text-align:justify;
  text-justify:inter-ideograph` for CJK.
- Cap figure height (`max-height:290pt`) or a tall figure pushes a blank half-page.
- `break-inside:avoid` on `figure`, `pre`, `.box`, and `tbody tr`.
- **Headings need `break-after:avoid` as well as `break-inside:avoid`**, or a heading lands at
  the foot of a page/column with its paragraph on the next. This is the first defect users
  report; put it in the base stylesheet.
- Chrome needs `--virtual-time-budget` **≥ 15000** for KaTeX to finish typesetting before
  the print fires. Lower values silently emit unrendered math delimiters.
- PyMuPDF's built-in CJK fonts render Latin at full-width spacing (`C S 2 3 1 n`) — stamp
  header/footer with a real font file (`msyh.ttc`) and `subset_fonts()` afterwards.
- **A formula that fits its column can still be printed over the next one.** Overflow is
  measured per column, and a left-column overflow of even 40 pt collides with real text.
  See `references/two-column-paper.md` §4 — the criterion has two traps that both shipped.

## Files

```
SKILL.md                        this file
references/two-column-paper.md  journal two-column layout: geometry, multicol architecture,
                                overflow criterion, figure/table span rules
scripts/estimate.py             stage 0 — token & wall-clock estimate, formula-density flag
scripts/probe.py                stage 1 — page/block/font-size report
scripts/detect-truncation.py    stage 1.5 — find text the SOURCE lost to HTML clipping
scripts/extract.py              stage 2 — structure.json + figures at 300 dpi
scripts/classify.py             stage 3 — math spans + heading levels (size AND colour)
scripts/fidelity.py             stage 5 — dropped content / untranslated / caption gate
scripts/coverage-check.py       stage 5 — source-to-output block coverage (dropped pages)
scripts/extract-source-links.py stage 4 — pull the source's link annotations + anchor text
scripts/restore-links.py        stage 4 — put the source's CONTENT links back into the body
scripts/links-audit.py          stage 5 — link coverage: source annotations vs output
scripts/check-markup.py         stage 5 — markup integrity after splicing <a> into prose
scripts/add-internal-links.py   stage 6 — add TOC jump links to the rendered PDF
scripts/typeset.py              stage 6 — HTML + KaTeX + Chrome → stamped PDF
scripts/compare.py              measure any two PDFs against each other
```
