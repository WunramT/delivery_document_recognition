# Dokumentvalidierung – lokale Test- und Evaluationsumgebung

Prüft gescannte Versanddokumente (Loading List, Lieferschein, CMR) seitenweise:

1. **Dokumenttyp** – OCR-Keywords im Kopfbereich (PP-OCR), optional Bildklassifikator als zweite Stimme
2. **Objekte** – RF-DETR erkennt `unterschrift`, `stempel`, `tour_nummer`, `cmr_count`
3. **Positionsprüfung** – liegen Unterschrift/Stempel in den Soll-Zonen des Dokumenttyps?
4. **Tournummer** – Crop der `tour_nummer`-Box → PP-OCR → Formatprüfung + Konfidenz-Schwelle

Die Produktion läuft später im Browser (ONNX Runtime Web). Deshalb wertet `make eval`
**ausschließlich die ONNX-Modelle** aus, und Vor-/Nachverarbeitung (RF-DETR, PP-OCR-CTC,
DB-Textdetektion, Zonen- und Regel-Logik) sind selbst implementiert – ohne Python-Tricks,
damit sie 1:1 nach JavaScript portiert werden können.

## Setup

### Variante A: Devcontainer (empfohlen)

VS Code → „Reopen in Container“ → **`docval (CPU)`** oder **`docval (GPU, NVIDIA)`** wählen
(`.devcontainer/cpu/` bzw. `.devcontainer/gpu/`, gemeinsames `.devcontainer/Dockerfile`).

- Python 3.11, OpenCV-Systembibliotheken, poppler (PDF-Rendering).
- GPU-Variante: `--gpus all`, PyTorch mit CUDA 12.6. Alles läuft auch auf der CPU, nur langsamer.
- `labels/` wird **read-only** nach `/data` gemountet (`DOCVAL_DATA=/data`); Eingabedaten werden nie verändert.
- Modellgewichte liegen im benannten Docker-Volume `docval-models` (`/models`).
  `postCreateCommand` führt einmal `make fetch-models` aus – danach läuft alles **offline**.

### GPU mit Podman unter Windows (einmalig)

Fehler `unresolvable CDI devices nvidia.com/gpu=all` beim Start des GPU-Containers heißt:
In der Podman-Maschine fehlt die CDI-Beschreibung der NVIDIA-GPU. Voraussetzung ist ein
aktueller NVIDIA-Treiber unter Windows (die GPU wird per WSL durchgereicht). Dann einmalig:

```powershell
podman machine ssh
```
```bash
# in der Podman-Maschine (Fedora):
curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
  | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
sudo yum install -y nvidia-container-toolkit
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list          # muss nvidia.com/gpu=all anzeigen
exit
```

Test: `podman run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi`. Danach den Container
neu öffnen („Rebuild Container“ ist nicht nötig, „Reopen in Container“ reicht) und im Container
`make gpu-check` ausführen. Nach einem Treiber-Update die `cdi generate`-Zeile wiederholen.
Bis dahin funktioniert die Variante **`docval (CPU)`** ohne weitere Einrichtung.

### Variante B: ohne Container

```bash
python3.11 -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 torchvision==0.29.0
pip install -r requirements.txt
pip install -r requirements-reference.txt   # optional: PaddleOCR-Python-Referenz
pip install --force-reinstall --no-deps opencv-contrib-python==4.10.0.84   # nur mit Referenz
make fetch-models
```

Ohne `make` (Windows, PowerShell): `$env:PYTHONPATH="src"`, dann `python -m docval <befehl>`
(`split`, `train`, `export`, `eval`, `report`, `fetch-models`) bzw. `python scripts/inspect_dataset.py`.

### Abhängigkeiten und Lizenzen

- `requirements.in` = direkte Abhängigkeiten, `requirements.txt` = alle exakt gepinnt (Python 3.11).
- Nur Apache-2.0/MIT/BSD im Kern. RF-DETR nur **N/S/M** (Apache-2.0; XL/2XL sind PML und werden
  abgelehnt). Kein ultralytics/YOLO, Chandra, Surya.
