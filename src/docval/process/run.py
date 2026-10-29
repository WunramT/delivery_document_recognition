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
from ..doctype.rules import UNCERTAIN, combine, keyword_decision, keyword_scores
from ..jsonutil import dumps
from ..models import ocr_model_dir, offline, setup_cache
from ..ocr.onnx_ocr import OcrEngine, pad_crop, pil_to_bgr
from ..ocr.postprocess import parse_cmr_count
from ..zones import MISSING, OK, UNCERTAIN as ZONE_UNCERTAIN, WRONG_POSITION, apply_overrides, check_page
from ..zones.synthetic import to_rgb
from .organize import REVIEW_TYPES, majority_tour, organize

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
# 8 digits, a single space inside allowed ("1228 8834"), not part of a longer number
NUMBER8 = r"(?<!\d)(?:\d ?){7}\d(?!\d)"
# 9 or 10 digits: a TA read with an extra digit next to it ("121685946")
NUMBER_LONG = r"(?<!\d)(?:\d ?){8,9}\d(?!\d)"
PAGE_OF = r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)"


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


def detector_dir(cfg, log=None) -> Path:
    """process.model: auto = the final model (make train-final, trained on all labeled pages) if it
    is newer than the evaluated one, else the evaluated one; final | eval force one of them."""
    ev, fin = artifacts(cfg, "detector"), artifacts(cfg, "detector_final")
    want = (cfg["process"].get("model") or "auto")
    has_fin = (fin / "detector.onnx").is_file()
    if want == "final" or (want == "auto" and has_fin and (
            not (ev / "detector.onnx").is_file()
            or (fin / "detector.onnx").stat().st_mtime >= (ev / "detector.onnx").stat().st_mtime)):
        return fin
    if want == "auto" and has_fin and log:
        log("[process] HINWEIS: detector_final ist älter als das ausgewertete Modell - nach make train export "
            "eval auch make train-final ausführen; verwendet wird das ausgewertete Modell")
    return ev


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


def pen_mark(im, box, band: float = 0.012, min_frac: float = 0.002) -> bool:
    """Coloured ink (pen, marker) in the row of a loading-list TA: the list is printed in black,
    a struck-out row or a note like "nie jedzie" is mostly written in colour. Only a hint - a
    row struck out in black is not found."""
    import numpy as np

    y1, y2 = max(0.0, box[1] - band), min(1.0, box[3] + band)
    a = np.asarray(im.convert("RGB").crop((0, int(y1 * im.height), im.width, max(int(y1 * im.height) + 1, int(y2 * im.height)))),
                   dtype=np.int16)
    sat = (a.max(2) - a.min(2) > 90) & (a.max(2) > 80)
    return bool(sat.mean() >= min_frac)


