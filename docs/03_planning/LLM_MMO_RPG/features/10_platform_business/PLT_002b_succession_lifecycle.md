# PLT_002b — Succession Lifecycle (Sequences + Acceptance Criteria)

> **Continued from:** [`PLT_002_succession.md`](PLT_002_succession.md). That file holds the contract layer (§1-§10): user story, domain, EVT mapping, ownership_transfer aggregate, tier+scope, DP primitives, state machine, action surface, pattern choices, failure-mode UX, cross-service handoff. This file holds the dynamic layer (§11-§17): worked sequences, acceptance criteria, deferrals, cross-references, readiness.
>
> **Conversational name:** "Succession lifecycle" (SUC-L). Read [`PLT_002_succession.md`](PLT_002_succession.md) FIRST.
>
> **Category:** PLT — Platform / Business
> **Status:** **CANDIDATE-LOCK 2026-04-25** (split from PLT_002 to honor 800-line cap during closure pass; §14 acceptance criteria added — 10 scenarios; Option C event terminology applied)
> **Stable IDs in this file:** none new — all aggregates/concepts defined in PLT_002 (root). This file references them.
> **Builds on:** PLT_002 §1-§10. Same DP contracts + Charter (PLT_001) + Forge (WA_003) + Heresy (WA_002) world_stability check.

---

## §11 Sequence: full happy-path (Scenario A end-to-end)

Compressed timeline; total 8 days.

```text
T0:    Tâm-Anh initiates transfer via Forge
       state = Pending { recipient: false, admin: false }
       expires_at = T0+14d

T0+30min:  Hoài-Linh sees banner, accepts
           state = Pending { recipient: true, admin: false }

T1d:   admin op_A reviews transfer, hits Approve
       op_B reviews + concurs (within 5min)
       state advances: Pending { recipient: true, admin: true }
       → IMMEDIATELY transitions to Cooldown { entered_at: T1d+5min }

T1d+5min:  Cooldown begins. UI shows countdown to both parties
           "Transfer finalizes in 7 days unless cancelled."
           (Tâm-Anh has 7 days to change her mind.)

T8d+5min:  Background sweeper at T8d+5min finds the cooldown elapsed
           t3_write_multi atomic:
             OwnershipTransfer.Finalized
             reality_registry.owner_id = hoai_linh
             coauthor_grant for tam_anh CREATED (BecomesCoAuthor)
             coauthor_grant for hoai_linh DELETED (no longer Co-Author; she's Owner)
           advance_turn EVT-T8 Administrative SuccessionFinalize ✓
           ForgeAuditEntry ✓
           bump forge_roles_version for both ✓

T8d+5min+1s:  Both UIs show: "✓ Reality ownership transferred. Hoài-Linh is now RealityOwner."
              Forge tab updates on next view-load.

T8d+5min+~4min:  Both JWT auto-refreshes pick up new roles.
                 Tâm-Anh's Forge UI: now shows Co-Author capabilities only
                 Hoài-Linh's Forge UI: now shows RealityOwner capabilities
```

---

## §12 Sequence: owner cancels during cooldown (Scenario B)

```text
T0:    Initiate (as §11)
T1d:   Both approvals → Cooldown begins

T4d:   Tâm-Anh changes mind. Forge → "Active transfer" → "Cancel"
       Confirmation: "Are you sure? This will abort the transfer to Hoài-Linh."
       Confirms.
       │
       POST /v1/forge/.../succession/{T1}/owner-cancel
       state = Aborted { reason: CooldownCancelled, by: tam_anh }
       advance_turn EVT-T8 Administrative SuccessionOwnerCancel ✓
       ForgeAuditEntry ✓
       │
       ▼
T4d+1s:  Both UIs show: "Transfer cancelled by RealityOwner. Reality ownership unchanged."
         Hoài-Linh's grant remains as Co-Author.
         Tâm-Anh remains as RealityOwner.
```

