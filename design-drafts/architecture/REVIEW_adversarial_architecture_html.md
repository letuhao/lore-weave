# Adversarial review — architecture HTML pages (pre-show)

**Artifacts reviewed**

- [agentic-ai-book-to-world-overview.html](./agentic-ai-book-to-world-overview.html) — non-specialist concept page  
- [loreweave-technical-architecture-and-pipelines.html](./loreweave-technical-architecture-and-pipelines.html) — technical / engineer page  

**Assumed audience for “show”**

- Exec / partner / investor skim → concept page only  
- Staff+ engineers / architects → technical page + footnotes in Q&A  

**Ground-truth sources used**

- Root [README.md](../README.md) (roadmap Phase 1–6+, services table)  
- [CLAUDE.md](../CLAUDE.md) (gateway + provider invariants)  
- [infra/docker-compose.yml](../infra/docker-compose.yml) (profiles, container set)  
- [services/video-gen-service/app/routers/generate.py](../services/video-gen-service/app/routers/generate.py) + [services/video-gen-service/README.md](../services/video-gen-service/README.md)  

**Labeling key**

- **Verified** — matches repo or explicit planning doc  
- **Simplified truth** — directionally correct; omits edge cases  
- **Forward-looking** — strategy / sibling repo; not fully reflected in monorepo wiring  
- **Risk of misread** — honest reader could conclude something false  

---

## Executive summary — residual risks after copy fixes

1. **Video / media path still needs verbal precision (F9 partial):** The technical page now states transition mode, but code in this repo still includes provider-direct generation paths (`/v1/video/generations`) alongside the ComfyUI target story. Residual risk: technical reviewers may ask whether ComfyUI is already the default runtime.  
2. **Phase framing can still be skimmed as “mostly shipped” (F10):** The Phase 1–5 legend remains broad; readers who skim may underweight that root roadmap still shows Phase 2 in progress and Phases 3–5 planned for deeper scope.  
3. **BYOK line remains intentionally simplified (F4):** Good for product messaging, but security-minded audiences may still ask for internal service-token and tenancy boundary clarification.  
4. **MCP + HITL bridge is still a commitment-sensitive area (F11):** Wording is cautious, but listeners can still interpret MCP as immediate production integration unless the talk track reinforces “design in progress / wire format not locked.”  
5. **Link usability depends on how you present the files (F13):** Relative markdown links work in-repo; if shown outside repo context, documentation links may not resolve and can weaken confidence in live demos.

---

## Consolidated findings table

| # | Finding | Page / section | Severity | Persona | Counter-defense | Recommendation |
|---|---------|----------------|----------|---------|-----------------|----------------|
| F1 | Title “From your book to a **living world**” can scan as shipped game product before reading body | Concept — hero | Med | Hostile reader | Subtitle + footer + dashed Future stage clarify vision vs product | Optional spoken caveat: “living world = design north star, not a mode in the app today.” |
| F2 | “Same manuscript data powers … structured lore” implies extraction always on | Concept — hero + Lore layer | Low | Hostile reader | README/plan: extraction opt-in per project | If challenged verbally: cite opt-in; optional one adjective in HTML later (“when enabled”). |
| F3 | “Reliable background handoff” implies durability guarantees not drawn on page | Concept — Handoff | Low | SRE | Outbox/queues exist in architecture; page is not an SLA doc | No change, or add “best-effort / at-least-once” in spoken Q&A only. |
| F4 | “Your keys…” oversimplifies worker + internal extraction paths | Concept — BYOK | Med | Security / engineer | End-user BYOK for interactive AI is real invariant; internal calls use service tokens + registry | **Tweak copy** later: “for interactive AI you bring keys” OR accept as simplification. |
| F5 | “External traffic enters **only** through NestJS gateway” without “browser” qualifier | Technical — §A intro | Med | Staff+ engineer | CLAUDE gateway invariant is the intended claim | **Addressed:** copy updated to “From browsers and other external clients…”. |
| F6 | Linear arrows in pipeline strips imply strict ordering; some flows parallel / retry | Technical — §B | Low | SRE | Page already says “not a frozen sequence diagram” | Verbal only; no change unless you want “~” notation. |
| F7 | `local-image-generator-service` appears as a peer box in pipe-flow; **not** a default `docker-compose` service name | Technical — ComfyUI strip | **High** | Staff+ engineer | Target topology + sibling repo is intentional documentation | **Addressed:** sibling-repo / not-in-default-compose footnote added in HTML. |
| F8 | “Nearly complete” for ComfyUI stack is **not** verifiable from this monorepo | Technical — Python note + strip | Med | Staff+ engineer | Product owner assertion about sibling repo | **Addressed:** wording softened to “integration in progress”. |
| F9 | Monorepo `video-gen-service` code path today is **OpenAI-compatible video API** + MinIO, not ComfyUI | Technical — ComfyUI narrative | **High** | Staff+ engineer | README + HTML document **direction**; integration is in flight | **Partially addressed:** HTML now states transition mode and notes provider-direct code paths may still exist. |
| F10 | Phase 1–5 row lists broad capabilities; README Phase 2 still *In Progress*, 3–5 *Planned* | Technical — phase table | Med | Hostile reader / engineer | “Shipped or in active development” spans partial + mature modules | Add one clause: “Roadmap phases 3–5 still planned for deeper features” in spoken intro. |
| F11 | MCP in bridge section could be read as “MCP already in prod” | Technical — §C | Med | Security | Text says “integration surface” and “not a fixed schema” | In Q&A: MCP = future tool contract; auth scope TBD. |
| F12 | Phase 6+ spatial bullets could excite scope creep if audience skips “Design track” label | Technical — §D | Low | Extension architect | Every card tagged Design track | No change; reader discipline. |
| F13 | Markdown links from `file://` opened HTML may not render for non-devs | Both — footer links | Low | Hostile reader | Repo-relative links are fine when hosted on intranet | Prefer hosting HTML on internal static site with same path layout. |

