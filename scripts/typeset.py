# -*- coding: utf-8 -*-
"""Stage 5 - typeset: body.html + design system + KaTeX -> headless Chrome -> stamped PDF.

Usage:
    python typeset.py <workdir> [--out name.pdf] [--no-stamp]

Expects <workdir>/body.html  (the model writes this: cover, TOC, sections).
<a _body>  Placeholders __FIG_<page>_<n>__ are replaced with the cropped figures.

Does four things:
  1. installs KaTeX locally into <workdir> (npm, offline afterwards)
  2. wraps body.html in the design system + KaTeX auto-render
  3. prints to PDF with headless Chrome
  4. stamps running header/footer + metadata, then reports measurements

VERIFY the report: KaTeX_* font chars must be > 0 and overflow spans must be 0.
"""
import sys, os, json, glob, shutil, argparse, subprocess, time

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf missing - pip install pymupdf")


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome():
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------------------
# Fonts — the one genuinely platform-specific part of this skill.
#
# The defaults are the Windows names, because that is where this was developed.
# On macOS and Linux those families do not exist, so the CSS silently falls back
# to a serif that renders CJK badly (or not at all). Override without editing
# this file:
#
#     PDF_TRANSLATION_SERIF="Songti SC"        # macOS body
#     PDF_TRANSLATION_SANS="PingFang SC"       # macOS headings
#     PDF_TRANSLATION_SERIF="Noto Serif CJK SC"   # Linux body
#     PDF_TRANSLATION_SANS="Noto Sans CJK SC"     # Linux headings
#
# PDF_TRANSLATION_FONT_DIR overrides where the *stamp* font file is looked for
# (the running header/footer is drawn by PyMuPDF, not by Chrome, so it needs a
# real font file on disk rather than a CSS family name).
# ---------------------------------------------------------------------------
SERIF_DEFAULT = '"Times New Roman","STSong","SimSun",serif'
SANS_DEFAULT = '"Microsoft YaHei","Segoe UI",sans-serif'

STAMP_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
]


def font_stacks():
    """(serif, sans) CSS font stacks, overridable by environment."""
    return (os.environ.get("PDF_TRANSLATION_SERIF") or SERIF_DEFAULT,
            os.environ.get("PDF_TRANSLATION_SANS") or SANS_DEFAULT)


def find_stamp_font():
    """A real font file for the stamped header/footer, or None."""
    env = os.environ.get("PDF_TRANSLATION_FONT_DIR")
    if env:
        for name in ("msyh.ttc", "PingFang.ttc", "NotoSansCJK-Regular.ttc",
                     "NotoSerifCJK-Regular.ttc", "STHeiti Medium.ttc"):
            p = os.path.join(env, name)
            if os.path.exists(p):
                return p
    for c in STAMP_FONT_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def render_css():
    """The design system with this platform's font stacks substituted in.

    The CSS uses `var(--serif)` / `var(--sans)` everywhere, so each stack has
    exactly one definition; the concrete families arrive here.
    """
    serif, sans = font_stacks()
    return CSS.replace("__SERIF__", serif).replace("__SANS__", sans)


def ensure_katex(workdir):
    """Install KaTeX into the workdir if absent. Returns (css, js, autorender) rel paths."""
    nm = os.path.join(workdir, "node_modules", "katex", "dist")
    if not os.path.exists(os.path.join(nm, "katex.min.js")):
        print("installing katex ...")
        pkg = os.path.join(workdir, "package.json")
        if not os.path.exists(pkg):
            subprocess.run(["npm", "init", "-y", "--silent"], cwd=workdir,
                           capture_output=True, shell=(os.name == "nt"))
        r = subprocess.run(["npm", "install", "katex", "--silent", "--no-audit",
                            "--no-fund"], cwd=workdir, capture_output=True,
                           text=True, shell=(os.name == "nt"))
        if not os.path.exists(os.path.join(nm, "katex.min.js")):
            print(r.stdout[-1500:]); print(r.stderr[-1500:])
            sys.exit("katex install failed")
    return ("node_modules/katex/dist/katex.min.css",
            "node_modules/katex/dist/katex.min.js",
            "node_modules/katex/dist/contrib/auto-render.min.js")


