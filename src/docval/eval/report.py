"""German evaluation report (Markdown + HTML) with error gallery."""

from __future__ import annotations

import html
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import artifacts
from ..zones.synthetic import to_rgb

COLORS = {"gt": (0, 160, 0), "pred": (220, 0, 0), "zone": (0, 90, 255)}


def pct(v, digits=1):
    return "-" if v is None else f"{v * 100:.{digits}f} %"


def fr(r, digits=1):
    """ratio dict -> '95.0 % (19/20, KI 75-99 %)'."""
    if not r or r.get("value") is None:
        return f"- (n={r['n'] if r else 0})"
    ci = r.get("ci95")
    c = f", 95%-KI {ci[0] * 100:.0f}–{ci[1] * 100:.0f} %" if ci else ""
    return f"{pct(r['value'], digits)} ({r['k']}/{r['n']}{c})"


def num(v, d=3):
    return "-" if v is None else f"{v:.{d}f}"


# ------------------------------------------------------------------ gallery images

def draw_item(item: dict, out: Path, max_side: int = 900) -> str | None:
    try:
        im = to_rgb(Image.open(item["path"]))
    except Exception:
        return None
    W, H = im.size
    if "crop_box" in item:  # OCR: show the padded crop, enlarged
        x1, y1, x2, y2 = item["crop_box"]
        px, py = (x2 - x1) * 0.4, (y2 - y1) * 1.0
        im = im.crop((max(0, int(x1 - px)), max(0, int(y1 - py)), min(W, int(x2 + px)), min(H, int(y2 + py))))
        s = min(4.0, 700 / max(1, im.width))
        im = im.resize((int(im.width * s), int(im.height * s)))
    else:
        d = ImageDraw.Draw(im)
        for z in (item.get("zones") or {}).values():
            b = z["box"]
            d.rectangle([b[0] * W, b[1] * H, b[2] * W, b[3] * H], outline=COLORS["zone"], width=3)
        if item.get("header_fraction"):
            d.rectangle([0, 0, W - 1, item["header_fraction"] * H], outline=COLORS["zone"], width=4)
        for kind in ("gt", "pred"):
            for b in item.get(kind, []):
                bb = b["box"]
                d.rectangle([bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H], outline=COLORS[kind], width=4)
                label = b["cls"] + ("" if kind == "gt" else f" {b['score']:.2f}")
                d.text((bb[0] * W + 4, bb[1] * H + 2 if kind == "gt" else bb[3] * H - 14), label, fill=COLORS[kind])
        s = max_side / max(W, H)
        im = im.resize((int(W * s), int(H * s)))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=82)
    return out.name


# ------------------------------------------------------------------ conclusion

