"""Command line entry: python -m docval <command>. See Makefile / README."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .config import artifacts, load_config
from .jsonutil import dumps


def log(msg: str) -> None:
    print(msg, flush=True)


def cmd_split(cfg) -> int:
    from .data.dataset import load_pages
    from .data.export_split import write_rfdetr_dataset
    from .data.split import assign_groups, grouped_stratified_split, split_summary

    pages, info = load_pages(cfg)
    ginfo = assign_groups(pages, cfg["split"])
    assign = grouped_stratified_split(pages, cfg["split"]["ratios"], cfg["seed"])
    summary = split_summary(pages, assign)
    classes = info["classes_in_coco"]
    # a class labeled in some exports only: in the others its objects are unlabeled and
    # would be learned as background -> left out until every export is labeled (make relabel)
    from .data.coverage import labeled_classes, partial_classes
    partial = partial_classes(labeled_classes(cfg), classes)
    if partial and cfg["split"].get("partial_classes", "exclude") == "exclude":
        classes = [c for c in classes if c not in partial]
        for c, missing in partial.items():
            log(f"[split] Klasse {c} weggelassen: in {len(missing)} Export(s) noch nicht gelabelt "
                f"({', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}) - erst `make relabel-model relabel`, "
                "dort nachlabeln (split.partial_classes: keep trainiert sie trotzdem)")
    out = artifacts(cfg, "splits", "detector")
    winfo = write_rfdetr_dataset(pages, assign, classes, out, cfg.get("form_mask"))
    manifest = {
        "seed": cfg["seed"], "grouping": ginfo, "summary": summary, "dataset": info, "written": winfo,
        "pages": [{"file_name": p.file_name, "split": assign[p.file_name], "group": p.group,
                   "doc_type": p.doc_type, "source_page": p.source_page} for p in pages],
    }
    (artifacts(cfg, "splits") / "split.json").write_text(dumps(manifest), encoding="utf-8")
    for s in ("train", "valid", "test"):
        d = summary.get(s, {"pages": 0, "groups": 0, "by_type": {}})
        log(f"[split] {s:5s}: {d['pages']:3d} Seiten, {d['groups']:2d} Gruppen, {d['by_type']}")
    log(f"[split] Gruppierung {ginfo['mode']}: {ginfo['n_groups']} Gruppen, "
        f"einzeln verteilt: {ginfo['ungrouped_pages']} ({', '.join(ginfo['ungrouped_doc_types']) or '-'}); "
        f"Leck-Gruppen: {summary['_leaking_groups'] or 'keine'}")
    fm = winfo["form_mask"]
    if fm["pages"]:
        log(f"[split] Vordruck-Maske: Feldzeile auf {fm['found']}/{fm['pages']} Seiten gefunden, "
            f"GT-Boxen im maskierten Bereich verworfen: {fm['dropped_boxes']}"
            + (f"; nicht gefunden: {', '.join(fm['not_found'][:5])}" if fm["not_found"] else ""))
    log(f"[split] Boxen gekappt: {info['clipped_boxes']}, verworfen: {info['dropped_boxes']}, "
        f"Klassen ohne Annotationen: {info['classes_missing'] or '-'} -> {out}")
    return 0


def cmd_train(cfg) -> int:
    from .detect.train import train

    train(cfg, artifacts(cfg, "splits", "detector"), artifacts(cfg, "detector", "run"), log)
    if cfg["doctype"]["classifier"].get("enabled"):
        cmd_train_doctype(cfg)
    return 0


def cmd_train_doctype(cfg) -> int:
    from .data.dataset import load_pages
    from .doctype.classifier import train as train_clf
    from .models import setup_cache

    setup_cache(cfg)
    pages, _ = load_pages(cfg)
    split = {p["file_name"]: p["split"] for p in
             json.loads((artifacts(cfg, "splits") / "split.json").read_text())["pages"]}
    c = dict(cfg["doctype"]["classifier"], seed=cfg["seed"])
    train_clf([p for p in pages if split.get(p.file_name) == "train"],
              [p for p in pages if split.get(p.file_name) == "valid"],
              cfg["doc_types"], c, artifacts(cfg, "doctype"), log=log)
    return 0


def cmd_export(cfg, name: str = "detector") -> int:
    """name: detector (evaluated model) or detector_final (make train-final)."""
    from .detect.train import export, parity

    run = artifacts(cfg, name, "run")
    out = artifacts(cfg, name)
    split_dir = artifacts(cfg, "splits", name)
    classes = json.loads((split_dir / "classes.json").read_text())
    export(cfg, run, out, classes, log)
    imgs = sorted(p for p in (split_dir / "test").iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    n = cfg["detector"]["parity"]["n_images"]
    if len(imgs) < n:  # fewer test images than requested: fill up from valid/train
        for s in ("valid", "train"):
            imgs += sorted(p for p in (split_dir / s).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    res = parity(cfg, run, out, imgs[:n], log)
    (out / "parity.json").write_text(dumps(res), encoding="utf-8")
    return 0 if res["passed"] else 3


def cmd_train_final(cfg) -> int:
    """Production model: same settings, trained on every labeled page (train + valid + test of the
    last make split) -> artifacts/detector_final/detector.onnx, used by make process. Its quality is
    the one make eval measured on the evaluated model; thresholds and zones stay from make eval."""
    from .data.export_split import write_final_dataset
    from .detect.train import train

    src = artifacts(cfg, "splits", "detector")
    if not (src / "classes.json").is_file():
        log("FEHLER: kein Split - zuerst make split train export eval")
        return 2
    if not artifacts(cfg, "report", "results.json").is_file():
        log("WARNUNG: noch kein make eval - make process braucht dessen Schwellen und Zonen")
    info = write_final_dataset(src, artifacts(cfg, "splits", "detector_final"))
    log(f"[train-final] Trainingsseiten {info['train_pages']} (train+valid+test: {info['pages']}), "
        f"Boxen {info['train_boxes']}")
    train(cfg, artifacts(cfg, "splits", "detector_final"), artifacts(cfg, "detector_final", "run"), log)
    rc = cmd_export(cfg, "detector_final")
    log(f"[train-final] -> {artifacts(cfg, 'detector_final', 'detector.onnx')} - make process verwendet es "
        "(process.model: auto)")
    return rc


def cmd_eval(cfg) -> int:
    from .eval.run import run_eval

    return run_eval(cfg, log)


def cmd_report(cfg) -> int:
    from .eval.report import render_from_results

    return render_from_results(cfg, log)


def cmd_review_labels(cfg) -> int:
    from .eval.label_review import run_label_review

    return run_label_review(cfg, log)


def cmd_relabel(cfg) -> int:
    from .eval.relabel import run_relabel

    return run_relabel(cfg, log)


def cmd_relabel_model(cfg) -> int:
    from .eval.reference_model import run_reference_train

    return run_reference_train(cfg, log)


def cmd_compare_labels(cfg) -> int:
    from .eval.label_compare import run_label_compare

    a = cfg.get("_args") or {}
    if not a.get("export"):
        log("FEHLER: --export <Tour-Ordner> angeben, z. B. make compare-labels EXPORT=425_21.09.2026")
        return 2
    return run_label_compare(cfg, a["export"], a.get("old"), log)


def cmd_presentation(cfg) -> int:
    from .eval.presentation import run_presentation

    return run_presentation(cfg, log)


def cmd_vlm_compare(cfg) -> int:
    from .eval.vlm_compare import run_vlm_compare

    a = cfg.get("_args") or {}
    if a.get("limit"):
        cfg["vlm_compare"]["limit"] = a["limit"]
    if a.get("views"):
        want = [v.strip() for v in a["views"].split(",") if v.strip()]
        known = cfg["vlm_compare"]["views"]
        bad = [v for v in want if v not in known]
        if bad:
            log(f"FEHLER: unbekannte Ansicht {bad}, vorhanden: {', '.join(known)}")
            return 2
        cfg["vlm_compare"]["views"] = {v: known[v] for v in want}
    return run_vlm_compare(cfg, log)


def cmd_process(cfg) -> int:
    from .process.run import run_process

    a = cfg.get("_args") or {}
    if not a.get("input"):
        log("FEHLER: --input <PDF oder Ordner> angeben, z. B. make process SCANS=scans/503_01.09.2026.pdf")
        return 2
    return run_process(cfg, a["input"], a.get("tour"), a.get("run"), log)


def cmd_review(cfg) -> int:
    from .process.serve import run_review

    a = cfg.get("_args") or {}
    if not a.get("run"):
        log("FEHLER: --run <Name> angeben (Ordner unter artifacts/process/), z. B. make review RUN=503_01.09.2026_4000")
        return 2
    return run_review(cfg, a["run"], a.get("port"), log, not a.get("no_browser"))


def cmd_finalize(cfg) -> int:
    from .process.finalize import run_finalize

    a = cfg.get("_args") or {}
    if not a.get("run"):
        log("FEHLER: --run <Name> angeben (Ordner unter artifacts/process/), z. B. make finalize RUN=503_01.09.2026_4000")
        return 2
    return run_finalize(cfg, a["run"], a.get("decision"), bool(a.get("force")), log)


def cmd_label_scans(cfg) -> int:
    from .process.labels import run_label_scans

    a = cfg.get("_args") or {}
    if not a.get("run"):
        log("FEHLER: --run <Name> angeben (Ordner unter artifacts/process/), z. B. make label-scans RUN=503_01.09.2026_4000")
        return 2
    return run_label_scans(cfg, a["run"], log)


def cmd_fetch(cfg) -> int:
    from .models import fetch_all

    fetch_all(cfg, log)
    return 0


COMMANDS = {"split": cmd_split, "train": cmd_train, "train-final": cmd_train_final, "train-doctype": cmd_train_doctype,
            "export": cmd_export, "eval": cmd_eval, "report": cmd_report, "review-labels": cmd_review_labels, "relabel": cmd_relabel, "relabel-model": cmd_relabel_model, "compare-labels": cmd_compare_labels, "presentation": cmd_presentation, "vlm-compare": cmd_vlm_compare,
            "process": cmd_process, "review": cmd_review, "finalize": cmd_finalize, "label-scans": cmd_label_scans, "fetch-models": cmd_fetch}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docval")
    ap.add_argument("command", choices=sorted(COMMANDS))
    ap.add_argument("--config", default=None, help="default: $DOCVAL_CONFIG or config.yaml")
    ap.add_argument("--split", default=None, help="eval: split to evaluate (test | valid | train); review-labels: also all")
    ap.add_argument("--export", default=None, help="compare-labels: export folder, e.g. 425_21.09.2026")
    ap.add_argument("--old", default=None, help="compare-labels: old COCO file (default: backup or editor state)")
    ap.add_argument("--limit", type=int, default=None, help="vlm-compare: only the first N pages")
    ap.add_argument("--views", default=None, help="vlm-compare: comma-separated views, e.g. unten")
    ap.add_argument("--input", default=None, help="process: scanned PDF, image or folder of one tour")
    ap.add_argument("--tour", default=None, help="process: tour number, e.g. 503/01.09.2026/4000 or 503_01.09.2026")
    ap.add_argument("--run", default=None, help="process: output name; finalize/label-scans: folder under artifacts/process/")
    ap.add_argument("--decision", default=None, help="finalize: decision file (default: <run>/entscheidung.json)")
    ap.add_argument("--force", action="store_true", help="finalize: also with unconfirmed pages / incomplete tour")
    ap.add_argument("--port", type=int, default=None, help="review: port on 127.0.0.1 (default process.review_port)")
    ap.add_argument("--no-browser", action="store_true", help="review: do not open the browser")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    cfg = load_config(args.config)
    from .data.exports import apply_exports
    cfg = apply_exports(cfg, log)
    cfg["_args"] = {"export": args.export, "old": args.old, "limit": args.limit, "views": args.views,
                    "input": args.input, "tour": args.tour, "run": args.run, "decision": args.decision,
                    "force": args.force, "port": args.port, "no_browser": args.no_browser}
    if args.split:
        cfg.setdefault("eval", {})["split"] = args.split
    if args.command != "fetch-models" and not os.environ.get("DOCVAL_ONLINE"):
        from .models import offline, setup_cache
        setup_cache(cfg)
        offline()  # after `make fetch-models` everything runs from the local cache
    t0 = time.time()
    rc = COMMANDS[args.command](cfg)
    log(f"[{args.command}] {time.time() - t0:.1f} s, exit {rc}")
    return rc
