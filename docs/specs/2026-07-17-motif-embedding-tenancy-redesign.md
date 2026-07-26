# Motif Embedding — Tenancy Re-design (per-user BYOK for private, platform for shared)

> **Problem (raised 2026-07-17):** every motif — including a user's STRICTLY-PRIVATE ones — is embedded
> with the ONE platform model (`motif_embed_model_ref`, owner `motif_embed_owner_id`). The platform bears
> the embedding cost/compute for content only one user ever uses. That mis-attributes cost across the
> tenancy boundary (BYOK: the user pays for their own LLM/embedding work).
>
> **Decision (PO):** re-embed **shared** motifs (system + public) with the **platform** model; embed a
> user's **strictly-private** motifs with **their own BYOK embedding key**. The user pays for their own.
>
> **⚠ Verified finding (2026-07-17, against code — the premise above was imprecise):** the live cost
> mis-attribution is in **arcs**, not motifs. Motif *summary* vectors are **never persisted** today —
> `create()`/seed insert `embedding=NULL`, and `retrieve()` only *queues* NULL rows for a back-fill that
> **nothing drains** ([motif_retrieve.py](../../services/composition-service/app/db/repositories/motif_retrieve.py))
> — so motif suggest is *always* in the genre/tension degrade path (why the "degraded" banner is always on).
> **Arcs DO persist** — `_embed_and_persist_arc` embeds a user's PRIVATE arc with the **platform** model on
> retrieve back-fill. **That** is the live tenancy bug. So the build is: **(1) fix arcs** (private→owner BYOK,
> two-space retrieve) — *done, this doc's §7.1*; **(2) motifs** — build the missing persist path *and* make it
> tier-aware from day one. Same architecture; the finding relocates where the fix lands.
>
> **Ranking presentation (PO chose 2026-07-17):** §4 option **(A) two sections** — "Motif của bạn" (U-space)
> + "Từ thư viện" (P-space), ranked independently, no cross-space score compare. `match_reason.section ∈
> {'mine','library'}` carries the split; `section == space` (a user's own *published* motif appears under
> "library", keeping each section single-space/honest). Fallback = non-semantic (confirmed). Migration =
> lazy re-embed (confirmed).

## 1 · The core tension this must solve — cross-tier ranking spans two vector spaces

The retriever ranks a chapter against the caller's VISIBLE set:
`_VISIBLE_PREDICATE = (owner_user_id IS NULL /*system*/ OR visibility='public' OR owner_user_id=$caller)`.
Under the new rule that set spans **two embedding spaces**:
- **P-space** (platform model): system + public [+ book_shared — shared among grantees].
- **U-space** (the caller's own BYOK embedding model): the caller's strictly-private motifs.

Cosine is only meaningful WITHIN one space. So the retriever must embed the query **twice** (once per model)
and rank each space separately. The open decision is **how to combine** the two ranked lists (§4).

## 2 · Tier → embedding-space mapping (the write path)

| Motif tier | Owner | Embedded by | Space | Who pays |
|---|---|---|---|---|
| **System** (`owner_user_id IS NULL`) | platform | platform model (`motif_embed_*`) | P | platform (seed-time) |
| **Public / unlisted** (`visibility='public'`) | a user, but SHARED to all | **platform** model | P | platform |
| **book_shared** (collaborator tier) | book, shared to grantees | **platform** model | P | platform |
| **Strictly private** (`owner=caller AND visibility='private' AND NOT book_shared`) | the user | **the user's BYOK embedding model** | U(user) | **the user** |

Rule of thumb: **shared ⇒ platform space; strictly-private ⇒ the owner's own space.** The moment a motif
becomes shareable (publish, adopt-into-book_shared) it is **re-embedded** with the platform model (a tier
transition triggers a re-embed).

Each motif row already carries `embedding_model` (text, per-row) + `embedding` + `embedded_summary_hash`
→ the retriever reads each row's model to know its space. **No schema change needed** (add a small
`embedding_owner` marker if we must distinguish "platform-P" from "user-U" beyond the model id).

## 3 · Resolving the user's embedding model + the NO-MODEL fallback

- The user's embedding model resolves via **provider-registry** (`user_models` with an `embed` capability;
  same path knowledge-service uses). Passed to `embedding_client.embed(user_id=<caller>, model_ref=<user's>)`
  → the call bills the **user's** ledger (cost attribution solved).
- **If the caller has NO embedding-capable model registered:** their private motifs cannot be U-embedded.
  Policy (recommended): **non-semantic fallback** for their private tier — rank by genre/tension/recency
  (no vector), and surface the honest "unranked — semantic matching unavailable" banner (already built,
  commit 164228a0a). This keeps the cost goal (platform never embeds their private content) and never
  lies about the ranking. *(Alternative: silently fall back to platform embedding — REJECTED: it re-creates
  the exact cost mis-attribution this re-design removes.)*

## 4 · 🔴 THE ONE FORKING DECISION — how to present the two-space ranking

The suggest UI needs a result from two independently-ranked lists (U-space private + P-space shared).

- **(A) Two sections** — *"Your motifs"* (U-ranked) + *"From the library"* (P-ranked). No cross-space score
  comparison (honest — scores from different models aren't comparable). Simple, truthful, matches the
  mental model ("my tropes vs the shelf"). **Recommended.**
- **(B) One normalized list** — rank within each space, convert to a comparable score (rank-percentile or
  z-score per space), merge into a single ranked list. Nicer single-list UX, but the cross-space score is
  a **heuristic** (a 0.8 in U-space ≠ a 0.8 in P-space). Risk: presents a merged order as if it were one
  true ranking.

## 5 · Migration

- Existing motifs are all platform-embedded. **Strictly-private** rows must be re-embedded with their
  owner's model. Approach (recommended): **lazy re-embed** — on a private motif's next write OR next
  retrieve-miss, if `embedding_model == platform` re-embed with the owner's model (idempotent via
  `embedded_summary_hash` + a model-mismatch check). Avoids a big backfill + bills each user as they use it.
  *(Alternative: a per-user backfill worker — more upfront, but deterministic.)*
- The tier-transition re-embed (§2, publish/adopt→shared) re-embeds with the platform model.

## 6 · Standards / invariants this must respect
- **Provider-gateway**: all embeds via provider-registry `/internal/embed` (no SDK, no per-service model
  literal) — already how `embedding_client` works; just switch the `user_id`/`model_ref` per tier.
- **No hardcoded model**: unchanged (platform model still resolves from settings; user model from registry).
- **Tenancy**: the cost now follows the owner (user pays for U-space; platform for P-space) — this re-design
  IS the tenancy fix.
- **No-silent-fail**: the degrade banner (built) covers the no-user-model + platform-unset cases.

## 7 · Scope / phases (once §4 is decided)
1. **Write path** — `embed_motif_summary` branches on tier: strictly-private → `(caller, user_model)`;
   shared → `(platform_owner, platform_model)`. Tier-transition re-embed on publish/adopt.
2. **Retrieve** — partition candidates by space; two query embeds; rank each; combine per §4.
3. **Fallback** — non-semantic ranking + banner when no user embedding model.
4. **Migration** — lazy re-embed of private rows.
5. **Tests** — write-path tier branching, two-space retrieve, cost-attribution (user ledger hit), fallback.
6. **Live smoke** — a user with a BYOK embed model: private motif → U-embedded (user ledger), suggest ranks it.

**Open before BUILD:** §4 (A vs B) + §3 fallback (confirm non-semantic) + §5 (lazy vs backfill).
