# PLT_002 — Succession (Reality Ownership Transfer)

> **Conversational name:** "Succession" (SUC). The formal handover of RealityOwner role from current owner to an existing Co-Author. High-stakes; multi-stage state machine with recipient consent + admin oversight + cooldown. Closes the V1 gap where RealityOwner could not self-resign without admin S5 intervention.
>
> **Category:** PLT — Platform / Business (relocated 2026-04-25 from `02_world_authoring/`; original WA_005 ID retired per foundation I15)
> **Status:** **CANDIDATE-LOCK 2026-04-25** (originally DRAFT as WA_005; relocated 2026-04-25 to `10_platform_business/` because account ownership lifecycle is platform/account territory; closure pass 2026-04-25 split into root + lifecycle to honor 800-line cap; §14 acceptance criteria added in PLT_002b — 10 scenarios; Option C terminology applied EVT-T8 AdminAction → Administrative). LOCK granted after the 10 §14 acceptance scenarios have passing integration tests.
> **Companion file:** [`PLT_002b_succession_lifecycle.md`](PLT_002b_succession_lifecycle.md) — sequences (§11-§13), acceptance criteria (§14), deferrals (§15), cross-references (§16), readiness checklist (§17).
> **Stable ID rename:** WA_005 → PLT_002. Old ID `WA_005` MUST NOT be reused for a different feature (foundation I15).
> **Catalog refs:** PLT-*. Resolves [PLT_001 CHR-D1](PLT_001_charter.md) (ownership transfer feature).
> **Builds on:** [PLT_001 Charter](PLT_001_charter.md) (recipients must be existing Co-Authors V1), [WA_003 Forge](../02_world_authoring/WA_003_forge.md) (UI surface; reuses ImpactClass / EditOutcome pattern), [02_storage C03 reality_registry](../../02_storage/) (owner ground-truth that gets mutated)
> **Defers to:** future PLT_NNN for "transfer to non-Co-Author" (skip-the-Charter-step flow); future audit retention policy for transfer history.

---

## §1 User story (concrete)

**Scenario A — Healthy succession:**

Tâm-Anh (RealityOwner of `R-tdd-h-2026-04`) decides to step back. Hoài-Linh has been a Co-Author for 6 months; Tâm-Anh wants to hand the reality over. She:

1. Opens Forge → "Co-Authors" tab → her own row → "Transfer ownership" (visible only to RealityOwner)
2. Confirmation page: "Transfer ownership of R-tdd-h-2026-04 to a Co-Author. This is a high-stakes action. The transfer takes 7-21 days to complete and requires recipient + admin approval."
3. Picks recipient: Hoài-Linh (V1: must be existing Co-Author of this reality)
4. Picks her own post-transfer fate: `Become Co-Author` (default) | `Be Removed Entirely`
5. Adds reason: "Stepping back from co-authoring; Hoài-Linh has been the de-facto creative lead for months"
6. Types the reality name to confirm (anti-misclick): `R-tdd-h-2026-04`
7. Clicks "Initiate Transfer"
8. Backend creates `ownership_transfer` row with state=`Pending { recipient_accepted: false, admin_approved: false }`
9. Hoài-Linh sees a banner in Forge: "Tâm-Anh wants to transfer ownership of R-tdd-h-2026-04 to you." → reviews → "Accept ownership"
10. Backend updates state: `recipient_accepted: true`
11. LoreWeave admin reviews the transfer (V1 mandatory). Admin approves or rejects.
12. On admin approve: state advances to `Cooldown { entered_at }` — 7-day cancel window
13. During cooldown, Tâm-Anh OR Hoài-Linh can cancel. After 7 days without cancellation: state → `Finalized`
14. Finalize executes atomically:
    - `reality_registry.owner_id = Hoài-Linh`
    - Tâm-Anh's grant becomes `Co-Author` (per her post-transfer choice)
    - JWT version bumped for both
    - EVT-T8 Administrative emitted
15. Both users see in-app confirmation. Reality continues running normally.

