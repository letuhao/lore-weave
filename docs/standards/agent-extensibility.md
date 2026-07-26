# Agent Extensibility Standard

Patterns for adding a **user-authorable agent capability** (a skill, slash command,
declarative hook, subagent, MCP-server registration, plugin bundle — anything a user or
agent registers that later shapes an LLM turn) to the LoreWeave platform.

These are not theory: every rule below **caught a real bug** during the Agent
Extensibility Registry build (P0→P5, 6 `/review-impl` rounds) and is grounded in
industry practice (Claude Code subagents/hooks/skills; the official MCP Registry's
"aggregators implement additional security checks" posture; the 2026 MCP tool-poisoning /
rug-pull literature). Read this before building the next capability so the shape doesn't
drift. Owning track spec: `docs/specs/2026-07-02-agent-extensibility-registry.md`.

---

## 1. The capability shape (storage → resolver → consumer → proof)

A new user-authorable capability follows ONE shape end-to-end:

1. **Storage** — a table in `agent-registry-service` carrying the LOCKED 3-tier tenancy:
   a `tier` (system/user/book) + a scope key (`owner_user_id` and/or `book_id`) + a
   per-tier partial `UNIQUE(scope, name)` (never a global `UNIQUE(name)` — that is the
   entity-kinds bug). A `CHECK` pins exactly one scope key per tier.
2. **CRUD** on agent-registry: create (validated, quota-capped for user tier), list/get/
   patch/delete gated by `authorizeRowWrite` (user→own · system→admin · book→live ≥edit
   grant + `Active()`), every not-authorized path returns **404 (anti-oracle)**, never 403.
3. **`/internal/<capability>` resolver** (X-Internal-Token) — returns the *effective* set
   for a `(user_id, book_id)` context, `enabled`-filtered, with **higher-tier-shadows-by-
   name** (book ▷ user ▷ system, first-seen dedup). This is the seam a consumer reads.
4. **Consumer** (chat-service) — a **degrade-safe client** (mirror `user_skills_client`:
   any failure → empty result, NEVER raises into the turn) + the **pure logic** that acts
   on the resolved set, unit-tested in isolation.
5. **Proof** — unit tests on the pure logic + a **live E2E through a real chat turn**
   (local lm_studio model, $0) proving the capability reaches the model *by effect*, not
   just that the resolver returned rows.

**Why:** this exact shape repeated for skills, commands, hooks, and subagents. Codifying
it means the next capability is a fill-in-the-blanks, and the tenancy/anti-oracle/degrade
guarantees come for free instead of being re-derived (and re-broken).

**The consumer live-smoke is mandatory** (rule `new-cross-service-contract-needs-consumer-
live-smoke`): a new registry→chat contract MUST be exercised through the consumer's real
path. Command expansion looked correct in unit tests but the model saw the raw `/cmd` —
the router persisted the message before `stream_response` mutated it; only a live turn
caught it.

## 2. Validate-parity — import/bulk MUST reuse the single-create validator

Any path that creates members in bulk (a bundle import, a batch, a seed) **must run the
exact same validator as the single-create path** — not a subset.

**Why (P5 MED):** bundle import checked only a skill's slug, so a bundle could smuggle a
skill whose body carried executable `scripts/` content — defeating the "skills are
prompt-only" guard that `validateSkill` enforces on the normal create path. The fix was
to call `validateSkill` per member. A bulk path is an attractive place to forget a guard;
assume every guard on the single path must hold on the bulk path.

## 3. No silent no-op — the API advertises ONLY what the engine implements

If a resolver/catalog advertises a capability variant, the engine MUST act on it. When
some variants aren't wired yet, **reject the unwired ones at the API** (create + patch) —
do not accept-and-ignore.

**Why (P4 HIGH/MED):** the hook engine only handled `deny`, but the API accepted
`require_approval` (silently ran the tool with no gate) and `annotate`/`post_turn`
(silently did nothing). A user opted into a guardrail that no-op'd. Fixes: wire
`require_approval`; gate the API to the WIRED `(event, action)` matrix at create AND
patch; the FE builder offers only wired combos. The DB CHECK stays forward-compatible —
**the API is the gate, not the schema.** A resolver returning a variant the consumer
drops on the floor is a defect, not a feature.

## 4. Quarantine-by-default + reuse the security pipeline for EVERY external source

Anything reaching outside the platform (a user-registered MCP server, an official-registry
ingest, any third-party endpoint) is untrusted **regardless of the source's reputation**,
and flows through one pipeline: **SSRF guard → model-capability rejection → supply-chain
scan → quarantine (pending/suspended) → federate only after it clears.** Secrets go in the
AES-GCM vault; the internal envelope (`X-Internal-Token`) is NEVER sent to an external
host; egress is IP-pinned (resolve-then-connect) with an allowlist + response cap +
circuit breaker.

**Why (P3 + industry):** the official MCP Registry does namespace-auth only and *relies on
aggregators to add security checks*; and **verification ≠ safety** — the official channel
shipped a backdoor (Postmark) and a verified marketplace leaked 3,000 credentials
(Smithery); a scan of 1,899 servers found 5.5% tool-poisoning. So "it's on the official
registry" is not a reason to skip the scan. A rug-pull (clean tools at scan, poisoned
later) means an external server also needs a **scheduled re-scan**, not just a
register-time one (`D-REG-P3-SCHEDULED-RESCAN`).

## 5. Closed-set args = enum; the resolver never silently no-ops

A capability-selection argument on any tool (a panel id, a subagent name, a domain, a
mode) is a **closed set → an `enum`**, never a bare `string`. A reject path returns a
`result.error` the model can self-correct from — never a bare `{ok:false}` or a silent
drop. This extends the LOCKED Frontend-Tool-Contract rule to server-side capability tools.

**Why:** a weak local model sent `panel:"editor"` instead of `panel_id:"editor"`; a bare
`string` gave it nothing to anchor on and the resolver silently no-op'd, so the model
hallucinated success. An enum pins the value AND reinforces the arg name; an error message
lets the model recover. Register the arg in `CLOSED_SET_ARGS`; verify the loop by its
EFFECT (a live turn), not by the tool-call appearing in the stream.

---

## Checklist — adding a new user-authorable agent capability

- [ ] Table: `tier` + scope key + `CHECK` (one key per tier) + per-tier partial `UNIQUE(scope, name)`. Additive migration.
- [ ] CRUD: create (validated + user-tier quota), list/get/patch/delete via `authorizeRowWrite`, **404 anti-oracle** on every deny.
- [ ] Reserved/collision names rejected at create (and the same guard mirrored in the consumer if it parses names).
- [ ] `/internal/<capability>` resolver: enabled-filter + higher-tier-shadow-by-name + `catalog_version`.
- [ ] Consumer: degrade-safe client (failure → empty, never raises) + pure logic + unit tests.
- [ ] If it has an import/bundle path: **reuse the single-create validator** (§2).
- [ ] If it advertises variants: **the API accepts only wired variants** (§3); FE offers only those.
- [ ] If it reaches an external host: the full **quarantine + scan + SSRF/egress** pipeline (§4); no secret in a JWT-facing serializer (`has_secret` only).
- [ ] Any capability-selection tool arg is an **enum**, resolver returns `result.error` on a miss (§5); register in `CLOSED_SET_ARGS`.
- [ ] **Live E2E through a real turn** (or a real browser for GUI) proves the effect, not just the wire. `/review-impl` if it's load-bearing (tenancy, secrets, external, nested execution).
