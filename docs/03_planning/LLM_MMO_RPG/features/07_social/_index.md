# 07_social — Index

> **Category:** SOC — Social
> **Catalog reference:** [`catalog/cat_07_SOC_social.md`](../../catalog/cat_07_SOC_social.md) (owns `SOC-*` stable-ID namespace)
> **Purpose:** Player-to-player social mechanics. Note: **SOC-6 (parties)** and **SOC-7 (global chat)** are explicitly out-of-scope — sessions replace both. Session-based interaction lives here.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `SOC_001_<name>.md`.)

---

## Out-of-scope reminders

- **SOC-6 Parties** — WITHDRAWN. PC-D1 locked "No parties — Session replaces all group mechanics".
- **SOC-7 Global chat** — WITHDRAWN. PC-D3 locked "Session only — no global chat".

Don't design features that undo these decisions.

---

## Kernel touchpoints (shared across SOC features)

- `decisions/locked_decisions.md` — PC-D1/D2/D3 (no parties, PvP in session, session-only interaction)
- `02_storage/SR11_turn_ux_reliability.md` — PresenceState enum (session-scoped liveness) + session participant extension
- `02_storage/S12_websocket_security.md` — session.membership_changed + presence.update WS messages
- `03_multiverse/` — reality-scoped session membership
- **DF5 Session/Group Chat** (pending design) — biggest consumer of SOC primitives

---

## Naming convention

`SOC_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
