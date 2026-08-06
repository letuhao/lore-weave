# The data-plane access law — one read layer per plane

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3** — 🔴 **this document IS the
failure.** It re-derived `DP-A1` (only-sanctioned-path), `DP-A2` (control/data split), `DP-A5`
(tier taxonomy), `DP-A10` (primitives not queries) and `DP-A12` (type-gated access) as
`DPA-A1..A18`, without opening `06_data_plane/` once. See §0.

**Status:** 🔴 **BLOCKED by a cold-start red team, 2026-08-06 — do not build against this document.**
14 findings; the four highest-cost were re-verified by hand and every one holds. **§9 (`DPA-A7`) is
the PO's seal and survives as a DECISION; the spec's expression of it does not.** See §0.

~~Ready for a red team~~ · §14/§15 were written before the review and that part held — the review's
finding is that §15 does not close what it claims, not that §14 concealed anything.
**Date:** 2026-08-06 · **Id family:** `DPA-*`
**Companions:** [`DATA_ARCHITECTURE.md`](../DATA_ARCHITECTURE.md) §3 *(the model this extends)* ·
[command hub](2026-08-06-command-hub.md) *(sealed)* ·
[ordinal spaces](2026-08-06-ordinal-spaces.md) *(the register pattern)*

> **PO, 2026-08-06:** *"Many sources reading, but only ONE read layer, and every read goes
> through it — so that later, changing one thing does not mean re-implementing and
> refactoring all the logic."*

Every number below was measured at `285c4baa3`.

---

## 0. 🔴 RED-TEAM VERDICT — BLOCK (2026-08-06)

A cold-start reviewer with no access to this document's reasoning was told to refute it. It
returned **BLOCK** with 14 findings. **Four were re-verified by hand before acceptance, and all
four hold.** The document stays in the tree unamended below this line, because a spec edited to
hide its review is worth less than a spec that carries one.

### The four that were re-measured, and what they cost

| # | the spec said | measured | why the spec was wrong |
|---|---|---|---|
| **1** | *"`DATA_ARCHITECTURE.md` … stops at the door of the tier being built"*, and Redis's port is *"nothing"* | **§5 is a dedicated section on this exact plane**, and [`DATA_ARCHITECTURE.md:343`](../DATA_ARCHITECTURE.md) already states **invariant `I7` — *"`meta-worker` is the only consumer of `xreality.*` Redis Streams"*** | **a `DPA`-shaped single-reader rule for a Redis plane already existed, in the file this spec claims is silent.** A Phase-0 AUDIT-EXISTING miss — the failure `CLAUDE.md` opens with |
| **2** | Redis: **40 files, 14 services, 3 languages** | **22 modules; Python is the LARGEST group (32 `.py` vs 27 `.go` vs 11 `.ts`)** | the grep passed `--include=*.rs --include=*.go --include=*.ts` and **omitted Python entirely**. §8 step 3 is sized against a number that excluded its biggest consumer language |
| **3** | manifest: *"**1** accessor outside the owning crates"* | **10** non-test `.rules()` call sites | the grep matched `Ruleset::engine_default()` — **CONSTRUCTION** — and the result was then labelled *accessor*. A different thing than the word used for it |
| **4** | *"the repo already runs six drills … it has simply never been pointed at the data planes"* | `scripts/restore-drill.sh` **is already a rebuild drill over a data plane** (per-shard restore into an isolated DB, row-count comparison vs live, `archive_verification_log`, `BackupDrillFailed`), plus `chaos/drills/` and `contracts/chaos/drill.go` | `DPA-A17` is not a new pattern for this tree — it is `restore-drill.sh` generalised, and the spec should EXTEND it rather than propose beside it. Second audit miss |

### The structural findings — not measurement, design

