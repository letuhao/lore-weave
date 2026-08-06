# The data-plane access law — one read layer per plane

**Status:** PROPOSED · **§9 (`DPA-A7`) SEALED 2026-08-06** — the event-log port question is answered; §11 adds five rules found by measuring against outside practice
**Date:** 2026-08-06 · **Id family:** `DPA-*`
**Companions:** [`DATA_ARCHITECTURE.md`](../DATA_ARCHITECTURE.md) §3 *(the model this extends)* ·
[command hub](2026-08-06-command-hub.md) *(sealed)* ·
[ordinal spaces](2026-08-06-ordinal-spaces.md) *(the register pattern)*

> **PO, 2026-08-06:** *"Many sources reading, but only ONE read layer, and every read goes
> through it — so that later, changing one thing does not mean re-implementing and
> refactoring all the logic."*

Every number below was measured at `285c4baa3`.

---

## 1. Why — and the exact thing being bought

The goal is **not** tidiness. It is a bounded **change surface**:

> **`DPA-A1` — Changing how a plane is STORED must touch exactly ONE file per language
> runtime that consumes it.**

That is the actor hub's acceptance test (*"adding a feature touches zero files"*) one tier
over, and it is the property the PO named. Everything else in this document exists to make
`DPA-A1` mechanically true rather than aspirational.

### What the measurement found

| plane | port in code | who actually touches it | |
|---|---|---|---|
| **manifest** (resolved rules) | `ruleset-loader::resolve` → `Arc<D::Rules>` (`RLS-A12`); read via `RealityRules::rules()` | **1** accessor outside the owning crates | ✅ |
| **checkpoint** | `sim-core` checkpoint API | **2** call sites | ✅ |
| **actor RAM** | `Actor::quantity/set_quantity(&HubRegistry)` · `island/view.rs` | every `Actor` field is **private**; `hub` is private in commit-service too | ⚠️ held by Rust privacy, not by a check |
| **cache** | `contracts/cache/keys.yaml` + `KeyRegistry`, which **refuses an unregistered kind at runtime** | — | ✅ **the model to copy** |
| **meta DB** | `MetaWrite()` + `meta-sensitive-read-paths.yml` | two lints, one of which ran nowhere until 2026-08-06 | ✅ |
| **event log (ES)** | `dp-kernel`: `EventStore` **+** `EventReader` **+** `rebuilder::AggregateEventSource` — **three** traits | **19 raw `FROM events`, in 11 files, across 4 modules and 2 languages** | 🔴 |
| **Redis** | *nothing* | **40 files, 14 services, 3 languages** | 🔴 |

And `DATA_ARCHITECTURE.md` §3 already has exactly the right shape — a *Layer / Owner /
Notes* table over seven layers. **The game tier appears in that entire file twice.** The
model is correct and stops at the door of the tier being built.

---

## 2. `DPA-A2` — a plane is a DATUM WITH AN AUTHORITY, never a database

The first draft of this law was per-technology, and per-technology is wrong. Redis holds
**four unrelated things** — the proposal/event bus, the WS ticket store, rate-limit
counters, and the cache — with different owners, different lifetimes and different
consequences for being read from the wrong place. One rule over "Redis" would be four rules
wearing one name, and the first exception would dissolve it.

> **A plane is defined by the QUESTION IT ANSWERS.** Where it is stored is an
> implementation detail of the plane — which is precisely what `DPA-A1` promises to let you
> change.

This is also what makes the law survive a migration: moving the ticket store from Redis to
Postgres changes the plane's *storage*, not the plane.

---

## 3. `DPA-A3` — the law separates three things that are habitually confused

| | rule | already true where |
|---|---|---|
| **WRITE** | exactly **one writer path** per plane | meta (`MetaWrite`), and nowhere else by mechanism |
| **READ** | exactly **one read layer** per plane per language runtime; **every consumer goes through it** | actor RAM (by privacy), manifest, checkpoint |
| **SSOT** | exactly **one plane is authoritative** for a datum; every other copy declares itself **derived + rebuildable** | `DATA_ARCHITECTURE.md` §3, for the novel tier only |

Conflating them is how a codebase ends with N readers *and* N truths and cannot tell which
problem it has. They fail differently: a second writer corrupts, a second reader ossifies
(it is `DPA-A1` that it breaks), and a second SSOT silently diverges.

---

## 4. `DPA-A4` — three access ROLES, and one of them must NOT use the port

