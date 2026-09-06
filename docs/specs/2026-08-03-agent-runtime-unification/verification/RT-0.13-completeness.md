# RT-0.13 — completeness attack on `ARCHITECTURE.md` §0.13

**Artifact:** `docs/specs/2026-08-03-agent-runtime-unification/ARCHITECTURE.md` §0.13, and in particular
§0.13.1's table, *"the gap is bounded, not guessed — ten ways a substrate stops being a function."*

**HEAD:** `4ec3f2a83318d0343c14c31bdd5645619fd9e16d` (verified via `git rev-parse HEAD`).
**Method:** code-first. No commit messages read. Every claim below carries a `file:line`. Candidates I
could not substantiate are listed as *not substantiated* rather than dropped, because a completeness
claim deserves to know which shots missed.

---

## Verdict

| # | attack | result |
|---|---|---|
| 1 | find an eleventh source | **BOUND BROKEN.** Two proven sources outside the ten, one of them with a runnable demonstration |
| 2 | audit the CONCURRENCY row | **TWO DEFECTS FOUND.** A never-expiring, mis-keyed process global decides the surface; a second is served across users. Single process, single loop, **zero locks** |
| 3 | "ambient confined to `manifest.py` by accident" | **TRUE today** — and three of the clause's four words are wrong |
| 4 | is the four-revision input set closed? | **NO.** At least six surface-affecting inputs are in none of the four |
| 5 | 87 vs 101 provenance | **NUMBER REAL, CAUSE MISATTRIBUTED**, and it is not the only cause |

The clause's *thesis* survives every one of these — the substrate is not a function, and that is the
finding. What does not survive is the word **bounded**. §0.13.1 is an excellent list of examples
wearing a closure claim it did not earn, and the closure claim is load-bearing: §0.13.2's layer A
("everything that affects the surface is named") is derived from it, and inherits the hole.

---

## 1 · The eleventh source — **Unicode normalisation form of externally-supplied text**

This is not a variant of any of the ten. It is not iteration order, not process state, not an
unrecorded parameter, not a closure, not a clock. It is that **the same text, in two byte-forms that
compare equal to every human and to the model, has two different token costs — and the cost is a hard
budget cliff that deletes tools from the wire.**

### The mechanism, in three hops

**Hop 1 — the estimator is per-codepoint and script-weighted.**
`sdks/python/loreweave_context/tokens.py:41-51`:

```python
total = 0.0
for ch in text:
    total += _char_factor(ord(ch))
return max(1, round(total))
```

with `_F_CJK = 1.05`, `_F_VIETNAMESE = 0.55`, `_F_LATIN = 0.25`, `_F_OTHER = 0.45`
(`tokens.py:13-17`), and the Vietnamese band claimed at `0x1EA0–0x1EFF` **plus the combining-mark
block `0x0300–0x036F`** (`tokens.py:33`).

That last detail is the defect. Under NFC, `ế` is one codepoint in `0x1EA0–0x1EFF` → **0.55**. Under
NFD it is `e` + `U+0302` + `U+0301` → `0.25 + 0.55 + 0.55` = **1.35**. The estimator charges
2.45× for the identical grapheme.

**Hop 2 — that number is the tool's price.**
`services/chat-service/app/services/tool_surface.py:109-110`:

```python
def _tool_tokens(td: dict) -> int:
    return estimate_tokens(json.dumps(td, ensure_ascii=False))
```

`ensure_ascii=False` is what makes this reachable: it emits the description's non-ASCII characters
raw, so they hit the script-aware branches. With `ensure_ascii=True` they would be `\uXXXX` escapes
and land uniformly in `_F_LATIN`.

**Hop 3 — the price is a cliff, not a weight.**
`tool_surface.py:192-201`:

```python
ordered = sorted(
    ((n, td) for n, td in defs.items() if n not in kept),
    key=lambda kv: (0 if _is_read_tool(kv[0]) else 1, _tool_tokens(kv[1]), kv[0]),
)
for nm, td in ordered:
    t = _tool_tokens(td)
    if used + t > token_budget and used > 0:
        break
    kept.add(nm)
    used += t
```

`_tool_tokens` is both the **sort key** and the **accumulator**, and the loop `break`s. An inflated
estimate therefore does two things at once: it reorders the queue, and it exhausts the 2 000-token
hot seed earlier. Tools fall off the end of the surface.

### The demonstration

Run against the estimator's own constants, on a plausible Vietnamese tool description:

```
input : "Tạo một nhân vật mới trong cuốn sách hiện tại và lưu vào bảng chú giải"
NFC   : 70 codepoints → estimate_tokens = 20
NFD   : 90 codepoints → estimate_tokens = 28
                                 ratio  = 1.40
```

**A 40 % cost inflation for a string that is `==`-equal after normalisation and identical on screen.**
Nothing in `manifest_revision`, `policy_revision`, `budget_revision` or `code_revision` moves.

### Is it reachable in *this* system? Yes, on two paths.

**(a) The frozen catalogue already contains the vulnerable characters.**
`contracts/agent-runtime-baseline/tools-list.snapshot.json` — 642 non-ASCII characters, including
`ị` ×24 and `ả` ×22 (both `0x1EA0–0x1EFF`) and CJK (`套`, `路`). The snapshot happens to be NFC today
(`unicodedata.normalize('NFC', s) == s` → `True`); NFD would add 52 codepoints. **Nothing asserts,
records or enforces that form.** It is NFC by luck of whoever typed it.

**(b) The per-user federated overlay is arbitrary third-party text.**
`services/chat-service/app/client/knowledge_client.py:557-566` — `get_tool_definitions(user_id)`
appends *"the caller's external-MCP federation overlay (`u_`/`b_`/`s_` tools)"*. Those descriptions
come from a server this repository does not control, in any language and any normalisation form. A
macOS-authored MCP server emits NFD by default. Here the 1.4× is not a corner case; it is the
expected case.

**And no normalisation exists on this path.** `_normalize_tool_parameters`
(`knowledge_client.py:194-205`) normalises the schema's *shape* (`setdefault("type")`,
`setdefault("properties")`), never its text. The only module in chat-service with `normalize` in its
name, `app/services/text_normalizer.py:1-7`, is a **TTS markdown stripper** — wrong layer, wrong
path, no `unicodedata` import anywhere in it.

> **Why this is genuinely an eleventh and not a re-labelling of one of the ten.** The ten's nearest
> row is *"external services — model, database | genuinely non-deterministic; must be quarantined,
> not denied."* Quarantine is exactly what cannot be done here. The variance does not sit *below* the
> surface where a boundary can be drawn around it — it is *inside the budget arithmetic that computes
> the surface*. You cannot mark where determinism ends when the non-determinism is in the ruler.

---

## 1b · The twelfth — **the catalog itself is a network read with a TTL and a silent empty-degrade**

The ten treats the tool universe as given and asks what narrows it. But the universe is fetched.

`knowledge_client.py:557-624`:

- **it is a network call** — MCP `list-tools` against the ai-gateway (`:581`, `:591-597`);
- **it is cached for 60 s per process, keyed on `user_id` alone** (`:40`, `:571-574`, `:623`) — so
  the *same* input at *t* and at *t+61 s* can produce different surfaces with nothing else changed;
- **on any failure it returns an empty catalogue** (`:598-600`):

```python
except Exception as exc:
    logger.warning("get_tool_definitions (mcp list-tools) failed: %s", exc)
    return []
```

A transient gateway hiccup does not raise, does not record a narrowing, and does not mark the record
degraded. It produces **a turn with no tools at all**, which under §0.1's own vocabulary is the
largest possible silent narrowing — 315 withheld, zero registered. The docstring calls this out
(*"the caller then runs the chat turn tool-free"*) and treats it as a feature.

- **the catalogue is also `PARTIAL`-capable by design** — `_catalog_meta` carries the gateway's
  *"availability / partial-catalog signal"* (`:617-622`), i.e. the system already knows a provider can
  drop out of federation wholesale, changing the universe.

Neither the fetch time, the cache generation, the federation result, nor the degrade is in any of the
four revisions. **§0.13.2 layer A cannot close over an input it fetches.**

---

## 1c · Candidates tested and **not** substantiated

Reported so the bound can be tightened rather than merely doubted.

