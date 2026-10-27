# Versanddokument-Erkennung mit ML

Welche manuellen Schritte bei der Dokumentenbearbeitung wir mit lokalen Modellen automatisieren können.

*Stand: Evaluation vom 15.10.2026. Der PoC ist lauffähig, aber noch nicht im Einsatz.*

---

## 1. Kurzfassung

* Der unsortierte Papierstapel einer Tour (Ladeliste, CMR, Lieferscheine) wird einmal gescannt. Die Anwendung erkennt Dokumenttyp, Nummern, Stempel und Unterschriften, sortiert die Seiten, gleicht sie ab und schreibt Mail-Entwürfe und ein Protokoll.
* Dafür laufen nur kleine lokale Modelle (Objekterkennung, OCR, Bildklassifikator) und feste Regeln. Eine Cloud oder ein großes Sprachmodell braucht es nicht.
* Auf den CMR-Testseiten hat die Anwendung keinen fehlenden Stempel und keine fehlende Unterschrift übersehen, weder auf 19 echten noch auf 90 künstlich manipulierten Seiten. Was unsicher ist, geht an eine Person.
* Von Hand dauert eine Tour heute etwa 16 Minuten. Im ersten Test mit der Anwendung waren es 8 Minuten, ohne Einarbeitung.
* Zum Vergleich lief ein großes Bild-Sprach-Modell (imajev-4b, 4 Mrd. Parameter). Es war deutlich schlechter und etwa 200-mal langsamer als unser spezialisiertes Modell.
* Am meisten würden jetzt mehr gelabelte Touren helfen.

---

## 2. Ausgangslage: der manuelle Prozess

* Etwa 30 Touren pro Woche mit je 50 bis 100 Seiten kommen unsortiert aus der Transportabteilung.
* Eine Person arbeitet heute etwa 8 Stunden pro Woche daran, also rund 16 Minuten pro Tour.
* Handgriffe je Tour:
  * Ladeliste prüfen: Wie viele Aufträge (TA) sind verladen, was ist handschriftlich gestrichen?
  * Stapel in CMR und Lieferscheine trennen, Duplikate aussortieren
  * je CMR: Stempel **und** Unterschrift des Empfängers, richtige Tournummer, Folge 1…n vollständig?
  * je Lieferschein: Stempel **oder** Unterschrift, richtige Tour?
  * je TA: Gibt es ein CMR und einen Lieferschein?
  * CMR sortieren, als PDF an die Archiv-Postfächer senden, Papier ablegen

Auf vielen gleichartigen Seiten werden immer dieselben Fragen nach festen Regeln beantwortet. Dafür eignet sich ML gut. Heute sieht sich ein Mensch jede dieser Seiten einzeln an.

---

## 3. Was ersetzt wird und mit welcher Art von Modell

### Automatisch

1. Seiten nach Typ trennen (CMR, Lieferschein, Ladeliste …): Klassifikation aus OCR-Schlüsselwörtern und einem Bildklassifikator
2. Tournummer prüfen: Die Objekterkennung findet das Feld, die OCR liest es, eine Formatregel prüft es.
3. CMR-Folge auf Vollständigkeit prüfen (1/13, 2/13 …): OCR und Programmlogik
4. CMR sortieren und PDFs bauen: reine Programmlogik
5. Prüfen, ob es je TA ein CMR und einen Lieferschein gibt: Abgleich der gelesenen Nummern. Bis der Abgleich validiert ist, erscheint das Ergebnis nur als Hinweis.
6. Mails an das Archiv: Die Anwendung erzeugt Entwürfe, senden muss weiter die Person.

### Vorschlag, die Person bestätigt

7. Duplikate aussortieren: Die Logik vergleicht die gelesenen Nummern und behält die Kopie mit Stempel.
8. TAs der Ladeliste lesen (Objekterkennung und OCR): Handschriftliche Streichungen markiert die Person. Farbige Vermerke zeigt die Anwendung als Hinweis an.
9. Stempel und Unterschrift prüfen, also ob sie vorhanden sind und an der richtigen Stelle stehen: Objekterkennung und Zonenregel liefern den Vorschlag, die Person entscheidet.

