<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 04_lifecycle.md
byte_range: 5147-8299
sha256: 2c95e4cea5f4489c5150416d961da00fc77afe95397b5570bf8132b0b8882c1f
generated_by: scripts/chunk_doc.py
-->

## 4. Lifecycle (locked)

PC lifecycle spans active play, offline, and eventual "NPC-ification":

```
        user login as PC                      user logout
USER ────────────────────► [ACTIVE PC] ─────────────────────► [OFFLINE PC]
                                │                                   │
                                │ in-world death (event)            │ hidden by user
                                ▼                                   │
                          [DEAD PC]                                  ▼
                          (reality-dependent                   [HIDDEN PC]
                           semantics)                               │
                                                                    │ time passes
                                                                    │ without user return
                                                                    ▼
                                                            [PC-AS-NPC]
                                                            (LLM takes over,
                                                             leaves hiding spot,
                                                             lives as NPC)
```

### 4.1 B-PC1 — Death is reality-dependent

Death is just an event (`pc.died`). What happens after is **per-reality world rule**:

| Reality's rule | Effect |
|---|---|
| Permadeath reality | PC status = 'dead' permanently, user must create new PC |
| Respawn reality | After T seconds, PC status → 'alive' at respawn point |
| Body-persists reality | PC body remains as lootable object; new PC must be created |
| Resurrect-by-ritual reality | Other PCs/NPCs can restore |

World Rule feature (deferred) decides which applies. Default V1: permadeath (simplest).

### 4.2 B-PC2 — Offline PC defaults to vulnerable

When user logs out, PC remains in world with status = 'offline':
- **Visible to other PCs/NPCs in the region**
- **Can be attacked/affected by others** (potential bad outcomes)
- **LLM does not act on behalf of offline PC** (it just stands there)

User is strongly encouraged to **HIDE** their PC before logout:
- Travel PC to a "safe hub" region
- Use `/hide` command (equivalent to stashing away)
- Hidden PC is invisible to world actions, unattackable

### 4.3 B-PC3 — Prolonged absence → PC-as-NPC conversion

If PC remains hidden for too long (threshold TBC, config), system converts PC to NPC-mode:
- LLM generates a persona from PC's history (and glossary derivation if any)
- PC leaves hiding spot, joins regular NPC population
- PC's state becomes subject to world's NPC simulation rules (Daily Life feature, deferred)
- If user returns, they can "reclaim" their PC → LLM yields control back

**Important**: PC-as-NPC is still L3, still the user's creation. Canon identity preserved. Just control hand-off.

Details of NPC-ification persona generation, thresholds, reclaim UX → **Daily Life feature** (deferred, §9).