(Identical mechanism if Hoài-Linh withdraws via `RecipientWithdraw` — sub-shape SuccessionRecipientWithdraw and reason=CooldownCancelled.)

---

## §13 Sequence: admin rejects during Pending (Scenario C)

```text
T0:    Initiate
T0+30min:  Hoài-Linh accepts → state = Pending { recipient: true, admin: false }

T2h:   Admin op_X reviews. Notices: Tâm-Anh's account had a password reset 3 days ago.
       Possible account-recovery suspicion. Admin rejects:
       │
       POST /v1/admin/.../succession/{T1}/reject
       body: { reason: "Account security review needed; please contact support to verify identity. Refer to ticket #12345." }
       (Single admin OK for reject — easier escape per §7.5)
       │
       state = Aborted { reason: AdminRejected, by: op_X, note: "Account security review..." }
       advance_turn EVT-T8 Administrative SuccessionAdminReject ✓
       ForgeAuditEntry ✓
       │
       ▼
T2h+1s:  Both UIs notified:
         Tâm-Anh: "Transfer rejected by admin: Account security review needed..."
         Hoài-Linh: "Transfer rejected by admin. Tâm-Anh remains RealityOwner."

         If false-positive, support resolves; Tâm-Anh re-initiates after verification.
```

---

## §14 Acceptance criteria (LOCK gate)

The design is implementation-ready when gateway-bff + world-service + admin tooling can pass these scenarios. Each is one row in the integration test suite. LOCK granted after all 10 pass.

### 14.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-SUC-1 FULL HAPPY PATH** | §11 8-day timeline: initiate → recipient accept (T+30min) → admin op_A+op_B approve (T+1d) → 7d cooldown → Finalize at T+8d. | All state transitions logged in `OwnershipTransfer.stage_history`; Finalize executes atomic `t3_write_multi` with 4 ops (state Finalized + reality_registry.owner_id = recipient + outgoing's `coauthor_grant` CREATED if PostTransferFate=BecomesCoAuthor + recipient's `coauthor_grant` DELETED); `forge.roles_version` bumps for both users; subsequent JWT refresh shows updated roles. ForgeAuditEntry logged with `approval_chain: [op_A, op_B]`. |
| **AC-SUC-2 BECOMES-CO-AUTHOR FATE** | Outgoing owner's `PostTransferFate = BecomesCoAuthor` (default). | After Finalize, `coauthor_grant` row exists for outgoing owner with role=Co-Author + `granted_by` = new owner; outgoing UI shows them as Co-Author with capability matrix per PLT_001 §6.1. |
| **AC-SUC-3 REMOVED FATE** | Outgoing owner's `PostTransferFate = Removed`. | After Finalize, NO `coauthor_grant` row for outgoing owner; outgoing user retains LoreWeave account but loses access to this reality; subsequent Forge access returns `CapabilityDenied { reason: "no grant" }`. |

### 14.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-SUC-4 OWNER CANCEL DURING COOLDOWN** | §12 sequence: Tâm-Anh cancels at T+4d during cooldown. | `OwnerCancel` POST accepted; state transitions to `Aborted { reason: CooldownCancelled, by: tam_anh }`; reality_registry.owner_id UNCHANGED; recipient's `coauthor_grant` UNCHANGED (still Co-Author); ForgeAuditEntry logs cancel + reason. |
| **AC-SUC-5 ADMIN REJECTS DURING PENDING** | §13 sequence: admin op_X rejects with reason. | Single-admin reject OK per §7.5; state → `Aborted { reason: AdminRejected, by: op_X, note }`; both parties notified with reason; ForgeAuditEntry logs admin reject + reason. Reality ownership unchanged. |
| **AC-SUC-6 PENDING TTL EXPIRY** | 14 days elapse without both `recipient_accepted=true` AND `admin_approved=true`. | Background sweeper finds expired Pending row; transitions to `Aborted { reason: PendingExpired }`; ForgeAuditEntry logs expiry; both parties notified on next session. Reality ownership unchanged. |
| **AC-SUC-7 RECIPIENT WITHDRAW DURING COOLDOWN** | Hoài-Linh accepted, admin approved, cooldown started; Hoài-Linh withdraws at T+5d. | `RecipientWithdraw` POST accepted; state → `Aborted { reason: CooldownCancelled, by: recipient }`; same effect as §12 (no ownership change). |

