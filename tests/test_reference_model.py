"""Template model for re-labeling new classes: folds, routing, coverage."""

from types import SimpleNamespace

from docval.data.coverage import complete_exports, partial_classes
from docval.eval.reference_model import assign_folds, merge_predictions, plan_classes

OLD = ["unterschrift", "stempel", "tour_nummer", "cmr_count"]
ALL = OLD + ["ta_nummer", "ls_nummer", "seitenzahl"]


def test_coverage():
    cov = {"425_21.09.2026": set(ALL), "503_01.09.2026": set(OLD), "609_17.09.2026": set(OLD)}
    assert complete_exports(cov, ALL) == ["425_21.09.2026"]
    part = partial_classes(cov, ALL)
    assert set(part) == {"ta_nummer", "ls_nummer", "seitenzahl"}
    assert part["ta_nummer"] == ["503_01.09.2026", "609_17.09.2026"]
    assert partial_classes({"a": set(OLD), "b": set(OLD)}, ALL) == {}   # missing everywhere = not partial


def test_folds_keep_groups_together_and_balance():
    pages = [SimpleNamespace(file_name=f"p{i}", group=g) for i, g in enumerate("aaabbcdef")]
    folds = assign_folds(pages, 2)
    assert len({folds[f"p{i}"] for i in range(3)}) == 1          # group a in one fold
    sizes = [sum(1 for v in folds.values() if v == k) for k in (0, 1)]
    assert abs(sizes[0] - sizes[1]) <= 1
    assert assign_folds(pages, 2) == folds                        # deterministic


def test_merge_predictions_union():
    a = {"cls": "ta_nummer", "box": [0.1, 0.1, 0.3, 0.2], "score": 0.6}
    b = {"cls": "ta_nummer", "box": [0.11, 0.1, 0.31, 0.2], "score": 0.8}   # same object, other fold
    c = {"cls": "stempel", "box": [0.1, 0.1, 0.3, 0.2], "score": 0.5}       # other class, same place
    out = merge_predictions([a, b, c])
    assert [d["score"] for d in out] == [0.8, 0.5]


def test_plan_classes():
    # template tour: everything from the held-out template model
    assert plan_classes(set(ALL), True, OLD, ALL) == ([], ALL)
    # old tour: its labeled classes from the main detector, the new ones from the template
    assert plan_classes(set(OLD), False, OLD, ALL) == (OLD, ["ta_nummer", "ls_nummer", "seitenzahl"])
    # no template model: as before, the main detector for all its classes
    assert plan_classes(set(OLD), False, OLD, None) == (OLD, [])
