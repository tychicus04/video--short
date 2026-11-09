// buildNeon(scene) draws the resolved scene (.superpowers/sdd/2026-11-09-kieu-neon/runtime-contract.md) into #scene and returns
// its one paused GSAP timeline; index.html registers that at window.__timelines["main"]. Python has computed every position and
// time, so this only builds what the JSON says and animates it with the contract's eight actions. Looks follow
// docs/superpowers/specs/2026-11-09-kieu-neon-thu/template.html. Deterministic (nothing random, no endless repeat) and it never animates
// an element's display or visibility, only opacity; anything the JSON asks that this does not know throws.
function buildNeon(S) {
"use strict";
const NS = "http://www.w3.org/2000/svg";
const fail = msg => { throw new Error("kit: " + msg); };
const ICONS = (() => { const x = new XMLHttpRequest(); x.open("GET", "icons.json", false); x.send(); return JSON.parse(x.responseText); })();

const COLOR = { normal: "#2BE3FF", risk: "#FF4D61", claim: "#FFC53D", safe: "#3DFF9E", white: "#FFFFFF" };
const RGB = { normal: "43,227,255", risk: "255,77,97", claim: "255,197,61", safe: "61,255,158", white: "255,255,255" };
const FONT = { "BeVietnamPro-Bold.ttf": "f-bold", "BeVietnamPro-ExtraBold.ttf": "f-extra", "IBMPlexMono-SemiBold.ttf": "f-mono" };
const DIM = 0.35, FADE = 0.35, PALE = "#BFF6FF";
// render.py's title bar (its STRIPE, BAR, YELLOW, TEAL are in kit.css): the box is 569 × 164 as drawn there, the text starts 22 px in
const BAR = [94, 680, 662, 843], BAR_OUT = 0.45, STRIPE_OUT = 0.2;   // the box rolls back in 0.45 s, then the stripe shrinks in 0.2 (TITLE_OUT 0.65)

const H = (tag, cls, parent, css, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (css) e.style.cssText = css;
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
};
const V = (tag, attrs, parent) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
};
const box = (b, css = "") => `left:${b[0]}px;top:${b[1]}px;width:${b[2] - b[0]}px;height:${b[3] - b[1]}px;${css}`;
const glyphs = s => [...s.normalize("NFC")];
const svgIn = L => V("svg", { class: "sv", width: 1, height: 1 }, L);

const scene = document.getElementById("scene");
const tl = gsap.timeline({ paused: true });
const guard = [];   // [element, id] of every text line, which must stay inside its box

// ---------- elements ----------
// One record per element: its root (opacity = the element's own), one layer per colour it ever has, and what the actions need.
const els = {}, LEN = new WeakMap();   // LEN: a path's dash length
for (const e of S.elements) {
  if (els[e.id]) fail(`two elements have the id ${e.id}`);
  els[e.id] = { e, f: { draw: false, type: false }, tones: [e.tone || "white"], paths: [], lines: [], chars: [], cl: null, layers: {}, cur: e.tone || "white" };
}
const acts = [...S.actions].sort((a, b) => a.t - b.t);   // stable: equal times keep the JSON's order
const KNOWN = ["on", "draw", "type", "off", "tone", "flow", "move", "swap"];
for (const a of acts) {
  if (!KNOWN.includes(a.do)) fail(`unknown action "${a.do}" at ${a.t} s`);
  for (const id of a.ids) {
    const r = els[id] || fail(`action "${a.do}" at ${a.t} s: no element ${id}`);
    if (a.do === "draw" || a.do === "type") r.f[a.do] = true;
    if (a.do === "tone" && !["normal", "risk", "claim", "safe", "dim"].includes(a.to)) fail(`tone to "${a.to}" at ${a.t} s`);
    if (a.do === "tone" && a.to !== "dim" && !r.tones.includes(a.to)) r.tones.push(a.to);
  }
}

function iconG(r, svg, name, x, y, size, key, px) {   // the glow sits on a plain group: a filter on the scaled one would scale with it
  const paths = ICONS[name] || fail(`no icon "${name}"`);
  const g = V("g", { class: "g-" + key }, svg);
  const s = V("g", { transform: `translate(${x - size / 2},${y - size / 2}) scale(${size / 24})`, fill: "none", stroke: COLOR[key],
                     "stroke-width": px * 24 / size, "stroke-linecap": "round", "stroke-linejoin": "round" }, g);
  for (const d of paths) r.paths.push(V("path", { d }, s));
}

