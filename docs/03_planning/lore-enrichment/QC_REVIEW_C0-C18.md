# Lore-Enrichment — Human-in-loop QC Review of the RAID run (C0–C18)

> Started 2026-05-31 · Branch `lore-enrichment/foundation` · HEAD `8b864487` · Reviewer: human-in-loop (default v2.2)
> Method (per PO): risk-weighted · `/review-impl` adversarial on load-bearing cycles · **live stack-health = full demo re-run**.
> Status (2026-05-31): **NEAR-FINAL** — Step 1 ✅, Step 2 high-risk (C2/C11/C12/C13/C15/C16/C17 + C14) ✅, Step 2 low-risk tier (C0,1,3,6,7,8,9,10,18) ✅ light pass (C5 only outstanding), Step 3 live audit ✅ (F-C2-1/F-C1617-1 cleared, F-C13-2 confirmed, F-LIVE-1 recurs), Step 4 defer-triage ✅, Step 5 go/no-go ✅. **Remaining:** C5 deep review + live capstone (knowledge rebuild → F-C13-1 retract e2e). Verdict: **CONDITIONAL GO** — 1 HIGH + 3 MED to fix (+044/046 cheap do-now); core invariants sound. See Step 5 (bottom).

---

## Step 1 — Live stack-health (DONE)

Stack: the full `infra-*` compose was already up and healthy (postgres/redis/neo4j/glossary/knowledge/book/provider-registry/lore-enrichment all `healthy`). LM Studio reachable on `:1234` with `qwen/qwen3.6-35b-a3b` (chat) + `text-embedding-bge-m3` (embed) loaded; both registered in `provider_registry` for the demo user.

### ✅ Verified live
- **Readiness/liveness (C18):** `lore-enrichment` `/health`=200 and `/ready`=200 from inside the container (port 8093 → host 8221).
- **C4 glossary→KG event pipeline:** consumer group on `loreweave:events:glossary` has **pending 0, lag 0** — not wedged (the prior incident class is clear).
- **P1 generation + H0 quarantine (real Qwen, end-to-end):** ran `tests/live_smoke_c14_job.py` against the live stack for 蓬萊:
  - resolved gen + embed model_refs **by name** via provider-registry BYOK (no hardcoded names) ✓
  - ingested a 山海经 grounding chunk via **real bge-m3 embed** ✓
  - **real Qwen 3.6 generated 5 source-faithful Chinese dimensions**; honest-sparse where the corpus didn't cover (`历史`/`文化` → "检索片段未载…"), `features` quotes the 山海经 anchor「宫室皆以金玉為之，鸟兽尽白」 ✓
  - **H0 held:** persisted proposal `origin=enrichment`, `confidence=0.30 (<1.0)`, `review_status=proposed`, `pending_validation`, 4 grounding refs. Confirmed in DB. ✓
- **P1 promote→canon (real Qwen, end-to-end) — after rebuilding the stale knowledge image (F-LIVE-1):** quarantined proposal → approve → **author promote → enriched-writeback → canon** (glossary entity created, 5 facts promoted) **with permanent origin marker retained** (`origin=enrichment`, `original_technique=retrieval`, `promoted_by`=demo user); 4 lifecycle events, 0 failures. Smoke EXIT 0; DB shows the `promoted` row with markers. ✓ — **H0 invariant live-verified both directions.**

### 🔴 Findings from the live run

> **Process note (review honesty):** the first promote re-run failed on `glossary-service:8087` — that was a **typo in my smoke-harness env** (`GLOSSARY_SERVICE_URL_H=…:8087`), NOT a product bug. The service's real config is correct: live env **and** `infra/docker-compose.yml:577` both have `GLOSSARY_SERVICE_URL=http://glossary-service:8088`. Discarded. Recording it only so the next session doesn't re-chase it.

**F-LIVE-1 (HIGH, stack-health — NOT a code bug) — RESOLVED in-session by rebuild. The running `knowledge-service` image was STALE; the C13 H0 write-back route was missing in-cluster (404).**

> **✅ RESOLVED 2026-05-31:** rebuilt + recreated `knowledge-service`; confirmed `/app/app/routers/internal_enrichment.py` now present + service healthy. Re-ran the C14 promote smoke → **LIVE-SMOKE PASS (EXIT 0)**: real Qwen P1 gen → quarantined H0 proposal → review → author promote → **enriched-writeback → promote→canon** (glossary entity `019e78d4-…`, `facts_promoted=5`) **WITH permanent origin marker intact**; 4 events, 0 failures. **DB ground-truth:** a `promoted` row with `origin=enrichment, conf=0.30 (<1.0), original_technique=retrieval, promoted_by set, promoted_entity_id set`. → **H0 promote→canon path now live-verified end-to-end.** Original-finding detail kept below for the record. **(Net: a deploy/CI gap, not a code defect — see DEFERRED candidate for a stale-image guard.)**

With the harness port fixed, the promote got past the owner check and through `glossary` and then failed at:
```
WritebackError: POST http://knowledge-service:8092/internal/knowledge/enriched-writeback failed (404)
```
The route **exists in source** (`services/knowledge-service/app/routers/internal_enrichment.py` — `enriched-writeback`/`enriched-promote`/`enriched-retract`) and is registered in `app/main.py:27,529`. But the **running container does not have the file** (`ls /app/app/routers/internal_enrichment.py` → No such file). Image built **2026-05-30 15:49Z**; the C13 commit `6daa89fd` landed **2026-05-30 18:22** (+07) — i.e. the deployed image **predates C13**. → The H0 promotion write-back into the KG is unverifiable on the current stack because the container is stale.
**This is exactly the stale-image false-green class from last session** (glossary image was 13d stale, `5e902190`) and the core of ContextHub lesson `e16b6f02`. The *code* looks correct; the *deployed artifact* is behind.
**Fix:** `docker compose build knowledge-service && docker compose up -d knowledge-service`, then re-run the C14 promote smoke → confirm enriched-writeback (quarantined) → promote→canon → origin marker, live. Until then, promote→canon is **NOT** live-verified this session (DB still shows `proposed=1, promoted=0`).

**F-LIVE-2 (MED, real code bug) — circular import on the `app.clients.writeback` entry path. ✅ RESOLVED 2026-05-31 (commit pending).**

Importing `app.clients.writeback` first raised:
```
ImportError: cannot import name 'CanonVerifier' from partially initialized module 'app.verify.canon_verify' (circular import)
chain: clients.writeback → verify → generation → retrieval → strategies → strategies.fabrication → verify.canon_verify
```
The running service avoids it because `app.main`'s import order initializes the modules in a working sequence — so production startup is fine — but any entry point that imports `writeback` first (incl. the committed verification scripts) crashes.

