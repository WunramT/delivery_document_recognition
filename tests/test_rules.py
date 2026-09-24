from types import SimpleNamespace as P

from docval.data.split import assign_groups, grouped_stratified_split, segment_ids, split_summary
from docval.doctype.rules import UNCERTAIN, combine, fold, keyword_decision, keyword_scores
from docval.ocr.postprocess import correct, evaluate_text, parse_cmr_count, stack_complete

KW = {"cmr": ["CMR", "Frachtbrief"], "lieferschein": ["Lieferschein", "Dowód dostawy"],
      "loading_list": ["Loading List", "List załadunkowy"]}
RX = r"^\d+/\d+$"


def test_fold_and_keywords():
    assert fold("List załadunkowy") == "listzaladunkowy"
    assert keyword_scores("LIST ZAŁADUNKOWY Nr 5", KW) == {"loading_list": ["List załadunkowy"]}
    assert keyword_scores("Liefersch3in 4711", KW) == {"lieferschein": ["Lieferschein"]}  # 1 OCR error
    assert keyword_scores("CNR", KW) == {}  # short keywords exact only
    assert keyword_decision({}, [])[0] is None
    assert keyword_decision({"cmr": ["CMR"], "lieferschein": ["x"]}, [])[0] is None
    assert keyword_decision({"cmr": ["CMR"], "lieferschein": ["x"]}, ["cmr"])[0] == "cmr"


def test_combine_logic():
    assert combine("cmr", "kw", "cmr", 0.99, 0.8, 0.9)["doc_type"] == "cmr"
    assert combine("cmr", "kw", "lieferschein", 0.6, 0.8, 0.9)["doc_type"] == "cmr"  # keyword wins
    assert combine("cmr", "kw", "lieferschein", 0.95, 0.8, 0.9)["doc_type"] == UNCERTAIN  # conflict
    assert combine(None, "-", "cmr", 0.85, 0.8, 0.9)["doc_type"] == "cmr"
    assert combine(None, "-", "cmr", 0.5, 0.8, 0.9)["doc_type"] == UNCERTAIN
    assert combine(None, "-", None, None, 0.8, 0.9)["doc_type"] == UNCERTAIN


def test_tour_correction():
    assert correct("200/01", RX) == ("200/01", [])
    assert correct(" 2O0/Ol ", RX)[0] == "200/01"
    assert correct("20S\\B1", RX)[0] == "205/81"
    assert correct("200|01", RX)[0] == "200/01"
    assert correct("AB/CD", RX)[0] == "AB/CD"  # no valid reading -> unchanged, rejected by regex
    r = evaluate_text("2OO/01", 0.95, RX, 0.9)
    assert r["accepted"] and r["text"] == "200/01" and r["corrections"]
    assert not evaluate_text("200/01", 0.5, RX, 0.9)["accepted"]
    assert not evaluate_text("20001", 0.99, RX, 0.9)["accepted"]


TOUR = r"^\d+/\d{2}\.\d{2}\.\d{4}/\d+$"


def test_tour_correction_real_format():
    ok = "503/01.09.2026/4000"
    assert correct(ok, TOUR) == (ok, [])
    assert correct("Tura503/01.09.2026/4000", TOUR)[0] == ok      # label prefix in the box
    assert correct("503/01.09.2026/4000b", TOUR)[0] == ok         # trailing noise
    assert correct("5O3/01,09.2026\\4000", TOUR)[0] == ok        # look-alikes, position-aware
    assert correct("503|01.09.2026|4000", TOUR)[0] == ok
    for bad in ["50301.09.20261400000", "Tura50301092026400", "TO"]:  # not recoverable
        assert not evaluate_text(bad, 0.99, TOUR, 0.9)["accepted"]
    r = evaluate_text("Tour 503/01.09.2026/4000", 0.95, TOUR, 0.9)
    assert r["accepted"] and r["text"] == ok


def test_cmr_count():
    assert parse_cmr_count("CMR 11/12") == (11, 12)
    assert parse_cmr_count("CMR l/2") == (1, 2)
    assert parse_cmr_count("13/12") is None
    assert stack_complete([(1, 3), (2, 3), (3, 3)])["complete"]
    assert "fehlende Seiten [2]" in stack_complete([(1, 3), (3, 3)])["reason"]


def pages_from(seq, pdf="a.pdf"):
    m = {"L": "loading_list", "C": "cmr", "I": "lieferschein"}
    return [P(file_name=f"p{i:03d}", doc_type=m[c], source_pdf=pdf, source_page=i + 1,
              tour_number=None, group=None) for i, c in enumerate(seq)]


REAL = "LLLLLLCCIIIIIICCIIIIICCCCIIIIIIIIIICCCCIIIIIIIICCIICCCCIIIIIIIIIIIIICCICCICCIII"


def test_segments_real_sequence():
    ids = segment_ids(pages_from(REAL), ["cmr"], ["loading_list"])
    assert len(set(ids)) == 10
    assert ids[0] == ids[5] != ids[6]


def test_grouped_split_no_leak_and_deterministic():
    cfg = {"group_by": "segment", "ungroup_doc_types": ["loading_list"],
           "segment_start_types": ["cmr"], "own_segment_types": ["loading_list"]}
    pages = pages_from(REAL)
    info = assign_groups(pages, cfg)
    assert info["n_groups"] == 9 + 6
    ratios = {"train": 0.7, "valid": 0.15, "test": 0.15}
    a1 = grouped_stratified_split(pages, ratios, 42)
    a2 = grouped_stratified_split(pages, ratios, 42)
    assert a1 == a2
    s = split_summary(pages, a1)
    assert s["_leaking_groups"] == []
    for name in ratios:
        assert s[name]["by_type"].get("cmr", 0) >= 1
        assert s[name]["by_type"].get("loading_list", 0) >= 1
