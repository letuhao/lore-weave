# C25 Live-Smoke — Packer override-merge (composition)

**Token:** `live smoke: derivative generate → overridden entity stays overridden across chapters`

## Setup
- Stack UP + healthy (rebuilt composition-service/composition-worker/knowledge-service images, `up -d`); knowledge :8216 /health=200, gateway :3123 /health=200.
- Derivative Work `019ec734-3f1a-…` (C24 genderbend dị bản of 万古神帝), branch_point=3, its OWN `is_derivative` knowledge project `019ec734-3f0d-…` (delta, **0 entities** — fresh partition). Base = source project `019eb683-…` (万古神帝, 张若尘 et al.).
- `entity_override` on 张若尘 (glossary anchor `019eb701-d1b7-…`): `{"description": "now a woman (genderbend) — 张若尘 is female in this dị bản"}`.
- 2 scene nodes created in the derivative AFTER the branch (ch4 sort=40, ch5 sort=50), each with 张若尘 present.

## Cross-service two-project merge (verified in composition logs)
For each scene the packer issued knowledge reads against BOTH partitions in one pack:
- BASE: `drawers/search?project_id=019eb683-…` (source, branch-filtered)
- DELTA: `drawers/search?project_id=019ec734-…` (derivative's own)

## Result — override stays applied across ≥2 chapters
```
[ch4] node=019ec75c-5644-… overridden=True
   present: 张若尘: now a woman (genderbend) — 张若尘 is female in this dị bản
            池瑶: 九大帝君之一青帝之女…  (inherited base, NOT overridden)
            林妃: 云武郡王的王妃…        (inherited base, NOT overridden)
[ch5] node=019ec75c-624f-… overridden=True
   present: 张若尘: now a woman (genderbend) — 张若尘 is female in this dị bản
RESULT: PASS — overridden entity stays overridden across 2 chapters
```
- 张若尘 carries the override in BOTH chapters (re-applied every pack).
- Other entities keep their inherited base descriptions → override targets ONLY the matched entity.
- The delta project is empty (0 entities) → the 张若尘 present line is the inherited base entity, with the derivative's override merged on top (delta-precedence merge + override-after-merge).

## Self-syncing (no cache) — verified live
Edited the override to `"EDITED: now a powerful sorceress queen"` → next pack of the SAME scene:
```
EDITED override visible: True
stale v1 gone: True
```
The edited override took effect on the next pack with the old value gone — overrides are re-read + re-applied every pack, NO cache. (Restored the original value afterward.)

## Findings (folded into review)
- **Cross-space override-target id drift (C24 FE):** the C24 wizard originally recorded `target_entity_id` as a KNOWLEDGE node `id` (`b338ec39…`, an unanchored duplicate 张若尘 node, glossary_entity_id NULL) rather than the GLOSSARY anchor that the `present` lens keys on (`019eb701…`). C25 reconciles a knowledge-id target → its glossary anchor via `get_entity` (`_resolve_override_anchors`), and matches both the raw target AND the resolved anchor. For this row the knowledge node was un-retrievable (the public `/entities/{id}` resolves by canonical_id, not raw id) so the row was re-pointed to the glossary anchor for the smoke. Tracked finding for C26/FE: the divergence wizard should persist the glossary anchor id as `target_entity_id`.
- **glossary present lens is BOOK-scoped, not project-scoped:** base and delta surface the same glossary bio for an entity, so the override must apply AFTER the base+delta merge (the derivative's divergence truth wins over both). Implemented as merge-then-override.
