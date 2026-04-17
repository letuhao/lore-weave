# Session Handoff — Session 45 END / Session 46 START (K17.10-partial)

> **Purpose:** orient the next agent in one read. **Source of truth for detailed state remains [SESSION_PATCH.md](SESSION_PATCH.md).** This file is the single, unversioned handoff — updated in place at the end of each session. Do NOT create `_V*.md` variants.
> **Date:** 2026-04-17 (session 45 END)
> **HEAD:** K17.10-partial (2 commits this session: K17.9-R1 + K17.10-partial)
> **Branch:** `main` (ahead of origin by sessions 38–45 commits — user pushes manually)

---

## 1. TL;DR — what shipped this session

Session 45 shipped two things:

1. **K17.9-R1** — `/review-impl` adversarial follow-ups. Deep re-read of K17.9 caught 5 real issues (1 MED, 2 LOW, 1 COSMETIC, 1 TRIVIAL) the initial self-review rubber-stamped. Fixes + 1 new CJK predicate injection test, landed in commit `7f8702c`.
2. **K17.10-partial** — Golden-set extraction-quality eval, harness complete, 3 of 5 English fixtures landed. Remaining 2 English fixtures blocked by Anthropic output content filter (see §4 below for the resume plan).

```
K17.9-R1  /review-impl follow-ups          ✅  +1 CJK test, comments, test hygiene (commit 7f8702c)
K17.10    Golden-set quality eval          ⚠  PARTIAL: harness 100% done + unit-tested; 3/5 fixtures
```

**Test execution:**
- `tests/unit/test_eval_harness.py`: **18/18 pass in 0.45s**
- `tests/quality/` without flag: 1 skipped (opt-in `--run-quality`), as designed
- `test_pass2_writer.py`: **15/15** after K17.9-R1
- Pre-existing environmental failures (SSL/truststore `OSError [Errno 22]`) in `test_config.py` / `test_circuit_breaker.py` / `test_glossary_client.py` — **not caused by this session**, confirmed on HEAD via `git stash`.

---

## 2. Where to pick up (K17.10 resume plan — top priority)

```
K17.1–K17.9     LLM extraction pipeline + injection defense   ✅
K17.10          Golden-set quality eval                        ⚠ PARTIAL
  ├─ harness (eval_harness.py + tests)                        ✅ 18/18
  ├─ opt-in pytest marker + LLM entry point                    ✅
  ├─ alice_ch01 / alice_ch02 / sherlock_scandal_ch01           ✅
  ├─ 4th English fixture                                       ← NEXT
  └─ 5th English fixture                                       ← NEXT
K17.10-v2       Xianxia + Vietnamese fixtures                  ← after v1 + threshold tuning
K16.2–K16.15    Extraction job lifecycle                       ← parallel track
```

### Resume recipe (30-60 min expected)

