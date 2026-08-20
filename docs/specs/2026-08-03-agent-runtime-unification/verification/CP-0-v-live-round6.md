# CP-0 · V-LIVE — round 6 verdict

**Artifact under test:** `db4245eb5` (frozen)
**Driven:** the real UI (Playwright-driven Chrome against `http://localhost:5174`) — both the embedded
book-assistant panel and the full `/chat` page. Not the API.
**Throwaway book:** `VLIVE-R6 Throwaway (CP-0 verification)` — `019fcbd3-20f7-7b29-b7ff-2ab2f551f55b`
**Sessions used:** `019fcbd5-4f14-7eb7-aa30-125ca02bb4db` (run A, run D, late-cancel control),
`019fcbd9-561e-7c89-8623-f31e3bff5895` (run B, run C ×2)
**Account:** `claude-test@loreweave.dev` (`019d5e3c-7cc5-7e6a-8b27-1344e148bf7c`)
**Model:** Gemma-4 26B-A4B QAT (lm_studio, local)
**No dogfood data touched.** Every row below is in the throwaway book's sessions.

## Overall verdict: **FAIL**

| | verdict |
|---|---|
| **P1** — every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}` | **FALSIFIED** |
| **P3** — every terminal path writes an outcome | **FALSIFIED** |
| **Run A · clean** | **PASS** |
| **Run B · withheld** | **PASS** |
| **Run C · cancelled** | **FAIL** (pre-first-token window). Passes once tokens have streamed |
| **Run D · killed** | **FAIL** |
| The defect CP-0 was built for (offered set changes between passes) | **PASS** — both states recorded |

---

## 0. PRECONDITION — the container was stale for the **SIXTH** round running

I hashed the repo tree against the container **before driving anything**. It did not match.

```
$ docker exec infra-chat-service-1 sh -c 'cd /app && find app -name "*.py" | sort | xargs sha256sum'
$ diff <repo per-file hashes> <container per-file hashes>
71c71  < instrument.py            d39922e9…  |  > 6e0c53eb…
89c89  < stream_service.py        af802cf2…  |  > 2d8077f3…
102c102 < voice_stream_service.py 7eece13e…  |  > 7aed2753…
```

Exactly the three CP-0 files; the other 104 matched. Normalising line endings (the Windows worktree is
CRLF, git blobs are LF) identifies the running commit:

| file | container (LF-normalised) | worktree = HEAD `db4245eb5` |
|---|---|---|
| `instrument.py` | `fc74d8bc240df111` | `0647c38d7b0302cf` |
| `stream_service.py` | `470575d00d6c455c` | `ac87086d239bc4b8` |
| `voice_stream_service.py` | `4c3f42a96a4da920` | `85c435548f674654` |

`fc74d8bc240df111` is the `instrument.py` blob at **`711f94c61`** (2026-08-04 10:54) — i.e. exactly the
artifact I was handed in **round 5**, which round 5 rebuilt. **Nine commits and four hours behind the
frozen artifact `db4245eb5` (14:59).** The container reported `Up 3 hours (healthy)`; the image was
built at 10:59:28. Every CP-0 change committed after round 5 — including the P3 "recording hole
closed" commit I was asked to verify — was **not running**.

Remediation, then re-verification:

```
$ docker compose -f infra/docker-compose.yml build chat-service
$ docker compose -f infra/docker-compose.yml up -d --force-recreate chat-service
$ <per-file LF-normalised comparison, all 107 files>
total files: 107; drift: 0
```

I re-checked at the **end** of the run (the container was killed and restarted three times for run D):

```
files checked: 107; drift: 0
$ docker exec infra-chat-service-1 sh -c "tr -d '\r' < /app/app/services/instrument.py | sha256sum"
0647c38d7b0302cf…   == worktree == HEAD db4245eb5
```

Everything below was produced against the frozen artifact.

---

## 1. P1 — **FALSIFIED**, by one tool in one turn

### The correct accounting

Catalogue derived from the frozen snapshot `contracts/agent-runtime-baseline/tools-list.snapshot.json`:
**315 tools** (75 deprecated, 240 live), `frozen_at 2026-08-03T23:01:35Z`. Round 5's "307" came from the
turn's own `tool_list` result, and its "0 unaccounted" counted rows rather than tools. Redone properly:

**Run A** — session `019fcbd5…`, `sequence_num=2`:

```
pass objects: [(1, 58), (2, 58)]   withheld records: 29   distinct withheld tools: 29
adv union: 58   wh union: 29   adv|wh: 87
  pass 1: adv=58 wh=29 SAME-PASS-OVERLAP=0 NEITHER=237 (deprecated=73, live=164)
  pass 2: adv=58 wh=0  SAME-PASS-OVERLAP=0 NEITHER=266 (deprecated=73, live=193)
