# Work Assistant — Phase 4 (Voice All-Day) — ready-to-build plan

**Date:** 2026-07-15 · **Track:** Work Assistant · **Phase:** 4 · **Status:** PLAN (sealed, pre-build) ·
**Spec:** [`12-voice-parity.md`](../specs/2026-07-11-work-assistant-mode/12-voice-parity.md) (implements D2, D11) ·
**Sealed decisions:** [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §3 P4-D1..6

---

## 0. What Phase 4 is (and is NOT)

**Is:** make the EXISTING voice path a first-class assistant citizen — voice turns get tools, capture, context-budget frames, and **real billing**, and their audio has a retention + erasure story.

**Is NOT:** ambient / always-listening anything (D2, LOCKED — P4-D6). Voice is push-to-talk-shaped: the user talking to the assistant, never open-mic capture of a room/meeting/colleague. This is the line the wearables crossed and did not survive.

## 1. Substrate already built (do not rebuild)

Nearly all of voice exists: STT → LLM stream → sentence-buffered TTS over SSE; assistant audio persisted to MinIO with replay; VAD; a voice overlay + waveform; STT/TTS resolved as **BYOK provider credentials** through provider-registry (local Whisper-class + Kokoro ⇒ **$0-capable**). Voice turns are ordinary chat messages in the same session (`content_parts.input_method='voice'`), so voice + text interleave in one transcript.

**The three verified defects (spec 12 Q2) — why it's P4, not P1:**
1. The voice path calls `_stream_via_gateway` **directly** (`voice_stream_service.py:407`) → grounding + injection defense but **no tools, no skills, no canon capture, no context-budget frames**.
2. `billing.log_usage(... input_tokens=0, output_tokens=0)` (`voice_stream_service.py:544-545`) — **the day is unbilled**: STT + LLM + TTS on every utterance, metered as zero. The spend lane + daily cap are blind.
3. Voice turns persist to `chat_messages` (so the distiller journals them) but **never call capture** — half the day is uncaptured while the home strip says ON, with no decision log.

## 2. The slice board (dependency order)

> ⚠️ **REVIEW-PATCHED 2026-07-15** (cold review R3 — see [`2026-07-15-phase-345-clean-seal.md`](2026-07-15-phase-345-clean-seal.md) §7). Corrections that change scope: the spend **`lane` column is NOT built** (only the daily-cap degrade shipped); the **audio sweeper + MinIO delete already exist** (reuse, don't rebuild); voice is **NOT gated for assistant sessions today** (the uncaptured/unbilled bug is LIVE); WS-4.1 is a **shared-inner-generator refactor**, not a `stream_response` swap; retention default **stays ≤48h**, not 7d.

| Slice | Title | Scope | Depends on | Risk |
|---|---|---|---|---|
| **WS-4.0** | Two-stores reconcile | Land `D-CHATAI-VOICE-TWO-STORES` (the `SETTING_ENUMS` validation disabled for `stt_source`/`tts_source` — a `'user_model'` vs `'ai_model'` vocab mismatch, `settings_resolution.py:64`). **Prereq for WS-4.3 only** (a new voice setting), NOT for 4.1/4.2 — the pipeline works today. | — | Low-Med — a settings vocab cleanup. |
| **WS-4.1** | Route voice through the shared agent loop | **Extract a shared inner GENERATOR** that both `_emit_chat_turn` and voice consume (voice keeps its sentence-buffered TTS interception in the middle) — do NOT route through `stream_response` (wrong layer: serialized SSE + double-persist). The content-dict seam is `_stream_with_tools` but voice's `content = chunk["content"]` KeyErrors on `tool_call`/`suspend`/`agent_surface` chunks — handle them, and decide `suspend` (frontend-tool) applicability for a voice turn (no client resume loop). **Capture is a SEPARATE layer** (`_emit_chat_turn` post-turn `maybe_capture_canon`) — the refactor must route capture too, not assume it comes free. | WS-4.0-not-required | 🔴 High — a real 3-layer refactor (streaming core is ~70% shared; tools + capture + budget are NOT). Live-smoke a voice turn calling a tool + firing capture. |
| **WS-4.2a** | LLM-token billing fix (easy) | Voice ALREADY receives the LLM `UsageEvent` from `_stream_via_gateway` and **discards** it (`voice_stream_service.py`). Thread `last_usage` into `log_usage` (fix both the DB row AND the SSE `finish-message` `usage:{0,0}` the FE reads). | — | Low — the LLM half is cheap. |
| **WS-4.2b** | STT/TTS usage plumbing (structural) | STT/TTS usage is **uncapturable at the call site today**: `SttResult` has no tokens; `stream_tts` **discards** any `UsageEvent` (SDK `client.py:326`). Requires: provider-registry STT/TTS adapters EMIT usage → the SDK surfaces it → voice logs it. STT bills by **audio-minutes**, TTS by **characters** (NOT tokens — fix the acceptance wording). **Also depends on the spend `lane` column (T-8) which is UNBUILT** — either build the lane ×3 tables first or scope to the existing global cap. | provider-registry + SDK change; the `lane` column (unbuilt) | Med-High — cross-service + SDK boundary; larger than a call-site fix. |
| **WS-4.3** | Audio retention → per-user setting | The sweeper + MinIO delete **already exist** (`main.py _audio_cleanup_loop`, `voice.py /cleanup`, on `AUDIO_TTL_HOURS`). Real work = convert the **global env → a per-user setting** (SET-* boundary). **Default stays ≤48h** (P4-D4 corrected — do NOT lengthen to 7d; that weakens a privacy feature), user-settable 0..48h. | WS-4.0 (settings store) | Low-Med — env → setting; the object lifecycle exists. |
| **WS-4.4** | Audio joins the D-R27 erasure | The D-R27 `DELETE /assistant/data` cascades `message_audio_segments` rows but **orphans their MinIO objects** (real bug). Apply the existing `RETURNING object_key → delete_object` pattern (already in `voice.py DELETE /voice/data`) to the cascade — **SELECT the object_keys BEFORE the `chat_sessions` delete cascades them away** (a CTE, since the cascade won't RETURN them). + an ABSENCE test on the MinIO object. | WS-4.3, erasure primitive (built) | Med — reuse the pattern; mind the SELECT-before-cascade ordering. |
| **WS-4.5** | Affordance gate (a real FIX, not a formality) | Voice is currently rendered UNCONDITIONALLY for assistant sessions (`ChatInputBar.tsx` takes no `sessionKind`) — so the uncaptured + unbilled bugs are **LIVE**, not hidden. Add the P1-P3 gate NOW (hide voice for assistant sessions until WS-4.1/4.2 land) + log a capture decision (`reason='voice_path_unsupported'`, net-new). | — | Med — the bug is live; the gate is a real safety fix, not a no-op. |

## 3. Acceptance (spec 12 Q5 — the exit gate)

- A voice turn **fires capture** (decision logged, reason visible).
- A voice day is **billed with real tokens** (STT + LLM + TTS) and lands in the assistant lane.
- A voice turn can **call a tool**.
- Voice turns **appear in the distilled entry**.
- Audio is **deleted per the retention setting AND by "delete my day"** (an ABSENCE test on the MinIO object).
- The affordance is **absent in P1–P3**.

## 4. Cross-service live-smoke (≥2 services — mandatory at VERIFY)

The money path + the tool path must be proven on a real stack, not mocks (the repo's repeated cross-service lesson): one real voice turn → STT (provider-registry) → `stream_response` (tool call) → TTS → `chat_messages` + a **non-zero** `usage_logs` row in the assistant lane + a capture decision. Then a retention sweep + a "delete my day" that removes the MinIO audio object.

## 5. Deliberately excluded

- Ambient / always-listening (D2).
- Voice as a NEW transport — it stays chat messages in the same session; no separate voice store.
- The proactive-turn seam (Phase 3) — voice is request-driven; it shares the spend lane with P3 but not the initiator seam.