1. **Read the README** at [services/knowledge-service/tests/fixtures/golden_chapters/README.md](../../services/knowledge-service/tests/fixtures/golden_chapters/README.md) — schema, annotation rules, the content-filter gotcha.
2. **Get two public-domain excerpts** (3–5 paragraphs each). Safer sources than Conan Doyle (which tripped the filter twice):
   - *Pride and Prejudice* ch. 1 — "It is a truth universally acknowledged…" (Project Gutenberg #1342)
   - *The Adventures of Tom Sawyer* ch. 1 — "TOM!" aunt Polly scene (Gutenberg #74)
   - *Little Women* ch. 1 opening (Gutenberg #514)
   - *Moby Dick* ch. 1 opener "Call me Ishmael…" (Gutenberg #2701) — already planned
   - If Conan Doyle specifically matters: paste directly from Gutenberg instead of asking the model to reproduce.
3. **Annotate each** following the schema in `expected.yaml` files of the 3 existing fixtures. 3–6 entities, 2–4 relations, 2–4 events, 2–3 traps per chapter. Conservative — when in doubt, make it a trap.
4. **Verify** with `pytest tests/unit/test_eval_harness.py -v` — the `test_iter_chapter_fixtures_sorted` test will round-trip both new fixtures through the loader.
5. **(Optional) Run the live eval** once the fixture set is complete, to sanity-check thresholds:
   ```bash
   export ANTHROPIC_API_KEY=…
   export KNOWLEDGE_EVAL_MODEL=claude-haiku-4-5-20251001
   export KNOWLEDGE_EVAL_MODEL_SOURCE=user_model
   export KNOWLEDGE_EVAL_USER_ID=<uuid>
   pytest tests/quality/ --run-quality -v -s
   ```
6. **Close D-K17.10-01** in SESSION_PATCH.md "Recently cleared" once the two fixtures land.

### Alternative: hand-code the fixtures

The filter is on **model output**, not input. You (the user) can paste the chapter text into the session and the model can then annotate it — filter bypassed entirely. That's the most reliable path.

---

## 3. Deferred items — 2 new this session

| ID | Description | Target |
|---|---|---|
| **D-K17.10-01** | 2 remaining English fixtures blocked by content filter. Harness is feature-complete; just need two more `{chapter_id}/chapter.txt + expected.yaml` pairs. | K17.10-v1-complete (session 46) |
| **D-K17.10-02** | Xianxia (2) + Vietnamese (2) fixtures. v1 stays English-only so thresholds can stabilize on a clean seed. | K17.10-v2 (after v1 threshold tuning) |

All other deferrals unchanged. See [SESSION_PATCH.md §Deferred Items](SESSION_PATCH.md).

---

## 4. Important context the next agent must know

### K17.10 — the Anthropic content-filter gotcha (NEW)

- Asking the model to reproduce period-typical 19th-century adventure prose for fixture generation tripped **"Output blocked by content filtering policy"** on two separate Conan Doyle excerpts in session 45 (A Scandal in Bohemia ch. 2, The Red-Headed League ch. 1).
- The filter is on the **output** side. The input prompt was fine; the model's reproduction hit it.
- **Workaround:** have the human paste the Gutenberg excerpt directly into the session, then annotate. Do not ask the model to reproduce copyrighted-adjacent or period-flavored text.
- Documented in [tests/fixtures/golden_chapters/README.md](../../services/knowledge-service/tests/fixtures/golden_chapters/README.md) under "Content-filter gotcha".

### K17.10 — architectural decisions worth knowing before extending

- **Harness imports K15.1 + K17.5 canonicalizers directly** — no duplication. If K17.5 `_normalize_predicate` changes, the eval automatically uses the new rule. The import of the private `_normalize_predicate` is explicit with a justification comment.
- **Macro-mean aggregation, not micro-weighted.** `mean(chapter_P)` — one big chapter doesn't dominate.
- **Unified TP/FP/FN across entities+relations+events per chapter.** Don't split into three separate scorecards — it would let extractors game the best-performing kind.
- **Trap hits count as BOTH an FP (precision denominator) AND a trap-rate numerator.** Prevents gaming precision by racing toward traps.
- **Event summary matching:** asymmetric Jaccard on token sets, threshold 0.50, filtered to tokens `len > 2` (drops "a", "the", "to"). Asymmetric on purpose — paraphrase should not penalize.
- **No Neo4j writes during eval.** Test calls `extract_entities`/`extract_relations`/`extract_events` directly — skips Pass 2 writer, graph stays clean.
- **Opt-in only.** `@pytest.mark.quality` + `--run-quality` flag. Default `pytest` run skips it with a clear reason. CI remains free and deterministic.

### K17.9 correction to previous handoff (IMPORTANT — the old note was wrong)

Previous handoff claimed "a predicate-level injection test would either never match or be misleading — correctly omitted from K17.9 coverage." That was wrong. K17.9-R1 **added** exactly that test (`test_k17_9_relation_predicate_cjk_injection_sanitized`) because:
- `[^\w]+` → `_` treats CJK characters as `\w` in Python 3, so `无视指令` survives normalization intact.
- For CJK, `_sanitize(rel.predicate)` is load-bearing and needs regression coverage.
- `pass2_writer.py` has a comment documenting why the call stays despite English being pre-normalized.

Short version: **for CJK content, predicate injection coverage matters.**

### Workflow v2.2 (12-phase) — unchanged from session 45

```
CLARIFY → DESIGN → REVIEW-DESIGN → PLAN → BUILD → VERIFY → REVIEW-CODE → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

- **POST-REVIEW** is a human checkpoint, NOT a self-adversarial re-read. Deep review is on-demand via the explicit `/review-impl` command. Session 45's K17.9-R1 proved the reshape was right — the initial K17.9 self-review rubber-stamped "0 issues" and `/review-impl` found 5 real ones.
- State machine: `.workflow-state.json` + `scripts/workflow-gate.sh` (run from repo root).
- Pre-commit hook blocks commits without VERIFY + POST-REVIEW + SESSION completed.

### Infra & test invocation (unchanged)

- Compose: `cd infra && docker compose up -d`; Neo4j profile: `docker compose --profile neo4j up -d neo4j`
- Neo4j port: **7688**, Postgres port: **5555**
- pytest from `services/knowledge-service/`. Quality eval is opt-in: `pytest tests/quality/ --run-quality`.

### Multi-tenant safety rail (unchanged)

- `entity_canonical_id` scopes by `user_id` + `project_id`. `project_id=None` → `"global"` in the hash key.

### Pre-existing failing tests to ignore

`test_config.py` / `test_circuit_breaker.py` / `test_glossary_client.py` throw `OSError: [Errno 22]` from `truststore._api.load_verify_locations`. This is an environment/SSL issue pre-existing on HEAD (verified via `git stash`). Not in scope for K17.10 work. Fix is separate infra hygiene.

---

## 5. Session 45 stats

| Metric | Before session 45 | After session 45 | Delta |
|---|---|---|---|
| `test_pass2_writer.py` tests | 7 | **15** | **+8 (K17.9 + K17.9-R1 CJK test)** |
| `test_eval_harness.py` tests | 0 | **18** | **+18 (new K17.10)** |
| K17.4–K17.10 extraction-scoped unit tests | 70 | **≈186** (185 extraction + 18 harness = 203 total; 18 unit harness + 185 K17 pipeline) | — |
| Golden fixtures | 0 | **3 of 5 planned English** | +3 |
| Session commits | 0 | **2** (K17.9-R1 landed `7f8702c`; K17.10-partial pending) | — |
| New deferred items | — | **2** (D-K17.10-01 + D-K17.10-02) | +2 |
| Production behavior changes | — | 0 | — |

---

## 6. Housekeeping note

This file is the single, unversioned handoff. **Future sessions MUST update this file in place — do NOT create a `_V19.md`.**
