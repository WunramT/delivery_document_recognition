# Prototyp: imajev-4b vs. RF-DETR (Unterschrift / Stempel)

Frage: Kann ein Vision-Language-Entscheidungsmodell ([imajev-4b](https://huggingface.co/mohit67890/imajev-4b),
Apache-2.0, LoRA auf Qwen3.5-4B) „Unterschrift da? Stempel da?“ besser beantworten als unser
RF-DETR-Detektor?

`make vlm-compare` nimmt **dieselben Testseiten, dieselbe Vordruck-Maske und dieselbe GT** wie
`make eval`, fragt imajev je Seite und vergleicht mit RF-DETR. Nur ein Test – nicht Teil der
Pipeline (imajev läuft nicht im Browser).

## Ablauf (ca. 30 min beim ersten Mal, davon ~15 min Download)

Voraussetzung: `make eval` lief schon einmal (liefert `artifacts/detector/detector.onnx`,
`artifacts/report/results.json` und `pages.csv`).

### 1. imajev-Server starten (eigenes Terminal, eigene venv – nicht im docval-Container)

Braucht eine NVIDIA-GPU mit ≥ 12 GB (bf16) oder einen Mac mit Apple Silicon. Auf der CPU
läuft es auch, aber mit mehreren Sekunden pro Seite.

```bash
git clone https://github.com/mohit67890/imajev && cd imajev
python3.11 -m venv .venv && . .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e ".[serve,torch]"                          # Mac: ".[serve,mlx]"
python scripts/download_model.py --model 4b              # Qwen3.5-4B, ~9 GB
hf download mohit67890/imajev-4b --local-dir adapters/imajev-4b
PYTHONPATH=src:scripts python scripts/playground/server.py --backend torch \
  --model-bundle artifacts/model-qwen4b.json --adapter adapters/imajev-4b \
  --model-name imajev-4b --host 0.0.0.0 --port 8765
```

Windows/PowerShell: statt `PYTHONPATH=src:scripts python …` erst `$env:PYTHONPATH="src;scripts"`, dann
`python scripts/playground/server.py …`. Mac: `--adapter adapters/imajev-4b/mlx`, ohne `--backend torch`.

Bewusst **ohne** `--calibration` (laut Modellkarte macht die Kalibrierung reine Foto-Fragen
schlechter) und ohne `--rotations` (für Ja/Nein-Fragen ohne Wirkung). Bereit, wenn
http://127.0.0.1:8765/ die Playground-Seite zeigt.

### 2. Vergleich laufen lassen (im docval-Container / docval-venv)

```bash
make vlm-compare LIMIT=10      # erster Versuch: 10 Seiten
make vlm-compare               # alle Testseiten (CMR + Lieferschein)
```

Läuft docval im Devcontainer und der Server auf dem Windows-Host:
`IMAJEV_URL=http://host.containers.internal:8765/v1/systemone make vlm-compare`
(Docker: `host.docker.internal`).

Antworten werden in `artifacts/vlm_compare/cache/` gespeichert – ein zweiter Lauf fragt nur
neue Seiten. Nach geänderten Fragen in `config.yaml` wird automatisch neu gefragt.

### 3. Ergebnis lesen

`artifacts/vlm_compare/report.md`:

1. **Kurzfazit** – AUC je Klasse und Ansicht, imajev vs. RF-DETR, mit Urteil
   (besser / gleichauf / zu wenige Seiten).
2. **Details** – Recall, Precision, Fehlalarme, Übersehene, Anteil automatisch entschieden.
3. **Entscheidung je Seite (CMR)** – dieselben vier Töpfe wie im Eval-Report
   (automatisch richtig / Person / Fehler übersehen / Fehlalarm) + Liste der Seiten, auf denen
   beide verschieden entscheiden.

`artifacts/vlm_compare/pages.csv` – jede Seite × Ansicht × Klasse mit imajev-P und RF-DETR-Score.

## Was verglichen wird – und was nicht

- imajev gibt **keine Boxen**, nur P(ja) je Frage. Verglichen wird auf Seitenebene; RF-DETR zählt
  mit seinem höchsten Score der Klasse.
- Zwei **Ansichten** (`vlm_compare.views`): ganze Seite und Unterschriftsbereich (untere 40 %).
  Der Server verkleinert jedes Bild auf ≤ 0,4 Megapixel – auf einer ganzen A4-Seite ist eine
  Unterschrift dann nur wenige Pixel hoch. Der Ausschnitt zeigt, ob das der Engpass ist.
- **Position** (Feld 22/23/24, Feld 13) prüft imajev nicht. Für die CMR-Entscheidung zählt GT
  `falsche_position` deshalb für beide Modelle als „nicht ok“.
- Fragen sind englisch (Modellgrenze) und stehen in `config.yaml` unter `vlm_compare.questions`.

## Entscheidungshilfe

- imajev-AUC deutlich höher (≥ 0,02) **und** weniger „Fehler übersehen“ → weiter prüfen
  (mehr Seiten, Fragen schärfen, Latenz/Hardware klären).
- Gleichauf oder schlechter → RF-DETR behalten: läuft im Browser, schneller (Laufzeit steht im Report), liefert
  Boxen für die Positionsprüfung.
- Weniger als 10 Seiten mit bzw. ohne Objekt → keine Aussage möglich, mehr Testdaten nötig.