| | |
|---|---|
| **the ports named are the wrong FILES** | §6.1 names three trait definitions. Grepped: **zero storage vocabulary in any of them.** Every `FROM events` lives in ADAPTERS the registry does not name. §6.2's *"port must exist"* check passes while the row is semantically empty — **the phantom-registration shape it claims to refuse, in its own example** |
| **`DPA-A1` vs `DPA-A7`** | *"one file per runtime"* against three Rust ports. And two of the three sealed ports return `Vec<EventEnvelope>` — **the exact shape `DPA-A16` names as the cause of the semantic bypass.** One of §9 and §15 is wrong and the document does not know which |
| **`DPA-A15` is unachievable where it is needed** | `AggregateEventSource` is implemented across a crate boundary, so `EventEnvelope` **cannot** be `pub(crate)`. It closes the hole only for single-crate planes — i.e. where §15 admits it was already closed |
| **the rebuild drill is circular** | its subject set is chosen by `derived_from` — **the declaration the drill exists to falsify.** A plane that lies `ssot: true` owes no drill. It also passes a double-write: wipe Redis, replay, rebuild succeeds, two SSOTs stand |
| **`storage.vocabulary` is required and unimplementable** | for **3 of the 5** step-1 planes (actor RAM · manifest · checkpoint) — they have no tables and no key prefixes. Either the field is optional (schema not closed) or step 1 cannot land |
| **`ssot` XOR `derived_from` breaks on the exemplar** | the cache plane is **fan-in** from four unrelated sources, one of which is a hand-edited config file — not a plane. §2 splits Redis into four planes for holding four unrelated things and then counts the cache, which does the same, as one |
| **`DPA-A9`'s only precedent is its counterexample** | a TTL cache **serves** stale, it does not refuse — and `sensitive_paths` ships `invalidation_trigger: ""` with a note saying it leans on the TTL. That is `on_stale: serve`, which `DPA-A9` calls the defect |
| **`DPA-A18` has no varying subject** | the only auditor is a separate Go service nothing can import regardless. `NV-1`, in a document that cites `NV-3` twice |

### What survived

`DPA-A11` (the port must be the easiest path) · `DPA-A16`'s countable trigger · `DPA-A4`'s
auditor carve-out · the claim that every `Actor` field is private · that both meta lints ran as
described · that `game-wire` carries no version · **and that the event-log plane is genuinely
un-ported** — 13 SQL sites across 7 production files in three languages. The problem is real;
this document's account of it is not yet accurate.

### The pattern, recorded

Findings 2 and 3 are the same defect this run logged three times already (`BDR-9`, `BDR-17`,
`BDR-19`): **a number shipped under the word MEASURED, produced by a command that measured
something else.** Finding 1 and 4 are `AUDIT-EXISTING` — the phase this repository's own
`CLAUDE.md` opens with, skipped in a document about not duplicating what already exists.

**Next action is the PO's**, and the options are not equal: amend, or rewrite from the corrected
measurements. Nothing should be built against §6.1.1 until that is decided.

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

### The severity, stated accurately

**Nothing here was about to collapse.** Five of the seven planes are already correctly
single-ported, and the two that are not have been that way for months without producing a
corruption. Overstating this would be its own kind of unreliability, and a spec that opens
with an emergency is a spec that gets its costs waved through.

What the missing law actually costs is **erosion, not collapse**: the change surface widens
one file at a time until moving a plane's storage is a multi-week refactor instead of a
one-file edit. `DPA-A1` is the thing being bought, and its absence is felt on the day
somebody tries to change something — not before.

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

### 6.1.1 The complete field set — decided BEFORE the first plane is written

A registry is a contract, and `QTY-A10(c)`'s lesson generalises: a field costs one edit now
and N edits after every plane declares one. So the schema is closed here, not grown later.

