"""Status presentation as PDF from the last evaluation (artifacts/report/results.json).

    make create_pdf        -> artifacts/report/praesentation.pdf

Slides: what the pipeline checks, its building blocks, data, results, the risk of wrongly
accepted pages with the two operating points (current / high accept threshold), open
issues and the recommendation. Rendered with matplotlib (vector PDF, no scans included,
so the file can be shared). Everything is read from results.json - rerun after `make eval`.
"""

from __future__ import annotations

import datetime as dt
import json
import textwrap

from ..config import artifacts

W, H = 13.333, 7.5          # 16:9 in inches
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
LINE = "#e2e1dc"
ACCENT = "#2a78d6"
TILE = "#f2f1ec"
GOOD = "#0ca30c"
CRITICAL = "#d03b3b"
WARN_TEXT = "#9a5b00"
FONT = "DejaVu Sans"

CLASS_DE = {"unterschrift": "Unterschrift", "stempel": "Stempel", "tour_nummer": "Tournummer",
            "cmr_count": "CMR-Zählung"}


# ------------------------------------------------------------------ helpers

def _v(r):
    return None if not r else r.get("value")


def pct(r, digits=0):
    v = _v(r) if isinstance(r, dict) else r
    return "–" if v is None else f"{v * 100:.{digits}f} %"


def frac(r):
    return "" if not r or r.get("value") is None else f"{r['k']} von {r['n']}"


def ci(r):
    c = (r or {}).get("ci95")
    return "" if not c else f"95 %-KI {c[0] * 100:.0f}–{c[1] * 100:.0f} %"


