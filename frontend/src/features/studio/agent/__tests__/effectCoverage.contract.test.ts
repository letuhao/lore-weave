// W0-S4 / X-4c — THE LANE-B COVERAGE LEDGER (Q-30-X4-LANE-B-HANDLERS §4).
//
// X-4's bug class is: a wave ships a panel and FORGETS its effect handler, so an agent write lands in
// the DB and the panel shows stale state until the user manually refetches. A per-handler unit test
// cannot catch that — it only tests handlers that EXIST. This ledger inverts it: it enumerates every
// write TOOL NAME the platform exposes, maps it to its owning §8.0b handler file, and asserts every
// one of them is covered by >=1 registered handler unless it is in an explicit PENDING allowlist.
//
// Because it feeds REAL TOOL NAMES through the REAL registrations, it also catches:
//   · the string-vs-RegExp silent no-op (X-4.0) — a pattern that matches nothing reds HERE, nowhere else;
//   · the DOUBLE-FIRE (§8.0b) — matchEffectHandlers returns EVERY match and runEffectHandlers awaits
//     ALL of them, so two files claiming one domain do not shadow, they fire twice.
//
// 🔴 EVERY WAVE'S DoD: "delete this wave's rows from PENDING by creating/extending its §8.0b handler
//    file — THE TEST REDS UNTIL YOU DO." That is what makes X-4 a mechanical ledger, not a checklist.
import { describe, expect, it, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { clearEffectHandlers, matchEffectHandlers } from '../effectRegistry';
import { registerAllStudioEffectHandlers, _resetAllStudioEffectHandlers } from '../handlers';

// ── The ledger. Tool NAME → the §8.0b file that owns its effect handler. ──────────────────────────
// Seeded from the LIVE inventory (grep -ohE '"(composition|plan|world_map|registry|kg)_[a-z_0-9]+"'
// over services/), not from a doc — a ledger of fictional names is green over a broken reality.
const WRITE_TOOLS: Record<string, string> = {
  // ── authoringRunEffects — Wave 0 CLEARS this (the one genuinely-stale shipped domain). ──
  composition_authoring_run_list: 'authoringRunEffects',
  composition_authoring_run_get: 'authoringRunEffects',
  composition_authoring_run_create: 'authoringRunEffects',
  composition_authoring_run_gate: 'authoringRunEffects',
  composition_authoring_run_start: 'authoringRunEffects',
  composition_authoring_run_resume: 'authoringRunEffects',
  composition_authoring_run_pause: 'authoringRunEffects',
  composition_authoring_run_close: 'authoringRunEffects',
  composition_authoring_run_accept_unit: 'authoringRunEffects',
  composition_authoring_run_reject_unit: 'authoringRunEffects',
  composition_authoring_run_revert_all: 'authoringRunEffects',

  // ── knowledgeEffects — Wave 0 CLEARS this by VERIFYING it, not by adding a handler. ──
  // X-4 claimed kg_create_node had no handler. It already has one: KNOWLEDGE_WRITE_PATTERN is a
  // negative-lookahead (allow-by-default over kg_*, minus reads) and kg_create_node is not excluded.
  // Adding a second handler would DOUBLE-FIRE (and red the <=1 assertion below).
  kg_create_node: 'knowledgeEffects',

  // ── compositionEffects — S6/spec 31 (canon, corrections, style, voice). CLEARED for the canon
  //    family (S6 M1 ships quality-canon-rules + quality-canon). §8.0b re-partition: publish and
  //    conformance were mis-lumped here (three cross-session families in one file); they move to
  //    their OWN files below, so each family's handler is created by the wave that ships its panel. ──
  composition_canon_rule_create: 'compositionEffects',
  composition_canon_rule_update: 'compositionEffects',
  composition_canon_rule_delete: 'compositionEffects',
  composition_canon_rule_restore: 'compositionEffects',
  // S1-A3 — the work-resolution family scene-compose/chapter-assemble render from (outline/scene
  // writes are covered by bookEffects; create_work + generate were the residual hole).
  composition_create_work: 'compositionEffects',
  composition_generate: 'compositionEffects',
  // S5 (D-DIVERGENCE-MCP-TOOLS) — archiving a dị bản removes it from the book's Work set, so the
  // divergence manage panel + active-work resolvers (['composition','work']) must refresh. Covered
  // by compositionEffects `/^composition_(create_work|generate|archive_derivative)/`. Its READ
  // sibling composition_list_derivatives is asserted handler-free in READ_TOOLS below.
  composition_archive_derivative: 'compositionEffects',
  // S1-A3 — the prose WRITE (bookEffects, via /^composition_write_prose/). Now enumerated so the
  // ledger guards it (and its READ sibling composition_get_prose is asserted handler-free below).
  composition_write_prose: 'bookEffects',
  // publish → flywheel (S6/M5): the delta the flywheel panel renders. Keyed on extraction-complete,
  // NOT the publish confirm (the delta is produced async after publish) — see the S6 spec §9 (E2).
  composition_publish: 'flywheelEffects',
  // conformance → S4 (spec 33 quality-conformance panel).
  composition_conformance_run: 'conformanceEffects',

  // ── arcEffects — Wave 2 (spec 32) creates the file; Wave 4 extends its BODY (not a 2nd pattern). ──
  composition_arc_create: 'arcEffects',
  composition_arc_update: 'arcEffects',
  composition_arc_delete: 'arcEffects',
  composition_arc_move: 'arcEffects',
  composition_arc_restore: 'arcEffects',
  composition_arc_apply: 'arcEffects',
  composition_arc_assign_chapters: 'arcEffects',
  composition_arc_import_analyze: 'arcEffects',
  composition_arc_extract_template: 'arcEffects',
  composition_arc_suggest: 'arcEffects',
  composition_arc_template_drift: 'arcEffects',

  // ── motifEffects — Wave 3 (spec 33). ──
  composition_motif_create: 'motifEffects',
  composition_motif_patch: 'motifEffects',
  composition_motif_archive: 'motifEffects',
  composition_motif_adopt: 'motifEffects',
  composition_motif_bind: 'motifEffects',
  composition_motif_unbind: 'motifEffects',
  composition_motif_link_create: 'motifEffects',
  composition_motif_link_delete: 'motifEffects',
  composition_motif_mine: 'motifEffects',
  composition_motif_suggest_for_chapter: 'motifEffects',

  // ── planEffects — Wave 5 (spec 35). ──
  plan_compile: 'planEffects',
  plan_run_pass: 'planEffects',
  plan_apply_revision: 'planEffects',
  plan_propose_spec: 'planEffects',
  plan_self_check: 'planEffects',
  plan_validate: 'planEffects',
  plan_link: 'planEffects',
  plan_handoff_autofix: 'planEffects',
  plan_interpret_feedback: 'planEffects',
  plan_review_checkpoint: 'planEffects',

  // ── worldEffects — S7 / Wave 8 (spec 38) — CLEARED (Group B ships the world-map panel). ──
  world_map_create: 'worldEffects',
  world_map_delete: 'worldEffects',
  world_map_add_marker: 'worldEffects',
  world_map_remove_marker: 'worldEffects',
  world_map_add_region: 'worldEffects',
  world_map_remove_region: 'worldEffects',
  world_map_update: 'worldEffects',
  world_map_update_marker: 'worldEffects',
  world_map_update_region: 'worldEffects',

  // ── registryEffects — §8.0b has NO row for registry_*; PO-2 dropped it to Track C. It is TRACKED
  // (target wave-7), never silently dropped. No Studio panel reads registry workflows today, so a
  // Wave-0 handler here would be the no-op class again.
  registry_ingest: 'registryEffects',
  registry_propose_skill: 'registryEffects',
  registry_propose_workflow: 'registryEffects',
  registry_update_skill: 'registryEffects',
  registry_update_workflow: 'registryEffects',
  registry_set_skill_enabled: 'registryEffects',
};

// ── The PENDING allowlist. A row here = "this tool has NO handler, ON PURPOSE, until wave N". ──────
// Per §8.0b each handler file is created by the wave that ships its PANEL: a Wave-0 handler
// invalidating query keys of panels that DO NOT EXIST YET is itself a silent-no-op handler — exactly
// the class this ledger exists to kill. So Wave 0 ships the ENFORCEMENT, and each wave clears its rows.
const PENDING_FILES: Record<string, string> = {
  // compositionEffects: SHIPPED (S6 M1) — `/^composition_canon_rule_/` covers the canon family.
  // arcEffects: SHIPPED (S2/spec 32) — `/^composition_arc_/` covers every composition_arc_* write.
  // flywheelEffects: SHIPPED (S6/M5) — /^composition_publish$/ invalidates the flywheel delta; the
  // panel's own poll catches the async extraction that lands after the publish confirm (E2).
  // conformanceEffects: SHIPPED (S4/spec 33) — /^composition_conformance_run/ (studioConformanceEffects).
  // motifEffects: SHIPPED (S4/spec 33 wave 3) — /^composition_motif_/ (studioMotifEffects).
  // planEffects: SHIPPED (S3/M4) — `/^plan_(?!pass_status)/` refreshes the Pass Rail on plan_* writes.
  registryEffects: 'wave-7',
};

// 🔴 NOTE ON `diagnosticsEffects`: §8.0b and Q-30-X4-LANE-B-HANDLERS §4 both list it as a PENDING
// file, but its only tool family — `composition_diagnostics` — is declared READ-ONLY in its own MCP
// description ("READ-ONLY and cheap — it never calls an LLM and never runs conformance",
// server.py:3939). A read tool must NOT have an effect handler (it would thrash the query cache on a
// chatty read loop — the exact thing every existing pattern's negative-lookahead excludes). So it has
// no WRITE_TOOLS row, and it is asserted at ZERO handlers in READ_TOOLS below instead. If Wave 7 adds
// a real diagnostics WRITE tool, it gets a row here then.

const PENDING: Record<string, string> = Object.fromEntries(
  Object.entries(WRITE_TOOLS)
    .filter(([, file]) => file in PENDING_FILES)
    .map(([tool, file]) => [tool, PENDING_FILES[file]]),
);

// Representative READS per domain. An over-broad new pattern that starts thrashing the cache reds here.
const READ_TOOLS = [
  'glossary_get_entity', 'glossary_list_entities', 'glossary_search',
  'kg_graph_query', 'kg_project_list', 'kg_triage_list',
  'world_map_get', 'world_map_list',
  'composition_diagnostics', 'composition_get_work', 'composition_list_outline',
  'composition_get_prose', 'composition_get_outline_node',   // S1-A3 — reads MUST stay handler-free (no cache thrash)
  'composition_list_derivatives',   // S5 — the divergence LIST read; NO handler (archive_derivative carries the effect)
  'composition_get_derivative_context',   // S5 — one branch's durable spec; a READ, NO handler
  'composition_motif_get', 'composition_arc_get', 'plan_pass_status',
  'registry_list_skills', 'registry_get_workflow',
];

beforeEach(() => {
  clearEffectHandlers();
  _resetAllStudioEffectHandlers();
  registerAllStudioEffectHandlers();   // ← what the APP registers, via the SAME barrel the reconciler calls.
});

describe('Lane-B effect coverage ledger', () => {
  const covered = Object.keys(WRITE_TOOLS).filter((t) => !(t in PENDING));
  const pending = Object.keys(WRITE_TOOLS).filter((t) => t in PENDING);

  it.each(covered)('%s has >=1 registered effect handler', (tool) => {
    expect(matchEffectHandlers(tool).length).toBeGreaterThanOrEqual(1);
  });

  // The other half of the ledger: a PENDING row must be HONEST. If a wave lands its handler and
  // forgets to delete its PENDING rows, this reds — so the allowlist cannot rot into a lie.
  it.each(pending)('%s is PENDING and therefore has NO handler yet (delete the row when you build it)', (tool) => {
    expect(matchEffectHandlers(tool)).toHaveLength(0);
  });

  // §8.0b — matchEffectHandlers returns EVERY match and runEffectHandlers awaits ALL of them, so two
  // files claiming one domain DOUBLE-FIRE (they do not shadow). Wave 4/6 add ROWS ONLY; if a builder
  // also adds a second registerEffectHandler call for a domain that has one, this reds.
  it.each(Object.keys(WRITE_TOOLS))('%s matches AT MOST one handler (no double-fire)', (tool) => {
    expect(matchEffectHandlers(tool).length).toBeLessThanOrEqual(1);
  });

  it.each(READ_TOOLS)('%s is a READ — it must have NO handler (no cache thrash)', (tool) => {
    expect(matchEffectHandlers(tool)).toHaveLength(0);
  });

  it('every PENDING row names a file that is actually in the PENDING file map', () => {
    const orphans = Object.entries(PENDING)
      .filter(([tool, wave]) => PENDING_FILES[WRITE_TOOLS[tool]] !== wave);
    expect(orphans).toEqual([]);
  });
});

// 🔴 THE WIRING PROOF. The ledger above calls the barrel itself — which proves the BARREL registers
// everything, and proves NOTHING about whether the app's reconciler calls that barrel (memory:
// test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired). So assert the
// chokepoint at the SOURCE: the reconciler must call the barrel, and must NOT hand-roll the list —
// a hand-rolled list is how a new handler file ships registered-in-tests but dead in the app.
describe('the reconciler is wired to the SAME barrel this ledger tests', () => {
  const src = readFileSync(
    resolve(process.cwd(), 'src/features/studio/agent/useStudioEffectReconciler.ts'), 'utf-8',
  );

  it('useStudioEffectReconciler calls registerAllStudioEffectHandlers()', () => {
    expect(src).toContain('registerAllStudioEffectHandlers()');
  });

  it('useStudioEffectReconciler does NOT hand-roll individual register*EffectHandlers() calls', () => {
    const handRolled = src.match(/register(?!AllStudio)\w*EffectHandlers\(\)/g) ?? [];
    expect(handRolled).toEqual([]);
  });
});