- MPL-2.0 (unverändert genutzt): `certifi`, `tqdm`.
- `requirements-reference.txt` (PaddleOCR/paddlex) zieht die LGPL-Pakete `crc32c` und
  `python-bidi` nach und ist deshalb **optional** (nur für den Referenzvergleich,
  `ocr.paddle_reference`). Der Kern läuft ohne.

## Make-Targets

| Target | Was passiert |
|---|---|
| `make inspect` | Schritt 0: Statistik, Validierung, Herkunft Dokumenttyp/Tournummer, Gruppierung → `artifacts/inspect/inspect.md`; legt ggf. Label-Vorlagen + `labels/tour_review.html` an |
| `make split` | train/valid/test 70/15/15, fester Seed, **gruppiert nach Sendung**, stratifiziert nach Dokumenttyp → `artifacts/splits/detector/{train,valid,test}/_annotations.coco.json` (Bilder verlinkt), `artifacts/splits/split.json` |
| `make train` | RF-DETR (`detector.size`, Standard Nano, 640 px) + Dokumenttyp-Klassifikator (timm MobileNetV3); Logs: TensorBoard + `metrics.csv` in `artifacts/detector/run/` |
| `make export` | Detektor → `artifacts/detector/detector.onnx` + **Paritätstest** PyTorch vs. ONNX Runtime (CPU) auf 20 Bildern → `parity.json` (Exit 3 bei Abweichung) |
| `make eval` | alle Stufen auf dem Test-Split mit ONNX → `artifacts/report/report.md` + `report.html` + `pages.csv`; **Exit-Code 1, wenn ein Kriterium verfehlt wird**. `make eval SPLIT=valid` wertet zur Diagnose den valid-Split aus |
| `make report` | Report aus `artifacts/report/results.json` neu rendern (ohne neu zu rechnen) |
| `make relabel` | Vorlabels: bisherige Labels + Modellergebnisse je Export als COCO mit Bildern (+ zip) → `artifacts/relabel/` |
| `make review-labels` | Label-Prüfung: Detektor vs. Labels auf allen Splits, `cmr_count`-Stapel je Tour → `artifacts/label_review/` (`REVIEW_SPLIT=test` für nur einen Split) |
| `make test` | pytest-Unit-Tests |
| `make smoke` | ganze Pipeline auf 12 synthetischen Seiten, 1 Epoche, CPU (~1 min, Grenze 5 min) – prüft, ob die Umgebung intakt ist |
| `make fetch-models` | alle Gewichte in den Cache (einmalig, online) |
| `make gpu-check` | zeigt, ob PyTorch die GPU sieht (sonst Training auf der CPU) |
| `make all` | split → train → export → eval |

Richtwert Training auf der CPU (Nano, 640 px, 55 Trainingsseiten): grob 2–5 min pro Epoche, mit
Early Stopping typischerweise 1–3 h. Auf einer GPU wenige Minuten.

## Konfiguration (`config.yaml`)

Alles Einstellbare steht dort: Pfade, Klassen, Label-Quellen, Split, Detektor-Hyperparameter,
Keywords (DE/PL, erweiterbar), Zonen-Regeln, Regex der Tournummer, OCR-Modelle, Schwellen und
Akzeptanzkriterien. `configs/smoke.yaml` überschreibt nur einzelne Werte (`extends:`).

Wichtige Stellen:

- `split.group_by: segment` – eine neue Sendung beginnt bei jedem CMR-Block; die Loading List
  ist ein eigenes Segment. Weil es nur eine Loading List gibt, werden ihre Seiten einzeln
  verteilt (`ungroup_doc_types`) – das Leck-Risiko steht im Report.
  Alternativen: `source_pdf`, `tour_number` (sobald die Tournummern erfasst sind), `none`.
- `detector.score_threshold: auto` – Schwelle je Klasse mit bestem F1 auf dem **valid**-Split;
  der Test-Split bleibt unberührt. Alternativ eine feste Zahl für alle Klassen.
