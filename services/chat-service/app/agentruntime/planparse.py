"""CP-3.2 · the markdown authoring surface → a structured SPEC. **A parse failure is a rejection.**

C-12: a rejection names the **locus** — line, field, and what would have been accepted — never
*"invalid"*. This module exists because the plan has three authors (the model, a workflow template,
a human) and only one of them can read a stack trace.

🔴 **THE FORMAT IS A MEASURED CHOICE THIS MODULE DOES NOT GET TO MAKE.** §0.11's second adjustment
is explicit: markdown is the industry default for the human surface and the most token-efficient of
the compared formats, *but the one benchmark that compared comprehension of **nested data** favoured
YAML — and `accepts`/`emits` bindings ARE nested data. Different model, different task. §0.12 forbids
importing that result: measure on our model, in brick 0.*

So the syntax here is deliberately the **thin** one: markdown headings for the prose a human reads,
and a small explicit key list for the bindings, with no nesting deeper than one level. That is not a
claim that markdown won — it is the shape that survives either answer, because the binding lines are
already flat enough to become YAML without restructuring the steps.

WHAT IS NOT HERE, AND WHY
-------------------------
**No `eval`, no template interpolation, no `{{step2.entity_id}}` strings.** A binding written as
text inside a value is indistinguishable from a user who typed that text, so the executor would have
to guess which it was — and the plan is the mechanism that exists to stop guessing about
identifiers. `from:` is a distinct key, so the shape says which.
"""
from __future__ import annotations

import re
from types import MappingProxyType

from .plan import Binding, PlanError, Spec, Step


class PlanParseError(PlanError):
    """C-12 · a rejection with a locus. **Never raised without a line number.**"""

    def __init__(self, line_no: int, line: str, reason: str, accepted: str) -> None:
        self.line_no = line_no
        self.line = line
        self.reason = reason
        self.accepted = accepted
        super().__init__(f"line {line_no}: {reason}. Accepted: {accepted}\n    {line.rstrip()}")


_STEP_RE = re.compile(r"^##\s+step\s*:\s*(?P<decl>[a-z][a-z0-9_-]*)\s*$", re.IGNORECASE)
_GOAL_RE = re.compile(r"^#\s+goal\s*:\s*(?P<goal>.+?)\s*$", re.IGNORECASE)
_KEY_RE = re.compile(r"^\s*-\s*(?P<key>[a-z_]+)\s*:\s*(?P<val>.*?)\s*$")
#: `book_id from step 0.book_id` — the ONLY reference form, and it names both ends.
_FROM_RE = re.compile(
    r"^(?P<param>[a-z_][a-z0-9_]*)\s+from\s+step\s+(?P<step>\d+)\s*\.\s*(?P<emit>[a-z_][a-z0-9_]*)$",
    re.IGNORECASE)
#: `limit = 20` — a literal, and the `=` is what makes it visibly not a reference.
_LIT_RE = re.compile(r"^(?P<param>[a-z_][a-z0-9_]*)\s*=\s*(?P<val>.+)$")

#: `book_id from books[0].book_id` — the name, and the ONE location it is taken from.
_EMIT_RE = re.compile(
    r"^(?P<name>[a-z_][a-z0-9_]*)\s+from\s+(?P<path>[A-Za-z_][A-Za-z0-9_.\[\]]*)$",
    re.IGNORECASE)

_STEP_KEYS = {"accepts", "emits", "done_when", "gated", "contract_version"}

#: The two keys whose values are NESTED DATA, and what each one accepts instead of an inline value.
_NESTED_KEYS = {
    "emits": ("an empty `- emits:` followed by indented `- <name> from <path>` lines, e.g. "
              "`- book_id from books[0].book_id`. The path is required: `book_list` returns 197 "
              "books and only the plan can say which one it meant"),
    "accepts": ("an empty `- accepts:` followed by indented `- <param> from step N.<name>` or "
                "`- <param> = <literal>` lines; bindings are nested data and each needs its own"),
}


def _literal(text: str):
    """A JSON scalar, and **nothing more expressive than one**.

    Bare `true`/`false`/`null`/int are accepted because a plan author writes them; anything else
    stays a string. There is deliberately no expression syntax — a literal that could compute is a
    literal that could read something it was not handed.
    """
    t = text.strip()
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return t


