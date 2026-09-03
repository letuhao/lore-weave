# RT1 — identity and search · red team on **A3** and **A5**

**Mandate:** falsify, not grade. `DESIGN-HYPOTHESIS.md` §3.
**Assumptions attacked:** **A3** (text-in capabilities eliminate id-resolution failure *by
construction*) · **A5** (id-requiring reads collapse to one universal search per domain, returning
references not content).
**Method:** repo-grounded. Every factual claim below carries `file:line`. Claims are tagged
**[M] MEASURED** (a number that already exists in this repo's code, tests, evals or production
autopsy) or **[I] INFERRED** (a reading of code whose consequence has not been measured).
**Baseline read:** `DESIGN-HYPOTHESIS.md`, `SPEC.md` §1.0 + §1.4, `poc/P1-P2-findings.md` P8/P15/P16.

---

## 0 · The one-paragraph verdict

**A3's mechanism is already shipped in this repository, for the exact argument the design cites as
its worst case, and the production number it points at was measured over a corpus that includes the
period after it shipped.** `ambient_book` (2026-07-22, `575ad5f38`) plus the schema projection that
*deletes* `book_id` from the advertised schema (2026-07-27, `820cbdd72`) is A3, implemented, for
`book_id`. That makes A3 **cheaply testable rather than speculative** — and it also means the
design's headline evidence (57% id failures / 57% id-demanding surface) cannot be read as support
for A3 until it is split by whether the tool was `ambient_book` and by whether the call predates the
projection. **A5 is in worse shape: the "search returns references, model fetches what it needs"
pattern is shipped end-to-end for the glossary domain — `glossary_search` → `glossary_get_entity` —
and the second hop was measured at 14/197 = 7% success.** The falsifier A5 names for itself
("a reference that is not actionable without a second id-requiring call") is not hypothetical; it is
the current, measured, worst-performing read pair in the catalog.

| id | assumption | verdict |
|---|---|---|
| RT1-01 | A3 | **WOUNDS** — the mechanism exists and is testable; the cited evidence does not yet isolate it |
| RT1-02 | A3 | **KILLS (as stated)** — the named sub-agent boundary has no catalog; it re-runs the same model against the same id-demanding tools, capped at 4 iterations |
| RT1-03 | A3 | **KILLS** — resolution already relocated *and already fails silently*: a non-UUID arg is overwritten with the session's id, producing a wrong-object success |
| RT1-04 | A3 | **KILLS** — the repo's one real internal name→id resolver has a measured, named failure on live Vietnamese data, and its failure mode is **mint**, not error |
| RT1-05 | A3 | **WOUNDS** — a name is not an identity here: identity is `hash(user, project, name, kind)`; a text-in capability must also resolve `kind`, which is itself an open refactor |
| RT1-06 | A5 | **KILLS** — the reference→second-call hop is shipped and measured at **7%** |
| RT1-07 | A5 | **KILLS** — the universal search is itself id-gated: both candidate implementations take `book_id` as a required path UUID |
| RT1-08 | A5 | **WOUNDS** — composite keys are real and cross-service; one reference from one domain cannot key the next call |
| RT1-09 | A5 | **WOUNDS** — no search spans the stores; scope/permission filtering silently *narrows* the corpus rather than erroring |
| RT1-10 | A5 | **WOUNDS** — on the primary (CJK/Vietnamese) corpus the ranking leg is inert by design and the repo ships two contradictory answers for one table |
| RT1-11 | A5 | **WOUNDS** — the "39 id-requiring reads" denominator does not reconcile with a direct census (64 of 98 read tools require a UUID) |
| RT1-12 | A5 | **KILLS (as named)** — this repo shipped a "universal find tool", observed the false-negative it causes, and retracted the claim in writing on 2026-07-24 |
| RT1-13 | A5 | **KILLS** — `glossary_search` advertises natural-language input; its NL path AND-combines tokens, misses, and falls through to *most-recently-edited* |
| RT1-14 | A5 | **WOUNDS** — semantic tenant scoping is a post-filter over a fixed ×10 oversample; a busy graph silently under-returns |

---

## 1 · Attacks on **A3** — does resolution disappear, or relocate?

### RT1-01 — A3 is not a new idea here. It shipped for `book_id` eleven days ago. **[M]**

The design states A3's mechanism as *"Resolution moves inside, where the code has the catalog"* and
its illustration as *"cannot fail with 'invalid chapter_id', because the caller never supplies one."*

That is `ambient_book`, and it is in the tree three ways:

1. **The meta flag and envelope resolution** — `services/glossary-service/internal/api/mcp_server.go:57`
   (`glossary_search`), `:74` (`glossary_get_entity`), `services/book-service/internal/api/mcp_server.go:259`,
   `services/composition-service/app/mcp/server.py:603`. Commit `575ad5f38`, 2026-07-22:
   *"realize the X-Book-Id win — model omits book_id, envelope resolves it."*
2. **The schema projection that removes the argument entirely** —
   `services/chat-service/app/services/stream_service.py:1272-1294`. Its docstring is A3's own
   argument, written from a live failure:

   > *"on a BOOK-BOUND session, an `ambient_book` tool's advertised schema drops `book_id` entirely
   > … A weak model shown a book_id property treats it as a demand and stalls hunting for the id …
   > **Absent from the schema, the belief cannot form.**"*

   Commit `820cbdd72`, 2026-07-27.
3. **A studio single-book override for the tools that are *not* ambient** —
   `stream_service.py:1622-1645`, commit `28e784a4d`, 2026-07-25.

**Why this wounds A3 rather than supporting it.** The design's evidence for A3 is
`poc/P1-P2-findings.md` P8: 960 of 1,688 real tool errors are id-resolution, `book_id` the
second-worst argument at 182 occurrences. That corpus is *all* 7,442 calls ever made
(`poc/P1-P2-findings.md:53`), which spans both sides of 2026-07-22 and 2026-07-27. **The design cites
a number that already contains the treatment as evidence that the treatment will work.** Until it is
split, A3 is untested in the one place it has already been tried.

**[I]** Note also the boundary condition the mechanism carries: `ResolveBookScope` fail-closes when
there is neither an arg nor an ambient book (`mcp_tools_structure.go:169-173`,
`glossary-service/internal/api/mcp_server.go:437-441` → `"book_id is required (a UUID)"`). Ambient
resolution only removes the id where a **single-valued session binding** already exists. It does not
generalise to "the second chapter", to a cross-book request, or to any surface without a studio.

---

### RT1-02 — the sub-agent the design names as the existing boundary **has no catalog**. It is the same model, with fewer tools and four turns. **[M]**

`SPEC.md:174-175` and `poc/P1-P2-findings.md` P15 both rest A3/A4 on:

> *"the sub-agent boundary already exists: `subagent_runtime.py`'s `tool_scope` is the only place in
> this repo where a capability genuinely owns a tool whitelist."*

