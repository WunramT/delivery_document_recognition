"""Pre-annotations for re-labeling: the existing labels combined with the detector's results.

For every export folder a copy in the same layout as the input is written to
artifacts/relabel/<export>/ (_annotations.coco.json with the original image ids and file
names, images, page_types.csv, tour_numbers.csv) plus <export>.zip - ready to import into
the label tool, correct page by page and export again into labels/.

What happens to a box (config `relabel`, categories as in the label review):
- label matches the model (IoU >= iou_match)    -> `matched`: keep the label (gt) or take the model box
- box drawn differently (overlap, IoU < 0.5)    -> `different_box`: model | gt | both
- confident prediction without label             -> `add_missing`: added
- prediction on a box of another class           -> `add_other_class`: usually a model error, off by default
- duplicate label                                -> `drop_duplicates`: removed
- label the model does not find / in the masked CMR fields 22+23 -> kept unchanged
Every change is listed in relabel_changes.csv and shown in relabel_overview.html.
"""

from __future__ import annotations

import csv
import html
import json
import shutil
import time
from pathlib import Path

from ..config import artifacts, resolve
from ..data.coco import load_coco
from ..data.dataset import load_pages
from ..data.labels import short_name
from ..detect.onnx_detector import OnnxDetector, iou
from ..models import setup_cache
from .label_review import classify_page, thresholds
from .metrics import match

DEFAULT_POLICY = {"matched": "gt", "different_box": "model", "add_missing": True, "add_other_class": False,
                  "drop_duplicates": True, "add_min_score": 0.3, "copy_images": True, "zip": True,
                  "mark": "none"}


def propose(gts: dict[str, list], preds: list[dict], thr: dict[str, float], iou_m: float,
            policy: dict) -> tuple[list[dict], list[dict]]:
    """gts {cls: [box]}, preds [{cls, box, score}] (normalized xyxy).
    Returns (boxes [{cls, box, source, score}], changes [{action, cls, old, new, score}])."""
    pol = {**DEFAULT_POLICY, **(policy or {})}
    findings = classify_page(gts, preds, thr, iou_m)
    boxes = {c: [{"cls": c, "box": list(b), "source": "label", "score": None} for b in g] for c, g in gts.items()}
    changes = []

    def find(c, b):
        return next((x for x in boxes.get(c, []) if x["source"] == "label" and x["box"] == list(b)), None)

    for f in findings:
        c, k = f["cls"], f["category"]
        if k == "doppeltes_label" and pol["drop_duplicates"]:
            x = find(c, f["gt"])
            if x:
                boxes[c].remove(x)
                changes.append({"action": "entfernt_doppelt", "cls": c, "old": f["gt"], "new": None, "score": None})
        elif k == "abweichende_box" and pol["different_box"] in ("model", "both"):
            new = {"cls": c, "box": list(f["pred"]), "source": "modell", "score": f["score"]}
            x = find(c, f["gt"])
            if pol["different_box"] == "model" and x:
                boxes[c][boxes[c].index(x)] = new
                changes.append({"action": "ersetzt", "cls": c, "old": f["gt"], "new": f["pred"], "score": f["score"]})
            else:
                boxes.setdefault(c, []).append(new)
                changes.append({"action": "hinzugefügt_alternative", "cls": c, "old": f["gt"], "new": f["pred"],
                                "score": f["score"]})
        elif k in ("label_fehlt", "andere_klasse"):
            if (k == "label_fehlt" and not pol["add_missing"]) or (k == "andere_klasse" and not pol["add_other_class"]):
                continue
            if pol["add_min_score"] is not None and f["score"] < float(pol["add_min_score"]):
                continue
            boxes.setdefault(c, []).append({"cls": c, "box": list(f["pred"]), "source": "modell", "score": f["score"]})
            changes.append({"action": "hinzugefügt" if k == "label_fehlt" else "hinzugefügt_andere_klasse",
                            "cls": c, "old": None, "new": f["pred"], "score": f["score"]})
    if pol["matched"] == "model":
        for c, g in gts.items():
            pr = sorted([d for d in preds if d["cls"] == c and d["score"] >= thr.get(c, 0.5)],
                        key=lambda d: -d["score"])
            tp, idx = match(g, pr, iou_m)
            for d, ok, k in zip(pr, tp, idx):
                x = find(c, g[k]) if ok else None
                if x and iou(x["box"], d["box"]) < 0.999:
                    boxes[c][boxes[c].index(x)] = {"cls": c, "box": list(d["box"]), "source": "modell",
                                                   "score": round(d["score"], 3)}
                    changes.append({"action": "angepasst", "cls": c, "old": g[k], "new": d["box"],
                                    "score": round(d["score"], 3)})
    return [b for bs in boxes.values() for b in bs], changes


