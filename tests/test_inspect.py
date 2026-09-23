import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml

from docval.data import dataset_info as di
from docval.data.labels import match_to_coco, read_label_table, write_template

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


def isolated_config(tmp_path, doc_csv=None):
    """Repo config, but label CSVs point into tmp_path (never the real labels/)."""
    cfg = yaml.safe_load(open(ROOT / "config.yaml"))
    cfg["labels"]["doc_type"]["csv"] = str(doc_csv or tmp_path / "no_page_types.csv")
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return str(p)


def run_inspect(tmp_path, coco, images, doc_csv=None, *extra):
    return subprocess.run([sys.executable, str(ROOT / "scripts/inspect_dataset.py"),
                           "--config", isolated_config(tmp_path, doc_csv),
                           "--coco", str(coco), "--images", str(images),
                           "--out", str(tmp_path / "out"), "--labels", str(tmp_path / "labels"), *extra],
                          capture_output=True, text=True)


def test_read_label_table_excel_style(tmp_path):
    p = tmp_path / "page_types.csv"
    p.write_bytes("\ufeffDateiname;Seitentyp\nCMR_1.jpg;cmr\nLS_2.jpg;\n".encode("utf-8"))
    values, info = read_label_table(p)
    assert info["delimiter"] == ";"
    assert (info["file_col"], info["value_col"]) == ("Dateiname", "Seitentyp")
    assert values == {"CMR_1.jpg": "cmr"}
    assert info["empty_values"] == 1


def test_match_to_coco_handles_roboflow_names():
    values = {"CMR_4711_p1.jpg": "cmr", "other.jpg": "lieferschein"}
    coco = ["CMR_4711_p1_jpg.rf.0123456789abcdef0123456789abcdef.jpg", "x.jpg"]
    matched, stats = match_to_coco(values, coco)
    assert matched == {coco[0]: "cmr"}
    assert stats["by_stem"] == 1
    assert stats["unmatched_coco"] == ["x.jpg"]
    assert stats["unmatched_csv"] == ["other.jpg"]


def test_doc_type_csv_used_as_source(tiny_coco, tmp_path):
    path, img_dir = tiny_coco
    data = json.loads(path.read_text())
    doc_csv = tmp_path / "page_types.csv"
    doc_csv.write_text("file_name,page_type\n" + "".join(f"{i['file_name']},cmr\n" for i in data["images"]))
    r = run_inspect(tmp_path, path, img_dir, doc_csv, "--no-hash")
    assert r.returncode == 0, r.stderr
    rep = json.loads((tmp_path / "out" / "inspect.json").read_text())
    assert rep["doc_type"]["source"]["kind"] == "csv"
    assert not (tmp_path / "labels" / "doc_types.csv").exists()


def test_inspect_script_end_to_end(tiny_coco, tmp_path):
    path, img_dir = tiny_coco
    out, labels = tmp_path / "out", tmp_path / "labels"
    before = {p.name: p.stat().st_mtime for p in img_dir.iterdir()}
    r = subprocess.run([sys.executable, str(ROOT / "scripts/inspect_dataset.py"),
                        "--config", isolated_config(tmp_path),
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
    assert run_inspect(tmp_path, path, img_dir, None, "--no-hash").returncode == 0
    rows = {r["file_name"]: r["tour_number"] for r in csv.DictReader(open(labels / "tour_numbers.csv"))}
    assert rows["CMR_4711_p1_jpg.rf.0123456789abcdef0123456789abcdef.jpg"] == "1234567"
    assert rows["loading_list_77.jpg"] == ""
    rep = json.loads((tmp_path / "out" / "inspect.json").read_text())
    assert rep["tour_text"]["format_check"]["n_invalid"] == 1  # "1234567" is not number/number


def test_csv_grouping_by_source_pdf():
    recs = {f"p{i}.png": {"file_name": f"p{i}.png", "doc_type": t, "source_pdf": "a.pdf", "source_page": str(i)}
            for i, t in [(2, "cmr"), (1, "loading_list"), (3, "lieferschein")]}
    g = di.csv_grouping(recs, "doc_type")
    assert (g["group_col"], g["page_col"], g["n_groups"]) == ("source_pdf", "source_page", 1)
    assert g["type_sequence"]["a.pdf"] == "LCI"  # lieferschein gets I (L is taken)
    assert g["legend"] == {"L": "loading_list", "C": "cmr", "I": "lieferschein"}


def test_file_names_relative_to_coco_dir(tmp_path):
    """Export layout: labels/_annotations.coco.json + labels/images/, file_name 'images/x.png'."""
    from PIL import Image
    root = tmp_path / "labels"
    (root / "images").mkdir(parents=True)
    Image.new("RGB", (100, 200), "white").save(root / "images" / "p1.png")
    coco = {"images": [{"id": 1, "file_name": "images/p1.png", "width": 100, "height": 200}],
            "annotations": [{"id": 1, "image_id": 1, "category_id": 3, "bbox": [10, 10, 40, 10]},
                            {"id": 2, "image_id": 1, "category_id": 2, "bbox": [80, 190, 30, 15]}],
            "categories": [{"id": 1, "name": "unterschrift"}, {"id": 2, "name": "stempel"},
                           {"id": 3, "name": "tour_nummer"}]}
    (root / "_annotations.coco.json").write_text(json.dumps(coco))
    r = run_inspect(tmp_path, root / "_annotations.coco.json", root / "images")
    assert r.returncode == 0, r.stderr
    rep = json.loads((tmp_path / "out" / "inspect.json").read_text())
    assert "missing_image_file" not in rep["validation"]["counts"]
    assert rep["validation"]["out_of_image"]["sides"] == {"right": 1, "bottom": 1}
    assert len(list((tmp_path / "out" / "tour_crops").glob("*.png"))) == 1


def test_by_doc_type_table(tiny_coco, tmp_path):
    path, img_dir = tiny_coco
    data = json.loads(path.read_text())
    doc_csv = tmp_path / "page_types.csv"
    doc_csv.write_text("file_name;doc_type\n" + "".join(
        f"{i['file_name']};{'cmr' if i['id'] <= 2 else 'lieferschein'}\n" for i in data["images"]))
    assert run_inspect(tmp_path, path, img_dir, doc_csv, "--no-hash").returncode == 0
    rep = json.loads((tmp_path / "out" / "inspect.json").read_text())
    assert rep["by_doc_type"]["cmr"]["pages"] == 2
    assert rep["by_doc_type"]["cmr"]["pages_with"]["unterschrift"] == 1
    assert "Klassen je Dokumenttyp" in (tmp_path / "out" / "inspect.md").read_text()
