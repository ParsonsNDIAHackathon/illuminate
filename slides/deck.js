/* Media slots and deck wiring.
 *
 * Every image or video in the deck is a slot, not a hard-coded <img>:
 *
 *   <figure class="shot" data-slot="media/risk-graph" data-try="png,mp4"
 *           data-note="Canvas coloured by risk band">
 *     <figcaption>…</figcaption>
 *   </figure>
 *
 * The resolver tries each extension in order and mounts the first file that
 * actually loads. If none do, it draws a labelled placeholder naming the exact
 * path to drop a file at — so an unfinished deck still presents, and filling it
 * in never means editing HTML.
 *
 * Works over file:// as well as http:// — it probes with element load/error
 * events rather than fetch(), which file:// blocks.
 */

/* ---- slide frame --------------------------------------------------------- */

/* Reveal sets display:block *inline* on the slide it is showing, and an inline
 * style beats any stylesheet rule — so a flex <section> quietly reverts to block
 * flow and tall media runs off the bottom of the frame. Give every slide an inner
 * flex column instead. Doing it here rather than in the markup means a new
 * <section class="s"> needs no boilerplate: write content, get the layout.
 * <aside class="notes"> stays outside, where the notes plugin expects it. */
document.querySelectorAll('.reveal .slides section.s').forEach(sec => {
  if (sec.querySelector(':scope > .wrap')) return;
  const wrap = document.createElement('div');
  wrap.className = 'wrap';
  while (sec.firstChild) {
    const node = sec.firstChild;
    if (node.nodeType === 1 && node.tagName === 'ASIDE') break;   // notes come last
    wrap.appendChild(node);
  }
  sec.prepend(wrap);
});

/* ---- media slots --------------------------------------------------------- */

const VIDEO_EXT = new Set(['mp4', 'webm', 'mov', 'm4v', 'ogv']);
const DEFAULT_TRY = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm'];

/** Candidate paths for a slot, in priority order. */
function candidatesFor(el) {
  const slot = (el.dataset.slot || '').trim();
  if (!slot) return [];
  if (/\.[a-z0-9]{2,5}$/i.test(slot)) return [slot];       // explicit extension wins
  const tries = (el.dataset.try || '').split(',').map(s => s.trim().replace(/^\./, '')).filter(Boolean);
  return (tries.length ? tries : DEFAULT_TRY).map(ext => `${slot}.${ext}`);
}

function frameOf(el) {
  let frame = el.querySelector(':scope > .frame');
  if (!frame) {
    frame = document.createElement('div');
    frame.className = 'frame';
    el.prepend(frame);
  }
  return frame;
}

function mount(el, node) {
  const frame = frameOf(el);
  frame.replaceChildren(node);
  el.dataset.resolved = node.currentSrc || node.src || '';
}

function placeholder(el, tried) {
  const kindAttr = (el.dataset.kind || '').toLowerCase();
  const looksVideo = kindAttr === 'video' || candidatesFor(el).every(c => VIDEO_EXT.has(c.split('.').pop()));
  const kind = kindAttr || (looksVideo ? 'video' : 'screenshot');
  const preferred = tried[0] || el.dataset.slot || 'media/…';
  const alts = tried.slice(1);

  const box = document.createElement('div');
  box.className = 'ph';
  box.innerHTML = `
    <div class="ph-icon">${looksVideo ? '▶' : '▣'}</div>
    <div class="ph-kind">${kind}</div>
    <div class="ph-title">${el.dataset.note || 'Drop a capture in here'}</div>
    <div class="ph-slot">save as <b>slides/${preferred}</b>${
      alts.length ? `<br>or ${alts.map(a => a.split('.').pop()).join(' / ')}` : ''
    }</div>`;
  mount(el, box);
  el.dataset.resolved = '';
}

function resolve(el, list, i = 0) {
  if (i >= list.length) return placeholder(el, list);
  const src = list[i];
  const ext = src.split('.').pop().toLowerCase();
  const next = () => resolve(el, list, i + 1);

  if (VIDEO_EXT.has(ext)) {
    const v = document.createElement('video');
    v.muted = true;                 // required for unattended autoplay
    v.loop = !el.hasAttribute('data-once');
    v.playsInline = true;
    v.preload = 'auto';
    if (el.hasAttribute('data-controls')) v.controls = true;
    v.addEventListener('loadeddata', () => mount(el, v), { once: true });
    v.addEventListener('error', next, { once: true });
    v.src = src;
    v.load();
  } else {
    const img = new Image();
    img.alt = el.dataset.note || '';
    img.addEventListener('load', () => mount(el, img), { once: true });
    img.addEventListener('error', next, { once: true });
    img.src = src;
  }
}

document.querySelectorAll('figure.shot').forEach(el => resolve(el, candidatesFor(el)));

/* ---- deck ---------------------------------------------------------------- */

Reveal.initialize({
  width: 1600,
  height: 900,
  margin: 0.02,
  minScale: 0.2,
  maxScale: 1.6,
  center: false,               // slides.s centre themselves; keeps full-bleed media honest
  hash: true,
  slideNumber: 'c/t',
  transition: 'fade',
  transitionSpeed: 'fast',
  backgroundTransition: 'fade',
  navigationMode: 'linear',    // one arrow press = one step, including vertical stacks
  plugins: [RevealNotes],
});

/* Play the video on the slide you are on, pause every other one, so a looping
   capture never runs unseen — and always restarts from the top. */
function syncVideos(current) {
  document.querySelectorAll('.reveal video').forEach(v => {
    if (current && current.contains(v)) {
      v.currentTime = 0;
      const p = v.play();
      if (p && p.catch) p.catch(() => {});   // autoplay refusal is not an error worth showing
    } else {
      v.pause();
    }
  });
}

Reveal.on('ready', e => syncVideos(e.currentSlide));
Reveal.on('slidechanged', e => syncVideos(e.currentSlide));
