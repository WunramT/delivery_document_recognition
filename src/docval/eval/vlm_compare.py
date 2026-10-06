"""`make vlm-compare`: prototype - is a vision-language decision model (imajev-4b,
https://huggingface.co/mohit67890/imajev-4b) better or worse than the RF-DETR pipeline
at "is there a signature / a stamp on this page?"

Same pages (eval split), same pre-print mask and same GT as `make eval`. imajev runs as a
separate local HTTP server in its own venv (docs/VLM_VERGLEICH.md); this module only sends
requests and caches the answers in artifacts/vlm_compare/cache/, so a re-run (e.g. after a
new `make eval`) costs nothing.

imajev returns no boxes, only P(yes) per question. Compared are therefore page-level
decisions: presence per class (both views) and the CMR decision ok / fehlt / unsicher
against `pages.csv` of the last `make eval`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from ..config import artifacts
from ..data.dataset import load_pages
from ..data.labels import short_name
from ..jsonutil import dumps
from ..zones import MISSING, OK, UNCERTAIN, WRONG_POSITION
from .metrics import ratio

ALL = "alle"


# ------------------------------------------------------------------ metrics

def auc(scores: list[float], labels: list[bool]) -> float | None:
    """ROC-AUC (Mann-Whitney, ties count half). Threshold-free: 1.0 = positives always
    score higher than negatives, 0.5 = chance. None if one class is missing."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def binary_stats(pred: list[bool], labels: list[bool]) -> dict:
    tp = sum(p and y for p, y in zip(pred, labels))
    fp = sum(p and not y for p, y in zip(pred, labels))
    fn = sum(not p and y for p, y in zip(pred, labels))
    return {"recall": ratio(tp, tp + fn), "precision": ratio(tp, tp + fp),
            "accuracy": ratio(sum(p == y for p, y in zip(pred, labels)), len(labels)), "fp": fp, "fn": fn}


def auto_stats(decisions: list[bool | None], labels: list[bool]) -> dict:
    """decisions: True/False = decided automatically, None = a person checks."""
    done = [(d, y) for d, y in zip(decisions, labels) if d is not None]
    return {"auto": ratio(len(done), len(labels)), "auto_correct": ratio(sum(d == y for d, y in done), len(done))}


def three_state(p: float, accept: float, reject: float) -> bool | None:
    return True if p >= accept else False if p < reject else None


# ------------------------------------------------------------------ imajev client

def post_multipart(url: str, request: dict, image: bytes, timeout: float) -> dict:
    """POST /v1/systemone as multipart (field 'request' + file 'image'), stdlib only."""
    b = uuid.uuid4().hex
    body = b"".join([
        f'--{b}\r\nContent-Disposition: form-data; name="request"\r\n\r\n'.encode(),
        json.dumps(request).encode(), b"\r\n",
        f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="page.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n".encode(), image, b"\r\n",
        f"--{b}--\r\n".encode()])
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # local server, no proxy
    try:
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None


def build_request(questions: dict[str, str]) -> dict:
    return {"state": {"document": "scanned page of a transport document (CMR consignment note, "
                                  "delivery note or loading list)"},
            "questions": {c: {"type": "noul", "instructions": q} for c, q in questions.items()}}


def jpeg(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def crop_norm(im: Image.Image, box: list[float] | None) -> Image.Image:
    if not box:
        return im
    W, H = im.size
    return im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))


def center_in(box: list[float], area: list[float] | None) -> bool:
    if not area:
        return True
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return area[0] <= cx <= area[2] and area[1] <= cy <= area[3]


