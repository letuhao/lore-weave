"""D-KG-EXTRACTION-CANON-GATE judge accuracy eval (measure-before-wire).

The POC (see docs/sessions/SESSION_HANDOFF.md 2026-07-05 entry) proved the
symbolic-prefilter + LLM-judge mechanism works end-to-end, including
degrading safely under a real infra fault, but left judge ACCURACY on hard
cases as an open, unmeasured question -- the $0 local Gemma-4 26B model was
reliably right on easy cases and inconsistent on hard ones. This script
answers that question with a scored fixture set instead of more anecdotal
spot-checks, across one or more candidate models, so the wiring decision
(services/knowledge-service/app/extraction/canon_check.py -> pass2_orchestrator
Step 5) is evidence-based.

Run inside the knowledge-service container (needs app.* + service env):

  python -m eval.run_canon_check_eval run \
      --user-id=019d5e3c-7cc5-7e6a-8b27-1344e148bf7c \
      --model gemma-4-26b-qat=019ebb72-27a2-72f3-a42d-d2d0e0ded179 \
      --model qwen3-35b=019dc738-a6b7-7bff-b953-b47868ae7db0

Metrics are computed only over RESOLVED verdicts (confirmed is True/False);
a `None` verdict (LLM error / timeout -> degrade-safe) is reported as
`inconclusive`, never silently scored as correct or incorrect -- an
inconclusive-heavy model is itself a finding, not noise to average away.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from eval.canon_check_fixtures import ALICE_SNAPSHOT, FIXTURES, CanonCheckFixture


# ── pure scoring helpers (unit-tested in tests/unit/test_canon_check_eval_metrics.py) ──


@dataclass
class FixtureResult:
    fixture_id: str
    expected: bool
    confirmed: bool | None
    why: str
    note: str

    @property
    def outcome(self) -> str:
        if self.confirmed is None:
            return "inconclusive"
        return "correct" if self.confirmed == self.expected else "wrong"


@dataclass
class ModelReport:
    label: str
    results: list[FixtureResult] = field(default_factory=list)

    @property
    def resolved(self) -> list[FixtureResult]:
        return [r for r in self.results if r.confirmed is not None]

    @property
    def inconclusive_count(self) -> int:
        return sum(1 for r in self.results if r.confirmed is None)

    @property
    def accuracy(self) -> float | None:
        resolved = self.resolved
        if not resolved:
            return None
        return sum(1 for r in resolved if r.outcome == "correct") / len(resolved)

    @property
    def confusion(self) -> dict:
        tp = sum(1 for r in self.resolved if r.expected and r.confirmed)
        fp = sum(1 for r in self.resolved if not r.expected and r.confirmed)
        tn = sum(1 for r in self.resolved if not r.expected and not r.confirmed)
        fn = sum(1 for r in self.resolved if r.expected and not r.confirmed)
        return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

    @property
    def precision(self) -> float | None:
        c = self.confusion
        denom = c["tp"] + c["fp"]
        return (c["tp"] / denom) if denom else None

    @property
    def recall(self) -> float | None:
        c = self.confusion
        denom = c["tp"] + c["fn"]
        return (c["tp"] / denom) if denom else None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "n_fixtures": len(self.results),
            "inconclusive": self.inconclusive_count,
            "accuracy": round(self.accuracy, 4) if self.accuracy is not None else None,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "recall": round(self.recall, 4) if self.recall is not None else None,
            "confusion": self.confusion,
            "misses": [
                {"fixture_id": r.fixture_id, "expected": r.expected, "confirmed": r.confirmed,
                 "note": r.note, "why": r.why}
                for r in self.results if r.outcome != "correct"
            ],
        }


# ── async eval phase (imports deferred -- app.config needs service env) ──


async def _run_one_model(llm, *, label: str, model_ref: str, user_id: str) -> ModelReport:
    from app.extraction.canon_check import check_extraction_canon

    report = ModelReport(label=label)
    for fixture in FIXTURES:
        candidates = await check_extraction_canon(
            fixture.chapter_text,
            ALICE_SNAPSHOT,
            llm=llm,
            user_id=user_id,
            model_source="user_model",
            model_ref=model_ref,
        )
        if not candidates:
            # symbolic prefilter didn't even flag it -- treat as a hard miss,
            # not inconclusive, since every fixture is designed to be flagged.
            report.results.append(FixtureResult(
                fixture.fixture_id, fixture.expected_is_contradiction,
                confirmed=False, why="SYMBOLIC PREFILTER DID NOT FLAG", note=fixture.note,
            ))
            continue
        c = candidates[0]
        report.results.append(FixtureResult(
            fixture.fixture_id, fixture.expected_is_contradiction,
            confirmed=c.confirmed, why=c.why, note=fixture.note,
        ))
    return report


async def _run(args) -> int:
    from app.clients.llm_client import get_llm_client

    llm = get_llm_client()
    reports = []
    for spec in args.model:
        label, _, model_ref = spec.partition("=")
        if not model_ref:
            print(f"bad --model spec (want label=uuid): {spec!r}", file=sys.stderr)
            return 1
        print(f"--- running {label} ({model_ref}) over {len(FIXTURES)} fixtures ---", file=sys.stderr)
        report = await _run_one_model(llm, label=label, model_ref=model_ref, user_id=str(args.user_id))
        reports.append(report)
        print(json.dumps(report.to_dict(), indent=2))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_fixtures": len(FIXTURES),
        "models": [r.to_dict() for r in reports],
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="D-KG-EXTRACTION-CANON-GATE judge accuracy eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    from uuid import UUID

    p_run = sub.add_parser("run", help="score one or more models against the fixture set")
    p_run.add_argument("--user-id", type=UUID, required=True)
    p_run.add_argument("--model", action="append", required=True,
                        help="label=model_ref_uuid, repeatable")
    p_run.add_argument("--out", help="optional path to write the JSON report")

    args = ap.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