**Steel-man:** If the team disputes **High** items: F7/F9 are the strongest “credibility” issues for a **technical** audience; F1 is the strongest for a **hype-sensitive** audience. Address F9 with one honest sentence in slide talk even if HTML is not edited in this pass.

---

## Persona reviews (max 8 bullets each, both HTML files)

### 1 — Hostile non-technical reader

1. Hero “living world” + game-like pipeline ending can skim as “LoreWeave is already a game platform” until the dashed Future box is read (F1).  
2. “Structured lore library” may imply every user has a full knowledge graph working out of the box (F2).  
3. Agentic bullets are strong product claims; a cynic may ask “whose rules?” without naming tenant admin (acceptable for concept page).  
4. BYOK line builds trust; it does not mention data residency or encryption at rest (out of scope for this artifact — OK).  
5. Footer link to raw `.md` may confuse non-GitHub users (F13).  
6. Technical page phase table uses “Shipped” adjacent to long feature list — skim risk conflates **code exists** with **all roadmap done** (F10).  
7. ComfyUI model list reads like a marketing checklist; impressive but invites “prove it” (F8).  
8. Overall: concept page is **reasonably honest** if read for 60+ seconds; **30-second skim** is the danger.

**Counter-defense (architecture):** Two-tier story is correct: **novel platform today**, **Living Worlds design track tomorrow**; visuals already separate Today vs Future.

---

### 2 — Staff+ skeptical engineer

1. Gateway “only” wording needs “external client” qualifier (F5).  
2. `local-image-generator-service` is not in-tree; diagram as equal node suggests it ships with clone (F7).  
3. Code inspection: `video-gen-service` implements remote **HTTP video generation API**, not ComfyUI node graph in this repo (F9) — **largest factual tension**.  
4. “worker-infra → streams consumers read” compresses Redis Streams / RabbitMQ / multiple consumers — acceptable simplification (F6).  
5. `translation-service` as Python matches README; good (verified).  
6. Neo4j “optional profile” matches compose — verified.  
7. Pass-2 “style” extraction named on knowledge strip — simplified but aligned with planning vocabulary.  
8. Phase 6+ cards match extension planning directionally; no false claim of DB tables.

**Counter-defense:** Monorepo is **contract-first BFF + services**; sibling repo for GPU-heavy media is a **deliberate split**; HTML describes **target** integration. **Recommendation:** tighten language on F9/F7 in a follow-up edit pass.

---

### 3 — SRE / operator

1. Arrows do not show retries, DLQs, idempotency keys — expected for one-pager (F6).  
2. “Reliable background handoff” on concept page could be heard as “no message loss” — not promised (F3).  
3. Neo4j optional + memory limits in real compose not shown — OK for altitude.  
4. `worker-ai` has `restart: unless-stopped` in compose; failure modes not on HTML — OK.  
5. Video strip → MinIO omits disk / quota / antivirus scanning — out of scope.  
6. RabbitMQ as single broker point — true dependency; not unique to diagram.  
7. Health-gated `depends_on` chains in compose are stricter than arrows imply — simplification.  
8. No mention of backup / DR — correct omission for marketing-style HTML.

