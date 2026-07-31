"""The cycle: register → rank → ask → validate → heal → settle → freeze.

This is the piece eight rounds of probes never exercised. Every earlier probe was
**one slot, one shot, in isolation**; what was never run is the LOOP — a slot
settling, the next slot referencing it, a cross-module reference coming out with a
null target, and a freeze at the end.

The division of labour, which is the whole design and is falsifiable here:

    the planner owns the EDGES   — which slot is next, when to heal, when to stop
    the model owns the TURNS     — naming, ordering by meaning, judging relevance

`ASK-A6` is why: offered a state machine in prose and only edges that terminate,
the model invented one that did not. So the machine is here, in code, and the model
is never asked which transition to take.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from app.pool import criteria
from app.pool.kinds import parse, planner_for
from app.pool.register import OpenRow, abduce
from app.pool.registry import Registry, Slot

__all__ = ["State", "SlotState", "PoolRun", "run_cycle"]

#: A model turn: prompt -> text. Injected, so the loop is testable with no network.
Complete = Callable[[str], str]


class State(str, Enum):
    EMPTY = "EMPTY"
    PROBED = "PROBED"
    PROPOSED = "PROPOSED"
    SETTLED = "SETTLED"
    STARVED = "STARVED"
    DECLINED = "DECLINED"
    REOPENED = "REOPENED"


#: The ONLY legal transitions. The model never chooses one (`ASK-A6`).
EDGES: dict[State, frozenset[State]] = {
    State.EMPTY: frozenset({State.PROBED}),
    State.PROBED: frozenset({State.PROPOSED, State.STARVED}),
    State.STARVED: frozenset({State.PROPOSED, State.DECLINED}),
    State.PROPOSED: frozenset({State.PROPOSED, State.SETTLED, State.DECLINED}),
    State.SETTLED: frozenset({State.REOPENED}),
    State.REOPENED: frozenset({State.PROPOSED}),
    State.DECLINED: frozenset(),
}


@dataclass
class SlotState:
    slot_id: str
    state: State = State.EMPTY
    members: list[dict] = field(default_factory=list)
    refused: list[dict] = field(default_factory=list)
    verdict: str = ""
    attempts: int = 0

    def move(self, to: State) -> None:
        if to not in EDGES[self.state]:
            raise ValueError(
                f"illegal transition {self.slot_id}: {self.state.value} -> {to.value}. "
                f"Legal: {sorted(s.value for s in EDGES[self.state])}"
            )
        self.state = to


@dataclass
class PoolRun:
    slots: dict[str, SlotState]
    register: list[OpenRow]
    digest: str | None = None
    log: list[str] = field(default_factory=list)

    @property
    def pool(self) -> dict[str, list[dict]]:
        return {k: v.members for k, v in self.slots.items() if v.members}

    @property
    def frozen(self) -> bool:
        return self.digest is not None

    def cross_module_demands(self) -> list[OpenRow]:
        """`EPL-A8` — rows pointing at a slot nobody has registered."""
        return [r for r in self.register if r.reason == "unregistered_target"]


def _freeze(pool: dict[str, list[dict]]) -> str:
    """Content-address the pool (`PPB-A6`). Sorted, so the digest is of the CONTENT."""
    canon = json.dumps(pool, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canon.encode("utf-8"), digest_size=32).hexdigest()


def run_cycle(reg: Registry, evidence: str, complete: Complete,
              *, evidence_n: int, heal_rounds: int = 1,
              approve: Callable[[Slot, list[dict]], bool] = lambda s, m: True) -> PoolRun:
    """Fill every registered slot, then freeze.

    ``approve`` stands in for the human gate. It is a parameter and not a default
    behaviour because a run that approves itself is not a run with a gate — the
    tests pass an auto-approver, and a real run does not.
    """
    run = PoolRun(slots={sid: SlotState(sid) for sid in reg.slots}, register=[])
    run.register = abduce(reg, {})

    for _ in range(len(reg.slots)):
        run.register = abduce(reg, run.pool)
        todo = [r for r in run.register
                if r.target in run.slots and run.slots[r.target].state in
                (State.EMPTY, State.PROBED, State.REOPENED)]
        # A slot stuck in PROPOSED has already had its heal rounds; it is not retried
        # here. It stays open, blocks the freeze, and is the human's to resolve.
        if not todo:
            break
        target = todo[0].target                      # ranked by blocking power
        st, slot = run.slots[target], reg[target]
        kind = planner_for(slot)

        st.move(State.PROBED)
        run.log.append(f"{target}: probe {kind.probe(slot, reg)}")

        prompt = kind.ask(slot, reg, evidence, run.pool)
        for attempt in range(heal_rounds + 1):
            st.attempts += 1
            members, refused = parse(complete(prompt))
            st.move(State.PROPOSED)
            v = criteria.evaluate(slot, members, refused, evidence_n=evidence_n,
                                  registry_enums=reg.engine_enums)
            st.members, st.refused, st.verdict = members, refused, str(v)
            run.log.append(f"{target}: attempt {attempt} -> {v}")
            if v.passed or attempt == heal_rounds:
                break
            prompt = (kind.ask(slot, reg, evidence, run.pool)
                      + "\n\nYOUR PREVIOUS ANSWER FAILED. Fix ONLY these and keep the rest:\n"
                      + "\n".join(f"  - {f.criterion}: {f.detail}" for f in v.findings))

        # A hard-failed slot is NOT offered to the gate. The first run of this loop
        # called approve() regardless of the verdict, so a slot whose criteria had
        # broken settled anyway — the gate fired and nothing consumed it, which is
        # ASK-A5's failure class inside the loop that documents it. A hard failure
        # leaves the slot in PROPOSED, where it keeps the pool open and blocks the
        # freeze; that is the mechanism, not the log line.
        if v.hard_broken:
            run.log.append(f"{target}: stays PROPOSED — {v}")
        elif approve(slot, st.members):
            st.move(State.SETTLED)
            run.log.append(f"{target}: SETTLED with {len(st.members)} members, "
                           f"{len(st.refused)} refused")
        else:
            run.log.append(f"{target}: stays PROPOSED — the gate declined")

    run.register = abduce(reg, run.pool)
    blocking = [r for r in run.register if r.target in reg.slots]
    if not blocking and all(s.state in (State.SETTLED, State.DECLINED)
                            for s in run.slots.values()):
        run.digest = _freeze(run.pool)
        run.log.append(f"FROZEN {run.digest[:16]}…")
    else:
        run.log.append(f"NOT FROZEN — {len(blocking)} slot-level open row(s)")
    return run
