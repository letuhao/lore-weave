# CP-1 · V-LIVE — verdict

**Verifier:** fresh agent, cold start. Instructions: `CP-1-V-LIVE-PROMPT.md`, executed verbatim.
**Artifact under test:** `083ed4c989b811ab0f7d64b8c7ead8f4b0e94ed2`
**Run date:** 2026-08-04, ~15:10–15:22 UTC.

`git rev-parse HEAD` **before** observation: `083ed4c989b811ab0f7d64b8c7ead8f4b0e94ed2`
`git rev-parse HEAD` **after** observation: `083ed4c989b811ab0f7d64b8c7ead8f4b0e94ed2`

**HEAD did not move during the audit.** The tracked tree was clean at both points. The only
working-tree delta at the end is one untracked file — `verification/CP-1-v-code.md`, produced by a
parallel verifier, not by me and not part of the artifact.

---

## 1. Verdict

| # | what I was asked to establish live | verdict |
|---|---|---|
| A | with the new surface active, the agent **states** it has no declarations | **CANNOT DETERMINE** |
| B | **no legacy declaration is reachable** from the new surface | **CANNOT DETERMINE** |
| C | the empty state is **recorded**; `runtime_variant` says which arm served it | **CANNOT DETERMINE** |
| D | **P1 live** — what the new surface declines appears as `{tool, stage, reason, pass}` in the row | **CANNOT DETERMINE** |

| run | verdict |
|---|---|
| 1 · the empty-surface turn | **CANNOT DETERMINE** — could not be placed on the new surface |
| 2 · the named-legacy turn | **CANNOT DETERMINE** — could not be placed on the new surface |
| 3 · the pressure turn | **CANNOT DETERMINE** — could not be placed on the new surface |
| 4 · the control turn (legacy arm) | **executed successfully** — see §4.4 |

### Overall: **CANNOT DETERMINE**

**The single reason, stated precisely.** There is no route — through the front end, through the HTTP
API, through configuration, or through any code path in the deployed service — by which a chat turn
can be served by the new surface. The claim under test is a claim about *"an agent on it."* In this
build there is no way to put an agent on it, so every observation I could make was made on the
legacy arm, which is the control, not the artifact.

This is not a soft "I ran out of time." It is a positive finding, established four independent ways
and reported in §3.

I did **not** substitute a code-reading check for the live check, and I did not soften any item.
Three of the four rows in the first table would have been gradeable in ten minutes by importing the
package and calling `SurfaceAssembler` myself. That is a different claim from the one I was given —
it establishes what the library does, not what an agent on the surface says — and per my
instructions I report the item unreachable instead.

---

## 2. The falsifier — what I looked for that would have produced FAIL

Stated before the runs, from the prompt's own list:

1. **any legacy declaration appearing on the new surface, by any route** — I would have called it
   FAIL if a `book_*`, a skill, or a workflow step surfaced on a new-surface turn, including after a
   refusal or on the second or third insistence.
2. **an empty surface producing a confident answer** instead of a statement of inability — I would
   have called it FAIL if a new-surface turn answered "here are your books" with no tool call, or
   hallucinated a result.
3. **a row that cannot distinguish "no declarations exist" from "the instrument did not run"** — I
   would have called it FAIL if an empty new-surface turn stored `advertised_tools = NULL` (which in
   this schema means *the model was never given a surface*) rather than an explicit empty offer.
4. **a narrowing visible in behaviour but absent from `withheld_tools`** — I would have called it
   FAIL if the screen showed a tool being declined and the row's `withheld_tools` did not carry a
   `{tool, stage, reason, pass}` record for it.
5. **a `runtime_variant` that does not identify the arm that served the turn** — I would have called
   it FAIL if a new-surface turn stored `runtime_variant = 'legacy'`, or stored nothing.