class ImajevClient:
    """Asks every view once per page; answers are cached on disk (key: page, view, questions)."""

    def __init__(self, vcfg: dict, cache_dir: Path, log):
        self.url = vcfg["url"]
        self.timeout = vcfg.get("timeout_s", 120)
        self.quality = vcfg.get("jpeg_quality", 90)
        self.request = build_request(vcfg["questions"])
        self.qhash = hashlib.sha1(json.dumps(self.request, sort_keys=True).encode()).hexdigest()[:10]
        self.cache_dir = cache_dir
        self.log = log
        self.calls = 0

    def check(self) -> str | None:
        """None if the server answers, else the error text."""
        base = self.url.split("/v1/")[0]
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"{base}/v1/models", timeout=10) as r:
                return None if r.status == 200 else f"HTTP {r.status}"
        except Exception as e:  # noqa: BLE001 - shown to the user as is
            return str(e)

    def __call__(self, file_name: str, view: str, im: Image.Image) -> dict:
        key = hashlib.sha1(f"{file_name}|{view}|{self.qhash}".encode()).hexdigest()[:16]
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        t0 = time.perf_counter()
        res = post_multipart(self.url, self.request, jpeg(im, self.quality), self.timeout)
        wall_ms = (time.perf_counter() - t0) * 1000
        out = {"file_name": file_name, "view": view, "wall_ms": wall_ms,
               "server_ms": (res.get("usage") or {}).get("total_ms"), "model": res.get("model"),
               "answers": {c: {"p": a.get("noul"), "unknown": a.get("unknown_probability"),
                               "abstained": a.get("abstained")} for c, a in (res.get("answers") or {}).items()}}
        path.write_text(dumps(out), encoding="utf-8")
        self.calls += 1
        return out


# ------------------------------------------------------------------ main

def read_pages_csv(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["file_name"]: r for r in csv.DictReader(f, delimiter=";")}


def detector_thresholds(cfg, classes) -> tuple[dict, dict, str]:
    """Working thresholds of the last `make eval` (results.json), else the fallback."""
    res = artifacts(cfg, "report", "results.json")
    fac = cfg["detector"].get("score_uncertain_factor", 0.6)
    if res.is_file():
        thr = (json.loads(res.read_text(encoding="utf-8")).get("detector") or {}).get("thresholds") or {}
        if all(c in thr for c in classes):
            return thr, {c: fac * thr[c] for c in classes}, "results.json (make eval)"
    st = cfg["detector"].get("score_threshold")
    t = st if isinstance(st, (int, float)) else cfg["detector"].get("score_threshold_fallback", 0.5)
    return {c: t for c in classes}, {c: fac * t for c in classes}, f"fest {t} (kein results.json)"


