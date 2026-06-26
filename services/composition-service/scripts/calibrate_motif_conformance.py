"""W5 conformance calibration harness + eval-gate (§3) — ADVISORY honesty made structural.

WHAT THIS IS (and is NOT):
  loreweave_eval's reported F1=0.869 is an EXTRACTION judge (entity/relation/event
  precision vs human gold). motif_conformance is a NEW dimension with NO inherited
  gold (audit F-3: "stop calling any of this 'reuse the calibrated judge'"). This
  harness REUSES the *mechanism* (calibrate_judge — binary kappa/balanced-acc) but
  re-earns *trust* on a conformance-specific gold set. Until both binary sub-flags
  clear the gate on the PO seed, the dim ships `calibrated=false` and the UI labels
  it "unverified self-report".

THE GATE (the P1 ship condition, §6.2):
  Shipping UNCALIBRATED is an ACCEPTED outcome, not a failure (§R2.1). The gate
  prints CALIBRATED (both sub-flags pass on the PO seed) → a human may then set
  motif_conformance_calibrated=true; OR SHIP-UNCALIBRATED (below threshold / gold
  set too small / single-class) → the dim ships labeled-uncalibrated. A genuine
  BUILD failure is only: the harness can't run, the merge clobbers other dims, or
  the advisory dim blocks a commit (covered by the unit guards).

TWO SOURCES (§3.2):
  A — PO seed (the human ground truth, the calibration anchor). The gate decision
      rests on A ALONE (model-as-gold never becomes the metric of record).
  B — strong-model bootstrap (optional, coverage extender). Reported SEPARATELY
      (A-only vs A+B) so the reader sees how much B moved the number.

PANEL SAFETY (§5 / gap5):
  loreweave_eval.panel_safety needs >=2 disjoint judges. A single-model self-host
  CANNOT meet that — the printed note says so plainly. NEVER present a self-host
  kappa as a production metric of record.

PROVIDER RULE: the judge + any strong model resolve via /v1/model-registry/user-
models (no hardcoded model names, no direct SDK — the ai-provider-gate rule). The
judge call goes through the gateway → this script doubles as the cross-service
live-smoke (composition → provider-registry).

Usage (offline gate, no stack — prints SHIP-UNCALIBRATED with the seed it finds):
    python scripts/calibrate_motif_conformance.py --offline
Usage (live, against a running stack — the real calibration + live-smoke):
    python scripts/calibrate_motif_conformance.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow running from the service dir (so `loreweave_eval` + `app` import resolve
# when invoked as a host script against the live stack).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loreweave_eval.calibration import JudgeCalibration, calibrate_judge  # noqa: E402

GW = os.environ.get("LOREWEAVE_GATEWAY", "http://localhost:3123")
GOLD_DIR = Path(__file__).resolve().parent / "motif_conformance_gold"
PO_SEED = GOLD_DIR / "po_seed.jsonl"
BOOTSTRAP = GOLD_DIR / "bootstrap.jsonl"

# The binary trust gate thresholds (the EXISTING calibrate_judge defaults; the
# motif_conformance dim is calibrated only if BOTH sub-flags clear these).
MIN_KAPPA = 0.4
MIN_BALANCED_ACC = 0.75


# ── gold loading (pure) ─────────────────────────────────────────────────────

def load_gold(path: Path) -> list[dict[str, Any]]:
    """Load a gold JSONL, skipping the leading `_comment`/`schema` meta lines and
    blank lines. A row needs scene_text + the two gold flags to count."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if "_comment" in obj or "schema" in obj:
            continue  # the meta header lines
        if "scene_text" not in obj:
            continue
        rows.append(obj)
    return rows


# ── pair building + the gate verdict (pure — unit-testable without a stack) ─

@dataclass
class GateResult:
    n_a: int
    n_b: int
    cal_realized_a: JudgeCalibration | None
    cal_tension_a: JudgeCalibration | None
    cal_realized_ab: JudgeCalibration | None
    cal_tension_ab: JudgeCalibration | None
    calibrated: bool
    verdict: str  # "CALIBRATED" | "SHIP UNCALIBRATED"


