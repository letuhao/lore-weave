# Interface Matrix — FE-support · BE-only · MCP-support

- **Date:** 2026-06-26
- **Purpose:** Classify every platform capability by *how it can be reached*, so we can decide **what a public external agent gets through MCP**. This is the decision input for [03-public-mcp-security-design.md](03-public-mcp-security-design.md).

## How to read this

Each capability is tagged with one or more **interfaces**:

| Tag | Meaning |
|---|---|
| **FE** | Has a frontend UI (a human can do it in the app) |
| **REST** | Public `/v1/*` JWT REST endpoint exists |
| **MCP** | Exposed as an MCP tool (today, internally) |
| **BE-only** | Exists only as `/internal/*` service-to-service or background worker — **no FE, no public REST, no MCP** |
| **ADMIN** | Requires admin (RS256) authority |

And with an **MCP tier** where applicable: **R**ead / **A**uto-write / **W** confirm-gated / **S** schema-secret.

> **Key takeaway up front:** the platform already has *deep* MCP coverage (~100 tools across 10 domains) — books, chapters, glossary, wiki, knowledge graph, translation, composition, jobs, settings, enrichment are all MCP-reachable. The gap for "public MCP" is **not** missing tools; it is (a) **auth at the edge** (no external credential exists), (b) **the write-gating model assumes a browser** (confirm cards / suspend-resume), and (c) **identity/billing/abuse controls** for an untrusted caller. See §4–§6.

---

## 1. Capability matrix by domain

### Identity & account (auth-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Register / login / refresh / logout | ✓ | ✓ | — | Edge-of-platform; **never** MCP |
| Change password / reset / verify email | ✓ | ✓ | — | Security-sensitive; never MCP |
| Read/update profile, preferences | ✓ | ✓ | **MCP-A** (`settings_update_profile`) | profile is MCP-writable (Tier-A) |
| Public profile, follow/followers | ✓ | ✓ | — | social |
| Delete account | ✓ | ✓ | — | never MCP |
| Admin token mint, break-glass | — | ADMIN | — | BE/admin only |
| Email→user_id, full-profile | — | BE-only | (used by settings MCP) | internal |

### Books & chapters (book-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| List/get books & chapters, revisions | ✓ | ✓ | **MCP-R** | full read coverage |
| Create/update book & chapter, save draft, bulk-create | ✓ | ✓ | **MCP-A** | auto-write + undo |
| Publish / unpublish / delete / purge / restore-revision | ✓ | ✓ | **MCP-W** | confirm-gated |
| Media / audio generate (priced) | ✓ | ✓ | **MCP-W*** | cost-gated |
| Cover upload, import (.docx/.epub), progress, stats, favorites | ✓ | ✓ | — (some) | upload/import not MCP-exposed |
| Collaborators (E0 grants) | ✓ | ✓ | — | not MCP today |
| Worlds (container) | ✓ | ✓ | — | not MCP today |
| Book projection, access resolver, lexical-search, chapter blocks/scenes/hierarchy | — | BE-only | — | service-to-service |

### Glossary & wiki (glossary-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Search / get entity / list standards / ontology read | ✓ | ✓ | **MCP-R** | rich read |
| Chapter-links, evidence, draft translations | ✓ | ✓ | **MCP-A** | |
| Propose entity/kind/attr/alias/merge/status/reassign, plan | ✓ | ✓ | **MCP-W** | confirm-gated; lands in AI-suggestions inbox |
| Book/user tier create/patch/delete/revert | ✓ | ✓ | **MCP-W** | |
| Deep-research (priced) | ✓ | ✓ | **MCP-W*** | cost-gated |
| **Wiki** list/get/create/edit/delete | ✓ | ✓ | (via kg) | wiki-gen is MCP (`kg_build_wiki`) |
| Wiki revisions, suggestions, staleness | ✓ | ✓ | — | |
| System-tier kinds/genres/attrs | — (CMS) | ADMIN | **MCP-W (admin)** | `glossary_admin_*` |
| extract-entities, dedup, canon-content, enrichments, gold-pairs | — | BE-only | — | service-to-service |

