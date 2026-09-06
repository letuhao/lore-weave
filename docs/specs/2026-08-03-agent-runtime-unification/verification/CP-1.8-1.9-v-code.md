# CP-1.8 / CP-1.9 · V-CODE — verdict

*Artifact frozen at `1ab136b1c16c68a3889ddaab932343e11b3f58c1`. Verified at start and again before
writing this file; HEAD did not move. Fresh verifier, no authorship, commit messages and builder
notes not read. Everything below that says "measured" was executed in a sandbox against the source
tree; nothing live was run and no tracked file other than this one was written.*

---

## 1 · Verdict

| | claim | verdict |
|---|---|---|
| **U-1** | Unicode normalisation cannot silently delete a declaration from the wire; text is NFC-normalised at the point it enters the package | **FAIL** |
| **U-2** | a catalogue that fails to load registers the narrowing **and** tells the model | **FAIL** (both halves, on the production path) |
| **U-3** | skill vectors are never shared between two embedding models | **PASS** |
| **U-4** | one user's provider-availability signal never reaches another user's turn | **PASS** |
| **1.8a** | narrowing stages are data with pipeline stage kinds; `order_by` required before `top_k`/`take_while_budget` | **FAIL** (the ordering rule holds; the kind set is not closed) |
| **1.8b** | one canonical-serialisation implementation, gate-enforced | **PASS with a correction** — enforced by a test, not by the gate; the design says "gate" |
| **1.8c** | ambient reads confined to one named module, gate-enforced | **PASS with a residual** — one live in-package instance the gate is green on |

**Overall: FAIL.** Two of the four CP-1.9 claims are defeated by inputs that occur in production, and
one of them (U-2) is defeated by *statement ordering inside the fix's own file* rather than by
anything subtle. CP-1.8a's headline property — "no kind can express arbitrary logic" — is false by
two independent routes, both measured.

---

## 2 · The falsifier, per claim

A `PASS` below states what would have produced `FAIL` and how I searched for it.

### U-1 — FAIL

**What I looked for:** a string that reaches `_tool_tokens` (`tool_surface.py:109-110`,
`estimate_tokens(json.dumps(td))`) without passing `_nfc`. `_tool_tokens` serialises the **whole
tool definition**, so the subject is not "the description" — it is every string on the row.

**Found, measured.** `_nfc` is applied to exactly one of the three fields the door writes:

```
knowledge_client.py:637   "name": t.name,                                  ← not normalised
knowledge_client.py:640   "description": _nfc(t.description or ""),        ← normalised
knowledge_client.py:641   "parameters": _normalize_tool_parameters(...),   ← not normalised
knowledge_client.py:647-649  fn["_meta"] = dict(meta)                      ← not normalised
```

An external-MCP overlay tool (`u_`/`b_`/`s_` — the arbitrary third-party text `_nfc`'s own docstring
names as the live subject) whose **parameter-schema description** arrives decomposed:

```
schema desc NFC → _tool_tokens = 83
schema desc NFD → _tool_tokens = 91          (1.096×)
NFD synonyms in _meta            → 176       (2.1× the same tool)

budget = 88, competitor costs 87
  arrival=NFC → kept = ['u_viet_tool']
  arrival=NFD → kept = ['u_zzz_other']       ← the declaration is cut from the wire
```

Same tool, same words, no revision change, no budget change — deleted by encoding. That is exactly
the mechanism U-1 claims to have closed, reached through the two fields the fix did not touch. The
estimate is both the sort key (`tool_surface.py:194`) and the accumulator (`:197-201`), so the effect
is on *which* declarations survive, not on a number.

**Second entry point missed:** `manifest.load` — §0.14.2 names it explicitly as door (a) — performs
no normalisation (`manifest.py:227-228`, `validate_document` at `:231-279`). Measured: `id`, `kind`,
`lifecycle` and `admitted_against` are ASCII-constrained by the contract so they have no subject, but
**`owning_service` is not**: a row carrying `"chát-service"` in NFD loads, validates, and is stored
un-normalised — two `canon.digest` values for one visibly identical document, which is the
"drift check reports a change nobody made" failure §0.14.2 was written to prevent.