def conclusion(R: dict) -> list[str]:
    L = []
    crit = R["acceptance"]
    passed = [c for c in crit if c["passed"]]
    failed = [c for c in crit if not c["passed"]]
    n = R["meta"]["n_pages"]
    if passed:
        L.append("**Was funktioniert:** " + "; ".join(
            f"{c['stage']} – {c['metric']} ({pct(c['value'])})" for c in passed if c["value"] is not None))
    if failed:
        L.append("**Verfehlt:** " + "; ".join(
            f"{c['stage']} – {c['metric']} ({pct(c['value'])} statt {c['cmp']} {pct(c['threshold'], 0)}"
            f"{', ' + c['note'] if c['note'] else ''})" for c in failed))
    wide = [c for c in crit if c["ci95"] and c["ci95"][1] - c["ci95"][0] > 0.2]
    if n < 60 or wide:
        L.append(f"**Größter Hebel: mehr Daten.** Der Test-Split hat nur {n} Seiten; "
                 f"{len(wide)} von {len(crit)} Kriterien haben ein 95%-Konfidenzintervall breiter als 20 Prozentpunkte. "
                 "Eine einzelne Fehlentscheidung verschiebt die Metriken um mehrere Prozentpunkte – "
                 "Schwellen wie 98–99 % sind so statistisch nicht nachweisbar. Mehrere Scan-Stapel von "
                 "verschiedenen Tagen (v. a. Loading Lists) würden Aussagekraft und Split-Trennung verbessern.")
    det = R["detector"]["per_class"]
    weak = [c for c, v in det.items() if v["recall"]["value"] is not None and v["recall"]["value"] < 0.9]
    if weak:
        L.append(f"**Detektor:** schwach bei {', '.join(weak)} – zuerst Schwelle in der PR-Tabelle prüfen "
                 "(niedrigere Schwelle kostet Präzision), dann mehr Trainingsbeispiele oder eine größere "
                 "Modellgröße (`detector.size: small`).")
    o = R["ocr"]
    if o["n_with_gt"] == 0 and o["n_boxes"]:
        L.append("**Tournummer:** noch keine Ground-Truth – `labels/tour_numbers.csv` über "
                 "`labels/tour_review.html` ausfüllen, sonst ist die OCR-Genauigkeit nicht messbar.")
    pos = R["position"]
    if pos["gt_not_ok"]:
        L.append(f"**Positionsprüfung:** {len(pos['gt_not_ok'])} Seiten erfüllen schon laut GT die Regel nicht "
                 "(Liste im Abschnitt 3) – Zonen (`zones.overrides`) oder Regeln (`zones.rules`) prüfen.")
    for t, st in (pos.get("field_stats") or {}).items():
        if st["pages"] and st["pages_all_fields"] == 0:
            L.append(f"**Feld-Regel {t}:** keine einzige {t}-Seite hat laut Ground Truth alle Felder unterschrieben – "
                     "entweder sind die Seiten wirklich unvollständig (dann sind es echte Negative), oder die "
                     "Feld-Boxen passen nicht zum Formular. Ohne vollständige Seiten gibt es keine Fehlalarm-Messung "
                     "und keine synthetischen Negative für diesen Typ.")
    if not L:
        L.append("Alle Kriterien erfüllt.")
    return L


# ------------------------------------------------------------------ markdown