Read what it actually does. `services/chat-service/app/services/subagent_runtime.py:102-120`:

```python
def resolve_scoped_tools(catalog: list[dict], tool_scope: list) -> list[dict]:
    """The subagent's advertised tool set = the caller's full catalog INTERSECT
    the def's ``tool_scope`` globs (fnmatch) …"""
```

The sub-agent is handed **an fnmatch-filtered subset of the same MCP catalog** and a natural-language
`task` string (`subagent_runtime.py:159-163`). It is another LLM loop. It does not have a catalog in
the sense A3 needs ("the code has the catalog"); it has *fewer* of the same id-demanding tools, and:

- `SUBAGENT_MAX_ITERATIONS = 4` (`subagent_runtime.py:76`) — a resolution that today takes
  `tool_list` → `book_list` → `book_structure_read` → `book_get_chapter` has **no iterations left**
  for the actual job.
- `SUBAGENT_RESULT_CHAR_CAP = 4000` with silent truncation + a note (`subagent_runtime.py:71`,
  `:172-182`).
- `MAX_SUBAGENT_DEPTH = 1` (`:61`) — a capability cannot delegate resolution further.
- **A sub-agent cannot complete a gated write at all.** `stream_service.py:3992-4010`: a headless
  sub-run cannot raise an approval card, so any tool requiring approval or spend
  *"was NOT run"* and returns a `result.error`. Same at `:3799-3812` for `require_approval` hooks
  and `:3751-3755` for batch confirmation.

**Scenario that falsifies A3 as stated.** `run_book_edit("rename the second chapter of Mị Đế to
'Thần Hồn Quy Vị'")`. The capability's sub-agent must (a) resolve the book — ambient covers this only
inside a studio; (b) resolve "the second chapter" — `book_structure_read` returns
`structureChapterRef{ChapterID, Title, SortOrder}` (`mcp_tools_structure.go:379-383`), so the
sub-agent must pick by `sort_order`, which no tool filters on, from a page of up to 100
(`mcp_tools_structure.go:176`); (c) call the rename, which is a Tier-A write. Steps (a)–(c) are 3–4
tool calls against a 4-iteration cap, and (c) fails outright if the user has not pre-allowlisted it.
**Resolution did not move into code. It moved into a smaller, more constrained copy of the same
failing loop, behind a 4000-char truncating window — which is exactly A3's own stated blast radius:
"worse than today — the failure becomes unobservable."**

---

### RT1-03 — resolution has already relocated, and it already produces a **silent wrong answer**. **[M]** on the code, **[I]** on the rate

`services/chat-service/app/services/stream_service.py:1613-1621`:

```python
if isinstance(supplied, str) and not _is_uuid(supplied):
    logger.warning(
        "tool arg %s=%r is not a UUID — the model mistranscribed it; substituting the "
        "turn's known id", key, supplied[:64],
    )
    args_obj[key] = val_s
```

The loop runs for `("book_id", book_id), ("chapter_id", chapter_id), ("project_id", project_id)`
(`:1586`). So when the model sends `chapter_id="the second chapter"` — or `"placeholder_id_1"`, which
production shows it does 60 times (`poc/P1-P2-findings.md` P8) — the seam **replaces it with the
session's currently-bound chapter and the call succeeds.**

This is the A3 end-state, already built: no `invalid chapter_id` error, because the caller's id was
discarded. And it is precisely the failure A3 warns about in its own blast-radius line. An edit
intended for chapter 2 lands on whatever chapter the studio is bound to, the tool returns `ok=true`,
and **no error class in the P8 autopsy can ever contain it** — the autopsy counts `ok=false`.

**This is the single most important structural finding in this report:** the 57% number is a census
of *loud* failures. Every mechanism the design proposes converts loud failures into quiet ones. There
is currently **no counter of wrong-object successes anywhere in the repo** (searched: no
`scope_source` mismatch metric, no post-hoc "did the model mean this object" check; the only signal
is the `logger.warning` above, which is not aggregated).

---

### RT1-04 — the one real internal name→id resolver in this repo has a **named, measured failure on live Vietnamese data**, and its failure mode is *mint*, not error. **[M]**

`services/knowledge-service/app/extraction/entity_resolver.py` is the closest thing the repo has to
"resolution inside the code, with the catalog." It resolves an extracted name to an existing entity
via a glossary anchor index. Its own comment records the measurement
(`entity_resolver.py:216-219`):

> *"Because entity identity is hash(user, project, name, kind), that miss does not degrade to 'no
> anchor' — it **MINTS A SECOND NODE** beside the author's. Measured on the live Mị Đế chapter: Chân
> Linh, Vô Cấu Chân Linh and Thần hồn each forked a duplicate next to their anchored twins."*

Three named entities, one live chapter, on the dogfood book. And two more ambiguity behaviours in the
same file:

- `entity_resolver.py:143-151` — when two anchors fold to the same name within a kind, **the first
  one wins** and a WARNING is logged. Insertion order decides identity.
- `entity_resolver.py:153-159` — when a folded name maps to two anchors across kinds, **no fallback
  key is registered at all**; the name is simply unresolvable without a kind.

The glossary side confirms name→row is many-to-one *in the live data*: an entire remediation endpoint
exists to merge them — `services/glossary-service/internal/api/dedup_name_variants_handler.go:1-17`,
`POST /internal/books/{book_id}/dedup-name-variants`, grouping live entities by
`(kind, textnorm.Normalize(cached_name))` and merging every group of >1.

**Why the design's mitigation does not cover it.** A3 says the failure is eliminated because the
caller never supplies an id. But the failure here is not "the caller supplied a bad id" — it is
*"the name the user typed does not identify one object"*, which is a property of the request, and
A3's own falsifier says so: *"the ambiguity was never in the interface, it was in the request."*
This resolver is the proof that the ambiguity is in the request, and it is quantified: on the dogfood
book, an author-facing consequence has already been recorded — `DEBT-REGISTER.md` row
`2026-08-03-05` (`D-CANON-CHECK-BLIND-TO-ROLE`), where a `rival` **minted seven minutes earlier**
took the antagonist's defining act and the critic scored `canon_consistency = 5/5` on all three
chapters. That row explicitly notes *"Kind was correct on both entities — this is not a kind bug."*

---

### RT1-05 — a name is not an identity in this system. Text-in capabilities must also resolve `kind`, and `kind` is an **open refactor with no design**. **[M]**

`sdks/python/loreweave_extraction/canonical.py:194-227`:

```python
key = f"v{canonical_version}:{user_id}:{project_id or 'global'}:{kind}:{canonical}"
return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
```

Identity is `hash(user, project, name, kind)`. So `"update Phoenix's description"` is under-specified
by construction — `"Phoenix"` the `character` and `"Phoenix"` the `organization` are different nodes,
and the resolver's own comment uses that exact example (`entity_resolver.py:47-48`).

And `kind` is not a settled field:

- `docs/specs/2026-08-03-glossary-kg-entity-refactor/README.md:26` — *"it was whichever extraction
  batch named it first; **11%** of a measured book disagreed with the model's own modal answer."*
- Same file, `:8` — *"🔴 **NO DESIGN EXISTS**"* for the entity-consistency refactor as a whole.
- `DEBT-REGISTER.md` `2026-08-02-02`, `2026-08-02-04` — the KG-mirror and API/FE halves of the kind
  work are both open; **399 entities carry a facet and no consumer can see one.**

**[I]** A text-in capability therefore has to make a `kind` decision that this repo has an open
refactor about, with an 11%-disagreement baseline, and it has to make it *invisibly*. The design's
claim that resolution "moves inside, where the code has the catalog" assumes the catalog answers the
question. Here the catalog is the thing under dispute.

---

## 2 · Attacks on **A5** — do references collapse the reads, or move the id one hop?

### RT1-06 — A5's falsifier is not hypothetical. The pattern is shipped, and the second hop is measured at **7%**. **[M]**

A5's own falsifier: *"A reference that is not actionable without a second id-requiring call — which
reintroduces the 57% class one hop later."*

That is `glossary_search` → `glossary_get_entity`, and the tool description says so in the catalog —
`services/glossary-service/internal/api/mcp_server.go:60-63`:

> *"Fetch one glossary entity's full detail … **by id**, within a book. **Use after
> `glossary_search`** to read an entity in depth."*

- `glossary_search` returns references, correctly: ranked entities with id, name, aliases, kind,
  short description (`mcp_server.go:52-58`; output `searchToolOut{Entities: resp.Entities}` at
  `:459`, each carrying `EntityID` — `select_for_context_handler.go:50-56`). It is bounded
  (`:445-451`, default + max limit). **It is the A5 ideal, already built.**
- `glossary_get_entity` then hard-requires the UUID — `mcp_server.go:472-475`:
  `"entity_id must be a UUID"`.

Production, from `poc/P1-P2-findings.md` P8:

| tool | successes / real attempts | dominant error |
|---|---|---|
| `glossary_get_entity` | **14 / 197 (7%)** | — |
| `glossary_list_chapter_links` | **1 / 264** | 201× `entity_id must be a UUID` |
| `glossary_propose_entity_edit` | **0 / 101** | 66× `entity_id must be a real UUID, got 'place…'` |

**The design proposes, as the fix for the 39 id-requiring reads, the exact shape whose second hop is
the three worst-performing tools in the catalog.** A5's stated mechanism (grep/glob: search returns
locations, model fetches what it needs) is not a new architecture here — it is the current one, and
it is where the failures are concentrated.

**The unresolved question is *why* the second hop fails**, and it is decisive between two very
different repairs. Either (a) the model had the id on the wire and still sent a placeholder — in
which case A5 is dead and no amount of reference-shaping helps; or (b) the model never called the
search first — in which case A5 survives and the real fix is ordering/steering, which is far cheaper
than the proposed rebuild. **This is settleable from data already in Postgres.** See §4, POC-1.

---

### RT1-07 — the universal search is **itself id-gated**. Both candidate implementations require `book_id` as a path UUID. **[M]**

A5: *"One universal search per domain replaces 39 id-requiring reads."*

There are two real candidates in the tree and both take an id before they will search anything:

| candidate | file:line | required id |
|---|---|---|
| hybrid (lexical + semantic + rerank) | `services/knowledge-service/app/routers/public/raw_search.py:79-80` — `GET /v1/knowledge/books/{book_id}/search` | `book_id: UUID = Path(...)` |
| lexical only | `services/book-service/internal/api/search.go:246-251` — `GET /v1/books/{book_id}/search` | `parseUUIDParam(w, r, "book_id")` |

And the hybrid one takes a **second** optional UUID whose failure is silent-empty:
`before_chapter_id`, *"Unresolvable → fail-closed (no hits)"* (`raw_search.py:100-106`,
resolution at `:156-158`).

`glossary_search` escapes this **only** via `ambient_book` (`mcp_server.go:57`, resolution at
`:437-441`) — i.e. it is not id-free, it is id-free *inside a studio binding*, and it fail-closes
with `"book_id is required (a UUID)"` otherwise. **[I]** Therefore A5 does not stand on its own: it
is a corollary of A3's ambient mechanism, and it inherits every limit of it (single-valued binding,
no cross-book request, no non-studio surface).

**The scenario:** *"which chapter did Lâm Trạch set the trap in?"* asked from a plain chat session
with no studio binding. There is no id-free entry point to any content search in this repository.

---

### RT1-08 — composite keys are real, they cross service boundaries, and they are **27% of the read surface**. **[M]**

A direct census of the MCP read tools (all four core services read exhaustively; the tail swept):

| metric | count | share of 98 |
|---|---|---|
| read tools (unique names) | **98** | — |
| require ≥1 **UUID** | **64** | **65%** |
| **require a COMPOSITE key** (2+ ids that must agree) | **22 hard + 4 conditional = 26** | **27%** |
| take only names / slugs / free text / nothing | 34 | 35% |
| have any `limit`/pagination param | 37 | **38%** |

Per service: composition **11**, glossary **5**, book **3 hard + 3 conditional**, translation **2**,
jobs **1**, knowledge **1 mixed**.

Representative rows:

| call | file:line | key |
|---|---|---|
| `book_get_chapter` | `mcp_tools_read.go:227-228`, validated `:291-295`, enforced `:307-308` (`WHERE c.id=$1 AND c.book_id=$2`) | **(book_id, chapter_id)** |
| `book_list_revisions` | `mcp_tools_read.go:371-372`, `:395-399`, `:411-412` | **(book_id, chapter_id)** |
| `composition_get_outline_node` | `composition-service/app/mcp/server.py:718`, cross-project rejected at `:738` | **(project_id, node_id)** |
| `composition_find_references` | `…/server.py:6072` | **(book_id, entity_id)** — *two different services own the halves* |
| `composition_arc_template_drift` | `…/server.py:6906` | **(node_id, project_id)** and their *books* must match |
| composition error-block list | `…/server.py:7605-7611` — `"op=list requires chapter_id"` | **(project_id ambient, chapter_id)** — `chapter_id` is a **book-service** id |
| `jobs_get` | `jobs-service/app/mcp/server.py:295` | **(service slug, job_id)** — 19 real attempts, **0 successes** (P8) |
| `kg_entity_edge_timeline` | `knowledge-service/app/mcp/server.py:866` | **(entity_id UUID, edge_type code)** — the code must exist on that entity |
| `book_structure_edit op=reorder_chapters` | `mcp_tools_structure.go:359` — *"the COMPLETE new order for one language track, each active chapter once"* | **N chapter UUIDs, exhaustive and exact** |

**Three consequences A5 has no account of:**

