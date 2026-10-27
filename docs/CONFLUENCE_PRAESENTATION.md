# Versanddokument-Erkennung mit ML

**Welche manuellen Schritte bei der Dokumentenbearbeitung wir mit lokalen Modellen automatisieren können.**

*Stand: Evaluation 15.10.2026 · PoC lauffähig, noch nicht im Einsatz*

---

## 1. Kurzfassung

* **Was:** Der unsortierte Papierstapel einer Tour (Ladeliste, CMR, Lieferscheine) wird einmal gescannt. Die Anwendung erkennt Dokumenttyp, Nummern, Stempel und Unterschriften, sortiert, gleicht ab und schreibt Mail-Entwürfe und Protokoll.
* **Wie:** ausschließlich **kleine, lokale Modelle** (Objekterkennung, OCR, Bildklassifikator) plus feste Regeln – keine Cloud, kein großes Sprachmodell.
* **Ergebnis:** Auf den CMR-Testseiten wurde **kein einziger fehlender Stempel / keine fehlende Unterschrift übersehen** (0 von 19 echten Seiten, 0 von 90 künstlichen Fälschungen). Unsicheres geht an eine Person.
* **Aufwand:** heute ca. **16 min pro Tour** von Hand, im ersten Test mit der Anwendung **8 min** – ohne Einarbeitung.
* **Gegenprobe:** Ein großes Bild-Sprach-Modell (imajev-4b, 4 Mrd. Parameter) war **deutlich schlechter und ca. 200× langsamer** als unser spezialisiertes Modell.
* **Stand:** lauffähig, im PoC getestet, noch nicht im Einsatz. Größter Hebel: mehr gelabelte Touren.

---

## 2. Ausgangslage: der manuelle Prozess

* ca. **30 Touren pro Woche**, je **50–100 Seiten**, unsortiert aus der Transportabteilung
* heute: **eine Person, ca. 8 Stunden pro Woche** (≈ 16 min pro Tour)
* Handgriffe je Tour:
  * Ladeliste prüfen: Wie viele Aufträge (TA) sind verladen, was ist handschriftlich gestrichen?
  * Stapel in CMR und Lieferscheine trennen, Duplikate aussortieren
  * je CMR: Stempel **und** Unterschrift des Empfängers, richtige Tournummer, Folge 1…n vollständig?
  * je Lieferschein: Stempel **oder** Unterschrift, richtige Tour?
  * je TA: gibt es ein CMR und einen Lieferschein?
  * CMR sortieren, als PDF an die Archiv-Postfächer senden, Papier ablegen

> Typische ML-Aufgabe: viele gleichartige Seiten, wenige feste Fragen, klare Regeln – und ein Mensch, der heute jede Seite einzeln ansieht.

---

## 3. Was wird ersetzt – und durch welche Art von Modell

Legende: **automatisch** · **Vorschlag – Person bestätigt** · **bleibt manuell**

1. **Seiten nach Typ trennen** (CMR, Lieferschein, Ladeliste …) → **automatisch** · *Klassifikation* (OCR-Schlüsselwörter + Bildklassifikator)
2. **Tournummer prüfen** → **automatisch** · *Objekterkennung + OCR + Formatregel*
3. **CMR-Folge vollständig (1/13, 2/13 …)** → **automatisch** · *OCR + Logik*
4. **CMR sortieren, PDFs bauen** → **automatisch** · *reine Logik*
5. **Duplikate aussortieren** → **Vorschlag – Person bestätigt** · *Logik über gelesene Nummern, Kopie mit Stempel bleibt*
6. **TAs der Ladeliste lesen** → **Vorschlag – Person bestätigt** · *Objekterkennung + OCR*; handschriftliche Streichungen markiert die Person (farbige Vermerke werden als Hinweis erkannt)
7. **Je TA ein CMR und ein Lieferschein?** → **automatisch, vorerst als Hinweis** · *Abgleich der gelesenen Nummern*
8. **Stempel und Unterschrift vorhanden und an der richtigen Stelle?** → **Vorschlag – Person entscheidet** · *Objekterkennung + Zonenregel*
9. **Mails an das Archiv** → **Entwurf automatisch, Senden bleibt bei der Person**
10. **Heftklammern, Papierablage, SAP-Kontrolle am Folgetag** → **bleibt manuell** (Erinnerung steht im Protokoll)

