# Post-fanout live verification — 2026-07-08

Final VERIFY pass for the combined fan-out round covering
[`docs/plans/2026-07-07-mcp-discovery-and-reliability-hardening.md`](../../plans/2026-07-07-mcp-discovery-and-reliability-hardening.md)
(slices A1-A5, B1-B3 + reconciliation) and
[`docs/plans/2026-07-07-intent-skill-router.md`](../../plans/2026-07-07-intent-skill-router.md)
(F0, F2, and this document = **F3**). All code changes were **uncommitted working-tree
diffs** at the time of this pass (branch `feat/context-budget-law`) — per `CLAUDE.md`'s
cross-service live-smoke rule and the repo memory
`live-smoke-rebuild-stale-images-first`, the dev stack was rebuilt from the current
working tree before any live test ran (Task 1), not trusted from already-running
containers.

Four tasks, in order: (1) stack rebuild, (2) the original 4-session Vietnamese
web-search repro, (3) Part E's eval harness re-run (F3 itself), (4) the external
audit's #2/#3 live re-verify.

---

## Task 1 — Stack rebuild

Per repo memory `live-smoke-rebuild-stale-images-first`, the containers running before
this session (`chat-service` built ~1h earlier, git_sha label `4f655d42f...`) predated
the fan-out's uncommitted diffs. Rebuilt the 7 services this fan-out touched:

```
cd infra && docker compose build chat-service ai-gateway mcp-public-gateway \
  glossary-service composition-service knowledge-service lore-enrichment-service
docker compose up -d chat-service ai-gateway mcp-public-gateway \
  glossary-service composition-service knowledge-service lore-enrichment-service
```

All 7 images built clean; all 7 containers came up `healthy` on the new images:

```
infra-ai-gateway-1                  Up (healthy)
infra-mcp-public-gateway-1          Up (healthy)
infra-chat-service-1                Up (healthy)
infra-knowledge-service-1           Up (healthy)
infra-lore-enrichment-service-1     Up (healthy)
infra-composition-service-1         Up (healthy)
infra-glossary-service-1            Up (healthy)
```

(`provider-registry-service` and `sdks/python`/`ai-gateway` Go/TS-only diffs outside
this set were confirmed to not require a service rebuild for this pass — provider-registry
only gained a new live-smoke Go test file, run separately, not a runtime code change.)

---

## Task 2 — 4-session Vietnamese web-search repro (live)

Original bug: 4 real sessions in `loreweave_chat` (`019f3d43-ea03-...`,
`019f3d43-308d-...`, `019f3d42-533f-...`, `019f3d3f-9738-...`) all failed on
*"tìm kiếm thông tin về chiến tranh Mỹ và Iran hôm nay trên internet"* — universal/chat
surface, no book, model `gemma-4-26b-a4b-qat`. Confirmed via
`SELECT session_id, model_ref, enabled_tools, enabled_skills FROM chat_sessions ...`
that 3 of 4 originals had `enabled_tools={glossary_web_search[,glossary_deep_research]}`,
`enabled_skills={universal}` — i.e. the tool was **pinned**, not discovered.

The original sessions' `model_ref` (`019f33f5-fa03-7acd-887d-8da1bf8a1b26`) no longer
exists in `user_models` (rotated out since). Used the current active replacement with
the same underlying model name: **`Gemma-4 26B-A4B QAT (200K)`**
(`019ebb72-27a2-72f3-a42d-d2d0e0ded179`), plus a differential control on
**`Qwen2.5 7B Instruct`** (`019eb620-bfb1-78ce-ad72-a360c604cfc1`, the model the prior
loop-flake investigation used to isolate gemma-specific defects from platform bugs).
Ran 4 fresh sessions against the **rebuilt** stack: {gemma, Qwen} × {pinned like the
original bug, unpinned — the realistic no-setup path a normal user hits, testing F0's
`universal_skill` fix}.

### gemma-4-26b-a4b-qat, pinned (`019f3dfa-4e68-72a7-89f4-6ceb1a3f6c00`)

