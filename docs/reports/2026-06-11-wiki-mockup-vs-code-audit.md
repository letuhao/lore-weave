# Audit Report — Wiki LLM-Building: mockup (draft HTML) vs actual source code

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` (HEAD `c0601953`)
**Question:** has the wiki feature's source code *actually* been completed vs. the design?
**Inputs:** the 5-screen draft mockup [`docs/specs/2026-06-08-wiki-llm-building-mockup.html`](../specs/2026-06-08-wiki-llm-building-mockup.html) + spec [`2026-06-08-wiki-llm-building.md`](../specs/2026-06-08-wiki-llm-building.md), audited against the live FE (`frontend/src/`) and BE (`knowledge-service`, `glossary-service`).
**Method:** desk audit with file:line evidence (two parallel code sweeps + manual verification of the key discrepancy). **NOT** a live click-through — see §6.

---

## 1. Verdict (TL;DR)

| Layer | Status | One-line |
|-------|--------|----------|
| **Backend (M0–M8 + Phase-2)** | ✅ **Genuinely complete** | Every pipeline + change-control + M8-flywheel capability verified at file:line. Remaining deltas are **tracked deferrals**, not holes. |
| **Frontend** | 🟡 **Functionally complete, visually/UX simplified** | The working path is all there (citations, generate dialog, job banner, staleness feed, suggestion review). But several mockup screens are rendered as **simpler components** — the gaps are *presentation richness*, not broken capability. Est. ~65–70% of the mockup's UI detail. |
| **One real spec↔code mismatch** | ⚠️ | The mockup shows a **per-step model** (prose model + separate verify model). **Neither FE nor BE supports it** — the whole pipeline uses one `model_ref`. This was never built in either layer (not a regression; a never-implemented design idea). |

**Answer to "đã thực sự hoàn thành chưa":** The **backend is done** (ship-ready, only tracked deferrals). The **frontend delivers the full functional flow but not the full mockup UI** — the job-progress detail (screen 3) and the suggestion-diff / change-feed-richness (screens 4–5) are the meaningful UX gaps. Nothing is *broken*; the difference is fidelity to the draft, and those richer views were never built.

---

## 2. Per-screen matrix

Legend: ✅ present · 🟡 partial/simplified · ❌ missing · 🔵 design-intentional divergence

### Screen ① — Reader (AI article)
| Mockup element | Status | Evidence |
|---|---|---|
| Article-list sidebar grouped by kind | ✅ | `WikiTab.tsx:130-251` (`WikiSidebar`), group memo `:119-127` |
| Kind-filter chips + search box | ✅ | `WikiTab.tsx:174-199` (chips), `:162-170` (search) |
| "N bài" count | 🟡 | `WikiTab.tsx:159-161` — total only, **no "M do AI sinh" split** |
| AI badge "AI tạo · chưa kiểm chứng" | ✅ | `WikiGenBadge.tsx:12-43`; used `WikiTab.tsx:233,306` |
| Verify-flag warning + panel | ✅ | `VerifyFlagsPanel.tsx:12-66`; `WikiTab.tsx:343-346` (no separate "xem tất cả cờ" modal — flags shown inline) |
| Inline citation marks `[n]` + popover | ✅ | `CitationChip.tsx:25-102`, `InlineRenderer.tsx:9-16` (snippet + relevance% + jump-to-source) |
| **References section + jump link** | ✅ (**FE audit false-positive corrected**) | Baked into `body_json` by `mappers.py:104-108,136` (`## References` + bulletList, each `[n]` carries a `citation` mark) → rendered by ContentRenderer → each ref is a CitationChip w/ jump. **Only the mockup's `.relbar` relevance-bar styling is absent**; the function (list + jump + relevance-in-popover) is present. |
| "Tạo lại" (Regenerate) button | ✅ | `WikiTab.tsx:314-322` (opens dialog scoped to the entity) |
| Infobox (attribute panel) | ✅ | `WikiTab.tsx:27-55` (`WikiInfobox`), rendered `:347-353` |

