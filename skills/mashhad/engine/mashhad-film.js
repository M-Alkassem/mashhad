/*! mashhad-film: a scroll-driven film for any web page. MIT. No dependencies.
 *
 * <script type="module" src="/mashhad/hero/mashhad-film.js"></script>
 * <mashhad-film src="/mashhad/hero" length="400">
 *   <div data-from="0" data-to="0.3">Your headline</div>      (shown while progress is in range)
 *   <div data-from="0.7" data-to="1">Your call to action</div>
 * </mashhad-film>
 *
 * src     folder made by `mashhad.py pack` (manifest.json, landscape/, portrait/, poster.jpg)
 * length  scroll distance in % of the screen height (default 400 = four screens)
 * smooth  0..1, how quickly the film catches up with the scroll (default 0.2; 1 = instant)
 *
 * Sets --mashhad-progress (0..1) on the element and fires a "progress" event, so overlays can
 * animate with plain CSS. Respects prefers-reduced-motion (shows one still frame).
 */
const css = `
mashhad-film { display: block; position: relative; }
mashhad-film > .mf-stage { position: sticky; top: 0; height: 100vh; height: 100svh; overflow: hidden; background: #000; }
mashhad-film canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
mashhad-film .mf-layer { position: absolute; inset: 0; pointer-events: none; }
mashhad-film [data-from] { position: absolute; opacity: 0; transition: opacity .6s ease, transform .6s ease; transform: translateY(14px); }
mashhad-film [data-from].mf-on { opacity: 1; transform: none; }
mashhad-film [data-from] a, mashhad-film [data-from] button { pointer-events: auto; }
mashhad-film .mf-load { position: absolute; left: 50%; bottom: 22px; width: 120px; height: 2px; margin-left: -60px;
  background: rgba(255,255,255,.15); overflow: hidden; border-radius: 2px; transition: opacity .5s; }
mashhad-film .mf-load i { display: block; height: 100%; width: 0; background: rgba(255,255,255,.7); }
`;

class MashhadFilm extends HTMLElement {
  static get observedAttributes() { return ["src"]; }

  connectedCallback() {
    if (this._ready) return;
    this._ready = true;
    if (!document.getElementById("mashhad-film-css")) {
      const s = document.createElement("style");
      s.id = "mashhad-film-css";
      s.textContent = css;
      document.head.append(s);
    }
    const stage = document.createElement("div");
    stage.className = "mf-stage";
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d");
    const layer = document.createElement("div");
    layer.className = "mf-layer";
    layer.append(...this.childNodes);
    this.bar = document.createElement("div");
    this.bar.className = "mf-load";
    this.bar.innerHTML = "<i></i>";
    stage.append(this.canvas, layer, this.bar);
    this.append(stage);
    this.beats = [...layer.querySelectorAll("[data-from]")];
    this.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.style.height = this.reduced ? "100vh" : `${Number(this.getAttribute("length") || 400)}vh`;
    this.shown = -1;
    this.pos = 0;
    this._onScroll = () => this._kick();
    this._onResize = () => { this._size(); this._pickVariant(); };
    addEventListener("scroll", this._onScroll, { passive: true });
    addEventListener("resize", this._onResize);
    this._size();
    this._load();
  }

  disconnectedCallback() {
    removeEventListener("scroll", this._onScroll);
    removeEventListener("resize", this._onResize);
  }

  async _load() {
    const base = (this.getAttribute("src") || ".").replace(/\/$/, "");
    this.base = base;
    this.manifest = await fetch(`${base}/manifest.json`).then((r) => r.json());
    this._pickVariant();
  }

  _pickVariant() {
    if (!this.manifest) return;
    const v = this.manifest.variants;
    const portrait = innerHeight / innerWidth > 1.15 && v.portrait;
    const name = portrait ? "portrait" : "landscape" in v ? "landscape" : Object.keys(v)[0];
    if (name === this.variant) return;
    this.variant = name;
    const spec = v[name];
    this.count = spec.frames;
    this.imgs = new Array(this.count);
    this.loaded = 0;
    this.shown = -1;
    const url = (i) => `${this.base}/${spec.path.replace("{n}", String(i + 1).padStart(spec.pad || 4, "0"))}`;
    // coarse to fine: every 16th, then every 4th, then the rest, so scrubbing works almost at once
    const seen = new Set();
    const order = [];
    for (const step of this.reduced ? [this.count] : [16, 4, 1])
      for (let i = 0; i < this.count; i += step) if (!seen.has(i)) { seen.add(i); order.push(i); }
    if (this.reduced) order.push(this.count - 1);
    let next = 0;
    const pump = () => {
      if (next >= order.length) return;
      const i = order[next++];
      const im = new Image();
      im.decoding = "async";
      im.onload = im.onerror = () => {
        this.loaded++;
        this.bar.firstChild.style.width = `${(100 * this.loaded) / order.length}%`;
        if (this.loaded >= order.length) this.bar.style.opacity = 0;
        this._draw(true);
        pump();
      };
      im.src = url(i);
      this.imgs[i] = im;
    };
    for (let k = 0; k < 6; k++) pump(); // six downloads in flight
  }

  _size() {
    const r = Math.min(devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(innerWidth * r);
    this.canvas.height = Math.round(innerHeight * r);
    this.shown = -1;
    this._draw(true);
  }

  progress() {
    if (this.reduced) return 1;
    const r = this.getBoundingClientRect();
    const run = r.height - innerHeight;
    return run > 0 ? Math.min(1, Math.max(0, -r.top / run)) : 0;
  }

  _kick() {
    if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = 0; this._draw(); });
  }

  _draw(force) {
    if (!this.imgs) return;
    const p = this.progress();
    const smooth = Math.min(1, Math.max(0.02, Number(this.getAttribute("smooth") || 0.2)));
    const now = performance.now();
    const dt = Math.min(0.25, (now - (this._t || now)) / 1000) || 1 / 60;
    this._t = now;
    // frame-rate independent catch-up: the same feel at 30, 60 or 120 Hz
    this.pos += (p - this.pos) * (force ? 1 : 1 - Math.pow(1 - smooth, dt * 60));
    if (Math.abs(p - this.pos) > 0.0005) this._kick();
    let i = Math.round(this.pos * (this.count - 1));
    let j = i;
    while (j >= 0 && !(this.imgs[j] && this.imgs[j].complete && this.imgs[j].naturalWidth)) j--;
    if (j < 0) { j = i; while (j < this.count && !(this.imgs[j] && this.imgs[j].complete && this.imgs[j].naturalWidth)) j++; }
    const im = this.imgs[j];
    if (im && im.naturalWidth && (j !== this.shown || force)) {
      const cw = this.canvas.width, ch = this.canvas.height;
      const s = Math.max(cw / im.naturalWidth, ch / im.naturalHeight);
      const w = im.naturalWidth * s, h = im.naturalHeight * s;
      this.ctx.drawImage(im, (cw - w) / 2, (ch - h) / 2, w, h);
      this.shown = j;
    }
    this.style.setProperty("--mashhad-progress", this.pos.toFixed(4));
    for (const b of this.beats) b.classList.toggle("mf-on", this.pos >= +b.dataset.from && this.pos <= +(b.dataset.to ?? 1));
    this.dispatchEvent(new CustomEvent("progress", { detail: this.pos }));
  }
}

if (!customElements.get("mashhad-film")) customElements.define("mashhad-film", MashhadFilm);
export default MashhadFilm;
