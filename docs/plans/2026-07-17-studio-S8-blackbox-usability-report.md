# S8 Translation — blackbox-user usability report (real app, author role)

> A web-novel author, unaided, driven through the LIVE Studio translation surface (vite :5199 →
> gateway :3123 → docker stack) on 2026-07-17. Screenshots in `frontend/s8-journey/`. The question:
> **is this actually usable, or does it just render?** Verdict below each step.

## The journey

| Step | What the author sees | Usable? |
|---|---|---|
| **1 · open Translation** (`1-matrix-fresh-book.png`) | "Translation Matrix · 3 chapters" with a **Translate…** CTA top-right AND an empty-state "No translations yet → **Start Translation**". | ✅ Two discoverable entry points; the CTA outlives the empty state (the original T1 bug: no button at all). |
| **2 · open the modal** (`2-translate-modal.png`) | "Translate Chapters" — a **Target Language** picker, a **Model** picker (Gemma-4 26B, pre-seeded), a summary "3 chapters · Untranslated: 3" with a primary **"Translate 3 chapters that need it"**, quick-select chips, and every chapter with an *Untranslated* badge. | ✅ Pickers render immediately (T5: not gated on a chapter-list fetch); smart default selection; scope is obvious. |
| **3 · pick a language** (`3-language-picked-vi.png`) | The picker offers exactly the closed registry (vi selected). | ✅ D13: if you can't pick it you can't submit it — no free-text foot-gun. |
| **4 · see the scope** (`4-modal-with-scope.png`) | The chapter checklist + model info are all visible before committing. | ✅ The author knows exactly what will run and on which model. |
| **5 · a book with a translation** (`5-matrix-with-coverage.png`) | Every chapter is a **row** with a checkbox and a **Tiếng Việt (vi)** column showing `—` for untranslated; a footnote "**1 translation(s) belong to chapters that are no longer active**"; "Showing 3 of 3"; "1 more languages hidden · show filter". | ✅ T2/D3 (untranslated chapters visible + selectable), D5 (orphan surfaced not dropped), the language column uses the endonym. |
| **6 · the service is down** (`6-degraded-typed-error.png`) | The header + CTA stay; the matrix region shows "**Couldn't load translations — the translation service may be unavailable. Try again.**" + a **Retry** button. | ✅ T4/D9: a clear, localized, actionable message — never the raw "Error occurred while trying to proxy…" string or a blank/broken panel. |

## Cross-service behaviour (API-level, live)

- Set target `Vietnamese` → **400 invalid_target_language**; `VI` → normalized **`vi`**; `zh_CN` → **`zh-CN`** (C1/D13, the write-side that closed the free-text hole).
- `docker stop translation-service` → gateway **HTTP 500 in 5s** (no hang) → the FE renders the retryable typed-error above.

## Verdict

**The tool is genuinely operable, not a skeleton.** Every read has its write, every list row is a
selectable target, every action leads somewhere, and every failure surfaces a clear reason + a way
forward. The original spec-29 complaint — *"the matrix has no button to translate · pressing translate
does nothing · no modal to pick language"* — is fully resolved, and the *"errors swallowed into
states that look like nothing happened"* class is gone (typed error + Retry everywhere).

**One minor UX note (already fixed this session):** un-ticking every language in the filter used to
show "No translations yet"; it now shows a distinct "All languages are filtered out" + reset (LOW-1).

**Automated coverage:** `frontend/tests/e2e/specs/studio-translation-s8.spec.ts` (5 specs) + the
journey spec run green on the live stack, so this walkthrough is repeatable, not a one-off.