function words(r, parent, s) {   // a line's text: typed ones are a span per character, shown in place, so nothing reflows
  guard.push([parent, r.e.id]);
  if (r.f.type) r.cl.push(...glyphs(s).map(c => H("span", "ch", parent, null, c)));
  else parent.textContent = s;
}
const fontOf = e => FONT[e.font] || fail(`no font ${e.font} (${e.id})`);
const line = (r, L, key, b, size, css = "", font = fontOf(r.e)) =>   // one text line, `size` px, as wide as `b`
  H("div", `tx ${font} t-${key}`, L, box(b, `font-size:${size}px;line-height:${b[3] - b[1]}px;${css}`));

const KINDS = {
  icon: (r, L, key) => iconG(r, svgIn(L), r.e.icon, r.e.x, r.e.y, r.e.size, key, r.e.size >= 150 ? 4 : 3.5),   // 4 px at a hub
  badge: (r, L, key) => iconG(r, svgIn(L), r.e.icon, r.e.x, r.e.y, r.e.size, key, 2.5),
  hero(r, L, key) {
    const e = r.e;
    iconG(r, svgIn(L), e.icon, e.x, e.y, e.size, key, 4.5);
    if (e.label) words(r, line(r, L, key, e.label_box, 30, "text-align:center", "f-mono"), e.label);
  },
  tile(r, L, key) {
    const e = r.e, s = e.size;
    V("rect", { x: e.x - s / 2, y: e.y - s / 2, width: s, height: s, rx: 6, fill: `rgba(${RGB[key]},.16)`, stroke: COLOR[key], "stroke-width": 2.5 },
      V("g", { class: "g-" + key }, svgIn(L)));
  },
  link(r, L, key) {
    const e = r.e, g = V("g", { class: "g-" + key }, svgIn(L));
    const dx = e.x2 - e.x1, dy = e.y2 - e.y1, n = Math.hypot(dx, dy) || 1;
    const offs = e.style === "tunnel" ? [-6, 6] : e.style === "solid" || e.style === "dashed" ? [0] : fail(`link style ${e.style}`);
    for (const o of offs) {   // a tunnel is two rails 6 px either side of its line: layout.TUNNEL_HALF, which keeps text clear of them
      const ox = -dy / n * o, oy = dx / n * o;
      const l = V("line", { x1: e.x1 + ox, y1: e.y1 + oy, x2: e.x2 + ox, y2: e.y2 + oy, stroke: COLOR[key], "stroke-width": e.style === "dashed" ? 2 : 2.5,
                            "stroke-opacity": e.style === "dashed" ? 0.8 : 0.75, "stroke-linecap": e.style === "dashed" ? "butt" : "round" }, g);
      if (e.style === "dashed") l.setAttribute("stroke-dasharray", "6 9");
      r.lines.push({ el: l, x1: e.x1 + ox, y1: e.y1 + oy, x2: e.x2 + ox, y2: e.y2 + oy });
    }
  },
  label(r, L, key) {   // a node's label, a section's, a chip's are all one line in their box
    words(r, line(r, L, key, r.e.box, r.e.size, `text-align:${r.e.align === "center" ? "center" : "left"}`), r.e.text);
  },
  chip(r, L, key) {   // the frame (border 3, radius 40, padding 4 × 16) fills the box, the text is centred inside it
    const e = r.e, w = e.box[2] - e.box[0], h = e.box[3] - e.box[1];
    const frame = H("div", `chip t-${key}`, L, box(e.box));
    const d = H("div", `tx ${fontOf(e)} t-${key}`, frame,
                `left:16px;top:4px;width:${w - 38}px;height:${h - 14}px;line-height:${h - 14}px;font-size:${e.size}px;text-align:center`);
    words(r, d, e.text);
  },
  statement(r, L, key) {
    const e = r.e, lh = e.lh || (e.box[3] - e.box[1]) / e.lines.length;
    e.lines.forEach((s, i) => words(r, line(r, L, key, [e.box[0], e.box[1] + i * lh, e.box[2], e.box[1] + (i + 1) * lh], e.size, "text-align:center"), s));
  },
  quote(r, L, key) {   // the spike's bubble: 540 wide, its body 310 high (more with a 4th line), a tail hanging from its lower left
    const e = r.e, [x0, y0, x1, y1] = e.box, pitch = e.size * 1.16, top = y0 + 78, B = Math.max(y0 + 310, top + e.lines.length * pitch + 24);
    const T = Math.min(y1, B + 58);
    const g = V("g", { class: "g-" + key, fill: "none", stroke: COLOR[key], "stroke-width": 4, "stroke-linejoin": "round" }, svgIn(L));
    r.paths.push(V("path", { d: `M${x0 + 28} ${y0} H${x1 - 28} Q${x1} ${y0} ${x1} ${y0 + 28} V${B - 28} Q${x1} ${B} ${x1 - 28} ${B} H${x0 + 130} ` +
                             `L${x0 + 70} ${T} L${x0 + 80} ${B} H${x0 + 28} Q${x0} ${B} ${x0} ${B - 28} V${y0 + 28} Q${x0} ${y0} ${x0 + 28} ${y0} Z` }, g));
    const wide = x1 - x0 - 60;   // the spike's text: 36 px inside the bubble on the left, 24 on the right (480 of 540)
    words(r, H("div", `tx f-mono t-${key}`, L, `left:${x0 + 36}px;top:${y0 + 24}px;width:${wide}px;height:33px;font-size:24px;line-height:33px`), e.who);
    e.lines.forEach((s, i) => {
      const d = H("div", "tx f-extra", L, `left:${x0 + 36}px;top:${top + i * pitch}px;width:${wide}px;height:${pitch}px;font-size:${e.size}px;` +
                                         `line-height:${pitch}px;color:#fff;text-shadow:0 0 14px rgba(${RGB[key]},.35)`);
      words(r, d, s);
    });
  },
};