def drop_off_column(dets: list[dict], min_overlap: float = 0.5) -> list[dict]:
    """Loading list: the TA boxes form one column (one box per row). A ta_nummer box that overlaps
    that column (median left/right edge of the page's TA boxes) by less than `min_overlap` of its
    width sits in a neighbouring column - seen: the order number (61624820) read as a TA - and is
    dropped. Needs at least three TA boxes, otherwise the column is not known."""
    ta = [d for d in dets if d["cls"] == "ta_nummer"]
    if len(ta) < 3:
        return dets
    x1 = sorted(d["box"][0] for d in ta)[len(ta) // 2]
    x2 = sorted(d["box"][2] for d in ta)[len(ta) // 2]

    def in_column(b):
        return max(0.0, min(b[2], x2) - max(b[0], x1)) >= min_overlap * (b[2] - b[0])

    return [d for d in dets if d["cls"] != "ta_nummer" or in_column(d["box"])]


def ta_from_long(pages: list[dict]) -> list[int]:
    """Loading-list TA boxes read as 9-10 digits ("ZlecenieN 121685946" = TA 12168594 plus a digit
    next to it): an 8-digit part that is also a TA on a CMR or a Lieferschein number of this scan
    becomes the TA (`fixed` = the OCR text, shown on the review page). Only an unambiguous match
    counts; everything else stays unread. Moves the entries from ta_unread to ta; returns the pages."""
    known = {t["ta"] for p in pages if p["doc_type"] != "loading_list" for t in p.get("ta") or []}
    known |= {p["ls_number"] for p in pages if p.get("ls_number")}
    fixed = []
    for p in pages:
        if p["doc_type"] != "loading_list" or not p.get("ta_unread"):
            continue
        have = {t["ta"] for t in p["ta"]}
        rest = []
        for u in p["ta_unread"]:
            runs = [m.group(0).replace(" ", "") for m in re.finditer(NUMBER_LONG, u.get("text") or "")]
            hits = {r[i:i + 8] for r in runs for i in range(len(r) - 7)} & (known - have)
            if len(hits) == 1:
                ta = hits.pop()
                p["ta"].append({"ta": ta, "excluded": False, "box": u["box"], "score": u["score"],
                                "mark": u.get("mark", False), "fixed": u.get("text") or ""})
                have.add(ta)
                fixed.append(p["n"])
            else:
                rest.append(u)
        p["ta_unread"] = rest
        p["ta"].sort(key=lambda t: (t["box"][1], t["box"][0]))   # reading order, as in Pipeline.ta
    return sorted(set(fixed))


def ta_missed(ocr, im, ta_boxes: list, known: set) -> list[dict]:
    """8-digit numbers in the TA column of a loading list that no ta_nummer box covers (a row the
    model missed). The column = the x range of the found TA boxes; needs at least two of them."""
    if len(ta_boxes) < 2:
        return []
    W, H = im.width, im.height
    X1, X2 = int(max(0.0, min(b[0] for b in ta_boxes) - 0.03) * W), int(min(1.0, max(b[2] for b in ta_boxes) + 0.03) * W)
    Y1 = int(max(0.0, min(b[1] for b in ta_boxes) - 0.02) * H)
    out = []
    for d in ocr.detect_recognize(pil_to_bgr(im.convert("RGB").crop((X1, Y1, X2, H)))):
        nums = numbers8(d["text"])
        if not nums:
            continue
        xs, ys = [q[0] for q in d["quad"]], [q[1] for q in d["quad"]]
        box = [round((X1 + min(xs)) / W, 4), round((Y1 + min(ys)) / H, 4), round((X1 + max(xs)) / W, 4), round((Y1 + max(ys)) / H, 4)]
        cy = (box[1] + box[3]) / 2
        if any(b[1] - 0.005 <= cy <= b[3] + 0.005 for b in ta_boxes):
            continue
        for n in nums:
            if n not in known:
                known.add(n)
                out.append({"ta": n, "box": box})
    return out


class BoxReader:
    """OCR of one box exactly as make process reads it - also used live by make review when the
    person draws a box. read() returns {"text": OCR text, "value": parsed value or ""}:
    ls_nummer / ta_nummer -> 8-digit numbers, seitenzahl / cmr_count -> "i/n",
    tour_nummer -> the tour number if it fits the format."""

    def __init__(self, cfg: dict, engine=None, mode: str | None = None):
        if engine is None:   # only the primary engine (make review starts fast)
            prim = cfg["ocr"].get("primary") or f"{next(iter(cfg['ocr']['engines']))}/det_rec"
            name, mode = prim.split("/")
            e = cfg["ocr"]["engines"][name]
            engine = OcrEngine(name, ocr_model_dir(cfg, e["det"]), ocr_model_dir(cfg, e["rec"]),
                               {"limit_side_len": cfg["ocr"].get("det_limit_side_len", 960)})
        self.cfg, self.ocr, self.mode = cfg, engine, mode or "det_rec"

    def crop(self, im, box):
        return pad_crop(im, [box[0] * im.width, box[1] * im.height, box[2] * im.width, box[3] * im.height],
                        self.cfg["ocr"]["crop_padding"])

    def lines(self, im, box) -> list[str]:
        """OCR lines inside a box (detection + recognition: a box can hold several lines, e.g.
        "Zlecenie" above the TA, or several TAs on a CMR)."""
        crop = pil_to_bgr(self.crop(im, box))
        lines = [d["text"] for d in self.ocr.detect_recognize(crop)]
        if not lines:  # very small box: recognition only
            t, _ = self.ocr.recognize(crop)
            lines = [t] if t else []
        return lines

    def read(self, im, box, cls: str) -> dict:
        if cls == "tour_nummer":
            from ..eval.run import ocr_tour
            r = ocr_tour(self.ocr, self.crop(im, box), self.mode, self.cfg["ocr"],
                         self.cfg["labels"]["tour_number"]["format_regex"])
            return {"text": r["raw"], "value": r["text"] if r["valid_format"] else ""}
        text = " ".join(self.lines(im, box))
        if cls in ("ls_nummer", "ta_nummer"):
            nums = numbers8(text)
            value = (nums[0] if nums else "") if cls == "ls_nummer" else ", ".join(nums)
        elif cls == "seitenzahl":
            po = parse_page_of(text)
            value = f"{po[0]}/{po[1]}" if po else ""
        elif cls == "cmr_count":
            c = parse_cmr_count(text) or parse_page_of(text)
            value = f"{c[0]}/{c[1]}" if c else ""
        else:
            value = ""
        return {"text": text[:120], "value": value}


class Pipeline:
    """All models of one run, loaded once."""

    def __init__(self, cfg, log):
        from ..eval.run import load_engines

        self.cfg, self.log = cfg, log
        det_dir = detector_dir(cfg, log)
        if not (det_dir / "detector.onnx").is_file():
            raise FileNotFoundError(f"{det_dir / 'detector.onnx'} fehlt - zuerst `make train export eval`")
        self.detector = OnnxDetector(det_dir, min_score=0.01)
        self.model_name = det_dir.name
        log(f"[process] Detektor: {det_dir}")
        self.classes = self.detector.classes
        self.thr, self.unc, self.thr_source = load_thresholds(cfg, self.classes, log)
        self.zones = load_zones(cfg)
        self.rules = process_rules(cfg)
        engines = load_engines(cfg)
        prim = cfg["ocr"].get("primary") or f"{next(iter(engines))}/det_rec"
        name, self.tour_mode = prim.split("/")
        self.ocr = engines[name]
        self.reader = BoxReader(cfg, self.ocr, self.tour_mode)
        self.clf = None
        ccfg = cfg["doctype"]["classifier"]
        if ccfg.get("enabled") and artifacts(cfg, "doctype", "doctype.onnx").is_file():
            from ..doctype.classifier import OnnxDocTypeClassifier
            self.clf = OnnxDocTypeClassifier(artifacts(cfg, "doctype"))

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

        from ..zones.form_mask import suppress_unmasked

        masked, info = [], None
        inp = im
        mcfg = self.cfg.get("form_mask") or {}
        if applies(self.cfg, doc_type) or (doc_type == UNCERTAIN and applies(self.cfg, "cmr")):
            inp, info = mask_fields(im, mcfg)
            masked = info["masked"]
        # CMR whose field row was not found: pre-printed 22/23 must not count as signed
        if info is not None and not info["found"] and doc_type == UNCERTAIN:
            info = None   # unknown type without a field row: probably no CMR at all
        self.mask_found = None if info is None else info["found"]
        dets = [d for d in suppress_unmasked(self.detector(inp), info, mcfg)
                if d["score"] >= self.unc.get(d["cls"], 0.0)]
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
        if not parsed:  # slash read as "1" / "|": "3113" -> 3/13
            parsed = parse_page_of(t)
        return {"text": t, "parsed": list(parsed) if parsed else None, "box": b}

    def box_lines(self, im, box) -> list[str]:
        return self.reader.lines(im, box)

    def ta(self, im, dets) -> tuple[list[dict], list[dict]]:
        """TA numbers from the ta_nummer boxes (loading list: one per row, CMR: one box with all
        TAs). Only boxes are read - other 8-digit numbers on the page are ignored. Returns
        (TAs in reading order, each once, with their box; boxes without a readable number)."""
        out, unread = {}, []
        boxes = sorted((d for d in dets if d["cls"] == "ta_nummer"), key=lambda d: (d["box"][1], d["box"][0]))
        for d in boxes:
            lines = self.box_lines(im, d["box"])
            nums = numbers8(" ".join(lines))
            if not nums:
                unread.append({"box": d["box"], "text": " ".join(lines)[:80], "score": d["score"]})
            for t in nums:
                out.setdefault(t, {"ta": t, "excluded": False, "box": d["box"], "score": d["score"]})
        return list(out.values()), unread

    def ls_number(self, im, dets) -> dict | None:
        """Lieferschein number (= TA) from the ls_nummer box: "Lieferschein 12283251" on the front
        page, "Lieferschein (12283251)" on the following pages."""
        d = self.best(dets, "ls_nummer") or max((x for x in dets if x["cls"] == "ls_nummer"),
                                                 key=lambda x: x["score"], default=None)
        if d is None:
            return None
        text = " ".join(self.box_lines(im, d["box"]))
        nums = numbers8(text)
        return {"number": nums[0] if nums else None, "text": text[:80], "box": d["box"]}

    def page_of(self, im, dets) -> dict | None:
        """"Seite 1/2" (Lieferschein, bottom right) / "2/6" (loading list, top right) -> [i, n]."""
        d = self.best(dets, "seitenzahl") or max((x for x in dets if x["cls"] == "seitenzahl"),
                                                  key=lambda x: x["score"], default=None)
        if d is None:
            return None
        text = " ".join(self.box_lines(im, d["box"]))
        return {"parsed": parse_page_of(text), "text": text[:40], "box": d["box"]}

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
        if dt_["doc_type"] == "loading_list":
            dets = drop_off_column(dets)
        props = self.proposals(dets)
        reviewable = dt_["doc_type"] in REVIEW_TYPES or dt_["doc_type"] == UNCERTAIN
        rec = {"w": im.width, "h": im.height, "doc_type": dt_["doc_type"], "doc_reason": dt_["reason"],
               "header": dt_["header"], "dets": dets, "masked": masked, "proposals": props,
               "scores": {c: max([d["score"] for d in dets if d["cls"] == c], default=0.0)
                          for c in ("unterschrift", "stempel")},
               "tour": self.tour(im, dets) if reviewable else None,
               "cmr_count": self.cmr_count(im, dets) if dt_["doc_type"] in ("cmr", UNCERTAIN) else None,
               "view": self.view(dt_["doc_type"], dets), "mask_found": self.mask_found,
               "carrier": (carrier(dt_["header"], self.cfg) if dt_["doc_type"] == "bestaetigung" else
                           carrier(dt_["header"], self.cfg, "customers") if dt_["doc_type"] == "lieferschein"
                           else None)}
        rec["proposal"] = props.get(dt_["doc_type"], {}).get("classes", {})
        t = dt_["doc_type"]
        rec["ta"], rec["ta_unread"] = self.ta(im, dets) if t in ("loading_list", "cmr", UNCERTAIN) else ([], [])
        if t == "loading_list":   # a row without TA box; pen in the row (struck out, "nie jedzie"): the person decides
            rec["ta_missed"] = ta_missed(self.reader.ocr, im, [d["box"] for d in dets if d["cls"] == "ta_nummer"],
                                         {x["ta"] for x in rec["ta"]})
            for x in rec["ta"] + rec["ta_unread"] + rec["ta_missed"]:
                x["mark"] = pen_mark(im, x["box"])
        ls = self.ls_number(im, dets) if t in ("lieferschein", UNCERTAIN) else None
        po = self.page_of(im, dets) if t in ("lieferschein", "loading_list", UNCERTAIN) else None
        rec["ls_read"], rec["page_read"] = ls, po
        rec["ls_number"] = (ls or {}).get("number")
        rec["page_of"] = (po or {}).get("parsed")
        rec["ls_page"] = rec["page_of"] if t == "lieferschein" else None
        return rec


def carrier(header: str, cfg: dict, key: str = "confirmations") -> str | None:
    """Carrier from the header text: of a collective confirmation (process.confirmations, e.g.
    "DLW Kartons" -> hermes) or of a Lieferschein by its delivery address (process.customers,
    e.g. "Hermes"). None if unknown or ambiguous."""
    d = cfg["doctype"]
    hits = keyword_scores(header, (cfg["process"].get(key) or {}), d.get("fuzzy_min_len", 7))
    return next(iter(hits)) if len(hits) == 1 else None


def numbers8(text: str) -> list[str]:
    """8-digit numbers (TA / Lieferschein number) in OCR text, in order, each once:
    "Zlecenie 12283251" -> [12283251]; "12283251, 1228 8834" -> [12283251, 12288834]."""
    out = []
    for m in re.finditer(NUMBER8, text or ""):
        n = m.group(0).replace(" ", "")
        if n not in out:
            out.append(n)
    return out


def parse_page_of(text: str) -> list[int] | None:
    """"Seite 1/2", "1 / 2", "2/6" -> [i, n] with 1 <= i <= n; else None.
    The OCR often reads the slash as "|", "l", "I" or "1": "Seite 1|2" and "Seite 112" -> [1, 2],
    "3110" -> [3, 10] - a "1" counts as the slash only where i <= n results (page numbers < 100)."""
    t = re.sub(r"(?<=\d)\s*[|lI\\]\s*(?=\d)", "/", text or "")
    for m in re.finditer(PAGE_OF, t):
        i, n = int(m.group(1)), int(m.group(2))
        if 1 <= i <= n:
            return [i, n]
    for m in re.finditer(r"(?<![\d/])(\d{3,4})(?![\d/])", t):
        s = m.group(1)
        for k in range(1, len(s) - 1):
            if s[k] == "1" and s[k + 1] != "0":
                i, n = int(s[:k]), int(s[k + 1:])
                if 1 <= i <= n <= 99:
                    return [i, n]
    return None


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
    fixed = ta_from_long(pages)
    if fixed:
        log(f"[process] TA mit einer Ziffer zu viel gelesen, über CMR/Lieferschein korrigiert: S. {', '.join(map(str, fixed))}")
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
        "ta_validated": bool((pcfg.get("ta") or {}).get("validated")), "model": pipe.model_name,
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