**Judging the tests.** `TestToolTextIsNormalisedAtIngestion` is better than most — it has a control
(`test_the_defect_is_real_before_asserting_the_fix`) and its fixture is genuinely decomposed, so it
avoids the "normalise your own fixture then assert equality" trap the prompt names. But:

* `test_non_strings_pass_through_untouched` (`test_knowledge_client.py:1568`) asserts that dicts and
  lists pass through **untouched**, with the docstring *"the schema carries dicts and lists."* The
  test names the exact gap and codifies it as correct behaviour. This is the stale-label pattern
  inverted: a test whose docstring identifies the unfixed subject.
* `test_the_ingestion_path_applies_it` (`:1574`) asserts `'"description": _nfc(' in src`. One
  occurrence satisfies it; there are six other `"description":` sites in the same file with no
  `_nfc` (`:713, :1004, :1011, :1107, :1111, :1151`). A substring wiring gate cannot count.

### U-2 — FAIL, both halves

**What I looked for:** the two halves separately, per hunting-ground 5 — and then whether the
recorder has a sink at the moment the failure happens.

**The recorder is correct. The wiring is arm-after-use.** The only three sites that arm the
request-scoped sink are `stream_service.py:5971`, `:6547` and `:8048`. The catalogue fetch and the
outage read are at `:5589` and `:5602` — **382 lines earlier, in the same function**
(`stream_response`, which calls `_emit_chat_turn` at `:6101`, so `:6547` is also downstream).
Executed:

```
get_tool_definitions at        [5589]
catalogue_outage_registered at [5602]
surface_withheld.set at        [5971]
sink armed before the fetch?   False
```

and end-to-end, reproducing `:5589 → :5602` in a fresh request context with the real client:

```
catalog: [] | _catalogue_outage: False
=> the model is told: False

# the same sequence with a sink armed first (what every test does):
outage: True | rows: [{'scope':'catalogue','stage':'catalogue_unavailable','reason':'...'}]
```

So on a real turn the row is **not written** and the notice at `:5814` **never renders**. The founding
defect — model says a withheld capability "does not exist at all" — is reproduced intact.

The comment at `stream_service.py:5964-5970` states the rule that this violates, in the imperative,
calling itself the sixth recurrence: *"THE SINK IS ARMED AT THE TOP OF THE TURN, not before the stage
someone happens to be fixing."* The seventh recurrence is 382 lines above the sentence forbidding it.

**Judging the tests.** Every U-2 test is either self-armed or source-textual, so none can see this:

| test | why it cannot fire |
|---|---|
| `test_the_record_carries_a_scope_and_no_tool`, `test_count_is_ABSENT…`, `test_a_per_declaration_record…`, `test_an_EMPTY_catalogue_is_not_an_outage` | each calls `surface_withheld.set(sink)` itself, then tests the recorder in isolation |
| `test_the_client_registers_on_a_real_failure_path` (`test_cp0_instrument.py:1378`) | asserts `src.count("self._register_catalogue_outage(") >= 2` — a substring count |
| `test_the_model_is_told_not_only_the_row` (`:1387`) | asserts the notice **string literal** is present in the module source |
| `test_the_stream_reads_the_record_rather_than_inferring` (`:1417`) | asserts the assignment **line text** is present |

Three of the four "wiring gates" are `in src` checks. They prove the code was typed, not that it runs.
The realistic defect shape that slips past them is the one that shipped: correct statements in the
wrong order.

**Two siblings, also unfixed.** `get_admin_tool_definitions` returns `[]` on failure with only a
`logger.warning` and no `_register_catalogue_outage` (`knowledge_client.py:705`), and the outage read
is explicitly gated `and not admin_context` (`stream_service.py:5588`) — so an admin turn has neither
half. The resume path fetches at `:8022` and has no `_catalogue_outage` telling at all.

