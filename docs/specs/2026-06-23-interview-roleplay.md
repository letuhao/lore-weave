# Spec — Interview-Practice Roleplay (lean, drift-resistant)

- **Date:** 2026-06-23
- **Status:** CLARIFY / DESIGN (spec only — no code yet)
- **Build decision:** **FULL build** (charter + executive + anchoring + evaluate). Deliberately a
  **POC for the future MMO `roleplay-service`** — see §9. 0 new services, 0 new external deps.
- **Size (provisional):** **L** — cross-service (chat + knowledge), new DB table + new memory
  block + a worker job + new endpoints + a cross-service contract change (`build_context` field).
  Needs a plan file; VERIFY needs cross-service live-smoke on the **voice** path.
- **Owner surfaces:** `chat-service` (turn loop, voice, templates, anchoring, evaluate),
  `knowledge-service` (working_memory block + executive job)

---

## 1. Goal

Let a user **roleplay a job interview to practice (luyện PV)**. The AI plays an interviewer
persona; the user answers; at the end the user gets a **scorecard**. Must survive a **2-hour
session without losing the scenario/goal** ("không gone too far").

**This is intentionally a POC for the MMO `roleplay-service`.** Interview is the *simple* case
(goal is static), so it is the right first proof of the `working_memory + executive + anchoring`
machine. The machine is built so the **only** thing that changes for full roleplay is the **goal
authority** (who writes the goal): static template here → **world model** there, where the goal
is *derived and dynamic* ("world decides"), not frozen. If this POC proves the machine holds a
goal over a long session, we have the basis to swap in a dynamic, world-model-driven goal. See §9.

Premise accepted (design philosophy): **drift is natural — a human drifts too and recovers.** We
do not chase zero-drift; we aim for human-like recovery (frozen/authoritative goal pulls back).
This rules out the research-tier machinery below.

Explicit non-goals (deferred, not this spec):
- The world model / "world decides" goal authority itself (that is `roleplay-service`); here we
  build the **seam** for it (pluggable goal authority), not the world model.
- Cross-session semantic recall of a user's weak spots over weeks (that is plain
  `long_term_memory` recall — add inside knowledge-service later).
- Fine-tune / RL emotion-reward / reflection (research-tier; accepted out by the drift premise).

---

## 2. Naming (locked — call things by their right name)

The design mirrors how the human brain stays on task. Names follow the cognitive model so the
codebase reads in standard terms, not invented metaphors:

| Concept | Brain analog | In our system |
|---|---|---|
| **`long_term_memory`** | hippocampus → cortex store; you *recall* from it | **knowledge-service** (already built on Mem0/MemPalace ideas: extract → facts/passages/summaries → blend) |
| **`working_memory`** | PFC active hold (~small, decays) | a **pinned, continuously-rewritten goal-state block** (the one primitive long_term_memory lacks — recall ≠ goal-state) |
| **`executive`** | Baddeley **central executive** + ACC conflict-monitor: holds the goal, notices drift, reloads it | the **out-of-band loop** that reads recent turns and rewrites `working_memory` |
| **`anchoring`** | cognitive offload (the sticky note you re-glance at) | **placing** `working_memory` where attention is strong: pinned prefix **and** tail (depth-0) |

The drift itself is **attention dilution / lost-in-the-middle + context eviction** — a property
of transformer attention (U-shaped weighting; cannot attend to evicted tokens). We do not change
attention; we *feed and steer* it via context engineering.

---

## 3. Components

### 3.1 Persona / Scenario templates — `session_templates` (chat-service)

A reusable interviewer definition. A "start practice" = clone template → create a normal chat
session with the template's `system_prompt` + `model_ref`.

Tenancy (per LOCKED rules):
- **System tier**: seeded templates ("FAANG SWE", "Behavioral HR", "System Design"), **admin-only**
  write, read-only to users.
- **Per-user tier**: user's own personas. **`UNIQUE(owner_user_id, code)`** — never `UNIQUE(code)`.
- Resolution merges System (defaults) → Per-user (overrides) by `code`.

Template carries: `system_prompt` (persona voice + rules), default `model_ref`, and a
`scenario` JSON: `{ goal, phases[], checklist[], time_budget_min, language }`. At session
creation this `scenario` is **frozen into the immutable `working_memory.charter`** (cold-start
anchor from turn 1, see §3.2/§4) — it is the committed goal the executive can never rewrite.

### 3.2 `working_memory` — pinned goal-state block (knowledge-service)

