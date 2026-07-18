# PO Decision Sheet — Writing Studio tool↔GUI build

> **Status:** awaiting PO. The build is PAUSED at the PO's instruction (*"chưa build vội, cần clear open
> questions, concern trước đã"*). Wave 0 was started and stopped mid-flight — see §5.
>
> **Read §1 and answer. Everything else is FYI or already closed.**

---

## 0 · What changed since the plan was approved

A **concurrent audit** (a separate session) independently re-verified 10 claims from plan 30 with live
repro inside the container. It **converged with our own adversarial QC on the most important finding**,
and it **caught one systemic hole we missed**. It also found two of our documents describing a bug with
the *wrong mechanism*.

**The convergence (good).** Both audits independently found that the motif-Mine / 拆文 failure is **an
HTTP 500 *before* the job is ever enqueued**, not a 404 at the poll:
`_enqueue_motif_job` stamps a synthetic `uuid4()` as `project_id`; `GenerationJobsRepo.create()` is not a
plain INSERT — it derives the `NOT NULL book_id` via `INSERT … SELECT … FROM composition_work WHERE
project_id = $2`; the synthetic id matches **zero rows**; it raises `ReferenceViolationError`;
`/actions/confirm` returns **500** with the confirm token burned (retry → 409). **No Redis XADD, no
worker, no LLM call — so nobody was ever charged.** (Our plan-30 §3.3 says the user "pays and watches a
spinner forever." That is **wrong in the user's favour**, and it must be corrected before it misleads
the next agent.)

Our Wave-0 QC caught this and already rebuilt `W0-BE1` as the full fix (DDL + `create_unbound()` +
writer + owner-scoped read + MCP arg), with the tests forced **through the producer** — because a fixture
that raw-`INSERT`s the job row would ship **green over a still-broken live path**
(`fixtures-can-seed-a-field-the-writer-never-sets`). **No plan change needed. But three documents still
carry the wrong mechanism (§2, DOC-1).**

---

## 1 · 🔴 THE DECISIONS — answer these

### D-1 · The `Vietnamese` → `vi` data migration  · **DESTRUCTIVE · blocks Wave T**

`target_language` is a free string with no validator, and it is part of
`UNIQUE(chapter_id, target_language, version_num)`. The dev DB now holds **5 rows saying `Vietnamese`
next to 89 saying `vi`** — written by an LLM agent on 2026-06-27. They are the *same language* occupying
*two identities* in a uniqueness key, so they cannot be merged without a **three-table rekey**.

- **Option A — rekey now** (as part of Wave T). Cost: a destructive migration touching a UNIQUE column
  across 3 tables. Needs a dry-run + a rollback path + a row-count assertion before/after.
- **Option B — enum the write path now, rekey later.** Cost: the phantom rows stay; every consumer must
  keep tolerating two spellings; the debt compounds with each new corrupt row.
- **Option C — leave both.** Cost: the corruption keeps growing. Not recommended.

**Recommendation: A, but I do not run it without your explicit go.** It is squarely in the CRITICAL class
(destructive / irreversible). If you say go, I will produce the migration + dry-run output for your review
*before* executing.

> **Your answer:**

---

### D-2 · The 4 HIGH bugs — hotfix batch now, or inside Wave 0?

Three of the four are **already Wave-0 slices**: `AddModelCta` (X-1 / `W0-S3`), motif-Mine 500
(`W0-BE1`), the conformance 404s (`W0-S7`). The fourth — **Translate throws away your ticked chapters**
and substitutes the whole backlog (`TranslationTab.tsx:300-305` renders `<TranslateModal>` with **no
`preselectedChapterIds`** though the prop exists and the sibling `ExtractionWizard` passes it) — lives in
**Wave T**, which is scheduled last.

Two of these are **actively damaging users today**: `AddModelCta` silently loses unsaved prose, and
Translate silently mistranslates the wrong chapters.

- **Option A — one small hotfix batch first** (the 4 HIGHs, disjoint from the wave plan), then Wave 0.
  Cost: one extra commit cycle; delays Wave 0 by a few hours.
- **Option B — Wave 0 as planned, pull the Translate fix forward into it.** Cost: none really; Wave 0
  already carries 3 of the 4.

**Recommendation: B.** Wave 0 *is* the hotfix batch — it already contains 3 of the 4. Add the Translate
one-liner to it and ship Wave 0 first, before any new panel work.

> **Your answer:**

---

### D-3 · 🆕 The global `MutationCache.onError` — the hole that hid all of this

`frontend/src/App.tsx:6` constructs `new QueryClient({…})` with **no `MutationCache`**. There is no
global `onError`. So **every failed mutation in the entire frontend fails silently** — the button just
re-enables. That is *why* three separate live bugs survived to an audit: nothing ever announced them.

