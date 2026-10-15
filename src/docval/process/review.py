"""Review page of one tour: pruefung.html (German) / pruefung_pl.html (Polish).

One view, four parts:
0. what is missing in this tour (live): CMR numbers, Lieferschein/loading list pages, TA
   comparison, pages without stamp/signature. Each item can be accepted anyway with a reason;
   the person confirms the list - only then `make finalize` writes the e-mail drafts
1. organisational result (automatic): doc types, tour number, CMR sequence, duplicates; the
   loading list with its TAs - the person strikes the TAs that were not loaded and confirms it
2. Klärfälle: pages where the automatic part was not sure (doc type, CMR i/n, tour number,
   Lieferschein number)
3. one card per CMR/Lieferschein with the detected signature/stamp - the person marks
   "present"/"missing" per object (pre-set from the model) and confirms every card; TAs of a
   CMR and number/page of a Lieferschein can be corrected there. The person's decision is final.

Self-contained, opens by double click (no server, no internet); images are loaded from
seiten/ next to it. Intermediate state stays in the browser (localStorage). "Entscheidung
speichern" writes entscheidung.json, which `make finalize` turns into the archive PDFs.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..eval.i18n import CLASS_NAMES, DOC_TYPE_NAMES, SUFFIX
from ..eval.label_editor import CLASS_COLORS
from .texts import MSG, REASONS, render_check

UI = {
    "de": {
        "html_lang": "de", "title": "Prüfung Tour", "reviewer": "Prüfer/in", "save": "Entscheidung speichern",
        "discard": "verwerfen", "progress": "{done} / {total} bestätigt",
        "h_org": "1 · Organisatorisch – automatisch geprüft",
        "h_clear": "2 · Klärfälle – bitte ergänzen",
        "h_review": "3 · Unterschrift und Stempel – Ihre Entscheidung",
        "review_note": "Die Markierungen des Modells sind ein Vorschlag. Prüfen Sie jede Karte und bestätigen "
                       "Sie sie – Ihre Entscheidung gilt.",
        "stale": "Sie haben Zuordnungen geändert – die Liste oben wird beim Abschluss (make finalize) neu "
                 "geprüft. Die CMR-Folge darunter ist bereits aktuell.",
        "stack": "CMR-Folge", "missing": "fehlt", "dup": "doppelt", "unread": "nicht lesbar",
        "loading_list": "Ladeliste", "ta_loaded": "verladene TA", "ta_excluded": "gestrichen / nicht verladen",
        "f_all": "alle", "f_open": "offen", "f_unsure": "Modell unsicher", "f_invalid": "ungültig",
        "present": "vorhanden", "absent": "fehlt", "model": "Modell", "changed": "geändert",
        "rule_all": "Stempel und Unterschrift nötig", "rule_any": "Stempel oder Unterschrift nötig",
        "valid": "gültig", "invalid": "ungültig", "open": "offen",
        "confirm": "Bestätigen", "confirmed": "bestätigt", "archive": "archivieren",
        "dup_of": "Duplikat von S. {n}", "dup_alt": "weitere Kopie: S. {n} – ggf. diese archivieren", "other_tour": "andere Tour: {tour}", "page": "S. {n}",
        "doctype": "Dokumenttyp", "cmr_count": "CMR-Nr. (i/n)", "tour": "Tournummer",
        "clear_dt": "Dokumenttyp unsicher", "clear_tour": "Tournummer nicht sicher gelesen",
        "clear_cmr": "CMR-Zählung nicht lesbar", "ocr_read": "gelesen", "none": "keine", "choose": "– wählen –",
        "resolved": "erledigt",
        "save_need_name": "Bitte zuerst Ihren Namen bei „Prüfer/in“ eintragen.",
        "save_open": "{n} Karten sind noch nicht bestätigt. Trotzdem speichern? (Der Abschluss geht erst, "
                     "wenn alle bestätigt sind.)",
        "saved": "Gespeichert. Datei als entscheidung.json in den Ordner dieser Seite legen, dann: "
                 "make finalize RUN={name}",
        "loaded": "Zwischenstand aus dem Browser geladen.",
        "confirm_discard": "Alle Eingaben auf dieser Seite verwerfen?",
        "help": "Tasten: J/K oder Pfeile = Karte wechseln · 1 = Unterschrift · 2 = Stempel · A = archivieren · "
                "Enter = bestätigen + weiter · Leertaste = ganze Seite",
        "legend": "Rahmen durchgezogen = sicher erkannt, gestrichelt = unsicher; schraffiert = Vordruck "
                  "Feld 22/23 (wird ignoriert). Bild anklicken = ganze Seite.",
        "no_review": "Keine CMR/Lieferscheine zu prüfen.", "img_missing": "Bild fehlt: ",
        "pages_of": "Seiten", "tour_label": "Tour",
        "no_mask": "Vordruckfelder 22/23 nicht erkannt – Unterschrift/Stempel dort selbst prüfen",
        "h_missing": "0 · Fehlt in dieser Tour – vor dem Abschluss bestätigen",
        "missing_none": "Nichts fehlt.", "accept": "trotzdem akzeptieren", "accepted": "akzeptiert",
        "undo": "zurücknehmen", "note": "Bemerkung", "cancel": "abbrechen",
        "note_needed": "Bei „Sonstiges“ bitte eine Bemerkung eintragen.",
        "confirm_missing": "Fehlliste bestätigen – Mail-Entwürfe freigeben", "missing_confirmed": "Fehlliste bestätigt",
        "missing_changed": "Die Liste hat sich seit der Bestätigung geändert – bitte erneut bestätigen.",
        "need_ta_confirm": "Zuerst die Ladeliste bestätigen (Abschnitt 1).",
        "ta_click": "TA anklicken = gestrichen / nicht verladen (nochmal klicken = zurück). Bild der Seite: Seitenzahl anklicken.",
        "ta_add": "TA hinzufügen", "ta_confirm": "Ladeliste bestätigen", "ta_confirmed": "Ladeliste bestätigt",
        "ta_unread": "TA-Feld nicht lesbar – Seite ansehen, TA ggf. hinzufügen", "struck": "gestrichen",
        "ls_number": "LS-Nr.", "ls_page": "Seite", "ta_field": "TA", "clear_ls": "Lieferscheinnummer nicht gelesen",
        "bad_number": "Bitte eine 8-stellige Nummer eintragen.", "missing_cls": "{cls} fehlt",
        "save_unconfirmed": "Die Fehlliste ist noch nicht bestätigt – make finalize erzeugt dann keine "
                            "Mail-Entwürfe. Trotzdem speichern?",
    },
    "pl": {
        "html_lang": "pl", "title": "Kontrola trasy", "reviewer": "Sprawdzający", "save": "Zapisz decyzję",
        "discard": "odrzuć", "progress": "potwierdzono {done} / {total}",
        "h_org": "1 · Organizacja – sprawdzone automatycznie",
        "h_clear": "2 · Do wyjaśnienia – proszę uzupełnić",
        "h_review": "3 · Podpis i pieczątka – Twoja decyzja",
        "review_note": "Oznaczenia modelu są tylko propozycją. Sprawdź każdą kartę i potwierdź ją – "
                       "decyduje Twoja ocena.",
        "stale": "Zmieniono przypisania – lista powyżej zostanie sprawdzona ponownie przy zamknięciu "
                 "(make finalize). Kolejność CMR poniżej jest już aktualna.",
        "stack": "Kolejność CMR", "missing": "brak", "dup": "duplikat", "unread": "nieczytelne",
        "loading_list": "Lista załadunkowa", "ta_loaded": "załadowane TA", "ta_excluded": "skreślone / nie jedzie",
        "f_all": "wszystkie", "f_open": "otwarte", "f_unsure": "model niepewny", "f_invalid": "nieważne",
        "present": "jest", "absent": "brak", "model": "model", "changed": "zmieniono",
        "rule_all": "wymagane pieczątka i podpis", "rule_any": "wymagana pieczątka lub podpis",
        "valid": "ważny", "invalid": "nieważny", "open": "otwarte",
        "confirm": "Potwierdź", "confirmed": "potwierdzono", "archive": "archiwizować",
        "dup_of": "duplikat str. {n}", "dup_alt": "inna kopia: str. {n} – ew. archiwizować tę", "other_tour": "inna trasa: {tour}", "page": "str. {n}",
        "doctype": "Typ dokumentu", "cmr_count": "nr CMR (i/n)", "tour": "Numer trasy",
        "clear_dt": "Typ dokumentu niepewny", "clear_tour": "Numer trasy odczytany niepewnie",
        "clear_cmr": "Nieczytelny licznik CMR", "ocr_read": "odczytano", "none": "brak", "choose": "– wybierz –",
        "resolved": "załatwione",
        "save_need_name": "Najpierw wpisz swoje imię i nazwisko w polu „Sprawdzający”.",
        "save_open": "Niepotwierdzone karty: {n}. Zapisać mimo to? (Zamknięcie jest możliwe dopiero po "
                     "potwierdzeniu wszystkich.)",
        "saved": "Zapisano. Plik entscheidung.json umieść w folderze tej strony, potem: make finalize RUN={name}",
        "loaded": "Wczytano zapisany stan z przeglądarki.",
        "confirm_discard": "Odrzucić wszystkie wpisy na tej stronie?",
        "help": "Klawisze: J/K lub strzałki = zmiana karty · 1 = podpis · 2 = pieczątka · A = archiwizować · "
                "Enter = potwierdź + dalej · spacja = cała strona",
        "legend": "Ramka ciągła = pewne wykrycie, przerywana = niepewne; kreskowanie = nadruk pól 22/23 "
                  "(pomijany). Kliknij obraz = cała strona.",
        "no_review": "Brak CMR/dowodów dostawy do sprawdzenia.", "img_missing": "Brak obrazu: ",
        "pages_of": "stron", "tour_label": "Trasa",
        "no_mask": "Nie rozpoznano pól 22/23 z nadrukiem – podpis/pieczątkę tam sprawdzić samodzielnie",
        "h_missing": "0 · Braki w tej trasie – potwierdzić przed zamknięciem",
        "missing_none": "Niczego nie brakuje.", "accept": "mimo to zaakceptuj", "accepted": "zaakceptowano",
        "undo": "cofnij", "note": "uwaga", "cancel": "anuluj",
        "note_needed": "Przy „Inne” proszę wpisać uwagę.",
        "confirm_missing": "Potwierdź listę braków – zwolnij szkice e-maili", "missing_confirmed": "Lista braków potwierdzona",
        "missing_changed": "Lista zmieniła się od potwierdzenia – proszę potwierdzić ponownie.",
        "need_ta_confirm": "Najpierw potwierdź listę załadunkową (część 1).",
        "ta_click": "Kliknij TA = skreślone / nie jedzie (ponowne kliknięcie = cofnij). Obraz strony: kliknij numer strony.",
        "ta_add": "dodaj TA", "ta_confirm": "Potwierdź listę załadunkową", "ta_confirmed": "Lista załadunkowa potwierdzona",
        "ta_unread": "Nieczytelne pole TA – obejrzeć stronę, ew. dodać TA", "struck": "skreślone",
        "ls_number": "nr dowodu", "ls_page": "strona", "ta_field": "TA", "clear_ls": "Nie odczytano numeru dowodu dostawy",
        "bad_number": "Proszę wpisać numer 8-cyfrowy.", "missing_cls": "brak: {cls}",
        "save_unconfirmed": "Lista braków nie jest potwierdzona – make finalize nie utworzy szkiców e-maili. "
                            "Zapisać mimo to?",
    },
}

# what the page needs of a page record (OCR texts of the header etc. stay in ergebnis.json)
PAGE_KEYS = ("n", "id", "image", "source", "w", "h", "doc_type", "doc_reason", "dets", "masked", "proposals",
             "scores", "tour", "cmr_count", "ta", "ta_unread", "ls_number", "ls_page", "ls_read", "page_of",
             "view", "mask_found")


def page_data(result: dict, lang: str) -> dict:
    classes = result["classes"]
    return {
        "name": result["name"], "tour": result["tour"], "created": result["created"],
        "rules": result["rules"], "doc_types": result["doc_types"], "ta_validated": bool(result.get("ta_validated")),
        "thr": result["thresholds"]["accept"],
        "colors": {c: CLASS_COLORS[i % len(CLASS_COLORS)] for i, c in enumerate(classes)},
        "pages": [{k: p.get(k) for k in PAGE_KEYS} for p in result["pages"]],
        "org": result["organize"],
        "checks": [{"level": c["level"], "text": render_check(c, lang)} for c in result["organize"]["checks"]],
    }


def write_review(out_dir: Path, result: dict, lang: str = "de") -> Path:
    t = UI[lang]
    js_t = dict(t, cls=CLASS_NAMES[lang], dt=DOC_TYPE_NAMES[lang], reasons=REASONS[lang],
                items={k: v for k, v in MSG[lang].items() if k.startswith("item_")})
    page = TEMPLATE
    for k, v in t.items():
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
header{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:center;padding:8px 16px;
  border-bottom:1px solid var(--line);background:var(--bg);flex-wrap:wrap}
header h1{font-size:16px;margin:0 8px 0 0}
button,select,input{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff}
button{cursor:pointer}
button.primary{background:var(--sel);color:#fff;border-color:var(--sel)}
.muted{color:var(--muted)} .small{font-size:12px}
main{max-width:1600px;margin:0 auto;padding:8px 16px 40px}
h2{font-size:16px;margin:22px 0 8px}
#notice{display:none;padding:6px 16px;background:var(--warnbg);border-bottom:1px solid var(--line)}
ul.checks{list-style:none;padding:0;margin:0}
ul.checks li{padding:5px 10px;border-radius:6px;margin-bottom:4px;display:flex;gap:8px}
ul.checks li.ok{background:var(--okbg)} ul.checks li.fehler{background:var(--errbg)} ul.checks li.hinweis{background:var(--warnbg)}
ul.checks .ic{font-weight:700;width:1.2em;flex:none}
li.ok .ic{color:var(--ok)} li.fehler .ic{color:var(--err)} li.hinweis .ic{color:var(--warn)}
.stale{display:none;margin:6px 0;padding:6px 10px;border-left:3px solid var(--warn);background:var(--warnbg)}
.stack{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0}
.chip{border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;cursor:pointer;background:var(--okbg)}
.chip.miss{background:var(--errbg);border-color:var(--err);color:var(--err);cursor:default}
.chip.dup,.chip.unread{background:var(--warnbg);border-color:var(--warn)}
.ll{margin-top:8px}
.ll a{cursor:pointer;color:var(--sel)}
.clear{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.clear .item{border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;gap:10px}
.clear .item.done{border-color:var(--ok)}
.clear img{width:90px;border:1px solid var(--line);cursor:pointer;align-self:flex-start}
.clear label{display:block;margin:3px 0}
.clear input{width:190px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 10px}
.filters button.on{background:var(--fg);color:#fff;border-color:var(--fg)}
#cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:14px}
.card{border:1px solid var(--line);border-left:5px solid var(--line);border-radius:8px;padding:8px;outline:none;background:#fff}
.card.cur{box-shadow:0 0 0 3px rgba(31,111,235,.45)}
.card.confirmed.is-valid{border-left-color:var(--ok)} .card.confirmed.is-invalid{border-left-color:var(--err)}
.card.noarch{opacity:.55}
.card .head{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
.card .head b{font-size:15px}
.tag{font-size:12px;padding:0 6px;border-radius:4px;background:var(--warnbg);color:var(--warn)}
.view{position:relative;overflow:hidden;width:100%;background:var(--panel);cursor:zoom-in;border:1px solid var(--line)}
.view img{position:absolute;display:block;user-select:none}
.box{position:absolute;border:2px solid;pointer-events:none}
.box.weak{border-style:dashed}
.box span{position:absolute;left:-2px;top:-17px;color:#fff;font-size:11px;padding:0 3px;white-space:nowrap;border-radius:2px}
.mask{position:absolute;pointer-events:none;background:repeating-linear-gradient(45deg,rgba(110,110,115,.35) 0 6px,transparent 6px 12px)}
.rule{margin:6px 0 2px;font-size:12px}
.cls{display:flex;align-items:center;gap:6px;margin:4px 0;flex-wrap:wrap}
.cls .sw{width:12px;height:12px;border-radius:3px;flex:none}
.cls .nm{width:110px}
.cls button{padding:2px 8px}
.cls button.yes.on{background:var(--ok);border-color:var(--ok);color:#fff}
.cls button.no.on{background:var(--err);border-color:var(--err);color:#fff}
.chg{font-size:11px;color:var(--warn)}
.foot{display:flex;align-items:center;gap:10px;margin-top:8px}
.pill{font-size:12px;padding:1px 8px;border-radius:10px;border:1px solid var(--line)}
.pill.is-valid{background:var(--okbg);color:var(--ok);border-color:var(--ok)}
.pill.is-invalid{background:var(--errbg);color:var(--err);border-color:var(--err)}
.foot .conf{margin-left:auto}
.card.confirmed .conf{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.flash{animation:fl .6s}
@keyframes fl{0%,100%{box-shadow:none}50%{box-shadow:0 0 0 4px rgba(201,42,42,.6)}}
.chip.ta{background:#fff} .chip.struck{text-decoration:line-through;background:var(--errbg);border-color:var(--err);color:var(--err)}
a.lnk,a[data-go]{cursor:pointer;color:var(--sel)}
.acc{color:var(--ok);font-size:12px} .accbtn{font-size:12px;padding:1px 8px;margin-left:6px}
.accform{display:inline-flex;gap:4px;flex-wrap:wrap;margin-left:6px} .accform input{width:180px}
.mconf{margin:8px 0} .flds{display:flex;gap:10px;flex-wrap:wrap;margin:4px 0;font-size:12px}
.flds input{width:120px;padding:2px 6px} .flds input.wide{width:220px}
#modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:10;align-items:center;justify-content:center}
#modal.on{display:flex}
#modal .view{height:94vh;width:auto;cursor:zoom-out;background:#fff}
</style></head><body>
<header>
  <h1 id="title"></h1>
  <label>{{reviewer}} <input id="reviewer" autocomplete="name" style="width:180px"></label>
  <span id="progress" class="muted"></span>
  <span style="flex:1"></span>
  <button id="discard">{{discard}}</button>
  <button id="save" class="primary">{{save}}</button>
</header>
<div id="notice"></div>
<main>
  <h2>{{h_missing}}</h2>
  <div id="missing"></div>
  <h2>{{h_org}}</h2>
  <ul class="checks" id="checks"></ul>
  <div class="stale" id="stale">{{stale}}</div>
  <div><b>{{stack}}</b> <div class="stack" id="stack"></div></div>
  <div class="ll" id="ll"></div>
  <div id="clearwrap"><h2>{{h_clear}}</h2><div class="clear" id="clear"></div></div>
  <h2>{{h_review}}</h2>
  <p>{{review_note}}<br><span class="muted small">{{legend}}</span><br><span class="muted small">{{help}}</span></p>
  <div class="filters" id="filters"></div>
  <div id="cards"></div>
</main>
<div id="modal"></div>
<script>
const D = __DATA__;
const T = __I18N__;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => o[k]);
const REVIEW = ["cmr", "lieferschein"];
const OBJ = ["unterschrift", "stempel"];
const byN = {}; D.pages.forEach(p => byN[p.n] = p);
const KEY = "docval-pruefung:" + D.name + ":" + D.created;
let S = {reviewer: "", pages: {}};
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.pages) { S = s; notice(T.loaded); } } catch (e) {}
function persist() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
function notice(msg) { const n = $("notice"); n.textContent = msg; n.style.display = msg ? "block" : "none"; }

// ------------------------------------------------------------ effective values (person > model)
const us = p => S.pages[p.n] || (S.pages[p.n] = {});
const has = (p, k) => S.pages[p.n] && S.pages[p.n][k] != null && S.pages[p.n][k] !== "";
const docType = p => has(p, "doc_type") ? S.pages[p.n].doc_type : p.doc_type;
const reviewable = p => REVIEW.includes(docType(p));
function parseCount(s) { const m = /^\s*(?:cmr)?\s*(\d{1,3})\s*\/\s*(\d{1,3})\s*$/i.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] ? [+m[1], +m[2]] : null; }
const cmrCount = p => has(p, "cmr") ? parseCount(S.pages[p.n].cmr) : (p.cmr_count && p.cmr_count.parsed) || null;
const tourOf = p => has(p, "tour") ? S.pages[p.n].tour.trim() : (p.tour && p.tour.accepted ? p.tour.text : null);
const otherTour = p => { const t = tourOf(p); return t && D.tour && t !== D.tour ? t : null; };
const rule = p => D.rules[docType(p)] || {require: [], mode: "all"};
function proposal(p, c) { const pr = p.proposals[docType(p)]; const v = pr && pr.classes[c]; return v === "ja" ? true : v === "nein" ? false : null; }
function val(p, c) { const s = S.pages[p.n]; return s && s.v && c in s.v ? s.v[c] : proposal(p, c); }
function valid(p) {
  const r = rule(p), vs = r.require.map(c => val(p, c));
  if (!vs.length) return true;
  if (r.mode === "any") return vs.some(v => v === true) ? true : vs.some(v => v === null) ? null : false;
  return vs.some(v => v === false) ? false : vs.some(v => v === null) ? null : true;
}
const dupOf = p => D.org.duplicates[String(p.n)];
const archive = p => has(p, "archive") ? S.pages[p.n].archive : dupOf(p) == null;
const needsReview = p => reviewable(p) && archive(p);
const confirmed = p => !!(S.pages[p.n] && S.pages[p.n].confirmed);
const touched = () => D.pages.some(p => ["doc_type", "cmr", "tour", "archive", "ls", "ls_page", "ta"].some(k => has(p, k)));
// 8-digit numbers (TA / Lieferschein number), a single space inside allowed - as in run.py
function parse8(s) { const out = []; for (const m of String(s || "").matchAll(/(?<!\d)(?:\d ?){7}\d(?!\d)/g)) { const n = m[0].replace(/ /g, ""); if (!out.includes(n)) out.push(n); } return out; }
function parsePageOf(s) { const m = /(\d{1,2})\s*\/\s*(\d{1,2})/.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] ? [+m[1], +m[2]] : null; }
const lsNumber = p => has(p, "ls") ? (parse8(S.pages[p.n].ls)[0] || null) : p.ls_number || null;
const lsPage = p => has(p, "ls_page") ? parsePageOf(S.pages[p.n].ls_page) : p.ls_page || null;
const cmrTAs = p => has(p, "ta") ? parse8(S.pages[p.n].ta) : (p.ta || []).map(t => t.ta);
const struck = t => !!(S.struck && S.struck[t]);
function listTAs() {   // TAs of the loading list (read + added by the person), each once
  const out = [], seen = new Set();
  for (const p of D.pages) if (docType(p) === "loading_list") for (const t of p.ta || []) if (!seen.has(t.ta)) { seen.add(t.ta); out.push({ta: t.ta, n: p.n}); }
  for (const t of S.added || []) if (!seen.has(t)) { seen.add(t); out.push({ta: t, n: null, manual: true}); }
  return out;
}
const loaded = () => listTAs().filter(x => !struck(x.ta)).map(x => x.ta);
function cardTitle(p) {
  const dt = docType(p), cc = cmrCount(p);
  if (dt === "cmr") return cc ? `CMR ${cc[0]}/${cc[1]}` : "CMR ?";
  let t = T.dt[dt] || dt;
  if (dt === "lieferschein") { const num = lsNumber(p), pg = lsPage(p); if (num) t += " " + num; if (pg) t += ` · ${T.ls_page} ${pg[0]}/${pg[1]}`; }
  return t;
}
function missingPages(list) {
  const got = list.filter(Boolean); if (!got.length) return [];
  const n = Math.max(...got.map(x => x[1])), seen = new Set(got.map(x => x[0])), out = [];
  for (let i = 1; i <= n; i++) if (!seen.has(i)) out.push(i);
  return out;
}

// ------------------------------------------------------------ missing list (mirrors organize.py)
function missingItems() {
  const it = [], I = T.items, acc = S.accepted || {};
  const add = (key, code, level, params, go) => it.push({key, level, go, accepted: !!acc[key], text: fmt(I[code], params)});
  const st = stackInfo();
  if (st.tot.size === 1) { const total = [...st.tot][0]; for (let i = 1; i <= total; i++) if (!st.by[i]) add("cmr:" + i, "item_cmr", "fehler", {i, total}); }
  const ls = D.pages.filter(p => docType(p) === "lieferschein" && archive(p) && !otherTour(p));
  const byNum = {};
  for (const p of ls) { const num = lsNumber(p); if (num) (byNum[num] = byNum[num] || []).push(lsPage(p)); }
  for (const num of Object.keys(byNum).sort()) {
    const total = Math.max(0, ...byNum[num].filter(Boolean).map(x => x[1]));
    for (const i of missingPages(byNum[num])) add(`ls:${num}:${i}`, "item_ls_page", "fehler", {number: num, i, total});
  }
  const ll = D.pages.filter(p => docType(p) === "loading_list");
  if (ll.length) {
    const pos = ll.map(p => p.page_of), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1]));
    for (const i of missingPages(pos)) add("ll:" + i, "item_ll_page", "fehler", {i, total});
    const L = loaded();
    if (L.length) {
      const lvl = D.ta_validated ? "fehler" : "hinweis", ex = listTAs().filter(x => struck(x.ta)).map(x => x.ta);
      const cmrT = [];
      D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).forEach(p => cmrTAs(p).forEach(t => { if (!cmrT.includes(t)) cmrT.push(t); }));
      const lsN = [...new Set(ls.map(lsNumber).filter(Boolean))].sort();
      L.filter(t => !cmrT.includes(t)).forEach(t => add("ta_cmr:" + t, "item_ta_cmr", lvl, {ta: t}));
      cmrT.filter(t => !L.includes(t) && !ex.includes(t)).forEach(t => add("ta_cmr_extra:" + t, "item_ta_cmr_extra", lvl, {ta: t}));
      L.filter(t => !lsN.includes(t)).forEach(t => add("ta_ls:" + t, "item_ta_ls", lvl, {ta: t}));
      lsN.filter(t => !L.includes(t) && !ex.includes(t)).forEach(t => add("ta_ls_extra:" + t, "item_ta_ls_extra", lvl, {ta: t}));
    }
  }
  for (const p of order()) if (needsReview(p) && valid(p) === false)
    add("page:" + p.n, "item_page", "fehler", {title: cardTitle(p), page: fmt(T.page, {n: p.n}),
      missing: rule(p).require.filter(c => val(p, c) === false).map(c => fmt(T.missing_cls, {cls: T.cls[c] || c})).join(", ")}, p.n);
  return it.sort((a, b) => (a.level === "fehler" ? 0 : 1) - (b.level === "fehler" ? 0 : 1));
}
const missingKeys = items => items.map(x => x.key).sort();
const missingConfirmed = items => !items.length || (!!S.missing_keys && JSON.stringify(S.missing_keys) === JSON.stringify(missingKeys(items)));
let accOpen = null;
function accHtml(key) {
  const a = (S.accepted || {})[key];
  if (a) return ` <span class="acc">· ✓ ${T.accepted}: ${esc(T.reasons[a.reason] || a.reason)}${a.note ? " – " + esc(a.note) : ""}</span> <a class="lnk small" data-unacc="${esc(key)}">${T.undo}</a>`;
  if (accOpen === key) return `<span class="accform"><select data-accr><option value="">${T.choose}</option>${Object.entries(T.reasons).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select><input data-accn placeholder="${esc(T.note)}"><button data-accok="${esc(key)}">OK</button><button data-acccancel="1">${T.cancel}</button></span>`;
  return `<button class="accbtn" data-acc="${esc(key)}">${T.accept}</button>`;
}
function renderMissing() {
  const items = missingItems(), ic = {fehler: "✗", hinweis: "!"};
  let h = items.length ? `<ul class="checks">` + items.map(x => `<li class="${x.accepted ? "ok" : x.level}"><span class="ic">${x.accepted ? "✓" : ic[x.level]}</span><span>${x.go ? `<a data-go="${x.go}">${esc(x.text)}</a>` : esc(x.text)}${accHtml(x.key)}</span></li>`).join("") + `</ul>`
    : `<p style="color:var(--ok)">✓ ${T.missing_none}</p>`;
  if (items.length) {
    const needTa = D.pages.some(p => docType(p) === "loading_list") && !S.ta_confirmed;
    h += `<div class="mconf">` + (missingConfirmed(items) ? `<span class="pill is-valid">✓ ${T.missing_confirmed}</span> <a class="lnk small" data-mreset="1">${T.undo}</a>`
      : `<button id="mconfirm" class="primary"${needTa ? " disabled" : ""}>${T.confirm_missing}</button>` + (needTa ? ` <span class="muted small">${T.need_ta_confirm}</span>` : "")
        + (S.missing_keys ? ` <span class="small" style="color:var(--warn)">${T.missing_changed}</span>` : "")) + `</div>`;
  }
  $("missing").innerHTML = h;
}
function refreshAcc(key) {
  renderMissing();
  const m = /^page:(\d+)$/.exec(key || ""); if (m && byN[+m[1]]) update(byN[+m[1]]);
}
document.addEventListener("click", e => {
  const t = e.target.closest("[data-acc],[data-accok],[data-acccancel],[data-unacc],[data-mreset],#mconfirm,#taconf,#taaddbtn,.chip.ta");
  if (!t) return;
  if (t.dataset.acc != null) { const prev = accOpen; accOpen = t.dataset.acc; refreshAcc(prev); refreshAcc(accOpen); }
  else if (t.dataset.acccancel != null) { const prev = accOpen; accOpen = null; refreshAcc(prev); }
  else if (t.dataset.accok != null) {
    const f = t.closest(".accform"), reason = f.querySelector("[data-accr]").value, note = f.querySelector("[data-accn]").value.trim();
    if (!reason) { f.querySelector("[data-accr]").focus(); return; }
    if (reason === "sonstiges" && !note) { alert(T.note_needed); f.querySelector("[data-accn]").focus(); return; }
    S.accepted = S.accepted || {}; S.accepted[t.dataset.accok] = {reason, note}; accOpen = null; persist(); refreshAcc(t.dataset.accok);
  }
  else if (t.dataset.unacc != null) { delete S.accepted[t.dataset.unacc]; persist(); refreshAcc(t.dataset.unacc); }
  else if (t.dataset.mreset != null) { delete S.missing_keys; persist(); renderMissing(); }
  else if (t.id === "mconfirm") { S.missing_keys = missingKeys(missingItems()); persist(); renderMissing(); }
  else if (t.id === "taconf") { S.ta_confirmed = true; persist(); renderLoadingList(); renderMissing(); }
  else if (t.id === "taaddbtn") {
    const v = parse8($("taadd").value);
    if (!v.length) { alert(T.bad_number); return; }
    S.added = S.added || []; v.forEach(x => { if (!S.added.includes(x)) S.added.push(x); });
    S.ta_confirmed = false; persist(); renderLoadingList(); renderMissing();
  }
  else if (t.classList.contains("ta")) {
    S.struck = S.struck || {}; const ta = t.dataset.ta;
    if (S.struck[ta]) delete S.struck[ta]; else S.struck[ta] = true;
    S.ta_confirmed = false; persist(); renderLoadingList(); renderMissing();
  }
  e.stopPropagation();
}, true);

// ------------------------------------------------------------ header + organisational part
function renderHeader() {
  $("title").textContent = T.title + " " + (D.tour || D.name);
  const need = D.pages.filter(needsReview), done = need.filter(confirmed);
  $("progress").textContent = fmt(T.progress, {done: done.length, total: need.length});
  $("stale").style.display = touched() ? "block" : "none";
}
function renderChecks() {
  const ic = {ok: "✓", fehler: "✗", hinweis: "!"};
  $("checks").innerHTML = D.checks.map(c => `<li class="${c.level}"><span class="ic">${ic[c.level]}</span><span>${esc(c.text)}</span></li>`).join("");
}
function stackInfo() {
  const by = {}, tot = new Set(), unread = [];
  for (const p of D.pages) {
    if (docType(p) !== "cmr" || !archive(p) || otherTour(p)) continue;
    const c = cmrCount(p);
    if (!c) { unread.push(p.n); continue; }
    (by[c[0]] = by[c[0]] || []).push(p.n); tot.add(c[1]);
  }
  return {by, tot, unread};
}
function renderStack() {
  const {by, tot, unread} = stackInfo();
  const N = Math.max(0, ...tot, ...Object.keys(by).map(Number));
  let h = "";
  for (let i = 1; i <= N; i++) {
    const ns = by[i];
    if (!ns) h += `<span class="chip miss">${i} · ${T.missing}</span>`;
    else h += `<span class="chip${ns.length > 1 ? " dup" : ""}" data-go="${ns[0]}">${i}/${[...tot].join("|")} · ${ns.map(n => fmt(T.page, {n})).join(", ")}${ns.length > 1 ? " · " + T.dup : ""}</span>`;
  }
  for (const n of unread) h += `<span class="chip unread" data-go="${n}">? · ${fmt(T.page, {n})} · ${T.unread}</span>`;
  $("stack").innerHTML = h || `<span class="muted">${T.none}</span>`;
}
function renderLoadingList() {
  const ll = D.pages.filter(p => docType(p) === "loading_list");
  if (!ll.length) { $("ll").innerHTML = ""; return; }
  const tas = listTAs(), unread = ll.filter(p => (p.ta_unread || []).length), L = loaded();
  let h = `<b>${T.loading_list}</b>: ` + ll.map(p => `<a class="lnk" data-modal="${p.n}">${fmt(T.page, {n: p.n})}${p.page_of ? " (" + p.page_of.join("/") + ")" : ""}</a>`).join(", ");
  h += `<div class="muted small">${T.ta_click}</div><div class="stack">` + (tas.map(x => `<span class="chip ta${struck(x.ta) ? " struck" : ""}" data-ta="${x.ta}" title="${x.n ? esc(fmt(T.page, {n: x.n})) : "+"}">${x.ta}${x.manual ? " +" : ""}</span>`).join("") || `<span class="muted">${T.none}</span>`) + `</div>`;
  if (unread.length) h += `<div class="small" style="color:var(--warn)">${T.ta_unread}: ${unread.map(p => `<a class="lnk" data-modal="${p.n}">${fmt(T.page, {n: p.n})}</a>`).join(", ")}</div>`;
  h += `<div class="small">${T.ta_loaded}: ${L.length}${tas.length > L.length ? ` · ${T.struck}: ${tas.length - L.length}` : ""}</div>`;
  h += `<div style="margin-top:4px"><input id="taadd" placeholder="12345678" style="width:120px"> <button id="taaddbtn">${T.ta_add}</button> `
    + (S.ta_confirmed ? `<span class="pill is-valid">✓ ${T.ta_confirmed}</span>` : `<button id="taconf" class="primary">${T.ta_confirm}</button>`) + `</div>`;
  $("ll").innerHTML = h;
}

// ------------------------------------------------------------ Klärfälle
function unclearKinds(p) {
  const k = [];
  if (p.doc_type === "unsicher") k.push("dt");
  if (reviewable(p) && REVIEW.includes(p.doc_type) && !(p.tour && p.tour.accepted)) k.push("tour");
  if (docType(p) === "cmr" && !(p.cmr_count && p.cmr_count.parsed)) k.push("cmr");
  if (docType(p) === "lieferschein" && p.doc_type === "lieferschein" && !p.ls_number) k.push("ls");
  return k;
}
function renderClear() {
  const items = D.pages.filter(p => unclearKinds(p).length);
  $("clearwrap").style.display = items.length ? "block" : "none";
  $("clear").innerHTML = items.map(p => {
    const k = unclearKinds(p);
    const done = (!k.includes("dt") || has(p, "doc_type")) && (!k.includes("cmr") || cmrCount(p)) && (!k.includes("ls") || lsNumber(p));
    const opts = [`<option value="">${T.choose}</option>`].concat(D.doc_types.map(t =>
      `<option value="${t}"${docType(p) === t && (has(p, "doc_type") || p.doc_type === t) ? " selected" : ""}>${esc(T.dt[t] || t)}</option>`)).join("");
    let f = `<b>${fmt(T.page, {n: p.n})}</b> <span class="muted small">${esc(p.source)}</span>` + (done ? ` <span class="small" style="color:var(--ok)">✓ ${T.resolved}</span>` : "");
    f += `<div class="small muted">${k.map(x => T["clear_" + x]).join(" · ")}</div>`;
    f += `<label>${T.doctype} <select data-n="${p.n}" data-f="doc_type">${opts}</select></label>`;
    if (docType(p) === "cmr") {
      const read = p.cmr_count && p.cmr_count.text ? ` <span class="muted small">${T.ocr_read}: „${esc(p.cmr_count.text)}“</span>` : "";
      f += `<label>${T.cmr_count} <input data-n="${p.n}" data-f="cmr" placeholder="3/13" value="${esc(has(p, "cmr") ? S.pages[p.n].cmr : (cmrCount(p) || []).join("/"))}">${read}</label>`;
    }
    if (docType(p) === "lieferschein") {
      const read = p.ls_read && p.ls_read.text ? ` <span class="muted small">${T.ocr_read}: „${esc(p.ls_read.text)}“</span>` : "";
      f += `<label>${T.ls_number} <input data-n="${p.n}" data-f="ls" placeholder="12345678" value="${esc(has(p, "ls") ? S.pages[p.n].ls : lsNumber(p) || "")}">${read}</label>`;
    }
    if (reviewable(p)) {
      const read = p.tour && p.tour.raw ? ` <span class="muted small">${T.ocr_read}: „${esc(p.tour.raw)}“</span>` : "";
      f += `<label>${T.tour} <input data-n="${p.n}" data-f="tour" placeholder="${esc(D.tour || "")}" value="${esc(has(p, "tour") ? S.pages[p.n].tour : "")}">${read}</label>`;
    }
    return `<div class="item${done ? " done" : ""}"><img src="${esc(p.image)}" data-modal="${p.n}" alt=""><div>${f}</div></div>`;
  }).join("");
}
$("clear").addEventListener("change", e => {
  const el = e.target, p = byN[+el.dataset.n];
  if (!p) return;
  const s = us(p), f = el.dataset.f;
  if (el.value === "") delete s[f]; else s[f] = el.value;
  if (f !== "ls") s.confirmed = false;
  persist(); renderAll();
});

// ------------------------------------------------------------ cards
let filter = "all", cur = null;
const FILTERS = {all: () => true, open: p => needsReview(p) && !confirmed(p),
  unsure: p => rule(p).require.some(c => proposal(p, c) === null), invalid: p => valid(p) === false};
function renderFilters() {
  $("filters").innerHTML = Object.keys(FILTERS).map(f => `<button data-f="${f}" class="${f === filter ? "on" : ""}">${T["f_" + f]} (${D.pages.filter(p => reviewable(p) && FILTERS[f](p)).length})</button>`).join("");
}
$("filters").addEventListener("click", e => { const f = e.target.dataset.f; if (f) { filter = f; renderFilters(); renderCards(); } });
function order() {
  const key = p => [docType(p) === "cmr" ? 0 : 1, archive(p) ? 0 : 1, otherTour(p) ? 1 : 0,
    docType(p) === "cmr" ? ((cmrCount(p) || [999])[0]) : 0, p.n];
  return D.pages.filter(reviewable).sort((a, b) => {
    const x = key(a), y = key(b);
    for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i];
    return 0;
  });
}
function viewHtml(p, v, classes) {
  const [x1, y1, x2, y2] = v, rw = x2 - x1, rh = y2 - y1;
  const pos = b => `left:${(b[0] - x1) / rw * 100}%;top:${(b[1] - y1) / rh * 100}%;width:${(b[2] - b[0]) / rw * 100}%;height:${(b[3] - b[1]) / rh * 100}%`;
  let h = `<img src="${esc(p.image)}" alt="" style="width:${100 / rw}%;left:${-x1 / rw * 100}%;top:${-y1 / rh * 100}%" onerror="this.replaceWith(Object.assign(document.createElement('div'),{textContent:T.img_missing+this.getAttribute('src'),style:'padding:8px'}))">`;
  for (const m of p.masked || []) h += `<div class="mask" style="${pos(m)}"></div>`;
  for (const d of p.dets) {
    if (classes && !classes.includes(d.cls)) continue;
    const col = D.colors[d.cls] || "#000", weak = d.score < (D.thr[d.cls] != null ? D.thr[d.cls] : 0.5);
    h += `<div class="box${weak ? " weak" : ""}" style="${pos(d.box)};border-color:${col}"><span style="background:${col}">${esc(T.cls[d.cls] || d.cls)} ${d.score.toFixed(2)}</span></div>`;
  }
  return `<div class="view" data-modal="${p.n}" style="aspect-ratio:${rw * p.w} / ${rh * p.h}">${h}</div>`;
}
function cardHtml(p) {
  const dt = docType(p), v = valid(p), r = rule(p);
  const title = cardTitle(p);
  let flds = "";
  if (dt === "cmr") flds = `<div class="flds"><label>${T.ta_field} <input class="fld wide" data-f="ta" placeholder="12345678, 12345679" value="${esc(has(p, "ta") ? S.pages[p.n].ta : cmrTAs(p).join(", "))}"></label></div>`;
  if (dt === "lieferschein") { const pg = lsPage(p); flds = `<div class="flds"><label>${T.ls_number} <input class="fld" data-f="ls" placeholder="12345678" value="${esc(has(p, "ls") ? S.pages[p.n].ls : lsNumber(p) || "")}"></label><label>${T.ls_page} <input class="fld" data-f="ls_page" placeholder="1/2" style="width:60px" value="${esc(has(p, "ls_page") ? S.pages[p.n].ls_page : pg ? pg.join("/") : "")}"></label></div>`; }
  let tags = "";
  if (dupOf(p) != null) tags += `<span class="tag">${fmt(T.dup_of, {n: dupOf(p)})}</span>`;
  const copies = D.pages.filter(q => dupOf(q) === p.n && !archive(q)).map(q => q.n);
  if (copies.length && valid(p) === false) tags += `<span class="tag">${fmt(T.dup_alt, {n: copies.join(", ")})}</span>`;
  if (dt === "cmr" && p.mask_found === false) tags += `<span class="tag">${T.no_mask}</span>`;
  if (otherTour(p)) tags += `<span class="tag">${esc(fmt(T.other_tour, {tour: otherTour(p)}))}</span>`;
  let rows = "";
  for (const c of r.require) {
    const val_ = val(p, c), pr = proposal(p, c), sc = (p.scores || {})[c] || 0;
    const prTxt = pr === true ? "✓" : pr === false ? "✗" : "?";
    const changed = S.pages[p.n] && S.pages[p.n].v && c in S.pages[p.n].v && S.pages[p.n].v[c] !== pr;
    rows += `<div class="cls"><span class="sw" style="background:${D.colors[c]}"></span><span class="nm">${esc(T.cls[c] || c)}</span>
      <button class="yes${val_ === true ? " on" : ""}" data-c="${c}" data-v="1">✓ ${T.present}</button>
      <button class="no${val_ === false ? " on" : ""}" data-c="${c}" data-v="0">✗ ${T.absent}</button>
      <span class="muted small">${T.model}: ${prTxt}${sc ? " " + sc.toFixed(2) : ""}</span>${changed ? `<span class="chg">${T.changed}</span>` : ""}</div>`;
  }
  const vc = v === true ? "is-valid" : v === false ? "is-invalid" : "is-open";
  return `<div class="head"><b>${esc(title)}</b><span class="muted small">${fmt(T.page, {n: p.n})} · ${esc(p.source)}</span>${tags}</div>
    ${flds}${viewHtml(p, p.view || [0, 0, 1, 1], OBJ)}
    <div class="rule muted">${r.mode === "any" ? T.rule_any : T.rule_all}</div>${rows}
    <div class="foot"><label><input type="checkbox" class="arch"${archive(p) ? " checked" : ""}> ${T.archive}</label>
    <span class="pill ${vc}">${v === true ? T.valid : v === false ? T.invalid : T.open}</span>
    <button class="conf">${confirmed(p) ? "✓ " + T.confirmed : T.confirm}</button></div>
    ${v === false && archive(p) ? `<div class="small">${accHtml("page:" + p.n)}</div>` : ""}`;
}
function cardClass(p) {
  const v = valid(p);
  return "card " + (v === true ? "is-valid" : v === false ? "is-invalid" : "is-open") +
    (confirmed(p) ? " confirmed" : "") + (archive(p) ? "" : " noarch") + (p.n === cur ? " cur" : "");
}
function renderCards() {
  const list = order().filter(FILTERS[filter]);
  $("cards").innerHTML = list.length ? list.map(p => `<div class="${cardClass(p)}" tabindex="0" data-n="${p.n}">${cardHtml(p)}</div>`).join("")
    : `<p class="muted">${T.no_review}</p>`;
}
function update(p) {
  const el = document.querySelector(`#cards .card[data-n="${p.n}"]`);
  if (el) { el.className = cardClass(p); el.innerHTML = cardHtml(p); }
  renderHeader(); renderStack(); renderFilters(); renderMissing();
}
function setVal(p, c, v) { const s = us(p); s.v = s.v || {}; s.v[c] = v; s.confirmed = false; persist(); update(p); }
function confirmCard(p) {
  if (rule(p).require.some(c => val(p, c) === null)) {
    const el = document.querySelector(`#cards .card[data-n="${p.n}"]`);
    if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
    return false;
  }
  us(p).confirmed = true; persist(); update(p); return true;
}
$("cards").addEventListener("click", e => {
  const el = e.target.closest(".card"); if (!el) return;
  const p = byN[+el.dataset.n]; setCur(p.n);
  if (e.target.closest(".flds,.accform")) return;
  const b = e.target.closest("button");
  if (b && b.dataset.c) setVal(p, b.dataset.c, b.dataset.v === "1");
  else if (b && b.classList.contains("conf")) confirmCard(p);
  else if (e.target.closest(".view")) openModal(p);
});
$("cards").addEventListener("change", e => {
  if (e.target.classList.contains("fld")) {
    const p = byN[+e.target.closest(".card").dataset.n], s = us(p), f = e.target.dataset.f, v = e.target.value.trim();
    if (v === "") delete s[f]; else s[f] = v;
    persist(); update(p); renderClear(); return;
  }
  if (!e.target.classList.contains("arch")) return;
  const p = byN[+e.target.closest(".card").dataset.n];
  const s = us(p); s.archive = e.target.checked; s.confirmed = false; persist(); update(p);
});
function setCur(n) {
  cur = n;
  document.querySelectorAll("#cards .card").forEach(c => c.classList.toggle("cur", +c.dataset.n === n));
}
function move(step) {
  const cards = [...document.querySelectorAll("#cards .card")];
  if (!cards.length) return;
  let i = cards.findIndex(c => +c.dataset.n === cur);
  i = i < 0 ? 0 : Math.max(0, Math.min(cards.length - 1, i + step));
  setCur(+cards[i].dataset.n);
  cards[i].focus({preventScroll: true});
  cards[i].scrollIntoView({block: "nearest", behavior: "smooth"});
}

// ------------------------------------------------------------ full page
function openModal(p) {
  $("modal").innerHTML = viewHtml(p, [0, 0, 1, 1], null);
  $("modal").classList.add("on");
}
function closeModal() { $("modal").classList.remove("on"); $("modal").innerHTML = ""; }
$("modal").addEventListener("click", closeModal);
document.addEventListener("click", e => {
  const m = e.target.closest("[data-modal]");
  if (m && !e.target.closest("#cards") && !e.target.closest("#modal")) openModal(byN[+m.dataset.modal]);
  const g = e.target.closest("[data-go]");
  if (g) {
    const n = +g.dataset.go;
    if (filter !== "all") { filter = "all"; renderFilters(); renderCards(); }
    setCur(n);
    const el = document.querySelector(`#cards .card[data-n="${n}"]`);
    if (el) { el.scrollIntoView({block: "center", behavior: "smooth"}); el.focus({preventScroll: true}); }
  }
});
document.addEventListener("keydown", e => {
  if (e.target.matches("input,select,textarea")) return;
  if ($("modal").classList.contains("on")) {
    if (e.key === "Escape" || e.key === " ") { closeModal(); e.preventDefault(); }
    return;
  }
  const p = byN[cur];
  const k = e.key.toLowerCase();
  if (k === "j" || k === "arrowdown" || k === "arrowright") move(1);
  else if (k === "k" || k === "arrowup" || k === "arrowleft") move(-1);
  else if (!p || !reviewable(p)) return;
  else if (k === "1" || k === "2") {
    const c = OBJ[+k - 1];
    if (rule(p).require.includes(c)) setVal(p, c, val(p, c) !== true);
  } else if (k === "a") { const s = us(p); s.archive = !archive(p); s.confirmed = false; persist(); update(p); }
  else if (k === "enter") { if (confirmCard(p)) move(1); }
  else if (k === " ") openModal(p);
  else return;
  e.preventDefault();
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
$("save").onclick = async () => {
  if (!S.reviewer.trim()) { alert(T.save_need_name); $("reviewer").focus(); return; }
  const open = D.pages.filter(p => needsReview(p) && !confirmed(p)).length;
  if (open && !confirm(fmt(T.save_open, {n: open}))) return;
  const items = missingItems(), mconf = missingConfirmed(items);
  if (!mconf && !confirm(T.save_unconfirmed)) return;
  const out = {format: "docval-entscheidung", version: 1, name: D.name, tour: D.tour, ergebnis_created: D.created,
    reviewer: S.reviewer.trim(), saved: new Date().toISOString(), open, pages: {}};
  for (const p of D.pages) {
    // archive_set: shown as duplicate or ticked/unticked by the person - otherwise finalize
    // picks among copies itself (e.g. two pages the person gave the same CMR number)
    const e = {doc_type: docType(p), archive: archive(p), archive_set: has(p, "archive") || dupOf(p) != null,
      confirmed: confirmed(p)};
    if (reviewable(p)) {
      for (const c of OBJ) e[c] = val(p, c);
      e.valid = valid(p);
      e.cmr_count = docType(p) === "cmr" ? cmrCount(p) : null;
      e.tour = has(p, "tour") ? S.pages[p.n].tour.trim() : null;
    }
    if (docType(p) === "lieferschein") { e.ls_number = lsNumber(p); e.ls_page = lsPage(p); }
    if (docType(p) === "cmr" && has(p, "ta")) e.ta = cmrTAs(p);
    out.pages[p.n] = e;
  }
  Object.assign(out, {ta_struck: Object.keys(S.struck || {}).filter(k => S.struck[k]), ta_added: S.added || [],
    ta_confirmed: !!S.ta_confirmed, accepted: S.accepted || {}, missing_keys: missingKeys(items), missing_confirmed: mconf});
  if (await saveText("entscheidung.json", JSON.stringify(out, null, 1))) notice(fmt(T.saved, {name: D.name}));
};
$("discard").onclick = () => {
  if (!confirm(T.confirm_discard)) return;
  S = {reviewer: S.reviewer, pages: {}}; persist(); notice(""); renderAll();
};
$("reviewer").value = S.reviewer || "";
$("reviewer").addEventListener("input", e => { S.reviewer = e.target.value; persist(); });

function renderAll() { renderHeader(); renderChecks(); renderStack(); renderLoadingList(); renderClear(); renderFilters(); renderCards(); renderMissing(); }
renderAll();
</script>
</body></html>
"""
