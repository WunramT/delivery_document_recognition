"""Production process: organisational checks, TA rows, review page, finalize."""

import json

from PIL import Image

from docval.process.finalize import apply_decision, run_finalize
from docval.process.organize import organize, page_valid
from docval.process.review import write_review
from docval.process.run import find_ta, normalize_tour, tour_from_name
from docval.process.texts import render_check

TOUR = "503/01.09.2026/4000"
RULES = {"cmr": {"require": ["unterschrift", "stempel"], "mode": "all"},
         "lieferschein": {"require": ["unterschrift", "stempel"], "mode": "any"}}
CFG_NAME = {"labels": {"tour_number": {"format_regex": r"^\d+/\d{2}\.\d{2}\.\d{4}/\d+$", "from_export_name": {
    "pattern": r"^(?P<tour>\d+)_(?P<date>\d{2}\.\d{2}\.\d{4})", "format": "{tour}/{date}/{plant}", "plant": "4000"}}}}


def page(n, doc_type, cmr=None, tour=TOUR, u="ja", s="ja", ta=(), score=0.9, accepted=True):
    props = {"classes": {"unterschrift": u, "stempel": s}}
    return {"n": n, "id": f"s{n:03d}", "image": f"seiten/s{n:03d}.png", "source": f"scan.pdf#{n}", "w": 100,
            "h": 140, "doc_type": doc_type, "doc_reason": "", "dets": [], "masked": [],
            "proposals": {"cmr": props, "lieferschein": props}, "proposal": props["classes"],
            "scores": {"unterschrift": score, "stempel": score},
            "tour": {"text": tour, "accepted": accepted, "raw": tour} if tour else None,
            "cmr_count": {"text": "", "parsed": list(cmr)} if cmr else ({"text": "?", "parsed": None}
                                                                         if doc_type == "cmr" else None),
            "ta": [{"ta": t, "excluded": False} for t in ta], "view": [0, 0.5, 1, 1]}


def codes(org):
    return {c["code"]: c for c in org["checks"]}


def test_complete_tour_sorted():
    pages = [page(1, "loading_list", tour=None), page(2, "cmr", (2, 3)), page(3, "lieferschein"),
             page(4, "cmr", (1, 3)), page(5, "cmr", (3, 3)), page(6, "lieferschein")]
    org = organize(pages, TOUR, RULES)
    assert org["complete"]
    assert org["cmr_order"] == [4, 2, 5]
    assert org["ls_order"] == [3, 6]
    assert "cmr_complete" in codes(org) and "tour_ok" in codes(org)


def test_missing_cmr_and_duplicate_keeps_signed_copy():
    # CMR 1 twice: the copy without stamp (recipient's copy) is dropped, CMR 3/4 missing
    pages = [page(1, "cmr", (1, 4), s="nein"), page(2, "cmr", (1, 4)), page(3, "cmr", (2, 4)), page(4, "cmr", (4, 4))]
    org = organize(pages, TOUR, RULES)
    assert not org["complete"]
    assert org["missing_cmr"] == [3]
    assert org["duplicates"] == {1: 2}
    assert org["cmr_order"] == [2, 3, 4]
    assert "Polilogistics" in render_check(codes(org)["cmr_missing"], "de")
    assert "Polilogistics" in render_check(codes(org)["cmr_missing"], "pl")


def test_person_overrides_duplicate_choice_and_decision():
    pages = [page(1, "cmr", (1, 1)), page(2, "cmr", (1, 1))]
    pages[0]["archive"], pages[1]["archive"] = False, True
    org = organize(pages, TOUR, RULES)
    assert org["cmr_order"] == [2] and org["duplicates"] == {1: 2}
    p = page(3, "cmr", (1, 1), u="unsicher")
    assert page_valid(p, RULES["cmr"]) is None
    p["decision"] = {"unterschrift": False}
    assert page_valid(p, RULES["cmr"]) is False


