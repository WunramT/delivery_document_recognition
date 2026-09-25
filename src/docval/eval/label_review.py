"""Label review: where detector and annotation disagree, on all splits.

Writes artifacts/label_review/{label_review.html, label_review.csv, crops/}. Each
disagreement is sorted into a category that says what to look at:

- abweichende_box: GT and prediction overlap, but IoU < iou_match -> the box is drawn
  differently (e.g. "CMR 3/9" vs. only "3/9"); counts as FN + FP in the metrics.
- label_fehlt:     confident prediction without any GT box of the class -> annotation missing?
- andere_klasse:   prediction lies on a GT box of another class -> class mixed up?
- nicht_erkannt:   GT box without any overlapping prediction.
- doppeltes_label: two GT boxes of the same class on top of each other.

Plus for cmr_count: OCR of every GT box and the CMR stack check per export (tour):
which "CMR i/n" were read, which are missing, and CMR pages without a cmr_count label.
Train pages are included on purpose: a confident "label_fehlt" on a train page means the
model finds it despite the label saying otherwise - a strong sign for a missing label.
"""

from __future__ import annotations

import csv
import html
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import artifacts
from ..data.dataset import load_pages
from ..data.labels import short_name
from ..detect.onnx_detector import OnnxDetector, iou
from ..models import setup_cache
from ..zones.synthetic import to_rgb
from .metrics import match

CATEGORIES = {
    "abweichende_box": "Box anders gezogen (überlappt, IoU unter der Schwelle)",
    "label_fehlt": "Label fehlt? (sichere Vorhersage ohne GT-Box)",
    "andere_klasse": "Andere Klasse? (Vorhersage liegt auf GT-Box einer anderen Klasse)",
    "nicht_erkannt": "Nicht erkannt (GT-Box ohne überlappende Vorhersage)",
    "doppeltes_label": "Doppeltes Label (zwei GT-Boxen derselben Klasse übereinander)",
}
TOUCH_IOU = 0.05      # "overlaps at all"
OTHER_CLASS_IOU = 0.3
DUPLICATE_IOU = 0.7


def classify_page(gts: dict[str, list], preds: list[dict], thr: dict[str, float], iou_match: float) -> list[dict]:
    """gts: {cls: [box]} (normalized xyxy), preds: [{cls, box, score}] (all scores).
    Returns findings [{category, cls, gt, pred, score, iou, best_score}]."""
    out = []
    dedup: dict[str, list] = {}
    for c, g in gts.items():
        keep = []
        for b in g:
            twin = next((k for k in keep if iou(k, b) >= DUPLICATE_IOU), None)
            if twin is not None:  # reported once, then ignored (it would also count as FN)
                out.append({"category": "doppeltes_label", "cls": c, "gt": b, "pred": None,
                            "score": None, "iou": round(iou(twin, b), 3)})
            else:
                keep.append(b)
        dedup[c] = keep
    classes = set(gts) | {d["cls"] for d in preds}
    for c in sorted(classes):
        g = dedup.get(c, [])
        all_c = [d for d in preds if d["cls"] == c]
        pr = sorted([d for d in all_c if d["score"] >= thr.get(c, 0.5)], key=lambda d: -d["score"])
        tp, idx = match(g, pr, iou_match)
        used_gt = {k for k in idx if k >= 0}
        free_gt = [k for k in range(len(g)) if k not in used_gt]
        free_pr = [d for d, t in zip(pr, tp) if not t]
        # pair unmatched GT and unmatched prediction that overlap -> box drawn differently
        paired_pr = set()
        for k in free_gt:
            best, best_v = None, TOUCH_IOU
            for n, d in enumerate(free_pr):
                v = iou(d["box"], g[k])
                if n not in paired_pr and v >= best_v:
                    best, best_v = n, v
            if best is not None:
                paired_pr.add(best)
                d = free_pr[best]
                out.append({"category": "abweichende_box", "cls": c, "gt": g[k], "pred": d["box"],
                            "score": round(d["score"], 3), "iou": round(best_v, 3)})
            else:
                below = [d["score"] for d in all_c if iou(d["box"], g[k]) >= iou_match]
                out.append({"category": "nicht_erkannt", "cls": c, "gt": g[k], "pred": None, "score": None,
                            "iou": None, "best_score": round(max(below), 3) if below else None})
        for n, d in enumerate(free_pr):
            if n in paired_pr:
                continue
            if any(iou(d["box"], b) >= TOUCH_IOU for b in g):
                continue  # second prediction on an already matched box: model issue, not label
            other = [(oc, b) for oc, bs in gts.items() if oc != c for b in bs if iou(d["box"], b) >= OTHER_CLASS_IOU]
            if other:
                out.append({"category": "andere_klasse", "cls": c, "gt": other[0][1], "pred": d["box"],
                            "score": round(d["score"], 3), "iou": round(iou(d["box"], other[0][1]), 3),
                            "gt_cls": other[0][0]})
            else:
                out.append({"category": "label_fehlt", "cls": c, "gt": None, "pred": d["box"],
                            "score": round(d["score"], 3), "iou": None})
    return out