### U-3 — PASS

**Falsifier searched for:** an input under which two distinct embedding models share one cached
vector set. `_get_skill_vectors` keys on `_skill_catalog_signature() + (model_source, model_ref)`
(`skill_router.py:130`) and the cache is a single slot compared for equality (`:131`), so a model
change forces a recompute; it cannot alias. `embedding_client.embed` forwards `model_source`/
`model_ref` on the wire (`embedding_client.py:120-126`), so the key names the model that actually
produced the vectors — the key is honest, not merely present.

**The tests are the good ones in this set.** `TestSkillVectorsAreNotSharedAcrossEmbeddingModels`
drives the real `route_additional_skills` through a stubbed client and asserts on **which model refs
were seen embedding**, not on a cache internal; `test_the_same_model_twice_still_hits_the_cache` is
the companion that rejects "key on everything, never hit". `TestSkillVectorCacheIgnoresDescriptionText`
was **renamed** when U-3 changed what it asserts, with the rename noted in the docstring — the
stale-label discipline the prompt asks about, honoured.

**Residual (not a falsifier of the claim as written).** The twin carried *two* fixes and only one was
ported. `tool_discovery` HIGH-2 removed `model_source`/`model_ref` from its signature because they
were *"the SAME turn-scoped chat-completion model values… most chat models can't embed, so that either
failed upstream… or risked an improvised vector from a model never meant to embed"*
(`tool_discovery.py:1660-1672`), replacing them with `_resolve_embedding_model(user_id)` (`:1263`).
`skill_router` still receives the session's **chat** model: `messages.py:368` →
`stream_service.py:5396` → `skill_registry.py:697` → `skill_router.py:130`. So U-3's key is honest
about a model that should not be embedding at all. Same erratum-not-applied-everywhere shape U-3
itself was, one level up.

### U-4 — PASS

**Falsifier searched for:** any read of the availability signal that is not keyed by the reading
turn's user, and any write that lands in a bucket another user reads.
`_catalog_meta: dict[str, dict]` (`knowledge_client.py:313`) is written under the same `cache_key` as
the tool definitions (`:657` / `:658`), read as `self._catalog_meta.get(user_id or "")` (`:767`), and
`user_id` has no default (`:744`). All four call sites pass the turn's `user_id`
(`stream_service.py:2952, 3032, 3059, 3326`). The `""` bucket is the overlay-free platform catalogue,
not another user's. `_admin_tool_definitions` is process-wide but does not vary by user, so it is not
a second instance of this class. I found no path on which user B reads user A's entry.

The test that rejects the *relocated* fix — `test_the_user_argument_has_no_default` — is the right
shape, and the `>= 4` call-site count is a substring check but a defensible one here because the
signature change makes a missed site a `TypeError`.

**Residual:** `_catalog_meta` is never invalidated or evicted. A failed fetch does not clear it
(`:653-658` run only on success), so during an outage `find_tools` reads that user's last *successful*
"everything is fine" signal. That is the user's own stale signal, not another's, so U-4's claim
survives — but the field it protects is wrong at exactly the moment it matters.

### 1.8a — FAIL

**The ordering rule holds and is well built.** `validate_pipeline` (`surface.py:235-251`) is called
at the top of `assemble` (`:329`), so rejection is at construction of the assembly, not at use.
Measured: `TopK` and `TakeWhileBudget` without a preceding `OrderBy` both raise; a missing ordering
field raises rather than falling back to id-order (`:184-189`); a missing `cost` raises (`:406-411`);
`id` is appended as the final component and not duplicated (`:174-177`); `cost` as primary is refused
(`:168-172`); the rank and the ordering key reach the record (`narrowing.py:65-77`, measured:
`{'tool':'t3','stage':'top_k','rank':3,'ordered_by':[['kind','asc'],['id','asc']]}`). Each of
§0.14.1a's checkable rules 2, 3, 4 and 6 is implemented and fires.