CSS = r"""
:root{
  --ink:#1a2028; --ink-soft:#3d4653; --ink-mute:#78838f;
  --rule:#e2e7ee; --brand:#1f4e79; --brand-lite:#eaf1f8;
  --code-bg:#f7f9fc; --code-bd:#e3e9f1;
  /* Font stacks are substituted at render time from font_stacks(); see the
     environment variables documented above. Never hardcode a family here. */
  --serif:__SERIF__; --sans:__SANS__;
}
@page{ size:A4; margin:20mm 18mm 17mm 18mm; }
*{ box-sizing:border-box; }
html,body{ margin:0; padding:0; }
body{
  font-family:var(--serif);
  font-size:10.5pt; line-height:1.85; color:var(--ink);
  -webkit-print-color-adjust:exact; print-color-adjust:exact;
  text-align:justify; text-justify:inter-ideograph;
}
.sans{ font-family:var(--sans); }
.mono,.mono *{ font-family:Consolas,"Courier New",monospace; }

.cover{ height:250mm; display:flex; flex-direction:column; break-after:page; }
.cover-main{ flex:1; display:flex; flex-direction:column; justify-content:center;
             align-items:center; text-align:center; }
.kicker{ font-family:var(--sans); font-size:9.5pt;
         letter-spacing:.45em; color:var(--brand); margin-bottom:16mm; }
.cover h1{ font-family:var(--sans); font-size:30pt; line-height:1.4;
           font-weight:700; color:var(--brand); margin:0 0 4mm; letter-spacing:.03em; }
.cover .sub{ font-family:var(--sans); font-size:15pt;
             color:var(--ink-soft); letter-spacing:.14em; margin-bottom:3mm; }
.cover .en{ font-size:12pt; color:var(--ink-mute); font-style:italic; }
.cover .hr{ width:54mm; height:2px; background:var(--brand); margin:10mm auto; }
.cover .author{ font-size:14pt; color:var(--ink); }
.cover .course{ font-family:var(--sans); font-size:11pt;
                color:var(--ink-soft); margin-top:3mm; }
.cover .note{ font-size:8.5pt; color:var(--ink-mute); line-height:1.9;
              text-align:center; border-top:1px solid var(--rule); padding-top:4mm; }

h1.chap{ font-family:var(--sans); font-size:18pt; font-weight:700;
         color:var(--brand); margin:0 0 6mm; padding-bottom:2.5mm;
         border-bottom:2.5px solid var(--brand);
         break-inside:avoid; break-after:avoid; }
h2.mod{ font-family:var(--sans); font-size:13pt; font-weight:700;
        color:var(--brand); margin:8mm 0 3mm; padding-left:3.4mm;
        border-left:4px solid var(--brand);
        break-inside:avoid; break-after:avoid; }
h3.sec{ font-family:var(--sans); font-size:11pt; font-weight:700;
        color:var(--ink); margin:5.5mm 0 1.6mm;
        break-inside:avoid; break-after:avoid; }
h3.sec .en{ font-weight:400; font-size:9.5pt; color:var(--ink-mute); margin-left:1.5mm; }
p{ margin:0 0 2.6mm; }
b,strong{ font-family:var(--sans); font-weight:700; color:var(--brand); }
code{ font-family:Consolas,monospace; font-size:.92em; background:var(--brand-lite);
      color:#12456e; padding:.1em .34em; border-radius:3px; }

ul,ol{ margin:0 0 3mm; padding-left:6.5mm; }
li{ margin:0 0 1.3mm; }
li::marker{ color:var(--brand); }

.toc-title{ font-family:var(--sans); font-size:23pt; font-weight:700;
            color:var(--brand); text-align:center; letter-spacing:.3em; margin:4mm 0 2mm; }
.toc-hr{ width:34mm; height:2px; background:var(--brand); margin:0 auto 9mm; }
.toc-part{ font-family:var(--sans); font-size:12pt; font-weight:700;
           color:var(--brand); margin:7mm 0 2.5mm; padding-bottom:1.2mm;
           border-bottom:1px solid var(--rule); }
.toc-part .en{ font-weight:400; font-size:9pt; color:var(--ink-mute); margin-left:2mm; }
.toc-item{ display:flex; align-items:baseline; font-size:10pt; margin:.7mm 0; }
.toc-item .t{ color:var(--ink-soft); }
.toc-item .dots{ flex:1; margin:0 2mm; border-bottom:1px dotted #c6cfda;
                 transform:translateY(-.3em); }
.toc-item .pg{ color:var(--ink-mute); font-size:9pt; }

figure{ margin:5mm 0 5.5mm; text-align:center; break-inside:avoid; }
figure img{ max-width:100%; max-height:290pt; border:1px solid var(--code-bd);
            border-radius:2px; }
figcaption{ margin-top:2.2mm; font-size:8.8pt; line-height:1.7;
            color:var(--ink-mute); text-align:left; }
figcaption .lbl{ font-family:var(--sans); font-weight:700;
                 color:var(--brand); margin-right:.35em; }

pre{ background:var(--code-bg); border:1px solid var(--code-bd);
     border-left:3px solid var(--brand); border-radius:3px;
     padding:3.2mm 3.8mm; margin:3.5mm 0 4.5mm;
     font-family:Consolas,monospace; font-size:8.8pt; line-height:1.66;
     color:#22303c; white-space:pre-wrap; word-break:break-word;
     break-inside:avoid; text-align:left; }
pre .c{ color:#5b8a4a; } pre .k{ color:#0b5ea8; }
pre .s{ color:#a31515; } pre .n{ color:#8250a8; }

.formula{ margin:5mm 0 6mm; text-align:center; break-inside:avoid; }
.formula .katex{ font-size:1.22em; }
.eqno{ color:var(--ink-mute); font-size:9pt; margin-left:8mm; }
.katex{ font-size:1.03em; }

.lead{ color:var(--ink-soft); }
.box{ background:var(--code-bg); border:1px solid var(--code-bd);
      border-left:3px solid var(--brand); border-radius:3px;
      padding:3.4mm 4mm; margin:4mm 0 5mm; font-size:9.6pt;
      line-height:1.78; color:var(--ink-soft); break-inside:avoid; }
.box .h{ font-family:var(--sans); font-weight:700;
         color:var(--brand); display:block; margin-bottom:1.4mm; }
table{ width:100%; border-collapse:collapse; font-size:9pt; margin:4mm 0 5mm; }
thead th{ background:var(--brand); color:#fff; font-family:var(--sans);
          font-weight:700; text-align:left; padding:2.2mm 2.6mm; font-size:9pt; }
tbody td{ padding:2mm 2.6mm; border-bottom:1px solid var(--rule);
          vertical-align:top; line-height:1.65; }
tbody tr:nth-child(even){ background:#fafbfd; }
thead{ display:table-header-group; }
tbody tr{ break-inside:avoid; }
.break{ break-after:page; }
.endnote{ margin-top:6mm; padding-top:3mm; border-top:1px solid var(--rule);
          font-size:9pt; color:var(--ink-mute); text-align:center; }
"""


