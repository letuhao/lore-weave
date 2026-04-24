<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_08_NAR_narrative_canon.md
byte_range: 55586-59109
sha256: 299c5d252170aa272884aea5556a98e18cc0f6e69af78cdbd851a2727cebea86
generated_by: scripts/chunk_doc.py
-->

## NAR — Narrative / Canon

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NAR-1 | Four-layer canon model (L1 axiomatic / L2 seeded / L3 local / L4 flexible) | ✅ | V1 | WA-3 | [03 §3](03_MULTIVERSE_MODEL.md) |
| NAR-2 | L3 event logging (every play emits durable events) | ✅ | V1 | IF-1 | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| NAR-3 | L1 runtime enforcement (reject or lint output violating axiomatic canon) | 🟡 | V1 | NPC-6 | Part of NPC-6; may need DF4 integration |
| NAR-4 | L3 → L2 canonization flow (author-gated, author-only trigger, no player request queue) | 📦 | V3 | NAR-2, WA-6 | **DF3 — Canonization**; [03 §9.7.1](03_MULTIVERSE_MODEL.md#971-author-only-trigger-m3-d1), M3-D1 |
| NAR-5 | Canon-worthy action detection (eligibility flag + World-Rule defaults by category) | 📦 | V3 | NAR-2, NAR-9 | DF3; [03 §9.7.3](03_MULTIVERSE_MODEL.md#973-eligibility--consent-gates-m3-d3), M3-D3 |
| NAR-6 | Canon-diff UI for author review (5 mandatory sections + 5s delay + typed confirm) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.2](03_MULTIVERSE_MODEL.md#972-diff-view-mandatory-m3-d2), M3-D2 |
| NAR-7 | IP attribution metadata for canonized content + author-controlled export | 📦 | V3 | NAR-4 | DF3 + [01 E3](01_OPEN_PROBLEMS.md); [03 §9.7.6](03_MULTIVERSE_MODEL.md#976-attribution--ip-metadata-m3-d6), M3-D6 |
| NAR-8 | L1/L2 author edit propagation — 6-layer author-safety UX (cascade preview, passive read-through default, optional force-propagate with 3-gate consent, L1 warnings, xreality channel reuse, change timeline) | ✅ | V1 | NAR-1, NAR-13..16 | [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution), M4-D1..D6 |
| NAR-13 | Cascade-impact preview modal before L1/L2 edit | ✅ | V1 | WA-3, NAR-8 | [03 §9.8.1](03_MULTIVERSE_MODEL.md#981-preview-before-l1l2-edit-m4-d1), M4-D1 |
| NAR-14 | Force-propagate L1/L2 change with 3-gate consent (edit opt-in + reality-owner consent + R13 audit) | 📦 | V3 | NAR-8, R13-L2 | [03 §9.8.3](03_MULTIVERSE_MODEL.md#983-optional-force-propagate-m4-d3), M4-D3; DF3-adjacent |
| NAR-15 | L1 axiomatic edit warnings (conflict listing + runtime canon-guardrail) | ✅ | V1 | NAR-3, NAR-8 | [03 §9.8.4](03_MULTIVERSE_MODEL.md#984-l1-axiomatic--louder-warnings-m4-d4), M4-D4 |
| NAR-16 | `xreality.canon.updated` event channel + meta-worker consumption | ✅ | V1 | R5-L2 meta-worker | [03 §9.8.5](03_MULTIVERSE_MODEL.md#985-xreality-event-channel-reuse-m4-d5), M4-D5 |
| NAR-17 | Glossary entity change timeline view with per-reality drill-down | ✅ | V1 | NAR-8, NAR-7 | [03 §9.8.6](03_MULTIVERSE_MODEL.md#986-glossary-entity-change-timeline-m4-d6), M4-D6 |
| NAR-9 | Per-PC canonization consent opt-in (default ON, sticky per PC) | ✅ | V1 | PO-4 | [03 §9.7.3](03_MULTIVERSE_MODEL.md#973-eligibility--consent-gates-m3-d3), M3-D3 |
| NAR-10 | 90-day canonization undo window + compensating-write for later reverts | 📦 | V3 | NAR-4 | DF3; [03 §9.7.5](03_MULTIVERSE_MODEL.md#975-reversibility--90-day-undo-window-m3-d5), M3-D5 |
| NAR-11 | L2 → L1 axiomatic promotion gate (R9 pattern: 7d cool + typed confirm + double approval) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.4](03_MULTIVERSE_MODEL.md#974-l2--l1-promotion--harder-gate-m3-d4), M3-D4 |
| NAR-12 | Canonized content distinguishability (label + icon + export strip/footnote/appendix) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.7](03_MULTIVERSE_MODEL.md#977-distinguishability-in-book-content-m3-d7), M3-D7 |