KINDS.section = KINDS.label;
for (const r of Object.values(els)) {
  const build = KINDS[r.e.kind] || fail(`unknown element kind "${r.e.kind}" (${r.e.id})`);
  r.root = H("div", "el", scene);
  for (const key of r.tones) {
    r.layers[key] = H("div", "lay", r.root, key === r.tones[0] ? null : "opacity:0");
    r.chars.push(r.cl = []);
    build(r, r.layers[key], key);
  }
  if (!r.f.draw) continue;
  for (const p of r.paths) {   // a path that is drawn some time is one dash as long as itself: whole at offset 0, hidden at `len`
    const len = Math.ceil(p.getTotalLength()) + 2;
    p.style.strokeDasharray = len;
    LEN.set(p, len);
  }
}

// ---------- actions ----------
const show = (r, t) => tl.to(r.root, { opacity: 1, duration: 0.01 }, t);
const of = a => a.ids.map(id => els[id]);
const DO = {
  on(a) {   // blinks in: 0 → 1 → .25 → 1 → .6 → 1 over 0.2 s
    for (const r of of(a)) tl.to(r.root, { keyframes: { opacity: [0, 1, 0.25, 1, 0.6, 1] }, duration: 0.2, ease: "none" }, a.t);
  },
  draw(a) {
    for (const r of of(a)) {
      if (!r.paths.length && !r.lines.length) fail(`draw at ${a.t} s: ${r.e.id} (${r.e.kind}) has no stroke`);
      show(r, a.t);
      // a stroke stands drawn until its draw starts (an `on` before it shows the whole thing; a draw after an `off` draws again):
      // at a.t it is emptied, then grown
      for (const p of r.paths) tl.set(p, { strokeDashoffset: LEN.get(p) }, a.t);
      for (const l of r.lines) tl.set(l.el, { attr: { x2: l.x1, y2: l.y1 } }, a.t);
      if (r.paths.length) tl.to(r.paths, { strokeDashoffset: 0, duration: a.d, ease: "power2.inOut" }, a.t);
      for (const l of r.lines) tl.to(l.el, { attr: { x2: l.x2, y2: l.y2 }, duration: a.d, ease: "power2.inOut" }, a.t);   // dashes stay put as the line grows
    }
  },
  type(a) {
    for (const r of of(a)) {
      if (!r.chars[0].length) fail(`type at ${a.t} s: ${r.e.id} (${r.e.kind}) has no text`);
      show(r, a.t);
      for (const list of r.chars) tl.to(list, { opacity: 1, duration: 0.001, stagger: a.d / list.length, ease: "none" }, a.t);   // every colour layer types together
    }
  },
  off(a) {
    for (const r of of(a)) tl.to(r.root, { opacity: 0, duration: a.d, ease: "power1.out" }, a.t);
  },
  tone(a) {
    for (const r of of(a)) {
      if (a.to === "dim") { tl.to(r.root, { opacity: DIM, duration: FADE }, a.t); continue; }
      if (a.to !== r.cur) {   // two stacked layers, one fading out as the other fades in
        tl.to(r.layers[r.cur], { opacity: 0, duration: FADE, ease: "none" }, a.t);
        tl.to(r.layers[a.to], { opacity: 1, duration: FADE, ease: "none" }, a.t);
        r.cur = a.to;
      }
      tl.to(r.root, { opacity: 1, duration: FADE }, a.t);
    }
  },
  flow(a) {   // a dot runs the link n times, then fades
    for (const r of of(a)) {
      const e = r.e, [sx, sy, ex, ey] = a.dir === "b-a" ? [e.x2, e.y2, e.x1, e.y1] : a.dir === "a-b" ? [e.x1, e.y1, e.x2, e.y2] : fail(`flow dir ${a.dir}`);
      const root = H("div", "el", scene), dot = V("circle", { cx: sx, cy: sy, r: 5, fill: PALE }, V("g", { class: "g-normal" }, svgIn(H("div", "lay", root))));
      tl.to(root, { opacity: 1, duration: 0.05 }, a.t);
      tl.to(dot, { attr: { cx: ex, cy: ey }, duration: a.d, repeat: a.repeat - 1, ease: "none" }, a.t);
      tl.to(root, { opacity: 0, duration: 0.1 }, a.t + a.repeat * a.d);
    }
  },
  move(a) {   // the tile appears at its `from` and flies to where it rests
    of(a).forEach((r, i) => {
      show(r, a.t);
      tl.fromTo(r.root, { x: a.from[i][0] - r.e.x, y: a.from[i][1] - r.e.y }, { x: 0, y: 0, duration: a.d, ease: "power2.inOut", immediateRender: false }, a.t);
    });
  },
  swap(a) {   // ids = [old, new]
    const [o, n] = of(a);
    tl.to(o.root, { opacity: 0, duration: FADE, ease: "none" }, a.t);
    tl.to(n.root, { opacity: 1, duration: FADE, ease: "none" }, a.t);
  },
};
const D = { off: FADE, flow: 0.85, move: 0.6 };   // what an action without `d` takes
for (const a of acts) {
  const act = { d: D[a.do], ...a };
  if (["draw", "type", "off", "flow", "move"].includes(a.do) && !(act.d > 0)) fail(`${a.do} at ${a.t} s has no duration`);
  DO[a.do](act);
}