def run_vlm_compare(cfg, log) -> int:
    from .run import PagePrep

    vcfg = cfg["vlm_compare"]
    out = artifacts(cfg, "vlm_compare")
    cache = out / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    classes = list(vcfg["questions"])
    views: dict[str, list | None] = vcfg["views"]
    hi = vcfg.get("auto_band", 0.9)

    client = ImajevClient(vcfg, cache, log)
    err = client.check()
    if err and not any(cache.iterdir()):
        log(f"FEHLER: imajev-Server nicht erreichbar ({vcfg['url']}): {err}\n"
            "        Server starten: docs/VLM_VERGLEICH.md, Schritt 1")
        return 2
    if err:
        log(f"[vlm] WARNUNG: Server nicht erreichbar ({err}) - nur Antworten aus dem Cache")

    split_path = artifacts(cfg, "splits", "split.json")
    if not split_path.is_file():
        log("FEHLER: kein Split - zuerst `make split`")
        return 2
    split = {p["file_name"]: p["split"] for p in json.loads(split_path.read_text())["pages"]}
    eval_split = vcfg.get("split") or cfg.get("eval", {}).get("split", "test")
    want = vcfg.get("doc_types")
    pages, _ = load_pages(cfg)
    test = [p for p in pages if split.get(p.file_name) == eval_split and p.path is not None
            and (not want or p.doc_type in want)]
    if vcfg.get("limit"):
        test = test[:int(vcfg["limit"])]
    log(f"[vlm] {len(test)} Seiten ({eval_split}, {', '.join(want) if want else 'alle Typen'}), "
        f"Ansichten: {', '.join(views)}")

    detector = None
    det_dir = artifacts(cfg, "detector")
    if (det_dir / "detector.onnx").is_file():
        from ..detect.onnx_detector import OnnxDetector
        detector = OnnxDetector(det_dir, min_score=0.01)
        thr, unc, thr_src = detector_thresholds(cfg, classes)
        log(f"[vlm] RF-DETR-Schwellen: {thr_src}")
    else:
        thr, unc, thr_src = {}, {}, None
        log("[vlm] WARNUNG: kein artifacts/detector/detector.onnx - nur imajev wird ausgewertet")

    prep = PagePrep(cfg)
    rows, det_ms, failed = [], [], []
    for i, p in enumerate(test, 1):
        _, im = prep(p)                                 # masked like the detector input; drops masked GT boxes
        preds = []
        if detector:
            t0 = time.perf_counter()
            preds = detector(im)
            det_ms.append((time.perf_counter() - t0) * 1000)
        for view, area in views.items():
            try:
                ans = client(p.file_name, view, crop_norm(im, area))
            except Exception as e:  # noqa: BLE001 - one bad page must not stop the run
                failed.append(f"{short_name(p.file_name)} [{view}]: {e}")
                continue
            for c in classes:
                gt = any(center_in(b.norm(p.width, p.height), area) for b in p.boxes_of(c))
                ds = max([d["score"] for d in preds if d["cls"] == c and center_in(d["box"], area)], default=0.0)
                a = ans["answers"].get(c) or {}
                rows.append({"file_name": p.file_name, "doc_type": p.doc_type, "view": view, "cls": c,
                             "gt": gt, "vlm_p": a.get("p"), "vlm_unknown": a.get("unknown"),
                             "det_score": ds if detector else None, "vlm_ms": ans.get("wall_ms")})
        if i % 10 == 0 or i == len(test):
            log(f"[vlm] {i}/{len(test)} Seiten, {client.calls} neue Anfragen, {len(failed)} Fehler")

    R = {"meta": {"split": eval_split, "n_pages": len(test), "views": views, "url": vcfg["url"],
                  "questions": vcfg["questions"], "auto_band": hi, "detector": bool(detector),
                  "det_thresholds": thr, "det_uncertain": unc, "det_threshold_source": thr_src,
                  "failed": failed},
         "latency": {"vlm_ms_median": _median([r["vlm_ms"] for r in rows if r["cls"] == classes[0]]),
                     "det_ms_median": _median(det_ms)},
         "presence": presence_stats(rows, classes, views, hi, thr, unc)}
    R["decision"] = decision_stats(cfg, test, rows, classes, views, hi)
    (out / "results.json").write_text(dumps(R), encoding="utf-8")
    write_rows(out / "pages.csv", rows)
    (out / "report.md").write_text(render(R, classes), encoding="utf-8")
    log(f"[vlm] -> {out / 'report.md'}")
    for f in failed[:5]:
        log(f"[vlm] Fehler: {f}")
    return 0