- `zones.rules` – was pro Dokumenttyp gefordert ist:
  - **CMR:** gilt nur als unterschrieben, wenn **jedes** der Felder 22 (Absender), 23
    (Frachtführer) und 24 (Empfänger) eine Unterschrift enthält (`fields`, Zuordnung über den
    Box-Mittelpunkt). Die Feld-Boxen sind eine Näherung des Standard-CMR und stehen direkt in
    der Config; der Report zeigt je Feld, wie oft es laut GT unterschrieben ist. Soll pro Feld
    auch ein Stempel da sein: `stempel` in `require` des Felds ergänzen.
  - **CMR, Nebenzone Feld 13:** `review_zones` – liegt Unterschrift/Stempel nicht im
    Unterschriftsbereich, aber in Feld 13 (zugelassen), wird die Seite `unsicher` =
    Prüfung durch eine Person (`action: ok` würde sie akzeptieren). Der Report listet alle
    annotierten Objekte außerhalb der Soll-Zone mit Position, um die Feld-13-Box zu prüfen.
  - **Lieferschein, Loading List:** nichts gefordert, Position nicht geprüft.
  - Die Loading List ist für Tournummer und Akzeptanzkriterien nicht relevant
    (`ocr.doc_types`, `acceptance.doc_types`); sie bleibt für den Dokumenttyp im Datensatz.
  - Allgemein möglich: `require` + `mode` (`all`/`any`) mit abgeleiteten Zonen je Klasse und
    `optional` (nur geprüft, falls vorhanden).
- `zones.overrides` – manuelle Korrektur einzelner Kanten abgeleiteter Zonen.
- `form_mask` – **Vordruck-Maske für CMR:** Stempel + Unterschrift in Feld 22/23 sind
  eingescannte Originale, die mitgedruckt werden, und sehen echt aus. Die Feldzeile 22/23/24
  wird über die gedruckten Rahmenlinien gefunden (lange waagerechte/senkrechte Linien →
  eingeschlossene Zellen → unterste Zeile mit 3 Zellen), Feld 22 + 23 werden samt Rahmen
  weiß gefüllt – beim Split (Training sieht maskierte CMR-Seiten), in der Evaluation und
  später im Browser (OpenCV.js). Übrig bleibt nur die echte Unterschrift/der echte Stempel.
  Der Report zeigt, auf wie vielen CMR-Seiten die Zeile gefunden wurde, und die Galerie
  „Maske“ Kontrollbilder. Passt die Erkennung nicht: `search_y`, `cell_min_w/max_w`,
  `line_min_frac` anpassen.
