"""`make finalize RUN=<name>`: the person's decision -> archive files of the tour.

Reads artifacts/process/<name>/ergebnis.json + entscheidung.json (saved from the review
page), applies the decision (signature/stamp, archive flags, doc type, CMR i/n, tour
number), runs the organisational checks again and writes freigabe/:

    CMR_<tour>.pdf        CMR sorted 1..n, duplicates removed
    LS_<tour>.pdf         Lieferscheine
    andere_touren/        pages of another tour (additional load), one PDF per tour + type
    CMR_<tour>.eml        e-mail drafts with the PDF attached (open in Outlook, send)
    LS_<tour>.eml
    protokoll_de.txt / protokoll_pl.txt / protokoll.csv
                          result, what is still to do, paper sort order, model vs. person

Refuses to run while CMR/Lieferscheine are unconfirmed (FORCE=1 overrides). The e-mail drafts
are only written when the person confirmed the list of missing documents on the review page
(or nothing is missing). Items accepted anyway (with a reason) do not keep the tour open.
Copies the PDFs into process.deliver.* only when the tour is complete (or with FORCE=1).
"""

from __future__ import annotations

import copy
import csv
import json
import re
import shutil
from email.message import EmailMessage
from pathlib import Path

from PIL import Image

from ..config import artifacts, resolve
from ..zones.synthetic import to_rgb
from .organize import ERROR, check_units, organize
from .labels import build_export, export_name
from .run import safe_name
from .texts import MSG, item_text, pages_text, reason_text, render_check

OBJ = ("unterschrift", "stempel")

