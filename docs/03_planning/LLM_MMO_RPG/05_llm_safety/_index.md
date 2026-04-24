# 05_llm_safety — Index

> **Purpose:** Cross-cutting LLM I/O discipline for the LLM MMO RPG track — 3-intent classifier (A5), command dispatch (A5), World Oracle (A3 determinism), 5-layer injection defense (A6). Implementation contract for `roleplay-service` + `world-service`. Split from `05_LLM_SAFETY_LAYER.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. `VERIFY OK`, sha256=`a0e022afde81fe30126c6b1977e55fc92bf039d7b83fdab82c542f68c7632864`, 15 403 bytes, 6 chunks.

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Former section | Lines | Resolves |
|---:|---|---|---:|---|
| 00 | [00_principle.md](00_principle.md) | H1 + §1 Principle | 26 | — (framing) |
| 01 | [01_intent_classifier.md](01_intent_classifier.md) | §2 Three-intent classifier | 23 | **A5-D1** (story / command / meta intents) |
| 02 | [02_command_dispatch.md](02_command_dispatch.md) | §3 Command dispatch | 74 | **A5** — structured tool-calls from classified intents |
| 03 | [03_world_oracle.md](03_world_oracle.md) | §4 World Oracle | 70 | **A3** — deterministic canon lookup (`OracleResult` contract, cached provenance) |
| 04 | [04_injection_defense.md](04_injection_defense.md) | §5 Injection defense — 5 layers | 89 | **A6** — 5-layer defense-in-depth (moved to 02_storage/S09 for canonical prompt-assembly enforcement) |
| 99 | [99_integration_and_refs.md](99_integration_and_refs.md) | §6 Integration · §7 Residual OPEN · §8 What this resolves · §9 References | 65 | Service wiring + residual pending-V1-data items |

**Totals:** 6 chunks · 15 403 bytes · 347 lines. All chunks well under 500-line soft cap.

---

## Exported stable IDs (authoritative owner = this subfolder)

- **A3** resolution — World Oracle + `OracleResult` contract (chunk 03)
- **A5-D1** — 3-intent classifier decision (chunk 01)
- **A5** — command dispatch pattern (chunk 02)
- **A6** — 5-layer injection defense framework (chunk 04)

**Cross-references (canonical enforcement lives elsewhere):**
- Prompt-assembly enforcement of A6 injection defense → `../02_storage/S09_prompt_assembly.md` (§12Y.L5 multi-layer defense)
- WebSocket-surface injection vector → `../02_storage/S12_websocket_security.md` (§12AB.L6 delimiter + fingerprint + nonce + HMAC)
- Canon injection defense → `../02_storage/S13_canonization_pre_spec.md` (§12AC.L9 5-layered canon markup + canary)
- Decision log rows (A3-*, A5-*, A6-* if added) → `../decisions/locked_decisions.md`
- Testing strategy for A3/A5/A6 → `../../05_qa/LLM_MMO_TESTING_STRATEGY.md`

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Editing the intent classifier or command dispatch:** edit chunks 01/02. Any change must be reflected in `../02_storage/S09_prompt_assembly.md` (the prompt-assembly library enforces the classifier contract at runtime).
3. **Changing the Oracle contract:** edit chunk 03. If the `OracleResult` shape changes, update the schema-as-code source in `contracts/oracle/` (when that package is created) and `../02_storage/R03_schema_evolution.md` additivity rules apply.
4. **New injection-defense layer:** extend chunk 04 + mirror the change into `../02_storage/S09_prompt_assembly.md` / `S12_websocket_security.md` / `S13_canonization_pre_spec.md` as appropriate.
5. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/05_llm_safety/chunk_rules.json --force
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/05_llm_safety/chunk_rules.json
```
