# W4 — MCP tools (motif library) · DETAILED DESIGN

> **Workstream:** W4 of the narrative-motif-library parallel build.
> **Spec:** [`2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) — read **§13** (MCP catalog) + **§R2.8** (the corrected catalog: adopt→Tier-W, mine/import→202+poll+ledger, per-tool IDOR, user-scope, +`status`/`_conformance_run`). §13.1's tier table is **superseded** by R2.8 / audit H-6.
> **Master plan:** [`2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) §3 (F0 envelope/repo contract) + §4 **W4** def.
> **Ground truth read before writing:** `services/composition-service/app/mcp/server.py` (the full existing pattern), `services/composition-service/app/routers/actions.py` (confirm allowlist + `_execute_generate` — note: **no usage-billing precheck**), `sdks/python/loreweave_mcp/*` (kit), `services/knowledge-service/app/db/repositories/action_tokens.py` (the consumed-token ledger), `services/composition-service/app/worker/{events,job_consumer,constants,operations}.py` (the 202+poll enqueue rails), `services/glossary-service/internal/api/{book_tools,user_tools}.go` (the adopt-as-class-C precedent), `services/chat-service/app/client/billing_client.py` (the usage-billing client shape).

---

## 1. Scope + the envelope/guard contracts reused

### 1.1 What W4 owns (sole owner of all three files for this feature)
| File | Ownership | Adds |
|---|---|---|
| `services/composition-service/app/mcp/server.py` | **sole owner for the feature** (F0 froze the file; W4 owns the *motif additions*) | 10 motif tools + 1 poll tool + 4 confirm descriptors + 1 user-scope owner-resolver helper |
| `services/composition-service/app/routers/actions.py` | **sole owner** | 4 new confirm descriptors, their execute effects (202+poll enqueue, NOT in-process), the **consumed-token ledger** call, the **net-new usage-billing precheck** |
| `services/composition-service/tests/unit/test_motif_mcp.py` | **new file** | wire + handler-shape + IDOR + replay + tier-unconstructible tests |

