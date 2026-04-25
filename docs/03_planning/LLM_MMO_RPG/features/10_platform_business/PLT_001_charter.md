# PLT_001 — Charter (Co-Author Management)

> **Conversational name:** "Charter" (CHR). The formal grant of co-authoring rights — RealityOwner invites another LoreWeave user as Co-Author, with explicit invitation lifecycle, audit log, and revocation flow. Pairs with WA_003 Forge: Forge is the WHERE (the console); Charter is the WHO (the people allowed to use it).
>
> **Category:** PLT — Platform / Business (relocated 2026-04-25 from `02_world_authoring/`; original PLT_001 ID retired per foundation I15)
> **Status:** DRAFT 2026-04-25 (originally drafted as WA_004; relocated 2026-04-25 to `10_platform_business/` because identity / co-author management is platform/account territory, not "validate rules of reality" which is WA's original intent)
> **Stable ID rename:** WA_004 → PLT_001. Old ID `WA_004` MUST NOT be reused for a different feature (foundation I15).
> **Catalog refs:** PLT-* (this feature is the first PLT entry). Resolves [WA_003 FRG-D5](../02_world_authoring/WA_003_forge.md) (Co-Author invitation flow).
> **Builds on:** [WA_003 Forge](../02_world_authoring/WA_003_forge.md) (consumes its RBAC roles + EditOutcome pattern), [WA_001 Lex](../02_world_authoring/WA_001_lex.md) + [WA_002 Heresy](../02_world_authoring/WA_002_heresy.md) (no direct interaction; Charter just gates who can call into them via Forge), [02_storage C03 reality_registry](../../02_storage/) (ownership ground-truth)
> **Defers to:** auth-service for `UserId` newtype + user lookup; companion **PLT_002 Succession** (formerly PLT_002) for ownership transfer + Co-Author tier system.

---

## §1 User story (concrete)

**Scenario A — RealityOwner Tâm-Anh invites a co-author:**

Tâm-Anh owns reality `R-tdd-h-2026-04`. She wants Hoài-Linh (a friend) to help curate the world's NPC personas. She:

1. Opens Forge → "Co-Authors" tab (introduced by PLT_001)
2. Sees current grants: only herself (RealityOwner)
3. Clicks "+ Invite Co-Author"
4. Enters Hoài-Linh's email (or LoreWeave username) → backend resolves to `UserId(hoai_linh)`
5. Picks role: `Co-Author` (V1: only flat role; V2+ tiers)
6. Adds note: "Help me curate NPC personas"
7. Clicks "Send Invitation"
8. Backend creates a `coauthor_invitation` row (T2, 7-day TTL)
9. Hoài-Linh receives in-app notification (V1; email V2+)
10. Hoài-Linh logs in, opens Forge → sees pending invitation banner
11. Reviews details (reality name, inviter, role, note) → clicks "Accept"
12. Backend creates `coauthor_grant` row + deletes invitation + emits EVT-T8 AdminAction
13. Hoài-Linh's JWT is refreshed with `forge.roles: { R-tdd-h-2026-04: Co-Author }` on next session bind
14. Tâm-Anh's UI updates (next view-load): grant list now shows Hoài-Linh

**Scenario B — RealityOwner revokes a Co-Author:**

Some weeks later, Tâm-Anh decides to revoke Hoài-Linh's access. She:

1. Opens Forge → "Co-Authors" → Hoài-Linh's row → "Revoke"
2. Confirmation dialog: "Revoke Hoài-Linh's Co-Author access? They will lose edit rights immediately."
3. She confirms. Backend deletes the grant + emits EVT-T8 AdminAction.
4. Hoài-Linh's next request to Forge fails with `CapabilityDenied` (her JWT is stale; she sees "Bạn đã không còn quyền chỉnh sửa thực tại này.")
5. Audit log records the revocation with reason (optional)

**Scenario C — Co-Author Hoài-Linh resigns:**

Alternate flow. Hoài-Linh decides to step down:

1. She opens Forge → "Co-Authors" → her own row → "Resign" (self-revoke button)
2. Confirmation: "Resign as Co-Author? You will lose edit rights immediately."
3. Confirms. Backend deletes the grant + emits EVT-T8 AdminAction with `resigned_by_self: true`.
4. Tâm-Anh sees notification: "Hoài-Linh has resigned as Co-Author."

**Scenario D — Owner abandonment (V1 escape hatch via admin):**

If Tâm-Anh's account is deleted or she abandons the reality, Co-Authors are STUCK at V1 (no ownership-transfer feature). Escape hatch: admin (LoreWeave operator) can re-assign ownership via S5 admin action (Tier 1 dual-actor + 14-day cooldown). V2+ adds in-product ownership transfer flow (CHR-D1).

**This feature design specifies:** the invitation lifecycle (create / accept / decline / expire), the grant aggregate, the JWT-refresh contract for role changes, the audit log entries, and the V1 escape hatch via admin. Frontend out of scope (downstream React feature).

---

## §2 Domain concepts

| Concept | Maps to | Notes |
|---|---|---|
| **CoAuthorGrant** | A row in `coauthor_grant` aggregate; one per `(reality_id, user_id)` for active grants | Deleted (not soft-deleted) on revoke/resign; revocation tracked in audit log only. |
| **CoAuthorInvitation** | A row in `coauthor_invitation` aggregate; transient pending state | TTL 7 days. On accept → grant created + invitation deleted. On decline / expire → invitation deleted; no grant. |
| **InvitationOutcome** | `enum InvitationOutcome { Pending \| Accepted \| Declined \| Expired \| Cancelled }` | Audit-log-only states; aggregates only persist Pending. |
| **GrantAction** | Closed enum of all grant-affecting operations | `Invite \| Accept \| Decline \| CancelInvitation \| Revoke \| Resign`. |
| **JWT-Refresh** | Mechanism: when grants change, the affected user's JWT must be refreshed on next bind to pick up new roles | DP-K10 `refresh_capability` + extension. |

---

## §2.5 Event-model mapping (per 07_event_model EVT-T1..T11)

Charter operations are AdminAction-class privileged writes (per WA_003 §2.5 pattern).

| Charter action | EVT-T* | Producer | Notes |
|---|---|---|---|
| Invite | **EVT-T8** AdminAction (sub-shape `CharterInvite`) | gateway → world-service | RealityOwner privilege. |
| Accept invitation | **EVT-T8** AdminAction (sub-shape `CharterAccept`) | gateway → world-service | Invitee privilege. |
| Decline invitation | **EVT-T8** AdminAction (sub-shape `CharterDecline`) | gateway → world-service | Invitee privilege; logged for audit but not strictly necessary. |
| Cancel invitation (inviter cancels before invitee responds) | **EVT-T8** AdminAction (sub-shape `CharterCancel`) | gateway → world-service | RealityOwner privilege. |
| Revoke grant | **EVT-T8** AdminAction (sub-shape `CharterRevoke`) | gateway → world-service | RealityOwner privilege. |
| Resign grant | **EVT-T8** AdminAction (sub-shape `CharterResign`) | gateway → world-service | Co-Author privilege; self-only. |
| (V2+) Ownership transfer | **EVT-T8** AdminAction (sub-shape `CharterTransfer`) | gateway → world-service + admin oversight | Tier1 + 14-day cooldown; deferred to PLT_002. |

EVT-T8 sub-shapes locked here; new sub-shapes added in V2+ via additive schema bump.

---

## §3 Aggregate inventory

Two new aggregates, both small.

### 3.1 `coauthor_grant`

```rust
#[derive(Aggregate)]
#[dp(type_name = "coauthor_grant", tier = "T2", scope = "reality")]
pub struct CoAuthorGrant {
    pub grant_id: Uuid,                          // primary key
    pub reality_id: RealityId,
    #[dp(indexed)] pub user_id: UserId,           // grantee (LoreWeave user)
    pub role: AuthorRole,                         // V1: Co-Author only
    pub granted_at_wall_clock: Timestamp,
    pub granted_at_fiction_time: FictionTimeTuple,
    pub granted_by: UserId,                       // RealityOwner who issued it
    pub note: Option<String>,                     // ≤500 chars; rationale at invite time
    pub last_active_at: Timestamp,                // updated on each Forge edit; for staleness telemetry
}
```

- T2 + RealityScoped: per-reality access list; durable.
- One row per `(reality_id, user_id)` pair where role is active. Deleted on revoke/resign (NOT soft-delete; revocation is in audit log).
- `granted_by` always equals current RealityOwner at grant time. If ownership transfers (V2+), grants stay; the new RealityOwner does not need to re-invite.

### 3.2 `coauthor_invitation`

```rust
#[derive(Aggregate)]
#[dp(type_name = "coauthor_invitation", tier = "T2", scope = "reality")]
pub struct CoAuthorInvitation {
    pub invitation_id: Uuid,                      // primary key
    pub reality_id: RealityId,
    #[dp(indexed)] pub invitee_user_id: UserId,
    pub inviter_user_id: UserId,                  // RealityOwner at invite time
    pub proposed_role: AuthorRole,                // V1 only Co-Author
    pub created_at_wall_clock: Timestamp,
    pub expires_at: Timestamp,                    // 7 days from created_at
    pub note: Option<String>,
}
```

- T2 + RealityScoped: durable so it survives gateway restart.
- TTL 7 days enforced by background sweeper task; expired invitations deleted + audit-log entry written with outcome=Expired.
- One pending invitation at a time per `(reality_id, invitee_user_id)`. Re-invite requires waiting for previous to expire/resolve.

### 3.3 References (no other new aggregates)

- **Reuse `forge_audit_log`** (WA_003 §3.1): Charter operations log into the same audit table with `EditAction::Charter*` sub-shapes.
- **`reality_registry`** (`02_storage/C03_meta_registry_ha.md`): RealityOwner ground-truth; Charter reads to verify ownership for inviter authorization.
- **`auth-service` user table** (out of scope): user lookup by email/username happens at gateway-bff layer before reaching Charter.

---

## §4 Tier + scope table (DP-R2 mandatory)

| Aggregate | Read tier | Write tier | Scope | Read freq | Write freq | Eligibility |
|---|---|---|---|---|---|---|
| `coauthor_grant` | T2 | T2 | Reality | ~1/JWT-refresh per Co-Author + ~1/co-author-tab-load | ~0 hot path | Per-reality ACL; durable; eventual-consistency on JWT refresh OK. |
| `coauthor_invitation` | T2 | T2 | Reality | ~1/co-author-tab-load + ~1/invitee-login | ~0 hot path | Transient (7d TTL); durable so it survives gateway restart. |

No T0/T1/T3 in this feature.

- No T0: invitations must persist across gateway restart.
- No T1: not high-churn.
- No T3: grants don't need atomicity with other aggregates beyond their own tx.

---

## §5 DP primitives this feature calls

### 5.1 Reads

```rust
// List current grants (for Forge "Co-Authors" tab)
let grants = dp::query_scoped_reality::<CoAuthorGrant>(
    ctx,
    Predicate::field_eq(reality_id, target_reality),
    limit=50, ...
).await?;

// List pending invitations issued FROM this reality
let invitations = dp::query_scoped_reality::<CoAuthorInvitation>(
    ctx,
    Predicate::field_eq(reality_id, target_reality),
    limit=20, ...
).await?;

// List invitations issued TO this user (for "pending invites" banner on login)
// NOTE: this is a CROSS-REALITY query — needs special handling, see §8.4
let my_invites = dp::query_meta::<CoAuthorInvitation>(
    Predicate::field_eq(invitee_user_id, current_user_id),
    limit=20, ...
).await?;
```

### 5.2 Writes

```rust
// Invite
dp::t2_write::<CoAuthorInvitation>(ctx, invitation_id, InvitationDelta::Create { ... }).await?;

// Accept (atomic: create grant + delete invitation)
dp::t3_write_multi(ctx, vec![
    T3WriteOp::new::<CoAuthorGrant>(grant_id, GrantDelta::Create { ... }),
    T3WriteOp::new::<CoAuthorInvitation>(invitation_id, InvitationDelta::Delete),
]).await?;

// Decline / Cancel / Expire
dp::t2_write::<CoAuthorInvitation>(ctx, invitation_id, InvitationDelta::Delete).await?;

// Revoke / Resign
dp::t2_write::<CoAuthorGrant>(ctx, grant_id, GrantDelta::Delete).await?;

// Audit (always after a grant-affecting operation; reuses forge_audit_log)
dp::t2_write::<ForgeAuditEntry>(ctx, entry_id, AuditDelta::Append { ... }).await?;

// Emit EVT-T8 AdminAction at reality root
dp::advance_turn(ctx, &ChannelId::reality_root(reality_id), TurnEvent::AdminAction { sub_shape: Charter*, ... }, causal_refs=[]).await?;
```

T3 used only for the Accept atomic — invitation deletion + grant creation must be visible together to prevent races (e.g., user accepts twice in quick succession).

---

## §6 Role lifecycle

### 6.1 State machine

```text
                 (none)
                    │ Invite (RealityOwner)
                    ▼
              [Pending Invitation]
                    │
   ┌────────────────┼────────────────┐────────────────┐
   │                │                │                │
   ▼ Accept         ▼ Decline        ▼ Cancel         ▼ Expire (7d)
                   (invitee)        (inviter)         (TTL)
   │
   ▼
  [Active Grant]
   │
   ┌─────────────────────┐
   │                     │
   ▼ Revoke              ▼ Resign
   (RealityOwner)        (self)
   │                     │
   ▼                     ▼
                 (none, audit-only history)
```

### 6.2 V1 transitions and authorization

| Transition | Initiator | Authorization check |
|---|---|---|
| `(none) → Pending` (Invite) | RealityOwner only | `reality_registry.owner == requesting_user` |
| `Pending → Active` (Accept) | invitee only | `invitation.invitee_user_id == requesting_user` AND `invitation.expires_at > now` |
| `Pending → (none)` (Decline) | invitee only | same as Accept |
| `Pending → (none)` (Cancel) | RealityOwner only | `reality_registry.owner == requesting_user` |
| `Pending → (none)` (Expire) | system (background sweeper) | TTL elapsed |
| `Active → (none)` (Revoke) | RealityOwner only | `reality_registry.owner == requesting_user` AND `grant.user_id != requesting_user` (cannot self-revoke own ownership; resign-or-transfer required) |
| `Active → (none)` (Resign) | grant holder only | `grant.user_id == requesting_user` |

### 6.3 RealityOwner cannot resign their own ownership in V1

V1: RealityOwner resignation = orphans the reality. Not allowed in V1. V2+ adds ownership transfer (CHR-D1) which is the proper resignation path. V1 escape: admin reassigns ownership via S5 (Tier 1).

### 6.4 JWT refresh on grant change

Grant changes do NOT immediately invalidate active sessions. Instead:
- Affected user's JWT carries a `forge.roles_version: u64` claim (per-reality version)
- Charter writes bump the per-reality version
- On next `refresh_capability` call (DP-K10; auto-triggered every 4 minutes per default), JWT picks up new roles
- Worst-case staleness: 4 minutes between grant change and JWT refresh

For revocation specifically: world-service ALSO checks `coauthor_grant` existence at write time as defense-in-depth. So even if a stale JWT has `Co-Author`, the actual write fails with `CapabilityDenied` if the grant has been deleted.

---

## §7 Charter actions (V1 closed set)

6 V1 actions. Each routes through Forge's existing edit-pipeline (extended with Charter sub-shapes).

### 7.1 Invite

```rust
pub struct CharterInvite {
    pub reality_id: RealityId,
    pub invitee_user_id: UserId,                  // resolved by gateway from email/username
    pub proposed_role: AuthorRole,                // V1 must equal Co-Author
    pub note: Option<String>,
}
```

- **Initiator:** RealityOwner of target reality
- **Validation:** ownership check; invitee_user_id exists in auth-service; no existing active grant for `(reality, invitee)`; no existing pending invitation
- **Effect:** creates `coauthor_invitation` row; emits EVT-T8 `CharterInvite`; audit log entry
- **TTL:** 7 days (configurable per reality in V2+; HER-D2 for similar pattern)

### 7.2 Accept

```rust
pub struct CharterAccept {
    pub invitation_id: Uuid,
}
```

- **Initiator:** invitee only
- **Validation:** invitation exists and not expired; `invitation.invitee_user_id == requester`
- **Effect:** atomic `t3_write_multi` (create grant + delete invitation); emits EVT-T8 `CharterAccept`; audit log; bumps `forge.roles_version` for the user (next JWT refresh picks up new role)

### 7.3 Decline

```rust
pub struct CharterDecline {
    pub invitation_id: Uuid,
    pub reason: Option<String>,                   // optional
}
```

- **Initiator:** invitee only
- **Effect:** deletes invitation; emits EVT-T8 `CharterDecline`; audit log

### 7.4 CancelInvitation

```rust
pub struct CharterCancelInvitation {
    pub invitation_id: Uuid,
}
```

- **Initiator:** RealityOwner only (the original inviter)
- **Effect:** deletes pending invitation before invitee responds; emits EVT-T8 `CharterCancel`; audit

### 7.5 Revoke

```rust
pub struct CharterRevoke {
    pub grant_id: Uuid,
    pub reason: Option<String>,
}
```

- **Initiator:** RealityOwner of target reality
- **Validation:** ownership check; grant exists; not self-targeting (RealityOwner can't revoke own ownership)
- **Effect:** deletes grant; emits EVT-T8 `CharterRevoke`; bumps the affected user's `forge.roles_version`; audit
- **Side-effect:** affected user's next request to Forge for this reality fails with `CapabilityDenied` once their JWT refreshes

### 7.6 Resign

```rust
pub struct CharterResign {
    pub grant_id: Uuid,
    pub reason: Option<String>,
}
```

- **Initiator:** grant holder only (self)
- **Validation:** `grant.user_id == requester`; user is NOT the RealityOwner (they cannot resign in V1)
- **Effect:** same as Revoke; audit entry marked `resigned_by_self: true`

### 7.7 Read-only views

- `ViewCoAuthorGrants` — list of all active grants for a reality (visible to RealityOwner + all current Co-Authors + Admins)
- `ViewPendingInvitationsOutbound` — pending invitations issued FROM this reality (visible to RealityOwner only)
- `ViewMyPendingInvitations` — pending invitations issued TO the requesting user across ALL realities

---

## §8 Pattern choices

### 8.1 V1 = flat Co-Author role only

V1 supports exactly two role values: `RealityOwner` (immutable, set at reality creation) and `Co-Author`. No tiered roles (Junior/Senior/Reviewer/etc.). V2+ adds tier system per CHR-D2.

This intentionally keeps RBAC simple: per WA_003 §6.1, Co-Author has fixed capabilities (Trivial + Minor solo; Major dual-actor; Tier1 cannot trigger). No need for further granularity in V1.

### 8.2 Hard-delete grants on revoke/resign (no soft-delete)

Locked: revocation deletes the `coauthor_grant` row. History is in `forge_audit_log` only.

Reasons:
- Active access checks need to be O(1) — soft-deleted rows would clutter every query
- Audit log already provides full history reconstruction
- Re-grant scenario produces a fresh `grant_id` with new `granted_at` — semantically a new relationship

### 8.3 Invitation TTL = 7 days (V1)

Configurable per reality in V2+ (CHR-D3). V1 fixed at 7 days because:
- Too short → invitee may miss notification (especially at V1 with in-app notifications only)
- Too long → forgotten invitations clutter the system
- 7 days is the same as common email-link expiry conventions

Background sweeper checks every 1 hour for expired invitations; deletes + emits audit. Sweep cadence is tunable (CHR-D4).

### 8.4 Cross-reality invitation query (`ViewMyPendingInvitations`)

This is the only query in Charter that crosses reality boundaries. Per DP-A7 reality-scoping, normal `query_scoped` is reality-scoped. For "show me my pending invitations across all realities":

- V1 implementation: a META-LAYER projection at gateway-bff or platform DB level
- Each `coauthor_invitation` write also writes a denormalized row to `meta_user_pending_invitations` (a global table keyed by `user_id`)
- Charter is the ONLY producer of this meta table
- TTL synchronization: when `coauthor_invitation` is deleted (accept/decline/cancel/expire), the corresponding meta row is also deleted

This is a deliberate cross-reality leak — but only for INVITATION pending state, which is by-definition cross-reality. Full content of invitations stays per-reality.

### 8.5 JWT refresh is eventual (4-minute staleness)

Locked V1: JWT staleness up to 4 minutes after grant change. Reasons:
- Force-refresh on every grant change requires push-to-all-active-sessions infrastructure (not V1)
- 4-minute staleness is acceptable: defense-in-depth at write-time check (§6.4) catches stale-JWT writes; reads are idempotent

V2+ adds: opt-in immediate JWT invalidation for high-security ops (admin force-revoke).

### 8.6 No notification protocol in V1 beyond in-app banner

V1: invitee sees a banner in their LoreWeave UI when they log in. No email, no push. CHR-D5 deferred to V2+ ops.

### 8.7 No role downgrade or upgrade in V1

V1: a Co-Author cannot be "promoted" or "demoted". Grant changes = revoke + invite-new. V2+ adds in-place role change (CHR-D6).

---

## §9 Failure-mode UX

| Failure | When | UX | Recovery |
|---|---|---|---|
| `UserNotFound` | Inviter enters email/username that doesn't resolve | Toast: "Không tìm thấy người dùng. Kiểm tra email hoặc tên đăng nhập." | Inviter retypes |
| `AlreadyHasGrant` | Invite for user who's already a Co-Author | Toast: "Người này đã là Co-Author của thực tại này." | (no action needed) |
| `PendingInvitationExists` | Invite while previous invitation is still pending | Toast: "Đã có lời mời chờ phản hồi. Hủy nó trước khi gửi lời mời mới." | Inviter cancels old invite first |
| `InvitationExpired` | Invitee accepts/declines after TTL | Toast: "Lời mời đã hết hạn. Vui lòng yêu cầu RealityOwner gửi lại." | inviter re-sends |
| `CapabilityDenied` (not RealityOwner) | Co-Author tries to invite/revoke | Toast: "Chỉ RealityOwner mới có thể gửi lời mời / thu hồi quyền." | (out of role) |
| `CapabilityDenied` (stale JWT post-revoke) | Revoked Co-Author tries to edit | Toast: "Bạn đã không còn quyền chỉnh sửa thực tại này." + auto-redirect to home | User logs out / refreshes |
| `CannotResignOwner` | RealityOwner tries to resign their own ownership | Toast: "RealityOwner không thể tự từ chức. Vui lòng chuyển quyền sở hữu qua admin (V1) hoặc dùng tính năng chuyển nhượng (V2+)." | escalate to admin |
| `SelfRevoke` | RealityOwner tries to revoke their own grant | Toast: "Không thể tự thu hồi quyền của chính mình." | (impossible action surfaced) |

---

## §10 Cross-service handoff

### 10.1 Invite flow

```text
Forge UI (Tâm-Anh) → POST /v1/forge/realities/{R}/charter/invite
    body: { invitee_email, proposed_role: Co-Author, note }
    │
gateway-bff:
    JWT check (Tâm-Anh has RealityOwner for R) ✓
    auth-service: resolve invitee_email → invitee_user_id
    forward to world-service
    │
world-service:
    forge_validator: action=CharterInvite, impact=Major (creates grant pathway)
    RBAC: RealityOwner + Major = Ok solo
    pre-checks:
        - reality_registry.owner == Tâm-Anh ✓
        - no existing grant for (R, invitee) ✓
        - no existing pending invitation for (R, invitee) ✓
    ▼
    t2_write CoAuthorInvitation { create row with TTL 7d }
    advance_turn at reality root with EVT-T8 AdminAction { CharterInvite { ... } }
    t2_write ForgeAuditEntry
    (V1) write meta_user_pending_invitations entry for invitee
    ▼
gateway-bff → frontend: 200 OK { invitation_id, expires_at }
```

### 10.2 Accept flow

```text
Hoài-Linh logs in → frontend GET /v1/forge/me/pending-invitations
    │
gateway-bff:
    query meta_user_pending_invitations WHERE user_id = Hoài-Linh
    return list (V1 may be 0..N invitations across multiple realities)
    │
frontend renders banner: "1 pending invitation: R-tdd-h-2026-04 (Tâm-Anh wants you as Co-Author)"

Hoài-Linh clicks "Accept" → POST /v1/forge/charter/invitations/{ID}/accept
    │
gateway-bff:
    JWT check (Hoài-Linh authed) ✓
    forward to world-service
    │
world-service:
    pre-checks:
        - invitation exists ✓
        - invitation.invitee_user_id == Hoài-Linh ✓
        - invitation.expires_at > now ✓
    ▼
    t3_write_multi atomic:
        T3WriteOp CoAuthorGrant::Create { ... }
        T3WriteOp CoAuthorInvitation::Delete
    advance_turn at reality root with EVT-T8 AdminAction { CharterAccept { ... } }
    t2_write ForgeAuditEntry
    bump Hoài-Linh's forge.roles_version
    delete meta_user_pending_invitations entry
    ▼
gateway-bff → frontend: 200 OK { grant_id }

(Hoài-Linh's UI navigates to reality R; Forge prompts JWT refresh on next call)
```

### 10.3 Revoke flow

```text
Tâm-Anh → POST /v1/forge/realities/{R}/charter/grants/{grant_id}/revoke
    body: { reason: "..." }
    │
gateway-bff → world-service:
    forge_validator: action=CharterRevoke, impact=Major
    pre-checks:
        - reality_registry.owner == Tâm-Anh ✓
        - grant exists and grant.reality_id == R ✓
        - grant.user_id != Tâm-Anh ✓ (cannot self-revoke ownership)
    ▼
    t2_write CoAuthorGrant::Delete
    advance_turn EVT-T8 AdminAction { CharterRevoke { ... } }
    t2_write ForgeAuditEntry
    bump Hoài-Linh's forge.roles_version
    ▼
200 OK

(Hoài-Linh's next request refreshes JWT → Co-Author role removed → CapabilityDenied)
```

---

## §11 Sequence: invite → accept (Scenario A end-to-end)

```text
T0: Tâm-Anh opens Forge → Co-Authors tab → "+ Invite"
    fills email + note + clicks "Send"

T0+50ms: gateway-bff resolves email → user_id(hoai_linh)
         POST /v1/forge/.../charter/invite
         world-service:
             t2_write CoAuthorInvitation {
                 invitation_id: I1,
                 reality_id: R,
                 invitee_user_id: hoai_linh,
                 inviter_user_id: tam_anh,
                 proposed_role: Co-Author,
                 expires_at: T0 + 7d,
                 note: "Help curate NPC personas"
             }
             advance_turn AdminAction CharterInvite ✓
             ForgeAuditEntry { action: CharterInvite, ... } ✓
             meta_user_pending_invitations.insert(hoai_linh, I1) ✓

T0+200ms: Tâm-Anh's UI: "✓ Lời mời đã gửi (hết hạn sau 7 ngày)."

────── 2 hours later ──────

T+2h: Hoài-Linh logs in → GET /v1/forge/me/pending-invitations
      response: [{ invitation_id: I1, reality: R-tdd-h-2026-04, inviter: Tâm-Anh, role: Co-Author, ...}]

      banner: "1 pending invitation"

T+2h+30s: Hoài-Linh clicks banner → reviews details → "Accept"
          POST /v1/forge/charter/invitations/I1/accept
          world-service:
              t3_write_multi atomic [
                  CoAuthorGrant::Create { grant_id: G1, reality_id: R,
                                          user_id: hoai_linh, role: Co-Author, ... },
                  CoAuthorInvitation::Delete(I1),
              ]
              advance_turn AdminAction CharterAccept ✓
              ForgeAuditEntry { action: CharterAccept, ... } ✓
              forge_roles_version bump for hoai_linh ✓
              meta_user_pending_invitations.delete(hoai_linh, I1) ✓

          response 200 OK { grant_id: G1 }

T+2h+31s: Hoài-Linh's UI: "✓ Bạn đã trở thành Co-Author của thực tại R-tdd-h-2026-04."
          UI auto-navigates to reality R's Forge view
          on next API call: gateway forces JWT refresh →
            new JWT carries forge.roles { R: Co-Author }

T+2h+31s+1s: Tâm-Anh's UI on next view-load: grant list shows Hoài-Linh as Co-Author
```

---

## §12 Sequence: revoke (Scenario B)

```text
T+30d: Tâm-Anh decides to revoke Hoài-Linh
    Forge → Co-Authors → Hoài-Linh's row → "Revoke" → confirmation modal → confirm

T+30d+50ms: POST /v1/forge/.../charter/grants/G1/revoke
            body: { reason: "Project direction changed" }
            world-service:
                pre-checks: ownership ✓, grant exists ✓, not self-revoke ✓
                t2_write CoAuthorGrant::Delete(G1)
                advance_turn AdminAction CharterRevoke ✓
                ForgeAuditEntry { action: CharterRevoke, reason: "...", ... } ✓
                forge_roles_version bump for hoai_linh

            response 200 OK

T+30d+1s: Tâm-Anh's UI: "✓ Đã thu hồi quyền Co-Author của Hoài-Linh."
           grant list updates (Hoài-Linh removed)

────── meanwhile, Hoài-Linh's session is still open ──────

T+30d+5min: Hoài-Linh's JWT auto-refresh triggers (DP-K10 4-min cadence)
            new JWT no longer has Co-Author role for R
            next time she tries to edit: world-service rejects with CapabilityDenied
            UI shows: "Bạn đã không còn quyền chỉnh sửa thực tại này." + redirect

(If she had a write-in-flight at T+30d+50ms, world-service's defense-in-depth
 §6.4 grant-existence check rejects it explicitly, beating any JWT staleness.)
```

---

## §13 Sequence: resign (Scenario C)

```text
Hoài-Linh decides to resign:
    Forge → Co-Authors → her own row → "Resign" → confirmation

POST /v1/forge/charter/grants/G1/resign
    body: { reason: "Stepping back from co-authoring this reality" }

world-service:
    pre-checks: grant.user_id == hoai_linh ✓
                hoai_linh is NOT RealityOwner of R ✓ (CannotResignOwner check)
    t2_write CoAuthorGrant::Delete(G1)
    advance_turn AdminAction CharterResign ✓
    ForgeAuditEntry { action: CharterResign, resigned_by_self: true, reason: "...", ... } ✓
    forge_roles_version bump for hoai_linh

    (V2+) emit notification to RealityOwner Tâm-Anh

response 200 OK

Hoài-Linh's UI: "Bạn đã rời khỏi vai trò Co-Author."
                redirect to home

Tâm-Anh's UI on next check (V1: passive; V2+: push):
                "Hoài-Linh has resigned as Co-Author."
```

---

## §14 Open questions deferred

| ID | Question | Defer to |
|---|---|---|
| CHR-D1 | Ownership transfer — RealityOwner hands over to a Co-Author or new user. Tier1 + 14-day cooldown + dual-confirm + admin oversight | **PLT_002** Future ownership-transfer feature |
| CHR-D2 | Co-Author tier system (Junior / Senior / Reviewer with different impact-class limits) | V2+ — requires WA_003 RBAC matrix expansion |
| CHR-D3 | Per-reality configurable invitation TTL (7d default, range 1d-30d) | V2+ ops |
| CHR-D4 | Sweeper cadence tuning for expired invitations | Phase 5 ops |
| CHR-D5 | Notification protocol beyond in-app banner (email, push, mobile) | V2+ ops + frontend |
| CHR-D6 | In-place role change (promote / demote without revoke + re-invite) | V2+ — depends on CHR-D2 tier system |
| CHR-D7 | Bulk operations (invite multiple users at once) | V2+ |
| CHR-D8 | Audit log retention policy (V1 keeps everything; V2+ may archive) | V2+ ops + S5 retention config |
| CHR-D9 | Cross-reality leak: meta_user_pending_invitations is a global denormalized table. V2+ may revise to a different model (e.g., per-user platform DB). | V2+ infrastructure |
| CHR-D10 | Force-immediate JWT invalidation for high-security revoke (e.g., admin emergency revoke) | V2+ security ops |
| CHR-D11 | Co-Author can-resign-then-be-re-invited cooldown (prevent yo-yo abuse) | V2+ ops |
| CHR-D12 | Author identity verification (account ownership challenge before invite acceptance) | V2+ security |

---

## §15 Cross-references

- [WA_001 Lex](../02_world_authoring/WA_001_lex.md) — gated by Charter (Co-Authors who can edit Lex)
- [WA_002 Heresy](../02_world_authoring/WA_002_heresy.md) — gated by Charter
- [WA_003 Forge](../02_world_authoring/WA_003_forge.md) — Charter's UX lives in Forge's "Co-Authors" tab; reuses `forge_audit_log`; reuses `EditAction` + EVT-T8 sub-shape pattern
- [02_storage C03 reality_registry] — RealityOwner ground-truth for authorization checks
- [auth-service] — UserId resolution from email/username (out of PLT_001 scope)
- [07_event_model/03_event_taxonomy.md](../../07_event_model/03_event_taxonomy.md) — EVT-T8 AdminAction with new sub-shapes Charter*
- [decisions/deferred_DF01_DF15.md](../../decisions/deferred_DF01_DF15.md) — DF4 World Rules umbrella
- (Future) **PLT_002** — ownership transfer (CHR-D1)

---

## §16 Implementation readiness checklist

- [x] **§2** Domain concepts (CoAuthorGrant, CoAuthorInvitation, InvitationOutcome, GrantAction, JWT-Refresh)
- [x] **§2.5** EVT-T* mapping (EVT-T8 AdminAction with 6 new sub-shapes Charter*)
- [x] **§3** Aggregate inventory (2 new: `coauthor_grant`, `coauthor_invitation`; reuses `forge_audit_log` from WA_003)
- [x] **§4** Tier+scope table (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Role lifecycle state machine + V1 transitions + JWT refresh contract
- [x] **§7** 6 V1 actions + 3 read views
- [x] **§8** Pattern choices (flat Co-Author V1, hard-delete grants, 7d invitation TTL, cross-reality meta-table for invitee queries, eventual JWT refresh, no V1 notification)
- [x] **§9** Failure-mode UX (8 failure cases)
- [x] **§10** Cross-service handoff (invite, accept, revoke flows)
- [x] **§11** Sequence: invite + accept end-to-end
- [x] **§12** Sequence: revoke (Tâm-Anh removes Hoài-Linh)
- [x] **§13** Sequence: resign (Hoài-Linh leaves voluntarily)
- [x] **§14** Deferrals (CHR-D1..D12)

**Deferred:** acceptance criteria (intentionally not in V1 of this doc).

**Resolves:** WA_003 FRG-D5 ✓ (Co-Author invitation flow).

**Status:** DRAFT 2026-04-25.

**Drift watchpoint:** §8.4 cross-reality `meta_user_pending_invitations` is the only intentional cross-reality leak in this design. Reconcile with platform infrastructure team if they prefer a per-user platform-DB model instead. CHR-D9 captures.

**Next** (when this doc locks): gateway-bff exposes `/v1/forge/.../charter/...` REST endpoints; world-service implements Charter validators + grant/invitation handlers + JWT refresh hooks; auth-service contributes UserId resolution; frontend implements React invitation UI + grant list (downstream feature in `frontend/`). Vertical-slice target: Tâm-Anh + Hoài-Linh full invite/accept/revoke cycle reproduces deterministically.