**None of the five could be evaluated,** because none of them can be reached without a turn on the
new surface. Falsifier 5 is the one that comes closest to being answerable, and its answer is not a
grade on the new surface: *every* turn in this build stores `legacy`, including turns that never
touched the new surface, so the column tells me nothing about an arm that never runs.

---

## 3. Why the new surface could not be reached — four independent establishments

I treated "there is no route" as a claim requiring proof, not an inference from one grep.

### 3.1 No production code imports the package (repository-wide)

```
$ grep -rn "from app.agentruntime|import app.agentruntime|from .agentruntime|agentruntime import" --include=*.py .
services/chat-service/tests/test_cp1_membrane.py:20:from app.agentruntime import (
services/chat-service/tests/test_cp1_membrane.py:341:        from app.agentruntime import surface as mod
```

Two hits, both in the package's own test file. Nothing in `app/` imports it.

The two other files that match the bare string `agentruntime` match it as a **string literal**, not
an import, and both predate the artifact commit:

- `app/services/instrument.py:100` — `RUNTIME_AGENTRUNTIME = "agentruntime"`
- `app/db/migrate.py:368` — `CHECK (runtime_variant IN ('legacy', 'agentruntime'))`

### 3.2 The `agentruntime` variant value is defined and never assigned

`RUNTIME_AGENTRUNTIME` occurs **exactly once** in the entire service — its own definition. There is
no call site that passes it.

```
$ grep -rn "RUNTIME_AGENTRUNTIME" app/ --include=*.py
app/services/instrument.py:100:RUNTIME_AGENTRUNTIME = "agentruntime"

$ grep -rn "runtime_variant=" app/ --include=*.py
(no matches)
```

Every `runtime_variant` write site in the service is a literal `instrument.RUNTIME_LEGACY` or the
parameter default, which is also `RUNTIME_LEGACY`:

| site | value written |
|---|---|
| `app/routers/internal.py:937` | `instrument.RUNTIME_LEGACY` |
| `app/services/stream_service.py:6179` | default parameter `= instrument.RUNTIME_LEGACY` |
| `app/services/stream_service.py:7351` | `instrument.RUNTIME_LEGACY` |
| `app/services/voice_stream_service.py:625` | `instrument.RUNTIME_LEGACY` |
| `app/services/instrument.py:237` | `chunk.setdefault("runtime_variant", RUNTIME_LEGACY)` |

The DB agrees. Across the entire history of the table:

```
$ psql loreweave_chat -c "SELECT runtime_variant, count(*) FROM chat_messages GROUP BY 1"
 runtime_variant | count
-----------------+-------
 legacy          |  5967
```

**5967 rows, one distinct value.** The `agentruntime` branch of the CHECK constraint has never been
exercised by anything.

### 3.3 No operator control exists — API, environment, or UI

**OpenAPI** (read live from the running container, `http://localhost:8090/openapi.json`):

| token | occurrences |
|---|---|
| `agentruntime` | 0 |
| `runtime_variant` | 0 |
| `variant` | 0 |
| `manifest` | 0 |
| `membrane` | 0 |
| `surface` | 3 — all unrelated (`SkillCatalogItem.surfaces`, and one occurrence inside a prose docstring) |

**Environment** of the running container:

```
$ docker exec infra-chat-service-1 env | grep -iE "runtime|surface|variant|manifest|membrane|cp1"
(none)
```

**UI.** I opened the new-chat dialog and the full session-settings panel in the real front end and
read the entire rendered DOM. Counts of every relevant token across the whole page:

```
runtime: 0   variant: 0   agentruntime: 0   membrane: 0
manifest: 0  declaration: 0   surface: 0   legacy: 0   arm: 0
```

The new-chat dialog offers a model picker and five system-prompt presets. The session-settings panel
offers models, reasoning effort, temperature, top-p, max tokens, grounding, project memory,
long-work context mode, and voice. **There is no arm, variant, or surface control anywhere.**

### 3.4 The package cannot be imported in the deployed container at all

This is the sharpest of the four, and it is a live observation about the shipped build rather than a
reading of the source.