**The kind set is not closed, by two independent routes — both measured.**

*Route 1 — the pipeline is duck-typed, not kind-checked.* `_narrow`'s `else` branch calls
`stage.keep(row)` (`surface.py:417-420`) and `validate_pipeline` only `isinstance`-checks for
`OrderBy` and `RANK_DEPENDENT` (`:245-247`). Nothing anywhere requires a stage to be one of the six.

```python
class ArbitraryStage:                       # never imported from the package
    stage, reason = "custom", "because my lambda said so"
    def __init__(self, fn): self.fn = fn
    def keep(self, row): return self.fn(row)

SurfaceAssembler(doc).assemble(pass_number=1,
    pipeline=[ArbitraryStage(lambda r: r["id"] in ("t0","t2"))])
# → names=('t0','t2'), withheld=2, conservation law satisfied, validate_pipeline silent
```

`NarrowingRule(keep=Callable)` has not been removed. It has been un-named.

*Route 2 — `Filter.value: Any` re-admits arbitrary logic through Python's own protocols.* `keep`
dispatches to `in` and `==` (`surface.py:105-111`), both of which are user-overridable:

```python
class Regexish:
    def __contains__(self, x): return bool(re.match(r"^b", str(x)))
Filter("s","r", field="id", op="in", value=Regexish())     # a regex stage, zero new operators
#   keep({'id':'book_list'}) = True   keep({'id':'glossary'}) = False

class EqAnything:
    def __eq__(self, o): return str(o).endswith("_list")
Filter("s","r", field="id", op="eq", value=EqAnything())   # same, through __eq__
```

So `test_the_operator_set_is_closed` verifies a property that does not bound anything: the three
operators are closed, and the space of predicates they can express is not. §0.14.1's reasoning —
*"Regex or arbitrary comparison would re-admit the closure problem under a new name"* — is right about
the risk and wrong that a three-operator whitelist retires it.

**The test that was supposed to catch this cannot.** `test_no_stage_kind_carries_a_callable`
(`test_cp1_membrane.py:983`) asserts `"Callable" not in str(f.type)` over the six dataclasses' fields.
Measured, it sees `['str','str','str','str','Any']` — and a bare `lambda` is *storable* in `value`
(`Filter("s","r",field="id",op="eq",value=lambda r: True)` constructs). It cannot see either route,
because it inspects declared field types and both routes live in runtime values and in the dispatch.
This is hunting-ground 3 precisely: red-able for the shape injected (`keep: Callable[[dict], bool]`
as a *field*), blind to the shape that will occur.

**Content-addressability, the second stated justification, is also conditional.** *"A closure is not
content-addressable, so a pipeline built from closures has no identity"* (`surface.py:56-57`). Measured:
`canon.digest(asdict(TakeWhileBudget(...)))` works; `canon.digest` of a pipeline containing a
`Regexish` value raises `NotCanonicalisable`. The property holds only over the well-behaved subset,
and nothing digests a pipeline today.

**Vacuity, stated plainly.** `SurfaceAssembler`, all six kinds and `canon` have **zero production
callers** — measured by repo-wide search; every reference outside the package is in
`test_cp1_membrane.py`. That is expected at CP-1 (the manifest is empty by design) and is not itself
the finding. The finding is sharper: **a real manifest row cannot be ordered by any key the design
cares about.** Measured against `build([admit(...)])`:

```
row keys: ['admitted_against','id','kind','lifecycle','members','owning_service']
OrderBy(('lane','asc'))       → ValueError: row does not carry 'lane'
OrderBy(('relevance','desc')) → ValueError: row does not carry 'relevance'
OrderBy(('tier','asc'))       → ValueError: row does not carry 'tier'
TakeWhileBudget(cost_field='cost') → ValueError: row does not carry 'cost'
```