1. **`project_id` + X is the dominant composite** — 8 of composition's 11 pair `project_id` with a
   second opaque UUID, and the handlers explicitly reject a mismatched pair
   (`server.py:738`, `:889`). A search hit returning only `node_id` is unusable.
2. **`book_id` and `project_id` are different keys with no free conversion.**
   `composition_get_work` (`composition-service/app/mcp/server.py:588`) is the **only** bridge, and
   its own description says so verbatim: *"a book_id is NOT a project_id."* Any unified reference
   must carry **both axes**, or every hit costs an extra round-trip — which is itself an
   id-requiring call.
3. **Cross-service composites cannot be produced by any one domain's search.**
   `composition_find_references` needs a book-service id and a glossary-service id in the same call.
   **A "one search per domain" surface produces a reference in domain A that is a required key in
   domain B.**

And `reorder_chapters` is a case no reference-shaped read can serve at all: the model must hold *the
complete active set* of chapter UUIDs, in order, each exactly once — structurally incompatible with a
bounded, ranked, top-K search result.

**[I]** The paging gap compounds it: **62% of read tools have no `limit`**, and outside book-service a
limit that does exist usually truncates **with no cursor** (`translation_list_versions`,
`translation_job_status`, `jobs-service` excepted — it has `limit` + `cursor`,
`jobs-service/app/mcp/server.py:175`). A reference-based design needs page 2 to exist; on most of
this surface it does not.

**[I]** The lexical hit envelope makes the composite worse rather than better: `buildLexicalHit`
returns `chapterId` but **no `bookId`** (`search.go:345-362`). The model must carry the `book_id` it
passed into the search back out to use the result — which is exactly the "remember an id across
turns" task the P8 data says it cannot do.

---

### RT1-09 — no search spans the stores; and permission/scope filtering silently **narrows** rather than errors. **[M]**

**The store map, measured. [M]**

| store | what it holds | searchable? |
|---|---|---|
| Postgres — **~25 per-service logical DBs**, one server (`infra/docker-compose.yml:16-18`, DSNs at `:99,167,215,342,405,438,475`) | manuscript prose (`chapters`, `chapter_blocks`, `chapter_revisions.body` JSONB), glossary entities, chat messages, composition, jobs | yes, but **per-DB only — no cross-DB join is possible** |
| Neo4j | `:Entity`, `:Event`, `:Fact`, `:Passage` — and it is simultaneously the **graph**, the **vector** and the **CJK lexical** store (5 dim-routed cosine vector indexes, `app/db/neo4j_schema.cypher:309,318,327,336,345`; CJK full-text index at `:370-372`) | yes |
| MinIO / S3 — 7 buckets (`infra/docker-compose.yml:172,499,686,1007,1312,1454`) | **original uploaded import files, media, audio, cold event archives — not prose** (`book-service/internal/api/import.go:135-139`, `media.go:28`) | **no. Zero code paths query object storage by content**; the only `list_objects` is a GC reaper (`lore-enrichment-service/app/storage/minio_client.py:75`) |
| vector | **three mutually incompatible implementations**: Neo4j native indexes; composition `REAL[]` columns scanned by **brute-force cosine in Python** (`app/db/repositories/references.py:195-215`, `motif_repo.py:901`); lore-enrichment stdlib cosine (`app/retrieval/store.py:98,463`). **No pgvector in any product DB** — explicitly declined (`composition-service/app/db/migrate.py:596-602`, `lore-enrichment-service/app/retrieval/store.py:17`) | partially |

**Good news for A5, stated plainly:** the object-storage leg of the design's stated problem
(*"the corpus is Postgres + Neo4j + object storage + vector"*, `DESIGN-HYPOTHESIS.md` A5) is
**smaller than assumed** — prose lives in Postgres, and nothing needs to search S3.

**Bad news:** the **only** cross-store search is `run_hybrid_search`
(`services/knowledge-service/app/search/retriever.py:226`), which fuses three legs — book-service
Postgres lexical over HTTP (`:256`), Neo4j CJK full-text (`:268`), Neo4j vector (`:299`) — inside
**one book**. Nothing spans glossary + chapters + KG + chat. And the fusion is **RRF (rank-based)
precisely because the legs' scores are incomparable** (`app/search/hybrid_fusion.py:1-6`).
**[I]** A single search returning ranked references *across* stores would have to invent a shared
score scale that this repo has twice concluded does not exist — once in `hybrid_fusion.py`, once in
the calibration finding at `retriever.py:56-60` (*"NO global cosine threshold cleanly drops junk"*,
`MIN_RELEVANCE_DEFAULT = 0.0`). Junk rejection is done by a cross-encoder reranker that is **BYOK and
optional**, degrading to `"not_configured"` (`retriever.py:357-368`) — so on an unconfigured account
the universal search's ranking *is* raw RRF.

**Scope filtering narrows silently.** `raw_search.py:130-137`:

```python
# A non-owner asking surface=all is silently downgraded to canon — drafts are
# private-until-published, never exposed to shared users.
effective_surface: Surface = (
    "all" if (surface == "all" and caller == project.user_id) else "canon"
)
```

And the corpus is not even complete for the owner: **draft chapters are absent from semantic search
until a separate, owner-only, explicit indexing call** — `POST /books/{book_id}/index-drafts`
(`raw_search.py:189-243`), which additionally 409s when the project has no embedding model
(`:230-233`) or Neo4j is unset (`:234-238`). Grant failure returns a uniform 404 `not_indexed`
(`:124-130`) — deliberately indistinguishable from "this book was never indexed".

**Why this breaks A5 specifically.** A5's contract is *"search returns locations; the model fetches
only what it needs."* If the search silently returns a **narrower corpus** than the caller asked for —
canon-only instead of all, or an unindexed book that answers 404-as-not-indexed — then the model's
correct conclusion from an empty result ("it does not exist") is wrong, and there is no signal
distinguishing *absent* from *out of scope* from *not indexed*. The design's error contract (R10, 4
classes at the raise site) does not reach this: **these are successes with empty result sets, not
raises.** Same class as RT1-03.

---

### RT1-10 — on the primary corpus the ranking leg is inert by design, and the repo ships **two contradictory answers for one table**. **[M]**

This product's corpus is CJK + Vietnamese (`封神演義` dogfood, `万古神帝` eval corpus, `Mị Đế`).

**The ranking leg does not work on short CJK terms, and the code says so.** `search.go:25-28`:

> *"exact-substring (ILIKE, `$3` = escaped pattern) is the **PRIMARY** matcher: it catches short CJK
> terms the trigram `%` operator misses at the default `similarity_threshold`; `similarity()` only
> **ranks**."*

Identical language on the glossary side (`entity_search.go:12-17`,
`glossary-service/internal/migrate/entity_search.go:14`).

**The repo already fixed this — for passages only, and the fix cannot reach the glossary. [M]**
`services/knowledge-service/app/db/neo4j_schema.cypher:355-372` states the diagnosis and the
remedy:

> *"trigram ranking is noise on CJK and a GIN-trigram index can't accelerate a 2-char query, so a
> short Chinese proper-noun keyword search has poor recall (**V6 FAIL**). Neo4j ships a built-in
> `cjk` analyzer … (**Postgres zhparser/pg_jieba are NOT, so they'd need an infra change**). So the
> CJK-tokenized lexical leg lives HERE, over the same `:Passage` nodes…"*

`passage_text_cjk_ft` is therefore the **only CJK-correct lexical index in the system**, and it
covers `:Passage` — manuscript prose. **Glossary entities live in Postgres and have no equivalent.**
So the search over the objects a text-in capability most needs to resolve — named entities — is
precisely the one the repo has documented as CJK-broken and declined to fix, because fixing it needs
an infra change.

**[I]** Consequence: for a two-character
Chinese name the trigram leg contributes nothing, so entity/chapter search degenerates to *exact
substring*. No typo tolerance, no partial-name match, no alias morphology. A text-in capability whose
resolution step is "search for the name the user typed" therefore requires the user to type the name
**exactly** as stored — which is the same demand as supplying an id, one abstraction layer up.

**The write path folds names; the search path does not. [M]** This is the sharpest i18n asymmetry
found. Identity-time canonicalisation applies NFKC + Unicode casefold + CJK traditional→simplified +
a 60-entry honorific strip covering Japanese `様/さん/先生`, Chinese `大人/公子/夫人/师父`, Korean
`님/씨/선생님`, Vietnamese `ông /bà /cô /thầy ` (`canonical.py:55-122`, `:130-166`), and the glossary
even maintains a folded `normalized_name` column, re-stamped by the dedup remediation
(`dedup_name_variants_handler.go:13-16`).

**The search leg queries none of it.** `entity_handler.go:709-713` matches raw
`e.cached_name` / `glossary_aliases_text(e.cached_aliases)` via ILIKE + `%` trigram — no fold, no
`normalized_name`, no honorific strip. The same file's own comment notes the FTS alternative is
unusable here: *"search_vector's 'simple' FTS config can't segment CJK"* (`:695-696`).

**[I]** Consequence for A5: a user who types `王大人` cannot find the entity the write path
deliberately stored as `王`; `ông Nam` cannot find `Nam`; a traditional-form query cannot find a
simplified-form row. **The system knows these are the same entity — it hashes them to the same
`canonical_id` — and its search cannot tell.** A text-in capability that resolves by searching
therefore fails on exactly the surface forms the identity layer was built to unify.

**The semantic leg's score is not separable on this corpus. [M]**
`docs/sessions/SESSION_ARCHIVE.md:1737`:

> *"bge-m3 cosine here is compressed [0.68–0.82] with poor neg/pos separation (**封神榜 0.733 > a real
> positive 0.706**) → **no global threshold cleanly filters junk**; floor OFF by default."*

**Measured recall ceilings. [M]** `docs/plans/2026-06-08-raw-search-e5-tuning.md:4` — lexical
oracle-recall **0.63**; after the E5 tuning pass, `SESSION_ARCHIVE.md:1737` — lexical oracle-recall
**0.953** isolated, hybrid recall@10 **0.94** on the original golden set but **0.86** on the broader
33-query set, *"wide terms cap it"*. So the best-measured search in this repo tops out around
0.86–0.94 recall. **[I]** Replacing a deterministic `get(id)` (recall 1.0 when the id is right) with
a 0.86-recall search is a correctness regression on every read where the id *was* obtainable.

**Two contradictory searches over one table. [M]** `chat_messages` has both:

- `services/chat-service/app/db/conversation_search.py:9-14` — ILIKE substring, with the reason
  spelled out: *"this is a multilingual novel workspace, and a recovery query is almost always a NAME
  (`Lâm Uyển`, `万古神帝`) that English FTS stems/tokenizes wrong."*
- `services/chat-service/app/routers/sessions.py:197-211` — `to_tsvector('english', m.content) @@
  plainto_tsquery('english', $2)`, with an `'english'` GIN index at
  `services/chat-service/app/db/migrate.py:88` and an `'english'` `ts_headline` snippet.

One of these is documented in this repo as wrong for this corpus, and it is the one serving
cross-session search. **"One universal search per domain" requires picking one answer per domain;
this repo currently holds two mutually exclusive answers for a single table, and has not noticed.**

---

### RT1-11 — the number A5 is sized against does not reconcile with a direct census. **[M]**

`SPEC.md:182-183` and `poc/P1-P2-findings.md` P15 size the work as **"the 39 id-requiring reads"**,
from a stated 80 Tier-R reads out of 198 non-retired tools.

A direct census of the tool registration sites (RT1-08) finds **98 read tools, 64 of which require at
least one UUID** — 27 of the 98 carry `visibility:legacy`, so even excluding every legacy tool the
non-legacy id-requiring read count is well above 39.

The two counts are not obviously reconcilable (different denominators: "non-retired" vs "registered",
"Tier-R" vs "read-shaped"), and RT1 does not claim the POC is wrong. **The point is that this is the
fourth mutually inconsistent tool count in a spec whose §1 opens by citing "4 mutually inconsistent
tool counts" as the defect it exists to fix** (`SPEC.md:16-17`). A5's feasibility claim ("~20 tools
is reachable") is arithmetic over a denominator nobody can currently reproduce.

**Cheapest observation:** derive the read count from the generated manifest R1 already requires
(`SPEC.md:318`) rather than from a hand count — and make the number a CI artifact, per the standing
rule that a coverage denominator must come from the SSOT and not from what you built.

---

### RT1-12 — this repo **already shipped a "universal find" tool, and retracted the claim in writing**, for the exact reason A5 must defend against. **[M]**

`services/knowledge-service/app/mcp/server.py:368-379` — the comment above `story_search`:

> *"K26 (2026-07-24) — was **'the universal find tool'**, which **over-claimed cross-store reach it
> does not have**: this searches MANUSCRIPT PROSE only. A model reading 'universal find' would use it
> to look for a character and, getting prose hits, **conclude it had searched everything** — never
> calling `glossary_search` / `memory_search` (**a false negative**). … Scope restored + an explicit
> redirect to the sibling stores."*

The description was then rewritten to lead with **"Search the book's MANUSCRIPT PROSE"** (`:378`).

This is the strongest single piece of counter-evidence in the report, because it is not RT1's
inference — it is a decision this team already made, eleven days ago, after observing the failure.
**A5 proposes to re-create the tool that was deliberately un-created.** The design's phrase is *"one
universal search per domain"*, which is *narrower* than what was retracted — but the retraction's
mechanism (a model that gets hits concludes it has searched everything and stops) applies to any
search whose name implies more reach than it has, and RT1-08 established that the domains have keys
that cross each other.

**Cheapest observation:** none needed. This is settled; it should be cited in the spec as a
constraint on how a consolidated search may be *named and described*, not re-derived.

---