PROTO = {
    "de": {
        "title": "Prüfprotokoll Tour {tour}",
        "scan": "Scan: {input} – {n} Seiten, verarbeitet {created}",
        "reviewer": "Geprüft von: {reviewer} ({saved})",
        "complete": "ERGEBNIS: VOLLSTÄNDIG – Papier kann ins Dokumentenarchiv.",
        "open": "ERGEBNIS: OFFEN – Papier noch nicht ins Archiv, siehe „Zu tun“.",
        "forced": "ACHTUNG: mit FORCE=1 abgeschlossen, obwohl {n} Seiten nicht bestätigt waren: {pages}",
        "h_org": "Organisatorisch",
        "h_sig": "Unterschrift / Stempel (Entscheidung der prüfenden Person)",
        "sig_line": "{type}: {valid} gültig, {invalid} ungültig",
        "invalid_item": "{page} {title}: {missing}",
        "missing_cls": "{cls} fehlt",
        "differs": "Abweichung vom Modellvorschlag: {pages}",
        "differs_none": "Entscheidung stimmt auf allen Seiten mit dem Modellvorschlag überein",
        "h_todo": "Zu tun",
        "todo_cmr_missing": "CMR Nr. {missing} von {total} fehlt – an Polilogistics melden, Ersatz-CMR besorgen",
        "todo_invalid": "{page} {title}: {missing} – Ersatzdokument besorgen",
        "todo_other": "{page} gehört zu Tour {tour} – zu dieser Tour legen",
        "todo_send": "Senden: {file} an {to} (Entwurf {eml}) und ins digitale Archiv ({archive})",
        "todo_paper": "Papier ins Dokumentenarchiv (Reihenfolge unten)",
        "todo_paper_wait": "Papier erst ins Archiv, wenn die offenen Punkte erledigt sind",
        "todo_sap": "Am nächsten Tag: SAP-Transaktion ZCHECKLSARCHIV, Tour {tour}{tas} – Meldung „alles archiviert“ prüfen",
        "tas": ", TA {tas}",
        "h_paper": "Reihenfolge Papier",
        "paper_cmr": "CMR (1..n): {pages}",
        "paper_ls": "Lieferscheine: {pages}",
        "paper_drop": "Nicht archivieren (Duplikat/aussortiert): {pages}",
        "h_files": "Dateien",
        "h_missing": "Fehlliste (fehlende Dokumente)",
        "missing_none": "nichts fehlt",
        "accepted_mark": "trotzdem akzeptiert",
        "bulk": "Gesammelt bestätigt (Modell sicher, Schritt bestätigt): {n} von {total} Seiten; die übrigen einzeln entschieden",
        "labels": "Label-Export für das nächste Training: {dir} ({n} Seiten korrigiert, {boxes} Boxen von der Person) – "
                  "vor dem Training im Editor durchsehen",
        "missing_acc": "trotzdem akzeptiert: {text} – Grund: {reason}",
        "missing_confirmed": "Fehlliste bestätigt von {reviewer} – Mail-Entwürfe erzeugt",
        "missing_unconfirmed": "Fehlliste nicht bestätigt – keine Mail-Entwürfe erzeugt",
        "todo_confirm_missing": "Fehlliste auf der Prüfseite bestätigen, Entscheidung neu speichern, make finalize "
                                "erneut – erst dann entstehen die Mail-Entwürfe",
        "archive_dir": "srem-svr-file01",
        "delivered": "kopiert nach {dir}",
        "not_delivered": "nicht ins Archiv kopiert (Tour nicht vollständig, FORCE=1 erzwingt es)",
    },
    "pl": {
        "title": "Protokół kontroli trasy {tour}",
        "scan": "Skan: {input} – stron: {n}, przetworzono {created}",
        "reviewer": "Sprawdził(a): {reviewer} ({saved})",
        "complete": "WYNIK: KOMPLETNE – papier może trafić do archiwum dokumentów.",
        "open": "WYNIK: OTWARTE – papieru jeszcze nie archiwizować, patrz „Do zrobienia”.",
        "forced": "UWAGA: zamknięto z FORCE=1, mimo że stron niepotwierdzonych było {n}: {pages}",
        "h_org": "Organizacja",
        "h_sig": "Podpis / pieczątka (decyzja osoby sprawdzającej)",
        "sig_line": "{type}: ważne {valid}, nieważne {invalid}",
        "invalid_item": "{page} {title}: {missing}",
        "missing_cls": "brak: {cls}",
        "differs": "Inna decyzja niż propozycja modelu: {pages}",
        "differs_none": "Decyzja zgodna z propozycją modelu na wszystkich stronach",
        "h_todo": "Do zrobienia",
        "todo_cmr_missing": "Brak CMR nr {missing} z {total} – zgłosić do Polilogistics, załatwić zastępczy CMR",
        "todo_invalid": "{page} {title}: {missing} – załatwić dokument zastępczy",
        "todo_other": "{page} należy do trasy {tour} – dołączyć do tej trasy",
        "todo_send": "Wysłać: {file} na {to} (szkic {eml}) i do archiwum cyfrowego ({archive})",
        "todo_paper": "Papier do archiwum dokumentów (kolejność poniżej)",
        "todo_paper_wait": "Papier do archiwum dopiero po załatwieniu otwartych punktów",
        "todo_sap": "Następnego dnia: transakcja SAP ZCHECKLSARCHIV, trasa {tour}{tas} – sprawdzić komunikat "
                    "„wszystko zarchiwizowane”",
        "tas": ", TA {tas}",
        "h_paper": "Kolejność papieru",
        "paper_cmr": "CMR (1..n): {pages}",
        "paper_ls": "Dowody dostawy: {pages}",
        "paper_drop": "Nie archiwizować (duplikat/odłożone): {pages}",
        "h_files": "Pliki",
        "h_missing": "Lista braków (brakujące dokumenty)",
        "missing_none": "niczego nie brakuje",
        "accepted_mark": "zaakceptowano mimo to",
        "bulk": "Potwierdzone zbiorczo (model pewny, krok potwierdzony): {n} z {total} stron; pozostałe rozstrzygnięte pojedynczo",
        "labels": "Eksport etykiet do następnego treningu: {dir} (poprawionych stron: {n}, ramek od osoby: {boxes}) – "
                  "przed treningiem przejrzeć w edytorze",
        "missing_acc": "zaakceptowano mimo to: {text} – powód: {reason}",
        "missing_confirmed": "Listę braków potwierdził(a) {reviewer} – utworzono szkice e-maili",
        "missing_unconfirmed": "Lista braków niepotwierdzona – nie utworzono szkiców e-maili",
        "todo_confirm_missing": "Potwierdzić listę braków na stronie kontroli, zapisać decyzję ponownie, ponownie "
                                "make finalize – dopiero wtedy powstaną szkice e-maili",
        "archive_dir": "srem-svr-file01",
        "delivered": "skopiowano do {dir}",
        "not_delivered": "nie skopiowano do archiwum (trasa niekompletna, FORCE=1 wymusza)",
    },
}
TYPE_NAMES = {"de": {"cmr": "CMR", "lieferschein": "Lieferscheine"},
              "pl": {"cmr": "CMR", "lieferschein": "Dowody dostawy"}}
