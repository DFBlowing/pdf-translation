#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""estimate.py — 翻译前的工作量预估：token 与耗时。

为什么要有这个脚本：
    用户在第 0 阶段就要决定「只出 md」还是「出 PDF」。这个决定取决于成本，
    而成本取决于文档规模。靠感觉报数字没有意义，所以这里**实测**源文的
    页数 / 英文词数 / 图数 / 公式密度，再套用标定过的系数。

系数怎么来的（参考案例实测，不是猜的）：
    源文  Disco Intelligent Omni-Surfaces, IEEE TWC 2026
          14 页 / 9,932 个英文词 / 73 个编号公式 / 6 图 / 2 表 / 46 条参考文献
    译文  18 页 / 9,329 个汉字（参考文献按原样保留，不计入翻译量）
    ⇒ **汉字数 ≈ 英文词数 × 0.94**

    token 系数按三段相加（都在参考案例上对过）：
      · 译文产出     ≈ 英文词 × 1.3   （汉字 + HTML 标记 + KaTeX）
      · 读源文       ≈ 英文词 × 2.0   （逐页读结构，含重读）
      · 排版迭代     ≈ 上两项之和 × (0.3 ~ 1.2)
                      公式密集（每页 ≥4 个编号公式）取上限，
                      纯文字取下限 —— 公式越栏要反复「渲染→量→改」，
                      实测每一轮就是一次全量重排。

用法：
    python estimate.py <input.pdf> [--json out.json]
"""
import argparse
import json
import re
import sys

# 标定系数（见模块 docstring，参考案例实测）
CJK_PER_WORD = 0.94          # 汉字数 / 英文词数
OUT_PER_WORD = 1.3           # 译文产出 token / 英文词
READ_PER_WORD = 2.0          # 读源文 token / 英文词
ITER_LIGHT = 0.3             # 排版迭代系数下限（纯文字）
ITER_HEAVY = 1.2             # 排版迭代系数上限（公式密集）

EQ_PER_PAGE_HEAVY = 4        # 每页编号公式数 ≥ 此值算「公式密集」

# 耗时：以「模型写正文」为主，渲染轮次为辅。参考案例一次完整流水线
# （3 轮渲染 + 每轮量测）约 4 分钟，模型写作占大头。
MIN_PER_PAGE_LIGHT = 2.5     # 分钟/页，纯文字
MIN_PER_PAGE_HEAVY = 5.0     # 分钟/页，公式密集


def measure(pdf):
    import pymupdf
    doc = pymupdf.open(pdf)
    words = 0
    images = 0
    eqnos = 0
    for i in range(doc.page_count):
        pg = doc[i]
        txt = pg.get_text()
        words += len(re.findall(r"[A-Za-z][A-Za-z\-']+", txt))
        images += len(pg.get_images(full=True))
        # 编号公式：行尾/行首的 (12) —— 与正文引用 (12) 的区别是它独占一行右侧
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if re.fullmatch(r"\(\d{1,2}\)", t):
                    eqnos += 1
    return doc.page_count, words, images, eqnos


def estimate(pdf):
    pages, words, images, eqnos = measure(pdf)
    if pages == 0:
        raise SystemExit("PDF 没有页面")
    eq_per_page = eqnos / pages
    heavy = eq_per_page >= EQ_PER_PAGE_HEAVY

    cjk = int(words * CJK_PER_WORD)
    out_tok = words * OUT_PER_WORD
    read_tok = words * READ_PER_WORD
    base = out_tok + read_tok
    lo = base * (1 + ITER_LIGHT)
    hi = base * (1 + ITER_HEAVY)
    if not heavy:
        hi = base * (1 + ITER_LIGHT * 1.6)      # 纯文字不会迭代太多

    rate = MIN_PER_PAGE_HEAVY if heavy else MIN_PER_PAGE_LIGHT
    mins_lo, mins_hi = pages * rate * 0.8, pages * rate * 1.4

    def k(n):
        return f"{n/1000:.0f}k"

    return {
        "pdf": pdf,
        "pages": pages,
        "english_words": words,
        "images": images,
        "numbered_equations": eqnos,
        "equations_per_page": round(eq_per_page, 1),
        "formula_heavy": heavy,
        "estimated_cjk_chars": cjk,
        "estimated_output_tokens": [int(out_tok), int(out_tok * 1.5)],
        "estimated_input_tokens": [int(read_tok), int(read_tok * 1.8)],
        "estimated_total_tokens": [int(lo), int(hi)],
        "estimated_minutes": [int(mins_lo), int(mins_hi)],
        "_k": {"out": k(out_tok), "read": k(read_tok), "lo": k(lo), "hi": k(hi)},
    }


def render(r):
    heavy = "是" if r["formula_heavy"] else "否"
    m = r["estimated_minutes"]
    t = r["estimated_total_tokens"]
    print("=" * 56)
    print("  翻译工作量预估")
    print("=" * 56)
    print(f"  源文件        : {r['pdf']}")
    print(f"  页数          : {r['pages']}")
    print(f"  英文词数      : {r['english_words']:,}")
    print(f"  图片对象      : {r['images']}"
          f"  （原始 XObject 数，一张图常由多个拼成）")
    print(f"  编号公式      : {r['numbered_equations']}"
          f"  （{r['equations_per_page']}/页，公式密集：{heavy}）")
    print()
    print(f"  译文汉字数(估): 约 {r['estimated_cjk_chars']:,}")
    print(f"  产出 token    : {r['_k']['out']} – "
          f"{r['estimated_output_tokens'][1]/1000:.0f}k")
    print(f"  输入 token    : {r['_k']['read']} – "
          f"{r['estimated_input_tokens'][1]/1000:.0f}k")
    print(f"  合计 token    : {r['_k']['lo']} – {r['_k']['hi']}")
    print(f"  预计耗时      : {m[0]} – {m[1]} 分钟")
    print()
    print("  系数标定自参考案例（IEEE TWC 2026, 14 页 / 9,932 词 / 73 式）:")
    print("    汉字数 ≈ 英文词数 × 0.94")
    print("    token  = 产出 + 读源文 + 排版迭代")
    print()
    print("  ⚠ 这是**首次生成**的估算。用户每提一轮修改意见，就要重跑一次")
    print("    渲染-量测循环，成本按轮次线性叠加。公式密集的文档尤其如此 ——")
    print("    参考案例共经历 9 轮反馈，实际消耗远高于此表。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    r = estimate(a.pdf)
    render(r)
    if a.json:
        json.dump(r, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
