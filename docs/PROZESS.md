# Ablauf im Vertrieb mit Dokumentprüfung (Soll-Prozess)

Ziel: Die Transportabteilung liefert die unsortierten Papiere einer Tour. Statt sie vor dem
Scannen von Hand zu sortieren und zu prüfen, wird **der ganze Stapel einmal gescannt**. Die
Anwendung erledigt das Organisatorische automatisch, und eine Person entscheidet auf **einer
Seite** über alle Stempel und Unterschriften. **Das letzte Wort hat immer die Person.**

```
Papierstapel ──scannen──► make process ──► Prüfseite (pruefung.html) ──► make finalize
 (unsortiert)              automatisch:      Person bestätigt jede            CMR_<Tour>.pdf (sortiert)
                           Typ, Tour,        Karte Unterschrift/Stempel       LS_<Tour>.pdf
                           CMR i/n, Duplikate,                                Mail-Entwürfe, Protokoll
                           TA-Abgleich                                        Papier-Reihenfolge
```

## Geklärt mit dem Fachbereich (Stand 14.10.2026)

Diese Punkte gelten vor der Tabelle darunter; wo sie abweicht, ist die Umsetzung noch offen
(siehe „Geplante Änderungen“). Offene Fragen an die Kollegen: Dokument „Offene Fragen an den
Fachbereich – Dokumentprüfung Vertrieb“.

| Thema | Entscheidung |
|---|---|
| TA | = Auftrag, 8 Ziffern, steht auf Ladeliste, CMR und Lieferschein. Beginnt nicht immer mit 12; es gibt andere 8-stellige Nummern → TA nur aus einer `ta_nummer`-Box lesen, nie per Suche über die ganze Seite |
| Geladene TAs | Quelle ist die **Ladeliste**. Streichungen (nicht mehr in der Tour) stehen handschriftlich auf der Ladeliste; die Person streicht diese TAs in der Anwendung und bestätigt die Liste. Gestrichene TAs werden nicht gemeldet. SAP ist keine Quelle (ohne Streichungen, nicht aktuell) |
| TA ↔ CMR | ein CMR trägt n TAs, eine TA steht auf genau einem CMR |
| Lieferschein | Stempel **und/oder** Unterschrift. Ausnahme bekannte Kunden (W4000: Hermes, DHL): sie unterschreiben nicht auf dem Lieferschein, sondern auf einer **Sammelbestätigung** für alle Aufträge; sie wird hinter ihren Lieferscheinen gescannt und hängt in SAP am letzten Lieferschein (Dokumenttyp `bestaetigung`; Beispiele in `609_17.09.2026`, Seiten 7, 8, 48, 52; DHL nennt die Bestellnummer, Hermes die Lieferscheinnummer). Kleinere Kunden: lehnt die Prüfung ab, entscheidet die Person selbst und sendet den Lieferschein außerhalb der Anwendung. Keine Kundenliste. Mehrseitig: Vorderseite oben Mitte „Lieferschein XXXXXXXX“, Folgeseiten oben links „Lieferschein (XXXXXXXX)“, unten rechts „Seite 1/2“; mehrere TAs pro Seite, TA mittig unter „Zlecenie“. Gleiche TA-Nummern = Duplikat |
| Ladeliste | mehrseitig möglich, oben rechts „2/6“, Tournummer oben auf jeder Seite; alle Seiten nötig (sie beschreibt die Tour); kein Stempel nötig |
| CMR | immer einseitig, gleicher Aufbau, eine Folge pro Tour. Stempel **und** Unterschrift, dürfen auch außerhalb von Feld 24 stehen; die Kundenausnahme gilt **nicht** für CMR. Reihenfolge im PDF ist dem Archiv egal (es liest den Barcode), die Anwendung sortiert trotzdem aufsteigend |
| Ausnahmen | ein fehlendes CMR oder eine Seite, die die Prüfung nicht besteht: nur nach **aktiver Zustimmung mit Grund**; danach gilt die Tour in der Anwendung als abgeschlossen (kein Nachverfolgen) |
| Archiv, Versand | die Archiv-Mail kommt heute direkt vom Drucker und enthält nur das gescannte PDF als Anhang; das Archiv liest den Barcode. CMR werden einzeln archiviert und warten nicht auf fehlende; fehlende Dokumente werden später einzeln gesendet und normal archiviert |
| Fehlende Dokumente | für die Tour anzeigen; die Mail wird erst nach aktiver Bestätigung erzeugt. Senden bleibt bei den Benutzern |
| Nachtrag | ein Ersatz-CMR kann später gescannt werden, Zuordnung über die Tournummer auf dem Dokument, muss bestätigt werden; fehlende Daten der Tour anzeigen |
| Polilogistics | keine Mail aus der Anwendung |
| Rollen, Audit | eine Person reicht, alle dürfen alles (die Daten bleiben im Browser des Benutzers); eingetippter Name reicht; Protokoll unbefristet aufbewahren, Ablage mit fein einstellbaren Rechten möglich; Protokoll nicht in die Archiv-Mail. Ein Browser darf nur mit ausdrücklicher Erlaubnis des Benutzers in einen Ordner schreiben (File System Access API), still schreiben geht nur über einen Server |
| Arbeitsplätze | aktuelles Microsoft Edge, 8 GB RAM |
| Mengen, Scans | ~30 Touren/Woche à 50–100 Seiten; Farbe, keine leeren Rückseiten |
| Sprachen | Polnisch, Rumänisch, Englisch, Deutsch |
| Nicht Teil des Projekts | Überblick über offene Touren |

