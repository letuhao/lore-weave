#!/usr/bin/env python3
"""soak-armed-gate — refuse to read "zero failures" as "soaking fine".

T25a named the hazard in the plan and then the plan fell into it:

    "A gate that reads zero because nothing is wired looks exactly like a gate that
     reads zero because nothing failed. That is the most dangerous shape in this whole
     phase and it must not be read as a pass."

`D-T25B-SOAK` recorded its first half DONE on 2026-08-12 — *variable set, dual-write
live, writes proven to reach the secondary* — and its second half as *"wall-clock and
cannot be worked, only waited"*. Measured 2026-08-21: the `knowledge_vector_dual_write_total`
family was absent from `/metrics` entirely and the secondary held **0 rows in every table**
while the graph held 1051 passages. Nine days of waiting against a switch that was off.

⚠️ THE FIRST VERSION OF THIS GATE NAMED THE WRONG CAUSE, and then the plan copied it.
It read the family's absence as *"the store was never constructed, so
KNOWLEDGE_VECTOR_DB_URL is unset"*. The variable had been set in `infra/.env` since
2026-08-12; the running IMAGE was built before the metric existed, so the absence measured
the code's AGE, not the config. Recreating the container changed nothing until the image
was rebuilt. Worse in the other direction: `metrics.py` PRE-SEEDS every scope x outcome
series at import, so a service with the DSN explicitly cleared exposes all eight lines at
0.0 — proved by running current code with it unset — and the old gate called that
ARMED_IDLE. Family presence could never decide arming, and reading it that way is exactly
the "zero because nothing is wired" collapse T25a warned about, wearing the opposite mask.

Arming is therefore read from its OWN signal, `knowledge_vector_dual_write_armed`, set
from configuration at startup:

    DISARMED       the arming gauge reads 0 (or neither signal is exposed at all) ->
                   nothing writes to the secondary. Zero means "not running".
    INDETERMINATE  the family is exposed but the arming gauge is ABSENT -> a service too
                   old to publish arming, whose pre-seeded zeros are identical either
                   way. Unreadable, and NOT a pass.
    ARMED_IDLE     armed, but no write has reached it. Still not evidence.
    SOAKING        armed, writes have landed, `secondary_failed` is 0. The only pass.
    FAILING        `secondary_failed` is non-zero. Exits non-zero on its own.

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

#: The ARMING signal, and the reason this gate was wrong on 2026-08-21. `FAMILY` is
#: pre-seeded at import (`metrics.py` walks every scope x outcome and calls `.labels()`),
#: so an UNARMED service running current code exposes all eight series at 0.0 — byte for
#: byte what an armed service that has not yet been written to exposes. Family presence
#: therefore proves only "the code is recent", never "the secondary is configured".
ARMED_GAUGE = "knowledge_vector_dual_write_armed"

#: `_created` gauges are emitted by prometheus_client for every counter the moment it is
#: REGISTERED, so they exist even when nothing has ever been written. Counting them as
#: evidence of arming would make DISARMED unreachable — the exact collapse this gate
#: exists to prevent — so the family probe deliberately ignores them.
_LINE = re.compile(
    r"^" + re.escape(FAMILY) + r"\{(?P<labels>[^}]*)\}\s+(?P<value>[0-9.eE+-]+)\s*$"
)
_LABEL = re.compile(r'(\w+)="([^"]*)"')
#: A no-label gauge is exposed bare (`name 0.0`); some clients emit `name{} 0.0`. Anchored
#: on whitespace-then-value so a hypothetical `_created`/`_total` sibling cannot match.
_ARMED = re.compile(
    r"^" + re.escape(ARMED_GAUGE) + r"(?:\{\s*\})?\s+(?P<value>[0-9.eE+-]+)\s*$"
)

DISARMED = "DISARMED"
#: Family present, arming gauge ABSENT — a service too old to publish arming. Its counter
#: reads 0.0 whether or not it is armed, so no verdict can be drawn. Deliberately NOT
#: folded into ARMED_IDLE: that fold is what let an unarmed stack read as a soaking one.
INDETERMINATE = "INDETERMINATE"
ARMED_IDLE = "ARMED_IDLE"
SOAKING = "SOAKING"
FAILING = "FAILING"


def parse(text: str) -> tuple[bool, dict[tuple[str, str], float], float | None]:
    """Return (family_present, {(outcome, scope): value}, armed_or_None).

    `armed` is None when the gauge is absent from the exposition at all — which is a
    THIRD state, not a synonym for zero: a service predating the arming signal cannot
    report it, and its pre-seeded counter looks identical armed or not.

    `family_present` is decided by a real sample line, not by a substring match on the
    name: a `# HELP`/`# TYPE` header is emitted alongside the `_created` gauges and would
    otherwise make an unwired service look armed.
    """
    counters: dict[tuple[str, str], float] = {}
    present = False
    armed: float | None = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _LINE.match(line)
        if m:
            present = True
            labels = dict(_LABEL.findall(m.group("labels")))
            counters[(labels.get("outcome", "?"), labels.get("scope", "?"))] = float(
                m.group("value")
            )
            continue
        a = _ARMED.match(line)
        if a:
            armed = float(a.group("value"))
    return present, counters, armed


def classify(
    present: bool,
    counters: dict[tuple[str, str], float],
    armed: float | None = None,
    *,
    min_writes: int = 1,
) -> tuple[str, str]:
    """Decide arming FIRST, from the arming gauge, and only then read the counters.

    The order is the fix. The original gate inferred arming from family presence, and on
    2026-08-21 that inference was simply false in both directions: the family was absent
    while `KNOWLEDGE_VECTOR_DB_URL` had been set for nine days (the running image was too
    old to carry the metric), and a service with the DSN explicitly cleared publishes all
    eight series at 0.0 (proved by running current code with it unset). Presence measures
    the code's age; it has never measured arming.
    """
    if armed is not None and not armed:
        return DISARMED, (
            f"`{ARMED_GAUGE}` reads 0 — KNOWLEDGE_VECTOR_DB_URL is not configured, so no "
            "vector write reaches the secondary. Every counter below is zero because "
            "nothing is running, which is not a passing measurement."
        )
    if armed is None:
        if not present:
            return DISARMED, (
                f"neither `{ARMED_GAUGE}` nor the `{FAMILY}` family is exposed — this "
                "service predates the dual-write entirely. A soak is not running, and "
                "zero here is not a passing measurement."
            )
        return INDETERMINATE, (
            f"the `{FAMILY}` family is exposed but `{ARMED_GAUGE}` is ABSENT — this "
            "service predates the arming signal, and the family is PRE-SEEDED, so its "
            "zeros are identical armed or not. Arming cannot be determined from this "
            "exposition; rebuild the service before reading the soak."
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


#: The full PRE-SEEDED family exactly as `metrics.py` emits it at import: every scope x
#: outcome at 0.0, before any write. This text is IDENTICAL on an armed and an unarmed
#: service — which is the whole reason the arming gauge exists — so every fixture below
#: pairs it with an explicit arming line rather than letting presence stand in for it.
_PRESEEDED = "".join(
    f'{FAMILY}{{outcome="{o}",scope="{s}"}} 0.0\n'
    for s in ("passage", "entity")
    for o in ("both", "primary_only", "secondary_failed", "primary_failed")
)


def _armed(value: int) -> str:
    return f"{ARMED_GAUGE} {float(value)}\n"


_SYNTHETIC = {
    "a service too old for either signal": ("", DISARMED),
    "only the _created gauges prometheus emits at registration": (
        f'{FAMILY}_created{{outcome="both",scope="passage"}} 1.78e+09\n'
        f"# HELP {FAMILY} dual write outcomes\n# TYPE {FAMILY} counter\n",
        DISARMED,
    ),
    # ── the live 2026-08-21 defect, frozen as a fixture ──────────────────────
    # Current code with KNOWLEDGE_VECTOR_DB_URL cleared. The OLD gate read this as
    # ARMED_IDLE and would have let the T25 cutover proceed against a secondary that
    # nothing was writing to.
    "current code with the DSN UNSET (pre-seeded zeros, armed=0)": (
        _PRESEEDED + _armed(0),
        DISARMED,
    ),
    "armed, but no write has reached it": (_PRESEEDED + _armed(1), ARMED_IDLE),
    "armed with writes landing, none failed": (
        _armed(1)
        + f'{FAMILY}{{outcome="both",scope="passage"}} 1051.0\n'
        + f'{FAMILY}{{outcome="secondary_failed",scope="passage"}} 0.0\n',
        SOAKING,
    ),
    "armed with a failing secondary": (
        _armed(1)
        + f'{FAMILY}{{outcome="both",scope="passage"}} 900.0\n'
        + f'{FAMILY}{{outcome="secondary_failed",scope="passage"}} 3.0\n',
        FAILING,
    ),
    "armed, failures on a scope other than the one that succeeded": (
        _armed(1)
        + f'{FAMILY}{{outcome="both",scope="passage"}} 900.0\n'
        + f'{FAMILY}{{outcome="secondary_failed",scope="entity"}} 2.0\n',
        FAILING,
    ),
    # A service new enough to pre-seed the counter but too old to publish arming. Not a
    # pass and not a fail — unreadable, and saying so is the point.
    "family present but no arming gauge": (_PRESEEDED, INDETERMINATE),
    "a bare `{}` gauge rendering is still read": (
        _PRESEEDED + f"{ARMED_GAUGE}{{}} 1.0\n",
        ARMED_IDLE,
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

    # ── the properties the fixtures alone cannot pin ─────────────────────────
    # 1. The distinction the whole gate exists for.
    disarmed, _ = classify(*parse(_PRESEEDED + _armed(0)))
    idle, _ = classify(*parse(_PRESEEDED + _armed(1)))
    ok = disarmed == DISARMED and idle == ARMED_IDLE and disarmed != idle
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  DISARMED and ARMED_IDLE are distinct verdicts")

    # 2. The regression itself: BYTE-IDENTICAL counters, opposite verdicts, decided
    #    solely by the arming gauge. If a future edit reinstates presence-inference this
    #    goes red, because presence is the same on both sides.
    a_text, b_text = _PRESEEDED + _armed(0), _PRESEEDED + _armed(1)
    a_present, a_counters, _ = parse(a_text)
    b_present, b_counters, _ = parse(b_text)
    ok = (a_present, a_counters) == (b_present, b_counters) and classify(
        *parse(a_text)
    )[0] != classify(*parse(b_text))[0]
    bad += not ok
    print(
        f"  {'PASS' if ok else 'FAIL'}  identical counters + opposite arming "
        f"-> opposite verdicts"
    )

    # 3. An absent gauge must never borrow the armed reading.
    ok = classify(*parse(_PRESEEDED))[0] == INDETERMINATE
    bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  a missing arming gauge is not read as armed")

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
    # FAILING exits non-zero WITHOUT --require-soaking. The other verdicts are legitimate
    # states on the way to a soak (not armed yet, armed but unexercised) and an operator
    # polling for progress should not have to treat them as errors. `secondary_failed` is
    # different in kind: it means the secondary is MISSING ROWS the primary accepted, and
    # a cutover-guarding gate that reports that and still exits 0 is a check whose worst
    # finding a caller can ignore by default.
    if verdict == FAILING:
        return 1
    if a.require_soaking and verdict != SOAKING:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
