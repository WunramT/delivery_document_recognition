"""`make eval`: evaluate every stage on the test split with the ONNX models.

Writes artifacts/report/{results.json, report.md, report.html, gallery/} and
returns exit code 1 if an acceptance criterion is missed.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from pathlib import Path

import yaml
from PIL import Image

from ..config import artifacts
from ..data.dataset import load_pages
from ..detect.onnx_detector import OnnxDetector, iou
from ..doctype.rules import UNCERTAIN, combine, keyword_decision, keyword_scores
from ..models import ocr_model_dir, offline, setup_cache
from ..ocr.onnx_ocr import OcrEngine, Recognizer, crop_quad, pad_crop, pil_to_bgr
from ..ocr.postprocess import evaluate_text, parse_cmr_count, stack_complete
from ..zones import MISSING, NOT_REQUIRED, OK, WRONG_POSITION, check_page, derive_zones
from ..zones.synthetic import make_variants, to_rgb
from .metrics import average_precision, match, ratio

DET_THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
OCR_THRESHOLDS = [0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98, 0.99, 0.995]
# approximate CMR signature fields (bottom of the form), normalized page coords
CMR_FIELDS = {"22 Absender": [0.0, 0.72, 0.34, 1.0], "23 Frachtführer": [0.33, 0.72, 0.67, 1.0],
              "24 Empfänger": [0.66, 0.72, 1.0, 1.0]}


class Timer:
    def __init__(self):
        self.t: dict[str, list[float]] = {}

    def add(self, stage: str, seconds: float):
        self.t.setdefault(stage, []).append(seconds * 1000)

    def summary(self) -> dict:
        return {k: {"n": len(v), "mean_ms": statistics.mean(v), "median_ms": statistics.median(v),
                    "max_ms": max(v)} for k, v in self.t.items() if v}


def gt_dets(page) -> list[dict]:
    return [{"cls": b.cls, "box": b.norm(page.width, page.height), "score": 1.0} for b in page.boxes]


# ------------------------------------------------------------------ zones

def zones_for(cfg, train_pages, log) -> tuple[dict, dict]:
    z = cfg["zones"]
    samples: dict = {}
    for p in train_pages:
        if not p.doc_type:
            continue
        for b in p.boxes:
            samples.setdefault(p.doc_type, {}).setdefault(b.cls, []).append(b.norm(p.width, p.height))
    derived = derive_zones(samples, z["percentiles"][0], z["percentiles"][1], z["margin"], z["min_samples"])
    path = artifacts(cfg, "zones.yaml")
    header = ("# Soll-Zonen, abgeleitet aus dem Train-Split (normiert x1,y1,x2,y2; 0 = links/oben).\n"
              "# Manuell korrigieren: Werte ändern und 'locked: true' setzen, dann wird die Datei\n"
              "# nicht mehr überschrieben. Neu abgeleitete Werte stehen immer in zones.derived.yaml.\n")
    artifacts(cfg).mkdir(parents=True, exist_ok=True)
    (artifacts(cfg, "zones.derived.yaml")).write_text(header + yaml.safe_dump({"zones": derived}, sort_keys=True),
                                                     encoding="utf-8")
    source = "abgeleitet"
    if path.is_file():
        cur = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if cur.get("locked"):
            log(f"[zones] {path} ist gesperrt (locked: true) - manuelle Zonen werden verwendet")
            return cur["zones"], {"source": "manuell (locked)", "derived": derived, "path": str(path)}
    path.write_text(header + yaml.safe_dump({"locked": False, "zones": derived}, sort_keys=True), encoding="utf-8")
    return derived, {"source": source, "derived": derived, "path": str(path)}


def cmr_field_check(zones: dict) -> list[str]:
    notes = []
    cz = zones.get("cmr", {})
    for cls in ("unterschrift", "stempel"):
        if cls not in cz:
            notes.append(f"CMR: keine Zone für {cls} (zu wenige Trainingsbeispiele)")
            continue
        zb = cz[cls]["box"]
        covered = []
        for name, f in CMR_FIELDS.items():
            ix = max(0.0, min(zb[2], f[2]) - max(zb[0], f[0]))
            share = ix / (f[2] - f[0])
            if share >= 0.5:
                covered.append(name)
        if zb[1] < 0.6:
            notes.append(f"CMR {cls}: Zone reicht bis y={zb[1]:.2f} nach oben - größer als der Unterschriftenbereich")
        missing = [n for n in CMR_FIELDS if n not in covered]
        notes.append(f"CMR {cls}: Zone x {zb[0]:.2f}-{zb[2]:.2f}, y {zb[1]:.2f}-{zb[3]:.2f} deckt "
                     f"{', '.join(covered) or 'kein Feld'} ab" + (f"; nicht abgedeckt: {', '.join(missing)}" if missing else ""))
    return notes


# ------------------------------------------------------------------ OCR engines

def load_engines(cfg) -> dict:
    engines = {}
    for name, e in cfg["ocr"]["engines"].items():
        eng = OcrEngine(name, ocr_model_dir(cfg, e["det"]), ocr_model_dir(cfg, e["rec"]),
                        {"limit_side_len": cfg["ocr"].get("det_limit_side_len", 960)})
        eng.header_rec = Recognizer(ocr_model_dir(cfg, e.get("header_rec", e["rec"])))
        engines[name] = eng
    return engines


def ocr_det_rec_text(eng: OcrEngine, bgr, rec=None) -> tuple[str, float]:
    quads = eng.det(bgr)
    if not quads:
        return "", 0.0
    res = (rec or eng.rec)([crop_quad(bgr, q) for q in quads])
    text = " ".join(t for t, _ in res)
    score = min(s for _, s in res) if res else 0.0
    return text, score


def ocr_tour(eng: OcrEngine, crop: Image.Image, mode: str, ocfg: dict, regex: str) -> dict:
    bgr = pil_to_bgr(crop)
    if mode == "rec_only":
        raw, score = eng.recognize(bgr)
        r = evaluate_text(raw, score, regex, ocfg["min_score"])
    else:
        dets = eng.detect_recognize(bgr)
        # pick the detected line that fits the format best, then highest score
        cands = [evaluate_text(d["text"], d["score"], regex, ocfg["min_score"]) for d in dets]
        cands.sort(key=lambda c: (not c["valid_format"], -c["score"]))
        r = cands[0] if cands else evaluate_text("", 0.0, regex, ocfg["min_score"])
        r["n_lines"] = len(dets)
    return r


def paddle_reference(cfg, crops: list, log) -> dict:
    """PaddleOCR Python pipeline (rec only) on the same GT crops."""
    import numpy as np

    out = {}
    try:
        from paddleocr import TextRecognition
    except Exception as e:
        return {"error": f"paddleocr nicht verfügbar: {e}"}
    for name, e in cfg["ocr"]["engines"].items():
        model = e["rec"].split("/")[-1].removesuffix("_onnx")
        try:
            rec = TextRecognition(model_name=model)
            texts = []
            for c in crops:
                res = rec.predict(np.asarray(to_rgb(c))[:, :, ::-1].copy(), batch_size=1)
                r = res[0]
                texts.append((str(r["rec_text"]), float(r["rec_score"])))
            out[name] = {"model": model, "texts": texts}
        except Exception as ex:  # optional
            log(f"[eval] Paddle-Referenz {model} übersprungen: {ex}")
            out[name] = {"model": model, "error": str(ex)[:200]}
    return out


# ------------------------------------------------------------------ main

def run_eval(cfg, log) -> int:
    setup_cache(cfg)
    offline()
    t_start = time.time()
    pages, dinfo = load_pages(cfg)
    split_path = artifacts(cfg, "splits", "split.json")
    if not split_path.is_file():
        log("FEHLER: kein Split - zuerst `make split`")
        return 2
    manifest = json.loads(split_path.read_text())
    split = {p["file_name"]: p["split"] for p in manifest["pages"]}
    group = {p["file_name"]: p["group"] for p in manifest["pages"]}
    for p in pages:
        p.group = group.get(p.file_name)
    eval_split = cfg.get("eval", {}).get("split", "test")
    test = [p for p in pages if split.get(p.file_name) == eval_split and p.path is not None]
    train_pages = [p for p in pages if split.get(p.file_name) == "train"]
    det_dir = artifacts(cfg, "detector")
    if not (det_dir / "detector.onnx").is_file():
        log("FEHLER: kein ONNX-Modell - zuerst `make train export`")
        return 2
    detector = OnnxDetector(det_dir, min_score=0.01)
    classes = detector.classes
    thr = cfg["detector"]["score_threshold"]
    iou_thr = cfg["detector"]["iou_match"]
    timer = Timer()
    gallery: dict[str, list] = {"detektor": [], "dokumenttyp": [], "position": [], "tournummer": []}
    R: dict = {"meta": {"split": eval_split, "n_pages": len(test), "classes": classes,
                        "detector": json.loads((det_dir / "detector.json").read_text()),
                        "dataset": dinfo, "grouping": manifest["grouping"], "split_summary": manifest["summary"]}}
    parity_path = det_dir / "parity.json"
    R["parity"] = json.loads(parity_path.read_text()) if parity_path.is_file() else None
    log(f"[eval] {len(test)} Seiten im Split '{eval_split}'")

    # ---------------------------------------------------------- 1. detector
    preds: dict[str, list] = {}
    images: dict[str, Image.Image] = {}
    for p in test:
        im = Image.open(p.path)
        im.load()
        images[p.file_name] = im
        t0 = time.perf_counter()
        preds[p.file_name] = detector(im)
        timer.add("detektor", time.perf_counter() - t0)
    det_res = {"per_class": {}, "pr_table": {}}
    for c in classes:
        n_gt, scored = 0, []
        for p in test:
            g = [b.norm(p.width, p.height) for b in p.boxes_of(c)]
            pr = [d for d in preds[p.file_name] if d["cls"] == c]
            n_gt += len(g)
            tp, _ = match(g, pr, iou_thr)
            scored += [(d["score"], t) for d, t in zip(pr, tp)]
        rows = []
        for t in DET_THRESHOLDS:
            tp_n = sum(1 for s, ok in scored if s >= t and ok)
            fp_n = sum(1 for s, ok in scored if s >= t and not ok)
            rows.append({"threshold": t, "tp": tp_n, "fp": fp_n, "fn": n_gt - tp_n,
                         "precision": tp_n / (tp_n + fp_n) if tp_n + fp_n else None,
                         "recall": tp_n / n_gt if n_gt else None})
        at = next(r for r in rows if abs(r["threshold"] - thr) < 1e-9) if thr in DET_THRESHOLDS else None
        if at is None:
            tp_n = sum(1 for s, ok in scored if s >= thr and ok)
            fp_n = sum(1 for s, ok in scored if s >= thr and not ok)
            at = {"tp": tp_n, "fp": fp_n, "fn": n_gt - tp_n}
        det_res["per_class"][c] = {"n_gt": n_gt, "ap50": average_precision(scored, n_gt),
                                   "recall": ratio(at["tp"], n_gt),
                                   "precision": ratio(at["tp"], at["tp"] + at["fp"])}
        det_res["pr_table"][c] = rows
    # gallery: pages with most errors at the working threshold
    for p in test:
        errs, reasons = 0, []
        pr_all = [d for d in preds[p.file_name] if d["score"] >= thr]
        for c in classes:
            g = [b.norm(p.width, p.height) for b in p.boxes_of(c)]
            pr = [d for d in pr_all if d["cls"] == c]
            tp, _ = match(g, pr, iou_thr)
            fn, fp = len(g) - sum(tp), len(pr) - sum(tp)
            if fn:
                reasons.append(f"{fn}× {c} nicht gefunden")
            if fp:
                reasons.append(f"{fp}× {c} falsch-positiv")
            errs += fn + fp
        if errs:
            gallery["detektor"].append({"file_name": p.file_name, "path": str(p.path), "severity": errs,
                                        "title": f"{Path(p.file_name).name} ({p.doc_type})",
                                        "reason": "; ".join(reasons), "gt": gt_dets(p), "pred": pr_all})
    R["detector"] = det_res
    log("[eval] Detektor: " + ", ".join(
        f"{c} R={v['recall']['value'] if v['recall']['value'] is not None else '-'}" for c, v in det_res["per_class"].items()))

    # ---------------------------------------------------------- 2. doc type
    engines = load_engines(cfg)
    primary = next(iter(engines.values()))
    dcfg = cfg["doctype"]
    clf = None
    ccfg = dcfg["classifier"]
    if ccfg.get("enabled") and (artifacts(cfg, "doctype", "doctype.onnx")).is_file():
        from ..doctype.classifier import OnnxDocTypeClassifier
        clf = OnnxDocTypeClassifier(artifacts(cfg, "doctype"))
    dt_rows = []
    for p in test:
        im = images[p.file_name]
        head = im.crop((0, 0, im.width, max(1, int(im.height * dcfg["header_fraction"]))))
        t0 = time.perf_counter()
        text, _ = ocr_det_rec_text(primary, pil_to_bgr(head), primary.header_rec)
        timer.add("dokumenttyp_ocr", time.perf_counter() - t0)
        hits = keyword_scores(text, dcfg["keywords"], dcfg.get("fuzzy_min_len", 7))
        kw_type, kw_reason = keyword_decision(hits, dcfg.get("priority", []))
        clf_type = clf_conf = None
        if clf is not None:
            t0 = time.perf_counter()
            clf_type, clf_conf, _ = clf.predict(im)
            timer.add("dokumenttyp_klassifikator", time.perf_counter() - t0)
        dec = combine(kw_type, kw_reason, clf_type, clf_conf, ccfg["min_confidence"], ccfg["conflict_confidence"])
        dt_rows.append({"file_name": p.file_name, "gt": p.doc_type, "pred": dec["doc_type"], "source": dec["source"],
                        "reason": dec["reason"], "keyword": kw_type, "classifier": clf_type,
                        "classifier_conf": clf_conf, "header_text": text[:300]})
        if dec["doc_type"] != p.doc_type:
            gallery["dokumenttyp"].append({
                "file_name": p.file_name, "path": str(p.path),
                "severity": 2 if dec["doc_type"] != UNCERTAIN else 1,
                "title": f"{Path(p.file_name).name}: GT {p.doc_type} -> {dec['doc_type']}",
                "reason": f"{dec['reason']} | OCR-Kopf: '{text[:120]}'", "gt": [], "pred": [],
                "header_fraction": dcfg["header_fraction"]})
    types = sorted({r["gt"] for r in dt_rows if r["gt"]} | set(cfg["doc_types"]))
    decided = [r for r in dt_rows if r["pred"] != UNCERTAIN]
    conf = {g: {q: 0 for q in types + [UNCERTAIN]} for g in types}
    for r in dt_rows:
        if r["gt"] in conf:
            conf[r["gt"]][r["pred"] if r["pred"] in conf[r["gt"]] else UNCERTAIN] += 1
    per_type = {}
    for t in types:
        rows_t = [r for r in dt_rows if r["gt"] == t]
        dec_t = [r for r in rows_t if r["pred"] != UNCERTAIN]
        per_type[t] = {"n": len(rows_t), "accuracy": ratio(sum(r["pred"] == t for r in dec_t), len(dec_t)),
                       "uncertain": ratio(len(rows_t) - len(dec_t), len(rows_t))}
    R["doctype"] = {
        "accuracy": ratio(sum(r["pred"] == r["gt"] for r in decided), len(decided)),
        "uncertain": ratio(len(dt_rows) - len(decided), len(dt_rows)),
        "keyword_only": ratio(sum(r["keyword"] == r["gt"] for r in dt_rows), len(dt_rows)),
        "classifier_only": ratio(sum(r["classifier"] == r["gt"] for r in dt_rows), len(dt_rows)) if clf else None,
        "confusion": conf, "per_type": per_type, "rows": dt_rows, "classifier": bool(clf)}
    log(f"[eval] Dokumenttyp: Accuracy {R['doctype']['accuracy']['value']}, unsicher {R['doctype']['uncertain']['value']}")

    # ---------------------------------------------------------- 3. position check
    zones, zinfo = zones_for(cfg, train_pages, log)
    zcfg = cfg["zones"]
    rules = zcfg["rules"]
    unc = cfg["detector"]["score_uncertain"]

    def check(doc_type, dets):
        return check_page(doc_type, dets, zones, rules, zcfg["min_overlap"], thr, unc)

    real_rows = []
    pred_doc = {r["file_name"]: r["pred"] for r in dt_rows}
    for p in test:
        gt_status = check(p.doc_type, gt_dets(p))["status"]
        t0 = time.perf_counter()
        res = check(p.doc_type, preds[p.file_name])
        timer.add("positionspruefung", time.perf_counter() - t0)
        e2e = check(pred_doc.get(p.file_name), preds[p.file_name])
        real_rows.append({"file_name": p.file_name, "doc_type": p.doc_type, "gt_status": gt_status,
                          "status": res["status"], "reason": res["reason"], "e2e_status": e2e["status"]})
        if gt_status == OK and res["status"] in (MISSING, WRONG_POSITION):
            gallery["position"].append({"file_name": p.file_name, "path": str(p.path), "severity": 3,
                                        "title": f"Fehlalarm {Path(p.file_name).name} ({p.doc_type}): {res['status']}",
                                        "reason": res["reason"], "gt": gt_dets(p), "pred": preds[p.file_name],
                                        "zones": zones.get(p.doc_type, {})})
    ok_pages = [r for r in real_rows if r["gt_status"] == OK]
    false_alarms = [r for r in ok_pages if r["status"] in (MISSING, WRONG_POSITION)]
    uncertain_real = [r for r in ok_pages if r["status"] not in (OK, MISSING, WRONG_POSITION)]
    # synthetic negatives
    syn_dir = artifacts(cfg, "synthetic")
    syn_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(cfg["seed"])
    syn_rows = []
    by_fn = {p.file_name: p for p in test}
    for r in ok_pages:
        p = by_fn[r["file_name"]]
        rule = rules.get(p.doc_type) or {}
        for v in make_variants(p, images[p.file_name], zones, rule, rng, zcfg["synthetic"]["fill"],
                               zcfg["synthetic"]["kinds"]):
            out = syn_dir / f"{Path(p.file_name).stem}__{v['kind']}.png"
            v["image"].save(out)
            d = detector(v["image"])
            res = check(p.doc_type, d)
            caught = res["status"] in (MISSING, WRONG_POSITION)
            syn_rows.append({"file_name": p.file_name, "kind": v["kind"], "expected": v["expected"],
                             "status": res["status"], "caught": caught,
                             "correct_kind": res["status"] == v["expected"], "reason": res["reason"],
                             "image": str(out)})
            if not caught:
                gallery["position"].append({
                    "file_name": p.file_name, "path": str(out), "severity": 2 if res["status"] == OK else 1,
                    "title": f"Nicht erkannt: {Path(p.file_name).name} {v['kind']} -> {res['status']}",
                    "reason": f"Soll {v['expected']}: {res['reason']}",
                    "gt": [{"cls": b.cls, "box": b.norm(p.width, p.height), "score": 1.0} for b in v["boxes"]],
                    "pred": d, "zones": zones.get(p.doc_type, {})})
    by_kind = {}
    for s in syn_rows:
        k = by_kind.setdefault(s["kind"], [0, 0])
        k[0] += int(s["caught"])
        k[1] += 1
    R["position"] = {
        "zones": zones, "zones_info": zinfo, "cmr_fields": cmr_field_check(zones),
        "false_alarm": ratio(len(false_alarms), len(ok_pages)),
        "uncertain_real": ratio(len(uncertain_real), len(ok_pages)),
        "recall_negatives": ratio(sum(s["caught"] for s in syn_rows), len(syn_rows)),
        "correct_kind": ratio(sum(s["correct_kind"] for s in syn_rows), len(syn_rows)),
        "by_kind": {k: ratio(v[0], v[1]) for k, v in by_kind.items()},
        "gt_not_ok": [r for r in real_rows if r["gt_status"] not in (OK, NOT_REQUIRED)],
        "e2e_status_agree": ratio(sum(r["e2e_status"] == r["status"] for r in real_rows), len(real_rows)),
        "rows": real_rows, "synthetic": syn_rows}
    log(f"[eval] Position: Fehlalarm {R['position']['false_alarm']['value']}, "
        f"Recall Negative {R['position']['recall_negatives']['value']} ({len(syn_rows)} synthetisch)")

    # ---------------------------------------------------------- 4. tour number OCR
    ocfg = cfg["ocr"]
    regex = cfg["labels"]["tour_number"]["format_regex"]
    tour_rows = []
    gt_crops = []
    for p in test:
        gb = p.boxes_of("tour_nummer")
        if not gb:
            continue
        im = images[p.file_name]
        crop = pad_crop(im, gb[0].xyxy, ocfg["crop_padding"])
        gt_crops.append(crop)
        row = {"file_name": p.file_name, "doc_type": p.doc_type, "gt": p.tour_number, "gt_box": {}, "pred_box": {}}
        for name, eng in engines.items():
            for mode in ocfg["modes"]:
                t0 = time.perf_counter()
                row["gt_box"][f"{name}/{mode}"] = ocr_tour(eng, crop, mode, ocfg, regex)
                timer.add(f"tour_ocr_{name}_{mode}", time.perf_counter() - t0)
        cand = [d for d in preds[p.file_name] if d["cls"] == "tour_nummer" and d["score"] >= thr]
        if cand:
            d = max(cand, key=lambda x: x["score"])
            b = [d["box"][0] * p.width, d["box"][1] * p.height, d["box"][2] * p.width, d["box"][3] * p.height]
            pc = pad_crop(im, b, ocfg["crop_padding"])
            for name, eng in engines.items():
                row["pred_box"][f"{name}/rec_only"] = ocr_tour(eng, pc, "rec_only", ocfg, regex)
            row["pred_iou"] = iou(d["box"], gb[0].norm(p.width, p.height))
        tour_rows.append(row)
    variants = sorted({k for r in tour_rows for k in r["gt_box"]} | {f"pred:{k}" for r in tour_rows for k in r["pred_box"]})
    with_gt = [r for r in tour_rows if r["gt"]]
    ocr_res = {"n_boxes": len(tour_rows), "n_with_gt": len(with_gt), "variants": {}, "rows": tour_rows}
    for v in variants:
        src = "pred_box" if v.startswith("pred:") else "gt_box"
        key = v.removeprefix("pred:")
        vals = [(r, r[src].get(key)) for r in with_gt]
        n = len(with_gt)  # a missing pred box counts as not accepted
        acc = [(r, x) for r, x in vals if x and x["accepted"]]
        exact_acc = sum(1 for r, x in acc if x["text"] == r["gt"])
        exact_all = sum(1 for r, x in vals if x and x["text"] == r["gt"])
        fmt = sum(1 for r, x in vals if x and x["valid_format"])
        ocr_res["variants"][v] = {"acceptance": ratio(len(acc), n), "exact_accepted": ratio(exact_acc, len(acc)),
                                  "exact_all": ratio(exact_all, n), "valid_format": ratio(fmt, n)}
    prim = f"{next(iter(engines))}/rec_only"
    th_rows = []
    for t in OCR_THRESHOLDS:
        acc = [r for r in with_gt if r["gt_box"][prim]["valid_format"] and r["gt_box"][prim]["score"] >= t]
        th_rows.append({"threshold": t, "acceptance": ratio(len(acc), len(with_gt)),
                        "exact_accepted": ratio(sum(r["gt_box"][prim]["text"] == r["gt"] for r in acc), len(acc))})
    ocr_res["threshold_table"] = th_rows
    ocr_res["primary"] = prim
    if ocfg.get("paddle_reference") and gt_crops:
        ref = paddle_reference(cfg, gt_crops, log)
        agree = {}
        for name, rr in ref.items():
            if "texts" not in rr:
                agree[name] = {"error": rr.get("error")}
                continue
            k = sum(1 for (t, _), row in zip(rr["texts"], tour_rows)
                    if t.replace(" ", "") == row["gt_box"][f"{name}/rec_only"]["raw"].replace(" ", ""))
            agree[name] = {"model": rr["model"], "agreement": ratio(k, len(tour_rows))}
        ocr_res["paddle_reference"] = agree
    for r in tour_rows:
        x = r["gt_box"][prim]
        if r["gt"] and x["text"] != r["gt"]:
            sev = 3 if x["accepted"] else 1
        elif not x["accepted"]:
            sev = 1
        else:
            continue
        p = by_fn[r["file_name"]]
        gallery["tournummer"].append({
            "file_name": r["file_name"], "path": str(p.path), "severity": sev,
            "title": f"{Path(r['file_name']).name}: GT '{r['gt'] or '-'}' OCR '{x['text']}' "
                     f"({'akzeptiert' if x['accepted'] else 'abgelehnt'})",
            "reason": x["reason"], "crop_box": p.boxes_of("tour_nummer")[0].xyxy, "gt": [], "pred": []})
    # cmr_count (optional)
    if ocfg.get("read_cmr_count") and "cmr_count" in classes:
        cc = []
        for p in test:
            for b in p.boxes_of("cmr_count"):
                t, s = primary.recognize(pil_to_bgr(pad_crop(images[p.file_name], b.xyxy, ocfg["crop_padding"])))
                cc.append({"file_name": p.file_name, "group": p.group, "text": t, "parsed": parse_cmr_count(t)})
        groups = {}
        for c in cc:
            if c["parsed"]:
                groups.setdefault(c["group"], []).append(tuple(c["parsed"]))
        ocr_res["cmr_count"] = {"n": len(cc), "parsed": ratio(sum(1 for c in cc if c["parsed"]), len(cc)),
                                "stacks": {g: stack_complete(v) for g, v in groups.items()}, "rows": cc}
    else:
        ocr_res["cmr_count"] = None
    R["ocr"] = ocr_res
    log(f"[eval] Tournummer: {len(tour_rows)} Boxen, {len(with_gt)} mit GT")

    # ---------------------------------------------------------- acceptance
    A = cfg["acceptance"]
    crit = []

    def add(stage, metric, r, thrv, cmp=">="):
        v = r["value"] if r else None
        if v is None:
            ok = not A.get("fail_on_missing_gt", True)
            note = "keine Daten/GT"
        else:
            ok = v >= thrv if cmp == ">=" else v <= thrv
            note = ""
        crit.append({"stage": stage, "metric": metric, "value": v, "threshold": thrv, "cmp": cmp,
                     "passed": ok, "n": r["n"] if r else 0, "ci95": r["ci95"] if r else None, "note": note})

    for c, t in A["detector_recall"].items():
        pc = det_res["per_class"].get(c)
        add("Detektor", f"Recall@IoU{iou_thr} {c}", pc["recall"] if pc else None, t)
    add("Dokumenttyp", "Accuracy (ohne unsicher)", R["doctype"]["accuracy"], A["doctype_accuracy"])
    add("Dokumenttyp", "Anteil unsicher", R["doctype"]["uncertain"], A["doctype_uncertain_max"], "<=")
    add("Position", "Recall synthetische Negative", R["position"]["recall_negatives"], A["position_recall_negatives"])
    add("Position", "Fehlalarmrate echte korrekte Seiten", R["position"]["false_alarm"], A["position_false_alarm_max"], "<=")
    pv = ocr_res["variants"].get(prim, {})
    add("Tournummer", f"Exact Match akzeptiert ({prim}, GT-Box)", pv.get("exact_accepted"), A["tour_exact_match_accepted"])
    R["acceptance"] = crit
    R["timing"] = timer.summary()
    R["runtime_s"] = round(time.time() - t_start, 1)
    size = cfg["report"]["gallery_size"]
    R["gallery"] = {k: sorted(v, key=lambda g: -g["severity"])[:size] for k, v in gallery.items()}

    out = artifacts(cfg, "report")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(R, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    from .report import render

    render(cfg, R, out, log)
    failed = [c for c in crit if not c["passed"]]
    for c in crit:
        v = "-" if c["value"] is None else f"{c['value']:.3f}"
        log(f"[eval] {'OK  ' if c['passed'] else 'FAIL'} {c['stage']}: {c['metric']} = {v} "
            f"({c['cmp']} {c['threshold']}, n={c['n']}) {c['note']}")
    log(f"[eval] Report: {out / 'report.md'} | {out / 'report.html'}")
    if failed and not A.get("enforce", True):
        log(f"[eval] {len(failed)} Kriterien verfehlt - acceptance.enforce=false, Exit-Code 0")
        return 0
    return 1 if failed else 0

