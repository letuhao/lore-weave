# Track B brief — Domain Backend Capabilities & Fixes

**One-liner:** build the new domain tools the flagship needs + clear the domain feedback backlog. Mostly
independent of Track A — new tools auto-appear in the catalog once A's WS-1 lands.

- **Read first:** umbrella §5 (W2/W4), §6 Phase 4, §6b Track B · `contracts.md` (you IMPLEMENT C5; you get C4
  free from A's gateway normalization) · scenarios S02, S04 · investigation (memory=KG; auto-capture is F4 write-side).
- **Owns (services · files):**
  - glossary-service (Go): entity/parser/ontology handlers
  - knowledge-service (Py): KG projection, memory/L2, reader/world backends
  - chat-service (Py — **only** the context/persist files for auto-capture; NOT A's or C's files)
- **Deliver (largely parallel — disjoint services):**
  - **WS-4A seed-doc→entities** (glossary): `glossary_extract_entities_from_doc` per C5 → feeds
    `glossary_propose_entities`.
  - **WS-4B glossary→KG projection** (knowledge): `kg_project_entities_to_nodes` per C5 + `kg_propose_edge`
    fail-fast on missing endpoint (`KG_ENDPOINT_NOT_NODE`).
  - **WS-4C auto-capture** (chat/knowledge): persist chat-established facts as glossary entities as stated;
    admit `llm_tool_call` facts to L2 (lower the 0.8 gate for that source). Closes F4 write-side.
  - **Entity identity** (glossary): complete the in-flight `scope_label`/world-`scope` work (dedup key
    `(name,kind,scope)`, clean name) + `glossary_entity_rename` + reachable `glossary_entity_delete`.
  - **Domain feedback fixes** (glossary): upsert/merge-on-create · dedup NFC/NFD + read-your-writes ·
    `glossary_confirm_action` doc-drift · `propose_*`-writes-immediately naming.
  - **Product-journey backends** for W8/W10/W11 (world-container graph/map authoring; reader spoiler-cutoff).
- **Consumes:** C5 (own the signatures — coordinate with C so its workflows call them right); C4 (free from A).
- **Definition of done:** each new tool works end-to-end (unit + a live call); entity identity is world-scoped
  and editable; the W2/W4 flagship beats have real backing capability.
- **Validates via:** scenarios S02 (VB seed-doc), S03, S04; each new tool discoverable once N1 lands.
- **Note:** you can start immediately (gated only on the C5 signatures being frozen — they are). Build + unit-test
  against those; your tools appear in `tool_list` after N1.
