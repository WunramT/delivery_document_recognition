import subprocess
import sys
from pathlib import Path

import yaml

from docval.config import load_config
from docval.data.dataset import load_pages
from docval.data.exports import apply_exports

ROOT = Path(__file__).resolve().parents[1]


def make_export(path: Path, n: int, seed: int):
    subprocess.run([sys.executable, str(ROOT / "scripts/make_smoke_dataset.py"), "--out", str(path),
                    "--n", str(n), "--seed", str(seed)], check=True, capture_output=True)


def test_two_exports_are_merged(tmp_path):
    exp = tmp_path / "exports"
    make_export(exp / "2026-09-07", 4, 1)
    make_export(exp / "2026-09-15", 3, 2)   # same file names as the first export
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump({"extends": str(ROOT / "config.yaml"),
                                        "paths": {"exports": str(exp), "artifacts": str(tmp_path / "art")},
                                        "labels": {"tour_number": {"csv": str(tmp_path / "none.csv")}}}))
    cfg = apply_exports(load_config(cfg_path))
    info = cfg["_exports"]
    assert [e["images"] for e in info["exports"]] == [4, 3]
    pages, _ = load_pages(cfg)
    assert len(pages) == 7
    assert len({p.file_name for p in pages}) == 7                  # no name collisions
    assert all(p.path is not None and p.path.is_file() for p in pages)
    assert all(p.doc_type for p in pages)
    assert all(p.tour_number for p in pages)                     # from the per-export CSVs
    assert {p.source_pdf.split(":")[0] for p in pages} == {"2026-09-07", "2026-09-15"}
    assert sum(len(p.boxes) for p in pages) > 0


def test_no_exports_folder_keeps_config(tmp_path):
    cfg = load_config()
    cfg["paths"]["exports"] = str(tmp_path / "missing")
    before = dict(cfg["paths"])
    assert apply_exports(cfg)["paths"] == before


def test_global_tour_csv_does_not_match_other_exports_by_stem(tmp_path):
    exp = tmp_path / "exports"
    make_export(exp / "a", 2, 1)
    make_export(exp / "b", 2, 2)
    for e in ("a", "b"):  # no per-export tour numbers
        (exp / e / "tour_numbers.csv").unlink()
    glob = tmp_path / "tour_numbers.csv"   # old global CSV with names of ONE export, no prefix
    glob.write_text("file_name,tour_number\nimages/smoke_0001.png,111/01.01.2026/1\n")
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump({"extends": str(ROOT / "config.yaml"),
                                        "paths": {"exports": str(exp), "artifacts": str(tmp_path / "art")},
                                        "labels": {"tour_number": {"csv": str(glob)}}}))
    pages, _ = load_pages(apply_exports(load_config(cfg_path)))
    assert all(p.tour_number is None for p in pages)  # ambiguous -> not assigned at all


def test_exports_directly_under_labels_with_tour_from_folder_name(tmp_path):
    labels = tmp_path / "labels"
    make_export(labels / "425_21.09.2026", 3, 1)
    make_export(labels / "exports" / "503_01.09.2026", 2, 2)   # nested layout still works
    for d in (labels / "425_21.09.2026", labels / "exports" / "503_01.09.2026"):
        (d / "tour_numbers.csv").unlink()                        # tour only from the folder name
    (labels / "page_types.csv").write_text("x")                  # loose files in labels/ are ignored
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump({"extends": str(ROOT / "config.yaml"),
                                        "paths": {"exports": str(labels), "artifacts": str(tmp_path / "art")},
                                        "labels": {"tour_number": {"csv": str(tmp_path / "none.csv")}}}))
    cfg = apply_exports(load_config(cfg_path))
    assert [e["name"] for e in cfg["_exports"]["exports"]] == ["425_21.09.2026", "503_01.09.2026"]
    pages, _ = load_pages(cfg)
    assert all(p.path is not None for p in pages)
    by_export = {}
    for p in pages:
        by_export.setdefault(p.file_name.split("/images/")[0], set()).add(p.tour_number)
    assert by_export == {"425_21.09.2026": {"425/21.09.2026/4000"},
                         "exports/503_01.09.2026": {"503/01.09.2026/4000"}}


def test_same_images_in_two_exports_are_reported(tmp_path):
    import shutil

    exp = tmp_path / "exports"
    make_export(exp / "652_15.09.2026", 3, 1)
    make_export(exp / "609_17.09.2026", 3, 2)
    shutil.copytree(exp / "652_15.09.2026", exp / "FT")     # same batch exported twice
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump({"extends": str(ROOT / "config.yaml"),
                                        "paths": {"exports": str(exp), "artifacts": str(tmp_path / "art")}}))
    dups = apply_exports(load_config(cfg_path))["_exports"]["image_duplicates"]
    assert {tuple(sorted(d[2:])) for d in dups} == {("652_15.09.2026", "FT")}
    assert len(dups) == 3