### 14.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-SUC-8 SINGLETON-ACTIVE** | Try to initiate a 2nd transfer for the same reality while a 1st is in `Pending` state. | Pre-check (§3.1.1) finds existing Pending row; reject with `OwnershipTransferAlreadyActive { transfer_id: <existing> }`; UI toast: "Đã có yêu cầu chuyển nhượng đang chờ. Vui lòng hủy nó trước khi bắt đầu mới."; first transfer untouched. |
| **AC-SUC-9 BLOCKED DURING SHATTERED** | `world_stability.current_stage = Catastrophic` or `Shattered`; user tries InitiateTransfer. | Pre-check per §8.8 reads `world_stability`; blocks initiate; UI modal: "Thực tại đang ở trạng thái '<stage>'. Không thể chuyển nhượng cho đến khi ổn định trở lại."; no transfer row created. |
| **AC-SUC-10 FINALIZE FAILURE RECOVERY** | At T+8d, `t3_write_multi` at Finalize fails partway (DB transaction error). | Postgres rolls back the multi-write; `OwnershipTransfer.state` stays in `Cooldown` (not Finalized); sweeper retries on next 1h cycle. After 24h of failed retries, sweeper escalates to admin queue per §8.7; ops alerted with structured log. Reality ownership unchanged during all retry attempts. |

**Lock criterion:** all 10 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-acceptance criteria + Option C terminology) → `LOCKED` (after tests).

---

## §15 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| SUC-D1 | Transfer to non-Co-Author (skip the Charter step; recipient is fresh user with extra verification) | V2+ — needs identity verification challenges |
| SUC-D2 | Configurable cooldown per reality (V1 fixed 7d; V2+ range 1d-30d) | V2+ ops |
| SUC-D3 | PostTransferFate options beyond BecomesCoAuthor / Removed (e.g., BecomesReadOnly, RetainAdminEscape) | V2+ |
| SUC-D4 | Allow transfer during Catastrophic / Shattered stages with admin override | V2+ + WA_002 stage policy |
| SUC-D5 | V2+ pre-approval bypass for long-tenure Co-Authors (>6 months) skipping admin step | V2+ ops |
| SUC-D6 | Multi-recipient transfer (transfer to a co-owner pair) | V3+ — needs new "co-ownership" data model |
| SUC-D7 | Reality forking on transfer (recipient gets a fork, original owner keeps original) | V3+ — depends on DF8 canon-fork |
| SUC-D8 | Account-deletion automatic transfer (if owner deletes account, what happens?) | V2+ + auth-service policy |
| SUC-D9 | Notification protocol beyond in-app banner (email, push) | V2+ ops |
| SUC-D10 | Owner-impersonation defense (multi-factor auth at Initiate time) | V2+ security |
| SUC-D11 | Admin approval queue UI / workflow tooling | V2+ frontend (admin console) |
| SUC-D12 | Audit retention policy for transfer history (V1 keeps everything; V2+ may archive after 90d) | V2+ ops + S5 retention |
| **HER-D8 inherited** | V1 emission via EVT-T8 Administrative-only vs V1+30d EVT-T11 WorldTick (OwnershipChanged) at reality root | **Tracked in [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md)** drift-resolutions table (HER-D8 row). Inherited from WA_002 Heresy lifecycle; PLT_002 §10.4 Finalize emission follows the same V1/V1+30d split. The boundary folder is the single source of truth. |

---

## §16 Cross-references