def parse(text: str) -> Spec:
    """markdown → `Spec`. Raises `PlanParseError` with a line number on the first bad line.

    The `Spec` constructor then runs `check_bindings`, so a syntactically valid plan whose step 3
    reads something no earlier step emits is still refused — at generation, per §6.2. This function
    owns the *shape*; the contract owns the *sense*, and neither substitutes for the other.
    """
    goal = ""
    done_when = ""
    steps: list[Step] = []
    cur: dict | None = None
    section: str | None = None

    def _close() -> None:
        if cur is None:
            return
        steps.append(Step(
            declaration=cur["declaration"],
            contract_version=cur.get("contract_version", ""),
            accepts=MappingProxyType(cur["accepts"]),
            emits=MappingProxyType(cur["emits"]),
            done_when=cur.get("done_when", ""),
            gated=cur.get("gated", False),
        ))

    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith(("<!--", ">")):
            continue

        m = _GOAL_RE.match(line)
        if m:
            if goal:
                raise PlanParseError(n, line, "a second `# goal:` heading",
                                     "one goal per plan; a revision is a new SPEC version")
            goal = m.group("goal")
            section = None
            continue

        m = _STEP_RE.match(line)
        if m:
            _close()
            cur = {"declaration": m.group("decl"), "accepts": {}, "emits": {}}
            section = None
            continue

        if line.lower().startswith("# done_when:"):
            done_when = line.split(":", 1)[1].strip()
            section = None
            continue

        # 🔴 A `- key: value` LINE IS A KEY LINE EVEN INSIDE AN OPEN SECTION, and a key nobody
        # recognises is reported AS a bad key. Without this, `- gatd: true` following an indented
        # `- emits:` was consumed by the emits section and reported as a malformed emit — so the
        # rejection for a typo'd `gated` never mentioned `gated`, which is the one word that would
        # have fixed it. A step that needs approval silently becoming one that does not is the exact
        # consequence this parser's catch-all exists to prevent, so the message has to point at the
        # right thing. Binding lines carry no colon, so none of them can be captured here.
        m = _KEY_RE.match(line)
        if m and cur is not None and m.group("key") not in _STEP_KEYS:
            # 🔴 The reason and the accepted-set are LOCALS, not inline literals, and that is not
            # style. The census keys a refusal by its shape with string literals placeholdered, so
            # this rejection and the catch-all below — both `PlanParseError(n, line, <str>, <str>)`
            # — collapsed to ONE id, and an allowlist row would then have named whichever came
            # first. Two refusals must be two rows.
            _bad_key = m.group("key")
            _reason = f"unrecognised step key {_bad_key!r}"
            _accepted = f"one of {sorted(_STEP_KEYS)} as `- <key>: <value>`"
            raise PlanParseError(n, line, _reason, _accepted)
        if m and cur is not None and m.group("key") in _STEP_KEYS:
            key, val = m.group("key"), m.group("val")
            if key in ("accepts", "emits") and not val:
                section = key
                continue
            section = None
            if key == "gated":
                cur["gated"] = _literal(val) is True
            elif key in _NESTED_KEYS:
                # 🔴 **ONE REFUSAL FOR BOTH KEYS, and the census is why.** `emits:` and `accepts:`
                # each had their own `raise PlanParseError(n, line, <str>, <str>)`, which the
                # census keys by SHAPE with prose blanked — so the two collapsed to one id and an
                # allowlist row would have named whichever came first. Two refusals must be two
                # rows, or they must be one refusal. They say the same thing about two keys, so
                # this is the honest direction: both are nested data, and each entry needs its own
                # line (emits since 2026-08-09, when every emit began naming a path).
                raise PlanParseError(
                    n, line, f"`{key}:` carries a value on the same line", _NESTED_KEYS[key])
            else:
                cur[key] = val
            continue

        if section in ("accepts", "emits") and cur is not None:
            body = line.strip().lstrip("-").strip()
            if section == "emits":
                em = _EMIT_RE.match(body)
                if not em:
                    raise PlanParseError(
                        n, line, "an emit that does not name where its value comes from",
                        "`- <name> from <path>`, e.g. `- book_id from books[0].book_id`. The path "
                        "is REQUIRED even when it looks obvious: `book_list` returns 197 books and "
                        "only the plan can say which one it meant")
                cur["emits"][em.group("name")] = em.group("path")
                continue
            fm = _FROM_RE.match(body)
            if fm:
                cur["accepts"][fm.group("param")] = Binding(
                    from_step=int(fm.group("step")), from_emit=fm.group("emit"))
                continue
            lm = _LIT_RE.match(body)
            if lm:
                cur["accepts"][lm.group("param")] = Binding(
                    from_step=None, literal=_literal(lm.group("val")))
                continue
            raise PlanParseError(
                n, line, f"{body!r} is neither a reference nor a literal",
                "`<param> from step <N>.<name>` to carry a value forward, or `<param> = <value>` "
                "for a literal. There is no third form: a reference written inside a value cannot "
                "be told from text the user typed, which is the guess the plan exists to remove")

        if cur is None and not goal:
            raise PlanParseError(
                n, line, "content before any `# goal:` heading",
                "a plan opens with `# goal: <what this is for>`; without one there is nothing for "
                "the plan-level done_when to be about")
        raise PlanParseError(
            n, line, "unrecognised line",
            f"`## step: <declaration>`, or one of {sorted(_STEP_KEYS)} as `- <key>: <value>`")

    _close()
    if not goal:
        raise PlanParseError(1, text.splitlines()[0] if text.splitlines() else "",
                             "the plan has no `# goal:` heading",
                             "a plan opens with `# goal: <what this is for>`")
    if not steps:
        raise PlanParseError(1, "", "the plan has no steps",
                             "at least one `## step: <declaration>`; an empty plan cannot reach a "
                             "done_when and would be a silent exit by construction")
    return Spec(goal=goal, steps=tuple(steps), done_when=done_when)
