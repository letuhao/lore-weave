# Glossary catalog unification — live results (2026-07-22)

Spec: `docs/specs/2026-07-22-glossary-catalog-unification.md`. Harness: `discover_ab.py`
(feed ONLY the default-visible tools to a weak model, check which tool it picks).

## Catalog shrink (live-counted on the running container, glossary `/mcp` :8211)

| | before | after |
|---|---|---|
| default-visible (hot-set) | ~42 | **25** |
| legacy/hidden | 8 | **29** (20 newly-tagged this effort) |

**16 old tools → 4 unified surfaces:** `glossary_curation_list` (view enum ← 3 inbox
reads), `glossary_propose_curation` (op enum ← 4 curation proposes), `glossary_set_genres`
(target enum ← 3 genre setters), `glossary_get_entity.include` (← 4 entity-detail reads).

## Ambient-envelope smoke (the new tools are born `WithAmbientBook`)

`glossary_curation_list` called with **no `book_id` arg** + `X-Book-Id` header → resolved
from the envelope, `isError:false`. Cross-book Tier-A write guard on `set_genres`:
- cross-book, no `allow_cross_book` → `cross_book_confirm_required` + guidance (NOT applied)
- cross-book, `allow_cross_book:true` → grant-checked + applied
- ambient (no arg) → normal path

## Discoverability (gemma-4-12b, `google/gemma-4-12b-qat`, temp 0, N=4 runs)

Does a weak model pick the RIGHT unified tool + discriminator for a natural request, given
only the shrunk 25-tool catalog?

| scenario | expected | result |
|---|---|---|
| "show the merge candidates to review" | `curation_list` view=merge_candidates | ✅ 4/4 |
| "what AI-suggested entities need review?" | `curation_list` view=ai_suggestions | ✅ 4/4 |
| "list the unknown-kind entities to triage" | `curation_list` view=unknowns | ✅ 4/4 |
| "approve these draft entities as active" | `propose_curation` op=status_change | ✅ 4/4 |
| "merge duplicate X into Y" | `propose_curation` op=merge | ✅ 4/4 |
| "reassign entity to the 'character' kind" | `propose_curation` op=reassign_kind | ⚠️ 3/4 |
| "turn on the 'xianxia' genre" | `set_genres` target=book_active | ✅ 4/4 (after fix) |
| "show entity + revisions + evidence" | `get_entity` include=[revisions,evidence] | ✅ 4/4 |

**Aggregate: 7–8/8 per run.** The discriminator (view/op/target/include) is **always
correct when the tool is picked** — the enum design works. The lone variable is `reassign`:
on a request naming a specific kind ("reassign to the **'character'** kind") the model
sometimes calls `book_ontology_read` first to look up the referent — a defensible
read-then-act that a real multi-turn loop recovers from, not a naming defect.

### Finding that drove a fix
Initially "turn on the xianxia genre" mis-routed to `book_ontology_read` because
`set_genres`'s description led with the abstract *"Wire the genre MATRIX"*. Synonyms live
in `_meta` (NOT shown to the model), so the **description** must carry discovery — front-
loading *"Turn a book's genres ON or OFF … ACTIVATE or DEACTIVATE"* fixed it to 4/4.
General lesson: a unified tool's description must lead with the plain user action, not the
internal concept.

Run: `python discover_ab.py` (needs glossary `/mcp` :8211 + lm_studio :1234 with gemma-4).

---

## 2026-07-23 — the unification shipped a PROVIDER-WIDE OUTAGE (found by real E2E only)

### What broke
`glossary_curation_list` (Part B) declared its discriminated-union payload as
`Items any`. The go-sdk reflector renders an `any` field as the JSON-Schema
**boolean** `true`. That is legal JSON Schema 2020-12 — and ai-gateway's zod
federation validator rejects it:

```
WARN [FederationService] provider 'glossary' list-tools failed → PARTIAL:
  [{ "code":"custom", "path":["tools",12,"outputSchema","properties","items"], "message":"Invalid input" }]
LOG  [FederationService] catalog: 235 tools / 10 providers (... PARTIAL)
```

**One malformed schema on one tool silently de-federated all 54 sibling tools.**
Measured: `0` `glossary_*` tools of 245 federated. Every agent lost the entire
glossary catalog — including the very tools the unification had just created.

### Why nothing caught it
Every existing gate stayed green, because the schema is **valid in isolation**:
the tool's unit tests, `TestMCPClosedSetArgsAreEnums`, `TestLegacyToolsCarryVisibilityMeta`,
and route-conformance all pass. The defect only exists at the **federation boundary** —
a different service, a different language, a different validator. Classic two-sides-
joined-only-by-a-contract bug (the same shape as the `panel_id` frontend-tool bug).

It also **masked** a separate investigation: gemma looked like it was ignoring an
explicit re-route, when in fact it *followed* it and got
`tool_load(name="glossary_propose_entities") → {"not_found": [...]}` — the tool
genuinely did not exist in its catalog. The model was right; the platform was broken.

### Fix
Hand-written `curationListOutputSchema()` (`curation_tools.go`) declaring
`items: {type: array, items: {type: object}}` — states the union's real shape, emits
no boolean subschema. Wire shape unchanged.

### Gate added
`TestNoBooleanSubschemasAnywhere` (`mcp_tool_schema_contract_test.go`) walks **every**
tool's `inputSchema` + `outputSchema` over the real `tools/list` wire and fails on any
boolean subschema (`additionalProperties` exempt — a boolean there is idiomatic and
accepted). Verified adversarially: **reds on the exact defect**, green with the fix.

### Verification (live, before → after)

| | before | after |
|---|---|---|
| ai-gateway catalog | 235 tools, `PARTIAL` | **289 tools, no PARTIAL** |
| `glossary_*` federated | **0** | **54** |
| S00b turn A tool calls | 4 (all rejected placeholder-id edits) | **2** |
| first-try correct write | ✗ | ✅ `glossary_propose_entities` `ok=true` |
| entity in DB | ✗ none | ✅ `019f8cbe-b8c1-7a05-b368-ed00a87cbde7` "Lâm Uyên" (draft) |

The winning trace is the documented **read-then-act** shape — `glossary_book_ontology_read`
(fetch the valid kinds) → `glossary_propose_entities` with a real `book_id` UUID and
`kind: "character"`. No `find_tools`, no schema-guess round-trip.

### Lesson
A schema that is valid in its own language can still be **invalid at the federation
boundary**, and the blast radius is the whole provider, not the one tool. Any new
`any`/`interface{}`-typed field in an MCP payload needs an explicit schema. Sibling
services registering MCP tools should carry the same guard.