### Bleibt manuell

10. Heftklammern entfernen, Papier ablegen, SAP-Kontrolle am Folgetag. Das Protokoll erinnert daran.

Wir haben festgelegt, dass immer die Person entscheidet, ob ein Dokument gültig unterschrieben ist. Das Modell zeigt ihr die passenden Ausschnitte und markiert jeden als „sicher“ oder „unsicher“.

---

## 4. Die Pipeline in vier Bausteinen

```
Papierstapel ──scannen──► Verarbeitung (lokal) ──► Prüfseite im Browser ──► Abschluss
 (unsortiert)              Dokumenttyp, Nummern,     Person bestätigt          CMR_<Tour>.pdf (1..n)
                           Stempel/Unterschrift,     Stempel/Unterschrift,     LS_<Tour>.pdf
                           Duplikate, Abgleich       streicht TAs              Mail-Entwürfe, Protokoll
```

1. Dokumenttyp: Die OCR liest Schlüsselwörter im Kopfbereich (DE/PL), ein kleiner Bildklassifikator stimmt mit ab.
2. Objekte finden: Ein Detektor markiert 7 Dinge, nämlich Unterschrift, Stempel, Tournummer, CMR-Zählung, TA-Nummer, Lieferscheinnummer und Seitenzahl.
3. Regeln prüfen: Liegen Stempel und Unterschrift in den Soll-Feldern (CMR-Feld 22/23/24)? Vorgedruckte Felder werden vorher ausgeblendet.
4. Nummern lesen: Die OCR liest nur den Ausschnitt der gefundenen Box, danach wird das Ergebnis gegen das bekannte Format geprüft (z. B. `503/01.09.2026/4000`).

Alles Weitere (Duplikate, Vollständigkeit, TA-Abgleich, Sortieren) ist normale Programmlogik. ML liefert nur die Angaben, die bisher ein Mensch von der Seite abgelesen hat.

---

## 5. Beispiel: eine echte CMR-Seite durch alle Schritte

* Die Schlüsselwörter werden gefunden, die Seite ist ein CMR.
* Feld 22 und 23 tragen eingedruckte Unterschriften und Stempel des Absenders. Die Vordruck-Maske übermalt sie weiß, damit das Modell nur echte Unterschriften sieht.
* Der Detektor findet Unterschrift und Stempel, jeweils mit einem Score zwischen 0 und 1 und der Soll-Zone.
* Tournummer und „CMR 3/13“ werden aus ihren Boxen gelesen und gegen das Format geprüft.

> 📷 Bild einfügen: Folie „Beispiel: eine CMR-Seite – Schritt 2 Dokumenttyp“. Quelle: `make create_pdf`, dann `artifacts/report/praesentation/folie_XX.png` (der Folientitel steht im Bild)

> 📷 Bild einfügen: Folie „Schritt 3: Vordruck-Maske – vorher / nachher“. Quelle: wie oben

> 📷 Bild einfügen: Folie „Schritt 4–5: Objekte finden und Position prüfen“. Quelle: wie oben

> 📷 Bild einfügen: Folie „Schritt 6: Tournummer und CMR-Zählung lesen“. Quelle: wie oben

---

## 6. Ergebnisse (Test-Split, 42 Seiten aus 4 Touren)

### Was beim Sachbearbeiter ankommt

Für 19 CMR-Testseiten gilt die Regel zu Stempel und Unterschrift. Davon hat die Anwendung 15 selbst richtig entschieden und 1 an die Person gegeben. Übersehen hat sie keinen Fehler. In 3 Fällen meldete sie „Stempel fehlt“, obwohl einer da war.

Im Härtetest wurden auf 90 Seiten Unterschrift oder Stempel künstlich entfernt oder verschoben. 88 davon hat die Anwendung erkannt, 2 gingen an die Person, und keine wurde als „ok“ durchgelassen.

### Die 8 Akzeptanzkriterien

Zu jedem Wert stehen das Ziel und das 95-%-Konfidenzintervall (KI).

Erfüllt:

1. Dokumenttyp richtig: 100 % (42/42), Ziel ≥ 98 %, KI 92 bis 100 %
2. Dokumenttyp „unsicher“: 0 %, Ziel ≤ 5 %, KI 0 bis 8 %
3. Tournummer, angenommene Lesungen richtig: 100 % (31/31), Ziel ≥ 99 %, KI 89 bis 100 %
4. Unterschrift auf CMR gefunden: 100 % (19/19), Ziel ≥ 95 %, KI 83 bis 100 %
5. Manipulierte Seiten erkannt: 97,8 % (88/90), Ziel ≥ 95 %, KI 92 bis 99 %

Verfehlt:

6. Stempel auf CMR gefunden: 80 % (16/20), Ziel ≥ 95 %, KI 58 bis 92 %
7. Tournummer-Box gefunden: 90,6 % (29/32), Ziel ≥ 98 %, KI 76 bis 97 %
8. Fehlalarmrate auf korrekten Seiten: 16,7 % (3/18), Ziel ≤ 5 %, KI 6 bis 39 %

Laufzeit pro Seite auf einer normalen CPU ohne Grafikkarte: Detektor etwa 0,4 s, Dokumenttyp-OCR etwa 1,7 s, Nummern-OCR etwa 0,1 s.

Formal hat der Lauf damit nicht bestanden. Die drei verfehlten Werte führen aber zu mehr Arbeit für die Person und nicht zu falsch freigegebenen Dokumenten: Ein übersehener Stempel wird zum Fehlalarm, die Person sieht ihn und braucht einen Klick.

Mit 42 Testseiten lässt sich ein Ziel von 98 % statistisch nicht nachweisen. 19 von 19 richtig heißt mit 95 % Sicherheit nur, dass der wahre Wert bei mindestens 83 % liegt. Deshalb steht bei jeder Zahl das Konfidenzintervall.

> 📷 Bild einfügen: Folie „Was beim Sachbearbeiter ankommt“. Quelle: `make create_pdf`, dann `artifacts/report/praesentation/`

> 📷 Bild einfügen: Folie „Beispiel Härtetest: Unterschrift entfernt“. Quelle: wie oben

---

## 7. Probleme in den echten Daten und was wir dagegen tun

### Vorgedruckte Unterschriften und Stempel (CMR-Feld 22/23)

* Der Absender druckt seine Unterschrift und seinen Stempel als Bild mit auf das CMR. Für ein Modell sehen sie echt aus.
* Die Lösung kommt ohne ML aus. Die Anwendung findet die Feldzeile über die gedruckten Rahmenlinien und übermalt Feld 22 und 23 weiß, im Training, in der Auswertung und später im Browser.
* Die Feldzeile wurde auf allen 19 CMR-Testseiten gefunden, und keine echte Unterschrift wurde versehentlich übermalt.

> 📷 Bild einfügen: ein Masken-Kontrollbild (blau sind die gefundenen Felder). Quelle: `artifacts/report/gallery/maske_00.jpg` (oder die Folie „Schritt 3: Vordruck-Maske“)

### Stempel über gedruckten Feldern

* Auf einer CMR-Seite liegt der Stempel über CMR-Zählung, Tournummer und TA-Nummer. Das Modell hat alle drei Boxen verfehlt, und die Tournummer war nicht lesbar. Das war der einzige OCR-Fehler im Test.
* Die Anwendung zeigt so eine Seite als Klärfall an. Die Person zieht eine Box, und die Live-OCR liest die Nummer nach.

> 📷 Bild einfügen: Tour 609, Seite 35. Quelle: `artifacts/report/gallery/detektor_02.jpg` und `tournummer_00.jpg`

### Seltene Layouts

* Eine Ladeliste mit nur einer TA sieht anders aus als die üblichen. Das Modell fand dort weder Tournummer noch TA noch Seitenzahl.
* Wir brauchen mehr gelabelte Beispiele solcher Fälle. Bis dahin landet die Seite bei der Person.

> 📷 Bild einfügen: Tour 606, Seite 5. Quelle: `artifacts/report/gallery/detektor_04.jpg`

### Übersehene Stempel und Unterschriften ohne erkennbaren Grund