def test_lieferschein_stamp_or_signature():
    assert page_valid(page(1, "lieferschein", u="nein", s="ja"), RULES["lieferschein"]) is True
    assert page_valid(page(1, "lieferschein", u="nein", s="nein"), RULES["lieferschein"]) is False
    assert page_valid(page(1, "lieferschein", u="nein", s="unsicher"), RULES["lieferschein"]) is None


def test_other_tour_unread_and_unclear():
    pages = [page(1, "cmr", (1, 1)), page(2, "lieferschein", tour="504/01.09.2026/4000"),
             page(3, "lieferschein", accepted=False), page(4, "unsicher"), page(5, "cmr")]
    org = organize(pages, TOUR, RULES)
    assert org["other_tour"] == {2: "504/01.09.2026/4000"}
    assert org["unclear"] == {"doc_type": [4], "tour": [3], "cmr_count": [5]}
    assert org["ls_order"] == [3]
    c = codes(org)
    assert {"doctype_unclear", "tour_other", "tour_unread", "cmr_unread"} <= set(c)
    assert "504/01.09.2026/4000" in render_check(c["tour_other"], "de")


def ls(n, number, page_i=1, page_n=1, **kw):
    p = page(n, "lieferschein", **kw)
    p["ls_number"], p["ls_page"] = number, [page_i, page_n]
    return p


def test_ta_check_loading_list_cmr_and_lieferschein():
    ll = page(1, "loading_list", tour=None)
    ll["ta"] = [{"ta": "12283251", "excluded": False}, {"ta": "12288834", "excluded": False},
                {"ta": "33258864", "excluded": True}]                       # struck out by the person
    pages = [ll,
             page(2, "cmr", (1, 1), ta=["12283251", "12288834", "44400001"]),  # one TA too many on the CMR
             ls(3, "12283251", 1, 2), ls(4, "12283251", 2, 2),               # two-page Lieferschein
             ls(5, "12283251", 1, 2, s="nein", u="nein"),                    # copy of page 1 without stamp
             ls(6, "55500001")]                                              # number not on the loading list
    org = organize(pages, TOUR, RULES)
    ta = org["ta"]
    assert ta["loaded"] == ["12283251", "12288834"] and ta["excluded"] == ["33258864"]
    assert ta["cmr_missing"] == [] and ta["cmr_extra"] == ["44400001"]
    assert ta["ls_missing"] == ["12288834"] and ta["ls_extra"] == ["55500001"]
    assert org["duplicates"] == {5: 3}                                       # page 4 is NOT a duplicate
    assert sorted(org["ls_order"]) == [3, 4, 6]
    c = codes(org)
    assert c["ta_ls_missing"]["level"] == "hinweis" and org["complete"]       # not validated -> hint only
    assert "nicht validiert" in render_check(c["ta_ls_missing"], "de")
    assert "44400001" in render_check(c["ta_cmr_extra"], "pl")
    assert organize(pages, TOUR, RULES, ta_validated=True)["complete"] is False


def test_find_ta_rows_and_not_shipped():
    lines = [{"text": "1", "y1": 100, "y2": 120, "x": 10}, {"text": "12283251", "y1": 102, "y2": 121, "x": 50},
             {"text": "2", "y1": 140, "y2": 160, "x": 10}, {"text": "1228 8834", "y1": 141, "y2": 159, "x": 50},
             {"text": "Nie jedzie", "y1": 139, "y2": 161, "x": 300}, {"text": "PLZ 63500", "y1": 180, "y2": 200, "x": 50}]
    out = find_ta(lines, r"(?<!\d)12\d{6}(?!\d)", ["nie jedzie"])
    assert [(t["ta"], t["excluded"]) for t in out] == [("12283251", False), ("12288834", True)]


def test_tour_names():
    assert tour_from_name("503_01.09.2026", CFG_NAME) == TOUR
    assert normalize_tour(TOUR, CFG_NAME) == TOUR
    assert normalize_tour("503_01.09.2026", CFG_NAME) == TOUR