| field | required | carries | refused when |
|---|---|---|---|
| `id` · `question` | yes | `DPA-A2` — the plane is the QUESTION, not the store | two planes answer the same question |
| `ssot` **xor** `derived_from` | yes | `DPA-A3` · `DPA-A10` | both, or neither; or a `derived_from` chain that cycles or never reaches an `ssot: true` plane |
| `storage.kind` · `storage.vocabulary` | yes | `DPA-A1` — the names the gate scopes to the ports | an empty vocabulary (a plane the gate cannot check is worse than an unregistered one) |
| `ports.<runtime>` | yes | `DPA-A5` · `DPA-A7` — a MAP of named jobs per runtime | a path that is not a real file; an empty map on a plane with any consumer |
| `compatibility` · `oldest_readable` | yes | `DPA-A8` | `none` on a plane with ports in two runtimes |
| `consistency` | yes | `DPA-A12` — `strong` · `eventual` · `ttl_bounded` | `strong` on a plane that is `derived_from` something |
| `freshness` | iff `derived_from` | `DPA-A9` — the bound, AND `on_stale: refuse` | a derived plane with no bound; `on_stale: serve` (a stale value returned silently is the defect) |
| `owner` · `deprecation` | yes | `DPA-A12` — who answers, and how it is retired | absent owner; `deprecation` naming an unknown successor plane |
| `access[]` | no | `DPA-A4` — role per path, default `consumer` | `auditor` or `migrator` with no `reason`; an `auditor` path whose output is read by domain code |
| `status` | yes | the debt, printed every run | `open` with no count, or `closed` while findings exist |

**`ssot` xor `derived_from` is the whole of `DPA-A3`'s third rule in one line**, and the
`xor` is the load-bearing part: a plane that declares neither is a datum with no authority,
which is exactly the state you cannot detect once it exists.

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

### ⚠ The limit of this section, so nobody treats it as authority

**These are search-result summaries, not sources read in depth.** They were enough to find
five fields the registry was missing, which is what they were for. They are **not** a
literature review, and nothing further should be sealed on their strength — if a rule below
turns out to matter, read the primary source before it hardens.

### What this changes about the plan

Nothing in §8's order — but the registry schema in §6.1 grows five fields **before** the
first plane is written into it. That is the whole reason this section exists ahead of the
build rather than after it.

---

## 12. `DPA-A13` — ENUMERATE the characteristics; do not wait to discover them

The most useful thing the comparison produced is not a field. It is a method.

**Three invariants were found unguarded on 2026-08-06 by a PO question** — the kernel
outside `crate-purity-gate`'s scope, the transport tier with no capability rule, and a
meta-write gate that ran nowhere. None was found by a check. All three had been true and
unguarded for weeks, and each would have gone on being true until the day it wasn't.

That is the predictable outcome of a tree that has strong **mechanism** discipline
(non-vacuity, bite tests, ratchets) and assembles its **taxonomy** from first principles
each time: every rule has to be derived from an incident, so every lesson is paid for once
in production.

> **`DPA-A13` — every architectural characteristic this repo CLAIMS must name either a
> fitness function that checks it, or a declared gap. The list is enumerated and reviewed;
> it is not discovered.**

`docs/standards/README.md` is already the catalogue of cross-cutting rules and
`gate-wiring-gate.py` already answers *"is every gate wired"*. **Neither answers the
question in the other direction** — *"is every claimed characteristic gated?"* — and that
direction is where all three of this morning's findings lived.

⚠ **This id does NOT ship with this spec.** It is a platform-wide obligation over
`docs/standards/`, not a data-plane rule, and folding it in would make this document govern
something it did not measure. Recorded here because this is where it was found; its home
and its gate are a separate round.

---

## 13. `DPA-A14` — a port returns DOMAIN types, never storage types

The vocabulary scan in §6.2 greps for a plane's storage names. **It cannot see a port that
re-exports the storage through its own type system**, and that is the most likely way
`DPA-A1` is defeated in practice:

```rust
// The gate is GREEN on this file — it is the port. And every consumer of
// `EventRow` now knows the column set, so changing the table still touches N files.
pub struct EventRow { pub seq: i64, pub payload: serde_json::Value, /* … */ }
pub fn read(..) -> Vec<EventRow>
```

> **A port's return type is part of the port.** It must be a DOMAIN type — one whose shape
> is a fact about the plane's *question*, not about its *storage*. A port that hands back
> rows has moved the coupling from the SQL string into the struct, where the grep cannot
> follow it.

This is the leaky-abstraction failure of ports & adapters, and it is why *"is there a port"*
is the wrong acceptance question. The right one is `DPA-A1` itself: **change the storage and
count the files.**

