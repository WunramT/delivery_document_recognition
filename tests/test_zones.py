import random

from PIL import Image

from docval.data.dataset import Box, Page, clip_box
from docval.zones import (MISSING, NOT_REQUIRED, OK, UNCERTAIN, WRONG_POSITION, apply_overrides,
                          check_page, derive_zones, overlap_fraction)
from docval.zones.synthetic import make_variants

RULES = {"cmr": {"require": ["unterschrift", "stempel"], "mode": "all"},
         "lieferschein": {"require": [], "optional": ["unterschrift", "stempel"]},
         "loading_list": {"require": []},
         "x_any": {"require": ["unterschrift", "stempel"], "mode": "any"}}
ZONES = {"cmr": {"unterschrift": {"box": [0.5, 0.7, 1.0, 1.0]}, "stempel": {"box": [0.5, 0.7, 1.0, 1.0]}},
         "lieferschein": {"unterschrift": {"box": [0.5, 0.7, 1.0, 1.0]}, "stempel": {"box": [0.5, 0.7, 1.0, 1.0]}},
         "x_any": {"unterschrift": {"box": [0.5, 0.7, 1.0, 1.0]}, "stempel": {"box": [0.5, 0.7, 1.0, 1.0]}}}


def det(cls, box, score=0.9):
    return {"cls": cls, "box": box, "score": score}


def check(doc, dets):
    return check_page(doc, dets, ZONES, RULES, 0.5, 0.5, 0.3)


def test_clip_box():
    assert clip_box([1200, 10, 100, 20], 1241, 1754) == ([1200, 10, 1241, 30], True)
    assert clip_box([10, 10, 5, 5], 100, 100) == ([10, 10, 15, 15], False)


def test_normalize_box():
    import pytest
    assert Box("x", [124.1, 175.4, 248.2, 350.8]).norm(1241, 1754) == pytest.approx([0.1, 0.1, 0.2, 0.2])


def test_overlap_fraction():
    assert overlap_fraction([0, 0, 1, 1], [0, 0, 0.5, 1]) == 0.5
    assert overlap_fraction([0, 0, 1, 1], [2, 2, 3, 3]) == 0.0


def test_derive_zones_percentiles_and_margin():
    boxes = [[0.7, 0.8, 0.8, 0.9]] * 5 + [[0.6, 0.75, 0.7, 0.85]]
    z = derive_zones({"cmr": {"unterschrift": boxes, "stempel": boxes[:2]}}, 0, 100, 0.02, 3)
    zb = z["cmr"]["unterschrift"]["box"]
    assert zb == [round(0.65 - 0.05 - 0.02, 4), round(0.8 - 0.05 - 0.02, 4), round(0.75 + 0.05 + 0.02, 4), round(0.85 + 0.05 + 0.02, 4)]
    assert "stempel" not in z["cmr"]  # below min_samples


def test_check_page_statuses():
    good = [det("unterschrift", [0.7, 0.8, 0.8, 0.9]), det("stempel", [0.6, 0.8, 0.8, 0.95])]
    assert check("cmr", good)["status"] == OK
    assert check("cmr", good[:1])["status"] == MISSING
    moved = [good[0], det("stempel", [0.1, 0.1, 0.3, 0.2])]
    r = check("cmr", moved)
    assert r["status"] == WRONG_POSITION and "außerhalb" in r["reason"]
    weak = [good[0], det("stempel", [0.6, 0.8, 0.8, 0.95], 0.4)]
    assert check("cmr", weak)["status"] == UNCERTAIN
    # missing beats uncertain
    assert check("cmr", [det("stempel", [0.6, 0.8, 0.8, 0.95], 0.4)])["status"] == MISSING
    assert check("loading_list", [])["status"] == NOT_REQUIRED
    assert check("unsicher", good)["status"] == UNCERTAIN
    assert check("x_any", good[:1])["status"] == OK


def test_synthetic_variants_expected_results():
    im = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
    for x in range(120, 180):
        for y in range(150, 190):
            im.putpixel((x, y), (0, 0, 200, 255))
    page = Page(1, "p.png", None, 200, 200, doc_type="cmr",
                boxes=[Box("unterschrift", [120, 150, 150, 190]), Box("stempel", [140, 150, 180, 190])])
    zones = {"cmr": {"unterschrift": {"box": [0.5, 0.6, 1, 1]}, "stempel": {"box": [0.5, 0.6, 1, 1]}}}
    vs = make_variants(page, im, zones, RULES["cmr"], random.Random(0))
    kinds = {v["kind"]: v["expected"] for v in vs}
    assert kinds["entfernt_stempel"] == MISSING
    assert kinds["entfernt_alle"] == MISSING
    assert kinds["verschoben_unterschrift"] == WRONG_POSITION
    removed = next(v for v in vs if v["kind"] == "entfernt_alle")["image"]
    assert removed.getpixel((160, 170)) == (255, 255, 255)
    # stamp removed, signature area that overlaps is kept
    rs = next(v for v in vs if v["kind"] == "entfernt_stempel")["image"]
    assert rs.getpixel((145, 170)) == (0, 0, 200)
    assert rs.getpixel((170, 170)) == (255, 255, 255)
    assert im.getpixel((170, 170)) == (0, 0, 200, 255)  # original untouched


def test_optional_objects_lieferschein():
    good = [det("unterschrift", [0.7, 0.8, 0.8, 0.9])]
    assert check("lieferschein", [])["status"] == OK                 # nothing required
    assert check("lieferschein", good)["status"] == OK
    wrong = [det("stempel", [0.1, 0.1, 0.3, 0.2])]
    assert check("lieferschein", wrong)["status"] == WRONG_POSITION  # present, but misplaced


def test_per_class_thresholds():
    d = [det("unterschrift", [0.7, 0.8, 0.8, 0.9], 0.3), det("stempel", [0.6, 0.8, 0.8, 0.95], 0.3)]
    r = check_page("cmr", d, ZONES, RULES, 0.5, {"unterschrift": 0.25, "stempel": 0.5},
                   {"unterschrift": 0.15, "stempel": 0.3})
    assert [x["status"] for x in r["details"]] == [OK, UNCERTAIN]


def test_zone_overrides_only_given_edges():
    z = apply_overrides({"cmr": {"unterschrift": {"box": [0.64, 0.75, 1.0, 0.99], "n_samples": 20}}},
                        {"cmr": {"unterschrift": {"x1": 0.0, "x2": 1.0}}})
    assert z["cmr"]["unterschrift"]["box"] == [0.0, 0.75, 1.0, 0.99]


def test_synthetic_optional_only_moved():
    im = Image.new("RGB", (200, 200), "white")
    page = Page(1, "p.png", None, 200, 200, doc_type="lieferschein",
                boxes=[Box("unterschrift", [120, 150, 150, 190])])
    vs = make_variants(page, im, ZONES, RULES["lieferschein"], random.Random(0))
    assert [(v["kind"], v["expected"]) for v in vs] == [("verschoben_unterschrift", WRONG_POSITION)]