## Wer macht was

| Schritt im bisherigen Ablauf | Neu | Wer |
|---|---|---|
| 1. Ladeliste prüfen: wie viele TA verladen, „Nie jedzie“ gestrichen | TA-Nummern der Ladeliste lesen, Zeilen mit „nie jedzie“/„nicht verladen“ ausnehmen, mit CMR und Lieferscheinen abgleichen | Anwendung – **vorerst nur Hinweis** (siehe unten) |
| 2. Heftklammern entfernen | unverändert (vor dem Scannen) | Person |
| 3. In CMR und Lieferscheine trennen | Dokumenttyp je Seite (OCR-Schlüsselwörter + Bildklassifikator) | Anwendung, automatisch |
| 3.1.1 / 3.2.1 Duplikate entfernen | CMR: gleiche Nummer „CMR i/n“ zweimal → die Kopie mit Stempel/Unterschrift bleibt. Lieferschein: gleiche TA-Nummern → ebenso | Anwendung schlägt vor, Person kann umstellen („archivieren“) |
| 3.1.2 / 3.2.3 je TA ein CMR / ein Lieferschein | TA-Abgleich | Anwendung – Hinweis |
| 3.1.3 Stempel + Unterschrift des Empfängers (CMR) | Modell markiert, **Person entscheidet** je Karte | **Person** |
| 3.2.2 Stempel und/oder Unterschrift (Lieferschein) | ebenso, Regel „Stempel **oder** Unterschrift“ | **Person** |
| 3.1.3 Tournummer / 3.2.2 Tournummer passt | Tournummer gelesen; andere Tour → „zur richtigen Tour legen“ | Anwendung, automatisch |
| 3.1.3 CMR-Folge vollständig (1 / 13 …) | Zählung gelesen, fehlende Nummern → „an Polilogistics melden“ | Anwendung, automatisch |
| 3.1.4 CMR sortieren | CMR-PDF in der Reihenfolge 1..n; Reihenfolge fürs Papier steht im Protokoll | Anwendung, automatisch |
| 4. Senden an leopol-ls@ / leopol-cmr@ und Archiv srem-svr-file01 | getrennte PDFs + Mail-Entwürfe (.eml); Kopie in den Archiv-Ordner, sobald die Tour vollständig ist (`process.deliver`) | Anwendung erstellt, Person sendet |
| 5. Papier ins Dokumentenarchiv, wenn alles ok | Protokoll sagt „VOLLSTÄNDIG“ oder „OFFEN“ mit Liste „Zu tun“ | Person |
| 6. Am nächsten Tag ZCHECKLSARCHIV | Erinnerung im Protokoll mit Tour (und TA-Nummern) | Person (SAP) |
| Ersatz-CMR besorgen | nicht Teil der Anwendung, steht aber als Aufgabe im Protokoll | Person |

Automatisch ist nur, was in der Auswertung zuverlässig war: Dokumenttyp, Tournummer und die
CMR-Zählung. Alles, wobei die Anwendung unsicher ist, landet als **Klärfall** auf der Prüfseite
(Dokumenttyp unsicher, Tournummer oder CMR-Nummer nicht lesbar) und wird dort ergänzt.

## Bedienung

```
make process SCANS=scans/503_01.09.2026.pdf            # PDF, Bild oder Ordner mit PDFs/Bildern
make process SCANS=scans/tour503/ TOUR=503_01.09.2026  # Tour angeben, wenn der Name sie nicht enthält
```