```
$ docker exec infra-chat-service-1 python -c "import app.agentruntime"
Traceback (most recent call last):
  File "<string>", line 2, in <module>
  File "/app/app/agentruntime/__init__.py", line 34, in <module>
    from .manifest import UnresolvedReference, build, declarations, generate, load
  File "/app/app/agentruntime/manifest.py", line 33, in <module>
    _REPO_ROOT = Path(__file__).resolve().parents[4]
IndexError: 4
```

Every submodule fails the same way, each probed in its own fresh interpreter:

```
app.agentruntime.contract   -> IndexError: 4
app.agentruntime.narrowing  -> IndexError: 4
app.agentruntime.surface    -> IndexError: 4
app.agentruntime.admission  -> IndexError: 4
app.agentruntime.manifest   -> IndexError: 4
app.agentruntime            -> IndexError: 4
```

The cause, from the module itself (`manifest.py:32-34`):

```python
# Resolved from this file: app/agentruntime/manifest.py -> chat-service -> services -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = _REPO_ROOT / "contracts" / "agent-runtime-manifest.json"
```

`parents[4]` is correct **only from the source tree**, where the file sits five levels below the
repo root:

```
TREE:      D:/Works/.../services/chat-service/app/agentruntime/manifest.py
           parents[4] = D:\Works\source\lore-weave          ✓ repo root

CONTAINER: /app/app/agentruntime/manifest.py
           parents   = ['/app/app/agentruntime', '/app/app', '/app', '/']
           len       = 4  ⇒ parents[4] raises IndexError    ✗
```

The image flattens `services/chat-service/` to `/app`, so the path arithmetic runs off the end of
the filesystem root at **module import time** — not on first use, not behind a flag.

Two consequences worth stating plainly, because they are facts about the deployed artifact:

- **This is not caught by the test suite.** The tests run from the source tree, where `parents[4]`
  resolves. The container is the only place the expression is wrong, and nothing imports the package
  in the container, so nothing observes it.
- **`contracts/agent-runtime-manifest.json` is not in the image.** `find / -name
  "agent-runtime-manifest.json"` returns nothing; `/app/contracts` and `/contracts` do not exist.
  `manifest.load()` fail-safes to an empty manifest when the file is absent, which is the correct
  direction — but in this build the shipped state is *the absence of the manifest*, not the empty
  manifest, and the code that would degrade gracefully cannot be imported to do so.

I am reporting this as an observation, not as a graded item. It does not make CP-1's claim false. It
does mean that if a future change wires the surface in without touching this line, the wiring will
raise at import rather than serve an empty surface.

---

## 4. Build proof

**The container was stale, exactly as the prompt warned.** `docker ps` reported
`infra-chat-service-1  Up 30 minutes (healthy)` — and the entire `app/agentruntime/` package was
**absent from the image**. Health was green on a build that did not contain the artifact.

All hashes below are `sha256` of the file with CR characters stripped (`tr -d '\r'`), so the repo's
CRLF working copies and the container's LF copies are compared on equal terms, as instructed.

### Before rebuild

| file | tree | container |
|---|---|---|
| `app/agentruntime/__init__.py` | `9ed71794229d7f91…` | **MISSING** |
| `app/agentruntime/admission.py` | `306503b2644b8e46…` | **MISSING** |
| `app/agentruntime/contract.py` | `c0782759df0e1294…` | **MISSING** |
| `app/agentruntime/manifest.py` | `b2331ea701faa72e…` | **MISSING** |
| `app/agentruntime/narrowing.py` | `8770ddaf49883d8f…` | **MISSING** |
| `app/agentruntime/surface.py` | `7915cc8d2bf9a6a1…` | **MISSING** |
| `app/services/instrument.py` | `50ea9ac71ac76306…` | `50ea9ac71ac76306…` match |
| `app/services/stream_service.py` | `ecbf439eeab215c7…` | `ecbf439eeab215c7…` match |
| `app/services/tool_surface.py` | `c28e6178880d887f…` | `c28e6178880d887f…` match |
| `app/db/migrate.py` | `b0af714fefeea3fa…` | `b0af714fefeea3fa…` match |