TURN-LEVEL NEITHER: 237  (live 164)
```

**Run B** — session `019fcbd9…`, `sequence_num=2`:

```
pass objects: [(1, 49), (2, 49), (3, 61)]   withheld records: 57
  pass 1: adv=49 wh=52 same-pass-overlap=0 NEITHER=223 (live=150)
  pass 2: adv=49 wh=0  same-pass-overlap=0 NEITHER=275 (live=201)
  pass 3: adv=61 wh=5  same-pass-overlap=0 NEITHER=258 (live=184)
TURN-LEVEL NEITHER = 206  (live=133, deprecated=73)
```

**The number: 237 (run A) and 206 (run B) catalogue tools land in NEITHER bucket** — 164 and 133 of
them non-deprecated. Per pass it is worse: **266** at run A pass 2, **275** at run B pass 2, because
pass 2 carries **zero** withheld records in both turns.

Two round-5 claims *do* hold and I confirm them: **same-pass overlap is 0** at every pass of both turns
(the metric verifier's 28 same-pass triples do not recur on new rows), and the pass-1 withheld bucket is
non-empty.

### The decisive counter-example — `world_map_create`

Session `019fcbd9-561e-7c89-8623-f31e3bff5895`, `sequence_num=2`, one turn, one tool:

```
world_map_create:
   pass 1: advertised=NO   withheld_record=NONE
   pass 2: advertised=NO   withheld_record=NONE
   pass 3: advertised=NO   withheld_record={'pass': 3, 'tool': 'world_map_create',
                                            'stage': 'token_budget',
                                            'reason': 'did not fit the activation token budget'}
```

The system's **own pass-3 record** proves `world_map_create` was a genuine candidate in this turn. At
passes 1 and 2 it was absent from the advertised set and registered nothing. `world_map_add_marker`,
`world_map_add_region`, `world_map_update_marker` and `world_map_update_region` are four identical
counter-examples in the same row. `world_create` is a fifth in the other direction: unrecorded at passes
1–2, then *advertised* at pass 3.

**One counter-example falsifies a property claim. There are five in a single database row.**

### Why the gap is a real narrowing, not a catalogue that was simply smaller

An objection would be that the ~100-tool pool is the whole universe for the turn, so nothing was
"withheld". The rows refute that. The pass-1 candidate pool (advertised ∪ withheld) is **query-dependent
in membership**:

```
RUN A pass-1 candidate pool:  87  (adv 58, wh 29)
RUN B pass-1 candidate pool: 101  (adv 49, wh 52)
pool A == pool B ?  False
in A's pool, not in B's (3):  glossary_book_sync_apply, glossary_plan, glossary_propose_batch
in B's pool, not in A's (17): jobs_cancel, jobs_get, jobs_list, jobs_pause, jobs_summary,
                              translation_coverage, translation_job_control, translation_job_status,
                              translation_list_versions, translation_patch_block,
                              translation_retranslate_dirty, translation_save_edited_version,
                              translation_segment_status, translation_set_active_version,
                              translation_start_extraction, translation_start_job,
                              translation_update_settings
