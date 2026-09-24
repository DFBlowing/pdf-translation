# Translation Cases

Two **layout demonstrations**, each an English original paired with its Chinese translation — what this
skill actually produces from a real paper.

> **These files are large (~36 MB total), so they are not committed to git.** They live on a GitHub Release:
>
> **[⬇ Download both cases (release `cases-v1`)](https://github.com/DFBlowing/pdf-translation/releases/tag/cases-v1)**
>
> | Archive | Size | Contents |
> |---|---|---|
> | `case1-disco-en-zh.zip` | 5.4 MB | Disco paper: 14-page original + 18-page translation |
> | `case2-cs231n-en-zh.zip` | 29.2 MB | CS231n notes: 191-page original + 155-page translation |
>
> Each archive holds `01-原文-EN.pdf`, `02-译文-ZH.pdf`, and a copyright notice.
> The translation in the archive is a **lossless export** (images at half resolution, still PNG/Flate,
> ~110 dpi), which is why it is 21 MB rather than the 65 MB full-quality file produced locally —
> layout, text and links are identical, only the figure pixels are fewer.

---

## Case 1 — Disco Intelligent Omni-Surfaces (formula-heavy, two-column journal paper)

| | |
|---|---|
| Original | 14 pages · 9,652 English words · 72 numbered equations · 6 figures · 2 tables · 46 references |
| Translation | 18 pages · 9,329 CJK characters · 259 clickable links |

An IEEE two-column layout. The point of this case is **formulas**:

- All 73 equations are **re-typeset with KaTeX** — real vector fonts (`KaTeX_Math-Italic` and friends as
  font subsets), not cropped bitmaps and not Unicode character soup. So they scale, they align, and they print.
- The **column-overflow criterion** hit two traps here: the first filter silently missed the class of
  overflow that only grazed the column boundary. Fixing the criterion took the same document from
  "0 overflows" to "16 overflows" — the original number was wrong, not the document.
- Reference markers `[n]` are the **cross-layout-stable anchor**: citations and the bibliography link both
  ways, with no dangling anchors.

## Case 2 — Stanford CS231n notes (prose + a lot of code)

| | |
|---|---|
| Original | 191 pages · 50,529 English words · 82 figures · 0 numbered equations |
| Translation | 155 pages · 73,288 CJK characters · 133 external links + 17 TOC/footnote jumps |
| Measured wall clock | ~**29 minutes** (13 parallel subagents) |
| Measured output | **222,496** tokens |

A single-column course handout. The point of this case is **scale**, **code blocks** and **links**:

- 191 pages were split across **13 parallel batches**. That is what took wall-clock time from "hours" to
  "half an hour" — the cost driver is **turns × context size**, not translation length.
- **Code is preserved verbatim**; only prose is translated. A reader can copy the code and run it.
- 82 figures kept their positions; **51 of them carry a numbered caption** (图 1–51, contiguous, no
  gaps). The 20 whose source figure had no caption stay captionless — no invented number, no invented
  description.
- All **251** source link annotations were aligned one by one: 66 site-chrome dropped, 52 already
  present, 66 restored, **67 unplaceable and reported as such** (their visible text had been fully
  translated with no Latin trace left). The delivery carries 133 external links. See "Links and
  navigation are content" in the repository README.

### ⚠️ A defect in the source file itself

This PDF was produced from HTML with `overflow: hidden` code boxes, and the detector reports **73 lines
of code clipped against the box edge** in the source (across 42 pages):

```
hidden_layer = np.maximum(0, np.dot(X, W) + b) # note, ReLU activ
                                                              ↑ this is the box edge
```

**The missing characters do not exist anywhere in the PDF** — no extraction tool can recover them. This
is not a parsing failure.

The translation **heals them from the official upstream notes**, inventing nothing and leaving no
disclaimer behind:

- Of 72 candidates, **65 are provably healed** — the test is that the output contains **characters the
  source does not hold** (`# get the gradi` → `# get the gradient`). A plain substring test cannot see
  this: the severed fragment is a *prefix* of the healed text, so `in` reports success as failure.
- The remaining candidates are detector false positives (a line that happens to end on a complete word).
  Each was read by hand and all are healed too — the line `x[ix] = old_value # restore to previous value
  (very important` looks complete and is not; its parenthesis never closes.
- **No "text missing in the original" note survives anywhere in the delivered document.** Marking each
  site is not disclosure, it is an unfixed document.

---

## Copyright

The **originals** remain the property of their authors and publishers:

- *Disco Intelligent Omni-Surfaces: 360° Fully-Passive Jamming Attacks* — © **IEEE** and the authors
  (IEEE Transactions on Wireless Communications)
- *CS231n: Convolutional Neural Networks for Visual Recognition* — © **Stanford Vision Lab** and the authors

The **translations** were generated automatically by this tool and are provided for **study, research and
technical demonstration only**. No commercial use. This repository **claims no rights** over either the
originals or the translations, and **derives no revenue** from them.

**If any of these files infringes your rights, please open an
[Issue](https://github.com/DFBlowing/pdf-translation/issues) or email zzdf176@gmail.com and I will remove
them immediately — my sincere apologies.**
