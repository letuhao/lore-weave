# Feature Workflow

> **Step-by-step for an AI agent designing a new feature in the LLM MMO RPG track.** Follow in order. Skipping steps creates integration blockers for the next agent.

---

## 1. Session start (5 minutes)

- [ ] Read [`README.md`](../README.md) tail of latest SESSION_HANDOFF.
- [ ] Read all 7 files in `00_foundation/` top-to-bottom.
- [ ] Skim [`ORGANIZATION.md`](../ORGANIZATION.md) + [`AGENT_GUIDE.md`](../AGENT_GUIDE.md) if new to the track.
- [ ] **Do NOT load `02_storage/*` or `03_multiverse/*` yet** — only when Step 4 tells you to.

---

## 2. Scope the feature

Answer these 5 questions before anything else:

1. **Which service does it live in?** (`03_service_map.md`) — extend an existing service, or new service?
2. **What data does it own?** — a new table? Extends an existing schema?
3. **What events does it emit? Consume?** — give the event names, not hand-waving.
4. **Which kernel APIs does it call?** (`04_kernel_api.md`) — MetaWrite? AssemblePrompt? outbox? All three?
5. **Which IDs does it claim?** (`06_id_catalog.md`) — pick the next free number in the relevant namespace.

If you can't answer all 5 in 2 sentences each, the feature scope is unclear. Stop and discuss with the user before designing.

---

## 3. Pick the target folder

| Feature type | Goes in | Example |
|---|---|---|
| Extends a category feature | `catalog/cat_NN_*.md` (append row) | Add a new NPC capability → `catalog/cat_05_NPC_systems.md` |
| Changes a PC-* rule | `04_player_character/<section>.md` | Adjust PC-B1 death behavior default |
| New V1 deferred-big-feature spec | `docs/03_planning/LLM_MMO_RPG/10X_<NAME>.md` (new file, per ORGANIZATION.md §7 "new DFs graduate here") | DF4 World Rules design doc |
| New multiverse rule / resolution | `03_multiverse/<appropriate chunk>.md` | New M-resolution for a new M-risk |
| Kernel change (storage / security / SRE) | `02_storage/<chunk>.md` — **this is kernel territory** | New retention tier, new RPC auth layer |
| Cross-service integration concern | New file at `00_foundation/` level? **No — escalate.** Foundation only grows with architect sign-off. |

**Rule of thumb:** if the feature is "consume kernel and deliver user value", it goes in `catalog/`, `04_player_character/`, or a new DF doc. If it's "change how services integrate", it's kernel work.

---

## 4. Read ONLY the specific chunks you need

This is the critical step. Do not load entire subfolders. Examples:

| Feature | Load these |
|---|---|
| Chat-service message routing | `02_storage/R06_R12_publisher_reliability.md` · `02_storage/S09_prompt_assembly.md` · `03_service_map.md` |
| PC death → NPC conversion | `02_storage/R08_npc_memory_split.md` · `03_multiverse/06_M_C_resolutions.md` (§9.9 severance if applicable) · `04_player_character/04_lifecycle.md` · `decisions/deferred_DF01_DF15.md` (DF1/DF4) |
| Quest category gating | `03_multiverse/06_M_C_resolutions.md` (M3-D3) · `catalog/cat_04_PL_play_loop.md` · `decisions/deferred_DF01_DF15.md` (DF4) |
| New admin command | `02_storage/R13_admin_discipline.md` · `02_storage/S05_admin_command_classification.md` · `02_governance/ADMIN_ACTION_POLICY.md` · `05_llm_safety/02_command_dispatch.md` |
| New event schema | `02_storage/R03_schema_evolution.md` · `02_storage/R06_R12_publisher_reliability.md` |
| New user-visible state | `02_storage/S10_severance_vs_deletion.md` · `05_vocabulary.md` (GoneState section) |
| New canon-writing flow | `02_storage/S13_canonization_pre_spec.md` · `03_multiverse/06_M_C_resolutions.md` (§9.7 M3) · `decisions/deferred_DF01_DF15.md` (DF3) |

**Principle:** foundation tells you WHICH chunks are relevant. Load only those. `02_storage/` is 36 chunks — you rarely need more than 3.

---

