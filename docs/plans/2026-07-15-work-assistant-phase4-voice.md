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

| Slice | Title | Scope | Depends on | Risk |
|---|---|---|---|---|
| **WS-4.0** | Two-stores reconcile (PREREQ) | Land `D-CHATAI-VOICE-TWO-STORES-ENUM` (the voice settings-store migration) FIRST — building on a mid-migration store forks it (spec 12 Q3#4 · P4-D1). `settings_resolution.py` is the touch point. | — | Med — a settings migration; must complete before the rest. |
| **WS-4.1** | Route voice through the text agent loop | Replace the `_stream_via_gateway` direct call with the shared `stream_response` path (~70% already shared, per the code comment). Voice turns then inherit tools, skills, **capture**, and context-budget frames for free — fixing defects #1 AND #3 in one move. | WS-4.0 | 🔴 High — the load-bearing change; live-smoke a real voice turn calling a tool + firing capture. |
| **WS-4.2** | Real usage accounting | Fix the `0/0` billing (defect #2): meter STT + LLM + TTS token/spend into the **assistant lane** so the spend lane + daily cap see voice. STT/TTS are BYOK provider calls → capture their real usage from the provider-registry response. | WS-4.1, spend lane (WS-2.8, built) | Med — money path; live-smoke that a voice day accrues real spend, not zero. |
| **WS-4.3** | Audio retention policy | Transcripts kept (they ARE the journal source); **audio** retention **user-set, default 7 days** (P4-D4), settable to 0 (delete audio the moment its transcript is written) up to a bounded max. A retention sweeper purges expired MinIO audio objects (never purged today). | WS-4.0 (settings store) | Med — MinIO object lifecycle + a bounded sweeper. |
| **WS-4.4** | Audio joins erasure | Audio segments join the erasure copy-set AND "delete my day" — the scoped-erasure primitive (WS-2.6c/2.10d/D-R27) gains a MinIO-audio leg. | WS-4.3, erasure primitive (built) | Med — extend the existing cascade with an object-store delete + an ABSENCE test. |
| **WS-4.5** | Affordance gating | Voice input hidden/disabled for assistant-bound sessions in P1–P3 (P4-D5); a reachable voice turn logs `reason='voice_path_unsupported'` in the capture decision. (This is the *guard until WS-4.1 lands*; once P4 ships, the affordance turns on.) | — | Low — an FE gate + a capture-decision log line. |

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
