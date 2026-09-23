# Two-column academic papers (IEEE / ACM / Elsevier)

The main `SKILL.md` pipeline was distilled from a **single-column textbook**. A two-column
journal paper is a different layout problem, and this file is the whole of what was learned
making one work. Read it before typesetting any paper whose source has two columns.

Reference case: *Disco Intelligent Omni-Surfaces: 360° Fully-Passive Jamming Attacks*,
IEEE TWC 2026, 14 pages, two columns, 73 equations, 46 references, 6 figures, 2 tables.

---

## 0. Ask these two questions before anything else

Do not infer the answers from the source and do not default. Ask, in Chinese, and wait:

1. **正文要单栏还是双栏？** — the layout of the translated body.
2. **图片要单栏还是双栏？** — how figures are placed.

Both are independent of what the source does. A reader may want the source's two columns
reproduced faithfully, or may want single-column because it is easier to read on a tablet.
For a two-column body, also confirm whether figures should **span both columns** (as in the
source) or sit **inside one column**.

Record the answers at the top of the workdir's `NEXT.md` so a later session does not re-ask.

> Why this is a gate rather than a preference: the column decision changes the **CSS
> architecture** (see §2), the **figure markup**, and the **overflow criterion** (§4).
> Retrofitting it means re-running the whole translate → typeset → verify loop.

---

## 1. Measure the source's columns first

Never assume the gutter position. On a 594.96 × 841.92 pt page (US Letter at 72 dpi, the
IEEE default) the reference case measured:

| Quantity | Value |
|---|---|
| Left column | x 51.0 – **291.1** |
| Right column | x **304.4** – **544.5** |
| Column width | **240.1 pt** |
| Content width (both columns) | **493.5 pt** |
| Gutter | 13.3 pt |

Get these from the source's own text bboxes — histogram the left/right edges of body-text
lines on a few full pages. **Do not copy the numbers above to another paper**; margins and
column counts differ.

Two derived numbers drive everything downstream:

- `COL_SPLIT` — the x that separates "left column" from "right column". Use the gutter's
  midpoint (300.0 here), and classify a line by its **right edge** (`x1 <= COL_SPLIT` → left)
  or **left edge** (`x0 >= COL_SPLIT` → right). Classifying by `x0 < COL_SPLIT` alone is
  wrong: a wide centred display formula in the *right* column can have `x0 < COL_SPLIT`.
- The **outer margin** beyond the right column (594.96 − 544.5 ≈ 50 pt). Overflow into it is
  cosmetic; overflow from the left column into the right column is a **visible collision**.

---

## 2. The column architecture: one multicol per text run

**Do not put `column-count:2` on the whole article.** Chrome breaks a multicol wherever a
`column-span:all` element appears, and then fills each resulting "column row"
**sequentially**, not balanced — left column to the bottom, then right. The visible symptom is
a **blank right column** after every cross-column figure, with later figures pushed down.
`column-fill:balance` on the container does **not** fix it; Chrome ignores it here.

Instead, wrap each **run of non-spanning blocks** in its own `<div class="colseg">`:

```css
.paper.two-col .colseg { column-count: 2; column-gap: 7mm; }
```

Spanning blocks (full-width figures, tables, abstract, footnotes, references, bios) stay as
plain full-width siblings *between* the colsegs. Each colseg then balances internally, and
because a short colseg is short, the following spanning element can be pulled onto the same
page — which is exactly what "get rid of the blank column" means.

Implement it as a tag-depth scanner over the body's top-level children, with an explicit
span-all class set. Two bugs to avoid, both hit in practice:

- **Re-attach the document suffix.** Building `body = prefix + segments + suffix` with a
  regex whose group stopped at the first inner `</div>` silently dropped everything after the
  last `</section>` — and the injected `<style>` block lives there, so the figure CSS
  disappeared and paired subplots stacked vertically.
- **Split the run at an in-column table.** A long run that ends mid-page is what leaves the
  blank; cutting it immediately before a **single-column** table (`figure.tblwrap` without
  `span-all`) gave the best result measured (page 6 went from 780/246 to 789/786, i.e. full).
  Splitting at section headings instead made things *worse* (14 → 16 pages, new gaps).

### What does not work — all measured, do not retry

| Attempt | Result |
|---|---|
| `column-fill:balance` on the whole article | no effect (Chrome ignores it after a span) |
| `break-inside:avoid` removed from `.formula` | no effect (KaTeX display is unbreakable inline-block) |
| replacing every display formula with a placeholder | balancing still unstable |
| `break-before:column` to force a balanced last fragment | **worse** — the last fragment becomes page-height and the next spanning block is always pushed to a new page |
| splitting at every `h2` | 14 → 16 pages, new gaps |

### Balancing is still imperfect

A multi-page multicol's **last fragment** is not guaranteed balanced, and tall
`break-inside:avoid` blocks defeat balancing badly (synthetic test: plain paragraphs →
480/468; with twelve 150 pt atomic blocks → 380/225). In the reference case the final body
page keeps a ragged bottom of ~190 pt. That is a Chrome limitation, not a bug in your CSS;
say so rather than chasing it. Only a LaTeX re-typeset fixes it.

---

## 3. Figures: match the source's own span

Decide each figure by measuring the **source's** image bbox, not by taste:

- Source figure occupies roughly one column width (≈240 pt) → keep it **single-column**.
- Source figure has `(a)` in the left column and `(b)` in the right, caption across both →
  make it **cross-column**, each subplot filling one column.

Cross-column pair markup that measured exactly on the column edges (51.0–290.9 /
304.6–544.4):

