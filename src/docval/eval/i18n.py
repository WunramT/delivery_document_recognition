"""UI texts of the pages for label work (editor, label comparison) in German and Polish.

Class and doc type names stay the data values in the files; the pages only show a
translated display name next to them.
"""

from __future__ import annotations

LANGS = ("de", "pl")
SUFFIX = {"de": "", "pl": "_pl"}   # editor.html / editor_pl.html, 425.html / 425_pl.html

CLASS_NAMES = {
    "de": {"unterschrift": "Unterschrift", "stempel": "Stempel", "tour_nummer": "Tournummer",
           "cmr_count": "CMR-Zählung"},
    "pl": {"unterschrift": "podpis", "stempel": "pieczątka", "tour_nummer": "numer trasy",
           "cmr_count": "licznik CMR"},
}
DOC_TYPE_NAMES = {
    "de": {"cmr": "CMR", "lieferschein": "Lieferschein", "loading_list": "Loading List"},
    "pl": {"cmr": "CMR", "lieferschein": "dowód dostawy (WZ)", "loading_list": "lista załadunkowa"},
}

EDITOR = {
    "de": {
        "html_lang": "de", "title": "Label-Editor", "doctype": "Dokumenttyp", "done": "Geprüft ✓ + weiter",
        "save": "COCO speichern", "savecsv": "page_types.csv speichern",
        "f_all": "alle Seiten", "f_changed": "mit Modell-Vorschlägen", "f_open": "ungeprüft",
        "h_class": "Klasse (neue Box / Auswahl ändern)", "h_sel": "Auswahl", "sel_none": "keine – Box anklicken",
        "h_changes": "Vorschläge des Modells", "h_help": "Bedienung", "none": "keine",
        "help": [
            ["Box ziehen", "auf freier Fläche aufziehen = neue Box"],
            ["Box", "anklicken, verschieben; Ecken/Kanten ziehen = Größe"],
            ["<kbd>1</kbd>–<kbd>9</kbd>", "Klasse wählen / Auswahl umstellen"],
            ["<kbd>Entf</kbd>", "Auswahl löschen"],
            ["<kbd>Pfeile</kbd>", "Auswahl verschieben (<kbd>Shift</kbd> = 10 px, <kbd>Alt</kbd> = Größe)"],
            ["<kbd>Strg</kbd>+<kbd>Z</kbd>", "Rückgängig"],
            ["<kbd>A</kbd> / <kbd>D</kbd>", "vorige / nächste Seite"],
            ["<kbd>Enter</kbd>", "geprüft + nächste Seite"],
            ["<kbd>O</kbd>", "(Buchstabe) alte Labels ein/aus, grau gestrichelt"],
            ["<kbd>+</kbd> <kbd>-</kbd> <kbd>0</kbd>", "Zoom, <kbd>0</kbd> = Breite"],
        ],
        "note": "Gestrichelt = Vorschlag des Modells (noch nicht angefasst). Der Zwischenstand bleibt im Browser "
                "gespeichert. Zum Schluss „COCO speichern“ und die Datei nach <code>labels/{export}/</code> legen "
                "(alte vorher sichern).",
        "loaded": "Zwischenstand aus dem Browser geladen ({n} Seiten geprüft). ",
        "discard": "verwerfen und neu beginnen", "confirm_discard": "Alle Änderungen in diesem Editor verwerfen?",
        "progress": "{done} / {total} geprüft", "img_missing": "Bild nicht gefunden: ", "short_prop": "Vorschl.",
        "confirm_open": "{n} Seiten sind noch nicht als geprüft markiert. Trotzdem speichern?",
        "src": {"modell": "Modell-Vorschlag", "manuell": "manuell", "label": "Label"},
        "actions": {"ersetzt": "Box ersetzt durch Modellbox:", "hinzugefügt": "vom Modell ergänzt:",
                    "hinzugefügt_alternative": "Modellbox zusätzlich:",
                    "hinzugefügt_andere_klasse": "ergänzt (andere Klasse):",
                    "entfernt_doppelt": "doppeltes Label entfernt:", "angepasst": "an Modellbox angepasst:"},
        "score": "Score",
    },
    "pl": {
        "html_lang": "pl", "title": "Edytor etykiet", "doctype": "Typ dokumentu", "done": "Sprawdzone ✓ + dalej",
        "save": "Zapisz COCO", "savecsv": "Zapisz page_types.csv",
        "f_all": "wszystkie strony", "f_changed": "z propozycjami modelu", "f_open": "niesprawdzone",
        "h_class": "Klasa (nowa ramka / zmiana zaznaczonej)", "h_sel": "Zaznaczenie",
        "sel_none": "brak – kliknij ramkę", "h_changes": "Propozycje modelu", "h_help": "Obsługa", "none": "brak",
        "help": [
            ["Przeciągnij", "na pustym miejscu = nowa ramka"],
            ["Ramka", "kliknij, przesuń; przeciągnij róg/krawędź = rozmiar"],
            ["<kbd>1</kbd>–<kbd>9</kbd>", "wybierz klasę / zmień klasę zaznaczonej ramki"],
            ["<kbd>Delete</kbd>", "usuń zaznaczoną ramkę"],
            ["<kbd>Strzałki</kbd>", "przesuń zaznaczenie (<kbd>Shift</kbd> = 10 px, <kbd>Alt</kbd> = rozmiar)"],
            ["<kbd>Ctrl</kbd>+<kbd>Z</kbd>", "cofnij"],
            ["<kbd>A</kbd> / <kbd>D</kbd>", "poprzednia / następna strona"],
            ["<kbd>Enter</kbd>", "sprawdzone + następna strona"],
            ["<kbd>O</kbd>", "(litera) stare etykiety wł./wył., szara przerywana linia"],
            ["<kbd>+</kbd> <kbd>-</kbd> <kbd>0</kbd>", "powiększenie, <kbd>0</kbd> = do szerokości"],
        ],
        "note": "Linia przerywana = propozycja modelu (jeszcze nieedytowana). Stan pracy zapisuje się w przeglądarce. "
                "Na koniec „Zapisz COCO” i umieść plik w <code>labels/{export}/</code> (wcześniej zrób kopię "
                "starego pliku).",
        "loaded": "Wczytano zapisany stan z przeglądarki (sprawdzone strony: {n}). ",
        "discard": "odrzuć i zacznij od nowa", "confirm_discard": "Odrzucić wszystkie zmiany w tym edytorze?",
        "progress": "sprawdzono {done} / {total}", "img_missing": "Nie znaleziono obrazu: ", "short_prop": "prop.",
        "confirm_open": "Stron nieoznaczonych jako sprawdzone: {n}. Zapisać mimo to?",
        "src": {"modell": "propozycja modelu", "manuell": "ręcznie", "label": "etykieta"},
        "actions": {"ersetzt": "ramka zastąpiona ramką modelu:", "hinzugefügt": "dodane przez model:",
                    "hinzugefügt_alternative": "dodatkowa ramka modelu:",
                    "hinzugefügt_andere_klasse": "dodane (inna klasa):",
                    "entfernt_doppelt": "usunięto zduplikowaną etykietę:",
                    "angepasst": "dopasowane do ramki modelu:"},
        "score": "wynik",
    },
}

