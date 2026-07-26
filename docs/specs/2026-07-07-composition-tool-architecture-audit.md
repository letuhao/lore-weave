# Composition tool architecture audit — "does the planner→writer loop actually work?"

> **Status:** Research only, 2026-07-07. No build decisions locked yet — this is the reference
> the next discussion builds on. Triggered by the user's suspicion that composition-service's ~56
> tools were designed for creative writing but are largely unexploited/scattered, and — sharper —
> that even where wiring exists on paper, it may not survive real usage (user reports hitting
> errors trying to actually use PlanForge today; QC/review-impl passes never caught a live-run
> case). That specific claim is **not yet diagnosed** — this doc is the architecture map to
> diagnose it against, not the diagnosis itself.

## 1. Complete MCP tool census (`services/composition-service/app/mcp/server.py`)

**56 tools total**, all fit a 10-group taxonomy cleanly:

| Group | Count | Tools |
|---|---|---|
| Structure/Outline | 10 | `composition_get_work`, `composition_create_work`, `composition_list_outline`, `composition_get_outline_node`, `composition_outline_node_create/update/delete/restore`, `composition_scene_link_create/delete` |
| Prose I/O (cross-service) | 2 | `composition_get_prose`, `composition_write_prose` |
| Canon rules | 4 | `composition_list_canon_rules`, `composition_canon_rule_create/update/delete` |
| Generation/Publish | 3 | `composition_generate`, `composition_get_generation_job`, `composition_publish` |
| Authoring-run/Orchestration | 11 | `composition_authoring_run_*` (list/get/create/gate/start/resume/pause/close/accept_unit/reject_unit/revert_all) |
| Motif library (CRUD+graph+recommend) | 10 | `composition_motif_search/get/book_list/suggest_for_chapter/create/archive/patch/link_list/link_create/link_delete` |
| Motif application (instantiate into scenes) | 2 | `composition_motif_bind`, `composition_motif_unbind` |
| Arc-level | 2 | `composition_arc_suggest`, `composition_arc_import_analyze` |
| Motif tenancy/spend-gated jobs | 4 | `composition_motif_adopt`, `composition_motif_mine`, `composition_conformance_run`, `composition_get_mine_job` |
| PlanForge pipeline | 8 | `plan_propose_spec`, `plan_validate`, `plan_self_check`, `plan_interpret_feedback`, `plan_apply_revision`, `plan_review_checkpoint`, `plan_handoff_autofix`, `plan_compile` |

**Tool-contract hygiene nits found:** `plan_validate` is labeled a read tool but unconditionally
writes a `validation_report` artifact and flips `plan_run.status` (tier mismatch). `plan_
interpret_feedback` is labeled a write tool but performs no repository write at all (tier
mismatch, other direction). Small fix, not yet done.

## 2. Persistence vs. consumption — which written tables are actually load-bearing