Total time T0 → finalize: minimum 7 days (cooldown floor); typically 7-14 days.

**Scenario B — Owner reconsiders:**

Tâm-Anh initiates the transfer. Hoài-Linh accepts. Admin approves. During the 7-day cooldown, Tâm-Anh changes her mind and clicks "Cancel transfer". The transfer aborts; state → `Aborted { reason: OwnerCancelled }`. Reality ownership unchanged. Audit log records the abort + reason.

**Scenario C — Admin rejects:**

Admin reviewing the transfer notices Tâm-Anh's account had a recent password reset event 3 days ago — possible account-recovery suspicion. Admin rejects with reason "Account security review needed; please contact support". Transfer aborts immediately; both parties notified; if false-positive, support helps re-initiate.

**This feature design specifies:** the multi-stage state machine; the action handlers; the recipient-acceptance UX; the admin-approval workflow; the cooldown semantics; the atomic finalize transaction touching `reality_registry` + `coauthor_grant`; failure UX for each abort path; and audit trail.

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **OwnershipTransfer** | A row in `ownership_transfer` aggregate; one ACTIVE transfer per reality at a time | State machine documented §6. Soft-deletion on abort is preserved for audit. |
| **TransferState** | Closed enum: `Pending \| Cooldown \| Finalized \| Aborted` | See §6. |
| **PostTransferFate** | What happens to the OUTGOING owner | `BecomesCoAuthor (default)` \| `Removed`. Author picks at initiation. |
| **TransferAction** | Closed enum of ops that mutate transfer state | 7 actions in §7. |
| **AbortReason** | Closed enum of why a transfer ended without finalize | `OwnerCancelled` \| `RecipientDeclined` \| `AdminRejected` \| `PendingExpired` \| `CooldownCancelled` \| `RealityArchived` (V2+). |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11; Option C redesign 2026-04-25)

Succession operations are AdminAction-class (per WA_003 / PLT_001 pattern).

| Action | EVT-T* | Producer | Notes |
|---|---|---|---|
| InitiateTransfer | **EVT-T8** AdminAction (sub-shape `SuccessionInitiate`) | RealityOwner via Forge → world-service | Tier1 ImpactClass; requires reality-name typed-confirm at UI layer. |
| RecipientAccept | **EVT-T8** AdminAction (sub-shape `SuccessionRecipientAccept`) | recipient via Forge → world-service | Tier1; requires confirmation. |
| RecipientDecline | **EVT-T8** AdminAction (sub-shape `SuccessionRecipientDecline`) | recipient | Aborts the transfer. |
| AdminApprove | **EVT-T8** AdminAction (sub-shape `SuccessionAdminApprove`) | admin (S5 dual-actor) | Two operators must concur. |
| AdminReject | **EVT-T8** AdminAction (sub-shape `SuccessionAdminReject`) | admin (single operator OK for reject — easier escape) | Aborts the transfer. |
| OwnerCancel | **EVT-T8** AdminAction (sub-shape `SuccessionOwnerCancel`) | RealityOwner | Always permitted while transfer is Pending or Cooldown. |
| Finalize | **EVT-T8** AdminAction (sub-shape `SuccessionFinalize`) + **EVT-T11** WorldTick (V2+) at reality root | system (background sweeper) | After cooldown elapses without abort. |

EVT-T8 sub-shapes locked here.

---

## §3 Aggregate inventory

One new aggregate. Mutates `reality_registry` + `coauthor_grant` at finalize time (atomic).

### 3.1 `ownership_transfer`