def _exports_of(cfg) -> dict:
    """{rel file_name: (export name, export dir, orig file_name, orig id)} from the merged COCO."""
    coco_path = resolve(cfg["paths"]["coco"])
    data = load_coco(coco_path)
    out = {}
    for img in data["images"]:
        if "export" in img:
            out[img["file_name"]] = (img["export"], Path(img["export_dir"]), img["orig_file_name"], img["orig_id"])
        else:  # single export (no subfolders): the COCO file itself
            out[img["file_name"]] = (coco_path.parent.name, coco_path.parent, img["file_name"], img["id"])
    return out


def _coco_file(d: Path) -> Path:
    from ..data.exports import COCO_NAMES
    return next(d / n for n in COCO_NAMES if (d / n).is_file())


def run_relabel(cfg, log) -> int:
    from .run import PagePrep

    setup_cache(cfg)
    t0 = time.time()
    pol = {**DEFAULT_POLICY, **(cfg.get("relabel") or {})}
    pages, _ = load_pages(cfg)
    det_dir = artifacts(cfg, "detector")
    if not (det_dir / "detector.onnx").is_file():
        log("FEHLER: kein ONNX-Modell - zuerst `make train export`")
        return 2
    detector = OnnxDetector(det_dir, min_score=0.01)
    classes = detector.classes
    thr, thr_src = thresholds(cfg, classes, log)
    iou_m = cfg["detector"]["iou_match"]
    prep = PagePrep(cfg)
    origin = _exports_of(cfg)
    split = {}
    sp = artifacts(cfg, "splits", "split.json")
    if sp.is_file():
        split = {p["file_name"]: p["split"] for p in json.loads(sp.read_text())["pages"]}
    log(f"[relabel] {len(pages)} Seiten, Schwellen {thr_src}: " + ", ".join(f"{c}={t:g}" for c, t in thr.items()))

    per_export: dict[str, dict] = {}
    all_changes, overview = [], []
    for p in pages:
        if p.file_name not in origin:
            continue
        exp, exp_dir, orig_fn, orig_id = origin[p.file_name]
        E = per_export.setdefault(exp, {"dir": exp_dir, "pages": {}})
        W, H = p.width, p.height
        labels_all = [(b.cls, b.norm(W, H)) for b in p.boxes]
        if p.path is None:
            E["pages"][orig_id] = [{"cls": c, "box": b, "source": "label", "score": None} for c, b in labels_all]
            continue
        _, im = prep(p)  # p.boxes loses labels in the masked CMR fields 22/23 -> kept unchanged below
        masked_out = _removed_by_mask(labels_all, [(b.cls, b.norm(W, H)) for b in p.boxes])
        preds = detector(im)
        gts = {c: [b.norm(W, H) for b in p.boxes_of(c)] for c in classes}
        boxes, changes = propose(gts, preds, thr, iou_m, pol)
        boxes += [{"cls": c, "box": b, "source": "label", "score": None} for c, b in masked_out]
        E["pages"][orig_id] = boxes
        for ch in changes:
            ch.update(export=exp, file_name=orig_fn, page=p.file_name, split=split.get(p.file_name, "-"),
                      doc_type=p.doc_type)
            all_changes.append(ch)
        if changes:
            overview.append({"file_name": p.file_name, "path": str(p.path), "doc_type": p.doc_type,
                             "changes": changes,
                             "gt": [{"cls": c, "box": b} for c, bs in gts.items() for b in bs],
                             "pred": [{"cls": x["cls"], "box": x["box"], "score": x["score"] or 0.0}
                                      for x in boxes if x["source"] == "modell"]})

    out = artifacts(cfg, "relabel")
    for exp, E in per_export.items():
        write_export(E["dir"], E["pages"], out / exp, pol, log, cfg["classes"])
    write_changes(out, all_changes)
    write_overview(out, overview, thr, thr_src, pol)
    counts: dict = {}
    for ch in all_changes:
        counts[(ch["cls"], ch["action"])] = counts.get((ch["cls"], ch["action"]), 0) + 1
    log("[relabel] Änderungen: " + (", ".join(f"{c}/{a}: {n}" for (c, a), n in sorted(counts.items())) or "keine")
        + f" auf {len(overview)} Seiten")
    log(f"[relabel] {out}/<export>/ (+ .zip) | {out / 'relabel_overview.html'} | {out / 'relabel_changes.csv'} "
        f"({time.time() - t0:.0f} s)")
    return 0


def _removed_by_mask(labels_before: list, labels_after: list) -> list:
    """Labels the form mask removed from p.boxes (multiset difference)."""
    rest, removed = list(labels_after), []
    for x in labels_before:
        if x in rest:
            rest.remove(x)
        else:
            removed.append(x)
    return removed


