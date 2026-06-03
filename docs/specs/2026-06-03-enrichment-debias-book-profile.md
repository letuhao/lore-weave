# Bug + fix design — De-bias enrichment: per-book worldview profile · 2026-06-03

> **Severity: HIGH production bug** (the platform is multi-book). Surfaced by the Compose
> benchmark ([compose-review.md](2026-06-03-enrichment-compose-review.md) F2), but it is a
> **pre-existing defect in current enrichment** — not specific to Compose. **Foundational fix:
> do this BEFORE the Compose build** (Compose's "free-form / any subject" premise depends on it).
> Status: DESIGN. Branch `lore-enrichment/foundation`.

## 1. The bug — the generation/verify layer is hardcoded to ONE book's universe
The enrichment generation + verification is pinned to 《封神演义》/商周, Chinese, and "location",
with no per-book parameterization and no book-metadata source. **Any non-Fengshen book already gets
wrong output** (its entities are described as Shang-Zhou mythic-xianxia, in Chinese, with a
"no modern tech / foreign religion / later dynasty" era rule applied regardless of genre).

**Four axes of hardcoded bias (evidence):**
| Axis | Hardcoded to | Evidence |
|---|---|---|
| **Worldview/setting** | 《封神演义》 | `app/generation/generate.py:85` "忠于《封神演义》原著"; `app/strategies/fabrication.py:202` "深谙《封神演义》世界观"; `recook.py` "商周·封神演义" |
| **Era / anachronism policy** | 商周 (reject modern tech, foreign faiths, later dynasties) | `fabrication.py:210` "须符合商周·封神纪元…不得出现后世朝代、近现代器物、外来宗教"; `app/verify/canon_verify.py ANACHRONISM_MARKERS` (LE-058 — a 封神-specific denylist applied globally) |
| **Output language** | Chinese | `generate.py:89` / `fabrication.py` "内容必须为中文" |
| **Entity-kind label** | "地点" (location) | `generate.py:86` "为地点「…」补全"; only `EntityKind.LOCATION` is modeled |

**No source of per-book worldview exists** — lore-enrichment fetches zero book metadata (grep: only
glossary entities + KG, never a book genre/synopsis/setting/language). So today the bias is unfixable
without new plumbing. It was acceptable as a single-book *demo*; it is a bug for a multi-book product.

## 2. The fix — a per-book "enrichment profile" + parameterized prompts/verify

### 2.1 `enrichment_book_profile` (new table, keyed by book_id)
| field | type | meaning |
|---|---|---|
| `book_id` | UUID PK | the book |
| `worldview` | TEXT | free-text setting, e.g. "Shang-Zhou mythic xianxia (封神演义)" \| "near-future cyberpunk Saigon" \| "Victorian gothic horror" |
| `language` | TEXT | output language code/name (`zh`/`en`/`vi`/… or `auto` = the book's language) |
| `era_policy` | TEXT NULL | optional era/anachronism constraint as free text ("no post-商周 tech, no foreign religions"); **NULL = no era constraint** (anachronism check OFF/advisory) |
| `voice` | TEXT NULL | optional tone/voice hint ("classical-vernacular Chinese, 原著 tone") |
| `updated_at` | timestamptz | |

- **Bootstrapping (no manual setup burden):** an **AI-suggest** action proposes `worldview`/`language`/
  `era_policy`/`voice` from the book's synopsis + a few sample chapters (one LLM call, author-editable).
  The author can override anytime in a new Enrichment → **Settings** panel.
- **Default (NO regression):** seed the existing **Fengshen demo book's** profile with the current
  hardcoded values (`worldview=封神演义`, `language=zh`, `era_policy=商周-no-modern`, `voice=原著`).
  Books with no profile → a **neutral default**: generic worldbuilder, `language=auto`, `era_policy=NULL`
  (anachronism off), kind label from the entity-kind. So the demo + existing tests behave identically.

### 2.2 Profile resolution + threading
- New `app/db/book_profile.py`: `get_book_profile(pool, book_id) -> BookProfile` (returns the neutral
  default when unset). `BookProfile` is a small frozen model.
- Thread it to the prompt builders + the verifier. Cleanest: resolve in `build_live_runner` (it already
  has `book_id`) and carry on `StrategyContext.profile` (additive, frozen-model field) → the strategies
  pass it to their prompt builders + the `CanonVerifier`. The worker (`resume_consumer`) already has
  `book_id` on the request → no new wire field.

### 2.3 Parameterize the prompt builders (remove the hardcoded constants)
`generate.py` / `fabrication.py` / `recook.py` builders take `(profile, kind_label, …)`:
- "你是一位忠于《封神演义》原著的…" → "You are a worldbuilding assistant faithful to this work's
  setting: **{profile.worldview}**. Write in **{profile.language}**, matching its voice
  (**{profile.voice}**)." (Render the instruction itself in the target language or keep it
  meta-instructional; keep JSON-only + grounding rules unchanged.)
- "为地点「{name}」" → "for the **{kind_label}** «{name}»".
- fabrication's era clause → "**{profile.era_policy}**" (omit the clause entirely when `era_policy` is NULL).
- recook's "商周·封神" re-contextualisation target → `{profile.worldview}` + `{profile.era_policy}`.

### 2.4 Book-driven anachronism (C12)
`CanonVerifier`'s anachronism check becomes **profile-driven**: when `era_policy` is set, derive/markers
from it (the current 封神 `ANACHRONISM_MARKERS` become the *Fengshen profile's* policy, not a global
constant); when `era_policy` is NULL → the anachronism check is **OFF** (or advisory only — never
auto-rejects a sci-fi/modern book for "modern tech"). Contradiction + injection + regurgitation checks
are unaffected (they're not era-specific).

## 3. Affected files (BE + FE)
- **BE:** `app/generation/generate.py`, `app/strategies/fabrication.py`, `app/strategies/recook.py`
  (prompt builders → `profile`/`kind_label`), `app/verify/canon_verify.py` (anachronism → profile),
  `app/strategies/base.py` (`StrategyContext += profile`), `app/jobs/assembly.py` (resolve + thread),
  `app/worker/resume_consumer.py` (no new field — resolve from `book_id`), **new** `app/db/book_profile.py`
  + migration (`enrichment_book_profile`) + a `GET/PUT /v1/lore-enrichment/books/{id}/profile` +
  `POST …/profile/suggest` (AI) endpoint + openapi.
- **FE:** new Enrichment → **Settings** panel (worldview/language/era/voice + "Suggest from book" button),
  `api.ts`/`types.ts`/hooks/i18n.
- **Migrate the existing demo:** seed the Fengshen book's profile = current constants.

## 4. Slices
- **Slice 0a (the bug fix, BE):** profile table + reader + neutral default + Fengshen-default seed +
  parameterize the 3 prompt builders + profile-driven anachronism + thread via StrategyContext +
  endpoints/contract. **Acceptance:** with the Fengshen profile, output is byte-comparable to today
  (no regression — existing 562+ tests stay green); with a neutral/other profile, the prompt contains
  NO 封神/商周/地点/中文 hardcode and the anachronism check is off. New tests pin both.
- **Slice 0b (FE):** the Settings panel + AI-suggest + i18n + vitest.
- **Then** the Compose slices (D→C→F→B) build on the now-book-aware prompts.

## 5. Why this is the right fix (not a workaround)
- It removes the bias at the SOURCE (one profile, all techniques + verify read it) rather than
  per-mode patches.
- It fixes **existing** enrichment for non-Fengshen books, not just Compose.
- It is **regression-safe** (default = today's Fengshen behavior).
- It unblocks Compose's freeform/any-subject premise (and the multi-language, multi-genre product goal).
- It is **not legal/era advice** — the era policy is an authoring aid, not a correctness guarantee.

## 6. Open question
- **Profile granularity:** per-**book** (recommended — worldview is a book property) vs per-project vs
  per-job override? Recommend per-book + an optional per-job override field on `/compose` for one-off
  experiments. Confirm.