`tool_calls` JSONB: 3× `find_tools` with `args:{}` (empty), each returning the **new**
directive note —
`"intent is required and was missing or empty on this call — describe in your own
words what you want to do ... and call find_tools again with a non-empty intent"`
(this is Fix 1 from the loop-flake investigation, confirmed live) — followed by 12×
`glossary_web_search` with `args:{}`, each failing normal Pydantic validation
(`"missing properties: [\"query\"]"`). **15 tool-call iterations total, 22.3s** — bounded,
not the original 40 iterations / 53.8s. Final answer (Vietnamese): opens with *"gặp lỗi
kỹ thuật khi cố gắng thực hiện lệnh tìm kiếm trực tiếp"* (encountered a technical error
trying to run the direct search), then gives background content framed as *"dựa trên
các thông tin cập nhật gần đây nhất"* (based on the most recently updated info), and
closes by pointing the user at real news sources (VnExpress, Tuổi Trẻ, Reuters, AP,
BBC, CNN) to check "right now."

**Assessment: partial improvement, not fully clean.** The loop is bounded and the
technical failure is disclosed up front (unlike the original bug, which silently
hallucinated). The "recently updated" framing is still a mild overreach for
training-data content — not the full "here is today's news" fabrication of the
original bug, but not the cleanest possible honesty either. Root cause: **gemma's own
tool-calling defect persists** — it sends empty `args` to both `find_tools` and
`glossary_web_search` regardless of the directive message's content (matches this
repo's memory `context-budget-test-model-gemma26b` and the loop-flake investigation's
finding that gemma "kept sending empty args regardless of the new message"). This is a
model-specific defect, not something this fan-out set out to fix — the platform-side
retry-cap correctly *bounds the damage* rather than curing the model.

### gemma-4-26b-a4b-qat, unpinned (`019f3dfa-a583-70aa-86f9-783e250e0f63`)

`tool_calls`: 11× `find_tools`, all `args:{}`, all hitting the same directive note —
model never attempted `glossary_web_search` at all. **7.5s, clean stop.** Final answer
explicitly discloses: *"tôi không có quyền truy cập trực tiếp vào các công cụ tìm kiếm
web tự do trong phiên làm việc này"* (I don't have direct access to free web-search
tools in this session) — an honest "can't do it here," then hedged historical
background pointing to real news sources. **No hallucination dressed as live data.**

### Qwen2.5 7B Instruct, pinned (`019f3dfc-6a58-7e4a-b0c9-13ceebd83790`)

`tool_calls`: **ONE** clean call —
`glossary_web_search({"query": "chiến tranh Mỹ và Iran hôm nay"})` — real provider
response:
```json
{"sources": [
  {"url": "https://vietnamnet.vn/su-kien/tinh-hinh-my-iran-moi-nhat-606483.html", "title": "Tình hình Mỹ - Iran mới nhất - Cập nhật liên tục 24h", "snippet": "..."},
  {"url": "https://znews.vn/tieu-diem/my_tan_cong_iran.html", ...},
  {"url": "https://znews.vn/tieu-diem/trung-dong.html", ...},
  {"url": "https://vnexpress.net/topic/cang-thang-my-iran-23938", ...},
  {"url": "https://baomoi.com/tag/Chi%E1%BA%BFn-tranh-M%E1%BB%B9.epi", ...}
]}
```
**7.9s total.** Final answer cites all 4 distinct URLs with real snippet content
(ceasefire/Hormuz-strait negotiation details, sanctions, a named US official). **Real,
non-hallucinated, single-call, no loop.** This is the clean positive control proving
the platform-side fix (retry-cap, dedup, no duplicate-empty-validation-spam) works
end-to-end for a model that behaves — the original bug's platform-layer causes are
fixed; what's left (gemma's empty-args defect) is model-specific.

### Qwen2.5 7B Instruct, unpinned (`019f3dfc-8945-75c1-8c47-2377b1dc74aa`)

