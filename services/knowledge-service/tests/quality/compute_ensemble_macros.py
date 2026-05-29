"""Compute per-judge macro precision/recall/F1 from a saved ensemble dump.

Reads judge_verdicts_<label>.json files + judge_ensemble_report.json
under a variant dump dir, recomputes per-chapter precision/recall using
the same formulas the ensemble runner uses (matches llm_judge.py:
precision_credit = supported→1.0, partial→0.5, else→0.0), and prints
a markdown table compatible with c72_compare.md.

Usage:
    python compute_ensemble_macros.py <variant-dir> [<variant-label>]

Example:
    python compute_ensemble_macros.py eval_runs/c72b c72b
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean


PRECISION_CREDIT = {
    "supported": 1.0,
    "partial": 0.5,
    "unsupported": 0.0,
    "unjudged": 0.0,
}

# Match llm_judge.GoldVerdict: "found" verdicts encoded as ItemVerdict
# (covered/supported = found). The judge_ensemble runner serializes
# the JSON verdicts with label tags including "covered".
RECALL_FOUND = {"covered", "supported"}


def compute_per_judge_macros(verdicts_file: Path) -> dict:
    data = json.loads(verdicts_file.read_text(encoding="utf-8"))
    verdicts = data.get("verdicts", [])

    by_chapter: dict[str, dict] = {}
    for v in verdicts:
        ch = v["chapter"]
        cat = v["category"]
        kind = v["kind"]
        verdict = v["verdict"]
        by_chapter.setdefault(ch, {}).setdefault((cat, kind), []).append(verdict)

    chapter_p = []
    chapter_r = []
    for ch, slots in by_chapter.items():
        prec_judged = 0
        prec_credit = 0.0
        rec_judged = 0
        rec_found = 0
        for (_cat, kind), verdicts_list in slots.items():
            if kind == "precision":
                for v in verdicts_list:
                    if v != "unjudged":
                        prec_judged += 1
                        prec_credit += PRECISION_CREDIT.get(v, 0.0)
            elif kind == "recall":
                for v in verdicts_list:
                    if v != "unjudged":
                        rec_judged += 1
                        if v in RECALL_FOUND:
                            rec_found += 1
        if prec_judged > 0:
            chapter_p.append(prec_credit / prec_judged)
        if rec_judged > 0:
            chapter_r.append(rec_found / rec_judged)

    macro_p = mean(chapter_p) if chapter_p else None
    macro_r = mean(chapter_r) if chapter_r else None
    macro_f1 = (
        2 * macro_p * macro_r / (macro_p + macro_r)
        if (macro_p and macro_r and macro_p + macro_r > 0)
        else None
    )
    return {
        "chapters_p": len(chapter_p),
        "chapters_r": len(chapter_r),
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    variant_dir = Path(sys.argv[1])
    variant_label = sys.argv[2] if len(sys.argv) >= 3 else variant_dir.name

    judge_files = [
        ("gemma", variant_dir / "judge_verdicts_gemma.json"),
        ("qwen-30b", variant_dir / "judge_verdicts_qwen-30b.json"),
        ("claude-4.7-opus", variant_dir / "judge_verdicts_claude-4_7-opus.json"),
    ]

    results = []
    for label, fn in judge_files:
        if not fn.is_file():
            print(f"WARN: missing {fn}", file=sys.stderr)
            continue
        r = compute_per_judge_macros(fn)
        r["judge"] = label
        results.append(r)

    if not results:
        print("ERROR: no verdict files found", file=sys.stderr)
        return 1

    # Markdown table
    print(f"\n## Ensemble results — {variant_label}\n")
    print("| Judge | Macro P | Macro R | Macro F1 |")
    print("|---|---:|---:|---:|")
    f1s = []
    for r in results:
        p = r["macro_precision"]
        rec = r["macro_recall"]
        f1 = r["macro_f1"]
        print(
            f"| {r['judge']} | "
            f"{p:.3f} | {rec:.3f} | {f1:.3f} |"
        )
        if f1 is not None:
            f1s.append(f1)

    if f1s:
        median_f1 = sorted(f1s)[len(f1s) // 2] if len(f1s) % 2 else sum(sorted(f1s)[len(f1s) // 2 - 1: len(f1s) // 2 + 1]) / 2
        print(f"| **Median across {len(f1s)} judges** | — | — | **{median_f1:.3f}** |")

    # Ensemble report (Fleiss κ, acceptance)
    report_path = variant_dir / "judge_ensemble_report.json"
    if report_path.is_file():
        ensemble = json.loads(report_path.read_text(encoding="utf-8"))
        kappa = ensemble.get("fleiss_kappa")
        interp = ensemble.get("fleiss_kappa_interpretation")
        print(f"| Fleiss κ | — | — | **{kappa:.3f}** ({interp}) |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