- `labels.tour_number.format_regex` – Tour/Datum/Nummer, z. B. `503/01.09.2026/4000`
  (alle drei Teile zusammen sind die Tournummer). Die OCR-Korrektur sucht das Muster auch
  innerhalb des gelesenen Texts (z. B. Beschriftung „Tour“ davor) und ersetzt Verwechsler
  (O→0, l→1, `\`→`/`, `,`→`.`) nur an Stellen, an denen das Format eine Ziffer/Trenner erwartet.
- `acceptance` – Schwellen für `make eval`.

## Mehrere Exporte

Jeder Scan-Stapel (= eine Tour) als eigener Ordner direkt unter `labels/`, benannt
`<Tour>_<Datum>`:

```
labels/
  425_21.09.2026/  _annotations.coco.json  images/  page_types.csv  tour_numbers.csv (optional)
  503_01.09.2026/  ...
```

(`labels/exports/<Name>/` funktioniert ebenso.) Sobald mindestens ein solcher Ordner existiert,
werden alle bei jedem Befehl automatisch zusammengeführt (`artifacts/merged/`, nur JSON/CSV –
Bilder werden nicht kopiert); `paths.coco`/`paths.images` werden dann ignoriert.

- **Tournummer aus dem Ordnernamen:** `425_21.09.2026` → `425/21.09.2026/4000` (Werk aus
  `labels.tour_number.from_export_name.plant`) für jede Seite mit `tour_nummer`-Box. Eine
  `tour_numbers.csv` im Ordner hat Vorrang (Ausnahmen).
- `page_types.csv` muss aus **demselben** Export stammen wie `_annotations.coco.json` und
  `images/` – sonst warnt der Report („Labels passen nicht zu den Bildern“).
- Dateinamen werden zu `<Ordner>/images/<Datei>`; gleiche Namen in zwei Exporten sind kein Problem.
- Jeder Export ist eine eigene Gruppe im Split; Seiten verschiedener Touren vermischen sich nie.
- Dieselbe PDF-Seite in zwei Exporten wird als Warnung gemeldet („doppelte Seiten“).
- Nach dem Hinzufügen eines Exports: `make inspect split train export eval`.

## Label-CSVs ausfüllen

- **Dokumenttyp:** `labels/page_types.csv` (`file_name;doc_type;source_pdf;source_page`) –
  vorhanden. Werte müssen in `doc_types` stehen (`cmr`, `lieferschein`, `loading_list`).
  Trennzeichen und Spalten werden erkannt; Dateinamen werden auch ohne Ordner/Endung zugeordnet.
- **Tournummer:** `labels/tour_numbers.csv` (`file_name,tour_number`). Am einfachsten:
  1. `make inspect` (erzeugt Crops unter `artifacts/inspect/tour_crops/`)
  2. `labels/tour_review.html` im Browser öffnen, Nummern eintippen (Enter = nächstes Feld;
     Eingaben bleiben im Browser gespeichert), „herunterladen“, Datei als `labels/tour_numbers.csv` speichern.
     Format: `503/01.09.2026/4000` (die ganze Nummer, ohne Beschriftung).
  3. Unleserlich: `?` eintragen – eine automatisch akzeptierte OCR-Lesung dort zählt als Fehler.
- Quelle umschalten: `labels.*.source` (`csv` oder `coco_attribute`, z. B. `attributes.text`).
- Bestehende CSVs werden nie überschrieben, nur um neue Dateinamen ergänzt.

## Soll-Zonen

`make eval` leitet die Zonen aus dem **Train-Split** ab (Perzentile 2–98 % der Box-Zentren plus
Rand und halbe Median-Boxgröße) und schreibt `artifacts/zones.yaml`. Zum manuellen Korrigieren
Werte ändern und `locked: true` setzen – dann wird die Datei nicht mehr überschrieben;
frisch abgeleitete Werte stehen weiter in `artifacts/zones.derived.yaml`.

## Labels prüfen (`make review-labels`)

Nach `make eval` (nutzt dessen kalibrierte Schwellen) läuft der Detektor über **alle** Seiten,
auch die Trainingsseiten, und jede Abweichung zu den Labels landet in einer Kategorie:

| Kategorie | Bedeutung | Typische Ursache |
|---|---|---|
| Box anders gezogen | GT und Vorhersage überlappen, IoU < 0,5 – zählt in den Metriken als „nicht gefunden“ **und** „falsch-positiv“ | uneinheitlicher Label-Stil (z. B. „CMR 3/9“ vs. nur „3/9“) |
| Label fehlt? | sichere Vorhersage ohne GT-Box | vergessenes Label – besonders verdächtig auf `train` |
| Andere Klasse? | Vorhersage liegt auf GT-Box einer anderen Klasse | Klasse verwechselt |
| Nicht erkannt | GT-Box ohne überlappende Vorhersage | eher Modell, oder Box auf etwas anderem |
| Doppeltes Label | zwei GT-Boxen derselben Klasse übereinander | doppelt geklickt |

Dazu für `cmr_count`: OCR jeder GT-Box (unlesbare Boxen mit Bild), die Stapelprüfung je
Export/Tour (jede Nummer 1…n genau einmal?), CMR-Seiten **ohne** `cmr_count`-Label und die
Boxgröße je Export (große Unterschiede = unterschiedlich gezogene Boxen). In
`label_review.csv` gibt es eine leere Spalte `entscheidung` zum Abhaken; korrigiert wird im
Label-Tool, danach neu exportieren und `make split train export eval`.

## Labels mit Modell-Vorschlägen überarbeiten (`make relabel`)

Nach `make eval` schreibt `make relabel` je Export einen Ordner im selben Aufbau wie die Eingabe
(`artifacts/relabel/<Tour>_<Datum>/` mit `_annotations.coco.json`, `images/`, `page_types.csv`,
gleiche Bild-IDs und Dateinamen) plus `<Tour>_<Datum>.zip`. Darin:

- Label und Modell stimmen überein → Label bleibt (`relabel.matched: model` übernimmt die meist engere Modellbox)
- Box anders gezogen → Modellbox ersetzt das Label (`different_box`)
- sichere Vorhersage ohne Label (Score ≥ `add_min_score`, Standard 0,3) → ergänzt
- doppeltes Label → eins entfernt
- Vorhersage auf einer Box anderer Klasse → nicht übernommen (meist Modellfehler)
- Labels in den maskierten CMR-Feldern 22/23 und nicht gefundene Labels → unverändert

**Bearbeiten:** `artifacts/relabel/<Tour>_<Datum>/editor.html` per Doppelklick im Browser
öffnen (Chrome/Edge empfohlen, läuft offline, kein Server nötig). Links die Seitenliste
(Filter „mit Modell-Vorschlägen“ / „ungeprüft“), in der Mitte die Seite mit allen Boxen:

- Box anklicken und verschieben, Ecken/Kanten ziehen = Größe, auf freier Fläche aufziehen = neue Box
- `1`–`4` Klasse wählen bzw. die markierte Box umstellen, `Entf` löschen, `Strg+Z` rückgängig
- Pfeiltasten verschieben (Shift = 10 px, Alt = Größe), `A`/`D` Seite zurück/vor, `Enter` = geprüft + weiter
- `O` blendet die alten Labels grau ein, `+`/`-`/`0` Zoom; Dokumenttyp oben pro Seite änderbar
- gestrichelt = Vorschlag des Modells, noch nicht angefasst

Der Zwischenstand bleibt im Browser erhalten (Seite schließen ist kein Problem). Zum Schluss
**„COCO speichern“** → `_annotations.coco.json` nach `labels/<Tour>_<Datum>/` (alte Datei vorher
sichern; Chrome/Edge fragt nach dem Speicherort, andere Browser legen sie in „Downloads“ ab),
bei geänderten Typen zusätzlich **„page_types.csv speichern“**. Bild-IDs und Dateinamen bleiben
gleich, die Bilder im Export müssen nicht angefasst werden. Danach
`make inspect split train export eval`.

`relabel_overview.html` zeigt alle geänderten Seiten mit Links zu den Editoren,
`relabel_changes.csv` listet jede Änderung. Wer lieber im bisherigen Label-Tool arbeitet:
`<Tour>_<Datum>.zip` dort importieren (am sichersten als neues Projekt).

## Alte und neue Labels zeigen (`make compare-labels`)

```
make compare-labels EXPORT=425_21.09.2026            # oder nur EXPORT=425
make compare-labels EXPORT=425 OLD=pfad/zur/alten_annotations.coco.json
```

Erzeugt `artifacts/label_compare/<Tour>.html` – eine einzelne Datei mit eingebetteten Bildern
zum Weitergeben: die Label-Konvention (`label_guide` in `config.yaml`), eine Tabelle je Klasse
(ergänzt, entfernt, angepasst, Flächenverhältnis, Größe, Streuung der Boxgröße), Nahaufnahmen
vorher/nachher und alle geänderten Seiten nebeneinander. Die alten Labels kommen aus `OLD`,
sonst aus einer Sicherung im Tour-Ordner (z. B. `_annotations.coco.alt.json`), sonst aus dem
Editor von `make relabel` (dort steht der Stand vor dem Bearbeiten). Achtung: Die Datei enthält
die Scans – nur intern weitergeben.

## Experimente vergleichen (z. B. eine Tour neu gelabelt)

Alle Ordner in `labels/` lassen, nur die überarbeitete Datei austauschen, und den neuen Lauf in
einen **eigenen Artefakt-Ordner** schreiben – der alte Lauf bleibt als Vergleich stehen:

```
DOCVAL_ARTIFACTS=artifacts/exp_425 make split train export eval
make compare A=artifacts B=artifacts/exp_425      # → artifacts/exp_425/report/compare.md
```

Der Split ist derselbe (gleicher Seed, gleiche Seiten, gleiche Dokumenttypen). `compare`
zeigt Akzeptanzkriterien, Recall/AP50 je Klasse und je Export/Tour Recall und mittlere IoU
der Treffer. Die neu gelabelte Tour sollte bei der IoU zulegen, die anderen sollten nicht
schlechter werden. Achtung: Die Test-Labels der Tour haben sich mitgeändert, und je Tour liegen
nur wenige Test-Seiten – kleine Unterschiede sind Rauschen.

## Report lesen (`artifacts/report/report.html`)

1. **Gesamtergebnis und Fazit** – was funktioniert, was verfehlt ist, wo der größte Hebel liegt.
2. **Akzeptanzkriterien** – Wert, Schwelle, Stichprobengröße `n` und **95%-Konfidenzintervall**
   (Wilson). Bei kleinen `n` ist das Intervall breit: 10 von 10 richtig heißt nur „≥ 69 %“ mit
   95 % Sicherheit. Ein Kriterium „ohne Daten/GT“ gilt als verfehlt (`fail_on_missing_gt`).
3. **Detektor** – Paritätstest, Recall/Precision/AP50 je Klasse und eine **P/R-Tabelle über die
   Schwelle**, um `detector.score_threshold` bewusst zu wählen.
4. **Dokumenttyp** – Konfusionsmatrix, Metriken je Typ, Keyword vs. Klassifikator einzeln.
5. **Positionsprüfung** – Fehlalarmrate auf echten korrekten Seiten, Recall auf synthetischen
   Negativen (Unterschrift/Stempel entfernt oder in eine falsche Zone verschoben; unter
   `artifacts/synthetic/`), abgeleitete Zonen und Abgleich mit den CMR-Feldern 22/23/24.
   Seiten, die schon laut GT die Regel nicht erfüllen, sind separat aufgeführt.
6. **Tournummer** – v5 vs. v6, nur Recognition vs. Det+Rec, GT-Box vs. vorhergesagte Box,
   Schwellen-Tabelle (Akzeptanzquote vs. Exact Match) und Referenz PaddleOCR-Python.
7. **Laufzeit** pro Seite und Stufe (CPU).
8. **Fehlergalerie** – bis zu 30 schlimmste Fälle je Stufe: grün = GT, rot = Vorhersage,
   blau = Soll-Zone bzw. OCR-Kopfbereich.

## Struktur

```
.devcontainer/{cpu,gpu}/devcontainer.json, Dockerfile
config.yaml, configs/smoke.yaml
src/docval/data      COCO laden/validieren, Label-Quellen, Split, RF-DETR-Ordner
src/docval/detect    RF-DETR Training/Export/Parität, ONNX-Inferenz
src/docval/doctype   Keyword-Regeln + Kombination, Klassifikator (ONNX)
src/docval/zones     Zonen ableiten, Positionsprüfung, synthetische Negative
src/docval/ocr       PP-OCR ONNX (Det + Rec), Tournummer-Korrektur, CMR-Zählung
src/docval/eval      Metriken, Evaluation, Report
scripts/             inspect_dataset.py, make_smoke_dataset.py, fetch_models.py
labels/              page_types.csv, tour_numbers.csv, tour_review.html
tests/               pytest
artifacts/           (gitignored) Splits, Modelle, ONNX, zones.yaml, report/
```
