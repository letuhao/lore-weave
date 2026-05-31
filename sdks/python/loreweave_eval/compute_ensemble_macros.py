"""Compute per-judge macro precision/recall/F1 from a saved ensemble dump,
plus the **disjoint-judge metric of record** and a bootstrap confidence interval.

Reads every ``judge_verdicts_<label>.json`` under a variant dump dir, recomputes
per-chapter precision/recall (same formulas as llm_judge.py: precision_credit =
supported→1.0, partial→0.5, else→0.0), and reports:

  * a per-judge macro P/R/F1 table (with the extractor/filter judges flagged);
  * the **full-panel median F1** (historical metric — kept for comparison); and
  * the **DISJOINT median F1** (cycle 74e) — median over only the judges that are
    NEITHER the extractor (`KNOWLEDGE_EXTRACTOR_MODEL`) NOR the filter
    (`KNOWLEDGE_FILTER_MODEL`), with a bootstrap CI over chapters. This removes the
    self-reinforcement inflation (a model grading its own output) from the locked
    metric — see docs/plans/2026-05-31-extraction-accuracy-and-eval-plan.md §3.

Usage:
    python compute_ensemble_macros.py <variant-dir> [<variant-label>]

Env (optional — defaults are the known production UUIDs):
    KNOWLEDGE_EXTRACTOR_MODEL  extractor model UUID to exclude from the metric
    KNOWLEDGE_FILTER_MODEL     filter model UUID to exclude from the metric
    KNOWLEDGE_BOOTSTRAP_N      bootstrap resamples (default 2000)
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from statistics import mean, median


PRECISION_CREDIT = {
    "supported": 1.0,
    "partial": 0.5,
    "unsupported": 0.0,
    "unjudged": 0.0,
}

# Match llm_judge.GoldVerdict: "found" verdicts encoded as ItemVerdict
# (covered/supported = found).
RECALL_FOUND = {"covered", "supported"}

# Pipeline models that must NOT serve as judges of record (self-reinforcement).
# Q0-0b: the canonical defaults now live in `panel.py` (single source of truth);
# re-exported here under their historical private names for back-compat with any
# caller/test that referenced them.
from .panel import DEFAULT_EXTRACTOR_REF as _DEFAULT_EXTRACTOR_UUID
from .panel import DEFAULT_FILTER_REF as _DEFAULT_FILTER_UUID
from .panel import panel_from_env

_BOOTSTRAP_SEED = 0xC74E  # deterministic; bootstrap must be reproducible


def _per_chapter_pr(verdicts: list[dict]) -> tuple[dict[str, float], dict[str, float]]:
    """Return ``(chapter→precision, chapter→recall)`` over JUDGED verdicts.

    A chapter only appears in the precision (resp. recall) map when it has at
    least one judged precision (resp. recall) verdict — mirrors the macro logic
    that skips empty denominators.
    """
    by_chapter: dict[str, dict] = {}
    for v in verdicts:
        ch = v["chapter"]
        by_chapter.setdefault(ch, {}).setdefault((v["category"], v["kind"]), []).append(
            v["verdict"]
        )

    chap_p: dict[str, float] = {}
    chap_r: dict[str, float] = {}
    for ch, slots in by_chapter.items():
        prec_judged = rec_judged = rec_found = 0
        prec_credit = 0.0
        for (_cat, kind), vlist in slots.items():
            for v in vlist:
                if v == "unjudged":
                    continue
                if kind == "precision":
                    prec_judged += 1
                    prec_credit += PRECISION_CREDIT.get(v, 0.0)
                elif kind == "recall":
                    rec_judged += 1
                    if v in RECALL_FOUND:
                        rec_found += 1
        if prec_judged > 0:
            chap_p[ch] = prec_credit / prec_judged
        if rec_judged > 0:
            chap_r[ch] = rec_found / rec_judged
    return chap_p, chap_r


def _macro_f1(chap_p: dict[str, float], chap_r: dict[str, float],
              chapters: list[str] | None = None) -> float | None:
    """Macro P/R over the given chapters (default: all), then harmonic F1."""
    ps = [chap_p[c] for c in (chapters or chap_p) if c in chap_p]
    rs = [chap_r[c] for c in (chapters or chap_r) if c in chap_r]
    if not ps or not rs:
        return None
    p, r = mean(ps), mean(rs)
    return 2 * p * r / (p + r) if (p + r) > 0 else None


def load_judge(verdicts_file: Path) -> dict:
    data = json.loads(verdicts_file.read_text(encoding="utf-8"))
    chap_p, chap_r = _per_chapter_pr(data.get("verdicts", []))
    return {
        "label": data.get("judge_label", verdicts_file.stem),
        "uuid": data.get("judge_uuid", ""),
        "chap_p": chap_p,
        "chap_r": chap_r,
        "macro_p": mean(chap_p.values()) if chap_p else None,
        "macro_r": mean(chap_r.values()) if chap_r else None,
        "macro_f1": _macro_f1(chap_p, chap_r),
    }


def compute_per_judge_macros(verdicts_file: Path) -> dict:
    """Backward-compatible scalar view used by older callers."""
    j = load_judge(verdicts_file)
    return {
        "chapters_p": len(j["chap_p"]),
        "chapters_r": len(j["chap_r"]),
        "macro_precision": j["macro_p"],
        "macro_recall": j["macro_r"],
        "macro_f1": j["macro_f1"],
    }


def _median(xs: list[float]) -> float:
    return median(xs)


def disjoint_median_with_ci(
    judges: list[dict], *, n_boot: int
) -> dict:
    """Median F1 over judges, with a percentile bootstrap CI over the common
    chapter set. Caller passes the already-filtered (disjoint) judge list."""
    f1s = [j["macro_f1"] for j in judges if j["macro_f1"] is not None]
    if len(f1s) < 2:
        return {"n_judges": len(f1s), "median_f1": (f1s[0] if f1s else None),
                "ci_low": None, "ci_high": None, "n_common_chapters": 0}
    point = _median(f1s)

    # Common chapters present (in BOTH p and r) for every disjoint judge.
    common: set[str] | None = None
    for j in judges:
        present = set(j["chap_p"]) & set(j["chap_r"])
        common = present if common is None else (common & present)
    common_list = sorted(common or [])

    ci_low = ci_high = None
    if len(common_list) >= 2:
        rnd = random.Random(_BOOTSTRAP_SEED)
        n = len(common_list)
        stats: list[float] = []
        for _ in range(n_boot):
            sample = [common_list[rnd.randrange(n)] for _ in range(n)]
            per_judge = [
                _macro_f1(j["chap_p"], j["chap_r"], sample) for j in judges
            ]
            per_judge = [x for x in per_judge if x is not None]
            if len(per_judge) >= 2:
                stats.append(_median(per_judge))
        if stats:
            stats.sort()
            ci_low = stats[int(0.025 * len(stats))]
            ci_high = stats[min(len(stats) - 1, int(0.975 * len(stats)))]
    return {
        "n_judges": len(f1s),
        "median_f1": point,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n_common_chapters": len(common_list),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    variant_dir = Path(sys.argv[1])
    variant_label = sys.argv[2] if len(sys.argv) >= 3 else variant_dir.name
    # Q0-0b: exclusion set comes from the JudgePanel (env-overridable, same
    # defaults) instead of inline env reads — enforced in code, not by hand.
    panel = panel_from_env()
    n_boot = int(os.environ.get("KNOWLEDGE_BOOTSTRAP_N", "2000") or 2000)
    excluded = panel.excluded

    files = sorted(variant_dir.glob("judge_verdicts_*.json"))
    if not files:
        print(f"ERROR: no judge_verdicts_*.json in {variant_dir}", file=sys.stderr)
        return 1
    judges = [load_judge(f) for f in files]

    print(f"\n## Ensemble results — {variant_label}\n")
    print("| Judge | role | Macro P | Macro R | Macro F1 |")
    print("|---|---|---:|---:|---:|")
    for j in judges:
        role = ("EXTRACTOR" if j["uuid"] == extractor
                else "FILTER" if j["uuid"] == filt else "independent")
        p, r, f1 = j["macro_p"], j["macro_r"], j["macro_f1"]
        cells = (f"{p:.3f}" if p is not None else "—",
                 f"{r:.3f}" if r is not None else "—",
                 f"{f1:.3f}" if f1 is not None else "—")
        print(f"| {j['label']} | {role} | {cells[0]} | {cells[1]} | {cells[2]} |")

    all_f1 = [j["macro_f1"] for j in judges if j["macro_f1"] is not None]
    if all_f1:
        print(f"| **full-panel median** (incl. extractor/filter) | — | — | — | "
              f"**{_median(all_f1):.3f}** |")

    disjoint = [j for j in judges if j["uuid"] not in excluded]
    res = disjoint_median_with_ci(disjoint, n_boot=n_boot)
    if res["median_f1"] is not None:
        ci = (f" · 95% CI [{res['ci_low']:.3f}, {res['ci_high']:.3f}]"
              if res["ci_low"] is not None else " · CI n/a (<2 common chapters)")
        labels = ", ".join(j["label"] for j in disjoint)
        print(f"| **DISJOINT median of record** ({res['n_judges']}J: {labels}) | — | — | — | "
              f"**{res['median_f1']:.3f}**{ci} |")
        if res["n_judges"] < 2:
            print("\nWARNING: <2 disjoint judges — disjoint metric not robust; "
                  "add a non-pipeline judge (gemma + another).", file=sys.stderr)
    else:
        print("\nWARNING: no disjoint judges found (all judges are the extractor/filter).",
              file=sys.stderr)

    report_path = variant_dir / "judge_ensemble_report.json"
    if report_path.is_file():
        ens = json.loads(report_path.read_text(encoding="utf-8"))
        k = ens.get("fleiss_kappa")
        if k is not None:
            print(f"| Fleiss κ | — | — | — | **{k:.3f}** ({ens.get('fleiss_kappa_interpretation')}) |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