union of both pools: 104   frozen catalogue: 315
frozen tools never a candidate in either turn: 220
```

A step **upstream of `hot_seed`** selected ~100 tools out of 315 on the basis of the user's message —
`jobs_*` and `translation_*` appear only when the message mentions them — and registered
**nothing**: no `{tool, stage, reason, pass}` for the ~215 it dropped. The only recorded stages are
`hot_seed` and `token_budget`, and both operate *inside* the already-narrowed pool
("did not fit the hot_seed token budget (2000 tok)"). That is precisely the shape §0.3 forbids:
*a narrowing that does not register is a defect, not a policy.*

### The 164 live tools in NEITHER (run A, turn level)

`book_structure_part_archive`, `book_task_provide_input`, `catalog_get_book`, `catalog_list_public_books`,
`composition_arc_apply`, `composition_arc_edit`, `composition_arc_extract_template`, `composition_arc_get`,
`composition_arc_import_analyze`, `composition_arc_list`, `composition_arc_suggest`,
`composition_arc_template_drift`, `composition_arc_template_edit`, `composition_arc_template_get`,
`composition_arc_template_list`, `composition_authoring_run_get`, `composition_authoring_run_list`,
`composition_authoring_run_manage`, `composition_authoring_run_review`, `composition_canon_rule_edit`,
`composition_conformance_run`, `composition_conformance_status`, `composition_create_derivative`,
`composition_create_work`, `composition_decompile_arcs`, `composition_derivative_edit`,
`composition_entity_override_edit`, `composition_generate`, `composition_get_derivative_context`,
`composition_get_generation_job`, `composition_get_mine_job`, `composition_get_outline_node`,
`composition_get_work`, `composition_glossary_build`, `composition_library_translate`,
`composition_list_canon_rules`, `composition_list_derivatives`, `composition_list_outline`,
`composition_motif_adopt`, `composition_motif_bind_edit`, `composition_motif_book_list`,
`composition_motif_edit`, `composition_motif_get`, `composition_motif_link_edit`,
`composition_motif_link_list`, `composition_motif_mine`, `composition_motif_search`,
`composition_motif_suggest_for_chapter`, `composition_outline_node_edit`, `composition_reference_update`,
`composition_scene_link_edit`, `composition_structure_template_edit`, `composition_switch_active_work`,
`composition_task_provide_input`, `glossary_book_create`, `glossary_book_delete`, `glossary_book_patch`,
`glossary_book_revert`, `glossary_book_set_active_genres`, `glossary_book_set_kind_genres`,
`glossary_entity_get_genres`, `glossary_entity_set_genres`, `glossary_get_entity_evidence`,
`glossary_list_ai_suggestions`, `glossary_list_chapter_links`, `glossary_list_entity_revisions`,
`glossary_list_merge_candidates`, `glossary_list_unknown_entities`, `glossary_propose_kinds`,
`glossary_propose_merge`, `glossary_propose_new_attribute`, `glossary_propose_new_entity`,
`glossary_propose_new_kind`, `glossary_propose_reassign_kind`, `glossary_propose_restore_revision`,
`glossary_propose_status_change`, `glossary_task_provide_input`, `glossary_user_create`,
`glossary_user_delete`, `glossary_user_patch`, `glossary_user_restore`, `glossary_user_standards_read`,
`jobs_cancel`, `jobs_get`, `jobs_list`, `jobs_pause`, `jobs_summary`, `kg_adopt_template`,
`kg_build_graph`, `kg_build_wiki`, `kg_create_node`, `kg_multi_query`, `kg_project_entities_to_nodes`,
`kg_view_delete`, `kg_view_upsert`, `kg_world_query`, `lore_ask`, `lore_browse_entities`, `lore_entity`,
`lore_timeline`, `plan_apply_revision`, `plan_bootstrap_apply`, `plan_bootstrap_propose`,
`plan_find_missing_material`, `plan_get_missing_material`, `plan_handoff_autofix`,
`plan_interpret_feedback`, `plan_keep_material`, `plan_link`, `plan_pass_status`,
`plan_review_checkpoint`, `plan_run_pass`, `plan_self_check`, `plan_validate`, `registry_get_skill`,
`registry_get_workflow`, `registry_list_skills`, `registry_list_workflows`, `registry_propose_skill`,
`registry_propose_workflow`, `registry_set_skill_enabled`, `registry_update_skill`,
`registry_update_workflow`, `settings_get_defaults`, `settings_get_profile`, `settings_list_models`,
`settings_list_providers`, `settings_model_delete`, `settings_model_register`,
`settings_model_set_active`, `settings_model_set_default`, `settings_model_set_favorite`,
`settings_model_update`, `settings_provider_inventory`, `settings_update_profile`,
`translation_coverage`, `translation_job_control`, `translation_job_status`,
`translation_list_versions`, `translation_patch_block`, `translation_retranslate_dirty`,
`translation_save_edited_version`, `translation_segment_status`, `translation_set_active_version`,
`translation_start_extraction`, `translation_start_job`, `translation_update_settings`, `world_create`,
`world_delete`, `world_get`, `world_list`, `world_map_add_marker`, `world_map_add_region`,
`world_map_create`, `world_map_delete`, `world_map_get`, `world_map_list`, `world_map_remove_marker`,
`world_map_remove_region`, `world_map_update`, `world_map_update_marker`, `world_map_update_region`,
`world_move_book`, `world_update`

Of these, run B independently demonstrates that at least **34** (`jobs_*`, `translation_*`, `world_*`)
were genuine candidates the very same day, on the same account, in the same book.

### Nine names appear in `advertised`/`withheld` but not in the frozen catalogue

`chat_search_sessions`, `confirm_action`, `conversation_search`, `glossary_confirm_action`,
`glossary_propose_entity_edit`, `load_skill`, `run_subagent`, `workflow_list`, `workflow_load`.
These are kit/meta declarations; four of them (`glossary_confirm_action`, `glossary_propose_entity_edit`
and the `chat_*`/`conversation_*` pair) suggest the snapshot is 24 h stale relative to the live surface.
I record this as an **ambiguity, not a finding**: the brief pins the catalogue to the frozen snapshot, and
the P1 result is unaffected — the counter-example tool is *in* the frozen catalogue.

---

## 2. P3 — **FALSIFIED** on both paths. The claimed stamp does not exist on any row.

### (a) Cancel before the first streamed token — user row `outcome IS NULL`

Stop clicked **262 ms** after send (body text had grown by 114 chars = the echoed user bubble only; no
assistant token had arrived).

```sql
SELECT message_id, sequence_num, role, outcome, finish_reason, length(content), created_at
FROM chat_messages WHERE session_id='019fcbd9-561e-7c89-8623-f31e3bff5895' AND sequence_num>=13;
```
```
message_id        | 019fcbe5-5e39-74ac-9129-3f7fda42519d
sequence_num      | 13
role              | user
outcome           |                        <-- NULL
finish_reason     |
len               | 104
content           | Write a 4000-word annotated bibliography of Ashfen scholarship, twenty numbered…
parent_message_id |
created_at        | 2026-08-04 08:30:34.552702+00
```

No assistant row was created. Reproduced a second time (stop at **63 ms**), `sequence_num=14`, same
result. The service logged this itself:

```
INFO:app.services.stream_service: CP-0.4 silent-exit: empty terminal turn with NO parent to stamp
  (session 019fcbd9-561e-7c89-8623-f31e3bff5895, msg 2ad8ef57-eaa1-4b74-a77d-c2d0bf7dfc04,
   reason=interrupted) — the one remaining shape, and it is countable.
