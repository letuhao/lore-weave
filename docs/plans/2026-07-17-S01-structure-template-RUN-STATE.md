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
| **B · panel + list + CLONE** | Open the panel, see built-ins + own, **clone a built-in** → an editable copy appears | Usability PASS — proven operable, not a shell. | **DONE** | `StructureTemplatesPanel` + `useStructureTemplates` + api (clone/create/update/archive/restore) + GG-8 (catalog/enum/contract/i18n). tsc 0, panelCatalogContract+legacyParity 14/14. **Backend live-smoke through the gateway :3123**: clone → "Hero's Journey (copy)", owner set True, v1, 12 beats. **LIVE BROWSER SMOKE on isolated static :5209** (dist-s01, HMR-free so S-04's session can't confound it): open palette → panel → built-ins listed → select Save-the-Cat → beats + read-only note render → **clone → an own editable "mine" copy appears** (new mine row, no read-only note) — `studio-structure-templates-journey.spec.ts` **1 passed (12.9s)**. |
| **C · beat editor** | On an own template: add / reorder / relabel / remove beats, rename, **save** | Usability PASS — real authoring, persists. | **DONE** | `OwnEditor` (own templates → editable beat rows: key/label/purpose + ↑↓ reorder + ✕ remove + add + rename + Save OCC); built-ins stay read-only+clone. Hook `save` mutation. **Live browser smoke :5209 (isolated): clone → rename unique → edit beat label → add beat → Save → navigate to a built-in → reopen my template → the edited label loads FROM THE SERVER** (persist proven, not local state) — 2/2 passed (6.5s). tsc 0. **The smoke CAUGHT a real dead-end**: clone named `"X (copy)"` fixed → cloning the same built-in twice 409'd on UNIQUE(owner,name). Fixed `clone_builtin` to auto-disambiguate `(copy)/(copy 2)/…`; real-DB repo test 8/8 incl. the new disambiguation test. |
| **D · archive/restore** (+ use-in-decompose → DEBT) | archive/restore an own template; the panel is fully usable | Archive/restore PASS; use-in-decompose tracked as DEBT (loop-connection, below). | **DONE** | `OwnEditor` gains an Archive button; `ArchivedDetail` (read-only + Restore); a "show archived" toggle. Hook archive/restore mutations + showArchived. **Live browser smoke :5209 (isolated): clone Story Circle → rename → save → archive → it leaves the default list → toggle archived → it reappears badged archived → select → restore → back in the default list** — 3/3 passed (9.3s, all of B+C+D). tsc 0. Backend restore already proven (repo 8/8). |

## REGISTERS
### DECISIONS (sealed — re-read, don't re-litigate; from 01_DECISIONS.md)
- `kind` = free-text label, NOT enum (CV-1). Tenancy = partial-unique `(owner_user_id,name) WHERE NOT NULL`
  + separate builtin-name unique; writes refuse owner-NULL (clone-to-edit). version OCC + is_archived from
  day one. book-shared tier OUT.
### DEBT
- **D-S01-USE-IN-DECOMPOSE (loop-connection)** — a "Use in decompose" deep-link from a custom structure
  into the decompose flow (`PlannerView`, composition). Deferred, NOT dropped. Gate: naturally-next-phase
  integration — it crosses into the decompose surface (possibly co-edited) and its smoke needs a book WITH
  chapters (decompose maps beats onto existing chapters). The structure-templates panel is **fully usable
  without it** (create/clone/edit/archive/restore all proven live) — this is a loop-connection (§2 bar #6),
  not a dead-end within the panel. Wire when the decompose surface is stable + seed a chaptered book for the
  smoke.

### DRIFT
- Slice C's live smoke CAUGHT a real dead-end (clone-twice 409) that unit tests + a single-clone smoke
  missed — the usability-first QC directive paid off exactly as intended. Fixed at the repo (auto-disambiguate).
- Slice D scoped down: use-in-decompose moved to DEBT (above) rather than rushed at the end of a long
  session. The bar it touches (#6 loop-connected) is honestly not yet met for decompose; recorded, not hidden.

## SAME-FOLDER RULES
Multiple sessions may run in parallel. Never `git add -A` — stage only S-01's files. The studio registry
(catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) is convergence-node work; for slice B's
panel, register minimally and note it in the commit. Scoped tests during BUILD.

## RESUME
Re-read THIS file first → `git log --oneline -10` → continue at the first non-DONE slice.
