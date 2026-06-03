# Enrichment — Free-form input modes (analysis + draft) · 2026-06-03

> **Goal:** let the author start enrichment *the way they want* — not only "fill the
> dimensions of a detected gap". The user asked for 4 new input modes; this doc analyses
> them, unifies them into one **Compose** flow, and is the basis for the draft mockup
> [`enrichment-create.html`](enrichment-create.html). Aligns with the current GUI
> (the `Proposals · Gaps · Sources · Jobs` tab strip + the dark/amber design system).
>
> **Reality check first** (from the code — [`app/strategies/base.py`](../services/lore-enrichment-service/app/strategies/base.py),
> [`recook.py`](../services/lore-enrichment-service/app/strategies/recook.py),
> [`app/gaps/model.py`](../services/lore-enrichment-service/app/gaps/model.py)): today enrichment is
> **entity + fixed-dimension driven** — `run(gap_batch, context)` fills an existing
> LOCATION's 5 frozen dimensions (历史/地理/文化/features/inhabitants), grounded on registered
> corpora. No free-text intent, no inline context, no file upload, no web. These new modes are a real expansion.

## 1. The unifying insight — 5 input *sources*, one **Compose** flow

Every mode is the same spine with a different **input source**:

```
[ input source ] → (optional ② abstract to facts) → generate dimensions for a TARGET entity
                 → ③ regurgitation guard → C12 verify → H0 proposal (quarantined) → review → ④ promote
```

| # | Mode (vi · en) | Input source |
|---|---|---|
| **A** | **Lấp gap** · gap-fill *(existing)* | detected under-described entities |
| **B** | **Theo ý định** · free-text intent | a sentence describing what to enrich |
| **C** | **Dán ngữ cảnh** · paste context | reference text the author pastes |
| **D** | **Từ bản nháp** · from your draft | the author's own full description (expand/polish) |
| **F** | **Đính kèm tệp** · attach files | files the author uploads (extract → cook), self-asserted responsibility |
| ~~E~~ | ~~**Tìm web** · web search → cook~~ | **DROPPED** — copyright-indefensible, see §9 |

→ **Recommendation: build ONE `POST /v1/lore-enrichment/compose` endpoint** discriminated
by `input_source`, reusing the existing recook abstraction (②), generation chokepoint (C11),
regurgitation guard (③), and the C12 verifier. Each source only swaps the *grounding* and the
*prompt seed*; the H0 + verify + review + promote machinery is shared and already built.

## 2. Per-mode analysis

| Mode | What the user gives | Grounding / seed | Technique reuse | New backend | Entity model | © risk |
|---|---|---|---|---|---|---|
| **A gap-fill** | nothing (picks a gap) | registered corpora (retrieval) | as-is | none | existing LOCATION gap | low |
| **B intent** | one free-text line | LLM's own knowledge (+ optional corpus) | new "intent" prompt | **intent→target resolver** (LLM maps the line to an entity + dimensions, or proposes a new entity) | needs a target entity — resolve to existing, or **create new** | med (LLM may regurgitate training data → ③ applies) |
| **C context** | a pasted text blob | the pasted text (treated as an inline corpus) | recook's ②-abstract + generate | **inline-grounding seam** (feed text instead of retrieval) | target entity (existing or new by name+kind) | med-high → ② mandatory + ③ + user license assertion |
| **D draft** | a full description they wrote | the draft itself (seed to expand) | new "expand/refine" prompt | compose endpoint + expand prompt | target entity (existing or new) | low (their own writing) — ③ still on |
| **F files** | a list of files (.txt/.md/.pdf/.docx/.epub) | extracted text → ingest as corpus | recook ②-abstract + generate (**reuses the Sources ingest pipeline**) | **file upload + text extraction** (PDF/docx/epub→text) | target entity (existing or new) | med → user-sourced; **user self-asserts responsibility** (like C); ②③ |

**Effort (rough):** D ≈ C ≈ F < B. D/C/F reuse the most existing machinery (F = C's pipeline +
the Sources ingest + a file-extraction step); B needs an intent→entity resolver.
(Mode E — web search — was analysed and **dropped**; see §9.)