SINGULAR = {"de": {"lieferschein": "Lieferschein"}, "pl": {"lieferschein": "dowód dostawy"}}
CLS_NAMES = {"de": {"unterschrift": "Unterschrift", "stempel": "Stempel"},
             "pl": {"unterschrift": "podpis", "stempel": "pieczątka"}}


def apply_decision(pages: list[dict], decision: dict) -> list[dict]:
    """Page records with the person's decision applied (copies; ergebnis.json stays as is):
    signature/stamp, archive, doc type, CMR i/n, tour number, Lieferschein number and page,
    TAs of a CMR, TAs struck out on / added to the loading list."""
    out = []
    dpages = decision.get("pages") or {}
    struck = set(decision.get("ta_struck") or [])
    added = [t for t in decision.get("ta_added") or [] if t]
    for p in pages:
        q = copy.deepcopy(p)
        d = dpages.get(str(p["n"])) or {}
        if d.get("doc_type"):
            q["doc_type"] = d["doc_type"]
        q["proposal"] = (q.get("proposals") or {}).get(q["doc_type"], {}).get("classes", {})
        if d.get("archive_set", "archive" in d and not d["archive"]):
            q["archive"] = bool(d.get("archive", True))   # else organize() picks among duplicates
        q["confirmed"] = bool(d.get("confirmed"))
        q["decision"] = {c: bool(d[c]) for c in OBJ if d.get(c) is not None}
        if d.get("cmr_count"):
            q["cmr_count"] = dict(q.get("cmr_count") or {}, parsed=[int(x) for x in d["cmr_count"]])
        if d.get("tour"):
            q["tour"] = dict(q.get("tour") or {}, text=d["tour"], accepted=True, manual=True)
        if "ls_number" in d:
            q["ls_number"] = d["ls_number"] or None
        if "ls_page" in d:
            q["ls_page"] = [int(x) for x in d["ls_page"]] if d["ls_page"] else None
        if d.get("ta") is not None and q["doc_type"] == "cmr":
            q["ta"] = [{"ta": t, "excluded": False, "manual": True} for t in d["ta"]]
        if q["doc_type"] == "loading_list":
            if d.get("ta_list") is not None:   # the person's list: read, corrected, drawn, struck
                q["ta"] = [{"ta": t["ta"], "excluded": bool(t.get("struck")), "box": t.get("box"),
                            "manual": t.get("src") == "person"} for t in d["ta_list"]
                           if re.fullmatch(r"\d{8}", t.get("ta") or "")]
            q["ta"] = [dict(t, excluded=t.get("excluded") or t["ta"] in struck) for t in q.get("ta") or []]
        q["bulk"] = bool(d.get("bulk"))
        if d.get("boxes") is not None:
            q["boxes_final"], q["boxes_rejected"] = d["boxes"], d.get("rejected") or []
        out.append(q)
    lists = [q for q in out if q["doc_type"] == "loading_list"]
    if lists and added:
        have = {t["ta"] for q in lists for t in q.get("ta") or []}
        lists[0]["ta"] = list(lists[0].get("ta") or []) + [
            {"ta": t, "excluded": t in struck, "manual": True} for t in added if t not in have]
    return out