def _median(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def presence_stats(rows, classes, views, hi, thr, unc) -> dict:
    """Per view x class x doc-type group: AUC, working point, automatic share."""
    out: dict = {}
    for view in views:
        for c in classes:
            sel = [r for r in rows if r["view"] == view and r["cls"] == c and r["vlm_p"] is not None]
            groups = {ALL: sel}
            for t in sorted({r["doc_type"] for r in sel if r["doc_type"]}):
                groups[t] = [r for r in sel if r["doc_type"] == t]
            for g, rs in groups.items():
                y = [r["gt"] for r in rs]
                vp = [r["vlm_p"] for r in rs]
                s = {"n": len(rs), "n_pos": sum(y),
                     "vlm": {"auc": auc(vp, y), **binary_stats([p >= 0.5 for p in vp], y),
                             **auto_stats([three_state(p, hi, 1 - hi) for p in vp], y)}}
                if rs and rs[0]["det_score"] is not None:
                    ds = [r["det_score"] for r in rs]
                    s["det"] = {"auc": auc(ds, y), **binary_stats([d >= thr[c] for d in ds], y),
                                **auto_stats([three_state(d, thr[c], unc[c]) for d in ds], y)}
                out.setdefault(view, {}).setdefault(c, {})[g] = s
    return out


def decision_stats(cfg, test, rows, classes, views, hi) -> dict | None:
    """End-to-end decision on pages with a rule (CMR): imajev vs. pages.csv of `make eval`.
    imajev cannot see positions: GT `falsche_position` counts as 'not ok' for both."""
    pos = read_pages_csv(artifacts(cfg, "report", "pages.csv"))
    view = "unten" if "unten" in views else next(iter(views))
    rules = cfg["zones"]["rules"]
    p_of = {(r["file_name"], r["cls"]): r["vlm_p"] for r in rows if r["view"] == view}
    res = {"view": view, "pages_csv": bool(pos), "vlm": _dq(), "det": _dq() if pos else None, "rows": []}
    for p in test:
        rule = rules.get(p.doc_type) or {}
        need = [c for c in (rule.get("require") or []) if c in classes]
        for f in (rule.get("fields") or {}).values():
            need += [c for c in f.get("require", []) if c in classes and c not in need]
        q = pos.get(p.file_name)
        if not need or not q or q.get("position_gt") in (None, "", "nicht_gefordert"):
            continue
        ps = [p_of.get((p.file_name, c)) for c in need]
        if any(v is None for v in ps):
            continue
        vlm = OK if all(v >= hi for v in ps) else MISSING if any(v < 1 - hi for v in ps) else UNCERTAIN
        gt = q["position_gt"]
        _count(res["vlm"], gt, vlm)
        if res["det"] is not None:
            _count(res["det"], gt, q["position"])
        res["rows"].append({"file_name": p.file_name, "gt": gt, "vlm": vlm, "det": q.get("position"),
                            "vlm_p": dict(zip(need, ps))})
    return res if res["rows"] else None


def _dq() -> dict:
    return {"n": 0, "auto_richtig": 0, "person": 0, "auto_falsch_fehler_uebersehen": 0, "auto_falsch_fehlalarm": 0}


def _count(dq: dict, gt: str, st: str) -> None:
    bad = (MISSING, WRONG_POSITION)
    dq["n"] += 1
    if st not in (OK, *bad):
        dq["person"] += 1
    elif st == OK and gt != OK:
        dq["auto_falsch_fehler_uebersehen"] += 1
    elif st in bad and gt not in bad:
        dq["auto_falsch_fehlalarm"] += 1
    else:
        dq["auto_richtig"] += 1


def write_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["file_name", "doc_type", "ansicht", "klasse", "gt", "imajev_p", "imajev_unknown",
                    "rfdetr_score", "uneinig_bei_0.5"])
        for r in rows:
            vp, ds = r["vlm_p"], r["det_score"]
            disagree = "" if vp is None or ds is None else int((vp >= 0.5) != (ds >= 0.5))
            w.writerow([r["file_name"], r["doc_type"], r["view"], r["cls"], int(r["gt"]),
                        _f(vp), _f(r["vlm_unknown"]), _f(ds), disagree])


# ------------------------------------------------------------------ report

def _f(v, d=3):
    return "" if v is None else f"{v:.{d}f}"


def _pct(r: dict | None) -> str:
    if not r or r.get("value") is None:
        return "–"
    return f"{100 * r['value']:.0f} % ({r['k']}/{r['n']})"


def _verdict(s: dict) -> str:
    v, d = s["vlm"]["auc"], (s.get("det") or {}).get("auc")
    if s["n_pos"] < 10 or s["n"] - s["n_pos"] < 10:
        return "zu wenige Seiten für eine Aussage"
    if v is None or d is None:
        return "–"
    if abs(v - d) < 0.02:
        return "gleichauf"
    return "**imajev besser**" if v > d else "**RF-DETR besser**"


