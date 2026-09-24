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
- `zones.rules` – was pro Dokumenttyp gefordert ist (`require`, `mode: all` = und, `any` = oder)
  und was nur geprüft wird, *falls* vorhanden (`optional`: dann muss es in der Zone liegen).
  CMR: Unterschrift + Stempel gefordert; Lieferschein: nichts gefordert, vorhandene
  Unterschrift/Stempel müssen aber in der Zone liegen; Loading List: nichts.
- `zones.overrides` – manuelle Korrektur einzelner Zonenkanten, z. B. CMR über die ganze
  Breite (Felder 22, 23, 24).
- `labels.tour_number.format_regex` – Tour/Datum/Nummer, z. B. `503/01.09.2026/4000`
  (alle drei Teile zusammen sind die Tournummer). Die OCR-Korrektur sucht das Muster auch
  innerhalb des gelesenen Texts (z. B. Beschriftung „Tour“ davor) und ersetzt Verwechsler
  (O→0, l→1, `\`→`/`, `,`→`.`) nur an Stellen, an denen das Format eine Ziffer/Trenner erwartet.
- `acceptance` – Schwellen für `make eval`.

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
