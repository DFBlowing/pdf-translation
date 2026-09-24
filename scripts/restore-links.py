# -*- coding: utf-8 -*-
"""Restore the source's content hyperlinks into the assembled body.

Reference case (CS231n lecture notes): the source carries 251 unique URI annotations
and only 67 reached the first delivery, because the first-30-page sample had its links
hand-written into the sample builder while the five batch fragments were never given the
link inventory at all. The numbers are that case's; the cause is general, and it is the
one this script exists to undo. See "Links and navigation are content" in SKILL.md.

Policy
------
* Site chrome is dropped, exactly like the grey running header (`#ababab`) was:
  `github.com/cs231n` / `twitter.com/cs231n` / `mailto:karpathy@cs.stanford.edu`
  repeat on every chapter's last page, and `cs231n.github.io/` repeats as the
  chapter-title link on every chapter's first page. 66 of the 251.
  A translation is not a website; the reference `ku` carries no site chrome.
* Every other annotation is a content link and is restored.

Location -- four attempts, recorded because each failure was instructive
------------------------------------------------------------------------
Both documents follow the same reading order, so v1 walked the output with one
forward cursor. It restored 14 of 136:

  * one wrong match poisons the cursor, which then skips everything after it;
  * worse, the walk died on its FIRST element -- the sample's front matter was
    hand-written in a different order from the source's, so `cs231n.stanford.edu`
    matched the same URI near the END of the document (byte 140669). A greedy
    walk cannot survive a local reordering.

v2 used an LCS over the URI sequence -- correct for the reordering (46 pinned),
but then **windows collapsed**: the chapter-title link recurs once per chapter,
so LCS matched a LATE source occurrence against an EARLY output one and capped
every window's right edge near the front matter.

v3 dropped windows for an interpolated *expected* position, and restored 0. The
cause was a silent parity bug: `re.split(r"(<[^>]+>)", ...)` leaves text at even
indices only while the file does not begin with a tag, and the loop tested the
parity the wrong way round -- so it searched the MARKUP, not the prose. It found
`figure` inside `<figure class=...>` and would have spliced `<a>` into the tag.
Nothing was written, because `--apply` had not been passed. Detect a tag by
`s.startswith("<")`, never by parity.

v4 (this one) fixes that and adds a **bootstrap**: the links restored in one
round become pins for the next, which tightens the interpolated prior around the
middle of the document -- the region the batches left link-free, where the
linear prior was off by up to 14 kB. The tolerance shrinks each round.

Usage
-----
    python restore-links.py --body <body.html> --links <source-links.json>           # dry run
    python restore-links.py --body <body.html> --links <source-links.json> --review  # + context
    python restore-links.py --body <body.html> --links <source-links.json> --apply   # rewrite
    python restore-links.py --body <body.html> --links <source-links.json> --diag    # diagnostics

    `--body` and `--links` default to ./full/body.html and ./source-links.json, the names
    the rest of the pipeline uses. Nothing is written without `--apply`, and `--apply` is
    idempotent: a link already in place is found and left alone, so a re-run restores 0.
"""
import json, os, re, sys
from collections import Counter

R = os.path.dirname(os.path.abspath(__file__))


