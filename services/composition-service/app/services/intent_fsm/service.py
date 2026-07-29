"""The intent-collection FSM (spec `docs/specs/2026-07-28-intent-collection-fsm.md`).

## What this is for

Measured 2026-07-28: **0 of 95 chapter outline nodes carried a single intent slot.** The columns
have modelled chapter intent since the schema was written and nothing has ever produced a value —
`beat_role` was dropped on the floor by the plan apply step, and the planner emitted `intent: ""` in
0 of 30 entries. This service is the missing producer.

## Why a state machine and not a chat loop

An author cannot state their intent up front — it is not one large answer they are withholding, it
accretes through the work (the PO's correction, spec §1). So the machine's job is to make intent
*cheap to say*: propose small, grounded, reversible options and let the author correct them. With a
weak model that only works under rails, and each rail kills a specific failure:

| without rails | the rail |
|---|---|
| the model answers three slots at once, badly | ONE slot per call |
| it drifts back to something already settled | the cursor only advances |
| it re-asks what the author declined | `absent` is terminal for that slot |
| bad JSON wedges the run | one retry, then `proposal_failed` — recorded, never silent |
| a double-click double-applies | the optimistic `transition` 409s the loser |
| it "finishes" while the author is away | **every author-facing state blocks** |

That last one is not a UX preference. An unattended fill loop is precisely how a model invents canon
and the author never notices, because they will not re-read what they believe they approved.

## The state graph

    opened ──propose──▶ proposing ──▶ awaiting_author ──answer──▶ applying ──▶ advanced ──propose──▶ …
                            │              │                                       │
                            ▼              └── decline ⇒ writes "absent" ──────────▶│
                     proposal_failed ──skip───────────────────────────────────────▶ │
                                                                     (no slots left) ⇒ done

`advanced` is a real resting state, not a transient. Keeping it real means **every LLM call sits on
exactly one route** (`propose`), so spend is visible per call instead of buried inside an apply.

Durability note, registered honestly: like glossary-build's v1 driver there is no heartbeat here —
but there is also no background task. Every transition is driven by a request, so a restart leaves
the run in a state the next request can legally move from. `proposing` and `applying` are the only
windows a crash can strand, and `resume()` exists for exactly that.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.engine.compress import _NO_THINK
from app.engine.plan_forge.structure import resolve_structure
from app.services.intent_fsm import engine
from app.services.intent_fsm.repo import IntentRepo
from app.services.intent_fsm.slots import (
    SlotError,
    effective_class,
    plan_for,
    render,
    spec,
)

logger = logging.getLogger("app.services.intent_fsm")

#: States a stranded run may be resumed FROM. Both are windows where a request died mid-flight:
#: `proposing` (the LLM call) and `applying` (the node write). Neither is author-facing, so rewinding
#: is always safe — the author sees no state they have to re-decide.
_RESUMABLE = {"proposing": "opened", "applying": "awaiting_author"}

_LIVE = ("opened", "proposing", "awaiting_author", "applying", "advanced", "proposal_failed")

#: Closed set. A free-string action is the frontend-tool bug class that shipped once already: the
#: model sent a value nobody validated, the resolver silently no-opped, and it hallucinated success.
ACTIONS = ("accept", "revise", "decline")


def _beats_of(run: dict) -> list[dict[str, Any]]:
    """The run's FROZEN beat vocabulary, in the shape `slots.choices_for` reads.

    Never re-resolved mid-run — see the comment on `beat_keys` in `open_run`.
    """
    return [{"key": k} for k in (run.get("params") or {}).get("beat_keys") or []]


class IntentFSMError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class IntentFSMService:
    def __init__(self, repo: IntentRepo, outline, llm, *, plan_runs=None,
                 structure_templates=None, kal=None) -> None:
        self._repo = repo
        self._outline = outline
        self._llm = llm
        self._plan_runs = plan_runs
        self._templates = structure_templates
        self._kal = kal

    # ── LLM binding — the platform job seam (never a provider SDK, never a literal model) ───────
    def _llm_fn(self, *, user_id: str, model_source: str, model_ref: str):
        async def call(messages: list[dict], max_tokens: int,
                       response_format: dict | None = None) -> str:
            # `response_format` rides straight through provider-registry to LM Studio's grammar
            # layer, so a closed-set slot's enum is enforced at DECODE time. Measured 2026-07-28:
            # parse failures 2 -> 0, quality unchanged, and a fixed seed reproduces 18/18.
            job = await self._llm.submit_and_wait(
                user_id=user_id, operation="chat",
                model_source=model_source, model_ref=model_ref,
                input={"messages": messages,
                       "response_format": response_format or {"type": "text"},
                       "temperature": 0.5, "max_tokens": max_tokens, **_NO_THINK},
                job_meta={"usage_purpose": "intent_fsm"},
            )
            if getattr(job, "status", None) != "completed":
                raise LLMError(f"intent_fsm LLM job status={getattr(job, 'status', None)}")
            return extract_judge_content(job.result)
        return call

    # ── opening a run ───────────────────────────────────────────────────────────────────────────
    async def open_run(self, *, owner: UUID, book_id: UUID, node_id: UUID,
                       params: dict[str, Any]) -> dict:
        """Create a run over the slots this node has NOT settled yet.

        Slots the author already settled or declared `absent` are excluded from the plan, not merely
        skipped at ask time: `absent` is an authored statement and re-asking it is the failure this
        design exists to prevent, while a settled slot needs an explicit re-open (spec §10 Q3, which
        is deliberately unanswerable until prose exists).
        """
        for key in ("model_source", "model_ref"):
            if not params.get(key):
                raise IntentFSMError(422, "MISSING_PARAMS", f"params missing: {key}")
        arm = params.get("arm", "constrained_first")
        if arm not in ("constrained_first", "reversed"):
            raise IntentFSMError(422, "BAD_ARM", f"arm must be constrained_first or reversed, got {arm!r}")

        node = await self._outline.get_node(node_id)
        if node is None or node.book_id != book_id:
            raise IntentFSMError(404, "NODE_NOT_FOUND", "outline node not found in this book")
        if node.kind not in ("chapter", "scene"):
            raise IntentFSMError(422, "BAD_NODE_KIND",
                                 f"intent is collected on a chapter or a scene, not a {node.kind}")

        already = dict(getattr(node, "intent_slots", None) or {})
        try:
            ordered = plan_for(arm=arm, only=params.get("slots"))
        except SlotError as exc:
            raise IntentFSMError(422, "BAD_SLOTS", str(exc)) from exc
        slot_plan = [s for s in ordered if already.get(s) not in ("settled", "absent")]
        if not slot_plan:
            raise IntentFSMError(409, "NOTHING_TO_ASK",
                                 "every slot in scope is already settled or declared absent")

        beats, structure = await self._beats(owner, book_id, params.get("structure_template_id"))
        try:
            return await self._repo.create_run(
                owner=owner, book_id=book_id, project_id=node.project_id, node_id=node_id,
                slot_plan=slot_plan,
                params={
                    **params, "arm": arm,
                    # FROZEN for the run, resolved ONCE. Two reasons, and the second is the real
                    # one: (a) propose and answer must agree on whether `beat_role` was a closed
                    # set, and re-resolving in each would let them disagree; (b) an author who
                    # switches structure template mid-run must not retroactively change what the
                    # earlier slots were asked against — the instrument would then describe a run
                    # that never happened.
                    "beat_keys": [str(b.get("key")) for b in beats if b.get("key")],
                    # The structure's PROVENANCE. Whether `beat_role` was asked against the
                    # author's real structure or a platform fallback changes what the POC's
                    # `closed` class actually measured, and a consumer that sees only the beats
                    # cannot tell those apart.
                    "structure": structure,
                },
            )
        except asyncpg.UniqueViolationError as exc:
            raise IntentFSMError(409, "ACTIVE_RUN",
                                 "this node already has an intent run in progress") from exc

    async def _beats(self, owner: UUID, book_id: UUID,
                     template_id: Any = None) -> tuple[list[dict], dict]:
        """The book's beat vocabulary — the closed set for `beat_role`.

        There is no global beat vocabulary; the valid keys are the chosen structure template's
        (`arc_template.beats[].key`), which is why this resolves per book. Preference order is the
        explicit param, then the structure the book's newest plan run was actually planned against
        (asking against a different vocabulary than the outline was built with would offer the
        author beats their own plan does not use), then `resolve_structure`'s default.
        """
        if self._templates is None:
            return [], {"source": "unavailable", "note": "structure templates not configured"}
        tid = template_id
        if tid is None and self._plan_runs is not None:
            try:
                runs, _ = await self._plan_runs.list_for_book(book_id, limit=1)
                tid = getattr(runs[0], "structure_template_id", None) if runs else None
            except Exception:  # noqa: BLE001 — a degraded read falls back, never breaks the run
                logger.warning("intent_fsm: plan-run structure read failed for book=%s", book_id,
                               exc_info=True)
        resolved = await resolve_structure(
            self._templates, owner,
            structure_template_id=UUID(str(tid)) if tid else None,
        )
        return resolved.beats, resolved.to_package()

    # ── reads ───────────────────────────────────────────────────────────────────────────────────
    async def get(self, run_id: UUID, owner: UUID) -> dict:
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise IntentFSMError(404, "NOT_FOUND", "intent run not found")
        run["records"] = await self._repo.list_records(run_id, owner)
        return run

    async def list_runs(self, *, owner: UUID, book_id: UUID, limit: int = 20) -> list[dict]:
        return await self._repo.list_runs(owner=owner, book_id=book_id, limit=limit)

    # ── propose: the ONE LLM step ───────────────────────────────────────────────────────────────
    async def propose(self, run_id: UUID, owner: UUID) -> dict:
        """[opened | advanced | proposal_failed] → proposing → awaiting_author | proposal_failed."""
        run = await self._repo.transition(
            run_id, owner, ["opened", "advanced", "proposal_failed"], "proposing")
        if run is None:
            raise IntentFSMError(409, "BAD_STATE",
                                 "run is not waiting to propose (it may be awaiting your answer)")
        slot = run["slot_cursor"]
        if not slot:
            return await self._finish(run)

        s = spec(slot)
        params = run["params"] or {}
        node = await self._outline.get_node(run["node_id"])
        if node is None:
            await self._repo.transition(run_id, owner, ["proposing"], "failed",
                                        error_detail="the outline node no longer exists")
            raise IntentFSMError(404, "NODE_GONE", "the outline node no longer exists")

        beats = _beats_of(run)
        canon = await self._canon(owner, run["book_id"])
        filled = self._filled(node)

        try:
            candidates, calls, retried = await engine.propose(
                self._llm_fn(user_id=str(owner), model_source=params["model_source"],
                             model_ref=params["model_ref"]),
                s, node={"title": node.title, "synopsis": node.synopsis, "kind": node.kind},
                filled=filled, canon=canon, beats=beats,
                n=int(params.get("n", 3)), lang=params.get("lang", "vi"),
            )
        except LLMError as exc:
            # A transport/provider failure is NOT `proposal_failed` — that state means "the model
            # answered and the answer was unusable", which is a fact about the model. Conflating
            # them would make the POC's failure rate measure the network.
            await self._repo.transition(run_id, owner, ["proposing"], "opened",
                                        error_detail=str(exc))
            raise IntentFSMError(502, "LLM_FAILED", str(exc)) from exc

        klass = effective_class(slot, beats=beats)
        if not candidates:
            out = await self._repo.transition(
                run_id, owner, ["proposing"], "proposal_failed", candidates=[],
                error_detail=f"the model produced no usable option for '{slot}' after one retry")
            await self._repo.record_slot(
                run, slot=slot, position=self._position(run, slot), constraint_class=klass,
                outcome="proposal_failed", candidates=[], llm_calls=calls, retried=retried)
            return await self.get(out["run_id"], owner)

        out = await self._repo.transition(
            run_id, owner, ["proposing"], "awaiting_author",
            candidates=[{"value": c["value"], "why": c["why"]} for c in candidates],
            error_detail=None)
        # Recorded at PROPOSE time, not at answer time: a run the author abandons here must still
        # show what it cost and what it offered. `offered` is corrected when they answer.
        await self._repo.record_slot(
            run, slot=slot, position=self._position(run, slot), constraint_class=klass,
            outcome="offered", candidates=[{"value": render(slot, c["value"]), "why": c["why"]}
                                           for c in candidates],
            llm_calls=calls, retried=retried)
        return await self.get(out["run_id"], owner)

    # ── answer: the author's blocking checkpoint ────────────────────────────────────────────────
    async def answer(self, run_id: UUID, owner: UUID, *, action: str,
                     value: Any = None) -> dict:
        """awaiting_author → applying → advanced (or done).

        All three actions WRITE. `decline` is not a no-op: it stamps `absent`, which is the author
        saying the story has not decided this — never re-asked, never auto-filled. Treating it as
        "skip" is what lets a fill loop re-ask what the story has no answer to, and the model then
        obliges by inventing.
        """
        if action not in ACTIONS:
            raise IntentFSMError(422, "BAD_ACTION", f"action must be one of {list(ACTIONS)}")
        run = await self._repo.transition(run_id, owner, ["awaiting_author"], "applying")
        if run is None:
            raise IntentFSMError(409, "BAD_STATE", "run is not awaiting an answer")
        slot = run["slot_cursor"]
        s = spec(slot)

        if action == "decline":
            settled, verdict, outcome, author_value = s.empty, "absent", "absent", None
        else:
            raw = value
            if action == "accept" and raw is None:
                cands = run.get("candidates") or []
                if not cands:
                    await self._repo.transition(run_id, owner, ["applying"], "awaiting_author")
                    raise IntentFSMError(422, "NO_CANDIDATE",
                                         "nothing to accept — send the value you are accepting")
                raw = cands[0]["value"]
            if raw is None:
                # `revise` with no value. Without this the text coercion stringifies it and the
                # author's slot is settled to the literal word "None" — a write that looks entirely
                # successful, is marked `settled`, and is therefore never re-asked. Declining is
                # what the author meant, and they have a route for it.
                await self._repo.transition(run_id, owner, ["applying"], "awaiting_author")
                raise IntentFSMError(422, "NO_VALUE",
                                     "revise needs a value — use action='decline' to record that "
                                     "the story has not decided this slot")
            try:
                settled = s.coerce(raw)
            except SlotError as exc:
                # Rewound, not failed: the author's answer was unusable for this COLUMN, and they
                # are still the one being asked. Leaving the run in `applying` would strand it.
                await self._repo.transition(run_id, owner, ["applying"], "awaiting_author")
                raise IntentFSMError(422, "BAD_VALUE", str(exc)) from exc
            verdict, outcome, author_value = "settled", "applied", render(slot, settled)

        try:
            persisted = await self._outline.settle_intent_slot(
                run["project_id"], run["node_id"],
                slot=slot, value=settled, pg_cast=s.pg_cast, verdict=verdict)
        except Exception as exc:  # noqa: BLE001 — a failed write must not strand the run
            await self._repo.transition(run_id, owner, ["applying"], "awaiting_author",
                                        error_detail=str(exc))
            raise IntentFSMError(502, "APPLY_FAILED", str(exc)) from exc

        # Read BACK off the node, never echoed from the request: metric B asks whether the artifact
        # ends up saying exactly what the author said, and echoing would make it measure nothing.
        await self._repo.record_slot(
            run, slot=slot, position=self._position(run, slot),
            # From the run's FROZEN vocabulary, not re-derived. Re-deriving without the beats
            # would silently downgrade `beat_role` from `closed` to `blank_open` on the upsert,
            # overwriting the class the slot was actually asked under — and the POC's whole
            # constraint-vs-fatigue question is read off this column.
            constraint_class=effective_class(slot, beats=_beats_of(run)),
            outcome=outcome, candidates=run.get("candidates") or [],
            author_value=author_value, applied_value=render(slot, persisted))
        return await self._advance(run)

    async def skip(self, run_id: UUID, owner: UUID) -> dict:
        """proposal_failed → advanced. The slot is left UNASKED and said so (spec §6)."""
        run = await self._repo.transition(run_id, owner, ["proposal_failed"], "applying")
        if run is None:
            raise IntentFSMError(409, "BAD_STATE", "run has no failed proposal to skip")
        return await self._advance(run)

    async def cancel(self, run_id: UUID, owner: UUID) -> dict:
        run = await self._repo.transition(run_id, owner, list(_LIVE), "cancelled")
        if run is None:
            raise IntentFSMError(409, "BAD_STATE", "run is already finished")
        return await self.get(run_id, owner)

    async def resume(self, run_id: UUID, owner: UUID) -> dict:
        """Rewind a run stranded mid-request by a restart.

        Only the two non-author-facing states are resumable, and each rewinds to the state BEFORE
        its side effect — so resuming can re-do work but can never skip the author. An `applying`
        run rewinds to `awaiting_author`: the write may or may not have landed, and re-applying the
        same value to the same column is idempotent, whereas advancing past it would silently drop
        the slot.
        """
        run = await self._repo.get_run(run_id, owner)
        if run is None:
            raise IntentFSMError(404, "NOT_FOUND", "intent run not found")
        target = _RESUMABLE.get(run["status"])
        if target is None:
            raise IntentFSMError(409, "NOT_STRANDED",
                                 f"a run in '{run['status']}' is not stranded — nothing to resume")
        await self._repo.transition(run_id, owner, [run["status"]], target)
        return await self.get(run_id, owner)

    async def score(self, run_id: UUID, owner: UUID, *, slot: str,
                    verdicts: list[dict]) -> dict:
        """Metric A (spec §8) — the AUTHOR's per-candidate accept / light_edit / discard.

        Scored by the author and never by a judge model: the thing being measured is authorial
        taste, so a model grading it would be the thing under test grading itself.
        """
        allowed = {"accept", "light_edit", "discard"}
        for v in verdicts:
            if not isinstance(v, dict) or v.get("verdict") not in allowed:
                raise IntentFSMError(422, "BAD_VERDICT",
                                     f"each verdict must be one of {sorted(allowed)}")
        if await self._repo.set_verdicts(run_id, owner, slot, verdicts) is None:
            raise IntentFSMError(404, "NO_RECORD", f"no record for slot '{slot}' in this run")
        return await self.get(run_id, owner)

    # ── cursor ──────────────────────────────────────────────────────────────────────────────────
    def _position(self, run: dict, slot: str) -> int:
        plan = run.get("slot_plan") or []
        return plan.index(slot) + 1 if slot in plan else 0

    async def _advance(self, run: dict) -> dict:
        plan, cur = run.get("slot_plan") or [], run["slot_cursor"]
        nxt = None
        if cur in plan and plan.index(cur) + 1 < len(plan):
            nxt = plan[plan.index(cur) + 1]
        if nxt is None:
            return await self._finish(run)
        out = await self._repo.transition(run["run_id"], run["owner_user_id"],
                                          ["applying", "proposing"], "advanced",
                                          slot_cursor=nxt, candidates=[], error_detail=None)
        if out is None:
            # Reachable: a concurrent `resume` moves `applying` → `awaiting_author` out from under
            # us. The slot's value HAS landed, so the run simply re-asks it and the author's second
            # answer is idempotent — safe, but it must not be invisible. A silent lost advance is
            # how a run that looks stuck becomes unexplainable.
            logger.warning("intent_fsm: lost the advance on run=%s (slot=%s → %s); the run will "
                           "re-ask the settled slot", run["run_id"], cur, nxt)
        return await self.get(run["run_id"], run["owner_user_id"])

    async def _finish(self, run: dict) -> dict:
        await self._repo.transition(run["run_id"], run["owner_user_id"],
                                    list(_LIVE), "done", slot_cursor=None, candidates=[])
        return await self.get(run["run_id"], run["owner_user_id"])

    # ── grounding ───────────────────────────────────────────────────────────────────────────────
    def _filled(self, node) -> dict[str, Any]:
        """The slots already settled on this node, for the prompt.

        Read from `intent_slots` rather than from "the column is non-empty": a column holding the
        planner's value is a SUGGESTION, and presenting it to the model as settled author intent
        would launder a machine guess into a constraint the next answer must not contradict.
        """
        state = dict(getattr(node, "intent_slots", None) or {})
        out: dict[str, Any] = {}
        for name, verdict in state.items():
            if verdict != "settled":
                continue
            v = getattr(node, name, None)
            if v is not None and str(v).strip():
                out[name] = v
        return out

    async def _canon(self, owner: UUID, book_id: UUID) -> list[str]:
        """The book's cast, for the `canon_open` slots.

        Degrade-safe: a thin or empty roster only makes the proposal less grounded, and blocking
        intent collection on the knowledge layer being up would be a worse trade. The constraint
        class recorded for the slot still says `canon_open`, which is honest — the class describes
        what was ASKED; how well it was grounded is what metric A measures.
        """
        if self._kal is None:
            return []
        try:
            return [str(e.get("name")) for e in await self._kal.roster(book_id, user_id=owner)
                    if e.get("name")]
        except Exception:  # noqa: BLE001
            logger.warning("intent_fsm: roster unavailable for book=%s", book_id, exc_info=True)
            return []
