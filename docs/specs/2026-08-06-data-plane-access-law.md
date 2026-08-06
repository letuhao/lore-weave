# The data-plane access law — one read layer per plane

**Status:** PROPOSED — the PO asked for the spec; §9 names the one decision that is theirs
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
    ports:
      rust: crates/dp-kernel/src/event_store_pg.rs
      go:   <none yet — see §8>
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

## 9. The one decision that is the PO's, and it blocks step 2

**The event log has THREE port traits** — `dp-kernel::EventStore`, `dp-kernel::EventReader`,
and `rebuilder::AggregateEventSource`.

Either:

- **(a) one hub split three ways** — in which case 11 files are in violation and the work is
  a collapse to one port; or
- **(b) three genuinely different jobs** — append · read-to-replay · read-to-rebuild-aggregate
  — in which case they are three ports of one plane, each with its own consumers, and the
  violation count is much smaller.

**The answer decides whether those 19 reads are defects or legitimate port implementations,
and I cannot derive it.** It is an architecture question about what the kernel's storage
contract IS, not a measurement.

Evidence for whichever way it goes: `event_store.rs` and `load_aggregate.rs` are separate
modules today, and `rebuilder` is a separate crate — so the tree already behaves as if (b),
without anywhere saying so. That is the weaker kind of true: shaped like a decision nobody
made.

---

## 10. What this document does NOT decide

| | |
|---|---|
| which Redis planes exist exactly | step 3 — four is the measured guess (bus · tickets · rate limits · cache), and it needs its own pass |
| the wire shape of any port | ports are code; this governs who may bypass them |
| whether a plane should MOVE storage | `DPA-A1` makes moving cheap; it does not argue for a move |
| the ES port count | §9, the PO's |

---

## 11. Ids introduced

| id | |
|---|---|
| `DPA-A1` | changing a plane's storage touches ONE file per consuming runtime |
| `DPA-A2` | a plane is a datum with an authority, never a database |
| `DPA-A3` | one writer · one read layer · one SSOT — three rules, not one |
| `DPA-A4` | three roles: consumer (must use the port) · auditor (must NOT) · migrator |
| `DPA-A4.1` | an auditor is a role, not a registered exception |
| `DPA-A5` | the port is per (plane × runtime); a second runtime is a visible registry edit |
| `DPA-A6` | where a language enforces the port, the gate guards the enforcement |