class Deck:
    def __init__(self, path, title, png_dir=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages

        plt.rcParams.update({"font.family": FONT, "pdf.fonttype": 42})
        self.plt = plt
        self.pdf = PdfPages(path, metadata={"Title": title, "Creator": "docval"})
        self.n = 0
        self.footer = ""
        self.png_dir = png_dir
        if png_dir:
            png_dir.mkdir(parents=True, exist_ok=True)
            for f in png_dir.glob("folie_*.png"):
                f.unlink()

    def slide(self, title, kicker=None):
        self.n += 1
        fig = self.plt.figure(figsize=(W, H))
        fig.patch.set_facecolor(SURFACE)
        self.fig = fig
        if kicker:
            self.text(0.6, 0.55, kicker.upper(), 11, ACCENT, weight="bold")
        if title:
            self.text(0.6, 0.95 if kicker else 0.75, title, 26, INK, weight="bold")
            self.fig.add_artist(self.plt.Line2D([0.6 / W, (W - 0.6) / W], [1 - 1.55 / H] * 2, color=LINE, lw=1))
        self.text(0.6, H - 0.35, self.footer, 9, MUTED)
        self.text(W - 0.6, H - 0.35, str(self.n), 9, MUTED, ha="right")
        return fig

    def save(self):
        self.pdf.savefig(self.fig, facecolor=SURFACE)
        if self.png_dir:
            self.fig.savefig(self.png_dir / f"folie_{self.n:02d}.png", dpi=110, facecolor=SURFACE)
        self.plt.close(self.fig)

    def close(self):
        self.pdf.close()

    # coordinates in inches from the top-left corner
    def text(self, x, y, s, size=14, color=INK, ha="left", va="top", weight="normal", style="normal"):
        return self.fig.text(x / W, 1 - y / H, s, fontsize=size, color=color, ha=ha, va=va,
                             fontweight=weight, fontstyle=style, family=FONT)

    def wrap(self, s, width_in, size):
        chars = max(10, int(width_in * 72 / (size * 0.56)))
        return textwrap.wrap(s, chars) or [""]

    def para(self, x, y, s, width_in, size=14, color=INK, gap=1.35, weight="normal"):
        lines = self.wrap(s, width_in, size)
        for i, ln in enumerate(lines):
            self.text(x, y + i * size * gap / 72, ln, size, color, weight=weight)
        return y + len(lines) * size * gap / 72

    def bullets(self, x, y, items, width_in, size=15, color=INK, gap_after=0.14):
        for it in items:
            sub = isinstance(it, tuple)
            s = it[0] if sub else it
            ind = 0.35 if sub else 0
            self.text(x + ind, y, "–" if sub else "•", size, ACCENT if not sub else INK2)
            y = self.para(x + ind + 0.3, y, s, width_in - ind - 0.3, size - (2 if sub else 0),
                          INK2 if sub else color) + gap_after
        return y

    def box(self, x, y, w, h, fc=TILE, ec=None, lw=0, radius=0.08):
        from matplotlib.patches import FancyBboxPatch
        p = FancyBboxPatch((x / W, 1 - (y + h) / H), w / W, h / H,
                           boxstyle=f"round,pad=0,rounding_size={radius / W}", transform=self.fig.transFigure,
                           fc=fc, ec=ec or fc, lw=lw)
        self.fig.add_artist(p)

    def image(self, x, y, w, h, im):
        """Image fitted into the box (x, y, w, h in inches), centered, thin border."""
        import numpy as np
        iw, ih = im.size
        s = min(w / iw, h / ih)
        dw, dh = iw * s, ih * s
        ox, oy = x + (w - dw) / 2, y + (h - dh) / 2
        ax = self.fig.add_axes([ox / W, 1 - (oy + dh) / H, dw / W, dh / H])
        ax.imshow(np.asarray(im), interpolation="lanczos")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(LINE)

    def arrow(self, x1, y1, x2, y2, color=MUTED):
        from matplotlib.patches import FancyArrowPatch
        self.fig.add_artist(FancyArrowPatch((x1 / W, 1 - y1 / H), (x2 / W, 1 - y2 / H), transform=self.fig.transFigure,
                                            arrowstyle="-|>", mutation_scale=14, color=color, lw=1.4))

    def table(self, x, y, widths, header, rows, size=12, row_h=0.42, colors=None, bold_first=True):
        """rows: list of lists of str (or (str, color) for a colored cell)."""
        tw = sum(widths)
        self.fig.add_artist(self.plt.Line2D([x / W, (x + tw) / W], [1 - (y + row_h) / H] * 2, color=INK2, lw=0.8))
        cx = x
        for w, hd in zip(widths, header):
            for i, ln in enumerate(self.wrap(hd, w - 0.1, size - 1)[:2]):
                self.text(cx + 0.05, y + 0.06 + i * (size - 1) * 1.25 / 72, ln, size - 1, INK2, weight="bold")
            cx += w
        yy = y + row_h + 0.08
        for r in rows:
            cx = x
            lines_max = 1
            for j, (w, cell) in enumerate(zip(widths, r)):
                col = INK
                if isinstance(cell, tuple):
                    cell, col = cell
                lines = self.wrap(str(cell), w - 0.12, size)
                lines_max = max(lines_max, len(lines))
                for i, ln in enumerate(lines):
                    self.text(cx + 0.05, yy + i * size * 1.3 / 72, ln, size, col,
                              weight="bold" if (j == 0 and bold_first) else "normal")
                cx += w
            h = max(row_h, lines_max * size * 1.3 / 72 + 0.14)
            yy += h
            self.fig.add_artist(self.plt.Line2D([x / W, (x + tw) / W], [1 - (yy - 0.06) / H] * 2, color=LINE, lw=0.6))
        return yy

    def tile(self, x, y, w, h, value, label, sub="", status=None):
        self.box(x, y, w, h)
        vcol = INK
        if status is not None:
            vcol = GOOD if status else CRITICAL
        self.text(x + 0.25, y + 0.22, label, 12, INK2, weight="bold")
        self.text(x + 0.25, y + 0.62, value, 30, INK if status is None else vcol, weight="bold")
        if status is not None:
            self.text(x + w - 0.25, y + 0.85, "✓ erfüllt" if status else "✗ verfehlt", 12, vcol, ha="right",
                      weight="bold")
        if sub:
            self.para(x + 0.25, y + h - 0.55, sub, w - 0.4, 10.5, INK2)


# ------------------------------------------------------------------ content

def acceptance(R, prefix):
    return next((c for c in R.get("acceptance", []) if c["metric"].startswith(prefix)), None)


def open_issues(R) -> list:
    from .report import plausibility

    out = []
    for c in R.get("acceptance", []):
        if not c["passed"]:
            v = "–" if c["value"] is None else f"{c['value'] * 100:.1f} %"
            out.append(f"{c['stage']}: {c['metric']} – {v} statt {c['cmp']} {c['threshold'] * 100:g} % (n = {c['n']})")
    for w in plausibility(R):
        out.append(w.replace("`", ""))
    pos = R.get("position", {})
    outside = pos.get("outside_zone") or []
    if outside:
        pages = sorted({o["file_name"].split("/")[0] + "/" + o["file_name"].split("/")[-1].split("_")[-1]
                        for o in outside if not o.get("review_zone")})
        if pages:
            out.append(f"Unterschrift/Stempel außerhalb jeder Soll-Zone auf {len(pages)} Seite(n) "
                       f"({', '.join(pages[:4])}) – fachlich klären: zulässiges anderes Formular?")
    fm = R.get("form_mask") or {}
    if fm.get("dropped_gt_boxes"):
        out.append(f"{fm['dropped_gt_boxes']} Label(s) lagen im maskierten Feld 22/23 – Maske auf diesen Seiten prüfen.")
    summ = (R.get("meta") or {}).get("split_summary") or {}
    unk = sum(v for s in ("train", "valid", "test") for t, v in (summ.get(s, {}).get("by_type") or {}).items()
              if t in ("?", "unbekannt", ""))
    if unk:
        out.append(f"{unk} Seiten ohne gültigen Dokumenttyp (\"?\" / \"unbekannt\") – fallen aus Regeln und Zonen.")
    cmr_n = (R.get("detector", {}).get("by_doc_type", {}).get("cmr", {}).get("unterschrift") or {}).get("n")
    if cmr_n:
        out.append(f"Kleine Datenbasis: {cmr_n} CMR-Unterschriften im Test – „0 Fehler“ heißt statistisch nur "
                   f"„selten“; belastbar wird es mit mehr Touren.")
    return out


def build(R, cfg, path, png_dir=None, log=print):
    meta = R["meta"]
    det = meta.get("detector", {})
    exports = (R.get("exports") or {}).get("exports") or []
    date = dt.date.today().strftime("%d.%m.%Y")
    D = Deck(path, "Validierung von Lieferpapieren – Stand", png_dir)
    D.footer = f"Dokumentvalidierung · Stand {date} · Test-Split {meta['n_pages']} Seiten · enthält Beispielseiten – nur intern"

    # 1 title
    D.slide("")
    D.text(0.9, 2.0, "STATUS", 13, ACCENT, weight="bold")
    D.text(0.9, 2.45, "Validierung von Lieferpapieren", 40, INK, weight="bold")
    D.para(0.9, 3.45, "Automatische Prüfung von CMR, Lieferschein und Loading List: Dokumenttyp, Unterschrift und "
                      "Stempel an der richtigen Stelle, Tournummer und CMR-Zählung lesen.", 10.5, 18, INK2)
    D.text(0.9, 5.2, f"Stand {date}", 14, INK)
    D.text(0.9, 5.6, f"{len(exports) or 1} Tour(en) · {sum(e['images'] for e in exports) if exports else '–'} Seiten · "
                     f"Detektor RF-DETR {det.get('size', '?')} · alles lokal, ohne Cloud", 13, INK2)
    D.save()

    # 2 pipeline
    D.slide("Was die Pipeline mit jeder Seite macht", "Aufbau")
    steps = [("Scan", "eine Seite\n(PNG/JPG)"), ("Dokumenttyp", "CMR, Lieferschein\noder Loading List"),
             ("Vordruck-Maske", "nur CMR: Felder\n22/23 ausblenden"), ("Objekte finden", "Unterschrift, Stempel,\nTournummer, CMR i/n"),
             ("Positionsprüfung", "steht alles im\nSollfeld?"), ("Lesen (OCR)", "Tournummer,\nCMR-Zählung")]
    bw, gap, y0 = 1.76, 0.26, 2.3
    for i, (t, sub) in enumerate(steps):
        x = 0.6 + i * (bw + gap)
        D.box(x, y0, bw, 1.55, fc=TILE)
        D.text(x + bw / 2, y0 + 0.28, f"{i + 1}", 12, ACCENT, ha="center", weight="bold")
        D.text(x + bw / 2, y0 + 0.62, t, 12.5, INK, ha="center", weight="bold")
        for k, ln in enumerate(sub.split("\n")):
            D.text(x + bw / 2, y0 + 0.98 + k * 0.24, ln, 10.5, INK2, ha="center")
        if i < len(steps) - 1:
            D.arrow(x + bw + 0.03, y0 + 0.78, x + bw + gap - 0.03, y0 + 0.78)
    D.arrow(W / 2, y0 + 1.65, W / 2, y0 + 2.15)
    labels = [("ok", "automatisch freigegeben", GOOD), ("an Person", "unsicher oder Feld 13", WARN_TEXT),
              ("fehlt / falsche Stelle", "Rückfrage nötig", CRITICAL)]
    for i, (t, sub, col) in enumerate(labels):
        x = W / 2 - (3 * 2.7 + 2 * 0.3) / 2 + i * 3.0
        D.box(x, y0 + 2.25, 2.7, 1.0, fc=TILE)
        D.text(x + 1.35, y0 + 2.45, t, 15, col, ha="center", weight="bold")
        D.text(x + 1.35, y0 + 2.83, sub, 11, INK2, ha="center")
    D.save()

    # 2a-d example page through every step
    if (cfg.get("presentation") or {}).get("examples", True):
        try:
            from .presentation_examples import example_slides
            example_slides(D, R, cfg, log)
        except Exception as e:  # examples are a bonus - the deck is built without them
            log(f"[praesentation] Beispielfolien übersprungen: {e}")
            D.plt.close("all")

    # 3 building blocks
    dta = R["doctype"]["accuracy"]
    fm = R.get("form_mask") or {}
    bdt = R["detector"].get("by_doc_type", {}).get("cmr", {})
    tour = acceptance(R, "Exact Match akzeptiert")
    cc = (R.get("ocr") or {}).get("cmr_count") or {}
    dq = R["position"].get("decision_quality") or {}
    D.slide("Die Bausteine", "Aufbau")
    rows = [
        ["Dokumenttyp", "erkennt CMR / Lieferschein / Loading List",
         "Schlüsselwörter im Seitenkopf (OCR) + Bildklassifikator (MobileNetV3)", f"{pct(dta)} richtig"],
        ["Vordruck-Maske", "blendet die vorgedruckten Unterschriften/Stempel in CMR-Feld 22 und 23 aus",
         "Linienerkennung (OpenCV), keine KI", f"Feldzeile auf {pct(fm.get('pages'))} gefunden"],
        ["Objekterkennung", "findet Unterschrift, Stempel, Tournummer, CMR-Zählung",
         f"RF-DETR {det.get('size', '')} (Apache-2.0), {det.get('resolution', '')} px, als ONNX",
         "Recall CMR: Unterschrift " + pct(bdt.get("unterschrift")) + ", Stempel " + pct(bdt.get("stempel"))],
        ["Positionsprüfung", "prüft, ob Unterschrift und Stempel im Sollfeld stehen; Feld 13 → Person",
         "Zonen aus den Trainingsdaten + Regeln in config.yaml",
         f"{dq.get('auto_richtig', 0)} von {dq.get('n', 0)} echten Seiten automatisch richtig"],
        ["Tournummer", "liest Tour/Datum/Werk, prüft das Format, korrigiert Verwechsler (O→0 …)",
         "PP-OCRv5 (Apache-2.0), Text-Erkennung + Formatregel", f"{pct(_v(tour) if tour else None)} exakt (angenommen)"],
        ["CMR-Zählung", "liest „CMR i/n“, prüft je Tour auf Vollständigkeit", "PP-OCR + Stapelprüfung",
         f"{pct(cc.get('parsed'))} lesbar"],
    ]
    D.table(0.6, 1.85, [2.1, 3.9, 3.9, 2.2], ["Baustein", "Aufgabe", "Technik", "Stand (Test)"], rows, size=12)
    D.save()

    # 4 tools & operation
    tm = R.get("timing") or {}
    path_ms = sum((tm.get(k) or {}).get("median_ms", 0) for k in
                  ("detektor", "vordruck_maske", "dokumenttyp_ocr", "dokumenttyp_klassifikator",
                   f"tour_ocr_{(R.get('ocr') or {}).get('primary', 'ppocrv5/det_rec').replace('/', '_')}"))
    D.slide("Werkzeuge und Betrieb", "Aufbau")
    y = D.bullets(0.6, 1.95, [
        "Läuft komplett lokal und offline – keine Cloud-Dienste, nur Modelle mit Apache-2.0/MIT/BSD-Lizenz.",
        "Entwicklungsumgebung als Container (CPU oder GPU); ein Befehl je Schritt: make split · train · export · eval.",
        f"Laufzeit ca. {path_ms / 1000:.1f} s pro Seite auf einer normalen CPU, ohne Grafikkarte.",
        "Jeder Lauf erzeugt einen Bericht mit Kennzahlen, 95 %-Konfidenzintervallen und Fehlergalerie.",
        "Label-Werkzeuge für die Fachabteilung:",
        ("Label-Editor im Browser (deutsch / polnisch): Boxen prüfen und korrigieren, Modell schlägt vor",),
        ("Label-Prüfung: zeigt, wo Modell und Labels voneinander abweichen",),
        ("Vorher/Nachher-Vergleich der Labels und Vergleich zweier Trainingsläufe",),
    ], 11.8, 15)
    D.save()

    # 5 data
    summ = meta.get("split_summary") or {}
    D.slide("Datenbasis", "Daten")
    if exports:
        rows = [[e["name"], str(e["images"]), e.get("tour_from_name") or "–"] for e in exports]
        D.table(0.6, 1.9, [2.3, 0.9, 2.9], ["Tour-Ordner", "Seiten", "Tournummer (aus Ordnername)"], rows, size=12)
    srows = []
    for s in ("train", "valid", "test"):
        d = summ.get(s) or {}
        bt = d.get("by_type") or {}
        srows.append([s, str(d.get("pages", 0)), str(bt.get("cmr", 0)), str(bt.get("lieferschein", 0)),
                      str(bt.get("loading_list", 0))])
    D.table(7.2, 1.9, [1.0, 0.9, 0.8, 1.35, 1.3], ["Split", "Seiten", "CMR", "Lieferschein", "Loading List"], srows,
            size=12)
    D.para(7.2, 4.0, "Getrennt nach Sendungen: Seiten einer Sendung liegen nie gleichzeitig in Training und Test. "
                     "Gemessen wird ausschließlich auf dem Test-Split, den das Modell nie gesehen hat.", 5.5, 12.5, INK2)
    D.para(0.6, 5.6, "Labels wurden mit dem Editor nach einer einheitlichen Konvention überarbeitet (Boxen eng um den "
                     "Inhalt, nichts doppelt, Vordruck in Feld 22/23 nicht labeln).", 12, 13, INK2)
    D.save()

    # 6 results tiles
    D.slide("Ergebnisse auf dem Test-Split", "Ergebnisse")
    acc = {c["metric"]: c for c in R.get("acceptance", [])}
    a_dt = acceptance(R, "Accuracy")
    a_u = acceptance(R, "Recall@IoU0.5 unterschrift")
    a_s = acceptance(R, "Recall@IoU0.5 stempel")
    a_t = acceptance(R, "Recall@IoU0.5 tour_nummer")
    tiles = [
        (pct(dta), "Dokumenttyp richtig", f"{frac(dta)} Seiten · {ci(dta)}", a_dt["passed"] if a_dt else None),
        (pct(_v(tour) if tour else None), "Tournummer exakt gelesen",
         f"angenommene Lesungen · Ziel ≥ {tour['threshold'] * 100:g} %" if tour else "", tour["passed"] if tour else None),
        (pct(cc.get("parsed")), "CMR-Zählung lesbar", frac(cc.get("parsed")), None),
        (pct(bdt.get("unterschrift")), "Unterschrift gefunden (CMR)",
         f"{frac(bdt.get('unterschrift'))} · Ziel ≥ {a_u['threshold'] * 100:g} %" if a_u else "", a_u["passed"] if a_u else None),
        (pct(bdt.get("stempel")), "Stempel gefunden (CMR)",
         f"{frac(bdt.get('stempel'))} · Ziel ≥ {a_s['threshold'] * 100:g} %" if a_s else "", a_s["passed"] if a_s else None),
        (pct(_v(a_t) if a_t else None), "Tournummer gefunden",
         f"n = {a_t['n']} · Ziel ≥ {a_t['threshold'] * 100:g} %" if a_t else "", a_t["passed"] if a_t else None),
    ]
    tw, th = 3.85, 1.95
    for i, (v, lab, sub, st) in enumerate(tiles):
        D.tile(0.6 + (i % 3) * (tw + 0.25), 1.9 + (i // 3) * (th + 0.25), tw, th, v, lab, sub, st)
    D.para(0.6, 6.45, "„Gefunden“ zählt nur bei ausreichender Überlappung mit dem Label (IoU ≥ 0,5); eine anders "
                      "gezogene Box gilt dort als Fehler, obwohl das Objekt erkannt wurde.", 12, 11.5, INK2)
    D.save()

    # 7 decision quality + risk
    ops = R.get("position_operating_points") or {}
    D.slide("Was beim Sachbearbeiter ankommt", "Ergebnisse")
    real = dq
    D.para(0.6, 1.95, f"Echte CMR-Seiten im Test (n = {real.get('n', 0)}), aktuelle Schwelle:", 12, 15, INK)
    cells = [(str(real.get("auto_richtig", 0)), "automatisch richtig", INK), (str(real.get("person", 0)), "an Person", INK),
             (str(real.get("auto_falsch_fehler_uebersehen", 0)), "Fehler übersehen", None),
             (str(real.get("auto_falsch_fehlalarm", 0)), "Fehlalarm", INK)]
    for i, (v, lab, col) in enumerate(cells):
        x = 0.6 + i * 3.08
        D.box(x, 2.5, 2.85, 1.45)
        good = v == "0"
        D.text(x + 0.25, 2.68, lab, 12, INK2, weight="bold")
        D.text(x + 0.25, 3.05, v, 32, col or (GOOD if good else CRITICAL), weight="bold")
        if col is None:
            D.text(x + 2.6, 3.3, "✓ keiner" if good else "✗ Risiko", 12, GOOD if good else CRITICAL, ha="right",
                   weight="bold")
    syn = (ops.get("aktuell") or {}).get("synthetic") or {}
    pos = R["position"]
    D.para(0.6, 4.35, "Härtetest: Bei jeder korrekten Testseite wird die Unterschrift bzw. der Stempel künstlich "
                      "entfernt oder verschoben. Die Pipeline muss das merken.", 12, 14, INK)
    n_ok = syn.get("faelschlich_ok")
    D.text(0.6, 5.25, f"{'✗ ' if n_ok else '✓ '}{n_ok if n_ok is not None else '–'} von "
                      f"{syn.get('n', len(pos.get('synthetic', [])))}", 30, CRITICAL if n_ok else GOOD, weight="bold")
    D.para(3.6, 5.3, ("manipulierten Seiten wurden trotzdem als „ok“ freigegeben – das ist der Fehler, der nicht "
                      "passieren darf. Ursache: einzelne Fehlerkennungen des Modells mit mittlerem Score in der Zone.")
           if n_ok else "manipulierten Seiten wurden fälschlich als „ok“ freigegeben.", 9.1, 13.5, INK2)
    D.save()

    # 7a hard test example
    if (cfg.get("presentation") or {}).get("examples", True):
        try:
            from .presentation_examples import hard_test_slide
            hard_test_slide(D, R, cfg, log)
        except Exception as e:
            log(f"[praesentation] Härtetest-Beispiel übersprungen: {e}")
            D.plt.close("all")

    # 8 operating points
    D.slide("Entscheidung: mit welcher Schwelle starten?", "Empfehlung")
    if len(ops) >= 2:
        names = {"aktuell": "Schwelle wie heute (auf Recall optimiert)", "hoch": "Hohe Schwelle (Vorschlag)"}
        for i, key in enumerate(("aktuell", "hoch")):
            o = ops[key]
            x = 0.6 + i * 6.2
            D.box(x, 1.95, 5.9, 4.3, fc=TILE, ec=ACCENT if key == "hoch" else TILE, lw=2 if key == "hoch" else 0)
            D.text(x + 0.3, 2.15, names[key], 15, INK, weight="bold")
            th = ", ".join(f"{CLASS_DE.get(c, c)} ≥ {o['accept'][c]:g}" for c in ("unterschrift", "stempel")
                           if c in o["accept"])
            D.text(x + 0.3, 2.55, f"automatisch ok ab Score: {th}", 11, INK2)
            r, s = o["real"], o["synthetic"]
            fa = s["faelschlich_ok"]
            D.text(x + 0.3, 3.05, "Manipulierte Seiten fälschlich „ok“", 12, INK2, weight="bold")
            D.text(x + 0.3, 3.4, f"{fa} von {s['n']}", 30, CRITICAL if fa else GOOD, weight="bold")
            D.text(x + 3.2, 3.5, "✗ Risiko" if fa else "✓ keine", 13, CRITICAL if fa else GOOD, weight="bold")
            D.text(x + 0.3, 4.35, "Echte Seiten zur Prüfung an Person", 12, INK2, weight="bold")
            D.text(x + 0.3, 4.7, f"{r['person']} von {r['n']}", 30, INK, weight="bold")
            D.text(x + 0.3, 5.55, f"automatisch richtig {r['auto_richtig']} · Fehler übersehen {r['fehler_uebersehen']}"
                                  f" · Fehlalarm {r['fehlalarm']}", 11, INK2)
        D.para(0.6, 6.45, "Zwischen Unsicher- und Annahme-Schwelle entscheidet eine Person. Die hohe Schwelle liegt "
                          "knapp über der höchsten echten Fehlerkennung auf dem Validierungs-Split.", 12, 11.5, INK2)
    else:
        D.para(0.6, 2.0, "Für den Vergleich der Betriebspunkte bitte `make eval` mit score_threshold: auto ausführen.",
               12, 15, INK2)
    D.save()

    # 8a alternative approach: vision-language model (make vlm-compare)
    try:
        from .presentation_vlm import vlm_slides
        vlm_slides(D, R, cfg, log)
    except Exception as e:  # optional prototype - the deck is built without it
        log(f"[praesentation] Vergleichsfolien übersprungen: {e}")
        D.plt.close("all")

    # 9 open issues
    D.slide("Offene Punkte", "Probleme")
    issues = open_issues(R)
    D.bullets(0.6, 1.95, issues[:9] or ["Keine offenen Punkte aus diesem Lauf."], 12, 13.5)
    D.save()

    # 10 recommendation
    D.slide("Empfehlung und nächste Schritte", "Empfehlung")
    hoch = ops.get("hoch")
    share = pct(hoch["person_share"]) if hoch else "einem Teil"
    D.bullets(0.6, 1.95, [
        "Start mit der hohen Schwelle: „ok“ nur, wenn das Modell sehr sicher ist – im Zweifel entscheidet eine Person.",
        (f"Im Test gingen damit {share} der echten CMR-Seiten an eine Person; falsch freigegeben wurde keine "
         "manipulierte Seite." if hoch and not hoch["synthetic"]["faelschlich_ok"] else
         f"Im Test gingen damit {share} der echten CMR-Seiten an eine Person.",),
        "Die Entscheidungen der Prüfer werden zu neuen Labels – das Modell wird mit jeder Tour besser.",
        "Schwelle schrittweise senken, sobald ein größerer Test-Split weiterhin null falsche Freigaben zeigt.",
        "Fachlich klären: andere Formulare (Unterschrift oben) und Feld 13 als zulässige Stelle.",
        "Weitere Touren mit dem Label-Editor erfassen – größter Hebel für Recall und belastbare Zahlen.",
        "Pilot: parallel zur manuellen Prüfung laufen lassen und Abweichungen auswerten.",
    ], 12, 15)
    D.save()

    # 11 appendix: criteria
    D.slide("Anhang: Akzeptanzkriterien dieses Laufs", "Anhang")
    rows = []
    for c in R.get("acceptance", []):
        v = "–" if c["value"] is None else f"{c['value'] * 100:.1f} %"
        rows.append([c["stage"], c["metric"], v, f"{c['cmp']} {c['threshold'] * 100:g} %", str(c["n"]),
                     ci({"ci95": c.get("ci95")}).replace("95 %-KI ", ""),
                     ("✓ erfüllt", GOOD) if c["passed"] else ("✗ verfehlt", CRITICAL)])
    D.table(0.6, 1.85, [1.6, 4.6, 1.1, 1.1, 0.7, 1.5, 1.4], ["Stufe", "Metrik", "Wert", "Ziel", "n", "95 %-KI", ""],
            rows, size=11.5)
    D.save()
    D.close()
    return D.n


def run_presentation(cfg, log) -> int:
    rp = artifacts(cfg, "report", "results.json")
    if not rp.is_file():
        log("FEHLER: keine results.json - zuerst `make eval`")
        return 2
    R = json.loads(rp.read_text(encoding="utf-8"))
    out = artifacts(cfg, "report", "praesentation.pdf")
    n = build(R, cfg, out, artifacts(cfg, "report", "praesentation"), log)
    log(f"[praesentation] {n} Folien -> {out} (einzeln als PNG in {out.parent / 'praesentation'})")
    return 0
