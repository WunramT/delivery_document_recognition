"""Messages of the organisational checks and the protocol, German and Polish.

One template per check code; organize.py only produces codes + parameters, so the
review page and the protocol say the same thing in both languages.
"""

from __future__ import annotations

MSG = {
    "de": {
        "doctype_ok": "Dokumenttyp: {n} Seiten erkannt – {cmr} CMR, {ls} Lieferscheine, {ll} Ladeliste",
        "doctype_unclear": "Dokumenttyp unsicher: {pages} – bitte unten zuordnen",
        "discarded": "Abholscheine (nicht Teil der Prüfung, werden verworfen): {pages}",
        "tour_ok": "Tournummer {tour} auf allen CMR/Lieferscheinen gelesen",
        "tour_unread": "Tournummer nicht sicher gelesen: {pages} – zählt zu Tour {tour}, bitte prüfen",
        "tour_other": "Andere Tour (Zuladung): {items} – zur richtigen Tour legen",
        "tour_unknown": "Tournummer der Tour nicht bestimmt – beim Start angeben (TOUR=...)",
        "cmr_complete": "CMR vollständig: {n} von {n}",
        "cmr_missing": "CMR fehlt: Nr. {missing} von {total} – an Polilogistics melden",
        "cmr_conflict": "CMR-Gesamtzahl widersprüchlich: {totals}",
        "cmr_unread": "CMR-Zählung nicht lesbar: {pages} – bitte unten eintragen",
        "cmr_none": "Keine CMR im Stapel",
        "cmr_dup": "Doppelte CMR-Kopien, werden nicht archiviert: {items}",
        "ls_count": "Lieferscheine: {n}",
        "ls_none": "Keine Lieferscheine im Stapel",
        "ls_dup": "Doppelte Lieferscheine (gleiche TA), werden nicht archiviert: {items}",
        "ta_list": "Ladeliste: {n} TA verladen{excluded}",
        "ta_excluded": ", gestrichen/nicht verladen: {tas}",
        "ta_none": "Ladeliste: keine TA-Nummern gelesen",
        "ta_no_list": "Keine Ladeliste im Stapel",
        "ta_cmr_missing": "Kein CMR mit TA {tas}",
        "ta_ls_missing": "Kein Lieferschein mit TA {tas}",
        "ta_ls_count": "{ls} Lieferscheine für {ta} verladene TA",
        "ta_ok": "Jede verladene TA hat ein CMR und einen Lieferschein",
        "ta_note": " (Hinweis: TA-Lesung noch nicht validiert)",
        "pages": "S. {list}",
        "page": "S. {n}",
        "cmr_of": "CMR {i}/{n}",
        "dup_of": "{dup} (behalten: {keep})",
    },
    "pl": {
        "doctype_ok": "Typ dokumentu: rozpoznano {n} stron – CMR: {cmr}, dowody dostawy: {ls}, "
                      "lista załadunkowa: {ll}",
        "doctype_unclear": "Typ dokumentu niepewny: {pages} – przypisać poniżej",
        "discarded": "Dowody odbioru (Abholschein, poza kontrolą, odrzucone): {pages}",
        "tour_ok": "Numer trasy {tour} odczytany na wszystkich CMR/dowodach dostawy",
        "tour_unread": "Numer trasy odczytany niepewnie: {pages} – liczone do trasy {tour}, sprawdzić",
        "tour_other": "Inna trasa (doładunek): {items} – dołączyć do właściwej trasy",
        "tour_unknown": "Nie ustalono numeru trasy – podać przy uruchomieniu (TOUR=...)",
        "cmr_complete": "CMR kompletne: {n} z {n}",
        "cmr_missing": "Brak CMR: nr {missing} z {total} – zgłosić do Polilogistics",
        "cmr_conflict": "Sprzeczna łączna liczba CMR: {totals}",
        "cmr_unread": "Nieczytelny licznik CMR: {pages} – wpisać poniżej",
        "cmr_none": "Brak CMR w stosie",
        "cmr_dup": "Zduplikowane kopie CMR, nie będą archiwizowane: {items}",
        "ls_count": "Dowody dostawy: {n}",
        "ls_none": "Brak dowodów dostawy w stosie",
        "ls_dup": "Zduplikowane dowody dostawy (ten sam TA), nie będą archiwizowane: {items}",
        "ta_list": "Lista załadunkowa: załadowano {n} TA{excluded}",
        "ta_excluded": ", skreślone/nie jedzie: {tas}",
        "ta_none": "Lista załadunkowa: nie odczytano numerów TA",
        "ta_no_list": "Brak listy załadunkowej w stosie",
        "ta_cmr_missing": "Brak CMR z TA {tas}",
        "ta_ls_missing": "Brak dowodu dostawy z TA {tas}",
        "ta_ls_count": "Dowody dostawy: {ls} na {ta} załadowanych TA",
        "ta_ok": "Każdy załadowany TA ma CMR i dowód dostawy",
        "ta_note": " (wskazówka: odczyt TA jeszcze niezweryfikowany)",
        "pages": "str. {list}",
        "page": "str. {n}",
        "cmr_of": "CMR {i}/{n}",
        "dup_of": "{dup} (zostaje: {keep})",
    },
}


def pages_text(nums: list[int], lang: str) -> str:
    return MSG[lang]["pages"].format(list=", ".join(str(n) for n in nums))


def render_check(check: dict, lang: str) -> str:
    """check: {"code", "params", "hint"?}. List parameters are joined with ", "."""
    m = MSG[lang]
    params = {}
    for k, v in check.get("params", {}).items():
        if k == "pages":
            params[k] = pages_text(v, lang)
        elif k == "excluded":
            params[k] = m["ta_excluded"].format(tas=", ".join(v)) if v else ""
        elif k == "items":
            params[k] = ", ".join(_item(x, lang) for x in v)
        elif isinstance(v, list):
            params[k] = ", ".join(str(x) for x in v)
        else:
            params[k] = v
    text = m[check["code"]].format(**params)
    return text + (m["ta_note"] if check.get("hint") else "")


def _item(x, lang: str) -> str:
    """Item of a list parameter: a page number, a {page, tour} or a {dup, keep} pair."""
    m = MSG[lang]
    if isinstance(x, dict) and "keep" in x:
        return m["dup_of"].format(dup=m["page"].format(n=x["dup"]), keep=m["page"].format(n=x["keep"]))
    if isinstance(x, dict) and "tour" in x:
        return f"{m['page'].format(n=x['page'])} → {x['tour']}"
    return str(x)
