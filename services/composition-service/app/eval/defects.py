"""The seeded-defect registry (spec §S10).

One row per defect the generation engine is supposed to catch. Each row declares three
things, and the third is the one the existing harness has never had:

  1. **how to seed it** — the scenario, and the state the engine must be given
  2. **how to detect it** — the field(s) on the engine's own result that constitute a FIRE
  3. **its CONTROL** — the same scenario with the defect removed, on which the detector must
     stay QUIET

Why a control is not optional
-----------------------------
`scripts/eval_a2_canon.py` gates on `status=="checked" AND iterations>=1` across five
scenarios and reports "PASS — gone-cast contradiction detected". That result is produced
identically by a working canon loop and by an engine that runs a revise pass on every scene
regardless. The eval cannot tell them apart, so a green run proves nothing about the
detector — only that it is reachable.

A detector is characterised by TWO numbers, and a suite that only measures one of them is
measuring recall and calling it correctness. So detection here means: fires on the seeded
variant AND stays quiet on the control. Anything less is a hit count.

Why the classes are what they are
---------------------------------
Each is a failure this repo has actually observed, not an invented one — a registry of
hypotheticals would drift from the engine and rot. The provenance is on each row.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    """What a single run of one variant produced."""

    FIRED = "fired"      # the detector triggered
    QUIET = "quiet"      # the detector did not trigger
    ERROR = "error"      # the run failed before the detector could speak


@dataclass(frozen=True)
class Observation:
    """One engine result, reduced to what the detector reads.

    Deliberately a plain mapping rather than a typed engine object: the suite must be
    runnable against a recorded fixture as well as a live stack, and a live-only instrument
    is how the nine existing scripts came to run nowhere.
    """

    fields: dict[str, object] = field(default_factory=dict)
    #: True when the run itself failed (transport, timeout, no model). An ERROR is NOT a
    #: quiet detector — conflating them would score an outage as a clean engine, which is the
    #: "skip reads as pass" shape this repo keeps finding.
    failed: bool = False
    note: str = ""


#: A detector reads an Observation and says whether the engine flagged the defect.
Detector = Callable[[Observation], bool]


@dataclass(frozen=True)
class DefectClass:
    code: str
    #: What the engine is supposed to notice.
    defect: str
    #: The scenario WITH the defect planted.
    seeded: str
    #: The SAME scenario with the defect removed. The detector must stay quiet here — this is
    #: the half `eval_a2_canon.py` has never had.
    control: str
    #: Reads the engine's own result. Kept as a function so the FIRE condition lives next to
    #: the defect it belongs to instead of being re-derived per script.
    detector: Detector
    #: Where this failure was actually seen. A class with no provenance is a hypothetical.
    provenance: str
    #: The observation keys this detector consumes. Declared, not inferred, because the gate
    #: has to check them against what the engine ACTUALLY emits — and because a freeform
    #: `dict[str, object]` otherwise turns a key typo into a silent QUIET, which scores as
    #: "the engine did not have this defect".
    reads: tuple[str, ...] = ()
    #: Non-empty ⇒ this class is BLIND: the engine does not emit what its detector needs, and
    #: what must be built is named here. A blind class is never scored — see `suite.observe`.
    #:
    #: This field exists because the first version of this registry declared five classes of
    #: which three read fields with ZERO occurrences anywhere in the service
    #: (`scenes_covered`, `unresolved_refs`, `actual_words`). Their detectors would have been
    #: permanently quiet, every run would have scored MISSED, and MISSED reads as "the engine
    #: has this defect" when the truth is "the instrument cannot see". False negatives dressed
    #: as findings are worse than an absent class, so blindness is declared and excluded.
    blocked_on: str = ""


def _fired_canon(o: Observation) -> bool:
    """`status=="checked"` AND `iterations>=1`, lifted verbatim from eval_a2_canon.

    `iterations>=1` is the true FIRE signal: the engine only revises after the symbolic guard
    finds a gone-cast candidate AND a distinct judge confirms it. `resolved` is the repair
    OUTCOME, not the detection — gating on it would fail the eval precisely when the reflect
    loop works best.
    """
    return o.fields.get("status") == "checked" and int(o.fields.get("iterations", 0) or 0) >= 1


def _fired_scene_boundary(o: Observation) -> bool:
    """The drafter ran past its own scene. Detected structurally, not by a judge: the draft
    is attributed to more scene ids than the one requested."""
    return int(o.fields.get("scenes_covered", 1) or 1) > 1


def _fired_length_shortfall(o: Observation) -> bool:
    """The draft came back materially under the length its own prompt asked for.

    Measured 2026-07-30 on the Mị Đế book: targets of 900/850/800/750/800 produced
    445/414/532/618/736 words, because `max_tokens` was 1024 while 900 Vietnamese words is
    ~2300 tokens. The prompt asked for one thing and the wire allowed another.

    Deliberately does NOT fire on an ESTIMATED count. For a spaceless script the LENGTH
    directive's "words" has no clear referent — `realised_words` says so via
    `word_count_method` — and a 0.75 threshold applied to an estimate would report every CJK
    scene as short. That is a finding manufactured by the metric, which is the exact class
    this instrument exists to avoid; better to score nothing than to score a fiction.
    """
    if str(o.fields.get("word_count_method", "")).endswith("_estimate"):
        return False
    target = int(o.fields.get("target_words", 0) or 0)
    actual = int(o.fields.get("actual_words", 0) or 0)
    return bool(target) and actual < target * 0.75


def _fired_truncation(o: Observation) -> bool:
    """A structured response came back clipped. `finish_reason == "length"` is the platform's
    wire value (contracts/llm-budget.contract.json)."""
    return o.fields.get("finish_reason") == "length"


def _fired_unresolved_reference(o: Observation) -> bool:
    """The plan referenced a cast member that does not exist in the book's roster — the
    "anonymous characters were uses of undeclared identifiers" failure PF-1 names."""
    return int(o.fields.get("unresolved_refs", 0) or 0) > 0


#: The registry. Order is not significant; the CODES are, because a gate and a report key off
#: them. Adding a class means adding its control too — `gate.py` refuses a row without one.
DEFECTS: tuple[DefectClass, ...] = (
    DefectClass(
        code="gone_cast_asserted_active",
        defect="a character established GONE in an earlier chapter is portrayed as bodily "
               "present and acting, with no revival signal",
        seeded="Kai strode through the eastern gate at dawn, fully rested, and personally "
               "rallied the troops for the coming siege, shouting orders across the yard.",
        # Same beat, same character, same chapter — but he is REMEMBERED, not present. A
        # memory, a corpse, or others speaking about him is explicitly NOT a contradiction
        # (the judge's own system prompt says so), so a detector that fires here is
        # over-flagging, and the seeded run alone could never reveal that.
        control="The troops spoke of Kai at the eastern gate that dawn, repeating the orders "
                "he had shouted across the yard before the siege took him.",
        detector=_fired_canon,
        reads=("status", "iterations"),
        provenance="eval_a2_canon.py (the one seeded class that already existed); the "
                   "Mị Đế book shipped the inverse — Tô Thanh Dao killed in scene 1 against "
                   "the synopsis",
    ),
    DefectClass(
        code="scene_boundary_overrun",
        defect="asked to draft ONE scene, the model writes through its neighbours because "
               "the plan block shows the whole chapter",
        seeded="Draft scene 2 only. The chapter plan lists scenes 1-4 and scene 2 ends on a "
               "hard cut to the next morning.",
        control="Draft scene 2 only. The chapter plan lists scene 2 and nothing after it.",
        detector=_fired_scene_boundary,
        reads=("scenes_covered",),
        blocked_on="the engine reports no per-draft scene attribution — `scenes_covered` has "
                   "ZERO occurrences in the service. Needs the drafter to emit which scene "
                   "ids its output covers (S2 territory).",
        provenance="SCENE-BOUNDARY (2026-07-30, Mị Đế): scene 1's draft arrived carrying "
                   "scene 3's and scene 4's material",
    ),
    DefectClass(
        code="length_directive_ignored",
        defect="the draft lands far under the word count its own prompt requested",
        seeded="target_words=900 on a Vietnamese scene (~2300 output tokens needed)",
        control="target_words=200 on the same scene (comfortably inside any budget)",
        detector=_fired_length_shortfall,
        # UNBLOCKED 2026-07-31: the generate response now carries `actual_words` +
        # `word_count_method` (routers/engine.py -> cowrite.realised_words). This was the
        # cheapest of the three gaps and it makes the Mị Đế bug — 900 words asked, 445
        # delivered — the first thing this suite can actually measure.
        reads=("target_words", "actual_words", "word_count_method"),
        provenance="D-SCENE-OUTPUT-BUDGET-FLAT — measured 900/850/800/750/800 -> "
                   "445/414/532/618/736 words",
    ),
    DefectClass(
        code="structured_output_truncated",
        defect="a JSON response is clipped mid-array and reported as a parse failure rather "
               "than a capacity failure",
        seeded="a cast/plan request whose output exceeds the model's allowance",
        control="the same request with an allowance that clears its own bound",
        detector=_fired_truncation,
        reads=("finish_reason",),
        provenance="glossary runDocExtractor/runPlanner repaired clipped JSON as if it were "
                   "malformed; composition cast_plan records the same class biting",
    ),
    DefectClass(
        code="unresolved_cast_reference",
        defect="the plan names a character the book's roster does not contain",
        seeded="a decompose whose beats reference a character never introduced",
        control="the same decompose over a roster that contains every referenced character",
        detector=_fired_unresolved_reference,
        reads=("unresolved_refs",),
        blocked_on="`unresolved_refs` has ZERO occurrences in the service — the plan validator "
                   "rejects unknown refs but reports no COUNT a detector can read.",
        provenance="PF-1 — 'anonymous characters were uses of undeclared identifiers'",
    ),
)

#: The minimum the suite must carry to be able to catch a NEW regression rather than only
#: re-confirming the one failure it was built around. Five classes is not a magic number — it
#: is the count at which the registry stopped being "the canon check, plus scaffolding".
MIN_CLASSES = 5

#: How many classes must be SCORABLE — i.e. not blind on a field the engine never emits. A
#: registry can look broad and measure almost nothing: the first version of this file declared
#: five classes of which only two could ever produce a number. Ratcheted upward as the engine
#: gains observability; it must never fall.
MIN_SCORABLE = 3
