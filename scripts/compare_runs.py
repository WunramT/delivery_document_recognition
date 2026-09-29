"""Compare two evaluation runs side by side (e.g. before/after re-labeling one tour).

    python scripts/compare_runs.py artifacts artifacts/exp_relabel
    make compare A=artifacts B=artifacts/exp_relabel

A and B are artifacts folders (or report folders, or results.json files). Prints a German
Markdown table and writes it to <B>/report/compare.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(p: str) -> tuple[dict, Path]:
    path = Path(p)
    for cand in (path, path / "results.json", path / "report" / "results.json"):
        if cand.is_file():
            return json.loads(cand.read_text(encoding="utf-8")), cand.parent
    sys.exit(f"keine results.json unter {p} - zuerst `make eval` mit diesem Artefakt-Ordner")


def v(r):
    return None if not r else r.get("value")


def pct(x):
    return "-" if x is None else f"{x * 100:.1f} %"


def ap(x):
    return "-" if x is None else f"{x:.3f}"


def delta(a, b, scale=100, unit=" pp"):
    if a is None or b is None:
        return ""
    d = (b - a) * scale
    return f"{'+' if d >= 0 else ''}{d:.1f}{unit}"


def compare(A: dict, B: dict, na: str, nb: str) -> str:
    L = [f"# Vergleich zweier Läufe", "", f"- A: `{na}` – Split {A['meta']['split']}, {A['meta']['n_pages']} Seiten",
         f"- B: `{nb}` – Split {B['meta']['split']}, {B['meta']['n_pages']} Seiten", ""]
    if A["meta"]["n_pages"] != B["meta"]["n_pages"]:
        L += ["**Achtung:** unterschiedlich viele Test-Seiten – der Split ist nicht derselbe, die Zahlen "
              "sind nur eingeschränkt vergleichbar.", ""]
    L += ["## Akzeptanzkriterien", "", "| Stufe | Metrik | A | B | Δ | n (B) |", "|---|---|---|---|---|---|"]
    ka = {(c["stage"], c["metric"]): c for c in A["acceptance"]}
    for c in B["acceptance"]:
        a = ka.get((c["stage"], c["metric"]), {})
        mark = lambda x: "" if x is None else (" ✅" if x else " ❌")  # noqa: E731
        L.append(f"| {c['stage']} | {c['metric']} | {pct(a.get('value'))}{mark(a.get('passed'))} | "
                 f"{pct(c['value'])}{mark(c['passed'])} | {delta(a.get('value'), c['value'])} | {c['n']} |")
    L += ["", "## Detektor je Klasse (Test-Split)", "",
          "| Klasse | Schwelle A / B | Recall A | Recall B | Δ | AP50 A | AP50 B |", "|---|---|---|---|---|---|---|"]
    pa, pb = A["detector"]["per_class"], B["detector"]["per_class"]
    for c in pb:
        a, b = pa.get(c, {}), pb[c]
        L.append(f"| {c} | {a.get('threshold', '-')} / {b.get('threshold', '-')} | {pct(v(a.get('recall')))} | "
                 f"{pct(v(b['recall']))} | {delta(v(a.get('recall')), v(b['recall']))} | "
                 f"{ap(a.get('ap50'))} | {ap(b.get('ap50'))} |")
    ea, eb = A["detector"].get("by_export") or {}, B["detector"].get("by_export") or {}
    if eb:
        L += ["", "## Je Export/Tour: Recall und mittlere IoU der Treffer", "",
              "Eine neu gelabelte Tour sollte vor allem bei der IoU (engere, einheitliche Boxen) und beim "
              "Recall von cmr_count/stempel zulegen. Nur Test-Seiten – wenige Seiten je Tour, große Streuung.", "",
              "| Export | Klasse | Recall A | Recall B | IoU A | IoU B |", "|---|---|---|---|---|---|"]
        for e, x in eb.items():
            for c, r in x["per_class"].items():
                if not r["recall"]["n"]:
                    continue
                a = (ea.get(e) or {}).get("per_class", {}).get(c, {})
                ia, ib = a.get("mean_iou"), r["mean_iou"]
                L.append(f"| {e} ({x['pages']} S.) | {c} | {pct(v(a.get('recall')))} | {pct(v(r['recall']))} "
                         f"({r['recall']['k']}/{r['recall']['n']}) | {'-' if ia is None else f'{ia:.2f}'} | "
                         f"{'-' if ib is None else f'{ib:.2f}'} |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    args = ap.parse_args()
    A, _ = load(args.a)
    B, bdir = load(args.b)
    md = compare(A, B, args.a, args.b)
    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    print(md)
    (bdir / "compare.md").write_text(md, encoding="utf-8")
    print(f"[compare] {bdir / 'compare.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
