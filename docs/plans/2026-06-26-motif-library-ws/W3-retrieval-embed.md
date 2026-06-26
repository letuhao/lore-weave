# W3 — Retrieval + Platform Embedding · DETAILED DESIGN

> **Track:** LOOM / composition-service · **Workstream:** W3 (Wave 1, P1) · **Size:** M (1 new repo + 1 new engine helper + 1 test module against a frozen F0 contract).
> **Master plan:** [`2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) §3 (F0 froze the `MotifRetriever.retrieve()` signature + `MotifCandidate` shape) + §4 **W3** (lines 107–111).
> **Spec:** [`2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) — read **§R1.1.2** (one platform embed model), **§R2.2** (genre = bounded SQL filter), **§3.1** (retrieve step), and the corrected schema **§R1.4** (`embedded_summary_hash`, platform `embedding_model`, 2 tenancy partials).
> **Audit:** [`2026-06-26-motif-library-audit.md`](../../reports/2026-06-26-motif-library-audit.md) — **B-1** (cross-tier embedding-space mismatch, the #1 silent bug), **data-R1** (SQL pre-filter, not a full-table vector load), **data-R8 / H-5** re-embed transactionality, **A8/A9** (cross-model cosine garbage).
> **Grounded against real code:** `services/composition-service/app/db/repositories/references.py` (the brute-force `search()` + `_cosine` + the deliberate `embedding`-exclusion from `_SELECT_COLS`), `app/clients/embedding_client.py` (`/internal/embed`, `EmbeddingError.retryable`), `app/routers/references.py` (embed-on-write degrade posture), `app/config.py`, `app/db/migrate.py` (idempotent single-DDL house style).

---

## 1 · Scope + the contract I implement

### 1.1 What W3 OWNS (disjoint files — no other WS edits these)

| File | New? | Contents |
|---|---|---|
| `app/db/repositories/motif_retrieve.py` | **new** (F0 ships an interface stub; W3 fills it) | `MotifRetriever.retrieve()` — the SQL pre-filter + brute-force cosine top-K + `match_reason` build. **No `embedding` in any returned `Motif`** (mirror references' `_SELECT_COLS` rule). |
| `app/engine/motif_embed.py` | **new** | The **platform-embed** pipeline: `motif_summary_text()`, `summary_hash()`, `embed_motif_summary()` (one fixed `motif_embed_model` via provider-registry `/internal/embed`), `embed_query()` (the chapter-intent vector for retrieval), and the **transactional re-embed** helper used by W1's clone/patch and the create path. |
| `app/tests/unit/test_motif_retrieve.py` | **new** | Pre-filter bounds the load · cosine ranking correct · one-platform-model assert (B-1/A8/A9) · transactional re-embed (data-R8) · embed-down degrade (R4). |

### 1.2 What W3 does NOT own (consumes only the frozen signature)

- `db/migrate.py`, `db/models.py`, `config.py`, `deps.py` — **F0** owns. W3 *reads* the schema + `Motif`/`MotifCandidate` types + the new config keys; it does not edit them. Any field/config gap I need is a **note to F0**, not an edit here (§8).
- `engine/plan.py`, `engine/motif_select.py` — **W2** owns. W2 **consumes** `retrieve()`; until W3 lands, W2 mocks it. The contract below is the seam.
- `routers/motif.py`, `motif_repo.py` clone/patch — **W1** owns. W1 **calls** `engine/motif_embed.py`'s embed helpers inside its create/clone/patch transactions (the embed pipeline is W3's; the SQL write is W1's). The split: **W3 owns "what text → which model → vector + hash"; W1 owns "write that vector in a row in a tx".** The transactional-re-embed helper (1.4) is the shared seam.

### 1.3 The `retrieve()` contract (frozen by F0 §3.3 — I implement it verbatim)

```python
# app/db/repositories/motif_retrieve.py
class MotifRetriever:
    def __init__(self, pool: asyncpg.Pool) -> None: ...

    async def retrieve(
        self,
        caller_id: UUID,
        *,
        book_id: UUID | None,          # for the anti-repetition join hint only; NOT a tier key (R1.1: motif has NO book_id)
        project_id: UUID,              # carried for trace/telemetry; not a filter key on `motif`
        genre_tags: list[str],         # the book's genres → SQL `genre_tags && $genres` pre-filter (R2.2)
        language: str,                 # exact-match pre-filter (R1.1.3 — language is part of the dedup/embed key)
        beat_role: str | None,         # the L1 beat intent → folded into the query text for the cosine vector
        tension: int | None,          # the chapter's EXISTING 0..100 tension (config.plan_high_tension_threshold scale)
        prev_effects: list[str] | None,  # previous-motif effects → precondition-overlap signal in match_reason
        query_text: str | None = None,   # optional explicit chapter-intent text (else built from beat_role+effects)
        limit: int | None = None,        # default config.motif_retrieve_top_k
        min_score: float | None = None,  # default config.motif_min_score
    ) -> list[MotifCandidate]: ...
```

```python
# MotifCandidate — frozen shape (master plan §3.3 line 73). Defined in db/models.py by F0; W3 returns it.
class MotifCandidate(BaseModel):
    motif: Motif            # WITHOUT the embedding vector (server-side only)
    score: float            # the cosine, 0..1 — the rank key
    match_reason: MatchReason

class MatchReason(BaseModel):
    tension: float          # how well motif.tension_target band fits the chapter tension (0..1)
    genre: float            # |genre_tags ∩ $genres| / |$genres|  (0..1) — overlap strength
    precond: float          # precondition-overlap vs prev_effects (0..1); 0.0 when prev_effects is None
    cosine: float           # == score (the embedding similarity component, surfaced explicitly for the UX "why")
```

**Contract guarantees W3 makes to W2 (these are the tests in §6/§7):**
1. **Candidates are pre-filtered in SQL** — the result set is bounded by `(genre ∩ $genres) AND status='active' AND language=$lang AND <tier predicate>` *before* any vector is loaded. `retrieve()` never loads the whole `motif` table's vectors.
2. **Ranked by cosine desc**, then a **deterministic tie-break** (`mining_support DESC NULLS LAST, judge_score DESC NULLS LAST, code ASC`) so W2's "reproducible top-1" eval-gate holds.
3. **`min_score` floor applied** — a candidate below `motif_min_score` is dropped (an unrelated motif never gets force-bound; W2's no-match fallback fires cleanly).
4. **All candidate vectors share ONE `embedding_model`** (`config.motif_embed_model`) — so the cosine is always same-space. Cross-model contamination is **structurally impossible** (3 + §7).
5. **No `embedding` field** on any returned `Motif` (vector stays server-side — references' rule).
6. **Embed-down ≠ empty result.** When the query vector can't be produced (provider outage), `retrieve()` degrades to **genre+tension ordering** over the same pre-filtered set (R4: degrade, don't invent), with `match_reason.cosine = 0.0` and a `degraded=True` marker on the candidate — it does **not** 500 and does **not** return `[]` (a bound, structurally-valid set is still useful to the planner).

---

## 2 · The retrieve algorithm — SQL pre-filter THEN app-code cosine

### 2.1 Why a pre-filter at all (data-R1 — the #1 perf + correctness fix)

`references.py:search()` does `SELECT … , embedding FROM reference_source WHERE user_id=$1 AND project_id=$2` and cosines **every** row in app code. That is fine there: a reference shelf is *single-tenant*, dozens to low-hundreds of rows (the table comment says so). **Motif retrieval is a different regime** — it merges the **shared, mining-grown system tier** + every public motif + the caller's own library, across all genres and languages. Loading **all** those vectors per chapter-plan call is the audit's data-R1 finding: an O(table) vector load on the hot planner path, growing without bound as the library grows.

The fix: **bound the candidate set in SQL first** — only `active`, only the caller's `language`, only motifs whose `genre_tags` intersect the book's genres (R2.2 makes genre a *bounded filter*, not a soft prior, exactly to keep this set small), only rows the caller may see (the R1.1 tier predicate). Then load vectors **for that bounded set only** and cosine in app code (the references pattern, now applied to a *bounded* set). The GIN index on `genre_tags` + the `language`/`status` predicates make the pre-filter index-assisted.

### 2.2 The pre-filter SQL (the real query)

```sql
-- motif_retrieve.py — the BOUNDING query. Loads `embedding` for the bounded set ONLY.
-- $1 caller_id · $2 genres (text[]) · $3 language · $4 hard candidate ceiling (config.motif_candidate_ceiling)
SELECT
    id, owner_user_id, code, language, visibility, kind, category, name, summary,
    genre_tags, roles, beats, preconditions, effects, tension_target, emotion_target,
    examples, abstraction_confidence, source, source_ref, source_version,
    embedding_model, embedded_summary_hash, judge_score, mining_support,
    status, version, created_at, updated_at,
    embedding                                   -- the ONLY place the vector is selected; never leaves the repo
FROM motif
WHERE status = 'active'
  AND language = $3
  AND genre_tags && $2::text[]                  -- array-overlap: at least one shared genre (GIN idx_motif_genre)
  AND (
        owner_user_id IS NULL                    -- system tier (seed/migrate-only)
        OR visibility = 'public'                 -- anyone's published motif
        OR owner_user_id = $1                     -- the caller's own (private/unlisted/public)
      )                                          -- == THE R1.1 read predicate, identical to MotifRepo.get_visible
ORDER BY
    (owner_user_id = $1) DESC NULLS LAST,        -- prefer the caller's own tier on the ceiling cut (shadow intent)
    mining_support DESC NULLS LAST,
    judge_score DESC NULLS LAST,
    updated_at DESC
LIMIT $4;                                        -- HARD candidate ceiling — the brute-force bound (5 + §8)
```

**Notes:**
- `genre_tags && $2` is Postgres array-overlap (`&&`) — true iff the sets intersect. With `idx_motif_genre` (GIN) this is index-assisted, so the pre-filter does **not** scan the whole table. (An empty `$genres` would make `&&` always-false → zero candidates; W3 treats `genre_tags == []` as "no genre constraint" and **omits** the `&&` clause for that call — the spec's default is genre-bounded, but a genre-less book must still retrieve. §8 micro-decision MD-2.)
- The tier predicate is **byte-identical** to `MotifRepo.get_visible`'s predicate (F0 §3.3). One predicate, two call sites — so a retrieved candidate is provably also fetchable by id (no "ranked but unreadable" ghost, no IDOR via the retrieve path). This is the B-2 read-predicate, reused.
- `language = $3` is exact-match. Cross-language retrieval is **out of scope** (the embedding model is one platform model, but a Vietnamese summary and an English summary are different points even in one space; mixing languages in the candidate set would let an English motif outrank a Vietnamese one on a Vietnamese book). R1.1.3 makes `language` part of the key precisely so retrieval stays within-language.
- The `LIMIT $4` is the **candidate ceiling** (distinct from the `top_k` returned). It caps how many vectors the brute-force pass loads — the bound that keeps app-code cosine O(ceiling), not O(table), even if a hugely-popular genre accrues thousands of public motifs (5). The `ORDER BY` before the LIMIT is a *cheap pre-rank* (popularity/quality/recency, no vector needed) so the ceiling cut keeps the *most promising* candidates, not arbitrary ones — then cosine re-ranks within that set.

### 2.3 The cosine pass (app code — the references shape, bounded)

Reuse `references.py`'s `_cosine` **verbatim** (it is correct: returns 0.0 on empty/zero/length-mismatch, so a degenerate row never out-ranks a real hit). Do **not** re-import it (cross-repo import couples the files); W3 ships its own copy in `motif_retrieve.py` with a comment pointing at the reference impl as the source-of-truth shape. (MD-4 weighs a shared `_vec.py` util — recommendation: copy for now, it's 12 lines and the duplication is honest; a shared util is a F0 concern if a third cosine site appears.)

```python
def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine of two equal-length vectors; 0.0 for empty/zero/mismatched-length
    (a degenerate row never out-ranks a real hit). Copy of references.py:_cosine —
    kept local so motif_retrieve has no cross-repo coupling. If a 3rd cosine site
    appears, F0 promotes this to db/repositories/_vec.py."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y; na += x * x; nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
```

```python
async def retrieve(self, caller_id, *, book_id, project_id, genre_tags, language,
                   beat_role, tension, prev_effects, query_text=None,
                   limit=None, min_score=None) -> list[MotifCandidate]:
    limit = limit or settings.motif_retrieve_top_k
    min_score = settings.motif_min_score if min_score is None else min_score
    ceiling = settings.motif_candidate_ceiling

    # (1) SQL pre-filter → BOUNDED candidate rows (with vectors). data-R1.
    rows = await self._fetch_candidates(caller_id, genre_tags, language, ceiling)
    if not rows:
        return []                                  # no in-genre/in-language motif → W2 falls back to invent

    # (2) Query vector (the chapter-intent embedding). Embed-DOWN → degrade, not invent (R4).
    qtext = query_text or _build_query_text(beat_role, prev_effects)
    qvec: list[float] | None = None
    if qtext:
        try:
            qvec = await embed_query(qtext)        # ONE platform model — engine/motif_embed.py
        except EmbeddingError:
            qvec = None                            # degrade branch below (NOT a 500, NOT [])

    # (3) Score every BOUNDED candidate; build match_reason. (Vectors loaded for the bound set ONLY.)
    scored: list[tuple[float, MotifCandidate]] = []
    for r in rows:
        genre_s   = _genre_overlap(r["genre_tags"], genre_tags)
        tension_s = _tension_band(r["tension_target"], tension)
        precond_s = _precond_overlap(r["preconditions"], prev_effects)
        if qvec is not None:
            vec = r["embedding"]
            cos = _cosine(qvec, list(vec)) if vec else 0.0
            rank = cos                              # cosine drives the rank when we have a query vector
            degraded = False
        else:
            cos = 0.0
            rank = 0.6 * genre_s + 0.4 * tension_s  # DEGRADE: genre+tension order (R4), no invented vector
            degraded = True
        if (qvec is not None) and rank < min_score:
            continue                                # min_score floor → no force-bind of an unrelated motif
        motif = _row_to_motif(r)                    # WITHOUT embedding (server-side only)
        scored.append((rank, MotifCandidate(
            motif=motif, score=rank,
            match_reason=MatchReason(tension=tension_s, genre=genre_s, precond=precond_s, cosine=cos),
            degraded=degraded,
        )))

    # (4) Rank desc + deterministic tie-break (reproducible top-1 for W2's eval).
    scored.sort(key=lambda t: (
        -t[0],
        -(t[1].motif.mining_support or 0),
        -float(t[1].motif.judge_score or 0.0),
        t[1].motif.code,
    ))
    return [c for _, c in scored[:max(0, limit)]]
```

`_build_query_text(beat_role, prev_effects)` mirrors the references router's auto-query seed (`" ".join([goal, synopsis, beat_role, title])`): it joins the beat intent + the prior-motif effects into one short string so the chapter-intent vector reflects *both* what this beat is for and what state precedes it. `_genre_overlap`, `_tension_band`, `_precond_overlap` are pure functions (unit-tested in isolation, §6).

`_tension_band(motif_tension_target_1to5, chapter_tension_0to100)`: the motif's `tension_target` is **SMALLINT 1..5** (spec §R1.4) while the chapter's `tension` is the **EXISTING 0..100** scale (`config.plan_high_tension_threshold = 70`). W3 maps the 1..5 band to a 0..100 midpoint (`1→10, 2→30, 3→50, 4→70, 5→90`) and scores closeness `1 - |band_mid - tension| / 100`. **W3 only *reports* this in `match_reason`; W2 owns the authoritative tension reconcile** (master plan §4 W2 "tension 1-5 ↔ 0-100 reconcile") — W3 must not duplicate W2's binding logic, it just surfaces the band-fit so the UX "why" is honest and W2 has the signal.

---

## 3 · The platform-embed pipeline (ONE fixed model — R1.1.2)

### 3.1 The invariant, stated as construction

> **Every motif vector is produced by exactly one model: `config.motif_embed_model`. Therefore every cosine in `retrieve()` is computed between two vectors in the *same* embedding space. Cross-model contamination (B-1 / A8 / A9) is impossible by construction — not by validation.**

This is the whole point of the R1.1.2 decision. `reference_source` uses the **Work's BYOK** model (`reference_embed_model_ref` in `work.settings`) — correct there, because every reference of a Work shares that one BYOK model, so its `search()` is same-space *within a Work*. **Motif retrieval crosses Works, users, and the shared system tier** — so a per-Work / per-user BYOK model would mean the seed pack (embedded once, at seed time) and a user's adopted clone (re-embedded with *their* BYOK model) live in **different spaces**, and `_cosine` would return garbage (same dim) or 0.0 (different dim). That is audit **B-1**: "a user whose embed model ≠ the seed pack's model gets cosine 0.0 against the entire system tier → the seeded pack is invisible, silently."

The construction kills it: **there is no per-Work choice for motif vectors.** `engine/motif_embed.py` hard-wires the platform model. The seed pack (W7), every user create (W1), every clone/adopt (W1), and the query vector (W3) **all** call the same `_platform_embed_model()` — so they are all the same space, always.

### 3.2 `engine/motif_embed.py` — the helpers

```python
# app/engine/motif_embed.py
from app.config import settings
from app.clients.embedding_client import get_embedding_client, EmbeddingError, EmbeddingResult

def _platform_embed_model() -> tuple[str, str]:
    """The ONE fixed (model_source, model_ref) for ALL motif vectors (R1.1.2).
    NOT the Work's BYOK model. Read from config.motif_embed_model (e.g.
    'platform_model:text-embedding-3-small' or a local-rerank-style BYOK-platform
    credential). The source defaults to 'platform_model'; this is the single
    chokepoint that makes cross-model contamination impossible."""
    raw = settings.motif_embed_model
    if ":" in raw:
        src, ref = raw.split(":", 1)
        return (src or "platform_model", ref)
    return ("platform_model", raw)

def motif_summary_text(motif_like) -> str:
    """The canonical text that gets embedded. Stable + deterministic so the hash
    is reproducible: name + summary + the ordered beat labels/intents. (Beats are
    part of identity — two motifs with the same summary but different beats are
    different motifs.) Mirrors how references embed `content`, but composed from
    the structured fields."""
    parts = [motif_like.name, motif_like.summary]
    for b in (motif_like.beats or []):
        parts += [b.get("label", ""), b.get("intent", "")]
    return "\n".join(p for p in parts if p).strip()

def summary_hash(text: str) -> str:
    """sha256 of the canonical embed text → motif.embedded_summary_hash. The
    staleness guard: if hash(current summary text) != stored hash, the vector is
    stale and MUST be re-embedded before it is trusted (data-R8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

async def embed_motif_summary(text: str) -> EmbeddingResult:
    """Embed a motif's canonical summary text with the PLATFORM model. Raises
    EmbeddingError (retryable flagged) — the caller (W1 create/clone/patch) decides
    fail-closed vs degrade. NEVER takes a model arg — the model is fixed."""
    src, ref = _platform_embed_model()
    client = get_embedding_client()
    return await client.embed(
        user_id=PLATFORM_EMBED_USER_ID,   # see MD-1: the user_id passed to /internal/embed for a platform model
        model_source=src, model_ref=ref, texts=[text],
    )

async def embed_query(text: str) -> list[float]:
    """Embed a chapter-intent query string with the SAME platform model → the
    retrieval query vector. Returns the bare vector. Raises EmbeddingError (the
    retrieve() degrade branch catches it)."""
    res = await embed_motif_summary(text)
    return res.embeddings[0] if res.embeddings else []
```

**Why `embed_query` reuses `embed_motif_summary`'s model:** the query vector and the motif vectors **must** be the same space or the cosine is meaningless. Routing both through `_platform_embed_model()` makes that automatic — there is no code path that embeds a motif with one model and the query with another.

### 3.3 The provider invariant + the model-name invariant (both held)

- **Provider gateway invariant:** `embed_motif_summary` calls `embedding_client.embed()` → `POST /internal/embed` on provider-registry. No provider SDK import in composition; no direct provider HTTP. Identical to how `reference_source` embeds. ✅
- **No-hardcoded-model invariant:** `motif_embed_model` is a **config value** (env-driven, like every other model ref), resolved at runtime — never a literal model string in W3 code. The `_platform_embed_model()` parse is the only place it's read. The `ai-provider-gate.py` hook sees a config read, not a literal. ✅ (MD-1 covers *how* the platform credential resolves on the provider-registry side — a platform-owned `user_models` row, mirroring the local-rerank BYOK-as-platform pattern in CLAUDE.md, **not** a new per-service `*_URL`/`*_MODEL` env. The composition side only knows the config key.)

---

## 4 · Re-embed staleness + the transactional re-embed (data-R8)

### 4.1 The staleness guard — `embedded_summary_hash`

`reference_source` is **immutable** after create (no PATCH of `content`) — so it never needs a re-embed guard. **`motif` is mutable** (the spec's PATCH edits `summary`, `name`, `beats`). A naive PATCH that updates `summary` but leaves the old vector is the silent-staleness bug: the row now retrieves on its *old* meaning. `embedded_summary_hash` (spec §R1.4) is the guard:

```
stored motif.embedded_summary_hash  ==  summary_hash(motif_summary_text(current row))   ⟹  vector is fresh
                                    !=                                                  ⟹  vector is STALE → re-embed
```

On every write that can change the embed text (`create`, `clone`, `patch`), the writer (W1) computes the new text + hash; if the hash differs from what's stored, it re-embeds **in the same transaction** and writes `embedding`, `embedding_model`, `embedded_summary_hash` together. W3 supplies the helper that makes this atomic.

### 4.2 The transactional re-embed helper — NO stale-vector window (data-R8 / H-5)

The failure mode data-R8 guards: *write the new summary, commit, then embed and write the vector in a second statement.* Between the two commits the row is live with a **new summary + an old vector** — a stale-vector window where `retrieve()` returns wrong results. The fix: **embed first (outside the tx, the network call), then write summary + vector + hash in ONE statement inside ONE tx.** Embedding is a network call and must not hold a DB tx open; so the order is: compute text → embed (no tx) → open tx → single `UPDATE … SET summary=…, embedding=…, embedding_model=…, embedded_summary_hash=… WHERE id=… AND version=$expected` → commit. The row is *never* live with a mismatched (summary, vector) pair.

```python
# engine/motif_embed.py — the seam W1 calls inside its create/clone/patch path.
async def reembed_in_tx(conn: asyncpg.Connection, motif_id, motif_like, *, expected_version) -> bool:
    """Re-embed a motif's summary and write (embedding, embedding_model,
    embedded_summary_hash) together, atomically, ONLY if the embed text changed.
    `conn` is an already-open tx connection owned by the CALLER (W1) — so the
    summary edit + the vector write commit as ONE unit (data-R8: no window where
    the row is live with new summary + old vector). Returns True if it re-embedded,
    False if the hash was unchanged (no-op, no provider call). Embedding (the
    network call) happens BEFORE we touch the row, so we never hold the tx open on
    a slow/cold local model."""
    text = motif_summary_text(motif_like)
    new_hash = summary_hash(text)
    if new_hash == motif_like.embedded_summary_hash:
        return False                                   # nothing to do — saves a provider call on a no-summary-change edit
    res = await embed_motif_summary(text)              # network call, OUTSIDE the row write (still inside caller's tx scope, but pre-UPDATE)
    if not res.embeddings or not res.embeddings[0]:
        raise EmbeddingError("platform embed returned empty", retryable=True)
    await conn.execute(
        """UPDATE motif
              SET embedding = $1, embedding_model = $2, embedded_summary_hash = $3, updated_at = now()
            WHERE id = $4 AND version = $5""",
        res.embeddings[0], res.model, new_hash, motif_id, expected_version,
    )
    return True
```

> **Ownership note:** the *create* path inserts the vector inline (W1's INSERT carries `embedding`/`hash` from a pre-INSERT `embed_motif_summary`); the *patch/clone* path uses `reembed_in_tx` so the summary-edit and the vector-write are one statement. W3 owns both helpers; W1 wires them into its router/repo. The clone case (3.1) **re-embeds rather than copies the source vector** — because even though the source vector *is* the same platform space (so copying would be correct), re-embedding is cheap, makes clone self-contained, and means a clone whose summary the user immediately edits can't carry a mismatched hash. (MD-3 weighs copy-vs-reembed-on-clone; recommendation: **re-embed on clone** for hash-consistency, accept the one extra embed call. The audit B-1 "adopt copies the source's stale vector" risk is then closed by construction — clone never copies a vector.)

### 4.3 The embed-DOWN degrade branch (R4 — degrade, don't invent)

Two distinct degrade points, both "degrade, never invent":

| Where | Failure | Behavior |
|---|---|---|
| **`retrieve()` query embed** (hot read path) | provider outage when embedding the chapter-intent query | **Degrade to genre+tension ordering** over the *same pre-filtered* candidate set (`rank = 0.6·genre + 0.4·tension`), `match_reason.cosine=0.0`, `degraded=True`. Never 500, never `[]` (a bound, valid set still helps the planner pick on-genre). W2 sees `degraded` and may choose to lower confidence / not auto-bind — but it gets *real, in-genre* candidates, not invented ones. |
| **create/clone/patch embed** (write path) | provider outage when embedding a new/edited summary | **Fail-closed** — raise `EmbeddingError` → W1's router returns 502 `{code: MOTIF_EMBED_FAILED, retryable}` (mirrors `references.py:110` exactly). A motif **must not** be persisted active with a null/stale vector (it would be silently un-retrievable — the references router rejects that path too). The write fails loudly; the user retries. (A *draft* motif may persist with `embedding=NULL` and simply never be a retrieval hit until re-embedded — same as references' transient-null posture — but an `active` motif always has a fresh vector.) |

The asymmetry is deliberate and matches the codebase: **reads degrade soft** (references' search returns neutral-empty on outage, never 500); **writes fail hard** (references' create 502s on embed failure rather than persist an unsearchable row). W3 mirrors both.

---

## 5 · When brute-force breaks + the pgvector trigger

The references table comment justifies brute-force: "a reference shelf is small — dozens to low-hundreds of rows … no pgvector / ivfflat / fixed-dimension column needed." **The motif library is not bounded that way** — the system tier is mining-grown and the public tier is every user's published motifs. So W3 must document the ceiling and the migration trigger:

- **What the pre-filter buys:** the brute-force pass is O(**candidates after the SQL pre-filter**), not O(table). For the common case — one book's 1–3 genres × one language × `active` — the candidate set is small (tens to low-hundreds), so brute-force is correct and a pgvector index would be premature. **The pre-filter is what keeps brute-force viable.**
- **The hard ceiling (`config.motif_candidate_ceiling`, default ~500):** the `LIMIT $4` in 2.2 caps vectors loaded per call even if a single popular genre accrues thousands of public motifs. Above the ceiling we cosine only the cheap-pre-ranked top-N (popularity/quality/recency) — a graceful degradation (we might miss a great-cosine-but-unpopular motif beyond the cut), not a perf cliff.
- **The pgvector trigger (document, don't build):** migrate `motif.embedding REAL[]` → a `vector(D)` column + an `ivfflat`/`hnsw` index **when** (a) a single genre+language candidate set routinely exceeds the ceiling (the pre-filter stops bounding it), OR (b) p95 retrieve latency on the planner path crosses budget, OR (c) "show cross-genre matches" (R2.2 toggle) demands an unfiltered scan. That migration is a **column-type + fixed-dimension change** — and **the one-platform-model decision (3) is the prerequisite that makes it possible**: a `vector(D)` column requires one fixed `D`, which a single embedding model guarantees and a per-user BYOK model would forbid. So R1.1.2 isn't only the correctness fix — it's also what keeps the pgvector door open. **This is a Track-2 / Perf deferral**, recorded in §8 + SESSION_HANDOFF; not P1 work.

---

## 6 · Tests + eval-gate

`app/tests/unit/test_motif_retrieve.py` (W3-owned). Unit-level (pure functions + repo against a test pool or a fake-conn), plus the W3 eval-gate assertions (master plan §4 W3).

### 6.1 Pure-function tests (no DB, no network)
- `test_cosine_zero_on_mismatch` — `_cosine([1,2,3],[1,2])==0.0`, `_cosine([],[1])==0.0`, `_cosine([0,0],[0,0])==0.0` (degenerate never out-ranks).
- `test_cosine_ranks_correctly` — a vector identical to the query scores 1.0; an orthogonal one ~0.0; ordering is by cosine desc.
- `test_genre_overlap` — `{a,b}∩{b,c}` over `{b,c}` → 0.5; disjoint → 0.0; full → 1.0.
- `test_tension_band_map` — `tension_target=5` (band-mid 90) vs chapter `tension=85` scores high; `target=1` vs `tension=90` scores low; `None` → neutral 0.5.
- `test_precond_overlap` — `prev_effects=None` → 0.0; overlapping effect/precondition text → >0.
- `test_build_query_text` — joins beat_role + prev_effects, drops empties, stable string.
- `test_summary_text_and_hash_stable` — `motif_summary_text` is deterministic across calls; `summary_hash` changes iff the text changes (re-order beats → different hash).

### 6.2 Retrieve behavior (repo against a seeded test DB / fake rows)
- `test_prefilter_bounds_the_load` *(eval-gate: "pre-filter bounds the load")* — seed motifs across 3 genres + 2 languages + draft/active; call `retrieve(genre=['cultivation'], language='en')`; assert the SQL returns **only** active+en+cultivation-overlapping rows, and assert (via a spy/`asyncpg` query log or a counting fake pool) that **the number of vectors loaded == the pre-filtered count, NOT the table count**. This is the data-R1 guard as a test.
- `test_min_score_floor` — a candidate whose cosine < `motif_min_score` is dropped (no force-bind).
- `test_deterministic_tiebreak` — two candidates with equal cosine resolve by `mining_support`, then `judge_score`, then `code` — same input → same top-1 across runs (W2's reproducibility dep).
- `test_no_embedding_in_result` — every returned `MotifCandidate.motif` has **no** `embedding` attribute populated (server-side-only rule).
- `test_tier_predicate_matches_get_visible` — assert the retrieve WHERE-predicate string and `MotifRepo.get_visible`'s predicate are the **same** (a candidate is always also `get_visible` by id → no ghost / no IDOR via retrieve). (Mechanically: a parametrized test that for each of {system, public-other, own-private, other-private} confirms retrieve includes iff get_visible includes.)

### 6.3 Embed pipeline
- `test_one_platform_model_for_all_vectors` *(eval-gate + §7 B-1)* — patch `embedding_client.embed` to record every `(model_source, model_ref)` it's called with; run create + clone + a query embed; assert **every** call used `config.motif_embed_model` and nothing else. (The structural assert of "cross-model contamination impossible.")
- `test_query_and_motif_share_model` — the query embed and the motif embed resolve to the identical `_platform_embed_model()` tuple.
- `test_reembed_transactional` *(eval-gate + §7 data-R8)* — using a fake conn that records statement order: assert the `UPDATE motif SET summary…, embedding…, hash…` is **one** statement (summary + vector + hash together), and that the embed network call happened **before** the UPDATE — so there is no commit between summary-write and vector-write (no stale window).
- `test_reembed_skips_when_hash_unchanged` — editing a non-summary field (e.g. `category`) → `reembed_in_tx` returns False, **no** provider call (no needless spend).
- `test_clone_reembeds_not_copies` — clone produces a fresh vector via the platform model (asserts the source vector is not byte-copied), closing B-1's "adopt copies stale vector."

### 6.4 Degrade
- `test_query_embed_outage_degrades` *(R4)* — patch `embed_query` to raise `EmbeddingError`; assert `retrieve()` returns the **pre-filtered set ordered by genre+tension** (not `[]`, not a raise), with `degraded=True` + `match_reason.cosine==0.0`.
- `test_write_embed_outage_fails_closed` — patch `embed_motif_summary` to raise; assert `reembed_in_tx`/create propagates `EmbeddingError` (W1 maps → 502), i.e. an active motif is never persisted with a stale/null vector.

### 6.5 Eval-gate (the W3 ship gate — master plan §4 W3 line 111)
Ships iff: **pre-filter bounds the load** (`test_prefilter_bounds_the_load`) · **cosine ranking correct** (`test_cosine_ranks_correctly`) · **one-platform-model assert** (`test_one_platform_model_for_all_vectors`) · **re-embed transactional** (`test_reembed_transactional`). These four are the §7 audit-guards-as-tests; if any is red, W3 does not land.

**Live-smoke (cross-service, embed touches provider-registry):** the assembled R-NODE-P1 (master plan §6) exercises a real `retrieve()` on a stack-up (`live smoke: motif bound + traced on a real stack-up`). At W3's own VERIFY, the provider-registry embed is the cross-service hop — either run it on a stack-up or record `LIVE-SMOKE deferred to D-MOTIF-RETRIEVE-LIVE-SMOKE` / `live infra unavailable: <reason>` per the VERIFY evidence rule.

---

## 7 · Audit risk-guards as failing-tests-first

Each audit blocker W3 touches becomes a **failing test written before the impl** (master plan §7):

| Audit ID | The risk | The failing-test-first (W3) | The construction that makes it pass |
|---|---|---|---|
| **B-1 / A8 / A9** | cross-tier/cross-model cosine → garbage or 0.0 → seed pack silently invisible | `test_one_platform_model_for_all_vectors` (every embed call uses `motif_embed_model`); `test_clone_reembeds_not_copies` | **One platform model for ALL motif vectors (3).** All vectors one space → cosine always valid. Contamination impossible *by construction*, asserted by the test. |
| **data-R1** | full-table vector load on the hot planner path | `test_prefilter_bounds_the_load` (vectors loaded == pre-filtered count, not table count) | **SQL pre-filter (2.2)** bounds the set (`genre && + status + language + tier predicate`, GIN-assisted) *before* any vector loads; `LIMIT` ceiling caps the brute-force. |
| **data-R8 / H-5** | new summary + old vector live between two commits (stale-vector window) | `test_reembed_transactional` (summary+vector+hash one statement; embed before UPDATE) | **`reembed_in_tx` (4.2):** embed (no tx) → single atomic UPDATE of summary+vector+hash in the caller's tx. Never live mismatched. |
| **B-2 (read predicate, reused)** | retrieve returns a motif the caller can't fetch by id (ghost / IDOR via the rank path) | `test_tier_predicate_matches_get_visible` | The retrieve WHERE tier-clause is **byte-identical** to `MotifRepo.get_visible` (one predicate, two sites). |
| **R4 (degrade-not-invent)** | embed outage → 500 or invented results | `test_query_embed_outage_degrades`, `test_write_embed_outage_fails_closed` | Read path degrades to genre+tension over the real pre-filtered set; write path fails closed (no active motif with a stale vector). |

---

## 8 · Open micro-decisions + recommendations

| ID | Decision | Options | **Recommendation** |
|---|---|---|---|
| **MD-1** | What `user_id` / credential does the **platform** embed model use on `/internal/embed`? `embedding_client.embed` requires a `user_id` (it's BYOK-shaped). | (a) a reserved platform `user_id` whose provider-registry `user_models` row holds the platform embed credential (mirrors the local-rerank "BYOK-as-platform" pattern in CLAUDE.md); (b) extend `/internal/embed` to accept a platform-model source with no user. | **(a)** — a reserved platform owner row keeps the provider invariant intact with zero provider-registry contract change; W3 reads `config.motif_embed_model` + `config.motif_embed_owner_id`. **Flag to F0** (it owns `config.py`): add `motif_embed_model` + `motif_embed_owner_id`. Confirm the platform credential is seeded on the provider-registry side (W7/infra, not W3). |
| **MD-2** | Genre-less book (`genre_tags == []`) | (a) omit the `&&` clause (retrieve across all genres, language+tier-bounded); (b) return `[]` (force the author to tag genres) | **(a)** — never zero-out retrieval on a missing tag; a language+tier+ceiling bound still applies, so it stays bounded. Surface a "tag genres for better matches" hint in W6, not a hard fail. |
| **MD-3** | Clone vector: copy source vs re-embed | (a) copy (same platform space → technically correct, cheaper); (b) re-embed | **(b) re-embed** — makes clone self-contained + hash-consistent, and closes B-1's "adopt copies stale vector" by construction (clone never copies a vector). One extra embed call per clone is acceptable (clone is not a hot path). |
| **MD-4** | `_cosine` duplication (references + motif_retrieve) | (a) copy 12 lines locally; (b) shared `db/repositories/_vec.py` | **(a) copy now** — honest 12-line duplication, no cross-repo coupling. If a 3rd site appears, F0 promotes to `_vec.py`. (Recorded so it's a conscious call, not drift.) |
| **MD-5** | `motif_candidate_ceiling` default | n/a | **~500** (config, F0-owned). Above it, cosine only the cheap-pre-ranked top-500; record the pgvector trigger (5) as Perf-deferral `D-MOTIF-PGVECTOR-TRIGGER`. |
| **MD-6** | Is `tension`/`precond` scoring W3's or W2's job? | n/a | W3 **reports** `match_reason.{tension,precond}` (for the UX "why" + as a signal); **W2 owns the authoritative tension reconcile + the bind decision**. W3 must not duplicate W2's binding logic — keep the boundary clean. |

**Notes to F0 (config.py / models.py — W3 does NOT edit, these are requests):**
- `config.py`: add `motif_embed_model: str` (required, no default — fail-to-start if unset, like other model refs), `motif_embed_owner_id: str` (MD-1), `motif_retrieve_top_k: int = 8`, `motif_min_score: float = 0.2`, `motif_candidate_ceiling: int = 500`. (`motif_max_reapply` is W2's; listed in F0 §3.4 already.)
- `db/models.py`: confirm `MotifCandidate` + `MatchReason` carry a `degraded: bool = False` field (the degrade marker §1.3-6); confirm `Motif` exposes `mining_support`, `judge_score`, `code`, `embedded_summary_hash` (needed for tie-break + staleness). All are in §R1.4 — just confirming the Pydantic surface.

---

## 9 · Task list (W3 build order — TDD)

1. **T1 — Read the frozen F0 contract.** Confirm `MotifRetriever`/`MotifCandidate`/`MatchReason` signatures + the new config keys are as designed; reconcile any drift with F0 *before* coding (don't fork the contract). File the §8 F0-notes if the keys/fields aren't there.
2. **T2 — `engine/motif_embed.py` pure parts (RED→GREEN).** `_platform_embed_model`, `motif_summary_text`, `summary_hash`, `_build_query_text` + their unit tests (6.1, 6.3 model-resolution). No network yet.
3. **T3 — `embed_motif_summary` / `embed_query`** over the existing `embedding_client` (platform model, MD-1 owner). Test with a patched client recording the model used (`test_one_platform_model_for_all_vectors`, `test_query_and_motif_share_model`).
4. **T4 — `reembed_in_tx`** (4.2) + `test_reembed_transactional`, `test_reembed_skips_when_hash_unchanged` (fake conn recording statement order). This is the data-R8 guard — write the test first, watch it fail on a naive 2-statement version, then make it one-statement.
5. **T5 — `motif_retrieve.py` `_fetch_candidates`** (the §2.2 SQL) + `test_prefilter_bounds_the_load`, `test_tier_predicate_matches_get_visible`. The data-R1 guard.
6. **T6 — `retrieve()` scoring + rank + tie-break + min_score** (§2.3) + `test_cosine_ranks_correctly`, `test_min_score_floor`, `test_deterministic_tiebreak`, `test_no_embedding_in_result`.
7. **T7 — the two degrade branches** (4.3) + `test_query_embed_outage_degrades`, `test_write_embed_outage_fails_closed`.
8. **T8 — VERIFY:** run the full `test_motif_retrieve.py`; confirm the 4 eval-gate tests (6.5) green; record the live-smoke token (or its deferral) for the provider-registry embed hop.
9. **T9 — hand the embed seam to W1:** confirm W1's create/clone/patch call `embed_motif_summary` / `reembed_in_tx` (a contract test at the W1↔W3 seam — W1 owns the call site, W3 owns the helper). Note in SESSION_HANDOFF that `D-MOTIF-PGVECTOR-TRIGGER` (Perf) is the documented brute-force ceiling.

**Disjointness check:** W3 writes only `db/repositories/motif_retrieve.py`, `engine/motif_embed.py`, `tests/unit/test_motif_retrieve.py`. It *reads* F0's schema/models/config and the existing `embedding_client`/`references` as patterns. The W1↔W3 seam (W1 calls W3's embed helpers) is the one cross-WS contact point — frozen as a function signature in this doc (4.2), so W1 and W3 build concurrently. ✅