| candidate | result |
|---|---|
| **floating-point non-associativity** in `estimate_tokens`' `total += ...` loop | **Not substantiated.** The mechanism is real (`1.05`, `0.55`, `0.45` are all inexact in binary64, and `round()` is half-to-even), but on the tested Vietnamese sample a shuffled summation of the identical factor multiset gave a bit-identical `20.2`. I could not produce a divergence. The *normalisation* finding above supersedes it: it changes the multiset, not merely its order. |
| **locale / collation** (`en_US.utf8`, not `C`) | **Not reachable on this path.** No `ORDER BY` on a text column exists anywhere in `tool_surface.py`, `tool_discovery.py`, `skill_registry.py`, `rail_progress.py` or `intent_workflows.py`. The one surface-affecting query, the sticky-domain lookback at `stream_service.py:5972-5977`, orders by `sequence_num DESC` — an integer. Collation is a live hazard elsewhere in this repo; it is not one here. |
| **IEEE division in the relevance scorer** (`tool_discovery.py:688`, `_score` vs `CONFIDENCE_THRESHOLD = 0.30` / `INCLUSION_FLOOR = 0.20`) | **Not substantiated as a source.** Division is correctly-rounded per IEEE-754, and `3/10` yields the same double as the literal `0.3`. Deterministic. |
| **dict / JSON key ordering** across versions | **Not substantiated.** `dict(input_schema)` (`knowledge_client.py:202`) does preserve the remote's key order into `json.dumps`, but a pure key reorder leaves the character multiset unchanged, and `estimate_tokens` sums per character. No cost change. |
| **`__hash__` of user objects** | **Weak.** `_catalog_signature` returns `hash(names)` on a tuple of `str` (`tool_discovery.py:1224-1230`) — PYTHONHASHSEED-randomised, so the tool-vector cache key differs across processes. But each process is self-consistent, so the effect is a cache miss, not a wrong answer. Worth noting only because the ten scopes "hash seed" to *set iteration*, and here it is a **cache key**. |
| **garbage collection** | **Not substantiated.** No `__del__`, weakref cache, or finalizer on the surface path. |

---

## 2 · The CONCURRENCY row — audited, and it was hiding a real defect

§0.13.1 marks this row **"never audited"**. Audited now.

**The concurrency model first, since it establishes reachability for everything below.**
`services/chat-service/Dockerfile:51` runs `uvicorn app.main:app` with **no `--workers`** — one
process, one event loop. Every turn is an async task in it (`app/routers/messages.py:349`,
`async def send_message(...) -> StreamingResponse`). And a grep for `asyncio.Lock`, `Semaphore` or
`threading.Lock` across `app/services/` and `app/client/` returns **zero hits**. Every module-level
container below is therefore shared by every concurrent turn of every user in the process, and every
one of them uses check → `await` → write, which interleaves at the await.

### 2.1 The headline: `_SKILL_VECTOR_CACHE` is process-lifetime, unkeyed by model, and embeds with the *chat* model

`app/services/skill_router.py:75-76`, written at `:132-133`, read at `:113`:

```python
_SKILL_VECTOR_CACHE: dict[str, list[float]] | None = None
_SKILL_VECTOR_CACHE_SIGNATURE: tuple[str, ...] | None = None
```

**On the per-turn path**: `stream_service.py:5381` `resolve_skills_to_inject_async(...)` →
`skill_registry.py:692` `route_additional_skills(...)` → `skill_router.py:163` `_get_skill_vectors(...)`
→ the `global` write at `:132-133`.

**Reaches the wire, budget-exempt**: the router's output is `injected_skill_codes`, and
`tool_surface.py:576` does `names = names | skill_named_tools(injected_skill_codes, catalog)` — a
union that bypasses the token budget entirely.

**And the cache key is wrong in exactly the two ways its own twin was already patched for.** The key
is `_skill_catalog_signature()` = `tuple(sorted(SYSTEM_SKILLS.keys()))` (`skill_router.py:91-92`) —
**the embedding model is not in it**. Meanwhile `stream_service.py:5396-5397` passes
`model_source=model_source, model_ref=model_ref`, i.e. **this turn's chat-completion model**, as the
thing to embed with. Compare the tool-vector twin, where both defects are fixed and documented:

| | `_TOOL_VECTOR_CACHE` | `_SKILL_VECTOR_CACHE` |
|---|---|---|
| model in the cache key | ✅ `tool_discovery.py:1297` (HIGH-1, rationale at `:1200-1208`) | 🔴 `skill_router.py:91-92` — not present |
| resolves a real embedding model | ✅ `tool_discovery.py:1263-1276` (HIGH-2, rationale at `:1233-1258`) | 🔴 reuses the chat model, `stream_service.py:5396-5397` |
| expiry | 60 s (`:1209`) | 🔴 **none — process lifetime** (`:73-74`) |

The consequence is a determinism defect of a kind the ten has no row for: **the first turn in the
process to reach `_get_skill_vectors` bakes the skill vectors into whatever embedding space that
user's chat model produced, and every subsequent turn — any user, any model, until restart —
cosine-compares its intent vector against that foreign space.** Which skills are injected, and
therefore which tools ride budget-exempt onto the wire, depends on *which turn happened to run first
after boot*. `tests/test_skill_router.py` only ever passes `model_source="user_model",
model_ref="m1"`, so no test can observe it.