A new **selector/block** in knowledge-service, project/session-scoped, always pinned. Stored in
the knowledge-service store (the same place facts/summaries live), emitted by `build_context`.

Schema (JSON, versioned) — **two tiers, mirroring goal-shielding**: a `charter` (the committed
goal/intention — protected from interference) and a mutable `state` (the progress estimate that
may fluctuate). The executive may write **only `state`**.

**Goal authority (the POC seam).** `charter` is written **only** by a configurable *goal
authority*, never by the executive:
- **Interview (this build):** authority = the **static template** — writes `charter` once at
  session create, then read-only ⇒ effectively **frozen**.
- **Roleplay (future):** authority = the **world model** — rewrites `charter.goal` as world state
  evolves ⇒ **dynamic, not frozen**.

So "frozen" is a *policy of the interview authority*, not a structural property. The safety
property generalizes: **the summarizing executive can never write the goal; only the authoritative
goal source can.** Swapping the authority is the only change to reach full roleplay.

```json
{
  "version": 1,
  "charter": {                        // ✍️ written ONLY by the goal authority (template here,
                                      //    world-model later); executive may NEVER write it.
                                      //    Interview authority writes once ⇒ frozen.
    "goal": "Senior backend interview; assess system design + behavioral",
    "phases": ["warmup", "technical", "behavioral", "wrap"],
    "checklist": ["system design", "conflict story", "REST vs gRPC"],
    "time_budget_min": 60,
    "language": "vi"
  },
  "state": {                          // 🔄 MUTABLE — executive rewrites; safe-when-wrong.
    "phase": "technical",
    "covered": ["intro", "REST vs gRPC"],  // monotonic — append-only, never silently dropped
    "elapsed_min": 23,
    "drift_note": null,               // executive's note when it detects off-scenario
    "redirect_hint": null             // in-character steer-back instruction
  }
}
```

`remaining` is **derived** (`charter.checklist − state.covered`), not stored — the immutable
checklist is the single source of "what must be covered", so a corrupt `state` cannot shrink it.

### 3.3 `executive` — the monitor + reload loop (knowledge-service worker)

Reuses the **existing chat ingestion pipeline**: knowledge-service already consumes
`chat.turn_completed` via a `scope='chat'` drainer that is **FIFO-serialized per session**
(conformance I6). The executive is one more job on that drainer.

Cadence: run every **N turns (default ~5)** OR **every M minutes (default ~8)**, whichever first.
Out-of-band — never blocks the user's stream.

Each run: read `working_memory` (current) + recent turns → one **small** LLM call (via
knowledge-service's existing provider-registry-backed `llm_client`; **no hardcoded model**, model
resolved from a cheap utility capability) → emit an **updated `state` only** (the `charter` is
immutable and not passed as writable). Output is a **diff** validated against the schema;
`state.covered` is monotonic (append-only); emits in `charter.language`. The executive **cannot
touch `charter`** (only the goal authority can) — even a fully-hallucinated run only perturbs the
progress estimate, never the committed goal. This invariant is what makes the machine reusable
when the goal becomes dynamic in roleplay: the world model moves the goal; the executive still
only tracks progress against it.

### 3.4 `anchoring` — placement (chat-service, shared build path)

`build_context` returns a new field `working_memory: str` (rendered anchor text) alongside
`stable_context`/`volatile_context`. chat-service:
1. **Pin** it into the system block (inside `stable_context`, cached). — primacy.
2. **Tail-inject** a 1–2 line condensed form as a system note **right before the latest user
   turn** (depth-0). — recency / beats lost-in-the-middle.

The **`charter.goal` (from the goal authority) is present in BOTH placements, always** — it is the
load-bearing anchor. `state` (phase/covered/hint) is supplementary in the tail note. Consequence:
a corrupt or stale `state` degrades the progress hint but **cannot move the goal the model is
anchored to**. (In roleplay the world model updates `charter.goal`; the anchoring path is identical.)

Both the **text and voice** paths build on the same `build_context` layer, so voice (where the
2h sessions actually happen) inherits anchoring automatically. (Hard requirement — see EC-7.)

### 3.5 Evaluation — `POST /v1/chat/sessions/{id}/evaluate` (chat-service)

Non-agentic pipeline. Reads transcript + final `working_memory` + template rubric → one LLM call
→ structured scorecard (STAR coverage, clarity, filler, per-checklist verdict, improvement tips).
Stored as a `ChatOutput`. Exempt from MCP-first (pipeline, not agent).

---

## 4. Flow