## 5. Claim your work area

- [ ] Open the target subfolder's `_index.md`.
- [ ] Set the `Active:` line to `<your-agent-id> <ISO UTC timestamp> <scope of your edit>`.
- [ ] If it is already claimed by another agent on a recent timestamp (< 2h), stop and pick a different area OR coordinate via SESSION_HANDOFF.

---

## 6. Design

- [ ] Follow the design doc shape of the subfolder you're in (most have an obvious template from neighboring chunks).
- [ ] Use vocabulary from `05_vocabulary.md`. Do not invent enums.
- [ ] Use IDs from `06_id_catalog.md`. Do not renumber.
- [ ] For every cross-service interaction, cite the kernel API from `04_kernel_api.md`. No hand-waving about "the service just calls X".
- [ ] If you find yourself needing to bypass an invariant, stop and follow `01_READ_THIS_FIRST.md` §"When you think the kernel is wrong".

---

## 7. Integration review (self-review before commit)

Before writing the commit, check:

- [ ] Every inter-service RPC is added to `contracts/service_acl/matrix.yaml` (I11).
- [ ] Every new LLM call goes through `AssemblePrompt()` (I2, I10).
- [ ] Every meta-table write uses `MetaWrite()` (I8).
- [ ] Every lifecycle transition uses `AttemptStateTransition()` (I9).
- [ ] Every cross-service event uses `outbox.Write()` (I13).
- [ ] Every new table has PII classification tags (`@pii_sensitivity` etc) per S8.
- [ ] Every new admin command declares `ImpactClass` (S5).
- [ ] No stable ID was renumbered (I15).
- [ ] No model name is hardcoded (I12).
- [ ] The `Active:` header you set in Step 5 is cleared.
- [ ] The subfolder's `_index.md` is updated with your new entry / status change.

If you fail any check, fix before committing. CI will catch most violations but self-review saves a round-trip.

---

## 8. Commit

- [ ] Stage only the files you touched (`git add <path>` per file, no `git add -A`).
- [ ] Commit message: `<type>(<scope>): <brief>` per the repo convention (see `git log --oneline | head` for examples). Include:
  - What changed (the feature name + target service)
  - Why (which kernel contract / user value)
  - Evidence (tests pass / no lint violations / foundation unchanged if applicable)
  - Which stable IDs were created / changed
- [ ] Include SESSION_HANDOFF row in the SAME commit (per CLAUDE.md §Phase 10+11 rule).

---

## 9. New-service checklist

If your feature adds a NEW service (not just extending an existing one), the above steps apply PLUS:

- [ ] Append row to `03_service_map.md` — name, language, owned DB, events in/out, responsibility.
- [ ] Register SVID (per `02_storage/S11_service_to_service_auth.md` §12AA).
- [ ] Add per-service Postgres role.
- [ ] Declare Postgres-DB name; update `reality_registry`-provisioner if per-reality, or static if shared meta.
- [ ] Add ACL matrix rows for every RPC the new service makes AND receives.
- [ ] Create runbook at `docs/sre/runbooks/<domain>/<service>.md` (SR3 27-runbook V1 gate applies if V1-critical).
- [ ] Add SLO alerts per SR1 if the service owns a user-facing SLI.
- [ ] Add deploy-class annotations per SR5 (major/minor/patch).

All in the same commit as the service scaffold. Cross-cutting = single commit, so a reviewer can see the full integration surface at once.

---

## 10. Anti-patterns to stop at

These are signals that the feature is drifting and needs escalation, not more design:

- "The invariant doesn't apply to us because ..." — no it does; find a different approach.
- "We'll worry about integration later." — you're writing an integration-breaker.
- "I'll just add a new enum value for this." — stop; update `05_vocabulary.md` with architect sign-off.
- "I'll skip the ACL matrix entry; it's just for this one call." — CI will block you anyway; add it.
- "I'll use direct SQL against the other service's DB for now." — I4 violation; use RPC.
- "The kernel chunk says X but my feature needs Y." — stop; use the escalation path in `01_READ_THIS_FIRST.md`.

If you catch yourself saying any of these, pause and re-read `02_invariants.md`. Every invariant exists because a previous attempt to skip it cost time and broke something.