> The ten's `process state` row reads *"hash seed, unordered `set` iteration | yes, legacy."* That row
> is scoped to ordering. This is process state that is **a cached numerical model of meaning**, keyed
> on the wrong thing, never invalidated, and decisive for the surface. It is not a bigger instance of
> the row; it is a different animal filed under it.

### 2.2 `_catalog_meta` is shared, unkeyed, cross-**user**

`KnowledgeClient` is a **process singleton** — `get_knowledge_client()` returns a module `global`
(`knowledge_client.py:1125-1134`), and the class docstring says so explicitly
(`:208-212`): *"One instance per chat-service process, shared across requests."*

Two pieces of its state are mutated on the per-turn path, and **only one of them is keyed**:

| state | line | keyed? |
|---|---|---|
| `self._tool_defs_cache[cache_key]` | `:571`, `:623` | ✅ by `user_id or ""` |
| `self._catalog_meta` | `:283`, `:622` | 🔴 **not keyed by anything** |

```python
622:  self._catalog_meta = dict(cat_meta) if isinstance(cat_meta, dict) else {}
```

Every cache-**miss** overwrites it, whoever the caller is. Every turn reads it back through
`get_catalog_meta()` (`:687-698`), which chat-service calls at four sites on the turn path —
`stream_service.py:2952`, `:3032`, `:3059`, `:3326`. From there it reaches
`provider_availability(catalog_meta)` (`tool_discovery.py:1410-1430`), which extracts
`unavailable_providers`, and `_scored_result_payload(..., catalog_meta=...)`
(`tool_discovery.py:1501-1507`), which **tells the model which providers are down**.

So: **user A's federation-availability metadata is served into user B's turn**, and the model is told
about an outage that is not in its own surface. The two failure directions are both live —
a spurious "provider unavailable" (the model stops trying a tool that works for *it*), and a missing
one (the model is told nothing is down while its own overlay is broken).

It is worse than a race, because it is also **stale by construction**: the cache-hit branch returns at
`:573-574`, *before* `_catalog_meta` is ever touched. For the whole 60 s TTL window, `_catalog_meta`
retains whatever the last cache-**miss** wrote — quite possibly a different user's, several turns ago.
There is no lock, no `ContextVar`, no per-user key.

### 2.3 Process-level caches on the surface path, all unlocked

| state | file:line | scope | lock |
|---|---|---|---|
| `_TOOL_VECTOR_CACHE` | `tool_discovery.py:1211`, written `:1313` | process, keyed `(catalog_sig, model_source, model_ref)` | none |
| `_EMBEDDING_MODEL_CACHE` | `tool_discovery.py:1260`, written `:1275` | process, keyed `user_id`, 60 s TTL | none |
| `_SKILL_VECTOR_CACHE` / `_SKILL_VECTOR_CACHE_SIGNATURE` | `skill_router.py:75-76`, written via `global` at `:111`, `:132-133` | process, **no TTL — process lifetime** | none |
| `_tool_defs_cache` | `knowledge_client.py:571`, `:623` | process singleton, 60 s TTL | none |
| `_skill_prompt_named_tokens` | `tool_surface.py:647` `@lru_cache(maxsize=64)` | process, unbounded lifetime | n/a |

