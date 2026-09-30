"""Offline box editor: one self-contained HTML page per export (artifacts/relabel/<export>/editor.html).

Open it in the browser (double click, no server, no internet), correct the boxes page by
page, then save _annotations.coco.json (and page_types.csv if a doc type was changed) back
into labels/<export>/. Everything the page needs is embedded; images are loaded from the
images/ folder next to it. Intermediate state is kept in the browser (localStorage).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..data.labels import match_to_coco, read_label_table

CLASS_COLORS = ["#1f6feb", "#d6336c", "#e8590c", "#0ca678", "#7048e8", "#a61e4d", "#5c940d", "#495057"]


def editor_data(export: str, coco: dict, coco_name: str, meta: dict, classes: list[str], doc_types: list[str],
                csv_path: Path | None) -> dict:
    """meta: {image id: {split, doc_type, changes: [str], orig: [[cls, x1, y1, x2, y2] px]}}"""
    name_of = {c["id"]: c["name"] for c in coco["categories"]}
    boxes: dict = {}
    other = []
    for a in coco["annotations"]:
        n = name_of.get(a["category_id"])
        if n is None or (n not in classes and not n.startswith("vorschlag_")):
            other.append(a)  # categories the detector does not know: kept untouched
            continue
        x, y, w, h = a["bbox"]
        src = (a.get("attributes") or {}).get("quelle", "label")
        boxes.setdefault(a["image_id"], []).append(
            {"cls": n.removeprefix("vorschlag_"), "x1": x, "y1": y, "x2": x + w, "y2": y + h, "source": src,
             "score": (a.get("attributes") or {}).get("score")})
    csv = None
    csv_key = {}
    if csv_path is not None and csv_path.is_file():
        values, info = read_label_table(csv_path)
        records = info.pop("records")
        fns = [img["file_name"] for img in coco["images"]]
        for fn_csv in records:
            m, _ = match_to_coco({fn_csv: "x"}, fns)
            for coco_fn in m:
                csv_key[coco_fn] = fn_csv
        csv = {"name": csv_path.name, "delimiter": info["delimiter"], "columns": info["columns"],
               "file_col": info["file_col"], "value_col": info["value_col"], "rows": list(records.values())}
    pages = []
    for img in coco["images"]:
        m = meta.get(img["id"], {})
        pages.append({"id": img["id"], "file_name": img["file_name"], "src": img["file_name"],
                      "w": img["width"], "h": img["height"], "split": m.get("split", "-"),
                      "doc_type": m.get("doc_type") or "", "csv_key": csv_key.get(img["file_name"]),
                      "changes": m.get("changes", []), "orig": m.get("orig", []),
                      "boxes": boxes.get(img["id"], [])})
    base = {k: v for k, v in coco.items() if k not in ("annotations",)}
    base["categories"] = [c for c in coco["categories"] if not c["name"].startswith("vorschlag_")]
    return {"export": export, "coco_name": coco_name, "classes": classes,
            "colors": {c: CLASS_COLORS[i % len(CLASS_COLORS)] for i, c in enumerate(classes)},
            "doc_types": doc_types, "coco": base, "other_annotations": other, "pages": pages, "csv": csv}


def write_editor(out_dir: Path, data: dict, lang: str = "de") -> Path:
    import html as _html

    from .i18n import CLASS_NAMES, DOC_TYPE_NAMES, EDITOR, SUFFIX

    t = EDITOR[lang]
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    js_t = {k: v for k, v in t.items() if k not in ("help", "note")}
    js_t.update(cls=CLASS_NAMES[lang], dt=DOC_TYPE_NAMES[lang])
    fill = {**{k: _html.escape(str(v)) for k, v in t.items() if isinstance(v, str)},
            "help": "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in t["help"]),
            "note": t["note"].replace("{export}", _html.escape(data["export"]))}
    page = TEMPLATE
    for k, v in fill.items():
        page = page.replace("{{" + k + "}}", v)
    page = (page.replace("__TITLE__", _html.escape(f"{t['title']} {data['export']}"))
            .replace("__I18N__", json.dumps(js_t, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__DATA__", blob))
    path = out_dir / f"editor{SUFFIX[lang]}.html"
    path.write_text(page, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="{{html_lang}}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#d9d9de;--panel:#f5f5f7;--sel:#e7f0ff;--ok:#2b8a3e;--warn:#e8590c}
*{box-sizing:border-box}
body{margin:0;font:14px/1.4 system-ui,sans-serif;color:var(--fg);background:var(--bg);height:100vh;display:flex;flex-direction:column}
header{display:flex;gap:12px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:16px;margin:0 8px 0 0}
button,select{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
button.primary{background:#1f6feb;color:#fff;border-color:#1f6feb}
button:disabled{opacity:.5;cursor:default}
.muted{color:var(--muted)}
main{flex:1;display:flex;min-height:0}
aside{width:260px;border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
aside .filters{padding:8px;display:flex;gap:6px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
#list{overflow:auto;flex:1}
#list div{padding:5px 10px;cursor:pointer;border-bottom:1px solid #f0f0f2;display:flex;gap:6px;align-items:center}
#list div.cur{background:var(--sel)}
#list .dot{width:10px;height:10px;border-radius:50%;border:1px solid var(--muted);flex:none}
#list .dot.done{background:var(--ok);border-color:var(--ok)}
#list .n{margin-left:auto;font-size:12px;color:var(--warn)}
#stage{flex:1;overflow:auto;background:#e9e9ee;position:relative}
#wrap{position:relative;margin:12px;display:inline-block;box-shadow:0 1px 4px rgba(0,0,0,.25)}
#wrap img{display:block;user-select:none;-webkit-user-drag:none}
#wrap svg{position:absolute;left:0;top:0;width:100%;height:100%;cursor:crosshair}
section#side{width:280px;border-left:1px solid var(--line);padding:10px;overflow:auto}
section#side h2{font-size:14px;margin:12px 0 6px}
.cls{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:6px;cursor:pointer}
.cls.cur{outline:2px solid var(--fg)}
.sw{width:14px;height:14px;border-radius:3px}
kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 4px;font-size:12px;background:#fff}
#changes li{margin-bottom:2px}
#notice{padding:6px 12px;background:#fff4e6;border-bottom:1px solid var(--line);display:none}
table.help td{padding:1px 4px;vertical-align:top}
</style></head><body>
<header>
  <h1 id="title"></h1>
  <span id="progress" class="muted"></span>
  <span style="flex:1"></span>
  <label>{{doctype}} <select id="doctype"></select></label>
  <button id="done" title="Enter">{{done}}</button>
  <button id="save" class="primary">{{save}}</button>
  <button id="savecsv">{{savecsv}}</button>
</header>
<div id="notice"></div>
<main>
  <aside>
    <div class="filters">
      <select id="filter"><option value="all">{{f_all}}</option><option value="changed">{{f_changed}}</option>
      <option value="open">{{f_open}}</option></select>
    </div>
    <div id="list"></div>
  </aside>
  <div id="stage"><div id="wrap"><img id="img" alt=""><svg id="svg"></svg></div></div>
  <section id="side">
    <div id="pageinfo" class="muted"></div>
    <h2>{{h_class}}</h2><div id="classes"></div>
    <h2>{{h_sel}}</h2><div id="selinfo" class="muted">{{sel_none}}</div>
    <h2>{{h_changes}}</h2><ul id="changes" style="padding-left:18px;margin:0"></ul>
    <h2>{{h_help}}</h2>
    <table class="help">{{help}}</table>
    <p class="muted">{{note}}</p>
  </section>
</main>
<script id="i18n" type="application/json">__I18N__</script>
<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const T = JSON.parse(document.getElementById("i18n").textContent);
const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (m, k) => (o[k] !== undefined ? o[k] : m));
const cname = c => (T.cls && T.cls[c]) || c;
const KEY = "docval-editor:" + D.export + ":" + D.pages.length + ":" + D.coco_name;
const $ = id => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
let state = {pages: {}}, cur = 0, curCls = D.classes[0], sel = -1, zoom = null, showOrig = false;
const undo = {};

function page() { return D.pages[cur]; }
function ps(p) {                       // editable state of a page
  p = p || page();
  if (!state.pages[p.id]) state.pages[p.id] = {boxes: JSON.parse(JSON.stringify(p.boxes)), reviewed: false,
                                               doc_type: p.doc_type};
  return state.pages[p.id];
}
function persist() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function restore() {
  try {
    const s = localStorage.getItem(KEY);
    if (s) {
      state = JSON.parse(s);
      const n = Object.values(state.pages).filter(x => x.reviewed).length;
      const el = $("notice");
      el.style.display = "block";
      el.textContent = fmt(T.loaded, {n: n});
      const b = document.createElement("button");
      b.textContent = T.discard;
      b.onclick = () => { if (confirm(T.confirm_discard)) {
        try { localStorage.removeItem(KEY); } catch (e) {} state = {pages: {}}; el.style.display = "none"; show(cur); } };
      el.appendChild(b);
    }
  } catch (e) {}
}
function pushUndo() {
  const id = page().id;
  (undo[id] = undo[id] || []).push(JSON.stringify(ps().boxes));
  if (undo[id].length > 100) undo[id].shift();
}
function doUndo() {
  const u = undo[page().id];
  if (u && u.length) { ps().boxes = JSON.parse(u.pop()); if (sel >= ps().boxes.length) sel = -1; persist(); draw(); }
}

// ------------------------------------------------------------------ list
function filtered() {
  const f = $("filter").value;
  return D.pages.map((p, i) => i).filter(i => {
    const p = D.pages[i];
    if (f === "changed") return p.changes.length > 0;
    if (f === "open") return !ps(p).reviewed;
    return true;
  });
}
function renderList() {
  const L = $("list");
  L.innerHTML = "";
  for (const i of filtered()) {
    const p = D.pages[i], s = ps(p);
    const d = document.createElement("div");
    if (i === cur) d.className = "cur";
    d.innerHTML = '<span class="dot' + (s.reviewed ? " done" : "") + '"></span><span></span>'
      + (p.changes.length ? '<span class="n">' + p.changes.length + " " + T.short_prop + "</span>" : "");
    d.children[1].textContent = p.file_name.split("/").pop() + " · " + ((T.dt && T.dt[s.doc_type]) || s.doc_type || "–");
    d.onclick = () => show(i);
    L.appendChild(d);
  }
  const done = D.pages.filter(p => ps(p).reviewed).length;
  $("progress").textContent = fmt(T.progress, {done: done, total: D.pages.length});
}

// ------------------------------------------------------------------ page
function show(i) {
  cur = Math.max(0, Math.min(D.pages.length - 1, i));
  sel = -1;
  const p = page();
  const img = $("img");
  img.onload = () => { fit(); draw(); };
  img.onerror = () => { $("pageinfo").textContent = T.img_missing + p.src; };
  img.src = p.src;
  $("svg").setAttribute("viewBox", "0 0 " + p.w + " " + p.h);
  $("doctype").value = ps(p).doc_type;
  $("pageinfo").textContent = p.file_name + " · Split " + p.split + " · " + p.w + "×" + p.h;
  const C = $("changes");
  C.innerHTML = "";
  for (const c of p.changes) {
    const li = document.createElement("li");
    li.textContent = typeof c === "string" ? c : ((T.actions[c.action] || c.action) + " " + cname(c.cls)
      + (c.score != null ? " (" + T.score + " " + Number(c.score).toFixed(2) + ")" : ""));
    C.appendChild(li);
  }
  if (!p.changes.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = T.none; C.appendChild(li); }
  renderList();
  const cd = $("list").querySelector(".cur");
  if (cd) cd.scrollIntoView({block: "nearest"});
  draw();
}
function fit() {
  const st = $("stage"), p = page();
  zoom = zoom || Math.min((st.clientWidth - 24) / p.w, 3);
  setZoom(zoom);
}
function setZoom(z) {
  zoom = Math.max(0.1, Math.min(4, z));
  const p = page();
  $("img").style.width = (p.w * zoom) + "px";
  $("img").style.height = (p.h * zoom) + "px";
  draw();
}

// ------------------------------------------------------------------ drawing
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function draw() {
  const svg = $("svg"), p = page(), s = ps(p);
  svg.innerHTML = "";
  const u = 1 / (zoom || 1);                  // one screen pixel in image pixels
  if (showOrig) for (const o of p.orig) {
    el("rect", {x: o[1], y: o[2], width: o[3] - o[1], height: o[4] - o[2], fill: "none", stroke: "#868e96",
                "stroke-width": 2 * u, "stroke-dasharray": (3 * u) + " " + (3 * u), "pointer-events": "none"}, svg);
  }
  s.boxes.forEach((b, i) => {
    const col = D.colors[b.cls] || "#000";
    const g = el("g", {}, svg);
    const r = el("rect", {x: b.x1, y: b.y1, width: b.x2 - b.x1, height: b.y2 - b.y1,
      fill: i === sel ? col + "22" : "transparent", stroke: col, "stroke-width": (i === sel ? 3 : 2) * u,
      "stroke-dasharray": b.source === "modell" ? (8 * u) + " " + (4 * u) : "none", style: "cursor:move"}, g);
    r.dataset.i = i;
    const t = el("text", {x: b.x1 + 2 * u, y: b.y1 - 4 * u, fill: col, "font-size": 13 * u,
      "font-family": "system-ui,sans-serif", "font-weight": 600, "pointer-events": "none"}, g);
    t.textContent = cname(b.cls) + (b.source === "modell" && b.score != null ? " " + Number(b.score).toFixed(2) : "");
    if (i === sel) {
      for (const [hx, hy, k] of handles(b)) {
        const h = el("rect", {x: hx - 5 * u, y: hy - 5 * u, width: 10 * u, height: 10 * u, fill: "#fff",
                              stroke: col, "stroke-width": 2 * u, style: "cursor:" + cursorOf(k)}, g);
        h.dataset.i = i; h.dataset.h = k;
      }
    }
  });
  renderSide();
}
function handles(b) {
  const mx = (b.x1 + b.x2) / 2, my = (b.y1 + b.y2) / 2;
  return [[b.x1, b.y1, "nw"], [mx, b.y1, "n"], [b.x2, b.y1, "ne"], [b.x2, my, "e"],
          [b.x2, b.y2, "se"], [mx, b.y2, "s"], [b.x1, b.y2, "sw"], [b.x1, my, "w"]];
}
function cursorOf(k) { return {n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
                              nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize"}[k]; }
function renderSide() {
  const C = $("classes");
  C.innerHTML = "";
  D.classes.forEach((c, i) => {
    const d = document.createElement("div");
    d.className = "cls" + (c === curCls ? " cur" : "");
    d.innerHTML = '<kbd>' + (i + 1) + '</kbd><span class="sw" style="background:' + D.colors[c] + '"></span><span></span>';
    d.children[2].textContent = cname(c);
    d.onclick = () => setClass(c);
    C.appendChild(d);
  });
  const s = ps(), b = s.boxes[sel];
  $("selinfo").textContent = b ? cname(b.cls) + " · " + (T.src[b.source] || b.source)
    + " · " + Math.round(b.x2 - b.x1) + "×" + Math.round(b.y2 - b.y1) + " px" : T.sel_none;
}
function setClass(c) {
  curCls = c;
  const s = ps();
  if (sel >= 0 && s.boxes[sel] && s.boxes[sel].cls !== c) {
    pushUndo(); s.boxes[sel].cls = c; s.boxes[sel].source = "manuell"; persist();
  }
  draw();
}

// ------------------------------------------------------------------ mouse
let drag = null;
function pt(ev) {
  const r = $("svg").getBoundingClientRect(), p = page();
  return [(ev.clientX - r.left) / r.width * p.w, (ev.clientY - r.top) / r.height * p.h];
}
function clampBox(b) {
  const p = page();
  const x1 = Math.min(b.x1, b.x2), x2 = Math.max(b.x1, b.x2), y1 = Math.min(b.y1, b.y2), y2 = Math.max(b.y1, b.y2);
  b.x1 = Math.max(0, x1); b.y1 = Math.max(0, y1); b.x2 = Math.min(p.w, x2); b.y2 = Math.min(p.h, y2);
}
$("svg").addEventListener("pointerdown", ev => {
  if (ev.button !== 0) return;
  const [x, y] = pt(ev), s = ps(), t = ev.target;
  $("svg").setPointerCapture(ev.pointerId);
  if (t.dataset && t.dataset.h) {
    sel = +t.dataset.i; pushUndo();
    drag = {mode: "resize", h: t.dataset.h, start: [x, y], orig: Object.assign({}, s.boxes[sel]), moved: false};
  } else if (t.dataset && t.dataset.i !== undefined) {
    sel = +t.dataset.i; pushUndo();
    drag = {mode: "move", start: [x, y], orig: Object.assign({}, s.boxes[sel]), moved: false};
  } else {
    sel = -1;
    drag = {mode: "new", start: [x, y], moved: false};
  }
  draw();
});
$("svg").addEventListener("pointermove", ev => {
  if (!drag) return;
  const [x, y] = pt(ev), s = ps(), dx = x - drag.start[0], dy = y - drag.start[1];
  if (Math.abs(dx) + Math.abs(dy) > 2 / zoom) drag.moved = true;
  if (!drag.moved) return;
  if (drag.mode === "new") {
    if (sel < 0) { pushUndo(); s.boxes.push({cls: curCls, x1: x, y1: y, x2: x, y2: y, source: "manuell", score: null});
                   sel = s.boxes.length - 1; }
    Object.assign(s.boxes[sel], {x1: drag.start[0], y1: drag.start[1], x2: x, y2: y});
  } else if (drag.mode === "move") {
    const o = drag.orig, p = page();
    const w = o.x2 - o.x1, h = o.y2 - o.y1;
    const nx = Math.max(0, Math.min(p.w - w, o.x1 + dx)), ny = Math.max(0, Math.min(p.h - h, o.y1 + dy));
    Object.assign(s.boxes[sel], {x1: nx, y1: ny, x2: nx + w, y2: ny + h});
  } else {
    const o = drag.orig, b = s.boxes[sel], k = drag.h;
    if (k.includes("w")) b.x1 = o.x1 + dx;
    if (k.includes("e")) b.x2 = o.x2 + dx;
    if (k.includes("n")) b.y1 = o.y1 + dy;
    if (k.includes("s")) b.y2 = o.y2 + dy;
  }
  draw();
});
$("svg").addEventListener("pointerup", ev => {
  if (!drag) return;
  const s = ps();
  if (drag.moved && sel >= 0 && s.boxes[sel]) {
    const b = s.boxes[sel];
    clampBox(b);
    if (b.x2 - b.x1 < 3 || b.y2 - b.y1 < 3) { s.boxes.splice(sel, 1); sel = -1; }
    else if (drag.mode !== "new") b.source = "manuell";
    persist();
  } else if (!drag.moved && drag.mode !== "new") {
    const u = undo[page().id]; if (u) u.pop();       // plain click: nothing changed
  }
  drag = null;
  draw();
});
$("stage").addEventListener("wheel", ev => {
  if (!ev.ctrlKey) return;
  ev.preventDefault();
  setZoom(zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15));
}, {passive: false});

// ------------------------------------------------------------------ keys
document.addEventListener("keydown", ev => {
  if (ev.target.tagName === "SELECT" || ev.target.tagName === "INPUT") return;
  const s = ps(), k = ev.key;
  if ((ev.ctrlKey || ev.metaKey) && k.toLowerCase() === "z") { ev.preventDefault(); doUndo(); return; }
  if (ev.ctrlKey || ev.metaKey) return;
  if (/^[1-9]$/.test(k) && D.classes[+k - 1]) { setClass(D.classes[+k - 1]); return; }
  if ((k === "Delete" || k === "Backspace") && sel >= 0) {
    ev.preventDefault(); pushUndo(); s.boxes.splice(sel, 1); sel = -1; persist(); draw(); return;
  }
  if (k.startsWith("Arrow") && sel >= 0) {
    ev.preventDefault();
    const st = ev.shiftKey ? 10 : 1, b = s.boxes[sel];
    const d = {ArrowLeft: [-st, 0], ArrowRight: [st, 0], ArrowUp: [0, -st], ArrowDown: [0, st]}[k];
    pushUndo();
    if (ev.altKey) { b.x2 += d[0]; b.y2 += d[1]; } else { b.x1 += d[0]; b.x2 += d[0]; b.y1 += d[1]; b.y2 += d[1]; }
    clampBox(b); b.source = "manuell"; persist(); draw(); return;
  }
  if (k === "a" || k === "A") { step(-1); return; }
  if (k === "d" || k === "D") { step(1); return; }
  if (k === "Enter") { ev.preventDefault(); markDone(); return; }
  if (k === "Escape") { sel = -1; draw(); return; }
  if (k === "o" || k === "O") { showOrig = !showOrig; draw(); return; }
  if (k === "+") { setZoom(zoom * 1.2); return; }
  if (k === "-") { setZoom(zoom / 1.2); return; }
  if (k === "0") { zoom = null; fit(); return; }
});
function step(d) {
  const f = filtered();
  const pos = f.indexOf(cur);
  if (pos < 0) { if (f.length) show(f[0]); return; }
  const n = f[pos + d];
  if (n !== undefined) show(n);
}
function markDone() {
  const s = ps();
  s.reviewed = true;
  persist();
  const f = filtered();                      // in "ungeprüft" the current page just left the list
  const next = f.find(i => i > cur);
  if (next !== undefined) show(next); else { renderList(); draw(); }
}
$("done").onclick = markDone;
$("filter").onchange = () => { renderList(); };
$("doctype").onchange = ev => { ps().doc_type = ev.target.value; persist(); renderList(); };

// ------------------------------------------------------------------ save
function r1(v) { return Math.round(v * 10) / 10; }
function buildCoco() {
  const coco = JSON.parse(JSON.stringify(D.coco));
  const cid = {};
  for (const c of coco.categories) cid[c.name] = c.id;
  for (const c of D.classes) if (cid[c] === undefined) {
    const id = Math.max(0, ...coco.categories.map(x => x.id)) + 1;
    coco.categories.push({id: id, name: c, supercategory: (coco.categories[0] || {}).supercategory || "none"});
    cid[c] = id;
  }
  const anns = JSON.parse(JSON.stringify(D.other_annotations));
  let aid = Math.max(0, ...anns.map(a => a.id || 0)) + 1;
  for (const p of D.pages) for (const b of ps(p).boxes) {
    const w = b.x2 - b.x1, h = b.y2 - b.y1;
    anns.push({id: aid++, image_id: p.id, category_id: cid[b.cls], bbox: [r1(b.x1), r1(b.y1), r1(w), r1(h)],
               area: r1(w * h), segmentation: [], iscrowd: 0});
  }
  coco.annotations = anns;
  return JSON.stringify(coco, null, 1);
}
function buildCsv() {
  const c = D.csv;
  const cols = c ? c.columns : ["file_name", "doc_type"];
  const fc = c ? c.file_col : "file_name", vc = c ? c.value_col : "doc_type", dl = c ? c.delimiter : ";";
  const rows = c ? JSON.parse(JSON.stringify(c.rows)) : [];
  const byKey = {};
  rows.forEach(r => byKey[r[fc]] = r);
  for (const p of D.pages) {
    const t = ps(p).doc_type || "";
    const key = p.csv_key || p.file_name;
    if (!byKey[key]) { const r = {}; cols.forEach(x => r[x] = ""); r[fc] = key; rows.push(r); byKey[key] = r; }
    byKey[key][vc] = t;
  }
  const q = v => { v = v == null ? "" : String(v); return /["\n\r]/.test(v) || v.includes(dl) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  return [cols.map(q).join(dl)].concat(rows.map(r => cols.map(x => q(r[x])).join(dl))).join("\r\n") + "\r\n";
}
async function saveText(name, text, mime) {
  if (window.showSaveFilePicker) {
    try {
      const h = await window.showSaveFilePicker({suggestedName: name});
      const w = await h.createWritable(); await w.write(text); await w.close();
      return true;
    } catch (e) { if (e && e.name === "AbortError") return false; }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type: mime}));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  return true;
}
$("save").onclick = async () => {
  const open = D.pages.filter(p => !ps(p).reviewed).length;
  if (open && !confirm(fmt(T.confirm_open, {n: open}))) return;
  await saveText(D.coco_name, buildCoco(), "application/json");
};
$("savecsv").onclick = () => saveText(D.csv ? D.csv.name : "page_types.csv", buildCsv(), "text/csv");
window.addEventListener("resize", () => draw());
// keyboard shortcuts must keep working after a click on a button or a doc type change
document.querySelectorAll("button").forEach(b => b.addEventListener("click", () => b.blur()));
$("doctype").addEventListener("change", ev => ev.target.blur());
$("filter").addEventListener("change", ev => ev.target.blur());

// ------------------------------------------------------------------ start
$("title").textContent = T.title + " " + D.export;
const dt = $("doctype");
for (const t of [""].concat(D.doc_types)) { const o = document.createElement("option"); o.value = t; o.textContent = t ? ((T.dt && T.dt[t]) || t) : "–"; dt.appendChild(o); }
restore();
for (const p of D.pages) {                   // a doc type unknown to the config stays selectable
  const t = ps(p).doc_type;
  if (t && !D.doc_types.includes(t)) { D.doc_types.push(t); const o = document.createElement("option"); o.value = t; o.textContent = t; dt.appendChild(o); }
}
show(0);
</script></body></html>
"""