§0.14.1a rule 1 names `lane`, `tier` and `relevance` as the fields a ranking is built from, and rule 5
requires `lane` to be declared data. `manifest._row` (`manifest.py:104-132`) emits none of them, and
`_is_read_tool` remains a name heuristic at `tool_surface.py:113-123`. Every test of the ranking uses
a hand-built fixture carrying `cost` and `lane` keys the generator cannot produce
(`test_cp1_membrane.py:907-909`). So the ordering machinery is correct and currently has no orderable
subject beyond `id`-shaped fields — and the `relevance` key that §0.14.1b calls "the only key that
would make a budget cut defensible" has no producer at all.

**Also unbuilt:** §0.14.1's `take_while_budget` row requires the boundary module to read the budget
and pass it in. `ambient.py` has no budget reader; `HOT_SEED_TOKEN_BUDGET = int(os.environ.get(...))`
is still an import-time ambient read at `tool_surface.py:50`.

**Minor:** the "rejected at construction, not at use" principle is not held for every kind.
`Filter(op="in")` with the default `value=None` constructs and raises `TypeError: argument of type
'NoneType' is not iterable` at use; `AllowList("s","r")` with the default `names=()` constructs and
silently narrows to zero. The shared `stage`/`reason` guard *does* reach all five removing kinds
(measured) — that part is solid.

### 1.8b — PASS, with the design's word corrected

**Falsifier searched for:** a second thing in `app/agentruntime/` that decides what bytes get hashed.
None exists — `canon.py` is the only module that imports `hashlib` or pins `sort_keys`/`separators`.
The rules themselves are right and each is independently tested: version prefix inside the hashed
bytes, floats refused rather than formatted, sets refused, `bool` checked before `int`, NFC before
hashing, key order irrelevant. `canonical_bytes` is exposed so a test can assert on bytes rather than
on a digest in which every defect looks the same — good design.

**The correction.** §0.14.2 says *"exactly one implementation, **gate-enforced**"*, and
`test_there_is_exactly_one_CANONICAL_implementation_in_the_package` (`test_cp1_membrane.py:867`)
narrates itself as the enforcement. It is a pytest, not the gate: `scripts/agentruntime-membrane-gate.py`
contains no canonicalisation check (`grep -n "canon\|sort_keys\|separators"` → no hits). Both run in
CI (`lint-foundation.yml:94`; `python-unit-tests.yml:59`), so the property is enforced — but the
document names the wrong mechanism, which is the class of error §0.14 opens by promising not to
repeat. The narrowing from "no `json.dumps`" to "markers of canonicalisation" is a *good* call and is
argued honestly in the docstring.

**Vacuity note:** the check's subject is an 8-file package where a second serialiser has never existed,
while the 18 repo-wide implementations §0.14.2 cites as motivation are untouched and out of scope. A
realistic input does make it fire (someone adds `hashlib` to a new module in this package), so it is
not vacuous — but its scope is much narrower than the sentence that motivates it.

### 1.8c — PASS, with one live residual

**Falsifier searched for:** an ambient read inside `app/agentruntime/` outside `ambient.py`. The gate
covers every capability §0.14.4 enumerates, and I confirmed by executing `_ambient_violations_in` on
probes rather than trusting the selftest: `os.environ`, `from os import environ`, `import time`,
`import uuid`, `from random import choice`, `open()`, `q.exists()` all go red. The `receiver !=
"ambient"` carve-out (`agentruntime-membrane-gate.py:217-219`) is the right shape — without it the
boundary would be unusable. `_purity_boundary` runs on every default invocation (`:404`) and the
selftest runs first by default (`:377-380`), so a self-test behind a flag CI never runs is avoided.
The disclosure of what the gate cannot see is written in three places and is accurate.