def unit_title(u: dict, by_n: dict, lang: str) -> str:
    if u["number"]:
        return f"{SINGULAR[lang]['lieferschein']} {u['number']}"
    return card_title(by_n[u["pages"][0]], lang)


def unit_missing(u: dict, lang: str) -> str:
    return ", ".join(PROTO[lang]["missing_cls"].format(cls=CLS_NAMES[lang].get(c, c)) for c in u["missing"]) or "?"


def missing_list(org: dict, invalid_units: list[dict], by_n: dict, accepted: dict, lang: str) -> list[dict]:
    """organize's missing items + CMR pages / Lieferscheine that fail the stamp/signature rule
    (key page:<n> resp. ls_doc:<number>)."""
    items = [dict(it) for it in org["missing_items"]]
    for u in invalid_units:
        items.append({"key": u["key"], "code": "item_page", "level": ERROR, "accepted": u["key"] in accepted,
                      "params": {"title": unit_title(u, by_n, lang), "page": pages_text(u["pages"], lang),
                                 "missing": unit_missing(u, lang)}})
    return items


def card_title(p: dict, lang: str) -> str:
    if p["doc_type"] == "cmr":
        c = (p.get("cmr_count") or {}).get("parsed")
        return MSG[lang]["cmr_of"].format(i=c[0], n=c[1]) if c else "CMR ?"
    t = SINGULAR[lang].get(p["doc_type"], p["doc_type"])
    if p["doc_type"] == "lieferschein" and p.get("ls_number"):
        t += f" {p['ls_number']}" + (f" ({p['ls_page'][0]}/{p['ls_page'][1]})" if p.get("ls_page") else "")
    return t


def write_pdf(images: list[Path], path: Path, dpi: int) -> None:
    ims = [to_rgb(Image.open(p)) for p in images]
    ims[0].save(path, save_all=True, append_images=ims[1:], resolution=float(dpi))


