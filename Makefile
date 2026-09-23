PY ?= python3
CONFIG ?= config.yaml

.PHONY: inspect test

## Schritt 0: Datensatz analysieren, Label-Vorlagen + Review-Seite erzeugen
inspect:
	$(PY) scripts/inspect_dataset.py --config $(CONFIG)

test:
	$(PY) -m pytest -q tests
