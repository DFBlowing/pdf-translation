# -*- coding: utf-8 -*-
"""Prove the spliced links did not corrupt the markup.

The v3 failure mode was splicing `<a href>` INSIDE a tag (`<fig<a href=..>ure>`),
which still "looks like" 66 links to a naive counter. These checks would catch it.

Usage:
    python check-markup.py <body.html>

    Defaults to ./full/body.html, the layout the rest of the pipeline writes into.
    Exits non-zero on corruption, so it doubles as a gate.
"""
import re, sys, os
from html.parser import HTMLParser

R = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(R, "full", "body.html")
if not os.path.exists(path):
    sys.exit(f"no such file: {path}\nusage: python check-markup.py <body.html>")
raw = open(path, encoding="utf-8").read()

ok = True

n_open = len(re.findall(r"<a\b", raw))
n_close = len(re.findall(r"</a>", raw))
print(f"  <a ...>          : {n_open}")
print(f"  </a>             : {n_close}")
if n_open != n_close:
    print("  !! unbalanced anchors"); ok = False

# a '<' inside an attribute value means we spliced into a tag
nested = re.findall(r"<[^>]*<a\b[^>]*>", raw)
print(f"  anchors nested inside a tag : {len(nested)}")
if nested:
    ok = False
    for s in nested[:3]:
        print(f"      {s[:90]}")

# every anchor must have a non-empty visible text child
empty = [m.group(0) for m in re.finditer(r'<a\b[^>]*>\s*</a>', raw)]
print(f"  empty anchors               : {len(empty)}")
if empty:
    ok = False

# tags must be balanced and nest legally
class Check(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ("br", "hr", "img", "meta", "link", "input"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("br", "hr", "img", "meta", "link", "input"):
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


p = Check()
p.feed(raw)
print(f"  unclosed tags at EOF        : {len(p.stack)} {p.stack[:6]}")
print(f"  nesting errors              : {len(p.errors)} {p.errors[:4]}")
if p.errors or p.stack:
    ok = False

# the hrefs must all be http(s)/mailto and well formed
bad = [u for u in re.findall(r'<a\b[^>]*?href="([^"]*)"', raw)
       if not re.match(r"^(https?://|mailto:|#)", u)]
print(f"  malformed href values       : {len(bad)} {bad[:4]}")
if bad:
    ok = False

print(f"  external links              : {len(re.findall(r'href=.https?://', raw))}")
print()
print("MARKUP OK" if ok else "MARKUP CORRUPT")
sys.exit(0 if ok else 1)