> **⚠️ The original prescribed fix ("lazy-import `CanonVerifier` in `strategies/fabrication.py`") was both INCOMPLETE and MISLOCATED.** Empirically peeling the cycle (patch → re-import → next edge) showed it is NOT a single fabrication→canon_verify edge. The true root cause is in **`verify/`**, not `strategies/`: `app/generation/__init__.py`, `app/retrieval/__init__.py`, and `app/strategies/__init__.py` each **eagerly import their heavy submodules**, so importing any *leaf* type (`generation.provenance.EnrichedFact`, `retrieval.strategy.GroundedProposal`) drags the entire generation→retrieval→strategies tree — which imports back into the still-initializing `verify` module. `canon_verify` AND `wiring` both import those two leaf types **for annotations only**, and both are loaded by `verify/__init__` before the strategies tree exists. Fixing only fabrication just moved the failure to `fabrication→wiring→canon_verify`, then `wiring→generation.provenance`. Fixing `strategies/*` would have been whack-a-mole (fabrication, recook, and any future strategy importing verify).

**Fix applied (2 files, `verify/` only — `strategies/` left untouched, honoring the locked "no edits to verify/ logic" boundary since this is import hygiene, not logic):** guard the two **annotation-only** descent-triggering imports under `if TYPE_CHECKING:` in **`app/verify/canon_verify.py`** (`EnrichedFact`, `GroundedProposal`) and **`app/verify/wiring.py`** (`EnrichedFact`, `GroundedProposal`). `FlagKind`/`CanonVerifier`/`VerifyResult` stay eager (`FlagKind` is used at runtime in `wiring._derive_status`). Both modules already have `from __future__ import annotations` (PEP 563), so the annotations were never evaluated at runtime → **provably behaviour-neutral**.

**VERIFY (live, in `infra-lore-enrichment-service-1`, files hot-copied for the test):**
- before: `python -c "import app.clients.writeback"` → ImportError (repro at `fabrication.py:71`) ✓ reproduced
- after:  `import app.clients.writeback` → **`WRITEBACK IMPORT OK`** ✓
- `import app.main` → **`APP.MAIN IMPORT OK`** (production path unaffected) ✓
- `from app.verify.wiring import verify_and_annotate, AnnotatedVerify, VerifyStatus; from app.strategies.fabrication import FabricationStrategy; from app.strategies.recook import ReCookStrategy; from app.verify.canon_verify import CanonVerifier, FlagKind, VerifyResult` → **`ALL SYMBOLS OK`** (no broken annotation/pydantic eval — class definitions succeed) ✓
- Full pytest suite NOT run: the prod image ships no pytest/test deps (this is F-LIVE-3 itself); change is annotation-only so unit deltas are nil. *Run `tests/unit/verify` + `tests/unit/strategies` in a dev/test image at COMMIT time for belt-and-suspenders.*
- ⚠️ The container has the patched files **hot-copied** (live, for verification). A `docker compose build lore-enrichment-service && up -d` is needed to bake them in — low urgency since behaviour-neutral and the running process already started via the working `app.main` order.

