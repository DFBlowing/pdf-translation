<div align="center">

# PDF Translation

**Turn English papers into beautifully typeset Chinese PDFs**

Formulas re-set, figures in place, tables rebuilt, footnotes clickable — not a text dump with a translation on top, but a **rebuilt Chinese layout**

[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-d97757)](https://claude.com/claude-code)
[![Codex](https://img.shields.io/badge/Codex-Skill-000000)](https://openai.com/codex)
[![DSH](https://img.shields.io/badge/DSH-Skill-1f4e79)](https://github.com/deepseek-ai)
[![Pi](https://img.shields.io/badge/Pi-Skill-6b4fbb)](https://github.com/badlogic/pi)
[![License](https://img.shields.io/badge/License-MIT-2ea44f)](LICENSE)

English · [中文](README.md)

</div>

---

## What this is

An **agent skill**. It is not tied to any one agent platform — if your agent can read
`SKILL.md` and run Python and Chrome, it can use this. Say "translate this PDF" and it
produces a **typeset Chinese version**.

Verified on **Claude Code**, **Codex**, **DSH**, and **Pi** (install paths under
[Install](#install)). Cursor, Cline, Gemini CLI, and anything else that reads `SKILL.md`
work the same way.

It solves one specific problem: **every existing toolchain destroys the math.**

Convert a PDF to Markdown and translate it, and formulas have only two options — flatten to
Unicode (losing fraction bars, radicals and script placement) or crop to a bitmap (which cannot
scale, will not share a baseline with the Chinese, and looks pasted). Both ruin math that was
**already typeset correctly**.

This skill takes a third route: **re-typeset the formulas with KaTeX**. The output is real
vector glyphs (`KaTeX_Math-Italic`, `KaTeX_Size2-Regular` font subsets) — scalable, alignable,
printable.

There is no comparable open-source project, and translating papers is a daily need for a lot of
people. So here it is.

---

## What it does

### 1. Repairs overlapping text in the source

Some PDFs have text layers that overlap each other, so naive extraction returns garbage. The
tool re-positions glyphs from their real coordinates.

<img src="docs/images/01-text-overlap.png" width="100%" alt="Overlapping text">

### 2. Figures: kept at the source's own column span

A figure the source sets across two columns — `(a)` left, `(b)` right, caption spanning both —
**stays across two columns** in the translation, each subplot filling one column, instead of
being squeezed to half width into a single column. Captions are translated sentence by sentence.

<img src="docs/images/02-figure.png" width="100%" alt="Figure translation">

### 3. Tables: cells rebuilt, not screenshotted

Tables that exist only as **vector outlines** (empty text layer) are rebuilt too. Header rows,
alignment and column span all follow the source.

<table>
<tr><th>Source</th><th>Translated</th></tr>
<tr>
<td><img src="docs/images/03-table-source.png" alt="Source table"></td>
<td><img src="docs/images/04-table-zh.png" alt="Translated table"></td>
</tr>
</table>

### 4. Headings: bilingual, hierarchy preserved

Headings keep the English original, Chinese first with English beneath, at the source's own
sizes and levels.

<table>
<tr><th>Source</th><th>Translated</th></tr>
<tr>
<td><img src="docs/images/06-heading-source.png" alt="Source heading"></td>
<td><img src="docs/images/05-heading-zh.png" alt="Translated heading"></td>
</tr>
</table>

### 5. Formulas: re-typeset, not cropped

Most formulas come back **symbol for symbol**, including multi-level scripts, large operators,
fractions and delimiters.

<table>
<tr><th>Source</th><th>Translated</th></tr>
<tr>
<td><img src="docs/images/07-formula-source.png" alt="Source formula"></td>
<td><img src="docs/images/08-formula-zh.png" alt="Translated formula"></td>
</tr>
</table>

Deeply nested formulas may differ in **character choice and line breaking** — the bracket
nesting inside a radical, where a long expression wraps — but the mathematics is unchanged and
readability is unaffected.

<table>
<tr><th>Source</th><th>Translated</th></tr>
<tr>
<td><img src="docs/images/10-formula-complex-source.png" alt="Complex source formula"></td>
<td><img src="docs/images/09-formula-complex-zh.png" alt="Complex translated formula"></td>
</tr>
</table>

### 6. Footnotes: translated, with two-way jumps

The source puts footnotes at the foot of the citing page; the translation collects them at the
end of the document (Chrome still has not implemented `float: footnote`, so true page-foot
footnotes are impossible). But **clicking a superscript in the body jumps to the footnote, and
clicking the ↩ at the end of a footnote jumps back**.

<img src="docs/images/11-footnotes.png" width="100%" alt="Footnotes">

### 7. Citations stay clickable

Every `[n]` in the body becomes a link to the matching reference entry. Hover to preview.

<img src="docs/images/12-citation-link.png" width="100%" alt="Citation links">

### 8. References are not translated

Author names, journal titles, volumes and DOIs are **bibliographic data** — translating them
breaks searchability and CrossRef matching. They are extracted verbatim, re-typeset, and given
their own page.

<img src="docs/images/13-references.png" width="100%" alt="References">

### 9. Title and abstract

<img src="docs/images/14-title-abstract.png" width="100%" alt="Title and abstract">

---

## How it works

Six stages. Three of them are scripts, two are the model's own work, one is a gate.

```
0. ask        → ASK first: Markdown only, or a typeset PDF? quote the token & time estimate
1. probe      → does this PDF have a text layer? which pages need OCR?
2. extract    → per-page text blocks + bbox + font/size, figures cropped at 300 dpi
3. classify   → which spans are math, which blocks are headings / code / captions
4. translate  → the model writes the Chinese into a structured body file
5. verify     → fidelity.py: no dropped sentences, no summarised captions
6. typeset    → HTML + KaTeX → headless Chrome → PDF, then stamp header/footer
```

Choose "Markdown only" and it stops after stage 5 — the whole typesetting path is skipped, at
roughly **a quarter of the cost**.

### Why HTML + CSS rather than LaTeX

Design iteration is a one-line CSS edit that renders in seconds; LaTeX needs a MiKTeX bootstrap
first. CJK line-breaking and font fallback become the browser's problem rather than xeCJK's.
LaTeX is the right tool when you are writing a math-dense document from scratch; here you are
**rebuilding someone else's layout**, and CSS is the cheaper instrument.

---

## Install

### Requirements

| Dependency | Notes |
|---|---|
| **A host agent** | any platform that supports agent skills — Claude Code, Codex, DSH, Pi, … **The agent's own model does the translating; the skill needs no API key** |
| **Python 3.9+** | needs `pymupdf`: `pip install pymupdf` |
| **Node.js + npm** | installs a local copy of KaTeX on first run (offline afterwards) |
| **Chrome or Edge** | prints the PDF. A standard install is found automatically; otherwise set `CHROME_PATH` |
| **CJK fonts** | body `STSong` / `SimSun`, headings `Microsoft YaHei` (bundled with Windows; see the FAQ for macOS/Linux) |

### Install the skill

Drop the repository into your agent's skill directory. The path differs per platform —
use whichever one you run:

```bash
git clone https://github.com/DFBlowing/pdf-translation.git

# Claude Code
cp -r pdf-translation ~/.claude/skills/

# Codex
cp -r pdf-translation ~/.codex/skills/

# DSH
cp -r pdf-translation ~/.dsh/skills/

# Pi
cp -r pdf-translation ~/.pi/agent/skills/
```

For any other agent, put the whole `pdf-translation` directory in its skill directory —
there is no platform-specific code in the skill.
(Symlinking instead of copying also works, and makes `git pull` updates trivial.)

Then say "translate this PDF" in a session, or invoke `/pdf-translation` directly.

---

## Usage

### It asks you three questions first

**Before doing any work**, it measures your document and puts the price in front of you:

> This PDF is **14 pages / 9,932 English words / 72 numbered equations** (formula-heavy).
>
> - **Markdown only**: about **15–25 minutes**, **20k–40k tokens** (skips typesetting)
> - **Typeset PDF**: about **60–100 minutes**, **40k–70k tokens**
>
> Which one? If PDF, should the body and figures be single- or two-column?

The estimate is measured, not guessed: the script counts pages, English words and numbered
equations, then applies coefficients **calibrated on a real paper** (CJK chars ≈ English words
× 0.94; predicted 9,336 characters against 9,329 actual).

### When it works

**Good fit:**

- Academic PDFs **with a text layer** (journal and conference papers, lecture notes, textbooks)
- Single- or two-column layouts
- Formulas, figures, tables, references, footnotes

**Not a good fit:**

- **Scans and photocopies** — no text layer, needs OCR first (the tool will tell you plainly)
- Documents whose formulas are **images** (common in scanned older papers)
- Magazines, handwriting, vertical writing

### Single or two columns?

This is **asked, never assumed**. It determines the CSS architecture, the figure markup and the
formula-overflow criterion — all expensive to retrofit.

For a two-column journal paper (IEEE / ACM / Elsevier) the skill reads
`references/two-column-paper.md`: measured column geometry, the per-run multicol architecture,
the overflow criterion and its two shipped bugs, and the figure/table span rules.

---

## FAQ

### Do I need an API key?

**This skill needs no key of its own.**

Translation is done by the **host agent using its own model** — the key lives in the agent, not
in the skill. If your agent can hold a conversation, it can use this. There is no key field
to fill in anywhere in the skill.

Only a few **optional** environment variables exist:

```bash
# Optional: Chrome is not in a standard location
export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Optional: CJK fonts on macOS / Linux (see below)
export PDF_TRANSLATION_SERIF="Songti SC"          # body
export PDF_TRANSLATION_SANS="PingFang SC"         # headings
```

### CJK fonts on macOS / Linux

The defaults are the Windows font names `STSong` / `SimSun` (body) and `Microsoft YaHei`
(headings). On other platforms override them with the variables above — **no code change
needed**:

| Platform | `PDF_TRANSLATION_SERIF` | `PDF_TRANSLATION_SANS` |
|---|---|---|
| Windows | `STSong` (default) | `Microsoft YaHei` (default) |
| macOS | `Songti SC` | `PingFang SC` |
| Linux | `Noto Serif CJK SC` | `Noto Sans CJK SC` |

The running header/footer is stamped by the script through PyMuPDF rather than Chrome, so it
needs a **font file** instead of a family name. The script probes the usual locations;
`PDF_TRANSLATION_FONT_DIR` overrides where it looks.

### Why aren't footnotes at the foot of the page?

Chrome has never implemented CSS GCPM's `float: footnote` (`position: running()` only serves
margin boxes). Simulating it with a one-way HTML flow runs into a circular dependency — the
citation's position depends on pagination, which depends on the footnote's height — and can
only be approximated with repeated renders, very fragile. So footnotes are collected at the end
and **two-way links** make up the difference. Real page-foot footnotes need a LaTeX re-typeset,
which is a different toolchain.

### Will the formulas come out wrong?

Mostly not. Deeply nested formulas may differ in characters or line breaks (see item 5 above).
**But that is still far better than flattening to Unicode or cropping to images** — those two
approaches are wrong by construction, not merely sometimes.

---

## Repository layout

```
pdf-translation/
├── SKILL.md                        the pipeline and its design decisions
├── references/
│   └── two-column-paper.md         journal layout: geometry, multicol, overflow criterion
├── scripts/
│   ├── estimate.py                 stage 0 — token and wall-clock estimate
│   ├── probe.py                    stage 1 — page/block/font-size report
│   ├── extract.py                  stage 2 — structure.json + figures at 300 dpi
│   ├── classify.py                 stage 3 — math spans + heading levels
│   ├── fidelity.py                 stage 5 — dropped / untranslated / caption gate
│   ├── typeset.py                  stage 6 — HTML + KaTeX + Chrome → PDF
│   └── compare.py                  measure any two PDFs against each other
└── docs/images/                    screenshots used by the README
```

---

## Known limitations

- **Formula-heavy documents need several iterations.** Fixing one batch of formulas changes
  pagination, which can expose new overflows, so the loop runs to convergence. That is why the
  tool quotes its cost honestly up front.
- **The last page of a column run may be ragged.** Chrome does not balance the final fragment of
  a multi-page multicol that contains tall atomic blocks; there is no CSS fix. Only a LaTeX
  re-typeset solves it properly.
- **Footnotes cannot sit at the page foot** (see the FAQ).
- **Headers and footers are stamped by the script**, not reproduced from the source.

---

## License

[MIT](LICENSE)

Screenshots are from a public IEEE TWC 2026 paper, used only to demonstrate typesetting.