### RT1-13 — `glossary_search` is advertised as natural-language, and its natural-language path returns **the most recently edited entities**. **[M]**

`glossary_search`'s description (`glossary-service/internal/api/mcp_server.go:53-57`):

> *"Search a book's glossary for entities … by name, alias, or **natural-language terms**."*

Its handler runs `selectGlossaryForContext` (`mcp_server.go:454-459`), a four-tier cascade
(`select_for_context_handler.go:252`): **pinned → exact → FTS → recent**. The FTS tier is
`plainto_tsquery('simple', …)` (`select_for_context_handler.go:482,488`), and Postgres
`plainto_tsquery` **AND-combines every token**. The failure is documented, with this exact example,
at `services/knowledge-service/app/context/selectors/glossary.py:9-20`:

> *"`"Tell me about Kai"` → `tell & me & about & kai`. For an entity whose search_vector contains only
> `kai` … **the user asking a natural-language question gets zero FTS hits and falls through to the
> recent-edited tier — a clear quality loss, masked only by pinned entities.**"*

And the fall-through is unconditional on emptiness — `select_for_context_handler.go:349-354`:

```go
// Tier 3 recent fallback: only when no query was given (general snapshot) or
// a query produced zero results (avoid an empty context).
if !hadQuery || len(selected) == 0 {
```

**So the domain search the design wants to be the id-free entry point answers a natural-language
question with the book's most recently edited entities.** Not an error, not an empty list — a
plausible, ranked, wrong answer. Same class as RT1-03 and RT1-09: the mechanism converts a loud
failure into a quiet one.

**In fairness:** the row *does* carry `tier` and `rank_score`
(`select_for_context_handler.go:111-112`), so the signal `tier:"recent"` reaches the model. But the
tool description documents neither field, so nothing tells the model what to do with it — and
`DESIGN-HYPOTHESIS.md`'s own framing is that an unexplained signal is not a signal.

Two aggravating facts:

- **knowledge-service already built a client-side workaround** rather than fix the tier: extract
  proper nouns from the message and issue **one call per candidate**
  (`selectors/glossary.py:21-25`). That is *N* id-free calls to answer one question — the opposite of
  the consolidation A5 promises.
- **The MCP tool takes the broken path while a working one exists in the same service.** The HTTP
  entity list has a trigram/ILIKE `search_mode=raw` leg that is explicitly CJK-safe
  (`entity_handler.go:687-696`, `:707-727`); `glossary_search` does not use it.

**Cheapest observation:** call `glossary_search` on the dogfood book with (a) a bare name and (b) the
same name inside a sentence, and compare `tier` on the returned rows. Two calls. If (b) comes back
`tier:"recent"`, A5's id-free entry point is confirmed to answer natural language with noise.

---

### RT1-14 — tenant scoping in the semantic store is a **post-filter over a fixed oversample**, so a busy graph silently under-returns. **[M]** on the mechanism, **[I]** on the incidence

Neo4j vector and full-text indexes are **global** — they cannot be pre-filtered by tenant. Every
semantic read therefore oversamples ×10 and filters afterwards:

`services/knowledge-service/app/db/neo4j_repos/passages.py:650-663`:

```cypher
CALL db.index.vector.queryNodes($index_name, $oversample_limit, $query_vector)
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  …
  AND ($include_drafts OR coalesce(node.canon, true) = true)
```

Same shape for the CJK full-text leg (`passages.py:825-836`) and for `:Entity`
(`entities.py:1294-1321`). The default is stated at `passages.py:730-737`:
*"Vector indexes are global in Neo4j — we oversample by 10× then post-filter on tenant scope."*

**[I]** With one tenant this is invisible. With a populated multi-tenant graph, the ×10 window can be
consumed entirely by other tenants' passages before the `WHERE` runs, and the call returns **fewer
hits than exist, with no error and no indicator**. Nothing in the code compensates — no adaptive
oversample, no "the filter consumed the whole window" signal.

**Why this specifically breaks A5.** A5's contract is that the model reasons over what search
returned. Under this mechanism, an empty or short result set is not evidence of absence; it can be
evidence of *neighbours*. Combined with RT1-09's silent surface downgrade and RT1-13's recent-tier
fallback, the universal search has **three independent ways to be quietly wrong** and no way to say
so — while R10's error contract, the design's answer to unactionable failures, only governs raises.

**Cheapest observation:** run the same `story_search` query twice on the dogfood project — once as
is, once with `oversample_factor` raised to 100 — and diff the hit count. One parameter, one run. If
the counts differ, the design must add "result completeness" to the reference contract, alongside
"references not content" and "a hard cap".

---

## 3 · What the attacks do *not* kill

Stated so the report is not one-sided:

- **The reference shape is right and already exists.** `book_structure_read` returns
  `structureChapterRef{ChapterID, Title, SortOrder}` with real paging
  (`mcp_tools_structure.go:379-383`, `:175-176`), and `glossary_search` returns bounded ranked
  references (`mcp_server.go:445-451`). A5's *output* contract is achievable; it is the *input*
  (RT1-07) and the *next hop* (RT1-06, RT1-08) that fail.
- **A name-addressed read already exists and is not on the failure list.**
  `memory_recall_entity` takes `entity_name` — a plain string, no UUID
  (`services/knowledge-service/app/mcp/server.py:473`), as does `memory_timeline`'s optional
  `entity_name` (`:497`). Neither appears among P8's twelve 0%-success tools. **[I]** That is the
  closest thing to positive evidence for A3/A5 in the repo, and it is worth measuring properly rather
  than asserting: see POC-6. Note the whole of knowledge-service is composite-free precisely because
  `project_id` is ambient everywhere (`_PROJECT_ID_ARG`, `server.py:176`) — i.e. the domain that
  looks most like A5's target is the one that already adopted A3's mechanism universally.
- **The choke risk is genuinely not intrinsic**, as `poc/P1-P2-findings.md` P16 says: p50 171 tokens,
  and the hazard concentrated in the 18/36 tools with no `limit` and 14 grandfathered offenders.
  RT1 found nothing to add against that; it is the strongest-supported part of A5.
- **`ambient_book` is a real, cheap win** and RT1-01 attacks the *evidence*, not the mechanism. If
  POC-2 below comes back showing ambient tools have a materially lower id-error rate, A3 gets a
  genuine measured leg — and a much cheaper implementation path than the full rebuild
  (see §5).

---

## 4 · The cheapest observations — POC candidates

Ordered by decisiveness per unit cost. **POC-1 and POC-2 are pure SQL over data that already
exists** (`chat_messages.tool_calls` JSONB carries `tool`, `args`, `ok`, `error`, `result` per call —
persisted at `stream_service.py:6524-6525`, read pattern given in `poc/P1-P2-findings.md` §4). No
code change, no model run, no product risk.

### POC-1 — settles **A5** outright. Cost: one query.
**Question:** when `glossary_get_entity` failed on `entity_id`, was a usable id already on the wire?

