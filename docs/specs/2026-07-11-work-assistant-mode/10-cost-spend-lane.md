# 10 · Cost & the Spend Lane — detailed design

**Date:** 2026-07-11 · **Phase:** P2 (the lane) · **Status:** DESIGN.

---

## Q1. What does an all-day assistant actually cost? (corrected)

For a **150-turn** text day. The overview's first estimate (~30–50 calls) missed two whole background streams.

| Stream | Calls/day | Note |
|---|---|---|
| Entity capture | ~N/4 ≈ **30–38** | bills at the **session's** model — there is no cheap-tier routing |
| Session compaction | ~turns/8 ≈ **15–20** | inherent to the all-day shape (`persist_auto_compact`) |
| Grounding | ~1 embed/grounded turn (+ occasional L2 summarize) | existing per-turn retrieval cost, now counted |
| Executive tick | **0** on the main session (**D13**); ~N/4 in coach sessions | v1 omitted this entirely |
| Distiller | ceil(day_tokens/window)+1 ≈ **3–15** | map-reduce ([`06`](06-journal-distiller.md)) |
| Entry extraction (P2) | 4 × ceil(paragraphs/15) + 1 summary + 1 embedding ≈ **6–12** | first extraction always cache-misses |
| Weekly/diary rollups (P3) | ~1 part-summary/week + book rollups growing O(days) | **not free** — the md5 cache never hits at part/book level on a growing journal |

**≈ 90–120 background LLM calls/day.** **$0 on local BYOK**; roughly **$1–3/day** on gpt-4o-class.

## Q2. The per-feature lane is its own M-sized build (COST-3)

"Generalize the existing mcp-key sub-cap" **understates it**:

- the existing sub-cap is **monthly-windowed** — we need a **daily** window (the goal is protecting the user's
  *daily interactive* cap);
- attribution rides a **literal `mcp_key_id` UUID column** on `usage_logs`, `token_reservations` **and**
  provider-registry's `usage_outbox` — a feature lane needs a **generic lane column** on all three (not another
  UUID special case), plus every hop carrying it;
- `SpendCapUSD` is **caller-supplied**, so the cap needs a settings home (`assistant.spend_cap_usd`) and every
  background call-site must resolve and forward it **through `job_meta` across the RabbitMQ hop** — the exact
  envelope-drop bug class already on record. **Consumer live-smoke required.**

**Bonus (T32):** the lane tag on `usage_logs` is also what finally makes **"delete my day" able to reach the
prompt payloads** — which hold the decryptable diary text and are otherwise structurally unreachable
(`owner_user_id` but no `book_id`). Do not let that become a separate orphan.

## Q3. 🔴 What happens when the cap is exhausted at 2pm? (T22)

For an all-day companion **the failure mode *is* the product** — and "guardrails exist" is not a design. A
denied reserve either kills the assistant from 2pm, or (worse) fails silently while the user believes they are
being remembered.

**The degrade ladder (specified now, not later):**

1. **Background streams stop first** — capture, distill, extraction. The home strip shows
   *"Memory paused — daily cap reached"* with the reason and a top-up action.
2. **Foreground chat keeps working** on the user's main budget — a different lane and a different consent.
3. **The undistilled day is queued, not lost** — it distills at the next window.
4. **Never a silent no-op.** "Cap exhausted mid-day" is an S14 scenario.

## Q4. Model routing

- Capture inherits the **session's** model (no cheap-tier routing exists). A per-user **capture/distill model
  role** (P2) would let both resolve a designated cheap model instead of the interactive one.
- **No "cheapest capable" auto-ranking exists** in the platform — don't promise it. `assistant.distill_model`
  → chat-capability default → **visible failure**.
- ⚠️ **Cross-provider fallback requires explicit confirm** — otherwise a local-model user's entire day ships to
  a cloud provider at distill time ([`09`](09-settings-consent-privacy.md) §Q6).

## Q5. Fairness

P5 WFQ fair scheduling is **env-gated, default OFF**. One user's all-day background loop would otherwise
starve others. Enable it and add an **`assistant:distill` lane** (config on the existing `FairScheduler`, not a
build).

## Q6. Acceptance

A day's spend lands in the assistant lane and is **visible in the usage panel** · the daily sub-cap denies
background work **without killing foreground chat** · the queued day distills next window · lane tag survives
every enqueue hop (consumer live-smoke) · `usage_logs` assistant-lane rows are deletable by day.