`_SKILL_VECTOR_CACHE` deserves its own line: it is **explicitly designed to never expire**
(`skill_router.py:21-29`, *"Skill-vector cache lifetime is DELIBERATELY simpler than the tool-vector
cache"*), with a manual `reset_skill_vector_cache()` (`:95-101`) as the only escape. Two replicas that
started either side of a skill-description edit hold **permanently different routing vectors**, and
therefore compute permanently different surfaces for the same message. That is not a race; it is a
stable divergence between processes, which is strictly harder to detect.

### 2.4 The one place a `set` orders the wire — the clause's own row, confirmed and located

The `process state` row asserts *"`active_tool_names: set[str]` reaches the wire unsorted."* Confirmed,
and here is the line: `stream_service.py:1383`, `for name in active_tool_names:`, appending to the
advertised `tools` array built at `:1340`. The set (`:1880`) is `.update()`d at eight sites during the
loop (`:2760`, `:2968`, `:3100`, `:3186`, `:3367`, `:4450`, `:4542`). Every upstream producer sorts
before returning — `tool_surface.py:464`, `:506`, `:637` — and `budget_names_by_tokens` returns a bare
`set` (`:170`); it is this final consumer that drops the order. The always-on core prefix is
deterministic (`ALWAYS_HOT_WRITES` and `ALWAYS_ON_CORE_NAMES` are frozen/tuple,
`tool_discovery.py:282`); only the discovered tail is unordered. The row is right, and now has a
`file:line`.

### 2.5 Also cross-turn by design, worth naming: `find_tools_attempts`

`tool_discovery.py:1184` — a process-wide `FindToolsAttemptTracker` (`self._sessions`, `:1123`,
mutated `:1156-1170`), on the turn path via `stream_service.py:3323` → `tool_discovery.py:1680`
`is_repeat = find_tools_attempts.record(session_id, group, intent)`. It feeds a *"Stop searching —
tell the user this capability is not supported"* note into the tool result (`:1519-1538`). This one is
correctly keyed by `session_id` and is *deliberately* turn-N-depends-on-turn-N-1 over a 10-minute
window (`_RETRY_WINDOW_S`, `:1108`) — but it is in-process only, so it resets silently on redeploy and
is not shared across replicas. Two replicas disagree about whether the model has already asked.

### 2.6 What is *correctly* handled, and should be credited

`instrument.surface_withheld` is a `ContextVar` (`instrument.py:254`), and the reasoning at
`:240-252` is right: a `ContextVar` is inherited by asyncio tasks, so it is naturally per-request.
The narrowing sink does **not** leak across concurrent turns. The recorder's `_segment = uuid4()`
(`instrument.py:308`) likewise makes `(segment, pass)` unique without cross-request coordination
(`:290-307`) — the one place in this audit where concurrency was designed for rather than assumed
away.

Cleared during the audit, so they need not be re-walked: `app/agentruntime/*.py` has **no
module-level mutable state at all**; `skill_registry.SYSTEM_SKILLS` (`:104`) is read-only with
`frozen=True` dataclasses; `tool_surface.py` has no module-level mutable containers and
`merge_activated_tools` (`:755`) rebuilds rather than mutating; there are **no mutable default
arguments** anywhere in `app/services/`; and `_tool_defs_cache` hands out a shared list object per
user but nothing mutates it in place today (`strip_tool_meta` copies, `tool_discovery.py:647-650`;
`_studio_panel_tool` deepcopies, `frontend_tools.py:505`) — an unenforced invariant, not a live
defect.

> **Row correction:** `concurrency` should not read *"never audited"* — it should read
> **"yes, proven: `_SKILL_VECTOR_CACHE` is a never-expiring process global, keyed without the
> embedding model and populated using the chat model, that decides which tools ride budget-exempt onto
> the wire; `KnowledgeClient._catalog_meta` is unkeyed process state served across users; single
> process, single loop, zero locks."**

---

## 3 · "Ambient reads are confined to `manifest.py` **by accident**"

**The confinement is TRUE today.** Verified independently across all six files of
`services/chat-service/app/agentruntime/`, including indirect reads through call chains.

Every ambient statement in the package is in `manifest.py`:

| line | read |
|---|---|
| `manifest.py:54` | `os.environ.get(_ENV_VAR)` — env |
| `manifest.py:57-60` | `Path(__file__).resolve()`, `.parents`, `candidate.exists()` — FS walk + stat |
| `manifest.py:191`, `:225`, `:227` | `.exists()`, `.read_text()` — FS read |
| `manifest.py:197-198` | `.mkdir()`, `.write_text()` — FS write |

`admission.py`, `narrowing.py`, `surface.py` are clean in every category — env, FS, clock,
randomness. **No clock and no randomness appear anywhere in the package.**

**The indirect check clears too, and for a structural reason.** The intra-package import graph is
`contract → ∅`, `narrowing → ∅`, `admission → contract`, `surface → narrowing`,
`manifest → {admission, contract, surface}` (the last function-local at `manifest.py:294`).
`manifest.py` is a **leaf consumer**: the one cross-edge runs *manifest → surface*, never the reverse.
No function in the other four calls `load()`, `manifest_path()`, `declarations()` or `generate()`.
Import-time side effects are limited to two `re.compile` calls and one `PurePath` construction
(`manifest.py:34`) — no syscall.

### Three corrections to how the clause states it

**(a) "by accident" is wrong on the mechanism, right on the guarantee.** The confinement is
*structural* — the import direction makes it unreachable from elsewhere — and `manifest_path()`'s
marker-search design is a deliberate, heavily-documented fix (`manifest.py:38-62`). But it is
**completely unguarded**, which is the point the clause was reaching for and stated as the wrong
property. The membrane gate cannot see ambient IO *at all*:

```python
scripts/agentruntime-membrane-gate.py:74:   _STDLIB = set(sys.stdlib_module_names)
scripts/agentruntime-membrane-gate.py:108:  if _is_internal(mod, from_file=path) or _root(mod) in _STDLIB:
scripts/agentruntime-membrane-gate.py:109:      continue
```

It is an **import-origin allowlist with stdlib blanket-permitted** — and `os`, `pathlib`, `time`,
`random` and `uuid` are all stdlib. The permission set is applied uniformly to every module
(`:315`, `:321-322`); there is no per-module rule and no notion of a privileged ambient module. Its
own self-test *pins* the permissive behaviour (`:382-384`). **Adding `import os; os.environ.get(...)`
to `surface.py`, or `datetime.now()` to `narrowing.py`, leaves CI green.** §0.13.2 layer B says this
is *"enforced by the membrane gate, which already walks the import graph"* — it walks the import
graph, and the import graph is not where this property lives.

**(b) `contract.py:91-96` is an exception under any definition looser than "syscall".**

```python
91:  parts = Path(source_path.replace("\\", "/")).parts
92:  if "services" in parts: ... parts[parts.index("services") + 1]
```

and `check_contract` **raises** if that derivation is empty (`:123-129`). C-0 makes *"the string
contains a `services/<name>/` segment"* a validity rule — i.e. the checkout layout is promoted into
the contract. This is the same assumption that already made this package unimportable in production,
documented at `manifest.py:41-52` (*"the image flattens `services/chat-service/` to `/app`"*).
`manifest.py` was fixed to stop counting directory levels; `contract.py` still parses for them. Inert
today only because every `source_path` reaching it is a literal — including `manifest.py:253`, which
*synthesises* `f"services/{owning_service}/"` purely to round-trip a stored value back through the
layout parser.

**(c) The package's public *surface* is ambient even though its code is not.**
`__init__.py:34-43` exports `load`, `generate`, `manifest_path`, `declarations`. "Ambient is confined
to one module" does not imply "ambient is confined behind one API": any future consumer calling
`agentruntime.declarations()` inherits an env read and an FS stat-walk. Latent only because **no
production code imports the package at all** — today the sole importers are
`services/chat-service/tests/test_cp1_membrane.py` and the gate itself
(`agentruntime-membrane-gate.py:260`, which takes only the two pure functions).

**(d) One undeclared coupling, offered as a gift to layer E.** The gate's M1 drift check computes
`expected = build([])` and compares it to the committed file
(`agentruntime-membrane-gate.py:278-284`). That **silently depends on `build()` being clock-free and
randomness-free** — a `generated_at` timestamp or a `uuid` in a row would make M1 fail on every run.
The dependency is nowhere asserted. It is exactly the `pure` declaration §0.13.2 layer E proposes,
already load-bearing and already unstated.

---

## 4 · The four-revision input set is **not closed**

§0.13.2 layer A: *"Everything that affects the surface is named and content-addressed:
`manifest_revision`, `policy_revision`, `budget_revision`, `code_revision`."*

Six surface-affecting inputs are in none of the four. The first is fatal on its own.

| # | input | evidence | why no revision covers it |
|---|---|---|---|
| **1** | **the federated catalogue** — the surface's entire universe | `knowledge_client.py:557-624` | fetched over the network per user, 60 s TTL, `[]` on failure, per-user `u_`/`b_`/`s_` overlay. A user registering an external MCP server changes the surface with **zero** change to any revision |
| **2** | **session conversation history** | `stream_service.py:5969-5982` — last 8 assistant `tool_calls` rows → `engaged_domains_from_tool_calls` → `sticky_domains` → `hot_domains` | the surface is a function of *previous turns*. The record holds no session-history revision |
| **3** | **an external embedding model's output** | `skill_router.py:137-203`; feeds `injected_skill_codes` at `stream_service.py:5381` | see §5.2 — a model call *upstream* of the surface |
| **4** | **the user's configured embedding model** | `tool_discovery.py:1263-1276` — `_resolve_embedding_model(user_id)` reads the provider-registry `embedding`-capability default | a per-user provider setting silently re-ranks skills, therefore domains, therefore tools |
| **5** | **the chat model's context window** | `scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length)` at `tool_surface.py:378`, `:635`; `sdks/python/loreweave_context/budget.py:44-46` | `budget_revision` names the *constant*; the effective budget is `flat_default/200_000 * context_length`. Switching model role changes the surface. (See the HEAD-adjacent settings work touching the model-roles map — that writer moves this input.) |
| **5b** | **which turn ran first after process boot** | `skill_router.py:73-76`, `:91-92`, `:132-133` (§2.1) | the skill-vector space is frozen at first use, keyed without the model. Not an *input* any revision could name — it is a property of the process's history |
| **6** | **persisted rail / workflow / pin state** | `stream_service.py:5958-6013` — `_wf_step_tools`, `_rail_done_tools`, `_rail_repeat_done_tools`, `_rail_next_tools`, `pinned_step_tools`; `SessionToolPins` at `tool_surface.py:205-217` | per-session DB state; `policy_revision` names the rules, not the accumulated progress |

There is a seventh, and it is the one that should worry the clause most, because it is *invisible to
every revision by construction*: **input #1's normalisation form** (§1). Two byte-identical
revisions, two different surfaces.

> The honest reformulation of layer A is not "everything is named" but **"the surface is a function of
> `(four revisions, catalogue snapshot, session state, router output)`"** — and the last three are the
> expensive ones. Naming four cheap inputs and declaring closure is the same move §0.13 diagnoses in
> P4: a value that does not depend on its input.

---

## 5 · §0.13.4 — the number is real, the cause is not

### 5.1 Provenance: **verified, and it is a first-party measurement**

`87` and `101` originate at
`docs/specs/2026-08-03-agent-runtime-unification/verification/CP-0-v-live-round6.md:139-140`:

```
RUN A pass-1 candidate pool:  87  (adv 58, wh 29)
RUN B pass-1 candidate pool: 101  (adv 49, wh 52)
pool A == pool B ?  False
in A's pool, not in B's (3):  glossary_book_sync_apply, glossary_plan, glossary_propose_batch
in B's pool, not in A's (17): jobs_*, translation_*
```

Arithmetic checks: 87 − 3 + 17 = 101. It propagates to three other places consistently —
`docs/plans/2026-08-04-agent-runtime-RUNSTATE.md:56` (P7), `CP-0-v-live-round7.md:117`, and the
source comment at `tool_surface.py:392-393`. **No drift, real provenance, correctly quoted.**

One precision note the clause elides: 87 and 101 are the **pass-1 candidate pool reconstructed from
the instrument** (advertised ∪ withheld), not a direct count of candidates. It is a lower bound on the
pool, and it is only meaningful because round 6 had exactly two recorded stages.

### 5.2 The cited cause is **wrong**, and the author's own comment says so

§0.13.4 writes:

> *"`budget_names_by_tokens` was query-dependent — 87 candidate tools for one message and 101 for
> another."*

`budget_names_by_tokens` is **a pure function**. Its whole body is `_budget_names_impl`
(`tool_surface.py:173-202`): no env, no clock, no randomness, no I/O; the ordering is a total key
`(is_read, tokens, name)` with a name tie-break (`:192-195`); its inputs are `(catalog, names,
token_budget)`. Given the same three arguments it returns the same set. It cannot be the moving part.

The measurement's own source says the moving part is upstream. `CP-0-v-live-round6.md:154-158`:

> *"A step **upstream of `hot_seed`** selected ~100 tools out of 315 on the basis of the user's
> message … The only recorded stages are `hot_seed` and `token_budget`, and both operate **inside**
> the already-narrowed pool."*

And the comment the author wrote in the code, at `tool_surface.py:386-401`:

> *"Every stage I had instrumented — hot_seed, rail gate, oneshot, failure breaker, permission mode —
> sits BELOW this line. The selection that decides which DOMAINS are candidates at all sits above it,
> and registered nothing. … A narrowing that never says no is the hardest kind to see."*

**The clause attributes the moving control to the one stage its own evidence exonerates**, and names
the deterministic budgeter instead of the non-deterministic selector. That matters beyond pedantry:
§0.13.4's instruction to CP-2/CP-4 is *"an A/B whose control is not a function is not an A/B"*, and a
team that reads it as "watch the budgeter" will harden a pure function and leave every actual cause
in place.

### 5.3 Other causes are present — "query-dependent" is an under-diagnosis

Runs A and B differed by more than their message text. At least four independent sources moved:

**(a) Session history.** `stream_service.py:5969-5982` unions `sticky_domains` — derived from the last
8 assistant messages' `tool_calls` in *that session* — into `hot_domains`, which is the input to
`hot_tool_names` and therefore to the candidate pool. Two runs in two sessions cannot have the same
pool even with an identical message. **The control was not merely query-dependent; it was
history-dependent**, which is worse, because no choice of message fixes it.

**(b) A model call upstream of the surface — and this breaks §0.13's layering, not just its list.**
`resolve_skills_to_inject_async` (`stream_service.py:5381`) invokes
`skill_router.route_additional_skills` (`skill_router.py:137-203`), which **embeds the user's turn
text via the external embedding client** (`:167-173`), cosine-ranks skills, and returns the top-K
(`:202-203`). Its output, `injected_skill_codes`, then:

- filters **the catalogue itself** — `filter_intent_gated_setup_tools(catalog, injected_skill_codes,
  ...)` at `stream_service.py:5947-5949`; and
- adds budget-exempt tools to the wire via `skill_named_tools` — `stream_service.py:6034`,
  `tool_surface.py:679-688`.

> **§0.13's governing sentence is "Below the model call, the same inputs produce the same surface."
> There are two model calls, and one of them is *above* the surface.** The clause's boundary assumes a
> single model call at the end of the pipeline. The embedding call cannot be quarantined below a
> boundary it sits above, and layer C's *"the record marks where determinism ends"* has no single
> place to put the mark.

The router degrades on failure to `return []` (`:174-181`) — *"indistinguishable from (and exactly as
safe as) a genuine embedding-client outage"*, per its own docstring. Safe for the turn; fatal for a
control arm, because the same message yields a different surface depending on whether an unrelated
service was up.