## 3. Unified API sketch (`POST /v1/lore-enrichment/compose`)

```jsonc
{
  "book_id": "uuid",
  "input_source": "gap | intent | context | draft | files",   // discriminator (web dropped, §9)
  "target": {                          // WHAT entity this enriches
    "mode": "existing | new",
    "canonical_name": "碧遊宮",         // existing gap OR a new entity name
    "entity_kind": "location",         // LOCATION modeled today; others = prerequisite §4
    "dimensions": ["history", "geography", "culture"]  // or "auto"
  },
  // exactly one of these, per input_source:
  "intent_text":  "Bổ sung lịch sử & văn hoá Triệt giáo ở Bích Du Cung",
  "context_text": "….author-pasted reference….",
  "draft_text":   "….author's own full description….",
  "files":        [ { "upload_id": "…", "filename": "notes.pdf", "license_asserted": "owned" } ],
                  // files are multipart-uploaded FIRST → text-extracted → ingested as a corpus,
                  // then grounded like context. The user self-asserts responsibility per file.
  // shared output config (same as auto-enrich today):
  "technique": "recook",               // P1/P2/P3
  "generation_model_ref": "uuid", "embedding_model_ref": "uuid",
  "max_spend_usd": 0.5, "top_k": 5,
  "user_license_assertion": "public_domain"   // for context (default-deny if absent)
}
```
→ Returns `202` + a `job_id`, exactly like `auto-enrich` (async via the worker). The result is
the **same `enrichment_proposal`** (origin=enrichment, conf<1.0, quarantined) → flows into the
existing Proposals/review/promote surface unchanged.

## 4. Prerequisite — entity-kind beyond LOCATION

Modes B/C/D/F let the author enrich a *subject* that may not be a modeled LOCATION.
`app/gaps/model.py` only defines `LOCATION` dimensions (CHARACTER/ITEM/FACTION are reserved,
not built). So:
- **Short term:** restrict the new modes to `entity_kind = location` (consistent with today),
  OR add a **"freeform"** target with a single free dimension (`description`) so any subject can
  be enriched without a frozen table.
- **Full:** define dimension tables for CHARACTER / ITEM / FACTION (mirrors `LOCATION_DIMENSIONS`).
  This is the bigger unlock and is independent of the input-mode work.

## 5. Copyright-safety mapping (the ①②③④ layers, per mode)

