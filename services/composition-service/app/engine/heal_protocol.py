"""S5 — one heal loop: the STAGE PROTOCOL, and a per-stage opt-out that must state its reason.

What this is
------------
Three modules run a version of the same pipeline over different subjects:

    self_heal          judge → locate → snap → vote → verify → rerank → edit → merge → splice → re-judge
    plan_heal          judge ──────────────────────────────────────→ edit
    error_block_heal   ──────  locate  ─────────────────────────────→ edit ─────────→ splice

`error_block_heal` is the one that already got reuse right, and the spec names it as the third
consumer for that reason: it composes self-heal's public primitives, skips six stages, and
records WHY for each — *the author already decided a defect is real, so re-adjudicating it would
be the tool second-guessing its user*; *snapping to a sentence boundary would silently widen a
span the author deliberately selected*.

That reasoning is the valuable artefact and it lives in a docstring, where nothing can check
it. `plan_heal` skips the same six and says nothing at all. So the protocol below makes three
things true that were not:

  1. The stage list is ENUMERATED once, instead of implied by a comment in one module.
  2. Every consumer accounts for EVERY stage — run it, or give a reason. Total coverage, so a
     stage cannot be silently absent the way `plan_heal`'s six are today.
  3. The declaration is CHECKED AGAINST THE CODE, in both directions, by
     `tests/unit/test_heal_protocol.py`.

Why the check reads code and not text
--------------------------------------
The obvious implementation greps each module for a stage's primitive. Measured, that is wrong:
`error_block_heal` mentions `_snap_to_sentence` in its docstring — in the sentence explaining
why it does NOT call it — so a text scan reports the stage as RUN and the declaration as a lie.
It is the same prose-is-not-behaviour confusion the injection lint had (S4), the deferral
registry's stripper had before it, and the `not_found` scan in S3 had. Here it would be
especially perverse: the check would be defeated by the very documentation that makes this
module the exemplar. So the checker strips docstrings and comments first.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["HealStage", "StagePlan", "STAGE_PRIMITIVES", "PLANS"]


class HealStage(StrEnum):
    """The ten stages, in pipeline order. Lifted from `error_block_heal`'s own diagram."""

    JUDGE = "judge"        #: decide WHAT is wrong (LLM, or a human marking a span)
    LOCATE = "locate"      #: map a quoted span back to real offsets
    SNAP = "snap"          #: widen a sloppy quote to a sentence boundary
    VOTE = "vote"          #: repeat the judge to raise recall
    VERIFY = "verify"      #: a skeptical pass that drops confabulated findings
    RERANK = "rerank"      #: rank which edits to recommend (never drops)
    EDIT = "edit"          #: produce the replacement text
    MERGE = "merge"        #: fold in deterministic/mechanical fixes
    SPLICE = "splice"      #: apply accepted edits back into the document
    REJUDGE = "rejudge"    #: re-run the judge to report the finding-count drop


#: stage → the primitives that IMPLEMENT it. A consumer "runs" a stage when it references one.
#:
#: Deliberately a symbol list rather than a call-graph proof: these modules compose each other's
#: public functions, and a module-level reference is the same granularity `error_block_heal`'s
#: docstring uses when it says which stages it composes. A finer check would be better and is
#: not what makes the declarations honest — the declarations were unchecked at ANY granularity.
STAGE_PRIMITIVES: dict[HealStage, tuple[str, ...]] = {
    HealStage.JUDGE: ("build_judge_messages", "parse_findings", "_judge",
                      "build_plan_judge_messages", "parse_plan_findings",
                      "build_direct_judge_messages", "parse_direct_findings"),
    HealStage.LOCATE: ("locate_span",),
    HealStage.SNAP: ("_snap_to_sentence",),
    HealStage.VOTE: ("_judge_vote", "_vote_bucket"),
    HealStage.VERIFY: ("_verify", "_verify_vote"),
    HealStage.RERANK: ("_rerank_edit",),
    HealStage.EDIT: ("build_selection_messages", "_compute_edits", "build_fix_scene_messages"),
    HealStage.MERGE: ("code_mechanical_edits", "code_pronoun_findings"),
    HealStage.SPLICE: ("apply_self_heal_edits", "EditProposal"),
    HealStage.REJUDGE: ("rejudge_after", "rejudge_before"),
}