**Mechanisable, partly:** a port's public return types must not be declared in the port
file's own storage-adjacent module, and a `#[derive(sqlx::FromRow)]`/`serde` row type must
not appear in the port's public signature. That catches the common shape. It does not catch
a hand-written struct that mirrors the columns, and §14 says so.

---

## 14. What this design does NOT prevent

Written before the red team rather than after it. A design that lists its own holes is
cheaper to attack usefully than one that has to be pried open first, and every item here is
a place the gate will report GREEN while `DPA-A1` is broken.

| hole | why the gate misses it | current answer |
|---|---|---|
| **the mirroring struct** | `DPA-A14` catches the derive-based row type; a hand-written struct with the same fields is indistinguishable from a domain type by any check | none. The acceptance test (§1) is the only detector, and it is human |
| **semantic bypass of a correct port** | a consumer calls the port and then re-implements the plane's invariants on the result — the port was used, the coupling remains | none |
| **Redis as a store of record** | the law is per-plane, and the check is a NAME check; a plane that quietly becomes authoritative does not rename itself | `ssot` xor `derived_from` is a declaration, and a false declaration is a lie a gate cannot see |
| **mislabelled `auditor`** | the one role that bypasses the port, so it is the route a defeated developer takes (`DPA-A11`) | `reason` is required, and an auditor whose output feeds domain code is refusable — but only if the gate can see that edge |
| **shape knowledge without names** | a consumer that knows column ORDER or a key FORMAT without ever naming the table | none |
| **the registry itself going stale** | it is a document, and this repo's most-recorded defect is exactly that | `ports` paths must resolve, `status` counts print every run, `vocabulary` must be non-empty — three checks that make a stale row red rather than quiet |

**The pattern across the first five: every one is a case where the gate is green and a human
would still see the problem.** That is the honest boundary of a grep-based fitness function,
and it is the reason `DPA-A1` is written as a *countable acceptance test* rather than as
*"use the port"* — the test survives all six.

---

## 15. Closing them — and the reason a better grep was never the answer

Every hole in §14 has the same signature: it is a property of **source text** that a
scan cannot distinguish from its legitimate twin. Iterating on the regex is the wrong move;
it produces a gate that cries wolf, and this project has already recorded what happens then
(*"crying wolf got the check switched off"* — `D-SPEC-CODE-ENUM-PARITY`).

> **Static analysis closes a mistake that has a NAME. Privacy closes one that has a
> REFERENCE. A drill closes one that has only a SHAPE.**

Three mechanisms, and the third is the one that was missing. **This repo already runs six
drills** — `closure-drill`, `relocate-drill`, `canary-drill`, `migrate-drill`,
`freeze_drill`, `provision_drill` — plus a `chaos/` tree and `SR07_chaos_drills.md`. The
pattern is established; it has simply never been pointed at the data planes.

### `DPA-A15` — make the STORAGE shape inexpressible, rather than detectable

The first hole was **misstated in §14**, and restating it dissolves most of it. The problem
is not *"a struct that mirrors"* — you cannot stop anyone copying a domain type, and there
is no reason to. It is *"a struct that mirrors **the storage**"*.

> A plane's storage row type is **`pub(crate)` or narrower**, and the port returns an
> **owned domain value**. Then a consumer cannot name the storage shape, so the widest thing
> it can copy is what the port already chose to expose.

**The coupling becomes bounded by the port's own surface** — which is the property
`DPA-A1` actually needs. This is `DPA-A6` again: where a language can enforce the boundary,
let it, and gate the enforcement rather than the data. `Actor` already works exactly this
way, and it is why the actor-RAM plane needed no grep at all.

### `DPA-A16` — a port exposes the plane's QUESTIONS, not its rows

The semantic bypass — call the port, then re-implement the plane's invariants on the result
— is caused by a port that hands back atoms. CQRS says this in its own words: *read models
are designed around questions, unlike a schema designed around writes.* A port returning
`Vec<Event>` guarantees every consumer folds; a port returning the folded answer makes the
bypass unwritable.