The obvious law — *"nothing touches a plane except through its port"* — is wrong, and it is
worth writing down why, because someone will otherwise "fix" the counter-example into
uselessness.

| role | rule | why |
|---|---|---|
| **consumer** | **MUST** use the read layer. No exceptions, no registered bypasses. | This is `DPA-A1`. A registered bypass is a change-surface leak with paperwork attached. |
| **auditor** | **MUST NOT** use the read layer. Reads the storage by construction-independent means, and its independence **is the product**. | `services/integrity-checker` reads `events` in Go against a Rust writer. Routed through the port it would verify the port against itself — the `V.2` mechanical-oracle argument, and the reason `scripts/declared-verb-oracle.py` is Python over a store the engine wrote. |
| **migrator** | Operates on the plane's **schema**, not its data. Outside the domain entirely. | A migration cannot go through a port that assumes the schema it is changing. |

**`DPA-A4.1` — an auditor is not an exception to the port; it is a different tier of
access.** The distinction is load-bearing: an exception accumulates, a role does not. The
registry declares roles, and a file with no declared role defaults to **consumer**, which is
the strict case (`NV-3`: default-uncovered is the failure this project keeps recording, so
the default here is the tightest rule, not the loosest).

---

## 5. `DPA-A5` — the read layer is per (plane × language runtime), and that is not a loophole

A single Rust trait cannot be the read layer for a Go consumer. So the port is
`(plane, runtime)` — and the number of runtimes is the number of ports, which the registry
states and the gate counts.

**This is the honest cost of a polyglot tree, and it is bounded by making it VISIBLE:**
adding a second runtime to a plane is a registry edit, in a diff, with a reason. What the
law refuses is the unbounded case — N files in one runtime each knowing the storage.

Mirror discipline between two runtime ports is the same problem `contracts/game-wire`
already solves (`turn.schema.json` has a Rust mirror test and a TS consumer checked against
it) and the same problem `meta-rs` ↔ `contracts/meta` already has. **A new cross-runtime
port inherits that obligation**: a machine-checked contract, not two hand-written halves.

---

## 6. The mechanism — a registry, and ONE gate that reads it

The repo has invented this pattern **three times already**, each with its own list:
`contracts/cache/keys.yaml`, `contracts/meta/meta-sensitive-read-paths.yml`, and the
hardcoded `sanctioned` map inside `meta-write-discipline-lint.sh`. **What is missing is not
a fourth gate — it is one registry the gates read.**

### 6.1 `contracts/data-planes.yaml`

```yaml
version: 1
planes:
  - id: event_log
    question: "what happened, in order, in this reality"
    ssot: true                      # authoritative; nothing else may claim this datum
    storage:                        # the part DPA-A1 promises you can change
      kind: postgres
      vocabulary: ["events"]        # table/key names that may appear ONLY inside a port
    ports:                          # DPA-A7: a LIST — three named jobs, one owner
      rust:
        append:  crates/dp-kernel/src/event_store.rs
        replay:  crates/dp-kernel/src/load_aggregate.rs
        rebuild: crates/rebuilder/src/lib.rs
      go: []                          # none yet — see §8
    compatibility: backward           # DPA-A8
    oldest_readable: 1
    consistency: strong               # DPA-A12
    deprecation: null                 # DPA-A12 — a path, declared even when unused
    access:
      - path: services/integrity-checker/
        role: auditor
        reason: "verifies the Rust writer's bytes from Go, independently. Through the port
                 it would verify the port against itself."
    status: open                    # counts printed every run until the debt is zero
```

Fields that carry the three rules of `DPA-A3`: `ssot` (one per datum, checked across
planes), `ports` (the read layer), `access` (roles). `derived_from` replaces `ssot: true`
for a rebuildable plane and **must** name what it rebuilds from.

### 6.2 `scripts/data-plane-gate.py`

The check is a **vocabulary scan**, which is the shape that already works twice here
(`hub-vocabulary-gate`, `engine-vocabulary-gate`):

> A plane's **storage vocabulary** — its table names, key prefixes, column names — may
> appear **only inside its declared ports**, in files whose role is `consumer`.

That is `DPA-A1` stated as something a grep can refuse, and it is why the acceptance test
is checkable at all: if the table name appears in one file, changing the table touches one
file.

**Non-vacuity obligations, from `docs/standards/non-vacuity.md` and today's three findings:**