**(c) The 60 s catalogue TTL and its empty-degrade** (§1b). Two runs more than 60 s apart re-fetch;
either can come back short, or empty.

**(d) A model-dependent budget.** `scale_by_window(HOT_SEED_TOKEN_BUDGET, creds.context_length)`
(`tool_surface.py:378`) — the ceiling that produced the `hot_seed` withheld records is a function of
the session's model. Different model, different ceiling, different pool.

### 5.4 The clause's *other* CP-0 claims: both verified

- **`manifest_revision` accepted but never supplied — TRUE.** Repo-wide, `manifest_revision` appears
  in exactly three lines of source, all inside the recorder itself: `instrument.py:319`, `:339`,
  `:340`. **No caller passes it**, so the branch at `:339` never fires and the key never reaches a
  row. Confirmed by grep across `services/`.
- **`uuid4` in the CP-0 recorder — TRUE**, `instrument.py:308` (`self._segment = uuid4().hex[:12]`),
  and the reasoning at `:290-307` is sound: a counter would need cross-request coordination.
- **"`seed` appears nowhere on the provider path"** (§0.13.3) — consistent with everything I saw; not
  independently exhaustively verified, and flagged here only so it is not read as confirmed by this
  document.

---

## What should change in the clause

Minimal, mechanical, no re-litigation of the thesis:

