# docval - Make targets (details: README.md)
PY ?= python
CONFIG ?= config.yaml
SMOKE_CONFIG := configs/smoke.yaml
export PYTHONPATH := $(CURDIR)/src
DOCVAL := $(PY) -m docval --config

.PHONY: help inspect split train export eval report test smoke fetch-models all clean-smoke gpu-check

help:
	@echo "inspect  Schritt 0: Datensatz analysieren, Label-Vorlagen + Review-Seite"
	@echo "split    train/valid/test (gruppiert, stratifiziert) im RF-DETR-Format"
	@echo "train    RF-DETR + Dokumenttyp-Klassifikator trainieren"
	@echo "export   Detektor nach ONNX + Paritätstest PyTorch vs. ONNX Runtime"
	@echo "eval     alle Stufen mit ONNX auswerten, Report; Exit != 0 bei verfehltem Kriterium"
	@echo "report   Report aus letzter results.json neu rendern"
	@echo "test     Unit-Tests"
	@echo "smoke    ganze Pipeline auf synthetischer Mini-Teilmenge (CPU, < 5 min)"
	@echo "fetch-models  alle Gewichte in den Cache laden (danach offline)"
	@echo "gpu-check     prüfen, ob PyTorch und ONNX Runtime die GPU sehen"

inspect:
	$(PY) scripts/inspect_dataset.py --config $(CONFIG)

split:
	$(DOCVAL) $(CONFIG) split

train:
	$(DOCVAL) $(CONFIG) train

export:
	$(DOCVAL) $(CONFIG) export

SPLIT ?= test
eval:
	$(DOCVAL) $(CONFIG) eval --split $(SPLIT)

report:
	$(DOCVAL) $(CONFIG) report

fetch-models:
	$(DOCVAL) $(CONFIG) fetch-models

all: split train export eval

gpu-check:
	@$(PY) -c "import torch; ok = torch.cuda.is_available(); print('torch', torch.__version__, '| CUDA verfügbar:', ok, '|', torch.cuda.get_device_name(0) if ok else 'keine GPU - Training läuft auf der CPU')"

test:
	$(PY) -m pytest -q tests

smoke:
	@start=$$(date +%s); \
	$(PY) scripts/make_smoke_dataset.py --n 12 && \
	$(DOCVAL) $(SMOKE_CONFIG) split && \
	$(DOCVAL) $(SMOKE_CONFIG) train && \
	$(DOCVAL) $(SMOKE_CONFIG) export && \
	$(DOCVAL) $(SMOKE_CONFIG) eval && \
	end=$$(date +%s); echo "[smoke] OK in $$((end-start)) s"; \
	if [ $$((end-start)) -gt 300 ]; then echo "[smoke] WARNUNG: länger als 5 Minuten"; exit 4; fi

clean-smoke:
	rm -rf artifacts/smoke