| Layer | A | B | C | D | F |
|---|---|---|---|---|---|
| **① input license default-deny** | corpus | n/a | **assert** | own | **assert per file** |
| **② abstract → neutral facts** | (recook) | optional | **yes** | no (it's their idea) | **yes** |
| **③ output regurgitation guard** | yes | **yes** (training-data leakage) | **yes** | yes | **yes** |
| **④ human promote gate + H0** | yes | yes | yes | yes | yes |

- **B/C/D/F** are user-driven → the author asserts they hold the rights; ②③ still protect against
  reproducing protected expression (incl. the model's own training data for B). The decisive
  point: the **user** performs the sourcing act and bears primary responsibility — the platform is
  a transformation *tool* (the standard, defensible posture). **F (attach files)** sits in exactly
  this posture: the user uploads their own files and self-asserts responsibility — same as C, just
  files instead of pasted text (this is why F is safe where the dropped web mode E is not).

## 6. GUI placement — a new **"Tạo / Create"** tab (aligns with current layout)

The current tab strip is `Proposals · Gaps · Sources · Jobs`. Add a 5th, leading tab **"Tạo"**
(Create / Compose) — the unified trigger surface. It does NOT replace anything:
- **Gaps** stays the analytical "what's under-described" list; its per-row **enrich →** (LE-064,
  just shipped) deep-links into Create › mode A prefilled.
- **Sources** stays the corpus manager; Create › mode C can optionally "save to a corpus" from here.
- **Create** = one composer: **Step 1** input-mode selector (5 cards) → **Step 2** the mode's
  input form → **Step 3** shared target + technique + models + cost-cap + the ①②③④ safety strip
  → run (async, same `202`/job/proposal path).

Reuses the existing design system verbatim: dark/amber tokens, Lora serif names, JetBrains mono
for ids/cost, the `rounded-lg border bg-card` cards, the technique `<select>`, the cost-cap input,
the H0 chip, and the eval-gate warning — so it reads as the same feature, just a richer entry point.

## 7. Suggested phasing (by risk/effort, lowest first)

1. **D — from your draft** (lowest risk, highest "I want to write it myself" value) + the
   `/compose` endpoint skeleton + the Create tab shell.
2. **C — paste context** (reuses ②-abstract; add the inline-grounding seam + license assert).
3. **F — attach files** (reuses C's pipeline + the Sources ingest; the only new piece is file
   text-extraction — PDF/docx/epub/txt/md → text. User self-asserts responsibility per file).
4. **B — free-text intent** (add the intent→target resolver; decide existing-vs-new entity).

In parallel, the **entity-kind extension** (§4) unblocks enriching non-LOCATION subjects.
(Mode E is **not** on this list — dropped, §9.)

## 8. Decisions (LOCKED 2026-06-03 with PO)
- **Target for B/C/D/F:** **both** — pick an *existing* glossary entity OR **create a new entity**
  from the input (a "new" name + kind path in the target picker).
- **Entity-kind v1:** **`location` + a generic `freeform` target** (one free `description`
  dimension) so any subject can be enriched now. CHARACTER/ITEM/FACTION dimension tables are a
  separate, later unlock (§4).
- **D — expand semantics:** **user chooses** (radio) — "only add missing dimensions (keep my prose
  verbatim)" OR "allow rewrite + voice-sync". Both ship.
- **F — file handling:** accept **.txt / .md / .pdf / .docx / .epub**, **OCR ON** for scanned PDFs.
  User-sourced + user self-asserts responsibility per file (default-deny on a copyrighted
  assertion, same posture as C). Size/page cap = a sane default (e.g. 25 MB / 300 pages), tunable.
- **Build order:** D → C → F → B (§7), on a shared `POST /compose` (§3) + the new "Tạo" tab (§6).
- **D expand semantics:** keep the author's draft verbatim and only *add* missing dimensions, or
  let the model rewrite/polish their prose too?

## 9. Rejected — Mode E (web search → cook)

**Decision (2026-06-03): DROPPED.** The copyright-safety layers do **not** genuinely protect this
mode — they create a *false sense of security*. Kept here so the reasoning isn't re-litigated.

- **① (license) is the load-bearing layer and it is undeterminable for web content.** A user
  "asserting" a license they have no authority over (ticking *public_domain* on a copyrighted page)
  does not make it so, and does **not** shift liability away from the platform — because the
  **platform itself** is the actor that fetched, transformed, and now distributes the third-party
  material. ① for web = a checkbox, not a shield.
- **② mitigates but doesn't resolve.** Facts aren't copyrightable, but the fact/expression line is
  fuzzy and litigated, and **selection-and-arrangement / database rights** can be protected even
  when individual facts aren't. LLM abstraction is also imperfect.
- **③ is best-effort and misses the relevant case.** It catches verbatim n-gram overlap, but
  **translation + re-contextualisation into Chinese/封神 is exactly the "derivative work" it can't
  catch.** Plus server-side fetching risks ToS violations.
- **The decisive difference vs. C:** in C the **user** performs the sourcing act and asserts rights
  (platform = tool); in E the **platform** is the active participant sourcing the infringing
  material. "The user asked for it" doesn't cover the platform.

**Replacement:** mode **C (paste context)** — the user sources + pastes + asserts rights, with the
same ②③④ guards on the provided text. If a "web assist" is ever revisited, the **only** defensible
shape is *search-shows-links-only* (the platform never auto-fetches content into the pipeline; the
user reads, decides, and copy-pastes into C). Not legal advice — any release decision needs IP counsel.