def render(R: dict, classes: list[str]) -> str:
    m, lat = R["meta"], R["latency"]
    L = ["# Prototyp: imajev-4b vs. RF-DETR (Unterschrift / Stempel)", "",
         f"Split **{m['split']}**, {m['n_pages']} Seiten. imajev: `{m['url']}`. "
         f"RF-DETR-Schwellen: {m['det_threshold_source'] or 'kein Detektor'}.", "",
         "imajev liefert keine Boxen, nur P(ja) je Frage. Verglichen wird deshalb auf **Seitenebene**: "
         "„Ist in dieser Ansicht eine Unterschrift/ein Stempel?“ Für RF-DETR zählt der höchste Score der "
         "Klasse in der Ansicht. GT = annotierte Boxen (Mittelpunkt in der Ansicht), Vordruck-Felder maskiert "
         "wie in `make eval`.", "",
         "- **AUC**: schwellenfrei, 1.0 = trennt perfekt, 0.5 = Zufall. Der fairste Einzelwert.",
         f"- **Automatisch**: imajev entscheidet bei P ≥ {m['auto_band']} bzw. < {1 - m['auto_band']:.1f}, "
         "RF-DETR bei Score ≥ Arbeitsschwelle bzw. < Unsicher-Schwelle; dazwischen prüft eine Person.", "",
         f"Laufzeit (Median je Seite und Ansicht): imajev {_f(lat['vlm_ms_median'], 0) or '–'} ms, "
         f"RF-DETR {_f(lat['det_ms_median'], 0) or '–'} ms (ONNX, CPU).", ""]
    if m["failed"]:
        L += [f"**{len(m['failed'])} Anfragen fehlgeschlagen**, z. B. `{m['failed'][0]}`", ""]

    L += ["## 1. Kurzfazit (AUC, alle Dokumenttypen)", "",
          "| Ansicht | Klasse | Seiten (mit Objekt) | AUC imajev | AUC RF-DETR | Ergebnis |", "|---|---|---|---|---|---|"]
    for view, per in R["presence"].items():
        for c in classes:
            s = per.get(c, {}).get(ALL)
            if s:
                L.append(f"| {view} | {c} | {s['n']} ({s['n_pos']}) | {_f(s['vlm']['auc'])} | "
                         f"{_f((s.get('det') or {}).get('auc'))} | {_verdict(s)} |")
    L.append("")

    L += ["## 2. Details je Dokumenttyp", "",
          "| Ansicht | Klasse | Typ | Modell | AUC | Recall | Precision | Fehlalarme | Übersehen | automatisch | davon richtig |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for view, per in R["presence"].items():
        for c in classes:
            for g, s in per.get(c, {}).items():
                for name, k in (("imajev (P ≥ 0.5)", "vlm"), ("RF-DETR", "det")):
                    x = s.get(k)
                    if x:
                        L.append(f"| {view} | {c} | {g} | {name} | {_f(x['auc'])} | {_pct(x['recall'])} | "
                                 f"{_pct(x['precision'])} | {x['fp']} | {x['fn']} | {_pct(x['auto'])} | "
                                 f"{_pct(x['auto_correct'])} |")
    L.append("")

    d = R.get("decision")
    L += ["## 3. Entscheidung je Seite (Dokumenttypen mit Regel, z. B. CMR)", ""]
    if not d:
        L += ["Keine Daten: `artifacts/report/pages.csv` fehlt (zuerst `make eval`) oder keine Seite mit Regel.", ""]
    else:
        L += [f"imajev-Ansicht **{d['view']}**: ok = alle geforderten Klassen P ≥ {m['auto_band']}, "
              f"fehlt = eine P < {1 - m['auto_band']:.1f}, sonst unsicher (Person). RF-DETR = Spalte `position` "
              "aus `make eval`. imajev prüft keine Position: GT `falsche_position` zählt für beide als nicht ok.", "",
              "| Modell | Seiten | automatisch richtig | Person prüft | Fehler übersehen | Fehlalarm |", "|---|---|---|---|---|---|"]
        for name, k in (("imajev", "vlm"), ("RF-DETR-Pipeline", "det")):
            q = d.get(k)
            if q:
                L.append(f"| {name} | {q['n']} | {q['auto_richtig']} | {q['person']} | "
                         f"{q['auto_falsch_fehler_uebersehen']} | {q['auto_falsch_fehlalarm']} |")
        L.append("")
        diff = [r for r in d["rows"] if r["vlm"] != r["det"]]
        if diff:
            L += ["Seiten, auf denen beide verschieden entscheiden (max. 30):", "",
                  "| Seite | GT | imajev | RF-DETR | imajev P |", "|---|---|---|---|---|"]
            for r in diff[:30]:
                ps = ", ".join(f"{c} {v:.2f}" for c, v in r["vlm_p"].items())
                L.append(f"| {short_name(r['file_name'])} | {r['gt']} | {r['vlm']} | {r['det']} | {ps} |")
            L.append("")
    L += ["Alle Einzelwerte: `artifacts/vlm_compare/pages.csv` (Spalte `uneinig_bei_0.5`).", ""]
    return "\n".join(L)