def to_markdown(cfg: dict, R: dict, gallery_files: dict) -> str:
    m = R["meta"]
    L = ["# Evaluationsbericht Dokumentvalidierung", ""]
    ok = all(c["passed"] for c in R["acceptance"])
    L.append(f"**Gesamtergebnis: {'BESTANDEN' if ok else 'NICHT BESTANDEN'}** · Split `{m['split']}` mit "
             f"{m['n_pages']} Seiten · Detektor RF-DETR {m['detector']['size']} ({m['detector']['resolution']} px, ONNX) · "
             f"Laufzeit {R['runtime_s']} s\n")
    L += ["## Fazit", ""] + [f"- {x}" for x in conclusion(R)] + [""]

    L += ["## Akzeptanzkriterien", "", "| Stufe | Metrik | Wert | Schwelle | n | 95%-KI | Ergebnis |", "|---|---|---|---|---|---|---|"]
    for c in R["acceptance"]:
        ci = f"{c['ci95'][0] * 100:.0f}–{c['ci95'][1] * 100:.0f} %" if c["ci95"] else "-"
        L.append(f"| {c['stage']} | {c['metric']} | {pct(c['value'])} | {c['cmp']} {pct(c['threshold'], 0)} | "
                 f"{c['n']} | {ci} | {'✅' if c['passed'] else '❌'} {c['note']} |")
    L.append("")

    g = m["grouping"]
    s = m["split_summary"]
    L += ["## Daten und Split", ""]
    L.append(f"- Gruppierung `{g['mode']}`: {g['n_groups']} Gruppen; einzeln verteilte Seiten: "
             f"{g['ungrouped_pages']} ({', '.join(g['ungrouped_doc_types']) or '-'}).")
    for k in ("train", "valid", "test"):
        if k in s:
            L.append(f"- {k}: {s[k]['pages']} Seiten, {s[k]['groups']} Gruppen, {s[k]['by_type']}")
    if g["ungrouped_pages"]:
        L.append(f"- **Risiko Datenleck:** Seiten von {', '.join(g['ungrouped_doc_types'])} stammen aus demselben "
                 "Dokument und liegen in mehreren Splits – Ergebnisse für diesen Typ sind optimistisch.")
    ds = m["dataset"]
    L.append(f"- Boxen am Bildrand gekappt: {ds['clipped_boxes']}; Klassen ohne Annotationen: "
             f"{', '.join(ds['classes_missing']) or '-'}")
    L.append("")

    fm = R.get("form_mask")
    if fm and fm["enabled"]:
        L += ["## Vordruck-Maske (CMR-Felder 22/23)", ""]
        L.append(f"- Feldzeile gefunden und Felder 22 + 23 maskiert: {fr(fm['pages'])}")
        L.append(f"- GT-Boxen im maskierten Bereich (aus Metriken entfernt): {fm['dropped_gt_boxes']} – "
                 "sollte 0 sein, sonst lag eine echte Unterschrift in Feld 22/23")
        if fm["not_found"]:
            L.append("- **Nicht gefunden** (unmaskiert geprüft): " + ", ".join(f"`{Path(x).name}`" for x in fm["not_found"]))
        L.append("- Kontrollbilder: Galerie „Maske“")
        L.append("")

    # detector
    par = R.get("parity")
    L += ["## 1. Detektor (ONNX)", ""]
    if par:
        L.append(f"Paritätstest PyTorch ↔ ONNX Runtime (CPU, {par['n_images']} Bilder): max. Abweichung "
                 f"Boxen {par['raw_max_box_diff']:.2e}, Scores {par['raw_max_score_diff']:.2e} (gleicher Eingangstensor, "
                 f"Top-50-Queries reihenfolgeunabhängig zugeordnet); "
                 f"Ende-zu-Ende inkl. eigener Vorverarbeitung: Boxen {par['e2e_max_box_diff']:.2e}, "
                 f"Scores {par['e2e_max_score_diff']:.2e}, ohne Gegenstück {par['e2e_unmatched']} → "
                 f"{'OK' if par['passed'] else 'ABWEICHUNG'}\n")
    det = R["detector"]
    cal = det.get("calibration")
    src = "auf dem valid-Split kalibriert (bestes F1)" if cal else "fest aus config.yaml"
    L += [f"Arbeitsschwellen je Klasse {src}, IoU {cfg['detector']['iou_match']}:", "",
          "| Klasse | Schwelle | GT | Recall | Precision | AP50 |", "|---|---|---|---|---|---|"]
    for c, v in det["per_class"].items():
        L.append(f"| {c} | {v.get('threshold', '-')} | {v['n_gt']} | {fr(v['recall'])} | {fr(v['precision'])} | {num(v['ap50'])} |")
    if cal:
        vd = cal["detector"]["per_class"]
        L += ["", f"Vergleich valid ({cal['n_pages']} Seiten) ↔ {m['split']} ({m['n_pages']} Seiten) bei denselben Schwellen – "
              "ist valid gut und test schlecht, liegt es an der Generalisierung (andere Sendungen), nicht an der Pipeline:", "",
              "| Klasse | Recall valid | Recall " + m["split"] + " | AP50 valid | AP50 " + m["split"] + " |", "|---|---|---|---|---|"]
        for c in det["per_class"]:
            a, b = vd.get(c, {}), det["per_class"][c]
            L.append(f"| {c} | {fr(a.get('recall'))} | {fr(b['recall'])} | {num(a.get('ap50'))} | {num(b['ap50'])} |")
        if m["split"] == "valid":
            L.append("\n**Hinweis:** ausgewertet wird der Split, auf dem auch die Schwellen kalibriert wurden – optimistisch.")
    bdt = det.get("by_doc_type") or {}
    if bdt:
        cls_ = list(det["per_class"])
        L += ["", "Recall je Dokumenttyp (gefordert ist Unterschrift/Stempel nur auf CMR):", "",
              "| Typ | " + " | ".join(cls_) + " |", "|---|" + "---|" * len(cls_)]
        for t, rr in bdt.items():
            L.append(f"| {t} | " + " | ".join(fr(rr[c]) if rr[c]["n"] else "-" for c in cls_) + " |")
    L += ["", "Precision/Recall über die Konfidenzschwelle:", ""]
    cls = list(R["detector"]["pr_table"])
    L.append("| Schwelle | " + " | ".join(f"{c} P / R" for c in cls) + " |")
    L.append("|---|" + "---|" * len(cls))
    for i, t in enumerate(R["detector"]["pr_table"][cls[0]] if cls else []):
        cells = []
        for c in cls:
            r = R["detector"]["pr_table"][c][i]
            cells.append(f"{num(r['precision'], 2)} / {num(r['recall'], 2)}")
        L.append(f"| {t['threshold']:.1f} | " + " | ".join(cells) + " |")
    L.append("")

    # doc type
    d = R["doctype"]
    L += ["## 2. Dokumenttyp", ""]
    L.append(f"- Kombiniert: Accuracy (ohne unsicher) {fr(d['accuracy'])}, unsicher {fr(d['uncertain'])}")
    L.append(f"- Nur Keywords: {fr(d['keyword_only'])}" + (f"; nur Klassifikator: {fr(d['classifier_only'])}" if d["classifier_only"] else "; Klassifikator: nicht trainiert/aktiv"))
    L += ["", "Konfusionsmatrix (Zeile = GT, Spalte = Vorhersage):", ""]
    cols = list(next(iter(d["confusion"].values())).keys()) if d["confusion"] else []
    L.append("| GT \\ Pred | " + " | ".join(cols) + " |")
    L.append("|---|" + "---|" * len(cols))
    for gt, row in d["confusion"].items():
        L.append(f"| {gt} | " + " | ".join(str(row[c]) for c in cols) + " |")
    L += ["", "| Typ | n | Accuracy | unsicher |", "|---|---|---|---|"]
    for t, v in d["per_type"].items():
        L.append(f"| {t} | {v['n']} | {fr(v['accuracy'])} | {fr(v['uncertain'])} |")
    misses = [r for r in d["rows"] if r["keyword"] != r["gt"]]
    if misses:
        L += ["", f"Keyword-Fehltreffer ({len(misses)}) – OCR-Text des Kopfbereichs, um `doctype.keywords` zu ergänzen:", "",
              "| Seite | GT | Keyword-Ergebnis | OCR-Kopf |", "|---|---|---|---|"]
        for r in misses:
            txt = (r.get("header_text") or "").replace("|", "/")[:160]
            L.append(f"| {Path(r['file_name']).name} | {r['gt']} | {r['keyword'] or '-'} | {txt} |")
    L.append("")

    # position
    p = R["position"]
    L += ["## 3. Positionsprüfung", ""]
    L.append(f"- Zonen: {p['zones_info']['source']}, Datei `{p['zones_info']['path']}`")
    L.append(f"- Fehlalarmrate auf echten korrekten Seiten: {fr(p['false_alarm'])}; davon zusätzlich unsicher: {fr(p['uncertain_real'])}")
    L.append(f"- Recall auf echten Negativen (Seiten, die laut GT die Regel verletzen): {fr(p.get('recall_real_negatives'))}")
    L.append(f"- Recall auf synthetischen Negativen: {fr(p['recall_negatives'])}; richtige Art (fehlt vs. falsche Position): {fr(p['correct_kind'])}")
    for k, v in p["by_kind"].items():
        L.append(f"  - {k}: {fr(v)}")
    L.append(f"- Ende-zu-Ende (mit vorhergesagtem Dokumenttyp) gleiches Ergebnis wie mit GT-Typ: {fr(p['e2e_status_agree'])}")
    L += ["", "Zonen (normiert x1, y1, x2, y2):", "", "| Typ | Klasse | Zone | Beispiele |", "|---|---|---|---|"]
    for t, zz in p["zones"].items():
        for c, z in zz.items():
            L.append(f"| {t} | {c} | {', '.join(f'{v:.2f}' for v in z['box'])} | {z.get('n_samples', '-')} |")
    for t, fields in (p.get("fields") or {}).items():
        st = (p.get("field_stats") or {}).get(t)
        L += ["", f"Feld-Regel {t}: Seite gilt nur als unterschrieben, wenn **jedes** Feld die geforderte Klasse enthält "
              "(Zuordnung über den Box-Mittelpunkt). Ground Truth aller Splits:", "",
              "| Feld | Box (x1, y1, x2, y2) | gefordert | Seiten mit Treffer |", "|---|---|---|---|"]
        for name, f in fields.items():
            hits = ", ".join(f"{c}: {n}/{st['pages']}" for c, n in (st["fields"].get(name) or {}).items()) if st else "-"
            L.append(f"| {name} | {', '.join(f'{v:.2f}' for v in f['box'])} | {', '.join(f.get('require') or [])} | {hits} |")
        if st:
            L.append(f"\n- Seiten mit allen Feldern erfüllt: **{st['pages_all_fields']} von {st['pages']}**")
            if st["outside_all_fields"]:
                L.append(f"- Boxen außerhalb aller Felder: {st['outside_all_fields']} – Feld-Boxen in `zones.rules.{t}.fields` prüfen")
    if p["gt_not_ok"]:
        L += ["", f"Seiten, die schon laut GT die Regel nicht erfüllen ({len(p['gt_not_ok'])}) – nicht in der Fehlalarmrate enthalten:", ""]
        for r in p["gt_not_ok"][:20]:
            L.append(f"- `{Path(r['file_name']).name}` ({r['doc_type']}): GT {r['gt_status']}, Pipeline {r['status']}")
    L.append("")

    # OCR
    o = R["ocr"]
    L += ["## 4. Tournummer-OCR", ""]
    L.append(f"{o['n_boxes']} `tour_nummer`-Boxen im Test-Split, davon {o['n_with_gt']} mit Ground-Truth-Text. "
             f"Format `{cfg['labels']['tour_number']['format_regex']}`, Konfidenzschwelle {cfg['ocr']['min_score']}.\n")
    L += ["| Variante | Akzeptanzquote | Exact Match (akzeptiert) | Exact Match (alle) | Format gültig |", "|---|---|---|---|---|"]
    for v, x in o["variants"].items():
        name = v.replace("pred:", "vorhergesagte Box · ").replace("/rec_only", " · nur Recognition").replace("/det_rec", " · Det+Rec")
        L.append(f"| {name} | {fr(x['acceptance'])} | {fr(x['exact_accepted'])} | {fr(x['exact_all'])} | {fr(x['valid_format'])} |")
    L += ["", f"Schwellen-Tabelle ({o['primary']}, GT-Box):", "", "| Schwelle | Akzeptanzquote | Exact Match akzeptiert |", "|---|---|---|"]
    for r in o["threshold_table"]:
        L.append(f"| {r['threshold']} | {fr(r['acceptance'])} | {fr(r['exact_accepted'])} |")
    if o.get("paddle_reference"):
        L += ["", "Referenz PaddleOCR-Python-Pipeline (gleiche Crops, nur Recognition) – Übereinstimmung mit eigener ONNX-Implementierung:", ""]
        for k, v in o["paddle_reference"].items():
            L.append(f"- {k}: " + (fr(v["agreement"]) + f" ({v['model']})" if "agreement" in v else f"Fehler: {v.get('error')}"))
    cc = o.get("cmr_count")
    L.append("")
    L.append("`cmr_count`: " + ("nicht annotiert – Stapel-Vollständigkeit nicht prüfbar." if not cc or not cc["n"]
                                else f"{cc['n']} Boxen, lesbar {fr(cc['parsed'])}; Stapel: " +
                                "; ".join(f"{g}: {v['reason']}" for g, v in cc["stacks"].items())))
    L.append("")

    # timing
    if R.get("stage_seconds"):
        L += ["## Laufzeit der Evaluation je Stufe (Wanduhr)", "", "| Stufe | Sekunden |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in R["stage_seconds"].items()]
        L.append("")
    L += ["## Laufzeit pro Seite (CPU)", "", "| Stufe | Mittel ms | Median ms | Max ms | n |", "|---|---|---|---|---|"]
    for k, v in R["timing"].items():
        L.append(f"| {k} | {v['mean_ms']:.0f} | {v['median_ms']:.0f} | {v['max_ms']:.0f} | {v['n']} |")
    L.append("")

    # gallery
    L += ["## Fehlergalerie", "", "Grün = Ground Truth, Rot = Vorhersage (mit Score), Blau = Soll-Zone bzw. OCR-Kopfbereich.", ""]
    for stage, items in R["gallery"].items():
        L += [f"### {stage.capitalize()} ({len(items)})", ""]
        if not items:
            L += ["Keine Fehler.", ""]
        for it, fn in zip(items, gallery_files.get(stage, [])):
            L.append(f"**{it['title']}** – {it['reason']}")
            if fn:
                L.append(f"![{it['title']}](gallery/{fn})")
            L.append("")
    return "\n".join(L)


def md_to_html(md: str) -> str:
    """Minimal Markdown -> HTML for this report (tables, headings, lists, images, bold, code)."""
    import re

    def inline(s):
        s = html.escape(s)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2" loading="lazy">', s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return s

    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>")
            for r in rows[2:]:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue
        if ln.startswith("#"):
            n = len(ln) - len(ln.lstrip("#"))
            out.append(f"<h{n}>{inline(ln[n:].strip())}</h{n}>")
        elif ln.lstrip().startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                out.append(f"<li>{inline(lines[i].lstrip()[2:])}</li>")
                i += 1
            out.append("</ul>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1d1d1f;"
           "background:#fff}table{border-collapse:collapse;margin:8px 0;font-size:14px}td,th{border:1px solid #ddd;"
           "padding:4px 8px;text-align:left}th{background:#f3f3f3}img{max-width:100%;border:1px solid #ccc;"
           "margin:4px 0 16px}code{background:#f3f3f3;padding:0 3px}h2{border-bottom:2px solid #eee;margin-top:32px}")
    return (f"<!doctype html><html lang='de'><head><meta charset='utf-8'><title>Evaluationsbericht</title>"
            f"<style>{css}</style></head><body>{''.join(out)}</body></html>")


def render(cfg: dict, R: dict, out: Path, log=print) -> None:
    gdir = out / "gallery"
    files = {}
    for stage, items in R["gallery"].items():
        files[stage] = [draw_item(it, gdir / f"{stage}_{i:02d}.jpg") for i, it in enumerate(items)]
    md = to_markdown(cfg, R, files)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.html").write_text(md_to_html(md), encoding="utf-8")


def render_from_results(cfg: dict, log=print) -> int:
    out = artifacts(cfg, "report")
    p = out / "results.json"
    if not p.is_file():
        log("FEHLER: keine results.json - zuerst `make eval`")
        return 2
    R = json.loads(p.read_text(encoding="utf-8"))
    render(cfg, R, out, log)
    log(f"[report] {out / 'report.md'} | {out / 'report.html'}")
    return 0 if all(c["passed"] for c in R["acceptance"]) else 1