| | |
|---|---|
| **subject check** | zero planes, zero ports, or zero scanned files ⇒ **FAIL**, never a green "nothing to lint". Two gates shipped that bug this week. |
| **selftest** | non-vacuous in both directions: it flags a raw read AND does not flag the port itself, a comment, or a same-named-but-different identifier. |
| **role default** | a file with no row is a **consumer** (strict), so a new file is covered on its first line. |
| **no silent cap** | every `status: open` plane prints its outstanding count every run. A gate that narrows its own scope must say by how much. |
| **port must exist** | a `ports:` path that is not a real file ⇒ FAIL. A registry pointing at nothing is the phantom-registration shape `design-lint` already refuses. |
| **one SSOT** | two planes claiming `ssot: true` for one datum ⇒ FAIL. |

### 6.3 Bite tests owed before it is believed

Plant a raw read outside the port → RED · route it through the port → GREEN · empty the
registry → RED · point a port at a missing file → RED · declare a second SSOT → RED ·
mark a consumer as `auditor` without a reason → RED.

---

## 7. `DPA-A6` — the actor-RAM plane is held by privacy, and that is a MECHANISM

`Actor`'s fields are all private and `quantity()` requires `&HubRegistry`, so a consumer
**cannot** read a quantity without the read layer. That is stronger than a grep and it
should be said plainly rather than replaced.

**What the gate adds is the thing privacy cannot see:** privacy is one `pub` away from
gone, and nothing today would notice. The registry pins the port; the gate reds if the
plane's vocabulary escapes it — including via a newly-`pub` field or a convenience getter.

⇒ **Where a language can enforce the port, let it. The gate guards the ENFORCEMENT, not the
data.** Adding a gate that duplicates what the type system already refuses is a check that
cannot fail.

---

## 8. Landing it without a big-bang refactor

40 Redis files and 19 raw event reads are not one commit, and a law that arrives all at once
arrives disabled. The order is chosen so the gate is **real and non-vacuous from its first
run**:

| step | planes | why first |
|---|---|---|
| **1** | manifest · checkpoint · actor RAM · cache · meta | already single-ported. The gate lands **green over five real planes** — so it has a subject, and so `status: open` below is measured against a working check rather than a hope. |
| **2** | **event log** | one plane, 11 files, and it needs §9's decision first |
| **3** | **Redis, split into its four planes** (bus · ticket store · rate limits · cache) — per `DPA-A2` | 14 services, so it is per-plane work, not one sweep |
| **4** | `DATA_ARCHITECTURE.md` §3 grows the game-tier rows | the doc is the human-readable face of the registry; it must not become a second, drifting copy — §3 links to the registry, it does not restate it |

Steps 2 and 3 are `status: open` rows from day one, with their counts printed on every run.
**That is the `TOO_SLOW` lesson applied in advance:** an honest classification that nobody
sees is indistinguishable from an unguarded invariant. A row here is a debt with a clock,
never a resting place.

---

## 9. `DPA-A7` — the event-log port: SEALED 2026-08-06, **both (a) and (b)**

The question was whether `dp-kernel::EventStore`, `dp-kernel::EventReader` and
`rebuilder::AggregateEventSource` are **(a)** one hub split three ways or **(b)** three
genuinely different jobs.

**PO: approve (a) AND (b).** Read as a single rule, because the two are answers to different
halves of the question and the tension between them is only apparent:

> **`DPA-A7` — ONE plane, ONE owner, THREE NAMED PORTS.** The three are genuinely different
> jobs — append · read-to-replay · read-to-rebuild-aggregate — so collapsing them into one
> trait would force every consumer to depend on capabilities it does not use, which is the
> interface-segregation failure and would make the port *harder* to use than raw SQL
> (`DPA-A11`). **And** they are three faces of one plane with one owner, so they must be a
> **declared surface** rather than three traits that happen to exist — which is what the tree
> has today, with two in `dp-kernel` and one in a separate `rebuilder` crate.

**⚠ This is my reading of a two-word approval, written down so it can be refused.** If the
intent was one of the two alone, say so and this section is wrong rather than the build.

### What it decides, concretely

| | |
|---|---|
| the 19 raw reads | judged against *"does this file use one of the three DECLARED ports"* — **not** against *"is there only one trait"* |
| the registry | `event_log` gets `ports: {rust: [append, replay, rebuild]}` — a list, and the list is the closed set |
| the work | **not** a collapse-to-one refactor. It is: name the three, give them one home, and route the consumers |
| what stays open | the count of genuine violations, which is only measurable once the three are named — recorded as a number the gate prints, never estimated here |