```rust
#[derive(Aggregate)]
#[dp(type_name = "ownership_transfer", tier = "T2", scope = "reality")]
pub struct OwnershipTransfer {
    pub transfer_id: Uuid,                             // primary key
    pub reality_id: RealityId,                          // (singleton ACTIVE per reality enforced by §3.1.1)
    pub state: TransferState,
    pub from_user_id: UserId,                           // current RealityOwner at initiate time
    pub to_user_id: UserId,                             // recipient; must be Co-Author at initiate time
    pub initiated_at_wall_clock: Timestamp,
    pub initiated_at_fiction_time: FictionTimeTuple,
    pub initiated_reason: String,                       // ≥30 chars required
    pub post_transfer_fate: PostTransferFate,           // BecomesCoAuthor | Removed
    pub recipient_accepted_at: Option<Timestamp>,
    pub admin_approved_at: Option<Timestamp>,
    pub admin_approver_chain: Vec<UserId>,              // 2 admins for S5 dual-actor
    pub cooldown_entered_at: Option<Timestamp>,
    pub finalized_at: Option<Timestamp>,
    pub aborted: Option<AbortRecord>,
}

pub enum TransferState {
    Pending,                                            // recipient AND admin approval needed
    Cooldown,                                           // both approved; 7-day cancel window active
    Finalized,                                          // terminal success
    Aborted,                                            // terminal failure (see aborted field)
}

pub struct AbortRecord {
    pub at: Timestamp,
    pub reason: AbortReason,
    pub by: UserId,                                     // who triggered the abort
    pub note: Option<String>,
}

pub enum AbortReason {
    OwnerCancelled,
    RecipientDeclined,
    AdminRejected,
    PendingExpired,                                     // 14-day Pending TTL exceeded without both approvals
    CooldownCancelled,
    RealityArchived,                                    // V2+: reality goes to special states
}

pub enum PostTransferFate {
    BecomesCoAuthor,                                    // V1 default
    Removed,                                            // outgoing owner removed entirely
}
```

- T2 + RealityScoped: durable; survives gateway restart.
- One ACTIVE transfer per reality at a time enforced by `§3.1.1` precheck.
- Aborted/Finalized rows kept for audit (V1 retention indefinite; V2+ may archive after 90d).

### 3.1.1 Singleton-active invariant

A reality may have at most ONE transfer in `Pending` or `Cooldown` state at any time. World-service enforces:

```rust
fn check_no_active_transfer(reality_id: RealityId) -> Result<(), DpError> {
    let existing = dp::query_scoped_reality::<OwnershipTransfer>(
        ctx,
        Predicate::field_eq(reality_id, target).and(
            Predicate::field_in(state, vec![Pending, Cooldown])
        ),
        limit=1
    ).await?;
    if !existing.is_empty() {
        return Err(DpError::OwnershipTransferAlreadyActive { transfer_id: existing[0].transfer_id });
    }
    Ok(())
}
```

To start a new transfer, any active one must complete (Finalized or Aborted) first.

### 3.2 References (no other new aggregates)

- **`reality_registry`** (`02_storage/C03_meta_registry_ha.md`): the ultimate target. `owner_id` is mutated atomically at Finalize.
- **`coauthor_grant`** (PLT_001 §3.1): mutated at Finalize — outgoing owner's grant created (if `BecomesCoAuthor`) or recipient's grant deleted (recipient is no longer a Co-Author since they ARE the owner now).
- **`forge_audit_log`** (WA_003 §3.1): every action emits an audit entry.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `ownership_transfer` | T2 | T2 (Pending/Cooldown updates) + **T3** (Finalize) | Reality | ~1/transfer-tab-load | rare (≤1 per reality lifetime per active state, plus background-sweeper polls) | Per-reality singleton-active state; T3 used at Finalize for atomicity with reality_registry + coauthor_grant. |

T3 used ONLY at Finalize because the multi-aggregate atomic write must include:
- `ownership_transfer.state = Finalized`
- `reality_registry.owner_id = recipient`
- `coauthor_grant` for outgoing owner created or removed
- `coauthor_grant` for recipient deleted (they become owner, not co-author)

Wrapped in `dp::t3_write_multi`.

---

## §5 DP primitives this feature calls

### 5.1 Reads (per Forge view-load)