### Knowledge graph & memory (knowledge-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Graph query, schema read, views, timeline, memory search/recall | ✓ | ✓ | **MCP-R** | |
| Propose fact/edge, schema-edit, adopt-template, triage resolve, view upsert | ✓ | ✓ | **MCP-A** | |
| Project create, **build graph**, **build wiki**, run benchmark | ✓ | ✓ | **MCP-W*** | cost-gated; `kg_build_graph` is the heavy one |
| Pending-facts confirm/reject, summaries, costs/budget, user-data export/delete | ✓ | ✓ | — (some) | |
| extract-entities, parse, summarize, coref, context/build, enriched writeback | — | BE-only | — | extraction internals |
| System graph-schema templates | — (CMS) | ADMIN | **MCP-W (admin)** | `kg_admin_*` |

### Translation (translation-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Coverage, segment status, versions, job status | ✓ | ✓ | **MCP-R** | |
| Set-active, save-edited, patch-block, update settings | ✓ | ✓ | **MCP-A** | |
| Start job / retranslate-dirty / start-extraction (priced) | ✓ | ✓ | **MCP-W*** | cost-gated |
| Job control (cancel/pause/resume/retry) | ✓ | ✓ | **MCP-A/W** | resume/retry re-spend → W |
| translate-text (sync) | ✓ | ✓ | — | not MCP |
| dispatch, extraction-cache replay/merge/retention | — | BE-only | — | worker internals |

### Composition / LOOM (composition-service)
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Get work/outline/prose/canon-rules/job | ✓ | ✓ | **MCP-R** | |
| Outline nodes, scene-links, canon-rules, write-prose | ✓ | ✓ | **MCP-A** | |
| Create work, generate (priced), publish | ✓ | ✓ | **MCP-W*** | cost-gated |
| Style/voice profiles, references, grounding, decompose, critique, progress | ✓ | ✓ | — | rich FE, not all MCP |
| pairwise-judge, promise-audit/extract/coverage | — | BE-only | — | eval internals |

### Jobs / settings / billing / chat / enrichment / misc
| Capability | FE | REST | MCP | Notes |
|---|---|---|---|---|
| Jobs list/summary/get + control + SSE | ✓ | ✓ | **MCP-R** (list/summary/get) | control is REST/FE; SSE is FE |
| Settings: profile, providers, models, defaults, inventory | ✓ | ✓ | **MCP-R/A** | secrets always redacted |
| Settings: model delete | ✓ | ✓ | **MCP-W** | |
| **Provider credential secret create/update** | ✓ | ✓ | **never MCP (S)** | secret must not enter agent context |
| Usage logs, summary, guardrail get/set, balance | ✓ | ✓ | — | not MCP; relevant for public spend caps |
| Billing reserve/reconcile/release | — | BE-only | — | the spend gate |
| Chat sessions/messages/outputs/voice | ✓ | ✓ | — | chat is the *client*, not a tool host |
| Enrichment jobs, gaps, proposals, compose, sources | ✓ | ✓ | **MCP-W*** (auto-enrich) | proposals reviewed in FE |
| Campaigns (auto-draft factory) | ✓ | ✓ | — | saga; not MCP today |
| Roleplay scripts + evaluate | ✓ | ✓ | — | |
| Video generation | ✓ | ✓ | — | priced; not MCP today |
| Leaderboards, public stats | ✓ | ✓ | — | public read |
| Notifications | ✓ | ✓ | — | relevant as async-completion channel for agents |
| Learning corrections / eval / mining | ✓ (some) | ✓ | — | read API |
| Catalog (public books/chapters) | ✓ | ✓ | — | unauthenticated public |
| Sharing visibility + unlisted | ✓ | ✓ | — | |

---

## 2. Roll-up counts

