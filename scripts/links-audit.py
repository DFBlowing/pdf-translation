# -*- coding: utf-8 -*-
"""How many of the source's hyperlink annotations survive in the output?

The source PDF has N link annotations. A faithful translation keeps them.
This measures the gap and, for the missing ones, how locatable they are.

This is a URI-presence view, and it OVERSTATES coverage: a URI counts as present
as soon as it appears *anywhere* in the body, so three citations of the same paper
collapse into one and an annotation whose text was translated away still looks kept.
On the reference case it reported 139 of 251 kept where the per-annotation ledger is
118. For the authoritative number, align every annotation to its own output
occurrence and report that ledger; use this for the per-range signal.

Usage:
    python links-audit.py --links <source-links.json> --body <body.html>

    Both default to the pipeline's usual names (./source-links.json,
    ./full/body.html). The per-range table is what tells you whether a whole
    batch was written without the inventory.
"""
import json, re, collections, sys, os

R = os.path.dirname(os.path.abspath(__file__))


def argval(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


LINKS = argval("--links", os.path.join(R, "source-links.json"))
BODY = argval("--body", os.path.join(R, "full", "body.html"))
for _flag, _p in (("--links", LINKS), ("--body", BODY)):
    if not os.path.exists(_p):
        sys.exit(f"{_flag}: no such file: {_p}\n"
                 f"usage: python links-audit.py --links <source-links.json> --body <body.html>")
src = json.load(open(LINKS, encoding="utf-8"))
body = open(BODY, encoding="utf-8").read()

# text visible in the output, tags stripped -- for anchor-text location tests
plain = re.sub(r"<[^>]+>", "", body)
plain = plain.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

have = set(re.findall(r'href="(https?://[^"]+)"', body))

RANGES = [(1, 30, "p1-30 sample"), (31, 60, "p31-60"), (61, 90, "p61-90"),
          (91, 120, "p91-120"), (121, 150, "p121-150"), (151, 191, "p151-191")]


def rng(p):
    for lo, hi, n in RANGES:
        if lo <= p <= hi:
            return n
    return "front/other"


missing = [x for x in src if x["uri"] not in have]
present = [x for x in src if x["uri"] in have]

print("source link annotations      :", len(src))
print("distinct source URIs         :", len(set(x['uri'] for x in src)))
print("distinct URIs in output      :", len(have))
print("annotations kept             :", len(present))
print("annotations MISSING          :", len(missing))
print()
cm = collections.Counter(rng(x["page"]) for x in missing)
ct = collections.Counter(rng(x["page"]) for x in src)
print(f"{'range':<16}{'kept':>6}{'missing':>9}{'total':>7}  {'coverage':>9}")
for _, _, n in RANGES:
    k, m, t = ct[n] - cm[n], cm[n], ct[n]
    print(f"{n:<16}{k:>6}{m:>9}{t:>7}  {(k / t * 100 if t else 100):>8.0f}%")

# ---- locatability of the missing links ------------------------------------
# A missing link is locatable if its anchor text (or a distinctive Latin token
# from it) survives in the output. The output is Chinese, so anchors that were
# fully translated cannot be found by text -- those need positional mapping.

LATIN = re.compile(r"[A-Za-z][A-Za-z0-9._\-/]{4,}")


def locatable(anchor):
    a = anchor.strip()
    if not a:
        return None
    if a in plain:
        return "exact"
    toks = [t for t in LATIN.findall(a) if len(t) >= 5]
    if not toks:
        return None
    hits = [t for t in toks if t in plain]
    if hits:
        return "token:" + hits[0]
    return None


loc = collections.Counter()
examples = []
for x in missing:
    r = locatable(x["anchor"])
    loc["locatable" if r else "needs-map"] += 1
    if len(examples) < 12 and not r:
        examples.append((x["page"], x["anchor"][:60], x["uri"][:70]))

print()
print("locatability of the", len(missing), "missing links:")
print("  anchor (or a Latin token) found in output :", loc["locatable"])
print("  not findable by text (fully translated)   :", loc["needs-map"])
print()
print("sample of the not-findable ones (page / anchor / uri):")
for pg, a, u in examples:
    print(f"  p{pg:<4} {a!r:<64} {u}")