def build_html(workdir, title):
    body_p = os.path.join(workdir, "body.html")
    if not os.path.exists(body_p):
        sys.exit(f"missing {body_p} - the model writes this in stage 4")
    body = open(body_p, encoding="utf-8").read()
    figs = json.load(open(os.path.join(workdir, "figs.json"), encoding="utf-8"))

    # replace __FIG_<name>__ with the cropped figure. <name> is the figure's
    # filename stem as extract.py wrote it, e.g. __FIG_fig_p6_1__ -> figs/fig_p6_1.png
    import re
    have = set()
    for lst in figs.values():
        for f in lst:
            have.add(f["name"])

    missing = []
    def sub(m):
        stem = m.group(1)
        name = stem if stem.endswith(".png") else stem + ".png"
        if name not in have:
            missing.append(stem)
            return f'<!-- MISSING FIGURE: {stem} -->'
        return f'<img src="figs/{name}" alt="">'
    body = re.sub(r"__FIG_([A-Za-z0-9_.]+)__", sub, body)

    if missing:
        print(f"  WARNING: {len(missing)} figure reference(s) matched no crop:")
        for s in missing:
            print(f"    {s}   (available: {', '.join(sorted(have))})")
    else:
        print(f"  figures    : all {len(have)} referenced crops resolved")

    css, js, ar = ensure_katex(workdir)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="{css}">
<style>{render_css()}</style>
</head>
<body>
{body}
<script src="{js}"></script>
<script src="{ar}"></script>
<script>
  renderMathInElement(document.body, {{
    delimiters: [
      {{left: "$$", right: "$$", display: true}},
      {{left: "$",  right: "$",  display: false}}
    ],
    throwOnError: false
  }});
