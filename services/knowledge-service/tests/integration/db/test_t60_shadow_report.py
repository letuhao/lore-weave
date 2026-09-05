"""T60 — print the shadow coverage report, so `cutover_permitted` is EVIDENCE not an assertion.

`QC-7` signed `cutover_permitted: True` as a datum and `T43` recorded that AGE *"cannot clear
the conformance floor at all"* because it refused two event writes and one fact write. T58/T59
implemented all three, so the number has to be re-derived rather than re-quoted — which is the
whole failure mode this plan keeps finding (`A14`'s stale 28, `T25j`'s stale precondition).

This is deliberately a REPORT, not a second copy of the floor rule: the assertions live in
`test_the_seed_corpus_reaches_every_operation`, and duplicating them here would be one concept
with two readers that can disagree.
"""

from __future__ import annotations

import random
import uuid

import pytest

# The `shadow` FIXTURE has to be imported too — it is defined in the differential module,
# not in a conftest, so importing only the helpers leaves pytest unable to resolve it.
from .test_shadow_differential import (  # noqa: F401
    OPERATIONS,
    SEEDS,
    _run_sequence,
    shadow,
)


@pytest.mark.asyncio
async def test_REPORT_the_shadow_coverage_and_cutover_verdict(shadow, capsys):
    for seed in SEEDS:
        rng = random.Random(seed)
        u, p = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
        await _run_sequence(shadow, rng, u, p)
    rep = shadow.coverage_report()
    uncovered = sorted(
        op for op in OPERATIONS if not rep["operations"][op]["observations"]
    )
    with capsys.disabled():
        print()
        print(f"  === shadow coverage: {getattr(shadow, 'name', '?')} ===")
        print(f"  cutover_permitted : {rep.get('cutover_permitted')}")
        print(f"  operations        : {len(OPERATIONS)}")
        print(f"  uncovered         : {uncovered or 'NONE'}")
        print(f"  blocked_by        : {rep.get('blocked_by')}")
        ops = rep["operations"]
        tot_obs = sum(o["observations"] for o in ops.values())
        tot_agr = sum(o["agreed"] for o in ops.values())
        tot_div = sum(o["diverged"] for o in ops.values())
        print(f"  totals            : {tot_obs} observations, {tot_agr} agreed, "
              f"{tot_div} diverged")
        for name in sorted(ops):
            o = ops[name]
            flag = "" if o["observations"] else "   <- UNCOVERED"
            print(f"    {name:26s} obs={o['observations']:4d} agreed={o['agreed']:4d} "
                  f"diverged={o['diverged']:3d}{flag}")

    # ⚠️ A REPORT that cannot fail is not a test, and this suite has caught that shape twice
    # today already. The teeth: the report must cover exactly the port's operation set. When
    # the port grows a 22nd operation, this reds until the shadow actually observes it —
    # which is the failure `blocked_by` exists for, one level up, and the reason a coverage
    # number is worth printing at all.
    assert set(ops) == set(OPERATIONS), (
        f"the shadow report covers {sorted(set(ops) ^ set(OPERATIONS))} differently from the "
        f"port's operation set — a number over the wrong denominator"
    )