Voraussetzung: ein trainiertes und ausgewertetes Modell (`make train export eval` – daraus
kommen `detector.onnx`, die Soll-Zonen und die Schwellen). Die Tournummer der Tour kommt aus
`TOUR=`, sonst aus dem Datei-/Ordnernamen (`503_01.09.2026` → `503/01.09.2026/4000`), sonst
aus der häufigsten gelesenen Tournummer.

Ergebnis in `artifacts/process/<Tour>/`:

- `pruefung.html` (Deutsch) / `pruefung_pl.html` (Polnisch) – per Doppelklick öffnen
  (Chrome/Edge, offline, kein Server). Die Seiten liegen in `seiten/` daneben.
- `ergebnis.json` – alle Lesungen und Modellergebnisse je Seite.

### Prüfseite

1. **Organisatorisch** – das automatische Ergebnis (grün ✓ / rot ✗ / gelb ! Hinweis) und die
   CMR-Folge 1..n als Kacheln (fehlende Nummer rot, doppelte gelb; Klick springt zur Karte).
2. **Klärfälle** – nur, wenn es welche gibt: Dokumenttyp wählen, CMR-Nummer `i/n` oder
   Tournummer eintragen.
3. **Unterschrift und Stempel** – eine Karte je CMR/Lieferschein mit dem Ausschnitt, in dem
   das Modell gesucht hat, und seinen Markierungen (durchgezogen = sicher, gestrichelt =
   unsicher, schraffiert = Vordruck Feld 22/23, wird ignoriert). Je Objekt „vorhanden“/„fehlt“
   – vorbelegt mit dem Modellvorschlag, bei „Modell unsicher“ leer – und **„Bestätigen“**.
   Klick aufs Bild zeigt die ganze Seite. Tasten: `J`/`K` Karte wechseln, `1` Unterschrift,
   `2` Stempel, `A` archivieren, `Enter` bestätigen + weiter, Leertaste ganze Seite.
   Filter „offen“, „Modell unsicher“, „ungültig“.

Name bei „Prüfer/in“ eintragen, **„Entscheidung speichern“** → Datei als
`entscheidung.json` in den Ordner der Prüfseite legen. Der Zwischenstand bleibt im Browser
erhalten.

### Abschluss

```
make finalize RUN=503_01.09.2026_4000
```

Bricht ab, solange archivierte CMR/Lieferscheine nicht bestätigt sind (`FORCE=1` schließt
trotzdem ab und vermerkt das im Protokoll). Rechnet die organisatorische Prüfung mit den
Korrekturen der Person neu und schreibt `freigabe/`:

- `CMR_<Tour>.pdf` (1..n, ohne Duplikate), `LS_<Tour>.pdf`, `andere_touren/` (Zuladungen)
- `CMR_<Tour>.eml`, `LS_<Tour>.eml` – Mail-Entwürfe mit Anhang an die Adressen aus
  `process.mail` (in Outlook öffnen, senden)
- `protokoll_de.txt` / `protokoll_pl.txt` – Ergebnis VOLLSTÄNDIG/OFFEN, ungültige Seiten,
  **Zu tun** (Polilogistics, Ersatzdokument, andere Tour, Senden, Papierarchiv,
  ZCHECKLSARCHIV), Reihenfolge fürs Papier, Abweichungen vom Modellvorschlag
- `protokoll.csv` – je Seite Modell und Entscheidung. Die Entscheidungen der Person sind
  zugleich **neue Labels**: Seiten mit Abweichung sind die wertvollsten fürs nächste Training.

Ist `process.deliver.cmr` / `.lieferschein` gesetzt (z. B. ein Ordner auf `srem-svr-file01`),
werden die PDFs bei vollständiger Tour dorthin kopiert.

## Neue Labels (`make label-scans`)

Für TA, Lieferschein-Nummer und Seitenzählung braucht der Detektor drei neue Klassen
(`config.yaml` → `classes`, Anleitung in `label_guide`):

| Klasse | Box |
|---|---|
| `ta_nummer` | Lieferschein: „Zlecenie“ + TA darunter in einer Box. Ladeliste: jede TA einzeln (eine Box pro Zeile – darauf streicht die Person später). CMR: alle TAs eines Blocks zusammen |
| `ls_nummer` | „Lieferschein XXXXXXXX“ (Vorderseite, oben Mitte) bzw. „Lieferschein (XXXXXXXX)“ (Folgeseiten, oben links) |
| `seitenzahl` | Lieferschein unten rechts „Seite 1/2“, Ladeliste oben rechts „2/6“ |

