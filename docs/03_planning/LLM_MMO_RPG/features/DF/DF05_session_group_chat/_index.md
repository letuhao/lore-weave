# DF05 — Session / Group Chat — Index

> **Status:** Placeholder. Not yet designed. V1-blocking. **Biggest V1 unknown — design first.**
> **Scope preview** (from SESSION_HANDOFF agenda): Multi-character scene, turn arbitration (B4 PARTIAL — distinct from SR11 turn queue; this is about NPC-responds-to-whom), PvP consent flow, message routing, session invite + share-link, player-voice override inline commands (C1-D2); covers PC-D1 / D2 / D3 + PL-1 / PL-3.
>
> **Scope size estimate:** ~400-500 lines distributed across `01_spec.md` / `02_ui_flow.md` / `03_data_model.md` / `04_integration.md` / `05_test_plan.md` / `06_v1_scope_cut.md`. Larger than DF4/DF7 because DF5 establishes the patterns DF4 enforces within.

**Active:** (empty — no agent currently editing; placeholder only)

---

## When work starts

When design of DF5 begins, this `_index.md` expands into a proper TOC. Interaction heavy with:

- **SR11** turn state machine + presence + disconnect policy (established)
- **S12** WebSocket ticket + control channel
- **R7** session-as-concurrency-boundary
- **DF4** (if already designed) per-reality rule overrides
- **DF7** (if already designed) PC state participating in multi-PC scene

If DF5 exposes gaps in SR11/S12/R7 kernel behavior, minimal kernel extensions allowed per feature-first-on-demand rule.
