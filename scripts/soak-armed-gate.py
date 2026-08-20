#!/usr/bin/env python3
"""soak-armed-gate — refuse to read "zero failures" as "soaking fine".

T25a named the hazard in the plan and then the plan fell into it:

    "A gate that reads zero because nothing is wired looks exactly like a gate that
     reads zero because nothing failed. That is the most dangerous shape in this whole
     phase and it must not be read as a pass."

`D-T25B-SOAK` recorded its first half DONE on 2026-08-12 — *variable set, dual-write
live, writes proven to reach the secondary* — and its second half as *"wall-clock and
cannot be worked, only waited"*. Measured 2026-08-21: `KNOWLEDGE_VECTOR_DB_URL` is unset
on the dev stack, the `knowledge_vector_dual_write_total` family is absent from its
`/metrics` entirely, and the secondary holds **0 rows in every table** while the graph
holds 1051 passages. Nine days of waiting against a switch that was off.

The distinction this gate exists to make, and which no counter can make alone:

    DISARMED    the metric family is ABSENT -> the store was never constructed, so the
                variable is unset. Zero here means "not running", not "not failing".
    ARMED_IDLE  the family is present and every counter is 0 -> the store exists but no
                write has reached it. Still not evidence.
    SOAKING     writes have landed and `secondary_failed` is 0. The only passing state.
    FAILING     `secondary_failed` is non-zero.

Usage
    python scripts/soak-armed-gate.py --url http://localhost:8216/metrics
    python scripts/soak-armed-gate.py --file exposition.txt [--min-writes N]
    python scripts/soak-armed-gate.py --selftest        # offline, no stack needed
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request

FAMILY = "knowledge_vector_dual_write_total"

#: `_created` gauges are emitted by prometheus_client for every counter the moment it is
#: REGISTERED, so they exist even when nothing has ever been written. Counting them as
#: evidence of arming would make DISARMED unreachable — the exact collapse this gate
#: exists to prevent — so the family probe deliberately ignores them.
_LINE = re.compile(
    r"^" + re.escape(FAMILY) + r"\{(?P<labels>[^}]*)\}\s+(?P<value>[0-9.eE+-]+)\s*$"
)
_LABEL = re.compile(r'(\w+)="([^"]*)"')

DISARMED = "DISARMED"
ARMED_IDLE = "ARMED_IDLE"
SOAKING = "SOAKING"
FAILING = "FAILING"


def parse(text: str) -> tuple[bool, dict[tuple[str, str], float]]:
    """Return (family_present, {(outcome, scope): value}).

    `family_present` is decided by a real sample line, not by a substring match on the
    name: a `# HELP`/`# TYPE` header is emitted alongside the `_created` gauges and would
    otherwise make an unwired service look armed.
    """
    counters: dict[tuple[str, str], float] = {}
    present = False
    for raw in text.splitlines():
        m = _LINE.match(raw.strip())
        if not m:
            continue
        present = True
        labels = dict(_LABEL.findall(m.group("labels")))
        counters[(labels.get("outcome", "?"), labels.get("scope", "?"))] = float(
            m.group("value")
        )
    return present, counters


def classify(
    present: bool, counters: dict[tuple[str, str], float], *, min_writes: int = 1
) -> tuple[str, str]:
    if not present:
        return DISARMED, (
            f"the `{FAMILY}` family is ABSENT — the dual-write store was never "
            "constructed, so KNOWLEDGE_VECTOR_DB_URL is unset. A soak is not running, "
            "and zero here is not a passing measurement."
        )
    failed = sum(v for (outcome, _), v in counters.items() if outcome == "secondary_failed")
    landed = sum(v for (outcome, _), v in counters.items() if outcome in ("both", "primary_only"))
    also_failed = sum(v for (outcome, _), v in counters.items() if outcome == "primary_failed")
    total = landed + failed + also_failed
    if failed:
        return FAILING, f"secondary_failed = {failed:g} across {total:g} write(s)"
    if total < min_writes:
        return ARMED_IDLE, (
            f"the store is wired but only {total:g} write(s) have reached it "
            f"(need >= {min_writes}). `secondary_failed = 0` is vacuous until writes flow."
        )
    return SOAKING, f"{total:g} write(s) landed, secondary_failed = 0"


_SYNTHETIC = {
    "an unwired service (family absent)": ("", DISARMED),
    "only the _created gauges prometheus emits at registration": (
        f'{FAMILY}_created{{outcome="both",scope="passage"}} 1.78e+09\n'
        f"# HELP {FAMILY} dual write outcomes\n# TYPE {FAMILY} counter\n",
        DISARMED,
    ),
    "wired but no write has reached it": (
        f'{FAMILY}{{outcome="both",scope="passage"}} 0.0\n'
        f'{FAMILY}{{outcome="secondary_failed",scope="passage"}} 0.0\n',
        ARMED_IDLE,
    ),
    "writes landing, none failed": (
        f'{FAMILY}{{outcome="both",scope="passage"}} 1051.0\n'
        f'{FAMILY}{{outcome="secondary_failed",scope="passage"}} 0.0\n',
        SOAKING,
    ),
    "a failing secondary": (
        f'{FAMILY}{{outcome="both",scope="passage"}} 900.0\n'
        f'{FAMILY}{{outcome="secondary_failed",scope="passage"}} 3.0\n',
        FAILING,
    ),
    "failures on a scope other than the one that succeeded": (
        f'{FAMILY}{{outcome="both",scope="passage"}} 900.0\n'
        f'{FAMILY}{{outcome="secondary_failed",scope="entity"}} 2.0\n',
        FAILING,
    ),
}


def selftest() -> int:
    print("soak-armed-gate - selftest (offline)")
    bad = 0
    for name, (text, want) in _SYNTHETIC.items():
        got, _why = classify(*parse(text))
        ok = got == want
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: expected {want}, got {got}")
    # The distinction the whole gate exists for, asserted as its own case.
    disarmed, _ = classify(*parse(""))
    idle, _ = classify(*parse(f'{FAMILY}{{outcome="both",scope="passage"}} 0.0\n'))
    ok = disarmed != idle
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  DISARMED and ARMED_IDLE are distinct verdicts")
    print("\n  all checks passed" if not bad else f"\n  {bad} check(s) FAILED")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", help="a /metrics endpoint to read")
    ap.add_argument("--file", help="a file holding metrics exposition text")
    ap.add_argument("--min-writes", type=int, default=1,
                    help="writes required before SOAKING is claimable (default 1)")
    ap.add_argument("--require-soaking", action="store_true",
                    help="exit non-zero unless the verdict is SOAKING")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not (a.url or a.file):
        ap.error("one of --url, --file or --selftest is required")

    if a.url:
        with urllib.request.urlopen(a.url, timeout=10) as r:
            text = r.read().decode("utf-8", "replace")
        source = a.url
    else:
        text = open(a.file, encoding="utf-8", errors="replace").read()
        source = a.file

    verdict, why = classify(*parse(text), min_writes=a.min_writes)
    print(f"[soak-armed-gate] {verdict} — {why}")
    print(f"[soak-armed-gate] source: {source}")
    if a.require_soaking and verdict != SOAKING:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
