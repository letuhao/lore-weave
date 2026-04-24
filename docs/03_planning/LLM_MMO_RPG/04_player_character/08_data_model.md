<!-- CHUNK-META
source: 04_PLAYER_CHARACTER_DESIGN.ARCHIVED.md
chunk: 08_data_model.md
byte_range: 11959-13167
sha256: 47c51329e04ccecfd9d772bda6ee7a605494bfddc4d0068963e7669f2173c1ac
generated_by: scripts/chunk_doc.py
-->

## 8. Data model adjustments

Extends [02 §5.1](02_STORAGE_ARCHITECTURE.md) PC projection:

```sql
ALTER TABLE pc_projection
  ADD COLUMN derived_from_glossary_entity_id UUID,   -- A-PC2: optional glossary ref
  ADD COLUMN template_code TEXT,                     -- A-PC1: which template (nullable)
  ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE,  -- B-PC2: user hid PC
  ADD COLUMN hidden_at TIMESTAMPTZ,                  -- for conversion timing
  ADD COLUMN control_mode TEXT NOT NULL DEFAULT 'player',  -- 'player' | 'npc_converted'
  ADD COLUMN npc_converted_at TIMESTAMPTZ;           -- when control_mode flipped

-- Index for NPC-conversion scanner
CREATE INDEX pc_projection_hidden_scan_idx
  ON pc_projection (is_hidden, hidden_at)
  WHERE is_hidden = TRUE AND control_mode = 'player';
```

New event types:
```
pc.created          — initial creation
pc.hidden           — user hid PC
pc.unhidden         — user reclaimed PC (back from hiding or NPC mode)
pc.died             — in-world death (consequence per reality rule)
pc.npc_converted    — automatic transition to NPC mode
pc.canonization_nominated    — author flag (future E-PC1 feature)
```

