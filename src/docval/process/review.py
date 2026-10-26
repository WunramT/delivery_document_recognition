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
        "step_locked": "Erst die Schritte davor bestätigen.", "open_issues": "Noch offen ({n})",
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
        "s4_intro": "Was fehlt, steht hier gesammelt – mit Bild (Klick öffnet die Seite). Jeder Punkt kann mit Grund "
                    "trotzdem akzeptiert werden. Was nicht akzeptiert ist, steht im Protokoll unter „Zu tun“ (nachfordern). "
                    "Erst nach „Fehlliste bestätigen“ entstehen die Archiv-Mails (CMR- und Lieferschein-PDF ans Archiv).",
        "sum_cmr": "CMR", "sum_ls": "Lieferscheine", "sum_struck": "gestrichene TAs", "sum_corr": "korrigierte Seiten",
        "sum_boxes": "gezeichnete Boxen", "reviewer": "Prüfer/in",
        "missing_none": "Nichts fehlt.", "accept": "trotzdem akzeptieren", "accepted": "akzeptiert",
        "undo": "zurücknehmen", "note": "Bemerkung", "cancel": "abbrechen", "choose": "– wählen –",
        "note_needed": "Bei „Sonstiges“ bitte eine Bemerkung eintragen.",
        "confirm_missing": "Fehlliste bestätigen ({n} offen → Protokoll „Zu tun“)", "missing_confirmed": "Fehlliste bestätigt",
        "missing_changed": "Die Liste hat sich seit der Bestätigung geändert – bitte erneut bestätigen.",
        "save_need_name": "Bitte zuerst Ihren Namen bei „Prüfer/in“ eintragen.",
        "save_open": "Noch nicht alle Schritte sind bestätigt ({steps}). Trotzdem speichern? (Der Abschluss geht "
                     "erst, wenn alle bestätigt sind.)",
        "save_unconfirmed": "Die Fehlliste ist noch nicht bestätigt – dann werden keine Mail-Entwürfe erzeugt. "
                            "Trotzdem speichern?",
        "saved": "Gespeichert um {time} (Download). Die Datei entscheidung.json in den Ordner dieser Seite legen.",
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
        "expected": "Normalerweise auf dieser Seite", "other_cls": "andere Objekte", "compare": "Kopien nebeneinander vergleichen",
        "archived": "wird archiviert", "iss_page": "Seitenzahl i/n eintragen", "ll_page": "Seite (i/n)",
        "page_draw": "Seitenzahl-Box zeichnen", "show_on_list": "auf der Ladeliste zeigen",
        "ta_no_cmr_s": "auf der Ladeliste, aber auf keinem CMR", "ta_extra_s": "auf CMR {page}, nicht auf der Ladeliste",
        "tav_hint": "Ladeliste zum Nachsehen – Strg + Mausrad zoomt, ziehen verschiebt",
        "live_ocr": "Live-OCR an", "ocr_check": "OCR – bitte prüfen", "ocr_busy": "OCR liest …",
        "ocr_none": "nicht erkannt: „{text}“", "saved_srv": "Gespeichert um {time} – die Tour ist fertig geprüft.",
        "save_failed": "Speichern über den Server fehlgeschlagen – die Datei wird stattdessen heruntergeladen.",
        "model_boxes": "Erkannte Boxen (ein-/ausschalten)", "box_on": "zählt", "box_off": "verworfen", "box_toggle": "umschalten",
        "ta_on_cmr": "TAs auf diesem CMR", "ta_ok": "auf der Ladeliste", "ta_bad": "nicht auf der Ladeliste",
        "ta_struck_s": "gestrichen", "peek_hint": "Vorschau – Klick öffnet die Seite zum Bearbeiten",
        "close_x": "Schließen",
        "tech_next": "Für die Technik: make finalize RUN={name}", "ph_ta": "TA eintippen", "ph_num": "Nummer eintippen",
        "ph_page": "z. B. 2/2", "ph_cmr": "z. B. 3/7", "ph_tour": "Tournummer eintippen", "ta_typed": "eingetippt",
        "sure": "sicher", "unsure": "unsicher", "page_q": "S. {n} gelesen als „{text}“ – ist das Seite {i}/{total}?",
        "page_is": "ja, S. {n} = {i}/{total}", "iss_lspage": "Seitenzahl eintragen", "one_page": "einseitig (1/1)",
        "box_optional": "Box um die Nummer ist freiwillig – ohne Box zählt die Seite nicht als geprüftes Trainingsbeispiel.",
        "all_done": "In diesem Schritt ist nichts mehr offen – jetzt „Schritt bestätigen und weiter“.",
        "draw_banner": "Box um „{cls}“ ziehen – Esc bricht ab", "ok_rows": "{n} TAs ohne Befund – anzeigen",
        "carrier_ok": "Sammelbestätigung geprüft", "carrier_done": "geprüft ✓", "iss_carrier": "Hermes/DHL: Sammelbestätigung prüfen",
        "fin_name": "Ihr Name", "fin_list": "Fehlliste bestätigen", "fin_save": "Speichern",
        "saved_title": "Gespeichert", "name_ph": "Ihr Name", "nothing_left": "Keine offenen Punkte mehr.",
        "suggestion": "Vorschlag",
        "fin_title": "Abschluss erzeugt", "fin_files": "Dateien im Ordner „freigabe“ der Tour:", "fin_prot": "Protokoll anzeigen",
        "fin_todo": "{n} Punkte unter „Zu tun“ im Protokoll", "fin_again": "neu erzeugen", "lvl_err": "Fehler", "lvl_hint": "Hinweis",
        "to_list": "→ Fehlliste", "kept_mark": "behalten trotz Handvermerk", "keep_t": "TA zählt als verladen – braucht CMR und Lieferschein",
        "strike_t": "TA nicht verladen – kein CMR/Lieferschein nötig", "discard_row": "verwerfen", "dup_ta": "doppelt (auch Zeile {i})",
        "iss_dup": "TA steht doppelt in der Liste – eine Zeile verwerfen", "need_reason": "Bitte einen Grund wählen.",
        "acc_title": "Trotzdem akzeptieren – Grund:", "go_on": "Weiter →", "wheel_hint": "Strg + Mausrad zoomt",
        "carrier_help": "Hermes/DHL unterschreiben nicht auf dem Lieferschein, sondern auf einer Sammelbestätigung (eigene Seite im Stapel).",
        "carrier_show": "Sammelbestätigung ansehen ({p})", "carrier_none": "Keine Sammelbestätigung im Stapel gefunden.",
        "st_missing": "fehlt", "st_nn": "nicht nötig", "open_n": "offen", "todo_head": "Zu tun",
        "steps_short": ["Zuordnen", "Ladeliste", "LS", "CMR", "Abschluss"],
        "iss_mark": "Handvermerk in der Zeile – streichen oder behalten", "mark_q": "Handvermerk – gestrichen?",
        "keep": "behalten", "kept": "behalten", "iss_bad": "ungültige Eingabe korrigieren", "revert": "↺ gelesener Wert",
        "bad_page": "Bitte als i/n eintragen, z. B. 2/2.", "bad_cmr": "Bitte als i/n eintragen, z. B. 3/7.",
        "bad_ta": "Nur 8-stellige Nummern, mit Komma getrennt.",
        "stale_step": "Seit der Bestätigung geändert – bitte erneut bestätigen.",
        "reconfirm": "Durch die Änderung müssen diese Schritte neu bestätigt werden: {steps}",
        "stale_saved": "Gespeicherter Stand veraltet – bitte erneut speichern", "nothing_open": "Nichts mehr offen",
        "findings": "{n} Befunde gehen in die Fehlliste", "incomplete": "unvollständig", "check": "prüfen",
        "type_done": "✓ Typ: {t}", "oclock": " Uhr", "tech": "Für die Technik",
        "ta_wo_cmr": "TAs ohne CMR auf der Ladeliste:", "row_on_list": "Zeile auf der Ladeliste:",
        "iss_found": "TA ohne Box gefunden – übernehmen oder löschen", "found_q": "ohne Box gefunden – übernehmen?",
        "take": "übernehmen", "remove": "Zeile löschen", "saved_btn": "✓ Gespeichert {time}", "save_stale": "Speichern (veraltet)",
        "name_first": "Erst den Namen eintragen.", "not_found": "nicht gefunden", "copy_of": "Kopie S. {n}",
        "not_needed": "nicht nötig (Stempel reicht)",
        "iss_pages_conflict": "Seitenzahlen widersprechen sich ({list}) – welche stimmt?",
        "fin_btn": "Abschluss erzeugen (PDFs, Mail-Entwürfe, Protokoll)", "fin_busy": "Abschluss wird erzeugt …",
        "fin_ok": "Fertig – Dateien im Ordner {out}", "fin_fail": "Abschluss nicht erzeugt:",
        "box_obj_optional": "Box freiwillig: Box zeichnen (B) macht die Seite zum geprüften Trainingsbeispiel.",
        "evidence": "Prüfbereich",
    },
    "pl": {
        "html_lang": "pl", "title": "Kontrola trasy", "save": "Zapisz decyzję", "discard": "odrzuć wszystko",
        "steps": ["Przypisanie stron", "Lista załadunkowa", "Dowody dostawy", "CMR", "Zamknięcie"],
        "step_confirm": "Potwierdź krok i dalej", "step_done": "Krok potwierdzony",
        "step_locked": "Najpierw potwierdź poprzednie kroki.", "open_issues": "Otwarte ({n})",
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
        "s4_intro": "Tu zebrane są wszystkie braki – z obrazem (kliknięcie otwiera stronę). Każdy punkt można "
                    "zaakceptować z powodem. Niezaakceptowane trafią do protokołu w „Do zrobienia” (dosłać). E-maile do "
                    "archiwum (PDF CMR i WZ) powstaną dopiero po „Potwierdź listę braków”.",
        "sum_cmr": "CMR", "sum_ls": "dowody dostawy", "sum_struck": "skreślone TA", "sum_corr": "poprawione strony",
        "sum_boxes": "narysowane ramki", "reviewer": "Sprawdzający",
        "missing_none": "Niczego nie brakuje.", "accept": "mimo to zaakceptuj", "accepted": "zaakceptowano",
        "undo": "cofnij", "note": "uwaga", "cancel": "anuluj", "choose": "– wybierz –",
        "note_needed": "Przy „Inne” proszę wpisać uwagę.",
        "confirm_missing": "Potwierdź listę braków ({n} otwarte → protokół „Do zrobienia”)",
        "missing_confirmed": "Lista braków potwierdzona",
        "missing_changed": "Lista zmieniła się od potwierdzenia – proszę potwierdzić ponownie.",
        "save_need_name": "Najpierw wpisz swoje imię i nazwisko w polu „Sprawdzający”.",
        "save_open": "Nie wszystkie kroki są potwierdzone ({steps}). Zapisać mimo to? (Zamknięcie jest możliwe "
                     "dopiero po potwierdzeniu wszystkich.)",
        "save_unconfirmed": "Lista braków nie jest potwierdzona – szkice e-maili nie zostaną utworzone. "
                            "Zapisać mimo to?",
        "saved": "Zapisano o {time} (pobrano). Plik entscheidung.json umieść w folderze tej strony.",
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
        "expected": "Zwykle na tej stronie", "other_cls": "inne obiekty", "compare": "porównaj kopie obok siebie",
        "archived": "będzie archiwizowana", "iss_page": "wpisz numer strony i/n", "ll_page": "strona (i/n)",
        "page_draw": "narysuj ramkę numeru strony", "show_on_list": "pokaż na liście załadunkowej",
        "ta_no_cmr_s": "na liście załadunkowej, ale na żadnym CMR", "ta_extra_s": "na CMR {page}, nie ma na liście załadunkowej",
        "tav_hint": "Lista załadunkowa do sprawdzenia – Ctrl + kółko myszy = zoom, przeciąganie przesuwa",
        "live_ocr": "OCR na żywo", "ocr_check": "OCR – sprawdzić", "ocr_busy": "OCR czyta …",
        "ocr_none": "nie rozpoznano: „{text}“", "saved_srv": "Zapisano o {time} – trasa sprawdzona.",
        "save_failed": "Zapis przez serwer nie powiódł się – plik zostanie pobrany.",
        "model_boxes": "Rozpoznane ramki (wł./wył.)", "box_on": "liczy się", "box_off": "odrzucona", "box_toggle": "przełącz",
        "ta_on_cmr": "TA na tym CMR", "ta_ok": "na liście załadunkowej", "ta_bad": "nie ma na liście załadunkowej",
        "ta_struck_s": "skreślone", "peek_hint": "Podgląd – kliknięcie otwiera stronę do edycji",
        "close_x": "Zamknij",
        "tech_next": "Dla działu IT: make finalize RUN={name}", "ph_ta": "wpisz TA", "ph_num": "wpisz numer",
        "ph_page": "np. 2/2", "ph_cmr": "np. 3/7", "ph_tour": "wpisz numer trasy", "ta_typed": "wpisano",
        "sure": "pewne", "unsure": "niepewne", "page_q": "str. {n} odczytano jako „{text}“ – czy to strona {i}/{total}?",
        "page_is": "tak, str. {n} = {i}/{total}", "iss_lspage": "wpisz numer strony", "one_page": "jednostronicowy (1/1)",
        "box_optional": "Ramka wokół numeru jest dobrowolna – bez ramki strona nie liczy się jako sprawdzony przykład do treningu.",
        "all_done": "W tym kroku nic nie zostało – teraz „Potwierdź krok i dalej”.",
        "draw_banner": "Zaznacz ramkę „{cls}” – Esc anuluje", "ok_rows": "{n} TA bez uwag – pokaż",
        "carrier_ok": "potwierdzenie zbiorcze sprawdzone", "carrier_done": "sprawdzone ✓",
        "iss_carrier": "Hermes/DHL: sprawdzić potwierdzenie zbiorcze",
        "fin_name": "Imię i nazwisko", "fin_list": "Potwierdź listę braków", "fin_save": "Zapisz",
        "saved_title": "Zapisano", "name_ph": "imię i nazwisko", "nothing_left": "Brak otwartych punktów.",
        "suggestion": "propozycja",
        "fin_title": "Zamknięcie utworzone", "fin_files": "Pliki w folderze „freigabe” trasy:", "fin_prot": "pokaż protokół",
        "fin_todo": "{n} punktów w „Do zrobienia” w protokole", "fin_again": "utwórz ponownie", "lvl_err": "błąd", "lvl_hint": "uwaga",
        "to_list": "→ lista braków", "kept_mark": "zostawione mimo uwagi", "keep_t": "TA liczy się jako załadowane – potrzebuje CMR i WZ",
        "strike_t": "TA nie załadowane – CMR/WZ niepotrzebne", "discard_row": "odrzuć", "dup_ta": "podwójnie (też wiersz {i})",
        "iss_dup": "TA podwójnie na liście – odrzuć jeden wiersz", "need_reason": "Proszę wybrać powód.",
        "acc_title": "Mimo to zaakceptuj – powód:", "go_on": "Dalej →", "wheel_hint": "Ctrl + kółko myszy = zoom",
        "carrier_help": "Hermes/DHL nie podpisują WZ, tylko potwierdzenie zbiorcze (osobna strona w stosie).",
        "carrier_show": "pokaż potwierdzenie zbiorcze ({p})", "carrier_none": "Nie znaleziono potwierdzenia zbiorczego w stosie.",
        "st_missing": "brak", "st_nn": "niepotrzebne", "open_n": "otwarte", "todo_head": "Do zrobienia",
        "steps_short": ["Przypisanie", "Lista", "WZ", "CMR", "Koniec"],
        "iss_mark": "odręczna uwaga w wierszu – skreślić lub zostawić", "mark_q": "odręczna uwaga – skreślone?",
        "keep": "zostaw", "kept": "zostawione", "iss_bad": "popraw nieprawidłowy wpis", "revert": "↺ odczytana wartość",
        "bad_page": "Proszę wpisać jako i/n, np. 2/2.", "bad_cmr": "Proszę wpisać jako i/n, np. 3/7.",
        "bad_ta": "Tylko numery 8-cyfrowe, oddzielone przecinkiem.",
        "stale_step": "Zmienione od potwierdzenia – proszę potwierdzić ponownie.",
        "reconfirm": "Po tej zmianie trzeba ponownie potwierdzić kroki: {steps}",
        "stale_saved": "Zapisany stan nieaktualny – proszę zapisać ponownie", "nothing_open": "Nic nie zostało",
        "findings": "{n} braków trafi na listę braków", "incomplete": "niekompletny", "check": "sprawdzić",
        "type_done": "✓ typ: {t}", "oclock": "", "tech": "Dla działu IT",
        "ta_wo_cmr": "TA bez CMR na liście załadunkowej:", "row_on_list": "Wiersz na liście załadunkowej:",
        "iss_found": "TA znalezione bez ramki – przejąć lub usunąć", "found_q": "znalezione bez ramki – przejąć?",
        "take": "przejmij", "remove": "usuń wiersz", "saved_btn": "✓ Zapisano {time}", "save_stale": "Zapisz (nieaktualne)",
        "name_first": "Najpierw wpisz imię i nazwisko.", "not_found": "nie znaleziono", "copy_of": "kopia str. {n}",
        "not_needed": "niepotrzebne (pieczątka wystarczy)",
        "iss_pages_conflict": "Numery stron są sprzeczne ({list}) – który jest prawidłowy?",
        "fin_btn": "Utwórz zamknięcie (PDF, szkice e-maili, protokół)", "fin_busy": "Tworzenie zamknięcia …",
        "fin_ok": "Gotowe – pliki w folderze {out}", "fin_fail": "Zamknięcie nie zostało utworzone:",
        "box_obj_optional": "Ramka dobrowolna: narysuj ramkę (B), aby strona była sprawdzonym przykładem do treningu.",
        "evidence": "obszar kontroli",
    },
}