**Follow-up (defer candidate):** the underlying smell — eager package `__init__` imports making leaf-type imports drag whole subtrees — is a latent cycle for OTHER entry orders too. A cleaner structural fix (thin out `generation/__init__`, `retrieval/__init__`, `strategies/__init__` so importing a leaf doesn't pull the tree) is larger than this QC warrants → propose a new DEFERRED row in Step 4.

**F-LIVE-3 (LOW/process) — verification scripts are not shipped in the image + not runnable as-is.**
`tests/` is not COPYed into the Docker image (only `app/`), and the smokes hardcode **host-port** env defaults (5555/6399/8208/8216/8211/8205). Combined with F-LIVE-2, the "documented" demo is not reproducible in-cluster without (a) copying the script in and (b) pre-importing `app.main`. Consider a committed, in-cluster-aware demo entrypoint (or ship `tests/` + a runner that uses service-name URLs) so the demo is reproducible by the next session.

### ℹ️ Observations (to confirm in Step 2 code review)
- **DB state:** `loreweave_lore_enrichment` has **2 proposals (both `proposed`/`approved`), 0 promoted, 3 corpus chunks** (each smoke run adds a fresh 蓬萊 proposal — itself a NIT: the smoke isn't idempotent on re-run, it creates a new job+proposal each time). The prior demo's "4 locations promoted to canon" is **not** persisted in the current stack — now explained by F-LIVE-1 (stale knowledge image blocks the write-back), corroborating SESSION_HANDOFF concern #3.
- **`LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1` is set directly on lore-enrichment.** Confirm generation/embedding actually route through provider-registry (provider-gateway invariant) and that this var isn't a direct-SDK bypass. (Generation in the smoke did go through provider-registry `/internal/llm` by model_ref; verify nothing else uses the direct LM Studio URL.)

---

## Step 2 — Code review (risk-weighted) — IN PROGRESS

### C13 (review gate + H0 write-back/promote/retract) — `/review-impl` adversarial — DONE 2026-05-31
Commits `62b84bfe` (impl) + `6daa89fd` (prior-adversary fixes). Files read end-to-end: `knowledge-service/app/routers/internal_enrichment.py`, `lore-enrichment/app/services/{review,writeback}.py`, `app/clients/writeback.py`, `app/api/{proposals,principal}.py`, `tests/test_review_gate.py`, `scripts/raid/verify-cycle-13.sh`.

**✅ What holds (verified, not assumed):**
- **H0 happy-path order is correct.** `promote()` (writeback.py:293) does authz-vs-book-owner (315) → `approved` check (359) → `write_back` quarantine (365) → `mark_promoted` with its OWN `approved` re-gate (379 → review.py:330) → **only then** KG flip to canon (389). No path reaches `source_type='glossary'`/conf=1.0 without owner+approved. `set_status` refuses `PROMOTED` (review.py:259); `mark_promoted` is the sole canon transition.
- **Prior-adversary fixes are REAL:** FIX-1 anchor never uses makeup `content[:32]` (writeback.py:97-115, faithful `target_ref`/`canonical_name`/synthetic id only); FIX-2 minted anchor born sub-canon (internal_enrichment.py:157,213; ON-MATCH leaves pre-existing canon untouched 192-194); FIX-3 `writeback_entity_id` persisted for orphan-retract (review.py:348).
- Q3 scoping on every repo read/write; authz from book-service projection truth, never client claim (writeback.py:109-123, 315-319).
- Injection-neutralized at every boundary (`_safe`, clients/writeback.py:74-79).

**🔴 F-C13-1 (HIGH — confirmed false-green; "built-but-not-wired") — the glossary recycle-bin leg of RETRACT is unreachable in production.**
`WritebackService.retract` only recycles the glossary entity when a user JWT is present (`writeback.py:476` — `if recycle_target is not None and jwt:`), via the **user-scoped** `DELETE /v1/glossary/.../entities/{id}` requiring `Authorization: Bearer {jwt}` (clients/writeback.py:237-263). But:
1. the retract API handler **never passes `jwt`** (`proposals.py:338-344` → `jwt=""` default);
2. `Principal` exposes **only `user_id`**, no token field (principal.py:38) — the bearer credential is decoded then discarded, so the handler *cannot* forward it even if it tried;
3. so the recycle path is structurally dead via the API — `glossary_recycled` is always `false`.

**Impact:** retracting a **promoted** proposal soft-retracts the KG facts (`valid_until`) but leaves the **glossary canon entity live** — its `short_description` is the promoted makeup content (set at promote, writeback.py:417) — and via C4 `glossary_sync` the Neo4j canon anchor stays too. The author's "undo" silently half-works; the API returns `200 {glossary_recycled:false}`. Contradicts brief Scope-IN (recycle-bin retraction) + acceptance token "→ retract → recycle-bin".

**Why it was a false-green (the masking):**
- the unit test `test_retract_routes_to_recycle_bin_and_soft_retracts_kg` (test_review_gate.py:553-569) calls `service.retract(..., jwt="jwt-token")` **directly**, hand-passing a jwt the real handler never has → asserts `glossary_recycled is True`. Handler-bypass.
- the live-smoke `verify-cycle-13.sh` exercises only `/internal/knowledge/enriched-retract` (KG `valid_until`, line 198-201) and **relabels** the brief's required smoke token `→ retract → recycle-bin` down to `→ retract → soft (valid_until)` (line 208) — quietly dropping the glossary leg.
- the prior C13 independent-adversary (6daa89fd) missed it for the same reason (tested at the service layer with a passed jwt).

**Fix (when cleared):** thread the bearer token end-to-end — add a `token: str | None` to `Principal` (principal.py) + forward `jwt=principal.token` from the retract handler; OR (consistent with promote) give the glossary recycle an **internal-token** route so retract doesn't depend on a user JWT at all (preferred — promote already canonizes via internal token; retract should be able to un-canonize the same way). Then add an **API-level** retract test (TestClient, real handler) + restore the brief's `→ retract → recycle-bin` live-smoke assertion.

**🟠 F-C13-2 (MED — verify in Step 3, cross-cycle assumption) — minted KG anchor Entity is never canonized by promote.**
`enriched-promote` flips only `:Fact` nodes + `:RELATES_TO` edges to canon (internal_enrichment.py:310-331); the `:Entity` **anchor** born sub-canon on ON-CREATE is NOT touched. The design relies on glossary→KG `glossary_sync` (C4) to canonize the anchor ON-MATCH. **Unverified:** that the C4 consumer's merge key matches internal_enrichment's `{user_id, glossary_entity_id}` (internal_enrichment.py:176). If keys diverge → either the anchor stays `pending_validation=true` forever, or a duplicate canon Entity is created. → Live-check in Step 3 (query Neo4j for the promoted anchor's `source_type`/`pending_validation` after a real promote).

**🟡 F-C13-3 (LOW) — promote partial-failure window.** `mark_promoted` (Postgres) commits before the KG flip (writeback.py:379 vs 389); a crash between leaves row=`promoted` but KG facts quarantined. Self-heals on idempotent re-promote (334-357); fail-SAFE direction (under-canonizes, never an H0 leak). Accept + document.

**🟡 F-C13-4 (LOW) — retract leaves the minted anchor Entity node in KG** (only facts/edges get `valid_until`, internal_enrichment.py:367-377). A never-promoted retracted anchor lingers as an orphan — but marked `pending_validation`, so not an H0 leak. Cleanliness.

**⚪ F-C13-5 (COSMETIC/test-quality) — retract tests drive the service, not the API.** All `test_retract_*` (test_review_gate.py:553,688,710) call `WritebackService.retract` directly with a fabricated jwt; none exercises the FastAPI handler, which is exactly where F-C13-1 lives. Add a `TestClient` retract test.

**ℹ️ Minor:** `promoted_at` is a client-supplied string on the internal promote endpoint (internal_enrichment.py:91) — audit metadata behind the internal token, low risk. Promote/retract use global `MATCH ()-[r:RELATES_TO]->()` then filter (internal_enrichment.py:322,373) — correctness fine, perf at scale (LOW).

---

### C16 (fabrication P2, gate-enforced) + C17 (re-cook P3, licensing) — `/review-impl` adversarial — DONE 2026-05-31
Commits C16 `02b95e5c`+`b331796b` (gate-on-runner fix, 054) ; C17 `228b1811`+`fb7ee726` (licensing fail-closed, WARN1/2). Files read: `app/strategies/{factory,fabrication,recook,licensing}.py`, `app/jobs/assembly.py`, `app/api/jobs.py`, `app/eval/gate.py` (`gated_feature_flags`), `app/db/migrate.py` (source_corpus license).

**✅ The two load-bearing controls are GENUINELY WIRED on the production path (prior false-greens really fixed) — verified, not assumed:**
- **C16 eval-gate is on the runner path (054 real).** `JobRunner(` is constructed in exactly ONE place (assembly.py:227, inside `build_live_runner`); `build_live_runner` has exactly ONE caller (api/jobs.py:163, the execution path); the runner's strategy comes from `factory.select(technique)` (assembly.py:176). `gated_feature_flags` (gate.py:132-136) forces every non-P1 technique OFF when `not decision.passed`, applied AFTER base_overrides → no `overrides={FABRICATION:True}` escape hatch. Gate read fails CLOSED on any error (factory.py:165-170; `LiveGateStatus.locked` default). A locked-gate fabrication job is handled cleanly: marked `failed` (auditable) + `409`, no 500/leak (jobs.py:174-186). The C14 "inert cost-cap" is also fixed here — the fabrication/recook cost_strategy is the strategy's own higher per-gap estimate (assembly.py:187-201), so the cap binds.
- **C17 licensing is default-deny end-to-end.** Schema: `source_corpus.license NOT NULL DEFAULT 'unknown'` (migrate.py:66) + idempotent `ALTER COLUMN ... SET DEFAULT 'unknown'` for already-deployed tables (116) + vocabulary CHECK (100-104) — fail-closed at ingest (the prior 'public-domain' admit-by-omission default is gone). Policy module is allow-by-presence (`{PUBLIC_DOMAIN, LICENSED}` only; None/blank/garbage → UNKNOWN → refused, licensing.py:142-160). recook enforces at corpus-admission (recook.py:335) AND fact-emit (352) and treats an unresolvable `None` lookup as `UNKNOWN`→refused (recook.py:390-396) — the assembly `_license_lookup` returns None for unknown corpora (assembly.py:158), so this edge matters and is handled. Fabrication + recook both refuse empty-grounding (free invention) — fabrication.py:322, recook.py:322.

**🟠 F-C1617-1 (MED — verify in Step 3, residual-state risk; same class as F-LIVE-1) — already-deployed source_corpus rows may retain the old admit-by-omission default.**
The licensing fail-closed migration sets the column DEFAULT to 'unknown' but **does NOT rewrite existing rows** (migrate.py:114-115, by design). On a DB whose `source_corpus` table was created BEFORE `fb7ee726`, any corpus row that was INSERTED un-tagged under the old `DEFAULT 'public-domain'` still carries `public-domain` → admissible → re-cookable. The comment assumes existing PD rows were *explicitly* tagged, but a row defaulted before the fix is indistinguishable now. → Step 3 live-check: `SELECT license, count(*) FROM source_corpus GROUP BY license` on the live DB; confirm every `public-domain` row was explicitly tagged (genuinely PD), not silently defaulted.

**🟡 F-C1617-2 (LOW/COSMETIC) — "license checked before any retrieval" claim drifts from code.** licensing.py:26 + recook docstring say corpus-admission licensing happens "before any retrieval / generation," but `_recook` runs `self._retrieval.run(...)` (recook.py:303) BEFORE the license check (335). No leak (no fact emitted, no re-cook output), but an embed query is spent on a possibly-unlicensed corpus and the doc claim is inaccurate. Accept + fix the claim, or move the admission check ahead of retrieval.

**Net C16/C17:** controls are real. This is the healthy contrast to C13's retract (F-C13-1) — same "is it on the production path?" question, opposite answer.

---

### C2 (data model + H0 DB CHECKs + promote trigger) — `/review-impl` adversarial — DONE 2026-05-31
File: `app/db/migrate.py` (enrichment_proposal + `enrichment_proposal_h0_guard` trigger).

**✅ Structural H0 backstop is REAL (the layer below the app gate):**
- `confidence NUMERIC(4,3) NOT NULL CHECK (confidence > 0 AND confidence < 1.0)` (migrate.py:275) — a proposal row **cannot** carry canon confidence (1.0), enforced on INSERT and UPDATE.
- `origin NOT NULL DEFAULT 'enrichment' CHECK (origin <> '' AND origin <> 'glossary')` (270) — a proposal's origin can never be the canon origin.
- lifecycle vocab CHECK (283) + `UNIQUE(job_id, gap_ref)` idempotent-resume (258).
- `enrichment_proposal_h0_guard` trigger (340-398): origin immutable (344), confidence<1.0 (350), legal transition DAG matching review.py (356-368), promote-only marker invariant — `promoted` requires `promoted_entity_id/by/at` ELSE forbids them (371-393), auto-stamps permanent origin markers at promote (379-384). So C13's `mark_promoted` reliance on "the DB rejects a promoted row without markers" is genuinely backed.

**🟡 F-C2-1 (LOW/defense-in-depth) — the H0 guard trigger is `BEFORE UPDATE` only (migrate.py:402), not `BEFORE INSERT`.** A direct `INSERT ... review_status='promoted'` would bypass rules 3 (DAG) + 4 (promote-only invariant) — those fire only on UPDATE. **Mitigated:** the INSERT-time CHECKs still force `confidence<1.0` + `origin<>'glossary'` (row stays structurally non-canon), the app always inserts `'proposed'`, and canon is written via the app `promote()` path — never derived from `proposal.review_status`. So not an exploitable leak (requires direct DB write, outside the threat model). Consider `BEFORE INSERT OR UPDATE` for completeness. → Step 3: confirm `trg_enrichment_proposal_h0` is actually INSTALLED on the live DB (a trigger in migrate.py ≠ a trigger on the running DB — stale-migration class).

---

### C12 (canon-verify: contradiction / anachronism / injection) — `/review-impl` adversarial — DONE 2026-05-31
File: `app/verify/canon_verify.py` + the production wiring in `app/jobs/assembly.py` (`_canon_lookup`).

**✅ Prior false-greens REALLY fixed (verified):**
- **Contradiction fail-open closed:** `passed = not flags and not verify_degraded` (canon_verify.py:156-159); a down/empty graph → `verify_degraded=True`, no pass (384-387); crucially a canon-lookup **exception** sets `verify_degraded=True` rather than returning `()` silently (436-440) — "couldn't check" is distinct from "no canon known," so a swallowed error can't yield `verified_clean`.
- **Anachronism zero-width bypass closed:** `_check_anachronism` scans `_prenormalize(content)` (strip ZW/bidi + NFKC, 353) so `火‍车` (ZWJ-smuggled) can't evade the denylist; marker list is conservative (no bare `电`, avoids 雷电 false-positive).
- **Injection** runs FIRST + multi-field (name, every grounding excerpt, every dimension label + content), neutralizes + flags HIGH (290-339).

**🟠 F-C12-1 (MED — latent false-green; "built-but-not-wired" on the contradiction check) — the contradiction check is effectively INERT in production, and its degraded-signal is mis-sourced.**
The production canon source is the injected `_canon_lookup`, which assembly.py wires to a **hardcoded `return []`** (assembly.py:124-129). Meanwhile `verify_degraded` is gated on **graph-stats reachability** (`_read_stats`/`is_empty`, canon_verify.py:383-387) — a DIFFERENT seam. So when the KG has any entities (it does — synced/quarantined nodes), `is_empty=False` → NOT degraded, yet every per-dimension `_canon_lookup` returns `[]` → no contradiction can ever fire → the proposal is reported **`verified_clean`** without any real canon comparison having happened. For the *current* demo this is honest (the sparse LOCATIONs genuinely have ~no authored canon to contradict — that's the whole reason enrichment exists), so it isn't producing wrong results today. But it's a latent false-green: the moment real authored canon exists while `_canon_lookup` stays stubbed/partial, contradictions pass silently as clean, and the `verify_degraded` guard won't catch it because degradation is tied to graph-stats, not to the canon source. **Fix:** tie `verify_degraded` to the canon-lookup seam's availability (a stub/failed canon source must degrade), and wire `_canon_lookup` to real glossary canon before relying on contradiction detection. → Note in Step 5 as the contradiction check's real maturity (P1 demo = effectively injection+anachronism only; contradiction is structurally present but unfed).

**🟡 F-C12-2 (LOW, documented) — contradiction heuristic catches only negation-style contradictions.** `_contradicted_term` (442-462) fires only when a canon term AND a negation marker (不是/并非/… or is-not/never/…) co-occur. A semantic contradiction without a negation word (canon: 玉虛宮=元始天尊居所; generated: 玉虛宮=通天教主居所) passes. Self-documented as "consistency, not correctness." Accept.

**🟡 F-C12-3 (LOW) — anachronism substring match can false-positive** on an era-appropriate name containing a marker char sequence (advisory only — never auto-rejects, so low impact). Accept.

---

### C11 (schema-gov generation + H0 mint chokepoint) — `/review-impl` adversarial — DONE 2026-05-31
File: `app/generation/provenance.py` (`make_enriched_fact` / `EnrichedFact`).

**✅ The strongest H0 guard in the codebase — airtight by construction, over-built (good):**
- Every distinguishing field is REQUIRED + validated: `origin` ∈ {enriched, enriched:<x>}, rejects glossary/blank (146-154, `H0OriginError`); `confidence: gt=0, lt=1.0` (140); non-empty `provenance` (156) + `source_refs` (166); `pending_validation must be True` (176); `review_status must be 'proposed'` (186). A canon-looking fact cannot be constructed.
- **Both pydantic validation-skip bypasses are closed** — `model_construct` is overridden to RAISE (196-210), and `model_copy(update=...)` round-trips through the validated constructor (212-225). This is the sophisticated part: the two ways to skip pydantic validators are both blocked, so H0 is "impossible to forget, not merely documented."
- `model_config = frozen=True` → no post-construction mutation.

**ℹ️ Deferred (not bugs):** the prior C11 WARNs (flat `GENERATION_CONFIDENCE=0.30` regardless of grounding quality; CJK fidelity) → DEFERRED 045/046/047. Confirm these are genuinely "refinement, not correctness" in Step 4 triage. No new findings — this cycle is clean.

---

### C15 (eval-gate scoring / judge-ensemble) — `/review-impl` adversarial — DONE 2026-05-31
Files: `app/eval/{gate,runner}.py`, `app/strategies/gate_reader.py`, `app/db/repositories/eval_runs.py`, `app/config.py`.

**✅ The gate VERDICT is earned + fail-closed end-to-end (verified):**
- **`passed` is the result of `gate_decision`, not self-reported.** runner.py computes `decision = gate_decision(provisional, suite, baseline_diff)` (142) and persists `passed=decision.passed` (153). `gate_decision` re-checks composite vs `min_composite` rather than trusting the scorecard's own field (gate.py:78-80) — a forged scorecard can't smuggle a pass.
- **A no-live-judge run CANNOT pass (no fixture false-green).** With no judges wired, `usefulness=0, judge_ensemble_acceptable=False` (runner.py:109) → `gate_decision` adds a blocking reason (gate.py:90-94) → `passed=False`. So P2/P3 unlock *requires* ≥2 real judges voting — structurally.
- **Critical floors can't be averaged away:** `GATE_CRITICAL_FLOORS` provenance≥90 / anachronism≥75 block independently of a high composite (gate.py:50-53,96-99).
- **Freshness bound (055) is ACTIVE, not inert:** `gate_max_age_seconds` defaults to **7 days** (config.py:31-34); gate_reader treats a passing run older than that as LOCKED (gate_reader.py:72-83). A stale pass against a since-changed corpus cannot keep P2/P3 open.
- **Fail-closed reader:** no run / cross-user / read error → LOCKED (gate_reader.py:65-67 + factory.read_gate wrapper).

**🟡 F-C15-1 (LOW, tracked = DEFERRED 056/057) — ensemble requires ≥2 judges VOTING but not ≥2 DISTINCT judge models, and κ is informational not a hard gate.** If a caller wires the *same* model as two judges, `judge_ensemble_acceptable` can be True with no real independence (Fleiss-κ agreement would be meaningless). Acknowledged + deferred (056 κ-informational, 057 diversity). Acceptable for the demo; confirm the deferrals are still the right call in Step 4 and that the demo's passing run used genuinely distinct judges.

---

## Step 2 — Self-review tier (lower-risk cycles) — PENDING
C0,C1,C3,C4,C5,C6,C7,C8,C9,C10,C14,C18 — Lead self-review (not full `/review-impl`). C14 (job orchestration/runner — cost-cap + resume) and C4/C5 (event pipeline + wiki) carry the most residual risk in this tier.

## Step 3 — Cross-cutting control audit — LIVE RESULTS 2026-05-31 (stack brought back up)
Brought the data backends up (`docker start infra-postgres-1 infra-neo4j-1 infra-redis-1` — all healthy). Ran the verify-live queries (no full app-stack / LM Studio needed for these).

**✅ F-C2-1 CLEARED (live):** `SELECT tgname,tgenabled FROM pg_trigger WHERE tgrelid='enrichment_proposal'::regclass` → `trg_enrichment_proposal_h0 | O` — the H0 structural trigger IS installed + enabled on the running DB. (The `BEFORE UPDATE`-only code observation stands as LOW, but the trigger is live.)

**✅ F-C1617-1 CLEARED (live):** `SELECT kind,license,count(*) FROM source_corpus GROUP BY kind,license` → `shanhaijing|public-domain×2`, `history|public-domain×1`, `other|copyrighted×1`. The PD rows are the genuine demo corpora (山海经, Shang–Zhou history); the 1 copyrighted (`other`) is correctly non-admissible; **zero `unknown`** → ingest sets licenses explicitly, no silent-default leak on this DB. (The "ALTER doesn't rewrite existing rows" note remains valid for a hypothetical pre-fix DB, but this DB is clean.)

**🔴 F-C13-2 CONFIRMED + UPGRADED (live) — promoted enrichment is ORPHANED from the canonical entity (MED, real integration defect; not an H0 leak).**
The Step-1 promote (蓬萊) persisted; live state:
- Proposal row: `origin=enrichment, confidence=0.300, original_technique=retrieval, promoted_entity_id==writeback_entity_id=019e78d4…` — H0 markers retained ✓.
- Neo4j has **TWO** 蓬萊 entities:
  - `蓬萊` gid=`019e7850…` `source_type=glossary` (the canonical entity from glossary_sync/C4) — knows nothing of the enrichment;
  - `loc:蓬萊` gid=`019e78d4…` (= the proposal's promoted_entity_id) `source_type=enriched:retrieval` `pending_validation=TRUE` `origin=enrichment` — **still quarantined after promotion**.
- The 5 promoted facts (历史/地理/文化/features/inhabitants) ARE canon (`source_type=glossary, pending=false, promoted_by set`) — but they hang off the **enriched anchor `loc:蓬萊`**, NOT the canonical `蓬萊`.

**Two confirmed problems:** (1) `enriched-promote` flips only `:Fact` nodes, never the `:Entity` anchor — so the anchor stays `enriched:retrieval`/pending forever (the C13-review prediction, now proven live); (2) the writeback's glossary entity (`019e78d4`, name `loc:蓬萊`) is a DIFFERENT node from the canonical `蓬萊` (`019e7850`) — divergent gid + name → the code docstring's "glossary_sync canonizes the anchor ON MATCH" is **false in live state**. Net: the promoted enrichment facts are canon-in-isolation but **orphaned** from the canonical entity — a graph/RAG consumer querying canonical 蓬萊 sees none of the enrichment. This undercuts the headline "promote→canon verified": the facts are canon but not *integrated*.
**Caveat (root cause split):** the `loc:` name prefix suggests the live-smoke seeded the anchor with a synthetic name (`loc:蓬萊`) rather than the canonical `蓬萊`, which would explain why glossary extract-entities created a *new* entity instead of matching canon — so the *duplication* may be partly a smoke artifact. But problem (1) — the anchor `:Entity` never canonizing — is a real C13 design gap regardless of the name. → Fix: `enriched-promote` should also canonize the anchor Entity (or the writeback must resolve the EXISTING canonical glossary entity, not mint a parallel one); add a live assertion that post-promote the canonical entity carries the enrichment.

**🔎 F-C13-2 ROOT CAUSE (code-traced 2026-05-31) — corrects the C13-review "merge-key divergence" hypothesis (which was WRONG):**
The C4 glossary_sync MERGE key is `(user_id, glossary_entity_id)` (knowledge-service `extraction/glossary_sync.py:67`) — **identical** to the enriched-writeback key (internal_enrichment.py:176). The keys MATCH; Neo4j is not the problem. The divergence is upstream at the **glossary entity** level:
1. the live-smoke sets `target_ref="loc:蓬萊"` (tests/live_smoke_c14_job.py:271) — a synthetic ref, not a real canonical entity id;
2. `_anchor_name` (writeback.py:112) prefers `target_ref` over `canonical_name`, so the glossary `extract-entities` write uses name `loc:蓬萊`;
3. glossary has no entity named `loc:蓬萊` → it MINTS a NEW one (`019e78d4`), distinct from the canonical `蓬萊` (`019e7850`).
→ So the orphaning is a **glossary-entity-resolution** defect, not a KG-sync bug. **Two real fixes:** (a) `enriched-promote` must also canonize the `:Entity` anchor (or the writeback must RESOLVE the existing canonical glossary entity `target_ref` points to, instead of using `target_ref` as a new entity *name*); (b) gap-detection/writeback should carry the canonical `glossary_entity_id` so facts attach to the real entity. The `loc:` smoke value is the trigger, but the pattern "use `target_ref` as the entity name → mint parallel entity" is a genuine fragility that would orphan any enrichment whose `target_ref` isn't already a glossary entity name. **Net severity: MED** (integration/data-quality defect; NOT an H0 leak — no un-promoted content became canon).

**🔴 F-LIVE-1 RECURS (live, 2026-05-31) — stale knowledge image after a plain stack restart.** Brought the app services up via `docker start` and attempted the F-C13-1 retract live-test (POST `/proposals/{id}/retract` as the book owner). Result: **502** — `knowledge-service:8092/internal/knowledge/enriched-retract` → **404**. Diagnosis: `infra-knowledge-service-1` is **missing `internal_enrichment.py`** again (`ls` → No such file; image `infra-knowledge-service`). So the Step-1 F-LIVE-1 fix did **not survive a stack restart** — `docker start` brought back a knowledge image without the C13 enriched-* routes, and the entire KG H0 write-back/promote/retract path is 404 in the restarted stack. **This strongly reinforces the stale-image/CI-guard deferral: the deploy gap is not one-off — a simple restart reintroduces it.** (A `docker compose build knowledge-service && up -d` is needed; the running image must be pinned to ≥ the C13 commit.)

**F-C13-1 retract live-test: BLOCKED by the above (KG retract 404s before the glossary-recycle step).** The 502 does confirm the retract ORDER (writeback.py:461 KG-retract runs FIRST, before the glossary recycle at 477) — consistent with the code reading. **F-C13-1 remains CONCLUSIVELY code-confirmed** (handler passes no jwt, proposals.py:338; `Principal` has no token field, principal.py:38) — the live test would only confirm the already-unambiguous outcome. To finish it: rebuild knowledge-service, re-run retract, assert `glossary_recycled=false` + both glossary entities' `deleted_at` stay NULL.

**Stack left UP** (postgres/neo4j/redis + glossary/book/provider-registry/knowledge/lore-enrichment), knowledge image stale. Pre-retract glossary state captured for the eventual test: entities `019e7850…` (canon 蓬萊) + `019e78d4…` (enriched anchor) both `deleted_at=NULL`, book `019e7850-a8d9…`.

**⏳ Still deferred (need knowledge rebuild + LM Studio):** complete F-C13-1 retract e2e; fresh-stack promote→canon re-confirm with the anchor-canonization (F-C13-2) consideration.

---

## Step 3 — (original blocker note, superseded above)
The full `infra-*` stack EXITED ~18 min before this audit (postgres/neo4j/redis/glossary/book/provider-registry all `Exited (255)`; lore-enrichment crash-looping without its DB). The live-verification queries that would resolve the verify-live MEDs are **deferred until the stack is brought back up**:
- **F-C2-1** — `SELECT tgname FROM pg_trigger WHERE tgrelid='enrichment_proposal'::regclass` (is `trg_enrichment_proposal_h0` installed live?).
- **F-C1617-1** — `SELECT license, count(*) FROM source_corpus GROUP BY license` (any silently-defaulted `public-domain`?).
- **F-C13-2** — Neo4j: after a live promote, is the anchor `:Entity` canon (`source_type='glossary'`, `pending_validation=false`) or stuck pending?
- **F-LIVE-1 re-confirm** — promote→canon on a freshly-built stack (the Step-1 finding).
- **F-C12-1** — *static-confirmed* already (assembly.py:124-129 `_canon_lookup` is a hardcoded `return []`); no live check needed.

## Step 2 — Self-review tier — IN PROGRESS

### C14 (job orchestration: cost-cap + resume) — self-review — DONE 2026-05-31
Files: `app/jobs/runner.py`, `app/api/jobs.py` (lifecycle actions + `load_spent_so_far`).

**✅ The cost-cap PAUSE works (prior "cost-cap inert" really fixed):** `charge_or_pause(unit_cost, machine)` runs BEFORE each gap (runner.py:178) with the real per-gap cost (`cost_strategy.estimate_cost([gap])`, 175 — the GapCostModel for P1 / 8.0 for fabrication, wired in assembly), breach → PAUSE + persist `paused` + emit, never crash (179-201), and the eval reserve is protected (M5). H0 holds: every proposal born quarantined, runner never canonizes, an ungroundable gap is SKIPPED not minted (207-216).

**🟠 F-C14-1 (MED — "built-but-not-wired", 2nd of its class) — cost-cap pause RECOVERY is unwired; a paused job cannot be completed through any wired path.**
- the `/{job_id}/resume` endpoint only flips status paused→running and **explicitly does NOT re-drive the pipeline** (jobs.py:314-326,373-374) — no gaps get re-processed by resuming;
- `load_spent_so_far` (jobs.py:328) has **ZERO callers** (grep: only its own def + a comment);
- the create-job path calls `build_live_runner` **without** `spent_so_far` (jobs.py:163); the param is never passed in production.
So the documented recovery mechanism ("re-run on a fresh runner via `build_live_runner(spent_so_far=...)`") has no wired caller, and there is no background worker (the pipeline runs synchronously inside the create-job POST). A cost-paused job is effectively **stuck** (status flips to `running` but nothing processes the remaining gaps). D-C14-FULL-RESUME frames this as an *optimization* (skip already-done gaps), but the reality is more basic: **there is no wired resume at all.** The demo never surfaces it (small batches stay under the cap).
**Design note for whoever wires resume:** the runner re-processes from gap 0 and the LLM `run_gap` (runner.py:206) runs BEFORE the idempotent persist-dedupe (246), so a naive wired resume would (a) re-spend real LLM tokens on already-done gaps and (b) re-charge them against the `spent_so_far`-seeded budget → a job paused near its cap would re-pause with no forward progress (non-converging). The fix must skip already-persisted gaps before `run_gap`, not just before persist.


### Self-review tier (C0,C1,C3,C5,C6,C7,C8,C9,C10,C18) — DONE 2026-05-31 (light pass)
Risk-appropriate spot-check (not full `/review-impl`): deliverable present? stub/placeholder-only? obvious bug? Leveraged files already seen during the high-risk review.

| Cycle | Verdict | Note |
|---|---|---|
| C0 skeleton | ✅ | `/health`,`/ready` live-200 (Step 1) |
| C1 KG-read clients + port | ✅ | `KnowledgeReadPort/Http` seen in canon_verify/assembly; Q6-degrades to typed empties |
| C3 OpenAPI contract + stubs | ✅* | contract frozen; **`sources.create_source` + `templates` routers still 501 stubs** — the corpus-register API is unimplemented (ingest happens via a direct/smoke path, not the public API) |
| C5 wiki-from-KG | ◻️ | NOT deeply reviewed (cross-service, knowledge-service) — residual coverage gap |
| C6 gap model + dims + fixtures | ✅ | frozen dimension table, deterministic ranking |
| C7 gap-detection engine | ✅* | engine pure/deterministic/Q6-degrade, BUT **`EntityCoverage` is constructed nowhere in `app/` → the engine has zero production callers**; the job API enriches **client-supplied `body.targets`** (`_gap_from_target`), not KG auto-detected gaps |
| C8 strategy-core (registry/cost/state) | ✅* | verified via C14/C16; **cost is a fixed PRE-charge estimate, not real token metering** (`jobs/cost.py:89` TODO D-C14-EMBED-METER) — the cap is an abstract-unit guardrail, not real-$ |
| C9 template strategy | ✅ | intentional empty-placeholder scaffold (C10/C11 fill) |
| C10 retrieval (real bge-m3) | ✅ | `GroundedProposal`/grounding seen in fabrication/recook; real embed seam by model_ref |
| C18 observability + /ready | ✅ | `/ready`=200 live; metrics read from the live pipeline (not hardcoded) |

**🟡 F-C7-1 (LOW, likely by-design) — gap-detection engine is library-only / not API-wired.** Enrichment is explicit-target-driven (client passes targets); the "auto-detect under-described entities from the project KG" capability (C7's whole point) has no production caller. Combined with retract-recycle (F-C13-1) + resume (F-C14-1) + corpus-register (C3 501), this is a consistent shape: **the engines/libraries are solid + tested; the API wiring of peripheral capabilities is incomplete** — the live demo runs on the smoke + the implemented core routes (jobs/proposals/eval/promote). Not a safety issue, but it means "the service does auto-gap-detection / resume / retract / corpus-ingest via API" is **not** yet true.
**ℹ️ Note (feeds F-C13-2):** because `target_ref` is client-supplied (not engine-resolved to a real glossary entity id), the writeback's "use `target_ref` as the glossary entity name" fragility is reachable in any real flow, not just the smoke.

---

## Step 4 — Defer triage (044–058 + confirm 042/043/048/049/053/054) — DONE 2026-05-31

**🔴 STALE-RESOLVED rows (listed open in DEFERRED.md but the code shows them FIXED — update the list):**
- **048** (contradiction fails-open on partial canon outage) — **RESOLVED.** My C12 review verified `_lookup_canon` now sets `verify_degraded=True` on a swallowed exception (canon_verify.py:436-440), distinct from "no canon known." The exact fix the row prescribes is in the code. → mark RESOLVED.
- **049** (anachronism zero-width evasion) — **RESOLVED.** `_check_anachronism` now scans `_prenormalize(content)` (canon_verify.py:353). → mark RESOLVED.

**✅ Confirmed genuinely resolved:** 042 (/ready split — live-200), 053 (glossary-first canon-content — but see F-C13-2 caveat: the mechanism works, yet can mint a *duplicate* entity), 054 (gate enforcement via C16 factory — verified on the runner path).

**My QC findings vs the defer list (alignment):**
| QC finding | Maps to | Status |
|---|---|---|
| F-C14-1 resume unwired | **051** | already tracked (MED) — my live trace *sharpens* it: "no wired resume at all," not just "not work-efficient" |
| F-C15-1 judge diversity | **056** | already tracked (MED) — demo cleared on 2 qwen-family near-clones |
| F-C12-3 anachronism denylist finite | **058** | already tracked (LOW) |
| D-C14-EMBED-METER cost pre-charge | **052** | already tracked (LOW) |
| **F-C13-1 retract recycle dead code** | — | **NET-NEW (HIGH)** |
| **F-C13-2 orphaned enrichment** | partially 053-adjacent | **NET-NEW (MED)** — 053 fixed content-sync but not entity-resolution |
| **F-C12-1 contradiction inert (stubbed `_canon_lookup`)** | NOT 048 | **NET-NEW (MED)** — 048 was about exception-handling; this is "the prod feed is `[]`" |
| **F-C7-1 gap-detect unwired** | — | **NET-NEW (LOW)** |
| **F-LIVE-1 recurs on restart** | — | **NET-NEW (infra)** |

**Triage of the remaining open rows:**
- **DO-NOW (cheap, real gap):** **044** (1-line: add `KNOWLEDGE_SERVICE_URL` to glossary compose env → wiki KG sections work) · **046** (MED — repair accepts numeric/digit hallucinations `{"历史":123}`→"123" as Chinese facts; real quality hole, ~1 validator line).
- **KEEP (tracked, target a real phase):** 043 (manual name-fill→Neo4j, platform completeness) · 050 (injection denylist misses classical-Chinese/base64 — consumer treats text as data) · 051 (=F-C14-1, full resume) · 055 (suite-hash binding remainder) · 056 (=F-C15-1, judge diversity).
- **KEEP LOW (edge/fail-closed):** 045 (confidence quantization, fail-closed) · 047 (technique vocab, DB-rejected) · 052 (cost metering) · 057 (gate-status route test) · 058 (anachronism markers).
- **Net:** the defer backlog is mostly honest; two rows (048/049) are stale-resolved and should be closed; the QC adds **5 net-new findings** (1 HIGH + 2 MED + 1 LOW + 1 infra) the prior adversary didn't surface — concentrated, again, on write/undo/recovery wiring + live state.

---

## Step 5 — Synthesis + PR go/no-go (2026-05-31)

### Coverage (what this QC actually examined — honesty about scope)
- **Thoroughly reviewed (code + adversarial):** C2, C11, C12, C13, C15, C16, C17 (the 7 load-bearing `/review-impl` cycles) + C14 (self-review). C4 glossary_sync code-traced during F-C13-2 root cause.
- **Light self-review (spot-check):** C0, C1, C3, C6, C7, C8, C9, C10, C18 — DONE (see tier table); only **C5 wiki-from-KG NOT deeply reviewed** (cross-service residual).
- **Defer triage (044–058 + 042/043/048/049/053/054):** DONE (Step 4) — 2 stale-resolved rows found (048/049), QC adds 5 net-new findings.
- **Live-verified:** P1 promote→canon (Step 1), H0 trigger installed (F-C2-1), licensing rows (F-C1617-1), promoted-anchor Neo4j state (F-C13-2), F-LIVE-1 recurrence.
- **Still open:** C5 deep review + the live capstone (knowledge rebuild → F-C13-1 retract e2e + fresh promote→canon). → Synthesis is **near-final**; only the live retract capstone + C5 remain, neither expected to change the verdict.

### Per-cycle verdict
| Cycle | Verdict | Note |
|---|---|---|
| C2 data model + H0 trigger | ✅ sound | trigger live-confirmed; F-C2-1 LOW (UPDATE-only) |
| C11 mint chokepoint | ✅ excellent | both pydantic validation-skips closed |
| C12 canon-verify | ⚠️ logic sound, **contradiction inert** | F-C12-1 MED |
| C13 review/writeback/promote/retract | ⚠️ promote sound, **retract + anchor broken** | F-C13-1 HIGH, F-C13-2 MED |
| C14 orchestration | ⚠️ cost-cap sound, **resume unwired** | F-C14-1 MED |
| C15 eval-gate scoring | ✅ sound | earned verdict, fail-closed, 7-day fresh |
| C16 fabrication gate | ✅ sound | gate genuinely on runner path |
| C17 re-cook licensing | ✅ sound | default-deny end-to-end |
| C0,1,3,5,6,7,8,9,10,18 | ◻️ not individually reviewed | low-risk tier |

### Confirmed findings by severity
- **HIGH (1):** **F-C13-1** — retract's glossary recycle-bin is unreachable in prod (handler passes no jwt; `Principal` has no token) → a promoted entity's canon survives "undo." Code-confirmed; live test blocked by stale knowledge image.
- **MED (3):** **F-C13-2** promoted enrichment orphaned from the canonical entity (anchor never canonized + writeback mints a parallel glossary entity) · **F-C14-1** cost-pause recovery unwired (paused job stuck) · **F-C12-1** contradiction check inert in prod (`_canon_lookup` stubbed `[]`).
- **Infra (1):** **F-LIVE-1 recurs** — knowledge image loses the C13 enriched-* routes on a plain stack restart; the H0 KG write-back path is 404 until rebuilt.
- **LOW/tracked:** F-C2-1, F-C12-2/3, F-C1617-2, F-C15-1, F-C13-3/4/5, F-LIVE-3. Cleared: F-C2-1(live), F-C1617-1(live), F-LIVE-2(fixed this session).

### The shape of the result (the real signal)
**Every core safety invariant was verified genuinely-wired, not rubber-stamped:** H0 mint chokepoint (C11), structural DB trigger (C2, live), eval-gate enforcement on the runner path (C16), licensing default-deny (C17), eval verdict earned + fail-closed (C15), injection/anachronism defense (C12). The prior independent-adversary's fixes (makeup-as-name, minted-anchor, cost-cap, gate-on-runner, licensing-fail-closed, contradiction-fail-open) are all **real**.
**The defects cluster on two axes, never the core invariants:** (1) **peripheral write/undo/recovery paths the demo never exercises** — retract (F-C13-1), resume (F-C14-1), enrichment→canon integration (F-C13-2), contradiction-vs-real-canon (F-C12-1); (2) **deploy/live state** — stale image (F-LIVE-1). Three of these are the "built-but-not-wired false-green" class (ContextHub lesson `e16b6f02`) the QC was chartered to catch — and the masking mechanism was identical each time: a test that exercises the service layer with hand-supplied inputs the real API/handler never provides.

### Go / No-go for a PR
**Verdict: CONDITIONAL GO — architecture is sound; NOT yet merge-/demo-complete.**
The H0 core and the cost/quality/licensing controls are trustworthy enough to build on. But per the repo's **No-Defer-Drift** rule, the confirmed defects are real bugs to FIX, not defer:
- **Must-fix before "P1 demo complete" / merge:** F-C13-1 (retract — thread the token or give retract an internal-token recycle route like promote), F-C13-2 (promote must canonize the anchor / resolve the existing canonical glossary entity), F-LIVE-1 (pin/guard the knowledge image ≥ C13 + a CI stale-image check).
- **Should-fix (or consciously defer with a row):** F-C14-1 (wire resume, skipping done gaps), F-C12-1 (feed `_canon_lookup` real canon or degrade honestly when stubbed).
- **Finish the QC:** the low-risk self-review tier (C0,1,3,5,6,7,8,9,10,18) + the Step-4 defer triage (044–058) before final sign-off.
- **Live capstone (pending knowledge rebuild):** complete the F-C13-1 retract e2e + a fresh-stack promote→canon re-confirm.

**Recommended next action:** open the PR as a *review vehicle* (branch is unpushed; opening it enables `/code-review ultra`), with this QC doc as the cover note and the HIGH+MED list as the explicit pre-merge checklist — OR fix the HIGH + 2 must-fix MEDs first, then open. Either is defensible; the deciding factor is whether you want external review eyes (open now) or a clean diff (fix first).
