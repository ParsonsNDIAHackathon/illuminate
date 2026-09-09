# Illuminate — pitch deck

A [reveal.js](https://revealjs.com) deck, 19 slides. No build step and no network: reveal is
vendored in `vendor/`, so `slides/index.html` opens straight from disk.

```bash
xdg-open slides/index.html          # or drag it into a browser
```

Serving it instead (`python3 -m http.server -d slides 8099` → <http://localhost:8099>) changes
nothing except that `file://` console noise goes away.

The running app also serves the deck at `/slides/` — <http://localhost:8080/slides/> under
`make up`, <http://localhost:5173/slides/> under `make dev` — and the **Deck** button at the
bottom of the app's left rail opens it in a new tab, so a demo can cut between the two. The
container bind-mounts this directory, so editing a slide needs a reload, not a rebuild.

## Publishing

`.github/workflows/pages.yml` puts this directory on GitHub Pages —
<https://parsonsndiahackathon.github.io/illuminate/>, with the short deck at `short.html`. It runs
on any push to `main` that touches `slides/`, and can be triggered by hand from the Actions tab.

Nothing about the deck changes to make this work: reveal is already vendored and every path in
`index.html` is relative, so the same files that open over `file://` serve unmodified from a
subpath. The workflow only has two jobs beyond copying the directory up:

- **Pull the LFS media.** `actions/checkout` leaves LFS files as pointer stubs by default, which
  would publish a 134-byte text file named `chat-report.mp4` and leave that slide showing its
  placeholder. The objects are pulled through a cache keyed on their oids — a cold build spends
  ~120MB of the account's monthly LFS bandwidth, a cached one spends none — and the build then
  asserts no pointer survived, so this fails loudly rather than silently.
- **Regenerate `short.html`.** Same `make-short.py` you would run locally, so the published short
  deck cannot drift from the long one even if someone forgets to commit it.

Pages must be switched on once, under **Settings → Pages → Source: GitHub Actions**.

## The short deck

`short.html` is the same deck cut to six slides — the big picture, the person, risk colouring,
why it flows, the generated report, and where it goes next. It shares `theme.css`, `deck.js` and
`vendor/`, so it is served and opened exactly like the full one (`slides/short.html`, or
<http://localhost:8080/slides/short.html> under `make up`).

It is **generated, not hand-edited**. Change a slide in `index.html`, then:

```bash
python3 slides/make-short.py
```

The list of slides it keeps is `PICKS` at the top of that script, written in reveal's own hash
coordinates — the numbers in the address bar as you page through the full deck, so `#/8` is
`'8'` and `#/11/2` is `'11/2'`. A sub-slide pulled out of a vertical stack becomes an ordinary
slide in the short deck.

| Key | |
| --- | --- |
| `→` / `space` | next step — walks vertical stacks too |
| `←` | back |
| `s` | speaker view: notes, timer, next slide |
| `esc` | slide overview |
| `f` / `b` | fullscreen / blackout |
| `?` | all shortcuts |

Presenter notes are on most slides — hit `s` before you start. Speaker view needs the deck
served over `http://`; over `file://` the popup opens but cannot read the deck back.

## Adding images and video

Every visual is a **slot**, not a hard-coded `<img>`. A slot names a path without an extension:

```html
<figure class="shot" data-slot="media/risk-graph" data-try="png,mp4,jpg,gif"
        data-note="Canvas coloured by risk band">
  <figcaption>…</figcaption>
</figure>
```

`deck.js` tries each extension in order and mounts the first file that loads. If none do, the
slide draws a dashed placeholder naming the exact path to save to — so the deck always presents,
and filling a slot in never means editing HTML. **Drop the file in `media/` with the right name
and reload.**

Videos autoplay muted and loop when you land on their slide, and restart each time. `data-controls`
adds a scrubber; `data-once` stops the loop.

### Slots

| File | Slide | Status |
| --- | --- | --- |
| `media/birdsnest.png` | The big picture — whole program graph | **your capture** (V-22, every layer, no depth limit) |
| `media/employee-risk.png` | Employee of a sub-contractor — person risk tab | **your capture** (R. Ostrowski) |
| `media/risk-graph.*` | **Canvas coloured by risk** — the money slide | **your capture** — swap in an mp4 under the same name if you want it moving |
| `media/risk-path.*` | Clicking a dimension lights its path up | ⬜ empty — optional slide, cut it if short |
| `media/chat-ask.png` | Chat: a template answer on the canvas | from `docs/screenshots/02-chat-sole-source.png` |
| `media/chat-styles.png` | Chat: goods purple, services yellow | from `docs/screenshots/03-chat-goods-services.png` |
| `media/chat-report.*` | **Chat: generate a report** | ⬜ empty — mp4 preferred |
| `media/report-risk.png` | The report's risk section | from `docs/screenshots/06-report-risk.png` |
| `media/chat-add-program.png` | **Chat: add a new program** | **your capture** |
| `media/permission-dialog.png` | Ask before writing | from `docs/screenshots/04-permission-dialog.png` |
| `media/map.png` | Map view — the optional closer | **your capture** |

The rows marked *from `docs/screenshots/`* are stand-ins — overwrite any of them with a fresher
capture under the same filename.

Capture at 1600×900 or wider. Screenshots sit on a dark card with a shadow, so grab the app in
dark theme and they drop straight in.

## Adding a slide

```html
<section class="s">
  <p class="kicker">Section label</p>
  <h2>The claim.</h2>
  <p class="lead">The elaboration.</p>
  <aside class="notes">What to say out loud.</aside>
</section>
```

`class="s"` is what gets the 1600×900 frame and the centred flex column — `deck.js` wraps the
contents itself, so there is no boilerplate div to remember. Add `tight` for less gap between
blocks, `pad-sm` for a narrower margin when a slide is media-heavy. Nest `<section>`s one level
to make a vertical stack (the chat sequence is one).

Useful classes: `.lead`, `.small`, `.card`, `.grid-2`, `.grid-3`, `.split` (text beside media,
`.media-left` to flip), `.stats`, `.ask` (a typed question), `.chips`, `.pipe`, `table.dims`,
and `.band` + `.dot.severe|high|elevated|low|unscored` for risk vocabulary.

Colours come from `theme.css`, which mirrors `web/src/styles/palette.ts` and `risk.ts` — so a
risk colour on a slide means what it means in the app. Use the CSS variables, not hex.

## Layout gotcha

Reveal sets `display: block` **inline** on the slide it is showing, and an inline style beats any
stylesheet rule. A flex `<section>` therefore silently reverts to block flow and tall media runs
off the bottom of the frame. That is why the flex column lives on an inner `.wrap` that `deck.js`
injects, and why `theme.css` styles `section.s > .wrap` rather than `section.s`.
