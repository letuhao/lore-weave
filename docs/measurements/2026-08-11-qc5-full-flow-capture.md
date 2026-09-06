# QC-5 — the full authoring flow, captured — 2026-08-11

> **Result: the pipeline is PROVEN end-to-end and the judge is NOT calibrated.** A real
> chapter was generated through the real endpoint, the role check ran inside it, and it
> produced typed `role_contradiction` findings on real prose. **8 of 8 are false positives**,
> and two of them contradict their own stated reason. Both halves are the result.

## What ran

`POST /v1/composition/works/{project}/chapters/{chapter}/generate` on the acceptance book,
chapter 11 — *"Cạm bẫy khép lại"* (**the trap closes**), the acceptance case's own chapter. <!-- doc-language-gate: ok -- the chapter title is the cited subject of this acceptance case -->
Job `019ff029-60d3-74ab-bb13-917941a7c7be`, **completed**, 4109-character draft.

| artefact QC-5 names | captured |
|---|---|
| the plan artifact | 47 outline nodes, 12 chapter nodes, 2 validated `plan_run`s |
| the drafted chapter | 4109 chars, generated this run |
| the critic's scores | canon envelope below (per-check, not per-dimension — see gap) |
| the glossary delta | 0 — `persist:false`, so this run is read-only by design |

## It took three runs, and the first two failures are the useful part

**Run 1 — no distinct critic.** `critic_source`/`critic_ref` empty on the work, so
`resolve_critic_refs(...).distinct` was False → `judge=None` → **neither** judge can run
(invariant 2: no model is silently its own judge). Fixed by configuring the account's
`distill` model as the critic, which is genuinely a different model from the drafter.

**Run 2 — a stale image.** The flag was set and the containers restarted, but
composition-service and composition-worker were still running the image built *before* the
role check existed. The run looked identical to a legitimate "no findings". Rebuilt, and
verified the code was actually in the container before re-running:

```
docker exec infra-composition-worker-1 python -c "from app.engine.canon_check import ..."
role check code present: True True
```

That is the *"rebuild stale images first"* trap, and it cost a full run. Checking the flag
was not enough; the flag was never the thing that was stale.

**Run 3 — the role judge fires inside the flow.** Two `judge_role_attribution` LLM jobs at
09:31 and 09:32, both `completed`, matching the run — the first time this check has executed
anywhere except a direct probe.

## The findings, and why they are wrong

```
predicate       object          why (judge's own words, truncated)
betrayed        Lâm Uyên        "Lâm Trạch reveals his betrayal to Lâm Uyên in the passage, not someone else."
cousin_of       Lâm Uyên        "…has betrayed Lâm Uyên, contradicting their cousin relationship."
located_at      Đình hóng gió   "Lâm Uyên is described as being in the main hall…, not at Đình hóng gió."
married_to      Lâm Uyên        "…has betrayed Lâm Uyên, which contradicts them being siblings."
knows           Tô Thanh Dao    "…knows the truth about Lâm Trạch's betrayal, contradicting…"
conspires_with  Lâm Trạch       "The passage shows that Tô Thanh Dao conspires with Lâm Trạch against Lâm Uyên."
located_at      Đình hóng gió   (duplicate of row 3)
sibling_of      Lâm Uyên        "…conspires with Lâm Trạch against Lâm Uyên, contradicting…"
```
<!-- doc-language-gate: ok -- stored entity names and the judge's verbatim verdicts; paraphrasing removes the evidence -->

Four distinct failure modes, and none is a machinery bug:

1. **Affirming a violation while describing agreement.** Row 1 says the passage attributes the
   betrayal to Lâm Trạch — *which is exactly what canon says* — and returns `violated: true`.
   Row 6 does the same for `conspires_with`. The judge is answering "is this relationship
   present in the passage?" instead of "does the passage contradict it?"
2. **Treating a plot event as ending a kinship.** Betraying your cousin does not stop them
   being your cousin. Rows 2, 4 and 8 all reason "X betrayed Y, therefore the family relation
   is contradicted."
3. **A confused subject.** Row 4's predicate is `married_to` but its reason argues about
   *siblings*; row 8's is `sibling_of` reasoning about conspiracy.
4. **A location read as a contradiction.** Row 3 flags `located_at` because the scene happens
   somewhere else — but a character being elsewhere later is movement, not a contradiction of
   a positioned relation.

## What this means for the acceptance criterion

QC-5 asks that a **misattributed** trap be caught. This draft attributes the betrayal
**correctly**, and the check fired anyway — the opposite error. The earlier direct probe
(`docs/measurements/2026-08-11-qc5-role-attribution-live.md`) got this right: 1 finding on a
misattributed draft, **0 on the correct control**. The difference is that the control was a
hand-written two-sentence passage; this is 4109 characters of real generated prose with many
relations in force at once.

**So the honest reading:** the pipeline is proven, the precision is not. A check that fires 8
times on a correct chapter would train an author to ignore it, which is worse than not
shipping it — and it is why the check stays **off by default**.

## The two other checks, and one real gap

```
canon_cast     no_rules     — 5/5 cast unresolved: the book has NO :EntityStatus rows,
                              so the liveness corpus is empty. Honest, not a false pass.
plan_liveness  no_position  — declared: plan_supported=False on the chapter path
name_grounding checked
```

`canon_cast: no_rules` is the same empty-corpus problem `D-T32-ALIVE-NO-FACTS` records, seen
from the reader's side.

**The gap QC-5 names that this run did NOT produce: the critic's per-chapter scores.** The
canon envelope carries per-CHECK statuses, not the 4-dimension `judge_prose` scores the task
asks for; those come from the D5 continuity critic, a different pass this endpoint does not run.

## Next

Calibrate `_build_role_judge_messages` against these 8. The prompt already says a passage that
is silent is not a contradiction; it needs to also say that **a relationship the passage
CONFIRMS is not a contradiction**, and that an event involving two people does not end a
kinship or a marriage. Then re-run this exact chapter — the job id above is the baseline.
