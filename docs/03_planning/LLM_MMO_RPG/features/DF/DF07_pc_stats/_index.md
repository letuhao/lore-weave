# DF07 — PC Stats & Capabilities — Index

> **Status:** Placeholder. Not yet designed. V1-blocking. Smallest of the three V1-blocking DFs.
> **Scope preview** (from SESSION_HANDOFF agenda): Concrete schema for PCS-4 "simple state-based" — inventory, relationships, optional simple stats per F4 ACCEPTED scope (no D&D mechanics); death outcomes per DF4.
>
> **Scope size estimate:** ~150-200 lines, mostly `01_spec.md` + `03_data_model.md`. UI/interaction flow comparatively lighter.

**Active:** (empty — no agent currently editing; placeholder only)

---

## When work starts

Interaction with:

- **PC-C3** "simple state-based (no RPG mechanics)" — locked constraint
- **F4** ACCEPTED "minimal RPG mechanics; game = conversation" — locked constraint
- **R8** NPC aggregate split + per-pair memory — PC-NPC relationship edge lives here
- **SR11** TurnState + PresenceState — PC also carries these during session
- **MV12** fiction_ts — PC sheet snapshots at fiction_ts points for time-travel-state
- **DF5** if designed first — defines what "PC in session" means
- **DF4** if designed first — defines what capabilities rules constrain

Recommended after DF5 so PC schema accounts for multi-character-scene participation.