The repo already legislates this — *"a resolver never silently no-ops"* — but wrote it for **agent→GUI
tools** and never applied it to **user-initiated GUI actions**. Same bug class, different surface.
(Note: individual hooks like `useAdoptFlow`/`useMotifBinding` *do* have `onError`. The gap is the
**global default**, which is what makes a *missing* handler safe by construction.)

- **Option A — add it to Wave 0** (~20 lines + a test). Every future silent failure becomes visible.
- **Option B — its own slice later.** Cost: every wave we ship until then can ship a silent no-op.

**Recommendation: A.** It is the highest leverage-per-line item in the whole build, and it makes the
other waves *safer to build*.

> **Your answer:**

---

### D-4 · The content-language SSOT — name it

There is no content-language SSOT. `frontend/src/lib/languages.ts` (18 entries) is **TS-only**; Python
has nothing; the MCP tool takes a bare `str`. This is the root cause of D-1.

Our adjudication (`BE-29-LANG-REGISTRY-PY`) already decided the **shape**: a translation-service-local
module + a committed contract file as the FE↔Py join, mirroring `contracts/frontend-tools.contract.json`
(a proven, precedent-setting mechanism in this repo). The concurrent audit proposes the same thing with a
different name.

⚠ **Both agree on the trap:** it must **NOT** be called `contracts/languages.yaml` —
`contracts/language-rule.yaml` **already exists** and means *service → programming language*. Two
concepts under one name is the exact drift this repo legislates against.

- **Option A — `contracts/languages.contract.json`** (our adjudicated default; matches the
  `frontend-tools.contract.json` precedent exactly, and the `.contract.json` suffix already *means*
  "cross-language SSOT" in this repo).
- **Option B — `contracts/content-languages.yaml`** (the other audit's proposal; the `content-` prefix is
  more self-documenting against the `language-rule.yaml` collision).

**Recommendation: A** — the suffix convention already carries the meaning, and `frontend-tools.contract.json`
is the proven shape. But this is a naming call and I will take either.

> **Your answer:**

---

### D-5 · `D-STUDIO-MOBILE-SHELL` — **blocks the ChapterEditorPage deletion (GG-4)**

The Studio has **no mobile editing surface**. `MobileEditorShell.tsx` / `MobilePanelSwitcher.tsx` exist
**only** on the legacy path. So even after Wave 6 ports every legacy feature, deleting
`ChapterEditorPage` would **remove mobile editing entirely**.

- **Option A — build a mobile Studio shell** (its own wave; not currently planned).
- **Option B — keep the legacy page for mobile only** (route-gate it). Cost: the "one editing surface"
  goal is not met; the parity guard must permanently exempt the mobile route.
- **Option C — accept desktop-only** and delete the mobile shell with the page.

**Recommendation: decide at Wave 6's close, not now** — but know that **GG-4 stays shut until you do.**
Wave 6 ships the *mechanical parity guard*, not the deletion. Nothing is lost by deferring this.

> **Your answer (or "decide at Wave 6"):**

---

### D-6 · `D-COMPOSE-GENERATE-UNGATED` — a paid route with no confirmation gate

`POST /works/{pid}/generate` **spends LLM tokens with no confirmation gate**, while its own MCP twin
**is** Tier-W confirm-gated. The shipped `ComposePanel` drives the **ungated** route today.

This is **adjacent to the CRITICAL "charges the user for nothing" class** — but it is **pre-existing and
not a regression of this batch**, and the user *does* get what they paid for (it generates). So it defers
under gate #1.

⚠ **It must be fixed AT THE ROUTE, not by gating the Regenerate button** — gating one call site would
create a second confirmation convention, and **AN-8 seals one-channel-per-object-class**.

- **Option A — pull it forward into Wave 0.**
- **Option B — carry it; raise at Wave 3/3c as planned.**

**Recommendation: B**, unless you want the spend gate closed immediately.

> **Your answer:**

---

### D-7 · `worldmap` — a **circular defer**. No wave builds it.

Spec 38 says the legacy place-graph *"belongs to plan 30's Wave 6 editor-craft ports, not here."*
**Wave 6 does not contain it.** So it is homed nowhere, and it **dies at the GG-4 gate.**

⚠ It is **not** the same thing as Wave 8's `world-map` panel: that one is book-service's
`world_maps`/`map_markers`/`map_regions`; the legacy `useWorldMap` reads `work.settings.world_map` — plan
30 §10 explicitly refutes conflating them.

- **Option A — add a `place-graph` panel slice to Wave 8** (leaf-reuse `WorldMap.tsx`; Wave 8 is already
  in those files).
- **Option B — rule that book-service's real world-map supersedes it.** Cost: the existing
  `work.settings.world_map` blobs must be **migrated or they are orphaned** — that migration must then be
  specced.

**Recommendation: A.** It is cheap (a leaf-reuse port into a wave already touching those files), and B
carries a silent data-orphaning risk.

> **Your answer:**

---

## 2 · Document corrections — no decision needed, I will just do these