def _pairs(rows: list[dict[str, Any]], sub: str):
    """Build (gold_flag, judge_flag) Pairs for one binary sub-flag (`sub` is the
    bare flag name, e.g. "beat_realized"). The gold label is keyed `gold_<sub>`
    (the human truth in the JSONL); the judge label is keyed `<sub>` inside the
    row's `_judge` dict (the judge_motif_conformance output). DROP rows where the
    judge returned None (unjudged — not a label, can't pair it)."""
    out = []
    for r in rows:
        judged = r.get("_judge", {}).get(sub)
        gold = r.get(f"gold_{sub}")
        if judged is None or gold is None:
            continue
        out.append((bool(gold), bool(judged)))
    return out


def compute_gate(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> GateResult:
    """Calibrate each binary sub-flag independently (two different questions, two
    base rates). The DECISION rests on A (the human seed) ALONE; A+B is reported
    for coverage only. `calibrated` ⇔ BOTH A sub-flags pass the binary gate."""
    def _cal(rows, sub):
        if not rows:
            return None
        return calibrate_judge(
            f"motif_conformance.{sub}", _pairs(rows, sub),
            min_kappa=MIN_KAPPA, min_balanced_accuracy=MIN_BALANCED_ACC,
        )

    cal_r_a = _cal(rows_a, "beat_realized")
    cal_t_a = _cal(rows_a, "tension_band_match")
    rows_ab = rows_a + rows_b
    cal_r_ab = _cal(rows_ab, "beat_realized") if rows_b else None
    cal_t_ab = _cal(rows_ab, "tension_band_match") if rows_b else None

    calibrated = bool(cal_r_a and cal_r_a.passed and cal_t_a and cal_t_a.passed)
    return GateResult(
        n_a=len(rows_a), n_b=len(rows_b),
        cal_realized_a=cal_r_a, cal_tension_a=cal_t_a,
        cal_realized_ab=cal_r_ab, cal_tension_ab=cal_t_ab,
        calibrated=calibrated,
        verdict="CALIBRATED" if calibrated else "SHIP UNCALIBRATED",
    )


# ── reporting (pure) ────────────────────────────────────────────────────────

def _fmt(cal: JudgeCalibration | None) -> str:
    if cal is None:
        return "n/a (no rows)"
    ka = "—" if cal.cohen_kappa is None else f"{cal.cohen_kappa:.3f}"
    ba = "—" if cal.balanced_accuracy is None else f"{cal.balanced_accuracy:.3f}"
    return (f"kappa={ka} balanced_acc={ba} n={cal.n_pairs} "
            f"{'PASS' if cal.passed else 'fail'} conf={cal.confusion}")


def print_report(g: GateResult, *, judge_label: str, distinct_judge: bool) -> None:
    print("=" * 78)
    print("MOTIF CONFORMANCE CALIBRATION GATE (W5 / §R2.1)")
    print("=" * 78)
    print(f"gold: Source A (PO seed) n={g.n_a}   Source B (bootstrap) n={g.n_b}")
    print(f"judge model: {judge_label}")
    print()
    print("A-only (the human ground truth — THIS is the decision basis):")
    print(f"  beat_realized      : {_fmt(g.cal_realized_a)}")
    print(f"  tension_band_match : {_fmt(g.cal_tension_a)}")
    if g.n_b:
        print("A+B (coverage extender — REPORTED ONLY, never the metric of record):")
        print(f"  beat_realized      : {_fmt(g.cal_realized_ab)}")
        print(f"  tension_band_match : {_fmt(g.cal_tension_ab)}")
    print()
    # panel-safety note (§5 / gap5) — ALWAYS printed, travels with every report.
    if not distinct_judge:
        print("panel_safety: SINGLE-MODEL self-host — the drafter would also be the "
              "judge. Conformance is SKIPPED entirely (no distinct critic); better "
              "no signal than a self-graded one.")
    else:
        print("panel_safety: a distinct-but-still-LOCAL judge does NOT meet the "
              ">=2-disjoint-judge metric-of-record bar (loreweave_eval.panel_safety). "
              "Treat any kappa here as a SELF-REPORT, not a production metric.")
    print()
    if g.verdict == "CALIBRATED":
        print(f"GATE: CALIBRATED — both sub-flags kappa>={MIN_KAPPA} & "
              f"balanced-acc>={MIN_BALANCED_ACC} on the PO seed (n={g.n_a}).")
        print("      → a human MAY now set motif_conformance_calibrated=true "
              "(mind the panel-safety note above).")
    else:
        why = []
        if g.n_a < 2:
            why.append(f"gold set too small (n={g.n_a})")
        for sub, cal in (("beat_realized", g.cal_realized_a),
                         ("tension_band_match", g.cal_tension_a)):
            if cal is None:
                why.append(f"{sub}: no pairs")
            elif cal.cohen_kappa is None:
                why.append(f"{sub}: single-class (need both classes — add drift negatives)")
            elif not cal.passed:
                why.append(f"{sub}: below threshold")
        print(f"GATE: SHIP UNCALIBRATED — {'; '.join(why) or 'thresholds not met'}.")
        print("      → the dim ships calibrated=false (UI-labeled 'unverified'); "
              "enlarge/label the gold set or tune the prompt. This is an ACCEPTED "
              "P1 ship outcome (§R2.1), not a build failure.")
    print("=" * 78)


# ── live run (the cross-service live-smoke) ─────────────────────────────────

def _jwt_sub(token: str) -> str:
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))["sub"]