Neue Scans werden lokal gelabelt (sie kommen nicht ins Repository):

```
make process SCANS=<scan.pdf>                      # einmal durch die Pipeline
make label-scans RUN=503_01.09.2026_4000           # -> artifacts/label_scans/503_01.09.2026/
```

Der Ordner hat den Aufbau eines Label-Exports (`_annotations.coco.json`, `images/`,
`page_types.csv`, `editor.html`/`editor_pl.html`), die Modellboxen sind als Vorschläge
eingetragen, die Dokumenttypen kommen aus der Prüfung (falls `entscheidung.json` da ist).
Ordner nach `labels/503_01.09.2026/` kopieren, dort im Editor die Boxen prüfen und die neuen
Klassen ziehen (Tasten `5`–`7`, die Anleitung zur gewählten Klasse steht unter der Klassenliste),
„COCO speichern“ nach `labels/503_01.09.2026/`, dann `make inspect split train export eval`.
`make relabel` lässt Labels von Klassen, die das Modell noch nicht kennt, unverändert.

Bestehende Touren (schon als Label-Export vorhanden): eine Tour vollständig mit allen Klassen
labeln, dann `make relabel-model relabel` – das Vorlage-Modell schlägt die neuen Klassen für alle
anderen Touren vor und prüft die Vorlage-Tour auf vergessene Boxen (Details: README, „Neue Klassen
in allen Touren nachlabeln“). Sammelbestätigungen (Hermes/DHL) dabei im Editor oben als
Dokumenttyp „Sammelbestätigung“ markieren.

## Geplante Änderungen an der Anwendung

Aus den Antworten oben, noch nicht umgesetzt:

1. TA-Nummern nur aus `ta_nummer`-Boxen (8 Ziffern), nicht mehr per Ganzseiten-OCR.
2. Prüfseite: Ladeliste mit allen gelesenen TAs; die Person streicht TAs (Klick auf die Box)
   und bestätigt die Liste. Abgleich: jede verbleibende TA auf genau einem CMR und auf einem
   Lieferschein.
3. Lieferscheine über `ls_nummer` zu Dokumenten gruppieren, Vollständigkeit über `seitenzahl`;
   Ladeliste ebenso (alle Seiten 1..n).
4. CMR: fehlt Stempel oder Unterschrift, bzw. fehlt ein CMR → „trotzdem akzeptieren“ mit Grund
   (Auswahl + Freitext), im Protokoll.
5. Fehlende Dokumente der Tour vorne anzeigen; Mail-Entwürfe erst nach aktiver Bestätigung.
6. Nachtrag: einzelnes Ersatz-CMR scannen, über die Tournummer der Tour zuordnen, bestätigen.
7. Oberfläche und Protokoll zusätzlich auf Rumänisch und Englisch.
8. Protokoll pro Tour als Datei: Die Person wählt den Protokoll-Ordner (Netzlaufwerk) einmal aus
   und erlaubt das Schreiben; die Anwendung legt dort je Tour die Datei ab. Ohne Erlaubnis: Download.
9. Sammelbestätigung (`bestaetigung`): Lieferscheine von Hermes/DHL gelten mit der Bestätigung im
   Stapel als bestätigt; die Person sieht beides nebeneinander und bestätigt.

## Was noch offen ist

- **TA-Abgleich (Schritt 1, 3.1.2, 3.2.3) ist nicht validiert.** Die TA-Nummern werden per
  Ganzseiten-OCR gelesen (`process.ta.regex`, z. B. `12283251`). Es gibt dafür noch keine
  Labels, und handschriftliche Vermerke bzw. durchgestrichene Zeilen erkennt die OCR nicht
  sicher. Deshalb erscheint das Ergebnis nur als Hinweis und blockiert nichts. Nach einer
  Prüfung an echten Touren `process.ta.validated: true` setzen – dann werden Abweichungen zu
  Fehlern. Bis dahin gleicht die Person die Anzahl der TA mit der Ladeliste ab.
- Lieferschein-Duplikate werden nur über gleiche TA-Nummern erkannt (sonst bleibt beides
  stehen und die Person nimmt die Kopie per „archivieren“ heraus).
- Mails werden nicht automatisch versendet (Entwürfe), ZCHECKLSARCHIV bleibt manuell.
- Produktion im Browser: Die Logik (`process/organize.py`, Zonen, Nachverarbeitung) ist wie
  der Rest so geschrieben, dass sie nach JavaScript portiert werden kann; die Prüfseite ist
  bereits eine reine Browserseite.