**Counter-defense:** Footer on technical page already disclaims “not a frozen sequence diagram”; for exec audience, SRE depth belongs in runbooks, not these drafts.

---

### 4 — Security / multi-tenant mindset

1. BYOK line on concept page omits internal service token pattern — risk of “everything is user OAuth” misread (F4).  
2. MCP bridge bullet increases **supply chain / tool injection** surface in listeners’ minds — must be verbally bounded to **trusted tools + auth** (F11).  
3. HITL is a governance win; it also implies **insider threat** and audit trails not shown — acceptable omission.  
4. Gateway-only external traffic is the right **trust zone** story for pen-test narrative — strengthen with F5 qualifier.  
5. No claim of “zero trust implemented” — good.  
6. Links to planning docs do not expose secrets — good.  
7. ComfyUI sibling repo: clarify network segmentation (VPC, mTLS) when integrated — not on page yet.  
8. Agentic “respects your rules” — good hook for quota / RBAC story in Q&A.

**Counter-defense:** Architecture’s real invariant is **no browser → provider** bypass and **registry-mediated** AI — still valid; internal east-west trust is a **second-layer** discussion.

---

### 5 — Extension / game architect (Living Worlds)

1. Phase 6+ README lists open problems (retrieval, cost, IP); HTML table cites them — **aligned** with `LLM_MMO_RPG/README.md`.  
2. Spatial layering bullets are **aspirational** vocabulary; not tied to locked DF IDs on page — OK for breadth slide.  
3. Event sourcing card correctly says **no shipped game event store** — strong honesty.  
4. Memory card references catalog open issues — directionally fair.  
5. Bridge section “MCP-shaped” avoids over-claiming MCP product — good.  
6. Risk: audience maps Phase 6+ cards 1:1 to **next quarter** engineering — mitigate with “catalog > 300 designed features; V1 slice is solo RP” from `catalog/99_scope_and_refs.md` in talk track.  
7. Concept page “Living Worlds” copy matches extension README’s “design track, gated” language — consistent.  
8. Game asset / ComfyUI tie-in bridges Phase 1–5 media to Phase 6+ **vision** — powerful if F9 is verbally honest.

**Counter-defense:** Extension dossier is explicitly gated; HTML does not claim V1 MMO shipping — it claims **problem domains** for future services.

---

## Ready-to-show checklist

Use this before sharing links or projecting pages.

- [ ] **Spoken 15-second framing** for execs: “Novel + AI platform today; Living Worlds is a documented extension, not a shipped game.”  
- [ ] **Spoken 15-second framing** for engineers: “External users hit BFF only; internal east-west exists; diagrams are orientation not sequence diagrams.”  
- [ ] **Video / ComfyUI one-liner prepared** to address F9: either “target topology is sibling ComfyUI repo; current gateway may still proxy Sora-style APIs until cutover” OR confirm code has already been updated since this review.  
- [ ] **Decide** whether `local-image-generator-service` is public; if yes, add URL in memo appendix next revision.  
- [ ] **Hosting**: if not opening from repo, mirror `docs/` paths so footer links resolve.  
- [x] **Optional HTML micro-edit** (post-review): qualify gateway sentence (F5); footnote sibling service not in default compose (F7); soften “nearly complete” (F8).  
- [ ] **Assign owner** for follow-up copy pass if any Med/High rows are accepted as pre-show blockers.

---

## Appendix — claim classification (quick reference)

| Claim | Verdict |
|-------|---------|
| Single BFF for external traffic | Verified (CLAUDE + gateway code path) |
| Go vs Python service split | Verified (README table) |
| Neo4j optional by profile | Verified (docker-compose) |
| Knowledge extraction opt-in / cost-gated | Verified (planning docs referenced in HTML) |
| Phase 6+ = design track, gated | Verified (`LLM_MMO_RPG/README.md`) |
| ComfyUI + model list in sibling repo | Forward-looking / README assertion; **verify sibling** |
| `video-gen-service` → ComfyUI in **this** repo runtime | **Risk of misread** until integration matches code (F9) |
| Linear pipeline arrows = exact orchestration | Simplified truth |

---

*Review produced as a pre-show adversarial pass; does not modify the HTML sources. Update this memo if the video-gen ↔ ComfyUI integration lands or if roadmap status changes materially.*