> Bewusste Entscheidung: Ob ein Dokument gültig unterschrieben ist, entscheidet immer die Person. Das Modell zeigt ihr nur die richtigen Ausschnitte und sagt „sicher“ oder „unsicher“.

---

## 4. Die Pipeline in vier Bausteinen

```
Papierstapel ──scannen──► Verarbeitung (lokal) ──► Prüfseite im Browser ──► Abschluss
 (unsortiert)              Dokumenttyp, Nummern,     Person bestätigt          CMR_<Tour>.pdf (1..n)
                           Stempel/Unterschrift,     Stempel/Unterschrift,     LS_<Tour>.pdf
                           Duplikate, Abgleich       streicht TAs              Mail-Entwürfe, Protokoll
```

1. **Dokumenttyp** – OCR liest Schlüsselwörter im Kopfbereich (DE/PL), ein kleiner Bildklassifikator stimmt mit ab
2. **Objekte finden** – ein Detektor markiert 7 Dinge: Unterschrift, Stempel, Tournummer, CMR-Zählung, TA-Nummer, Lieferscheinnummer, Seitenzahl
3. **Regeln prüfen** – liegen Stempel/Unterschrift in den Soll-Feldern (CMR-Feld 22/23/24)? Vorgedruckte Felder werden vorher ausgeblendet
4. **Nummern lesen** – OCR nur im Ausschnitt der gefundenen Box, danach Prüfung gegen das bekannte Format (z. B. `503/01.09.2026/4000`)

> Alles danach (Duplikate, Vollständigkeit, TA-Abgleich, Sortieren) ist klassische Programmlogik – ML liefert nur die Bausteine, die vorher ein Mensch „gesehen“ hat.

---

## 5. Beispiel: eine echte CMR-Seite durch alle Schritte

* **Dokumenttyp:** Schlüsselwörter gefunden → CMR
* **Vordruck-Maske:** Feld 22 und 23 tragen eingedruckte Unterschriften/Stempel des Absenders – sie werden weiß übermalt, damit das Modell nur echte Unterschriften sieht
* **Objekte:** Unterschrift und Stempel mit Score (0–1) und Soll-Zone
* **Lesen:** Tournummer und „CMR 3/13“ aus den Boxen, Formatprüfung

> 📷 **Bild einfügen:** Folie „Beispiel: eine CMR-Seite – Schritt 2 Dokumenttyp“ – **Quelle:** `make create_pdf` → `artifacts/report/praesentation/folie_XX.png` (Folien-Titel steht im Bild)

> 📷 **Bild einfügen:** Folie „Schritt 3: Vordruck-Maske – vorher / nachher“ – **Quelle:** wie oben

> 📷 **Bild einfügen:** Folie „Schritt 4–5: Objekte finden und Position prüfen“ – **Quelle:** wie oben

> 📷 **Bild einfügen:** Folie „Schritt 6: Tournummer und CMR-Zählung lesen“ – **Quelle:** wie oben

---

## 6. Ergebnisse (Test-Split, 42 Seiten aus 4 Touren)

**Was beim Sachbearbeiter ankommt** (CMR-Seiten mit Stempel-/Unterschriftsregel, n = 19):

* **15** automatisch richtig entschieden
* **1** an die Person zur Prüfung
* **0** Fehler übersehen
* **3** Fehlalarme („Stempel fehlt“, obwohl einer da ist)
* Härtetest mit 90 künstlich manipulierten Seiten (Unterschrift/Stempel entfernt oder verschoben): **0 fälschlich als „ok“ durchgelassen**, 88 erkannt, 2 an die Person