def result_with_images(tmp_path, pages):
    (tmp_path / "seiten").mkdir()
    for p in pages:
        Image.new("RGB", (100, 140), "white").save(tmp_path / p["image"])
    return {"format": "docval-ergebnis", "created": "2026-10-13T10:00:00", "input": "scan.pdf", "name": "t",
            "tour": TOUR, "dpi": 72, "thresholds": {"accept": {"unterschrift": 0.5}, "uncertain": {}},
            "rules": RULES, "classes": ["unterschrift", "stempel", "tour_nummer", "cmr_count"],
            "doc_types": ["cmr", "lieferschein", "loading_list"], "pages": pages,
            "organize": organize(pages, TOUR, RULES)}


def test_review_page_renders(tmp_path):
    R = result_with_images(tmp_path, [page(1, "cmr", (1, 1)), page(2, "lieferschein")])
    for lang in ("de", "pl"):
        html = write_review(tmp_path, R, lang).read_text(encoding="utf-8")
        assert "{{" not in html and "__DATA__" not in html and "__I18N__" not in html
        assert json.dumps(TOUR) in html


def test_finalize(tmp_path):
    pages = [page(1, "cmr", (2, 2)), page(2, "cmr", (1, 2), u="nein"), page(3, "cmr", (1, 2), s="nein"),
             page(4, "lieferschein", u="unsicher", s="nein")]
    R = result_with_images(tmp_path, pages)
    run = tmp_path / "artifacts" / "process" / "t"
    run.mkdir(parents=True)
    (tmp_path / "seiten").rename(run / "seiten")
    (run / "ergebnis.json").write_text(json.dumps(R), encoding="utf-8")
    dec = {"format": "docval-entscheidung", "ergebnis_created": R["created"], "reviewer": "A. B.", "pages": {
        "1": {"doc_type": "cmr", "confirmed": True, "unterschrift": True, "stempel": True, "archive": True},
        "2": {"doc_type": "cmr", "confirmed": True, "unterschrift": True, "stempel": True, "archive": True},
        "3": {"doc_type": "cmr", "confirmed": False, "archive": False, "archive_set": True},
        "4": {"doc_type": "lieferschein", "confirmed": False, "unterschrift": None, "stempel": False}}}
    (run / "entscheidung.json").write_text(json.dumps(dec), encoding="utf-8")
    cfg = {"paths": {"artifacts": str(tmp_path / "artifacts")}, "ui_languages": ["de", "pl"],
           "process": {"mail": {"cmr": "cmr@example.org"}, "deliver": {"cmr": str(tmp_path / "archiv")}}}
    logs = []
    assert run_finalize(cfg, "t", None, False, logs.append) == 2          # page 4 not confirmed
    dec["pages"]["4"].update(confirmed=True, unterschrift=True)
    (run / "entscheidung.json").write_text(json.dumps(dec), encoding="utf-8")
    assert run_finalize(cfg, "t", None, False, logs.append) == 0
    out = run / "freigabe"
    assert (out / "CMR_503_01.09.2026_4000.pdf").is_file() and (out / "LS_503_01.09.2026_4000.pdf").is_file()
    assert "cmr@example.org" in (out / "CMR_503_01.09.2026_4000.eml").read_text(errors="replace")
    assert (tmp_path / "archiv" / "CMR_503_01.09.2026_4000.pdf").is_file()   # complete -> delivered
    proto = (out / "protokoll_de.txt").read_text(encoding="utf-8")
    assert "VOLLSTÄNDIG" in proto and "CMR (1..n): S. 2, 1" in proto and "Abweichung vom Modellvorschlag: S. 2" in proto
    assert "ZCHECKLSARCHIV" in (out / "protokoll_pl.txt").read_text(encoding="utf-8")


