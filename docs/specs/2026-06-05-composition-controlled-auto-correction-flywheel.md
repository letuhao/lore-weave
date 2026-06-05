# Composition V1 — Controlled-Auto + Correction Flywheel (design)

> **Status:** DESIGN draft (LOOM, 2026-06-05) — **/review-impl-hardened** (2 HIGH: H1 composition not a relay source → §3/§7; H2 accept-as-is = self-reinforcement → §2 dropped; + 4 MED/2 LOW folded). Extends [`2026-06-05-composition-v1-reasoning-engine.md`](2026-06-05-composition-v1-reasoning-engine.md) (the reasoning core) + reuses the **learning-service** `corrections` flywheel (eval-track Q2) + the composition outbox (M9). A1 `diverge→converge` is built.
> **★ Spin-out finding (review H1):** M9 `composition.scene_committed` telemetry is **emitted but never relayed** (composition absent from `OUTBOX_SOURCES`) — tracked **D-COMP-OUTBOX-NOT-RELAYED**; this build fixes it as a side effect.
> **Thesis (PO):** early-stage V1 should be **controlled auto, not autonomous** — generate (diverge→converge) → **human gate** (the author corrects/accepts) → **capture the correction** → feed learning-service. The human gate guarantees quality (nothing bad ships) AND collects the preference signal to improve the drafter + reranker. This **also solves the A1 eval-gate problem**: the auto-judge coherence metric saturates (5/5); **human corrections are the discriminating quality ground-truth** (which scenes get edited / regenerated / re-picked = where the AI is weak).

---

## §1 Why controlled-auto beats the §8.3 hard-gate autonomous loop (for now)
The reasoning-engine spec §8.3 sketches an *autonomous* loop with the critic as a hard gate. But (a) the critic can't yet be trusted as a gate (the eval saturates — §A1 finding), and (b) we have no preference data to tune the drafter/reranker. So **sequence it:** controlled-auto (human gate + capture) FIRST → accumulate corrections → use them to train the reranker/drafter + validate the critic → THEN graduate to autonomous where the now-trusted critic gates. Corrections are the bridge.

## §2 Correction taxonomy — the human gate IS the signal
Post-generate actions. **Only GENUINE-AUTHOR-CHOICE actions are preference gold** (review H2): `accept-as-is` is NOT a correction — the author didn't choose the winner, the *reranker* did, so mining "winner ≻ rejected" trains the reranker on its own output = **self-reinforcement** (the exact failure the eval-track eliminated with disjoint judges, ~4-5pp inflation). So:

| Action | Is it gold? | Preference signal | Trains | Store (M3) |
|---|---|---|---|---|
| **accept** (as-is) | **NO** (review H2) | weak positive only; do NOT mine "winner ≻ rejected" (circular) | — | accept-rate metric (§6), not a correction row |
| **accept-with-edit** | YES | `edited` ≻ `winner` | **drafter** (prose-level, richest) | `corrections` (before/after) |
| **pick-different** (cand j) | YES | `cand_j` ≻ `winner_i` | **reranker** (the judge was wrong) | `corrections` (before=winner, after=j) |
| **regenerate-with-guidance** | CONDITIONAL | `−winner` + guidance **only if the old was not accepted** (review M5 — regen may be exploration, not dissatisfaction) | drafter | `corrections` w/ `parent_job_id` chain |
| **reject / discard** | YES | `−whole generation` (no `preferred`) | negative example | `corrections` (op=reject) |

**Key:** `pick-different` is the one DIRECT, non-circular correction on the **A1 reranker**. Caveat (review M4): a single author's picks are *personal taste* — aggregate across users before training a GLOBAL reranker, or scope to per-user personalization.

## §3 Data model + flow (reuse, don't rebuild)

```
FE correction surface
   │  POST /v1/composition/jobs/{job_id}/correction {kind, chosen_candidate_index?,
   │                                                 guidance?, edited_text?}
   ▼
composition-service
   • generation_correction (NEW, per-work): {id, job_id, work_id, user_id, kind,
        chosen_candidate_index?, guidance?, edit_struct (diff: # changed blocks),
        raw_before?/raw_after? (OPT-IN only, §5), created_at}
   • emit `composition.generation_corrected` → outbox_events (reuse M9 emit pattern)
   ▼  relay (worker-infra, existing) → loreweave:events:composition
learning-service  (NEW consumer handler — the only learning-side code)
   • handle_generation_corrected → persist_consumed_score / a preference row:
        {source=composition, kind, preferred?, non_preferred?, change_magnitude,
         work_id, job_id, origin_event_id (dedup)}  ← mirrors Q2 corrections-as-gold
```