| Interface | Approx. capabilities | Comment |
|---|---|---|
| **FE-supported** | ~26 feature modules → hundreds of actions | the whole product |
| **Public REST** | ~400+ `/v1/*` routes | every FE action has a REST route behind it |
| **MCP-exposed** | **~100 tools / 10 domains** | books, glossary, wiki, KG, memory, translation, composition, jobs, settings, enrichment |
| **BE-only** | ~80+ `/internal/*` routes + ~18 worker/ops services | extraction internals, billing gate, projections, sweepers |
| **Admin-only** | system-tier glossary/KG + billing admin + auth admin | RS256 |

## 3. Three notable gaps (capabilities *not* yet MCP, that a public agent might want)

These are **candidates** for new tools if the public-MCP product demands them — but each is fine to defer:

1. **Catalog / discovery read** — a public agent cannot currently *browse public books* via MCP (catalog is REST-only). Cheap to add a `catalog_*` read provider; high value for "let an external agent find content."
2. **Job control + async completion** — `jobs_*` is read-only over MCP; cancel/pause/resume is REST/FE only, and async-completion signalling to a headless agent has no channel (FE uses SSE + notifications). A public agent that starts a priced job needs a **poll or webhook** completion story (design doc §7, ties to internal `D-MCP-ASYNC-INCHAT-MSG`).
3. **Import / upload** — bulk chapter import and file upload are REST-only (multipart). A public agent ingesting a manuscript would need an MCP-friendly ingest path (or a presigned-upload tool).

## 4. Why "expose MCP publicly" is not just "open a port"

The internal MCP layer's three load-bearing assumptions all **break** for an untrusted external caller:

| Internal assumption (works today) | Why it breaks for a public agent |
|---|---|
| **Identity = `X-User-Id` forwarded by a trusted consumer** (chat-service verifies the JWT, forwards the header under `X-Internal-Token`). | An external agent is the consumer. There is no trusted party to verify a JWT and forward identity. The edge must *itself* authenticate the agent and *derive* `X-User-Id`. The BFF does **no** auth today (pure pass-through) — so a new auth-enforcing edge is required, not a config tweak. |
| **`X-Internal-Token` is a private-network shared secret.** | It must never reach the internet. Whatever the public agent presents must be a *different* credential class, exchanged at the edge for the internal envelope. |
| **Tier-W/S writes are gated by a human clicking a confirm card in the browser** (suspend→Apply, the `agui` frontend-tool channel). | A headless agent has no browser. "Suspend and wait for Apply" would hang forever (this is internal hole **H12/E8**). The public-MCP write policy needs a *non-visual* gate: deny W/S, or a programmatic two-call confirm the agent itself drives, or out-of-band human approval. |

## 5. What already helps us (assets to reuse)

- **Envelope-only identity + `extra="forbid"` + anti-oracle** — every tool already refuses LLM-supplied scope and never leaks existence. A public caller inherits these for free.
- **Tier model + confirm tokens** — server-minted, bound to user+payload+expiry, re-priced at execute. The confirm-token machinery is *exactly* the primitive a headless agent needs for a programmatic gate (no browser required to hold a token).
- **Spend guardrails (reserve→reconcile→release)** — per-user USD caps already gate every priced job. Public agents inherit the same wallet; we add a *per-key* sub-cap on top.
- **BYOK secrets are AES-GCM, never returned** — `settings_list_*` already redacts. A public agent never sees a provider secret.
- **Catalog/version + partial-catalog flag in ai-gateway** — discovery degrades gracefully.

## 6. Decision inputs for doc 03

From this matrix, the public-MCP design must decide:

1. **Which tiers an external key may call.** Recommended default: **R + A**, opt-in **W** (with a programmatic confirm flow + spend cap), **never S** (schema/secret) and never admin.
2. **Which domains to expose first.** Recommended v1: `memory_*`, `kg_*` (R/A), `glossary_*` (R/A), `book_*` (R/A), `jobs_*` (R), plus a new `catalog_*` (R). Defer priced-W and composition to a later tier.
3. **The credential class** (API key vs OAuth 2.1) and how it maps to a `user_id` + scopes — §03.
4. **Per-key rate-limit + spend cap + audit** — none exist at the edge today.
5. **The async-completion channel** for headless agents (poll vs webhook).