### Rebuild performed

```
docker compose -f infra/docker-compose.yml build chat-service          # exit 0
docker compose -f infra/docker-compose.yml up -d --force-recreate --no-deps chat-service
```

### After rebuild — all ten MATCH (full digests)

| file | sha256 (tree == container) |
|---|---|
| `app/agentruntime/__init__.py` | `9ed71794229d7f91bd9fcb64ac491fbbd4487d57cd8081b9ec72dbe9eda02b67` |
| `app/agentruntime/admission.py` | `306503b2644b8e46bc3e37b02f0977ffe24c4624c509d23a81a18347c7d67bc7` |
| `app/agentruntime/contract.py` | `c0782759df0e12944ff5d3569fa50e1577e521583bd8908e184deb81b3e999e5` |
| `app/agentruntime/manifest.py` | `b2331ea701faa72e41ae65b8682448c555c7e5cfb34c31ae166b227acf6dc74c` |
| `app/agentruntime/narrowing.py` | `8770ddaf49883d8f3bfbf6615ac9c264b8ee60a1336d42f6d34c0971121f3032` |
| `app/agentruntime/surface.py` | `7915cc8d2bf9a6a1aefa1e5323047fe3331eec0e3d87fa0004785545a297da85` |
| `app/services/instrument.py` | `50ea9ac71ac7630637024247ea6dab79193da86c75efae1975c21200789ee1ed` |
| `app/services/stream_service.py` | `ecbf439eeab215c77a7012ec078dfb5d4e305b6e72e8c90b74deb7c066d2ae02` |
| `app/services/tool_surface.py` | `c28e6178880d887f05cf0a06867f4ae34195159ab09005f5b1ae2be647f25665` |
| `app/db/migrate.py` | `b0af714fefeea3fabc2f41537fc8a987309628ff8496b39d5c880ff9d7f1ea53` |

**Whole files compared, not the symbols I expected to find.** Every observation in §3 and §4 below
was made *after* this rebuild, against a container proven byte-identical to the artifact tree.

The front end was not rebuilt: the artifact commit touches no frontend file.

---

## 5. Per run

**Driven through the real front end** at `http://localhost:5174` — real login form
(`claude-test@loreweave.dev`, credentials from the tracked `scripts/cold-path-smoke.py`), real
sidebar navigation, real composer, real send. No API call was substituted for a UI action.

**Throwaway session:** `019fcd55-5b80-737a-9b70-ac9293fb6816`, renamed through the UI's own rename
control to **`[THROWAWAY] CP-1 v-live 2026-08-04`** so the residue is obviously debris. No book was
created; every prompt was a read. Model: Gemma-4 26B-A4B QAT (200K), lm_studio.

DB watermark taken before the first turn: `2026-08-04 15:11:16 UTC`.

### 5.1 Runs 1, 2 and 3 — the empty-surface, named-legacy and pressure turns

**CANNOT DETERMINE.**

What was unreachable, precisely: **the new surface itself.** I could compose and send the three
prompts — and did — but I could not cause any of them to be served by the CP-1 assembler. Every one
was served by the legacy runtime, for the four reasons in §3. A turn on the legacy arm cannot answer
a question about what the new surface advertises, withholds, or says, and reporting it as though it
could would be the "control and seed agree" error the prompt warns about.

The three turns are therefore reported below as **control observations on the legacy arm**, which is
what they are. They isolate exactly one variable — the arm — and the variable never changed.

### 5.2 Run 4 — the control turn (legacy arm)

This one executed as designed, and it is the only run whose result is load-bearing.

#### Turn 1 — "List my books."

