"""Presentation slides for the prototype `make vlm-compare` (imajev-4b vs. RF-DETR):
one results slide and one slide with the negative that limits recall at precision 100 %.

Reads artifacts/vlm_compare/{results.json, pages.csv}; skipped if they are missing.
Config `presentation.vlm_example` (part of a file name, optionally "<name> <variant>")
picks the example; default is the negative that sets RF-DETR's signature threshold.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

from ..config import artifacts

DEFAULT_NOTE = ("Kein Label fehlt: hier wurde nur eine Zahl von Hand eingetragen, eine Unterschrift gibt es nicht. "
                "{who} sieht die Handschrift trotzdem wie eine Unterschrift aus.")


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _short(fn: str) -> str:
    from ..data.labels import short_name
    return short_name(fn)


def _recall_p100(rows, key):
    pos = [_num(r[key]) for r in rows if r["gt"] == "1" and _num(r[key]) is not None]
    neg = [_num(r[key]) for r in rows if r["gt"] == "0" and _num(r[key]) is not None]
    if not pos or not neg:
        return None
    t = max(neg)
    return sum(v > t for v in pos), len(pos)


def vlm_slides(D, R, cfg, log=print) -> bool:
    from .presentation import CLASS_DE, CRITICAL, GOOD, INK, INK2, frac, pct

    out = artifacts(cfg, "vlm_compare")
    if not (out / "results.json").is_file() or not (out / "pages.csv").is_file():
        log("[praesentation] kein make vlm-compare - Vergleichsfolien entfallen")
        return False
    V = json.loads((out / "results.json").read_text(encoding="utf-8"))
    fp = V.get("full_precision") or {}
    if not fp:
        return False
    view = "unten" if "unten" in fp else next(iter(fp))
    area = (V["meta"].get("views") or {}).get(view)
    model = V["meta"].get("model") or "imajev"
    classes = [c for c in ("unterschrift", "stempel") if c in fp[view]]
    rows_all = _rows(out / "pages.csv")

    # ---------------------------------------------------------------- results
    D.slide(f"Alternative geprüft: Sprach-Bild-Modell ({model})", "Vergleich")
    D.para(0.6, 1.9, f"{model} (Qwen3.5-4B + LoRA, Apache-2.0) beantwortet je Seite „Unterschrift da? Stempel da?“ "
                     "mit einer Wahrscheinlichkeit – ohne Boxen. Gleiche Testseiten, gleiche Maske für Feld 22/23. "
                     "Seiten ohne Objekt: echte + Kopien der Testseiten mit übermalten Label-Boxen.", 12, 13, INK2)
    trows, rf_wins = [], True
    for c in classes:
        s = fp[view][c]
        v, d = (s.get("vlm") or {}).get("recall"), (s.get("det") or {}).get("recall")
        kd, kv = (d or {}).get("k", 0), (v or {}).get("k", 0)
        rf_wins &= kd >= kv
        col_v, col_d = (INK, INK) if kd == kv else (CRITICAL, GOOD) if kd > kv else (GOOD, CRITICAL)
        auc = ((V.get("presence") or {}).get(view, {}).get(c, {}).get("alle") or {})
        a_v, a_d = (auc.get("vlm") or {}).get("auc"), (auc.get("det") or {}).get("auc")
        trows.append([CLASS_DE.get(c, c), f"{s['n_pos']} / {s['n_neg']}",
                      (f"{pct(v)} ({frac(v)})", col_v), (f"{pct(d)} ({frac(d)})", col_d),
                      "–" if a_v is None else f"{a_v:.3f}", "–" if a_d is None else f"{a_d:.3f}"])
    y = D.table(0.6, 3.05, [1.8, 1.9, 2.6, 2.6, 1.5, 1.6],
                ["Klasse", "Seiten mit / ohne", f"Recall bei Precision 100 % – {model}",
                 "Recall bei Precision 100 % – RF-DETR", f"AUC {model}", "AUC RF-DETR"], trows, size=12.5)
    lat = V.get("latency") or {}
    dec = V.get("decision") or {}
    items = []
    if lat.get("vlm_ms_median") and lat.get("det_ms_median"):
        items.append(f"Laufzeit je Seite: {model} {lat['vlm_ms_median'] / 1000:.0f} s (8-GB-Laptop-GPU), "
                     f"RF-DETR {lat['det_ms_median'] / 1000:.2f} s (CPU) – rund "
                     f"{lat['vlm_ms_median'] / lat['det_ms_median']:.0f}× langsamer.")
    if dec.get("vlm") and dec.get("det"):
        items.append(f"CMR-Entscheidung: an Person {dec['vlm']['person']} von {dec['vlm']['n']} Seiten ({model}) "
                     f"gegenüber {dec['det']['person']} von {dec['det']['n']} (RF-DETR); Fehler übersehen bei beiden "
                     f"{dec['vlm']['auto_falsch_fehler_uebersehen']} bzw. {dec['det']['auto_falsch_fehler_uebersehen']}.")
    items.append("Keine Position (Feld 22/23/24, Feld 13) und nicht im Browser lauffähig.")
    y = D.bullets(0.6, y + 0.3, items, 12, 13)
    D.text(0.6, max(y + 0.1, 6.3), "Ergebnis: RF-DETR bleibt – das Sprach-Bild-Modell ist bei keiner Klasse besser."
           if rf_wins else f"Ergebnis: {model} ist bei mindestens einer Klasse besser – weiter prüfen.",
           14, GOOD if rf_wins else CRITICAL, weight="bold")
    D.save()

    # ---------------------------------------------------------------- example negative
    want = (cfg.get("presentation") or {}).get("vlm_example")
    if not want:
        want = ((fp[view].get("unterschrift") or {}).get("det") or {}).get("hardest_negative")
    if not want:
        return True
    name, _, variant = want.partition(" ")
    variant = variant.strip() or None
    cand = [r for r in rows_all if r["ansicht"] == view and name.replace(".png", "") in _short(r["file_name"])
            and r["gt"] == "0" and (variant is None or r["variante"] == variant)]
    if not cand:
        log(f"[praesentation] Vergleichsbeispiel '{want}' nicht in pages.csv")
        return True
    ex = max(cand, key=lambda r: _num(r["rfdetr_score"]) or 0)
    cls, variant = ex["klasse"], ex["variante"]
    img = _example_image(cfg, ex)
    if img is None:
        log(f"[praesentation] Bild zu '{want}' nicht gefunden - Beispielfolie entfällt")
        return True
    from ..detect.onnx_detector import OnnxDetector
    from .presentation_examples import crop_norm, draw_boxes, shrink

    thr = R["detector"]["thresholds"]
    factor = cfg["detector"].get("score_uncertain_factor", 0.6)
    dets = [d for d in OnnxDetector(artifacts(cfg, "detector"), min_score=0.05)(img)
            if d["cls"] == cls and d["score"] >= thr.get(cls, 0.5) * factor]
    shown = draw_boxes(img, dets, CLASS_DE)
    shown = shrink(crop_norm(shown, area) if area else shown, 1600)

    p_v, p_d = _num(ex["imajev_p"]), _num(ex["rfdetr_score"])
    sel = [r for r in rows_all if r["ansicht"] == view and r["klasse"] == cls]
    without = [r for r in sel if not (r["file_name"] == ex["file_name"] and r["variante"] == variant)]
    rec_d, rec_d2 = _recall_p100(sel, "rfdetr_score"), _recall_p100(without, "rfdetr_score")
    rec_v, rec_v2 = _recall_p100(sel, "imajev_p"), _recall_p100(without, "imajev_p")

    wrong = {"RF-DETR": p_d is not None and p_d >= thr.get(cls, 0.5), model: p_v is not None and p_v >= 0.5}
    who = [m for m, w in wrong.items() if w]
    D.slide(f"Grenze {'beider Modelle' if len(who) == 2 else 'der Erkennung'}: Handschrift ohne "
            f"{CLASS_DE.get(cls, cls)}", "Vergleich")
    D.image(0.6, 1.85, 7.0, 4.6, shown)
    label = "Original" if variant == "original" else f"Kopie, {CLASS_DE.get(cls, cls)} übermalt"
    D.text(0.6, 6.6, f"{_short(ex['file_name'])} · {label} · Ausschnitt „{view}“", 10.5, INK2)
    x, w = 8.0, 4.75
    note = (cfg.get("presentation") or {}).get("vlm_example_note") or DEFAULT_NOTE.format(
        who="Für beide Modelle" if len(who) == 2 else f"Für {who[0]}" if who else "Für die Modelle")
    yy = D.para(x, 1.9, note, w, 13, INK, weight="bold")
    for i, (nm, pv) in enumerate((("RF-DETR", p_d), (model, p_v))):
        bx = x + i * (w / 2 + 0.05)
        D.box(bx, yy + 0.25, w / 2 - 0.05, 1.25)
        D.text(bx + 0.2, yy + 0.4, nm, 11, INK2, weight="bold")
        wrong = nm in who
        D.text(bx + 0.2, yy + 0.72, "–" if pv is None else f"{pv:.2f}", 26, CRITICAL if wrong else GOOD, weight="bold")
        D.text(bx + 0.2, yy + 1.25, f"{'✗ ' if wrong else ''}{CLASS_DE.get(cls, cls)} {'erkannt' if wrong else 'nicht erkannt'}",
               9.5, CRITICAL if wrong else INK2)
    yy += 1.75
    lines = []
    for nm, a, b in (("RF-DETR", rec_d, rec_d2), (model, rec_v, rec_v2)):
        if a and b and a != b:
            lines.append(f"Bei Precision 100 % setzt diese eine Seite die Schwelle von {nm}: Recall {a[0]}/{a[1]} – "
                         f"ohne sie wären es {b[0]}/{b[1]}.")
    lines.append("Abhilfe: Seiten mit Handschrift ohne Unterschrift gezielt als Negativbeispiele ins Training; "
                 "bis dahin entscheidet bei mittlerem Score eine Person.")
    D.bullets(x, yy, lines, w, 11.5)
    D.save()
    return True


def _example_image(cfg, ex: dict) -> Image.Image | None:
    """Rebuilds exactly the image both models saw (masked page, labeled boxes of the class
    erased for a negative copy), so the drawn RF-DETR box matches the score in pages.csv."""
    from ..data.dataset import load_pages
    from .run import PagePrep
    from .vlm_compare import negative_variants

    p = next((p for p in load_pages(cfg)[0] if p.file_name == ex["file_name"] and p.path is not None), None)
    if p is None:
        return None
    im = PagePrep(cfg)(p)[1].convert("RGB")
    if ex["variante"] == "original":
        return im
    ncfg = cfg["vlm_compare"].get("negatives") or {}
    return next((v for name, _, v in negative_variants(p, im, [ex["klasse"]], ncfg) if name == ex["variante"]), None)