```rust
// Active transfer (if any) for this reality
let transfer = dp::query_scoped_reality::<OwnershipTransfer>(
    ctx,
    Predicate::field_eq(reality_id, target).and(
        Predicate::field_in(state, vec![Pending, Cooldown])
    ),
    limit=1
).await?;

// History for audit tab
let history = dp::query_scoped_reality::<OwnershipTransfer>(
    ctx,
    Predicate::field_eq(reality_id, target),
    limit=20, ...
).await?;

// Cross-reality: pending transfers offered TO me (for "you've been offered ownership" banner on login)
let my_transfers = dp::query_meta::<OwnershipTransfer>(
    Predicate::field_eq(to_user_id, current_user_id).and(
        Predicate::field_eq(state, Pending)
    ),
    limit=20, ...
).await?;
```

### 5.2 Writes

```rust
// InitiateTransfer
dp::t2_write::<OwnershipTransfer>(ctx, transfer_id, TransferDelta::Initiate { ... }).await?;

// State updates (recipient_accepted, admin_approved, cooldown_entered)
dp::t2_write::<OwnershipTransfer>(ctx, transfer_id, TransferDelta::AdvanceState { ... }).await?;

// Abort (any path)
dp::t2_write::<OwnershipTransfer>(ctx, transfer_id, TransferDelta::Abort { reason, by }).await?;

// Finalize (T3 atomic)
dp::t3_write_multi(ctx, vec![
    T3WriteOp::new::<OwnershipTransfer>(transfer_id, TransferDelta::Finalize),
    T3WriteOp::new::<RealityRegistry>(realityregistry_id(reality_id), RealityRegistryDelta::ChangeOwner { new_owner_id: recipient }),
    // outgoing owner becomes Co-Author OR removed:
    T3WriteOp::new::<CoAuthorGrant>(grant_id_outgoing, GrantDelta::Create { ... }),  // if BecomesCoAuthor
    // OR (mutually exclusive with above):
    // (no write if Removed)

    // recipient was a Co-Author before; their grant must be deleted (they're now owner):
    T3WriteOp::new::<CoAuthorGrant>(grant_id_incoming, GrantDelta::Delete),
]).await?;

// Audit + EVT-T8 emission (always after each state-changing op)
dp::t2_write::<ForgeAuditEntry>(ctx, entry_id, AuditDelta::Append { ... }).await?;
dp::advance_turn(ctx, &ChannelId::reality_root(reality_id),
    TurnEvent::AdminAction { sub_shape: Succession*, ... }, causal_refs=[]
).await?;
```

---

## §6 State machine

```text
                         (no active transfer)
                                │
                                │ InitiateTransfer (RealityOwner)
                                ▼
                        ┌────────────────┐
                        │ Pending        │ TTL 14 days
                        │ recipient: ?   │
                        │ admin: ?       │
                        └────────────────┘
                                │
   ┌─────────────────┬──────────┼──────────┬─────────────────┐
   │                 │          │          │                 │
   ▼ RecipientDecline│          │          │ OwnerCancel     │
   ▼                 │          │          │                 │
   Aborted           │          │          │                 │
   {RecipientDeclined}          │          │                 │
                     │          │          │                 │
                     ▼ Recipient│          │ Admin           │
                     Accept     │          │ Approve         │
                     │          │          │                 │
                     ▼          ▼          ▼                 │
                  recipient_accepted: true                    │
                  admin_approved: true                        │
                                │                             │
                                │ both true                  ▼
                                │                          Aborted
                                │                          {OwnerCancelled}
                                ▼
                        ┌────────────────┐
                        │ Cooldown       │ 7-day cancel window
                        │ entered_at     │
                        └────────────────┘
                                │
   ┌─────────────────┬──────────┴──────────┬─────────────────┐
   │                 │                     │                 │
   ▼ OwnerCancel     ▼ RecipientWithdraw   ▼ AdminRejectLate ▼ (7d elapses)
   │                 │                     │                 │
   ▼                 ▼                     ▼                 ▼
   Aborted           Aborted               Aborted          Finalized
   {CooldownCancelled} {CooldownCancelled} {AdminRejected}  (terminal SUCCESS)
   (terminal)        (terminal)            (terminal)
```