**Residual, in-package and live.** `manifest.py:58` calls `Path(__file__).resolve()` — a filesystem
read *and* a read of the checkout layout — in a non-boundary module, and the gate is green on it.
Measured blind spots beyond §0.14.4's enumerated list: `Path.cwd()`, `Path.home()`, `.resolve()`,
`.touch()`, `.is_file()`, `time.perf_counter()`, and **`secrets.*`** — which §0.14.4's word
"randomness" covers even though its explicit list says only `random.*` and `uuid.*`. §0.14.4 discloses
"the check is by direct name", which covers the helper-indirection case honestly; it does not cover
"a filesystem method we did not think to list", and `resolve()` is a live instance of that.

---

## 3 · Findings

| # | severity | `file:line` | finding |
|---|---|---|---|
| F1 | **high** | `services/chat-service/app/services/stream_service.py:5589,5602,5971` | The catalogue sink is armed 382 lines **after** the fetch that must register into it, in the same function. Measured: the row is not written and the model is not told. Both halves of U-2 are inert on the production path. |
| F2 | **high** | `services/chat-service/app/client/knowledge_client.py:637,641,647-649` | `_nfc` is applied to `description` only. `name`, the parameter schema and `_meta` reach `_tool_tokens` un-normalised. Measured: 83 → 91 tokens, and the tool loses its budget slot to a competitor. |
| F3 | **medium** | `services/chat-service/app/agentruntime/surface.py:417-420` + `:245-247` | `assemble` dispatches on `.keep()` by duck-typing; no kind whitelist. An arbitrary closure-holding stage runs and passes `validate_pipeline`. Measured. |
| F4 | **medium** | `services/chat-service/app/agentruntime/surface.py:105-111` (`value: Any`) | `op ∈ {eq,in,not_in}` bounds the operator names, not the predicates: `__eq__`/`__contains__` on `value` express arbitrary logic. Measured with a regex-equivalent filter. |
| F5 | **medium** | `services/chat-service/app/client/knowledge_client.py:705`; `app/services/stream_service.py:5588,8022` | The admin catalogue path registers no outage and is explicitly excluded from the notice (`and not admin_context`); the resume path has no notice at all. |
| F6 | **medium** | `services/chat-service/app/agentruntime/manifest.py:104-132` vs ARCHITECTURE §0.14.1a rules 1 & 5 | No manifest row carries `lane`, `tier`, `relevance` or `cost`. Measured: `OrderBy` and `TakeWhileBudget` reject every real row. The ranking design has no subject; `_is_read_tool` (`tool_surface.py:113`) is still the name heuristic C-1 forbids. |
| F7 | **medium** | `services/chat-service/tests/test_cp1_membrane.py:983` | `test_no_stage_kind_carries_a_callable` inspects declared field *types*; measured, it sees `'Any'`. It is red-able only for the shape already removed and blind to both live routes (F3, F4). |
| F8 | **medium** | `test_cp0_instrument.py:1378,1387,1417`; `test_knowledge_client.py:1574` | Four of the wiring gates for U-1 and U-2 are `in src` / `src.count(...)` substring checks. They prove the code was typed. None can see F1, and `'"description": _nfc(' in src` is satisfied by one of seven `"description":` sites. |
| F9 | **low** | `services/chat-service/app/agentruntime/manifest.py:227-228,231-279` | `manifest.load` — §0.14.2's door (a) — does not normalise. Measured: `owning_service` accepts and stores NFD text, producing two `canon.digest` values for one visibly identical document. |
| F10 | **low** | `services/chat-service/tests/test_knowledge_client.py:1568` | `test_non_strings_pass_through_untouched` asserts dicts/lists pass through untouched, with a docstring naming the schema as the reason — the unfixed subject of F2, codified as correct. |
| F11 | **low** | `services/chat-service/app/services/skill_registry.py:697` ← `stream_service.py:5396` | The skill router embeds with the session's **chat** model. The twin removed exactly this (`tool_discovery.py:1660-1672`, HIGH-2) in favour of `_resolve_embedding_model`. Half the twin's fix was ported; half was not. |
| F12 | **low** | `services/chat-service/app/agentruntime/manifest.py:58` | `Path(__file__).resolve()` — an ambient read in a non-boundary module. The gate is green: `.resolve()`, `Path.cwd/home`, `.touch()`, `.is_file()`, `perf_counter`, `secrets.*` are all outside its lists. Measured on all seven. |
| F13 | **low** | ARCHITECTURE §0.14.2 vs `scripts/agentruntime-membrane-gate.py` | "gate-enforced" names a mechanism that does not implement it; the enforcement is `test_cp1_membrane.py:867`. |
| F14 | **low** | `services/chat-service/app/services/tool_surface.py:50` | `HOT_SEED_TOKEN_BUDGET = int(os.environ.get(...))` at import — the exact ambient read §0.14.1 requires the boundary module to take over. `ambient.py` has no budget reader. |
| F15 | **low** | `services/chat-service/app/client/knowledge_client.py:653-658` | `_catalog_meta` is never invalidated. On an outage the user's last *successful* availability signal is still served — their own, so U-4 holds, but wrong when it matters. |
| F16 | **low** | `services/chat-service/app/agentruntime/surface.py:89-92,118` | `Filter(op="in")` with default `value=None` constructs and raises `TypeError` at use; `AllowList("s","r")` constructs and narrows to zero. "Rejected at construction, not at use" holds for pipeline ordering, not for stage parameters. |

