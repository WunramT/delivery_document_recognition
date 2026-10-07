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

### 1. imajev-Server starten (zweites Terminal)

Braucht eine NVIDIA-GPU mit ≥ 12 GB (bf16) oder einen Mac mit Apple Silicon. Auf der CPU
läuft es auch, aber mit mehreren Sekunden pro Seite und ~16 GB RAM.

**Variante A: im GPU-Devcontainer `docval (GPU, NVIDIA)` (empfohlen)**

Der Container hat schon alles Schwere: Python 3.11, torch 2.14 (CUDA 12.6), transformers,
peft, accelerate. Die venv nutzt diese Pakete mit (`--system-site-packages`) und ergänzt nur
den Server (fastapi, uvicorn); die docval-Pakete bleiben unverändert. Alles liegt im
Volume `/models` und übersteht ein „Rebuild Container“. Im Container-Terminal:

```bash
cd /models && git clone https://github.com/mohit67890/imajev && cd imajev
python -m venv --system-site-packages .venv && . .venv/bin/activate
pip install -e ".[serve,torch]"                          # lädt nur fastapi/uvicorn/multipart nach
python scripts/download_model.py --model 4b              # Qwen3.5-4B, ~9 GB nach /models/imajev/.cache
hf download mohit67890/imajev-4b --local-dir adapters/imajev-4b
PYTHONPATH=src:scripts python scripts/playground/server.py --backend torch \
  --model-bundle artifacts/model-qwen4b.json --adapter adapters/imajev-4b \
  --model-name imajev-4b --port 8765
```

**Nach dem Start gibt der Server nichts mehr aus – er hängt nicht, er wartet auf Anfragen.**
Fertig geladen ist er, sobald die Zeile `backend=torch model=imajev-4b … load_seconds=…` erscheint.
Terminal offen lassen und `make vlm-compare` in einem **zweiten** Terminal starten.

Wichtig: nach `/models` klonen (Docker-Volume, schnell), **nicht** nach `/workspace/models`.
`/workspace` ist der Windows-Ordner, durchgereicht per Bind-Mount: dort dauert das Laden der
9 GB eine Viertelstunde statt ~1 Minute.

Server und `make vlm-compare` laufen im selben Container → die Standard-URL
`http://127.0.0.1:8765` passt, `IMAJEV_URL` ist nicht nötig. Ab dem zweiten Mal reichen die
Zeilen `cd /models/imajev`, `. .venv/bin/activate` und der Server-Befehl.

Falls der Server beim Laden mit einem transformers-Fehler abbricht (der Container hat
transformers 5.17, imajev ist mit 4.55+ getestet): `pip install "transformers<5"` – das
installiert nur in die venv, docval bleibt unberührt.

Im CPU-Devcontainer genauso, nur langsam; der Podman-Maschine dann ≥ 16 GB RAM geben
(`podman machine set --memory 16384`).

**Variante B: außerhalb des Containers (eigene venv auf dem Rechner)**

```bash
git clone https://github.com/mohit67890/imajev && cd imajev
python3.11 -m venv .venv && . .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e ".[serve,torch]"                          # Mac: ".[serve,mlx]"
python scripts/download_model.py --model 4b
hf download mohit67890/imajev-4b --local-dir adapters/imajev-4b
PYTHONPATH=src:scripts python scripts/playground/server.py --backend torch \
  --model-bundle artifacts/model-qwen4b.json --adapter adapters/imajev-4b \
  --model-name imajev-4b --host 0.0.0.0 --port 8765
```

Windows/PowerShell: statt `PYTHONPATH=src:scripts python …` erst `$env:PYTHONPATH="src;scripts"`, dann
`python scripts/playground/server.py …`. Mac: `--adapter adapters/imajev-4b/mlx`, ohne `--backend torch`.
Läuft docval dabei im Devcontainer:
`IMAJEV_URL=http://host.containers.internal:8765/v1/systemone make vlm-compare`
(Docker: `host.docker.internal`).