### 6.1 Pending state details

- **TTL = 14 days** from `initiated_at`. If 14 days elapse without both `recipient_accepted` AND `admin_approved` becoming true → `Aborted { PendingExpired }`.
- During Pending: ALL participants can act. Recipient declines → abort. Owner cancels → abort. Admin rejects → abort.
- Recipient and admin act independently. Order doesn't matter; both must say yes for state to advance.

### 6.2 Cooldown state details

- **Duration = 7 days** from `cooldown_entered_at`.
- During cooldown: owner OR recipient can cancel (`OwnerCancel` / `RecipientWithdraw`). Either aborts.
- Admin can also reject during cooldown (`AdminRejectLate`) for emergency cases (e.g., security review escalation).
- Background sweeper (every 1 hour) checks for Cooldown rows where `cooldown_entered_at + 7d < now` and triggers Finalize.
- No new approvals required to finalize — cooldown elapsing is the trigger.

### 6.3 Finalized state details

- Finalize is an atomic `t3_write_multi`:
  1. `ownership_transfer.state = Finalized`
  2. `reality_registry.owner_id = recipient`
  3. If `post_transfer_fate = BecomesCoAuthor`: create `coauthor_grant` for outgoing owner
  4. Delete `coauthor_grant` for recipient (they're the owner now)
- Both users' `forge.roles_version` bumped → next JWT refresh picks up new roles
- Audit log entry + EVT-T8 emission

### 6.4 Aborted state details

- Terminal. Cannot resume.
- `aborted` field carries `AbortRecord { at, reason, by, note }`.
- Audit log entry + EVT-T8 emission.
- New transfer can be initiated only after the active transfer is in Aborted or Finalized state (per §3.1.1).

---

## §7 Actions (V1 closed set)

7 V1 TransferActions.

### 7.1 InitiateTransfer

```rust
pub struct InitiateTransfer {
    pub reality_id: RealityId,
    pub to_user_id: UserId,                            // V1: must be Co-Author of this reality
    pub post_transfer_fate: PostTransferFate,
    pub initiated_reason: String,                       // ≥30 chars required
    pub typed_reality_name: String,                     // anti-misclick: must equal reality.display_name
}
```

- **Initiator:** RealityOwner only
- **Validation:**
  - ownership check: `reality_registry.owner == requester` ✓
  - recipient must be existing Co-Author: `coauthor_grant` exists for `(reality, to_user_id)` ✓
  - no active transfer (§3.1.1) ✓
  - typed_reality_name matches `reality_registry.display_name` ✓
  - reason length ≥30 chars ✓
  - to_user_id != requester (cannot self-transfer) ✓
- **Effect:** creates `ownership_transfer { state: Pending, recipient_accepted: false, admin_approved: false }`
- **TTL clock starts:** `expires_at = initiated_at + 14d`
- **Notification:** recipient sees banner; admin queue gets new entry for review

### 7.2 RecipientAccept

```rust
pub struct RecipientAccept {
    pub transfer_id: Uuid,
    pub typed_confirmation: String,                     // must equal "I accept ownership of <reality_display_name>"
}
```

- **Initiator:** recipient (matches `transfer.to_user_id`)
- **Validation:** transfer in Pending state, not expired; typed_confirmation matches expected literal
- **Effect:** `recipient_accepted = true, recipient_accepted_at = now`. If admin_approved already true, transitions to Cooldown.

### 7.3 RecipientDecline

```rust
pub struct RecipientDecline {
    pub transfer_id: Uuid,
    pub reason: Option<String>,
}
```

- **Initiator:** recipient
- **Effect:** `state = Aborted { reason: RecipientDeclined, by: recipient }`. Terminal.

### 7.4 AdminApprove

```rust
pub struct AdminApprove {
    pub transfer_id: Uuid,
    pub admin_review_notes: String,                     // ≥50 chars; what was reviewed
}
```

- **Initiator:** admin (operator A); requires S5 dual-actor (operator B must also approve)
- **Validation:** transfer in Pending; both admins concur within 5-min window
- **Effect:** `admin_approved = true, admin_approver_chain: [op_A, op_B]`. If recipient_accepted already true, transitions to Cooldown.

### 7.5 AdminReject

```rust
pub struct AdminReject {
    pub transfer_id: Uuid,
    pub reason: String,                                 // ≥50 chars; will be communicated to participants
}
```

- **Initiator:** admin (single operator OK for reject — easier escape from problematic transfers)
- **Effect:** `state = Aborted { reason: AdminRejected, by: admin, note: reason }`. Terminal. Both participants notified with admin's reason.

### 7.6 OwnerCancel

```rust
pub struct OwnerCancel {
    pub transfer_id: Uuid,
    pub reason: Option<String>,
}
```

- **Initiator:** RealityOwner only (the original owner who initiated; matches `transfer.from_user_id`)
- **Validation:** transfer in Pending OR Cooldown
- **Effect:** `state = Aborted { reason: OwnerCancelled or CooldownCancelled depending on prior state }`. Terminal.

### 7.7 RecipientWithdraw

```rust
pub struct RecipientWithdraw {
    pub transfer_id: Uuid,
    pub reason: Option<String>,
}
```

- **Initiator:** recipient
- **Validation:** transfer in Cooldown (recipient already accepted; this is "I changed my mind")
- **Effect:** `state = Aborted { reason: CooldownCancelled, by: recipient }`. Terminal.

### 7.8 Finalize (system-driven, not a user action)

Triggered by background sweeper when `cooldown_entered_at + 7d < now`. Atomic per §6.3.

### 7.9 Read-only views

- `ViewActiveTransfer(reality_id)` — visible to RealityOwner + recipient + admins. Shows current state + countdown.
- `ViewTransferHistory(reality_id)` — visible to RealityOwner + admins. All past transfers (Aborted/Finalized).
- `ViewMyOfferedTransfers(user_id)` — cross-reality query. Shows Pending transfers offered TO requesting user. (Reuses meta-table pattern from PLT_001 §8.4.)
- `ViewAdminPendingTransfers(admin)` — admin queue of Pending transfers awaiting review.

---

## §8 Pattern choices

### 8.1 V1 = recipient must be existing Co-Author

Locked: `to_user_id` must have an active `coauthor_grant` for the target reality at initiate time. Reasons:
- Reduces social-engineering risk (attacker can't transfer reality to a fresh sock-puppet account)
- Recipient has demonstrated investment via Co-Author tenure
- New users go through Charter (PLT_001) first; transfer is the next step

V2+ may allow direct transfer to non-Co-Author with extra friction (CHR-D1 stretched + verification challenges).

### 8.2 V1 always requires admin approval

V1 every transfer goes through admin review. Reasons:
- Account takeover detection (admin spots suspicious patterns: recent password reset, unusual login location)
- Coercion screening (admin can pause + contact owner offline)
- Audit responsibility (LoreWeave operator is in the loop for every ownership change)

V2+ may pre-approve transfers between long-standing Co-Authors (>6 months tenure + reality has been active) without admin step. CHR-D1-like.

### 8.3 7-day cooldown is fixed V1

Locked V1: cooldown = 7 days. Configurable per-reality in V2+ (SUC-D2). Reasons:
- Long enough for owner regret
- Short enough not to seem broken ("why is my transfer not done yet?")
- Cooldown can't be skipped — even if both parties + admin all want immediate finalize, V1 enforces 7-day minimum

### 8.4 Anti-misclick: typed reality-name confirmation at initiate

Locked V1: initiator must type the exact `reality_display_name` string at the UI confirmation step. Pure UI pattern; backend checks the typed string matches. Borrowed from GitHub's repo-deletion confirmation.

### 8.5 Cancel rights asymmetry

| State | Owner cancel | Recipient cancel | Admin reject |
|---|---|---|---|
| Pending | ✓ | ✓ (Decline) | ✓ |
| Cooldown | ✓ | ✓ (Withdraw) | ✓ (late) |
| Finalized | ✗ | ✗ | ✗ (terminal) |
| Aborted | ✗ | ✗ | ✗ (terminal) |

Both parties have symmetric cancel rights. Admin rejection is reserved for emergency security review.

### 8.6 V1 PostTransferFate options

V1 closed set: `BecomesCoAuthor` (default) | `Removed`. Owner picks at initiate time. Cannot be changed mid-transfer.

V2+ could add: `BecomesReadOnly` (observer-only access) or `RetainAdminEscape` (special "former owner" role with limited rights). Deferred SUC-D3.

### 8.7 Finalize is atomic; rollback on any failure

If `t3_write_multi` at Finalize fails partway (DB transaction error mid-commit), the transaction rolls back. The transfer stays in `Cooldown` state (since Finalize hasn't actually applied). Sweeper retries on next sweep cycle (1 hour later). After 24h of failed retries, escalate to admin queue for manual review.

### 8.8 No transfer-during-WorldStability-Catastrophic V1

Locked V1: transfers cannot be initiated when `world_stability.current_stage` is `Catastrophic` or `Shattered`. The reality is in crisis; ownership change adds confusion. Owner must wait for stability recovery first. SUC-D4: V2+ may relax with admin override.

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| `OwnershipTransferAlreadyActive` | Initiator tries to start while one is in flight | Toast: "Đã có yêu cầu chuyển nhượng đang chờ. Vui lòng hủy nó trước khi bắt đầu mới." | Owner cancels active first |
| `RecipientNotCoAuthor` | Owner picks a user who isn't a Co-Author | Toast: "Người nhận phải là Co-Author hiện tại của thực tại. Hãy mời họ làm Co-Author trước." | Inviter invites first |
| `TypedNameMismatch` | Anti-misclick check fails | Inline error: "Tên thực tại không khớp." | User retypes |
| `ReasonTooShort` | Reason <30 chars | Inline error: "Lý do phải dài ít nhất 30 ký tự." | User expands |
| `TransferExpired` (Pending TTL elapsed) | recipient/admin tries to act after 14d | Toast: "Yêu cầu này đã hết hạn." (auto-aborted by sweeper) | (terminal — initiator must restart if still desired) |
| `TypedConfirmationMismatch` (RecipientAccept) | Recipient's typed confirmation phrase wrong | Inline error: "Câu xác nhận không khớp. Vui lòng gõ chính xác." | User retypes |
| `WorldUnstable` | Initiate during Catastrophic / Shattered stage | Modal: "Thực tại đang ở trạng thái '<stage>'. Không thể chuyển nhượng cho đến khi ổn định trở lại." | Wait for stability recovery |
| `CapabilityDenied` (non-owner tries Initiate or OwnerCancel) | RBAC violation | Toast: "Chỉ RealityOwner mới có thể thực hiện việc này." | (out of role) |
| `AdminApprovalCooldown` (admin op-B doesn't approve within 5min of op-A) | S5 dual-actor failure | Toast (to op-A): "Phê duyệt không hoàn tất trong 5 phút. Vui lòng thử lại với một admin khác." | re-initiate admin approve |

---

## §10 Cross-service handoff

### 10.1 Initiate → Pending

```text
Tâm-Anh in Forge → POST /v1/forge/realities/{R}/succession/initiate
    body: {
        to_user_id: hoai_linh,
        post_transfer_fate: BecomesCoAuthor,
        initiated_reason: "...",
        typed_reality_name: "R-tdd-h-2026-04",
    }
    │
gateway-bff:
    JWT check (Tâm-Anh = RealityOwner of R) ✓
    forward to world-service
    │
world-service:
    forge_validator: action=InitiateTransfer, impact=Tier1
    Tier1 normally requires dual-actor — but for Initiate, the typed-name
    confirmation + 14-day Pending TTL provides the friction; no second
    operator required at initiate time. Admin approval comes later.
    pre-checks (§7.1):
        ownership ✓
        recipient is Co-Author ✓
        no active transfer ✓
        typed_name matches ✓
        reason ≥30 chars ✓
        not self-transfer ✓
        world_stability not Catastrophic/Shattered ✓
    │
    ▼
    t2_write OwnershipTransfer { state: Pending, ... }
    advance_turn EVT-T8 Administrative SuccessionInitiate ✓
    t2_write ForgeAuditEntry ✓
    write meta_user_offered_transfers entry for hoai_linh ✓
    enqueue admin review queue (out-of-band)
    │
    ▼
gateway-bff → frontend: 200 OK { transfer_id, expires_at: now+14d }
```

### 10.2 Recipient Accept

```text
Hoài-Linh in Forge → POST /v1/forge/.../succession/{transfer_id}/recipient-accept
    body: { typed_confirmation: "I accept ownership of R-tdd-h-2026-04" }
    │
world-service:
    pre-checks: state=Pending, not expired, recipient matches ✓
    t2_write OwnershipTransfer { recipient_accepted: true, recipient_accepted_at: now }
    if admin_approved already true:
        state advances to Cooldown { entered_at: now }
        background sweeper will check at now+7d
    advance_turn EVT-T8 Administrative SuccessionRecipientAccept ✓
    t2_write ForgeAuditEntry ✓
    │
    ▼
200 OK { state: Pending or Cooldown }
```

### 10.3 Admin Approve (S5 dual-actor)

```text
Operator A in admin console → POST /v1/admin/.../succession/{transfer_id}/approve
    body: { admin_review_notes: "..." }
    │
world-service:
    forge_validator: action=AdminApprove, requires S5 dual-actor
    creates pending_admin_approval row T1 (TTL 5min)
    return AwaitingApproval { pending_id }

Operator B in admin console → POST /v1/admin/.../approve-pending/{pending_id}
    │
world-service:
    completes the approve:
    t2_write OwnershipTransfer { admin_approved: true, admin_approver_chain: [op_A, op_B], admin_approved_at: now }
    if recipient_accepted already true:
        state advances to Cooldown { entered_at: now }
    advance_turn EVT-T8 Administrative SuccessionAdminApprove ✓
    t2_write ForgeAuditEntry ✓
```

### 10.4 Finalize (background sweeper)

```text
Sweeper task (every 1 hour):
    query OwnershipTransfer WHERE state=Cooldown AND cooldown_entered_at + 7d < now
    for each:
        try t3_write_multi atomic:
            OwnershipTransfer { state: Finalized, finalized_at: now }
            RealityRegistry { owner_id: recipient }
            (if BecomesCoAuthor): CoAuthorGrant create for outgoing owner
            CoAuthorGrant delete for recipient
        on success:
            advance_turn EVT-T8 SuccessionFinalize at reality root
            (V2+) advance_turn EVT-T11 WorldTick: OwnershipChanged
            t2_write ForgeAuditEntry
            bump forge_roles_version for both users
            push notification to both (V2+; V1 in-app on next view)
        on failure:
            log + retry next sweep
            after 24h: escalate to admin queue
```

---

## §11..§17 — Continued in PLT_002b

End of contract layer. The dynamic layer (sequences, acceptance criteria, deferrals, cross-references, readiness) is in the companion file:

→ **[`PLT_002b_succession_lifecycle.md`](PLT_002b_succession_lifecycle.md)**

Sections:

- §11 Sequence: full happy-path (8-day timeline T0 → T+8d Finalize)
- §12 Sequence: owner cancels during cooldown (Scenario B)
- §13 Sequence: admin rejects during Pending (Scenario C)
- §14 Acceptance criteria (10 scenarios — AC-SUC-1..10 across happy-path / failure-path / boundary)
- §15 Open questions deferred (SUC-D1..D12 + HER-D8 inherited)
- §16 Cross-references
- §17 Implementation readiness checklist (combined PLT_002 + PLT_002b)

PLT_002b is required reading before implementing the world-service Succession state machine.