### Screen ② — Generate dialog
| Mockup element | Status | Evidence |
|---|---|---|
| Mode toggle Mẫu/AI | 🔵 | `GenerateWikiDialog.tsx:155-182` — a **dropdown** (empty = deterministic, model = LLM) instead of a segmented toggle. Functionally equivalent. |
| Prose model picker | ✅ | `GenerateWikiDialog.tsx:155-182` (user chat models) |
| **Separate verify-model picker** | ❌ | Only one model field — **matches BE** (no per-step model anywhere). See §4. |
| Scope = kind chips | ✅ | `GenerateWikiDialog.tsx:185-212` (batch mode) |
| "Số bài / lần" limit | 🟡 | FE offers a **USD spend-cap** (`:214-231`), not a hard article count |
| "Ngôn ngữ sinh" picker | ❌ | No language field (BE derives language from BookProfile, so it's advisory-only in mockup) |
| Grounding status line | ❌ | No "Sách đã lập chỉ mục" indicator in the dialog |
| Cost estimate | 🟡 | `GenerateWikiDialog.tsx:235-247` (per-article rate / precise N×rate) — **no budget / monthly-used line** |

### Screen ③ — Job progress (the biggest gap)
| Mockup element | Status | Evidence |
|---|---|---|
| Progress bar + "X / Y entity" | ✅ | `WikiGenJobBanner.tsx:56-70` |
| **4-pass step indicator (Viết→cite→CanonVerifier→revise)** | ❌ | Banner is a status strip; no per-pass visualizer |
| **Per-entity result rows (created/skipped/warning/processing/queued)** | ❌ | No per-entity table — only aggregate progress + current name |
| Paused-on-budget card + Resume + Cancel | ✅ | `WikiGenJobBanner.tsx:75-105` (resume on paused; cancel pending\|paused) |

### Screen ④ — Suggestions / clobber-guard
| Mockup element | Status | Evidence |
|---|---|---|
| Pending suggestions list + Accept/Reject | ✅ (different location) | `WikiEditorPage.tsx:147-223` (`SuggestionPanel`) — in the **editor sidebar**, not the reader main area |
| **del/add diff visualization** | ❌ | `diff_json` exists on the type but is **not rendered** — only the reason text shows |
| AI-regen-as-suggestion vs community distinction | ❌ | Both render mixed, no visual differentiation |
| BE: list + review + AI-regen-envelope-unwrap | ✅ | `wiki_handler.go:1738-1843` (list), `:1847-2050` (review + unwrap + clobber-guard accept) |

### Screen ⑤ — Knowledge-updates feed
| Mockup element | Status | Evidence |
|---|---|---|
| "N bài outdated" badge | ✅ | `WikiTab.tsx:694-704` |
| "Quét lại fingerprint" rescan button | ❌ | No FE control (the sweep endpoint exists BE-side) |
| Deferred-ledger info banner | ❌ | Not rendered |
| **Batch action bar: severity breakdown + cost + dismiss-all** | 🟡 | `KnowledgeUpdatesPanel.tsx:138-151` — selected-count + single Regenerate only; **no severity counts, no cost line, no batch-dismiss** |
| Per-change rows grouped by reason | 🟡 | Grouped by `reason_code` (`:44-49`) but **no rich metadata / icon / "xem thay đổi" diff link** |
| Multi-select → batch regenerate | ✅ | `KnowledgeUpdatesPanel.tsx:42-70` → `WikiTab.tsx:751` |
| "Outdated" badge on sidebar/header | ✅ | `WikiTab.tsx:228-232,307-311` |

---

## 3. Backend completeness (M0–M8 + Phase-2) — ✅ verified

Every capability the screens depend on exists, at file:line:

- **M0** IR parser + TipTap mapper + citation mark — `parse.py:109-172`, `mappers.py:111-137`, `ir.py:76-106`
- **M2** context gather (glossary+KG+passages, cite-labels, injection-sanitize, hybrid retrieval, degrade) — `context.py:139-231`
- **M3** generate + rule-gate + 1× corrective retry — `generate.py:108-174`, `rulegate.py:48-79`
- **M4** CanonVerifier + `decide_auto_reject` (publish-block) + compose-cites + bounded keep-if-improved revise — `verify.py:170-203,113-147`, `revise.py:63-104`
- **M5** writeback + clobber-guard **allowlist** (overwrite only ai/system; human → suggestion) + source_usage + fingerprint — `wiki_writeback.go:123-198,226-257`, `fingerprint.py:39-78`
- **M6** orchestrator (per-entity loop, budget-pause-before-spend, skip-done resume, never-raise, per-book lock, flag-gated consumer + startup-drain) — `orchestrator.py:186-255`, `wiki_gen_processor.py:107-135`
- **M7b** job poll/resume/cancel + glossary proxy + `generation_status`/`provenance` on reads — `internal_wiki.py:333-392`, `wiki_jobs.go:21-114`, `wiki_handler.go:19-63`
- **Phase-2** staleness ledger + 5-event consumer + recipe-drift + KG-drift sweeps + feed/dismiss + resolve-on-regen + resolve-on-accept — `staleness_consumer.go:37-200`, `wiki_staleness.go:29-249`, `wiki_writeback.go:185-197`, `wiki_handler.go:1996-2016`
- **M8** learning judge (on-demand + auto-sampled, gated) + gold-pairs few-shot — `orchestrator.py:119-183`, `wiki_gold_pairs.go:72-146`

**Tracked BE deferrals (not gaps):** running-job cancel (`D-WIKI-M7B-RUNNING-CANCEL`), precise per-job cost (`D-WIKI-M6-PRECISE-COST`), consumer-group/DLQ (`D-WIKI-M6-CONSUMER-GROUP`), gen-limit surface (`D-WIKI-M7B-GEN-LIMIT`).

---

## 4. The one real spec↔code mismatch — per-step verify model

The mockup (screen ②) shows **two** model pickers: "Mô hình văn phong (prose)" + "Mô hình kiểm chứng (verify)". **This is not implemented in either layer:**
- BE job row carries only `model_source` + `model_ref` (`wiki_gen_jobs.py:43-57`); `writeback.py:86` has a `step_models` param but the orchestrator always calls it with the default (empty).
- FE dialog has a single model select.

So generate + verify always use the **same** model. This is a **never-built design idea**, not a regression. If wanted, it needs: a `verify_model_ref`/`_source` on the job + thread into `verify`/`revise` + a second FE picker. Recommend a deferred row `D-WIKI-PER-STEP-MODEL` rather than silently dropping it from the design.

---

## 5. Gaps ranked (what "finishing" the FE to the mockup would mean)

| # | Gap | Screen | Type | Effort |
|---|-----|--------|------|--------|
| 1 | Job-progress detail: 4-pass step indicator + per-entity result rows | ③ | UX richness (real) | M — needs BE to expose per-entity outcomes on the job poll |
| 2 | Suggestion **diff** rendering (del/add) + AI-vs-community distinction | ④ | UX richness | S–M (BE `diff_json` already there) |
| 3 | Change-feed richness: severity-breakdown bar + batch cost-estimate + batch-dismiss + per-change metadata/diff-link | ⑤ | UX richness | M |
| 4 | Per-step verify-model (FE picker + BE schema/threading) | ② | Feature never built | M (cross-service) |
| 5 | Rescan-fingerprint button + deferred-ledger info banner | ⑤ | Polish | S |
| 6 | Generate dialog: language picker, grounding-status line, budget/usage on cost | ② | Polish | S |
| 7 | Sidebar "M do AI sinh" count; mode segmented-toggle (vs dropdown) | ①② | Cosmetic | XS |

None of these block the **functional** flow (generate → review → publish → change-control all work end-to-end, per the BE live-smokes already recorded). They are the difference between "works" and "matches the polished draft".

---

## 6. Confidence + what this audit did NOT do

- Evidence is **file:line desk-level**; the BE was additionally cross-checked manually on the one high-stakes discrepancy (references — corrected). The FE "missing" items in §2 are code-presence reads, not click-throughs.
- **Not validated here:** a live browser pass of all 5 screens (the deferred `D-WIKI-*-LIVE-SMOKE` rows). The BE pipeline E2E + M7b lifecycle were already live-proven (handoff: 3 Dracula articles, provenance/citations/clobber-guard verified). The FE gaps above are the natural next live-smoke targets.
- The mockup is explicitly a **non-functional UX draft** ("bản phác thảo HTML phi chức năng") — it is the design ceiling, not a contract; some divergences (dropdown vs toggle, language auto-from-profile) are reasonable simplifications.

---

## 7. Recommendation

1. **Ship the backend** — it's complete; the deferrals are tracked. A PR `wiki/phase2-change-control → main` is justified on the BE alone.
2. **Decide FE scope explicitly** — the mockup is richer than the build. Either (a) accept the simplified FE as the v1 (functional, ~65–70% of mockup polish) and log the §5 gaps as a "wiki FE polish" deferred batch, or (b) schedule a follow-up `/loom` for the high-value gaps (#1 job detail, #2 suggestion diff, #3 change-feed richness).
3. **Log `D-WIKI-PER-STEP-MODEL`** so the per-step-model design point (mockup ②) is tracked, not silently dropped.
