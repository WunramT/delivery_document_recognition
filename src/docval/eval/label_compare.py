"""Old vs. new labels of one export, as a self-contained HTML page to show colleagues.

    make compare-labels EXPORT=425_21.09.2026 [OLD=path/to/old_annotations.coco.json]

Old labels come from OLD, else from a backup next to the current file in the export folder
(e.g. _annotations.coco.alt.json), else from the label editor of `make relabel`
(artifacts/relabel/<export>/editor.html keeps the labels as they were before editing).
Images are embedded, so the page can be sent as a single file.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
import statistics
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import artifacts, resolve
from ..data.coco import find_image, load_coco
from ..detect.onnx_detector import iou
from ..zones.synthetic import to_rgb
from .label_editor import CLASS_COLORS

KEEP_IOU = 0.9   # old and new box practically identical

DEFAULT_GUIDE = {
    "allgemein": ["Jedes sichtbare Objekt bekommt genau eine Box – nichts auslassen, nichts doppelt.",
                  "Box eng um den Inhalt ziehen (wenige Pixel Rand), nicht um das ganze Feld.",
                  "CMR: die vorgedruckten Unterschriften/Stempel in Feld 22 und 23 nicht labeln."],
    "unterschrift": "nur die handschriftliche Unterschrift, eng um die Tinte",
    "stempel": "der ganze Stempelabdruck, eng um den Abdruck",
    "tour_nummer": "die Tournummer vollständig (Tour/Datum/Werk), eng",
    "cmr_count": "„CMR i/n“ vollständig, eng",
}


# ------------------------------------------------------------------ loading

def _key(file_name: str) -> str:
    return Path(file_name.replace("\\", "/")).name


def boxes_from_coco(coco: dict, prefix: str | None = None) -> dict[str, list]:
    """{image base name: [[cls, x1, y1, x2, y2] px]}; prefix filters a merged COCO
    ("425_21.09.2026/...") down to one export."""
    names = {c["id"]: c["name"] for c in coco["categories"]}
    imgs = {i["id"]: i for i in coco["images"]
            if prefix is None or i["file_name"].replace("\\", "/").startswith(prefix + "/")}
    out: dict[str, list] = {_key(i["file_name"]): [] for i in imgs.values()}
    for a in coco["annotations"]:
        img = imgs.get(a["image_id"])
        if img is None:
            continue
        x, y, w, h = a["bbox"]
        out[_key(img["file_name"])].append([names.get(a["category_id"], "?"), x, y, x + w, y + h])
    return out


def boxes_from_editor(path: Path) -> dict[str, list]:
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', path.read_text(encoding="utf-8"), re.S)
    data = json.loads(m.group(1).replace("<\\/", "</"))
    return {_key(p["file_name"]): [list(o) for o in p["orig"]] for p in data["pages"]}


def find_old(export_dir: Path, current: Path, relabel_dir: Path, old: str | None) -> tuple[dict, str]:
    if old:
        p = resolve(old)
        coco = load_coco(p)
        pre = export_dir.name if any("/" in i["file_name"] and i["file_name"].split("/")[0] == export_dir.name
                                     for i in coco["images"]) else None
        return boxes_from_coco(coco, pre), str(p)
    backups = sorted((p for p in export_dir.glob("*.json") if p.resolve() != current.resolve()
                      and "annotation" in p.name.lower()), key=lambda p: p.stat().st_mtime)
    if backups:
        return boxes_from_coco(load_coco(backups[-1])), str(backups[-1])
    ed = relabel_dir / export_dir.name / "editor.html"
    if ed.is_file():
        return boxes_from_editor(ed), f"{ed} (Stand vor dem Bearbeiten)"
    raise SystemExit(f"keine alten Labels gefunden: OLD=<Datei> angeben, Sicherung in {export_dir} ablegen "
                     f"oder vorher `make relabel` ausführen")


# ------------------------------------------------------------------ comparison

def pair(old: list, new: list) -> tuple[list, list, list]:
    """Greedy per class by IoU. Returns (pairs [(o, n, iou)], removed [o], added [n])."""
    pairs, used = [], set()
    cand = sorted(((iou(o[1:], n[1:]), i, j) for i, o in enumerate(old) for j, n in enumerate(new)
                   if o[0] == n[0]), reverse=True)
    used_o = set()
    for v, i, j in cand:
        if v <= 0 or i in used_o or j in used:
            continue
        used_o.add(i)
        used.add(j)
        pairs.append((old[i], new[j], v))
    removed = [o for i, o in enumerate(old) if i not in used_o]
    added = [n for j, n in enumerate(new) if j not in used]
    return pairs, removed, added


def _cv(vals):
    return statistics.pstdev(vals) / statistics.mean(vals) if len(vals) > 1 and statistics.mean(vals) else None


def class_stats(pages: list[dict], classes: list[str]) -> dict:
    st = {}
    for c in classes:
        o = [(b[3] - b[1]) / p["w"] for p in pages for b in p["old"] if b[0] == c]
        n = [(b[3] - b[1]) / p["w"] for p in pages for b in p["new"] if b[0] == c]
        oh = [(b[4] - b[2]) / p["h"] for p in pages for b in p["old"] if b[0] == c]
        nh = [(b[4] - b[2]) / p["h"] for p in pages for b in p["new"] if b[0] == c]
        prs = [x for p in pages for x in p["pairs"] if x[0][0] == c]
        ratio = [((n_[3] - n_[1]) * (n_[4] - n_[2])) / max(1e-9, (o_[3] - o_[1]) * (o_[4] - o_[2])) for o_, n_, _ in prs]
        st[c] = {"old": len(o), "new": len(n),
                 "added": sum(1 for p in pages for b in p["added"] if b[0] == c),
                 "removed": sum(1 for p in pages for b in p["removed"] if b[0] == c),
                 "adjusted": sum(1 for x in prs if x[2] < KEEP_IOU),
                 "area_ratio": statistics.median(ratio) if ratio else None,
                 "w_old": statistics.median(o) if o else None, "w_new": statistics.median(n) if n else None,
                 "h_old": statistics.median(oh) if oh else None, "h_new": statistics.median(nh) if nh else None,
                 "cv_old": _cv([a * b for a, b in zip(o, oh)]), "cv_new": _cv([a * b for a, b in zip(n, nh)])}
    return st


# ------------------------------------------------------------------ drawing

def _jpeg(im: Image.Image, q=80) -> str:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def draw(im: Image.Image, boxes: list, colors: dict, width: int, crop=None) -> str:
    im = im.copy()
    W, H = im.size
    d = ImageDraw.Draw(im)
    lw = max(2, int(max(W, H) / 400))
    for c, x1, y1, x2, y2 in boxes:
        d.rectangle([x1, y1, x2, y2], outline=colors.get(c, "#000"), width=lw)
    if crop:
        im = im.crop(crop)
    s = width / im.width
    return _jpeg(im.resize((width, max(1, int(im.height * s)))))


def crop_around(o, n, W, H):
    x1, y1 = min(o[1], n[1]), min(o[2], n[2])
    x2, y2 = max(o[3], n[3]), max(o[4], n[4])
    px, py = max(40, (x2 - x1) * 0.35), max(40, (y2 - y1) * 0.6)
    return (int(max(0, x1 - px)), int(max(0, y1 - py)), int(min(W, x2 + px)), int(min(H, y2 + py)))


# ------------------------------------------------------------------ main

def run_label_compare(cfg, export: str, old: str | None, log, max_pages: int = 40) -> int:
    from ..data.exports import COCO_NAMES

    root = resolve(cfg["paths"].get("exports") or "labels")
    export_dir = root / export
    if not export_dir.is_dir():
        cands = [d.name for d in root.iterdir() if d.is_dir() and d.name.startswith(export)] if root.is_dir() else []
        if len(cands) != 1:
            log(f"FEHLER: Export '{export}' nicht in {root} gefunden" + (f" (meintest du {cands}?)" if cands else ""))
            return 2
        export_dir = root / cands[0]
    current = next((export_dir / n for n in COCO_NAMES if (export_dir / n).is_file()), None)
    if current is None:
        log(f"FEHLER: keine COCO-Datei in {export_dir}")
        return 2
    new_coco = load_coco(current)
    new = boxes_from_coco(new_coco)
    old_boxes, old_src = find_old(export_dir, current, artifacts(cfg, "relabel"), old)
    classes = [c for c in cfg["classes"]]
    colors = {c: CLASS_COLORS[i % len(CLASS_COLORS)] for i, c in enumerate(classes)}
    guide = {**DEFAULT_GUIDE, **(cfg.get("label_guide") or {})}

    pages = []
    for img in new_coco["images"]:
        k = _key(img["file_name"])
        o = [b for b in old_boxes.get(k, []) if b[0] in classes]
        n = [b for b in new.get(k, []) if b[0] in classes]
        prs, removed, added = pair(o, n)
        changed = len(removed) + len(added) + sum(1 for x in prs if x[2] < KEEP_IOU)
        pages.append({"key": k, "file_name": img["file_name"], "w": img["width"], "h": img["height"],
                      "old": o, "new": n, "pairs": prs, "removed": removed, "added": added, "changed": changed,
                      "path": find_image(img["file_name"], export_dir / "images", export_dir)})
    missing_old = sum(1 for p in pages if p["key"] not in old_boxes)
    st = class_stats(pages, classes)
    out = artifacts(cfg, "label_compare")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{export_dir.name}.html"
    path.write_text(render(export_dir.name, old_src, str(current), pages, st, classes, colors, guide, max_pages),
                    encoding="utf-8")
    n_changed = sum(1 for p in pages if p["changed"])
    log(f"[compare-labels] {export_dir.name}: {len(pages)} Seiten, {n_changed} geändert; alt aus {old_src}"
        + (f"; {missing_old} Seiten ohne alte Labels" if missing_old else ""))
    for c, s in st.items():
        if s["old"] or s["new"]:
            log(f"[compare-labels]   {c}: {s['old']} -> {s['new']} Boxen, +{s['added']} / -{s['removed']}, "
                f"{s['adjusted']} angepasst" + (f", Fläche x{s['area_ratio']:.2f}" if s["area_ratio"] else ""))
    log(f"[compare-labels] {path}")
    return 0


def _pct(v):
    return "–" if v is None else f"{v * 100:.1f} %"


def render(export, old_src, new_src, pages, st, classes, colors, guide, max_pages) -> str:
    esc = html.escape
    changed = sorted([p for p in pages if p["changed"]], key=lambda p: -p["changed"])
    n_add = sum(s["added"] for s in st.values())
    n_rem = sum(s["removed"] for s in st.values())
    n_adj = sum(s["adjusted"] for s in st.values())
    legend = " ".join(f"<span class='chip'><span class='sw' style='background:{colors[c]}'></span>{esc(c)}</span>"
                      for c in classes)
    L = [f"<header><h1>Labels vorher / nachher – Tour {esc(export)}</h1>"
         f"<p class='sub'>{len(pages)} Seiten · {len(changed)} geändert · {n_adj} Boxen angepasst · "
         f"{n_add} ergänzt · {n_rem} entfernt</p><p class='legend'>{legend}</p></header>"]

    # guide
    L.append("<section><h2>So sollen die Labels aussehen</h2><ul class='guide'>")
    for g in guide.get("allgemein", []):
        L.append(f"<li>{esc(g)}</li>")
    for c in classes:
        if guide.get(c):
            L.append(f"<li><span class='sw' style='background:{colors[c]}'></span><b>{esc(c)}</b>: {esc(guide[c])}</li>")
    L.append("</ul></section>")

    # numbers
    L.append("<section><h2>Was sich geändert hat</h2><div class='tablewrap'><table><thead><tr><th>Klasse</th>"
             "<th>Boxen vorher → nachher</th><th>ergänzt</th><th>entfernt</th><th>angepasst</th>"
             "<th>Fläche nachher / vorher</th><th>Größe (Median, Breite × Höhe der Seite)</th>"
             "<th>Streuung der Boxgröße</th></tr></thead><tbody>")
    for c in classes:
        s = st[c]
        if not (s["old"] or s["new"]):
            continue
        size = (f"{_pct(s['w_old'])} × {_pct(s['h_old'])} → {_pct(s['w_new'])} × {_pct(s['h_new'])}")
        cv = ("–" if s["cv_old"] is None or s["cv_new"] is None else f"{s['cv_old']:.2f} → {s['cv_new']:.2f}")
        ar = "–" if s["area_ratio"] is None else f"{s['area_ratio']:.2f}×"
        L.append(f"<tr><td><span class='sw' style='background:{colors[c]}'></span>{esc(c)}</td>"
                 f"<td>{s['old']} → {s['new']}</td><td>{s['added']}</td><td>{s['removed']}</td><td>{s['adjusted']}</td>"
                 f"<td>{ar}</td>"
                 f"<td>{size}</td><td>{cv}</td></tr>")
    L.append("</tbody></table></div><p class='note'>„Streuung“ = Variationskoeffizient der Boxfläche: je kleiner, "
             "desto einheitlicher sind die Boxen gezogen. Fläche &lt; 1 = die neuen Boxen sind enger.</p></section>")

    # close-ups per class
    L.append("<section><h2>Nahaufnahmen: vorher und nachher</h2>")
    for c in classes:
        cands = sorted(((x[2], p, x) for p in pages if p["path"] for x in p["pairs"]
                        if x[0][0] == c and x[2] < KEEP_IOU), key=lambda t: t[0])[:3]
        extra = [(None, p, (None, b, None)) for p in pages if p["path"] for b in p["added"] if b[0] == c][:max(0, 3 - len(cands))]
        items = cands + extra
        if not items:
            continue
        L.append(f"<h3><span class='sw' style='background:{colors[c]}'></span>{esc(c)}</h3><div class='pairs'>")
        for v, p, (o, n, _) in items:
            im = to_rgb(Image.open(p["path"]))
            W, H = im.size
            box = crop_around(o or n, n, W, H)
            left = draw(im, [o] if o else [], colors, 360, box)
            right = draw(im, [n], colors, 360, box)
            note = "fehlte vorher" if o is None else f"Überlappung alt/neu {v:.0%}"
            L.append(f"<figure class='pair'><div class='two'><div><span class='tag'>vorher</span><img src='{left}' alt=''>"
                     f"</div><div><span class='tag new'>nachher</span><img src='{right}' alt=''></div></div>"
                     f"<figcaption>{esc(p['key'])} · {esc(note)}</figcaption></figure>")
        L.append("</div>")
    L.append("</section>")

    # pages
    L.append(f"<section><h2>Seiten mit Änderungen ({len(changed)})</h2>"
             + (f"<p class='note'>Die {max_pages} Seiten mit den meisten Änderungen.</p>" if len(changed) > max_pages else ""))
    for p in changed[:max_pages]:
        if not p["path"]:
            continue
        im = to_rgb(Image.open(p["path"]))
        bits = []
        if p["added"]:
            bits.append(f"{len(p['added'])} ergänzt ({', '.join(sorted({b[0] for b in p['added']}))})")
        if p["removed"]:
            bits.append(f"{len(p['removed'])} entfernt ({', '.join(sorted({b[0] for b in p['removed']}))})")
        adj = [x for x in p["pairs"] if x[2] < KEEP_IOU]
        if adj:
            bits.append(f"{len(adj)} angepasst ({', '.join(sorted({x[0][0] for x in adj}))})")
        L.append(f"<figure class='page'><figcaption><b>{esc(p['key'])}</b> · {esc(' · '.join(bits))}</figcaption>"
                 f"<div class='two'><div><span class='tag'>vorher</span><img loading='lazy' src='{draw(im, p['old'], colors, 520)}' alt=''></div>"
                 f"<div><span class='tag new'>nachher</span><img loading='lazy' src='{draw(im, p['new'], colors, 520)}' alt=''></div></div></figure>")
    L.append("</section>")
    L.append(f"<footer>Alt: {esc(old_src)}<br>Neu: {esc(new_src)}</footer>")
    return PAGE.replace("__TITLE__", esc(f"Labels vorher/nachher {export}")).replace("__BODY__", "".join(L))


PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e3e3e8;--card:#f7f7f9;--new:#2b8a3e}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececf1;--muted:#a1a1aa;--line:#2e2e33;--card:#1f1f23;--new:#51cf66}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header,section,footer{max-width:1120px;margin:0 auto;padding:0 16px}
header{padding-top:28px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin:20px 0 8px;display:flex;align-items:center;gap:6px}
.sub{color:var(--muted);margin:0}.legend{display:flex;gap:10px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:13px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;flex:none}
.guide li{margin:4px 0;display:list-item}.note{color:var(--muted);font-size:13px}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;font-size:14px;min-width:640px}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;white-space:nowrap}th{color:var(--muted);font-weight:600}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px}.two>div{position:relative}
img{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:6px;background:#fff}
.tag{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.65);color:#fff;font-size:12px;padding:1px 8px;border-radius:999px}
.tag.new{background:var(--new)}
.pairs{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
figure{margin:0}figure.pair,figure.page{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
figure.page{margin:14px 0}figcaption{font-size:13px;color:var(--muted);margin:6px 2px}
footer{color:var(--muted);font-size:12px;padding:28px 16px 40px;overflow-wrap:anywhere}
@media (max-width:640px){.two{grid-template-columns:1fr}}
</style></head><body>__BODY__</body></html>"""
