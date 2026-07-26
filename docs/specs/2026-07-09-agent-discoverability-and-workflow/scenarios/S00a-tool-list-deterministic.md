# S00a · `tool_list(category)` — deterministic, complete enumeration stops the loop

> ⚙️ **MECHANISM / developer test — white-box BY DESIGN. This is NOT a black-box user scenario.**
> It verifies the primitive directly (it names the tool because it *is* the tool under test). The
> user-observable proof that this primitive fixed the experience lives in the black-box scenarios
> (S02 "add my characters" with no thrash). Keep those two roles separate: black-box scenarios judge the
> user outcome; mechanism tests like this one judge the primitive. If S00a passes, every domain scenario
> has a deterministic escape hatch from the `find_tools` grind.

| Field | Value |
|---|---|
| **Scenario id** | S00a |
| **Maps to umbrella** | Phase 1 — the discovery triad, §4.1 — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) |
| **Persona** | any (the model itself is the subject) |
| **Surface** | chat |
| **Permission mode** | `ask` (read-only — listing is inert) |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế (for scope) |
| **Status** | ✍️ drafting |
| **Owner** | — |

## 1. User story / intent

> When gemma faces "add an entity" and doesn't know the tool's name, it must be able to **list the whole
> glossary category once, deterministically**, see `glossary_propose_entities` in that list, and proceed —
> instead of re-phrasing `find_tools` a dozen times hoping the ranker surfaces it.

## 2. Preconditions / setup

- `tool_list` primitive built (Phase 1) and advertised; category enum single-sourced from
  `GROUP_DIRECTORY` + `all`.
- `gemma-4-26b-a4b-qat`, chat surface.

## 3. The behavior under test

Calling `tool_list(category)` returns **every** tool in that category (the visible set =
`catalog ∩ non-legacy ∩ policy-allowed`), unranked, as `{name, short description, tier, deprecated?}` —
reproducibly, with no similarity floor and no dependence on the `intent` wording.

## 4. Target chat script (EXPECTATION)

| # | User says | Assistant SHOULD do | Tool calls SHOULD be | End state |
|---|---|---|---|---|
| 1 | "What can I do with the glossary here?" | Call `tool_list("glossary")` once; present the full set grouped by read/write; name the create/edit tools explicitly. | `tool_list("glossary")` (1 call). **No `find_tools`.** | Full glossary tool list shown incl. `glossary_propose_entities`, `glossary_entity_set_attributes`. |
| 2 | "List everything across all domains." | `tool_list("all")` (or per-category); present the catalog compactly. | `tool_list("all")` (1 call). | Complete catalog; deterministic. |
| 3 | (repeat turn 1 in a fresh session) | Same list, same order. | `tool_list("glossary")` (1 call). | **Byte-identical** result — reproducible. |

## 5. Acceptance criteria (measurable)

- [ ] `tool_list("glossary")` returns the **full** glossary set (all policy-allowed, non-legacy tools) —
      count matches the catalog, not a top-K slice; `glossary_propose_entities` is present.
- [ ] Result is **deterministic**: identical across repeated calls / fresh sessions / reworded lead-in
      (it takes a category, not an `intent`).
- [ ] Deprecated (`legacy`) tools appear **labeled** `deprecated + superseded_by`, not dropped and not
      hidden (kills the 3-registry drift; the invisible-but-callable class is gone).
- [ ] gemma issues **0** `find_tools` calls for this task once `tool_list` exists.
- [ ] `tool_list("all")` scoped to the key returns only tools the key may actually call (no anti-oracle
      leak).

## 6. Baseline — CURRENT behavior with gemma (fill via live test)

- _pending — on the CURRENT system there is no `tool_list`; the closest is `find_tools(group, intent="")`
  enumeration fallback. Baseline should measure: does the enumeration fallback reliably fire for gemma,
  and does it include `glossary_propose_entities`? (Per the feedback: the 33-tool glossary dump did NOT
  include it — because it's `legacy`.) Record whether gemma can reach entity-create today at all._
- Transcript: `docs/eval/discoverability/YYYY-MM-DD-S00a-gemma.md`

## 7. Gap → required capability

- **Phase 0:** define the visible set = `catalog ∩ non-legacy ∩ policy-allowed`; label (don't drop)
  deprecated tools; single-source the category enum; resolve the `lore_enrichment` orphan + `admin`
  question.
- **Phase 1:** build `tool_list(category?)` as a first-class MCP meta-tool (promote `enumerateGroup`);
  land in TS (`find-tools.ts`) + Py (`tool_discovery.py`) lockstep with `find-tools.spec.ts` coverage;
  advertise it *first* (before `find_tools`) in `tools/list`.

## 8. Re-test gate

✅ when gemma answers "what can I do with the glossary" via a single deterministic `tool_list` call that
surfaces the create/edit tools, with 0 `find_tools` calls. This is the precondition that makes S02 (add
entities) winnable even if the workflow layer isn't reached.
