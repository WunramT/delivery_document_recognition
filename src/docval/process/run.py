"""`make process SCANS=<pdf | folder>`: one scanned tour through the pipeline.

    artifacts/process/<name>/seiten/s001.png ...   rendered pages
                             ergebnis.json          every page + organisational result
                             pruefung.html          review page (pruefung_pl.html in Polish)

No ground truth is used. The models come from the last `make train export eval`
(detector.onnx, doctype.onnx, zones.yaml, thresholds from results.json).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml
from PIL import Image, ImageSequence

from ..config import artifacts, resolve
from ..detect.onnx_detector import OnnxDetector
from ..doctype.rules import UNCERTAIN, combine, fold, fuzzy_contains, keyword_decision, keyword_scores
from ..jsonutil import dumps
from ..models import ocr_model_dir, offline, setup_cache
from ..ocr.onnx_ocr import Detector, crop_quad, pad_crop, pil_to_bgr
from ..ocr.postprocess import parse_cmr_count
from ..zones import MISSING, OK, UNCERTAIN as ZONE_UNCERTAIN, WRONG_POSITION, apply_overrides, check_page
from ..zones.synthetic import to_rgb
from .organize import REVIEW_TYPES, majority_tour, organize

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


# ------------------------------------------------------------------ input

def render_input(src: Path, out_dir: Path, dpi: int, log) -> list[dict]:
    """PDF(s) and/or images (a file or a folder, sorted by name) -> seiten/sNNN.png.
    Returns [{"image": relative path, "source": "file.pdf#3"}] in scan order."""
    files = [src] if src.is_file() else sorted(f for f in src.iterdir()
                                              if f.suffix.lower() in IMAGE_EXT + (".pdf",))
    if not files:
        raise FileNotFoundError(f"keine PDF/Bilder in {src}")
    pages_dir = out_dir / "seiten"
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir(parents=True)
    out = []

    def add(im: Image.Image, source: str):
        rel = f"seiten/s{len(out) + 1:03d}.png"
        to_rgb(im).save(out_dir / rel)
        out.append({"image": rel, "source": source})

    for f in files:
        if f.suffix.lower() == ".pdf":
            if not shutil.which("pdftoppm"):
                raise RuntimeError("pdftoppm (poppler-utils) fehlt - im Devcontainer vorhanden")
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(f), str(Path(tmp) / "p")], check=True)
                rendered = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
                for k, r in enumerate(rendered, 1):
                    with Image.open(r) as im:
                        add(im, f"{f.name}#{k}")
        else:
            with Image.open(f) as im:
                frames = list(ImageSequence.Iterator(im))
                for k, fr in enumerate(frames, 1):
                    add(fr.copy(), f.name if len(frames) == 1 else f"{f.name}#{k}")
    log(f"[process] {len(out)} Seiten aus {len(files)} Datei(en) -> {pages_dir}")
    return out


def tour_from_name(name: str, cfg: dict) -> str | None:
    """'425_21.09.2026' (folder/file name like the label exports) -> '425/21.09.2026/4000'."""
    fe = cfg["labels"]["tour_number"].get("from_export_name") or {}
    m = re.match(fe.get("pattern") or r"$^", name)
    if not m:
        return None
    return fe["format"].format(plant=fe.get("plant", ""), **m.groupdict())


def normalize_tour(arg: str | None, cfg: dict) -> str | None:
    if not arg:
        return None
    if re.fullmatch(cfg["labels"]["tour_number"]["format_regex"], arg):
        return arg
    t = tour_from_name(arg, cfg)
    if t is None:
        raise ValueError(f"Tournummer '{arg}' passt weder zum Format (z. B. 503/01.09.2026/4000) "
                         f"noch zu <Tour>_<Datum> (z. B. 503_01.09.2026)")
    return t


def safe_name(tour: str) -> str:
    return re.sub(r"[^\w.-]+", "_", tour)


# ------------------------------------------------------------------ models

def load_thresholds(cfg, classes, log) -> tuple[dict, dict, str]:
    """Accept/uncertain threshold per class from the last `make eval` (operating point
    process.operating_point), else detector.score_threshold."""
    point = cfg["process"].get("operating_point", "aktuell")
    path = artifacts(cfg, "report", "results.json")
    factor = cfg["detector"].get("score_uncertain_factor", 0.6)
    if path.is_file():
        R = json.loads(path.read_text(encoding="utf-8"))
        op = (R.get("position_operating_points") or {}).get(point)
        if op:
            return op["accept"], op["uncertain"], f"make eval, Betriebspunkt {point}"
        thr = R["detector"]["thresholds"]
        return thr, {c: round(t * factor, 3) for c, t in thr.items()}, "make eval"
    fixed = cfg["detector"]["score_threshold"]
    t = float(fixed) if fixed != "auto" else float(cfg["detector"].get("score_threshold_fallback", 0.5))
    log(f"[process] WARNUNG: keine results.json - feste Schwelle {t} für alle Klassen")
    return {c: t for c in classes}, {c: round(t * factor, 3) for c in classes}, "fest (keine Evaluation)"


def load_zones(cfg) -> dict:
    path = artifacts(cfg, "zones.yaml")
    if not path.is_file():
        raise FileNotFoundError(f"{path} fehlt - zuerst `make eval` (leitet die Soll-Zonen ab)")
    zones = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("zones") or {}
    return apply_overrides(zones, cfg["process"].get("zone_overrides") or {})


def process_rules(cfg) -> dict:
    """zones.rules, per doc type replaced by process.rules (Lieferschein: stamp or signature)."""
    rules = dict(cfg["zones"]["rules"])
    rules.update(cfg["process"].get("rules") or {})
    return rules


class Pipeline:
    """All models of one run, loaded once."""

    def __init__(self, cfg, log):
        from ..eval.run import load_engines

        self.cfg, self.log = cfg, log
        det_dir = artifacts(cfg, "detector")
        if not (det_dir / "detector.onnx").is_file():
            raise FileNotFoundError(f"{det_dir / 'detector.onnx'} fehlt - zuerst `make train export eval`")
        self.detector = OnnxDetector(det_dir, min_score=0.01)
        self.classes = self.detector.classes
        self.thr, self.unc, self.thr_source = load_thresholds(cfg, self.classes, log)
        self.zones = load_zones(cfg)
        self.rules = process_rules(cfg)
        engines = load_engines(cfg)
        prim = cfg["ocr"].get("primary") or f"{next(iter(engines))}/det_rec"
        name, self.tour_mode = prim.split("/")
        self.ocr = engines[name]
        self.clf = None
        ccfg = cfg["doctype"]["classifier"]
        if ccfg.get("enabled") and artifacts(cfg, "doctype", "doctype.onnx").is_file():
            from ..doctype.classifier import OnnxDocTypeClassifier
            self.clf = OnnxDocTypeClassifier(artifacts(cfg, "doctype"))
        tcfg = cfg["process"].get("ta") or {}
        self.ta_det = None
        if tcfg.get("enabled"):
            e = cfg["ocr"]["engines"][name]
            self.ta_det = Detector(ocr_model_dir(cfg, e["det"]), limit_side_len=tcfg.get("det_limit_side_len", 1600))

    # ---------------------------------------------------------- stages
    def doc_type(self, im: Image.Image) -> dict:
        from ..eval.run import header_keywords

        d = self.cfg["doctype"]
        text, hits = header_keywords(self.ocr, im, d)
        kw_type, kw_reason = keyword_decision(hits, d.get("priority", []))
        clf_type = clf_conf = None
        if self.clf is not None:
            clf_type, clf_conf, _ = self.clf.predict(im)
        c = d["classifier"]
        dec = combine(kw_type, kw_reason, clf_type, clf_conf, c["min_confidence"], c["conflict_confidence"])
        return {"doc_type": dec["doc_type"], "reason": dec["reason"], "header": text[:300]}

    def detect(self, im: Image.Image, doc_type: str) -> tuple[list[dict], list]:
        """Detections (>= uncertain threshold) on the detector input; CMR (and pages of
        unknown type whose CMR field row is found) with pre-printed fields 22/23 masked."""
        from ..zones.form_mask import applies, mask_fields

        masked = []
        inp = im
        mcfg = self.cfg.get("form_mask") or {}
        if applies(self.cfg, doc_type) or (doc_type == UNCERTAIN and applies(self.cfg, "cmr")):
            inp, info = mask_fields(im, mcfg)
            masked = info["masked"]
        dets = [d for d in self.detector(inp) if d["score"] >= self.unc.get(d["cls"], 0.0)]
        return [{"cls": d["cls"], "box": [round(v, 4) for v in d["box"]], "score": round(d["score"], 3)}
                for d in dets], masked

    def proposals(self, dets: list[dict]) -> dict:
        """Per reviewable doc type: check_page result and per required class ja/nein/unsicher.
        Found outside the target zone -> unsicher (the person decides)."""
        z = self.cfg["zones"]
        out = {}
        for t in REVIEW_TYPES:
            res = check_page(t, dets, self.zones, self.rules, z["min_overlap"], self.thr, self.unc)
            per = {}
            for d in res.get("details") or []:
                per[d["cls"]] = {OK: "ja", MISSING: "nein", WRONG_POSITION: "unsicher",
                                 ZONE_UNCERTAIN: "unsicher"}.get(d["status"], "unsicher")
            out[t] = {"status": res["status"], "reason": res["reason"], "classes": per}
        return out

    def best(self, dets, cls) -> dict | None:
        c = [d for d in dets if d["cls"] == cls and d["score"] >= self.thr.get(cls, 0.5)]
        return max(c, key=lambda d: d["score"]) if c else None

    def tour(self, im, dets) -> dict | None:
        from ..eval.run import ocr_tour

        d = self.best(dets, "tour_nummer")
        if d is None:
            return None
        b = d["box"]
        crop = pad_crop(im, [b[0] * im.width, b[1] * im.height, b[2] * im.width, b[3] * im.height],
                        self.cfg["ocr"]["crop_padding"])
        r = ocr_tour(self.ocr, crop, self.tour_mode, self.cfg["ocr"], self.cfg["labels"]["tour_number"]["format_regex"])
        return {"text": r["text"], "raw": r["raw"], "score": round(r["score"], 3), "accepted": r["accepted"],
                "reason": r["reason"], "box": b}

    def cmr_count(self, im, dets) -> dict | None:
        from ..eval.run import ocr_det_rec_text

        d = self.best(dets, "cmr_count")
        if d is None:
            return None
        b = d["box"]
        crop = pil_to_bgr(pad_crop(im, [b[0] * im.width, b[1] * im.height, b[2] * im.width, b[3] * im.height],
                                   self.cfg["ocr"]["crop_padding"]))
        t, _ = self.ocr.recognize(crop)
        parsed = parse_cmr_count(t)
        if not parsed:  # label and number on two lines
            t, _ = ocr_det_rec_text(self.ocr, crop)
            parsed = parse_cmr_count(t)
        return {"text": t, "parsed": list(parsed) if parsed else None, "box": b}

    def ta(self, im) -> list[dict]:
        """TA numbers on the page (full-page OCR), grouped into text rows. A row with a
        'not shipped' keyword (e.g. 'Nie jedzie') marks its TA numbers as excluded."""
        if self.ta_det is None:
            return []
        tcfg = self.cfg["process"]["ta"]
        bgr = pil_to_bgr(im)
        quads = self.ta_det(bgr)
        if not quads:
            return []
        texts = self.ocr.rec([crop_quad(bgr, q) for q in quads])
        lines = [{"text": t, "y1": float(q[:, 1].min()), "y2": float(q[:, 1].max()), "x": float(q[:, 0].min())}
                 for q, (t, _) in zip(quads, texts)]
        return find_ta(lines, tcfg["regex"], tcfg.get("not_shipped") or [])

    def view(self, doc_type, dets) -> list[float]:
        """Part of the page the review card shows: the configured area of the doc type
        plus every confident signature/stamp detection (weak ones only in the full page)."""
        v = list((self.cfg["process"].get("view") or {}).get(doc_type, [0.0, 0.0, 1.0, 1.0]))
        for d in dets:
            if d["cls"] in ("unterschrift", "stempel") and d["score"] >= self.thr.get(d["cls"], 0.5):
                b = d["box"]
                v = [min(v[0], b[0] - 0.03), min(v[1], b[1] - 0.03), max(v[2], b[2] + 0.03), max(v[3], b[3] + 0.03)]
        return [round(max(0.0, v[0]), 4), round(max(0.0, v[1]), 4), round(min(1.0, v[2]), 4), round(min(1.0, v[3]), 4)]

    def page(self, path: Path) -> dict:
        im = to_rgb(Image.open(path))
        dt_ = self.doc_type(im)
        dets, masked = self.detect(im, dt_["doc_type"])
        props = self.proposals(dets)
        reviewable = dt_["doc_type"] in REVIEW_TYPES or dt_["doc_type"] == UNCERTAIN
        rec = {"w": im.width, "h": im.height, "doc_type": dt_["doc_type"], "doc_reason": dt_["reason"],
               "header": dt_["header"], "dets": dets, "masked": masked, "proposals": props,
               "scores": {c: max([d["score"] for d in dets if d["cls"] == c], default=0.0)
                          for c in ("unterschrift", "stempel")},
               "tour": self.tour(im, dets) if reviewable else None,
               "cmr_count": self.cmr_count(im, dets) if dt_["doc_type"] in ("cmr", UNCERTAIN) else None,
               "ta": self.ta(im), "view": self.view(dt_["doc_type"], dets),
               "carrier": (carrier(dt_["header"], self.cfg) if dt_["doc_type"] == "bestaetigung" else
                           carrier(dt_["header"], self.cfg, "customers") if dt_["doc_type"] == "lieferschein"
                           else None)}
        rec["proposal"] = props.get(dt_["doc_type"], {}).get("classes", {})
        return rec


def carrier(header: str, cfg: dict, key: str = "confirmations") -> str | None:
    """Carrier from the header text: of a collective confirmation (process.confirmations, e.g.
    "DLW Kartons" -> hermes) or of a Lieferschein by its delivery address (process.customers,
    e.g. "Hermes"). None if unknown or ambiguous."""
    d = cfg["doctype"]
    hits = keyword_scores(header, (cfg["process"].get(key) or {}), d.get("fuzzy_min_len", 7))
    return next(iter(hits)) if len(hits) == 1 else None


def find_ta(lines: list[dict], regex: str, not_shipped: list[str]) -> list[dict]:
    """lines: [{"text", "y1", "y2", "x"}] (pixels). Lines whose vertical centers lie within
    half a line height form a row (one entry of the loading list). Returns
    [{"ta", "excluded", "row"}] in reading order, each TA once (excluded wins)."""
    rows: list[dict] = []
    for ln in sorted(lines, key=lambda l: (l["y1"] + l["y2"]) / 2):
        yc, h = (ln["y1"] + ln["y2"]) / 2, max(1.0, ln["y2"] - ln["y1"])
        if rows and abs(yc - rows[-1]["yc"]) <= 0.5 * max(h, rows[-1]["h"]):
            rows[-1]["lines"].append(ln)
        else:
            rows.append({"yc": yc, "h": h, "lines": [ln]})
    keys = [fold(k) for k in not_shipped if fold(k)]
    out: dict[str, dict] = {}
    for r in rows:
        text = " ".join(l["text"] for l in sorted(r["lines"], key=lambda l: l["x"]))
        hay = fold(text)
        excluded = any(fuzzy_contains(hay, k, 1 if len(k) >= 7 else 0) for k in keys)
        # per OCR line (columns are separate lines), spaces removed: "1228 8834" -> 12288834,
        # without gluing the row number of the neighbouring column to the TA
        for ln in r["lines"]:
            for m in re.finditer(regex, ln["text"].replace(" ", "")):
                ta = m.group(0)
                if ta not in out or excluded:
                    out[ta] = {"ta": ta, "excluded": excluded, "row": text[:120]}
    return list(out.values())


# ------------------------------------------------------------------ main

def run_process(cfg, src: str, tour_arg: str | None, out_name: str | None, log) -> int:
    from .review import write_review

    setup_cache(cfg)
    offline()
    t0 = time.time()
    src_path = resolve(src)
    if not src_path.exists():
        log(f"FEHLER: {src_path} nicht gefunden")
        return 2
    pcfg = cfg["process"]
    try:
        tour = normalize_tour(tour_arg, cfg)
    except ValueError as e:
        log(f"FEHLER: {e}")
        return 2
    tour_source = "angegeben" if tour else None
    if not tour:
        tour = tour_from_name(src_path.stem if src_path.is_file() else src_path.name, cfg)
        tour_source = "Dateiname" if tour else None
    name = out_name or (safe_name(tour) if tour else src_path.stem)
    out = artifacts(cfg, "process", name)
    out.mkdir(parents=True, exist_ok=True)
    try:
        pipe = Pipeline(cfg, log)
    except FileNotFoundError as e:
        log(f"FEHLER: {e}")
        return 2
    rendered = render_input(src_path, out, pcfg.get("dpi", 150), log)
    pages = []
    for n, r in enumerate(rendered, 1):
        t1 = time.time()
        rec = {"n": n, "id": f"s{n:03d}", **r, **pipe.page(out / r["image"])}
        pages.append(rec)
        cc = (rec["cmr_count"] or {}).get("parsed")
        log(f"[process] S. {n:3d}: {rec['doc_type']:12s} "
            f"tour={(rec['tour'] or {}).get('text', '-') if rec['tour'] else '-'} "
            f"{'CMR ' + '/'.join(map(str, cc)) if cc else ''} "
            f"{' '.join(f'{c}={v}' for c, v in rec['proposal'].items())} ({time.time() - t1:.1f} s)")
    if not tour:
        tour = majority_tour(pages)
        tour_source = "häufigste gelesene Tournummer" if tour else None
    org = organize(pages, tour, pipe.rules, bool((pcfg.get("ta") or {}).get("validated")))
    result = {
        "format": "docval-ergebnis", "version": 1, "created": dt.datetime.now().isoformat(timespec="seconds"),
        "input": str(src_path), "name": name, "tour": tour, "tour_source": tour_source,
        "dpi": pcfg.get("dpi", 150), "thresholds": {"accept": pipe.thr, "uncertain": pipe.unc,
                                                    "source": pipe.thr_source},
        "rules": {t: {"require": (pipe.rules.get(t) or {}).get("require") or [],
                      "mode": (pipe.rules.get(t) or {}).get("mode", "all")} for t in REVIEW_TYPES},
        "classes": pipe.classes, "doc_types": cfg["doc_types"], "pages": pages, "organize": org,
        "ta_validated": bool((pcfg.get("ta") or {}).get("validated")),
    }
    (out / "ergebnis.json").write_text(dumps(result, indent=1), encoding="utf-8")
    for lang in cfg.get("ui_languages") or ["de"]:
        p = write_review(out, result, lang)
        log(f"[process] Prüfseite: {p}")
    for c in org["checks"]:
        from .texts import render_check
        log(f"[process] {c['level']:8s} {render_check(c, 'de')}")
    log(f"[process] Tour {tour or '?'} ({tour_source or '-'}), {len(pages)} Seiten in {time.time() - t0:.0f} s -> {out}")
    log("[process] Weiter: Prüfseite öffnen, alle Karten bestätigen, „Entscheidung speichern“ "
        f"als {out / 'entscheidung.json'}, dann `make finalize RUN={name}`")
    return 0