```

**The log's premise is false.** The parent *does* exist — row `019fcbe5-5e39-74ac-9129-3f7fda42519d`,
same session, holding the exact prompt text, written 0.3 s earlier. Separately:

```sql
SELECT count(*) FROM chat_messages WHERE message_id='2ad8ef57-eaa1-4b74-a77d-c2d0bf7dfc04';
-- 0
```

The id the runtime is looking up is a UUIDv4; every persisted `chat_messages.message_id` is a UUIDv7.
The lookup cannot succeed, so "no parent to stamp" is reached unconditionally and the case is filed as
"countable" rather than recorded. **I report this as the observation, not as a diagnosis** — V-CODE owns
the mechanism.

### (b) `docker kill` mid-turn, before any tool call — user row `outcome IS NULL`

Sent 08:37:00.041 (streaming confirmed active 300 ms later); `docker kill infra-chat-service-1` at
08:37:05.616 — **5.6 s into the turn**, no tool call had been made.

```
 sequence_num |   role    |  outcome  | finish_reason | len |            created_at
--------------+-----------+-----------+---------------+-----+-------------------------------
            1 | user      |           |               |  94 | 2026-08-04 08:13:29.384161+00
            2 | assistant | completed | stop          |  58 | 2026-08-04 08:13:55.760133+00
            3 | user      |           |               | 216 | 2026-08-04 08:36:59.92407+00   <-- NULL