| Table | Writer(s) | Read by `pack.py` (generation prompt)? | Read by PlanForge propose/compile? | Read elsewhere non-trivial? | Verdict |
|---|---|---|---|---|---|
| `outline_node` | `outline_node_create/update`, `motif_bind/unbind`, REST-only A3 `commit_decomposed_tree` | **Y** (`packer/lenses.py:202-236`) | N (zero refs in `plan_forge_service.py`) | canon-issue checker, publish gate | Load-bearing; best writer (A3 batch decompose) is REST-only, not MCP |
| `canon_rule` | `canon_rule_create/update/delete` | **Y** (`packer/lenses.py:90-99`) | N | `canon_check.judge_canon` | Load-bearing |
| `scene_link` | `scene_link_create/delete` | **Y** (setup/payoff threads) | N | GUI | Load-bearing |
| `motif_application` | `motif_bind/unbind` | **N** (zero hits under `app/packer/`) | N | conformance trace (`composition_conformance_run`) | Nuanced, not pure waste: motif *content* is baked directly into `outline_node.synopsis/tension` at bind time (a deliberate one-way bake-in per `docs/specs/2026-06-26-narrative-motif-library.md` §0, confirmed met by `docs/reports/2026-06-29-motif-completeness-audit.md:129`). The LEDGER ROW itself is trace/GUI-only, but the content isn't lost — it rides into generation via `outline_node.synopsis`, which `gather_structural` DOES read. |
| `motif`, `motif_link` | motif CRUD/link/adopt tools | N | N | motif search/suggest, `MotifRetriever` | Feeds the bind/select engines, not `pack.py` directly — correct, one layer removed |
| `arc_template` | `arc_import_analyze` | N | N | `arc_suggest`, planning_pipeline | Planning-engine input only |
| `authoring_runs`/`_units` | authoring_run tools | N (orchestration state, not prompt content) | N | FSM gates for `generate`/`publish` | Load-bearing for orchestration |
| `plan_run`, `plan_artifact` | all 8 `plan_*` tools | **N** | Y (self only) | GUI raw-JSON review | Write-only relative to generation on its own — but see §3, the bootstrap layer bridges this for 2 of 3 artifact types |
| `style_profile` | REST-only `style_voice.py`, **no MCP tool** | **Y** (`pack.py:249-256`) | N | GUI | Load-bearing but MCP-inaccessible |
| `voice_profile` | REST-only, same router, **no MCP tool** | **Y** (`pack.py:257-265`) | N | GUI | Load-bearing but MCP-inaccessible |
| `narrative_thread` | auto-writer only (`detect_and_update_threads`) — no human/agent write path at all | **Y** (`pack.py:298,322-323`) | N | GUI debt view (deliberately read-only) | Load-bearing, fully autonomous — correctly needs no tool |
| `reference_source` | REST-only `references.py`, **no MCP tool** | **Y** (`pack.py:188-189,308,324-325`) | N | GUI | Load-bearing but MCP-inaccessible |
| `scene_grounding_pins` | REST-only `grounding.py`, **no MCP tool** | **Y** (`pack.py:432-437,560-650`) | N | GUI panel | Load-bearing but MCP-inaccessible |
| `entity_override` | REST-only, **no MCP tool** | **Y** (`pack.py:376`, derivative merge) | N | — | Load-bearing but MCP-inaccessible |

