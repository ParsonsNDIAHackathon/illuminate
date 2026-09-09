#!/usr/bin/env python3
"""Rebuild short.html by lifting whole slides out of index.html.

short.html is generated, never hand-edited: it shares theme.css, deck.js and vendor/ with the
full deck, so a slide only ever exists in one place. Edit index.html, re-run this, and the short
version carries the change.

    python3 slides/make-short.py        # from anywhere

PICKS are reveal's own hash coordinates — the numbers in the address bar as you page through
index.html, so `#/8` is "8" and `#/11/2` is "11/2". Both are zero-based, which is why they are
taken verbatim rather than renumbered: what you read off the screen is what you write down here.
A sub-slide picked out of a vertical stack becomes an ordinary slide in the short deck.
"""

import re
import sys
from pathlib import Path

PICKS = ['5', '6', '8', '9', '11/2', '13']

HEAD = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Illuminate — short</title>
  <link rel="stylesheet" href="vendor/reveal.min.css">
  <link rel="stylesheet" href="theme.css">
</head>
<body>
<div class="reveal">
<div class="slides">
'''

TAIL = '''
</div>
</div>

<script src="vendor/reveal.min.js"></script>
<script src="vendor/plugin/notes/notes.min.js"></script>
<script src="deck.js"></script>
</body>
</html>
'''

here = Path(__file__).resolve().parent
source = (here / 'index.html').read_text()
body = source[source.index('<div class="slides">'):]
# Stop at the last slide, so the final block does not swallow the page's own closing tags.
body = body[:body.rindex('</section>') + len('</section>')]

# Top-level sections start at column 0; the ones nested in a vertical stack are indented.
starts = [m.start() for m in re.finditer(r'^<section', body, re.M)] + [len(body)]
slides = []
for i in range(len(starts) - 1):
    block = body[starts[i]:starts[i + 1]]
    subs = [m.start() for m in re.finditer(r'^  <section', block, re.M)]
    if not subs:
        slides.append(block)
        continue
    subs.append(len(block))
    slides.append([block[subs[j]:subs[j + 1]] for j in range(len(subs) - 1)])


def pick(spec):
    parts = spec.split('/')
    h = int(parts[0])
    if h >= len(slides):
        sys.exit(f'{spec}: index.html has only {len(slides)} top-level slides')
    chosen = slides[h]
    if len(parts) == 1:
        if isinstance(chosen, list):
            sys.exit(f'{spec}: slide {h} is a vertical stack of {len(chosen)} — say {h}/0 . {h}/{len(chosen) - 1}')
        return chosen
    if not isinstance(chosen, list):
        sys.exit(f'{spec}: slide {h} has no vertical stack')
    v = int(parts[1])
    if v >= len(chosen):
        sys.exit(f'{spec}: slide {h} has only {len(chosen)} sub-slides')
    # Lifted out of its stack, so it loses the stack's indentation.
    return re.sub(r'^  ', '', chosen[v], flags=re.M)


picked = [pick(spec).strip() for spec in PICKS]
banner = [f'<!-- {"=" * (68 - len(str(n + 1)))} {n + 1} -->' for n in range(len(picked))]
out = HEAD + '\n' + '\n\n'.join(f'{b}\n{s}' for b, s in zip(banner, picked)) + '\n' + TAIL
(here / 'short.html').write_text(out)
print(f'short.html: {len(picked)} slides from index.html ({", ".join(PICKS)})')