```

After `docker compose up -d chat-service` and `health: healthy`, re-queried: **unchanged, still NULL.**
Nothing is written on recovery.

### The stamp is not merely wrong here — it is absent everywhere

```sql
SELECT role, outcome, count(*) FROM chat_messages GROUP BY 1,2 ORDER BY 1,2;
```
```
   role    |      outcome      | count
-----------+-------------------+-------
 assistant | abandoned_by_user |     8
 assistant | awaiting_input    |     5
 assistant | completed         |    60
 assistant | crashed           |     3
 assistant |                   |  2653
 user      |                   |  3154     <-- every user row in the database
```

**0 of 3154 user rows carry an outcome.** The builder's claim — "the outcome is stamped on the PARENT
USER MESSAGE for these turns" — has no instance anywhere in `loreweave_chat`.

### Does the stamp overwrite an outcome on turns that DID produce an assistant row? — **No**

Runs A and B both retained `outcome='completed'`, `finish_reason='stop'` throughout, and their parent
user rows stayed NULL. Nothing was clobbered. That half of the check passes — vacuously, because the
stamp never fires.

### Control: the cancel path works *once tokens have streamed*

Same session, stop clicked at 4.1 s after 850 chars had rendered:

```
 sequence_num | role      | outcome           | finish_reason | len
--------------+-----------+-------------------+---------------+-----
            4 | user      |                   |               |  95
            5 | assistant | abandoned_by_user | interrupted   | 756
```

`abandoned_by_user` + `interrupted` — a terminal outcome that *does* distinguish "the user abandoned
this" from "this broke". So P3's hole is exactly the pre-first-token window and the kill, as the run
brief predicted, and the closure claimed for it has not landed on live rows.

---

## 3. Run A — **PASS**

Session `019fcbd5-4f14-7eb7-aa30-125ca02bb4db`, `sequence_num=2`, message
`99bb76ed-2225-4340-952e-150d39ed9e57`.

```
 sequence_num |   role    |  outcome  | finish_reason | passes | withheld | calls | runtime_variant
--------------+-----------+-----------+---------------+--------+----------+-------+-----------------
            2 | assistant | completed | stop          |      2 |       29 |     2 | legacy
```

```
tool_calls:
{'id':'call_4274648666862596','tool':'book_list','ok':True,'source':'tool','latency_ms':68,
 'iteration':0,'declaration':'book_list','runtime_variant':'legacy','error':None}
{'id':'call_4274648666862597','tool':'glossary_search','ok':True,'source':'tool','latency_ms':69,
 'iteration':0,'declaration':'glossary_search','runtime_variant':'legacy','error':None}
```

`advertised_tools` present per pass; every `tool_calls` entry carries `source` and `latency_ms`; an
outcome is recorded. Requirements met.

### The four questions, answered from the record alone

| question | answerable? |
|---|---|
| Which tools was the model holding on its second pass? | **Yes** — `advertised_tools[pass=2].names`, 58 names, `tool_choice: auto` |
| Was anything hidden from it? | **The record answers "no, at pass 2" — and that answer is wrong.** 29 withheld records exist, all at pass 1; pass 2 carries none, while 266 catalogue tools were not offered. This is the P1 failure showing up as a *confidently wrong* answer rather than a missing one |
| Did the third result come from a tool or from our own breaker? | **Yes** — `source` is structural and discriminating: run B shows `meta` for `tool_list`/`tool_load` and `tool` for `jobs_list` |
| How did the turn end? | **Yes** — `outcome='completed'`, `finish_reason='stop'` |

Three of four from the record without inference. The second is answerable in form and false in fact.

---

## 4. Run B — **PASS**, and the defect CP-0 exists to catch is **caught**

Session `019fcbd9-561e-7c89-8623-f31e3bff5895`, `sequence_num=2`. The offered set **changes between
passes** and the record shows every state:

```
 pass | advertised_count | tool_choice
------+------------------+-------------
 1    | 49               | auto
 2    | 49               | auto
 3    | 61               | auto
```

pass 1 → pass 3 delta: **added** `world_create, world_delete, world_get, world_list, world_map_delete,
world_map_get, world_map_list, world_map_remove_marker, world_map_remove_region, world_map_update,
world_move_book, world_update` (12); **removed** none. The `tool_load('world')` that caused it is in
`tool_calls` with `source: meta`, and the five map-mutation tools that did *not* survive the widening
carry an explicit reason:

```
 pass |          tool           |    stage     |                 reason
