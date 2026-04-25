# 99 — Boundary Folder Changelog

> Append-only log of `_boundaries/*` edits + lock claims/releases.
>
> **Format:** newest entries at top.

---

## 2026-04-25 (afternoon) — WA boundary shrink: ownership matrix update

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25 (afternoon)
- **Files modified:**
  - `01_feature_ownership_matrix.md`:
    - `coauthor_grant`, `coauthor_invitation` → owner WA_004 → **PLT_001 Charter** (formerly WA_004; relocated 2026-04-25)
    - `ownership_transfer` → owner WA_005 → **PLT_002 Succession** (formerly WA_005)
    - `meta_user_pending_invitations` → owner WA_004 → **PLT_001 Charter** (formerly WA_004)
    - `forge_audit_log` consumers list updated (PLT_001 + PLT_002 + WA_006 instead of WA_004/005/006)
    - WA_003 Forge marked PROVISIONAL with note about future cross-cutting extraction
    - `RejectReason` namespace prefix table expanded — added `canon_drift.*`, `capability.*`, `parse.*`, `chorus.*`, `forge.*`, `charter.*`, `succession.*`; "Pending Path A tightening" replaced with "Path A applied 2026-04-25 (commit f7c0a54)"
    - `ForgeEditAction`, capability JWT, EVT-T8 sub-shapes — owner attributions for Charter/Succession updated WA_004/005 → PLT_001/002
    - Stable-ID prefix ownership rows: `CHR-D*`/`CHR-Q*` owner WA_004 → PLT_001; `SUC-D*`/`SUC-Q*` owner WA_005 → PLT_002
    - Drift watchpoint `CHR-D9`: owner WA_004 → PLT_001
  - `02_extension_contracts.md`: same pattern across §1.4 RejectReason table, §3 capability JWT, §4 EVT-T8 sub-shapes — all WA_004/005 references re-attributed to PLT_001/002
- **Drift watchpoints unchanged** (8 still active; ownership identifiers updated)
- **No new contracts added** — pure ownership re-attribution
- **Reason:** post-WA boundary review concluded WA's original intent ("validate rules of reality + detect paradox + allow controlled bypass") doesn't cover identity/account concerns. WA_004 Charter + WA_005 Succession relocated to `10_platform_business/` (commit 4be727d); WA_003 Forge marked PROVISIONAL pending future cross-cutting pattern extraction; WA_006 Mortality already PROVISIONAL from prior review (commit de9cf1a). WA folder shrinks from 6 to 3 active features (WA_001 Lex, WA_002 Heresy, WA_003 Forge PROVISIONAL) + 1 PROVISIONAL marker (WA_006).
- **Lock release:** at end of this commit

---

## 2026-04-25 — Folder seeded

- **Lock claim:** main session 2026-04-25 (Claude Opus 4.7) at 2026-04-25
- **Files created:**
  - `_LOCK.md` (single-writer mutex)
  - `00_README.md` (purpose, rules, how-to-use)
  - `01_feature_ownership_matrix.md` (initial entries for 11 designed features: PL_001/001b/002, NPC_001/002, WA_001..006)
  - `02_extension_contracts.md` (TurnEvent envelope §1, RealityManifest §2, capability JWT §3, EVT-T8 sub-shapes §4)
  - `03_validator_pipeline_slots.md` (proposed EVT-V* ordering pending event-model Phase 3 lock)
  - `99_changelog.md` (this file)
- **Initial drift watchpoints captured (8):** GR-D8, CST-D1, LX-D5, HER-D8, HER-D9, CHR-D9, WA_006 over-extension, B2 RealityManifest envelope
- **Reason:** post-WA_006 boundary review (2026-04-25) revealed boundary issues across the 11 features designed in one work session; a mutex'd boundary folder is the long-term fix
- **Lock release:** at end of seeding commit