def write_eml(path: Path, to: str, subject: str, body: str, attachment: Path) -> None:
    """Unsent e-mail draft (X-Unsent: 1): Outlook opens it ready to send."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["X-Unsent"] = "1"
    msg.set_content(body)
    msg.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf", filename=attachment.name)
    path.write_bytes(bytes(msg))


def run_finalize(cfg, run: str, decision_path: str | None, force: bool, log) -> int:
    base = artifacts(cfg, "process", run)
    res_path = base / "ergebnis.json"
    if not res_path.is_file():
        log(f"FEHLER: {res_path} fehlt - zuerst `make process`")
        return 2
    dec_path = resolve(decision_path) if decision_path else base / "entscheidung.json"
    if not dec_path.is_file():
        log(f"FEHLER: {dec_path} fehlt - auf der Prüfseite „Entscheidung speichern“ und die Datei dort ablegen")
        return 2
    R = json.loads(res_path.read_text(encoding="utf-8"))
    dec = json.loads(dec_path.read_text(encoding="utf-8"))
    if dec.get("format") != "docval-entscheidung":
        log(f"FEHLER: {dec_path} ist keine Entscheidungsdatei der Prüfseite")
        return 2
    if dec.get("ergebnis_created") != R["created"] and not force:
        log(f"FEHLER: Entscheidung gehört zu einem anderen Lauf ({dec.get('ergebnis_created')} statt "
            f"{R['created']}) - Prüfseite dieses Laufs verwenden (FORCE=1 erzwingt)")
        return 2
    pcfg = cfg["process"]
    pages = apply_decision(R["pages"], dec)
    by_n = {p["n"]: p for p in pages}
    rules = R["rules"]
    tour = R["tour"]
    accepted = {k: v for k, v in (dec.get("accepted") or {}).items() if v and v.get("reason")}
    org = organize(pages, tour, rules, bool(R.get("ta_validated")), accepted)
    archived = org["cmr_order"] + org["ls_order"] + [n for n in org["other_tour"] if by_n[n].get("archive", True)]
    open_pages = sorted(n for n in archived if not by_n[n]["confirmed"])
    if open_pages and not force:
        log(f"FEHLER: {len(open_pages)} Seiten nicht bestätigt (S. {', '.join(map(str, open_pages))}) - "
            "auf der Prüfseite bestätigen und neu speichern (FORCE=1 schließt trotzdem ab)")
        return 2
    # stamp/signature rule: per CMR page, per Lieferschein (all its pages together)
    units = check_units(pages, org["cmr_order"] + org["ls_order"], rules)   # pages of other tours: their tour
    unit_of = {n: u for u in units for n in u["pages"]}
    invalid_all = [u for u in units if u["valid"] is not True]
    invalid = [u for u in invalid_all if u["key"] not in accepted]
    # the person must have confirmed the missing list on the review page before mails are drafted
    keys = {it["key"] for it in missing_list(org, invalid_all, by_n, accepted, "de")}
    missing_ok = not keys or bool(dec.get("missing_confirmed"))
    unseen = sorted(keys - set(dec.get("missing_keys") or [])) if dec.get("missing_confirmed") else []
    if keys and not missing_ok:
        log("[finalize] HINWEIS: Fehlliste auf der Prüfseite nicht bestätigt - keine Mail-Entwürfe")
    if unseen:
        log(f"[finalize] WARNUNG: fehlt laut Abschluss, stand aber nicht in der bestätigten Fehlliste: {', '.join(unseen)}")
    # the person contradicts a definite model proposal (ja/nein; "unsicher" is no contradiction)
    differs = [p["n"] for p in pages if p["n"] in archived and any(
        c in p["decision"] and p["proposal"].get(c) in ("ja", "nein")
        and (p["proposal"][c] == "ja") != p["decision"][c] for c in OBJ)]
    complete = org["complete"] and not invalid

    # ---------------------------------------------------------------- files
    out = base / "freigabe"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    dpi = R.get("dpi", 150)
    tname = safe_name(tour or run)
    files = {}
    for kind, order in (("cmr", org["cmr_order"]), ("lieferschein", org["ls_order"])):
        if order:
            f = out / f"{'CMR' if kind == 'cmr' else 'LS'}_{tname}.pdf"
            write_pdf([base / by_n[n]["image"] for n in order], f, dpi)
            files[kind] = f
    other: dict[tuple, list[int]] = {}
    for n, t in org["other_tour"].items():
        if by_n[n].get("archive", True):
            other.setdefault((t, by_n[n]["doc_type"]), []).append(n)
    for (t, kind), ns in sorted(other.items()):
        d = out / "andere_touren"
        d.mkdir(exist_ok=True)
        write_pdf([base / by_n[n]["image"] for n in ns], d / f"{'CMR' if kind == 'cmr' else 'LS'}_{safe_name(t)}.pdf", dpi)
    mails = pcfg.get("mail") or {}
    emls = {}
    for kind, f in files.items():
        to = mails.get(kind)
        if to and missing_ok:
            label = "CMR" if kind == "cmr" else "Lieferscheine"
            emls[kind] = out / f.with_suffix(".eml").name
            write_eml(emls[kind], to, f"{label} Tour {tour or run}", f"Tour {tour or run}\n{f.name}\n", f)
    delivered = {}
    deliver = pcfg.get("deliver") or {}
    if complete or force:
        for kind, f in files.items():
            d = deliver.get(kind)
            if d:
                dd = resolve(d)
                dd.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dd / f.name)
                delivered[kind] = str(dd)

    # ---------------------------------------------------------------- labels for the next training
    lab_dir = out / "labels" / export_name(tour, run)
    lab_coco, lab_meta = build_export(R, dec, list(R.get("classes") or cfg.get("classes") or []), base, lab_dir)
    n_corr = sum(1 for d in (dec.get("pages") or {}).values() if d.get("corrected"))
    n_person = sum(1 for a in lab_coco["annotations"] if a["attributes"]["quelle"] == "person")
    try:
        from ..eval.i18n import guide, languages
        from ..eval.label_editor import editor_data, write_editor
        data = editor_data(lab_dir.name, lab_coco, "_annotations.coco.json", lab_meta, list(R.get("classes") or []),
                           list(R.get("doc_types") or []), lab_dir / "page_types.csv")
        for lang in languages(cfg):
            write_editor(lab_dir, data, lang, guide(cfg, lang))
    except (KeyError, TypeError) as e:   # minimal configs (tests): export without editor
        log(f"[finalize] Label-Editor nicht erzeugt: {e}")

    # ---------------------------------------------------------------- protocol
    ta_list = (org.get("ta") or {}).get("loaded") or []
    for lang in cfg.get("ui_languages") or ["de"]:
        t = PROTO[lang]
        pg = lambda n: MSG[lang]["page"].format(n=n)  # noqa: E731
        pgs = lambda ns: pages_text(list(ns), lang) if ns else "–"  # noqa: E731
        L = [t["title"].format(tour=tour or "?"), "",
             t["scan"].format(input=R["input"], n=len(pages), created=R["created"]),
             t["reviewer"].format(reviewer=dec.get("reviewer") or "?", saved=dec.get("saved") or "?"), "",
             t["complete"] if complete else t["open"]]
        if open_pages:
            L.append(t["forced"].format(n=len(open_pages), pages=pgs(open_pages)))
        L += ["", t["h_org"]]
        ic = {"ok": "✓", "fehler": "✗", "hinweis": "!"}
        L += [f"  {ic[c['level']]} {render_check(c, lang)}" for c in org["checks"]]
        L += ["", t["h_missing"]]
        mitems = missing_list(org, invalid_all, by_n, accepted, lang)
        for it in mitems:
            if it["accepted"]:
                L.append("  ✓ " + t["missing_acc"].format(text=item_text(it, lang),
                                                         reason=reason_text(accepted[it["key"]], lang)))
            else:
                L.append(f"  {'✗' if it['level'] == ERROR else '!'} {item_text(it, lang)}")
        if not mitems:
            L.append("  " + t["missing_none"])
        else:
            L.append("  " + (t["missing_confirmed"].format(reviewer=dec.get("reviewer") or "?") if missing_ok
                             else t["missing_unconfirmed"]))
        L += ["", t["h_sig"]]
        for kind in ("cmr", "lieferschein"):
            ku = [u for u in units if u["kind"] == kind]
            if not ku:
                continue
            bad = [u for u in ku if u in invalid_all]
            L.append("  " + t["sig_line"].format(type=TYPE_NAMES[lang][kind], valid=len(ku) - len(bad),
                                                 invalid=len(bad)))
            for u in bad:
                L.append("    - " + t["invalid_item"].format(page=pgs(u["pages"]), title=unit_title(u, by_n, lang),
                                                             missing=unit_missing(u, lang))
                         + (f" ({t['accepted_mark']})" if u["key"] in accepted else ""))
        n_bulk = sum(1 for n in archived if by_n[n].get("bulk"))
        if n_bulk:
            L.append("  " + t["bulk"].format(n=n_bulk, total=len(archived)))
        L.append("  " + (t["differs"].format(pages=pgs(differs)) if differs else t["differs_none"]))
        L += ["", t["h_todo"]]
        todo = []
        open_cmr = [it["params"]["i"] for it in org["missing_items"] if it["code"] == "item_cmr" and not it["accepted"]]
        if open_cmr:
            todo.append(t["todo_cmr_missing"].format(missing=", ".join(map(str, open_cmr)), total=org["cmr_total"]))
        if not missing_ok:
            todo.append(t["todo_confirm_missing"])
        for u in invalid:
            todo.append(t["todo_invalid"].format(page=pgs(u["pages"]), title=unit_title(u, by_n, lang),
                                                 missing=unit_missing(u, lang)))
        for n, tr in org["other_tour"].items():
            todo.append(t["todo_other"].format(page=pg(n), tour=tr))
        todo += [render_check(c, lang) for c in org["checks"]
                 if c["level"] == ERROR and c["code"] not in ("cmr_missing",)]
        for kind, f in files.items():
            todo.append(t["todo_send"].format(file=f.name, to=mails.get(kind, "?"),
                                              eml=emls[kind].name if kind in emls else "–",
                                              archive=delivered.get(kind) or t["archive_dir"]))
        todo.append(t["todo_paper"] if complete else t["todo_paper_wait"])
        todo.append(t["todo_sap"].format(tour=tour or "?", tas=t["tas"].format(tas=", ".join(ta_list)) if ta_list else ""))
        L += [f"  {k + 1}. {x}" for k, x in enumerate(todo)]
        L += ["", t["h_paper"], "  " + t["paper_cmr"].format(pages=pgs(org["cmr_order"])),
              "  " + t["paper_ls"].format(pages=pgs(org["ls_order"]))]
        drop = sorted(set(org["duplicates"]) | set(org["not_archived"]) | set(org.get("discarded") or []))
        if drop:
            L.append("  " + t["paper_drop"].format(pages=pgs(drop)))
        L += ["", t["h_files"]]
        for kind, f in files.items():
            note = (t["delivered"].format(dir=delivered[kind]) if kind in delivered
                    else t["not_delivered"] if deliver.get(kind) else "")
            L.append(f"  {f.name}" + (f" – {note}" if note else ""))
            if kind in emls:
                L.append(f"  {emls[kind].name}")
        for f in sorted((out / "andere_touren").glob("*.pdf")) if (out / "andere_touren").is_dir() else []:
            L.append(f"  andere_touren/{f.name}")
        L.append("  " + t["labels"].format(dir=f"labels/{lab_dir.name}/", n=n_corr, boxes=n_person))
        (out / f"protokoll_{lang}.txt").write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")

    with open(out / "protokoll.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["seite", "quelle", "dokumenttyp", "dokumenttyp_modell", "cmr", "tour", "ta", "lieferschein",
                    "seite_von", "modell_unterschrift", "entscheidung_unterschrift", "modell_stempel",
                    "entscheidung_stempel", "gueltig", "trotzdem_akzeptiert", "archiviert", "ziel", "bestaetigt"])
        orig = {p["n"]: p for p in R["pages"]}
        for p in pages:
            n = p["n"]
            target = ("CMR" if n in org["cmr_order"] else "LS" if n in org["ls_order"]
                      else f"Tour {org['other_tour'][n]}" if n in org["other_tour"]
                      else "Duplikat" if n in org["duplicates"] else "")
            c = (p.get("cmr_count") or {}).get("parsed")
            u = unit_of.get(n)
            v = u["valid"] if u else None
            po = p.get("ls_page") or p.get("page_of")
            acc = accepted.get(u["key"]) if u else None
            w.writerow([n, p["source"], p["doc_type"], orig[n]["doc_type"], f"{c[0]}/{c[1]}" if c else "",
                        (p.get("tour") or {}).get("text", ""),
                        " ".join(x["ta"] + ("(gestrichen)" if x.get("excluded") else "") for x in p.get("ta") or []),
                        p.get("ls_number") or "", f"{po[0]}/{po[1]}" if po else "",
                        p["proposal"].get("unterschrift", ""), p["decision"].get("unterschrift", ""),
                        p["proposal"].get("stempel", ""), p["decision"].get("stempel", ""),
                        "" if v is None else v, reason_text(acc, "de") if acc else "", n in archived, target,
                        p["confirmed"]])
    log(f"[finalize] Tour {tour}: {'VOLLSTÄNDIG' if complete else 'OFFEN'}"
        f"{'' if missing_ok else ' (Fehlliste nicht bestätigt, keine Mails)'} - "
        f"CMR {len(org['cmr_order'])}, Lieferscheine {len(org['ls_order'])}, ungültig {len(invalid)}, "
        f"Abweichung vom Modell {len(differs)}")
    for c in org["checks"]:
        log(f"[finalize] {c['level']:8s} {render_check(c, 'de')}")
    log(f"[finalize] -> {out} (protokoll_de.txt)")
    return 0
