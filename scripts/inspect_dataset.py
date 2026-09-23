#!/usr/bin/env python3
"""Step 0: analyze the COCO dataset before building anything.

Writes (never touches the input data):
  artifacts/inspect/inspect.json      machine-readable findings
  artifacts/inspect/inspect.md        human-readable summary (German)
  artifacts/inspect/tour_crops/*.png  padded crops of tour_nummer boxes
  labels/doc_types.csv                template, if doc type GT is missing
  labels/tour_numbers.csv             template, if tour number text is missing
  labels/tour_review.html             review page for tour number crops

Exit code 0 even with validation findings; 2 if the input cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docval.config import load_config  # noqa: E402
from docval.data import dataset_info as di  # noqa: E402
from docval.data.coco import find_image, load_coco, validate_coco  # noqa: E402
from docval.data.labels import (  # noqa: E402
    DOC_TYPES_HEADER, TOUR_NUMBERS_HEADER, read_label_csv, write_template,
)

try:
    from PIL import Image
except ImportError:  # image-dependent checks are skipped
    Image = None


def resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="default: $DOCVAL_CONFIG or config.yaml")
    ap.add_argument("--coco", help="override paths.coco")
    ap.add_argument("--images", help="override paths.images")
    ap.add_argument("--out", help="output dir (default <artifacts>/inspect)")
    ap.add_argument("--labels", help="labels dir (default paths.labels)")
    ap.add_argument("--no-hash", action="store_true", help="skip near-duplicate image hashing")
    ap.add_argument("--no-templates", action="store_true", help="do not write label CSVs / review page")
    return ap.parse_args()


# --------------------------------------------------------------------------- stats

def out_of_image_summary(val, data: dict) -> dict:
    cats = {c["id"]: c["name"] for c in data["categories"]}
    ann_cat = {a.get("id"): cats.get(a.get("category_id")) for a in data["annotations"]}
    issues = [i for i in val.issues if i.kind == "bbox_out_of_image"]
    sides: dict[str, int] = {}
    by_class: dict[str, int] = {}
    amounts = []
    for i in issues:
        for side, v in (i.detail or {}).items():
            sides[side] = sides.get(side, 0) + 1
            amounts.append(v)
        c = ann_cat.get(i.ann_id) or "?"
        by_class[c] = by_class.get(c, 0) + 1
    pc = di.percentiles(amounts, (50, 100))
    return {"n": len(issues), "sides": sides, "by_class": by_class,
            "overshoot_p50": round(pc.get("p50", 0), 1), "overshoot_max": round(pc.get("p100", 0), 1)}


def by_doc_type(data: dict, doc_of: dict[str, str], classes: list[str]) -> dict:
    """Per doc type: pages, pages with >=1 box per class, box centers per class."""
    cats = {c["id"]: c["name"] for c in data["categories"]}
    imgs = {i["id"]: i for i in data["images"]}
    out: dict[str, dict] = {}
    for img in data["images"]:
        t = doc_of.get(img["file_name"], "?")
        out.setdefault(t, {"pages": 0, "pages_with": {c: 0 for c in classes},
                           "cx": {c: [] for c in classes}, "cy": {c: [] for c in classes},
                           "pages_without_any": 0})
        out[t]["pages"] += 1
    seen: dict = {}
    for a in data["annotations"]:
        img = imgs.get(a.get("image_id"))
        name = cats.get(a.get("category_id"))
        if img is None or name not in classes or not img.get("width"):
            continue
        t = doc_of.get(img["file_name"], "?")
        key = (img["id"], name)
        if key not in seen:
            seen[key] = True
            out[t]["pages_with"][name] += 1
        x, y, w, h = a["bbox"]
        out[t]["cx"][name].append((x + w / 2) / img["width"])
        out[t]["cy"][name].append((y + h / 2) / img["height"])
    with_ann = {a.get("image_id") for a in data["annotations"]}
    for img in data["images"]:
        if img["id"] not in with_ann:
            out[doc_of.get(img["file_name"], "?")]["pages_without_any"] += 1
    for t, d in out.items():
        d["center_x"] = {c: di.percentiles(v, (2, 50, 98)) for c, v in d.pop("cx").items()}
        d["center_y"] = {c: di.percentiles(v, (2, 50, 98)) for c, v in d.pop("cy").items()}
    return out


def box_stats(data: dict) -> dict:
    imgs = {i["id"]: i for i in data["images"]}
    cats = {c["id"]: c["name"] for c in data["categories"]}
    per_class: dict[str, dict] = {}
    per_image_count: dict[str, dict] = {}
    for a in data["annotations"]:
        name = cats.get(a.get("category_id"), f"<unknown {a.get('category_id')}>")
        s = per_class.setdefault(name, {"n": 0, "images": set(), "w": [], "h": [], "area": [],
                                        "min_side_px": [], "cx": [], "cy": []})
        s["n"] += 1
        s["images"].add(a.get("image_id"))
        per_image_count.setdefault(name, {}).setdefault(a.get("image_id"), 0)
        per_image_count[name][a.get("image_id")] += 1
        img = imgs.get(a.get("image_id"))
        bbox = a.get("bbox")
        if not img or not img.get("width") or not img.get("height") or not isinstance(bbox, list) or len(bbox) != 4:
            continue
        W, H = img["width"], img["height"]
        x, y, w, h = bbox
        s["w"].append(w / W)
        s["h"].append(h / H)
        s["area"].append((w * h) / (W * H))
        s["min_side_px"].append(min(w, h))
        s["cx"].append((x + w / 2) / W)
        s["cy"].append((y + h / 2) / H)
    out = {}
    for name, s in per_class.items():
        hist: dict[str, int] = {}
        for c in per_image_count[name].values():
            k = str(c) if c < 3 else "3+"
            hist[k] = hist.get(k, 0) + 1
        out[name] = {
            "annotations": s["n"],
            "images": len(s["images"]),
            "per_image_hist": hist,
            "w_rel": di.percentiles(s["w"]),
            "h_rel": di.percentiles(s["h"]),
            "area_rel": di.percentiles(s["area"]),
            "min_side_px": di.percentiles(s["min_side_px"]),
            "center_x": di.percentiles(s["cx"], (2, 50, 98)),
            "center_y": di.percentiles(s["cy"], (2, 50, 98)),
        }
    return out


def image_stats(data: dict, image_dir: Path | None, want_hash: bool,
                coco_dir: Path | None = None) -> dict:
    res: dict[str, int] = {}
    orient = {"hochformat": 0, "querformat": 0}
    exts: dict[str, int] = {}
    for img in data["images"]:
        W, H = img.get("width"), img.get("height")
        res[f"{W}x{H}"] = res.get(f"{W}x{H}", 0) + 1
        if W and H:
            orient["hochformat" if H >= W else "querformat"] += 1
        ext = Path(img["file_name"]).suffix.lower()
        exts[ext] = exts.get(ext, 0) + 1
    out = {"resolutions": sorted(res.items(), key=lambda kv: -kv[1])[:15],
           "n_distinct_resolutions": len(res), "orientation": orient, "extensions": exts,
           "size_mismatch": [], "exif_rotated": [], "unreadable": [], "hashes": {},
           "mode": {}}
    if Image is None or (image_dir is None and coco_dir is None):
        out["note"] = "Pillow nicht installiert oder kein Bildordner - Dateiprüfung übersprungen"
        return out
    for img in data["images"]:
        p = find_image(img["file_name"], image_dir, coco_dir)
        if p is None:
            continue
        try:
            with Image.open(p) as im:
                out["mode"][im.mode] = out["mode"].get(im.mode, 0) + 1
                if (im.width, im.height) != (img.get("width"), img.get("height")):
                    out["size_mismatch"].append((img["file_name"], [im.width, im.height],
                                                 [img.get("width"), img.get("height")]))
                try:
                    orientation = im.getexif().get(0x0112, 1)
                except Exception:
                    orientation = 1
                if orientation not in (1, None):
                    out["exif_rotated"].append((img["file_name"], orientation))
                if want_hash:
                    im.draft("L", (256, 256))
                    out["hashes"][img["file_name"]] = di.dhash(im)
        except Exception as e:  # corrupt files
            out["unreadable"].append((img["file_name"], str(e)[:120]))
    return out


# --------------------------------------------------------------------------- crops + review page

def tour_crops(data: dict, image_dir: Path | None, crop_dir: Path, tour_class: str, pad: float,
               coco_dir: Path | None = None) -> list[dict]:
    if Image is None:
        return []
    crop_dir.mkdir(parents=True, exist_ok=True)
    cat_ids = {c["id"] for c in data["categories"] if c.get("name") == tour_class}
    imgs = {i["id"]: i for i in data["images"]}
    crops = []
    by_image: dict = {}
    for a in data["annotations"]:
        if a.get("category_id") in cat_ids and a.get("image_id") in imgs:
            by_image.setdefault(a["image_id"], []).append(a)
    for iid, anns in by_image.items():
        img = imgs[iid]
        p = find_image(img["file_name"], image_dir, coco_dir)
        if p is None:
            continue
        try:
            im = Image.open(p)
            # boxes refer to the stored pixel grid; do NOT apply EXIF rotation here
            im.load()
        except Exception:
            continue
        for a in anns:
            x, y, w, h = a["bbox"]
            px, py = w * pad, h * pad
            box = (max(0, int(x - px)), max(0, int(y - py)),
                   min(im.width, int(x + w + px + 0.999)), min(im.height, int(y + h + py + 0.999)))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            name = f"{iid}_{a['id']}.png"
            im.crop(box).save(crop_dir / name)
            crops.append({"file_name": img["file_name"], "crop": name, "ann_id": a["id"]})
        im.close()
    return crops


REVIEW_TEMPLATE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>Tournummer-Review</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}
header{position:sticky;top:0;background:#fafafa;padding:8px 0;border-bottom:1px solid #ddd;z-index:1}
.row{display:flex;gap:16px;align-items:center;padding:8px;border-bottom:1px solid #eee}
.row.done{background:#eef8ee}
.crops{display:flex;gap:8px;flex-wrap:wrap;min-width:320px}
.crops img{max-height:90px;max-width:480px;border:1px solid #ccc;background:#fff}
.fn{font-size:12px;color:#666;width:260px;word-break:break-all}
input{font-size:22px;font-family:monospace;width:220px;padding:4px}
.none{color:#a00;font-size:13px}
button{font-size:14px;padding:6px 12px}
</style></head><body>
<header>
<b>Tournummer-Review</b> &middot; <span id="progress"></span> &middot;
<label><input type="checkbox" id="onlyEmpty" style="width:auto"> nur leere</label>
<button id="dl">tour_numbers.csv herunterladen</button>
<small>Enter = nächstes Feld. Eingaben werden lokal im Browser zwischengespeichert.
Unleserlich: <code>?</code> eintragen. Heruntergeladene Datei nach <code>labels/tour_numbers.csv</code> kopieren.</small>
</header>
<div id="list"></div>
<script>
const ROWS = __ROWS__;
const KEY = "docval-tour-review";
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const list = document.getElementById("list");
function val(r){ return (r.file_name in saved) ? saved[r.file_name] : r.value; }
function persist(){ try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {} }
function progress(){
  const n = ROWS.filter(r => (val(r)||"").trim()).length;
  document.getElementById("progress").textContent = n + " / " + ROWS.length + " ausgefüllt";
}
ROWS.forEach((r, i) => {
  const d = document.createElement("div"); d.className = "row"; d.dataset.i = i;
  const fn = document.createElement("div"); fn.className = "fn"; fn.textContent = r.file_name;
  const c = document.createElement("div"); c.className = "crops";
  if (!r.crops.length) { const s = document.createElement("span"); s.className = "none";
    s.textContent = "keine tour_nummer-Box annotiert"; c.appendChild(s); }
  r.crops.forEach(src => { const im = document.createElement("img"); im.loading = "lazy";
    im.src = src; c.appendChild(im); });
  const inp = document.createElement("input"); inp.value = val(r) || ""; inp.dataset.i = i;
  inp.addEventListener("input", () => { saved[r.file_name] = inp.value; persist(); progress();
    d.classList.toggle("done", !!inp.value.trim()); });
  inp.addEventListener("keydown", e => { if (e.key === "Enter") {
    const all = [...document.querySelectorAll(".row:not([hidden]) input")];
    const k = all.indexOf(inp); if (all[k+1]) all[k+1].focus(); } });
  d.classList.toggle("done", !!(val(r)||"").trim());
  d.append(fn, c, inp); list.appendChild(d);
});
document.getElementById("onlyEmpty").addEventListener("change", e => {
  document.querySelectorAll(".row").forEach(d => {
    const r = ROWS[d.dataset.i]; d.hidden = e.target.checked && !!(val(r)||"").trim(); });
});
function csvCell(s){ s = s == null ? "" : String(s); return /[",\\n]/.test(s) ? '"' + s.replace(/"/g,'""') + '"' : s; }
document.getElementById("dl").addEventListener("click", () => {
  const lines = ["file_name,tour_number"].concat(ROWS.map(r => csvCell(r.file_name) + "," + csvCell((val(r)||"").trim())));
  const blob = new Blob([lines.join("\\n") + "\\n"], {type: "text/csv"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "tour_numbers.csv"; a.click();
});
progress();
</script></body></html>
"""