| # | Fix | Why |
|---|---|---|
| **DOC-1** | 🔴 Correct the mechanism in **spec 33 §1.2 + §5.1**, **spec 34 §0.1 + AT-5 + BE-7c**, and **plan 30 §3.3**: the motif-Mine / 拆文 / arc-import failure is a **500 at confirm (before enqueue)**, not a 404 at the poll. State plainly that **no user was ever charged** — our §3.3 currently claims the opposite. | Three sealed documents prescribe an **owner-scoped job read** as the cure. That route would read **a row that does not exist**, and it would **ship green** (its test seeds the row directly). The Wave-0 plan is already correct; the specs are not, and the specs are what the next agent reads. |
| **DOC-2** | Delete plan 30 §3.4's **`web_search` namespacing** row. | It cites *"the repo's own LOCKED law"*. That law does not exist as a locked standard — it is a *lesson*. The row overstates its own authority and sends the next agent chasing a non-rule. |
| **DOC-3** | Correct plan 30's **"progress is write-only"** framing. | The legacy page has a **full progress tab on a real GET route**. The true gap is narrower: *the Studio has no progress panel*. (We already downgraded `G-PROGRESS` to PARTIAL for exactly this reason — the §3 prose did not follow.) |
| **DOC-4** | Add **BE-5 `regenerate-to-beat` = DELETE the FE call, do not build the route** to plan 30's §6. | Spec 33 already seals this (`BE-5 — DO NOT BUILD — REFUTED`). Plan 30 §6 still implies a build. |

---

## 3 · New gates worth adding (each turns a bug we found into a bug we cannot re-ship)

| Gate | Catches | Cost |
|---|---|---|
| **Global `MutationCache.onError`** (D-3) | The entire silent-failure class. Would have surfaced all 3 live bugs on day one. | ~20 lines |
| **FE↔BE route contract check** | The 3 confirmed invented-URL 404s — and the 4th nobody has written yet. Mechanically checkable: every path in `api.ts` vs the route table. | a script + CI row |
| **No raw `<Link>` in dock-reachable code** + flush-on-unmount | `AddModelCta` (X-1) fixes *one* call site; nothing stops a 6th. And the Studio **never flushes pending saves on unmount** — so browser-back or a 401 redirect **also** loses prose. | a lint rule + a hook |
| **GG-1 has no gate** | Plan 30 calls *"every backend capability needs a human surface"* **THE LAW** and enforces it nowhere. A tool description saying *"the user approves in the UI"* is **greppable**. | a script |

**Recommendation:** take the first one in Wave 0 (D-3). The other three are cheap and I would fold them
into the waves that create their bug class — but say the word if you want them all up front.

---

## 4 · Already settled — do not re-raise

| Item | Verdict |
|---|---|
| **E-1** — "the adjudication register does not exist" | ✅ **CLOSED.** It was recovered from the workflow journal and split per wave into `docs/plans/studio-adjudication/`. Reconciliation folded **389** decisions into the wave plans and found **171** places where a plan contradicted an adjudicated decision. |
| **E-2** — `D-W7-X13-REHOME` | ✅ **CLOSED.** X-13 is built in `W0-S5c` — *earlier* than its deadline. |
| **E-4** — Track C's claim on the `world` container | ✅ A write-down, not a stall. P-5 is parked with no design; spec 38 has the design. |
| **The Work-less job lane** — "should be a Wave-0 BE prereq" | ✅ **It already is** (`W0-BE1`). |
| **`regenerate-to-beat`** | ✅ Sealed **DO NOT BUILD** (spec 33 BE-5). The fix is a **delete**. |
| **PO-1..PO-4** | ✅ Sealed 2026-07-12. Not re-openable from memory. |

---

## 5 · ⚠ Uncommitted, unverified work on disk right now

Wave 0 was started and **stopped mid-flight**. Stages 1–2 ran; stages 3–4 did not. These files are on
disk, **uncommitted and untested**:

- `frontend/src/components/shared/AddModelCta.tsx` (+ its test)
- `frontend/src/features/studio/agent/effectRegistry.ts`, `handlers/bookEffects.ts`,
  `useStudioEffectReconciler.ts` (+ tests)
- `frontend/src/features/studio/panels/catalog.ts`, `palette/useStudioCommands.ts` (+ tests)
- `frontend/src/i18n/locales/*/studio.json` (18 locales)
- `contracts/api/composition/v1/openapi.yaml`
- the spec renames `14_*`→`14a/14b`, `15_*`→`15a/15b`

**HEAD is clean** (`69f8f2963`, docs only). Nothing was committed.

🔴 **When the build resumes, this work must be VERIFIED, not assumed.** It was written by parallel agents
and never type-checked or tested. The resumed Wave 0 runs `npx tsc --noEmit` **first** — a parallel-lane
collision shows up as a type error, not as a merge conflict.

**If you prefer a clean start, say so and I will revert these and rebuild them under the corrected specs.**