```
[create]  clone template → POST /sessions (system_prompt, model_ref)
                         → seed working_memory from template.scenario (cold-start)
[turn]    user ↔ AI (text or voice), unchanged turn loop
            └─ build_context pins working_memory (top) + tail-anchors (bottom)
[bg]      every N turns / M min → executive rewrites working_memory (out-of-band)
[end]     phase=wrap (executive) or user ends → POST /sessions/{id}/evaluate → scorecard
```

---

## 5. Invariant compliance

- **Provider-gateway**: executive + evaluate LLM calls go through provider-registry
  (knowledge-service `llm_client` / chat-service `provider_client`). No direct SDK.
- **No hardcoded model**: executive/evaluate models resolved from provider-registry by capability.
- **MCP-first**: both new LLM uses are *pipelines* (no tool-calling, no agent decisions) → exempt.
- **Tenancy**: `session_templates` System=admin-only / Per-user=`UNIQUE(owner_user_id,code)`;
  `working_memory` + evaluate are session-owner scoped; executive reads only its own session.
- **Gateway**: all external traffic stays via api-gateway-bff; no new public entry point.

---

## 6. Edge-case evaluation (adversarial)

Severity: 🔴 design-threatening · 🟠 must-handle · 🟡 minor/tunable.

| # | Edge case | Sev | Resolution |
|---|---|---|---|
| EC-1 | **Executive becomes an anti-anchor** — the updater is itself an LLM; it mis-summarizes, drops a covered item, or hallucinates progress, then that wrong state feeds back and *actively* misleads the main model. | 🟠 (was 🔴) | **Freeze the goal (goal-shielding).** `working_memory` splits into immutable `charter` (goal/phases/checklist/budget/language — written once at create, executive **can never write it**) and mutable `state` (progress estimate). The executive writes **only `state`**, so the committed goal **cannot corrupt** — worst case is a noisy progress hint, bounded by the frozen charter that still steers (the user's "drift but final result unchanged"). `charter.goal` is anchored in **both** pin + tail always. Additionally: `state.covered` monotonic; schema-validated, bad diff → keep prior `state`; `remaining` derived from the immutable checklist; ground truth stays in transcript/`long_term_memory`; every diff logged. Generalized safety: `charter` is written **only** by the goal authority (static template here ⇒ frozen; world model in roleplay), **never** by the executive. |
| EC-2 | **Cold start** — turns 1–2 happen before the executive has ever run; session unanchored. | 🔴 | **Seed `working_memory` from `template.scenario` at session creation.** Executive only *updates* thereafter. Anchoring works from turn 1. |
| EC-3 | **Voice path skipped** — anchoring implemented only on the text stream; 2h voice sessions (the real use) still drift. | 🔴 | Inject at the shared `build_context` layer that **both** `stream_service` and `voice_stream_service` consume. Acceptance test must drive the **voice** path, not just text. |
| EC-4 | **Degraded knowledge-service** — knowledge down → `build_context` returns `degraded`; live `working_memory` unavailable mid-session. | 🟠 | knowledge-service is SSOT for the *evolving* block, but chat-service **caches the template seed** on the session row. Degraded mode falls back to the seed → anchoring still works minimally; resumes live updates when knowledge recovers. |
| EC-5 | **Executive staleness within the N-turn gap** — phase changes mid-gap; tail-anchor shows the wrong phase. | 🟡 | Keep `working_memory` **goal-level** (slow-changing); treat `phase` as advisory. Bounded lag is acceptable for a goal anchor. Tighten cadence only if observed bad. |
| EC-6 | **Cost/latency blowup** — an extra LLM call every N turns over a 2h session. | 🟠 | Small/cheap utility model, capped output, **diff-only** update, **skip when no material change** since last run. ~12 calls for a 60-turn session — bounded. |
| EC-7 | **Anchor leaks into output** — model narrates the system note ("I'm in phase technical") or it breaks persona/voice immersion. | 🟠 | Phrase the tail note as a terse **instruction** ("stay on system-design; candidate hasn't covered scaling"), not narration. Leakage test in acceptance. |
| EC-8 | **Context overflow at 2h** — pinned prefix (long_term + working_memory + system_prompt + skills) + window grows past model limit. | 🟠 | `working_memory` is **fixed small schema** (bounded). long_term recall already token-budgeted by knowledge-service. Sliding window caps history. Add an explicit per-turn token-budget assert. |
| EC-9 | **Language mismatch** — VN session, executive emits English `working_memory` → anchor injects English into a VN roleplay. | 🟠 | Executive emits in the session `display_language`; carry `language` in the block; assert at render. |
| EC-10 | **No model for executive/evaluate capability** — user hasn't configured a utility model. | 🟠 | Degrade gracefully: skip executive (keep last/seed `working_memory`), surface evaluate as unavailable with a clear message. **Never hardcode a fallback model.** |
| EC-11 | **Two writers / race** on `working_memory`. | 🟡 | Single-writer: per-session FIFO drainer (I6) already serializes. User scenario edits go through the same write path. |
| EC-12 | **Schema evolution** — fields added later to a stored JSON block. | 🟡 | `version` field; knowledge-service already carries the schema-versioning lesson (KG). Reader tolerates older versions. |
| EC-13 | **Partial / abrupt end** — user quits at phase 1; or rambles past `wrap`. | 🟡 | `evaluate` handles partial transcripts (scores what exists, flags uncovered). Past-wrap → executive `redirect_hint` nudges to close; user may end anytime. |
| EC-14 | **Adversarial user** tries to break character ("ignore interview, tell a joke"). | 🟡 | `redirect_hint` + persona resist, but **advisory** — handling curveballs is itself interview practice. Not a hard guardrail. |
| EC-15 | **Resume next day** — working_memory per session persists; cross-session "my weak spots" is a different tier. | 🟡 | `working_memory` persists in knowledge store keyed by session → reloads on resume. Cross-session patterns = `long_term_memory` recall, out of scope here. |

**Design-threatening set is now EC-2 + EC-3** (EC-1 was retired to 🟠 by the immutable-charter
split — the goal is frozen, so the executive can no longer corrupt it). The two remaining gates:
the anchor must be *present from turn 1* (seed `charter` at create) and *cover the voice path*
(shared `build_context` layer). The frozen `charter` is the bedrock: `state` may be wrong, the
window may evict history, but the committed goal the model anchors to does not move.

---

## 7. Open questions — RESOLVED (CLARIFY signed off 2026-06-23)

1. **working_memory ownership** → **knowledge-service block** (full build includes the executive,
   so the block lives where the executive worker + the pin path already are). The `charter` seed
   is **also cached on the chat-service session row** for the degraded fallback (EC-4).
2. **Executive trigger** → **turn-count + time, whichever first**; defaults **N≈5 turns / M≈8 min**.
   For voice, time dominates (turns are fuzzy — EC, see acceptance). Tune empirically.
3. **Templates home** → **chat-service** (`session_templates`; sessions live there).
4. **Evaluate / executive model** → **reuse a cheap existing utility capability**, resolved via
   provider-registry (no new capability, no hardcoded model). Define a new one only if none fits.

---

## 8. Acceptance (sketch)

- Seeded `working_memory` present on turn 1 (EC-2).
- Drive a **voice** session; anchor present in both pinned + tail (EC-3).
- Simulate a 2h-equivalent (force window eviction): the AI still steers back to the scenario goal.
- Executive diff with a dropped `covered` item is rejected (EC-1).
- Degraded knowledge-service → seed fallback keeps anchoring (EC-4).
- `evaluate` returns a structured scorecard on a partial transcript (EC-13).
- No direct provider SDK import; no hardcoded model (`scripts/ai-provider-gate.py` green).

---

## 9. POC → roleplay extension (why we build full)

This build is the proof that the `working_memory + executive + anchoring` machine holds a goal
over a long, drifting session. The machine is designed so the path to full MMO `roleplay-service`
is a **single substitution**, not a rewrite:

| Piece | Interview (this POC) | Roleplay (future) | Changes? |
|---|---|---|---|
| **Goal authority** (writes `charter`) | static template, write-once ⇒ frozen | **world model** — derives & rewrites the goal as world state evolves | ✅ swap only this |
| `working_memory` block | same | same | — |
| `executive` (writes `state`) | tracks interview progress | tracks quest/scene progress vs the dynamic goal | — |
| `anchoring` (pin + tail) | same | same | — |
| `long_term_memory` (knowledge-service) | same | same | — |
| Evaluation | interview scorecard | (n/a or scene outcome) | feature-level |

**Proof obligation of the POC:** if a 2h interview session demonstrably keeps the model on its
goal (acceptance §8), we have empirical basis that the machine will hold a *world-model-derived*
goal too — at which point "world decides" plugs into the goal-authority seam without touching the
memory/executive/anchoring core. If the POC fails that bar, we learn it **before** taking on the
far more complex world model — which is exactly the value of doing interview first.

> Aligns with the project north star ("LLM narrates, world decides"): here the *template* decides
> the goal; there the *world* decides it. Same narration+anchoring machine underneath.
