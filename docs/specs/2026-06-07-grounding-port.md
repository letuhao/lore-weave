# Spec — Shared Grounding Port (mui #3)

- **Date:** 2026-06-07 · **Branch:** `glossary/ai-pipeline-v2` · **Phase:** CLARIFY (PO sign-off pending).
- **Parent:** `docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md` (mui #3 — "consolidate per-consumer grounding into one port, last").
- **Size:** **XL** — new shared SDK + adoption across 3 services (lore-enrichment, knowledge, composition); multi-system contract. Workflow: v2.2 human-in-loop + `/review-impl` per phase (PO may opt into `/amaw`).

---

## 1. Problem (verified 2026-06-07)

"Grounding" — attaching evidence/citations to claims, and verifying generated content against canon — is implemented **divergently** in each consumer, with no shared code:

| Service | Grounding today | Verify today | Evidence shape |
|---|---|---|---|
| **lore-enrichment** | `GroundingRef` + multi-provider `compose_grounding` (`app/retrieval/grounding.py`) — the **mature** one | `CanonVerifier` (contradiction/anachronism/injection/regurgitation → `VerifyFlag`) `app/verify/canon_verify.py` | `GroundingRef{corpus_id,chunk_id,chunk_index,excerpt,score}` |
| **knowledge** | `EVIDENCED_BY` edges (provenance, **no text**) + `L3Passage` retrieval | precision-filter (LLM keep/drop, **ephemeral**, not persisted) | `L3Passage{text,source_type,source_id,chunk_index,score,chapter_index}` |
| **composition** | none per-item — packs all context into one prompt; lore hits carry source metadata only | spoiler/position rule (structural keep/drop) | dict `{text,source_type,source_id,chunk_index,score}` |
| **glossary (SSOT)** | authored evidence rows + `/evidences` | n/a (authored) | `evidence{evidence_id,attr_value_id,chapter_id,chapter_index,block_or_line,evidence_type,original_text,...}` (no score) |

Shapes are **similar but unaligned** (score conventions, locators, attach points). Three Python services each reimplement overlapping logic; only lore-enrichment has a real verifier. No `sdks/python/loreweave_grounding` exists (the SDK pattern does — `loreweave_eval` is the model: pure-Python, LLM injected as a Protocol).

## 2. CLARIFY locks (PO 2026-06-07)
| # | Decision | Locked |
|---|---|---|
| **L1** | Scope | **Full grounding SDK + adoption** — lift the grounding+verify logic into a shared package; wire knowledge + composition to it. |
| **L2** | Source of truth for the lib | lore-enrichment's `GroundingRef`/`compose_grounding`/`CanonVerifier` are the most mature → they are what gets lifted (generalized to a service-agnostic shape). |
| **L3 (proposed)** | Sequencing | Phased mini-epic; build the **SDK first**, adopt per service in later `/loom` cycles (mirrors #1c's G-merge→…→FE cadence). |
| **L4 (proposed)** | Risk posture | The SDK is **pure / no runtime coupling** (no HTTP, LLM injected as Protocol), so extracting it now is safe even though the merge-loop data shapes aren't live-proven — the unproven shapes (#1c merge) are NOT what grounding consumes. |

> **Open for the checkpoint:** confirm L3 (SDK-first, phased) + L4, and whether to opt into `/amaw` for the adoption phases (multi-system contract).

## 3. Design — `sdks/python/loreweave_grounding`

A pure-Python package (pydantic models + pure functions; any LLM call injected as a `Protocol`, per `loreweave_eval`). Registered in `sdks/python/pyproject.toml` `[tool.setuptools.packages.find].include`.

### 3.1 Unified evidence shape (`cites.py`)
```python
class GroundingCite(BaseModel):
    source_type: str          # "chapter" | "glossary_entity" | "chat_message" | "corpus" | "manual"
    source_id: str            # UUID / locator within source_type
    text: str                 # the quoted/grounding text (excerpt)
    score: float | None = None  # relevance 0..1; None = authored canon (glossary, no rank)
    chapter_id: str | None = None
    chapter_index: int | None = None    # reading position (spoiler filtering)
    block_or_line: str | None = None     # glossary-style fine locator
```
- `compose_cites(base, providers, *, top_k, dedup_key=...)` — generalization of lore-enrichment's `compose_grounding`: merge provider outputs, dedupe by normalized text, stable-sort by score desc (None sorts as authored-canon-first or a configurable rank), top-K. **Provider = a `Callable` injected by the service** (glossary-canon provider, knowledge-passage provider, corpus provider) — the SDK owns the merge/dedup/rank algorithm, not the I/O.
- Adapters: `from_glossary_evidence(row)`, `from_l3_passage(p)`, `from_grounding_ref(r)` — map each service's existing shape → `GroundingCite` (so adoption is incremental, not a rip-and-replace).

### 3.2 Verification (`verify.py`)
Lift `CanonVerifier` + `VerifyFlag`/`VerifyResult`/`FlagKind`/`Severity` verbatim-as-possible (it's already pure + well-tested in lore-enrichment). Generalize the hardcoded 封神 anachronism markers to **injected config** (`anachronism_markers: list[...]`, `canon_lookup: CanonLookupFn`) so it's book-agnostic (aligns with the de-bias NEUTRAL_PROFILE invariant — no hardcoded worldview).
```python
class CanonVerifier:
    def verify(self, proposal, facts, *, canon_lookup, anachronism_markers, ...) -> VerifyResult
```
Checks retained: contradiction (negation-proximity vs authored canon), anachronism (injected denylist), injection-neutralize, regurgitation (copyright). All pure/sync.

### 3.3 Ports (`ports.py`)
`GroundingReadPort` Protocol (what a service must provide to feed the composer): `get_glossary_canon`, `get_passages`, `get_chapter_locators`. Optional — services can keep their own clients and just map to `GroundingCite`.

## 4. Phasing (each its own `/loom` cycle + `/review-impl`)
1. ✅ **G3-SDK** *(DONE 2026-06-07)* — created `loreweave_grounding` (cites: `GroundingCite`+`merge_cites`/`compose_cites`+adapters · verify: `CanonVerifier`, markers/canon injected · sanitize+regurgitation verbatim · ports), registered in pyproject. **No service behavior change.** 22/22 SDK tests + `/review-impl` (MED-1: `from_grounding_ref` knowledge-context → neutral `"knowledge"` source_type, not a fake chapter id). Dropped the dead `read_port`/GraphStats coupling.
2. **LE-migrate** — lore-enrichment imports the SDK; its local `grounding.py`/`canon_verify.py` become thin shims (or are deleted) over the SDK. **Parity test: byte-identical grounding + verify output on a fixture** (the lift must not change behavior — the `loreweave_eval` 0a pattern). **← NEXT**
3. **K-adopt** — knowledge uses the SDK verifier in its precision filter (persist structured `VerifyFlag`s instead of ephemeral keep/drop) and/or emits `GroundingCite`s from L3 passages.
4. **C-adopt** — composition attaches `GroundingCite`s to packed entities/lore (per-item grounding it lacks today) via the SDK adapters.

## 5. Acceptance criteria
- AC1: `loreweave_grounding` installs via the existing `pip install /sdk` (in `packages.find`); imports with no HTTP/LLM hard dep.
- AC2: `GroundingCite` losslessly represents all four current shapes (adapters round-trip the fields each service needs).
- AC3: `compose_cites` reproduces lore-enrichment's current `compose_grounding` dedup/rank/top-K behavior (parity fixture).
- AC4: `CanonVerifier` reproduces lore-enrichment's current flags on the existing canon-verify test fixtures, with markers/canon injected (no hardcoded 封神).
- AC5 (later phases): LE-migrate is behavior-identical; K/C adoption adds grounding without regressing their suites.
- AC6: no service is forced to adopt — the SDK is additive; non-adopters keep working (best-effort/degradation invariant).

## 6. Risks
- **R-leaky:** consumers are asymmetric (composition doesn't ground per-item; knowledge's evidence is KG edges). Mitigation: `GroundingCite` is a *data* shape + the composer is *pure*; services adopt via adapters at their own pace (L1 "full" = the SDK + 2 adoptions, not a forced uniform rewrite).
- **R-premature:** arch doc said "after shapes stabilize". Mitigation (L4): the SDK is pure/no-coupling; the unproven shapes are the #1c merge ones, which grounding does not consume. Extracting now is safe; the *adoption* phases can wait if a consumer's shape is still moving.
- **R-parity:** the lift must not change lore-enrichment behavior. Mitigation: byte-identical parity fixtures (the `loreweave_eval` 0a discipline).

## 7. Confirm-at-BUILD (G3-SDK)
- Exact signatures of lore-enrichment `compose_grounding` + `GroundingRef` + `CanonVerifier.verify` + the flag/result dataclasses (re-read both files).
- Which lore-enrichment grounding/verify tests to lift as the SDK parity baseline.
- pyproject `packages.find` + any prompt/data-file include needed (verify has no prompt files; pure).