---

## 4 · The sibling table

Per hunting-ground 1: for every fix, the sibling I searched for and whether it was also fixed.

| fix | sibling searched for | how I searched | fixed? |
|---|---|---|---|
| U-1 `_nfc` on `description` (`kc:640`) | the other strings on the same row that reach `_tool_tokens` | read `_tool_tokens` → `json.dumps(td)`; enumerated every key `get_tool_definitions` writes | **NO** — `name` (`:637`), `parameters` (`:641`), `_meta` (`:649`) |
| U-1 `_nfc` in `get_tool_definitions` | the *other* declaration-catalogue ingestion in the same file | `grep -n '"description"'` over `knowledge_client.py` | **NO** — `get_admin_tool_definitions:713`; also prompts/resources `:1004,1011,1107,1111,1151` |
| U-1 "normalise at the door" | §0.14.2's door (a), `manifest.load` | `grep -rn unicodedata` across the service; then executed `manifest.load` on an NFD row | **NO** — `manifest.py:227-228` |
| U-2 `_register_catalogue_outage` | the other method that returns `[]` on a catalogue failure | `grep -rn record_catalogue_unavailable`; read both `list-tools` methods | **NO** — `knowledge_client.py:705` (admin) |
| U-2 "tell the model" | the resume turn and the admin turn | `grep -n _catalogue_outage` (3 hits, all fresh-turn) | **NO** — `stream_service.py:5588` excludes admin; `:8022` resume has none |
| U-2 sink arming | every `surface_withheld.set` in the repo, vs the read | repo-wide `grep -rn surface_withheld`; then AST line-order inside `stream_response`; then executed the sequence | **NO** — all three armings are downstream (F1) |
| U-3 `_SKILL_VECTOR_CACHE` model key | its twin `_TOOL_VECTOR_CACHE`, and every other `.embed(` caller | `grep -rn '\.embed(' --include=*.py services/`; read both cache key sites | **YES** for the key (twin already had it) — **NO** for the twin's *second* fix, HIGH-2 (F11) |
| U-4 `_catalog_meta` per-user | the other process-lifetime state on `KnowledgeClient` | read `__init__` (`:280-313`) field by field; `grep` all `get_catalog_meta` call sites | **YES** — `_tool_defs_cache` already keyed; `_admin_tool_definitions` does not vary by user |
| 1.8a `NarrowingRule.keep` removed | any remaining route to arbitrary per-row logic | executed a duck-typed stage; executed `__eq__`/`__contains__` on `value` | **NO** — two live routes (F3, F4) |
| 1.8b one canonicalisation | a second hash/sort-pinned dump in the package, and the gate the design names | ran the test's own regex over the package; `grep -n canon\|sort_keys\|separators` over the gate script | **YES** in the package — **NO**, the gate does not enforce it (F13) |
| 1.8c ambient boundary | ambient shapes outside §0.14.4's enumerated list, and the budget §0.14.1 said to move | executed `_ambient_violations_in` on 12 probe shapes; `grep -n os.environ` across the service | **NO** — `.resolve()` live in-package (F12); `HOT_SEED_TOKEN_BUDGET` not moved (F14) |