DT_EXTRA = {"de": {"loading_list": "Ladeliste", "sonstiges": "Sonstiges – verwerfen", "unsicher": "unklar"},
            "pl": {"sonstiges": "inne – odrzucić", "unsicher": "niejasne"}}
# reasons offered per missing item: something extra on the tour vs. something missing
REASONS_EXTRA = ["zuladung", "abgesprochen", "sonstiges"]
REASONS_MISSING = ["nachgereicht", "abgesprochen", "storniert", "sonstiges"]

# what the page needs of a page record (OCR texts of the header etc. stay in ergebnis.json)
PAGE_KEYS = ("n", "id", "image", "source", "w", "h", "doc_type", "doc_reason", "dets", "masked", "proposals",
             "scores", "tour", "cmr_count", "ta", "ta_unread", "ta_missed", "ls_number", "ls_page", "ls_read", "page_of", "page_read",
             "view", "mask_found", "carrier")


def page_data(result: dict, lang: str) -> dict:
    classes = result["classes"]
    return {
        "name": result["name"], "tour": result["tour"], "created": result["created"],
        "rules": result["rules"], "doc_types": [*result["doc_types"], *(["sonstiges"] if "sonstiges" not in result["doc_types"] else [])],
        "reasons_extra": REASONS_EXTRA, "reasons_missing": REASONS_MISSING, "ta_validated": bool(result.get("ta_validated")),
        "thr": result["thresholds"]["accept"], "classes": classes,
        "colors": {c: CLASS_COLORS[i % len(CLASS_COLORS)] for i, c in enumerate(classes)},
        "pages": [{k: p.get(k) for k in PAGE_KEYS} for p in result["pages"]],
    }