</script>
</body>
</html>
"""
    out = os.path.join(workdir, "doc.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"wrote html : {out} ({len(html)} bytes)")
    return out


def render(workdir, html, chrome):
    raw = os.path.join(workdir, "_raw.pdf")
    if os.path.exists(raw):
        os.remove(raw)
    url = "file:///" + html.replace("\\", "/")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=15000",     # KaTeX needs this or math stays unrendered
           "--no-pdf-header-footer", f"--print-to-pdf={raw}", url]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    dt = time.time() - t0
    print(f"chrome     : exit={r.returncode} in {dt:.1f}s")
    if not os.path.exists(raw):
        print(r.stderr[-1500:])
        sys.exit("chrome produced no PDF")
    return raw


def stamp(raw, final, title, subtitle):
    doc = pymupdf.open(raw)
    W, H = doc[0].rect.width, doc[0].rect.height
    LEFT, RIGHT = 51.0, W - 51.0
    ttf = find_stamp_font()
    have_font = ttf is not None
    if have_font:
        f = pymupdf.Font(fontfile=ttf)

    def put(page, x, y, text, size, color, right_edge=None):
        if not have_font:
            return
        w = f.text_length(text, fontsize=size)
        if right_edge is not None:
            x = right_edge - w
        page.insert_text(pymupdf.Point(x, y), text, fontname="StampF",
                         fontfile=ttf, fontsize=size, color=color)

    for i, page in enumerate(doc):
        if i == 0:
            continue
        page.draw_line(pymupdf.Point(LEFT, 45.0), pymupdf.Point(RIGHT, 45.0),
                       color=(0.88, 0.90, 0.93), width=0.6)
        put(page, LEFT, 38.5, title, 7.4, (0.44, 0.48, 0.53))
        lab = str(i + 1)
        if have_font:
            put(page, 0, H - 30, lab, 8.4, (0.44, 0.48, 0.53),
                right_edge=W / 2 + f.text_length(lab, fontsize=8.4) / 2)

    doc.set_metadata({"title": title, "subject": subtitle,
                      "author": "translated with pdf-translation"})
    if have_font:
        doc.subset_fonts()
    tmp = final + ".tmp"
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    os.replace(tmp, final)


def measure(final):
    doc = pymupdf.open(final)
    from collections import Counter
    fonts = Counter()
    ovf = 0
    for i in range(doc.page_count):
        r = doc[i].rect
        for b in doc[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if s["text"].strip():
                        fonts[s["font"]] += len(s["text"])
                    x0, y0, x1, y1 = s["bbox"]
                    if x0 < -0.5 or y0 < -0.5 or x1 > r.width + 0.5 or y1 > r.height + 0.5:
                        ovf += 1
    total = sum(fonts.values())
    math_chars = sum(v for k, v in fonts.items()
                     if "KaTeX" in k or "Math" in k or "CMSY" in k or "STIX" in k)
    imgs = sum(len(doc[i].get_images(full=True)) for i in range(doc.page_count))
    cjk = 0
    for i in range(doc.page_count):
        cjk += sum(1 for c in doc[i].get_text() if "\u4e00" <= c <= "\u9fff")
    t3 = sum(v for k, v in fonts.items() if k.startswith("Type3"))

    print()
    print("=== VERIFY (all four must hold) ===")
    print(f"  pages            : {doc.page_count}")
    print(f"  KaTeX/math chars : {math_chars}   {'OK' if math_chars > 0 else 'FAIL - math is NOT vector-set'}")
    print(f"  overflow spans   : {ovf}   {'OK' if ovf == 0 else 'FAIL - content past page edge'}")
    print(f"  CJK chars        : {cjk}   {'OK' if cjk > 0 else 'FAIL - fonts not embedded'}")
    print(f"  embedded images  : {imgs}")
    if t3:
        print(f"  Type3 glyph chars: {t3}   (warning: may be a non-embeddable font)")
    print()
    print("  top fonts:")
    for k, v in fonts.most_common(10):
        print(f"    {k:32} {v}")
    return math_chars, ovf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default="中文翻译版")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--no-stamp", action="store_true")
    a = ap.parse_args()

    wd = a.workdir
    final = os.path.join(wd, a.out or "translated.pdf")

    chrome = find_chrome()
    if not chrome:
        sys.exit("no Chrome/Edge found - set CHROME_PATH")
    print(f"chrome     : {chrome}")

    html = build_html(wd, a.title)
    raw = render(wd, html, chrome)
    if a.no_stamp:
        shutil.copy(raw, final)
    else:
        stamp(raw, final, a.title, a.subtitle)
    print(f"saved      : {final} ({os.path.getsize(final)/1e6:.2f} MB)")
    measure(final)


if __name__ == "__main__":
    main()
