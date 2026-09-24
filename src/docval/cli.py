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
    out = artifacts(cfg, "splits", "detector")
    winfo = write_rfdetr_dataset(pages, assign, classes, out)
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


def cmd_export(cfg) -> int:
    from .detect.train import export, parity

    run = artifacts(cfg, "detector", "run")
    out = artifacts(cfg, "detector")
    classes = json.loads((artifacts(cfg, "splits", "detector") / "classes.json").read_text())
    export(cfg, run, out, classes, log)
    test_dir = artifacts(cfg, "splits", "detector", "test")
    imgs = sorted(p for p in test_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    n = cfg["detector"]["parity"]["n_images"]
    if len(imgs) < n:  # fewer test images than requested: fill up from valid/train
        for s in ("valid", "train"):
            d = artifacts(cfg, "splits", "detector", s)
            imgs += sorted(p for p in d.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    res = parity(cfg, run, out, imgs[:n], log)
    (out / "parity.json").write_text(dumps(res), encoding="utf-8")
    return 0 if res["passed"] else 3


def cmd_eval(cfg) -> int:
    from .eval.run import run_eval

    return run_eval(cfg, log)


def cmd_report(cfg) -> int:
    from .eval.report import render_from_results

    return render_from_results(cfg, log)


def cmd_fetch(cfg) -> int:
    from .models import fetch_all

    fetch_all(cfg, log)
    return 0


COMMANDS = {"split": cmd_split, "train": cmd_train, "train-doctype": cmd_train_doctype,
            "export": cmd_export, "eval": cmd_eval, "report": cmd_report, "fetch-models": cmd_fetch}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docval")
    ap.add_argument("command", choices=sorted(COMMANDS))
    ap.add_argument("--config", default=None, help="default: $DOCVAL_CONFIG or config.yaml")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    cfg = load_config(args.config)
    if args.command != "fetch-models" and not os.environ.get("DOCVAL_ONLINE"):
        from .models import offline, setup_cache
        setup_cache(cfg)
        offline()  # after `make fetch-models` everything runs from the local cache
    t0 = time.time()
    rc = COMMANDS[args.command](cfg)
    log(f"[{args.command}] {time.time() - t0:.1f} s, exit {rc}")
    return rc
