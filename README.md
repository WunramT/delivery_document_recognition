# Dokumentvalidierung – lokale Test- und Evaluationsumgebung

Prüft gescannte Versanddokumente (Loading List, Lieferschein, CMR): Dokumenttyp,
Unterschrift/Stempel in den Soll-Zonen, Tournummer per OCR.

> Stand: **Schritt 0 (Datensatz-Inspektion)**. Devcontainer, Split, Training,
> Export, Evaluation und der vollständige Make-Umfang folgen in den nächsten Schritten.

## Eingabedaten

- `/data/coco.json` und `/data/images/` werden **read-only** gemountet und nie verändert.
- Alles Abgeleitete landet in `artifacts/` (gitignored).
- Pfade stehen in `config.yaml` unter `paths`.

## Schritt 0: `make inspect`

```bash
pip install -r requirements.txt
make inspect                                   # nutzt paths.* aus config.yaml
python3 scripts/inspect_dataset.py --coco pfad/coco.json --images pfad/bilder   # ohne Container
```

Ergebnis:

| Datei | Inhalt |
|---|---|
| `artifacts/inspect/inspect.md` | Zusammenfassung: Klassen, Boxgrößen, Auflösungen, Validierungsfehler, Herkunft Dokumenttyp, Tournummer-GT, Gruppierbarkeit |
| `artifacts/inspect/inspect.json` | dieselben Befunde maschinenlesbar |
| `artifacts/inspect/tour_crops/` | Crops aller `tour_nummer`-Boxen (12 % Rand) |
| `labels/doc_types.csv` | Vorlage `file_name,doc_type`, nur wenn der Dokumenttyp nicht im Datensatz steckt |
| `labels/tour_numbers.csv` | Vorlage `file_name,tour_number`, nur wenn der Tournummer-Text fehlt |
| `labels/tour_review.html` | Review-Seite: Crop + Eingabefeld je Bild |

Bestehende CSVs werden **nie überschrieben**, nur um neue Dateinamen ergänzt.

### Label-CSVs ausfüllen

- `labels/doc_types.csv`: Spalte `doc_type` mit einem Wert aus `doc_types` in `config.yaml`
  (`cmr`, `lieferschein`, `loading_list`).
- `labels/tour_numbers.csv`: am einfachsten über `labels/tour_review.html` im Browser
  (Datei direkt öffnen). Enter springt zum nächsten Feld, Eingaben werden lokal
  zwischengespeichert, „herunterladen“ erzeugt die CSV, die nach `labels/` kopiert wird.
  Unleserlich: `?` eintragen. Mehrere Boxen auf einer Seite: Werte mit `;` trennen.
- Welche Quelle die Pipeline nutzt, steht in `config.yaml` unter `labels.doc_type.source`
  bzw. `labels.tour_number.source` (`csv` oder `coco_attribute`, beim Dokumenttyp auch
  `filename`/`folder`/`coco_category`).

## Tests

```bash
make test
```