* Auf CMR hat das Modell 4 von 20 Stempeln übersehen, daher kommen alle 3 Fehlalarme. Auf Lieferscheinen fand es 9 von 13 Unterschriften.
* Auf den Bildern ist nichts Auffälliges zu sehen, weder schlechte Scans noch Strich-Unterschriften. Das Modell hat schlicht zu wenige Beispiele gesehen. Je Tour schwankt der Stempel-Recall zwischen 75 % und 100 %.
* Helfen würden mehr gelabelte Touren. Korrekturen auf der Prüfseite werden automatisch zu Trainingsdaten.

> 📷 Bild einfügen: übersehener Stempel auf einem CMR (grün das Label, rot die Vorhersage). Quelle: `artifacts/report/gallery/position_00.jpg`

### Viele ähnliche Nummern, OCR-Verwechsler

* Auf den Seiten stehen viele andere 8-stellige Nummern. Deshalb liest die Anwendung eine TA nur aus ihrer Box und sucht nie über die ganze Seite.
* Die OCR verwechselt O und 0, l und 1, `\` und `/`. Die Anwendung korrigiert das nur an Stellen, an denen das bekannte Format eine Ziffer erwartet.

### Handschrift auf der Ladeliste

* Gestrichene TAs („nie jedzie“, rot durchgestrichen) erkennt kein Modell zuverlässig. Die Person streicht sie selbst, farbige Vermerke markiert die Anwendung als Hinweis.

### Wenig Daten

* Wir haben 289 gelabelte Seiten aus 4 Touren. Jede einzelne Fehlentscheidung verschiebt die Testwerte um mehrere Prozentpunkte.

Wir hatten mit schlechten Scans und Strich-Unterschriften als Hauptproblem gerechnet. In den Testdaten waren es Überlagerungen, seltene Layouts und zu wenige Beispiele. Das hat erst die Fehlergalerie gezeigt.

---

## 8. Warum lokale Modelle?

* Die Scans enthalten Kundenadressen, Namen und Unterschriften. Mit lokalen Modellen verlassen sie den Rechner nicht.
* Die Modelle laufen offline. Es gibt keine Gebühr pro Seite, kein API-Konto und keinen Ausfall, wenn das Netz Probleme hat.
* Ziel ist der Browser auf einem normalen Arbeitsplatz (Microsoft Edge, 8 GB RAM), ohne Server und ohne Grafikkarte.
* Der Detektor RF-DETR Nano und die OCR PP-OCR mobile sind klein genug dafür. Eine Seite braucht auf der CPU wenige Sekunden, die Texterkennung eingerechnet.
* Jede Entscheidung hat eine Box, einen Score und eine Regel. Die Person kann also nachvollziehen, warum die Anwendung etwas vorschlägt.
* Im Kern stecken nur Lizenzen, die wir frei nutzen dürfen (Apache-2.0, MIT, BSD).

---

## 9. Warum nicht einfach ein großes KI-Modell?

### Gemessen: imajev-4b gegen RF-DETR Nano

imajev-4b ist ein Bild-Sprach-Modell mit 4 Mrd. Parametern, das auf Ja/Nein-Fragen zu Bildern trainiert ist. Wir haben es mit unserem Detektor RF-DETR Nano verglichen, auf denselben Testseiten, mit derselben Maske und derselben Bewertung.

* Ohne einen einzigen Fehlalarm erkannt (Recall bei Precision 100 %):
  * Unterschrift: imajev 44 %, RF-DETR 84 %
  * Stempel: imajev 23 %, RF-DETR 100 %
* Trennschärfe (AUC, 1,0 ist perfekt): bei der Unterschrift 0,95 für imajev und 0,99 für RF-DETR, beim Stempel 0,95 und 1,00
* Von 17 CMR-Seiten entscheidet imajev 4 selbst und schickt 13 an die Person. RF-DETR entscheidet 15 selbst und schickt 2. Keines der beiden Modelle übersieht einen Fehler.
* Laufzeit pro Ansicht: imajev etwa 73 s, RF-DETR etwa 0,35 s auf einer normalen CPU
* imajev liefert keine Boxen. Damit ließen sich weder die Prüfung des richtigen Felds noch die Ausschnitte für die Person umsetzen.

> 📷 Bild einfügen: Folie „Alternative geprüft: Sprach-Bild-Modell (imajev-4b)“. Quelle: `make vlm-compare`, danach `make create_pdf`, Bild in `artifacts/report/praesentation/`

### Nicht gemessen: Cloud-Modelle (GPT, Claude, Gemini …)

Cloud-Modelle haben wir nicht getestet. Gegen sie sprechen folgende Gründe:

* Kundendaten und Unterschriften gingen an einen externen Dienst.
* Bei etwa 30 × 75 Seiten pro Woche fallen Kosten pro Seite an, und wir hingen von Netz und Anbieter ab.
* Die Antworten kommen als Freitext ohne Boxen und ohne kalibrierte Scores. Wann ein Ergebnis „sicher“ ist, lässt sich so schwer festlegen.
* Bei Nummern, die exakt stimmen müssen, besteht das Risiko erfundener Antworten.

Für eine eng definierte Ausgabe wie eine Box, eine Nummer oder ein Ja/Nein war in unserem Test ein kleines, auf eigenen Daten trainiertes Modell genauer und rund 200-mal schneller als ein großes Allzweckmodell. Laufende Kosten fallen dabei nicht an.

---

## 10. Der Mensch in der Schleife

* Die Prüfseite führt in fünf Schritten durch die Tour: Seiten zuordnen, Ladeliste, Lieferscheine, CMR, Abschluss.
* Jeder Schritt beginnt mit einem Blatt „Was jetzt?“. Es zeigt, wie viel noch offen ist, und hat einen Knopf zum ersten offenen Punkt.
* Die Seite zeigt nur die Ausschnitte, auf die es ankommt, jeweils neben dem gelesenen Wert. Niemand muss durch 100 Seiten blättern.
* Sichere Seiten bestätigt die Person gesammelt, unsichere einzeln.
* Fehlt etwas, kann die Person es „trotzdem akzeptieren“, muss dafür aber einen Grund angeben. Der Grund steht im Protokoll.
* Jede Korrektur wird zu Trainingsdaten, denn eine gezogene oder verworfene Box fließt ins nächste Training. Je besser das Modell wird, desto weniger muss die Person klicken.

> 📷 Bild einfügen: Prüfseite, Schritt „CMR“ mit Kacheln (TAs grün oder rot, Ausschnitte von Stempel und Unterschrift). Quelle: Screenshot von `make review RUN=<Tour>`

> 📷 Bild einfügen: Prüfseite, große Ansicht einer Seite mit den Karten „Zu tun auf dieser Seite“. Quelle: wie oben, eine Kachel anklicken

> 📷 Bild einfügen: Prüfseite, Schritt „Abschluss“ mit Fehlliste. Quelle: wie oben

---

## 11. Muster für lokale ML-Anwendungen

### Aufgabenmuster, die sich wiederverwenden lassen

1. Seite klassifizieren und sortieren: Dokumenttyp aus Text und Bild
2. Objekt finden und Regel prüfen: Sind Stempel, Unterschrift oder Etikett da, und stehen sie an der richtigen Stelle?
3. Feld lesen und gegen ein Format prüfen: Nummer, Datum, Zählung
4. Zwei Quellen abgleichen: Was steht auf der Liste und fehlt bei den Dokumenten, und umgekehrt?

### Was wir gelernt haben

* Wenn die Ausgabe eng definiert ist, schlägt ein kleines spezialisiertes Modell mit Regeln ein großes allgemeines.
* Fachwissen in der Vorverarbeitung, etwa die Vordruck-Maske, bringt oft mehr als ein größeres Modell.
* Wir legen die Schwellen so, dass nichts durchrutscht. Alles Unsichere geht an den Menschen.
* Der größte Hebel sind mehr und sauber gelabelte Beispiele, nicht die Modellgröße.
* Wir geben Konfidenzintervalle an, testen mit künstlichen Fehlern und stellen per ONNX-Paritätstest sicher, dass Training und Betrieb dasselbe rechnen.

---

## 12. Stand und nächste Schritte

Pipeline, Prüfseite und Abschluss sind lauffähig und an echten Touren getestet. Im Einsatz ist die Anwendung noch nicht.

Die erste Zeitmessung ergab 8 Minuten statt etwa 16 pro Tour, beim ersten Durchlauf und ohne Vorerfahrung. Mit Routine und einem besseren Modell, das mehr selbst erkennt, sollte die Zeit weiter sinken.

### Entscheidungen (mit dem Fachbereich geklärt, Stand 14.10.2026)

<> Die Person hat immer das letzte Wort über Stempel und Unterschrift.

<> Quelle der verladenen TAs ist die Ladeliste mit ihren handschriftlichen Streichungen, nicht SAP.

<> Die Anwendung erzeugt Mails nur als Entwurf, senden müssen die Benutzer.

<> Fehlende Dokumente oder ungültige Seiten gehen nur nach aktiver Zustimmung mit Grund durch.

<> Der Detektor bleibt RF-DETR, das Bild-Sprach-Modell verfolgen wir nicht weiter.

<> Im Kern nutzen wir nur frei nutzbare Lizenzen (Apache-2.0, MIT, BSD).

### Nächste Schritte

[] Zeitmessung an weiteren Test-Touren wiederholen, bis ein belastbarer Wert pro Tour vorliegt

[] Weitere Touren labeln, besonders seltene Layouts und CMR-Stempel, dann neu trainieren und auswerten

[] TA-Abgleich an echten Touren validieren (bis dahin bleibt er ein Hinweis)

[] Nachtrag: ein einzelnes Ersatz-CMR nachträglich der Tour zuordnen

[] Oberfläche und Protokoll auf Rumänisch und Englisch

[] Protokoll je Tour direkt in einen freigegebenen Ordner schreiben

[] Sammelbestätigung von Hermes und DHL in die Prüfung aufnehmen

[] Umzug in den Browser (ONNX Runtime Web) und Pilotbetrieb mit dem Vertrieb

---

## Anhang: Technik

### Modelle (alle lokal, ONNX)

* Objekterkennung: RF-DETR Nano, 640 px, 7 Klassen, Apache-2.0
* OCR: PP-OCRv5 mobile für Texterkennung und Lesen, PP-OCRv6 small zum Vergleich, Apache-2.0
* Dokumenttyp: Schlüsselwörter (DE/PL), dazu MobileNetV3 small als zweite Stimme
* Vor- und Nachverarbeitung haben wir selbst geschrieben, damit sie sich 1:1 nach JavaScript portieren lässt.

### Datenbasis

* 289 gelabelte Seiten aus 4 Touren mit 1.238 Boxen
* 162 Lieferscheine, 96 CMR, 25 Ladelisten, 4 Sammelbestätigungen, 2 Abholscheine
* Aufteilung train/valid/test: 202/45/42 Seiten, gruppiert nach Sendung. Seiten einer Sendung landen nie zugleich in Training und Test.

### Qualitätssicherung

* ONNX-Paritätstest: Zwischen PyTorch und ONNX Runtime weicht der Score um höchstens 0,0012 ab. Training und Betrieb rechnen also dasselbe.
* Die eigene OCR-Implementierung stimmt zu 100 % mit der offiziellen PaddleOCR-Referenz überein (32/32).
* Die Schwellen je Klasse sind auf dem valid-Split kalibriert, der Test-Split bleibt unberührt.
* Härtetest mit künstlichen Negativen, bei denen Unterschrift oder Stempel entfernt oder verschoben sind

### Wichtige Befehle

* `make all`: aufteilen, trainieren, exportieren, auswerten. Ergebnis in `artifacts/report/report.html`
* `make create_pdf`: Präsentation mit Beispielseiten als `artifacts/report/praesentation.pdf` und PNGs
* `make vlm-compare`: Vergleich mit imajev-4b, Ergebnis in `artifacts/vlm_compare/report.md`
* `make process SCANS=<pdf>`: eine Tour verarbeiten
* `make review RUN=<Tour>`: Prüfseite mit Live-OCR
* `make finalize RUN=<Tour>`: PDFs, Mail-Entwürfe, Protokoll, Label-Export

Mehr dazu steht in `README.md` und `docs/PROZESS.md` im Repository.