`tool_calls`: **ONE** `find_tools({"group": "glossary", "intent": "search the web for
today's news about US and Iran war"})` → correctly surfaced `glossary_web_search` (and
`glossary_deep_research`) among 9 tools **with no pin at all** — direct proof of F0's
`universal_skill.py` fix (general web research is now reachable from the bookless
chat surface). Model then asked the user for confirmation before spending
(*"Bạn có muốn tôi tiếp tục thực hiện công việc này không?"*) rather than
auto-calling — a reasonable, non-buggy choice given the skill prompt frames the tool
as a paid outward call. **6.0s, no loop, no hallucination.**

### Task 2 verdict

Platform-side bugs from the original repro — unbounded `find_tools` retry loop (was
40 iterations/53.8s), unbounded duplicate-empty-arg validation spam, and hallucinated
"live news" dressed as fact — are **fixed**, proven by: (a) the Qwen positive control's
single clean real call with cited real sources, (b) both gemma variants now
terminating in 11-16 iterations (not 40) with an honest disclosure of the failure
rather than a confident fabrication, and (c) F0's fix confirmed live — the tool is now
reachable via `find_tools` on the bookless chat surface without any manual pin.
**Not fixed** (out of this fan-out's scope): gemma's own tool-calling defect of
sending empty `args` to any tool regardless of feedback — a known, separate,
model-specific issue this plan never claimed to cure.

---

## Task 4 — External audit issues #2/#3 live-verify (closes `D-INVOKE-TOOL-LIVE-SMOKE`)

Minted a real `mcp_api_keys` credential via `auth-service`
(`POST /v1/account/mcp-keys`, scopes `["read","paid_read","domain:knowledge",
"domain:book","domain:glossary"]`, key_id `019f3e00-60c7-764b-b5a1-0a6a68193d3f`) and
drove `mcp-public-gateway`'s live MCP endpoint (`http://mcp-public-gateway:8211/mcp`)
as a real streamable-HTTP MCP client (the `mcp` Python client library, the same one an
external agent would use) — not just the existing unit tests.

**#1/#2 — `find_tools(group="knowledge")` no longer empty:**

Targeted intent (`"knowledge graph and memory tools"`) →
```json
{"tools":[
  {"name":"kg_graph_query", "description":"Read the current project's knowledge graph..."},
  {"name":"memory_search", "description":"Search the project's stored knowledge..."},
  {"name":"kg_entity_edge_timeline", "description":"Retrieve the ordered temporal chain..."}
]}
```
3 real tools, not `{"tools":[]}` as the original audit found.

**Enumeration mode** (`find_tools({"group":"knowledge"})`, no `intent` at all) →
returned **all 11** real `kg_*`/`memory_*` tools unranked, with `"enumerated":true` —
directly closes audit issue #1 ("no list-everything-in-a-domain affordance") for this
domain too:
`kg_entity_edge_timeline, kg_graph_query, kg_list_templates, kg_project_list,
kg_schema_read, kg_sync_available, kg_triage_list, kg_view_read, memory_recall_entity,
memory_search, memory_timeline`.

**#2/#4 — `invoke_tool` dispatch + wording:**

`invoke_tool({"name":"memory_search","arguments":{"query":"test"}})` — `memory_search`
had already been surfaced by the earlier `find_tools` call, so this **succeeded**
(`isError:false`) with a real functional response:
```json
{"hits": [], "count": 0, "note": "no knowledge project is linked to this chat — pass the optional `project_id` argument (list your projects with kg_project_list), or link one in session settings to enable memory search"}
```
This is a real business response, not the old blanket "`'memory_recall_entity' is not
available yet`" refusal the audit hit for every `kg_*`/`memory_*` name regardless of
discovery state.

`invoke_tool({"name":"kg_project_list","arguments":{}})` **before** discovering it —
correctly refused, but with new wording:
```json
{"error":"'kg_project_list' hasn't been discovered yet this session — call find_tools with what you want to do first; it will be immediately callable once find_tools returns it."}
```
This reads as session-scoped lazy-activation guidance, not "this tool doesn't exist"
(the audit's #4 complaint about the old "is not available yet" phrasing).

**Full discover-then-invoke cycle**: `find_tools({"group":"knowledge","intent":"list
my knowledge graph projects"})` surfaced `kg_project_list` →
`invoke_tool({"name":"kg_project_list","arguments":{}})` then returned **real project
data**:
```json
{"projects":[{"project_id":"019f2be0-d145-7691-8182-5e17cf87e2c0","name":"Dracula (T5 audit)","project_type":"book","book_id":"019eeb09-a4aa-7acf-9281-e812d7975a6c","is_archived":false}],"more":false,"note":"pass a project_id to a project-scoped kg_* tool to act on that project"}
```

### Task 4 verdict

Audit #2 (knowledge domain unreachable via the documented `find_tools`→`invoke_tool`
path) and #3 (server prompts referencing unreachable tools) are **fixed and
live-verified** — not just unit-tested. `D-INVOKE-TOOL-LIVE-SMOKE` is closed: a real
external-shaped MCP client, using a freshly minted key, can now discover and invoke
the `knowledge` domain end-to-end and get real functional data back.

---

## Task 3 (F3) — Part E eval harness re-run

Reused `scripts/eval/run_skill_gate.py` + the existing 37-scenario / 5-file scenario
set (`scripts/eval/skill_scenarios/*.json`), same methodology as the two prior passes:
5 independent judges (one per skill file), each scoring blind, absolute (not A/B)
against each scenario's own self-contained `ground_truth`. Model:
**Qwen2.5 7B Instruct** (`019eb620-bfb1-78ce-ad72-a360c604cfc1`) — same model as the
round-3 (loop-flake) re-run, for a clean apples-to-apples comparison against both
prior baselines. Context: book `019ef35c-36c3-7379-aa0a-e8cab5202f5c` ("Dracula
(fresh agent journey)", 2 chapters) + a newly created knowledge project
`019f3e04-b08b-7e8e-a7ae-174e10134ab7` bound to it (both owned by the test account).

Raw transcripts: `docs/eval/skill-authoring/runs/sg-out-qwen-postfanout/<skill>/transcript.jsonl`.

### Scores — this pass (round 4, Qwen2.5 7B Instruct, full fan-out live)

Judged by 5 independent cold-start agents (one per skill file), blind, absolute-scoring
against each scenario's own `ground_truth`, same rubric as the prior 2 passes.

| Skill | Scenarios | PASS | WEAK | FAIL |
|---|---|---|---|---|
| composition | 6 | 1 | 1 | 4 |
| translation | 7 | 2 | 1 | 4 |
| book | 10 (11 records) | 1 | 4 | 5 |
| settings | 8 | 2 | 2 | 4 |
| jobs | 6 | 1 | 3 | 2 |
| **Total** | **37** | **7** | **11** | **19** |

### Comparison across all 3 rounds

| Round | Model | PASS | WEAK | FAIL | Fixes live at the time |
|---|---|---|---|---|---|
| 1 (first pass, 2026-07-07) | gemma-4-26b-a4b-qat | 13 | 14 | 7 (+4 NEEDS-RERUN) | none |
| 3 (loop-flake re-run, 2026-07-08) | Qwen2.5 7B Instruct | 9 | 15 | 14 | 2 targeted fixes only (`find_tools` empty-intent directive, `is_curated` skill-only-pin) |
| 4 (this pass) | Qwen2.5 7B Instruct | 7 | 11 | 19 | full fan-out (enumeration mode, retry-cap, embeddings, tool-call dedup, F0 universal web-research, knowledge-domain reachability, audit #2-#8 fixes) |

**Read plainly: the PASS count went down and the FAIL count went up across rounds 3→4,
on the raw table.** Per this repo's standard (report findings plainly, don't paper over
a regression), that is stated here without spin. Two things need saying alongside it,
both evidenced below: (a) a real methodological confound in this pass's own test
fixture likely explains a meaningful share of the FAIL increase, and (b) the specific
bugs this fan-out targeted are independently confirmed fixed by Tasks 2 and 4 above
(controlled, unconfounded reproductions) — this aggregate table is the noisiest of the
four verifications in this report, not the most trustworthy one.

### Confound: this pass's test fixture is sparser than what the ground_truth scenarios assume

This pass created a fresh book (`019ef35c-...`, 2 chapters, no outline, no motifs, no
canon rules, no cover, no prior trash activity) and a fresh knowledge project, since the
prior passes' exact book/project ids were never recorded (`meta.json` only stores
`model_ref`) and their sessions were not kept (`QG_KEEP_SESSIONS` unset). Checked the
scenario text directly — several turns hardcode assumptions this fixture doesn't meet:

- `book.json`'s `purge_requires_already_trashed_and_explicit_irreversible_confirm`:
  *"I want **chapter 3** completely and permanently gone"* — this test book has only
  2 chapters (`Chapter I`, `Chapter II`); chapter 3 does not exist.
- `book.json`'s `trashed_chapter_restore_is_studio_ui_only_not_revision_restore`:
  *"I trashed **chapter 4** by mistake yesterday"* — same gap, plus no chapter was ever
  trashed in this fixture.
- `composition.json`'s `outline_node_update_expected_version`: *"Update the synopsis of
  the **chapter 3 outline node**"* — this project has no outline at all yet.
- `composition.json`'s `project_id_resolution_from_book_id`/`prose_write_vs_generate_conflation`
  presuppose an existing outline tree to read/generate against.

Judges independently flagged the resulting behavior: book's `trash_delete_not_permanent...`
and `save_draft_cannot_guess_base_version...` scenarios "stalled on an ID-lookup error and
asked the user for a UUID"; composition's `project_id_resolution_from_book_id` "just
reports no outline structure available and asks whether to create one." In several of
these cases the model's tool-use was arguably *correct given the real (empty) state* —
it called a real tool, got a real "not found"/"no outline yet" response, and asked a
clarifying question — but the ground_truth (written against a presumed richer, populated
book) scores that as incomplete/FAIL. **This is a genuine limitation of this specific
re-run's setup, not confirmed to be the sole cause of the score decline** — there was
not time in this pass to reconstruct the original richer fixture and re-run a fully
controlled comparison; flagged here as an open question rather than swept under the rug.

### What IS confirmed, unconfounded, within this pass's own data

Comparing round 4 against round 3 on *mechanics* (not content-correctness, which the
fixture confound taints) — these are the same sparse-vs-rich-fixture conditions don't
apply to, since they're about tool-call behavior, not business-logic outcomes:

- **Long non-convergent retry loops (>200s) — gone in `book`.** Round 3 had 2 scenarios
  at 250-320s; round 4's max latency is 143.9s, and every scenario terminates (asks a
  clarifying question) rather than looping indefinitely.
- **`jobs` FAIL count improved:** 3→2 (round 3→4), PASS 0→1 — both round-3 FAILs were
  "real tool call, 0 chars to user"; round 4 still has 2 of that same pattern, but one
  scenario that failed cleanly before now passes.
- **Retry counts are capped, not unbounded, everywhere checked** — `translation`'s worst
  scenario now hits 7-8 repeated calls (still bad, but bounded) vs. the original bug's 40
  iterations; `composition`'s worst scenario hits a literal 9x identical
  `composition_motif_search` repeat, again bounded, not runaway.
- **Zero hallucinated tool names across all 37 scenarios, again** — consistent with both
  prior rounds; every judge explicitly checked bait scenarios designed to trip this
  (`settings_add_provider_key_no_invented_tool`, `jobs_no_generic_resume_tool`,
  `sharing_collaborator_access_is_studio_ui_only`) and none were tripped.
- **`composition` is "essentially unchanged" (1P/1W/4F, byte-identical tally to round 3)
  — and the composition judge diagnosed exactly why**: `find_tools` was never called
  even once across all 6 composition scenarios in this transcript. The enumeration-mode
  and embeddings-ranking fixes (this fan-out's Group B work) only help a turn that
  actually calls `find_tools` — here Qwen, when a budget-trimmed tool (`composition_generate`,
  `composition_outline_node_create`, `composition_outline_node_update`) isn't in its hot
  seed, just re-narrates the same failed plan in prose (~80K chars of repeated text
  across 3 scenarios) instead of querying for it. This is a **model-behavior gap**, not
  evidence the fix doesn't work — Task 4 above independently proves the enumeration
  fix works correctly when `find_tools` is actually invoked.
- **`settings` nominally regressed (4P/2F round 3 → 2P/4F round 4)** — the settings judge
  flagged a plausible but unconfirmed lead: 3 of the 4 new FAILs are "real tool call, 0
  chars to user," concentrated in the *last 3 of 9* turn-records, and those same later
  records are missing `budget_total` telemetry (`null`) unlike the first 4 — suggestive
  of session-level degradation (context/budget pressure) rather than a targeted-fix
  regression, but not independently confirmed this pass.
- **`translation`'s cancel-irreversibility warning is still missing** in round 4, exactly
  as in round 3 (`cancel_job_irreversibility_warning` FAILs both rounds) — this was
  never one of this fan-out's targeted bugs, so its persistence is expected, not a new
  regression.

### Supplementary (not independently judged): gemma-4-26b-a4b-qat, composition only

Time did not allow a full second 5-file run on gemma (the task's stretch goal); ran
composition only (6 scenarios) as a spot-check, self-reviewed rather than judge-scored.
Retry counts are bounded (max 23-25 repeated identical-tool calls, e.g.
`composition_get_work` ×23, `composition_list_outline` ×17) — not unbounded — but this
is a *different* pattern from the "duplicate empty-arg tool call" bug this fan-out
targeted: gemma here repeats the **same well-formed read call** many times rather than
sending empty args. Worth a dedicated look in a future pass, not conflated with the
already-fixed empty-args bug. Raw transcript:
`docs/eval/skill-authoring/runs/sg-out-qwen-postfanout/gemma_composition_transcript.jsonl`.

---

## Summary

| Task | Result |
|---|---|
| 1. Stack rebuild | Done — 7 images rebuilt from uncommitted working tree, all healthy |
| 2. 4-session repro | Platform bugs fixed (bounded loop — 11-16 iterations not 40, real cited answer for a well-behaved model, honest disclosure for gemma instead of hallucination); gemma's own tool-calling defect (empty args to any tool) persists — out of scope for this fan-out |
| 3. Part E re-run (F3) | Raw table declined (7P/11W/19F vs round 3's 9P/15W/14F) — read plainly, not spun. Real, unconfounded wins found within this pass's own mechanics: no more >200s non-convergent loops in `book`, `jobs` FAIL count down, all retry counts bounded not runaway, zero hallucinated tools (3rd round running). A genuine, evidenced confound (this pass's fresh/sparse test book+project vs. scenarios written assuming chapter-3/4 and pre-existing outline/cover/trash state) likely explains a meaningful share of the FAIL increase but was not independently isolated this pass — flagged as an open question, not resolved. `composition`'s tally is byte-identical to round 3 because the model never called `find_tools` even once in that skill's transcript — the enumeration fix is proven live in Task 4, but this model didn't exercise the code path that benefits from it here. |
| 4. Audit #2/#3 | Fixed and live-verified; `D-INVOKE-TOOL-LIVE-SMOKE` closed |

## Recommendation for a future pass

Re-run Part E's harness against a fixture that mirrors what the scenario authors
assumed (a book with ≥4 chapters, an existing composition outline/canon rules/motifs,
an existing cover, at least one already-trashed chapter) to get a genuinely clean
round-3-vs-round-4 comparison uncontaminated by the fixture gap documented above. Also
worth a dedicated look: gemma's "repeat the same well-formed read call ~20-25 times"
pattern (composition spot-check above) — bounded, but a different failure shape from
the already-fixed empty-args bug, not yet root-caused.