---

## 5 · §0.14, judged as claims rather than as settled design

The section is unusually careful about its own failure mode and mostly earns it. Rules 2, 3, 4 and 6
of §0.14.1a are each stated so they are checkable from a value, and each one is checkable and checked.
§0.14.3's split of `count` into *absent* vs *zero* is a genuinely subtle call, argued and implemented
correctly. §0.14.4's note about what the gate cannot see is the honest form the document promised.
Those parts are good and I will not spend more words on them.

Four places still overstate:

1. **§0.14.2: "Both are inside the boundary module of §0.14.4, which is what makes 'normalise once at
   entry' enforceable rather than aspirational."** This is false and not implementable as written.
   Door (b) — the external declaration catalogue — is `knowledge_client.get_tool_definitions`, in
   `app/client/`, a different package that the boundary module and the gate cannot reach. The
   implementation confirms it: `_nfc` lives at `knowledge_client.py:141`, outside `app/agentruntime/`
   entirely. The sentence claims an enforcement mechanism for the one door that actually carries
   third-party text, and no such mechanism can exist under this architecture. Meanwhile door (a),
   which *is* inside the package, was not implemented (F9) and — because the contract already
   constrains every row string except `owning_service` — barely has a subject.

2. **§0.14.1: "Three operators, deliberately. Regex or arbitrary comparison would re-admit the closure
   problem under a new name."** The diagnosis of the risk is right; the conclusion that a closed
   operator name-set retires it is wrong, and measurably so (F4). The design reasons about the
   operator *vocabulary* and never about the operand type, so `value: Any` walks straight through the
   argument. This is the answer to the question of whether the six dataclasses remove the closure
   problem or relocate it: **they relocate it**, into `Filter.value` and — more completely — into the
   absence of any kind check at the pipeline boundary (F3). The `NarrowingRule(keep=Callable)` shape
   is still constructible and still runs; it merely no longer has a name in the package.

3. **§0.14.1a rules 1 and 5, and §0.14.1b in full.** The design's whole argument for why `order_by`
   is load-bearing rests on ranking by `lane`, `tier` and `relevance`. None of the three can appear on
   a manifest row (F6), `_is_read_tool` is still the name heuristic rule 5 says must go, and no
   scoring stage exists to produce `relevance`. §0.14.1b's rule 4 — *"if scoring did not run, a
   pipeline that orders by `relevance` MUST be rejected"* — is satisfied today only in the degenerate
   sense that *every* pipeline naming `relevance` is rejected, because nothing can ever produce it.
   That is the correct fail-closed direction, and it is not evidence that the rule works.

4. **§0.14.2's "gate-enforced" and §0.14.1's "the boundary module must read it and pass it in".** The
   first names a mechanism that does not implement it (F13); the second is unbuilt (F14). Both are
   the "capability written as though it exists" shape the section's own preamble commits to avoiding —
   smaller instances than the four it catalogues, but the same shape.

**On whether §0.14 survives review:** its structure does, and its most-argued decisions (`count`
optionality, `id` as implicit final key, missing-field-is-rejection, one canonical form) hold up under
adversarial reading. What it does not yet have is any statement of *where the boundary of the new
package meets the legacy service* — and three of the four items above fail exactly on that seam:
the Unicode door, the budget, and the ranking fields all live on the legacy side, and the section
writes about them as though they were inside.
