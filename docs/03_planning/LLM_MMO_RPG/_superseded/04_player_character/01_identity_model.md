<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 01_identity_model.md
byte_range: 353-2265
sha256: efaf84312cf816caac86721690420783a444c36a7d65d73fb5a21959302bd7ff
generated_by: scripts/chunk_doc.py
-->

## 1. Three-layer identity model (locked)

```
┌────────────────────────────────────────────────────────┐
│  USER  (auth_users)                                    │
│  1 tài khoản thật; 1 user exists across all realities  │
└─────────────────┬──────────────────────────────────────┘
                  │ owns 1..N
                  ▼
┌────────────────────────────────────────────────────────┐
│  PC  (player_characters, reality-scoped)               │
│  1 user có N PCs, mỗi PC thuộc 1 reality duy nhất      │
│  Identity = (user_id, reality_id, pc_id)               │
└─────────────────┬──────────────────────────────────────┘
                  │ controls via
                  ▼
┌────────────────────────────────────────────────────────┐
│  SESSION  (in-memory + event-sourced)                  │
│  1 phiên chơi — user logged-in as PC, realtime active  │
└────────────────────────────────────────────────────────┘
```

Hard rules:
- PC thuộc về đúng 1 reality (until future world-travel feature)
- PC chết/archived ≠ user bị xóa. User owns many PCs.
- Session không persist; events do. Session là runtime abstraction.