**The tree already BEHAVED as if (b) and said so nowhere.** That is the weaker kind of true —
shaped like a decision nobody made — and `DPA-A7` is the sentence that was missing.

---

## 10. What this document does NOT decide

| | |
|---|---|
| which Redis planes exist exactly | step 3 — four is the measured guess (bus · tickets · rate limits · cache), and it needs its own pass |
| the wire shape of any port | ports are code; this governs who may bypass them |
| whether a plane should MOVE storage | `DPA-A1` makes moving cheap; it does not argue for a move |
| the ES port count | §9, the PO's |

---

## 11. Measured against the outside — what we already have, and the five things we do not

Searched 2026-08-06. The point of this section is not reassurance; it is to find the fields
the registry is missing **before** it is written, because a registry is a contract and
`QTY-A10(c)`'s lesson generalises: a field is far cheaper to add now than after every plane
declares one.

### What the industry calls what we already have

| ours | the name outside | reading |
|---|---|---|
| one read layer per plane | **ports & adapters / hexagonal** — *"ports are abstract interfaces defining contracts for external interactions; business logic depends on abstractions rather than implementations"* | same shape, arrived at independently |
| SSOT + derived, rebuildable copies | **SSOT** — Wikipedia's own article says keeping copies read-only while only the master is updated *"is an instance of CQRS"* | our derived planes are CQRS read models under another name |
| the gates | **architecture fitness functions** — *"an objective, automated check that a given architectural characteristic still holds"*, run in the pipeline. The canonical worked example given is **"no direct database calls from the UI layer"** | that is `tier-capability-gate`, built this morning, before I had the term for it |
| the island as authority | **server-authority model** — *"the server is the single source of truth; clients are trusted only to report their own inputs"* | matches, and `CWC-D3` is the same rule at the message level |
| `contracts/*` + gates in CI | **data contracts** — and the named failure is *"organizations that create contract documentation but don't build automated monitoring discover contracts become stale and untrustworthy"* | this project's single most-recorded defect, with the correct fix already adopted |

So the architecture is not unusual — it is a fairly strict reading of patterns that have
names. **That is the good news and it is also why the gaps matter: the gaps are the fields
those patterns carry that ours does not.**

### The five gaps, each becoming a registry field

> **`DPA-A8` — every plane declares a COMPATIBILITY POLICY.**
> Industry practice is that a contract is *"formal, **versioned**, machine-readable"* and
> that *"schema updates must pass compatibility checks... so new versions don't break older
> consumers."* We do this **for one plane and nowhere else**: the ruleset has
> `RULESET_SCHEMA_VERSION`, a frozen codec per version (`QTY-A11`) and `SCHEMA_VERSION_OLDEST`
> — a real compatibility window. `contracts/game-wire/*.json` has none.
> ⇒ each plane declares `compatibility: backward | forward | full | none` and the oldest
> version it still reads. A plane whose consumers span two runtimes and declares `none` is a
> defect the gate can name.

> **`DPA-A9` — every DERIVED plane declares a FRESHNESS BOUND, and reading past it REFUSES.**
> The sharpest finding. Industry: *"a table updated hourly needs `max_freshness: 60 minutes`"*
> and — the part that matters — *"if a feature is stale beyond its SLA, the consumer should
> receive a documented null with a reason code, **not a six-hour-old value that silently
> degrades**."* We already do exactly this in **one** place: `contracts/cache/keys.yaml`
> carries `ttl_seconds` **and** `invalidation_trigger` on every entry. No other derived plane
> declares a bound at all.
> ⇒ a derived plane without a freshness bound is unbounded staleness with no one accountable,
> and a stale read that returns a value is the failure mode this project already refuses
> everywhere else under the name *"a silent no-op"*. **The refusal is the point, not the
> number.**

> **`DPA-A10` — `derived_from` forms a checked DAG, and it is what catches a second SSOT
> transitively.**
> The named data-mesh pitfall is *"metadata fragmentation... cross-domain consumption
> complicated by inconsistent access patterns"*, and the named catalog pitfall is
> **stale metadata** — this repository's own most-recorded defect.
> ⇒ every derived plane names what it rebuilds from; the gate refuses a cycle and refuses a
> chain that does not terminate at an `ssot: true` plane. **A direct "two planes claim the
> same datum" check misses the transitive case**, which is the one that actually happens: A
> is derived from B, B from C, and someone quietly writes to A.

