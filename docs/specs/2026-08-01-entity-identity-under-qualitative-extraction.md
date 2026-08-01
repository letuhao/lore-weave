# Entity identity under qualitative extraction — an architecture review

**Date:** 2026-08-01 · **Status:** DIAGNOSIS (no code changed by this document) ·
**Trigger:** the author, on being shown that the canon gone-cast guard still cannot see a dead
character: *"data structure rất nghiêm ngặt nhưng cả extract glossary và KG không phải là hàm
định tính, và ở đây chúng ta đang ép buộc logic phi định tính phải tuân thủ định tính."*

That framing is correct, and the problem is larger than the bug that exposed it. This document
records what was **measured**, what the code **actually does**, and where the architecture — not
any single function — has to change. Everything below was read from source or queried from the
live dev stack on 2026-08-01; nothing is recalled from a handoff note.

---

## 1 · The defect, stated once

```
entity id = hash(user_id, project_id, name, kind)
```

`name` and `kind` are **both LLM outputs**. The system then joins on that key with **strict
equality**:

```cypher
-- app/db/neo4j_repos/fact_for_check.py :: _RESOLVE_GLOSSARY_IDS_CYPHER
UNWIND $glossary_entity_ids AS gid
MATCH (e:Entity {user_id: $user_id, glossary_entity_id: gid})
WHERE ($project_id IS NULL OR e.project_id = $project_id)
RETURN e.id AS id
```

No name fallback. No fuzzy tier. So:

- **Identity is a pure function of the model's surface choices.**
- A variation in wording or classification does not produce a *weaker match* — it produces a
  **different identity**.
- **A miss does not degrade; it MINTS.** There is no third outcome.
- The resulting duplicate is **not automatically reversible** — a human merges it by hand.

The codebase already knows this. `app/extraction/entity_resolver.py`:

> *"Because entity identity is hash(user, project, name, kind), that miss does not degrade to
> 'no anchor' — it MINTS A SECOND NODE beside the author's. Measured on the live Mị Đế chapter:
> Chân Linh, Vô Cấu Chân Linh and Thần hồn each forked a duplicate next to their anchored twins."*

---

## 2 · Measured evidence (dev stack, 2026-08-01)

**The consequence, at the point where it matters.** The composition canon guard asks
knowledge-service for liveness by **glossary entity id**; knowledge resolves it through the
`glossary_entity_id` FK.

| measurement | value |
|---|---|
| `:EntityStatus` rows in the whole graph | **21**, across 5 projects |
| …of those, attached to an entity **with** `glossary_entity_id` | **0** |
| project `019effe4`: entities / glossary-linked | 1814 / **1751** |
| …its `张若尘` node carrying 4 status rows | **one node, `glossary_entity_id` NULL** |
| throwaway book `019fbd90` (this session): entities / linked | 9 / **0** |

⇒ **No liveness row in the system has ever been reachable by the guard's query, on any book.**
The gone-cast check has never fired on real data — not because it is wrong, but because the
join key it reads through and the join key the status lands on are different populations.

Note the `019effe4` case specifically: that project *does* have 1751 anchored entities, so this
is not "the book had no glossary". The one node the death attached to is the unanchored one.

**Two entity populations, one graph:**

| | created by | carries `glossary_entity_id` | carries `:EntityStatus` |
|---|---|---|---|
| glossary-anchored | `glossary.entity_updated` events + K13.0 Pass 0 | ✅ | ❌ |
| extraction-minted | `resolve_or_merge_entity` from prose | ❌ | ✅ |

---

## 3 · Patch archaeology — why this is systemic

The anchoring mechanism is **well built and well documented**. K13.0 Pass 0
(`load_glossary_anchors`) pre-loads the book's glossary entries, MERGEs each as an anchored
`:Entity`, and hands the resolver a name/alias → canonical_id index. The two-layer pattern in
CLAUDE.md (glossary = authored SSOT, knowledge = derived, anchored by FK) is real code, not
aspiration.

And yet the file history is a chain of **narrowing patches on the lookup side**, each added
after a live duplication incident:

| patch | what it rescued |
|---|---|
| `_EXTRACTOR_TO_GLOSSARY_KIND` | extractor vocabulary ≠ glossary `kind_code` |
| `D-KG-KIND-VOCAB-FORK` | name-only fallback, gated on 2 conditions |
| C17 alias-map redirect | a human's merge being resurrected by re-extraction |
| `D-ANCHOR-PRELOAD-50-CAP` | handler's silent `limit=50`: a 300-entity book anchored 50 and **forked 250** |
| `D-ANCHOR-PRELOAD-FREQUENCY-GATE` | `min_frequency=2` default ⇒ a book written from scratch loaded **0 anchors** and extracted blind (live: 0 → 12 at `min_frequency=0`) |
| `AnchorPreloadUnavailable` | the read failing used to return `[]` "so extraction still runs" — fail-open dressed as resilience |

Each fix is correct in isolation. All of them are **defending an exact key against fuzzy
input, one observed failure at a time.** That list is unbounded, because the space of ways an
LLM can name a thing is unbounded.

---

## 4 · Quality protections — present, and where the gap is

**Present, and genuinely good:**