For every failed `glossary_get_entity` / `glossary_list_chapter_links` / `glossary_propose_entity_edit`
call, look back in the **same session** for an earlier successful `glossary_search` and ask whether
its `result` contained any `entity_id`.

- **Reference was present, model still sent a placeholder** ⇒ **A5 is dead.** The references-out
  shape does not fix the class; the model cannot carry an id across a hop. Rebuild does not help.
- **No prior successful search in the session** ⇒ **A5 survives**, and the defect is *ordering* — the
  model does not search before fetching. Fix = steering / a rail step / folding the search into the
  fetch. Radically cheaper than the proposed architecture.

This is the highest-value single query available, because it discriminates between a structural fix
and a prompt-level fix on the design's own worst-performing tools.

### POC-2 — settles **A3**'s evidentiary problem. Cost: one query.
**Question:** did `ambient_book` reduce id-resolution failures where it shipped?

Split the 960 id-resolution errors three ways:
(i) before 2026-07-22 (`575ad5f38`) vs after 2026-07-27 (`820cbdd72`);
(ii) tool declares `ambient_book` vs not;
(iii) argument = `book_id` vs `entity_id` vs other.

A3 predicts `book_id` errors on `ambient_book` tools collapse to ~zero after 07-27 while `entity_id`
errors are unchanged. **If `book_id` errors persist on ambient tools after the projection shipped,
A3's mechanism has already been tried on the friendliest possible argument and failed** — and the
57%/57% coincidence in `SPEC.md:55-57` is not the support it is presented as.

### POC-3 — settles RT1-03, the wrong-object class. Cost: one grep of the app logs.
Count occurrences of `"is not a UUID — the model mistranscribed it; substituting the turn's known id"`
(`stream_service.py:1614-1617`) and of `"ambient_book tool got book_id=… != the studio's book"`
(`stream_service.py:1596-1599`), broken down by argument (`book_id` / `chapter_id` / `project_id`).

Every `chapter_id` hit is a **silent wrong-object success** that the P8 autopsy structurally cannot
see. If the count is non-trivial, then A3's blast-radius clause ("worse than today — the failure
becomes unobservable") is not a risk, it is the **current state**, and the acceptance criteria in
`DESIGN-HYPOTHESIS.md` §4 must include a wrong-object counter, not only an error-rate.

### POC-4 — settles RT1-02, the "resolution moves inside" mechanism. Cost: one scripted run, no build.
Take the existing sub-agent runtime as-is. Define one sub-agent with
`tool_scope = ["book_*"]` and run: *"rename the second chapter of Mị Đế to X"*, N=10.
Record: iterations consumed vs the cap of 4 (`subagent_runtime.py:76`), whether it identified the
chapter by `sort_order`, whether the write returned the `"was NOT run"` approval error
(`stream_service.py:3992-4010`), and whether the 4000-char cap truncated the answer.

**This is A3's mechanism, tested on A3's own illustration, using code that already exists.** If the
sub-agent cannot resolve "the second chapter" inside its iteration budget, "eliminated by
construction" is false and the design must name a *code* resolver, not a sub-agent.

### POC-5 — settles RT1-10 on the real corpus. Cost: 20 queries against the running stack.
Against `封神演義` or `Mị Đế`: run the existing golden set (`rawsearch_golden.json`) plus 10 hand-made
**2-character CJK** entity names and 10 Vietnamese names with diacritic/honorific variants
(`ông Nam` / `Nam`, `Lâm Trạch` / `Lâm trạch`) through `glossary_search`. Report recall.

A5 requires that a name typed by a user reaches the right entity. If 2-char CJK recall is materially
below the 0.86–0.95 Latin-ish figures already measured, the universal search cannot be the resolution
substrate for this product's actual corpus.

**And this POC has a fix attached before it is even run**, which makes it the cheapest *actionable*
item in the report: apply the fold that already exists to the query as well as the row —
match `canonicalize_entity_name(q)` against the `normalized_name` column the dedup pass already
maintains (`dedup_name_variants_handler.go:13-16`), instead of raw ILIKE on `cached_name`
(`entity_handler.go:709-713`). One `WHERE` leg, one column already populated, no new index semantics.
Whatever happens to A3/A5, this is worth shipping.

### POC-6 — the positive control A3/A5 currently lack. Cost: one query, same corpus as POC-1.
Compute per-tool real success rate for the **name-addressed** reads that already exist —
`memory_recall_entity` (`knowledge-service/app/mcp/server.py:473`), `memory_timeline` (`:497`),
`story_search` (`:371`), `memory_search` (`:432`), `conversation_search`
(`chat-service/app/db/conversation_search.py:27`) — and compare against the UUID-addressed reads in
the same sessions.

**Every other POC here can only falsify. This one is the only cheap way A3/A5 can be *supported*:**
if name-addressed reads materially out-succeed id-addressed reads on the same corpus, that is the
design's first piece of direct evidence, and it costs the same single query. Run it alongside POC-1.

### POC-7 — settles RT1-13, the id-free entry point. Cost: **two tool calls.**
Call `glossary_search` against the dogfood book twice: (a) `query="Lâm Trạch"`, (b)
`query="tell me about Lâm Trạch's role in the trap"`. Compare the `tier` field on the returned rows
(`select_for_context_handler.go:111`).

If (b) returns `tier:"recent"`, the domain search the design nominates as the id-free entry point
answers a natural-language question with *the most recently edited entities*. **This is the cheapest
observation in the whole report and it targets A5's core promise directly.** It also comes with its
own fix (route `glossary_search` through the `search_mode=raw` trigram leg that already exists at
`entity_handler.go:707-727`, or fold the query — see POC-5).

### POC-8 — settles RT1-14, result completeness. Cost: one parameter, one run.
Run the same `story_search` query on the dogfood project twice — once as is, once with
`oversample_factor` raised from 10 to 100 (`passages.py:730`). Diff the hit count.

If the counts differ, "how many results exist" is not answerable from the current search, and the
reference contract needs a **completeness** property alongside "references not content" and "a hard
cap" — because a model that reasons over an incomplete result set concludes absence.

---

### If only three are run

| order | POC | cost | what it decides |
|---|---|---|---|
| 1 | **POC-7** | two tool calls | whether A5's id-free entry point returns noise for natural language |
| 2 | **POC-1** | one SQL query | whether the reference→second-call hop fails *with* the reference on the wire — structural fix vs prompt fix |
| 3 | **POC-2 + POC-6** | one SQL query (same shape) | whether A3's mechanism, already shipped, worked — and the design's only available positive control |

POC-7 first because it is the cheapest and it targets the design's own leading claim. POC-1 second
because it is the only observation that discriminates between a rebuild and a steering fix.

---

## 5 · The most damaging finding: the cheap rival captures most of the value

`DESIGN-HYPOTHESIS.md` §3 explicitly invites this.