**No literal `references` table** (it's `reference_source` + the separate `scene_grounding_pins`).
**No world/places table anywhere in composition-service** — consistent with the language rule
(that's Rust-kernel territory, a different service).

**Sharpest tool-surface finding:** every table `pack.py` reads besides `outline_node`/`canon_rule`/
`scene_link` — `style_profile`, `voice_profile`, `reference_source`, `scene_grounding_pins`,
`entity_override` — is **REST-only**. Zero of the 56 MCP tools can write to any of them. **An LLM
agent driving composition purely through MCP tools cannot set prose style, character voice,
pin/exclude grounding, add references, or set entity overrides** — a human via Studio REST can,
an autonomous agent cannot.

## 3. What an approved plan actually persists — corrected picture

**Raw `plan_compile` (the MCP tool alone): does NOT persist into real structure.** Traced
`plan_compile` → `PlanForgeService.compile()` → `compile_artifacts()`: zero `outline_node` rows,
zero `motif_application` bindings, zero `canon_rule` rows, zero cast assignment, `beat_role`
**explicitly forced empty** (inline comment: PlanForge's `arc_kind` is a theme tag, not a
structure_template kind). It only INSERTs a `plan_artifact` (the JSON package) and updates
`plan_run.status`.

**BUT — this is not the current end state.** A separate layer, `bootstrap_service.py`
(the PlanForge auto-bootstrap propose→record→approve→apply gate, spec
`docs/specs/2026-07-06-planforge-auto-bootstrap.md`), was built **in this same session**, M1
through M4, status **"Phase 2 complete"** (commit `410a2225f`), review-impl'd clean
(commit `6afae09e5`). It sits on top of `compile()`'s output and, on human approval:

- **[A] creates real `Chapter` rows** via book-service (`bootstrap_service.py` → `book_client.
  create_chapter`) — done, live-verified.
- **[B] creates real Glossary entities** from the compiled spec's already-correct `glossary_seeds`
  (replacing a separate pre-existing bug where `propose_cast` silently re-derived cast blind to the
  spec) — done, live-verified.
- **[C]/[D] scene/beat plan becomes per-chapter drafting context**, fed into the EXISTING
  `run_chapter_generate` action once [A] gives it a real `chapter_id` to target — done. This is a
  **deliberate, explicit non-goal to NOT invent a persisted Scene/Beat DB row** (`docs/specs/
  2026-07-06-planforge-auto-bootstrap.md` §5) — "the whole chapter is the smallest editable unit"
  is treated as a real architectural constraint, not a gap.

**So: chapter + glossary + scene/beat-as-context ARE closed loops today** — a plan's structural
content really does reach both the book's real structure (chapters, entities) and the writer
(scene/beat context at generation time). This directly answers the earlier framing of "plan
approved, không persist" — **for these three, it's fixed, and fixed via a proven, reusable
pattern (the propose→record→approve→apply gate).**

**What the bootstrap layer did NOT extend to (still open, confirmed gaps):**
- **Canon rules never become real `canon_rule` rows.** A compiled plan's `charter.
  consistency_anchors`/`forbids` stay JSON-only inside the `plan_artifact`, never INSERTed —
  `canon_rule_create` is never called from anywhere in `plan_forge_service.py` or
  `bootstrap_service.py`. Unlike [B]'s glossary fix, canon never got the same treatment.
- **Motif has no concept in PlanForge at all.** The compiled `PlanningPackage` schema has no
  motif field; PlanForge's propose/compile pipeline and the motif library are two pipelines that
  never intersect. A PlanForge-authored plan cannot specify "this motif should recur in this arc."

## 4. Planner-vs-Writer architectural intent — drifted, or never specified?

Two independent findings, opposite verdicts:

- **The A3 decompose planner (`engine/plan.py`) and the motif bind-time bake-in are NOT drift** —
  both were explicitly specified (`docs/specs/2026-06-02-composition-design.md` §2,
  `docs/specs/2026-06-05-composition-v1-reasoning-engine.md` §10.2 for `narrative_thread`;
  `docs/specs/2026-06-26-narrative-motif-library.md` §0 for motif bake-in) and are faithfully
  wired in code as designed. Their only real gap is a tool-surface one (A3's batch commit is
  REST-only), not an architecture gap.
- **PlanForge was the genuinely under-specified one** — `plan_forge_service.py`'s own docstring
  scopes it as a closed loop over `plan_run`/`plan_artifact` only; nothing in its original design
  committed it to ever touching real book structure. The 2026-07-06 auto-bootstrap doc is the
  point where the team FIRST forced this question and built a real answer for 3 of 5 candidate
  artifact types (chapter/glossary/scene-context), consciously scoping out a 4th (scene/beat as DB
  rows — a deliberate non-goal) and simply not yet reaching a 5th and 6th (canon, motif — not
  discussed in that doc at all).

**Bottom line:** the "designed for writing, never systematically exploited" framing was too broad
as originally stated. It's precisely true for **2 specific gaps** (canon-in-plan, motif-in-plan)
and for **the MCP tool-surface hole** (5 REST-only generation-input tables + A3's commit path) —
not for the architecture as a whole, most of which (outline, canon **enforcement** at generation
time, scene-links, narrative threads, motif bake-in) is specified and working.

## 5. Open, undiagnosed issue — real-world PlanForge usage is reportedly broken

**User's pushback (2026-07-07):** despite M1-M4 being "Phase 2 complete" with a clean review-impl
pass, the user reports hitting real errors trying to actually use PlanForge/chat tools today, and
observes that **QC/`review-impl` never caught a live-running-system case** — matching this repo's
own known failure pattern (mock-only test coverage hiding cross-service contract bugs, per memory
`new-cross-service-contract-needs-consumer-live-smoke` and `prefer-e2e-and-evaluation-over-live-smoke-poc`).

## 6. Diagnosed + live-reproduced (2026-07-07) — `glossary_web_search` fails in a bookless chat

**Reported symptom:** user asked a bookless general-purpose chat session (`chat_sessions.book_id`/
`project_id` both NULL, `enabled_tools: [glossary_web_search, glossary_deep_research]`) to search
today's news; the tool never worked. User's own hypothesis: "these tools only work when you have
a book and glossary." **That hypothesis is wrong** — confirmed by reading `glossary_web_search`'s
actual Go source (`services/glossary-service/internal/api/web_search_tool.go`): its own doc-comment
states *"Identity is the caller… no book grant — the search uses the user's own provider credential
+ their own spend, touching no book data"* — it is explicitly designed to need no book.

**Investigation (DB-first, then live repro):**
1. Pulled the real failing session from `loreweave_chat.chat_messages` (`session_id
   019f38aa-c817-78b6-a686-dc9fe13cff6f`). `tool_calls` shows `glossary_web_search` called 3 times,
   every call with `args: {}` and error `validating "arguments": ... missing properties: ["query"]`.
   Model: `google/gemma-4-26b-a4b-qat` via LM Studio (`user_models.user_model_id
   019f33f5-fa03-7acd-887d-8da1bf8a1b26`), `generation_params.reasoning_effort: "high"`.
2. Container logs from the original incident were gone (chat-service had since restarted) — could
   not inspect the original raw provider stream directly.
3. **Live-reproduced from scratch** against the real running stack, same conditions: created a
   fresh bookless session (test account, model `019ebb72-27a2-72f3-a42d-d2d0e0ded179` — the test
   account's own instance of the identical `google/gemma-4-26b-a4b-qat` model), same
   `reasoning_effort: "high"`, same `enabled_tools`, sent "tìm giúp tôi tình hình thời sự hôm nay
   bằng tool glossary_web_search" through the real gateway (`POST /v1/chat/sessions/{id}/messages`,
   real SSE stream captured to disk). **Reproduced byte-for-byte the same failure.**

**Root cause, confirmed from the raw stream (not the DB summary):**
- The model's own reasoning correctly plans the query: `reasoning-delta` shows *"...with the query
  \"tình hình thời sự hôm nay\"."* — the model knows exactly what to search for.
- The model attempts the tool call 3 times, each `{"type":"tool-call","tool":"glossary_web_search",
  "ok": false}` — matching the DB's empty-args finding exactly.
- **On the 4th attempt, the raw special-token tool-call format leaks directly into visible chat
  text** instead of being parsed as a structured call:
  ```
  <|tool_call>call:glossary_web_search{query:<|"|>tình hình thời sự hôm nay<|"|>}<tool_call|>
  ```
  This is **not valid JSON** — no real `"` characters (a `<|"|>` pseudo-token stands in for the
  quote), no `key: value` JSON syntax. This is this specific GGUF quant's OWN tool-call chat
  template, and LM Studio's OpenAI-compatible layer is not correctly translating it into a proper
  `function.arguments` JSON string before handing it to provider-registry/chat-service.
- `finishReason: "stop"` (not `"length"`) — ruling out the token-budget-exhaustion hypothesis I
  initially proposed (which was grounded in a real, but DIFFERENT, same-session bug — the PDF-
  caption `max_tokens` fix, HIGH#3 in `docs/sessions/SESSION_HANDOFF.md`'s PDF-import entry). Model
  reasoning-heavy, but it completes normally; the failure is purely in the tool-call **argument
  encoding**, not premature truncation.
- `_parse_tool_args()` (`services/chat-service/app/services/stream_service.py:479-489`) correctly
  guards against the resulting malformed JSON (`except (ValueError, TypeError): return {}`) — this
  is working as designed, not a chat-service bug. **But it has zero logging on this path** — a
  malformed non-empty `arguments` string silently collapses to `{}` with no trace, indistinguishable
  from a genuinely-empty string. This is the concrete, fixable gap: right now this failure mode is
  only visible as a confusing downstream "missing required field" error with no link back to what
  the provider actually sent.

**What this is, and isn't:**
- **Is:** a LM Studio + this specific `google/gemma-4-26b-a4b-qat` GGUF tool-calling-template
  incompatibility — an external tool/model limitation, not a LoreWeave architecture defect.
- **Is also a real, fixable gap on our side:** `capability_flags.tool_calling: true` is set for this
  model in provider-registry (both the original user's and the test account's instance) — this
  live-reproduced failure shows that flag is **overclaiming** a capability this model cannot
  reliably deliver via LM Studio. Silently offering tools to a model that will reliably mangle
  their arguments is worse than not offering them.
- **Isn't:** a "tool only works in book context" bug (that hypothesis is refuted by the source
  code), and isn't the reasoning-token-budget bug I first guessed (refuted by `finishReason:"stop"`).

**Follow-up empirical test (2026-07-07) — can MCP tool descriptions / skill/system-prompt tuning
fix this? Tested directly, answer: no.** User's reasonable hypothesis: this model is one of the
stronger mid-size local models available, so maybe better instructions could get it to emit valid
JSON. Ran 2 controlled A/B repros against the real running stack, same tool/query, same model:
- **Lower reasoning effort** (`"low"` instead of `"high"`): identical failure — 4 failed attempts,
  the malformed `<|tool_call>...<tool_call|>` pattern leaking into BOTH `reasoning-delta` and
  `text-delta` this time (arguably worse). Rules out reasoning intensity as the variable.
- **Explicit, aggressive system-prompt instruction** ("CRITICAL TOOL-CALL FORMAT RULE: … MUST emit
  arguments as strictly valid JSON using standard ASCII double-quote characters … NEVER use any
  other token … Example: `{"query": "example text"}` … Do not use markup like `<|...|>`"): **same
  failure, same exact malformed pattern**, byte-for-byte the same shape.

**Conclusion: this is not reachable from prompt/instruction engineering.** The malformed
`<|tool_call>call:NAME{key:<|"|>value<|"|>}<tool_call|>` wrapper is almost certainly produced by
LM Studio applying a **grammar-constrained sampling template** for this model's tool-calling
format — grammar constraints operate at the token-sampling level and by construction ignore what
the system/user prompt says, which is exactly the observed behavior (the model can't "choose" to
follow a formatting instruction that's being enforced by a sampling grammar it has no visibility
into). No amount of MCP tool-description or skill-prompt tuning on the chat-service/glossary-service
side can reach this layer — the fix, if there is one purely on our side, has to be a **parse-time
salvage** (recognizing this specific, now well-characterized malformed shape and repairing it
before `json.loads`), not a prompt change. The actual template/grammar mismatch is LM Studio's
config for this GGUF, outside this repo.

**Shipped 2026-07-07 (both fixes, per user direction "keep the parse fix + add the cross-channel
salvage").** `services/chat-service/app/services/stream_service.py`:

1. **`_parse_tool_args` repair** — tries `json.loads` as-is, then Gemma-token de-mangling
   (`_degemmify_tool_args`) + `json_repair` (new dependency, `json-repair>=0.30`, MIT — [PyPI](https://pypi.org/project/json-repair/))
   as a general net, gated on `_braces_balanced` so a genuinely truncated stream still degrades
   hard instead of being guess-repaired into a plausible-but-unverifiable value. Logs a warning on
   final failure (was silent before).
2. **Cross-channel salvage** (`_extract_leaked_tool_calls` + wiring in `_stream_with_tools`) — when
   a pass abandons the structured `tool_calls` channel entirely and dumps
   `<|tool_call>call:NAME{...}<tool_call|>` into plain `content`/`reasoning_content` instead
   (confirmed live: this happens on the pass where LM Studio gives up on the structured channel
   after ~3 empty-argument attempts), the loop now recovers `(name, args_body)` from the leaked
   text and executes it as if it had been a real tool call — instead of ending the turn empty-
   handed. Also patches a structured call's empty args from a same-named leak in the same pass, for
   the (not yet observed, but plausible) case where both co-occur.

**Live-verified end-to-end, real backend, real data** (not a mock): reproduced the exact original
failing scenario (bookless session, same model, `reasoning_effort: "high"`, same Vietnamese
query) — `glossary_web_search` executed successfully via the salvage path and returned REAL current
Vietnamese news (vietnamnet.vn, tuoitre.vn, baomoi.com sources) confirmed by direct DB read of
`chat_messages.tool_calls` (`"ok": true`, real `sources[]`). This is the first time this tool
actually worked for this model in a bookless chat.

**Known residual gap, not fixed (separate concern, flagged not silently dropped):** after the
salvage executes the tool, the model's FOLLOW-UP pass (meant to write a coherent answer using the
search results) produced no text at all — `chat_messages` showed only 1 assistant row, containing
the raw leaked tokens as `content`, no summary.

**Root-caused + fixed same session (user pushed back: "otherwise calling web search is pointless").**
Traced via a temporary debug print at the `while True:` loop's top (`iteration`/`write_passes` per
pass) — the loop stopped dead after exactly the salvage-success pass, no further iteration. Cause:
a PRE-EXISTING D7 termination guard, `if not offered_tools: break` — designed for a different,
older edge case ("the model was NOT offered tools this pass yet defiantly emitted a tool_calls
response anyway → something's wrong, bail out without looping"). The salvage pass is, by
construction, almost always exactly this "tools not offered" pass (D7's own forced-tool-free FINAL
pass is precisely where a broken-template model gives up on the structured channel and dumps its
native tokens as plain text instead) — so every successful salvage recovery tripped this old guard
and ended the turn immediately, before the model ever got a chance to read and use the tool result.
Fixed with a `salvaged_this_pass` flag (true when a pass's entire call set came from the leak scan,
i.e. `tool_frags` was empty): `if not offered_tools and not salvaged_this_pass: break` — a genuinely
recovered+executed call earns one more force-tool-free pass (bounded by the pre-existing
`max_total_passes` hard cap regardless, so no infinite-loop risk). New regression test
`test_salvaged_call_on_the_forced_final_pass_still_gets_a_followup` reproduces the exact
`max_iterations=1` shape that forces `offered_tools=False` on the very first pass. **Live-reverified
end-to-end**: same session/model/query — the assistant's second pass now writes a full, coherent
Vietnamese summary structured with headers/bullets over the real search results (a fire incident in
Phú Thọ, a National Assembly military-service petition, etc.) — not the PDF-caption token-budget
class of bug at all; a pure control-flow bug, unrelated to `max_tokens`.

**Bonus fix, found while re-verifying — a real, separate, unrelated regression, `D-RESUME-TOOLS-DROPPED`:**
while root-causing why the live salvage test's tool call showed `req.tools == []` before the
salvage code even engaged, traced (NOT via any uncommitted concurrent-session diff — confirmed via
`git show HEAD` — this was already on the last commit, `4fa6f7979`) that `_emit_chat_turn`'s branch
selector `if (use_tools or _subagent_tool is not None) and not is_resume:` conflated two unrelated
questions: "should this turn use the stateful `/v1/responses` chain" (correctly `False` on resume,
per its own adjacent comment) and "should this turn go through `_stream_with_tools` at all" — the
`and not is_resume` silently forced EVERY resumed turn through the plain no-tools
`_stream_via_gateway` path, even when it had real tools to offer. This directly re-broke the exact
fix `resume_stream_response`'s own comment describes ("Going through `_stream_with_tools` keeps the
seed and re-advertises the tool"). Fixed by nesting: the outer branch is `if use_tools or
_subagent_tool is not None:` (unconditional), and only the INNER stateful-chain decision sub-block
is additionally gated on `not is_resume`. This was the true root cause of 4 pre-existing test
failures (`test_admin_resume_readvertises_admin_catalog_only`,
`test_resume_with_no_memory_tools_sums_usage`, `test_resume_continues_under_plan_rules`,
`test_resume_curated_seed_uses_pins_not_full_hot_set`) that had been confirmed pre-existing via
stash A/B earlier in this session, then root-caused and fixed at the user's explicit follow-up
request ("clear luôn 4 fail pre-existing"). Full suite: 1105/1105 passed after the fix (was
1099 passed / 4 failed). This bug affected every resumed frontend-tool/tool-approval turn in
production — a much bigger blast radius than the web-search scenario that led to finding it.

**Not yet decided — remaining options for the user (LM Studio/model-level, outside this repo):**
1. Test whether OTHER tool-calling-flagged local models (Qwen2.5/Qwen3 in the same account) hit the
   same malformed-template issue, to know if this is Gemma-specific or a broader LM Studio pattern.
2. Consider whether `capability_flags.tool_calling` should carry a caveat/confidence tier per model
   rather than a flat boolean, given this model DOES eventually work (via salvage) but not cleanly.
3. ~~The raw leaked tokens still render at the START of the visible assistant message~~ →
   **RESOLVED same session.** `_split_safe_emit()` holds back content/reasoning deltas from the
   earliest point they could be the start of `<|tool_call>` (exact or partial-at-tail match) instead
   of forwarding every token live; resolved at pass-end — dropped if a real leak is confirmed,
   flushed as normal content if it was a false alarm (e.g. real prose starting with `<`), so nothing
   genuine is silently lost. Live-reverified: the raw marker no longer appears anywhere in the SSE
   wire or in `chat_messages.content` — the assistant's visible answer starts directly with the real
   summary.

**`/review-impl` same session — 1 MED finding, fixed; 1 accepted scope boundary, documented.**
- **MED (fixed):** `_extract_leaked_tool_calls`'s regex output is free-form — a leaked name was
  executed without checking it was ever actually offered this turn. Untrusted content re-entering
  context (e.g. a web-search snippet — already flagged untrusted DATA at the tool layer, per
  `glossary_web_search`'s own `Note` field — or any hallucination) that happens to contain
  `<|tool_call>call:some_other_tool{...}<tool_call|>` would have been salvaged and executed, even
  for a tool never in this turn's set. Tier/approval gating still applies uniformly to a salvaged
  call (not bypassed — no privilege escalation), but an unvalidated name could still reach
  `execute_tool` needlessly. Fixed: leaked names are filtered against `active_tool_names` (discovery
  surfaces) or the plain `tools` list (non-discovery), dropping + logging anything not genuinely
  reachable this turn, before execution. New regression test
  `test_leaked_call_for_an_unoffered_tool_is_dropped_not_executed`.
- **Accepted scope boundary:** `_extract_leaked_tool_calls`'s regex only recognizes the exact
  `<|tool_call>call:NAME{...}<tool_call|>` shape confirmed live for this model/quant. A differently-
  shaped malformation from a different model/LM-Studio version would fall through to the pre-
  existing D7 defensive-limit chunk (empty final text) — the original bug, for a different token
  shape. Documented, not silently uncovered; extend the regex if/when a second shape is observed.
- Full suite re-verified after both the cosmetic fix and the review-impl fix: 1116/1116 passed
  (was 1105 before this session's additions). Live-reverified end-to-end once more after the
  security fix: `glossary_web_search` still salvages+executes correctly (the real tool stays in
  `active_tool_names` for the whole turn once genuinely offered on an earlier pass).

## Reference file index (for the next research pass)

`services/composition-service/app/mcp/server.py`, `app/packer/pack.py`, `app/packer/lenses.py`,
`app/packer/assemble.py`, `app/engine/plan_forge/{propose,propose_llm,compile}.py`,
`app/services/plan_forge_service.py`, `app/services/bootstrap_service.py`,
`app/engine/planning_pipeline.py`, `app/engine/motif_select.py`, `app/db/migrate.py`,
`app/routers/{plan,style_voice,references,grounding,plan_bootstrap}.py`; specs:
`docs/specs/2026-06-02-composition-design.md`, `docs/specs/2026-06-05-composition-v1-reasoning-engine.md`,
`docs/specs/2026-06-26-narrative-motif-library.md`, `docs/specs/2026-07-06-planforge-auto-bootstrap.md`,
`docs/reports/2026-06-29-motif-completeness-audit.md`.

See also [`21_plan_hub.md`](2026-07-01-writing-studio/21_plan_hub.md) (the GUI-side track this
audit grew out of) — that doc's Wiring-architecture and Generation-exploitation-gaps sections
overlap with §2-4 here; this file is the deeper backend reference, that one is the Studio-panel
design built partly on top of it.
