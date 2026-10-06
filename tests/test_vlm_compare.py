from docval.eval.vlm_compare import _count, _dq, auc, center_in, presence_stats, three_state


def test_auc():
    assert auc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert auc([0.1, 0.9], [True, False]) == 0.0
    assert auc([0.5, 0.5], [True, False]) == 0.5      # tie counts half
    assert auc([0.9], [True]) is None                # one class only


def test_three_state():
    assert three_state(0.95, 0.9, 0.1) is True
    assert three_state(0.05, 0.9, 0.1) is False
    assert three_state(0.5, 0.9, 0.1) is None


def test_center_in():
    assert center_in([0.1, 0.7, 0.3, 0.9], [0.0, 0.6, 1.0, 1.0])
    assert not center_in([0.1, 0.1, 0.3, 0.3], [0.0, 0.6, 1.0, 1.0])
    assert center_in([0.1, 0.1, 0.3, 0.3], None)


def test_presence_stats_both_models():
    rows = [{"view": "seite", "cls": "stempel", "doc_type": "cmr", "gt": g, "vlm_p": v, "det_score": d}
            for g, v, d in [(True, 0.95, 0.8), (True, 0.4, 0.2), (False, 0.05, 0.6), (False, 0.5, 0.01)]]
    s = presence_stats(rows, ["stempel"], {"seite": None}, 0.9, {"stempel": 0.5}, {"stempel": 0.3})
    a = s["seite"]["stempel"]["alle"]
    assert a["n"] == 4 and a["n_pos"] == 2
    assert a["vlm"]["auc"] == 0.75 and a["det"]["auc"] == 0.75
    assert (a["vlm"]["fp"], a["vlm"]["fn"]) == (1, 1)        # 0.5 counts as yes
    assert (a["det"]["fp"], a["det"]["fn"]) == (1, 1)
    assert a["vlm"]["auto"]["k"] == 2 and a["vlm"]["auto_correct"]["k"] == 2
    assert a["det"]["auto"]["k"] == 4 and a["det"]["auto_correct"]["k"] == 2
    assert "cmr" in s["seite"]["stempel"]


def test_decision_count():
    dq = _dq()
    for gt, st in [("ok", "ok"), ("ok", "unsicher"), ("fehlt", "ok"), ("ok", "fehlt"), ("falsche_position", "fehlt")]:
        _count(dq, gt, st)
    assert dq == {"n": 5, "auto_richtig": 2, "person": 1, "auto_falsch_fehler_uebersehen": 1,
                  "auto_falsch_fehlalarm": 1}