> **`DPA-A11` — the port must be the EASIEST path, and that is an obligation on the PORT, not
> on the gate.**
> The most useful sentence found: *"organizations that adopt domain ownership without
> investing in the self-serve platform discover that teams default to doing things the way
> they always have — because **the easy path doesn't exist**."*
> ⇒ if reading through the port is more work than one line of raw SQL, the gate stops being a
> guard and becomes an obstacle to route around — and the route people take will be
> mislabelling themselves `auditor`, which is the one role that bypasses. **A port that is
> harder than the thing it replaces will be defeated by the people it is meant to help**, and
> no amount of gate is a fix for that. Each port owes an ergonomics answer in its own PR.

> **`DPA-A12` — every plane declares its CONSISTENCY CLASS and a DEPRECATION path.**
> Two smaller ones, both grounded. Consistency: CQRS read models *"lag behind writes by
> milliseconds to seconds"*, and the MMO literature splits **authoritative state** (resources,
> inventory) from **hot state that can be slightly stale** (presence, leaderboards) — our
> planes span exactly that range (island RAM is strong, projections eventual, cache
> TTL-bounded) and none of them says which. Deprecation: contracts carry *"ownership contact
> and deprecation timelines"*; we retired `player_character_index` this morning **ad hoc**,
> and it worked only because a re-pointed test caught three live references. That should be a
> declared path, not a good day.

### What this changes about the plan

Nothing in §8's order — but the registry schema in §6.1 grows five fields **before** the
first plane is written into it. That is the whole reason this section exists ahead of the
build rather than after it.

---

## 12. Ids introduced

| id | |
|---|---|
| `DPA-A1` | changing a plane's storage touches ONE file per consuming runtime |
| `DPA-A2` | a plane is a datum with an authority, never a database |
| `DPA-A3` | one writer · one read layer · one SSOT — three rules, not one |
| `DPA-A4` | three roles: consumer (must use the port) · auditor (must NOT) · migrator |
| `DPA-A4.1` | an auditor is a role, not a registered exception |
| `DPA-A5` | the port is per (plane × runtime); a second runtime is a visible registry edit |
| `DPA-A6` | where a language enforces the port, the gate guards the enforcement |
| `DPA-A7` | the event log is ONE plane, ONE owner, THREE NAMED PORTS (append · replay · rebuild) — sealed as both (a) and (b) |
| `DPA-A8` | every plane declares a compatibility policy and the oldest version it still reads |
| `DPA-A9` | every derived plane declares a freshness bound, and reading past it REFUSES rather than returning a stale value |
| `DPA-A10` | `derived_from` forms a checked DAG terminating at an SSOT — this is what catches a second SSOT transitively |
| `DPA-A11` | the port must be the EASIEST path; an obligation on the port, not on the gate |
| `DPA-A12` | every plane declares its consistency class (strong · eventual · TTL-bounded) and a deprecation path |

---

## 13. Sources

Consulted 2026-08-06 for §11. Listed because the section's claims are about what OTHER
systems do, and a claim about the outside world with no citation is the same shape as an
unmeasured figure.

- [Single source of truth — Wikipedia](https://en.wikipedia.org/wiki/Single_source_of_truth)
- [Ports and Adapters — AWS Labs, Open Resource Broker](https://awslabs.github.io/open-resource-broker/patterns/ports_and_adapters/)
- [Architecture Fitness Functions](https://synchronium.github.io/software-architecture-wiki/concepts/fitness-functions.html)
- [Architecture Testing for Java with ArchUnit — Loiane Groner](https://loiane.com/2026/07/architecture-testing-java-archunit/)
- [Read Models — CQRS, Event Sourcing & co.](https://www.cqrs.com/event-driven-architecture/read-models/)
- [CQRS Pattern — Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)
- [Data Contracts: Schemas, SLAs and Enforcement That Actually Ship](https://datadef.io/guides/en/data-contracts)
- [Data Contract Templates: What to Include (and What Most Teams Get Wrong)](https://promethium.ai/guides/data-contract-templates-what-to-include/)
- [Data Mesh After the Hype: What Actually Works](https://datalakehousehub.com/blog/2026-05-data-mesh-after-hype/)
- [Metadata Management in Data Mesh — Federated Ownership Patterns](https://promethium.ai/guides/metadata-management-data-mesh-federated-ownership-patterns/)
- [Server authority model — Roblox Creator Hub](https://create.roblox.com/docs/projects/server-authority)
- [Persistent multiplayer state without chaos](https://packagemain.tech/p/persistent-multiplayer-state-without)