@dataclass(frozen=True)
class StagePlan:
    """One consumer's declared pipeline. `skipped` must cover every stage not in `runs`."""

    module: str
    runs: frozenset[HealStage]
    #: stage → why this consumer does not run it. A REASON, not a marker: the whole point is
    #: that "we don't do that here" is a design decision somebody made, and an opt-out with no
    #: reason is indistinguishable from an omission nobody noticed.
    skipped: dict[HealStage, str]

    def accounts_for_every_stage(self) -> bool:
        return set(self.runs) | set(self.skipped) == set(HealStage)


PLANS: tuple[StagePlan, ...] = (
    StagePlan(
        module="self_heal",
        runs=frozenset(HealStage),
        skipped={},
    ),
    StagePlan(
        module="plan_heal",
        runs=frozenset({HealStage.JUDGE, HealStage.EDIT}),
        # These reasons did not exist. `plan_heal` skipped six stages in silence, and writing
        # them down is most of this slice's value: each one is a real property of its subject.
        skipped={
            HealStage.LOCATE:
                "an outline scene is addressed by ORDINAL (chapter N, scene M), not by a quoted "
                "span, so there is nothing to fuzzy-locate — the address is exact or invalid.",
            HealStage.SNAP:
                "snapping widens a span to a sentence boundary; a scene synopsis is replaced "
                "whole, so there is no partial span to widen.",
            HealStage.VOTE:
                "voting raises recall on a stochastic judge over PROSE. The outline is short "
                "and structured, and a second pass costs another LLM call per plan.",
            HealStage.VERIFY:
                "verify drops confabulated findings by re-reading the quoted span. With an "
                "ordinal address there is no quote to re-read; the address either resolves or "
                "is already rejected as out-of-range.",
            HealStage.RERANK:
                "reranking chooses which of many competing span edits to recommend. Plan "
                "findings do not compete — each addresses a distinct scene.",
            HealStage.MERGE:
                "the mechanical merge is a dup-word/pronoun sweep over prose. An outline "
                "synopsis is not prose the reader sees.",
            HealStage.SPLICE:
                "splicing reassembles a document from offset-addressed edits. A scene synopsis "
                "is a FIELD; it is replaced in place, so there are no offsets to reconcile.",
            HealStage.REJUDGE:
                "re-judging reports the finding-count drop. Not run today — this is the one "
                "skip here that is an omission rather than a property of the subject, and it "
                "is recorded as such rather than dressed up.",
        },
    ),
    StagePlan(
        module="error_block_heal",
        runs=frozenset({HealStage.LOCATE, HealStage.EDIT, HealStage.SPLICE}),
        # LIFTED VERBATIM in substance from the module's own docstring — the reasoning was
        # already right, it was just unreachable by any check.
        skipped={
            HealStage.JUDGE:
                "the AUTHOR marked the span and said what is wrong with it. Re-adjudicating "
                "their call would be the tool second-guessing its user.",
            HealStage.SNAP:
                "snapping widens a judge's sloppy quote to a sentence boundary. Applied to a "
                "HUMAN span it would silently widen a deliberate selection — the author marked "
                "those words.",
            HealStage.VOTE:
                "voting exists to decide whether a defect is REAL. The author already decided.",
            HealStage.VERIFY:
                "same as vote: verification adjudicates an LLM's claim, and there is no LLM "
                "claim here.",
            HealStage.RERANK:
                "reranking recommends which edits to accept. The author is the filter.",
            HealStage.MERGE:
                "the dup-word mechanical merge belongs to a whole-chapter sweep, not a "
                "targeted fix on one marked span.",
            HealStage.REJUDGE:
                "re-judging reports the drop in finding COUNT after editing. There was no "
                "judge pass to re-run, and the count here is one — the author's block, which "
                "is resolved or not by their own review.",
        },
    ),
)