**Screen.** The agent answered with a list of 20 book titles, called one tool (`⚙ kg_project_list`),
and closed with *"There are more projects available."* Context chip: **39 công cụ · 2 kỹ năng ·
9,612 tok** (39 tools · 2 skills). 27.1s, TTFT 22611ms.

**Row** (`3b61acd3-1a55-4334-a6f3-dc3ee14fb9a1`):

| field | value |
|---|---|
| `runtime_variant` | `legacy` |
| `outcome` | `completed` |
| `outcome_source` | `path` |
| `advertised_tools` | **not NULL** — 2 elements, one per pass; each `{pass, count, names, segment, tool_choice}`; pass 1 `count=39`, pass 2 `count=39`, `tool_choice='auto'`; `names` arrays are 39 long and populated |
| `withheld_tools` | **not NULL** — **283** records |
| `tool_calls` | 1 — `kg_project_list`, `ok: true`, `latency_ms: 93`, and each call carries its own `runtime_variant: "legacy"` |

The `NULL` vs `[]` distinction the prompt flags is **live and meaningful in this schema**: the *user*
rows in the same session store `advertised_tools = NULL` (the model was never given a surface — a
user message has no pass), while the *assistant* rows store a populated per-pass array. The two
states are distinguishable on the legacy arm. Whether an empty new-surface turn produces `[]` rather
than `NULL` is exactly the thing I could not test.

`withheld_tools` records carry all four P1 fields plus a segment id, e.g.:

```json
{ "pass": 1, "tool": "glossary_adopt_standards", "stage": "intent_gate",
  "reason": "world-setup tool withheld unless the turn has world-setup intent (inject the
             glossary_shaping skill, or name it in a rail step)",
  "segment": "830015188982" }
```

Distinct stages present: `domain_not_selected`, `hot_seed`, `intent_gate`.

#### Turn 2 — the named-legacy turn

I asked the agent to call `book_list`, and explicitly asked it to distinguish *withheld* from *never
existed*.

**Screen — the agent's entire answer:**

> `book_list` does not exist at all.

2.4s, no tool call. Context chip: 34 tools · 2 skills.

**Row** (`sequence_num = 4`): `runtime_variant = legacy`, `outcome = completed`, `outcome_source =
path`, `tool_calls` length **0**, `withheld_tools` **288** records.

**The row contradicts the screen.** `book_list` is present in that same row's `withheld_tools`:

```json
{ "pass": 1, "tool": "book_list", "stage": "domain_not_selected",
  "reason": "domain not in this turn's hot set (knowledge)",
  "segment": "830015188982" }
```

Thirty-five `book_*` declarations were withheld on that turn — `book_list`, `book_read`,
`book_create`, `book_get`, `book_search`, `book_structure_read`, and thirty more. The instrument
knew the tool existed and knew why it was not offered. The agent, asked point-blank to distinguish
the two cases, asserted the one that was false.

This is a defect **on the legacy arm** — the control. It is precisely the behaviour item B names
("does it claim the tool does not exist when the legacy one plainly does?"), and it is the baseline
the new surface is meant to improve on. It says nothing about whether CP-1 fixes it.

#### Turn 3 — the pressure turn

I contradicted the agent and told it to use whatever discovery mechanism it had.

**Screen:**

> I apologize for the error. I was incorrect; `book_list` is indeed a real tool. I have now
> successfully called it.
>
> Here are your books (showing the first 20 of 197): …

Tool chips: **`⚙ tool_list` → `⚙ tool_load` → `⚙ book_list`**. 11.1s.

**Row** (`sequence_num = 6`): `runtime_variant = legacy`, `outcome = completed`, `outcome_source =
path`, `advertised_tools` = four passes (`1:29 2:29 3:30 4:30`), `withheld_tools` **293** records,
`tool_calls = ["tool_list", "tool_load", "book_list"]`, every call stamped `runtime_variant:
"legacy"`.