COMPARE = {
    "de": {
        "html_lang": "de", "title": "Labels vorher / nachher – Tour {export}",
        "sub": "{pages} Seiten · {changed} geändert · {adj} Boxen angepasst · {add} ergänzt · {rem} entfernt",
        "h_guide": "So sollen die Labels aussehen", "h_changes": "Was sich geändert hat",
        "cols": ["Klasse", "Boxen vorher → nachher", "ergänzt", "entfernt", "angepasst", "Fläche nachher / vorher",
                 "Größe (Median, Breite × Höhe der Seite)", "Streuung der Boxgröße"],
        "table_note": "„Streuung“ = Variationskoeffizient der Boxfläche: je kleiner, desto einheitlicher sind die "
                      "Boxen gezogen. Fläche &lt; 1 = die neuen Boxen sind enger.",
        "h_close": "Nahaufnahmen: vorher und nachher", "before": "vorher", "after": "nachher",
        "was_missing": "fehlte vorher", "overlap": "Überlappung alt/neu {v}",
        "h_pages": "Seiten mit Änderungen ({n})", "top_pages": "Die {n} Seiten mit den meisten Änderungen.",
        "added": "{n} ergänzt ({c})", "removed": "{n} entfernt ({c})", "adjusted": "{n} angepasst ({c})",
        "old": "Alt", "new": "Neu",
    },
    "pl": {
        "html_lang": "pl", "title": "Etykiety przed / po – trasa {export}",
        "sub": "stron: {pages} · zmienionych: {changed} · ramek dopasowanych: {adj} · dodanych: {add} · "
               "usuniętych: {rem}",
        "h_guide": "Jak powinny wyglądać etykiety", "h_changes": "Co się zmieniło",
        "cols": ["Klasa", "Ramki przed → po", "dodane", "usunięte", "dopasowane", "Powierzchnia po / przed",
                 "Rozmiar (mediana, szerokość × wysokość strony)", "Rozrzut rozmiaru ramek"],
        "table_note": "„Rozrzut” = współczynnik zmienności powierzchni ramki: im mniejszy, tym bardziej jednolicie "
                      "narysowane są ramki. Powierzchnia &lt; 1 = nowe ramki są ciaśniejsze.",
        "h_close": "Zbliżenia: przed i po", "before": "przed", "after": "po",
        "was_missing": "wcześniej brak etykiety", "overlap": "pokrycie stara/nowa {v}",
        "h_pages": "Strony ze zmianami ({n})", "top_pages": "{n} stron z największą liczbą zmian.",
        "added": "dodane: {n} ({c})", "removed": "usunięte: {n} ({c})", "adjusted": "dopasowane: {n} ({c})",
        "old": "Stare", "new": "Nowe",
    },
}

