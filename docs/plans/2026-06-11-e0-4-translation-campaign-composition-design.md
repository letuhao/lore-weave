# E0-4 — translation + campaign + composition adopt · DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom). Slice of the E0 epic — see [`-design`](2026-06-11-e0-collaboration-design.md), [`-plan`](2026-06-11-e0-collaboration-plan.md). **Goal:** a book collaborator can use translation / campaign / composition on a shared book per their grant. The plan called this "M / straightforward"; CLARIFY (below) found it's three E0-3-scale adoptions → **sub-sliced into 4a/4b/4c**.

## 0. CLARIFY — PO decisions (2026-06-11, locked)

| ID | Decision | Choice |
|---|---|---|
| **D-E0-4-A** | **Slicing** | Sub-slice into 3 loom cycles: **E0-4a translation** → **E0-4b campaign** (depends on 4a) → **E0-4c composition** (independent). Each degrades to owner-only until it ships (fail-safe). |
| **D-E0-4-B** | **Attribution** | **Caller-attributed** — a collaborator's writes are stored under *their* `user_id` (NOT resolve-to-owner). Diverges from E0-3 (knowledge). |
| **D-E0-4-C** | **Billing** | **Strict caller-pays everywhere** — whoever runs it pays with their **own** BYOK key/budget. This is forced by the **BYOK isolation invariant**: provider-registry resolves models with `WHERE owner_user_id=caller` — only the key owner can cause their key to be charged. |
| **D-E0-4-D** | **Campaign tier** | create/start/cancel/patch-budget = **manage**; pause = **edit**; get/list/progress = **view**. (Expensive autonomous batch → high bar.) |
| **D-E0-4-E** | ~~Campaign billing split~~ **RESOLVED → no split** | Originally "knowledge=owner-pays, translation=caller-pays." **Superseded by the BYOK re-audit (2026-06-11):** the shared-graph constraint is on the **embedding model** (vector space), NOT the provider/key. A collaborator who has the **same embedding model** under their own BYOK (any provider) can extract into the shared graph with **their own key** — same vectors, billed to them. So **everything is caller-pays**, including the campaign's knowledge stage. |
| **D-E0-4-F** | **Read visibility** | **Shared per-book view for OUTPUTS** (coverage / versions / jobs) — reads gate on book-grant and **drop the `owner_user_id` predicate** (E0-2 R3 transform; `book_id` still scopes → IDOR-safe). **Settings stay per-user** (each collaborator's own model config; do NOT drop owner_user_id in `effective_settings` — that would resolve the owner's `model_ref` under the caller and fail/leak). |
| **D-E0-4-G** | **BYOK re-audit (2026-06-11)** | Confirmed: translation worker bills `msg["user_id"]` = caller (BYOK-correct); `effective_settings` resolves per-user (caller's own model). **E0-3 contradiction found:** `start_extraction = EDIT` + resolve-to-owner → an edit-collaborator triggers extraction on the **owner's** key (BYOK breach). **Fix = strict caller-pays + embedding-model-match guard** → tracked as **D-E0-3-CALLER-PAYS-EXTRACTION** (revise E0-3 before/with E0-4b): the embedding **provider call** uses the **caller's** key; graph **data** stays owner-partitioned (shared vector space); reject if the caller's embedding model ≠ the project's model+dim; the project exposes its embedding model identity so the collaborator can register the same one (provider-agnostic). |

**Resulting model = E0-2's book-service pattern** (caller-attributed writes + drop-owner read transform + a book-grant chokepoint), NOT E0-3's resolve-to-owner. Well-trodden. **E0-4a translation is unaffected by the BYOK re-audit — caller-pays was already correct.**

---

## E0-4a — translation-service adopt (THIS slice)

### 1. Surface (from the ownership map)
- **`_verify_book_owner(book_id, user_id)`** (jobs.py) — calls book-service `/internal/books/{id}/projection`, compares `owner_user_id`. Used by public `create_job` + internal `dispatch_job`. **The named swap target.**
- **Inline duplicate** in `extraction.py` `create_extraction_job` (same projection→owner compare).
- **Per-resource `owner_user_id == user_id`** checks scoped by job/chapter/book:
  - `jobs.py`: `list_jobs` (book-scoped read), `get_job` / `get_chapter_translation` / `_cancel_job_core` (job-scoped).
  - `versions.py`: `_assert_owner` ×3 — `get_chapter_version` (read), `set_active_version` (write), `save_edited_version` (write).
  - `extraction.py`: `cancel_extraction_job` / `get_extraction_job` (job-scoped).
  - `coverage.py`: `get_book_coverage` (book-scoped read).
  - `settings.py`: `get_book_settings` / `put_book_settings` — keyed by `book_id` (settings rows are per-book).
- **`internal_dispatch.py`** — `_verify_book_owner` re-check (defense-in-depth on the asserted user_id); the `dispatch_chapter_status` / `dispatch_job_status` / `dispatch_cancel` are owner-scoped by the **asserted** user_id (internal-token authenticated). These stay as-is structurally but the asserted user is now a collaborator (4b passes the caller).

### 2. need-mapping (per D-E0-4-D principle, scaled to translation)
| Route | need | scope |
|---|---|---|
| `GET /books/{id}/jobs` (list) · `GET /jobs/{id}` · `GET /jobs/{id}/chapters/{c}` · `GET /books/{id}/coverage` · `GET /chapters/{c}/versions` · `GET /chapters/{c}/versions/{v}` · `GET /books/{id}/settings` | **view** | book / job→book |
| `POST /books/{id}/jobs` (create-translate) · `POST /books/{id}/extract-glossary` · `PUT /books/{id}/settings` · `POST /chapters/{c}/versions/edit` (save human edit) · `PUT /chapters/{c}/versions/{v}/active` (publish) | **edit** | book / version→book |
| `POST /jobs/{id}/cancel` · `POST /extraction/jobs/{id}/cancel` | **edit** | job→book |

- **Reads** (view): apply `require_book_grant(view)` (book in path) or resolve book from the job/version row then check grant; **drop** the `WHERE owner_user_id=$2` predicate (keep `WHERE book_id=$1` / `WHERE job_id=$1` — D-E0-4-F). IDOR-safe: the row stays scoped by book/job, the grant is the gate.
- **Writes** (edit): grant-gate, then attribute to the **caller** (`owner_user_id = caller`, billed to caller's BYOK — unchanged insert, the caller's uid is already what's written).
- **`get_book_settings`** synthesizes defaults with `owner_user_id=uid` (caller) — fine; settings rows are book-keyed so reads/writes resolve the same row regardless of caller (drop-owner there too).

### 3. The gate (`app/auth/grant_deps.py` — mirrors E0-3 shape, caller-returning)
```python
def require_book_grant(need):           # book_id in path
    async def _dep(book_id, caller=Depends(get_current_user), gc=Depends(get_grant_client)):
        lvl = await gc.resolve_grant(book_id, UUID(caller))
        if lvl == GrantLevel.NONE: raise _not_found()      # anti-oracle 404
        if not lvl.at_least(need):  raise _forbidden()     # 403
        return UUID(caller)                                 # caller-attributed
    return _dep

def require_job_grant(need):            # job_id in path → bootstrap book_id
    async def _dep(job_id, caller=..., gc=..., db=...):
        book_id = await _book_for_job(db, job_id)           # SELECT book_id FROM translation_jobs
        if book_id is None: raise _not_found()
        ... resolve grant on book_id ...; return UUID(caller)
    return _dep

def require_version_grant(need):        # chapter_id + version path → book via chapter_translations
def require_chapter_grant(need):        # chapter_id (versions list) → book via chapter_translations (any row)
```
- Routes that take `book_id` in the path use `require_book_grant`. Routes keyed by `job_id`/`version_id`/`chapter_id` bootstrap `book_id` from the row (job→`translation_jobs.book_id`; version→`chapter_translations.book_id`; chapter→any `chapter_translations` row for that chapter), then resolve grant. A missing bootstrap row → 404 (anti-oracle, uniform with no-grant).
- **`_verify_book_owner` replaced** by `require_book_grant(edit)` for create-job/extract; the projection call is dropped (grant_client is the single authority). Internal dispatch's re-verify becomes a grant re-check on the asserted user_id.

### 4. Python `grant_client`
Copy-adapt E0-3's `app/clients/grant_client.py` into translation-service, swapping the config field names (`book_service_internal_url`, `internal_service_token`; timeout literal) and making `trace_id` optional (translation has no `logging_config.trace_id_var` guaranteed). **Deferred:** extract a shared `sdks/python/loreweave_grants/` after 4c so knowledge + translation + composition migrate off their local copies in one pass (`D-E0-4-PY-GRANT-SDK-EXTRACT`). 3 copies for a tracked window is acceptable; the SDK is 160 lines, stable (E0-3-proven).

### 5. Anti-oracle / errors
- no grant (`none`) → **404** (uniform with a missing book/job/version — no existence oracle, KSA §6.4).
- grantee under tier → **403**.
- book-service unreachable → grant `none` → 404 (fail-closed, grant_client contract).

### 6. Billing / attribution consequence (D-E0-4-B/C)
- A collaborator's translation job: `translation_jobs.owner_user_id = caller`; the worker resolves the model + bills via provider-registry under the **caller's** BYOK (the publish payload already carries `user_id = caller`). No quota charged to the book owner. The `active_chapter_translation_versions` row (the *published* translation) is per-(chapter, language) — shared, not user-keyed — so a collaborator publishing sets the book's active version (edit-gated, correct).
- Human-edit gold (`translation.corrected`) + publish signal (`translation.reviewed`) carry `user_id = caller` → learning attributes the signal to the actual editor.

### 7. Test plan
- **grant_client unit** (copy of E0-3's 10): parse/default-deny; cache positive-hit / none-never-cached / 45s expiry / fail-closed.
- **gate deny unit** (`test_grant_deps.py`): book-grant view/edit tiers (none→404, under→403, ≥→pass returns caller); job/version/chapter bootstrap → 404 on missing row; the bootstrap consults grant on the resolved book.
- **router deny** (the executable guard owner-run tests can't give): a view-grantee 403s on every write route (create/extract/save-edit/set-active/settings-put/cancel); a non-grantee 404s on every read route; an edit-grantee sees the OWNER's jobs/coverage (shared per-book view — D-E0-4-F).
- **existing-suite seam:** existing router tests run as the row owner; add a conftest autouse shim (mirror E0-3) that stubs `get_grant_client` → owner-level grant so the existing tests pass-through while the new deny tests exercise the real gate.
- **Live-smoke (≥2 services, → `D-E0-4A-LIVE-SMOKE`):** A grants B `edit` on a book → B creates a translation job (billed to B's BYOK, NOT A) → B sees A's existing coverage (shared view) → B publishes a version (active set) → view-grantee C 403s on create → revoke → B converges to 404 in ~45s. Token: `live smoke: translation grant-gated across book+translation`.

### 7b. REVIEW-design refinements (2026-06-11, self-review)
- **`effective_settings.py` — DO NOT touch (reverted after BYOK re-audit).** Initially I planned to drop the `owner_user_id` predicate for a "shared settings view." **That is wrong:** settings carry the user's `model_ref` (a BYOK `user_models` id). A collaborator must resolve **their own** model (per-user `WHERE owner_user_id=caller` → falls through to their `user_translation_preferences`), because the owner's `model_ref` won't resolve under the caller's user_id (provider-registry scopes by owner). So `effective_settings` stays per-user. **Settings reads/writes = per-user**, not shared-view. `book_translation_settings.book_id` is the PK (one row/book) so a collaborator's PUT would stomp the owner's row → keep settings writes **edit**-gated but track `D-E0-4A-SETTINGS-PERUSER` (composite PK so each collaborator keeps their own book-level config) as a follow-up; v1 a collaborator simply uses their user-prefs model (book-settings PUT by a collaborator is an edge case).
- **`_cancel_job_transition`** — the gated public cancel can't reuse `_cancel_job_core` (it owner-checks; a collaborator's `job.owner ≠ caller`). Add an authz-free transition helper (existence 404 / terminal 409 / UPDATE) called after `require_job_grant(edit)`. `_cancel_job_core` stays for the internal dispatch path (asserted-user check; 4b revisits).
- **`list_chapter_versions`** — takes only `chapter_id`; a chapter with zero translations can't bootstrap `book_id`. Gate when rows exist (bootstrap book → grant), return empty `[]` when none (preserves the owner's current empty-list behavior; leak-safe). Minor "chapter-has-translations" oracle → accept + document (chapter_id is an unguessable UUID; no content revealed).
- **`internal_dispatch`** — replace `_verify_book_owner` with a grant check (`require ≥edit` on the asserted `user_id`); forward-compatible with 4b (collaborator-asserted dispatch). For 4a the asserted user is always the owner → passes.
- **grant_client adapt** — translation config exposes `book_service_internal_url` + `internal_service_token` (no `book_client_timeout_s`/`book_service_url`); use a 10s literal timeout and make `trace_id` best-effort (translation has no guaranteed `logging_config.trace_id_var`).

### 8. Risks
- **R-IDOR** (primary): mitigated by the drop-owner transform keeping `book_id`/`job_id` scoping + the grant gate as the single chokepoint + router deny tests.
- **R-bootstrap-oracle**: job/version/chapter bootstraps return only `book_id` for the gate, never content; non-grantee → uniform 404.
- **R-internal-dispatch-asserted-user**: 4b will pass a collaborator's user_id to internal dispatch; the re-verify becomes a grant check (not owner check) — designed here, exercised in 4b.
- **R-billing-leak**: a collaborator's job must bill the caller, not the owner — verified in live-smoke (quota/usage row under B, not A).

---

## E0-4b — campaign-service adopt (NEXT, depends on 4a)
- `_owner_verified_chapters` → `require_book_grant(manage)` (create/start) per D-E0-4-D; campaign row `owner_user_id = caller`.
- **Two-resource check:** the knowledge project (`verify_project_owner`) — since campaign create needs the project, and E0-3 made the project book-owner-only, a collaborator won't own it. The campaign's knowledge dispatch runs as the **owner** (E0-3 resolve-to-owner, owner-paid — D-E0-4-E); its translation dispatch runs as the **caller** (4a grant-aware internal dispatch, caller-paid). Campaign resolves both: book-grant for the caller + the project's owner for the knowledge dispatch.
- Read routes (list/get/progress) → view; pause → edit; create/start/cancel/budget → manage.

## E0-4c — composition-service adopt (independent)
- `owns_book` (pack.py SEC2) + `get_book` (works.py) → grant-aware (view for read-pack, edit for prose-gen / create-work / patch-work).
- `WorksRepo` keyed by `user_id` → drop-owner / book-grant-scoped reads (shared per-book work view), caller-attributed writes.
- Prose/draft path forwards the caller's JWT → **already grant-honored by E0-2** (no change).
- Composition prose-gen bills the **caller's BYOK** (caller-pays, D-E0-4-C).