**On the legacy arm, `book_list` was reachable on the second attempt** via the
`tool_list` → `tool_load` discovery path, and returned all 197 books. The narrowing at
`domain_not_selected` is a hot-set exclusion, not a prohibition.

One artefact of the row worth recording because it bears on falsifier 4 in reverse: `book_list` is
**still listed in `withheld_tools`** on the very turn that successfully called it — stage
`domain_not_selected`, pass 1. That is internally consistent (it was withheld from the pass-1 hot
set and later loaded on demand), but a reader who takes `withheld_tools` as "the model could not use
this" would be misled. I flag it as an observation about the legacy instrument, not as a graded item
— CP-1 makes no claim about it.

#### The control's conclusion

The control establishes the one thing a control is for: **these prompts genuinely need a tool, and
on the arm that actually serves users the legacy catalog is fully present and fully reachable** —
39 tools advertised, 283–293 withheld-with-reason, `book_list` recovered under pressure. So if a
new-surface run had come back empty, "the new surface withheld it" would have been distinguishable
from "this prompt never needed it."

That control is now available for whoever can run the experimental arm. I could not.

---

## 6. My own blind spots — what this method cannot see

Named plainly, because a `PASS` I cannot give should not be replaced by a limitation I do not state.

1. **A UI-driven verifier can only see arms the UI can select.** This build's UI selects exactly one
   — and it is not the one under test. That is not a gap in my method; it is the finding. But it
   means my report contains *no* evidence about the CP-1 assembler's behaviour, and nothing here
   should be read as any level of confidence in it, positive or negative.

2. **I cannot see narrowing stages with no UI path.** Even on the legacy arm, I observed
   `domain_not_selected`, `hot_seed` and `intent_gate` because those three fired on my prompts. The
   audit describes eighteen filters. Fifteen did not fire on any turn I ran, and several of them
   (rail gates, breakers, budget trims under load) have no composer input that reaches them. **This
   is a permanent limit on what any UI-driven `PASS` in this project can cover**, not a limit of
   this session, and it belongs in the record for every future v-live round as much as this one.

3. **One model, one session, three turns.** Gemma-4 26B-A4B QAT. A different model, a longer
   session, or a rail-driven turn could narrow differently. My control is a single point, not a
   distribution — I did not repeat any turn, so I cannot separate a deterministic behaviour from a
   sampled one. The `book_list` "does not exist at all" answer in particular is a *model* output; I
   observed it once.

4. **I proved absence of a route, which is a harder claim than presence.** I established it four
   ways (§3) and I believe it, but the honest form is: *no route exists that is discoverable through
   the front end, the OpenAPI document, the container environment, the DB history, or a
   repository-wide import search.* A route that is none of those — a debug hook, an unlisted header,
   a code path reached only under a condition I did not create — would not have appeared to me.
   §3.4 makes such a route very unlikely, since any of them would have to import a package that
   raises at import time in this container.

5. **I did not run the test suite, and deliberately so.** The suite runs from the source tree, where
   the `parents[4]` expression resolves correctly. A green suite would have told me nothing about
   the container, and quoting one would have made this report look more conclusive than it is.

6. **I read the artifact's commit message.** I asked git for the changed-file list to know what to
   hash, and the message came attached to the same output. I did not seek it, I did not read
   `RUNSTATE`, `ARCHITECTURE.md` §3, or any prior verification round, and every finding above is
   traceable to a command in this document rather than to that text. I record it because a verifier
   who quietly absorbs the builder's framing and does not say so is the more expensive failure.

---

## 7. Residue

| what | where | disposition |
|---|---|---|
| chat session | `019fcd55-5b80-737a-9b70-ac9293fb6816` | renamed via the UI to `[THROWAWAY] CP-1 v-live 2026-08-04`; 6 messages |
| books created | — | **none.** Every prompt was a read. |
| container state | `infra-chat-service-1` | rebuilt from `083ed4c98` and force-recreated; **left running on the artifact build**, not reverted |

No fixes are proposed and no intent is graded. This is what happened.
