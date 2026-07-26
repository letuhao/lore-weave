# 12 · Voice All-Day — detailed design

**Date:** 2026-07-11 · **Phase:** P4 · **Status:** DESIGN · Implements **D2, D11**.

---

## Q1. What already exists?

Nearly all of it. Voice turns are **ordinary chat messages in the same session** (`content_parts.input_method
= 'voice'`), so voice and text interleave in one transcript: STT → LLM stream → sentence-buffered TTS over SSE,
assistant audio persisted to MinIO with replay, VAD, a voice overlay + waveform, and **STT/TTS resolved as BYOK
provider credentials** through provider-registry (local Whisper-class + Kokoro ⇒ **$0-capable**).

## Q2. So why is it P4, not P1? (D11 — three silent-wrongness bugs)

The voice path is a **deliberately minimal surface**: it calls `_stream_via_gateway` directly, so a voice turn
gets grounding and injection defense but **no tools, no skills, no canon capture, no context-budget frames** —
and `billing.log_usage` is called with **`input_tokens=0, output_tokens=0`** (verified).

Ship voice in P1 and you ship, by construction:

1. **The "collecting" chip lies.** Voice turns persist to `chat_messages` (so the **distiller journals them**)
   but **never call capture** — so half the user's day is uncaptured while the home strip says ON. There isn't
   even a decision log to explain it.
2. **The day is unbilled.** STT + LLM + TTS on every utterance, logged as **zero tokens**. The spend lane
   ([`10`](10-cost-spend-lane.md)) and the daily cap would both be blind — an all-day voice user would blow
   through real money with the meter reading zero.
3. **No tools.** The assistant can't act on anything said by voice.

→ **P1–P3: voice input is hidden/disabled for assistant-bound sessions.** Hiding the affordance is the honest
move; the alternative is a UI that promises something the backend doesn't do. (If it were ever reachable, the
voice path must at minimum **log a capture decision** with `reason='voice_path_unsupported'`.)

## Q3. What P4 must fix

| # | Work |
|---|---|
| 1 | **Route the transcript through the text agent loop** (`stream_response`) rather than duplicating it — the code comment says ~70% is already shared. Voice turns then get tools, skills, capture, and context-budget frames for free |
| 2 | **Real usage accounting** — the 0/0 billing fix, incl. STT and TTS spend, so the lane and cap work |
| 3 | **Audio retention policy** — transcripts yes; audio retention **user-set with a short default**. Audio segments join the erasure copy-set ([`09`](09-settings-consent-privacy.md) §Q8 / MinIO objects, which are **never purged** today) |
| 4 | The **voice two-stores deferral** (`D-CHATAI-VOICE-TWO-STORES-ENUM`) reconciles first — building on a mid-migration settings store would fork it further |

## Q4. What voice does NOT become (D2 — locked)

**Never ambient / always-listening.** Voice here is *the user talking to the assistant* — push-to-talk-shaped,
consent intrinsic. It is **not** open-mic capture of a room, a meeting, or a colleague.

This is the line the wearables crossed and did not survive: Limitless/Rewind stopped selling the Pendant and
withdrew from the EU/UK/BR, and open-mic capture produced "shadow work" (gigabytes of irrelevant audio the user
must manage) and could not distinguish a colleague from a TV. **We capture the user's own account, not the room.**

## Q5. Acceptance

A voice turn fires capture (decision logged, reason visible) · a voice day is **billed with real tokens**
(STT + LLM + TTS) and lands in the assistant lane · a voice turn can call a tool · voice turns appear in the
distilled entry · audio is deleted per the retention setting **and by "delete my day"** · the affordance is
**absent** in P1–P3.
