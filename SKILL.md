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
2. extract    → text blocks + bbox + font/size per page, figures cropped at 300 dpi
3. classify   → which spans are math, which blocks are headings / code / captions
4. translate  → the MODEL writes the Chinese, into a structured body file
5. verify     → fidelity.py: no dropped sentences, no summarised captions
6. typeset    → HTML + KaTeX → headless Chrome → PDF, then stamp header/footer

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
Run `lit is-complex` if LiteParse is available; if pages come back complex, this route is
wrong and you want an OCR-capable extractor instead.

### Stage 2 — extract

```bash
python "<skill-dir>/scripts/extract.py" "<input.pdf>" "<workdir>" --pages 1-10
```

Writes `<workdir>\structure.json` (all blocks with bbox/font/size) and `<workdir>\figs\*.png`
(figure regions merged from image bboxes and cropped at 300 dpi). **Always start with a
10-page range**, never the whole document — see "Sample first" below.

### Stage 3 — classify

```bash
python "<skill-dir>/scripts/classify.py" "<workdir>/structure.json"
```

Two jobs, both mechanical:

- **Math detection.** Spans whose font is `Type3 (...)` or a math font, or whose size differs
  from body text within a formula-shaped line run, are math. Report their bboxes and the
  reconstructed run so the model can read the formula off the geometry (see below).
- **Heading detection.** Size buckets from the histogram (`28pt`/`26pt` → chapter, `20pt` →
  section, `16pt` → body, `15pt` → code). Font names ending in `-Bold` confirm it.

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
  - **Where the source is truncated or garbled, say so rather than smoothing it over.**
    Extraction joins lines and sometimes clips them mid-word (`train(X,y) function that
    takes the data and the labels` cuts off). Translate what is there; if a sentence is
    clearly incomplete in the source, keep it incomplete rather than inventing an ending.

  **Before rendering, walk `structure.json` page by page and tick off each block against
  your `body.html`.** Any source block with no counterpart is a dropped sentence. This
  check is cheap and it is the one that catches the defect above.

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

- **Figures go in reading order**, each with a real numbered caption (`图 1`, `图 2`, …).

### Stage 5 — typeset

```bash
python "<skill-dir>/scripts/fidelity.py" "<workdir>"   # GATE - must exit 0 first
python "<skill-dir>/scripts/typeset.py" "<workdir>"
```

Builds `doc.html` from `body.html` + the design system + local KaTeX, prints to PDF with
headless Chrome, then stamps running header/footer and metadata. Reports the measurement
block you verify against (`KaTeX font char count`, `overflow spans`, `pages`).

**Run `fidelity.py` first and treat a non-zero exit as a hard stop.** It measures three
things that are otherwise invisible: source sentences with no counterpart in the output,
untranslated English prose, and captions that were summarised instead of translated. The
caption check is the one that earns its keep — it compares each `figcaption` against the
matching source caption and flags anything under ~0.18x the source length (Chinese runs
0.25–0.45x English normally, so the floor is low enough not to cry wolf).

**Chrome must be locatable.** The script probes the standard install paths; set
`CHROME_PATH` if it is somewhere else. KaTeX is installed into `<workdir>` on first run.

### Environment

`<skill-dir>` in every command above is this skill's own directory — the folder containing
`SKILL.md`. Resolve it to an absolute path before running anything; the scripts take only their
documented arguments and read no configuration file of their own.

**No API key is needed.** The translation is written by the host agent's model, so the
credential lives in the agent (Claude Code / DSH), never in this skill. The only optional
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
scripts/extract.py              stage 2 — structure.json + figures at 300 dpi
scripts/classify.py             stage 3 — math spans + heading levels
scripts/fidelity.py             stage 5 — dropped content / untranslated / caption gate
scripts/typeset.py              stage 6 — HTML + KaTeX + Chrome → stamped PDF
scripts/compare.py              measure any two PDFs against each other
```