// ---------- captions, title bar, logo (not elements: the checks never count them) ----------
for (const [a, b, text] of S.captions) {
  const c = H("div", "cap", scene, null, text);
  tl.to(c, { opacity: 1, duration: 0.01 }, a);
  tl.to(c, { opacity: 0, duration: 0.01 }, b);
}

if (S.title) {   // render.title_card: stripe from its middle, box left → right, typed with a cursor, then rolled back right → left
  const T = S.title, n = T.lines.reduce((s, l) => s + glyphs(l).length, 0), pitch = Math.round(T.size * 1.32);
  const stripe = H("div", "tb-stripe", scene), tb = H("div", "tb-box", scene), inner = H("div", "tb-in", tb);
  const y0 = (BAR[1] + BAR[3]) / 2 - pitch * T.lines.length / 2 - BAR[1];
  let k = 0;
  T.lines.forEach((ln, i) => {
    const d = H("div", "tb-line", inner, `top:${y0 + i * pitch}px;font-size:${T.size}px`);
    for (const c of glyphs(ln)) {
      const ch = H("span", "ch", d, null, c), cur = H("i", "cur", ch, `top:${T.size * 0.18}px;width:${Math.max(3, Math.floor(T.size / 9))}px;height:${T.size * 0.94}px`);
      const t = T.t0 + (T.t1 - T.t0) * (k + 0.5) / n, next = k + 1 < n ? T.t0 + (T.t1 - T.t0) * (k + 1.5) / n : T.t1;
      tl.to(ch, { opacity: 1, duration: 0.001 }, t);
      tl.to(cur, { opacity: 1, duration: 0.001 }, t);   // the cursor stands after the newest letter, only while typing
      tl.to(cur, { opacity: 0, duration: 0.001 }, next - 0.001);
      k++;
    }
  });
  tl.fromTo(stripe, { scaleY: 0 }, { scaleY: 1, duration: 0.25, ease: "power2.out" }, 0);
  tl.fromTo(tb, { width: 0 }, { width: BAR[2] - BAR[0] + 1, duration: 0.5, ease: "power2.out" }, 0.15);
  tl.to(tb, { width: 0, duration: BAR_OUT, ease: "power2.out" }, T.out);
  tl.to(stripe, { scaleY: 0, duration: STRIPE_OUT, ease: "power2.out" }, T.out + BAR_OUT);
}

const logo = H("div", "logo", scene);
H("img", null, logo).src = "anm-logo.png";
tl.to(logo, { opacity: 1, duration: 0.3 }, 0);

tl.to({}, { duration: S.total }, 0);   // the timeline is as long as the clip

// a text must fit its box (layout measured it with 6 % to spare): wider than that is a bug in the scene, and loud
document.fonts.ready.then(() => {
  const bad = guard.filter(([d]) => d.scrollWidth > d.clientWidth + 1).map(([d, id]) => `${id} (${d.scrollWidth} px in ${d.clientWidth})`);
  if (bad.length) console.error("kit: text wider than its box: " + bad.join(", "));
});
return tl;
}
