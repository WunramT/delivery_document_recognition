"""Review page of one tour: pruefung.html (German) / pruefung_pl.html (Polish).

A step-by-step assistant; a step opens when the one before is confirmed, going back is always
possible (a change there resets the confirmation of the later steps):

0. Seiten zuordnen - only if needed: doc type unsure, tour number unreadable, other tour,
   pick-up slip, collective confirmation; below, collapsed, every page by type (changeable)
1. Ladeliste - each page large with its TA boxes; a click on a box strikes the TA (not
   loaded), unreadable TAs are typed in, a TA the model missed: draw its box, type the number
2. Lieferscheine - first the ones whose number was not read (type it in), then one row per
   TA of the loading list: pages 1..n left to right, copies below, a missing page as a
   placeholder; Lieferscheine not on the loading list at the end. Rule per Lieferschein:
   stamp or signature on any of its pages
3. CMR - first the ones whose CMR i/n was not read, then 1..n left to right, copies below,
   missing numbers as placeholders; the TAs of every CMR against the loading list
4. Abschluss - missing list (accept anyway with a reason), confirm it (only then make finalize
   writes the e-mail drafts), name, save entscheidung.json

Every page opens in a large view (zoom with the mouse wheel, drag to move, already zoomed to
the number or the stamp area). Where the person says a signature/stamp is there but the model
has no box, the person draws one (or clicks a model box); "missing" turns the model's boxes
into rejected ones; a number typed in without a model box needs a box too. The boxes go into
entscheidung.json and from there (make finalize) into a label export for the next training.

Self-contained, opens by double click (no server, no internet); images are loaded from
seiten/ next to it. Intermediate state stays in the browser (localStorage).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..eval.i18n import CLASS_NAMES, DOC_TYPE_NAMES, SUFFIX
from ..eval.label_editor import CLASS_COLORS
from .texts import MSG, REASONS

UI = {
    "de": {
        "html_lang": "de", "title": "Prüfung Tour", "save": "Entscheidung speichern", "discard": "alles verwerfen",
        "steps": ["Seiten zuordnen", "Ladeliste", "Lieferscheine", "CMR", "Abschluss"],
        "step_confirm": "Schritt bestätigen und weiter", "step_done": "Schritt bestätigt",
        "step_locked": "Erst die Schritte davor bestätigen.", "open_issues": "Noch offen: {n}",
        "step_reset": "Eine Änderung hier setzt die Bestätigung der folgenden Schritte zurück.",
        "s0_intro": "Seiten, bei denen die automatische Zuordnung nicht sicher war. Seite anklicken, Typ oder "
                    "Tournummer festlegen.",
        "s0_none": "Nichts zu klären – alle Seiten sind sicher zugeordnet.",
        "s0_all": "Alle Seiten nach Typ (zum Ändern aufklappen)",
        "why_dt": "Dokumenttyp unsicher", "why_tour": "Tournummer nicht gelesen", "why_other": "andere Tour: {tour}",
        "why_discard": "Abholschein – wird verworfen", "why_conf": "Sammelbestätigung",
        "s1_intro": "TA-Box anklicken = gestrichen / nicht verladen (nochmal = zurück). Unlesbare TA eintippen. "
                    "Fehlt eine TA ganz: „TA-Box zeichnen“, Box um die Zeile ziehen, Nummer eintragen.",
        "s1_none": "Keine Ladeliste im Stapel – ohne Ladeliste gibt es keinen TA-Abgleich.",
        "ta_draw": "TA-Box zeichnen", "ta_read": "gelesen", "ta_unread": "unlesbar – eintippen",
        "ta_drawn": "gezeichnet", "struck": "gestrichen", "strike": "streichen", "unstrike": "zurück",
        "loaded_n": "{n} TA verladen", "struck_n": "{n} gestrichen", "ll_missing": "Ladeliste Seite {i} von {n} fehlt",
        "s2_unread": "Lieferscheinnummer nicht gelesen – Seite anklicken, Nummer eintragen",
        "s2_intro": "Eine Zeile je TA der Ladeliste, Seiten von links nach rechts, Kopien darunter. Kachel anklicken "
                    "= große Ansicht. Ein Lieferschein ist gültig mit Stempel oder Unterschrift auf einer seiner Seiten.",
        "s2_extra": "Lieferscheine, deren Nummer nicht auf der Ladeliste steht",
        "s2_struck": "Lieferscheine zu gestrichenen TAs", "no_ls": "kein Lieferschein",
        "page_missing": "Seite {i} fehlt", "carrier": "Hermes/DHL – Sammelbestätigung prüfen",
        "s3_unread": "CMR-Nummer (i/n) nicht gelesen – Seite anklicken, Nummer eintragen",
        "s3_intro": "CMR 1..n von links nach rechts, Kopien darunter. Stempel und Unterschrift nötig.",
        "cmr_missing": "CMR {i} fehlt", "cmr_conflict": "Widersprüchliche CMR-Gesamtzahl: {totals}",
        "ta_no_cmr": "TA ohne CMR", "ta_cmr_extra": "TA auf CMR, aber nicht auf der Ladeliste",
        "s4_intro": "Was fehlt, steht hier noch einmal gesammelt. Jeder Punkt kann mit Grund trotzdem akzeptiert "
                    "werden. Erst nach „Fehlliste bestätigen“ erzeugt make finalize die Mail-Entwürfe.",
        "sum_cmr": "CMR", "sum_ls": "Lieferscheine", "sum_struck": "gestrichene TAs", "sum_corr": "korrigierte Seiten",
        "sum_boxes": "gezeichnete Boxen", "reviewer": "Prüfer/in",
        "missing_none": "Nichts fehlt.", "accept": "trotzdem akzeptieren", "accepted": "akzeptiert",
        "undo": "zurücknehmen", "note": "Bemerkung", "cancel": "abbrechen", "choose": "– wählen –",
        "note_needed": "Bei „Sonstiges“ bitte eine Bemerkung eintragen.",
        "confirm_missing": "Fehlliste bestätigen – Mail-Entwürfe freigeben", "missing_confirmed": "Fehlliste bestätigt",
        "missing_changed": "Die Liste hat sich seit der Bestätigung geändert – bitte erneut bestätigen.",
        "save_need_name": "Bitte zuerst Ihren Namen bei „Prüfer/in“ eintragen.",
        "save_open": "Noch nicht alle Schritte sind bestätigt ({steps}). Trotzdem speichern? (Der Abschluss geht "
                     "erst, wenn alle bestätigt sind.)",
        "save_unconfirmed": "Die Fehlliste ist noch nicht bestätigt – make finalize erzeugt dann keine "
                            "Mail-Entwürfe. Trotzdem speichern?",
        "saved": "Gespeichert. Datei als entscheidung.json in den Ordner dieser Seite legen, dann: make finalize RUN={name}",
        "loaded": "Zwischenstand aus dem Browser geladen.", "confirm_discard": "Alle Eingaben auf dieser Seite verwerfen?",
        "page": "S. {n}", "doctype": "Dokumenttyp", "tour": "Tournummer", "tour_this": "= {tour}",
        "cmr_count": "CMR-Nr. (i/n)", "ls_number": "Lieferschein-Nr.", "ls_page": "Seite (i/n)", "ta_field": "TA",
        "present": "vorhanden", "absent": "fehlt", "model": "Modell", "ocr_read": "gelesen",
        "h_obj": "Unterschrift / Stempel", "missing_cls": "{cls} fehlt",
        "hint_draw": "Box zeichnen (B) oder eine Modellbox anklicken",
        "hint_reject": "Modellboxen gelten als Fehlalarm – anklicken behält eine",
        "draw": "Box zeichnen", "drawing": "Box ziehen … (Esc = abbrechen)", "boxes_person": "Ihre Boxen",
        "copies": "Kopien: {pages}", "dup": "Kopie – wird nicht archiviert", "archive_this": "diese archivieren",
        "valid": "gültig", "invalid": "ungültig", "open": "offen",
        "iss_doctype": "Dokumenttyp wählen", "iss_tour": "Tournummer eintragen", "iss_ls": "Lieferscheinnummer eintragen",
        "iss_cmr": "CMR-Nummer i/n eintragen", "iss_decide": "Stempel/Unterschrift entscheiden",
        "iss_box": "Box zeichnen: {cls}", "iss_ta": "TA eintragen oder streichen",
        "v_full": "ganze Seite", "v_area": "Prüfbereich", "v_num": "Nummer",
        "prev": "← zurück", "next": "weiter →", "close": "fertig (Esc)",
        "keys": "Tasten: 1 Unterschrift · 2 Stempel · B Box zeichnen · Enter weiter zur nächsten offenen · ←/→ · "
                "Esc schließen · Mausrad zoomen, ziehen verschiebt",
        "img_missing": "Bild fehlt: ", "none": "keine", "bad_number": "Bitte eine 8-stellige Nummer eintragen.",
    },
    "pl": {
        "html_lang": "pl", "title": "Kontrola trasy", "save": "Zapisz decyzję", "discard": "odrzuć wszystko",
        "steps": ["Przypisanie stron", "Lista załadunkowa", "Dowody dostawy", "CMR", "Zamknięcie"],
        "step_confirm": "Potwierdź krok i dalej", "step_done": "Krok potwierdzony",
        "step_locked": "Najpierw potwierdź poprzednie kroki.", "open_issues": "Otwarte: {n}",
        "step_reset": "Zmiana tutaj cofa potwierdzenie kolejnych kroków.",
        "s0_intro": "Strony, których automatyczne przypisanie nie było pewne. Kliknij stronę, ustal typ lub numer trasy.",
        "s0_none": "Nic do wyjaśnienia – wszystkie strony przypisane pewnie.",
        "s0_all": "Wszystkie strony według typu (rozwiń, aby zmienić)",
        "why_dt": "Typ dokumentu niepewny", "why_tour": "Nie odczytano numeru trasy", "why_other": "inna trasa: {tour}",
        "why_discard": "Abholschein – zostanie odrzucony", "why_conf": "potwierdzenie zbiorcze",
        "s1_intro": "Kliknij ramkę TA = skreślone / nie jedzie (ponownie = cofnij). Nieczytelne TA wpisać. "
                    "Brak TA: „narysuj ramkę TA”, zaznacz wiersz, wpisz numer.",
        "s1_none": "Brak listy załadunkowej – bez niej nie ma porównania TA.",
        "ta_draw": "narysuj ramkę TA", "ta_read": "odczytano", "ta_unread": "nieczytelne – wpisać",
        "ta_drawn": "narysowano", "struck": "skreślone", "strike": "skreśl", "unstrike": "cofnij",
        "loaded_n": "załadowano TA: {n}", "struck_n": "skreślono: {n}",
        "ll_missing": "Brak strony {i} z {n} listy załadunkowej",
        "s2_unread": "Nie odczytano numeru dowodu dostawy – kliknij stronę, wpisz numer",
        "s2_intro": "Jeden wiersz na TA z listy załadunkowej, strony od lewej do prawej, kopie pod spodem. Kliknięcie "
                    "kafelka = duży widok. Dowód dostawy jest ważny z pieczątką lub podpisem na jednej z jego stron.",
        "s2_extra": "Dowody dostawy z numerem spoza listy załadunkowej",
        "s2_struck": "Dowody dostawy do skreślonych TA", "no_ls": "brak dowodu dostawy",
        "page_missing": "brak strony {i}", "carrier": "Hermes/DHL – sprawdzić potwierdzenie zbiorcze",
        "s3_unread": "Nie odczytano numeru CMR (i/n) – kliknij stronę, wpisz numer",
        "s3_intro": "CMR 1..n od lewej do prawej, kopie pod spodem. Wymagane pieczątka i podpis.",
        "cmr_missing": "brak CMR {i}", "cmr_conflict": "Sprzeczna łączna liczba CMR: {totals}",
        "ta_no_cmr": "TA bez CMR", "ta_cmr_extra": "TA na CMR, ale nie na liście załadunkowej",
        "s4_intro": "Tu zebrane są wszystkie braki. Każdy punkt można zaakceptować z powodem. Dopiero po "
                    "„Potwierdź listę braków” make finalize utworzy szkice e-maili.",
        "sum_cmr": "CMR", "sum_ls": "dowody dostawy", "sum_struck": "skreślone TA", "sum_corr": "poprawione strony",
        "sum_boxes": "narysowane ramki", "reviewer": "Sprawdzający",
        "missing_none": "Niczego nie brakuje.", "accept": "mimo to zaakceptuj", "accepted": "zaakceptowano",
        "undo": "cofnij", "note": "uwaga", "cancel": "anuluj", "choose": "– wybierz –",
        "note_needed": "Przy „Inne” proszę wpisać uwagę.",
        "confirm_missing": "Potwierdź listę braków – zwolnij szkice e-maili",
        "missing_confirmed": "Lista braków potwierdzona",
        "missing_changed": "Lista zmieniła się od potwierdzenia – proszę potwierdzić ponownie.",
        "save_need_name": "Najpierw wpisz swoje imię i nazwisko w polu „Sprawdzający”.",
        "save_open": "Nie wszystkie kroki są potwierdzone ({steps}). Zapisać mimo to? (Zamknięcie jest możliwe "
                     "dopiero po potwierdzeniu wszystkich.)",
        "save_unconfirmed": "Lista braków nie jest potwierdzona – make finalize nie utworzy szkiców e-maili. "
                            "Zapisać mimo to?",
        "saved": "Zapisano. Plik entscheidung.json umieść w folderze tej strony, potem: make finalize RUN={name}",
        "loaded": "Wczytano zapisany stan z przeglądarki.", "confirm_discard": "Odrzucić wszystkie wpisy na tej stronie?",
        "page": "str. {n}", "doctype": "Typ dokumentu", "tour": "Numer trasy", "tour_this": "= {tour}",
        "cmr_count": "nr CMR (i/n)", "ls_number": "nr dowodu dostawy", "ls_page": "strona (i/n)", "ta_field": "TA",
        "present": "jest", "absent": "brak", "model": "model", "ocr_read": "odczytano",
        "h_obj": "Podpis / pieczątka", "missing_cls": "brak: {cls}",
        "hint_draw": "Narysuj ramkę (B) lub kliknij ramkę modelu",
        "hint_reject": "Ramki modelu = fałszywy alarm – kliknięcie zachowuje jedną",
        "draw": "narysuj ramkę", "drawing": "Zaznacz ramkę … (Esc = anuluj)", "boxes_person": "Twoje ramki",
        "copies": "kopie: {pages}", "dup": "kopia – nie będzie archiwizowana", "archive_this": "archiwizuj tę",
        "valid": "ważny", "invalid": "nieważny", "open": "otwarte",
        "iss_doctype": "wybierz typ dokumentu", "iss_tour": "wpisz numer trasy", "iss_ls": "wpisz numer dowodu dostawy",
        "iss_cmr": "wpisz numer CMR i/n", "iss_decide": "rozstrzygnij pieczątkę/podpis",
        "iss_box": "narysuj ramkę: {cls}", "iss_ta": "wpisz lub skreśl TA",
        "v_full": "cała strona", "v_area": "obszar kontroli", "v_num": "numer",
        "prev": "← wstecz", "next": "dalej →", "close": "gotowe (Esc)",
        "keys": "Klawisze: 1 podpis · 2 pieczątka · B ramka · Enter następna otwarta · ←/→ · Esc zamknij · "
                "kółko myszy = zoom, przeciąganie przesuwa",
        "img_missing": "Brak obrazu: ", "none": "brak", "bad_number": "Proszę wpisać numer 8-cyfrowy.",
    },
}

# what the page needs of a page record (OCR texts of the header etc. stay in ergebnis.json)
PAGE_KEYS = ("n", "id", "image", "source", "w", "h", "doc_type", "doc_reason", "dets", "masked", "proposals",
             "scores", "tour", "cmr_count", "ta", "ta_unread", "ls_number", "ls_page", "ls_read", "page_of",
             "view", "mask_found", "carrier")


def page_data(result: dict, lang: str) -> dict:
    classes = result["classes"]
    return {
        "name": result["name"], "tour": result["tour"], "created": result["created"],
        "rules": result["rules"], "doc_types": result["doc_types"], "ta_validated": bool(result.get("ta_validated")),
        "thr": result["thresholds"]["accept"], "classes": classes,
        "colors": {c: CLASS_COLORS[i % len(CLASS_COLORS)] for i, c in enumerate(classes)},
        "pages": [{k: p.get(k) for k in PAGE_KEYS} for p in result["pages"]],
    }


def write_review(out_dir: Path, result: dict, lang: str = "de") -> Path:
    t = UI[lang]
    js_t = dict(t, cls=CLASS_NAMES[lang], dt=DOC_TYPE_NAMES[lang], reasons=REASONS[lang],
                items={k: v for k, v in MSG[lang].items() if k.startswith("item_")}, pages_list=MSG[lang]["pages"])
    page = TEMPLATE
    for k, v in t.items():
        if isinstance(v, str):
            page = page.replace("{{" + k + "}}", html.escape(v))
    title = f"{t['title']} {result['tour'] or result['name']}"
    page = (page.replace("__TITLE__", html.escape(title))
            .replace("__I18N__", json.dumps(js_t, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__DATA__", json.dumps(page_data(result, lang), ensure_ascii=False).replace("</", "<\\/")))
    path = out_dir / f"pruefung{SUFFIX[lang]}.html"
    path.write_text(page, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="{{html_lang}}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#d9d9de;--panel:#f5f5f7;--sel:#1f6feb;--ok:#2b8a3e;
  --okbg:#ebfbee;--err:#c92a2a;--errbg:#fff5f5;--warn:#9a5b00;--warnbg:#fff4e6}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 system-ui,sans-serif;color:var(--fg);background:var(--bg)}
header{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;padding:8px 16px;
  border-bottom:1px solid var(--line);background:var(--bg);flex-wrap:wrap}
header h1{font-size:16px;margin:0 8px 0 0}
button,select,input{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--fg)}
button{cursor:pointer} button:disabled{opacity:.45;cursor:default}
button.primary{background:var(--sel);color:#fff;border-color:var(--sel)}
.muted{color:var(--muted)} .small{font-size:12px}
#stepper{display:flex;gap:4px;flex-wrap:wrap}
#stepper button{display:flex;gap:6px;align-items:center}
#stepper button.cur{background:var(--fg);color:#fff;border-color:var(--fg)}
#stepper button.done .no{background:var(--ok)}
#stepper .no{display:inline-block;width:20px;height:20px;border-radius:10px;background:var(--muted);color:#fff;font-size:12px;line-height:20px;text-align:center}
main{max-width:1800px;margin:0 auto;padding:8px 16px 60px}
h2{font-size:17px;margin:14px 0 6px} h3{font-size:15px;margin:14px 0 6px}
#notice{display:none;padding:6px 16px;background:var(--warnbg);border-bottom:1px solid var(--line)}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.issues{color:var(--err)}
.tiles{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start}
.tile{width:190px;border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;background:#fff;cursor:pointer;outline:none;font-size:12px}
.tile:focus{box-shadow:0 0 0 3px rgba(31,111,235,.45)}
.tile.v-ok{border-left-color:var(--ok)} .tile.v-bad{border-left-color:var(--err)} .tile.v-open{border-left-color:var(--warn)}
.tile.issue{border-color:var(--warn);border-style:dashed;border-left-style:solid}
.tile.dup{opacity:.5}
.tile .th{display:flex;justify-content:space-between;gap:4px;padding:2px 6px;border-bottom:1px solid var(--line)}
.tile .tf{display:flex;gap:4px;flex-wrap:wrap;padding:2px 6px;border-top:1px solid var(--line)}
.thumb{position:relative;overflow:hidden;width:100%;background:var(--panel)}
.thumb img{position:absolute;display:block;user-select:none;pointer-events:none}
.thumb .b{position:absolute;border:2px solid;pointer-events:none}
.ph{width:190px;min-height:120px;border:2px dashed var(--err);border-radius:6px;background:var(--errbg);color:var(--err);padding:8px;font-size:12px}
.ph.acc{border-color:var(--ok);background:var(--okbg);color:var(--ok)}
.st{font-weight:700} .st.y{color:var(--ok)} .st.n{color:var(--err)} .st.q{color:var(--warn)}
.chip{border:1px solid var(--line);border-radius:5px;padding:0 5px;font-size:11px}
.chip.ok{background:var(--okbg);border-color:var(--ok);color:var(--ok)} .chip.bad{background:var(--errbg);border-color:var(--err);color:var(--err)}
.row{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line)}
.row .lab{width:200px;flex:none}
.row .lab b{font-size:15px}
.cells{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:6px}
.col .ch{font-size:12px;font-weight:600}
.pill{font-size:12px;padding:1px 8px;border-radius:10px;border:1px solid var(--line);display:inline-block}
.pill.ok{background:var(--okbg);color:var(--ok);border-color:var(--ok)} .pill.bad{background:var(--errbg);color:var(--err);border-color:var(--err)}
.pill.open{background:var(--warnbg);color:var(--warn);border-color:var(--warn)}
.tag{font-size:12px;padding:0 6px;border-radius:4px;background:var(--warnbg);color:var(--warn);display:inline-block;margin-top:3px}
a.lnk,a[data-open]{cursor:pointer;color:var(--sel)}
.acc{color:var(--ok);font-size:12px} .accbtn{font-size:12px;padding:1px 8px;margin-top:4px}
.accform{display:inline-flex;gap:4px;flex-wrap:wrap;margin-top:4px} .accform input{width:150px}
ul.items{list-style:none;padding:0;margin:0} ul.items li{padding:5px 10px;border-radius:6px;margin-bottom:4px}
ul.items li.fehler{background:var(--errbg)} ul.items li.hinweis{background:var(--warnbg)} ul.items li.ok{background:var(--okbg)}
.ll{display:flex;gap:14px;align-items:flex-start;margin-bottom:20px}
.ll .vbox{flex:1;height:78vh;min-width:300px}
.ll .list{width:380px;flex:none}
.ll table{border-collapse:collapse;width:100%} .ll td{padding:3px 4px;border-bottom:1px solid var(--line)}
.ll tr.struck input{text-decoration:line-through;color:var(--err)}
.ll input.ta{width:110px}
.vw{position:relative;overflow:hidden;width:100%;height:100%;background:#e9e9ee;border:1px solid var(--line);cursor:grab;user-select:none}
.vw.drawing{cursor:crosshair}
.vin{position:absolute;left:0;top:0;transform-origin:0 0}
.vin img{display:block;width:100%;height:100%;pointer-events:none}
.vin .b{position:absolute;border:3px solid;cursor:pointer}
.vin .b span{position:absolute;left:-3px;top:-20px;color:#fff;font-size:13px;padding:0 4px;white-space:nowrap;border-radius:2px}
.vin .b.weak{border-style:dashed;border-width:2px;opacity:.75}
.vin .b.rej{border-style:dashed;border-color:var(--err)!important;opacity:.8}
.vin .b.rej span{background:var(--err)!important}
.vin .b.struck{background:repeating-linear-gradient(-20deg,transparent 0 8px,rgba(201,42,42,.35) 8px 11px)}
.vin .b.person{border-width:4px}
.vin .tmp{position:absolute;border:2px dashed #000;background:rgba(31,111,235,.15)}
.vin .mask{position:absolute;pointer-events:none;background:repeating-linear-gradient(45deg,rgba(110,110,115,.35) 0 6px,transparent 6px 12px)}
#ov{display:none;position:fixed;inset:0;z-index:20;background:#fff}
#ov.on{display:flex}
#ovimg{flex:1;padding:8px}
#ovside{width:400px;flex:none;border-left:1px solid var(--line);padding:12px;overflow:auto}
#ovside label{display:block;margin:6px 0 2px;font-size:12px;color:var(--muted)}
#ovside input.num{width:200px;font-size:16px}
.obj{display:flex;align-items:center;gap:6px;margin:6px 0;flex-wrap:wrap}
.obj .nm{width:100px;font-weight:600}
.obj button.on.y{background:var(--ok);border-color:var(--ok);color:#fff}
.obj button.on.n{background:var(--err);border-color:var(--err);color:#fff}
.hint{font-size:12px;color:var(--warn)}
.nav{display:flex;gap:6px;margin-top:14px;flex-wrap:wrap}
.vbtns{display:flex;gap:4px;margin:6px 0;flex-wrap:wrap}
.vbtns button{font-size:12px;padding:2px 8px}
details summary{cursor:pointer;margin:10px 0}
.sum{display:flex;gap:18px;flex-wrap:wrap;margin:8px 0}
.sum div{padding:8px 12px;border:1px solid var(--line);border-radius:8px} .sum b{font-size:20px;display:block}
</style></head><body>
<header>
  <h1 id="title"></h1>
  <div id="stepper"></div>
  <span style="flex:1"></span>
  <button id="discard">{{discard}}</button>
  <button id="save" class="primary">{{save}}</button>
</header>
<div id="notice"></div>
<main id="main"></main>
<div id="ov"><div id="ovimg"></div><div id="ovside"></div></div>
<script>
const D = __DATA__;
const T = __I18N__;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => o[k]);
const REVIEW = ["cmr", "lieferschein"], OBJ = ["unterschrift", "stempel"];
const SINGLE = ["tour_nummer", "cmr_count", "ls_nummer", "seitenzahl"];
const byN = {}; D.pages.forEach(p => byN[p.n] = p);
const KEY = "docval-pruefung2:" + D.name + ":" + D.created;
let S = {reviewer: "", pages: {}, steps: {}, accepted: {}, cur: null};
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.pages) { S = Object.assign(S, s); notice(T.loaded); } } catch (e) {}
let dirty = true, G = null, TM = null;
function persist() { dirty = true; TM = null; try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
function notice(msg) { const n = $("notice"); n.textContent = msg; n.style.display = msg ? "block" : "none"; }
const thrOf = c => D.thr[c] != null ? D.thr[c] : 0.5;

// ------------------------------------------------------------ effective values (person > model)
const us = p => S.pages[p.n] || (S.pages[p.n] = {});
const has = (p, k) => S.pages[p.n] && S.pages[p.n][k] != null && S.pages[p.n][k] !== "";
const docType = p => has(p, "doc_type") ? S.pages[p.n].doc_type : p.doc_type;
const reviewable = p => REVIEW.includes(docType(p));
function parseCount(s) { const m = /^\s*(?:cmr)?\s*(\d{1,3})\s*\/\s*(\d{1,3})\s*$/i.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] ? [+m[1], +m[2]] : null; }
function parse8(s) { const out = []; for (const m of String(s || "").matchAll(/(?<!\d)(?:\d ?){7}\d(?!\d)/g)) { const n = m[0].replace(/ /g, ""); if (!out.includes(n)) out.push(n); } return out; }
function parsePageOf(s) { const m = /(\d{1,2})\s*\/\s*(\d{1,2})/.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] ? [+m[1], +m[2]] : null; }
const cmrCount = p => has(p, "cmr") ? parseCount(S.pages[p.n].cmr) : (p.cmr_count && p.cmr_count.parsed) || null;
const ownTour = p => has(p, "tour") ? S.pages[p.n].tour.trim() : (p.tour && p.tour.accepted ? p.tour.text : null);
// the tour number is printed on the front page of a Lieferschein only: following pages take the
// tour of the page with the same number, else (page 2/2 ...) count to this tour - as organize.py
const backPage = p => docType(p) === "lieferschein" && (lsPage(p) || [1])[0] > 1;
function lsTours() {   // Lieferschein number -> tour read on one of its pages (cached until the next change)
  if (TM) return TM;
  TM = {};
  for (const q of D.pages) if (docType(q) === "lieferschein") { const n = lsNumber(q), t = ownTour(q); if (n && t && !(n in TM)) TM[n] = t; }
  return TM;
}
function tourOf(p) {
  const t = ownTour(p);
  if (t || docType(p) !== "lieferschein") return t;
  const num = lsNumber(p);
  if (num && lsTours()[num]) return lsTours()[num];
  return backPage(p) ? D.tour : null;
}
const otherTour = p => { const t = tourOf(p); return reviewable(p) && t && D.tour && t !== D.tour ? t : null; };
const lsNumber = p => has(p, "ls") ? (parse8(S.pages[p.n].ls)[0] || null) : p.ls_number || null;
const lsPage = p => has(p, "ls_page") ? parsePageOf(S.pages[p.n].ls_page) : p.ls_page || null;
const cmrTAs = p => has(p, "ta") ? parse8(S.pages[p.n].ta) : (p.ta || []).map(t => t.ta);
const rule = p => D.rules[docType(p)] || {require: [], mode: "all"};
function proposal(p, c) { const pr = (p.proposals || {})[docType(p)]; const v = pr && pr.classes[c]; return v === "ja" ? true : v === "nein" ? false : null; }
function val(p, c) { const s = S.pages[p.n]; return s && s.v && c in s.v ? s.v[c] : proposal(p, c); }
function valid(p) {   // one page on its own
  const r = rule(p), vs = r.require.map(c => val(p, c));
  if (!vs.length) return true;
  if (r.mode === "any") return vs.some(v => v === true) ? true : vs.some(v => v === null) ? null : false;
  return vs.some(v => v === false) ? false : vs.some(v => v === null) ? null : true;
}
const okTA = t => /^\d{8}$/.test(t || "");
const pagesText = ns => fmt(T.pages_list, {list: ns.join(", ")});

// ------------------------------------------------------------ copies (duplicates), decided live
function rankKey(p) { const r = rule(p), v = valid(p); return [v === true ? 1 : v === null ? 0 : -1, r.require.filter(c => val(p, c) === true).length, r.require.reduce((a, c) => a + ((p.scores || {})[c] || 0), 0), -p.n]; }
function cmpRank(a, b) { const x = rankKey(a), y = rankKey(b); for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return y[i] - x[i]; return 0; }
function groups() {
  if (!dirty && G) return G;
  const ls = {}, cmr = {}, arch = {};
  for (const p of D.pages) {
    if (otherTour(p)) continue;
    const t = docType(p);
    if (t === "lieferschein") { const num = lsNumber(p); if (!num) continue; const pg = lsPage(p); const k = num + "#" + (pg ? pg[0] : "?" + p.n); (ls[k] = ls[k] || []).push(p); }
    else if (t === "cmr") { const c = cmrCount(p); if (c) (cmr[c[0]] = cmr[c[0]] || []).push(p); }
  }
  for (const g of [...Object.values(ls), ...Object.values(cmr)]) {
    if (g.some(p => S.pages[p.n] && S.pages[p.n].archive === true)) {
      g.forEach(p => arch[p.n] = !!(S.pages[p.n] && S.pages[p.n].archive === true));
      g.sort((a, b) => (arch[b.n] ? 1 : 0) - (arch[a.n] ? 1 : 0) || cmpRank(a, b));
    } else { g.sort(cmpRank); g.forEach((p, i) => arch[p.n] = i === 0); }
  }
  G = {ls, cmr, arch}; dirty = false; return G;
}
const archive = p => { const a = groups().arch[p.n]; return a == null ? true : a; };
function copiesOf(p) { const g = groups(); for (const x of [...Object.values(g.ls), ...Object.values(g.cmr)]) if (x.includes(p)) return x; return [p]; }
function archiveThis(p) { for (const q of copiesOf(p)) us(q).archive = q === p; }
const lsPagesThisTour = () => D.pages.filter(p => docType(p) === "lieferschein" && !otherTour(p));
function lsByNumber() {   // number -> archived pages
  const out = {};
  for (const p of lsPagesThisTour()) { const num = lsNumber(p); if (num && archive(p)) (out[num] = out[num] || []).push(p); }
  return out;
}
function docValid(num) {   // Lieferschein: stamp or signature on any of its pages
  const vs = (lsByNumber()[num] || []).map(valid);
  return vs.some(v => v === true) ? true : vs.some(v => v === null) ? null : false;
}
function unitValid(p) { return docType(p) === "lieferschein" && lsNumber(p) && archive(p) ? docValid(lsNumber(p)) : valid(p); }

// ------------------------------------------------------------ loading list
function llEntries(p) {
  const s = us(p);
  if (!s.tl) s.tl = [...(p.ta || []).map(t => ({ta: t.ta, box: t.box || null, src: "model"})),
                     ...(p.ta_unread || []).map(u => ({ta: "", box: u.box, src: "model", unread: true}))];
  return s.tl;
}
const llPages = () => D.pages.filter(p => docType(p) === "loading_list");
function loaded() { const out = []; for (const p of llPages()) for (const e of llEntries(p)) if (!e.struck && okTA(e.ta) && !out.includes(e.ta)) out.push(e.ta); return out; }
function struckTAs() { const L = loaded(), out = []; for (const p of llPages()) for (const e of llEntries(p)) if (e.struck && okTA(e.ta) && !L.includes(e.ta) && !out.includes(e.ta)) out.push(e.ta); return out; }

// ------------------------------------------------------------ boxes: model boxes kept/rejected + the person's
const sameBox = (a, b) => !!(a && b) && a.every((v, i) => Math.abs(v - b[i]) < 1e-3);
function topOf(p, cls) { return p.dets.filter(x => x.cls === cls).reduce((a, b) => !a || b.score > a.score ? b : a, null); }
function detInc(p, d, i) {
  const ov = ((S.pages[p.n] || {}).bx || {})[i];
  if (ov != null) return ov;
  const sure = d.score >= thrOf(d.cls), anySure = p.dets.some(x => x.cls === d.cls && x.score >= thrOf(x.cls));
  if (OBJ.includes(d.cls) && reviewable(p)) {
    const v = val(p, d.cls);
    if (v === false) return false;
    if (v === true) return sure || (!anySure && topOf(p, d.cls) === d);   // a weak box confirmed by "present"
    return sure;
  }
  if (d.cls === "ta_nummer") return sure || [...(p.ta || []), ...(p.ta_unread || [])].some(t => sameBox(t.box, d.box));
  if (SINGLE.includes(d.cls)) return sure || (!anySure && topOf(p, d.cls) === d);   // the box that was read
  return sure;
}
function finalBoxes(p) {
  const pos = [], neg = [], ov = (S.pages[p.n] || {}).bx || {};
  p.dets.forEach((d, i) => {
    if (detInc(p, d, i)) pos.push({cls: d.cls, box: d.box, src: "modell", score: d.score});
    else if (d.score >= thrOf(d.cls) || ov[i] === false) neg.push({cls: d.cls, box: d.box, score: d.score});
  });
  for (const b of (S.pages[p.n] || {}).pb || []) pos.push({cls: b.cls, box: b.box, src: "person"});
  return {pos, neg};
}
const hasPos = (p, cls) => finalBoxes(p).pos.some(b => b.cls === cls);
function corrected(p) {
  const s = S.pages[p.n] || {};
  if ((s.pb || []).length || Object.keys(s.bx || {}).length) return true;
  if (["doc_type", "ls", "ls_page", "cmr", "tour", "ta"].some(k => has(p, k))) return true;
  if ((s.tl || []).some(e => e.src === "person" || (e.ta && !(p.ta || []).some(t => t.ta === e.ta)))) return true;
  return OBJ.some(c => s.v && c in s.v && s.v[c] !== proposal(p, c));
}

// ------------------------------------------------------------ steps
const stepOf = p => { const t = docType(p); return t === "lieferschein" ? 2 : t === "cmr" ? 3 : t === "loading_list" ? 1 : 0; };
function pageIssues(p) {   // [{step, text, box}]
  const out = [], t = docType(p);
  const add = (step, text, box) => out.push({step, text, box});
  const needBox = (step, cls) => add(step, fmt(T.iss_box, {cls: T.cls[cls] || cls}), cls);
  if (t === "unsicher" || !t) add(0, T.iss_doctype);
  if (REVIEW.includes(t)) {
    if (!tourOf(p)) add(0, T.iss_tour);
    if (has(p, "tour") && !hasPos(p, "tour_nummer")) needBox(0, "tour_nummer");
  }
  if (otherTour(p)) return out;
  if (t === "lieferschein") {
    if (!lsNumber(p)) add(2, T.iss_ls);
    else if (has(p, "ls") && !hasPos(p, "ls_nummer")) needBox(2, "ls_nummer");
    if (has(p, "ls_page") && !hasPos(p, "seitenzahl")) needBox(2, "seitenzahl");
  }
  if (t === "cmr") {
    if (!cmrCount(p)) add(3, T.iss_cmr);
    else if (has(p, "cmr") && !hasPos(p, "cmr_count")) needBox(3, "cmr_count");
    if (has(p, "ta") && cmrTAs(p).length && !hasPos(p, "ta_nummer")) needBox(3, "ta_nummer");
  }
  if (REVIEW.includes(t) && archive(p)) {
    if (unitValid(p) === null && valid(p) === null) add(stepOf(p), T.iss_decide);
    for (const c of rule(p).require) if (val(p, c) === true && !hasPos(p, c)) needBox(stepOf(p), c);
  }
  return out;
}
function stepIssues(k) {
  const out = [];
  for (const p of D.pages) for (const x of pageIssues(p)) if (x.step === k) out.push({p, ...x});
  if (k === 1) for (const p of llPages()) for (const e of llEntries(p)) if (!e.struck && !okTA(e.ta)) out.push({p, step: 1, text: T.iss_ta});
  return out;
}
function problemPages() {
  return D.pages.filter(p => p.doc_type === "unsicher" || pageIssues(p).some(x => x.step === 0) || otherTour(p)
    || ["abholschein", "bestaetigung"].includes(docType(p)) || (REVIEW.includes(docType(p)) && !tourOf(p) && !has(p, "tour")));
}
function stepDone(k) {
  if (stepIssues(k).length) return false;
  if (k === 0 && !problemPages().length) return true;
  if (k === 1 && !llPages().length) return true;
  return !!S.steps[k];
}
const canEnter = k => { for (let j = 0; j < k; j++) if (!stepDone(j)) return false; return true; };
function changed(k) { for (let j = k + 1; j <= 4; j++) S.steps[j] = false; persist(); }
function pageConfirmed(p) { return stepDone(0) && stepDone(Math.min(stepOf(p), 3)); }

// ------------------------------------------------------------ missing list (mirrors organize.py / finalize.py)
function missingPages(list) {
  const got = list.filter(Boolean); if (!got.length) return [];
  const n = Math.max(...got.map(x => x[1])), seen = new Set(got.map(x => x[0])), out = [];
  for (let i = 1; i <= n; i++) if (!seen.has(i)) out.push(i);
  return out;
}
function cmrInfo() {
  const g = groups(), tot = new Set(), unread = [];
  for (const p of D.pages) if (docType(p) === "cmr" && !otherTour(p)) { const c = cmrCount(p); if (c) { if (archive(p)) tot.add(c[1]); } else unread.push(p); }
  const N = Math.max(0, ...tot, ...Object.keys(g.cmr).map(Number));
  return {by: g.cmr, tot, N, unread};
}
const missCls = pages => rule(pages[0]).require.filter(c => !pages.some(q => val(q, c) === true)).map(c => fmt(T.missing_cls, {cls: T.cls[c] || c})).join(", ") || "?";
function missingItems() {
  const it = [], I = T.items, acc = S.accepted || {};
  const add = (key, code, level, params, go) => it.push({key, level, go, accepted: !!acc[key], text: fmt(I[code], params)});
  const ci = cmrInfo();
  if (ci.tot.size === 1) { const total = [...ci.tot][0]; for (let i = 1; i <= total; i++) if (!(ci.by[i] || []).some(archive)) add("cmr:" + i, "item_cmr", "fehler", {i, total}); }
  const byNum = lsByNumber();
  for (const num of Object.keys(byNum).sort()) {
    const pgs = byNum[num].map(lsPage), total = Math.max(0, ...pgs.filter(Boolean).map(x => x[1]));
    for (const i of missingPages(pgs)) add(`ls:${num}:${i}`, "item_ls_page", "fehler", {number: num, i, total});
  }
  const ll = llPages();
  if (ll.length) {
    const pos = ll.map(p => p.page_of), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1]));
    for (const i of missingPages(pos)) add("ll:" + i, "item_ll_page", "fehler", {i, total});
    const L = loaded();
    if (L.length) {
      const lvl = D.ta_validated ? "fehler" : "hinweis", ex = struckTAs(), cmrT = [];
      D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).forEach(p => cmrTAs(p).forEach(t => { if (!cmrT.includes(t)) cmrT.push(t); }));
      const lsN = Object.keys(byNum).sort();
      L.filter(t => !cmrT.includes(t)).forEach(t => add("ta_cmr:" + t, "item_ta_cmr", lvl, {ta: t}));
      cmrT.filter(t => !L.includes(t) && !ex.includes(t)).forEach(t => add("ta_cmr_extra:" + t, "item_ta_cmr_extra", lvl, {ta: t}));
      L.filter(t => !lsN.includes(t)).forEach(t => add("ta_ls:" + t, "item_ta_ls", lvl, {ta: t}));
      lsN.filter(t => !L.includes(t) && !ex.includes(t)).forEach(t => add("ta_ls_extra:" + t, "item_ta_ls_extra", lvl, {ta: t}));
    }
  }
  for (const p of D.pages) if (docType(p) === "cmr" && archive(p) && !otherTour(p) && valid(p) === false)
    add("page:" + p.n, "item_page", "fehler", {title: cardTitle(p), page: pagesText([p.n]), missing: missCls([p])}, p.n);
  for (const num of Object.keys(byNum).sort()) if (docValid(num) === false)
    add("ls_doc:" + num, "item_page", "fehler", {title: (T.dt.lieferschein || "Lieferschein") + " " + num, page: pagesText(byNum[num].map(q => q.n)), missing: missCls(byNum[num])}, byNum[num][0].n);
  for (const p of lsPagesThisTour()) if (!lsNumber(p) && valid(p) === false)
    add("page:" + p.n, "item_page", "fehler", {title: cardTitle(p), page: pagesText([p.n]), missing: missCls([p])}, p.n);
  return it.sort((a, b) => (a.level === "fehler" ? 0 : 1) - (b.level === "fehler" ? 0 : 1));
}
const missingKeys = items => items.map(x => x.key).sort();
const missingConfirmed = items => !items.length || (!!S.missing_keys && JSON.stringify(S.missing_keys) === JSON.stringify(missingKeys(items)));
function cardTitle(p) {
  const dt = docType(p), cc = cmrCount(p);
  if (dt === "cmr") return cc ? `CMR ${cc[0]}/${cc[1]}` : "CMR ?";
  let t = T.dt[dt] || dt;
  if (dt === "lieferschein") { const num = lsNumber(p), pg = lsPage(p); if (num) t += " " + num; if (pg) t += ` (${pg[0]}/${pg[1]})`; }
  return t;
}

// ------------------------------------------------------------ accept anyway
let accOpen = null;
function accHtml(key) {
  const a = (S.accepted || {})[key];
  if (a) return `<div class="acc">✓ ${T.accepted}: ${esc(T.reasons[a.reason] || a.reason)}${a.note ? " – " + esc(a.note) : ""} <a class="lnk" data-unacc="${esc(key)}">${T.undo}</a></div>`;
  if (accOpen === key) return `<div class="accform"><select data-accr><option value="">${T.choose}</option>${Object.entries(T.reasons).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select><input data-accn placeholder="${esc(T.note)}"><button data-accok="${esc(key)}">OK</button><button data-acccancel="1">${T.cancel}</button></div>`;
  return `<button class="accbtn" data-acc="${esc(key)}">${T.accept}</button>`;
}

// ------------------------------------------------------------ tiles
function thumbHtml(p, v) {
  const [x1, y1, x2, y2] = v, rw = x2 - x1, rh = y2 - y1;
  const pos = b => `left:${(b[0] - x1) / rw * 100}%;top:${(b[1] - y1) / rh * 100}%;width:${(b[2] - b[0]) / rw * 100}%;height:${(b[3] - b[1]) / rh * 100}%`;
  let h = `<img src="${esc(p.image)}" alt="" style="width:${100 / rw}%;left:${-x1 / rw * 100}%;top:${-y1 / rh * 100}%">`;
  for (const b of finalBoxes(p).pos) if (OBJ.includes(b.cls)) h += `<div class="b" style="${pos(b.box)};border-color:${D.colors[b.cls] || "#000"}"></div>`;
  return `<div class="thumb" style="aspect-ratio:${rw * p.w} / ${rh * p.h}">${h}</div>`;
}
function stIcons(p) {
  return rule(p).require.map(c => { const v = val(p, c); return `<span class="st ${v === true ? "y" : v === false ? "n" : "q"}" title="${esc(T.cls[c])}">${(T.cls[c] || c)[0].toUpperCase()}${v === true ? "✓" : v === false ? "✗" : "?"}</span>`; }).join(" ");
}
function tileHtml(p, step, opts = {}) {
  const iss = pageIssues(p).filter(x => x.step === step);
  const v = unitValid(p), full = opts.full || !reviewable(p);
  const cls = "tile " + (!archive(p) ? "dup " : "") + (iss.length ? "issue " : "") + (reviewable(p) ? (v === true ? "v-ok" : v === false ? "v-bad" : "v-open") : "");
  let foot = reviewable(p) ? stIcons(p) : "";
  if (opts.foot) foot += opts.foot;
  if (!archive(p)) foot += ` <span class="muted">${T.dup}</span>`;
  return `<div class="${cls}" tabindex="0" data-open="${p.n}" data-step="${step}"><div class="th"><b>${esc(opts.label || cardTitle(p))}</b><span class="muted">${fmt(T.page, {n: p.n})}</span></div>
    ${thumbHtml(p, full ? [0, 0, 1, 1] : (p.view || [0, 0, 1, 1]))}<div class="tf">${foot}${iss.length ? `<span class="issues">· ${esc(iss[0].text)}${iss.length > 1 ? " +" + (iss.length - 1) : ""}</span>` : ""}</div></div>`;
}
const phHtml = (text, key) => `<div class="ph${key && (S.accepted || {})[key] ? " acc" : ""}">${esc(text)}${key ? accHtml(key) : ""}</div>`;
function confirmBar(k) {
  const iss = stepIssues(k), done = stepDone(k);
  return `<div class="bar" id="bar${k}">${done ? `<span class="pill ok">✓ ${T.step_done}</span>` : ""}
    ${iss.length ? `<span class="issues">${fmt(T.open_issues, {n: iss.length})}: ${iss.slice(0, 6).map(x => `<a data-open="${x.p.n}" data-step="${k}">${fmt(T.page, {n: x.p.n})}</a> ${esc(x.text)}`).join(" · ")}${iss.length > 6 ? " …" : ""}</span>` : ""}
    <span style="flex:1"></span><span class="muted small">${T.step_reset}</span>
    ${k < 4 ? `<button class="primary" data-confirm="${k}"${iss.length ? " disabled" : ""}>${T.step_confirm}</button>` : ""}</div>`;
}

// ------------------------------------------------------------ step 0: assign pages
function render0() {
  const prob = problemPages();
  let h = `<h2>0 · ${T.steps[0]}</h2><p class="muted">${prob.length ? T.s0_intro : T.s0_none}</p><div class="tiles">`;
  for (const p of prob) {
    const why = [];
    if (p.doc_type === "unsicher") why.push(T.why_dt);
    if (REVIEW.includes(docType(p)) && !(p.tour && p.tour.accepted) && !tourOf(p)) why.push(T.why_tour);
    if (otherTour(p)) why.push(fmt(T.why_other, {tour: otherTour(p)}));
    if (docType(p) === "abholschein") why.push(T.why_discard);
    if (docType(p) === "bestaetigung") why.push(T.why_conf);
    h += tileHtml(p, 0, {full: true, label: T.dt[docType(p)] || docType(p), foot: `<span class="small">${esc(why.join(" · "))}</span>`});
  }
  h += `</div><details${S.open0 ? " open" : ""} id="all0"><summary>${T.s0_all}</summary>`;
  const by = {};
  for (const p of D.pages) (by[docType(p)] = by[docType(p)] || []).push(p);
  for (const t of Object.keys(by)) {
    h += `<h3>${esc(T.dt[t] || t)} (${by[t].length})</h3><div class="tiles">` + by[t].map(p => `<div class="tile" style="width:130px" tabindex="0" data-open="${p.n}" data-step="0">
      <div class="th"><span>${fmt(T.page, {n: p.n})}</span></div>${thumbHtml(p, [0, 0, 1, 1])}<div class="tf"><select data-dt="${p.n}">${D.doc_types.concat(t === "unsicher" ? ["unsicher"] : []).map(x => `<option value="${x}"${x === t ? " selected" : ""}>${esc(T.dt[x] || x)}</option>`).join("")}</select></div></div>`).join("") + `</div>`;
  }
  return h + `</details>` + confirmBar(0);
}

// ------------------------------------------------------------ step 1: loading list
const LV = {};
function render1() {
  const ll = llPages();
  let h = `<h2>1 · ${T.steps[1]}</h2>`;
  if (!ll.length) return h + `<p>${T.s1_none}</p>` + confirmBar(1);
  h += `<p class="muted">${T.s1_intro}</p>`;
  const pos = ll.map(p => p.page_of), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1]));
  const miss = missingPages(pos);
  if (miss.length) h += `<div class="tiles">${miss.map(i => phHtml(fmt(T.ll_missing, {i, n: total}), "ll:" + i)).join("")}</div>`;
  for (const p of ll) h += `<h3>${fmt(T.page, {n: p.n})}${p.page_of ? ` · ${p.page_of[0]}/${p.page_of[1]}` : ""}</h3>
    <div class="ll"><div class="vbox" id="llv${p.n}"></div><div class="list" id="lll${p.n}">${llList(p)}</div></div>`;
  h += `<p id="llsum"><b>${fmt(T.loaded_n, {n: loaded().length})}</b> · ${fmt(T.struck_n, {n: struckTAs().length})}</p>`;
  return h + confirmBar(1);
}
function llList(p) {
  const es = llEntries(p);
  return `<table>${es.map((e, i) => `<tr class="${e.struck ? "struck" : ""}"><td><input class="ta" data-ll="${p.n}" data-i="${i}" value="${esc(e.ta)}" placeholder="12345678"></td>
    <td class="small ${!e.struck && !okTA(e.ta) ? "issues" : "muted"}">${e.struck ? T.struck : e.src === "person" ? T.ta_drawn : !okTA(e.ta) ? T.ta_unread : T.ta_read}</td>
    <td><button class="small" data-strike="${p.n}" data-i="${i}">${e.struck ? T.unstrike : T.strike}</button>${e.src === "person" ? ` <button class="small" data-delta="${p.n}" data-i="${i}">×</button>` : ""}</td></tr>`).join("")}</table>
    <p><button data-tadraw="${p.n}">${T.ta_draw}</button></p>`;
}
function mountLL() {
  for (const p of llPages()) {
    const el = $("llv" + p.n); if (!el) continue;
    const v = new Viewer(el, p, {
      boxes: () => llBoxes(p),
      click: k => { const i = +k.split(":")[1]; const e = llEntries(p)[i]; if (e) { e.struck = !e.struck; changed(1); refresh1(p); } },
      draw: box => { const es = llEntries(p); us(p).pb = (us(p).pb || []).concat([{cls: "ta_nummer", box}]); es.push({ta: "", box, src: "person"}); changed(1); refresh1(p);
        setTimeout(() => { const inp = document.querySelector(`input[data-ll="${p.n}"][data-i="${es.length - 1}"]`); if (inp) inp.focus(); }, 0); },
    });
    LV[p.n] = v; v.fit([0, 0, 1, 1], 0);
  }
}
function llBoxes(p) {
  const out = [];
  llEntries(p).forEach((e, i) => { if (e.box) out.push({key: "e:" + i, box: e.box, cls: "ta_nummer", label: e.struck ? T.struck : (e.ta || "?"), style: e.struck ? "struck" : okTA(e.ta) ? "" : "rej", person: e.src === "person"}); });
  return out;
}
function refresh1(p) {
  const l = $("lll" + p.n); if (l) l.innerHTML = llList(p);
  if (LV[p.n]) LV[p.n].render();
  renderStepper();
  const b = $("bar1"); if (b) b.outerHTML = confirmBar(1);
  const s = $("llsum"); if (s) s.innerHTML = `<b>${fmt(T.loaded_n, {n: loaded().length})}</b> · ${fmt(T.struck_n, {n: struckTAs().length})}`;
}

// ------------------------------------------------------------ step 2: Lieferscheine
function lsRowCells(num, pages) {
  const byI = {}, extra = [];
  for (const p of pages) { const pg = lsPage(p); if (pg) (byI[pg[0]] = byI[pg[0]] || []).push(p); else extra.push(p); }
  const n = Math.max(0, ...pages.map(lsPage).filter(Boolean).map(x => x[1]), ...Object.keys(byI).map(Number));
  let h = "";
  for (let i = 1; i <= n; i++) {
    const col = (byI[i] || []).sort((a, b) => (archive(b) ? 1 : 0) - (archive(a) ? 1 : 0));
    h += `<div class="col"><div class="ch">${i}/${n}</div>` + (col.length ? col.map(p => tileHtml(p, 2, {label: `${num} · ${i}/${n}`})).join("") : phHtml(fmt(T.page_missing, {i}), `ls:${num}:${i}`)) + `</div>`;
  }
  for (const p of extra) h += `<div class="col"><div class="ch">?</div>${tileHtml(p, 2)}</div>`;
  return h;
}
function lsRow(label, num, pages, accKey) {
  const v = pages.length ? docValid(num) : null;
  let lab = `<b>${esc(label)}</b><br>`;
  if (pages.length) lab += `<span class="pill ${v === true ? "ok" : v === false ? "bad" : "open"}">${v === true ? T.valid : v === false ? T.invalid : T.open}</span>`;
  if (v === false) lab += accHtml("ls_doc:" + num);
  if (pages.some(p => p.carrier)) lab += `<br><span class="tag">${T.carrier}</span>`;
  const cells = pages.length ? lsRowCells(num, pages) : phHtml(T.no_ls, accKey);
  return `<div class="row"><div class="lab">${lab}</div><div class="cells">${cells}</div></div>`;
}
function render2() {
  let h = `<h2>2 · ${T.steps[2]}</h2>`;
  const all = lsPagesThisTour(), unread = all.filter(p => !lsNumber(p));
  if (unread.length) h += `<h3 class="issues">${T.s2_unread}</h3><div class="tiles">${unread.map(p => tileHtml(p, 2, {full: true})).join("")}</div>`;
  h += `<p class="muted">${T.s2_intro}</p>`;
  const byNum = {};
  for (const p of all) { const num = lsNumber(p); if (num) (byNum[num] = byNum[num] || []).push(p); }
  const L = loaded(), struck = struckTAs();
  if (llPages().length) {
    for (const ta of L) h += lsRow("TA " + ta, ta, byNum[ta] || [], "ta_ls:" + ta);
    const extra = Object.keys(byNum).filter(n => !L.includes(n) && !struck.includes(n));
    if (extra.length) h += `<h3>${T.s2_extra}</h3>` + extra.map(n => lsRow(n, n, byNum[n]) + `<div>${accHtml("ta_ls_extra:" + n)}</div>`).join("");
    const st = Object.keys(byNum).filter(n => struck.includes(n));
    if (st.length) h += `<details><summary>${T.s2_struck} (${st.length})</summary>${st.map(n => lsRow(n, n, byNum[n])).join("")}</details>`;
  } else {
    const order = Object.keys(byNum).sort((a, b) => Math.min(...byNum[a].map(p => p.n)) - Math.min(...byNum[b].map(p => p.n)));
    h += order.map(n => lsRow(n, n, byNum[n])).join("");
  }
  return h + confirmBar(2);
}

// ------------------------------------------------------------ step 3: CMR
function render3() {
  let h = `<h2>3 · ${T.steps[3]}</h2>`;
  const ci = cmrInfo(), L = loaded(), struck = struckTAs();
  if (ci.unread.length) h += `<h3 class="issues">${T.s3_unread}</h3><div class="tiles">${ci.unread.map(p => tileHtml(p, 3, {full: true})).join("")}</div>`;
  h += `<p class="muted">${T.s3_intro}</p>`;
  if (ci.tot.size > 1) h += `<p class="issues">${fmt(T.cmr_conflict, {totals: [...ci.tot].map(t => "/" + t).join(", ")})}</p>`;
  const taChips = p => " " + cmrTAs(p).map(t => `<span class="chip ${!L.length ? "" : L.includes(t) ? "ok" : struck.includes(t) ? "" : "bad"}">${t}</span>`).join(" ");
  h += `<div class="cells">`;
  for (let i = 1; i <= ci.N; i++) {
    const col = (ci.by[i] || []).slice().sort((a, b) => (archive(b) ? 1 : 0) - (archive(a) ? 1 : 0));
    h += `<div class="col"><div class="ch">${i}/${[...ci.tot].join("|") || "?"}</div>` + (col.length ? col.map(p => tileHtml(p, 3, {foot: taChips(p)})).join("") : phHtml(fmt(T.cmr_missing, {i}), ci.tot.size === 1 ? "cmr:" + i : null)) + `</div>`;
  }
  h += `</div>`;
  if (L.length) {
    const cmrT = [];
    D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).forEach(p => cmrTAs(p).forEach(t => { if (!cmrT.includes(t)) cmrT.push(t); }));
    const noCmr = L.filter(t => !cmrT.includes(t)), extra = cmrT.filter(t => !L.includes(t) && !struck.includes(t));
    if (noCmr.length) h += `<h3>${T.ta_no_cmr}</h3><div class="tiles">${noCmr.map(t => phHtml("TA " + t, "ta_cmr:" + t)).join("")}</div>`;
    if (extra.length) h += `<h3>${T.ta_cmr_extra}</h3><div class="tiles">${extra.map(t => phHtml("TA " + t, "ta_cmr_extra:" + t)).join("")}</div>`;
  }
  return h + confirmBar(3);
}

// ------------------------------------------------------------ step 4: finish
function render4() {
  const items = missingItems(), ic = {fehler: "✗", hinweis: "!"};
  const cmrN = D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).length;
  const lsN = Object.keys(lsByNumber()).length, corr = D.pages.filter(corrected).length;
  const boxes = D.pages.reduce((a, p) => a + ((S.pages[p.n] || {}).pb || []).length, 0);
  let h = `<h2>4 · ${T.steps[4]}</h2><div class="sum"><div><b>${cmrN}</b>${T.sum_cmr}</div><div><b>${lsN}</b>${T.sum_ls}</div>
    <div><b>${struckTAs().length}</b>${T.sum_struck}</div><div><b>${corr}</b>${T.sum_corr}</div><div><b>${boxes}</b>${T.sum_boxes}</div></div>
    <p class="muted">${T.s4_intro}</p>`;
  h += items.length ? `<ul class="items">` + items.map(x => `<li class="${x.accepted ? "ok" : x.level}">${x.accepted ? "✓" : ic[x.level]} ${x.go ? `<a data-open="${x.go}" data-step="${stepOf(byN[x.go])}">${esc(x.text)}</a>` : esc(x.text)}${accHtml(x.key)}</li>`).join("") + `</ul>`
    : `<p style="color:var(--ok)">✓ ${T.missing_none}</p>`;
  if (items.length) h += `<div class="bar">` + (missingConfirmed(items) ? `<span class="pill ok">✓ ${T.missing_confirmed}</span> <a class="lnk" data-mreset="1">${T.undo}</a>`
    : `<button class="primary" id="mconfirm">${T.confirm_missing}</button>` + (S.missing_keys ? ` <span class="small" style="color:var(--warn)">${T.missing_changed}</span>` : "")) + `</div>`;
  h += `<div class="bar"><label>${T.reviewer} <input id="reviewer" value="${esc(S.reviewer || "")}" autocomplete="name" style="width:220px"></label>
    <span style="flex:1"></span><button class="primary" id="save2">${T.save}</button></div>`;
  return h;
}

// ------------------------------------------------------------ rendering
function renderStepper() {
  $("stepper").innerHTML = T.steps.map((s, k) => `<button data-step-go="${k}" class="${k === S.cur ? "cur " : ""}${stepDone(k) ? "done" : ""}"${canEnter(k) ? "" : " disabled"}>
    <span class="no">${stepDone(k) ? "✓" : k}</span>${esc(s)}</button>`).join("");
}
function renderMain() {
  for (const k in LV) delete LV[k];
  $("main").innerHTML = [render0, render1, render2, render3, render4][S.cur]();
  if (S.cur === 1) mountLL();
}
function renderAll() { $("title").textContent = T.title + " " + (D.tour || D.name); renderStepper(); renderMain(); }
function go(k) { if (!canEnter(k)) { alert(T.step_locked); return; } S.cur = k; persist(); renderAll(); window.scrollTo(0, 0); }
function rerender() { const y = window.scrollY; if (OV) showOv(false); renderStepper(); renderMain(); window.scrollTo(0, y); }

// ------------------------------------------------------------ zoomable viewer (wheel = zoom, drag = move, draw mode)
class Viewer {
  constructor(el, p, cb) {
    this.el = el; this.p = p; this.cb = cb; this.s = 1; this.tx = 0; this.ty = 0; this.drawCls = null;
    el.innerHTML = `<div class="vw"><div class="vin" style="width:${p.w}px;height:${p.h}px"><img src="${esc(p.image)}" alt="${esc(T.img_missing + p.image)}"><div class="ovl"></div></div></div>`;
    this.vw = el.querySelector(".vw"); this.vin = el.querySelector(".vin"); this.ovl = el.querySelector(".ovl");
    this.vw.addEventListener("wheel", e => { e.preventDefault(); const r = this.vw.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.tx = mx - (mx - this.tx) * f; this.ty = my - (my - this.ty) * f; this.s *= f; this.apply(); }, {passive: false});
    this.vw.addEventListener("mousedown", e => this.down(e));
    this.move = e => this.mv(e); this.upf = e => this.up(e);
    this.render();
  }
  apply() { this.vin.style.transform = `translate(${this.tx}px,${this.ty}px) scale(${this.s})`; }
  fit(reg, pad = 0.02) {
    const r = this.vw.getBoundingClientRect(), W = this.p.w, H = this.p.h;
    if (!r.width || !r.height) return;
    const x1 = Math.max(0, reg[0] - pad), y1 = Math.max(0, reg[1] - pad), x2 = Math.min(1, reg[2] + pad), y2 = Math.min(1, reg[3] + pad);
    this.s = Math.min(r.width / ((x2 - x1) * W), r.height / ((y2 - y1) * H), 4);
    this.tx = r.width / 2 - (x1 + x2) / 2 * W * this.s; this.ty = r.height / 2 - (y1 + y2) / 2 * H * this.s; this.apply();
  }
  norm(e) { const r = this.vin.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; }
  startDraw(cls) { this.drawCls = cls; this.vw.classList.add("drawing"); }
  cancelDraw() { this.drawCls = null; this.vw.classList.remove("drawing"); if (this.tmp) { this.tmp.remove(); this.tmp = null; } }
  down(e) {
    if (e.button !== 0) return;
    e.preventDefault();
    if (this.drawCls) { this.start = this.norm(e); this.tmp = document.createElement("div"); this.tmp.className = "tmp"; this.vin.appendChild(this.tmp); }
    else this.pan = {x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty, moved: false, target: e.target};
    window.addEventListener("mousemove", this.move); window.addEventListener("mouseup", this.upf);
  }
  mv(e) {
    if (this.tmp) { const [x, y] = this.norm(e), [sx, sy] = this.start; Object.assign(this.tmp.style, {left: Math.min(x, sx) * 100 + "%", top: Math.min(y, sy) * 100 + "%", width: Math.abs(x - sx) * 100 + "%", height: Math.abs(y - sy) * 100 + "%"}); }
    else if (this.pan) { const dx = e.clientX - this.pan.x, dy = e.clientY - this.pan.y; if (Math.abs(dx) + Math.abs(dy) > 4) this.pan.moved = true; this.tx = this.pan.tx + dx; this.ty = this.pan.ty + dy; this.apply(); }
  }
  up(e) {
    window.removeEventListener("mousemove", this.move); window.removeEventListener("mouseup", this.upf);
    if (this.tmp) {
      const [x, y] = this.norm(e), [sx, sy] = this.start, box = [Math.min(x, sx), Math.min(y, sy), Math.max(x, sx), Math.max(y, sy)].map(v => Math.round(v * 10000) / 10000);
      const cls = this.drawCls; this.cancelDraw();
      if (box[2] - box[0] > 0.004 && box[3] - box[1] > 0.003) this.cb.draw(box, cls);
    } else if (this.pan) {
      const b = !this.pan.moved && this.pan.target.closest && this.pan.target.closest("[data-k]");
      this.pan = null;
      if (b && this.cb.click) this.cb.click(b.dataset.k);
    }
  }
  render() {
    const pos = b => `left:${b[0] * 100}%;top:${b[1] * 100}%;width:${(b[2] - b[0]) * 100}%;height:${(b[3] - b[1]) * 100}%`;
    let h = (this.p.masked || []).map(m => `<div class="mask" style="${pos(m)}"></div>`).join("");
    for (const b of this.cb.boxes()) {
      const col = D.colors[b.cls] || "#000";
      h += `<div class="b ${b.style || ""}${b.person ? " person" : ""}" data-k="${b.key}" style="${pos(b.box)};border-color:${col}"><span style="background:${col}">${esc(b.label)}</span></div>`;
    }
    this.ovl.innerHTML = h;
  }
}

// ------------------------------------------------------------ large view of one page (overlay)
let OV = null;   // {list, idx, step, viewer}
function ovPage() { return OV ? byN[OV.list[OV.idx]] : null; }
function stepList(step) {
  if (step === 0) { const pr = problemPages(); return pr.map(p => p.n).concat(D.pages.filter(p => !pr.includes(p)).map(p => p.n)); }
  return [...document.querySelectorAll(`#main [data-open][data-step="${step}"]`)].map(e => +e.dataset.open).filter((n, i, a) => a.indexOf(n) === i);
}
function openPage(n, step) {
  const list = stepList(step); if (!list.includes(n)) list.unshift(n);
  OV = {list, idx: list.indexOf(n), step};
  $("ov").classList.add("on"); showOv(true);
}
function closeOv() { if (OV && OV.viewer) OV.viewer.cancelDraw(); OV = null; $("ov").classList.remove("on"); $("ovimg").innerHTML = ""; renderStepper(); renderMain(); }
function ovBoxes(p) {
  const out = [];
  p.dets.forEach((d, i) => {
    const inc = detInc(p, d, i), sure = d.score >= thrOf(d.cls);
    out.push({key: "d:" + i, box: d.box, cls: d.cls, label: `${T.cls[d.cls] || d.cls} ${d.score.toFixed(2)}${inc ? "" : sure ? " ✗" : ""}`, style: inc ? "" : sure ? "rej" : "weak"});
  });
  ((S.pages[p.n] || {}).pb || []).forEach((b, i) => out.push({key: "p:" + i, box: b.box, cls: b.cls, label: (T.cls[b.cls] || b.cls) + " ✎", person: true}));
  return out;
}
function focusRegion(p) {
  const t = docType(p), best = c => topOf(p, c);
  if (OV.step === 0) return [0, 0, 1, 1];
  if (t === "lieferschein" && !lsNumber(p)) { const b = best("ls_nummer"); return b ? b.box : [0, 0, 1, 0.35]; }
  if (t === "cmr" && !cmrCount(p)) { const b = best("cmr_count"); return b ? b.box : [0, 0.5, 0.7, 0.8]; }
  return p.view || [0, 0, 1, 1];
}
function showOv(refit) {
  const p = ovPage(); if (!p) return;
  if (refit || !OV.viewer || OV.viewer.p !== p) {
    OV.viewer = new Viewer($("ovimg"), p, {
      boxes: () => ovBoxes(p),
      click: k => { const [kind, i] = k.split(":"); if (kind !== "d") return; const s = us(p); s.bx = s.bx || {}; s.bx[i] = !detInc(p, p.dets[+i], +i); edit(p); },
      draw: (box, cls) => { const s = us(p); s.pb = (s.pb || []).concat([{cls, box}]); if (OBJ.includes(cls) && reviewable(p)) { s.v = s.v || {}; s.v[cls] = true; s.dec = true; } edit(p); },
    });
    const v = OV.viewer;
    requestAnimationFrame(() => v.fit(focusRegion(p), 0.04));
  } else OV.viewer.render();
  $("ovside").innerHTML = sideHtml(p);
  if (refit) { const want = sideFocus(p); const el = want && $("ovside").querySelector(want); if (el) el.focus(); }
}
function sideFocus(p) { const t = docType(p); if (t === "lieferschein" && !lsNumber(p)) return 'input[data-f="ls"]'; if (t === "cmr" && !cmrCount(p)) return 'input[data-f="cmr"]'; if (OV.step === 0 && REVIEW.includes(t) && !tourOf(p)) return 'input[data-f="tour"]'; return null; }
function defaultDrawCls(p) { const x = pageIssues(p).find(i => i.box); if (x) return x.box; return reviewable(p) ? (rule(p).require.find(c => val(p, c) !== false) || "stempel") : "tour_nummer"; }
function sideHtml(p) {
  const t = docType(p), s = S.pages[p.n] || {}, iss = pageIssues(p);
  let h = `<h3 style="margin-top:0">${esc(cardTitle(p))}</h3><div class="muted small">${fmt(T.page, {n: p.n})} · ${esc(p.source)} · ${OV.idx + 1}/${OV.list.length}</div>`;
  h += `<div class="vbtns"><button data-fit="full">${T.v_full}</button><button data-fit="area">${T.v_area}</button>${REVIEW.includes(t) ? `<button data-fit="num">${T.v_num}</button>` : ""}</div>`;
  if (iss.length) h += `<div class="issues small">${iss.map(x => "• " + esc(x.text)).join("<br>")}</div>`;
  h += `<label>${T.doctype}</label><select data-f="doc_type">${D.doc_types.concat(t === "unsicher" ? ["unsicher"] : []).map(x => `<option value="${x}"${x === t ? " selected" : ""}>${esc(T.dt[x] || x)}</option>`).join("")}</select>`;
  if (REVIEW.includes(t)) {
    const read = p.tour && p.tour.raw ? ` – ${T.ocr_read}: „${esc(p.tour.raw)}“` : "";
    h += `<label>${T.tour}${read}</label><input data-f="tour" placeholder="${esc(D.tour || "")}" value="${esc(has(p, "tour") ? s.tour : tourOf(p) || "")}" style="width:220px">`;
    if (D.tour && tourOf(p) !== D.tour) h += ` <button data-tourthis="1">${esc(fmt(T.tour_this, {tour: D.tour}))}</button>`;
  }
  if (t === "lieferschein") {
    const read = p.ls_read && p.ls_read.text ? ` – ${T.ocr_read}: „${esc(p.ls_read.text)}“` : "";
    const pg = lsPage(p);
    h += `<label>${T.ls_number}${read}</label><input class="num" data-f="ls" placeholder="12345678" value="${esc(has(p, "ls") ? s.ls : lsNumber(p) || "")}">`;
    h += `<label>${T.ls_page}</label><input data-f="ls_page" placeholder="1/2" style="width:80px" value="${esc(has(p, "ls_page") ? s.ls_page : pg ? pg.join("/") : "")}">`;
    if (p.carrier) h += `<div class="tag">${T.carrier}</div>`;
  }
  if (t === "cmr") {
    const read = p.cmr_count && p.cmr_count.text ? ` – ${T.ocr_read}: „${esc(p.cmr_count.text)}“` : "";
    const cc = cmrCount(p);
    h += `<label>${T.cmr_count}${read}</label><input class="num" data-f="cmr" placeholder="3/13" value="${esc(has(p, "cmr") ? s.cmr : cc ? cc.join("/") : "")}">`;
    h += `<label>${T.ta_field}</label><input data-f="ta" placeholder="12345678, 12345679" style="width:300px" value="${esc(has(p, "ta") ? s.ta : cmrTAs(p).join(", "))}">`;
  }
  if (REVIEW.includes(t) && OV.step !== 0) {
    h += `<h3>${T.h_obj}</h3>`;
    for (const c of rule(p).require) {
      const v = val(p, c), pr = proposal(p, c), sc = (p.scores || {})[c] || 0;
      h += `<div class="obj"><span class="nm" style="color:${D.colors[c]}">${esc(T.cls[c] || c)}</span>
        <button class="y${v === true ? " on" : ""}" data-obj="${c}" data-v="1">✓ ${T.present}</button><button class="n${v === false ? " on" : ""}" data-obj="${c}" data-v="0">✗ ${T.absent}</button>
        <span class="muted small">${T.model}: ${pr === true ? "✓" : pr === false ? "✗" : "?"}${sc ? " " + sc.toFixed(2) : ""}</span></div>`;
      if (v === true && !hasPos(p, c)) h += `<div class="hint">${T.hint_draw}</div>`;
      if (v === false && p.dets.some(d => d.cls === c)) h += `<div class="muted small">${T.hint_reject}</div>`;
    }
    const v = unitValid(p);
    h += `<p><span class="pill ${v === true ? "ok" : v === false ? "bad" : "open"}">${v === true ? T.valid : v === false ? T.invalid : T.open}</span></p>`;
    if (v === false && archive(p)) h += accHtml(t === "lieferschein" && lsNumber(p) ? "ls_doc:" + lsNumber(p) : "page:" + p.n);
    const cop = copiesOf(p);
    if (cop.length > 1) h += `<p class="small">${fmt(T.copies, {pages: cop.map(q => fmt(T.page, {n: q.n})).join(", ")})}${archive(p) ? "" : ` · ${T.dup} <button data-archthis="1">${T.archive_this}</button>`}</p>`;
  }
  const dc = defaultDrawCls(p), drawing = OV.viewer && OV.viewer.drawCls;
  h += `<h3>${T.draw}</h3><div class="vbtns"><select id="drawcls">${D.classes.map(c => `<option value="${c}"${c === dc ? " selected" : ""}>${esc(T.cls[c] || c)}</option>`).join("")}</select>
    <button id="drawbtn">${drawing ? T.drawing : T.draw + " (B)"}</button></div>`;
  const pb = s.pb || [];
  if (pb.length) h += `<div class="small">${T.boxes_person}: ${pb.map((b, i) => `<span class="chip">${esc(T.cls[b.cls] || b.cls)} <a class="lnk" data-delpb="${i}">×</a></span>`).join(" ")}</div>`;
  h += `<div class="nav"><button data-nav="-1">${T.prev}</button><button data-nav="1">${T.next}</button><button data-close="1">${T.close}</button></div><p class="muted small">${T.keys}</p>`;
  return h;
}
function edit(p) { changed(S.cur); if (OV) showOv(false); }
function setField(p, f, v) {
  const s = us(p); v = (v || "").trim();
  if (f === "doc_type") { if (v === p.doc_type) delete s.doc_type; else s.doc_type = v; changed(0); if (OV) showOv(false); return; }
  if (v === "") delete s[f]; else s[f] = v;
  edit(p);
}
function setObj(p, c, v) { const s = us(p); s.v = s.v || {}; s.v[c] = v; s.dec = true; edit(p); }
function nextOpen(dir = 1) {
  if (!OV) return;
  for (let k = OV.idx + dir; k >= 0 && k < OV.list.length; k += dir) if (pageIssues(byN[OV.list[k]]).some(x => x.step === OV.step)) { OV.idx = k; showOv(true); return; }
  if (OV.idx + dir >= 0 && OV.idx + dir < OV.list.length) { OV.idx += dir; showOv(true); } else closeOv();
}
$("ovside").addEventListener("change", e => {
  const p = ovPage(), f = e.target.dataset.f; if (!p || !f) return;
  setField(p, f, e.target.value);
});
$("ovside").addEventListener("click", e => {
  const p = ovPage(), b = e.target.closest("button,a"); if (!p || !b) return;
  if (b.dataset.obj) setObj(p, b.dataset.obj, b.dataset.v === "1");
  else if (b.dataset.fit) OV.viewer.fit(b.dataset.fit === "full" ? [0, 0, 1, 1] : b.dataset.fit === "area" ? (p.view || [0, 0, 1, 1]) : (topOf(p, docType(p) === "cmr" ? "cmr_count" : "ls_nummer") || {box: [0, 0, 1, 0.35]}).box, 0.04);
  else if (b.dataset.tourthis) setField(p, "tour", D.tour);
  else if (b.dataset.archthis) { archiveThis(p); edit(p); }
  else if (b.dataset.delpb != null) { const s = us(p); s.pb.splice(+b.dataset.delpb, 1); edit(p); }
  else if (b.id === "drawbtn") { OV.viewer.startDraw($("drawcls").value); $("ovside").innerHTML = sideHtml(p); }
  else if (b.dataset.nav) nextOpen(+b.dataset.nav);
  else if (b.dataset.close) closeOv();
});

// ------------------------------------------------------------ events on the main page
document.addEventListener("click", e => {
  if (e.target.closest("select,input") || e.target.closest("#ov")) return;
  const t = e.target.closest("[data-acc],[data-accok],[data-acccancel],[data-unacc],[data-mreset],#mconfirm,[data-confirm],[data-step-go],[data-strike],[data-delta],[data-tadraw],#save2,[data-open]");
  if (!t) return;
  if (t.dataset.acc != null) { accOpen = t.dataset.acc; rerender(); }
  else if (t.dataset.acccancel != null) { accOpen = null; rerender(); }
  else if (t.dataset.accok != null) {
    const f = t.closest(".accform"), reason = f.querySelector("[data-accr]").value, note = f.querySelector("[data-accn]").value.trim();
    if (!reason) { f.querySelector("[data-accr]").focus(); return; }
    if (reason === "sonstiges" && !note) { alert(T.note_needed); f.querySelector("[data-accn]").focus(); return; }
    S.accepted = S.accepted || {}; S.accepted[t.dataset.accok] = {reason, note}; accOpen = null; persist(); rerender();
  }
  else if (t.dataset.unacc != null) { delete S.accepted[t.dataset.unacc]; persist(); rerender(); }
  else if (t.dataset.mreset != null) { delete S.missing_keys; persist(); rerender(); }
  else if (t.id === "mconfirm") { S.missing_keys = missingKeys(missingItems()); persist(); rerender(); }
  else if (t.dataset.confirm != null) { const k = +t.dataset.confirm; if (stepIssues(k).length) return; S.steps[k] = true; changed(k); go(k + 1); }
  else if (t.dataset.stepGo != null) go(+t.dataset.stepGo);
  else if (t.dataset.strike != null) { const p = byN[+t.dataset.strike], x = llEntries(p)[+t.dataset.i]; x.struck = !x.struck; changed(1); refresh1(p); }
  else if (t.dataset.delta != null) { const p = byN[+t.dataset.delta], es = llEntries(p), x = es[+t.dataset.i]; es.splice(+t.dataset.i, 1); us(p).pb = (us(p).pb || []).filter(b => !sameBox(b.box, x.box)); changed(1); refresh1(p); }
  else if (t.dataset.tadraw != null) { const v = LV[+t.dataset.tadraw]; if (v) v.startDraw("ta_nummer"); }
  else if (t.id === "save2") save();
  else if (t.dataset.open != null) openPage(+t.dataset.open, +(t.dataset.step || S.cur));
  else return;
  e.preventDefault();
});
document.addEventListener("change", e => {
  const el = e.target;
  if (el.closest("#ov")) return;
  if (el.dataset.ll != null) { const p = byN[+el.dataset.ll], x = llEntries(p)[+el.dataset.i]; const v = parse8(el.value)[0] || el.value.replace(/\s/g, ""); x.ta = v; if (v && !okTA(v)) alert(T.bad_number); changed(1); refresh1(p); }
  else if (el.dataset.dt != null) { setField(byN[+el.dataset.dt], "doc_type", el.value); rerender(); }
  else if (el.id === "reviewer") { S.reviewer = el.value; persist(); }
});
document.addEventListener("toggle", e => { if (e.target.id === "all0") { S.open0 = e.target.open; persist(); } }, true);
document.addEventListener("keydown", e => {
  if (OV) {
    const p = ovPage();
    if (e.target.matches("input,select")) {
      if (e.key === "Enter") { e.target.dispatchEvent(new Event("change", {bubbles: true})); e.preventDefault(); nextOpen(1); }
      else if (e.key === "Escape") e.target.blur();
      return;
    }
    const k = e.key.toLowerCase();
    if (k === "escape") { if (OV.viewer.drawCls) { OV.viewer.cancelDraw(); showOv(false); } else closeOv(); }
    else if (k === "enter") nextOpen(1);
    else if (k === "arrowright") { if (OV.idx < OV.list.length - 1) { OV.idx++; showOv(true); } }
    else if (k === "arrowleft") { if (OV.idx > 0) { OV.idx--; showOv(true); } }
    else if ((k === "1" || k === "2") && reviewable(p) && rule(p).require.includes(OBJ[+k - 1])) setObj(p, OBJ[+k - 1], val(p, OBJ[+k - 1]) !== true);
    else if (k === "b") { OV.viewer.startDraw(($("drawcls") || {}).value || defaultDrawCls(p)); $("ovside").innerHTML = sideHtml(p); }
    else return;
    e.preventDefault(); return;
  }
  if (e.target.matches("input,select")) return;
  const tiles = [...document.querySelectorAll("#main .tile[data-open]")], i = tiles.indexOf(document.activeElement);
  if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key) && tiles.length) {
    const j = Math.max(0, Math.min(tiles.length - 1, i < 0 ? 0 : i + (["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : -1)));
    tiles[j].focus(); tiles[j].scrollIntoView({block: "nearest"}); e.preventDefault();
  } else if (e.key === "Enter" && i >= 0) { const t = tiles[i]; openPage(+t.dataset.open, +t.dataset.step); e.preventDefault(); }
  else if (e.key === "Escape") for (const k in LV) LV[k].cancelDraw();
});

// ------------------------------------------------------------ save
async function saveText(name, text) {
  if (window.showSaveFilePicker) {
    try {
      const h = await window.showSaveFilePicker({suggestedName: name, types: [{description: "JSON", accept: {"application/json": [".json"]}}]});
      const w = await h.createWritable(); await w.write(text); await w.close();
      return true;
    } catch (e) { if (e && e.name === "AbortError") return false; }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type: "application/json"}));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  return true;
}
async function save() {
  if (!(S.reviewer || "").trim()) { alert(T.save_need_name); if (canEnter(4)) go(4); const r = $("reviewer"); if (r) r.focus(); return; }
  const openSteps = [0, 1, 2, 3].filter(k => !stepDone(k));
  if (openSteps.length && !confirm(fmt(T.save_open, {steps: openSteps.map(k => T.steps[k]).join(", ")}))) return;
  const items = missingItems(), mconf = missingConfirmed(items);
  if (!mconf && !confirm(T.save_unconfirmed)) return;
  const out = {format: "docval-entscheidung", version: 2, name: D.name, tour: D.tour, ergebnis_created: D.created,
    reviewer: S.reviewer.trim(), saved: new Date().toISOString(), steps: [0, 1, 2, 3, 4].map(stepDone),
    open: D.pages.filter(p => reviewable(p) && !pageConfirmed(p)).length, pages: {},
    accepted: S.accepted || {}, missing_keys: missingKeys(items), missing_confirmed: mconf};
  for (const p of D.pages) {
    const s = S.pages[p.n] || {}, fb = finalBoxes(p);
    const e = {doc_type: docType(p), archive: archive(p), archive_set: true, confirmed: pageConfirmed(p),
      bulk: reviewable(p) && !s.dec, corrected: corrected(p), boxes: fb.pos, rejected: fb.neg};
    if (reviewable(p)) {
      for (const c of OBJ) e[c] = val(p, c);
      e.valid = unitValid(p);
      e.cmr_count = docType(p) === "cmr" ? cmrCount(p) : null;
      e.tour = has(p, "tour") ? s.tour.trim() : null;
    }
    if (docType(p) === "lieferschein") { e.ls_number = lsNumber(p); e.ls_page = lsPage(p); }
    if (docType(p) === "cmr" && has(p, "ta")) e.ta = cmrTAs(p);
    if (docType(p) === "loading_list") e.ta_list = llEntries(p).map(x => ({ta: (x.ta || "").replace(/\s/g, ""), box: x.box, struck: !!x.struck, src: x.src}));
    out.pages[p.n] = e;
  }
  if (await saveText("entscheidung.json", JSON.stringify(out, null, 1))) notice(fmt(T.saved, {name: D.name}));
}
$("save").onclick = save;
$("discard").onclick = () => { if (!confirm(T.confirm_discard)) return; S = {reviewer: S.reviewer, pages: {}, steps: {}, accepted: {}, cur: 0}; persist(); notice(""); renderAll(); };

if (S.cur == null || !canEnter(S.cur)) { S.cur = 0; while (S.cur < 4 && stepDone(S.cur)) S.cur++; }
renderAll();
</script>
</body></html>
"""