def test_apply_decision_changes_type_and_count():
    p = page(1, "unsicher")
    q = apply_decision([p], {"pages": {"1": {"doc_type": "cmr", "cmr_count": [3, 5], "tour": "x/y",
                                             "unterschrift": True, "confirmed": True}}})[0]
    assert q["doc_type"] == "cmr" and q["cmr_count"]["parsed"] == [3, 5] and q["tour"]["text"] == "x/y"
    assert q["decision"] == {"unterschrift": True} and "archive" not in q and p["doc_type"] == "unsicher"


def test_label_scans_export(tmp_path):
    from docval.process.labels import build_export, export_name

    pages = [page(1, "cmr", (1, 1)), page(2, "unsicher")]
    pages[0]["dets"] = [{"cls": "stempel", "box": [0.1, 0.8, 0.3, 0.9], "score": 0.9},
                        {"cls": "stempel", "box": [0.5, 0.8, 0.6, 0.9], "score": 0.1}]
    R = result_with_images(tmp_path, pages)
    R["thresholds"]["accept"] = {"stempel": 0.5}
    classes = ["unterschrift", "stempel", "ta_nummer"]
    coco, meta = build_export(R, {"pages": {"2": {"doc_type": "lieferschein"}}}, classes, tmp_path, tmp_path / "out")
    assert export_name(TOUR, "x") == "503_01.09.2026" and export_name(None, "x") == "x"
    assert [c["name"] for c in coco["categories"]] == classes
    assert len(coco["annotations"]) == 1 and coco["annotations"][0]["attributes"]["quelle"] == "modell"
    assert (tmp_path / "out" / "images" / "s001.png").is_file()
    rows = (tmp_path / "out" / "page_types.csv").read_text(encoding="utf-8-sig").splitlines()
    assert rows[2] == "images/s002.png;lieferschein;scan.pdf;2"
    assert meta[1]["changes"][0]["action"] == "hinzugefügt"


def test_confirmation_carrier():
    from docval.process.run import carrier

    cfg = {"doctype": {"fuzzy_min_len": 7}, "process": {"confirmations": {
        "hermes": ["DLW Kartons"], "dhl": ["Entladebericht", "2-Mann-Handling"]}}}
    assert carrier("DLW Kartons  Übergabe 17.09.2026", cfg) == "hermes"
    assert carrier("DHL 2-Mann-Handling GmbH Entladebereicht", cfg) == "dhl"   # 1 OCR error tolerated
    assert carrier("Lieferschein 80012345", cfg) is None


def test_lieferschein_customer():
    from docval.process.run import carrier

    cfg = {"doctype": {"fuzzy_min_len": 7}, "process": {"customers": {"hermes": ["Hermes"], "dhl": ["DHL"]}}}
    assert carrier("Lieferschein 80012345 Lieferanschrift Hermes Germany GmbH", cfg, "customers") == "hermes"
    assert carrier("Lieferanschrift DHL Home Delivery GmbH", cfg, "customers") == "dhl"
    assert carrier("Lieferanschrift Möbel Meyer", cfg, "customers") is None


def test_abholschein_discarded():
    pages = [page(1, "cmr", (1, 1)), page(2, "abholschein", tour=None), page(3, "lieferschein")]
    org = organize(pages, TOUR, RULES)
    assert org["discarded"] == [2] and org["complete"]
    assert 2 not in org["cmr_order"] + org["ls_order"]
    assert "Abholschein" in render_check(codes(org)["discarded"], "de")


def test_editor_ignores_broken_page_types(tmp_path):
    from docval.eval.label_editor import editor_data

    broken = tmp_path / "page_types.csv"
    broken.write_bytes(b"\r\n" * 53)            # what an earlier save left behind
    coco = {"images": [{"id": 1, "file_name": "images/a.png", "width": 10, "height": 10}],
            "annotations": [], "categories": []}
    d = editor_data("x", coco, "_annotations.coco.json", {}, ["stempel"], ["cmr"], broken)
    assert d["csv"] is None                     # editor writes a fresh file_name;doc_type CSV
