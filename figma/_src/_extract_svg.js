/* Извлекает из отрендеренного макета SVG по каждому экрану.
   Геометрия берётся из getBoundingClientRect, цвета/шрифты — из getComputedStyle,
   поэтому SVG совпадает с тем, что показывает приложение.
   Запускать в контексте страницы: (() => { <этот код>; return JSON.stringify(collect()); })() */

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function f(n) { return Math.round(n * 100) / 100; }

function col(c) {
  const m = String(c).match(/rgba?\(([^)]+)\)/);
  if (!m) return { hex: "#000000", a: 0 };
  const p = m[1].split(/[,\s\/]+/).filter(x => x !== "").map(Number);
  const a = p.length > 3 ? p[3] : 1;
  const h = n => ("0" + Math.max(0, Math.min(255, Math.round(n))).toString(16)).slice(-2);
  return { hex: "#" + h(p[0]) + h(p[1]) + h(p[2]), a: isNaN(a) ? 1 : a };
}

/* разбивает текст на строки по фактической вёрстке */
function lines(node) {
  const text = node.textContent;
  if (!text.trim()) return [];
  const r = document.createRange();
  const segs = [];
  let start = -1, curTop = null;
  for (let i = 0; i < text.length; i++) {
    r.setStart(node, i); r.setEnd(node, i + 1);
    const rect = r.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0 && !text[i].trim()) continue;
    const top = Math.round(rect.top);
    if (start < 0) { start = i; curTop = top; continue; }
    if (Math.abs(top - curTop) > 2) { segs.push([start, i]); start = i; curTop = top; }
  }
  if (start >= 0) segs.push([start, text.length]);
  return segs.map(function (p) {
    r.setStart(node, p[0]); r.setEnd(node, p[1]);
    const rect = r.getBoundingClientRect();
    return { t: text.slice(p[0], p[1]).replace(/\s+$/, ""), rect: rect };
  }).filter(s => s.t.trim().length);
}

function textSvg(seg, cs, fb) {
  const r = seg.rect;
  const x = r.left - fb.left, y = r.top - fb.top, h = r.height;
  const fs = parseFloat(cs.fontSize) || 14;
  const baseline = y + (h - fs) / 2 + fs * 0.8;
  const ls = (cs.letterSpacing && cs.letterSpacing !== "normal") ? parseFloat(cs.letterSpacing) : 0;
  const color = col(cs.color);
  let a = `x="${f(x)}" y="${f(baseline)}" font-family="Inter, -apple-system, Segoe UI, sans-serif"` +
    ` font-size="${f(fs)}" font-weight="${cs.fontWeight}" fill="${color.hex}"`;
  if (color.a < 1) a += ` fill-opacity="${f(color.a)}"`;
  if (ls) a += ` letter-spacing="${f(ls)}"`;
  if (cs.fontStyle === "italic") a += ` font-style="italic"`;
  if (cs.textTransform === "uppercase") a += ` text-transform="uppercase"`;
  return `<text ${a}>${esc(seg.t)}</text>`;
}

const SIDES = [
  ["borderTopWidth", "borderTopColor", 0], ["borderRightWidth", "borderRightColor", 1],
  ["borderBottomWidth", "borderBottomColor", 2], ["borderLeftWidth", "borderLeftColor", 3]
];

function walk(el, out, fb) {
  const cs = getComputedStyle(el);
  if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) < 0.02) return;
  const r = el.getBoundingClientRect();
  const x = r.left - fb.left, y = r.top - fb.top, w = r.width, h = r.height;
  if (w < 0.5 || h < 0.5) return;

  const self = [], kids = [];
  const bg = col(cs.backgroundColor);
  if (bg.a > 0.02) {
    const rad = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, w / 2, h / 2);
    self.push(`<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}" rx="${f(rad)}"` +
      ` fill="${bg.hex}" fill-opacity="${f(bg.a)}"/>`);
  }
  SIDES.forEach(function (s) {
    const bw = parseFloat(cs[s[0]]) || 0;
    if (bw < 0.4) return;
    const c = col(cs[s[1]]);
    if (c.a < 0.02) return;
    const rad = Math.min(parseFloat(cs.borderTopLeftRadius) || 0, w / 2, h / 2);
    let rw = w, rh = bw, rx = x, ry = y;
    if (s[2] === 2) ry = y + h - bw;
    if (s[2] === 3) { rw = bw; rh = h; }
    if (s[2] === 1) { rx = x + w - bw; rw = bw; rh = h; }
    self.push(`<rect x="${f(rx)}" y="${f(ry)}" width="${f(rw)}" height="${f(rh)}" rx="${f(Math.min(rad, 3))}"` +
      ` fill="${c.hex}" fill-opacity="${f(c.a)}"/>`);
  });

  el.childNodes.forEach(function (n) {
    if (n.nodeType === 3) {
      lines(n).forEach(s => self.push(textSvg(s, cs, fb)));
    }
  });

  el.children && Array.prototype.forEach.call(el.children, function (ch) { walk(ch, kids, fb); });

  const content = self.concat(kids);
  if (!content.length) return;
  const cls = (el.className && el.className.toString) ? el.className.toString().trim() : "";
  const isFrame = el.classList && el.classList.contains("frame");
  if (!isFrame && cls) {
    const name = cls.split(/\s+/).filter(Boolean).slice(0, 2).join(".");
    out.push(`<g id="${esc(name)}">` + content.join("") + "</g>");
  } else {
    content.forEach(c => out.push(c));
  }
}

function frameSvg(fr) {
  const fb = fr.getBoundingClientRect();
  const W = Math.round(fb.width), H = Math.round(fb.height);
  const out = [];
  const cs = getComputedStyle(fr);
  const bg = col(cs.backgroundColor);
  out.push(`<rect x="0" y="0" width="${W}" height="${H}" fill="${bg.hex}"/>`);
  // дети .frame
  Array.prototype.forEach.call(fr.children, ch => walk(ch, out, fb));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`
    + out.join("") + "</svg>";
}

function collect() {
  const res = [];
  document.querySelectorAll(".frame").forEach(function (fr, i) {
    res.push({ index: i + 1, name: fr.dataset.screen, svg: frameSvg(fr) });
  });
  return res;
}
