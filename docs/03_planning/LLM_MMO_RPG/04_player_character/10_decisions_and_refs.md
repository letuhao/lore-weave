<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 10_decisions_and_refs.md
byte_range: 16446-18777
sha256: 8cb1d29937f9de10779118a2adb6b8e75a9e2ef0fe6f6cb4375da2615ac7d61d
generated_by: scripts/chunk_doc.py
-->

## 10. Decisions status

| Decision | Answer | Status |
|---|---|---|
| A-PC1 PC creation | Full custom + templates | **LOCKED** |
| A-PC2 Play as glossary entity | Supported | **LOCKED** |
| A-PC3 Canon validation at creation | None — paradox allowed | **LOCKED** |
| B-PC1 Death | Per-reality rule (just an event) | **LOCKED** — rule details in DF4 |
| B-PC2 Offline PC | Visible + vulnerable; hide to be safe; LLM does not act | **LOCKED** — details in DF1 |
| B-PC3 Prolonged hidden | Converts to NPC; leaves hiding; LLM takes over | **LOCKED** — details in DF1 |
| C-PC1 Max PCs per user | 5 (configurable); more via purchase | **LOCKED** — purchase in DF2 |
| C-PC2 PC personality | User IS PC when active; LLM persona only when NPC-converted | **LOCKED** — generation in DF8 |
| C-PC3 Stats model | Simple state-based, no RPG mechanics | **LOCKED** — schema in DF7 |
| D-PC1 Party model | None — session replaces parties | **LOCKED** — details in DF5 |
| D-PC2 PvP | Yes, within a session | **LOCKED** — consent in DF4/DF5 |
| D-PC3 Interaction channel | Session only, no global | **LOCKED** — details in DF5 |
| E-PC1 PC affects canon | Yes — deferred big feature | **LOCKED** as deferred (DF3) |
| E-PC2 Author notification | Yes — deferred | **LOCKED** as deferred (DF3) |
| E-PC3 Paradox allowed | Yes, governed by World Rules | **LOCKED** as deferred (DF4) |

### New config keys

```
roleplay.pc.max_per_user = 5
roleplay.pc.npc_conversion_threshold_days = TBC (future DF1 decision)
roleplay.pc.default_death_rule = 'permadeath' (V1 default; per-reality override later)
```

## 11. References

- [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — reality model this sits on top of
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — PC projection lives here (§5.1); extended in §8 above
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — B3 (world tick), E3 (IP), M3 (canonization contamination) now cross-ref DF1/DF3/DF4
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — PC locks added; new deferred features DF1–DF8 registered
- [98_CHAT_SERVICE_DESIGN.md](../98_CHAT_SERVICE_DESIGN.md) — sibling for Cursor-style chat; DF5 is multi-char scene variant
- [103_PLATFORM_MODE_PLAN.md](../103_PLATFORM_MODE_PLAN.md) — tier/billing home for DF2
