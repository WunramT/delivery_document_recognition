"""`make label-scans RUN=<name>`: a processed tour (`make process`) as a label export.

    artifacts/label_scans/<Tour>_<Datum>/  _annotations.coco.json  images/  page_types.csv
                                           editor.html / editor_pl.html (+ .zip)

Same layout as the exports in labels/, so new scans (and new classes such as ta_nummer,
ls_nummer, seitenzahl) can be labeled in the offline editor. Pre-labels: the model's
detections at the working threshold (dashed in the editor) and the doc types - from the
review decision (entscheidung.json) where it exists. Afterwards copy the folder to
labels/<Tour>_<Datum>/, save the corrected COCO there and run make inspect split train ...
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from ..config import artifacts
from ..eval.i18n import guide, languages
from ..eval.label_editor import editor_data, write_editor
from .organize import KNOWN_TYPES

COCO_NAME = "_annotations.coco.json"


def export_name(tour: str | None, run: str) -> str:
    """'503/01.09.2026/4000' -> '503_01.09.2026' (the folder name labels/ expects)."""
    parts = (tour or "").split("/")
    return f"{parts[0]}_{parts[1]}" if len(parts) >= 2 and parts[0] and parts[1] else run


def build_export(R: dict, decision: dict | None, classes: list[str], src: Path, out: Path) -> tuple[dict, dict]:
    """Write images/, page_types.csv and the COCO file; returns (coco, editor meta)."""
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    dpages = (decision or {}).get("pages") or {}
    thr = R["thresholds"]["accept"]
    cat = {c: i + 1 for i, c in enumerate(classes)}
    coco = {"info": {"description": f"docval label-scans {R['name']}", "date_created": R["created"]},
            "images": [], "annotations": [],
            "categories": [{"id": i, "name": c, "supercategory": "none"} for c, i in cat.items()]}
    meta, rows, aid = {}, [], 1
    for p in R["pages"]:
        fn = f"images/{Path(p['image']).name}"
        shutil.copy2(src / p["image"], out / fn)
        coco["images"].append({"id": p["n"], "file_name": fn, "width": p["w"], "height": p["h"]})
        doc_type = (dpages.get(str(p["n"])) or {}).get("doc_type") or p["doc_type"]
        doc_type = doc_type if doc_type in KNOWN_TYPES else ""
        changes = []
        for d in p["dets"]:
            if d["cls"] not in cat or d["score"] < thr.get(d["cls"], 0.5):
                continue
            x1, y1, x2, y2 = d["box"][0] * p["w"], d["box"][1] * p["h"], d["box"][2] * p["w"], d["box"][3] * p["h"]
            coco["annotations"].append({
                "id": aid, "image_id": p["n"], "category_id": cat[d["cls"]],
                "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                "area": round((x2 - x1) * (y2 - y1), 1), "iscrowd": 0, "segmentation": [],
                "attributes": {"quelle": "modell", "score": d["score"]}})
            changes.append({"action": "hinzugefügt", "cls": d["cls"], "score": d["score"]})
            aid += 1
        src_pdf, _, src_page = p["source"].partition("#")
        rows.append([fn, doc_type, src_pdf, src_page or "1"])
        meta[p["n"]] = {"split": "-", "doc_type": doc_type, "changes": changes, "orig": []}
    (out / COCO_NAME).write_text(json.dumps(coco, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out / "page_types.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["file_name", "doc_type", "source_pdf", "source_page"])
        w.writerows(rows)
    return coco, meta


def run_label_scans(cfg, run: str, log) -> int:
    base = artifacts(cfg, "process", run)
    if not (base / "ergebnis.json").is_file():
        log(f"FEHLER: {base / 'ergebnis.json'} fehlt - zuerst `make process`")
        return 2
    R = json.loads((base / "ergebnis.json").read_text(encoding="utf-8"))
    dec_path = base / "entscheidung.json"
    decision = json.loads(dec_path.read_text(encoding="utf-8")) if dec_path.is_file() else None
    name = export_name(R.get("tour"), run)
    out = artifacts(cfg, "label_scans", name)
    coco, meta = build_export(R, decision, cfg["classes"], base, out)
    data = editor_data(name, coco, COCO_NAME, meta, cfg["classes"], cfg["doc_types"], out / "page_types.csv")
    editors = [write_editor(out, data, lang, guide(cfg, lang)) for lang in languages(cfg)]
    shutil.make_archive(str(out), "zip", root_dir=out)
    log(f"[label-scans] {len(R['pages'])} Seiten, {len(coco['annotations'])} Modell-Vorschläge, Dokumenttypen "
        f"{'aus der Prüfung' if decision else 'vom Modell'} -> {out}")
    for e in editors:
        log(f"[label-scans] Editor: {e}")
    log(f"[label-scans] Weiter: Ordner nach labels/{name}/ kopieren, dort im Editor labeln, „COCO speichern“ "
        f"als labels/{name}/{COCO_NAME} (und ggf. page_types.csv), dann make inspect split train export eval")
    return 0