RT1-01 establishes that **A3, for `book_id`, is a 22-line schema projection plus a meta flag**
(`stream_service.py:1272-1294`; `WithAmbientBook` at each registration site). It required no new
architecture, no capability boundary, no sub-agent, and no retirement of the catalog.

The obvious rival to the whole rebuild is therefore:

1. **Extend `ambient_book` to `entity_id` and `chapter_id`** — an `ambient_entity` / `ambient_chapter`
   binding on the surfaces that already have one, with the same schema projection. `entity_id` is the
   worst-affected argument (431 occurrences, `poc/P1-P2-findings.md` P8), and `glossary_get_entity`
   already resolves book scope ambiently (`mcp_server.go:466-469`) — the pattern is in place.
   **[I]** This is bounded to entities the session is actually about, so it does not solve the general
   ambiguity of RT1-04/RT1-05 — but it targets the exact 431 + 182 = 613 of 960 errors that are
   `entity_id` + `book_id`.
2. **Fold the search into the fetch** — accept `name` on `glossary_get_entity`, resolve internally,
   and return a disambiguation list (not an error) when the name maps to >1. RT1-04 shows this
   collision is real; RT1-06 shows the pair already exists. This is one handler change per domain.
3. **Route `glossary_search` through the working leg** (RT1-13 / POC-7) and **fold the query the way
   the write path folds the row** (RT1-10 / POC-5). Two `WHERE` clauses, against the
   worst-performing read pair in the catalog.
4. **Pay down the 14 grandfathered `limit` offenders** (`poc/P1-P2-findings.md` P16), which is the
   whole measured choke hazard.
5. **Ship R10's error contract**, which nothing here contradicts.

**If POC-1 returns "no prior successful search in the session" and POC-2 returns "book_id errors
collapsed on ambient tools", then items 1–5 capture the measured value of A3 and A5 at a small
fraction of the cost, and the structural rebuild is unjustified on this evidence.** That outcome is
live and cheap to check, and it should be checked *before* the acceptance criteria in
`DESIGN-HYPOTHESIS.md` §4 are written, not after.

**One thing the rival does NOT capture**, and it should be said so the rival is not oversold: none of
items 1–5 touches RT1-03's wrong-object class or RT1-14's silent under-return. Those are not
regressions the new design introduces — they exist today — but every mechanism in *both* the design
and the rival converts loud failures into quiet ones, and **this repo currently counts only loud
ones**. Whatever shape wins, `DESIGN-HYPOTHESIS.md` §4's acceptance criteria must include at least
one **wrong-answer** counter, not only an error-rate. Otherwise A10 ("can we measure?") is false for
exactly the failures the new architecture creates, and the document's own dependency graph says that
makes everything below it unknowable.

---

## 6 · Ledger — measured vs inferred

| claim | tag | source |
|---|---|---|
| `ambient_book` + schema projection shipped 07-22 / 07-27 | **[M]** | `575ad5f38`, `820cbdd72`; `stream_service.py:1272-1294` |
| P8 corpus = all 7,442 calls, spans both sides of that ship date | **[M]** | `poc/P1-P2-findings.md:53`, `:10` |
| sub-agent = fnmatch subset of the same catalog, 4 iterations, 4000-char cap, cannot do gated writes | **[M]** | `subagent_runtime.py:71,76,102-120`; `stream_service.py:3992-4010` |
| non-UUID arg silently overwritten with the session id | **[M]** | `stream_service.py:1613-1621` |
| rate of wrong-object successes | **[I]** — no counter exists | POC-3 |
| internal resolver forked 3 named entities on a live chapter | **[M]** | `entity_resolver.py:216-219` |
| identity = `hash(user, project, name, kind)`; kind 11% disagreement; no design | **[M]** | `canonical.py:226`; `glossary-kg-entity-refactor/README.md:8,26` |
| `glossary_get_entity` 14/197; `glossary_list_chapter_links` 1/264 | **[M]** | `poc/P1-P2-findings.md` P8 |
| *why* the second hop fails | **[I]** — the decisive unknown | POC-1 |
| both universal-search candidates require `book_id` path UUID | **[M]** | `raw_search.py:79-80`; `search.go:246-251` |
| 98 read tools · 64 need a UUID · 26 need a composite · 37 have a limit | **[M]** — direct census of registration sites | RT1-08 table |
| `book_id` is not `project_id`; one bridge tool only | **[M]** | `composition/app/mcp/server.py:588` |
| composite + cross-service keys | **[M]** | `mcp_tools_read.go:227-228,307-308`; `composition/app/mcp/server.py:6072,6906,7605-7611` |
| "39 id-requiring reads" vs a 64-of-98 census | **[M]** on both counts, **[I]** that they conflict (different denominators) | `SPEC.md:182-183` vs RT1-08 |
| name-addressed reads exist and are absent from the 0%-success list | **[M]**; their success *rate* **[I]** | `knowledge-service/app/mcp/server.py:473,497`; POC-6 |
| non-owner `surface=all` silently downgraded; drafts unindexed by default | **[M]** | `raw_search.py:130-137,189-243` |
| trigram misses short CJK; ILIKE is the only real matcher there | **[M]** (stated in code) / **[I]** (recall on 2-char CJK unmeasured) | `search.go:25-28`; POC-5 |
| the CJK-correct lexical index exists for `:Passage` only; glossary entities have none, and the Postgres fix needs infra | **[M]** | `neo4j_schema.cypher:355-372` |
| cosine non-separable on CJK; recall ceilings 0.63 → 0.953 / 0.86 | **[M]** | `SESSION_ARCHIVE.md:1737`; `2026-06-08-raw-search-e5-tuning.md:4` |
| two contradictory searches over `chat_messages` | **[M]** | `conversation_search.py:9-14` vs `sessions.py:197-211` |
| write path folds names (60 honorifics, NFKC, T2S); search path does not | **[M]** | `canonical.py:55-166` vs `entity_handler.go:709-713` |
| "universal find tool" shipped, observed to cause false negatives, retracted 2026-07-24 | **[M]** | `knowledge-service/app/mcp/server.py:368-379` |
| `plainto_tsquery` AND-combines ⇒ NL query → 0 FTS hits → recent-edited tier | **[M]** | `select_for_context_handler.go:482,488,349-354`; `selectors/glossary.py:9-25` |
| Neo4j indexes global; ×10 oversample then post-filter | **[M]** | `passages.py:650-663,730-737,825-836`; `entities.py:1294-1321` |
| incidence of silent under-return from that oversample | **[I]** — no counter exists | POC-7 (RT1-14) |
| no search reads object storage; prose is in Postgres | **[M]** | `minio_client.py:75`; `import.go:135-139` |
| RRF exists because leg scores are incomparable; rerank is BYOK/optional | **[M]** | `hybrid_fusion.py:1-6`; `retriever.py:56-60,357-368` |
| a cross-store ranked reference needs a score scale that does not exist | **[I]** | inference from the two rows above |