```css
figure.pair { column-span: all; display: flex; flex-wrap: wrap;
              justify-content: space-between; align-items: flex-start;
              margin: 5mm 0 5.5mm; break-inside: avoid; }
figure.pair img { flex: 0 0 48.6%; border: 0; }
```

`48.6%` is derived, not guessed: 493.5 pt × 0.486 = 239.9 pt ≈ the 240.1 pt column width.

Two traps:

- **`border: 0` is needed.** A template `figure img { border: 1px solid … }` survives
  downsampling as a fake dashed line and a grey halo around each subplot.
- **Keep a general `figure.span-all` class** as well, so any figure can be made cross-column
  without new CSS.

When the user asks for "all figures two-column", still check the source: a figure that the
source itself sets in one column becomes a distorted half-scale image if you force it across.

---

## 4. Formula overflow: the criterion is where the bugs live

This is the single highest-risk part. Get the criterion wrong and the pipeline reports
success while the user sees a formula printed over the neighbouring column.

### The criterion

For every text block whose fonts include `KaTeX`, compare its **right edge** to the right edge
of **the column it is in**:

```
col   = 0 if x0 < COL_SPLIT else 1
edge  = COL_LEFT_EDGE if col == 0 else COL_RIGHT_EDGE
over  = x1 - edge          # > tol ⇒ overflow
```

Exclude genuine cross-column elements by **width**:

```python
if x1 - x0 > 380:      # ≈ content width; cross-column tables/figures are ~425–493 pt
    continue
```

**Never** write the filter as `x0 < COL_SPLIT and x1 > COL_LEFT_EDGE + 40`. That was the
shipped bug: a left-column formula overflowing by exactly 40 pt has `x1 > 331.1`, so it was
classified as a "cross-column table" and **skipped**. The reference case's equation (42)
overflowed 40.2 pt straight into the right column's text, and the loop reported
`overflowing equations: 0` for it. A single-column formula is only ~240 pt wide even when it
overflows, so width is the reliable discriminator.

### Severity differs by column

- **Left-column overflow → collides with the right column's text. Always fix.**
- **Right-column overflow → lands in the outer margin. Fix above ~6 pt; below that it is
  invisible and not worth extra page breaks.**

Encode that split, so a 3 pt right-margin residual is reported as a warning instead of either
silently passing or pointlessly failing.

### Keep one implementation

The pipeline and the standalone measurement tool each had their own copy of the criterion and
**drifted**: only one was fixed, and the pipeline kept the old filter. Have the pipeline
`import` the measurement module (via `importlib`, since the filename has hyphens) rather than
duplicating it.

### Convergence must be honest

A repair round marks an equation, rebuilds it in wrapping mode, and re-renders. It is possible
for a marked equation to **still** overflow. The loop must not treat "no *new* problems" as
"no problems": check the residual set against the marked set and fail loudly if a *severe*
overflow survives. The shipped version printed `收敛` while `(29)` still overflowed 3.3 pt.

### Residual-overflow tooling

`validate-math.py` is the syntax gate: **KaTeX failing to parse emits the raw TeX into the
page**, which is worse than overflow and passes every other check. Always run it before
rendering.

Large KaTeX delimiters (`\left(`, `\right]`) are **filled vector paths**, not text — they are
invisible to text-layer APIs. Any overflow check that reads only `get_text()` will miss them;
intersect `get_drawings()` rectangles as well.

---

## 5. Tables

Measure the source's table bbox and decide the same way as figures:

- Table spans both columns in the source (e.g. 425 pt wide) → `span-all`.
- Table fits one column (e.g. 175 pt) → keep it in-column, and it doubles as a colseg split
  point (§2).

Styling notes that came from user review:

- **Header row must be black**, not the template's brand colour — a coloured header on a
  reproduced paper table reads as decoration and hides the text.
- **No cross-column background divider.** A `border-bottom` on a `span-all` table's container
  draws a rule across the whole page; scope background/border rules to the table itself.
- Source tables are often **vector outlines with an empty text layer**. Rebuild the cells from
  `get_drawings()` grid lines rather than expecting `get_text()` to return them.

---

## 6. Headings must not be orphaned

A heading at the foot of a column, with its paragraph on the next, is the defect users notice
first. Fix it in the base stylesheet, not per-document:

```css
h1.chap, h2.mod, h3.sec { break-inside: avoid; break-after: avoid; }
```

Verify it mechanically: for each column, take the last text line and flag the page if its font
is the heading font (bold YaHei at the heading size). Expect zero hits.

---

## 7. Verification checklist for a two-column build

Run all of these; each has caught a real defect in the reference case.

| Check | Target |
|---|---|
| equation numbers 1..N present | N/N |
| references 1..M present | M/M |
| CJK characters in the bibliography region | **0** (references are reproduced verbatim, not translated) |
| `$$` / `MISSING` / `U+FFFD` residue | 0 |
| internal links + dangling anchors | dangling **0** |
| text past the right column edge | 0 severe |
| formula-number vs formula-body overlap | 0 |
| **formula block overflow past its column** | 0 severe (see §4) |
| `[n]` citation markers carrying a link rect | 100% |
| heading as the last element of a column | 0 |

`[n]` coverage is worth checking separately: **Chrome silently drops link annotations** when a
layout change moves a citation to the very top line of a page. The HTML anchors are all
present; the PDF annotations are not. Repair them on the finished PDF by locating `id="ref-N"`
from the HTML — do not re-run the whole pipeline for it.

---

## 8. Housekeeping

Never leave the intermediate PDFs behind. A full-document run produces one PDF per round; the
reference case accumulated 38 files / ~98 MB before cleanup. Keep only the HTML and the
scripts — every intermediate PDF is reproducible from the run commands — and move the finished
PDF wherever the user wants it to live.

