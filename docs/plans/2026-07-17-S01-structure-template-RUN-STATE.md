# S-01 structure-template authoring — RUN-STATE

## COMMITMENT
Build S-01 (custom story structures) slice-by-slice, **QC each slice for real USABILITY before moving on**.
Spec: [`docs/specs/2026-07-17-studio-completeness-build/S-01_structure-template-authoring.md`] · Decisions:
[`01_DECISIONS.md`]. Finish = a brand-new user can create/clone a story structure, author its beats, and
decompose their book against it — proven by a LIVE BROWSER smoke, not just unit green.

## THE ANTI-PATTERN THIS RUN MUST NOT REPEAT (PO directive, 2026-07-17)
plan-hub is the cautionary tale: `usePlanNodeWrites` has only `edit`+`archive` (no create), assumes a plan
already exists, and renders read-only silently when writes are omitted → "view-only, everything blocked, the
user can't do anything." **An empty shell that ships green is the failure.** Every slice below is gated on a
USABILITY analysis (ENTRY from empty · ACTION→visible RESULT · no DEAD-END · operable-not-just-rendered), and
QC'd by a live-browser smoke that shows a user actually DOING the thing.

## USABILITY-FIRST SLICE BOARD
| slice | what the USER can do after it | usability check (must pass before build) | status | EVIDENCE |
|---|---|---|---|---|
| **A · BE write side** | *(nothing yet — foundation; honestly NOT user-operable alone)* | QC done on REAL DB, not skipped. | **DONE** | migration (partial-unique tenancy + version + is_archived) · repo (create/clone/update/archive/restore) · 6 routes (canon.py) · 5 MCP tools (per-user). **Real-DB repo test 7/7** (tenancy: 2 users share a name / 1 can't dup · cross-user isolation · built-in read-only · clone · OCC 412 · archive→restore). Routes 31/31 (test_outline_canon_routers). MCP 64/64 (catalog+schema). |
| **B · panel + list + CLONE** | Open the panel, see built-ins + own, **clone a built-in** → an editable copy appears | ENTRY from empty = clone (a user with zero own templates gets a starting structure in one click). RESULT = a new "mine" row, selectable. First genuinely operable slice. QC = live smoke: open → clone → own copy visible. | TODO | |
| **C · beat editor** | On an own template: add / reorder / relabel / remove beats, rename, **save** | ACTION→RESULT = edit a beat, save, reopen → it stuck (version bumped). Not an abstract drawer — a real authoring surface. QC = live smoke: clone → edit beats → save → reopen persists. | TODO | |
| **D · close the loop + archive/restore** | **Use the custom structure in decompose**; archive/restore an own template | NO DEAD-END = the template you authored actually DRIVES a decompose (maps beats onto chapters). archive hides, restore brings back. QC = live smoke: author → "Use in decompose" → beats mapped; archive→restore round-trip. | TODO | |

## REGISTERS
### DECISIONS (sealed — re-read, don't re-litigate; from 01_DECISIONS.md)
- `kind` = free-text label, NOT enum (CV-1). Tenancy = partial-unique `(owner_user_id,name) WHERE NOT NULL`
  + separate builtin-name unique; writes refuse owner-NULL (clone-to-edit). version OCC + is_archived from
  day one. book-shared tier OUT.
### PARKED · DEBT · DRIFT
- (append as we go — an empty DRIFT log at the end is dishonest)

## SAME-FOLDER RULES
Multiple sessions may run in parallel. Never `git add -A` — stage only S-01's files. The studio registry
(catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) is convergence-node work; for slice B's
panel, register minimally and note it in the commit. Scoped tests during BUILD.

## RESUME
Re-read THIS file first → `git log --oneline -10` → continue at the first non-DONE slice.