def write_export(src_dir: Path, pages: dict, out: Path, pol: dict, log, classes: list[str]) -> None:
    """Same layout as the input export, annotations replaced for the detector classes
    (annotations of other categories are kept as they are)."""
    data = load_coco(_coco_file(src_dir))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cat_id = {c["name"]: c["id"] for c in data["categories"]}
    cats = list(data["categories"])

    def cid(name):
        if name not in cat_id:
            cat_id[name] = max([c["id"] for c in cats] + [0]) + 1
            cats.append({"id": cat_id[name], "name": name, "supercategory": cats[0].get("supercategory", "none")
                         if cats else "none"})
        return cat_id[name]

    name_of = {c["id"]: c["name"] for c in data["categories"]}
    anns = [dict(a) for a in data["annotations"] if name_of.get(a.get("category_id")) not in classes]
    aid = max([a.get("id", 0) for a in anns] + [0]) + 1
    size = {img["id"]: (img["width"], img["height"]) for img in data["images"]}
    for img in data["images"]:
        W, H = size[img["id"]]
        for b in pages.get(img["id"], []):
            name = b["cls"]
            if pol["mark"] == "category" and b["source"] == "modell":
                name = f"vorschlag_{name}"
            x1, y1, x2, y2 = b["box"][0] * W, b["box"][1] * H, b["box"][2] * W, b["box"][3] * H
            a = {"id": aid, "image_id": img["id"], "category_id": cid(name),
                 "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                 "area": round((x2 - x1) * (y2 - y1), 1), "iscrowd": 0, "segmentation": []}
            if b["source"] == "modell":
                a["attributes"] = {"quelle": "modell", "score": b["score"]}
            anns.append(a)
            aid += 1
    coco = {k: v for k, v in data.items() if k not in ("annotations", "categories")}
    coco["categories"], coco["annotations"] = cats, anns
    (out / _coco_file(src_dir).name).write_text(json.dumps(coco, indent=1, ensure_ascii=False), encoding="utf-8")
    for extra in ("page_types.csv", "tour_numbers.csv", "README.txt"):
        if (src_dir / extra).is_file():
            shutil.copy2(src_dir / extra, out / extra)
    n_img = 0
    if pol["copy_images"]:
        from ..data.coco import find_image
        for img in data["images"]:
            src = find_image(img["file_name"], src_dir / "images", src_dir)
            if src is None:
                continue
            dst = out / img["file_name"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)   # real copies: zip/upload from Windows, input stays untouched
            n_img += 1
    if pol["zip"]:
        shutil.make_archive(str(out), "zip", root_dir=out)
    log(f"[relabel] {out.name}: {len(data['images'])} Seiten, {len(anns)} Boxen, {n_img} Bilder kopiert")


def _b(b):
    return "" if not b else ", ".join(f"{v:.4f}" for v in b)


def write_changes(out: Path, changes: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "relabel_changes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["export", "file_name", "split", "doc_type", "aktion", "klasse", "score", "alte_box", "neue_box"])
        for c in sorted(changes, key=lambda c: (c["export"], c["file_name"])):
            w.writerow([c["export"], c["file_name"], c["split"], c["doc_type"], c["action"], c["cls"],
                        c["score"] if c["score"] is not None else "", _b(c["old"]), _b(c["new"])])


def write_overview(out: Path, items: list[dict], thr, thr_src, pol) -> None:
    from .report import draw_item

    img_dir = out / "overview"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    esc = html.escape
    L = [f"<h1>Vorlabels zum Überarbeiten</h1><p>{len(items)} Seiten mit Änderungen. Grün = bisheriges Label, "
         "Rot = vom Modell übernommen/ergänzt (mit Score). Schwellen " + esc(thr_src) + ": "
         + ", ".join(f"{esc(c)} {t:g}" for c, t in thr.items()) + ". Regeln: "
         + esc(", ".join(f"{k}={v}" for k, v in pol.items() if k not in ("copy_images", "zip"))) + ".</p>"]
    for i, it in enumerate(sorted(items, key=lambda x: x["file_name"])):
        name = draw_item(it, img_dir / f"seite_{i:03d}.jpg", max_side=1000)
        ch = "; ".join(f"{c['action']} {c['cls']}" + (f" ({c['score']:.2f})" if c["score"] is not None else "")
                       for c in it["changes"])
        L.append(f"<h3>{esc(short_name(it['file_name']))} ({esc(it['doc_type'] or '-')})</h3><p>{esc(ch)}</p>"
                 + (f"<img src='overview/{name}' loading='lazy'>" if name else ""))
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1d1d1f;"
           "background:#fff}img{max-width:100%;border:1px solid #ccc;margin:4px 0 16px}h3{margin-bottom:2px}")
    (out / "relabel_overview.html").write_text(
        f"<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>Vorlabels</title><style>{css}</style></head>"
        f"<body>{''.join(L)}</body></html>", encoding="utf-8")