Bewusst **ohne** `--calibration` (laut Modellkarte macht die Kalibrierung reine Foto-Fragen
schlechter) und ohne `--rotations` (für Ja/Nein-Fragen ohne Wirkung). Bereit, wenn der
Server keine Fehler mehr ausgibt; Test (curl fehlt im Container):
`python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8765/v1/models').read())"`.

### Langsam? GPU-Speicher prüfen

imajev-4b braucht in bf16 ~9 GB GPU-Speicher. Auf einer GPU mit 8 GB (z. B. RTX 2000 Ada
Laptop) lagert der Windows-Treiber den Rest in den normalen Arbeitsspeicher aus: das Modell
läuft dann zwar, aber **~3 min pro Anfrage** statt ~1 s (Server-Log: `total_ms=171707`).
Die Hinweise `causal_conv1d` / `flash-linear-attention` im Log sind dagegen harmlos.

Zwei Wege:

- **imajev-4b über Nacht laufen lassen**, nur mit dem Ausschnitt (halbiert die Anfragen):
  `make vlm-compare VIEWS=unten`. Eine Seite ≈ 3 min, 20 Seiten ≈ 1 h. Abbrechen ist sicher:
  der Cache behält jede fertige Antwort, der nächste Lauf macht dort weiter.
- **imajev-2b** (passt in 8 GB, schnell, aber schwächer und eine Generation älter): ist
  2B schon so gut wie RF-DETR, ist die Frage beantwortet; ist 2B schlechter, sagt das über 4B
  noch nichts.

  ```bash
  cd /models/imajev && . .venv/bin/activate
  python scripts/download_model.py --model 2b              # -> artifacts/model.json, ~4.5 GB
  hf download mohit67890/imajev-2b --local-dir adapters/imajev-2b
  PYTHONPATH=src:scripts python scripts/playground/server.py --backend torch \
    --model-bundle artifacts/model.json --adapter adapters/imajev-2b \
    --model-name imajev-2b --port 8765
  ```

  Der Report zeigt im Titel, welches Modell geantwortet hat. Vor dem Wechsel des Modells
  `artifacts/vlm_compare/cache/` umbenennen, sonst mischen sich die Antworten.

### 2. Vergleich laufen lassen (im docval-Container / docval-venv)

```bash
make vlm-compare LIMIT=10      # erster Versuch: 10 Seiten
make vlm-compare               # alle Testseiten (CMR + Lieferschein)
make vlm-compare VIEWS=unten   # nur der Unterschriftsbereich (halb so viele Anfragen)
```

Antworten werden in `artifacts/vlm_compare/cache/` gespeichert – ein zweiter Lauf fragt nur
neue Seiten. Nach geänderten Fragen in `config.yaml` wird automatisch neu gefragt.

Dauer: je Testseite 1 Original (2 Fragen) + bis zu 2 Negative (je 1 Frage). Mit 8-GB-GPU
und `VIEWS=unten` grob 2–3 min pro Seite – über Nacht laufen lassen.

### 3. Ergebnis lesen

`artifacts/vlm_compare/report.md`:

1. **Recall bei Precision 100 %** – Hauptergebnis: wie viele echte Unterschriften/Stempel
   erkennt jedes Modell ohne einen einzigen Fehlalarm? Negative = Seiten ohne Objekt + Kopien
   jeder Testseite mit übermalten Label-Boxen einer Klasse (`artifacts/vlm_compare/negative/`).
   Die Seite, die die Schwelle setzt („härtestes Negativ“), ansehen: ist dort doch eine
   ungelabelte Unterschrift, ist das Label falsch, nicht das Modell.
2. **Kurzfazit** – AUC je Klasse und Ansicht, imajev vs. RF-DETR, mit Urteil
   (besser / gleichauf / zu wenige Seiten).
3. **Details** – Recall, Precision, Fehlalarme, Übersehene, Anteil automatisch entschieden.
4. **Entscheidung je Seite (CMR)** – dieselben vier Töpfe wie im Eval-Report
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