def draw_crop(path: Path, f: dict, out: Path) -> str | None:
    """Region around GT (green) and prediction (red), enlarged."""
    try:
        im = to_rgb(Image.open(path))
    except Exception:
        return None
    W, H = im.size
    boxes = [b for b in (f.get("gt"), f.get("pred")) if b]
    x1, y1 = min(b[0] for b in boxes) * W, min(b[1] for b in boxes) * H
    x2, y2 = max(b[2] for b in boxes) * W, max(b[3] for b in boxes) * H
    px, py = max(60, (x2 - x1) * 0.8), max(60, (y2 - y1) * 1.2)
    cx1, cy1 = max(0, int(x1 - px)), max(0, int(y1 - py))
    cx2, cy2 = min(W, int(x2 + px)), min(H, int(y2 + py))
    d = ImageDraw.Draw(im)
    if f.get("gt"):
        b = f["gt"]
        d.rectangle([b[0] * W, b[1] * H, b[2] * W, b[3] * H], outline=(0, 160, 0), width=4)
    if f.get("pred"):
        b = f["pred"]
        d.rectangle([b[0] * W, b[1] * H, b[2] * W, b[3] * H], outline=(220, 0, 0), width=3)
    im = im.crop((cx1, cy1, cx2, cy2))
    s = min(3.0, 520 / max(1, im.width), 360 / max(1, im.height))
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=85)
    return out.name