**The countable trigger, since this one has no clean static check:** the **second** consumer
that performs the same fold over a port's output. One consumer folding is a consumer; two
folding identically is a missing port method, and the second one is the signal. That is a
review rule with a number in it rather than a taste.

⚠ **This is the one hole that stays partly human**, and §14's row for it should be read as
still open. Named honestly rather than closed by assertion.

### `DPA-A17` — the two drills, which is where the un-greppable cases go

> **The rebuild drill.** Every `derived_from` plane owes a drill that **WIPES it and rebuilds
> it from its declared source**. A plane that cannot survive being deleted is
> **authoritative, whatever it declared** — and the drill is what says so.

This converts `ssot` / `derived_from` from an unfalsifiable label into a test. It is the
direct answer to *"Redis quietly became a store of record"*: nobody has to notice the intent,
because the drill fails.

> **The storage-shuffle drill.** In a throwaway environment, rename a column, reorder the
> projection, change a key prefix — then run the suite and count what broke. **Anything
> outside the port that breaks knew the SHAPE.**

That is `DPA-A1` **executed** rather than stated, and it is the only mechanism that reaches
hole #5 (shape knowledge with no name). It is also the acceptance test made repeatable: the
spec's headline claim stops being a promise and becomes a number somebody ran.

**Both are drills, not pre-commit gates** — they need a stack and they are destructive by
design. That places them with `closure-drill` and `migrate-drill`, in the CI leg those
already occupy, and it is the honest cost: they run on a schedule, not on every commit, so
they catch drift **late but certainly** rather than never.

### `DPA-A18` — an auditor's output may not reach a domain decision

The `auditor` role is the one bypass, so it is the route a defeated developer takes
(`DPA-A11`). The constraint that makes the label expensive to lie about is a dependency
rule, not a naming rule:

> A module declared `auditor` **must not be imported by domain code**. Its output is a
> report, an alert or a test verdict — never an input to a decision the engine makes.

That is checkable in exactly the shape `crate-purity-gate` already checks (and that ArchUnit
calls a dependency constraint). `integrity-checker` passes it by construction: it is a
separate service whose output is an alert. A module that wants the bypass AND wants to be
read by the domain has to pick one.

### What is left after all four

| §14 hole | closed by | residue |
|---|---|---|
| mirroring struct | `DPA-A15` — privacy | copying the DOMAIN type, which is harmless |
| semantic bypass | `DPA-A16` — partly | **genuinely open**; a countable review trigger, not a check |
| Redis-as-SSOT | `DPA-A17` rebuild drill | a drill that is skipped; `gate-wiring`'s `TOO_SLOW` lesson applies |
| mislabelled auditor | `DPA-A18` — dependency rule | an auditor nobody imports and nobody reads, i.e. dead code |
| shape knowledge | `DPA-A17` shuffle drill | found late, on a schedule, not at commit time |
| registry stale | §6.1.1's three checks | — |

**One of six stays open and it is named.** That is a better answer than six closed by
assertion, and it is what the red team should attack first.

---

## 16. Ids introduced

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
| `DPA-A13` | enumerate the claimed characteristics and gate each, or declare the gap — do not wait to discover them. **Platform-wide; does NOT ship with this spec** |
| `DPA-A14` | a port returns DOMAIN types, never storage types — otherwise the coupling moves from the SQL string into the struct, where the grep cannot follow |
| `DPA-A15` | make the STORAGE shape inexpressible (`pub(crate)` row types, port returns an owned domain value) rather than detectable — the coupling then bounded by the port's own surface |
| `DPA-A16` | a port exposes the plane's QUESTIONS, not its rows. Countable trigger: the SECOND consumer folding identically is a missing port method |
| `DPA-A17` | two drills — **rebuild** (wipe a derived plane and rebuild it; one that cannot survive it is authoritative whatever it declared) and **storage-shuffle** (rename/reorder/re-prefix and count what breaks outside the port). `DPA-A1` executed, not stated |
| `DPA-A18` | an `auditor` module must not be imported by domain code — its output is a report, never an input to a decision |

---

## 17. Sources

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