1. **Retitle §0.13.1.** *"ten ways"* → **"the sources found so far — this list is open, and a source
   that is not on it is not thereby absent."* A completeness claim is falsified by one miss; this
   document supplies two.
2. **Add two rows.** *normalisation / encoding of externally-supplied text* — **yes, proven,
   `estimate_tokens` NFC vs NFD = 20 vs 28 tokens on a Vietnamese description, feeding a hard budget
   cliff.* And *catalogue acquisition* — **yes: the universe is a 60 s-cached network fetch that
   degrades to empty without registering a narrowing.*
3. **Rewrite the `concurrency` row.** Not *"never audited"* — **`_SKILL_VECTOR_CACHE` is a
   never-expiring process global, keyed without the embedding model and populated with the chat
   model, whose contents decide which tools ride budget-exempt onto the wire;
   `KnowledgeClient._catalog_meta` is unkeyed and served across users; one process, one loop, zero
   locks.** The surface depends on *which turn ran first after boot* — a determinism defect no other
   row covers.
4. **Fix the `ambient` row and layer B.** Confinement is structural, not accidental — and
   **unenforced**: the membrane gate blanket-permits stdlib, so a second ambient module passes green.
   Layer B needs an AST check for ambient *calls*, not another import rule.
5. **Correct §0.13.4's attribution.** The 87/101 belongs to domain selection driven by an *embedding
   call* plus *session history* — not to `budget_names_by_tokens`, which is pure.
6. **Weaken layer A's closure claim** to name what it actually closes over, and list the catalogue
   snapshot, session state and router output as the three inputs that make replay expensive. That was
   the honest finding, and it is a stronger one than a closed set that is not closed.

*Attacked on completeness only. §0.13's thesis — that disclosure without determinism yields an honest
record of a chaotic process — is not disputed by anything above; it is corroborated by all of it.*