def write_review_html(path: Path, file_names: list[str], crops: list[dict], crop_rel: str,
                      existing: dict[str, str]) -> None:
    by_fn: dict[str, list[str]] = {}
    for c in crops:
        by_fn.setdefault(c["file_name"], []).append(f"{crop_rel}/{c['crop']}")
    # images with a box first, so the reviewer starts with useful rows
    ordered = sorted(file_names, key=lambda fn: (fn not in by_fn, fn))
    rows = [{"file_name": fn, "crops": by_fn.get(fn, []), "value": existing.get(fn, "")} for fn in ordered]
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    path.write_text(REVIEW_TEMPLATE.replace("__ROWS__", payload), encoding="utf-8")


# --------------------------------------------------------------------------- report

def fmt_pct(d: dict, keys=("p0", "p5", "p50", "p95", "p100"), digits=3) -> str:
    return " / ".join(f"{d[k]:.{digits}f}" for k in keys if k in d) if d else "-"


def to_markdown(r: dict) -> str:
    L = []
    s = r["summary"]
    L.append("# Datensatz-Inspektion (Schritt 0)\n")
    L.append(f"- COCO: `{r['inputs']['coco']}`\n- Bilder: `{r['inputs']['images']}`\n"
             f"- Erstellt: {r['inputs']['created']}\n")
    L.append("## Überblick\n")
    L.append(f"| Kennzahl | Wert |\n|---|---|\n| Bilder | {s['n_images']} |\n| Annotationen | {s['n_annotations']} |\n"
             f"| Kategorien | {', '.join(s['categories'])} |\n"
             f"| Kategorien ohne Annotation | {', '.join(s['categories_without_annotations']) or '-'} |\n"
             f"| Bilder ohne Annotation | {s['images_without_annotations']} |\n")
    L.append("## Annotationen pro Klasse\n")
    L.append("Relative Größen als Anteil an Bildbreite/-höhe, Perzentile p0 / p5 / p50 / p95 / p100.\n")
    L.append("| Klasse | Annot. | Bilder | pro Bild (0 fehlt) | Breite rel. | Höhe rel. | kürzeste Seite px |\n|---|---|---|---|---|---|---|")
    for name, b in r["boxes"].items():
        hist = ", ".join(f"{k}×: {v}" for k, v in sorted(b["per_image_hist"].items()))
        L.append(f"| {name} | {b['annotations']} | {b['images']} | {hist} | {fmt_pct(b['w_rel'])} | "
                 f"{fmt_pct(b['h_rel'])} | {fmt_pct(b['min_side_px'], digits=0)} |")
    L.append("\nLage der Box-Zentren (p2 / p50 / p98, 0 = links/oben):\n")
    L.append("| Klasse | x | y |\n|---|---|---|")
    for name, b in r["boxes"].items():
        L.append(f"| {name} | {fmt_pct(b['center_x'], ('p2','p50','p98'), 2)} | {fmt_pct(b['center_y'], ('p2','p50','p98'), 2)} |")
    im = r["images"]
    L.append("\n## Bildauflösungen\n")
    L.append(f"- {im['n_distinct_resolutions']} verschiedene Auflösungen; häufigste: "
             + ", ".join(f"{k} ({v})" for k, v in im["resolutions"][:8]))
    L.append(f"- Ausrichtung: {im['orientation']}; Dateitypen: {im['extensions']}; Farbmodi: {im.get('mode', {})}")
    if im.get("note"):
        L.append(f"- Hinweis: {im['note']}")
    L.append(f"- Größe im JSON ≠ Datei: {len(im['size_mismatch'])}; EXIF-Rotation gesetzt: {len(im['exif_rotated'])}; "
             f"nicht lesbar: {len(im['unreadable'])}")
    for fn, real, js in im["size_mismatch"][:5]:
        L.append(f"  - `{fn}`: Datei {real[0]}x{real[1]}, JSON {js[0]}x{js[1]}")
    for fn, o in im["exif_rotated"][:5]:
        L.append(f"  - `{fn}`: EXIF Orientation={o} (Boxen evtl. im gedrehten Koordinatensystem!)")

    L.append("\n## Validierung\n")
    v = r["validation"]
    if not v["counts"]:
        L.append("Keine Fehler gefunden.")
    else:
        L.append("| Fehlerart | Anzahl |\n|---|---|")
        for k, n in sorted(v["counts"].items()):
            L.append(f"| {k} | {n} |")
        oo = v.get("out_of_image")
        if oo and oo["n"]:
            L.append(f"\n`bbox_out_of_image`: {oo['n']} Boxen, Seiten {oo['sides']}, Überstand px "
                     f"(p50 / max) {oo['overshoot_p50']} / {oo['overshoot_max']}, Klassen {oo['by_class']}")
        L.append("\nBeispiele (max. 5 je Fehlerart):\n")
        shown: dict[str, int] = {}
        for i in v["examples"]:
            if shown.get(i["kind"], 0) >= 5:
                continue
            shown[i["kind"]] = shown.get(i["kind"], 0) + 1
            L.append(f"- `{i['kind']}`: {i['message']} (image_id={i['image_id']}, ann_id={i['ann_id']}, {i['file_name']})")

    d = r["doc_type"]
    L.append("\n## Herkunft des Dokumenttyps\n")
    L.append(f"**Ergebnis: `{d['source']['kind']}`** {d['source'].get('key', '') or ''}\n")
    L.append("1. Bild-Attribute im COCO-JSON: "
             + ("keine zusätzlichen Felder" if not d["image_fields"] else
                ", ".join(f"`{k}` ({s['count']}×, {s['distinct']} Werte)" for k, s in list(d["image_fields"].items())[:15])))
    for c in d["attribute_candidates"][:5]:
        L.append(f"   - Kandidat `{c['key']}`: Abdeckung {c['coverage']:.0%}, Werte {c['top'][:6]}")
    if d["doc_type_categories"]:
        L.append(f"   - Kategorien, die wie Dokumenttypen aussehen: {d['doc_type_categories']}")
    f = d["filename"]
    L.append(f"2. Dateinamen: {f['matched']} von {d['n_images']} ({f['coverage']:.0%}) eindeutig zuordenbar "
             f"{f['by_type']}, mehrdeutig: {f['ambiguous']}")
    if f["unmatched_examples"]:
        L.append("   - Beispiele ohne Treffer: " + ", ".join(f"`{x}`" for x in f["unmatched_examples"][:6]))
    L.append("3. Ordnerstruktur: " + (str(d["folders"]) if d["folders"] else "alle Bilder in einem Ordner"))
    c = d.get("csv")
    if c is not None:
        i = c["info"]
        if not i["exists"]:
            L.append(f"4. Externe CSV `{i['path']}`: nicht vorhanden")
        else:
            L.append(f"4. Externe CSV `{i['path']}`: Spalten {i['columns']} (Trenner `{i['delimiter']}`), "
                     f"genutzt: Datei=`{i['file_col']}`, Typ=`{i['value_col']}`; {i['rows']} Zeilen, "
                     f"{i['empty_values']} ohne Wert")
            L.append(f"   - Zugeordnet: {c['matched']} von {d['n_images']} COCO-Bildern ({c['coverage']:.0%}); "
                     f"Zuordnung {c['match_stats']}")
            L.append(f"   - Verteilung: {c['value_distribution']}")
            if c["values_not_in_doc_types"]:
                L.append(f"   - **Werte nicht in `doc_types` der config.yaml:** {c['values_not_in_doc_types']}")
            if c["unmatched_coco_examples"]:
                L.append("   - COCO-Bilder ohne CSV-Zeile: " + ", ".join(f"`{x}`" for x in c["unmatched_coco_examples"][:6]))
            if c["unmatched_csv_examples"]:
                L.append("   - CSV-Zeilen ohne COCO-Bild: " + ", ".join(f"`{x}`" for x in c["unmatched_csv_examples"][:6]))

    pd = r.get("by_doc_type") or {}
    if pd:
        cls = list(next(iter(pd.values()))["pages_with"].keys())
        L.append("\n## Klassen je Dokumenttyp\n")
        L.append("Seiten mit ≥ 1 Box der Klasse (Anteil):\n")
        L.append("| Dokumenttyp | Seiten | " + " | ".join(cls) + " | ohne Annotation |")
        L.append("|---|---|" + "---|" * len(cls) + "---|")
        for t, d in sorted(pd.items()):
            cells = [f"{d['pages_with'][c]} ({d['pages_with'][c] / d['pages']:.0%})" for c in cls]
            L.append(f"| {t} | {d['pages']} | " + " | ".join(cells) + f" | {d['pages_without_any']} |")
        L.append("\nBox-Zentren je Dokumenttyp (x p2/p50/p98 ; y p2/p50/p98):\n")
        L.append("| Dokumenttyp | " + " | ".join(cls) + " |")
        L.append("|---|" + "---|" * len(cls))
        for t, d in sorted(pd.items()):
            cells = []
            for c in cls:
                cx, cy = d["center_x"][c], d["center_y"][c]
                cells.append(f"{fmt_pct(cx, ('p2','p50','p98'), 2)} ; {fmt_pct(cy, ('p2','p50','p98'), 2)}" if cx else "-")
            L.append(f"| {t} | " + " | ".join(cells) + " |")

    t = r["tour_text"]
    L.append("\n## Ground-Truth-Text der Tournummer\n")
    L.append(f"**Ergebnis: `{t['source']['kind']}`** {t['source'].get('key', '') or ''}\n")
    L.append(f"- `tour_nummer`-Boxen: {t['n_annotations']} auf {t['n_images_with_box']} Bildern, "
             f"Bilder mit >1 Box: {t['n_images_multiple_boxes']}")
    L.append("- Zusatzfelder an diesen Annotationen: "
             + (", ".join(f"`{k}` ({s['count']}×)" for k, s in t["annotation_fields"].items()) or "keine"))
    for c in t["text_candidates"][:3]:
        L.append(f"   - Kandidat `{c['key']}`: Abdeckung {c['coverage']:.0%}, Beispiele {c['examples']}")
    if t["text_shapes"]:
        L.append("- Formate (9 = Ziffer, A = Buchstabe): " + ", ".join(f"`{k}` ({n})" for k, n in t["text_shapes"][:8]))
    fc = t.get("format_check")
    if fc and fc["n"]:
        L.append(f"- Formatprüfung `{fc['regex']}`: {fc['n'] - fc['n_invalid']} von {fc['n']} gültig"
                 + (f"; ungültig z. B. {fc['invalid_examples']}" if fc["n_invalid"] else ""))

    g = r["grouping"]
    L.append("\n## Gruppierung zu Stapeln/Dokumenten\n")
    L.append(f"- Gruppen-Attribute im JSON: "
             + (", ".join(f"`{c['key']}` ({c['distinct']} Werte, {c['coverage']:.0%})" for c in g["attribute_candidates"]) or "keine"))
    L.append(f"- Roboflow-Exportnamen (`*_jpg.rf.<hash>`): {g['roboflow_files']}; "
             f"gleicher Ursprungsname mehrfach: {g['same_source_stem']['n_stems']} Namen / {g['same_source_stem']['n_images']} Bilder"
             + (" – typisch für Augmentierung, Leck-Gefahr beim Split!" if g['same_source_stem']['n_stems'] else ""))
    fp = g["filename_page_groups"]
    L.append(f"- Dateiname mit Seitenzahl-Suffix: {fp['n_with_page_suffix']} Bilder → {fp['n_groups']} Gruppen, "
             f"davon {fp['n_multi_page_groups']} mehrseitig; Gruppengrößen {fp['group_size_hist']}")
    for name, pages in fp["examples"][:5]:
        L.append(f"   - `{name}` Seiten {pages}")
    L.append(f"- Bilder mit `cmr_count`-Box: {g['images_with_cmr_count']}")
    cg = (r["doc_type"].get("csv") or {}).get("grouping") or {}
    if cg.get("group_col"):
        L.append(f"- Label-CSV: Gruppenspalte `{cg['group_col']}`, Seitenspalte `{cg['page_col']}` → "
                 f"**{cg['n_groups']} Gruppe(n)**, Größen {cg['group_sizes'][:20]}")
        if cg["n_groups"] < 5:
            L.append("  - **Warnung:** zu wenige Gruppen für einen gruppierten Split train/valid/test.")
        L.append(f"  - Typfolge je Gruppe in Seitenreihenfolge ({', '.join(f'{k}={v}' for k, v in cg['legend'].items())}):")
        for name, seq in list(cg["type_sequence"].items())[:5]:
            L.append(f"    - `{name}`: `{seq}`")
    nd = g.get("near_duplicates")
    if nd is not None:
        L.append(f"- Nahezu identische Bilder (dHash ≤ {r['config']['near_duplicate_hash_distance']}): {len(nd)} Paare")
        for a, b, dist in nd[:8]:
            L.append(f"   - `{a}` ≈ `{b}` (Abstand {dist})")

    L.append("\n## Erzeugte Dateien\n")
    for k, v in r["outputs"].items():
        L.append(f"- {k}: {v}")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- main