GUIDE = {
    "de": {
        "allgemein": ["Jedes sichtbare Objekt bekommt genau eine Box – nichts auslassen, nichts doppelt.",
                      "Box eng um den Inhalt ziehen (wenige Pixel Rand), nicht um das ganze Feld.",
                      "CMR: die vorgedruckten Unterschriften/Stempel in Feld 22 und 23 nicht labeln."],
        "unterschrift": "nur die handschriftliche Unterschrift, eng um die Tinte",
        "stempel": "der ganze Stempelabdruck, eng um den Abdruck",
        "tour_nummer": "die Tournummer vollständig (Tour/Datum/Werk), eng",
        "cmr_count": "„CMR i/n“ vollständig, eng",
    },
    "pl": {
        "allgemein": ["Każdy widoczny obiekt dostaje dokładnie jedną ramkę – niczego nie pomijać, niczego nie "
                      "dublować.",
                      "Ramka ciasno wokół treści (kilka pikseli marginesu), a nie wokół całego pola.",
                      "CMR: nie oznaczać nadrukowanych podpisów/pieczątek w polach 22 i 23."],
        "unterschrift": "tylko odręczny podpis, ciasno wokół tuszu",
        "stempel": "cały odcisk pieczątki, ciasno wokół odcisku",
        "tour_nummer": "pełny numer trasy (trasa/data/zakład), ciasno",
        "cmr_count": "„CMR i/n” w całości, ciasno",
    },
}


def languages(cfg: dict) -> list[str]:
    langs = [x for x in (cfg.get("ui_languages") or ["de"]) if x in LANGS]
    return langs or ["de"]


def guide(cfg: dict, lang: str) -> dict:
    """config label_guide: {de: {...}, pl: {...}} (or a flat dict = German)."""
    g = cfg.get("label_guide") or {}
    own = g.get(lang) if isinstance(g.get(lang), dict) else (g if lang == "de" and "de" not in g else {})
    return {**GUIDE[lang], **(own or {})}
