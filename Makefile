# docval - Make targets (details: README.md)
PY ?= python
CONFIG ?= config.yaml
SMOKE_CONFIG := configs/smoke.yaml
export PYTHONPATH := $(CURDIR)/src
DOCVAL := $(PY) -m docval --config

.PHONY: train-final process finalize label-scans relabel-model create_pdf help inspect split train export eval report review-labels relabel compare compare-labels vlm-compare test smoke fetch-models all clean-smoke gpu-check

help:
	@echo "inspect  Schritt 0: Datensatz analysieren, Label-Vorlagen + Review-Seite"
	@echo "split    train/valid/test (gruppiert, stratifiziert) im RF-DETR-Format"
	@echo "train    RF-DETR + Dokumenttyp-Klassifikator trainieren"
	@echo "export   Detektor nach ONNX + Paritätstest PyTorch vs. ONNX Runtime"
	@echo "train-final  Produktionsmodell auf allen gelabelten Seiten (nach make eval), make process nutzt es"
	@echo "eval     alle Stufen mit ONNX auswerten, Report; Exit != 0 bei verfehltem Kriterium"
	@echo "report   Report aus letzter results.json neu rendern"
	@echo "create_pdf  Präsentation (PDF) zum aktuellen Stand aus dem letzten make eval"
	@echo "review-labels  Label-Prüfung: Detektor vs. Labels auf allen Splits, cmr_count-Stapel je Tour"
	@echo "relabel-model  Vorlage-Modell aus den vollständig gelabelten Touren (neue Klassen), danach make relabel"
	@echo "relabel  Vorlabels: Labels + Modellergebnisse je Export als COCO (+ Bilder, zip) zum Überarbeiten"
	@echo "compare  zwei Läufe vergleichen: make compare A=artifacts B=artifacts/exp_x"
	@echo "compare-labels  alte vs. neue Labels einer Tour als HTML: make compare-labels EXPORT=425_21.09.2026 [OLD=datei]"
	@echo "vlm-compare  Prototyp: imajev-4b vs. RF-DETR (Unterschrift/Stempel), Server siehe docs/VLM_VERGLEICH.md [LIMIT=10] [VIEWS=unten]"
	@echo "process  eine gescannte Tour: make process SCANS=<pdf|ordner> [TOUR=503_01.09.2026] -> Prüfseite"
	@echo "label-scans  gescannte Tour als Label-Export mit Editor (neue Klassen labeln): make label-scans RUN=<name>"
	@echo "finalize nach der Prüfung: make finalize RUN=<name> [DECISION=datei] [FORCE=1] -> PDFs, Mails, Protokoll"
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

train-final:
	$(DOCVAL) $(CONFIG) train-final

SPLIT ?= test
eval:
	$(DOCVAL) $(CONFIG) eval --split $(SPLIT)

report:
	$(DOCVAL) $(CONFIG) report

create_pdf:
	$(DOCVAL) $(CONFIG) presentation

REVIEW_SPLIT ?= all
review-labels:
	$(DOCVAL) $(CONFIG) review-labels --split $(REVIEW_SPLIT)

relabel:
	$(DOCVAL) $(CONFIG) relabel

relabel-model:
	$(DOCVAL) $(CONFIG) relabel-model

A ?= artifacts
B ?= $(DOCVAL_ARTIFACTS)
compare:
	$(PY) scripts/compare_runs.py $(A) $(B)

EXPORT ?=
OLD ?=
compare-labels:
	$(DOCVAL) $(CONFIG) compare-labels --export "$(EXPORT)" $(if $(OLD),--old "$(OLD)",)

LIMIT ?=
VIEWS ?=
vlm-compare:
	$(DOCVAL) $(CONFIG) vlm-compare $(if $(LIMIT),--limit $(LIMIT),) $(if $(VIEWS),--views $(VIEWS),)

SCANS ?=
TOUR ?=
RUN ?=
DECISION ?=
FORCE ?=
process:
	$(DOCVAL) $(CONFIG) process --input "$(SCANS)" $(if $(TOUR),--tour "$(TOUR)",) $(if $(RUN),--run "$(RUN)",)

finalize:
	$(DOCVAL) $(CONFIG) finalize --run "$(RUN)" $(if $(DECISION),--decision "$(DECISION)",) $(if $(FORCE),--force,)

label-scans:
	$(DOCVAL) $(CONFIG) label-scans --run "$(RUN)"

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
	$(DOCVAL) $(SMOKE_CONFIG) review-labels && \
	$(DOCVAL) $(SMOKE_CONFIG) relabel && \
	$(DOCVAL) $(SMOKE_CONFIG) presentation && \
	$(DOCVAL) $(SMOKE_CONFIG) process --input artifacts/smoke/data/images --tour 503_01.09.2026 || exit 1; \
	end=$$(date +%s); echo "[smoke] OK in $$((end-start)) s"; \
	if [ $$((end-start)) -gt 300 ]; then echo "[smoke] WARNUNG: länger als 5 Minuten"; exit 4; fi

clean-smoke:
	rm -rf artifacts/smoke