def write_review(out_dir: Path, result: dict, lang: str = "de") -> Path:
    t = UI[lang]
    dt = dict(DOC_TYPE_NAMES[lang], **DT_EXTRA[lang])
    js_t = dict(t, cls=CLASS_NAMES[lang], dt=dt, reasons=REASONS[lang],
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
header h1{font-size:16px;margin:0 8px 0 0;white-space:nowrap}
#stepper button{padding:4px 8px}
button,select,input{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--fg)}
button{cursor:pointer} button:disabled{cursor:default;background:#e4e4e8!important;color:#55555a!important;border-color:#d0d0d6!important}
button.primary{background:var(--sel);color:#fff;border-color:var(--sel)}
.muted{color:var(--muted)} .small{font-size:12.5px}
:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
.pill.acc{background:#eef5f0;color:#4f7a5c;border-color:#9bbfa5}
.bar.cb{position:sticky;bottom:0;z-index:4;background:#fff;box-shadow:0 -6px 16px rgba(0,0,0,.08)}
.stale{color:var(--warn);font-weight:600}
#stepper button.stale .no{background:var(--warn)}
.segs{display:flex;flex-wrap:wrap;gap:4px} .segs button{font-size:13px;padding:3px 8px} .segs button.on{background:var(--fg);color:#fff;border-color:var(--fg)}
.lbls{display:none}
#stepper{display:flex;gap:4px;flex-wrap:wrap}
#stepper button{display:flex;gap:6px;align-items:center}
#stepper button.cur{background:var(--fg);color:#fff;border-color:var(--fg)}
#stepper button.done .no{background:var(--ok)}
#stepper .no{display:inline-block;width:20px;height:20px;border-radius:10px;background:var(--muted);color:#fff;font-size:12px;line-height:20px;text-align:center}
main{max-width:1800px;margin:0 auto;padding:8px 16px 60px}
h2{font-size:17px;margin:14px 0 6px} h3{font-size:15px;margin:14px 0 6px}
#notice{display:none;position:fixed;top:58px;right:16px;max-width:560px;z-index:30;padding:10px 14px;border-radius:8px;
  background:#eef3fb;color:#1d3557;border:1px solid #c9d8f0;box-shadow:0 8px 24px rgba(0,0,0,.15)}
#notice.warn{background:var(--warnbg);color:#6b3f00;border-color:#f0c98a} #notice.ok{background:var(--okbg);color:var(--ok);border-color:#9bd3a8}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.issues{color:var(--err)}
.tiles{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start}
.tile{width:190px;border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;background:#fff;cursor:pointer;outline:none;font-size:13px}
.tile:focus{box-shadow:0 0 0 3px rgba(31,111,235,.45)}
.tile.v-ok{border-left-color:var(--ok)} .tile.v-bad{border-left-color:var(--err)} .tile.v-open{border-left-color:var(--warn)}
.tile.v-acc{border-left-color:#9bbfa5} .tile.done{border-left-color:#9bbfa5}
.tile.issue{border-color:var(--warn);border-style:dashed;border-left-style:solid}
.tile.dup{opacity:.5}
.tile .th{display:flex;justify-content:space-between;gap:4px;padding:2px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
.tile .tf{display:flex;gap:4px;flex-wrap:wrap;padding:2px 6px;border-top:1px solid var(--line)}
.thumb{position:relative;overflow:hidden;width:100%;background:var(--panel)}
.thumb img{position:absolute;display:block;user-select:none;pointer-events:none}
.thumb .b{position:absolute;border:2px solid;pointer-events:none}
.ph{width:190px;min-height:100px;border:1px solid var(--err);border-left:4px solid var(--err);border-radius:6px;background:var(--errbg);color:var(--err);padding:8px;font-size:13px}
.ph .tl{display:block;font-size:12px;color:#8a1f1f;margin-top:2px}
.ph.acc{border-color:#9bbfa5;background:#f3f8f4;color:#4f7a5c}
.st{font-weight:700} .st.y{color:var(--ok)} .st.n{color:var(--err)} .st.q{color:var(--warn)} .st.g{color:var(--muted);font-weight:400}
.chip{border:1px solid var(--line);border-radius:5px;padding:0 5px;font-size:12px}
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
.acc{color:#4f7a5c;font-size:13px} .accbtn{font-size:13px;padding:4px 2px;margin-top:2px;border:none;background:none;color:var(--sel);text-decoration:underline;min-height:28px}
.accform .ttl{font-weight:600;font-size:13px}
.accw{position:relative;display:inline-block}
.accform{position:absolute;z-index:8;left:0;top:calc(100% + 4px);width:280px;display:flex;flex-direction:column;gap:6px;padding:10px;
  background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 8px 28px rgba(0,0,0,.2);color:var(--fg);cursor:default}
.accform select,.accform input{width:100%} .accform .btns{display:flex;gap:6px;justify-content:flex-end}
input.need,select.need{border:2px solid var(--err);background:var(--errbg)}
ul.items{list-style:none;padding:0;margin:0} ul.items li{padding:8px 10px;border-radius:6px;margin-bottom:6px;display:flex;gap:14px;align-items:flex-start}
ul.items .itx{width:440px;flex:none} ul.items .mi{margin-top:0}
ul.items li.fehler{background:var(--errbg)} ul.items li.hinweis{background:var(--warnbg)} ul.items li.ok{background:var(--okbg)}
.ll{display:flex;gap:14px;align-items:flex-start;margin-bottom:20px}
.ll .vbox{flex:1;height:66vh;min-width:300px}
.ll .list{width:500px;flex:none}
.ll .rowcrop{margin:2px 0 4px} .ll tr.mark td{background:var(--warnbg)}
.ll table{border-collapse:collapse;width:100%;table-layout:fixed} .ll td{padding:3px 4px;border-bottom:1px solid var(--line);overflow:hidden}
.ll col.c1{width:126px} .ll col.c3{width:236px} .ll td:last-child{white-space:normal!important}
.ll tr.struck input{text-decoration:line-through;color:var(--err)}
.ll input.ta{width:110px}
.vw{position:relative;overflow:hidden;width:100%;height:100%;background:#e9e9ee;border:1px solid var(--line);cursor:grab;user-select:none}
.vw.drawing{cursor:crosshair}
.vin{position:absolute;left:0;top:0;transform-origin:0 0}
.vin img{display:block;width:100%;height:100%;pointer-events:none}
.vin .b{position:absolute;border:3px solid;cursor:pointer}
.vin .b span{display:none;position:absolute;left:-3px;bottom:100%;color:#fff;font-size:13px;padding:0 4px;white-space:nowrap;border-radius:2px;
  transform:scale(var(--ls,1));transform-origin:0 100%;z-index:2}
.vin .b:hover span{display:block}
.vin .b.weak{border-style:dashed;border-width:2px;opacity:.75}
.vin .b.rej{border-style:dashed;border-color:var(--err)!important;opacity:.8}
.vin .b.rej span{background:var(--err)!important}
.vin .b.struck{border-color:var(--err)!important;background:repeating-linear-gradient(-20deg,transparent 0 8px,rgba(201,42,42,.55) 8px 12px)}
.vin .b.struck span{background:var(--err)!important}
.vw .dban{display:none;position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:3;background:var(--sel);color:#fff;
  padding:6px 16px;border-radius:18px;font-weight:600;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.25);white-space:nowrap}
.vw.drawing{outline:3px solid var(--sel);outline-offset:-3px} .vw.drawing .dban{display:block}
.vin .b.person{border-width:4px}
.vin .b.ask{border-color:var(--warn)!important;background:rgba(255,170,0,.18)}
.vin .b.hl{box-shadow:0 0 0 5px rgba(31,111,235,.55);background:rgba(31,111,235,.12)}
.ll tr[data-row]:hover td{background:#eef4ff}
.vin .tmp{position:absolute;border:2px dashed #000;background:rgba(31,111,235,.15)}
.vin .mask{position:absolute;pointer-events:none;background:repeating-linear-gradient(45deg,rgba(110,110,115,.35) 0 6px,transparent 6px 12px)}
#ov{display:none;position:fixed;inset:0;z-index:20;background:rgba(20,20,25,.55);padding:18px}
#ov.on{display:flex}
#ovbox{display:flex;flex:1;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.35);min-height:0}
#ovx{position:absolute;top:22px;right:28px;z-index:2;font-size:20px;line-height:1;padding:4px 12px;border-radius:20px}
#peek{display:none;position:fixed;top:64px;bottom:84px;width:46vw;z-index:15;background:#fff;border:1px solid var(--line);
  border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.25);padding:8px;pointer-events:none}
#peek.on{display:flex;flex-direction:column} #peek .pv{flex:1;min-height:0;overflow:hidden;display:flex;justify-content:center}
#peek .thumb{height:100%;width:auto} #peek .ph2{font-size:12px;color:var(--muted);padding:4px}
.mb{display:flex;gap:6px;align-items:center;font-size:12.5px;margin:2px 0} .mb .sw{width:10px;height:10px;border-radius:2px;flex:none}
.mb.off span.nm{text-decoration:line-through;color:var(--muted)} .mb button{font-size:11px;padding:0 6px}
.tachips{display:flex;flex-wrap:wrap;gap:3px;margin:2px 0}
.chip.big{font-size:13px;padding:2px 8px}
.mi{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.mi .crop{cursor:pointer}
#ovimg{flex:1;padding:8px}
#ovside{width:400px;flex:none;border-left:1px solid var(--line);padding:12px;overflow:auto}
#ovside label{display:block;margin:6px 0 2px;font-size:12px;color:var(--muted)}
#ovside input.num{width:200px;font-size:16px}
.obj{display:flex;align-items:center;gap:6px;margin:6px 0;flex-wrap:wrap}
.obj .nm{width:110px;font-weight:600;display:flex;align-items:center;gap:6px} .obj .nm i{width:10px;height:10px;border-radius:2px;display:inline-block}
.obj button.on.y{background:var(--ok);border-color:var(--ok);color:#fff}
.obj button.on.n{background:var(--err);border-color:var(--err);color:#fff}
.hint{font-size:12px;color:var(--warn)}
.nav{display:flex;gap:6px;margin-top:14px;flex-wrap:wrap;position:sticky;bottom:-12px;background:#fff;padding:8px 0 12px;border-top:1px solid var(--line)}
.vbtns{display:flex;gap:4px;margin:6px 0;flex-wrap:wrap}
.vbtns button{font-size:13px;padding:2px 8px}
details summary{cursor:pointer;margin:10px 0}
.tile.t2{width:250px} .tile.t2.cm{width:206px}
.rows{display:block}
.copy{width:100%;font-size:12.5px;padding:4px 6px;border:1px dashed var(--line);border-radius:6px;background:var(--panel);cursor:pointer;display:flex;gap:6px;flex-wrap:wrap}
.danger{color:var(--err)!important;border-color:var(--err)}
#save.saved{border-color:var(--ok);color:var(--ok)} #save.stale{background:var(--warn);border-color:var(--warn);color:#fff}
.tag.ok{background:var(--okbg);color:var(--ok)}
.cr{padding:2px 6px} .cl{display:flex;justify-content:space-between;gap:6px;font-size:12px;color:var(--muted)} .cl b{color:var(--fg);font-size:12px}
.crop{position:relative;overflow:hidden;border:1px solid var(--line);background:var(--panel)} .crop img{position:absolute;max-width:none;pointer-events:none}
.nocrop{height:22px;border:1px dashed var(--line);color:var(--muted);text-align:center;font-size:12px;line-height:20px}
.objs{display:flex;gap:6px;padding:2px 6px 4px} .objs .oc{flex:1;min-width:0;overflow:hidden}
.tile select{width:100%}
.ph.q{border-color:var(--warn);background:var(--warnbg);color:var(--fg)} .ph button{margin-top:6px;font-size:12px}
#cmrgrid{row-gap:16px}
#toast{display:none;position:fixed;right:20px;bottom:20px;z-index:40;background:var(--ok);color:#fff;padding:12px 18px;border-radius:10px;
  box-shadow:0 8px 28px rgba(0,0,0,.25);font-weight:600} #toast.on{display:block}
.fin{display:flex;gap:10px;align-items:stretch;flex-wrap:wrap;margin:16px 0;position:sticky;bottom:0;z-index:4;background:#fff;padding:8px 0;box-shadow:0 -6px 16px rgba(0,0,0,.06)}
.lvl{font-size:12px;font-weight:600;padding:1px 7px;border-radius:9px;margin-right:6px} .lvl.fehler{background:var(--err);color:#fff} .lvl.hinweis{background:#f0c98a;color:#5a3500}
.mi .thumb{max-height:140px}
.exp .ex button{opacity:.35} .exp .ex:hover button,.exp .ex button.on,.exp .ex button:focus-visible{opacity:1}
.fin .fs{display:flex;gap:8px;align-items:center;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.fin .fs.ok{border-color:var(--ok);background:var(--okbg)}
.fin .no{display:inline-block;width:22px;height:22px;border-radius:11px;background:var(--muted);color:#fff;font-size:12px;line-height:22px;text-align:center;flex:none}
.fin .fs.ok .no{background:var(--ok)}
.savedbox{padding:12px 16px;border:2px solid var(--ok);border-radius:8px;background:var(--okbg);color:var(--ok);margin:10px 0}
.savedbox .muted{margin-top:4px}
#notice .x{float:right;cursor:pointer;padding:0 6px}
@media (max-width:1500px){.tile.t2.cm{zoom:.84} header h1 .tw{display:none} header .rl{display:none} header label input{width:130px!important} #stepper button{padding:4px 6px}}
.exp .ex{display:flex;gap:6px;align-items:center;margin:3px 0} .exp .nm{width:130px} .exp .sw{width:10px;height:10px;border-radius:2px;flex:none}
.exp button{font-size:13px;padding:1px 8px} .exp button.on{background:var(--sel);color:#fff;border-color:var(--sel)}
#cmp{display:none;position:fixed;inset:0;z-index:30;background:#fff;flex-direction:column} #cmp.on{display:flex}
.cmph{display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line);align-items:center}
#cmpb{flex:1;display:flex;gap:8px;padding:8px;min-height:0} .cpane{flex:1;display:flex;flex-direction:column;min-width:0}
.cv{flex:1;min-height:0} .cf{padding:6px 0;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.ocrtag{font-size:12.5px;padding:0 6px;border-radius:4px;background:#dbe7ff;color:#0a3d91;margin-left:4px;font-weight:600}
.tacheck{display:flex;gap:14px;align-items:flex-start} .tacheck .tal{width:470px;flex:none}
.tav{flex:1;height:75vh;position:sticky;top:60px;min-width:300px} .tai{padding:8px 0;border-bottom:1px solid var(--line)}
.sum{display:flex;gap:18px;flex-wrap:wrap;margin:8px 0}
.sum div{padding:8px 12px;border:1px solid var(--line);border-radius:8px} .sum b{font-size:20px;display:block}
</style></head><body>
<header>
  <h1 id="title"></h1>
  <div id="stepper"></div>
  <span style="flex:1"></span>
  <span id="srv" class="pill ok" style="display:none"></span>
  <label><span class="rl">{{reviewer}}</span> <input id="reviewer" autocomplete="name" placeholder="{{reviewer}}: {{name_ph}}" style="width:160px"></label>
  <button id="save">{{save}}</button>
</header>
<div id="notice"></div>
<main id="main"></main>
<div id="ov"><button id="ovx" title="Esc">✕</button><div id="ovbox"><div id="ovimg"></div><div id="ovside"></div></div></div>
<div id="peek"><div class="ph2" id="peekt"></div><div class="pv" id="peekv"></div></div>
<div id="cmp"><div class="cmph"><b id="cmpt"></b><span style="flex:1"></span><button data-cmpfit="full"></button><button data-cmpfit="area"></button><button data-cmpclose="1"></button></div><div id="cmpb"></div></div>
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
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && s.pages) { S = Object.assign(S, s); notice(T.loaded, 5000); } } catch (e) {}
let dirty = true, G = null, TM = null, SIG = {}, FERR = {};
function persist() { dirty = true; TM = null; SIG = {}; try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }
var NT = null;
function notice(msg, ms, kind) {   // a message at the top right, gone by itself after ms
  const n = $("notice"); clearTimeout(NT); n.className = kind || "";
  n.innerHTML = msg ? `<span class="x" title="${esc(T.close_x)}" onclick="notice('')">✕</span>${esc(msg)}` : ""; n.style.display = msg ? "block" : "none";
  if (msg && ms) NT = setTimeout(() => notice(""), ms);
}
function imgRetry(img) {   // a page image that did not load (busy disk/server): try twice more, then say so
  const k = +(img.dataset.retry || 0);
  if (k < 2) { img.dataset.retry = k + 1; const src = img.getAttribute("src"); setTimeout(() => { img.src = src.split("?")[0] + "?r=" + (k + 1); }, 400 * (k + 1)); }
  else { img.alt = T.img_missing + img.getAttribute("src").split("?")[0]; img.title = img.alt; }
}
const thrOf = c => D.thr[c] != null ? D.thr[c] : 0.5;

// ------------------------------------------------------------ effective values (person > model)
const us = p => S.pages[p.n] || (S.pages[p.n] = {});
const has = (p, k) => S.pages[p.n] && S.pages[p.n][k] != null && S.pages[p.n][k] !== "";
const docType = p => has(p, "doc_type") ? S.pages[p.n].doc_type : p.doc_type;
const reviewable = p => REVIEW.includes(docType(p));
function parseCount(s) { const m = /^\s*(?:cmr)?\s*(\d{1,3})\s*\/\s*(\d{1,3})\s*$/i.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] ? [+m[1], +m[2]] : null; }
function parse8(s) { const out = []; for (const m of String(s || "").matchAll(/(?<!\d)(?:\d ?){7}\d(?!\d)/g)) { const n = m[0].replace(/ /g, ""); if (!out.includes(n)) out.push(n); } return out; }
function parsePageOf(s) { const m = /^\s*(?:\D*?\s)?(\d{1,2})\s*\/\s*(\d{1,2})\s*$/.exec(s || ""); return m && +m[1] >= 1 && +m[1] <= +m[2] && +m[2] <= 30 ? [+m[1], +m[2]] : null; }
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
  if (!s.tl) s.tl = [...(p.ta || []).map(t => ({ta: t.ta, orig: t.ta, box: t.box || null, src: "model", mark: !!t.mark})),
                     ...(p.ta_unread || []).map(u => ({ta: "", orig: "", box: u.box, src: "model", unread: true, mark: !!u.mark})),
                     ...(p.ta_missed || []).map(u => ({ta: u.ta, orig: u.ta, box: u.box, src: "model", found: true, mark: !!u.mark}))]
                    .sort((a, b) => (a.box ? a.box[1] : 2) - (b.box ? b.box[1] : 2));
  // a TA box drawn anywhere (also in the large view of step 0) is a row of the list
  for (const b of s.pb || []) if (b.cls === "ta_nummer" && !s.tl.some(e => sameBox(e.box, b.box))) s.tl.push({ta: "", box: b.box, src: "person"});
  return s.tl;
}
const llPageOf = p => has(p, "page_of") ? parsePageOf(S.pages[p.n].page_of) : p.page_of || null;
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
  if (REVIEW.includes(t) && !tourOf(p)) add(0, T.iss_tour);
  if (otherTour(p)) return out;
  if (t === "loading_list" && !llPageOf(p) && llPages().length > 1) add(1, T.iss_page);
  if (t === "lieferschein") {
    if (!lsNumber(p)) add(2, T.iss_ls);
    if (!lsPage(p)) add(2, T.iss_lspage);
    if (p.carrier && !(S.carrier || {})[p.n]) add(2, T.iss_carrier);
  }
  if (t === "cmr" && !cmrCount(p)) add(3, T.iss_cmr);
  if (REVIEW.includes(t) && archive(p)) {
    if (unitValid(p) === null && valid(p) === null) add(stepOf(p), T.iss_decide);
  }
  return out;
}
const TYPED = {tour: "tour_nummer", page_of: "seitenzahl", ls: "ls_nummer", ls_page: "seitenzahl", cmr: "cmr_count", ta: "ta_nummer"};
function boxMissing(p) {   // numbers the person typed in without a box around them
  return [...Object.keys(TYPED).filter(f => has(p, f) && !hasPos(p, TYPED[f]) && !(f === "ta" && !cmrTAs(p).length)),
          ...(reviewable(p) ? rule(p).require.filter(c => val(p, c) === true && !hasPos(p, c)) : [])];
}
function pagesConflict(pages, get) {   // pages of one document that say different totals (1/2 and 2/3)
  const w = pages.filter(get); return new Set(w.map(p => get(p)[1])).size > 1 ? w : [];
}
function stepIssues(k) {
  const out = [];
  for (const p of D.pages) for (const x of pageIssues(p)) if (x.step === k) out.push({p, ...x});
  if (k === 1) for (const p of llPages()) for (const e of llEntries(p)) {
    if (e.struck) continue;
    if (e.bad != null) out.push({p, step: 1, text: T.iss_bad});
    else if (!okTA(e.ta)) out.push({p, step: 1, text: T.iss_ta});
    if ((e.mark || e.found) && !e.kept) out.push({p, step: 1, text: e.found ? T.iss_found : T.iss_mark});
    if (dupOf(p, e) != null) out.push({p, step: 1, text: T.iss_dup});
  }
  if (k === 1) { const c = pagesConflict(llPages(), llPageOf); for (const p of c) out.push({p, step: 1, text: fmt(T.iss_pages_conflict, {list: c.map(q => fmt(T.page, {n: q.n}) + " " + llPageOf(q).join("/")).join(", ")})}); }
  if (k === 2) for (const pgs of Object.values(lsByNumber())) { const c = pagesConflict(pgs, lsPage); for (const p of c) out.push({p, step: 2, text: fmt(T.iss_pages_conflict, {list: c.map(q => fmt(T.page, {n: q.n}) + " " + lsPage(q).join("/")).join(", ")})}); }
  for (const key in FERR) if (FERR[key].step === k) out.push({p: byN[FERR[key].n], step: k, text: T.iss_bad});
  return out;
}
function problemPages() {
  return D.pages.filter(p => p.doc_type === "unsicher" || pageIssues(p).some(x => x.step === 0) || otherTour(p)
    || ["abholschein", "bestaetigung"].includes(docType(p)) || (REVIEW.includes(docType(p)) && !tourOf(p) && !has(p, "tour")));
}
function sigOf(k) {   // what step k decided; a confirmation holds as long as this is unchanged
  if (SIG[k] != null) return SIG[k];
  const L = loaded();
  const v = k === 0 ? D.pages.map(p => [docType(p), tourOf(p)])
    : k === 1 ? [L, struckTAs(), llPages().map(llPageOf)]
    : k === 2 ? [L, lsPagesThisTour().map(p => [p.n, lsNumber(p), lsPage(p), unitValid(p), archive(p), !!(S.carrier || {})[p.n]])]
    : k === 3 ? [L, D.pages.filter(p => docType(p) === "cmr").map(p => [p.n, cmrCount(p), cmrTAs(p), valid(p), archive(p), otherTour(p)])]
    : decision();
  return SIG[k] = JSON.stringify(v);
}
function stepDone(k) {
  if (k === 4) return !!S.saved && S.saved.sig === sigOf(4);
  if (stepIssues(k).length) return false;
  if (k === 0 && !problemPages().length) return true;
  if (k === 1 && !llPages().length) return true;
  return !!S.steps[k] && (!S.stepSig || S.stepSig[k] == null || S.stepSig[k] === sigOf(k));
}
const stale = k => k < 4 ? !!S.steps[k] && !stepDone(k) : !!S.saved && !stepDone(4);
const canEnter = k => { for (let j = 0; j < k; j++) if (!stepDone(j)) return false; return true; };
function changed(k) { persist(); }
const touched = persist;
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
    const pos = ll.map(llPageOf), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1]));
    if (pos.every(Boolean) && !pagesConflict(ll, llPageOf).length) for (const i of missingPages(pos)) add("ll:" + i, "item_ll_page", "fehler", {i, total});
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
  const rs = /_extra:/.test(key) ? D.reasons_extra : D.reasons_missing;
  const form = accOpen !== key ? "" : `<div class="accform"><span class="ttl">${T.acc_title}</span><select data-accr><option value="">${T.choose}</option>${rs.map(k => `<option value="${k}">${esc(T.reasons[k] || k)}</option>`).join("")}</select>
    <input data-accn placeholder="${esc(T.note)}"><div class="btns"><button data-acccancel="1">${T.cancel}</button><button class="primary" data-accok="${esc(key)}">OK</button></div></div>`;
  return `<span class="accw"><button class="accbtn" data-acc="${esc(key)}">${T.accept}</button>${form}</span>`;
}

// ------------------------------------------------------------ tiles
function thumbHtml(p, v, all) {
  const [x1, y1, x2, y2] = v, rw = x2 - x1, rh = y2 - y1;
  const pos = b => `left:${(b[0] - x1) / rw * 100}%;top:${(b[1] - y1) / rh * 100}%;width:${(b[2] - b[0]) / rw * 100}%;height:${(b[3] - b[1]) / rh * 100}%`;
  let h = `<img src="${esc(p.image)}" alt="" onerror="imgRetry(this)" style="width:${100 / rw}%;left:${-x1 / rw * 100}%;top:${-y1 / rh * 100}%">`;
  for (const b of finalBoxes(p).pos) if (all || OBJ.includes(b.cls)) h += `<div class="b" style="${pos(b.box)};border-color:${D.colors[b.cls] || "#000"}"></div>`;
  return `<div class="thumb" style="aspect-ratio:${rw * p.w} / ${rh * p.h}">${h}</div>`;
}
function bestBox(p, cls) {
  const fb = finalBoxes(p).pos.filter(b => b.cls === cls);
  return fb.length ? (fb.find(b => b.src === "person") || fb.reduce((a, b) => (b.score || 0) > (a.score || 0) ? b : a)) : null;
}
function cropHtml(p, box, w, maxH, pad) {   // one part of the page, w px wide (narrower if it would be too high)
  const py = pad ? Math.max(pad * 1.5, (box[3] - box[1]) * 0.08) : 0;
  const x1 = Math.max(0, box[0] - pad), y1 = Math.max(0, box[1] - py), x2 = Math.min(1, box[2] + pad), y2 = Math.min(1, box[3] + py);
  const rw = x2 - x1, rh = y2 - y1, ar = (rh * p.h) / (rw * p.w);
  if (w * ar > maxH) w = maxH / ar;
  const sc = w / rw, ih = sc * p.h / p.w;
  return `<div class="crop" style="width:${w.toFixed(1)}px;height:${(w * ar).toFixed(1)}px"><img src="${esc(p.image)}" alt="" onerror="imgRetry(this)" style="width:${sc.toFixed(1)}px;height:${ih.toFixed(1)}px;left:${(-x1 * sc).toFixed(1)}px;top:${(-y1 * ih).toFixed(1)}px"></div>`;
}
function cropRow(p, cls, value, w = 236) {
  const b = bestBox(p, cls);
  return `<div class="cr"><div class="cl"><span>${esc(T.cls[cls] || cls)}</span><b>${esc(value || "?")}</b></div>${b ? cropHtml(p, b.box, w, 46, 0.006) : `<div class="nocrop">${T.not_found}</div>`}</div>`;
}
function objCrops(p, w = 112) {
  return `<div class="objs">` + rule(p).require.map(c => {
    const v = val(p, c), b = bestBox(p, c), nn = stCls(p, v) === "g";
    return `<div class="oc"><div class="cl"><span>${esc(T.cls[c] || c)}</span><span class="st ${stCls(p, v)}">${stSym(p, v, true)}</span></div>${b ? cropHtml(p, b.box, w, 80, 0.01) : `<div class="nocrop" title="${esc(nn ? T.not_needed : "")}">${nn ? "–" : T.not_found}</div>`}</div>`;
  }).join("") + `</div>`;
}
function tileBody(p) {   // the parts that decide: numbers next to what was read, stamp and signature
  const t = docType(p), tour = tourOf(p), tv = tour ? (tour === D.tour ? "✓ " + tour.split("/")[0] : tour) : "";
  if (t === "lieferschein") {
    const pg = lsPage(p);
    return cropRow(p, "ls_nummer", (lsNumber(p) || "") + (pg ? ` (${pg[0]}/${pg[1]})` : "")) + (backPage(p) ? "" : cropRow(p, "tour_nummer", tv)) + objCrops(p);
  }
  if (t === "cmr") {
    const cc = cmrCount(p), b = bestBox(p, "ta_nummer");
    return cropRow(p, "cmr_count", cc ? cc.join("/") : "", 192) +
      `<div class="cr"><div class="cl"><span>${esc(T.cls.ta_nummer)}</span></div>${taChips(p)}${b ? cropHtml(p, b.box, 192, 60, 0.003) : `<div class="nocrop">${T.not_found}</div>`}</div>` +
      cropRow(p, "tour_nummer", tv, 192) + objCrops(p, 90);
  }
  return null;
}
function taChips(p, big) {   // TAs of a CMR, each against the loading list
  const L = loaded(), st = struckTAs(), tas = cmrTAs(p);
  if (!tas.length) return `<div class="tachips"><span class="chip bad">?</span></div>`;
  return `<div class="tachips">` + tas.map(t => { const c = !L.length ? "" : L.includes(t) ? "ok" : st.includes(t) ? "" : "bad";
    return `<span class="chip ${c}${big ? " big" : ""}" title="${esc(!L.length ? "" : L.includes(t) ? T.ta_ok : st.includes(t) ? T.ta_struck_s : T.ta_bad)}">${t}${st.includes(t) ? " (" + T.ta_struck_s + ")" : ""}</span>`; }).join("") + `</div>`;
}
const accKeyOf = p => docType(p) === "lieferschein" && lsNumber(p) ? "ls_doc:" + lsNumber(p) : reviewable(p) ? "page:" + p.n : null;
const stCls = (p, v) => v === true ? "y" : v === false ? (rule(p).mode === "any" && unitValid(p) === true ? "g" : "n") : "q";   // not needed: grey
const stSym = (p, v, w) => v === true ? "✓" : v === false ? (rule(p).mode === "any" && unitValid(p) === true ? (w ? T.st_nn : "–") : (w ? T.st_missing : "✗")) : "?";
function stIcons(p, full) {
  return rule(p).require.map(c => { const v = val(p, c); return `<span class="st ${stCls(p, v)}" title="${esc(T.cls[c])}">${full ? esc(T.cls[c] || c) + ": " : (T.cls[c] || c)[0].toUpperCase()}${stSym(p, v, full)}</span>`; }).join(full ? " · " : " ");
}
function tileHtml(p, step, opts = {}) {
  const iss = pageIssues(p).filter(x => x.step === step);
  const v = unitValid(p), full = opts.full || !reviewable(p), acc = v === false && accKeyOf(p) && (S.accepted || {})[accKeyOf(p)];
  const cls = "tile " + (!archive(p) ? "dup " : "") + (iss.length ? "issue " : "") + (opts.done ? "done " : "") + (reviewable(p) ? (acc ? "v-acc" : v === true ? "v-ok" : v === false ? "v-bad" : "v-open") : "");
  let foot = reviewable(p) ? stIcons(p, true) : "";
  if (opts.foot) foot += opts.foot;
  if (!archive(p)) foot += ` <span class="muted">${T.dup}</span>`;
  const body = full ? null : tileBody(p);
  if (body) foot = opts.foot || "";
  if (body && !archive(p)) foot += ` <span class="muted">${T.dup}</span>`;
  return `<div class="${cls}${body ? " t2" : ""}${body && docType(p) === "cmr" ? " cm" : ""}" tabindex="0" role="button" aria-label="${esc(cardTitle(p) + ", " + fmt(T.page, {n: p.n}))}" data-open="${p.n}" data-step="${step}"><div class="th"><b>${esc(opts.label || cardTitle(p))}</b><span class="muted">${fmt(T.page, {n: p.n})}</span></div>
    ${body || thumbHtml(p, full ? [0, 0, 1, 1] : (p.view || [0, 0, 1, 1]))}<div class="tf">${foot}${iss.length ? `<span class="issues">· ${esc(iss[0].text)}${iss.length > 1 ? " +" + (iss.length - 1) : ""}</span>` : ""}</div></div>`;
}
const copyHtml = (p, step) => `<div class="copy" tabindex="0" data-open="${p.n}" data-step="${step}" title="${esc(T.dup)}">${fmt(T.copy_of, {n: p.n})} · ${stIcons(p, true)}</div>`;   // a copy that is not archived: small
const phHtml = (text, key) => `<div class="ph${key && (S.accepted || {})[key] ? " acc" : ""}">${esc(text)}${key && !(S.accepted || {})[key] ? `<span class="tl">${T.to_list}</span>` : ""}${key ? accHtml(key) : ""}</div>`;
const itemStep = key => { const k = key.split(":")[0]; return k === "ll" ? 1 : ["ls", "ls_doc", "ta_ls", "ta_ls_extra"].includes(k) ? 2 : ["cmr", "ta_cmr", "ta_cmr_extra"].includes(k) ? 3
  : k === "page" ? stepOf(byN[+key.split(":")[1]]) : 4; };
function confirmBar(k) {
  const iss = stepIssues(k), done = stepDone(k), nf = missingItems().filter(x => !x.accepted && itemStep(x.key) === k).length;
  return `<div class="bar cb" id="bar${k}">${done ? `<span class="pill ok">✓ ${T.step_done}</span>` : stale(k) ? `<span class="stale">${T.stale_step}</span>` : ""}
    ${iss.length ? `<span class="issues">${fmt(T.open_issues, {n: iss.length})}: ${iss.slice(0, 5).map(x => `<a data-open="${x.p.n}" data-step="${k}">${fmt(T.page, {n: x.p.n})}</a> ${esc(x.text)}`).join(" · ")}${iss.length > 5 ? " …" : ""}</span>`
      : `<span>${T.nothing_open}${nf ? " · " + fmt(T.findings, {n: nf}) : ""}</span>`}
    <span style="flex:1"></span>
    ${k < 4 ? `<button class="primary" data-confirm="${k}"${iss.length ? " disabled" : ""}>${done ? T.go_on : T.step_confirm}</button>` : ""}</div>`;
}

// ------------------------------------------------------------ step 0: assign pages
function render0() {
  const prob = problemPages();
  let h = `<h2>0 · ${T.steps[0]}</h2><p class="muted">${prob.length ? T.s0_intro : T.s0_none}</p><div class="tiles">`;
  for (const p of prob) {
    const why = [];
    if (docType(p) === "unsicher") why.push(T.why_dt);
    else if (has(p, "doc_type")) why.push(fmt(T.type_done, {t: T.dt[docType(p)] || docType(p)}));
    if (REVIEW.includes(docType(p)) && !(p.tour && p.tour.accepted) && !tourOf(p)) why.push(T.why_tour);
    if (otherTour(p)) why.push(fmt(T.why_other, {tour: otherTour(p)}));
    if (docType(p) === "abholschein") why.push(T.why_discard);
    if (docType(p) === "bestaetigung") why.push(T.why_conf);
    h += tileHtml(p, 0, {full: true, done: !pageIssues(p).some(x => x.step === 0), label: T.dt[docType(p)] || docType(p), foot: `<span class="small">${esc(why.join(" · "))}</span>`});
  }
  h += `</div><details${S.open0 ? " open" : ""} id="all0"><summary>${T.s0_all}</summary>`;
  const by = {};
  for (const p of D.pages) (by[docType(p)] = by[docType(p)] || []).push(p);
  for (const t of Object.keys(by)) {
    h += `<h3>${esc(T.dt[t] || t)} (${by[t].length})</h3><div class="tiles">` + by[t].map(p => `<div class="tile" style="width:160px" tabindex="0" data-open="${p.n}" data-step="0">
      <div class="th"><span>${fmt(T.page, {n: p.n})}</span></div>${thumbHtml(p, [0, 0, 1, 1])}<div class="tf"><select data-dt="${p.n}">${D.doc_types.concat(t === "unsicher" ? ["unsicher"] : []).map(x => `<option value="${x}"${x === t ? " selected" : ""}>${esc(T.dt[x] || x)}</option>`).join("")}</select></div></div>`).join("") + `</div>`;
  }
  return h + `</details>` + confirmBar(0);
}

// ------------------------------------------------------------ step 1: loading list
const LV = {};
let HL = null;   // loading-list row under the mouse: highlighted in the image too
document.addEventListener("mouseover", e => {
  const r = e.target.closest && e.target.closest("tr[data-row]"), k = r ? r.dataset.row : null;
  if (k === HL) return;
  const old = HL; HL = k;
  for (const n of new Set([old, k].filter(Boolean).map(x => +x.split(":")[0]))) if (LV[n]) LV[n].render();
  if (k) { const [n, i] = k.split(":").map(Number), en = llEntries(byN[n])[i]; if (LV[n] && en && en.box) LV[n].panTo(en.box); }
});
function render1() {
  const ll = llPages();
  let h = `<h2>1 · ${T.steps[1]}</h2>`;
  if (!ll.length) return h + `<p>${T.s1_none}</p>` + confirmBar(1);
  h += `<p class="muted">${T.s1_intro} · ${T.wheel_hint}</p>`;
  h += `<div id="llmiss">${llMissHtml()}</div>`;
  for (const p of ll) h += `<h3>${fmt(T.page, {n: p.n})}${llPageOf(p) ? ` · ${llPageOf(p)[0]}/${llPageOf(p)[1]}` : ""}</h3>
    <div class="ll"><div class="vbox" id="llv${p.n}"></div><div class="list" id="lll${p.n}">${llList(p)}</div></div>`;
  h += `<p id="llsum"><b>${fmt(T.loaded_n, {n: loaded().length})}</b> · ${fmt(T.struck_n, {n: struckTAs().length})}</p>`;
  return h + confirmBar(1);
}
function llMissHtml() {   // a missing page - or the question whether a page with an unread number is that page
  const ll = llPages(), pos = ll.map(llPageOf), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1])), miss = missingPages(pos);
  if (!miss.length || pagesConflict(ll, llPageOf).length) return "";
  const unk = ll.filter(p => !llPageOf(p));
  if (unk.length) return "";   // asked at the page-number field of the page without number
  return `<div class="tiles">${miss.map(i => phHtml(fmt(T.ll_missing, {i, n: total}), "ll:" + i)).join("")}</div>`;
}
const pageQ = (p, text, i, total, f) => `<div class="ph q">${esc(fmt(T.page_q, {n: p.n, text: text || "?", i, total}))}<br><button data-setpage="${p.n}" data-f="${f}" data-v="${i}/${total}">${esc(fmt(T.page_is, {n: p.n, i, total}))}</button></div>`;
function dupOf(p, e) {   // the same TA in an earlier row of the loading list: its row number (1..)
  if (e.struck || !okTA(e.ta)) return null;
  let k = 0;
  for (const q of llPages()) for (const x of llEntries(q)) { k++; if (x === e) return null; if (!x.struck && x.ta === e.ta) return k; }
  return null;
}
function llList(p) {
  const es = llEntries(p), po = llPageOf(p), iss = pageIssues(p).filter(x => x.step === 1);
  const read = p.page_read && p.page_read.text ? ` <span class="muted small">${T.ocr_read}: „${esc(p.page_read.text)}“</span>` : "";
  return `<p>${T.ll_page} <input data-llpage="${p.n}" placeholder="${esc(T.ph_page)}" class="${!po && llPages().length > 1 ? "need" : ""}" style="width:90px" value="${esc(has(p, "page_of") ? S.pages[p.n].page_of : po ? po.join("/") : "")}">${read}${ocrNote(p, "page_of")}</p>
    ${!po && llPages().length > 1 ? (() => { const pos = llPages().map(llPageOf), total = Math.max(0, ...pos.filter(Boolean).map(x => x[1])), miss = missingPages(pos).slice(0, 3);
      return miss.length ? `<div class="tiles">${miss.map(i => pageQ(p, (p.page_read || {}).text, i, total, "page_of")).join("")}</div>` : ""; })() : ""}
    ${iss.length ? `<p class="issues small">${iss.map(x => esc(x.text)).join(" · ")}</p>` : ""}<table><colgroup><col class="c1"><col><col class="c3"></colgroup>${es.map((e, i) => {
      const ask = (e.mark || e.found) && !e.struck && !e.kept, dup = dupOf(p, e), bad = !e.struck && (e.bad != null || !okTA(e.ta) || dup != null);
      const st = e.struck ? T.struck : e.bad != null ? `<span class="issues">${T.bad_number}</span>` : ask ? `<span class="stale">${e.found ? "✚ " + T.found_q : "✎ " + T.mark_q}</span>`
        : dup != null ? `<span class="issues">${fmt(T.dup_ta, {i: dup})}</span>` : e.kept && e.mark ? `<span class="stale">${T.kept_mark}</span>`
        : e.ocr ? `<span class="ocrtag">${T.ocr_check}</span>` : e.typed ? T.ta_typed : e.src === "person" ? (OCRBUSY && !e.ta ? T.ocr_busy : e.ocrt != null && !e.ta ? esc(fmt(T.ocr_none, {text: e.ocrt})) : T.ta_drawn)
        : !okTA(e.ta) ? T.ta_unread : T.ta_read;
      return `<tr data-row="${p.n}:${i}" class="${e.struck ? "struck" : ""}${ask ? " mark" : ""}"><td><input class="ta${bad ? " need" : ""}" data-ll="${p.n}" data-i="${i}" value="${esc(e.bad != null ? e.bad : e.ta)}" placeholder="${esc(T.ph_ta)}"></td>
    <td class="small ${bad ? "issues" : "muted"}">${st}${(e.typed || e.bad != null) && e.orig ? ` <a class="lnk" data-revert="${p.n}" data-i="${i}">${T.revert}</a>` : ""}</td>
    <td style="white-space:nowrap"><button class="small" data-strike="${p.n}" data-i="${i}" title="${esc(T.strike_t)}">${e.struck ? T.unstrike : T.strike}</button>${ask ? ` <button class="small" data-keep="${p.n}" data-i="${i}" title="${esc(T.keep_t)}">${e.found ? T.take : T.keep}</button>` : ""}${e.src === "person" || e.found ? ` <button class="small" data-delta="${p.n}" data-i="${i}" title="${esc(T.remove)}">${T.discard_row}</button>` : ""}</td></tr>
    ${e.box && (ask || e.struck || e.unread || e.mark || e.found || e.src === "person" || bad) ? `<tr data-row="${p.n}:${i}" class="${ask ? "mark" : ""}"><td colspan="3"><div class="rowcrop" data-tazoomll="${p.n}:${i}">${cropHtml(p, rowCrop(e.box), 480, 62, 0)}</div></td></tr>` : ""}`; }).join("")}</table>
    <p><button data-lldraw="${p.n}" data-cls="ta_nummer">${T.ta_draw}</button> <button data-lldraw="${p.n}" data-cls="seitenzahl">${T.page_draw}</button></p>`;
}
function mountLL() {
  for (const p of llPages()) {
    const el = $("llv" + p.n); if (!el) continue;
    const v = new Viewer(el, p, {
      inline: true,
      boxes: () => llBoxes(p),
      click: k => { if (!k.startsWith("e:")) return; const i = +k.split(":")[1]; const e = llEntries(p)[i]; if (e) { e.struck = !e.struck; changed(1); refresh1(p); } },
      draw: (box, cls) => {
        const ov = (a, b) => Math.min(a[2], b[2]) > Math.max(a[0], b[0]) && Math.min(a[3], b[3]) > Math.max(a[1], b[1]);
        const hit = cls === "ta_nummer" && llEntries(p).find(e => e.found && !e.kept && e.box && ov(e.box, box));
        if (hit) { hit.box = box; hit.kept = true; }
        us(p).pb = (us(p).pb || []).concat([{cls, box}]); changed(1); const es = llEntries(p); refresh1(p);
        if (cls === "ta_nummer") setTimeout(() => { const inp = document.querySelector(`input[data-ll="${p.n}"][data-i="${es.length - 1}"]`); if (inp) inp.focus(); }, 0);
        ocrBox(p, box, cls).then(() => { if (cls !== "ta_nummer") return; const inp = document.querySelector(`input[data-ll="${p.n}"][data-i="${es.length - 1}"]`); if (inp) { inp.focus(); inp.select(); } }); },
    });
    LV[p.n] = v; const cb = contentBox(p); v.fitWidth(cb[0], cb[2]);
  }
}
function contentBox(p) {   // the area with the found boxes (printed part of the page), full height
  const bs = [...p.dets.map(d => d.box), ...llEntries(p).filter(e => e.box).map(e => e.box)];
  if (!bs.length) return [0, 0, 1, 1];
  return [Math.max(0, Math.min(...bs.map(b => b[0])) - 0.06), 0, Math.min(1, Math.max(...bs.map(b => b[2])) + 0.06), 1];
}
function llBoxes(p) {
  const out = [];
  llEntries(p).forEach((e, i) => { if (e.box) out.push({key: "e:" + i, box: e.box, cls: "ta_nummer", label: e.struck ? T.struck : (e.ta || "?"), style: (e.struck ? "struck" : okTA(e.ta) ? "" : "rej") + ((e.mark || e.found) && !e.kept && !e.struck ? " ask" : "") + (HL === p.n + ":" + i ? " hl" : ""), person: e.src === "person"}); });
  for (const b of finalBoxes(p).pos) if (b.cls !== "ta_nummer") out.push({key: "x", box: b.box, cls: b.cls, label: T.cls[b.cls] || b.cls, person: b.src === "person", style: "weak"});
  return out;
}
function refresh1(p) {
  const a = document.activeElement, sel = a && a.matches && a.matches("#main input") ? (a.dataset.ll != null ? `input[data-ll="${a.dataset.ll}"][data-i="${a.dataset.i}"]` : a.dataset.llpage != null ? `input[data-llpage="${a.dataset.llpage}"]` : null) : null;
  const val = a && a.value, pos = a && a.selectionStart;
  const l = $("lll" + p.n); if (l) l.innerHTML = llList(p);
  if (sel && !document.activeElement.matches("#main input")) { const el = document.querySelector(sel); if (el) { if (el.value !== val && a.dataset.llpage != null) el.value = val; el.focus(); try { el.setSelectionRange(pos, pos); } catch (e) {} } }
  const m = $("llmiss"); if (m) m.innerHTML = llMissHtml();
  showFerr();
  const hd = l && l.parentElement.previousElementSibling; if (hd && llPageOf(p)) hd.textContent = `${fmt(T.page, {n: p.n})} · ${llPageOf(p)[0]}/${llPageOf(p)[1]}`;
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
    h += `<div class="col"><div class="ch">${i}/${n}${col.length > 1 ? ` · <a class="lnk" data-cmp="${col.map(q => q.n).join(",")}">${T.compare}</a>` : ""}</div>` + (col.length ? col.map(p => archive(p) ? tileHtml(p, 2, {label: `${i}/${n}`}) : copyHtml(p, 2)).join("")
      : extra.length && i <= 3 ? extra.map(p => pageQ(p, (p.page_read || {}).text, i, n, "ls_page")).join("") : phHtml(fmt(T.page_missing, {i}), `ls:${num}:${i}`)) + `</div>`;
  }
  for (const p of extra) h += `<div class="col"><div class="ch">?</div>${tileHtml(p, 2)}${n ? "" : `<button class="small" data-setpage="${p.n}" data-f="ls_page" data-v="1/1">${T.one_page}</button>`}</div>`;
  return h;
}
function lsRow(label, num, pages, accKey, extraKey) {
  const v = pages.length ? docValid(num) : null;
  let lab = `<b>${esc(label)}</b><br>`;
  const le = llEntryOf(num);
  if (le) { const b = le.e.box; lab += `<a data-tazoom="${le.p.n}:${le.i}" title="${esc(T.show_on_list)}">${cropHtml(le.p, [Math.max(0, b[0] - 0.03), Math.max(0, b[1] - 0.004), Math.min(1, b[2] + 0.03), Math.min(1, b[3] + 0.004)], 180, 56, 0)}</a>`; }
  const pgs = pages.map(lsPage), miss = pgs.every(Boolean) ? missingPages(pgs) : [], car = pages.filter(p => p.carrier);
  const missOpen = miss.some(i => !(S.accepted || {})[`ls:${num}:${i}`]), carOpen = car.some(p => !(S.carrier || {})[p.n]), acc = (S.accepted || {})["ls_doc:" + num];
  if (pages.length) { const [c, t] = v === false ? (acc ? ["acc", T.accepted] : ["bad", T.invalid]) : missOpen ? ["bad", T.incomplete] : miss.length ? ["acc", T.accepted] : v === null || carOpen ? ["open", carOpen ? T.check : T.open] : ["ok", T.valid];
    lab += `<span class="pill ${c}">${t}</span>`; }
  if (v === false) lab += accHtml("ls_doc:" + num);
  if (extraKey) lab += `<br>${accHtml(extraKey)}`;
  if (car.length) lab += `<br><span class="tag${car.every(p => (S.carrier || {})[p.n]) ? " ok" : ""}">${T.carrier}</span> ` + (car.every(p => (S.carrier || {})[p.n]) ? `<span class="acc">${T.carrier_done}</span>`
    : `<div class="muted small" style="margin:4px 0">${T.carrier_help}</div>${confHtml()}<button class="small" data-carrier="${car.map(p => p.n).join(",")}">${T.carrier_ok}</button>`);
  const cells = pages.length ? lsRowCells(num, pages) : phHtml(T.no_ls, accKey);
  return `<div class="row"><div class="lab">${lab}</div><div class="cells">${cells}</div></div>`;
}
function confHtml() {   // collective confirmations in the stack (Hermes/DHL sign there)
  const cs = D.pages.filter(q => docType(q) === "bestaetigung");
  return cs.length ? cs.map(q => `<a class="lnk small" data-open="${q.n}" data-step="0">${esc(fmt(T.carrier_show, {p: fmt(T.page, {n: q.n})}))}</a>`).join(" ") + "<br>" : `<div class="small stale">${T.carrier_none}</div>`;
}
function lsRowOk(num, pages) {   // nothing to look at: valid, all pages there and read, nothing open
  if (!pages.length || docValid(num) !== true) return false;
  const pgs = pages.map(lsPage);
  return pgs.every(Boolean) && !missingPages(pgs).length && !pages.some(p => pageIssues(p).some(x => x.step === 2));
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
    if (!OKSNAP) OKSNAP = new Set(L.filter(ta => lsRowOk(ta, byNum[ta] || [])));
    const ok = L.filter(ta => OKSNAP.has(ta) && lsRowOk(ta, byNum[ta] || []));
    h += `<div class="rows">` + L.filter(ta => !ok.includes(ta)).map(ta => lsRow("TA " + ta, ta, byNum[ta] || [], "ta_ls:" + ta)).join("") + `</div>`;
    if (ok.length) h += `<details id="okrows"${S.okrows ? " open" : ""}><summary>${fmt(T.ok_rows, {n: ok.length})}</summary><div class="rows">${ok.map(ta => lsRow("TA " + ta, ta, byNum[ta], "ta_ls:" + ta)).join("")}</div></details>`;
    const extra = Object.keys(byNum).filter(n => !L.includes(n) && !struck.includes(n));
    if (extra.length) h += `<h3>${T.s2_extra}</h3><div class="rows">` + extra.map(n => lsRow(n, n, byNum[n], null, "ta_ls_extra:" + n)).join("") + `</div>`;
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
  h += `<div class="cells" id="cmrgrid">`;
  for (let i = 1; i <= ci.N; i++) {
    const col = (ci.by[i] || []).slice().sort((a, b) => (archive(b) ? 1 : 0) - (archive(a) ? 1 : 0));
    h += `<div class="col"><div class="ch">${i}/${[...ci.tot].join("|") || "?"}${col.length > 1 ? ` · <a class="lnk" data-cmp="${col.map(q => q.n).join(",")}">${T.compare}</a>` : ""}</div>` + (col.length ? col.map(p => archive(p) ? tileHtml(p, 3, {foot: valid(p) === false ? accHtml("page:" + p.n) : ""}) : copyHtml(p, 3)).join("") : phHtml(fmt(T.cmr_missing, {i}), ci.tot.size === 1 ? "cmr:" + i : null)) + `</div>`;
  }
  h += `</div>`;
  if (L.length) {
    const cmrT = [];
    D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).forEach(p => cmrTAs(p).forEach(t => { if (!cmrT.includes(t)) cmrT.push(t); }));
    const noCmr = L.filter(t => !cmrT.includes(t)), extra = cmrT.filter(t => !L.includes(t) && !struck.includes(t));
    if (noCmr.length || extra.length) {
      h += `<h3>${T.ta_no_cmr} / ${T.ta_cmr_extra}</h3><div class="tacheck"><div class="tal">`;
      for (const t of noCmr) {
        const le = llEntryOf(t);
        h += `<div class="tai"><b>TA ${t}</b> – ${T.ta_no_cmr_s}${le ? ` · <a class="lnk" data-tazoom="${le.p.n}:${le.i}">${T.show_on_list}</a><br>${cropHtml(le.p, nearBand(le.e.box), 460, 60, 0)}` : ""}${accHtml("ta_cmr:" + t)}</div>`;
      }
      for (const t of extra) {
        const c = D.pages.find(q => docType(q) === "cmr" && archive(q) && !otherTour(q) && cmrTAs(q).includes(t)), b = c && bestBox(c, "ta_nummer");
        h += `<div class="tai"><b>TA ${t}</b> – ${fmt(T.ta_extra_s, {page: c ? `<a data-open="${c.n}" data-step="3">${fmt(T.page, {n: c.n})}</a>` : "?"})}${b ? `<br>${cropHtml(c, b.box, 460, 50, 0.006)}` : ""}${accHtml("ta_cmr_extra:" + t)}</div>`;
      }
      h += `</div><div><p class="muted small">${T.tav_hint} ${llPages().length > 1 ? llPages().map(p => `<button class="small" data-tavp="${p.n}">${fmt(T.page, {n: p.n})}</button>`).join(" ") : ""}</p><div class="tav" id="tav"></div></div></div>`;
    }
  }
  return h + confirmBar(3);
}

function llEntryOf(ta) {
  for (const p of llPages()) { const es = llEntries(p); const i = es.findIndex(e => e.ta === ta && e.box); if (i >= 0) return {p, i, e: es[i]}; }
  return null;
}
const rowCrop = b => [Math.max(0, b[0] - 0.38), Math.max(0, b[1] - 0.008), Math.min(1, b[2] + 0.3), Math.min(1, b[3] + 0.028)];   // with notes below the number
const rowBand = b => [0, Math.max(0, b[1] - 0.006), 1, Math.min(1, b[3] + 0.006)];
const nearBand = b => [Math.max(0, b[0] - 0.25), Math.max(0, b[1] - 0.01), Math.min(1, b[2] + 0.25), Math.min(1, b[3] + 0.01)];   // the row around a TA: struck out / notes
let TV = null;
function mountTA(n) {
  const el = $("tav"); if (!el || !llPages().length) { TV = null; return; }
  const p = byN[n] || llPages()[0];
  TV = new Viewer(el, p, {inline: true, boxes: () => llBoxes(p), draw: () => {}});
  TV.fit([0, 0, 1, 1], 0);
}
function zoomTA(n, i) {
  if (S.cur !== 3 && S.cur !== 2) return;
  if (S.cur === 2) { openPage(n, 1); const e = llEntries(byN[n])[i]; if (e && OV) requestAnimationFrame(() => OV.viewer.fit(rowBand(e.box), 0.01)); return; }
  if (!TV || TV.p.n !== n) mountTA(n);
  const e = llEntries(byN[n])[i]; if (TV && e) TV.fit(rowBand(e.box), 0.01);
}

// ------------------------------------------------------------ step 4: finish
let NAMEMSG = false, FIN = S.fin || null;   // FIN: {busy} | {ok, log, out, files, protocol} (kept in S.fin)
function render4() {
  const items = missingItems(), ic = {fehler: `<span class="lvl fehler">${T.lvl_err}</span>`, hinweis: `<span class="lvl hinweis">${T.lvl_hint}</span>`};
  const cmrN = D.pages.filter(p => docType(p) === "cmr" && archive(p) && !otherTour(p)).length;
  const lsN = Object.keys(lsByNumber()).length;
  const cN = cmrInfo().N;
  let h = `<h2>4 · ${T.steps[4]}</h2><div class="sum"><div><b>${cmrN}${cN && cN !== cmrN ? " / " + cN : ""}</b>${T.sum_cmr}</div><div><b>${lsN}</b>${T.sum_ls}</div>
    <div><b>${struckTAs().length}</b>${T.sum_struck}</div><div><b>${items.filter(x => !x.accepted).length}</b>${T.open_n}</div></div>
    <p class="muted">${T.s4_intro}</p>`;
  h += items.length ? `<ul class="items">` + items.map(x => `<li class="${x.accepted ? "ok" : x.level}"><div class="itx">${x.accepted ? "✓ " : ic[x.level]}${x.go ? `<a data-open="${x.go}" data-step="${stepOf(byN[x.go])}">${esc(x.text)}</a>` : esc(x.text)}<br>${accHtml(x.key)}</div>${itemImages(x.key)}</li>`).join("") + `</ul>`
    : `<p style="color:var(--ok)">✓ ${T.missing_none}</p>`;
  const mconf = missingConfirmed(items), name = (S.reviewer || "").trim(), nOpen = items.filter(x => !x.accepted).length;
  h += `<div class="fin"><div class="fs${name ? " ok" : ""}"><span class="no">1</span>${T.fin_name} <input id="reviewer2" autocomplete="name" placeholder="${esc(T.name_ph)}" class="${name ? "" : "need"}" value="${esc(S.reviewer || "")}" style="width:170px">${NAMEMSG && !name ? `<span class="issues small">${T.save_need_name}</span>` : ""}</div>
    <div class="fs${mconf ? " ok" : ""}"><span class="no">2</span>${!items.length ? T.nothing_left : mconf ? `✓ ${T.missing_confirmed} <a class="lnk" data-mreset="1">${T.undo}</a>`
      : `<button id="mconfirm" class="primary"${name ? "" : ` disabled title="${esc(T.name_first)}"`}>${fmt(T.confirm_missing, {n: nOpen})}</button>${name ? "" : ` <span class="muted small">${T.name_first}</span>`}` + (S.missing_keys ? ` <span class="small" style="color:var(--warn)">${T.missing_changed}</span>` : "")}</div>
    <div class="fs${stepDone(4) ? " ok" : ""}"><span class="no">3</span><button class="${mconf && !stepDone(4) ? "primary" : ""}" id="save2">${T.save}</button></div></div>`;
  if (stepDone(4)) h += `<div class="savedbox" id="savedbox">✓ <b>${esc(S.saved.msg)}</b>
    ${SRV && S.saved.fin ? `<p>${FIN && FIN.busy ? `<span class="hint">${T.fin_busy}</span>` : `<button class="${FIN && FIN.ok ? "" : "primary"}" id="fin2">${FIN && FIN.ok ? T.fin_again : T.fin_btn}</button>`}</p>` : ""}
    ${FIN && !FIN.busy ? finHtml() : ""}
    ${SRV && S.saved.fin ? "" : `<details class="muted small"><summary>${T.tech}</summary>${esc(fmt(T.tech_next, {name: D.name}))}</details>`}</div>`;
  else if (S.saved) h += `<p class="stale">${T.stale_saved}</p>`;
  return h + `<p style="margin-top:64px"><button class="small danger" id="discard2">${T.discard}</button></p>`;
}

function itemImages(key) {   // what the missing item is about, as pictures (click = the page)
  const [kind, a, b] = key.split(":"), out = [];
  const link = (p, inner) => `<a data-open="${p.n}" data-step="${stepOf(p)}" title="${esc(fmt(T.page, {n: p.n}))}">${inner}</a>`;
  const small = p => `<div style="width:250px">${docType(p) === "cmr" ? cropRow(p, "cmr_count", (cmrCount(p) || []).join("/")) : cropRow(p, "ls_nummer", lsNumber(p) || "")}${objCrops(p)}</div>`
    + `<div><div class="muted small">${T.evidence} · ${fmt(T.page, {n: p.n})}</div>${cropHtml(p, p.view || [0, 0.5, 1, 1], 300, 170, 0)}</div>`;
  if (kind === "page") { const p = byN[+a]; out.push(link(p, tileBody(p) ? small(p) : thumbHtml(p, p.view || [0, 0, 1, 1]))); }
  else if (kind === "ls_doc") for (const p of lsByNumber()[a] || []) out.push(link(p, small(p)));
  else if (kind === "ls") { for (const p of lsByNumber()[a] || []) { const bb = bestBox(p, "ls_nummer"); if (bb) out.push(link(p, cropHtml(p, bb.box, 220, 44, 0.01))); }
    const le = llEntryOf(a); if (le) out.push(`<div><div class="muted small">${T.row_on_list}</div>${link(le.p, cropHtml(le.p, rowCrop(le.e.box), 420, 60, 0))}</div>`); }
  else if (kind === "cmr") { const L = loaded(), cmrT = []; D.pages.filter(q => docType(q) === "cmr" && archive(q) && !otherTour(q)).forEach(q => cmrT.push(...cmrTAs(q)));
    const wo = L.filter(t => !cmrT.includes(t)).slice(0, 3);
    if (wo.length) out.push(`<div><div class="muted small">${T.ta_wo_cmr}</div>${wo.map(t => { const le = llEntryOf(t); return le ? link(le.p, cropHtml(le.p, nearBand(le.e.box), 420, 46, 0)) : "TA " + t; }).join("")}</div>`); }
  else if (kind === "ll") for (const p of llPages()) out.push(link(p, `<div style="width:90px">${thumbHtml(p, [0, 0, 1, 1])}</div>`));
  else if (kind === "ta_cmr" || kind === "ta_ls") { const le = llEntryOf(a); if (le) out.push(link(le.p, cropHtml(le.p, nearBand(le.e.box), 420, 50, 0))); }
  else if (kind === "ta_cmr_extra") { const c = D.pages.find(q => docType(q) === "cmr" && archive(q) && cmrTAs(q).includes(a)), bb = c && bestBox(c, "ta_nummer"); if (bb) out.push(link(c, cropHtml(c, bb.box, 300, 60, 0.008))); }
  else if (kind === "ta_ls_extra") for (const p of lsByNumber()[a] || []) { const bb = bestBox(p, "ls_nummer"); if (bb) { out.push(link(p, cropHtml(p, bb.box, 260, 40, 0.01))); break; } }
  return out.length ? `<div class="mi">${out.join("")}</div>` : "";
}

// ------------------------------------------------------------ rendering
let LASTSTALE = [], RENDERED = false, RECONF = false;
function renderStepper() {
  const st = [0, 1, 2, 3, 4].filter(stale);
  $("stepper").innerHTML = T.steps.map((s, k) => `<button data-step-go="${k}" class="${k === S.cur ? "cur " : ""}${stepDone(k) ? "done" : st.includes(k) ? "stale" : ""}"${canEnter(k) ? "" : " disabled"} title="${esc(st.includes(k) ? T.stale_step : s)}">
    <span class="no">${stepDone(k) ? "✓" : st.includes(k) ? "!" : k}</span><span class="lbl">${esc(s)}</span></button>`).join("");
  const sv = $("save"), ok = stepDone(4);   // the save button tells the state: saved / out of date / not yet
  sv.className = ok ? "saved" : st.includes(4) ? "stale" : "";
  sv.textContent = ok ? fmt(T.saved_btn, {time: S.saved.time || ""}) : st.includes(4) ? T.save_stale : T.save;
  sv.title = st.includes(4) ? T.stale_saved : "";
  const newly = st.filter(k => k < 4 && !LASTSTALE.includes(k));
  if (newly.length && RENDERED) { notice(fmt(T.reconfirm, {steps: newly.map(k => T.steps[k]).join(", ")}), 8000, "warn"); RECONF = true; }
  else if (RECONF && !st.some(k => k < 4)) { notice(""); RECONF = false; }   // changed back: confirmations hold again
  LASTSTALE = st; RENDERED = true;
}
function renderMain() {
  for (const k in LV) delete LV[k];
  hidePeek();
  $("main").innerHTML = [render0, render1, render2, render3, render4][S.cur]();
  if (S.cur === 1) { mountLL(); showFerr(); }
  if (S.cur === 3) mountTA();
}
function renderAll() { $("title").innerHTML = `<span class="tw">${esc(T.title)} </span>${esc(D.tour || D.name)}`; renderStepper(); renderMain(); }
let OKSNAP = null;
function go(k) { if (!canEnter(k)) { alert(T.step_locked); return; } S.cur = k; OKSNAP = null; notice(""); persist(); renderAll(); window.scrollTo(0, 0); }
function rerender() { const y = window.scrollY; if (OV) showOv(false); renderStepper(); renderMain(); window.scrollTo(0, y); }

// ------------------------------------------------------------ zoomable viewer (wheel = zoom, drag = move, draw mode)
class Viewer {
  constructor(el, p, cb) {
    this.el = el; this.p = p; this.cb = cb; this.s = 1; this.tx = 0; this.ty = 0; this.drawCls = null;
    el.innerHTML = `<div class="vw"><div class="dban"></div><div class="vin" style="width:${p.w}px;height:${p.h}px"><img src="${esc(p.image)}" alt="${esc(fmt(T.page, {n: p.n}))}" onerror="imgRetry(this)"><div class="ovl"></div></div></div>`;
    this.vw = el.querySelector(".vw"); this.vin = el.querySelector(".vin"); this.ovl = el.querySelector(".ovl"); this.ban = el.querySelector(".dban");
    this.vw.addEventListener("wheel", e => { if (cb.inline && !e.ctrlKey) return; e.preventDefault(); const r = this.vw.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.tx = mx - (mx - this.tx) * f; this.ty = my - (my - this.ty) * f; this.s *= f; this.apply(); }, {passive: false});
    this.vw.addEventListener("mousedown", e => this.down(e));
    this.move = e => this.mv(e); this.upf = e => this.up(e);
    this.render();
  }
  apply() { this.vin.style.transform = `translate(${this.tx}px,${this.ty}px) scale(${this.s})`; this.vin.style.setProperty("--ls", 1 / this.s); }
  fit(reg, pad = 0.02) {
    const r = this.vw.getBoundingClientRect(), W = this.p.w, H = this.p.h;
    if (!r.width || !r.height) return;
    const x1 = Math.max(0, reg[0] - pad), y1 = Math.max(0, reg[1] - pad), x2 = Math.min(1, reg[2] + pad), y2 = Math.min(1, reg[3] + pad);
    this.s = Math.min(r.width / ((x2 - x1) * W), r.height / ((y2 - y1) * H), 4);
    this.tx = r.width / 2 - (x1 + x2) / 2 * W * this.s; this.ty = r.height / 2 - (y1 + y2) / 2 * H * this.s; this.apply();
  }
  fitWidth(x1, x2) {   // the printed width fills the view, top of the page first
    const r = this.vw.getBoundingClientRect(); if (!r.width) return;
    this.s = Math.min(r.width / ((x2 - x1) * this.p.w), r.height / (0.55 * this.p.h), 4);   // at least half the page in view
    this.tx = (r.width - (x1 + x2) * this.p.w * this.s) / 2; this.ty = 0; this.apply();
  }
  panTo(box) {   // bring a box into view (same zoom)
    const r = this.vw.getBoundingClientRect(), y1 = box[1] * this.p.h * this.s + this.ty, y2 = box[3] * this.p.h * this.s + this.ty;
    if (y1 >= 10 && y2 <= r.height - 10) return;
    this.ty = r.height / 2 - (box[1] + box[3]) / 2 * this.p.h * this.s; this.apply();
  }
  norm(e) { const r = this.vin.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; }
  startDraw(cls) { this.drawCls = cls; this.ban.textContent = fmt(T.draw_banner, {cls: T.cls[cls] || cls}); this.vw.classList.add("drawing"); }
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
      let b = !this.pan.moved && this.pan.target.closest && this.pan.target.closest("[data-k]");
      if (b) {   // several boxes under the mouse: the smallest, then the next one on each further click
        const [x, y] = this.norm(e), hits = [...this.ovl.querySelectorAll("[data-k]")].filter(el => {
          const r = el.getBoundingClientRect(); return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom; })
          .sort((a, c) => a.offsetWidth * a.offsetHeight - c.offsetWidth * c.offsetHeight);
        if (hits.length > 1) { const key = hits.map(h => h.dataset.k).join("|"); this.cyc = this.cycKey === key ? (this.cyc + 1) % hits.length : 0; this.cycKey = key; b = hits[this.cyc]; }
      }
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
  hidePeek();
  const list = stepList(step); if (!list.includes(n)) list.unshift(n);
  OV = {list, idx: list.indexOf(n), step};
  $("ov").classList.add("on"); showOv(true);
}
function closeOv() { if (!OV) return; QUIET = Date.now() + 700; if (OV.viewer) OV.viewer.cancelDraw(); OV = null; $("ov").classList.remove("on"); $("ovimg").innerHTML = ""; renderStepper(); renderMain(); }
function ovBoxes(p) {
  const out = [];
  p.dets.forEach((d, i) => {
    const inc = detInc(p, d, i), sure = d.score >= thrOf(d.cls);
    out.push({key: "d:" + i, box: d.box, cls: d.cls, label: `${T.cls[d.cls] || d.cls}${sure ? "" : " ?"}${inc ? "" : sure ? " ✗" : ""}`, style: inc ? "" : sure ? "rej" : "weak"});
  });
  ((S.pages[p.n] || {}).pb || []).forEach((b, i) => out.push({key: "p:" + i, box: b.box, cls: b.cls, label: (T.cls[b.cls] || b.cls) + " ✎", person: true}));
  return out;
}
function focusRegion(p) {
  const t = docType(p), best = c => topOf(p, c);
  if (OV.step === 0) return [0, 0, 1, 1];
  if (t === "lieferschein" && !lsNumber(p)) { const b = best("ls_nummer"); return b ? b.box : [0, 0, 1, 0.35]; }
  if (t === "lieferschein" && p.carrier && !(S.carrier || {})[p.n]) return [0, 0, 1, 0.3];   // the delivery address with Hermes/DHL
  if (t === "cmr" && !cmrCount(p)) { const b = best("cmr_count"); return b ? b.box : [0, 0.5, 0.7, 0.8]; }
  return p.view || [0, 0, 1, 1];
}
function showOv(refit) {
  const p = ovPage(); if (!p) return;
  if (refit || !OV.viewer || OV.viewer.p !== p) {
    OV.viewer = new Viewer($("ovimg"), p, {
      boxes: () => ovBoxes(p),
      click: k => { const [kind, i] = k.split(":"); if (kind !== "d") return; const s = us(p); s.bx = s.bx || {}; s.bx[i] = !detInc(p, p.dets[+i], +i); edit(p); },
      draw: (box, cls) => { const s = us(p); s.pb = (s.pb || []).concat([{cls, box}]); if (OBJ.includes(cls) && reviewable(p)) { s.v = s.v || {}; s.v[cls] = true; s.dec = true; } edit(p); ocrBox(p, box, cls); },
    });
    const v = OV.viewer;
    requestAnimationFrame(() => v.fit(focusRegion(p), 0.04));
  } else OV.viewer.render();
  $("ovside").innerHTML = sideHtml(p); showFerr();
  if (refit) { const want = sideFocus(p); const el = want && $("ovside").querySelector(want); if (el) el.focus(); }
}
function showFerr() {   // wrong entries stay visible in their field (red) until corrected
  for (const k in FERR) { const e = FERR[k], el = OV && ovPage() && ovPage().n === e.n ? $("ovside").querySelector(`input[data-f="${e.f}"]`) : document.querySelector(`#main input[data-llpage="${e.n}"]`);
    if (el && (e.f !== "page_of" || el.dataset.f || el.dataset.llpage)) { el.value = e.v; el.classList.add("need"); } }
}
function sideFocus(p) { const t = docType(p); if (t === "lieferschein" && !lsNumber(p)) return 'input[data-f="ls"]'; if (t === "cmr" && !cmrCount(p)) return 'input[data-f="cmr"]'; if (OV.step === 0 && REVIEW.includes(t) && !tourOf(p)) return 'input[data-f="tour"]'; return null; }
const rawRead = s => s && /\d/.test(s) ? ` – ${T.ocr_read}: „${esc(s)}“` : "";
const EXPECT = {sonstiges: [], unsicher: [], cmr: ["unterschrift", "stempel", "tour_nummer", "cmr_count", "ta_nummer"],
  lieferschein: ["ls_nummer", "tour_nummer", "seitenzahl", "unterschrift", "stempel"],
  loading_list: ["tour_nummer", "ta_nummer", "seitenzahl"], bestaetigung: ["unterschrift", "stempel", "seitenzahl"], abholschein: ["seitenzahl"]};
function expected(p) {
  const t = docType(p);
  let e = EXPECT[t] || D.classes;
  if (t === "lieferschein" && backPage(p)) e = e.filter(c => c !== "tour_nummer");   // page 2/2: no tour number printed
  return e.filter(c => D.classes.includes(c));
}
function defaultDrawCls(p) {
  const x = pageIssues(p).find(i => i.box); if (x) return x.box;
  const pos = finalBoxes(p).pos;
  return expected(p).find(c => !pos.some(b => b.cls === c)) || expected(p)[0] || "stempel";
}
function sideHtml(p) {
  const t = docType(p), s = S.pages[p.n] || {}, iss = pageIssues(p);
  let h = `<h3 style="margin-top:0">${esc(cardTitle(p))}</h3><div class="muted small" title="${esc(p.source)}">${fmt(T.page, {n: p.n})}</div>`;
  if (REVIEW.includes(t)) h += `<div class="vbtns"><button data-fit="full">${T.v_full}</button><button data-fit="area">${T.v_area}</button><button data-fit="num">${T.v_num}</button></div>`;
  if (iss.length) h += `<div class="issues small">${iss.map(x => "• " + esc(x.text)).join("<br>")}</div>`;
  if (OCRBUSY) h += `<div class="hint">${T.ocr_busy}</div>`;
  h += `<label>${T.doctype}</label><div class="segs">${D.doc_types.map(x => `<button data-dtb="${x}" class="${x === t ? "on" : ""}">${esc(T.dt[x] || x)}</button>`).join("")}</div>`;
  if (REVIEW.includes(t)) {
    const read = rawRead(p.tour && p.tour.raw);
    h += `<label>${T.tour}${read}</label><input data-f="tour" placeholder="${esc(T.ph_tour)}" class="${tourOf(p) ? "" : "need"}" value="${esc(has(p, "tour") ? s.tour : tourOf(p) || "")}" style="width:220px">${ocrNote(p, "tour")}`;
    if (D.tour && tourOf(p) !== D.tour) h += ` <button data-tourthis="1">${esc(fmt(T.tour_this, {tour: D.tour}))}</button>`;
  }
  if (t === "loading_list") {
    const po = llPageOf(p), read = rawRead(p.page_read && p.page_read.text);
    h += `<label>${T.ll_page}${read}</label><input data-f="page_of" placeholder="${esc(T.ph_page)}" class="${po || llPages().length < 2 ? "" : "need"}" style="width:90px" value="${esc(has(p, "page_of") ? s.page_of : po ? po.join("/") : "")}">${ocrNote(p, "page_of")}`;
  }
  if (t === "lieferschein") {
    const read = rawRead(p.ls_read && p.ls_read.text);
    const pg = lsPage(p);
    h += `<label>${T.ls_number}${read}</label><input class="num${lsNumber(p) ? "" : " need"}" data-f="ls" placeholder="${esc(T.ph_num)}" value="${esc(has(p, "ls") ? s.ls : lsNumber(p) || "")}">${ocrNote(p, "ls")}`;
    h += `<label>${T.ls_page}</label><input data-f="ls_page" placeholder="${esc(T.ph_page)}" class="${pg ? "" : "need"}" style="width:90px" value="${esc(has(p, "ls_page") ? s.ls_page : pg ? pg.join("/") : "")}">${ocrNote(p, "ls_page")}${pg ? "" : ` <button class="small" data-setpage="${p.n}" data-f="ls_page" data-v="1/1">${T.one_page}</button>`}`;
    if (p.carrier) h += `<div class="tag">${T.carrier}</div> ` + ((S.carrier || {})[p.n] ? `<span class="acc">${T.carrier_done}</span>` : `<div class="muted small">${T.carrier_help}</div><button class="small" data-carrier="${p.n}">${T.carrier_ok}</button>`);
  }
  if (t === "cmr") {
    const read = rawRead(p.cmr_count && p.cmr_count.text);
    const cc = cmrCount(p);
    h += `<label>${T.cmr_count}${read}</label><input class="num${cc ? "" : " need"}" data-f="cmr" placeholder="${esc(T.ph_cmr)}" value="${esc(has(p, "cmr") ? s.cmr : cc ? cc.join("/") : "")}">${ocrNote(p, "cmr")}`;
    h += `<label>${T.ta_on_cmr}</label>${taChips(p, true)}`;
    const tb = bestBox(p, "ta_nummer"); if (tb) h += cropHtml(p, tb.box, 370, 90, 0.008);
    h += `<input data-f="ta" placeholder="${esc(T.ph_ta)}" style="width:370px;margin-top:4px" value="${esc(has(p, "ta") ? s.ta : cmrTAs(p).join(", "))}">${ocrNote(p, "ta")}`;
  }
  if (boxMissing(p).length) h += `<div class="muted small" style="margin-top:6px">${T.box_optional}</div>`;
  if (REVIEW.includes(t) && OV.step !== 0) {
    h += `<h3>${T.h_obj}</h3>`;
    for (const c of rule(p).require) {
      const v = val(p, c), pr = proposal(p, c), sc = (p.scores || {})[c] || 0;
      h += `<div class="obj"><span class="nm"><i style="background:${D.colors[c]}"></i>${esc(T.cls[c] || c)}</span>
        <button class="y${v === true ? " on" : ""}" data-obj="${c}" data-v="1">✓ ${T.present}</button><button class="n${v === false ? " on" : ""}" data-obj="${c}" data-v="0">✗ ${T.absent}</button>
        ${pr === null || sc < thrOf(c) ? `<span class="muted small" title="${sc ? sc.toFixed(2) : ""}">${T.suggestion}: ${pr === true ? "✓" : pr === false ? "✗" : "?"} (${T.unsure})</span>` : ""}</div>`;
      if (v === true && !hasPos(p, c)) h += `<div class="muted small">${T.box_obj_optional}</div>`;
      if (v === false && p.dets.some(d => d.cls === c)) h += `<div class="muted small">${T.hint_reject}</div>`;
    }
    const v = unitValid(p);
    h += `<p><span class="pill ${v === true ? "ok" : v === false ? "bad" : "open"}">${v === true ? T.valid : v === false ? T.invalid : T.open}</span></p>`;
    if (v === false && archive(p)) h += accHtml(t === "lieferschein" && lsNumber(p) ? "ls_doc:" + lsNumber(p) : "page:" + p.n);
    const cop = copiesOf(p);
    if (cop.length > 1) h += `<p class="small">${fmt(T.copies, {pages: cop.map(q => fmt(T.page, {n: q.n})).join(", ")})}${archive(p) ? "" : ` · ${T.dup} <button data-archthis="1">${T.archive_this}</button>`} <button data-cmp="${cop.map(q => q.n).join(",")}">${T.compare}</button></p>`;
  }
  const drawing = OV.viewer && OV.viewer.drawCls, ex = expected(p), pos = finalBoxes(p).pos;
  if (ex.length) h += `<h3>${T.expected}</h3>${drawing ? `<div class="hint">${T.drawing}</div>` : ""}<div class="exp">` + ex.map(c => {
    const n = pos.filter(b => b.cls === c).length;
    return `<div class="ex"><span class="sw" style="background:${D.colors[c] || "#000"}"></span><span class="nm">${esc(T.cls[c] || c)}</span><span class="st ${n ? "y" : "q"}">${n ? "✓" + (n > 1 ? " " + n : "") : "–"}</span><button data-drawc="${c}" class="${drawing === c ? "on" : ""}">${T.draw}</button></div>`;
  }).join("") + `</div>`;
  const rest = D.classes.filter(c => !ex.includes(c));
  if (rest.length && ex.length) h += `<details class="small"><summary>${T.other_cls}</summary>${rest.map(c => `<button data-drawc="${c}">${esc(T.cls[c] || c)}</button>`).join(" ")}</details>`;
  if (p.dets.length) h += `<details class="small"${overlapping(p) ? " open" : ""}><summary>${T.model_boxes} (${p.dets.length})</summary>` + p.dets.map((d, i) => {
    const inc = detInc(p, d, i);
    return `<div class="mb${inc ? "" : " off"}"><span class="sw" style="background:${D.colors[d.cls] || "#000"}"></span><span class="nm" title="${d.score.toFixed(2)}">${esc(T.cls[d.cls] || d.cls)} (${d.score >= thrOf(d.cls) ? T.sure : T.unsure})</span>
      <span class="${inc ? "acc" : "muted"}">${inc ? T.box_on : T.box_off}</span><button data-togdet="${i}">${T.box_toggle}</button></div>`;
  }).join("") + `</details>`;
  const pb = s.pb || [];
  if (pb.length) h += `<div class="small">${T.boxes_person}: ${pb.map((b, i) => `<span class="chip">${esc(T.cls[b.cls] || b.cls)} <a class="lnk" data-delpb="${i}">×</a></span>`).join(" ")}</div>`;
  h += `<div class="nav"><button data-nav="-1">${T.prev}</button><button data-nav="1">${T.next}</button><button data-close="1">${T.close}</button></div>${REVIEW.includes(t) ? `<p class="muted small">${T.keys}</p>` : ""}`;
  return h;
}
function overlapping(p) {   // two boxes on the same spot: show the list to switch each one
  const iou = (a, b) => { const w = Math.min(a[2], b[2]) - Math.max(a[0], b[0]), h = Math.min(a[3], b[3]) - Math.max(a[1], b[1]); if (w <= 0 || h <= 0) return 0; const i = w * h; return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i); };
  return p.dets.some((d, i) => p.dets.some((e, j) => j > i && iou(d.box, e.box) > 0.4));
}
function setPage(p, f, v) { us(p)[f] = v; if (us(p).ocrf) delete us(p).ocrf[f]; changed(f === "page_of" ? 1 : 2); }
function edit(p) { changed(S.cur); if (OV) showOv(false); }
const CHECK = {ls: [v => parse8(v).length === 1 && v.replace(/\D/g, "").length === 8, "bad_number"], cmr: [v => !!parseCount(v), "bad_cmr"],
  ls_page: [v => !!parsePageOf(v), "bad_page"], page_of: [v => !!parsePageOf(v), "bad_page"],
  ta: [v => parse8(v).length > 0 && !v.replace(/(?<!\d)(?:\d ?){7}\d(?!\d)/g, "").replace(/[\s,;]/g, ""), "bad_ta"]};
function modelVal(p, f) {
  const j = x => x ? x.join("/") : "";
  return {doc_type: p.doc_type, tour: p.tour && p.tour.accepted ? p.tour.text : "", ls: p.ls_number || "", ls_page: j(p.ls_page), page_of: j(p.page_of),
    cmr: j(p.cmr_count && p.cmr_count.parsed), ta: (p.ta || []).map(t => t.ta).join(", ")}[f] || "";
}
function setField(p, f, v) {
  const s = us(p); v = (v || "").trim();
  const key = p.n + ":" + f;
  if (v && CHECK[f] && !CHECK[f][0](v)) { FERR[key] = {n: p.n, f, v, msg: T[CHECK[f][1]], step: f === "page_of" ? 1 : stepOf(p)}; persist(); if (OV) showOv(false); else rerender(); return; }
  delete FERR[key];
  if (v && v.replace(/\s/g, "") === modelVal(p, f).replace(/\s/g, "")) v = "";   // back to what was read
  if (f === "doc_type") { if (v === p.doc_type) delete s.doc_type; else s.doc_type = v; changed(0); if (OV) showOv(false); return; }
  if (v === "") delete s[f]; else s[f] = v;
  if (s.ocrf) delete s.ocrf[f];
  edit(p);
}
function setObj(p, c, v) {
  const s = us(p); s.v = s.v || {};
  if (v === proposal(p, c)) delete s.v[c]; else s.v[c] = v;   // back to the proposal: no individual decision
  s.dec = Object.keys(s.v).length > 0 || undefined; edit(p);
}
function nextOpen(dir = 1) {
  if (!OV) return;
  for (let k = OV.idx + dir; k >= 0 && k < OV.list.length; k += dir) if (pageIssues(byN[OV.list[k]]).some(x => x.step === OV.step)) { OV.idx = k; showOv(true); return; }
  if (OV.step < 4 && !stepIssues(OV.step).length) {
    closeOv(); notice(T.all_done, 6000, "ok");
    const b = document.querySelector(`[data-confirm="${S.cur}"]`); if (b) { b.scrollIntoView({block: "center"}); b.focus(); }
    return;
  }
  if (OV.idx + dir >= 0 && OV.idx + dir < OV.list.length) { OV.idx += dir; showOv(true); } else closeOv();
}
$("ov").addEventListener("mousedown", e => { if (e.target.id === "ov") closeOv(); });
$("ovx").addEventListener("click", () => closeOv());
$("ovside").addEventListener("change", e => {
  const p = ovPage(), f = e.target.dataset.f; if (!p || !f) return;
  if (e.target.tagName === "INPUT" && e.target.value === e.target.defaultValue) return;   // Enter/Esc without a change
  setField(p, f, e.target.value);
});
$("ovside").addEventListener("click", e => {
  const p = ovPage(), b = e.target.closest("button,a"); if (!p || !b) return;
  if (b.dataset.obj) setObj(p, b.dataset.obj, b.dataset.v === "1");
  else if (b.dataset.fit) OV.viewer.fit(b.dataset.fit === "full" ? [0, 0, 1, 1] : b.dataset.fit === "area" ? (p.view || [0, 0, 1, 1]) : (topOf(p, docType(p) === "cmr" ? "cmr_count" : "ls_nummer") || {box: [0, 0, 1, 0.35]}).box, 0.04);
  else if (b.dataset.tourthis) setField(p, "tour", D.tour);
  else if (b.dataset.togdet != null) { const i = +b.dataset.togdet, st = us(p); st.bx = st.bx || {}; st.bx[i] = !detInc(p, p.dets[i], i); edit(p); }
  else if (b.dataset.archthis) { archiveThis(p); edit(p); }
  else if (b.dataset.delpb != null) { const s = us(p); s.pb.splice(+b.dataset.delpb, 1); edit(p); }
  else if (b.dataset.drawc) { OV.viewer.startDraw(b.dataset.drawc); $("ovside").innerHTML = sideHtml(p); }
  else if (b.dataset.cmp) openCompare(b.dataset.cmp.split(",").map(Number));
  else if (b.dataset.setpage) { setPage(p, b.dataset.f, b.dataset.v); showOv(false); }
  else if (b.dataset.dtb) { setField(p, "doc_type", b.dataset.dtb); if (OV.step === 0) nextOpen(1); }
  else if (b.dataset.carrier) { S.carrier = S.carrier || {}; S.carrier[p.n] = true; edit(p); }
  else if (b.dataset.nav) nextOpen(+b.dataset.nav);
  else if (b.dataset.close) closeOv();
});

// ------------------------------------------------------------ live OCR (make review: page served by the local server)
let SRV = false, OCRBUSY = 0;
async function ping() {
  if (!location.protocol.startsWith("http")) return;
  try { SRV = !!(await (await fetch("/api/ping")).json()).ok; } catch (e) { SRV = false; }
  const b = $("srv"); b.textContent = T.live_ocr; b.style.display = SRV ? "" : "none";
  if (SRV && S.cur === 4) rerender();   // "Abschluss erzeugen" needs the server
}
const OCR_CLS = ["ls_nummer", "seitenzahl", "cmr_count", "tour_nummer", "ta_nummer"];
function ocrField(p, cls) {
  const t = docType(p);
  return {ls_nummer: "ls", cmr_count: "cmr", tour_nummer: "tour", seitenzahl: t === "loading_list" ? "page_of" : "ls_page", ta_nummer: "ta"}[cls];
}
async function ocrBox(p, box, cls) {
  if (!SRV || !OCR_CLS.includes(cls)) return;
  OCRBUSY++; afterOcr(p, null);
  let res = null;
  try {
    const r = await fetch("/api/ocr", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({n: p.n, box, cls})});
    res = await r.json();
  } catch (e) { res = null; }
  OCRBUSY--;
  if (res && res.ok) applyOcr(p, box, cls, res);
  afterOcr(p, cls);
}
function applyOcr(p, box, cls, res) {   // the read value goes into its field unless the person typed one
  const s = us(p), v = res.value, t = docType(p);
  s.ocrf = s.ocrf || {}; s.ocrt = s.ocrt || {};
  if (cls === "ta_nummer" && t === "loading_list") {
    const e = llEntries(p).find(x => sameBox(x.box, box));
    if (e) { e.ocrt = res.text; if (v && (!e.ta || e.ocr)) { e.ta = v.split(", ")[0]; e.ocr = true; } }
  } else if (cls === "ta_nummer") {
    s.ocrt.ta = res.text;
    if (v && t === "cmr") { const cur = cmrTAs(p), add = v.split(", ").filter(x => !cur.includes(x)); if (add.length) { s.ta = cur.concat(add).join(", "); s.ocrf.ta = true; } }
  } else {
    const f = ocrField(p, cls); s.ocrt[f] = res.text;
    if (v && (!has(p, f) || s.ocrf[f])) { s[f] = v; s.ocrf[f] = true; }
  }
  changed(S.cur);
}
function afterOcr(p, cls) {
  if (OV && ovPage() === p) {
    showOv(false);
    const f = cls && ocrField(p, cls), el = f && $("ovside").querySelector(`input[data-f="${f}"]`);
    if (el) { el.focus(); el.select(); }
  } else if (S.cur === 1 && LV[p.n]) {
    refresh1(p);
    if (cls === "seitenzahl") { const el = document.querySelector(`input[data-llpage="${p.n}"]`); if (el) { el.focus(); el.select(); } }
  }
}
function ocrNote(p, f) {   // next to a field: wrong entry / read by OCR (check it) / not recognized
  const s = S.pages[p.n] || {}, er = FERR[p.n + ":" + f];
  if (er) return `<div class="issues small">${esc(er.msg)}</div>`;
  if ((s.ocrf || {})[f]) return `<span class="ocrtag">${T.ocr_check}</span>`;
  if ((s.ocrt || {})[f] && !has(p, f)) return ` <span class="small issues">${esc(fmt(T.ocr_none, {text: s.ocrt[f]}))}</span>`;
  return "";
}

// ------------------------------------------------------------ quick preview: hover a tile (or Space on it)
let PK = null, PKT = null, MOVED = 0, QUIET = 0;
document.addEventListener("mousemove", () => { MOVED = Date.now(); });
function showPeek(p, tile) {
  const r = tile.getBoundingClientRect(), right = r.left + r.width / 2 < window.innerWidth / 2;
  const el = $("peek"); el.style.left = right ? "auto" : "12px"; el.style.right = right ? "12px" : "auto";
  $("peekt").textContent = `${cardTitle(p)} · ${fmt(T.page, {n: p.n})} – ${T.peek_hint}`;
  $("peekv").innerHTML = thumbHtml(p, [0, 0, 1, 1], true);
  el.classList.add("on"); PK = p.n;
}
function hidePeek() { clearTimeout(PKT); $("peek").classList.remove("on"); PK = null; }
document.addEventListener("mouseover", e => {
  if (OV || CV) return;
  const t = !accOpen && !e.target.closest("button,a,input,select,.accform") && e.target.closest("#main .tile[data-open]");
  if (!t) { if (PK != null && !e.target.closest("#peek")) hidePeek(); return; }
  const n = +t.dataset.open; if (n === PK) return;
  clearTimeout(PKT); PKT = setTimeout(() => { if (!OV && !CV && Date.now() - MOVED < 500 && Date.now() > QUIET && t.isConnected) showPeek(byN[n], t); }, 400);
});
document.addEventListener("mouseout", e => { if (e.target.closest && e.target.closest("#main .tile[data-open]") && !e.relatedTarget?.closest?.("#main .tile[data-open]")) hidePeek(); });

// ------------------------------------------------------------ copies side by side
let CV = null;
function openCompare(ns) {
  CV = {ns}; $("cmp").classList.add("on");
  $("cmpt").textContent = T.compare;
  for (const [k, t] of [["full", T.v_full], ["area", T.v_area]]) document.querySelector(`[data-cmpfit="${k}"]`).textContent = t;
  document.querySelector("[data-cmpclose]").textContent = T.close;
  $("cmpb").innerHTML = ns.map(n => `<div class="cpane"><div class="cv" id="cv${n}"></div><div class="cf" id="cf${n}"></div></div>`).join("");
  CV.viewers = ns.map(n => { const p = byN[n]; return new Viewer($("cv" + n), p, {boxes: () => ovBoxes(p), draw: () => {}}); });
  requestAnimationFrame(() => CV && CV.viewers.forEach(v => v.fit(v.p.view || [0, 0, 1, 1], 0.03)));
  renderCompare();
}
function renderCompare() {
  for (const n of CV.ns) { const p = byN[n];
    $("cf" + n).innerHTML = `<b>${esc(cardTitle(p))}</b> <span class="muted">${fmt(T.page, {n})}</span> ${reviewable(p) ? stIcons(p, true) : ""}
      ${archive(p) ? `<span class="pill ok">${T.archived}</span>` : `<button data-cmparch="${n}">${T.archive_this}</button>`}`; }
  CV.viewers.forEach(v => v.render());
}
function closeCompare() { CV = null; $("cmp").classList.remove("on"); $("cmpb").innerHTML = ""; if (OV) showOv(false); else rerender(); }
$("cmp").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b || !CV) return;
  if (b.dataset.cmparch) { archiveThis(byN[+b.dataset.cmparch]); changed(S.cur); renderCompare(); }
  else if (b.dataset.cmpfit) CV.viewers.forEach(v => v.fit(b.dataset.cmpfit === "full" ? [0, 0, 1, 1] : (v.p.view || [0, 0, 1, 1]), 0.03));
  else if (b.dataset.cmpclose) closeCompare();
});

// ------------------------------------------------------------ events on the main page
document.addEventListener("click", e => {
  if (e.target.closest("select,input,.accform") && !e.target.closest("button") || e.target.closest("#ov") || e.target.closest("#cmp")) return;
  const t = e.target.closest("[data-acc],[data-accok],[data-acccancel],[data-unacc],[data-mreset],#mconfirm,[data-confirm],[data-step-go],[data-strike],[data-delta],[data-lldraw],[data-cmp],[data-tazoom],[data-tavp],[data-setpage],[data-carrier],[data-keep],[data-revert],[data-tazoomll],#save2,#discard2,#fin2,[data-open]");
  if (!t) return;
  if (t.dataset.acc != null) { accOpen = t.dataset.acc; rerender(); }
  else if (t.dataset.acccancel != null) { accOpen = null; rerender(); }
  else if (t.dataset.accok != null) {
    const f = t.closest(".accform"), reason = f.querySelector("[data-accr]").value, note = f.querySelector("[data-accn]").value.trim();
    if (!reason) { const s = f.querySelector("[data-accr]"); s.classList.add("need"); s.focus();
      if (!f.querySelector(".issues")) s.insertAdjacentHTML("afterend", `<span class="issues small">${T.need_reason}</span>`); return; }
    if (reason === "sonstiges" && !note) { alert(T.note_needed); f.querySelector("[data-accn]").focus(); return; }
    S.accepted = S.accepted || {}; S.accepted[t.dataset.accok] = {reason, note}; accOpen = null; touched(); rerender();
  }
  else if (t.dataset.unacc != null) { delete S.accepted[t.dataset.unacc]; touched(); rerender(); }
  else if (t.dataset.mreset != null) { delete S.missing_keys; touched(); rerender(); }
  else if (t.id === "mconfirm") { S.missing_keys = missingKeys(missingItems()); touched(); rerender(); }
  else if (t.dataset.tavp != null) mountTA(+t.dataset.tavp);
  else if (t.dataset.keep != null) { const p = byN[+t.dataset.keep], x = llEntries(p)[+t.dataset.i]; x.kept = true;
    if (x.found && x.box) us(p).pb = (us(p).pb || []).concat([{cls: "ta_nummer", box: x.box}]);   // its box goes into the training labels
    changed(1); refresh1(p); }
  else if (t.dataset.revert != null) { const p = byN[+t.dataset.revert], x = llEntries(p)[+t.dataset.i]; x.ta = x.orig; x.typed = false; delete x.bad; changed(1); refresh1(p); }
  else if (t.dataset.tazoomll != null) { const [n, i] = t.dataset.tazoomll.split(":").map(Number), e = llEntries(byN[n])[i]; if (LV[n] && e) LV[n].fit(rowBand(e.box), 0.01); }
  else if (t.id === "discard2") discardAll();
  else if (t.id === "fin2") finalizeRun();
  else if (t.dataset.setpage != null) { setPage(byN[+t.dataset.setpage], t.dataset.f, t.dataset.v); rerender(); }
  else if (t.dataset.carrier != null) { S.carrier = S.carrier || {}; t.dataset.carrier.split(",").forEach(n => S.carrier[n] = true); changed(2); rerender(); }
  else if (t.dataset.confirm != null) { const k = +t.dataset.confirm; if (stepIssues(k).length) return; S.steps[k] = true; S.stepSig = S.stepSig || {}; S.stepSig[k] = sigOf(k); persist(); go(k + 1); }
  else if (t.dataset.stepGo != null) go(+t.dataset.stepGo);
  else if (t.dataset.strike != null) { const p = byN[+t.dataset.strike], x = llEntries(p)[+t.dataset.i]; x.struck = !x.struck; changed(1); refresh1(p); }
  else if (t.dataset.delta != null) { const p = byN[+t.dataset.delta], es = llEntries(p), x = es[+t.dataset.i]; es.splice(+t.dataset.i, 1); us(p).pb = (us(p).pb || []).filter(b => !sameBox(b.box, x.box)); changed(1); refresh1(p); }
  else if (t.dataset.lldraw != null) { const v = LV[+t.dataset.lldraw]; if (v) v.startDraw(t.dataset.cls); }
  else if (t.dataset.cmp != null) openCompare(t.dataset.cmp.split(",").map(Number));
  else if (t.dataset.tazoom != null) { const [n, i] = t.dataset.tazoom.split(":").map(Number); zoomTA(n, i); }
  else if (t.id === "save2") save();
  else if (t.dataset.open != null) { QUIET = Date.now() + 1000; openPage(+t.dataset.open, +(t.dataset.step || S.cur)); }
  else return;
  e.preventDefault();
});
document.addEventListener("change", e => {
  const el = e.target;
  if (el.closest("#ov")) return;
  if (el.dataset.ll != null) {   // a wrong entry stays in the field (red), the list keeps the last valid number
    const p = byN[+el.dataset.ll], x = llEntries(p)[+el.dataset.i], raw = el.value.trim(), m = parse8(raw);
    if (raw && !(m.length === 1 && raw.replace(/\D/g, "").length === 8)) x.bad = raw;
    else { delete x.bad; const v = m[0] || ""; if (v !== x.ta) x.typed = !!v && v !== x.orig; x.ta = v; x.ocr = false; }
    changed(1); setTimeout(() => refresh1(p), 0);   // after the focus moved on (a click into the next field must land)
  }
  else if (el.dataset.llpage != null) { const p = byN[+el.dataset.llpage]; setField(p, "page_of", el.value); if (!FERR[p.n + ":page_of"]) setTimeout(() => refresh1(p), 0); }
  else if (el.dataset.dt != null) { setField(byN[+el.dataset.dt], "doc_type", el.value); rerender(); }
  else if (el.id === "reviewer" || el.id === "reviewer2") { S.reviewer = el.value; $("reviewer").value = el.value; touched(); if (S.cur === 4) rerender(); }
});
document.addEventListener("input", e => {
  if (e.target.id !== "reviewer2") return;
  const b = $("mconfirm"), v = e.target.value.trim(); if (b) { b.disabled = !v; b.title = v ? "" : T.name_first; }
  e.target.classList.toggle("need", !v);
});
document.addEventListener("focusin", e => { if (e.target.matches && e.target.matches("input.ta,input[data-f],input[data-llpage]")) { e.target.select(); e.target.dataset.sel = "1"; } });
document.addEventListener("mouseup", e => { if (e.target.dataset && e.target.dataset.sel) { e.preventDefault(); delete e.target.dataset.sel; } });
document.addEventListener("toggle", e => { if (e.target.id === "all0") { S.open0 = e.target.open; persist(); } if (e.target.id === "okrows") { S.okrows = e.target.open; persist(); } }, true);
document.addEventListener("keydown", e => {
  if (CV) { if (e.key === "Escape") { closeCompare(); e.preventDefault(); } return; }
  if (OV) {
    const p = ovPage();
    if (e.target.matches("input,select")) {
      if (e.key === "Enter") { e.target.dispatchEvent(new Event("change", {bubbles: true})); e.preventDefault(); if (!FERR[p.n + ":" + e.target.dataset.f]) nextOpen(1); }
      else if (e.key === "Escape") { e.target.dispatchEvent(new Event("change", {bubbles: true})); e.preventDefault(); closeOv(); }
      return;
    }
    const k = e.key.toLowerCase();
    if (k === "escape") { if (OV.viewer.drawCls) { OV.viewer.cancelDraw(); showOv(false); } else closeOv(); }
    else if (k === "enter") nextOpen(1);
    else if (k === "arrowright") { if (OV.idx < OV.list.length - 1) { OV.idx++; showOv(true); } }
    else if (k === "arrowleft") { if (OV.idx > 0) { OV.idx--; showOv(true); } }
    else if ((k === "1" || k === "2") && reviewable(p) && rule(p).require.includes(OBJ[+k - 1])) setObj(p, OBJ[+k - 1], val(p, OBJ[+k - 1]) !== true);
    else if (k === "b") { OV.viewer.startDraw(defaultDrawCls(p)); $("ovside").innerHTML = sideHtml(p); }
    else return;
    e.preventDefault(); return;
  }
  if (e.target.matches("input,select")) return;
  const tiles = [...document.querySelectorAll("#main .tile[data-open]")], i = tiles.indexOf(document.activeElement);
  if (e.key === " " && i >= 0) { const t = tiles[i]; if (PK === +t.dataset.open) hidePeek(); else showPeek(byN[+t.dataset.open], t); e.preventDefault(); return; }
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
  if (!(S.reviewer || "").trim()) { NAMEMSG = true; if (S.cur !== 4 && canEnter(4)) go(4); else rerender(); const r = $("reviewer2") || $("reviewer"); r.classList.add("need"); r.focus(); return; }
  const openSteps = [0, 1, 2, 3].filter(k => !stepDone(k));
  if (openSteps.length && !confirm(fmt(T.save_open, {steps: openSteps.map(k => T.steps[k]).join(", ")}))) return;
  if (!missingConfirmed(missingItems()) && !confirm(T.save_unconfirmed)) return;
  const out = Object.assign(decision(), {saved: new Date().toISOString()});
  const time = new Date().toLocaleTimeString(T.html_lang === "pl" ? "pl-PL" : "de-DE", {hour: "2-digit", minute: "2-digit"}) + T.oclock;
  const done = msg => { notice(""); S.saved = {at: out.saved, msg, time, sig: sigOf(4)}; persist(); if (S.cur !== 4 && canEnter(4)) go(4); else rerender();
    const b = $("savedbox"); if (b) b.scrollIntoView({block: "center"}); };
  if (SRV) {
    try {
      const r = await (await fetch("/api/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(out)})).json();
      if (r.ok) { FIN = null; delete S.fin; done(fmt(T.saved_srv, {time})); S.saved.fin = !!r.finalize; persist(); rerender(); return; }
    } catch (e) {}
    alert(T.save_failed);
  }
  if (await saveText("entscheidung.json", JSON.stringify(out, null, 1))) done(fmt(T.saved, {time}));
}
function finHtml() {   // what "Abschluss erzeugen" made: files, open points, protocol folded
  if (!FIN.ok) return `<div class="issues" style="margin-top:6px">${T.fin_fail}<pre class="small" style="white-space:pre-wrap">${esc(FIN.log.join("\n"))}</pre></div>`;
  const todo = (FIN.protocol.split(/\n\s*\n/).find(b => b.trim().startsWith(T.todo_head)) || "").split("\n").filter(l => /^\s*\d+\./.test(l)).map(l => l.replace(/^\s*\d+\.\s*/, ""));
  return `<div style="margin-top:8px;color:var(--fg)"><b>✓ ${T.fin_title}${FIN.time ? " " + esc(FIN.time) : ""}</b>
    ${todo.length ? `<div style="margin-top:6px"><b>${esc(T.todo_head)}</b><ol style="margin:4px 0 0 18px;padding:0">${todo.map(l => `<li>${esc(l)}</li>`).join("")}</ol></div>` : ""}
    <div class="small" style="margin-top:4px">${T.fin_files} ${FIN.files.filter(f => f !== "protokoll.csv").map(f => `<span class="chip">${esc(f)}</span>`).join(" ")}</div>
    <details class="small"><summary>${T.fin_prot}</summary><pre style="white-space:pre-wrap">${esc(FIN.protocol)}</pre></details></div>`;
}
async function finalizeRun() {   // make finalize on the server: PDFs, mail drafts, protocol, label export
  FIN = {busy: true}; rerender();
  try { const r = await (await fetch("/api/finalize", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"})).json(); FIN = {ok: !!r.ok, log: (r.log || [r.error || "?"]).map(l => l.replace(/^\[finalize\]\s*/, "")), out: r.out || "", files: r.files || [], protocol: r.protocol || ""}; }
  catch (e) { FIN = {ok: false, log: [String(e)], out: ""}; }
  if (FIN.ok) { FIN.time = new Date().toLocaleTimeString(T.html_lang === "pl" ? "pl-PL" : "de-DE", {hour: "2-digit", minute: "2-digit"}) + T.oclock; S.fin = FIN; persist(); }
  rerender();
}
function decision() {   // the content of entscheidung.json (without the time it is saved)
  const items = missingItems(), mconf = missingConfirmed(items);
  const out = {format: "docval-entscheidung", version: 2, name: D.name, tour: D.tour, ergebnis_created: D.created,
    reviewer: (S.reviewer || "").trim(), steps: [0, 1, 2, 3].map(stepDone).concat([true]),
    open: D.pages.filter(p => reviewable(p) && !pageConfirmed(p)).length, pages: {},
    accepted: S.accepted || {}, missing_keys: missingKeys(items), missing_confirmed: mconf};
  for (const p of D.pages) {
    const s = S.pages[p.n] || {}, fb = finalBoxes(p);
    const e = {doc_type: docType(p), archive: archive(p), archive_set: true, confirmed: pageConfirmed(p),
      bulk: reviewable(p) && !s.dec, corrected: corrected(p), boxes: fb.pos, rejected: fb.neg, box_missing: boxMissing(p).length > 0};
    if (p.carrier) e.carrier_checked = !!(S.carrier || {})[p.n];
    if (reviewable(p)) {
      for (const c of OBJ) e[c] = val(p, c);
      e.valid = unitValid(p);
      e.cmr_count = docType(p) === "cmr" ? cmrCount(p) : null;
      e.tour = has(p, "tour") ? s.tour.trim() : null;
    }
    if (docType(p) === "lieferschein") { e.ls_number = lsNumber(p); e.ls_page = lsPage(p); }
    if (docType(p) === "cmr" && has(p, "ta")) e.ta = cmrTAs(p);
    if (docType(p) === "loading_list") e.page_of = llPageOf(p);
    if (docType(p) === "loading_list") e.ta_list = llEntries(p).map(x => ({ta: (x.ta || "").replace(/\s/g, ""), box: x.box, struck: !!x.struck, src: x.src, typed: !!x.typed}));
    out.pages[p.n] = e;
  }
  return out;
}
$("save").onclick = save;
function discardAll() { if (!confirm(T.confirm_discard)) return; S = {reviewer: S.reviewer, pages: {}, steps: {}, accepted: {}, cur: 0}; FERR = {}; persist(); notice(""); renderAll(); }

$("reviewer").value = S.reviewer || "";
ping();
if (S.cur == null || !canEnter(S.cur)) { S.cur = 0; while (S.cur < 4 && stepDone(S.cur)) S.cur++; }
renderAll();
</script>
</body></html>
"""