W4 also **co-creates** (new, namespaced, no conflict with other WS):
- `services/composition-service/app/db/repositories/consumed_tokens.py` — the ledger repo (clone of knowledge-service's `ActionTokenRepo`).
- `services/composition-service/app/clients/billing_client.py` — the usage-billing client (clone of chat-service's, **+ a `precheck` method that does not exist anywhere yet**).
- `services/composition-service/app/db/migrate.py` gets a `consumed_tokens` table — **DELEGATED to F0** (F0 owns `migrate.py`; W4 supplies the DDL block to F0 during foundation, mirroring how W1 hands the `motif` DDL to F0). *Micro-decision MD-3 below.*

W4 **consumes** (read-only, frozen by F0 — never edits): `db/models.py` (`Motif`, `MotifApplication`, `MotifBeat`, `MotifRole`, `ArcTemplate`), `db/repositories/motif_repo.py` (`MotifRepo`: `get_visible`, `create`, `clone`, `list_for_caller`, `patch`, `archive`), `db/repositories/motif_retrieve.py` (`MotifRetriever.retrieve`), `db/repositories/motif_application.py` (the bind ledger — owned by **W2**; W4 calls its read/create/archive methods, does not define them), `config.py` (quota + embed knobs).

> **Disjointness note (master plan §1 rule):** `motif_application` writes for *bind* are the seam between W4 (the MCP `_bind` tool) and W2 (the planner's internal bind + the swap-archive lifecycle R2.6). **The repo method is owned by W2; W4 only calls it.** The `_bind` tool body lives in `server.py` (W4's file). The `archive_node`/`restore_node` reuse for swap-undo (R2.6) are **existing** `OutlineRepo` methods — W4 calls, never edits. No file is co-edited.

### 1.2 The envelope + guard contracts reused verbatim (no new kit — master plan F0.5)
Every motif tool reuses the **exact** existing composition MCP spine (`server.py` lines 1-128). Nothing here is novel machinery; it is the proven pattern applied to a new resource:

1. **Identity from the envelope ONLY** — `_ctx(ctx)` → `build_tool_context(ctx, settings.internal_service_token)`: constant-time `X-Internal-Token` check (SEC-1), then `X-User-Id` (+ optional `X-Project-Id`) lifted from headers into `ToolContext`. **Never a tool arg.**
2. **`ForbidExtra` on every arg model** (INV-2) — `extra="forbid"`. The LLM cannot smuggle `owner_user_id`/`user_id`/`visibility='public'` past the schema. All enums are **closed `Literal`s** so a bad value is a clean propose-time refusal, not a pydantic 500 in the confirm effect (the `_GenerateArgs` precedent, server.py:884-901).
3. **The scope guards (H15), fail-closed:**
   - `require_book_owner(_grant_resolver(), int(level))` via the existing `_gate(tc, book_id, level)` helper — VIEW (read) / EDIT (write) on the Work's `book_id`. This is the **book-bind** gate (for `_suggest_for_chapter`, `_bind`, `_arc_suggest`, `_conformance_run` — anything scoped to a project/book).
   - `require_user_scope(owner_of)` — **NEW for this feature**: motif/arc_template are **User-owned tier** (R1.1: no book_id). The user-tier tools (`_create`, `_get`, `_search`, `_adopt`) carry `_meta.scope='user'` and gate `motif.owner_user_id == caller` via a `_motif_owner_resolver`. *(§2 details which tool uses which guard, and why the read predicate makes `_get`/`_search` a hybrid.)*
4. **`uniform_not_accessible()` (H13)** — a denied caller and a missing/foreign row return the **same** `"not found or not accessible"` `ToolError`. No enumeration oracle: a foreign `motif_id` is indistinguishable from a non-existent one.
5. **Per-tool project-scope IDOR assertion** — the repeated guard from `node_update`/`node_delete`/`scene_link_delete` (server.py:421-424, 485-488, 602-605): the book gate proves the caller owns the *Work*, but a same-user caller could pass `project_id` from Work-A with a `motif_id`/`node_id` from their own Work-B, gating the **wrong** book. **Every by-id motif tool re-asserts the target belongs to the resolved scope before acting.** (§2 + §6 S1/S2.)
6. **Validated `_meta`** — `require_meta(tier, scope, synonyms=[…], tool_name=…)`: rejects a tool with no tier/scope at registration; `synonyms` feed `find_tools` recall (§4). Tier ∈ {R,A,W}; scope ∈ {book, user}.
7. **Tier-W confirm spine** — `mint_confirm_token(secret, user, resource_id, descriptor, payload)` on propose; the effect runs ONLY in `routers/actions.py` `POST /v1/composition/actions/confirm` after re-checking identity + ownership (the `composition_publish`/`composition_generate` precedent, server.py:828-976 + actions.py).

**Why no new kit:** the kit (`loreweave_mcp`) already exports every primitive W4 needs (`build_tool_context`, `ForbidExtra`, `require_book_owner`, `require_user_scope`, `uniform_not_accessible`, `require_meta`, `mint_confirm_token`/`verify_confirm_token`). Master plan F0.5 froze this explicitly: *"reuse the existing `make_stateless_fastmcp("composition")` + … — no new kit."*

---

## 2. Tool catalog — exact tiers (R2.8), args, guards, IDOR assertion, return shape

11 tools total: **4 R**, **2 A**, **4 W-confirm**, **1 R poll** (`composition_get_mine_job`, the clone of `composition_get_generation_job`). All names prefix-policed `composition_` (§4 federation). Tier source is **R2.8**, which supersedes §13.1's table (where adopt was mis-tabled Tier-A).

> **Guard legend:** `BOOK(level)` = `_gate(tc, work.book_id, level)` after `_work_or_deny`. `USER` = `require_user_scope(_motif_owner_resolver)` on `motif_id`. `READPRED` = the repo `get_visible(caller, id)` read predicate (R1.1: `owner IS NULL` system OR `visibility='public'` OR `owner = caller`) — this **is** the access check for cross-tier reads (a public motif you don't own is legitimately readable), so a read tool does NOT additionally `require_user_scope` (that would block reading public/system motifs). `IDOR` = the per-tool project/owner scope re-assertion.

### Tier R — reads (VIEW; no side effect)

#### R1 · `composition_motif_search`
- **Args** (`ForbidExtra`): `genre: str | None`, `kind: Literal['sequence','situation','hook','emotion_arc','trope','pattern','scheme'] | None`, `q: str | None`, `scope: Literal['mine','public','system','all'] = 'all'`, **`status: Literal['draft','active','archived'] | None = None`** (R2.8 — surfaces drafts; default None = active+draft owned, active-only for public/system), `language: str | None = None`, `limit: int = 20`.
- **Guard:** envelope identity only (`_ctx`). **No book gate** — motif is user/system-tier, not book-scoped. Access is enforced by the repo: `MotifRepo.list_for_caller(tc.user_id, scope=…, …)` applies the R1.1 read predicate in SQL (`READPRED`). `scope` is a *filter*, not a privilege escalation — `scope='system'` returns system rows (readable to all), `scope='mine'` returns only `owner=caller`; none of them can surface another user's private row.
- **IDOR:** structural — the read predicate is in the repo SELECT (master plan F0.3: `list_for_caller` filters by caller). A `scope='all'` cannot leak a private foreign motif because the predicate is `owner IS NULL OR visibility='public' OR owner = caller`.
- **Returns:** `{"motifs": [Motif.model_dump(mode="json") … ], "count": n}` — but **projected through the W1 catalog allow-list** when the row is not the caller's (never `embedding`, raw `source_ref`, or `examples[]` on a public/imported-derived row — audit B-3). *Micro-decision MD-1: search returns the allow-list projection uniformly to avoid a per-row branch; the owner's own full rows are fetched via `_get`.*

#### R2 · `composition_motif_get`
- **Args:** `motif_id: str`.
- **Guard:** `READPRED` — `motif = await repo.get_visible(tc.user_id, UUID(motif_id))`; `None` → `uniform_not_accessible()`. `get_visible` enforces R1.1 (system|public|owner), so a foreign **private** id is indistinguishable from a missing one (H13).
- **IDOR:** the `get_visible` predicate **is** the IDOR guard for a non-book resource (parallels `_work_or_deny`). No project assertion needed (motif has no project/book).
- **Returns:** full `Motif.model_dump(mode="json")` when `owner=caller`; the **allow-list projection** when system/public-not-owned (so an adopter previewing a public motif sees roles/beats/conditions but not `embedding`/raw `source_ref`/copied `examples[]`).

#### R3 · `composition_motif_suggest_for_chapter`
- **Args:** `project_id: str`, `node_id: str` (the chapter outline node), `limit: int = 5`.
- **Guard:** `BOOK(VIEW)` — this IS book-scoped (it ranks against a Work's chapter). `_work_or_deny(works, tc, pid)` → `_gate(tc, work.book_id, VIEW)`.
- **IDOR:** `node = await outline.get_node(tc.user_id, UUID(node_id)); if node is None or node.project_id != pid: raise uniform_not_accessible()` — the **exact** server.py:947-949 generate-target guard.
- **Returns:** `{"candidates": [{"motif": <allow-list projection>, "score": float, "match_reason": {tension, genre, precond, cosine}} …]}` via `MotifRetriever.retrieve(...)` (W3's frozen `retrieve()` — same core the planner pipeline uses; only the entry differs, §13.3). `match_reason` is the "why this motif" payload the FE binding UX needs (§13.5).

#### R4 · `composition_arc_suggest`
- **Args:** `project_id: str`, `premise: str | None = None`, `genre: str | None = None`, `limit: int = 5`.
- **Guard:** `BOOK(VIEW)` — scoped to the Work whose premise/genre seeds the rank. `_work_or_deny` + `_gate(VIEW)`.
- **IDOR:** none beyond the Work gate (no target id; it ranks the caller-visible arc_template set via the read predicate).
- **Returns:** `{"candidates": [{"arc_template": <allow-list projection>, "score": float, "match_reason": {...}} …]}`.

### Tier A — auto-write + Undo (EDIT; reversible; `_meta.undo_hint`)

#### A1 · `composition_motif_create`
- **Args** (`ForbidExtra`): **`target: Literal['user']`** (R2.8 — the `'book'` option is **removed** with the Book tier per R1.1; the closed enum makes a both-NULL / system-tier row **unconstructible** by the LLM), `code: str`, `name: str`, `language: str = 'en'`, `kind: Literal['sequence','situation','hook','emotion_arc','trope','pattern','scheme'] = 'sequence'`, `summary: str = ''`, `genre_tags: list[str] = []`, `roles: list[dict] = []`, `beats: list[dict] = []`, `preconditions: list[dict] = []`, `effects: list[dict] = []`, `tension_target: int | None = None`, `emotion_target: str | None = None`, `examples: list[dict] = []`, `visibility: Literal['private','unlisted'] = 'private'` (**`'public'` excluded from the create enum** — publishing is the separate W1 visibility-flip path, not a create-time arg).
- **Guard:** `USER` is **not** applicable on create (no existing resource to own). The invariant is **owner-stamping**: the handler calls `MotifRepo.create(tc.user_id, code=…, **fields)` which **server-stamps `owner_user_id = tc.user_id` unconditionally** (master plan F0.3) and the DB `CHECK (owner_user_id IS NOT NULL)` + the `motif_user_owned` CHECK reject any both-NULL write (audit B-2/S2). The envelope user is the owner; there is no arg that can override it.
- **IDOR:** N/A (create). The defense is "owner from envelope, never an arg" + the DB CHECK.
- **Returns:** `Motif.model_dump(mode="json")` + `_meta.undo_hint = _undo("composition_motif_archive"?, ...)`. **Micro-decision MD-2:** there is no `_motif_archive` *tool* in the R2.8 catalog (archive is the W1 HTTP `DELETE /motifs/{id}`). For a verified reverse op the undo hint must point at a tool the activity strip can call. Two options in §7; **recommendation:** add a tiny `composition_motif_archive` **Tier-A** tool (soft-archive, `status='archived'`, reversible via `patch status='active'`) so create/clone carry an honest `undo_hint`; otherwise emit `undo_hint: None` (honest, like `composition_create_work`, server.py:335). The recommended path adds A3 below.

#### A2 · `composition_motif_bind`
- **Args** (`ForbidExtra`): `project_id: str`, `node_id: str` (the chapter), `motif_id: str`, `role_bindings: dict[str, str] = {}` (`{role_key: glossary_entity_id}`), `derive_scenes: bool = True` (instantiate the motif's beats → scene nodes).
- **Guard:** `BOOK(EDIT)` — bind mutates a Work's outline. `_work_or_deny` + `_gate(EDIT)`.
- **IDOR (two assertions):**
  1. the chapter node is in the resolved Work's project: `node = await outline.get_node(tc.user_id, UUID(node_id)); if node is None or node.project_id != pid: raise uniform_not_accessible()` (server.py:947-949 pattern).
  2. the motif is caller-visible: `motif = await repo.get_visible(tc.user_id, UUID(motif_id)); if motif is None: raise uniform_not_accessible()` (you can only bind a motif you can see — R1.1).
- **Effect + undo (R2.6 — the load-bearing correction of MCP-R2):** binding writes a `motif_application` row (via W2's repo: `book_id=work.book_id`, `motif_version` pinned per edge-F3, `project_id`, `outline_node_id`, `role_bindings`). **Swap-after-prose archives, never deletes** the affected scene nodes + their generation_job links (reuse `OutlineRepo.archive_node`/`restore_node`, server.py:489/528). Because the prior state is **archived not destroyed**, the undo is a *verified reverse op*:
  - `_meta.undo_hint = _undo("composition_motif_bind", project_id, node_id, motif_id=<PRIOR motif>, role_bindings=<PRIOR bindings>)` when there was a prior binding (re-bind restores it + `restore_node`s the archived scenes);
  - on a **first** bind (no prior), `undo_hint = _undo("composition_motif_unbind", project_id, node_id, application_id)` — *requires* the tiny `composition_motif_unbind` Tier-A tool (archive the application + the derived scenes). **Micro-decision MD-2 (cont.):** R2.8 lists `_bind` but not `_unbind`; to *honor* the undo (the whole point of MCP-R2), W4 adds `composition_motif_unbind` (Tier-A) as the verified reverse op. §6 MCP-R2 is the failing-test that forces this.
- **Returns:** `{"application": <row>, "derived_scene_ids": [...], "_meta": {"undo_hint": …}}`.

#### A3 · `composition_motif_archive` + `composition_motif_unbind` *(the two reverse-op tools the undos point at — MD-2)*
- `composition_motif_archive(motif_id)` — **Tier-A**, `USER` guard (`require_user_scope` — you may only archive **your own** motif; a system/public-not-owned motif is read-only to you, the glossary system-kind-lock parity §11). Soft-archive (`MotifRepo.archive(tc.user_id, id)` flips `status='archived'`). `undo_hint = _undo("composition_motif_restore"?, …)` — or `None` if no restore tool (recommendation: archive is reversible via the W1 patch, so the FE can offer un-archive; the MCP undo emits `None` honestly, matching `canon_rule_delete` server.py:746). *This tool exists only so create/clone have an honest undo target; if the PO prefers `undo_hint: None` on create/clone, A3-archive can be dropped (§7 MD-2 option B).*
- `composition_motif_unbind(project_id, node_id, application_id)` — **Tier-A**, `BOOK(EDIT)` + IDOR (the application's `project_id == pid` AND `book_id == work.book_id`). Archives the `motif_application` + its derived scenes. The verified reverse op for a first-bind.

> **Net Tier-A count:** the R2.8 catalog names `_create`, `_bind`. To *honor* the Tier-A undo contract (master plan §7 H-4/MCP-R2), W4 adds `_unbind` (mandatory — without it a first-bind has no reverse op) and *optionally* `_archive` (MD-2). The wire-test `EXPECTED_TOOLS` set is updated to whichever set ships (§5).

### Tier W — cost/tenancy-gated, confirm-token (EDIT + confirm)

All four mint a confirm token on propose and run the effect **only** in `routers/actions.py`. **adopt** is Tier-W per R2.8 + audit H-6 (the glossary `glossary_adopt_standards` precedent: adopt is **class C / confirm-token**, returns a token + preview, confirmed via `glossary_confirm_action` — `services/glossary-service/internal/api/book_tools.go:21` *"adopt … = class C (confirm-token)"*). §13.1's "adopt = Tier-A" is the bug R1.6 corrects.

#### W1 · `composition_motif_adopt`
- **Args** (`ForbidExtra`): `motif_id: str`, **`target: Literal['user']`** (R1.1 — clone-down to the caller's user tier only; the Book-tier target is gone), `retag_genres: list[str] | None = None` (the cross-genre clone-and-retag, R2.2).
- **Guard (propose):** `READPRED` — `repo.get_visible(tc.user_id, UUID(motif_id))`; `None` → `uniform_not_accessible()`. You may adopt only a motif you can see (public/system/own).
- **IDOR:** the `get_visible` predicate. (Adopt has no project/book dimension after R1.1 — *this kills the audit IDOR-1 book dimension*, R1.1.)
- **Why Tier-W not Tier-A:** adopt is **tenancy-bearing + quota-bearing** (per-user `motif_max_adopt` ceiling, R1.3) and copies a vector + content across the tenancy boundary — it is the cross-tier mutation the platform wants a human confirm on, exactly like the glossary class-C adopt. It carries **no LLM spend** (so its confirm card shows a tenancy preview, not a $ estimate) but the **consumed-token ledger** still applies (no replay double-adopt past the quota) and the **quota precheck** runs in the effect.
- **Propose returns** (mirrors `composition_publish`, server.py:876): `{confirm_token, descriptor: "composition.motif_adopt", title: "Adopt motif into your library", domain: "composition", preview: {source_name, will_clone: bool, retag_to: […]}}`.
- **Confirm effect (`_execute_motif_adopt`):** re-check identity + `get_visible` + **quota** (count caller's adopted motifs < `motif_max_adopt`) → `MotifRepo.clone(envelope_user, src_motif_id, target_owner=envelope_user, retag_genres=…)` (the **one** clone primitive, F0.3/R1.1.1; resets id/owner/timestamps/version, copies the platform-model vector so cosine stays correct, strips `examples[]` if the source is imported-derived per B-3). Idempotent (`ON CONFLICT (owner,code,language) DO NOTHING`). **Ledger-claimed first** (§3). Returns `{outcome: "action_done", descriptor, motif_id: <clone id>}`.

#### W2 · `composition_motif_mine`
- **Args** (`ForbidExtra`): `scope: Literal['book','corpus']`, `book_id: str | None = None` (required iff `scope='book'`), `min_support: int = 2`, `promote_to: Literal['draft'] = 'draft'` (mined motifs always land `status='draft'`; the enum forbids auto-active), `language: str = 'en'`.
- **Guard (propose):** `BOOK(EDIT)` when `scope='book'` (`_gate(tc, UUID(book_id), EDIT)`); for `scope='corpus'` the gate is **user-scope** (the caller's own corpus — `require_user_scope` is N/A here since there's no single resource id, so the gate is simply "envelope identity + the worker filters `user_id=caller`"). *Micro-decision MD-4: corpus mining is gated by the envelope user only (the worker reads only the caller's books); a per-book grant re-check happens inside the worker per book touched.*
- **IDOR:** for `scope='book'`, the `BOOK(EDIT)` gate. For `corpus`, the worker filters every read on `user_id = envelope_user`.
- **Why Tier-W:** **LLM spend** (the abstraction step) → confirm card shows a **$ estimate** + the **real usage-billing precheck** (§3). Mining runs as a **202+poll worker job** (R2.8 — NOT in-process like `_execute_generate`).
- **Propose returns:** `{confirm_token, descriptor: "composition.motif_mine", title: "Mine motifs from <book|corpus>", domain: "composition", requires: "human confirmation — this spends LLM tokens", estimate: {…}}`.
- **Confirm effect (`_execute_motif_mine`):** ledger-claim → **usage-billing precheck** (deny → 402-style `action_error` with a `reason: "quota_exhausted"`) → **enqueue** a `mine_motifs` worker job (NOT run in-process): `GenerationJobsRepo.create(envelope_user, project_id?, operation='mine_motifs', input={worker_op:'mine_motifs', scope, book_id, min_support, language, …}, status='pending')` then `enqueue_job(redis_url, job_id, user_id, project_id)`. Returns **202-style** `{outcome: "action_accepted", descriptor, job_id, poll: "composition_get_mine_job"}`. The worker op `mine_motifs` is added to `SUPPORTED_OPERATIONS` + dispatched in `job_consumer._run_operation` — **but those files are owned by W8 (mining)**; W4 ships the *enqueue + poll tool + ledger + precheck*, and the W8 worker op is the **Wave-2** consumer. *Until W8 lands, the job sits `pending` and the poll returns `pending` — the contract is the enqueue, not the compute (master plan §2: W4 exposes the agentic surface; mining compute is W8/P3).*

#### W3 · `composition_arc_import_analyze`
- **Args** (`ForbidExtra`): `import_source_id: str`, `use_web: bool = False`, `arc_hint: str | None = None`.
- **Guard (propose):** `USER` on the `import_source` row — `import_source` is **per-user/per-book, structurally un-shareable** (no visibility column, §12.6/B-3). `require_user_scope(_import_source_owner_resolver)` → `import_source.owner_user_id == caller`; foreign → `uniform_not_accessible()`.
- **IDOR:** the user-scope owner check on `import_source_id`.
- **Why Tier-W:** **LLM spend** (the deconstruct) → confirm + $ estimate + precheck + 202+poll, identical contract to `_mine`.
- **Confirm effect (`_execute_arc_import`):** ledger-claim → precheck → enqueue `analyze_reference` worker job → 202 + `job_id` + `poll: "composition_get_mine_job"`. (Worker op owned by **W9 import**; W4 owns the enqueue/poll/ledger/precheck seam.)

#### W4 · `composition_conformance_run`
- **Args** (`ForbidExtra`): `project_id: str`, `scope: Literal['chapter','arc']`, `chapter_id: str | None = None` (required iff `scope='chapter'`).
- **Guard (propose):** `BOOK(EDIT)` (`_work_or_deny` + `_gate(EDIT)` — arc-scope conformance re-extracts, an LLM spend).
- **IDOR:** for `scope='chapter'`, assert the chapter node ∈ project (`outline.get_node` + `project_id == pid`).
- **Why Tier-W:** the arc extract-diff is a **cost-gated job** (§14.5 — *"arc scope is a cost-gated job → Tier-W MCP `composition_conformance_run`, confirm-token like mine/generate"*). Same 202+poll + precheck contract. *(Chapter-scope conformance is the cheaper coarse read — MD-5: chapter-scope MAY return inline like a Tier-R read, but to keep ONE contract W4 routes both through confirm+poll; the chapter job is just cheaper. Recommendation: confirm+poll for both, uniform.)*
- **Confirm effect (`_execute_conformance_run`):** ledger-claim → precheck → enqueue a `conformance_run` job → 202 + poll. (Compute owned by **W5 conformance**; W4 owns the enqueue/poll/ledger/precheck.)

### R-poll · `composition_get_mine_job` (clone of `composition_get_generation_job`)
- **Args:** `project_id: str`, `job_id: str`.
- **Guard:** `BOOK(VIEW)` — `_work_or_deny` + `_gate(VIEW)`, **exact** clone of `composition_get_generation_job` (server.py:269-286).
- **IDOR:** `job = await jobs.get(tc.user_id, UUID(job_id)); if job is None or job.project_id != pid: raise uniform_not_accessible()` — the same cross-Work guard (server.py:284). The repo already filters `user_id`.
- **Returns:** `job.model_dump(mode="json")` — status/result/cost for the mine/import/conformance jobs. **One poll tool serves all three W-async ops** (they all write `generation_job` rows); `_meta.synonyms` cover "mining job / import job / conformance job". *Micro-decision MD-6: reuse `composition_get_generation_job` instead? No — its synonyms/description are cowrite-specific and would confuse `find_tools` recall for mining; a thin dedicated `_get_mine_job` with mining synonyms is cleaner. It is a 15-line clone.*

---

## 3. The W-tier async contract — 202+poll, consumed-token ledger, real usage-billing precheck

This is the **net-new** machinery vs `_execute_generate` (which runs in-process, has **no** ledger, and has **no** usage-billing precheck — actions.py:205-308). Three pieces, all in `routers/actions.py` + two co-created files.

### 3.1 202+poll worker enqueue (NOT in-process)
R2.8 + master plan §4 W4: mine/import/conformance **enqueue a worker job**, unlike `_execute_generate` which calls `engine_router.generate(...)` in-process. The rails already exist (`worker/events.py:enqueue_job`, `worker/job_consumer.py`, `GenerationJobsRepo.create`). The confirm effect:

```
async def _execute_motif_mine(payload, project_id, work, envelope_user, *, jobs, ledger, billing):
    # 1. CONSUME the token FIRST (consume-first / fail-closed — knowledge ActionTokenRepo)
    if not await ledger.consume(jti=_jti(claims), descriptor=claims.descriptor, exp=_exp_dt(claims)):
        raise HTTPException(409, {"code": "action_error", "reason": "already_consumed"})  # replay
    # 2. REAL usage-billing precheck (NET-NEW — _execute_generate has none)
    ok = await billing.precheck(owner_user_id=str(envelope_user), purpose="motif_mine", estimate=_estimate(payload))
    if not ok:
        raise HTTPException(402, {"code": "action_error", "reason": "quota_exhausted"})
    # 3. ENQUEUE a worker job (NOT in-process) → 202 + poll handle
    job, _ = await jobs.create(envelope_user, project_id, operation="mine_motifs",
                               input={"worker_op": "mine_motifs", **mine_spec}, status="pending")
    await enqueue_job(settings.redis_url, job_id=str(job.id), user_id=str(envelope_user), project_id=str(project_id))
    return {"outcome": "action_accepted", "descriptor": claims.descriptor, "job_id": str(job.id),
            "poll": "composition_get_mine_job"}
```

**Ordering rationale (consume-first, audit-aligned):** claim the jti **before** the effect (knowledge-service `ActionTokenRepo.consume` doc: *"the caller claims BEFORE running the effect; once claimed, a later failed effect does NOT release the jti — a spent token never re-applies, the human re-proposes"*). For an **enqueue** the effect is cheap + idempotent (the job row + the stream XADD); claiming first means a network blip during enqueue can't be exploited to double-enqueue by replaying the token. If the enqueue itself fails after the claim, the job row still persists (`enqueue_job` is best-effort, the sweeper re-drives) — so no work is lost and the token is correctly spent.

### 3.2 Consumed-token ledger (no replay double-spend)
The confirm-token kit is **stateless / not single-use** (`confirm_token.py` docstring: *"Single-use is NOT in the token … a consuming service that needs one-shot semantics records the (u, r, d, exp) in its own consumed-token ledger at confirm time"*). The existing `_execute_publish`/`_execute_generate` are **idempotent-by-effect** (publish is a no-op if already canon; generate is gated by the chapter in-flight guard) so they tolerate replay. **The W-motif actions are NOT idempotent** (a replayed adopt past the quota, a replayed mine = double LLM spend) → they need the ledger.

- **New file:** `services/composition-service/app/db/repositories/consumed_tokens.py` — a verbatim clone of `knowledge-service/app/db/repositories/action_tokens.py` (`ActionTokenRepo.consume(jti, descriptor, exp) -> bool`, `INSERT … ON CONFLICT (jti) DO NOTHING`, returns `True` only on the first claim).
- **New table** (DDL handed to F0 for `migrate.py`, MD-3): `consumed_tokens(jti TEXT PRIMARY KEY, descriptor TEXT NOT NULL, exp TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ NOT NULL DEFAULT now())`. Not tenant-scoped (the jti is server-minted + globally unique; identity is checked at the confirm endpoint *before* the claim — same as knowledge-service).
- **The `jti` source:** the C-KIT confirm token's claim shape is `{u, r, d, p, exp}` — there is **no `jti`** field (unlike the richer Go glossary scheme). **Micro-decision MD-7 (load-bearing):** synthesize a deterministic jti from the immutable claim bytes so a replay of the *same* token collides: `jti = sha256(f"{u}|{r}|{d}|{exp}|{canonical(p)}")` — i.e. the token's identity. Two distinct proposes (different `exp`/payload) get distinct jtis; a replay of one token gets the same jti → `ON CONFLICT` rejects it. *(Recommendation: hash the raw `payload_b64.sig` token string itself — it is already the unique, signed identity of the proposal; simplest + collision-free. Use `jti = sha256(token)`.)*

### 3.3 Real usage-billing precheck (net-new — does NOT exist in `_execute_generate`)
`_execute_generate` spends LLM tokens with **zero** pre-spend quota check (actions.py:205-308 — confirmed: no billing call). R1.3 mandates *"a real usage-billing pre-check in the mine/import confirm effect — it is net-new."*

- **New file:** `services/composition-service/app/clients/billing_client.py` — modeled on `chat-service/app/client/billing_client.py` (internal-token-gated httpx client → `usage-billing-service:8086`), **plus a `precheck` method that exists nowhere yet**:
  ```
  async def precheck(self, *, owner_user_id, purpose, estimate) -> bool:
      # POST /internal/model-billing/precheck {owner_user_id, purpose, estimate_usd}
      # → {allowed: bool}. Fail-OPEN or fail-CLOSED? See MD-8.
  ```
- **Config:** add `usage_billing_service_url` + reuse `internal_service_token` (already present) to `config.py` — *delegated to F0* (F0 owns `config.py`; W4 supplies the keys, like the quota knobs in F0.4).
- **Micro-decision MD-8 (fail-open vs fail-closed):** the billing service being down should **not** silently let unbounded spend through, but also should not hard-block all mining on a billing outage. **Recommendation: fail-CLOSED for the precheck** (a billing outage denies the *new spend* with a clear `reason: "billing_unavailable"` — the human retries) because the whole point of the precheck is to gate spend; this matches the kit's fail-closed guard philosophy. (Contrast: post-hoc `log_usage` is best-effort fail-open, as in chat-service — losing a usage *record* is recoverable; permitting unbounded *spend* is not.)
- **The estimate:** `_estimate(payload)` is a coarse token estimate (corpus size × per-book abstraction cost for mine; chapter count × extract cost for import/conformance). It does not need to be exact — it gates the **obvious** over-quota case + drives the confirm card's $ display (§13.2: *"the confirm step shows the $ estimate"*).

### 3.4 The confirm route wiring (actions.py)
Extend the existing `confirm_action` allowlist (actions.py:139) + descriptor dispatch (actions.py:159-161):
```
_MOTIF_ADOPT_DESCRIPTOR     = "composition.motif_adopt"
_MOTIF_MINE_DESCRIPTOR      = "composition.motif_mine"
_ARC_IMPORT_DESCRIPTOR      = "composition.arc_import"
_CONFORMANCE_RUN_DESCRIPTOR = "composition.conformance_run"
# allowlist (line 139): add the 4 above to the (_PUBLISH, _GENERATE, …) tuple
# dispatch (line 159): elif claims.descriptor == _MOTIF_ADOPT_DESCRIPTOR: return await _execute_motif_adopt(...)
#                       elif ... mine / arc_import / conformance_run
```
The **identity + ownership re-check** (actions.py:125-157) is shared by every descriptor (already generic: verify token → `envelope_user == claims.user_id` → `works.get` → `authorize_book(EDIT)`), so the new descriptors inherit it. **adopt** does NOT have a Work/book (R1.1) → it **skips** the `works.get`/`authorize_book` block and instead re-checks `get_visible` in `_execute_motif_adopt` (the adopt confirm path branches before the Work re-resolve — *micro-decision MD-9: gate the Work re-resolve on `descriptor in {publish, generate, mine(book), conformance}` and let adopt/import use their own user-scope re-check*).

The C-CONFIRM domain map gains the 4 descriptors (§13.5: *"extend the C-CONFIRM domain map alongside `composition.publish`/`composition.generate`"*).

---

## 4. find_tools synonyms + prefix-policed federation

### 4.1 Synonyms (seed `find_tools` recall — §13.4)
`find_tools` (chat-service `tool_discovery.py`) fuzzy-searches name + description + **`_meta.synonyms`** (stdlib token-overlap + difflib). Each motif tool's `synonyms` MUST cover the multilingual + craft vocabulary so an assistant surfaces them on *intent*, not exact name. Per-tool synonym lists (the spec calls out `motif/trope/pattern/套路/爽点/打脸/beat/arc`):

| Tool | `synonyms` |
|---|---|
| `composition_motif_search` | `["motif","trope","pattern","plot beat","cliché","套路","爽点","打脸","find motif","browse motifs","narrative device"]` |
| `composition_motif_get` | `["motif detail","trope detail","get motif","show pattern","motif roles","motif beats"]` |
| `composition_motif_suggest_for_chapter` | `["suggest motif","which motif","motif for this chapter","why this motif","recommend trope","fit a pattern","plot beat for scene"]` |
| `composition_arc_suggest` | `["suggest arc","arc template","story arc","multi-chapter structure","arc for premise","arc structure"]` |
| `composition_motif_create` | `["create motif","new trope","author a motif","define pattern","add motif to my library","make a beat"]` |
| `composition_motif_bind` | `["bind motif","apply motif","use this trope","attach pattern to chapter","swap motif","set chapter motif"]` |
| `composition_motif_unbind` | `["unbind motif","remove motif","clear chapter motif","detach pattern"]` |
| `composition_motif_archive` | `["archive motif","delete motif","retire trope","remove from library"]` |
| `composition_motif_adopt` | `["adopt motif","clone motif","copy trope to my library","import public motif","reuse a pattern","clone and retag"]` |
| `composition_motif_mine` | `["mine motifs","extract patterns","discover tropes","find motifs in my books","analyze my corpus","套路 mining"]` |
| `composition_arc_import_analyze` | `["import arc","deconstruct","analyze a work","拆文","reverse-engineer arc","extract arc template","analyze reference"]` |
| `composition_conformance_run` | `["check conformance","did the AI follow the arc","verify against plan","arc conformance","beat realized","drift check"]` |
| `composition_get_mine_job` | `["mining job","import job","conformance job","poll mining","is mining done","motif job status"]` |

These are **structural** (drive recall), validated by `require_meta` (`synonyms` must be a list of strings — `meta.py:72`). The CJK terms matter: the platform is multilingual (R1.1.3) and a Chinese-language assistant turn must surface the tools.

### 4.2 Prefix-policed federation
ai-gateway federates the composition MCP server and **routes by tool-name prefix** (`tool_discovery.py:_provider_prefix` → `name.split("_", 1)[0]` → `"composition"`). Every motif tool is named `composition_*` → it federates **for free** wherever the agent runs (chat, glossary-assistant, the composition studio assistant) — the "domain owns tools, gateway federates" rule (§13/§13.4). No gateway change is needed *for routing* beyond confirming the `composition` prefix is federated (it already is — the existing 17 composition tools route this way).

- **Provider-availability (H10):** when composition is briefly down, `provider_availability` reports the `composition` prefix unavailable → `find_tools` tells the user "the capability exists, try again" rather than "I can't" (`tool_discovery.py:240`). The motif tools inherit this — no new code.
- **`_meta` is consumer-side only:** `strip_tool_meta` drops `_meta` before the def goes to the LLM (`tool_discovery.py:125`) — the LLM sees a plain OpenAI function def, the tier/scope/synonyms stay server-side. So adding synonyms costs **nothing** in LLM context.
- **Tier drives confirm UX downstream:** the consumer reads `_meta.tier` (`tool_tier`) — a `W` tool's result (`confirm_token` + descriptor) routes to the FE `confirm_action` card; an `A` tool's `_meta.undo_hint` routes to the activity strip. W4 sets the tiers correctly; the consumer wiring already exists.

---

## 5. Tests (`tests/unit/test_motif_mcp.py`) + eval-gate

Mirrors the existing two-layer shape (`test_mcp_server.py` wire + handler; `test_mcp_actions.py` confirm-route).

### 5.1 Wire path (loopback uvicorn, real streamable-HTTP) — reuse the `mcp_base_url` fixture
- `test_motif_tools_in_catalog` — `tools/list` includes the motif set; assert `EXPECTED_TOOLS` is extended with the 11 (or 13 incl. `_unbind`/`_archive`) motif tools. (Updates the existing `EXPECTED_TOOLS`/`TIER_R`/`TIER_W` constants — *W4 edits the test file it owns; the existing constants live there.*)
- `test_motif_tools_meta_valid` — each motif tool's `_meta`: tier ∈ {R,A,W}, scope ∈ {book, user}, non-empty `synonyms`. **Extends** the existing `test_every_tool_carries_valid_meta` to allow `scope == 'user'` (the existing test hardcodes `scope == 'book'`, server.py is all-book; W4's user-scope tools require relaxing that assertion to `scope in {'book','user'}` — **the one existing-test edit W4 makes, in its own file? NO** — `test_every_tool_carries_valid_meta` is in `test_mcp_server.py`, **not** W4's file). **Micro-decision MD-10 (disjointness):** W4 owns `test_motif_mcp.py` only; `test_mcp_server.py` is the pre-existing composition-MCP test. The `scope=='book'` assertion there will **fail** once user-scope motif tools register on the same server. → W4 must edit `test_mcp_server.py`'s assertion. **This makes `test_mcp_server.py` a W4-touched file** — declare it in the WS ownership (it is a test of the file W4 sole-owns, so this is consistent, not a cross-WS edit). Recommendation: relax to `scope in {'book','user'}` + keep the per-tool tier checks.
- `test_no_motif_tool_leaks_scope_arg` — extends the forbidden-arg set check (`{user_id, owner_user_id, …}`) over the motif `$defs` (the `ForbidExtra` arg models). Asserts `owner_user_id`/`visibility='public'`/`user_id` are never schema properties.
- Auth rejections (missing/wrong internal token, bad user-id) — covered by the existing wire tests for any tool; add one motif-tool smoke (`composition_motif_search`) to confirm the motif tools sit behind the same envelope gate.

### 5.2 Handler shape + scope (direct calls, stubbed repos + grant) — reuse the `_patched` ctx-monkeypatch + `_Ctx`
- `test_search_applies_read_predicate` — `MotifRepo.list_for_caller` stub returns mixed rows; assert the handler returns them via the allow-list projection (no `embedding` key leaks).
- `test_get_owner_full_vs_public_projection` — owner sees full row; public-not-owned sees allow-list projection.
- `test_get_foreign_private_uniform` — `get_visible` returns `None` for a foreign private id → `NotAccessibleError` (H13). **(S1 IDOR test.)**
- `test_suggest_foreign_node_uniform` — node with `project_id != pid` → `NotAccessibleError`. **(S1 IDOR per-tool.)**
- `test_create_stamps_owner_from_envelope` — `MotifRepo.create` is awaited with `tc.user_id` as owner; no arg can override.
- `test_create_target_enum_rejects_book_and_system` — pydantic rejects `target='book'` / `target='system'` (closed `Literal['user']`) → the both-NULL/system row is **unconstructible**. **(S2 tier-unconstructible test.)**
- `test_bind_records_application_and_undo` — bind writes a `motif_application` (stub) + returns `_meta.undo_hint` pointing at `composition_motif_unbind` (first bind) or `composition_motif_bind` with prior values (re-bind). **(MCP-R2.)**
- `test_bind_swap_archives_not_deletes` — re-bind over a chapter with prior scenes calls `archive_node` (NOT a delete) → the undo's `restore_node` is a verified reverse op. **(MCP-R2 / H-4.)**
- `test_adopt_propose_mints_token` — propose returns `confirm_token` + `descriptor == "composition.motif_adopt"` + tenancy preview; no clone happens at propose.
- `test_mine_propose_mints_token_with_estimate` — propose returns a token + a $ estimate; no enqueue at propose.

### 5.3 Confirm-route (FastAPI TestClient + `dependency_overrides`) — reuse `test_mcp_actions.py`'s client fixture shape
- `test_adopt_confirm_clones` — mint adopt token → confirm → `MotifRepo.clone` awaited with `target_owner=envelope_user`; returns `action_done` + new motif id.
- `test_mine_confirm_enqueues_202` — confirm → `GenerationJobsRepo.create(operation='mine_motifs', status='pending')` + `enqueue_job` awaited; returns `action_accepted` + `job_id` (NOT in-process compute). **(MCP-R4 async.)**
- `test_w_replay_blocked_by_ledger` — confirm the SAME token twice → first `action_done`/`action_accepted`, second → 409 `already_consumed` (the ledger `consume` returns `False`). **(W-replay eval-gate — the headline.)**
- `test_mine_precheck_denies_over_quota` — billing `precheck` stub returns `False` → confirm → 402 `quota_exhausted`; **no** job enqueued (precheck runs *before* enqueue). **(MCP-R4 real billing.)**
- `test_billing_unavailable_fails_closed` — `precheck` raises → fail-closed deny `billing_unavailable` (MD-8).
- `test_adopt_token_other_user_rejected` — token minted for USER, confirmed with `X-User-Id: OTHER` → 400 `action_error` (the existing anti-impersonation re-check, actions.py:135).
- `test_import_user_scope_foreign_rejected` — propose `_arc_import_analyze` for an `import_source_id` owned by another user → `NotAccessibleError` (user-scope guard). **(S1 IDOR for the un-shareable import resource.)**
- `test_get_mine_job_foreign_project_uniform` — poll a `job_id` under a different project → `NotAccessibleError` (the cloned cross-Work guard).

### 5.4 Eval-gate (master plan §4 W4)
The WS passes when: **IDOR** (foreign motif_id / node / import_source / job → `uniform_not_accessible`) ✔; **Tier-W replay blocked by the ledger** ✔; **`_create` cannot construct a both-NULL row** (the `Literal['user']` + the DB CHECK) ✔; **user-scope guard runs for user-tier tools** (`_get`/`_search`/`_create`/`_adopt`/`_archive`/`_import`) ✔. Plus the master-plan §7 risk-guard tests below.

---

## 6. Audit risk-guards as failing-tests (master plan §7)

Each is a **failing test first**, then the code that makes it pass.

| ID | Risk (audit) | Failing test | Code that satisfies it |
|---|---|---|---|
| **H-6 / MCP-R1** | adopt was mis-tiered Tier-A (auto-write a cross-tenant clone with no confirm) | `test_adopt_is_tier_W` — `composition_motif_adopt`'s `_meta.tier == 'W'`; the propose returns a `confirm_token` (no clone at propose) | adopt registered Tier-W; effect only in `_execute_motif_adopt` (§2 W1) |
| **MCP-R2** | bind's Tier-A undo was unhonored (swap deleted scenes → no reverse op) | `test_bind_swap_archives_not_deletes` + `test_bind_undo_restores` — swap calls `archive_node`; undo hint → `composition_motif_unbind`/re-bind restores | R2.6 archive-not-delete + the `_unbind` reverse-op tool (§2 A2/A3) |
| **MCP-R4** | mine ran in-process with no billing | `test_mine_confirm_enqueues_202` + `test_mine_precheck_denies_over_quota` | 202+poll enqueue + real `billing.precheck` before enqueue (§3) |
| **S1** | IDOR per-tool (foreign id under the wrong scope) | `test_get_foreign_private_uniform`, `test_suggest_foreign_node_uniform`, `test_import_user_scope_foreign_rejected`, `test_get_mine_job_foreign_project_uniform` | per-tool `get_visible` / `project_id == pid` / `require_user_scope` re-assertions (§1.2.5, §2) |
| **S2** | a tier was constructible the LLM shouldn't reach (both-NULL / system / public-at-create) | `test_create_target_enum_rejects_book_and_system`, `test_create_visibility_excludes_public` | closed `Literal['user']` target + `Literal['private','unlisted']` visibility + owner-stamp + DB CHECK (§2 A1) |
| **B-2 (echo)** | both-NULL write | `test_create_stamps_owner_from_envelope` | `MotifRepo.create` stamps `owner=tc.user_id`; F0's DB CHECK is the backstop |
| **B-4 (echo)** | no quota / no precheck on adopt+mine | `test_adopt_quota_rejects`, `test_mine_precheck_denies_over_quota` | quota count in `_execute_motif_adopt`; `billing.precheck` in mine/import/conformance |
| **W-replay** | confirm-token double-spend | `test_w_replay_blocked_by_ledger` | `consumed_tokens.consume` claim-first (§3.2) |

---

## 7. Open micro-decisions + recommendation

| ID | Decision | Recommendation |
|---|---|---|
| **MD-1** | `_search` projection — per-row (full for owned, allow-list for others) vs uniform allow-list? | **Uniform allow-list** in search; owner reads full via `_get`. Avoids a per-row branch + a leak risk; the FE list view doesn't need `embedding`/`examples`. |
| **MD-2** | Tier-A undo target — add `_archive`/`_unbind` tools, or emit `undo_hint: None`? | **Add `_unbind` (mandatory — first-bind has no other reverse op)** + **`_archive` (recommended)** so create/clone/bind carry *honest verified* undos (the whole point of Tier-A). If the PO wants the minimal catalog, drop `_archive` and emit `undo_hint: None` on create/clone (honest, matches `composition_create_work`). `_unbind` is non-negotiable for MCP-R2. |
| **MD-3** | `consumed_tokens` DDL — who owns it? | **F0 owns `migrate.py`**; W4 supplies the DDL block during foundation (mirrors W1 handing the motif DDL). Keeps the disjointness rule (one owner per file). |
| **MD-4** | corpus-mining gate (no single book id) | Envelope identity + the worker filters every read on `user_id = caller` + a per-book `EDIT` re-check inside the worker for each book touched. (A corpus is "all the caller's books"; there is no one resource to `require_book_owner` on.) |
| **MD-5** | chapter-scope conformance — inline (Tier-R) vs confirm+poll (Tier-W)? | **Confirm+poll for both** chapter and arc, ONE contract. The chapter job is just cheaper; uniformity beats a second code path. (§14.5 already routes arc through Tier-W.) |
| **MD-6** | poll tool — reuse `composition_get_generation_job` or a new `_get_mine_job`? | **New thin `composition_get_mine_job`** (15-line clone) with mining/import/conformance synonyms — cleaner `find_tools` recall; the existing job tool's synonyms are cowrite-specific. |
| **MD-7** | the `jti` for the ledger (the C-KIT token has no `jti` claim) | **`jti = sha256(token_string)`** — the signed token IS the unique proposal identity; a replay reuses the exact string → same hash → `ON CONFLICT` rejects. Simplest + collision-free. |
| **MD-8** | precheck fail-open vs fail-closed on a billing outage | **Fail-CLOSED** for the *precheck* (deny new spend with `billing_unavailable`; the human retries) — gating spend is the whole purpose. Contrast post-hoc `log_usage` = best-effort fail-open. |
| **MD-9** | confirm route — adopt/import skip the Work re-resolve | Gate the shared `works.get`/`authorize_book(EDIT)` block on `descriptor in {publish, generate, motif_mine(book), conformance}`; adopt + import re-check their own user-scope owner inside their effect (they have no Work/book — R1.1 / §12.6). |
| **MD-10** | `test_mcp_server.py`'s `scope == 'book'` assertion breaks when user-scope motif tools register | **Relax to `scope in {'book','user'}`** in `test_mcp_server.py` (a test of the file W4 sole-owns → consistent with W4 ownership, not a cross-WS edit). Declare `test_mcp_server.py` as W4-touched. |
| **MD-11** | mine/import/conformance worker *compute* is owned by W8/W9/W5 (Wave 2) | W4 ships the **enqueue + poll + ledger + precheck seam** in Wave 1; the worker ops (`mine_motifs`/`analyze_reference`/`conformance_run`) land with their WS. Until then the job sits `pending`, the poll returns `pending` — the **contract is the enqueue**, not the compute (master plan §2). A contract test asserts the enqueue + the `input.worker_op` stamp; an integration smoke is deferred to the Wave-2 R-NODE. Track: **`D-W4-MINE-WORKER-LIVE-SMOKE`** (live-smoke the enqueue→compute→poll once W8/W9/W5 land). |

---

## 8. Task list

**Wave-1 (P1), against frozen F0 contracts:**

1. **T1 — arg models + tier table (`server.py`).** Define the 11+2 `ForbidExtra` arg models with closed `Literal` enums (target/kind/visibility/scope/status). Add the 4 confirm descriptor constants. *(No behavior yet — schemas first, so `find_tools`/wire tests can assert them.)*
2. **T2 — `_motif_owner_resolver` + `_import_source_owner_resolver` (`server.py`).** The `require_user_scope` owner-of helpers (return `motif.owner_user_id` / `import_source.owner_user_id`; raise → uniform deny). Wire `require_user_scope` into the user-tier tools.
3. **T3 — Tier R tools (`server.py`):** `_search` (+`status`, allow-list projection), `_get` (owner-full vs allow-list), `_suggest_for_chapter` (BOOK(VIEW) + node IDOR + `retrieve()`), `_arc_suggest`. Consumes W3's `retrieve()` (mock until W3 lands).
4. **T4 — Tier A tools (`server.py`):** `_create` (owner-stamp, `Literal['user']`), `_bind` (BOOK(EDIT) + dual IDOR + `motif_application` write via W2's repo + R2.6 archive-not-delete undo), `_unbind` (the verified reverse op), `_archive` (MD-2, recommended).
5. **T5 — Tier W propose tools (`server.py`):** `_adopt` (READPRED + mint `composition.motif_adopt` token + tenancy preview), `_mine` (BOOK/USER gate + mint + $ estimate), `_arc_import_analyze` (USER on import_source + mint), `_conformance_run` (BOOK(EDIT) + mint). All mirror `composition_publish`'s propose shape.
6. **T6 — poll tool (`server.py`):** `composition_get_mine_job` — clone `composition_get_generation_job` with mining synonyms + the cross-Work IDOR guard.
7. **T7 — consumed-token ledger (`db/repositories/consumed_tokens.py` new).** Clone `ActionTokenRepo`; supply the `consumed_tokens` DDL to F0 (MD-3).
8. **T8 — billing client + precheck (`clients/billing_client.py` new).** Clone chat-service's client; **add the net-new `precheck` method** (fail-closed, MD-8). Supply `usage_billing_service_url` to F0's `config.py`.
9. **T9 — confirm effects (`routers/actions.py`).** Add the 4 descriptors to the allowlist + dispatch; implement `_execute_motif_adopt` (ledger→quota→clone), `_execute_motif_mine` / `_execute_arc_import` / `_execute_conformance_run` (ledger→precheck→enqueue→202+poll). Gate the shared Work re-resolve per MD-9.
10. **T10 — tests (`tests/unit/test_motif_mcp.py` new) + the one `test_mcp_server.py` assertion relax (MD-10).** All of §5 + §6. Each risk-guard is written failing first.
11. **T11 — VERIFY.** `pytest tests/unit/test_motif_mcp.py` green; wire-path `tools/list` shows the catalog; the §6 table all green. Cross-service tokens: this WS touches **2+ services conceptually** (composition MCP + the eventual usage-billing precheck + the W8/W9/W5 worker ops) → evidence string carries `LIVE-SMOKE deferred to D-W4-MINE-WORKER-LIVE-SMOKE` (the compute lands in Wave 2; the Wave-1 contract is the enqueue + ledger + precheck, unit+contract tested). The adopt path (no worker) **can** live-smoke end-to-end once W1's `clone()` lands → fold into R-NODE-P1.

**Hand-offs / dependencies:**
- **F0 must freeze:** `MotifRepo.{get_visible, create, clone, list_for_caller, archive}`, `MotifRetriever.retrieve`, the `Motif`/`MotifApplication` models, the `consumed_tokens` DDL + `usage_billing_service_url`/quota config. W4 mocks `retrieve()` + the `motif_application` repo until W3/W2 land.
- **W2 owns** `motif_application` repo methods (`create`/`get_for_node`/`archive`) + the swap-archive lifecycle — W4 **calls** them, never defines them.
- **W8/W9/W5 own** the worker compute ops — W4 owns the enqueue/poll/ledger/precheck seam (Wave-1), they own the compute (Wave-2). The `D-W4-MINE-WORKER-LIVE-SMOKE` deferral tracks the join.
