#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""estimate.py — 翻译前的工作量预估：token 与耗时。

为什么要有这个脚本：
    用户在第 0 阶段就要决定「只出 md」还是「出 PDF」。这个决定取决于成本，
    而成本取决于文档规模。靠感觉报数字没有意义，所以这里**实测**源文的
    页数 / 英文词数 / 图数 / 公式密度，再套用标定过的系数。

系数怎么来的（参考案例实测，不是猜的）：

  案例 A  Disco Intelligent Omni-Surfaces, IEEE TWC 2026（公式密集）
          14 页 / 9,932 英文词 / 73 编号公式 / 6 图 / 2 表 / 46 参考文献
          译文 18 页 / 9,329 汉字（参考文献按原样保留，不计入翻译量）
          ⇒ **汉字数 ≈ 英文词数 × 0.94**

  案例 B  Stanford CS231n 讲义（纯文字，代码多）
          191 页 / 50,529 英文词 / 82 图 / 0 编号公式
          译文 155 页 / 73,288 汉字 / 133 条外链
          实测增量（会话日志，相对开工前基线）：
            273 次 API 调用 / 输入 1,519,033 / 输出 222,496
            合计 41,162,585（其中绝大部分是缓存读）
            墙钟 ≈ 29 分钟 —— 走的是 13 个并行子 agent

token 系数按三段相加：
  · 译文产出     ≈ 英文词 × 4.3    （汉字 + HTML 标记 + 推理 token）
  · 读源文       ≈ 英文词 × 29     （逐页读结构，且每轮都重读上下文）
  · 排版迭代     ≈ 上两项之和 × (0.3 ~ 1.2)
                  公式密集（每页 ≥4 个编号公式）取上限，
                  纯文字取下限 —— 公式越栏要反复「渲染→量→改」，
                  实测每一轮就是一次全量重排。

⚠ 成本的主导项**不是译文长度，而是轮次 × 上下文大小**。案例 B 的 41M
  合计里有 39M 是缓存读：13 个子 agent 各自反复读自己的上下文。
  所以「翻倍页数」远不止翻倍 token，而「拆成并行批次」能在总 token 基本
  不变的前提下把墙钟时间压掉一大截。预估时把这两个数分开看。

用法：
    python estimate.py <input.pdf> [--json out.json]
"""
import argparse
import json
import re
import sys

# 标定系数（见模块 docstring，参考案例实测）
CJK_PER_WORD = 0.94          # 汉字数 / 英文词数
OUT_PER_WORD = 4.3           # 译文产出 token / 英文词（含标记与推理）
READ_PER_WORD = 29.0         # 读源文 token / 英文词（含每轮重读上下文）
ITER_LIGHT = 0.3             # 排版迭代系数下限（纯文字）
ITER_HEAVY = 1.2             # 排版迭代系数上限（公式密集）

EQ_PER_PAGE_HEAVY = 4        # 每页编号公式数 ≥ 此值算「公式密集」

# 耗时：以「模型生成译文」为主。
#
# ⚠ 这里曾经标定错过一次，教训值得留着：
#   第一版把每页耗时定成 2.5–5.0 分钟，而那个数字是从参考案例的**全程**
#   反推的 —— 那次包含 9 轮用户反馈和大量调试。拿"含返工的时长"去外推
#   新文档，会给出 191 页 = 6–11 小时这种荒谬结论。
#
#   正确的做法是把「干净首轮」和「每轮返工」分开算：
#     干净首轮  ≈ 页数 × 每页生成时间 + 固定开销（抽取/渲染）
#     每轮返工  ≈ 页数 × 很小的系数（只重渲，不重译）
#
#   每页生成时间的依据：
#     案例 B（191 页纯文字）实测墙钟 29 分钟，走的是 13 个并行子 agent，
#     ⇒ 并行时约 0.15 分钟/页。串行单 agent 要慢得多，因为每页都要把上下文
#     重新读一遍，取 0.5 分钟/页。所以这里给的是**并行**口径，串行请自行上调。
#     公式密集文档额外要反复「渲染→量→改」，再加一档。
MIN_PER_PAGE_LIGHT = 0.15    # 分钟/页，纯文字，并行批次
MIN_PER_PAGE_HEAVY = 0.45    # 分钟/页，公式密集，并行批次
MIN_PER_PAGE_SERIAL = 0.50   # 分钟/页，串行单 agent（仅作上限提示）
FIXED_OVERHEAD_MIN = 5       # 抽取 + 首次渲染的固定开销

REVISION_FACTOR = 0.35       # 每轮返工 = 干净首轮 × 此系数（只重渲 + 局部重译）


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
    base_min = FIXED_OVERHEAD_MIN + pages * rate
    mins_lo, mins_hi = base_min, base_min * 1.6
    # Serial single-agent path, for when the document is not fanned out.
    serial_min = FIXED_OVERHEAD_MIN + pages * (
        MIN_PER_PAGE_SERIAL * (1.6 if heavy else 1.0))

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
        "estimated_minutes_serial": [int(serial_min), int(serial_min * 1.6)],
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
    print(f"  预计耗时      : {m[0]} – {m[1]} 分钟   （并行批次，干净首轮）")
    s = r["estimated_minutes_serial"]
    print(f"                  {s[0]} – {s[1]} 分钟   （串行单 agent，作上限参考）")
    render_revision(r)
    print()
    print("  系数标定自两个参考案例实测（不是估的）：")
    print("    A  IEEE TWC 2026  14 页 / 9,932 词 / 73 式（公式密集）")
    print("    B  CS231n 讲义   191 页 / 50,529 词 / 82 图 / 0 式（纯文字+代码）")
    print("    汉字数 ≈ 英文词数 × 0.94")
    print("    token  = 产出(×4.3) + 读源文(×29) + 排版迭代")
    print()
    print("  ⚠ 0.94 是从案例 A 标定的，案例 B 实测 1.45/词（73,288 汉字）。对")
    print("    「散文 + 代码/图注」的讲义类文档，上面的汉字数请当**下限**读。")
    print()
    print("  ⚠ 成本主导项是**轮次 × 上下文大小**，不是译文长度。案例 B 的合计")
    print("    token 里绝大部分是缓存读 —— 页数翻倍远不止 token 翻倍，而拆成")
    print("    并行批次能在总 token 基本不变的前提下把墙钟时间压掉一大截。")
    print()
    print("  ⚠ 这是**干净首轮**的估算（一次成型，不含返工）。")
    print("    每追加一轮修改意见，约增加 %.0f%% 的时间 —— 那一轮只重渲染和" % (REVISION_FACTOR * 100))
    print("    局部重译，不需要从头再来。参考案例共经历 9 轮反馈，所以它实际")
    print("    花掉的时间远高于此表；但那是**返工**，不是**首轮**。")


def render_revision(r):
    """Print the marginal cost of one more revision round."""
    m = r["estimated_minutes"]
    extra_lo = m[0] * REVISION_FACTOR
    extra_hi = m[1] * REVISION_FACTOR
    print(f"  单轮返工追加  : {extra_lo:.0f} – {extra_hi:.0f} 分钟")


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