def argval(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


BODY = argval("--body", os.path.join(R, "full", "body.html"))
LINKS = argval("--links", os.path.join(R, "source-links.json"))

CHROME = {
    "https://github.com/cs231n",
    "https://twitter.com/cs231n",
    "mailto:karpathy@cs.stanford.edu",
    "http://cs231n.github.io/",       # chapter-title link, once per chapter page
}
ROUNDS = [(20000, "round 1 (prior wide)"),
          (11000, "round 2 (bootstrapped)"),
          (7000, "round 3 (tightened)")]

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9._\-/+#'()]{4,}")
STOP = {
    "should", "would", "could", "these", "those", "there", "their", "which",
    "where", "while", "about", "other", "using", "before", "after", "first",
    "second", "called", "because", "between", "however", "instead", "following",
    "example", "function", "output", "number", "values", "value", "input",
    "layer", "layers", "gradient", "https", "http", "index", "html", "papers",
    "paper", "report", "review", "pdf", "wiki", "notes", "course", "chapter",
    "section", "figure", "table", "image", "images", "works", "given", "point",
    "points", "shown", "also", "more", "most", "some", "such", "than", "that",
    "this", "with", "from", "into", "each", "them", "they", "when", "will",
    "your", "have", "here", "very", "well", "make", "made", "used", "uses",
    "like", "just", "only", "over", "same", "then", "were", "what", "much",
}


def anchor_tokens(anchor):
    """Distinctive Latin tokens, best first, plus their sub-parts.

    `p-norm.` and `CS229ref,` are single extraction tokens that never appear in
    the Chinese body, but their parts do (`norm`, `CS229`), so expand on
    punctuation and camelCase boundaries.
    """
    keep, seen = [], set()

    def add(t):
        tl = t.lower().strip(".-")
        if len(tl) < 4 or tl in STOP or t in seen:
            return
        seen.add(t)
        keep.append(t)

    for t in TOKEN.findall(anchor):
        add(t)
        for part in re.split(r"[.\-_/'’]+|(?<=[a-z0-9])(?=[A-Z])", t):
            if part and part != t:
                add(part)
    keep.sort(key=lambda t: (-(any(c.isupper() for c in t) or any(c.isdigit() for c in t)),
                             -len(t)))
    return keep


def phrase_probes(anchor):
    """Whitespace-flexible regexes for the anchor, longest first.

    Paper titles survive verbatim inside the Chinese text -- the output reads
    `《深度网络真的需要深吗？》（Do Deep Nets Really Need to be Deep?）` -- so an
    exact phrase hit is both the most accurate match and the best span to wrap.
    Matching only the token `Nets` there would have linked the WRONG title:
    three different source links all collapsed onto that one phrase.
    """
    words = [w for w in re.sub(r"\s+", " ", anchor).strip().split(" ") if w]
    words = [w.strip(",;") for w in words]
    out = []
    if len(words) >= 3:
        for n in (len(words), 8, 6, 5, 4, 3):
            if n > len(words) or n < 3:
                continue
            for s in range(0, len(words) - n + 1):
                probe = " ".join(words[s:s + n]).strip(" .,;:")
                if len(probe) < 14:
                    continue
                rx = r"\s+".join(re.escape(w) for w in probe.split(" "))
                out.append(re.compile(rx))
            if out:
                break
    return out[:12]


def lcs_pairs(a, b):
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, nxt = dp[i], dp[i + 1]
        for j in range(m - 1, -1, -1):
            row[j] = nxt[j + 1] + 1 if a[i] == b[j] else max(nxt[j], row[j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def ascii_alnum(ch):
    return ch.isascii() and ch.isalnum()


class Doc:
    """A body.html split into tags and text, with the helper indexes we need."""

    def __init__(self, raw):
        self.raw = raw
        self.segs = re.split(r"(<[^>]+>)", raw)
        self.starts, acc = [], 0
        for s in self.segs:
            self.starts.append(acc)
            acc += len(s)
        self.length = acc
        # a tag is a segment that starts with '<' -- never infer this from parity
        self.is_tag = [s.startswith("<") for s in self.segs]
        self.pre_at, self.a_at = [], []
        pre = a = False
        for i, s in enumerate(self.segs):
            if self.is_tag[i]:
                t = s.lower()
                if t.startswith("<pre"):
                    pre = True
                elif t.startswith("</pre"):
                    pre = False
                elif t.startswith("<a ") or t.startswith("<a>"):
                    a = True
                elif t.startswith("</a"):
                    a = False
            self.pre_at.append(pre)
            self.a_at.append(a)
        self.links = [(m.start(), m.group(1)) for m in
                      re.finditer(r'<a\b[^>]*?href="(https?://[^"]+|mailto:[^"]+)"', raw)]

    def candidates(self, tok):
        out = []
        for i in range(len(self.segs)):
            if self.is_tag[i] or self.pre_at[i] or self.a_at[i]:
                continue
            text = self.segs[i]
            for m in re.finditer(re.escape(tok), text):
                j, k = m.start(), m.end()
                b = text[j - 1] if j > 0 else " "
                f = text[k] if k < len(text) else " "
                if ascii_alnum(b) or b in "._-":
                    continue
                if ascii_alnum(f) or f in "._-":
                    continue
                out.append((self.starts[i] + j, i, j, k))
        return out

    def find_phrase(self, rx):
        out = []
        for i in range(len(self.segs)):
            if self.is_tag[i] or self.pre_at[i] or self.a_at[i]:
                continue
            for m in re.finditer(rx, self.segs[i]):
                out.append((self.starts[i] + m.start(), i, m.start(), m.end()))
        return out

    def near_tokens(self, pos, toks, radius=700):
        """How many of `toks` occur within `radius` bytes of `pos`.

        This is the guard that kills coincidental matches. A source link whose
        anchor is a prose sentence produced the token `Networks`, which matched
        a table-of-contents entry reading "Convolutional Networks" -- correct
        string, wholly unrelated link. Requiring a SECOND token from the same
        anchor nearby rejects it, because the real anchor's other words are not
        there.
        """
        hits = 0
        for t in toks:
            if any(abs(p - pos) <= radius for p, *_ in self.candidates(t)):
                hits += 1
        return hits

    def insert(self, edits):
        """edits: list of (seg, j, k, uri). Applied back to front."""
        new = list(self.segs)
        for i, j, k, uri in sorted(edits, key=lambda t: (-t[0], -t[1])):
            s = new[i]
            new[i] = f'{s[:j]}<a href="{uri}">{s[j:k]}</a>{s[k:]}'
        return "".join(new)


def main():
    apply = "--apply" in sys.argv
    review = "--review" in sys.argv
    src = json.load(open(LINKS, encoding="utf-8"))
    src.sort(key=lambda x: (x["page"], x["rect"][1], x["rect"][0]))
    src_uris = [x["uri"] for x in src]

    content = [(si, x) for si, x in enumerate(src) if x["uri"] not in CHROME]
    dropped = len(src) - len(content)
    done = {}            # si -> (how, uri)
    matches = []         # (page, uri, how, dist, context)
    claimed = []         # (seg, j, k) spans already given a link
    raw = open(BODY, encoding="utf-8").read()

    # Interpolate on the SOURCE PAGE, not on the annotation index. A page is a
    # fixed amount of output, so the relation is near-linear; the index is not,
    # because source pages carry very different numbers of links. Clamping on
    # the index also made p151-191 collapse onto the last pin (byte 166205),
    # which is why the whole tail kept failing.
    axis = [x["page"] + x["rect"][1] / 800.0 for x in src]

    for tol, label in ROUNDS:
        doc = Doc(raw)
        out_uris = [u for _, u in doc.links]
        pins = [(si, doc.links[oj][0]) for si, oj in lcs_pairs(src_uris, out_uris)]
        pins.sort()
        px = [p for _, p in pins]
        pa = [axis[s] for s, _ in pins]

        def expected(si):
            if not pins:
                return doc.length / 2
            a = axis[si]
            if a <= pa[0]:
                return px[0]
            if a >= pa[-1]:
                # extrapolate with the slope of the last segment rather than clamp
                da, dp = pa[-1] - pa[-2], px[-1] - px[-2] if len(pins) > 1 else (1, 0)
                slope = dp / da if da else 0
                return px[-1] + slope * (a - pa[-1])
            for k in range(1, len(pa)):
                if pa[k] >= a:
                    a0, a1, p0, p1 = pa[k - 1], pa[k], px[k - 1], px[k]
                    return p1 if a1 == a0 else p0 + (p1 - p0) * (a - a0) / (a1 - a0)
            return px[-1]

        pinned = {si for si, _ in pins}
        edits, log = [], []
        for si, rec in content:
            if si in done:
                continue
            if si in pinned:
                done[si] = "already present"
                continue
            exp = expected(si)
            if any(u == rec["uri"] and abs(p - exp) <= tol for p, u in doc.links):
                done[si] = "already present (near)"
                continue
            toks = anchor_tokens(rec["anchor"])
            probes = phrase_probes(rec["anchor"])

            def clashes(i, j, k):
                """one output span may carry at most one link"""
                return any(i == ci and not (k <= cj or j >= ck) for ci, cj, ck in claimed)

            best = None                       # (dist, i, j, k, how)
            # 1. exact phrase (keeps the whole paper title, unambiguous)
            for rx in probes:
                for pos, i, j, k in doc.find_phrase(rx):
                    d = abs(pos - exp)
                    if d <= tol and not clashes(i, j, k) and (best is None or d < best[0]):
                        best = (d, i, j, k, "phrase")
            # 2. single token. Anchors longer than a phrase are block-level
            #    extractions -- a whole printed line, whose token set is polluted
            #    with ordinary words. `there are 10 classes), but nowhere near
            #    human performance...` yielded `Networks`, which matched a table
            #    of contents reading "Convolutional Networks" and was accepted
            #    because OTHER common words from that line also sit in the TOC.
            #    For these, trust only the phrase probe.
            if best is None and toks and len(rec["anchor"]) <= 60:
                for tok in toks:
                    for pos, i, j, k in doc.candidates(tok):
                        d = abs(pos - exp)
                        if d > tol or clashes(i, j, k):
                            continue
                        others = [t for t in toks if t != tok]
                        # corroboration counts only distinctive witnesses
                        strong = [t for t in others if len(t) >= 6]
                        corr = doc.near_tokens(pos, strong)
                        n_occ = len(doc.candidates(tok))
                        need = 2 if len(toks) >= 6 else 1
                        # Requiring corroboration unconditionally is too strict:
                        # `CIFAR-10 dataset.` has its sibling translated to
                        # `数据集`, so nothing can corroborate it. Scale instead --
                        # a rarely-occurring string can be placed by proximity,
                        # a common word needs a witness.
                        ok = (not strong) or corr >= need or (
                            n_occ <= 6 and d <= tol // 2 and len(toks) <= 3)
                        if not ok:
                            continue
                        if best is None or d < best[0]:
                            best = (d, i, j, k, tok)
            if best is None:
                continue
            d, i, j, k, how = best
            claimed.append((i, j, k))
            edits.append((i, j, k, rec["uri"]))
            ctx = doc.segs[i]
            log.append((rec["page"], rec["uri"], how, d,
                        ctx[max(0, j - 60):j], ctx[j:k], ctx[k:k + 45]))
            done[si] = "restored"
        raw = doc.insert(edits) if edits else raw
        matches.extend(log)
        print(f"  {label:<28} tol={tol:<6} pins={len(pins):<3} restored={len(edits)}")

    stat = Counter(done.values())
    unresolved = [(si, rec) for si, rec in content if si not in done]
    final = len(re.findall(r'href="https?://', raw))

    if "--diag" in sys.argv:
        doc = Doc(raw)
        out_uris = [u for _, u in doc.links]
        pins = sorted((si, doc.links[oj][0]) for si, oj in lcs_pairs(src_uris, out_uris))
        px = [p for _, p in pins]
        pa = [axis[s] for s, _ in pins]

        def exp_of(si):
            a = axis[si]
            if a <= pa[0]:
                return px[0]
            if a >= pa[-1]:
                da, dp = pa[-1] - pa[-2], px[-1] - px[-2] if len(pins) > 1 else (1, 0)
                return px[-1] + (dp / da if da else 0) * (a - pa[-1])
            for k in range(1, len(pa)):
                if pa[k] >= a:
                    a0, a1, p0, p1 = pa[k - 1], pa[k], px[k - 1], px[k]
                    return p1 if a1 == a0 else p0 + (p1 - p0) * (a - a0) / (a1 - a0)
            return px[-1]

        print()
        print("=" * 74)
        print("DIAGNOSTIC for the unresolved ones")
        print("=" * 74)
        for si, rec in unresolved:
            e = exp_of(si)
            toks = anchor_tokens(rec["anchor"])
            line = f"  p{rec['page']:<4} exp={int(e):<7} anchor={rec['anchor'][:34]!r}"
            details = []
            for tok in toks[:3]:
                cands = [pos for pos, *_ in doc.candidates(tok)]
                if not cands:
                    details.append(f"{tok}:ABSENT")
                else:
                    near = min(cands, key=lambda p: abs(p - e))
                    details.append(f"{tok}:n={len(cands)},near={near},d={int(abs(near - e))}")
            print(line)
            print(f"        {'; '.join(details) if details else 'NO TOKENS'}")

    print()
    print("=" * 74)
    print("CONTENT LINK RESTORATION")
    print("=" * 74)
    print(f"  source annotations              : {len(src)}")
    print(f"  dropped as site chrome          : {dropped}")
    print(f"  content links to place          : {len(content)}")
    print()
    for k in sorted(stat):
        print(f"    {k:<30}: {stat[k]}")
    print(f"    {'restored by this script':<30}: {stat.get('restored', 0)}")
    print(f"    {'STILL UNRESOLVED':<30}: {len(unresolved)}")
    print()
    print(f"  external <a href> in body: {len(re.findall(r'href=.https?://', open(BODY, encoding='utf-8').read()))} -> {final}")
    if unresolved:
        print()
        print(f"  --- {len(unresolved)} unresolved ---")
        for si, rec in unresolved:
            print(f"    p{rec['page']:<4} {rec['anchor'][:44]!r:<48} {rec['uri'][:50]}")
    if review:
        print()
        print("=" * 74)
        print("EVERY RESTORED MATCH -- check these by eye")
        print("=" * 74)
        for pg, uri, tok, d, pre, hit, post in sorted(matches):
            print(f"  p{pg:<4} d={int(d):<6} tok={tok:<16} {uri[:46]}")
            print(f"        ...{pre}[[{hit}]]{post}...".replace("\n", " "))
    if apply:
        open(BODY, "w", encoding="utf-8").write(raw)
        print("\n  APPLIED to full/body.html")
    else:
        print("\n  dry run -- nothing written (pass --apply)")


if __name__ == "__main__":
    main()