def box_sizes(pages, cls: str) -> dict:
    """Median normalized width/height of the GT boxes per export (style differences)."""
    by: dict[str, list] = {}
    for p in pages:
        e = p.file_name.split("/")[0] if "/" in p.file_name else "-"
        for b in p.boxes_of(cls):
            n = b.norm(p.width, p.height)
            by.setdefault(e, []).append((n[2] - n[0], n[3] - n[1]))
    med = lambda v: sorted(v)[len(v) // 2]  # noqa: E731
    return {e: {"n": len(v), "w": round(med([a for a, _ in v]), 4), "h": round(med([b for _, b in v]), 4)}
            for e, v in sorted(by.items())}


def thresholds(cfg, classes, log) -> tuple[dict, str]:
    res = artifacts(cfg, "report", "results.json")
    if res.is_file():
        thr = json.loads(res.read_text(encoding="utf-8")).get("detector", {}).get("thresholds")
        if thr:
            return {c: float(thr.get(c, 0.5)) for c in classes}, "aus der letzten Evaluation (results.json)"
    fixed = cfg["detector"]["score_threshold"]
    if fixed != "auto":
        return {c: float(fixed) for c in classes}, "fest aus config.yaml"
    fb = float(cfg["detector"].get("score_threshold_fallback", 0.5))
    log(f"[review] keine results.json - Schwelle {fb} für alle Klassen (erst `make eval` für kalibrierte)")
    return {c: fb for c in classes}, "Fallback (keine Evaluation vorhanden)"


def cmr_count_check(cfg, pages, prep, engine) -> dict:
    """OCR of every GT cmr_count box + stack check per export (tour) over all splits."""
    from ..ocr.onnx_ocr import pad_crop, pil_to_bgr
    from ..ocr.postprocess import parse_cmr_count, stack_complete
    from .run import ocr_det_rec_text

    pad = cfg["ocr"]["crop_padding"]
    rows, per_export = [], {}
    for p in pages:
        e = p.file_name.split("/")[0] if "/" in p.file_name else "-"
        ex = per_export.setdefault(e, {"cmr_pages": 0, "labeled": 0, "counts": [], "no_label": [],
                                       "on_other_type": [], "unreadable": []})
        boxes = p.boxes_of("cmr_count")
        if p.doc_type == "cmr":
            ex["cmr_pages"] += 1
            if not boxes:
                ex["no_label"].append(p.file_name)
        elif boxes:
            ex["on_other_type"].append(p.file_name)
        if not boxes:
            continue
        ex["labeled"] += 1
        orig = prep(p)[0]
        for b in boxes:
            crop = pil_to_bgr(pad_crop(orig, b.xyxy, pad))
            t_rec, s_rec = engine.recognize(crop)
            t_det, s_det = ocr_det_rec_text(engine, crop)
            parsed = parse_cmr_count(t_rec) or parse_cmr_count(t_det)
            rows.append({"file_name": p.file_name, "export": e, "doc_type": p.doc_type, "text_rec": t_rec,
                         "text_det_rec": t_det, "score": round(max(s_rec, s_det), 3),
                         "parsed": list(parsed) if parsed else None, "box": b.norm(p.width, p.height),
                         "path": str(p.path)})
            if parsed:
                ex["counts"].append((parsed, p.file_name))
            else:
                ex["unreadable"].append(p.file_name)
    for e, ex in per_export.items():
        counts = [c for c, _ in ex["counts"]]
        ex["stack"] = stack_complete(counts) if counts else None
        seen: dict = {}
        for (x, y), fn in ex["counts"]:
            seen.setdefault(f"{x}/{y}", []).append(fn)
        ex["duplicates"] = {k: v for k, v in seen.items() if len(v) > 1}
        ex["read"] = sorted(seen, key=lambda k: [int(v) for v in k.split("/")])
    n = len(rows)
    return {"rows": rows, "per_export": per_export, "n": n,
            "readable": sum(1 for r in rows if r["parsed"]),
            "readable_rec": sum(1 for r in rows if parse_cmr_count(r["text_rec"])),
            "readable_det_rec": sum(1 for r in rows if parse_cmr_count(r["text_det_rec"]))}


def run_label_review(cfg, log) -> int:
    from .run import PagePrep

    setup_cache(cfg)
    t0 = time.time()
    pages, _ = load_pages(cfg)
    det_dir = artifacts(cfg, "detector")
    if not (det_dir / "detector.onnx").is_file():
        log("FEHLER: kein ONNX-Modell - zuerst `make train export`")
        return 2
    split = {}
    sp = artifacts(cfg, "splits", "split.json")
    if sp.is_file():
        split = {p["file_name"]: p["split"] for p in json.loads(sp.read_text())["pages"]}
    want = (cfg.get("eval") or {}).get("split") or "all"
    pages = [p for p in pages if p.path is not None and (want == "all" or split.get(p.file_name) == want)]
    detector = OnnxDetector(det_dir, min_score=0.01)
    classes = detector.classes
    thr, thr_src = thresholds(cfg, classes, log)
    iou_m = cfg["detector"]["iou_match"]
    prep = PagePrep(cfg)
    rcfg = cfg.get("label_review") or {}
    log(f"[review] {len(pages)} Seiten (Split {want}), Schwellen {thr_src}: "
        + ", ".join(f"{c}={t:g}" for c, t in thr.items()))
    findings = []
    for p in pages:
        _, im = prep(p)   # masked like in training/eval; GT in masked fields removed
        preds = detector(im)
        gts = {c: [b.norm(p.width, p.height) for b in p.boxes_of(c)] for c in classes}
        for f in classify_page(gts, preds, thr, iou_m):
            f.update(file_name=p.file_name, split=split.get(p.file_name, "-"), doc_type=p.doc_type,
                     path=str(p.path))
            findings.append(f)
    cc = None
    if "cmr_count" in classes and (cfg["ocr"].get("read_cmr_count", True)):
        from .run import load_engines
        engine = next(iter(load_engines(cfg).values()))
        cc = cmr_count_check(cfg, pages, prep, engine)
    out = artifacts(cfg, "label_review")
    write_outputs(out, cfg, pages, findings, cc, thr, thr_src, want, rcfg.get("max_crops_per_group", 40))
    counts: dict = {}
    for f in findings:
        counts[(f["cls"], f["category"])] = counts.get((f["cls"], f["category"]), 0) + 1
    log("[review] " + ", ".join(f"{c}/{k}: {n}" for (c, k), n in sorted(counts.items())))
    if cc:
        log(f"[review] cmr_count: {cc['n']} Boxen, lesbar {cc['readable']} "
            f"(nur Rec {cc['readable_rec']}, Det+Rec {cc['readable_det_rec']}); CMR-Seiten ohne cmr_count-Label: "
            f"{sum(len(e['no_label']) for e in cc['per_export'].values())}")
    log(f"[review] {out / 'label_review.html'} | {out / 'label_review.csv'} ({time.time() - t0:.0f} s)")
    return 0


# ------------------------------------------------------------------ output

def _b(b):
    return "" if not b else ", ".join(f"{v:.3f}" for v in b)


def write_outputs(out: Path, cfg, pages, findings, cc, thr, thr_src, want, max_crops) -> None:
    out.mkdir(parents=True, exist_ok=True)
    crops = out / "crops"
    if crops.exists():
        for f in crops.iterdir():
            f.unlink()
    with open(out / "label_review.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["kategorie", "klasse", "seite", "split", "doc_type", "score", "iou", "gt_box", "pred_box",
                    "hinweis", "entscheidung"])
        for f in findings:
            hint = f"GT-Klasse {f['gt_cls']}" if f.get("gt_cls") else (
                f"bester Score an der Stelle {f['best_score']}" if f.get("best_score") is not None else "")
            w.writerow([f["category"], f["cls"], f["file_name"], f["split"], f["doc_type"], f.get("score") or "",
                        f.get("iou") or "", _b(f.get("gt")), _b(f.get("pred")), hint, ""])
        if cc:
            for r in cc["rows"]:
                if not r["parsed"]:
                    w.writerow(["cmr_count_unlesbar", "cmr_count", r["file_name"], split_of(r, findings), r["doc_type"],
                                r["score"], "", _b(r["box"]), "", f"OCR '{r['text_rec']}' / '{r['text_det_rec']}'", ""])
            for e, ex in cc["per_export"].items():
                for fn in ex["no_label"]:
                    w.writerow(["cmr_ohne_cmr_count", "cmr_count", fn, "", "cmr", "", "", "", "", e, ""])

    esc = html.escape
    L = [f"<h1>Label-Prüfung</h1><p>{len(pages)} Seiten (Split <code>{esc(want)}</code>, alle Splits = "
         "auch Trainingsseiten) · Detektor-Schwellen " + esc(thr_src) + ": "
         + ", ".join(f"{esc(c)} {t:g}" for c, t in thr.items())
         + ". Grün = Label (GT), Rot = Vorhersage. Entscheidungen in <code>label_review.csv</code> "
         "(Spalte <i>entscheidung</i>) notieren, korrigieren im Label-Tool, dann neu exportieren.</p>"]
    # summary
    classes = sorted({f["cls"] for f in findings})
    L.append("<h2>Übersicht</h2><table><tr><th>Kategorie</th>" + "".join(f"<th>{esc(c)}</th>" for c in classes)
             + "</tr>")
    for k, title in CATEGORIES.items():
        L.append(f"<tr><td>{esc(title)}</td>" + "".join(
            f"<td>{sum(1 for f in findings if f['cls'] == c and f['category'] == k) or ''}</td>" for c in classes)
            + "</tr>")
    L.append("</table>")
    L.append("<p>Faustregel: <b>abweichende Box</b> gehäuft = Label-Stil uneinheitlich (Konvention festlegen, "
             "z. B. „Box nur um die Zahl“ oder „inkl. Beschriftung“) · <b>Label fehlt</b> mit hohem Score, "
             "besonders auf <i>train</i> = sehr wahrscheinlich vergessenes Label · <b>nicht erkannt</b> = eher "
             "Modell (oder Box auf etwas anderem).</p>")

    if cc:
        L += cmr_section(cc, crops, esc)
    L.append("<h2>Boxgröße je Export (Median, Anteil der Seite)</h2><p>Große Unterschiede zwischen Exporten "
             "deuten auf unterschiedlich gezogene Boxen hin.</p><table><tr><th>Klasse</th><th>Export</th>"
             "<th>n</th><th>Breite</th><th>Höhe</th></tr>")
    for c in cfg["classes"]:
        for e, v in box_sizes(pages, c).items():
            L.append(f"<tr><td>{esc(c)}</td><td>{esc(e)}</td><td>{v['n']}</td><td>{v['w']:.3f}</td>"
                     f"<td>{v['h']:.3f}</td></tr>")
    L.append("</table>")

    order = {"label_fehlt": 0, "abweichende_box": 1, "andere_klasse": 2, "doppeltes_label": 3, "nicht_erkannt": 4}
    for c in classes:
        L.append(f"<h2>{esc(c)}</h2>")
        for k in sorted(CATEGORIES, key=order.get):
            items = [f for f in findings if f["cls"] == c and f["category"] == k]
            if not items:
                continue
            items.sort(key=lambda f: (-(f.get("score") or 0), f["file_name"]))
            L.append(f"<h3>{esc(CATEGORIES[k])} – {len(items)}</h3><div class='grid'>")
            for i, f in enumerate(items[:max_crops]):
                name = draw_crop(Path(f["path"]), f, crops / f"{c}_{k}_{i:03d}.jpg")
                meta = [f"Split {f['split']}", f"Typ {f['doc_type'] or '-'}"]
                if f.get("score") is not None:
                    meta.append(f"Score {f['score']:.2f}")
                if f.get("iou") is not None:
                    meta.append(f"IoU {f['iou']:.2f}")
                if f.get("gt_cls"):
                    meta.append(f"GT-Klasse {f['gt_cls']}")
                if f.get("best_score") is not None:
                    meta.append(f"bester Score {f['best_score']:.2f}")
                L.append(f"<figure>{f'<img src=crops/{name} loading=lazy>' if name else ''}<figcaption><b>"
                         f"{esc(short_name(f['file_name']))}</b><br>{esc(' · '.join(meta))}</figcaption></figure>")
            L.append("</div>")
            if len(items) > max_crops:
                L.append(f"<p>… {len(items) - max_crops} weitere in label_review.csv</p>")
    css = ("body{font-family:system-ui,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;color:#1d1d1f;"
           "background:#fff}table{border-collapse:collapse;margin:8px 0;font-size:14px}td,th{border:1px solid #ddd;"
           "padding:4px 8px;text-align:left;vertical-align:top}th{background:#f3f3f3}code{background:#f3f3f3;"
           "padding:0 3px}h2{border-bottom:2px solid #eee;margin-top:32px}.grid{display:grid;grid-template-columns:"
           "repeat(auto-fill,minmax(260px,1fr));gap:12px}figure{margin:0;border:1px solid #ddd;padding:6px}"
           "figure img{max-width:100%;display:block}figcaption{font-size:13px;margin-top:4px;overflow-wrap:anywhere}")
    (out / "label_review.html").write_text(
        f"<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width,initial-scale=1'><title>Label-Prüfung</title><style>{css}</style></head>"
        f"<body>{''.join(L)}</body></html>", encoding="utf-8")