def _run_live(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> tuple[str, bool]:
    """Resolve the judge model via provider-registry + run judge_motif_conformance
    over every gold scene (the gateway round-trip = the live-smoke). Mutates each
    row in place with `_judge`. Returns (judge_label, distinct_judge)."""
    import asyncio
    import urllib.request

    from app.clients.llm_client import get_llm_client
    from app.engine.motif_conformance import judge_motif_conformance
    from app.packer.profile import NEUTRAL

    def _req(method, path, token=None, body=None, timeout=600):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(GW + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode().strip()
        return json.loads(raw) if raw else {}

    token = _req("POST", "/v1/auth/login",
                 body={"email": "claude-test@loreweave.dev", "password": "Claude@Test2026"})["access_token"]
    user_id = _jwt_sub(token)
    chat = [m for m in _req("GET", "/v1/model-registry/user-models?capability=chat", token)["items"]
            if m["is_active"]]
    if not chat:
        raise RuntimeError("no active chat model for the test account")
    judge_m = chat[0]
    # a distinct judge exists iff there are >=2 chat models (so the judge can differ
    # from a drafter) — the panel-safety dial.
    distinct_judge = len(chat) >= 2

    client = get_llm_client()

    async def _go() -> None:
        for r in rows_a + rows_b:
            band = r.get("tension_band") or [0, 100]
            out = await judge_motif_conformance(
                client, user_id=user_id, model_source="user_model",
                model_ref=judge_m["user_model_id"],
                beat_intent=r.get("beat_intent", ""), beat_key=r.get("beat_key", ""),
                motif_name=r.get("motif_name", ""),
                tension_band=(int(band[0]), int(band[1])),
                expected_roles=r.get("expected_roles", []),
                passage=r.get("scene_text", ""), profile=NEUTRAL,
            )
            r["_judge"] = out

    asyncio.run(_go())
    return judge_m.get("provider_model_name", judge_m["user_model_id"]), distinct_judge


def main() -> int:
    ap = argparse.ArgumentParser(description="motif conformance calibration gate")
    ap.add_argument("--offline", action="store_true",
                    help="skip the live judge run; prints the gate on the seed shape only")
    args = ap.parse_args()

    rows_a = load_gold(PO_SEED)
    rows_b = load_gold(BOOTSTRAP)

    judge_label = "(offline — no judge run)"
    distinct_judge = False
    if not args.offline:
        try:
            judge_label, distinct_judge = _run_live(rows_a, rows_b)
            print(f"live smoke: judge_motif_conformance ran a real conformance verdict "
                  f"on {len(rows_a) + len(rows_b)} gold scenes (composition→provider-registry).\n")
        except Exception as exc:  # noqa: BLE001 — the gate must still print a verdict
            print(f"live infra unavailable: {exc}\n  → falling back to OFFLINE gate "
                  "(SHIP UNCALIBRATED unless the seed carries pre-recorded _judge).\n")

    g = compute_gate(rows_a, rows_b)
    print_report(g, judge_label=judge_label, distinct_judge=distinct_judge)
    # The gate NEVER fails the process on SHIP-UNCALIBRATED (an accepted outcome).
    # Exit 0 always; the verdict is the signal. (A non-zero exit is reserved for a
    # genuine harness crash, which raises before reaching here.)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
