"""The open-decision register — an ABDUCTION over the pool (``PPL-A8``).

The register is **not a maintained checklist**. It is the answer to *"the pool is
not closed — what minimal set of facts would close it?"*, which is abduction, and
that means it is a **query result**: change a rule and the register changes with
it, because it was never stored.

Why clingo. Answer Set Programming is Datalog plus the two things this needs and
Datalog lacks — choice rules (which encode abducibles directly) and optimisation
(which ranks the register by blocking power in the same solve). The standard
caveat, that ASP grounds and so explodes on large domains, does not bind here:
the domain is tens of slots and a few hundred members.

`EPL-A8` is the load-bearing part and it needs no protocol of its own: a reference
whose target slot is not registered, or whose target member does not exist, is a
row with a null target. That single fact is how a decision in one module opens a
decision in another.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pool.registry import Registry, Slot

__all__ = ["OpenRow", "abduce", "PROGRAM"]

#: The rules. Everything the register knows is here; nothing is computed in Python
#: except turning the pool into facts and reading the answer set back.
PROGRAM = """
% ── a slot with no approved members is open ───────────────────────────────
open(needs_members, S) :- slot(S), not has_member(S).
has_member(S) :- member(S, _).

% ── a slot below its own floor is open ────────────────────────────────────
open(below_floor, S) :- slot(S), arity_min(S, Lo), count(S, N), N < Lo.

% ── a reference whose TARGET SLOT is not registered (EPL-A8, cross-module) ─
open(unregistered_target, T) :- ref_field(S, F, T), not slot(T).

% ── a reference whose target MEMBER does not exist ────────────────────────
open(dangling_ref, T) :- ref(S, M, F, T, TM), slot(T), not member(T, TM).

% ── blocking power: how many other open rows this one would clear ─────────
blocks(T, N) :- open(_, T), N = #count { S,F : ref_field(S, F, T) }.

% ── a slot is closed when it has members and nothing points into a hole ───
closed(S) :- slot(S), has_member(S), not open(_, S).

#show open/2.
#show blocks/2.
#show closed/1.
"""


@dataclass(frozen=True)
class OpenRow:
    reason: str
    target: str
    blocks: int = 0

    def __str__(self) -> str:
        b = f"  (blocks {self.blocks})" if self.blocks else ""
        return f"OPEN [{self.reason}] {self.target}{b}"


def _term(value: object) -> str:
    """Quote a MODEL-SUPPLIED value as an ASP string term.

    This is the boundary where model text would otherwise become program text, and
    a live run found it the hard way. A member code of ``24_pearls`` is a syntax
    error; the dangerous one is ``Blade``, which parses fine and becomes an ASP
    VARIABLE — the register would then be solving a different question than the one
    it was asked, with no error to show for it.

    The criteria reject both shapes before a slot may settle. That is the healing
    layer and it is not this layer: a validator the register DEPENDS ON for its own
    parsing is one adjacent decision away from being defeated, which is exactly the
    third shape in `NV`. Quoting removes the dependency instead of documenting it.
    """
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s.replace("\n", " ") + '"'


def _facts(reg: Registry, pool: dict[str, list[dict]]) -> list[str]:
    """Turn the registry + the filled pool into ASP facts. No rules here.

    Slot ids and field names go in BARE — they come from the registry, which the
    loader validates as identifiers. Everything a model produced goes in QUOTED.
    """
    out: list[str] = []
    for sid, slot in reg.slots.items():
        out.append(f"slot({sid}).")
        out.append(f"arity_min({sid},{slot.arity[0]}).")
        for f in slot.refs():
            out.append(f"ref_field({sid},{f.name},{f.target_slot}).")
    for sid, members in pool.items():
        out.append(f"count({sid},{len(members)}).")
        for m in members:
            code = m.get("code")
            if not code:
                continue
            out.append(f"member({sid},{_term(code)}).")
            body = m.get("body") or {}
            slot = reg.slots.get(sid)
            for f in (slot.refs() if slot else ()):
                val = body.get(f.name)
                for target_member in (val if isinstance(val, list) else [val] if val else []):
                    out.append(f"ref({sid},{_term(code)},{f.name},{f.target_slot},"
                               f"{_term(target_member)}).")
    return out


def abduce(reg: Registry, pool: dict[str, list[dict]]) -> list[OpenRow]:
    """Return the open-decision register, ranked by blocking power (`PPL-A6.1`)."""
    import clingo  # imported here so the module is importable without the solver

    ctl = clingo.Control(["--warn=none"])
    ctl.add("base", [], "\n".join(_facts(reg, pool)) + "\n" + PROGRAM)
    ctl.ground([("base", [])])

    opens: list[tuple[str, str]] = []
    blocks: dict[str, int] = {}

    def on_model(model: clingo.Model) -> None:
        opens.clear()
        blocks.clear()
        for sym in model.symbols(shown=True):
            if sym.name == "open":
                opens.append((str(sym.arguments[0]), str(sym.arguments[1])))
            elif sym.name == "blocks":
                blocks[str(sym.arguments[0])] = sym.arguments[1].number

    ctl.solve(on_model=on_model)
    rows = [OpenRow(reason=r, target=t, blocks=blocks.get(t, 0)) for r, t in opens]
    return sorted(rows, key=lambda r: (-r.blocks, r.target, r.reason))