- **Glossary review lifecycle.** `glossary_entities.status` — measured `draft` 6080 / `active`
  905 / `rejected` 10. A real human-in-the-loop state already exists on the authored side.
- **Evidence with citation.** Every write attaches an evidence edge carrying an exact quote
  (`_evidence_quote`), the extraction model, and the job id. `min_evidence` gates the guard read.
- **Triage** for off-schema edges (L7B write-boundary guard parks rather than drops silently).
- **Tier B autocreate off by default**, per-chapter cap, repaired endpoints confidence-capped
  at `0.3`, autocreate only above `confidence > 0.8`.
- **Fail-closed anchor preload** — refuses to extract un-anchored rather than mint duplicates.
- **The guard never fabricates.** Unresolvable cast → `unresolved_refs` → `check_over(0)` →
  `NO_RULES`. It reports that it could not check; it does not paint green.

**Missing — and the asymmetry is the finding:**

1. **The entity write has no confidence gate at all.**
   `pass2_writer.write_pass2_extraction` step 2 writes every LLM-emitted entity that survives
   `_sanitize` and a non-empty check. Confidence is *stored*, never *consulted*. Relations have
   thresholds; the object that **defines identity** has none.

2. **The KG has no "unresolved" state.** Resolution is binary: anchor hit → anchor, miss →
   mint. A qualitative producer requires a third outcome. The glossary already models it
   (`draft`); the KG does not.

3. **The fork is invisible.** `anchor_resolver_misses_total` counts misses, but nothing
   separates *"a genuinely new entity"* from *"failed to match one that already exists"*. Those
   are opposite events sharing one metric.

4. **The guard conflates two silences.** `CheckStatus` (`sdks/python/loreweave_guard`) has
   `NO_RULES` = *"ran, but the input corpus was empty"*. There is **no member** for *"the corpus
   is populated and this scene's cast could not be resolved into it"*. For a new book the first
   is normal; the second is a system defect — and the author cannot tell them apart.

---

## 5 · Where the architecture should change

Not another lookup patch. Give the write path the state its input semantics demand.

- **A · Make "unresolved" a first-class outcome.** *(the unlock; medium)*
  On an anchor miss in a book that **has** a glossary, do not mint a canonical node — write a
  **candidate** (unanchored, flagged) and surface it to the author as a glossary proposal.
  `draft` exists for exactly this. Promotion sets the FK. This converts a silent, irreversible
  fork into a reviewable queue, and it makes the human the disambiguator instead of the hash.

- **B · Separate identity from the name.** *(the structural fix; large — needs its own plan)*
  Identity should be an opaque id owned by the glossary layer. The KG should hold **mentions**
  pointing at it, not derive identity from `hash(name, kind)`. Until this lands, every LLM
  surface-form variation remains an identity event.

- **C · Make the fork measurable.** *(cheap; do first)*
  Per extraction, report: anchored / minted-new / **and of the minted, how many fold-collide
  with an existing anchor under a looser comparison**. That last number is the honest size of
  the problem, and nothing currently computes it. Without it, A and B are being designed blind.

- **D · Add the missing `CheckStatus`.** *(small)*
  Distinguish "cast could not be resolved" from "no rules". Same class of honesty fix as the
  per-check guard work earlier in this session, one layer down.

**Order:** C → D → A → B. C and D are cheap and make the rest legible; A is the behavioural
change; B is the re-architecture and should not start before C has produced numbers.

---

## 6 · What this document does NOT claim

- **The status-attach mechanism is a HYPOTHESIS, not a measurement.**
  `_resolve_status_entity_id` resolves via the chapter-local map (Tier A.1) before the anchor
  index (Tier A.2) — but the chapter-local map holds whatever `resolve_or_merge_entity` already
  returned, which **is** the anchor's id on a hit. So the status resolver *inherits* the entity
  step's outcome rather than causing the fork. The defect is upstream. **This was reasoned from
  code, not measured**, and confirming it is the next measurement to take — before any fix.

- **No claim that anchoring is broken in general.** For the throwaway book used in this
  session's live smoke the anchor set was legitimately empty (the book has no glossary entries
  at all), so that run could never have demonstrated the guard working, in either direction.

- **No cost or performance analysis** of candidate-state writes or of a mentions model.

- **The 21-row figure is the whole dev graph**, which is a development corpus, not production
  scale. The *ratio* (0 of 21 reachable) is the finding; the absolute number is not.

---

## 7 · Source references

| concern | file |
|---|---|
| strict FK resolution (the join) | `services/knowledge-service/app/db/neo4j_repos/fact_for_check.py` |
| anchor pre-load, degradation model | `services/knowledge-service/app/extraction/anchor_loader.py` |
| anchor index + resolve-or-mint | `services/knowledge-service/app/extraction/entity_resolver.py` |
| entity/status write path | `services/knowledge-service/app/extraction/pass2_writer.py` |
| guard status vocabulary | `sdks/python/loreweave_guard/` (`CheckStatus`) |
| liveness cascade (KG → plan → none) | `services/composition-service/app/engine/canon_reflect.py` |
| two-layer pattern (the rule) | `CLAUDE.md` › Architecture · `docs/standards/scope-separation.md` |