def split_of(row, findings) -> str:
    return next((f["split"] for f in findings if f["file_name"] == row["file_name"]), "")


def cmr_section(cc, crops: Path, esc) -> list[str]:
    n = cc["n"] or 1
    L = ["<h2>cmr_count: Lesbarkeit und Stapel je Tour</h2>",
         f"<p>{cc['n']} GT-Boxen, lesbar (Format <code>i/n</code>) {cc['readable']} ({cc['readable'] / n:.0%}); "
         f"nur Recognition {cc['readable_rec']}, Det+Rec {cc['readable_det_rec']}. Alle Splits, gruppiert nach "
         "Export (= Tour): ein vollständiger Stapel hat jede Nummer 1…n genau einmal.</p>",
         "<table><tr><th>Export</th><th>CMR-Seiten</th><th>mit cmr_count</th><th>gelesen</th><th>Stapel</th>"
         "<th>doppelt</th><th>CMR ohne cmr_count-Label</th><th>cmr_count auf anderem Typ</th></tr>"]
    for e, ex in cc["per_export"].items():
        if not ex["cmr_pages"] and not ex["labeled"]:
            continue
        st = ex["stack"]
        L.append(f"<tr><td>{esc(e)}</td><td>{ex['cmr_pages']}</td><td>{ex['labeled']}</td>"
                 f"<td>{esc(', '.join(ex['read']) or '-')}</td>"
                 f"<td>{esc(st['reason']) if st else '-'}</td>"
                 f"<td>{esc('; '.join(f'{k}: ' + ', '.join(short_name(x) for x in v) for k, v in ex['duplicates'].items())) or '-'}</td>"
                 f"<td>{esc(', '.join(short_name(x) for x in ex['no_label'])) or '-'}</td>"
                 f"<td>{esc(', '.join(short_name(x) for x in ex['on_other_type'])) or '-'}</td></tr>")
    L.append("</table>")
    bad = [r for r in cc["rows"] if not r["parsed"]]
    if bad:
        L.append(f"<h3>Nicht lesbare cmr_count-Boxen – {len(bad)}</h3><p>Liegt die Box auf dem richtigen Text? "
                 "Ist sie zu eng (Ziffern abgeschnitten) oder enthält sie mehr als „CMR i/n“?</p><div class='grid'>")
        for i, r in enumerate(bad[:60]):
            name = draw_crop(Path(r["path"]), {"gt": r["box"]}, crops / f"cmr_unlesbar_{i:03d}.jpg")
            L.append(f"<figure>{f'<img src=crops/{name} loading=lazy>' if name else ''}<figcaption><b>"
                     f"{esc(short_name(r['file_name']))}</b> ({esc(r['doc_type'] or '-')})<br>Rec "
                     f"„{esc(r['text_rec'])}“ · Det+Rec „{esc(r['text_det_rec'])}“</figcaption></figure>")
        L.append("</div>")
    return L
