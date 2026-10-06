"""Example slides for the status presentation: one real CMR test page through every step
(doc type, form mask, detection + position check, reading) and one example of the hard
test (signature removed). Mask, detector and position check are run live on that page
with the thresholds and zones of the last evaluation; doc type and OCR results come from
results.json.

Config `presentation.example_page` (part of a file name) picks the page; otherwise a CMR
page that was decided correctly and whose tour number was read correctly is chosen.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import artifacts

# categorical slots 1-4 of the validated reference palette, in fixed order
CLASS_COLORS = {"unterschrift": "#2a78d6", "stempel": "#eb6834", "tour_nummer": "#1baf7a", "cmr_count": "#eda100"}
ZONE = "#4a3aa7"


def _font(size):
    try:
        import matplotlib
        return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans-Bold.ttf"), size)
    except Exception:
        return ImageFont.load_default()


def draw_boxes(im: Image.Image, dets: list, names: dict, zones: list = (), lw=None) -> Image.Image:
    im = im.convert("RGB").copy()
    W, H = im.size
    d = ImageDraw.Draw(im)
    lw = lw or max(3, int(max(W, H) / 350))
    f = _font(max(14, int(max(W, H) / 70)))
    for z in zones:  # dashed zone outline
        x1, y1, x2, y2 = z[0] * W, z[1] * H, z[2] * W, z[3] * H
        step = lw * 6
        for x in range(int(x1), int(x2), step * 2):
            d.line([(x, y1), (min(x + step, x2), y1)], fill=ZONE, width=lw)
            d.line([(x, y2), (min(x + step, x2), y2)], fill=ZONE, width=lw)
        for y in range(int(y1), int(y2), step * 2):
            d.line([(x1, y), (x1, min(y + step, y2))], fill=ZONE, width=lw)
            d.line([(x2, y), (x2, min(y + step, y2))], fill=ZONE, width=lw)
    for det in dets:
        c = CLASS_COLORS.get(det["cls"], "#52514e")
        b = det["box"]
        x1, y1, x2, y2 = b[0] * W, b[1] * H, b[2] * W, b[3] * H
        d.rectangle([x1, y1, x2, y2], outline=c, width=lw)
        label = names.get(det["cls"], det["cls"]) + (f" {det['score']:.2f}" if det.get("score") is not None else "")
        tb = d.textbbox((0, 0), label, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = y1 - th - 2 * lw if y1 - th - 2 * lw > 0 else y2 + lw
        d.rectangle([x1, ty, x1 + tw + 2 * lw, ty + th + 2 * lw], fill=c)
        d.text((x1 + lw, ty + lw - tb[1]), label, fill="white", font=f)
    return im


def shrink(im: Image.Image, max_side=1500) -> Image.Image:
    s = max_side / max(im.size)
    return im if s >= 1 else im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def crop_norm(im, box):
    W, H = im.size
    return im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))


def pick_page(R, pages, cfg):
    want = (cfg.get("presentation") or {}).get("example_page")
    by_fn = {p.file_name: p for p in pages if p.path is not None}
    rows = (R.get("position") or {}).get("rows") or []
    prim = (R.get("ocr") or {}).get("primary")
    ocr = {r["file_name"]: r for r in (R.get("ocr") or {}).get("rows", [])}
    cc = {r["file_name"]: r for r in ((R.get("ocr") or {}).get("cmr_count") or {}).get("rows", [])}
    not_found = set((R.get("form_mask") or {}).get("not_found") or [])
    if want:
        hit = [by_fn[r["file_name"]] for r in rows if want in r["file_name"] and r["file_name"] in by_fn]
        if hit:
            return hit[0]
    cands = []
    for r in rows:
        fn = r["file_name"]
        if fn not in by_fn or r["doc_type"] != "cmr" or fn in not_found:
            continue
        score = 4 * (r["status"] == "ok" and r["gt_status"] == "ok")
        o = (ocr.get(fn) or {}).get("gt_box", {}).get(prim) or {}
        score += 2 * bool(o.get("accepted") and o.get("text") == ocr[fn].get("gt"))
        score += bool((cc.get(fn) or {}).get("parsed"))
        cands.append((-score, fn))
    return by_fn[sorted(cands)[0][1]] if cands else None


def example_slides(D, R, cfg, log=print):
    """Adds the example slides to the deck D. Returns False if no example could be built."""
    from ..data.dataset import load_pages
    from ..detect.onnx_detector import OnnxDetector
    from ..zones import check_page
    from .presentation import CLASS_DE, CRITICAL, GOOD, INK, INK2, WARN_TEXT
    from .run import PagePrep

    det_dir = artifacts(cfg, "detector")
    if not (det_dir / "detector.onnx").is_file():
        log("[praesentation] kein Detektor - Beispielfolien entfallen")
        return False
    pages, _ = load_pages(cfg)
    p = pick_page(R, pages, cfg)
    if p is None:
        log("[praesentation] keine CMR-Testseite gefunden - Beispielfolien entfallen")
        return False
    names = CLASS_DE
    detector = OnnxDetector(det_dir, min_score=0.05)
    prep = PagePrep(cfg)
    orig, masked = prep(p)
    orig, masked = orig.convert("RGB"), masked.convert("RGB")
    minfo = prep.info.get(p.file_name) or {}
    dets = detector(masked)
    thr = R["detector"]["thresholds"]
    factor = cfg["detector"].get("score_uncertain_factor", 0.6)
    unc = {c: t * factor for c, t in thr.items()}
    zones = R["position"]["zones"]
    rules = cfg["zones"]["rules"]
    res = check_page(p.doc_type, dets, zones, rules, cfg["zones"]["min_overlap"], thr, unc)
    shown = []
    for c in CLASS_COLORS:  # per class the two best detections above the uncertain threshold
        shown += sorted((d for d in dets if d["cls"] == c and d["score"] >= unc.get(c, 0.3)),
                        key=lambda d: -d["score"])[:2]
    short = "/".join([p.file_name.split("/")[0], Path(p.file_name).name]) if "/" in p.file_name else p.file_name
    status_txt = {"ok": ("ok – automatisch freigegeben", GOOD), "unsicher": ("an Person", WARN_TEXT)}
    log(f"[praesentation] Beispielseite: {p.file_name}")

    # A: doc type
    dtr = next((r for r in R["doctype"]["rows"] if r["file_name"] == p.file_name), {})
    hf = cfg["doctype"]["header_fraction"]
    D.slide("Beispiel: eine CMR-Seite – Schritt 2 Dokumenttyp", "Beispiel")
    page_img = draw_boxes(orig, [], names)
    dr = ImageDraw.Draw(page_img)
    lw = max(4, int(max(page_img.size) / 250))
    dr.rectangle([lw, lw, page_img.width - lw, int(page_img.height * hf)], outline="#2a78d6", width=lw)
    D.image(0.6, 1.85, 3.9, 5.2, shrink(page_img))
    y = D.para(5.0, 1.95, f"Seite {short} (Test-Split). Gelesen wird nur der Seitenkopf (oberste {hf:.0%}, "
                          "blau umrandet):", 7.6, 14, INK)
    if dtr.get("header_text"):
        y = D.para(5.2, y + 0.1, "„" + dtr["header_text"][:170].strip() + " …“", 7.3, 12, INK2) + 0.1
    y = D.bullets(5.0, y + 0.1, [
        f"Schlüsselwort im Text: {dtr.get('keyword') or 'keins'}",
        f"Bildklassifikator: {dtr.get('classifier') or '–'}"
        + (f" (Sicherheit {dtr['classifier_conf']:.2f})" if dtr.get("classifier_conf") is not None else ""),
        "Stimmen beide überein, gilt der Typ; widersprechen sie sich, geht die Seite an eine Person.",
    ], 7.6, 14)
    D.text(5.0, y + 0.25, f"→ Dokumenttyp: {(dtr.get('pred') or p.doc_type or '').upper()}", 22, INK, weight="bold")
    D.save()

    # B: form mask
    if minfo.get("found"):
        cells = minfo["cells"]
        top = max(0.0, min(c[1] for c in cells) - 0.04)
        region = [0.0, top, 1.0, min(1.0, max(c[3] for c in cells) + 0.02)]
        before = draw_boxes(orig, [], names)
        bd = ImageDraw.Draw(before)
        W, H = before.size
        lwm = max(4, int(W / 300))
        for i, c in enumerate(cells):
            col = "#d03b3b" if i in (cfg["form_mask"].get("mask_fields") or [0, 1]) else "#0ca30c"
            bd.rectangle([c[0] * W, c[1] * H, c[2] * W, c[3] * H], outline=col, width=lwm)
        D.slide("Schritt 3: Vordruck-Maske – vorher / nachher", "Beispiel")
        D.para(0.6, 1.9, "Auf jedem CMR sind in Feld 22 und 23 Unterschrift und Stempel bereits vorgedruckt. Das "
                         "Modell würde sie als echte Unterschrift zählen. Die Feldzeile wird an den gedruckten "
                         "Linien erkannt, Feld 22 und 23 werden weiß überdeckt – nur Feld 24 bleibt.", 12, 13.5, INK2)
        a, b = shrink(crop_norm(before, region), 1600), shrink(crop_norm(masked, region), 1600)
        D.image(0.6, 3.0, 5.95, 3.6, a)
        D.image(6.78, 3.0, 5.95, 3.6, b)
        D.text(0.6, 6.7, "vorher: rot = wird ausgeblendet (22, 23), grün = bleibt (24)", 11.5, INK2)
        D.text(6.78, 6.7, "nachher: das sieht das Modell", 11.5, INK2)
        D.save()

    # C: detection + position
    rule_cls = (rules.get(p.doc_type) or {}).get("require") or []
    zone_boxes = [zones[p.doc_type][c]["box"] for c in rule_cls if zones.get(p.doc_type, {}).get(c)]
    D.slide("Schritt 4–5: Objekte finden und Position prüfen", "Beispiel")
    D.image(0.6, 1.85, 3.9, 5.2, shrink(draw_boxes(masked, shown, names, zone_boxes)))
    y = D.para(5.0, 1.95, "Das Modell markiert jedes gefundene Objekt mit einem Score (0–1). Violett gestrichelt: "
                          "die Soll-Zone für Unterschrift und Stempel auf dem CMR.", 7.6, 13.5, INK2) + 0.15
    rows = []
    for d in sorted(shown, key=lambda d: -d["score"]):
        t = thr.get(d["cls"], 0.5)
        verdict = ("sicher", GOOD) if d["score"] >= t else ("unsicher → Person", WARN_TEXT)
        rows.append([names.get(d["cls"], d["cls"]), f"{d['score']:.2f}", f"≥ {t:g}", verdict])
    y = D.table(5.0, y, [2.3, 1.0, 1.2, 2.6], ["Objekt", "Score", "Annahme ab", "Bewertung"], rows[:6], size=12,
                row_h=0.36)
    y += 0.2
    for det in res.get("details", [])[:3]:
        ok = det["status"] == "ok"
        y = D.para(5.0, y, ("✓ " if ok else "✗ ") + det["reason"], 7.6, 12.5, GOOD if ok else CRITICAL)
    label, col = status_txt.get(res["status"], (res["status"], CRITICAL))
    D.text(5.0, y + 0.2, f"→ Ergebnis: {label}", 20, col, weight="bold")
    D.save()

    # D: reading
    def where(cls):
        """Model box if it sits on the label, else the label box (what the OCR evaluation reads)."""
        g = [b.norm(p.width, p.height) for b in p.boxes_of(cls)]
        best = max((d for d in dets if d["cls"] == cls and d["score"] >= thr.get(cls, 0.5)),
                   key=lambda d: d["score"], default=None)
        if best and (not g or max(iou(best["box"], b) for b in g) >= 0.5):
            return best
        return {"box": g[0]} if g else None

    from ..detect.onnx_detector import iou
    tour_det, cc_det = where("tour_nummer"), where("cmr_count")
    orow = next((r for r in R["ocr"]["rows"] if r["file_name"] == p.file_name), None)
    ccrow = next((r for r in ((R["ocr"].get("cmr_count") or {}).get("rows") or []) if r["file_name"] == p.file_name),
                 None)
    if tour_det or cc_det:
        prim = R["ocr"]["primary"]
        D.slide("Schritt 6: Tournummer und CMR-Zählung lesen", "Beispiel")
        y = 1.95
        if tour_det:
            b = tour_det["box"]
            pad = [max(0, b[0] - 0.02), max(0, b[1] - 0.012), min(1, b[2] + 0.02), min(1, b[3] + 0.012)]
            D.image(0.6, y, 6.0, 1.5, shrink(crop_norm(orig, pad), 1400))
            o = ((orow or {}).get("pred_box") or {}).get(prim) or ((orow or {}).get("gt_box") or {}).get(prim) or {}
            D.text(7.0, y + 0.05, "Tournummer gelesen", 12, INK2, weight="bold")
            D.text(7.0, y + 0.4, o.get("text") or "–", 24, INK, weight="bold")
            ok = bool(o.get("accepted")) and o.get("text") == (orow or {}).get("gt")
            D.text(7.0, y + 0.95, ("✓ Format Tour/Datum/Werk, Sicherheit " if o.get("accepted") else "✗ ")
                   + (f"{o.get('score', 0):.2f}" if o else "") + (" · stimmt mit Ordner überein" if ok else ""),
                   12, GOOD if ok else CRITICAL)
            y += 2.1
        if cc_det:
            b = cc_det["box"]
            pad = [max(0, b[0] - 0.03), max(0, b[1] - 0.012), min(1, b[2] + 0.03), min(1, b[3] + 0.012)]
            D.image(0.6, y, 6.0, 1.3, shrink(crop_norm(orig, pad), 1400))
            parsed = (ccrow or {}).get("parsed")
            D.text(7.0, y + 0.05, "CMR-Zählung gelesen", 12, INK2, weight="bold")
            D.text(7.0, y + 0.4, f"{parsed[0]} von {parsed[1]}" if parsed else ((ccrow or {}).get("text") or "–"), 24,
                   INK, weight="bold")
            D.text(7.0, y + 0.95, "Je Tour wird geprüft, ob jede Nummer 1 … n genau einmal vorkommt.", 12, INK2)
        D.para(0.6, 6.45, "Gelesen wird lokal mit PP-OCR. Ein Format-Check (Tour/Datum/Werk) und eine Korrektur "
                          "typischer Verwechsler (O→0, l→1) fangen Lesefehler ab; unsichere Lesungen gehen an eine Person.",
               12, 11.5, INK2)
        D.save()
    return True


def hard_test_slide(D, R, cfg, log=print):
    """One synthetic negative: signature removed -> what did the pipeline say?"""
    from ..data.dataset import load_pages
    from ..detect.onnx_detector import OnnxDetector
    from .presentation import CLASS_DE, CRITICAL, GOOD, INK, INK2

    syn = (R.get("position") or {}).get("synthetic") or []
    syn = [s for s in syn if Path(s.get("image", "")).is_file() and "unterschrift" in s["kind"]]
    if not syn or not (artifacts(cfg, "detector") / "detector.onnx").is_file():
        return False
    s = next((x for x in syn if x["status"] == "ok"), None) or next((x for x in syn if x["caught"]), syn[0])
    pages = {p.file_name: p for p in load_pages(cfg)[0]}
    p = pages.get(s["file_name"])
    if p is None or p.path is None:
        return False
    from .run import PagePrep
    _, masked = PagePrep(cfg)(p)
    manip = Image.open(s["image"]).convert("RGB")
    det = OnnxDetector(artifacts(cfg, "detector"), min_score=0.05)
    thr = R["detector"]["thresholds"]
    factor = cfg["detector"].get("score_uncertain_factor", 0.6)
    keep = lambda ds: [d for d in ds if d["cls"] in ("unterschrift", "stempel") and d["score"] >= thr.get(d["cls"], .5) * factor]  # noqa: E731
    region = [0.0, 0.55, 1.0, 1.0]
    a = shrink(crop_norm(draw_boxes(masked.convert("RGB"), keep(det(masked)), CLASS_DE), region), 1600)
    b = shrink(crop_norm(draw_boxes(manip, keep(det(manip)), CLASS_DE), region), 1600)
    wrong = s["status"] == "ok"
    D.slide("Beispiel Härtetest: Unterschrift entfernt", "Risiko")
    D.para(0.6, 1.9, "Aus einer korrekt unterschriebenen Testseite wird die Unterschrift künstlich entfernt "
                     "(bzw. verschoben). Richtig wäre: „fehlt“.", 12, 13.5, INK2)
    D.image(0.6, 2.65, 5.95, 3.3, a)
    D.image(6.78, 2.65, 5.95, 3.3, b)
    D.text(0.6, 6.1, "Original", 12, INK2, weight="bold")
    D.text(6.78, 6.1, f"manipuliert ({s['kind']})", 12, INK2, weight="bold")
    D.para(6.78, 6.55, ("✗ Pipeline sagt „ok“ – " if wrong else "✓ Pipeline sagt „" + s["status"] + "“ – ")
           + s["reason"], 5.95, 12, CRITICAL if wrong else GOOD, weight="bold")
    D.save()
    return True