------+-------------------------+--------------+-----------------------------------------
 3    | world_map_add_marker    | token_budget | did not fit the activation token budget
 3    | world_map_add_region    | token_budget | did not fit the activation token budget
 3    | world_map_create        | token_budget | did not fit the activation token budget
 3    | world_map_update_marker | token_budget | did not fit the activation token budget
 3    | world_map_update_region | token_budget | did not fit the activation token budget
```

`withheld_tools` names the tool, the stage and a reason — not an empty array. Two stages fire:

```
 pass |    stage     |                      reason                      | count
------+--------------+--------------------------------------------------+-------
 1    | hot_seed     | did not fit the hot_seed token budget (2000 tok) |    52
 3    | token_budget | did not fit the activation token budget          |     5
```

The record does **not** show only the final pass. On the narrow question the brief poses — *"construct a
turn where the offered set changes between passes and confirm the record shows both states"* — this is a
clean **PASS**, and it is the strongest result in this round.

`tool_calls` for the turn:

```
   tool    | source | latency_ms | iter |  ok  |   decl
-----------+--------+------------+------+------+-----------
 tool_list | meta   |            | 0    | true | tool_list
 tool_load | meta   |            | 1    | true | tool_load
 tool_load | meta   |            | 1    | true | tool_load
 jobs_list | tool   | 104        | 1    | true | jobs_list
```

**Minor finding, in scope:** `latency_ms` is NULL for every `source: meta` entry. The run-A requirement
reads "every `tool_calls` entry has `source` and `latency_ms`". Meta calls are in-process and arguably
have no meaningful latency, but the field is silently absent rather than `0` or annotated. I flag it and
do not rule on it.

---

## 5. Run C — **FAIL** · Run D — **FAIL**

Covered in §2. Summary:

- **C**: cancel at 262 ms and again at 63 ms → user row, `outcome NULL`, no assistant row, twice.
  Cancel at 4.1 s (after tokens) → `abandoned_by_user` / `interrupted`, correct.
- **D**: `docker kill` 5.6 s into a confirmed-streaming turn, before any tool call → user row,
  `outcome NULL`; still NULL after restart to healthy.

Both are the exact two paths the RUNSTATE lists as "recording hole CLOSED … awaits live verification".
They are not closed on live rows.

---

## 6. `awaiting_input` rows that can never receive input

**On live rows today: zero realised, one latent-by-expiry, and the voice hazard is real in source but
has produced no row yet.**

All five `awaiting_input` rows have a matching suspended run keyed by their own `message_id`:

```sql
SELECT m.message_id, m.session_id, m.sequence_num,
       (SELECT count(*) FROM chat_suspended_runs r WHERE r.message_id = m.message_id) AS run_by_message_id,
       (SELECT count(*) FROM chat_suspended_runs r WHERE r.session_id = m.session_id
                                                    AND r.expires_at > now())          AS live_runs
FROM chat_messages m WHERE m.outcome='awaiting_input' ORDER BY m.created_at;
```
```
              message_id              |              session_id              | seq | run_by_message_id | live_runs
--------------------------------------+--------------------------------------+-----+-------------------+-----------
 7a66b39d-a61e-496b-b80a-286243a339f2 | 019fca64-32ca-7f53-853a-085a24635c90 |  24 |                 1 |         0   <-- expired
 9aba6fe4-511d-49dc-b865-95408a3b0344 | 019fcaa6-10b2-76e4-84ae-842e4198b250 |  10 |                 1 |         2
 732760c4-d11f-4e84-bf7d-bd7cd1af394b | 019fcaa6-10b2-76e4-84ae-842e4198b250 |  12 |                 1 |         2
 bfdcc100-8ee3-4466-9d72-60acb7a5bced | 019fcac6-8c70-70f4-9593-2822dba0e97d |   6 |                 1 |         1
 bbae64a7-a33f-42fd-a99c-3e369b7246d5 | 019fcaf2-7716-7cf7-8a6a-424d2edf99d2 |   4 |                 1 |         1