- **Composition** owns the capture + outbox (reuses M1 `outbox_events` + the M9 `scene_committed` txn-local emit; `aggregate_type='composition'` → stream key `loreweave:events:composition`).
- **⚠ H1 (review, load-bearing) — composition is NOT a relay source yet.** `OUTBOX_SOURCES` (compose) = `book, translation, chat, glossary, knowledge` — **no `composition`**. M9's `scene_committed` is currently **emitted-but-unrelayed** (the B3.3 e2e only checked the outbox ROW). The build MUST add `composition:postgres://…loreweave_composition` to the worker-infra `OUTBOX_SOURCES` env, and the live-smoke MUST assert the event reaches the stream AND is consumed — not just that the row was written.
- **learning-service** adds `loreweave:events:composition` to its consumer STREAMS + one `handle_generation_corrected` handler. **Store = `corrections`** (review M3) — its `target_type`/`op`/`before_structural`/`after_structural` are generic enough; **the opt-in raw prose maps onto the EXISTING `before_content`/`after_content` RESERVED columns** (review L7 — Phase-E opt-in, not a new mechanism). `accept`/`reject` RATES → `quality_scores` or derived from the job, not a correction row.
- **`generation_job`** already retains `candidates` + `winner_index` (A1) → the preference pairs are reconstructable from the job + the correction.

## §4 FE — correction surface (always show all K candidates)
Extend the V0 `ComposeView` (ghost/accept/regenerate/discard) into the gate. **PO: always show all K candidates in parallel** (like §8.2 "takes" — maximum transparency + the most `pick-different` signal):
- **K candidate cards** side-by-side (the winner badged) — the author reads + compares.
- **Per-candidate:** Accept · Edit-then-accept (inline, the editor already supports insert; the diff is captured) · "This one instead" (pick-different).
- **Regenerate-with-guidance** (a guidance box + regenerate — reuses the V0 control; the guidance is captured).
- **Reject all.**
- Each action → `POST …/correction` with the kind. Accept also inserts to the editor (V0 SC4: ghost never autosaved until accept — preserved).
- Cost note: K parallel drafts already paid at generate; showing them is free. Reading 3 is the author's cost — acceptable for the quality gate + they chose it.

## §5 Raw-prose policy — OPT-IN (mirror `save_raw_extraction`)
Default = **structural + content-hash only** (the no-raw-text / multi-device privacy rule + learning-service redact-by-default). A per-work (or per-user) **`capture_correction_prose` opt-in** flips it to store the actual `winner`/`edited`/`chosen` prose — needed for prose-level preference tuning (DPO, V2). Same pattern + governance as the eval-track's raw-extraction opt-in. The structural signal (which candidate, edit magnitude, regenerate, kind) is ALWAYS captured; only the verbatim prose is gated.

## §6 The eval-gate, fixed
Replace the saturating auto-judge median with **correction-derived quality metrics** (the ground-truth the auto-judge lacked):
- **accept-as-is rate** (↑ = drafter+reranker good) · **edit rate + edit magnitude** (↓ = good) · **pick-different rate** (↓ = reranker good) · **regenerate rate** (↓ = drafter good) · **reject rate** (↓).
- A-slice gate: does `diverge→converge` (A1) lower edit/regenerate/reject rate vs V0 single-draft, on real author corrections? **This is a discriminating, human-grounded metric** — not a ceiling-5 auto-judge. (Auto-judge stays as a cheap proxy; humans are the gate.)
- **Caveats (review M6):** (a) **cold-start** — these rates need real usage before they exist; the auto-judge proxy bridges until then. (b) **edit-rate confounds "AI bad" with "this author tweaks everything"** → normalize per-author (compare a user's V0-mode vs auto-mode edit rate, not absolute), and pair with a within-author A/B so author-style cancels out.

## §7 Build plan (full loop) — proposed slices
1. **BE capture + RELAY WIRING (H1)** — `generation_correction` table + migration · `POST /jobs/{id}/correction` · `composition.generation_corrected` outbox emit (reuse M9 txn-local pattern) · the opt-in flag · **add `composition` to worker-infra `OUTBOX_SOURCES`** (the missing relay source — also un-breaks M9 telemetry). Live-smoke MUST assert the event reaches `loreweave:events:composition` (relayed), not just the outbox row.
2. **learning consume** — add `loreweave:events:composition` to STREAMS + `handle_generation_corrected` → **`corrections` store** (reuse Q2 gold-label path + dedup; only edit/pick/regenerate/reject; NOT accept-as-preference — H2). Tests + live-smoke (both DB halves, like Q3a — assert the correction row + dedup).
3. **FE correction surface** — K-candidate cards + accept/edit/pick/regenerate/reject + capture calls + i18n. Tests + tsc.
4. **gateway** — `/v1/composition/*` catch-all already proxies (no gateway change); learning already proxied.
5. **eval** — swap the A1 eval-gate to correction-rate metrics (§6); becomes the standing quality dashboard.

Each slice = own VERIFY + COMMIT (cross-service at 1+2 → live-smoke token).

## §8 Open decisions (at PLAN)
1. **`generation_correction` placement** — new table vs columns on `generation_job` (a job can have multiple corrections over time → new table).
2. **Preference reconstruction** — store the full `(preferred, non_preferred)` pair at capture time, or store the raw action + reconstruct from the job's candidates in learning? (Capture-time pair is simpler + dedup-stable.)
3. **regenerate chaining** — link the regenerated job to the prior (a `parent_job_id`) so `new ≻ old` is reconstructable.
4. **What counts as `edit`** — any post-accept editor change to the inserted span, or only edits made before accept? (Before-accept is cleanly attributable; post-accept edits blend with normal writing.)