def main() -> int:
    # Windows consoles default to cp1252; the report contains umlauts and arrows
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    args = parse_args()
    cfg = load_config(args.config)
    icfg = cfg.get("inspect", {})
    coco_path = resolve(args.coco or cfg["paths"]["coco"])
    image_dir = resolve(args.images or cfg["paths"]["images"])
    out_dir = resolve(args.out) if args.out else resolve(cfg["paths"]["artifacts"]) / "inspect"
    labels_dir = resolve(args.labels or cfg["paths"]["labels"])
    classes = cfg["classes"]

    try:
        data = load_coco(coco_path)
    except Exception as e:
        print(f"FEHLER: COCO-Datei nicht lesbar ({coco_path}): {e}", file=sys.stderr)
        return 2
    if not image_dir.is_dir():
        print(f"WARNUNG: Bildordner fehlt: {image_dir} - dateibasierte Prüfungen entfallen", file=sys.stderr)
        image_dir_ok = None
    else:
        image_dir_ok = image_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    coco_dir = coco_path.parent
    val = validate_coco(data, image_dir_ok, icfg.get("bbox_tolerance_px", 1.0), classes, coco_dir)
    ann_imgs = {a.get("image_id") for a in data["annotations"]}
    no_ann = [i["file_name"] for i in data["images"] if i["id"] not in ann_imgs]
    want_hash = icfg.get("compute_image_hashes", True) and not args.no_hash
    imstats = image_stats(data, image_dir_ok, want_hash, coco_dir)
    hashes = imstats.pop("hashes")
    doc = di.analyze_doc_type_sources(data, cfg["doc_types"], icfg.get("name_keywords", {}), classes)
    dcfg = cfg.get("labels", {}).get("doc_type", {})
    doc_csv_path = resolve(dcfg["csv"]) if dcfg.get("csv") else None
    if doc_csv_path is not None:
        doc["csv"] = di.analyze_doc_type_csv(data, doc_csv_path, cfg["doc_types"],
                                             dcfg.get("csv_file_column"), dcfg.get("csv_value_column"))
        if doc["csv"].get("coverage", 0) >= 0.99 and doc["source"]["kind"] == "missing":
            doc["source"] = {"kind": "csv", "key": str(dcfg["csv"])}
        elif doc["csv"]["info"]["exists"] and doc["source"]["kind"] == "missing":
            doc["source"] = {"kind": "csv_partial", "key": str(dcfg["csv"])}
    tour = di.analyze_tour_text(data, "tour_nummer")
    fmt = cfg.get("labels", {}).get("tour_number", {}).get("format_regex")
    if fmt:
        texts = [v for vv in tour["known_text_by_image_id"].values() for v in vv.split(";")]
        bad = [v for v in texts if not re.fullmatch(fmt, v)]
        tour["format_check"] = {"regex": fmt, "n": len(texts), "n_invalid": len(bad), "invalid_examples": bad[:10]}
    doc_of = (doc.get("csv") or {}).get("matched_values") or {}
    per_doc = by_doc_type(data, doc_of, classes) if doc_of else {}
    used_cats = {a.get("category_id") for a in data["annotations"]}
    empty_cats = [c["name"] for c in data["categories"] if c["id"] not in used_cats]
    grouping = di.analyze_grouping(data, "cmr_count")
    if hashes:
        grouping["near_duplicates"] = di.near_duplicates(hashes, icfg.get("near_duplicate_hash_distance", 6))

    report = {
        "inputs": {"coco": str(coco_path), "images": str(image_dir),
                   "created": time.strftime("%Y-%m-%d %H:%M:%S")},
        "config": {"near_duplicate_hash_distance": icfg.get("near_duplicate_hash_distance", 6)},
        "summary": {"n_images": len(data["images"]), "n_annotations": len(data["annotations"]),
                    "categories": [f"{c['id']}:{c['name']}" for c in data["categories"]],
                    "images_without_annotations": len(no_ann),
                    "categories_without_annotations": empty_cats,
                    "images_without_annotations_examples": no_ann[:20]},
        "boxes": di_sorted(box_stats(data), classes),
        "images": imstats,
        "validation": {"counts": val.count_by_kind(),
                       "examples": [vars(i) for i in val.issues[:500]],
                       "out_of_image": out_of_image_summary(val, data)},
        "doc_type": doc,
        "by_doc_type": per_doc,
        "tour_text": tour,
        "grouping": grouping,
        "outputs": {},
    }

    file_names = [i["file_name"] for i in data["images"]]
    if not args.no_templates:
        if doc["source"]["kind"] == "missing" and not (doc_csv_path and doc_csv_path.is_file()):
            st = write_template(labels_dir / "doc_types.csv", DOC_TYPES_HEADER, file_names)
            report["outputs"]["labels/doc_types.csv"] = st
        existing_tour: dict[str, str] = {}
        if tour["source"]["kind"] == "missing":
            id2fn = {i["id"]: i["file_name"] for i in data["images"]}
            prefill = {id2fn[iid]: v for iid, v in tour["known_text_by_image_id"].items() if iid in id2fn}
            st = write_template(labels_dir / "tour_numbers.csv", TOUR_NUMBERS_HEADER, file_names, prefill)
            report["outputs"]["labels/tour_numbers.csv"] = st
            existing_tour = read_label_csv(labels_dir / "tour_numbers.csv", "tour_number")
        crop_dir = out_dir / "tour_crops"
        crops = tour_crops(data, image_dir_ok, crop_dir, "tour_nummer",
                           icfg.get("tour_crop_padding", 0.12), coco_dir)
        report["outputs"]["tour_crops"] = f"{len(crops)} Crops in {crop_dir}"
        if tour["source"]["kind"] == "missing":
            html_path = labels_dir / "tour_review.html"
            rel = Path(os.path.relpath(crop_dir, labels_dir)).as_posix()
            write_review_html(html_path, file_names, crops, rel, existing_tour)
            report["outputs"]["labels/tour_review.html"] = "erstellt"
    report["runtime_s"] = round(time.time() - t0, 2)

    (out_dir / "inspect.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                          encoding="utf-8")
    md = to_markdown(report)
    (out_dir / "inspect.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n→ {out_dir / 'inspect.md'}\n→ {out_dir / 'inspect.json'}")
    return 0


def di_sorted(boxes: dict, classes: list[str]) -> dict:
    order = {c: i for i, c in enumerate(classes)}
    return dict(sorted(boxes.items(), key=lambda kv: order.get(kv[0], len(order))))


if __name__ == "__main__":
    sys.exit(main())