**Die 8 Akzeptanzkriterien** (Wert · Ziel · 95 %-Konfidenzintervall):

1. ✅ Dokumenttyp richtig: **100 %** (42/42) · Ziel ≥ 98 % · KI 92–100 %
2. ✅ Dokumenttyp „unsicher“: **0 %** · Ziel ≤ 5 % · KI 0–8 %
3. ✅ Tournummer, angenommene Lesungen richtig: **100 %** (31/31) · Ziel ≥ 99 % · KI 89–100 %
4. ✅ Unterschrift auf CMR gefunden: **100 %** (19/19) · Ziel ≥ 95 % · KI 83–100 %
5. ✅ Manipulierte Seiten erkannt: **97,8 %** (88/90) · Ziel ≥ 95 % · KI 92–99 %
6. ❌ Stempel auf CMR gefunden: **80 %** (16/20) · Ziel ≥ 95 % · KI 58–92 %
7. ❌ Tournummer-Box gefunden: **90,6 %** (29/32) · Ziel ≥ 98 % · KI 76–97 %
8. ❌ Fehlalarmrate auf korrekten Seiten: **16,7 %** (3/18) · Ziel ≤ 5 % · KI 6–39 %

**Laufzeit** (normale CPU, ohne Grafikkarte): Detektor ca. 0,4 s, Dokumenttyp-OCR ca. 1,7 s, Nummern-OCR ca. 0,1 s pro Seite.

> Einordnung: Formal „nicht bestanden“ – aber die Fehler zeigen in die **sichere Richtung**. Ein übersehener Stempel wird zum Fehlalarm, landet bei der Person und kostet einen Klick. Durchgerutscht ist nichts.

> Mit 42 Testseiten lässt sich ein Ziel von 98 % statistisch gar nicht nachweisen: „19 von 19 richtig“ heißt nur „mindestens 83 %“ mit 95 % Sicherheit. Deshalb steht bei jeder Zahl das Konfidenzintervall.

> 📷 **Bild einfügen:** Folie „Was beim Sachbearbeiter ankommt“ – **Quelle:** `make create_pdf` → `artifacts/report/praesentation/`

> 📷 **Bild einfügen:** Folie „Beispiel Härtetest: Unterschrift entfernt“ – **Quelle:** wie oben

---

## 7. Probleme aus echten Daten – und was wir dagegen tun

**Vorgedruckte Unterschriften und Stempel (CMR-Feld 22/23)**

* Der Absender druckt seine Unterschrift und seinen Stempel als Bild mit auf das CMR – für ein Modell sehen sie echt aus.
* Lösung ohne ML: Die Feldzeile wird über die gedruckten Rahmenlinien gefunden und Feld 22/23 weiß übermalt – im Training, in der Auswertung und später im Browser.
* Ergebnis: Feldzeile auf **19 von 19** CMR-Seiten gefunden, keine echte Unterschrift versehentlich übermalt.

> 📷 **Bild einfügen:** ein Masken-Kontrollbild (blau = gefundene Felder) – **Quelle:** `artifacts/report/gallery/maske_00.jpg` (oder Folie „Schritt 3: Vordruck-Maske“)

**Stempel über gedruckten Feldern**

* Auf einer CMR-Seite liegt der Stempel über CMR-Zählung, Tournummer und TA-Nummer → alle drei Boxen verfehlt, Tournummer nicht lesbar (der einzige OCR-Fehler im Test).
* Lösung: Seite wird als Klärfall angezeigt, die Person zieht eine Box, die Live-OCR liest die Nummer nach.

> 📷 **Bild einfügen:** Seite 609 / S. 35 – **Quelle:** `artifacts/report/gallery/detektor_02.jpg` und `tournummer_00.jpg`

**Seltene Layouts**

* Eine Ladeliste mit nur einer TA sieht anders aus als die üblichen – das Modell fand dort weder Tournummer noch TA noch Seitenzahl.
* Lösung: mehr Beispiele seltener Fälle labeln; bis dahin landet die Seite bei der Person.

