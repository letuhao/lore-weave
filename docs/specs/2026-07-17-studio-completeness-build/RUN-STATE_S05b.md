# RUN-STATE — S-05b UX hardening build

> Re-read after compaction, then `git log`, then continue. Parallel sessions: stage ONLY my files (use
> `git commit -m … -- <paths>` from REPO ROOT to dodge the shared-index race + cwd traps). i18n new keys →
> `python scripts/i18n_translate.py --ns knowledge` before commit (ML-7 gate).

## COMMITMENT
Build S-05b (spec: S-05b_ux-hardening.md) — clear the S-05 dead-ends + raise the GUI score. 6 slices,
QC (tests) each. DONE = every slice built, tests green with pasted output.

## CLARIFY seals (verified vs code 2026-07-18)
- Entity typeahead: REUSE hooks `useEntities({project_id,search})` + `useDebouncedValue` + `FormDialog`
  (@/components/shared) — the exact pattern in CreateRelationDialog. Build a SELF-CONTAINED
  `TriageRetargetDialog` (my file), don't edit CreateRelationDialog.
- map codes: `useResolvedSchema(projectId)` → `edge_types[].code` (unknown_edge_type) / `node_kinds[].code`
  (unknown_node_kind) / `vocab_values[set_code][].code` (unknown_vocab_value). Select per item_type.
- Evidence payloads (pure formatter, per item_type): unknown_edge_type `{predicate}`; unknown_vocab_value
  `{set_code,value}`; edge_kind_mismatch `{predicate,source_kind,target_kind}`; unknown_node_kind
  `{kind_code}`; edge_cardinality_conflict = NOT parked in current code → safe generic fallback sentence.
- revalidate: `POST /facts/{id}/revalidate` clears `valid_until` (mirror invalidate_fact; owner-scoped;
  no event). Small.
- F2 window.confirm KEPT (app already uses it in archive/unlock — consistent). Only window.prompt is fixed.
- F10 create-entity already exists (CreateEntityDialog in EntitiesTab) — no build, just verify.

## SLICE BOARD (done = evidence)
- [x] S5b-3 triageEvidence sentence formatter + wire — EVID: 6 formatter + 11 queue; commit 67f43fc49
- [x] S5b-4 de-jargon (plain fact-type labels + helper) + Advanced <details> for s/p/o — EVID: 14 EDP; 4f7eed31d
- [x] S5b-1 TriageRetargetDialog entity-picker → re_target (UUID prompt GONE) — EVID: 2 dialog + 9 queue; eb1f672d7
- [x] S5b-2 TriageMapDialog code-select over useResolvedSchema — EVID: 4 map + 11 queue; 3c99cac35 + fix f3ad65b8b
- [x] S5b-5 BE revalidate route + FE mark-wrong Undo + fact Replace — EVID: BE 12 + FE 23; ddcecacaf
- [x] S5b-6 triage empty-state orientation hint — EVID: 11 queue; (this commit)
- [ ] VERIFY broad + commit — EVID:

## DECISIONS (mine)
- S5b-2 fix: SchemaNodeKind uses `kind_code` not `code` — a mock with `{code}` was green over a wrong type
  (mock-hides-type). Added a node_kind test exercising the real field.
## DRIFT LOG
- S5b-2: caught the kind_code type mismatch only at tsc (test mock hid it) — fixed + added a real-field test.
