# Decision record — salience `feedback_weight` ↔ learning-service boundary

**Status:** DECIDED — **keep separate** (conscious won't-integrate, revisit-gated).
**Date:** 2026-07-05 · **Workstream:** P2·E (spec [`2026-07-04-enterprise-p2-structural.md`](2026-07-04-enterprise-p2-structural.md) §E).
**Decision owner:** platform. This is the "document + decide" the P1 note deferred.

## Question

Should knowledge-service's salience `feedback_weight`
(`app/context/selectors/salience.py`) be **sourced from a learning-service-published
quality signal**, or should the two learning loops stay **decoupled**?

## What was verified (code, 2026-07-05)

1. **The two loops operate at different granularities and don't reference each other.**
   - **knowledge-service salience** re-ranks glossary entities in a context build by a
     per-`(user, project, entity)` signal. Its `feedback_weight` term multiplies
     `EntitySalience.feedback_score`, which is sourced **entirely inside
     knowledge-service** from `entity_access_log.feedback_score`
     (`app/db/repositories/entity_access.py:126-131`) — an accumulated ±1 chat-thumbs
     tally attributed to entities surfaced in a rated turn (`apply_feedback`,
     `entity_access.py:82-115`). It defaults **0.0** (disabled) and is flip-gated on an
     ambiguous-query eval showing lift (`salience.py:13-15`).
   - **learning-service** is the correction-capture + eval/quality plane. Its quality
     signals (`quality_scores`, `eval_runs`, the one published outbox event
     `translation.eval_judged`) are keyed by **extraction-run (per-chapter) ·
     chapter-translation · chat-message · wiki-article · eval-run · model/config** —
     **not** by a glossary entity.

2. **learning-service does NOT publish or expose any per-entity quality signal that
   knowledge could consume.** The single per-`glossary_entity_id`-keyed datum it holds
   is `quality_scores(target_kind='glossary')` written by `handle_name_confirmed`
   (`app/events/handlers.py:919,936-940`) — and it is a **binary human name-confirmation
   flag (=1.0)**, persisted only to learning-service's own DB, surfaced by **no HTTP
   endpoint** and carried by **no event**.

3. **There is zero existing consumption** of learning-service signals in
   knowledge-service. The only coupling runs the other way (knowledge → learning:
   wiki-judge POST, `app/clients/learning_client.py`) and is unrelated to salience.

## Decision — keep separate

Sourcing salience `feedback_weight` from learning-service is **not warranted now**, and
would be net-new work on both sides for no demonstrated gain:

- **No signal to consume.** learning-service publishes nothing per-entity. Integration
  would first require learning-service to *produce* a new **continuous, per-entity
  quality signal** (the existing `glossary_name_confirmed` is binary and name-scoped, not
  a quality/relevance score) **and** a new cross-service contract to carry it — a real
  feature, not a wiring change.
- **Granularity mismatch.** learning-service's quality plane judges *chapters,
  translations, runs, models* — the flywheel for extraction/translation quality. Salience
  ranks *entities for one user's context build*. These are legitimately different loops;
  fusing them conflates "is this extraction/translation good" with "does this user care
  about this entity right now."
- **The in-service signal is the right primitive.** Per-user chat-thumbs attribution
  (`entity_access_log.feedback_score`) is already the correct, tenant-scoped, low-latency
  source for a *personalized* salience term. A platform-wide learning signal would be
  the wrong tier for a per-user ranking (it would push the same global bias onto every
  user's context). This aligns with the tenancy model — salience is per-user/per-project,
  not a System-tier global.
- **The term is disabled by default** and its own flip is eval-gated; there is no live
  quality deficit that a learning signal would fix.

## Revisit trigger (so this doesn't silently ossify)

Reopen **only if** a concrete need appears:
- an **ambiguous-query eval** shows `feedback_weight` (on the existing in-service signal)
  gives lift AND its ceiling is limited by sparse per-user thumbs → then a **global prior**
  from learning-service could backfill cold-start entities; **or**
- learning-service grows a genuine **per-entity continuous quality/relevance signal**
  (beyond the binary name-confirm flag) for another consumer, making the contract cheap to
  reuse.

At that point the minimal bridge is: learning-service publishes a per-`glossary_entity_id`
quality delta on its existing outbox; knowledge-service consumes it as a **separate,
additively-weighted** `global_feedback` term (NOT by overwriting the per-user
`feedback_score`), preserving the per-user vs platform-prior distinction above.

## Acceptance (spec §E)

Met by the "documented decision (boundary rationale)" branch. No code change; the
salience feedback term stays in-service and default-off. Tracked as
**`D-E-SALIENCE-LEARNING-BRIDGE`** (conscious won't-fix, revisit-gated) — not an open
build item.
