<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 06_social_sessions.md
byte_range: 9954-11224
sha256: 9ae7d69d98de9defe9c264ef2679c10d896b3d3e9c7992c77b69ec688626ef21
generated_by: scripts/chunk_doc.py
-->

## 6. Social model — Sessions, not Parties (locked)

No MMO-style parties/raids/guilds. Replace with Facebook-style group chat at the **session** level.

### 6.1 D-PC1 — Session is the social unit

A **session** is a shared interaction context:
- N participants (PCs + NPCs) co-located in a region
- All participants hear each other's speech
- Session is formed implicitly when characters are in same region speaking to same subject
- User-initiated sessions: create a session explicitly ("start a gathering") → invite specific PCs/NPCs

### 6.2 D-PC2 — PvP inside session

PCs can affect each other inside a session:
- Attack, steal, befriend, romance — all legal events
- Consent model TBC (per-reality rule? opt-in flag on PC?)
- Outside a session (different regions) PCs cannot interact

### 6.3 D-PC3 — All interaction via session

There is no "global chat" or "whisper from anywhere." All interaction is scoped to a session. Covers:
- PC ↔ PC: both in same session
- PC ↔ NPC: both in same session
- Private talk: create a private session with 2 participants

Session mechanics (creation, join/leave, turn ordering with N PCs + M NPCs, message fanout, persistence) → **Session / Group Chat feature** (deferred, §9).