> 📷 **Bild einfügen:** Seite 606 / S. 5 – **Quelle:** `artifacts/report/gallery/detektor_04.jpg`

**Ganz normale Stempel und Unterschriften übersehen**

* Stempel auf CMR: 4 von 20 übersehen – daraus kommen alle 3 Fehlalarme. Unterschrift auf Lieferscheinen: 9 von 13 gefunden.
* Die Bilder sind unauffällig (keine schlechten Scans, keine Strich-Unterschriften) – das Modell hat schlicht zu wenige Beispiele gesehen. Je Tour schwankt der Stempel-Recall zwischen 75 % und 100 %.
* Lösung: mehr Touren labeln. Korrekturen auf der Prüfseite werden automatisch zu Trainingsdaten.

> 📷 **Bild einfügen:** übersehener Stempel auf CMR – **Quelle:** `artifacts/report/gallery/position_00.jpg` (grün = Label, rot = Vorhersage)

**Viele ähnliche Nummern, OCR-Verwechsler**

* Auf den Seiten stehen viele andere 8-stellige Nummern → eine TA wird **nur** aus ihrer Box gelesen, nie per Suche über die ganze Seite.
* OCR verwechselt O/0, l/1, `\`/`/` → Korrektur nur an Stellen, an denen das bekannte Format eine Ziffer erwartet.

**Handschrift auf der Ladeliste**

* Gestrichene TAs („nie jedzie“, rot durchgestrichen) erkennt kein Modell zuverlässig → die Person streicht; farbige Vermerke werden als Hinweis markiert.

**Wenig Daten**

* 289 gelabelte Seiten aus 4 Touren. Jede einzelne Fehlentscheidung verschiebt die Testwerte um mehrere Prozentpunkte.

> Erkenntnis: Erwartet hatten wir schlechte Scans und Strich-Unterschriften. Tatsächlich waren es Überlagerungen, seltene Layouts und zu wenige Beispiele. Erst die Fehlergalerie zeigt die echten Ursachen.

---

## 8. Warum lokale Modelle?

* **Datenschutz:** Die Scans enthalten Kundenadressen, Namen und Unterschriften – sie verlassen den Rechner nicht.
* **Offline und ohne laufende Kosten:** keine Gebühr pro Seite, kein API-Konto, kein Ausfall bei Netzproblemen.
* **Läuft auf normaler Hardware:** Ziel ist der Browser (Microsoft Edge, 8 GB RAM) – ohne Server, ohne Grafikkarte.
* **Klein genug:** Detektor *RF-DETR Nano* und OCR *PP-OCR mobile* – wenige Sekunden pro Seite auf der CPU, inklusive Texterkennung.
* **Nachvollziehbar:** Jede Entscheidung hat eine Box, einen Score und eine Regel – die Person sieht, *warum*.
* **Lizenzen:** nur Apache-2.0 / MIT / BSD im Kern, frei nutzbar.

---

## 9. Warum nicht einfach ein großes KI-Modell?

**Gemessen:** imajev-4b (Bild-Sprach-Modell, 4 Mrd. Parameter, speziell für Ja/Nein-Fragen zu Bildern) gegen unseren Detektor RF-DETR Nano – dieselben Testseiten, dieselbe Maske, dieselbe Bewertung.

* **Ohne einen einzigen Fehlalarm erkannt** (Recall bei Precision 100 %):
  * Unterschrift: imajev **44 %** · RF-DETR **84 %**
  * Stempel: imajev **23 %** · RF-DETR **100 %**
* **Trennschärfe** (AUC, 1,0 = perfekt): Unterschrift 0,95 vs. **0,99** · Stempel 0,95 vs. **1,00**
* **CMR-Entscheidung, 17 Seiten:** imajev entscheidet **4** selbst und schickt 13 an die Person – RF-DETR entscheidet **15** selbst, 2 an die Person. Beide übersehen keinen Fehler.
* **Laufzeit pro Ansicht:** imajev ca. **73 s** · RF-DETR ca. **0,35 s** (normale CPU)
* imajev liefert **keine Boxen** – die Prüfung „richtiges Feld“ und die Ausschnitte für die Person wären damit nicht möglich.

> 📷 **Bild einfügen:** Folie „Alternative geprüft: Sprach-Bild-Modell (imajev-4b)“ – **Quelle:** `make vlm-compare`, danach `make create_pdf` → `artifacts/report/praesentation/`

**Nicht gemessen, aber begründet – Cloud-Modelle (GPT, Claude, Gemini …):**

* Kundendaten und Unterschriften gingen an einen externen Dienst
* Kosten pro Seite bei ca. 30 × 75 Seiten pro Woche, Abhängigkeit von Netz und Anbieter
* Antworten in Freitext ohne Boxen und ohne kalibrierte Scores – „sicher / unsicher“ lässt sich schwer festlegen
* Risiko erfundener Antworten bei Nummern, die exakt stimmen müssen

> Kernaussage: Für eine **eng definierte Ausgabe** (Box, Nummer, ja/nein) ist ein kleines, auf eigenen Daten trainiertes Modell genauer, schneller und billiger als ein großes Allzweckmodell.

---

## 10. Der Mensch in der Schleife

* Die Prüfseite führt in fünf Schritten durch die Tour: Seiten zuordnen → Ladeliste → Lieferscheine → CMR → Abschluss.
* Geführt: Jeder Schritt beginnt mit „Was jetzt?“ – wie viel offen ist und ein Knopf zum ersten offenen Punkt.
* Gezeigt werden nur die entscheidenden **Ausschnitte** neben dem gelesenen Wert – kein Blättern durch 100 Seiten.
* Sichere Seiten werden gesammelt bestätigt, unsichere einzeln.
* Fehlt etwas: „trotzdem akzeptieren“ nur mit Grund – steht im Protokoll.
* **Jede Korrektur wird Trainingsdaten:** Box gezogen oder verworfen → fließt ins nächste Training. Je besser das Modell, desto weniger Klicks.

> 📷 **Bild einfügen:** Prüfseite, Schritt „CMR“ mit Kacheln (TAs grün/rot, Ausschnitte Stempel/Unterschrift) – **Quelle:** Screenshot von `make review RUN=<Tour>`

> 📷 **Bild einfügen:** Prüfseite, große Ansicht einer Seite mit den Karten „Zu tun auf dieser Seite“ – **Quelle:** wie oben, Kachel anklicken

> 📷 **Bild einfügen:** Prüfseite, Schritt „Abschluss“ mit Fehlliste – **Quelle:** wie oben

---

## 11. Muster für lokale ML-Anwendungen

**Vier wiederverwendbare Aufgabenmuster:**

1. **Seite klassifizieren und sortieren** – Dokumenttyp aus Text und Bild
2. **Objekt finden und Regel prüfen** – Stempel, Unterschrift, Etikett: da? an der richtigen Stelle?
3. **Feld lesen und gegen ein Format prüfen** – Nummer, Datum, Zählung
4. **Zwei Quellen abgleichen** – Liste gegen Dokumente: Was fehlt, was ist zu viel?

**Fünf Lehren:**

* Klein + spezialisiert + Regeln schlägt groß + allgemein, wenn die Ausgabe eng definiert ist.
* Fachwissen als Vorverarbeitung (z. B. Vordruck-Maske) bringt oft mehr als ein größeres Modell.
* Schwellen so legen, dass nichts durchrutscht – Unsicheres geht an den Menschen.
* Daten schlagen Modellgröße: Der größte Hebel sind mehr und sauber gelabelte Beispiele.
* Ehrlich messen: Konfidenzintervalle, Härtetests mit künstlichen Fehlern, gleiche Ergebnisse in Training und Betrieb (ONNX-Paritätstest).

---

## 12. Stand und nächste Schritte

**Stand:** Pipeline, Prüfseite und Abschluss sind lauffähig und an echten Touren getestet. Die Anwendung ist **noch nicht im Einsatz**.

**Erste Zeitmessung:** 8 min statt ca. 16 min pro Tour – beim ersten Durchlauf ohne Vorerfahrung. Mit besserem Modell (mehr erkennt es selbst) und Routine sollte es weiter sinken.

**Entscheidungen** (mit dem Fachbereich geklärt, Stand 14.10.2026):

<> Die Person hat immer das letzte Wort über Stempel und Unterschrift.

<> Quelle der verladenen TAs ist die Ladeliste mit ihren handschriftlichen Streichungen, nicht SAP.

<> Mails werden nur als Entwurf erzeugt, Senden bleibt bei den Benutzern.

<> Fehlende Dokumente oder ungültige Seiten nur nach aktiver Zustimmung mit Grund.

<> Detektor bleibt RF-DETR; das Bild-Sprach-Modell wird nicht weiterverfolgt.

<> Nur frei nutzbare Lizenzen (Apache-2.0 / MIT / BSD) im Kern.

**Nächste Schritte:**

[] Zeitmessung an weiteren Test-Touren wiederholen (Ziel: belastbarer Wert pro Tour)

[] Weitere Touren labeln, besonders seltene Layouts und CMR-Stempel – dann neu trainieren und auswerten

[] TA-Abgleich an echten Touren validieren (bis dahin nur Hinweis)

[] Nachtrag: einzelnes Ersatz-CMR nachträglich der Tour zuordnen

[] Oberfläche und Protokoll auf Rumänisch und Englisch

[] Protokoll je Tour direkt in einen freigegebenen Ordner schreiben

[] Sammelbestätigung Hermes/DHL in die Prüfung aufnehmen

[] Umzug in den Browser (ONNX Runtime Web), Pilotbetrieb mit dem Vertrieb

---

## Anhang: Technik

**Modelle (alle lokal, ONNX)**

* Objekterkennung: **RF-DETR Nano**, 640 px, 7 Klassen, Apache-2.0
* OCR: **PP-OCRv5 mobile** (Erkennung + Lesen), PP-OCRv6 small als Vergleich, Apache-2.0
* Dokumenttyp: Schlüsselwörter (DE/PL) + **MobileNetV3 small** als zweite Stimme
* Vor-/Nachverarbeitung selbst geschrieben, damit sie 1:1 nach JavaScript portierbar ist

**Datenbasis**

* 289 gelabelte Seiten aus 4 Touren, 1.238 Boxen
* 162 Lieferscheine, 96 CMR, 25 Ladelisten, 4 Sammelbestätigungen, 2 Abholscheine
* Aufteilung train / valid / test: 202 / 45 / 42 Seiten, gruppiert nach Sendung (Seiten einer Sendung landen nie in Training und Test zugleich)

**Qualitätssicherung**

* ONNX-Paritätstest: Abweichung PyTorch ↔ ONNX Runtime max. 0,0012 im Score → Training und Betrieb rechnen dasselbe
* Eigene OCR-Implementierung stimmt zu 100 % mit der offiziellen PaddleOCR-Referenz überein (32/32)
* Schwellen je Klasse auf dem valid-Split kalibriert, Test-Split bleibt unberührt
* Härtetest: künstliche Negative (Unterschrift/Stempel entfernt oder verschoben)

**Wichtige Befehle**

* `make all` – aufteilen, trainieren, exportieren, auswerten → `artifacts/report/report.html`
* `make create_pdf` – Präsentation mit Beispielseiten → `artifacts/report/praesentation.pdf` und PNGs
* `make vlm-compare` – Vergleich mit imajev-4b → `artifacts/vlm_compare/report.md`
* `make process SCANS=<pdf>` – eine Tour verarbeiten
* `make review RUN=<Tour>` – Prüfseite mit Live-OCR
* `make finalize RUN=<Tour>` – PDFs, Mail-Entwürfe, Protokoll, Label-Export

**Weiterlesen:** `README.md` und `docs/PROZESS.md` im Repository
