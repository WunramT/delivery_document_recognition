import csv
import json
import subprocess
import sys
from pathlib import Path

from docval.data import dataset_info as di
from docval.data.labels import write_template

ROOT = Path(__file__).resolve().parents[1]
KW = {"cmr": ["cmr"], "lieferschein": ["lieferschein", "ls"], "loading_list": ["loading"]}


def test_base_stem_strips_roboflow_suffix():
    assert di.base_stem("a/CMR_1_p2_jpg.rf.0123456789abcdef0123.jpg") == "CMR_1_p2"
    assert di.base_stem("x/scan.tif") == "scan"


def test_page_suffix():
    assert di.split_page_suffix("CMR_4711_p2") == ("CMR_4711", 2)
    assert di.split_page_suffix("lieferschein_0815-1") == ("lieferschein_0815", 1)
    # timestamps are not split into prefix + page
    assert di.split_page_suffix("scan_20240501_123456")[1] is None


def test_doc_type_guess_short_keywords_need_token():
    assert di.guess_doc_type_from_name("details_2024", KW) == []
    assert di.guess_doc_type_from_name("LS_2024", KW) == ["lieferschein"]
    assert di.guess_doc_type_from_name("Loading-List 3", KW) == ["loading_list"]


def test_shape_and_percentiles():
    assert di.shape_of("AB-12") == "AA-99"
    p = di.percentiles([1, 2, 3, 4, 5], (0, 50, 100))
    assert p == {"p0": 1, "p50": 3, "p100": 5}


def test_doc_type_attribute_detected():
    data = {"images": [{"id": 1, "file_name": "a.jpg", "extra": {"doc_type": "cmr"}},
                       {"id": 2, "file_name": "b.jpg", "extra": {"doc_type": "lieferschein"}}],
            "annotations": [], "categories": []}
    r = di.analyze_doc_type_sources(data, ["cmr", "lieferschein"], KW)
    assert r["source"] == {"kind": "coco_attribute", "key": "extra.doc_type"}


def test_template_never_overwrites(tmp_path):
    p = tmp_path / "t.csv"
    assert write_template(p, ["file_name", "doc_type"], ["a", "b"]) == "created"
    rows = list(csv.reader(open(p)))
    rows[1][1] = "cmr"
    csv.writer(open(p, "w", newline="")).writerows(rows)
    assert write_template(p, ["file_name", "doc_type"], ["a", "b", "c"]) == "extended"
    rows = list(csv.DictReader(open(p)))
    assert [r["file_name"] for r in rows] == ["a", "b", "c"]
    assert rows[0]["doc_type"] == "cmr"


def test_inspect_script_end_to_end(tiny_coco, tmp_path):
    path, img_dir = tiny_coco
    out, labels = tmp_path / "out", tmp_path / "labels"
    before = {p.name: p.stat().st_mtime for p in img_dir.iterdir()}
    r = subprocess.run([sys.executable, str(ROOT / "scripts/inspect_dataset.py"),
                        "--coco", str(path), "--images", str(img_dir),
                        "--out", str(out), "--labels", str(labels)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads((out / "inspect.json").read_text())
    assert rep["doc_type"]["source"]["kind"] == "missing"
    assert rep["tour_text"]["source"]["kind"] == "missing"  # only 1 of 2 boxes has text
    assert rep["tour_text"]["text_candidates"][0]["key"] == "attributes.text"
    assert rep["grouping"]["same_source_stem"]["n_stems"] == 0
    assert rep["grouping"]["filename_page_groups"]["n_multi_page_groups"] == 1
    assert (labels / "doc_types.csv").is_file()
    assert (labels / "tour_numbers.csv").is_file()
    assert "tour_numbers.csv" in (labels / "tour_review.html").read_text()
    assert len(list((out / "tour_crops").glob("*.png"))) == 2
    # inputs untouched
    assert before == {p.name: p.stat().st_mtime for p in img_dir.iterdir()}


def test_tour_template_prefilled_from_partial_gt(tiny_coco, tmp_path):
    path, img_dir = tiny_coco
    labels = tmp_path / "labels"
    subprocess.run([sys.executable, str(ROOT / "scripts/inspect_dataset.py"), "--no-hash",
                    "--coco", str(path), "--images", str(img_dir),
                    "--out", str(tmp_path / "out"), "--labels", str(labels)], check=True,
                   capture_output=True)
    rows = {r["file_name"]: r["tour_number"] for r in csv.DictReader(open(labels / "tour_numbers.csv"))}
    assert rows["CMR_4711_p1_jpg.rf.0123456789abcdef0123456789abcdef.jpg"] == "1234567"
    assert rows["loading_list_77.jpg"] == ""