- [`PLT_002_succession.md`](PLT_002_succession.md) — root file (§1-§10): contract layer
- [PLT_001 Charter](PLT_001_charter.md) — Co-Author lifecycle; Succession requires recipient to be Co-Author at initiate
- [WA_003 Forge](../02_world_authoring/WA_003_forge.md) — UI surface; Succession UX lives in Forge
- [WA_002 Heresy](../02_world_authoring/WA_002_heresy.md) — `world_stability` consulted at initiate (block during Catastrophic/Shattered)
- [02_storage C03 reality_registry] — owner_id ground-truth; mutated atomically at Finalize
- [02_storage S05 admin classification] — S5 dual-actor for admin approve
- [auth-service] — UserId resolution; account-status checks
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T8 Administrative sub-shapes Succession*
- [`_boundaries/01_feature_ownership_matrix.md`](../../_boundaries/01_feature_ownership_matrix.md) — `ownership_transfer` ownership = PLT_002 (formerly WA_005)
- [`_boundaries/03_validator_pipeline_slots.md`](../../_boundaries/03_validator_pipeline_slots.md) — HER-D8 drift authoritative
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella

---

## §17 Implementation readiness checklist

Combined check across PLT_002 (root) + PLT_002b (this file). Both files together satisfy every required item per DP-R2 + 22_feature_design_quickstart.md §"Required feature doc contents":

PLT_002 (root):

- [x] **§2** Domain concepts (OwnershipTransfer, TransferState, PostTransferFate, AbortRecord, AbortReason)
- [x] **§2.5** EVT-T* mapping (EVT-T8 Administrative with 7 new Succession* sub-shapes — Option C terminology)
- [x] **§3** Aggregate inventory (1 new: `ownership_transfer`; references reality_registry + coauthor_grant + forge_audit_log)
- [x] **§3.1.1** Singleton-active invariant
- [x] **§4** Tier+scope table (T2 for state updates; T3 for Finalize atomicity)
- [x] **§5** DP primitives by name (incl. Finalize t3_write_multi shape)
- [x] **§6** State machine (Pending TTL 14d → Cooldown 7d → Finalized OR Aborted)
- [x] **§7** 7 V1 TransferActions + 4 read views
- [x] **§8** Pattern choices (recipient must be Co-Author, V1 always admin-approved, fixed 7d cooldown, anti-misclick typed name, blocked during world Catastrophic/Shattered)
- [x] **§9** Failure-mode UX (9 failure cases)
- [x] **§10** Cross-service handoff (initiate, recipient accept, admin approve dual-actor, finalize sweeper)

PLT_002b (this file):

- [x] **§11** Sequence: full happy-path (8-day timeline)
- [x] **§12** Sequence: owner cancels during cooldown
- [x] **§13** Sequence: admin rejects during Pending
- [x] **§14** Acceptance criteria (10 scenarios across happy-path / failure-path / boundary)
- [x] **§15** Deferrals (SUC-D1..D12 + HER-D8 inherited hybrid-tracked in `_boundaries/`)
- [x] **§16** Cross-references (incl. authoritative pointers to `_boundaries/`)

**Status transition:** DRAFT (2026-04-25 first commit `9d8ac58`) → relocated `4be727d` → split + closure pass (2026-04-25): added §14 acceptance criteria + applied Option C terminology (EVT-T8 AdminAction → Administrative) + extracted §11-§17 to this file → **CANDIDATE-LOCK**.

LOCK granted after all 10 §14 acceptance scenarios have a passing integration test.

**Resolves:** PLT_001 CHR-D1 ✓ (in-product ownership transfer feature).

**Drift watchpoints active:**
- HER-D8 inherited — V1 emission via EVT-T8 Administrative-only; V1+30d adds EVT-T11 WorldTick — `_boundaries/03_validator_pipeline_slots.md` authoritative

**Next** (when this doc locks): gateway-bff exposes `/v1/forge/.../succession/...` REST + `/v1/admin/.../succession/...` admin REST; world-service implements transfer state machine + Finalize sweeper task; admin console (downstream feature) implements the admin review queue UI. Vertical-slice target: full Tâm-Anh→Hoài-Linh transfer reproduces deterministically across all 10 §14 acceptance scenarios.
