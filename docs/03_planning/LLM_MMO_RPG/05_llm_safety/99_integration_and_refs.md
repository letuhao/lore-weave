<!-- CHUNK-META
source: 05_LLM_SAFETY_LAYER.ARCHIVED.md
chunk: 99_integration_and_refs.md
byte_range: 11913-15403
sha256: 3b0f2eef8d13bc06670054b42b336d54fd0b7863d9867d929452f28fa004b626
generated_by: scripts/chunk_doc.py
-->

## 6. Integration with other services

### 6.1 `world-service`

Hosts command dispatch (§3) + World Oracle (§4). Writes L3 events. Owns projections. **Does not call LLM directly** — narration is roleplay-service's job.

### 6.2 `roleplay-service`

Orchestrates LLM calls:

1. Receives narration-needed event (session action resolved, fact question, free narrative)
2. Assembles prompt: persona + canon retrieval (A6-D3) + user_input (A6-D2)
3. Calls LLM (via provider gateway)
4. Output filter (A6-D4)
5. Streams response to client via WebSocket
6. Emits `session.narrated` event for downstream (audit, drift detector)

Uses knowledge-service for retrieval. Uses world-service for Oracle queries. Uses provider-registry for LLM credentials.

### 6.3 `knowledge-service`

Provides canon-scoped retrieval (A6-D3). Enforces per-PC isolation (A6-D5) at service layer. Indexes per-pair NPC memory via pgvector (R8-L6).

### 6.4 Deferred: `output-filter-service`?

For V1, output filter (A6-D4) is a library inside roleplay-service (not a separate service). If filter becomes heavy (large model, high QPS), split into dedicated service in V2+. Not a V1 decision.

---

## 7. Residual OPEN (require V1 data or ongoing ops)

| Sub-item | Blocker |
|---|---|
| 3-intent classifier accuracy | V1 prototype on real sessions |
| Oracle key coverage (what fraction of fact questions hit pre-computed?) | V1 measurement; missed keys added over time |
| Tool-call reliability per model (Claude / GPT-4 / local Qwen / Ollama) | Per-model benchmark on real prompts; feeds provider selection |
| Output filter calibration (false positives vs misses) | V1 tuning + adversarial red-team |
| Novel jailbreak classes | Ongoing; no framework can claim "solved" |
| Oracle cache hit rate | V1 metric; feeds pre-warm strategy |
| Canon-drift detector (G3) integration | G3 itself is OPEN, future work |

---

## 8. What this resolves from 01_OPEN_PROBLEMS

| Problem | Status after this doc | Reason |
|---|---|---|
| **A3 Determinism & reproducibility** | `OPEN` → `PARTIAL` | Oracle pattern framework locked. Classifier accuracy + Oracle key coverage pending V1 data. |
| **A5 Tool-use reliability** | `PARTIAL` (formalized) | 3-intent classifier + hard rule (state mutations from client only) + tool-call allowlist locked. Per-model reliability benchmark pending V1. |
| **A6 Prompt injection & jailbreak** | `PARTIAL` (formalized) | 5-layer defense locked; Layer 3 (canon-scoped retrieval) is structural primary. Output filter calibration + novel jailbreak classes are ongoing ops. |

See [OPEN_DECISIONS.md](OPEN_DECISIONS.md) entries A3-D1..D4, A5-D1..D4, A6-D1..D5 for the 13 locked decisions.

---

## 9. References

- [01_OPEN_PROBLEMS.md §A3/A5/A6](01_OPEN_PROBLEMS.md) — problem statements
- [02_STORAGE_ARCHITECTURE.md §7 R7-L1 single-writer session, §12H R8 NPC memory aggregate split](02_STORAGE_ARCHITECTURE.md)
- [03_MULTIVERSE_MODEL.md §3 Four-layer canon, §9.7 Canonization safeguards](03_MULTIVERSE_MODEL.md) — canon layers + M3
- [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md) — PC identity, session scope
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — A3-D1..D4, A5-D1..D4, A6-D1..D5 locked
- Generative Agents paper (arXiv:2304.03442) — memory stream + retrieval patterns
- MemGPT (arXiv:2310.08560) — hierarchical memory context management
- OWASP LLM Top 10 — injection defense principles