```

```sql
SELECT (expires_at > now()) AS still_live, count(*) FROM chat_suspended_runs GROUP BY 1;
-- f | 166      t | 4
```

**One of the five (`7a66b39d…`) can never receive input** — its suspended run has passed the six-hour
`expires_at` TTL and the sweeper deletes on expiry, while the message keeps advertising
`awaiting_input` indefinitely. 166 of 170 suspended runs are already expired. That is a distinct,
realised "can never receive input" case, caused by TTL rather than by voice.

**The voice hazard is real but unrealised.** `save_suspended_run` has exactly one call site in the whole
service (`stream_service.py:6947`); `voice_stream_service.py` writes
`outcome = instrument.OUTCOME_AWAITING_INPUT` at line 615 when `_voice_suspended` and never saves a run.
A voice turn that suspends therefore produces an `awaiting_input` row the resume endpoint cannot find.
**I could not exercise the voice path live** — it needs microphone audio I cannot supply from a headless
browser — so I confirm the mechanism in source and confirm that **no such row exists in the database
today**. That is a limitation of this round, and I state it rather than assert the result.

---

## 7. My falsifier — stated before I ran

- **P1** would have been falsified by *any* catalogue tool, in a real turn, that appeared in neither the
  advertised set nor the withheld set of a pass **and** could be shown to be a genuine candidate by
  evidence internal to that same turn. I found five, and the strongest — `world_map_create` — is proven
  a candidate by the runtime's own pass-3 withheld record.
- **P3** would have been falsified by a `chat_messages` row of `role='user'` with `outcome IS NULL`
  after (a) a cancel with no streamed token, or (b) a `docker kill` before any tool call. Both were
  found, (a) twice; and the stronger form holds too — no user row in the entire database has ever been
  stamped.
- **P1 would have survived** if the neither-bucket were zero, or if every tool in it could be shown to
  have been outside the turn's candidate universe. It could not: the pool's membership moves with the
  user's message.
- **P3 would have survived** if either terminal path had written any of the six permitted outcome values
  to either the assistant or the user row. Neither did.

---

## 8. Out of scope — things I saw that CP-0 did not ask about

1. **The embedded book-assistant panel appears to have no reachable Stop control.** On
   `/books/{id}` → *Ask AI*, I polled the DOM every 1.5 s across three separate streaming turns
   (18 s, 15 s, 32 s windows) and `chat.isStreaming` never flipped: the composer kept rendering
   `data-testid="chat-send-button"` and no `bg-destructive` Stop button ever mounted. On the full
   `/chat` page the same button mounts **262 ms** after send, reliably. A user in the book panel
   appears unable to stop a running turn. I did not investigate further; it is a UI/state-wiring
   question, not an instrument one — but it is also what forced runs C and D onto `/chat`.
2. **An in-flight turn is transiently recorded as `outcome='crashed'`, `finish_reason='streaming'`.**
   Caught mid-run-B; it converges to `completed`/`stop` on clean finish. Pessimistic-then-corrected is
   defensible (it is presumably what makes a killed turn stay `crashed`), but any dashboard that
   samples live will over-report crashes. Noting, not ruling.
3. **After a `docker kill` + restart, the already-open browser tab's next send silently no-ops** — I
   sent a message that produced no row at all and no error; a page reload fixed it. Possibly an SSE
   reader that does not re-establish. Out of scope.
4. **The frozen snapshot may be stale relative to the live surface** — nine names appear in live
   `advertised`/`withheld` records that are not in the 315-tool snapshot (§1). Worth a re-freeze before
   the next round so the denominator is not itself a moving target.

---

## 9. How I drove the system, and what I could not do

- **UI, not API**, for every one of runs A–D and the late-cancel control. Login, book navigation, session
  creation and message sending all went through the rendered app. I used `page.evaluate` to press the
  Stop button and to time the sends, because the cancel windows I needed (63–262 ms) are shorter than a
  tool-call round trip; the clicks are real clicks on the real button, dispatched in-page.
- **Selectors are language-neutral** (`data-testid`, class) — this account's UI renders in Vietnamese
  and a text-matched selector would have coupled the result to a server-side preference.
- **Could not perform:** the voice-path `awaiting_input` test (§6), for want of microphone input. That is
  a gap in this round's coverage, and — since observability is this checkpoint's whole subject — I record
  it as a finding rather than a footnote.
