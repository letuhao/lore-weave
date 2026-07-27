# 25 — Producer identity & trust derivation

> **Status:** BUILT — 2026-07-27 (spec + all four §6 items, same day). Closes **IAS-Q2** and **IAS-Q3**, which turned out to be one
> question. Axioms `PID-A1..A6`, decisions `PID-D1..D7`, open `PID-Q1..Q3`.
> **Prefix `PID` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Builds on: [22 ingress](22_ingress_and_admission.md) (the front door this protects) ·
> [07 event model](07_event_model/02_invariants.md) (EVT-A7 producer trust, EVT-A8 untrusted⇒T6) ·
> [`02_storage/S11`](02_storage/S11_service_to_service_auth.md) (the 4-layer service-auth standard
> this is a V1 subset of).

---

## 1. The finding

`IAS-Q2` asked whether `producer_service` on the bus is authenticated. `IAS-Q3` asked whether
EVT-T4's *"trusted by construction"* is verified or assumed. Investigating both landed on the same
line of code:

```rust
// services/commit-service/src/admission.rs:34,45 — both read straight off the wire
pub producer_service: String,
pub event_category:   String,

// :268,278 — and the category selects WHICH VALIDATOR SUBSET RUNS
Category::parse(&proposal.event_category)   //  "T1" => T1,  _ => T6
```

**PID-F1 — the trust tier is self-declared by the message.** [EVT-A7](07_event_model/02_invariants.md)
assigns trust to **producers**; the code derives it from a **string in the payload**. A proposal that
writes `"event_category": "T1"` receives the reduced player subset and skips `a5-intent`,
`a6-sanitize`, `a6-output` and `canon-drift` — *the entire LLM-safety tier*. An LLM-originated
proposal claiming to be a player therefore escapes exactly the stages that exist for LLM output.

**PID-F2 — `producer_service` authorises nothing.** It is used only as one third of the EVT-L3 dedup
triple. Nothing compares it to anything.

**PID-F3 — the bus itself is open.** Neither `infra/docker-compose.yml` nor
`infra/foundation-dev/docker-compose.yml` sets `requirepass`, and there are no Redis ACLs. Anyone who
can reach Redis can `XADD` a proposal claiming any producer.

### 1.1 Two things worth stating plainly

**It is not exploitable today, and that is not reassurance.** All ten stages are `NotRun`, so the
skipped subset is currently empty. The defect goes live the moment the *first* LLM-safety stage is
built — which means it is a bug planted ahead of the feature that arms it, and the person building
that stage would have no reason to look here.

**One thing was already right.** `Category::parse` maps unknown values to `T6` — the **full**
pipeline. The unknown branch fails safe. The gap is that `"T1"` is a *known* value that grants a
reduction, and nothing checks whether the sender is entitled to it.

### 1.2 This is the confused-deputy bug again

The same shape was fixed at the WS edge earlier the same day: `ChannelRoom` took `actorEntityId`
from join options, so a client could act as another player. The fix was not to validate the claim
harder — it was to **stop reading it** and stamp the actor from the authenticated session.

> **PID-A1 — a trust-bearing attribute is never read from the message. It is DERIVED from a verified
> identity.** Validating a self-declared attribute more carefully is not a fix; the attribute must
> not be on the wire at all.

---

## 2. PID-A2..A4 — the mechanism

### PID-A2 — identity is proven, not asserted

Every proposal carries a **MAC over the exact bytes the producer sent**, computed with that
producer's own key. `producer_service` survives on the wire **only as a key-lookup hint**, and a hint
that does not verify is a rejection — so claiming to be someone else fails at the MAC rather than
being believed.

**PID-D1 — HMAC-SHA256, keyed per producer.** Not blake3 (already a Rust dependency) because the
signature is a **polyglot contract**: `game-server` is TypeScript and gets HMAC-SHA256 from Node's
built-in `crypto` at zero dependency cost, while blake3 would need a native/WASM binding added to a
service that currently has almost none. `hmac` + `sha2` on the Rust side are small and ubiquitous.
The asymmetry is the point — put the cost where it is cheapest to carry.

**PID-D2 — the MAC covers the RAW `proposal` bytes, and the signature travels beside them.** The
producer serialises its proposal, MACs those exact bytes, and XADDs `proposal <json>` plus
`producer_sig <hex>` as **separate stream fields**. This deletes the canonicalisation problem
outright: there is no agreed JSON key order to get wrong, no re-serialisation on the verifying side,
and no drift between a Rust `serde_json` and a JavaScript `JSON.stringify`. Signing *inside* the
JSON would have required both languages to agree on a canonical form — the classic way a polyglot
signature scheme dies quietly.

### PID-A3 — the category is derived, never transmitted

**`event_category` is REMOVED from the wire.** Admission holds a producer registry:

| Producer | Category | Rationale |
|---|---|---|
| `game-server` | `T1` Submitted | player input via the WS edge (EVT-A7 Player-Actor) |
| `llm-driver` | `T6` Proposal | LLM output — EVT-A8 forbids anything else |
| *unknown* | **reject** | default-DENY (PID-A4) |

