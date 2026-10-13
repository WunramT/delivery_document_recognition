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