The category is a property of *who signed*, so a producer cannot elect its own validator subset. This
mirrors `TurnSubmit` carrying no `actor` field (CWC-D3): the field's absence is the guarantee.

### PID-A4 — default-DENY, as a named stage

Verification is a new admission stage, `producer-identity`, running **first** — before schema, before
dedup. An unknown producer, a missing signature, or a MAC mismatch is a `Verdict::Fail` at that
stage, recorded like any other rejection (CS-A4: never silent).

First because everything after it is work done on behalf of a caller whose identity is unestablished,
and because the dedup triple itself contains `producer_service` — deduping on an unverified identity
lets a forger evict a real proposal from the dedup window.

---

## 3. PID-A5 — what this is NOT

**It is not a replacement for S11.** [S11](02_storage/S11_service_to_service_auth.md) specifies four
layers: SVID identity, mTLS, an ACL matrix, and user-context propagation. This is a **V1 subset of
layer 1** that needs no PKI, no SPIRE, no sidecar — and the piece it delivers is precisely the one
the bus needs today.

**PID-D3 — when SVIDs land, only the verifier changes.** The registry lookup becomes SVID validation;
`derive_category(verified_identity)` is untouched. The value of PID-A1 is that it puts the derivation
in one place, so the identity mechanism underneath can be replaced without revisiting every call
site.

**PID-D4 — Redis auth is defence in depth, not the fix.** `requirepass` + per-service ACLs should be
set (PID-Q2), but they cannot solve this: every legitimate producer writes to the **same** proposal
stream, so a stream-level ACL cannot distinguish producers *within* it. Transport auth keeps
strangers off the bus; the MAC is what distinguishes the parties allowed on it.

**PID-A6 — a shared platform token would NOT have worked.** `LOREWEAVE_INTERNAL_TOKEN` exists and is
tempting. It is a single bearer secret shared by every service, so it proves *"someone internal"* and
nothing else — the very distinction this document needs. Per-producer keys are the minimum that
carries identity rather than membership.

---

## 4. Decisions

| Id | Decision | Rationale |
|---|---|---|
| **PID-D1** | HMAC-SHA256, per-producer keys | polyglot: native in Node, standard in Rust; blake3 would cost game-server a binding |
| **PID-D2** | MAC covers raw `proposal` bytes; sig is a sibling stream field | no canonical-JSON agreement to get wrong across two languages |
| **PID-D3** | Category derived by `derive_category(verified_identity)`, one place | S11 SVIDs later replace the verifier, not the derivation |
| **PID-D4** | Redis `requirepass`/ACL is defence in depth | all producers share one stream; ACLs cannot separate them |
| **PID-D5** | `event_category` removed from the wire entirely | an absent field cannot be forged (CWC-D3 precedent) |
| **PID-D6** | `producer-identity` runs FIRST, default-DENY | dedup keys on producer; deduping an unverified identity is itself an attack |
| **PID-D7** | Keys from env, one per producer, service fails to start without its own | no hardcoded secrets; a missing key must not silently degrade to unsigned |

## 5. Open

| Id | Question | Notes |
|---|---|---|
| **PID-Q1** | Key rotation — two valid keys during a roll? | Registry should accept a list per producer; not built |
| **PID-Q2** | Redis `requirepass` + per-service ACLs | Config/infra, tracked separately from this code change |
| **PID-Q3** | Does the MAC need a timestamp/nonce against replay? | EVT-L3 dedup already makes a replayed proposal a duplicate; a signed stale proposal cannot be applied twice. Revisit if a producer ever signs something not covered by the dedup triple |

## 6. Build order — DONE

1. ~~Verifier + registry~~ ✅ `commit-service::producer`.
2. ~~Admission~~ ✅ `producer-identity` stage runs first; `admit_signed`; `event_category` gone from
   `Proposal`. 8 tests incl. the escalation itself.
3. ~~Producer side~~ ✅ `game-server/src/ws/producer-sign.ts`, Node `crypto`, zero new deps.
4. ~~Polyglot fixture~~ ✅ `contracts/agent/producer-identity.fixture.json`, asserted from both
   sides and **bite-proven** (changing what TS signs reds it).

### 6.1 What building it settled

**`Category::parse` became dead code, and that was the signal.** Removing `event_category` from the
wire left the string→tier mapping with no caller. It was deleted rather than kept: a function that
turns an arbitrary string into a trust tier, sitting unused and public, is an invitation to re-add
the field — and the next person to do it would have no reason to suspect why it was removed. The
category now has exactly one source.

**The fixture was generated by the PRODUCER side, on purpose.** Node computed the signature and Rust
verified it, so the passing test is a genuine cross-language check rather than one implementation
agreeing with itself. Generating it from the verifier would have proved nothing about the producer.

**An empty registry means "not enforced", and the spine now says so out loud.** Defaulting to
enforcement would have broken every existing caller; defaulting to silence would have let an
operator run an unauthenticated bus and see nothing unusual. It announces which mode it is in at
startup — the same reasoning as the rate limiter marking its decisions `degraded` (CNC-F16), and
the same failure it prevents: a security control that quietly stops applying.
