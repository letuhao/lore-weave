# Ambient book-scope — the token/burden win (spec 2026-07-22 Q4)

- **Date:** 2026-07-22 · gemma-4-26b-a4b-qat · N=5 · real book-service /mcp · DB-verified
- **Harness:** `ambient_ab.py`

Two conditions, "create a part" on The Tidewright:
- **BASELINE** — the book UUID is in the prompt; `book_id` is `required`; NO `X-Book-Id`. The model must
  transcribe the 36-char UUID into the call.
- **AMBIENT** — the prompt says "the current book" (no UUID); `X-Book-Id` header set; `book_id` optional.

| Condition | pass | book_id emitted | mistranscribed | mean tok in | mean tok out |
|---|---|---|---|---|---|
| baseline | 5/5 | 5/5 | 0 | 666 | 173 |
| **ambient** | 5/5 | **0/5** | 0 | **501 (−25%)** | **94 (−46%)** |

**Result:** in ambient mode the model **never touches the book UUID** — the transcription burden is
*eliminated*, not repaired. Win = **−25% input / −46% output tokens** + the whole mistranscription error
class removed at the source.

**Honest caveat:** gemma-4 transcribed the single UUID correctly 5/5 in this clean single-call isolate, so
the win here shows as tokens + removed error-surface, NOT a pass-rate delta. The mistranscription *failures*
that motivated the original S02 repair (`_inject_context_ids`) appear in longer multi-turn sessions; this
isolate is too easy to trigger them. The mechanism removes the burden regardless of whether a given model
happens to survive it.

## Live plumbing proof (every hop)
- book-service resolves `X-Book-Id` when `book_id` omitted (read + create_part DB-verified, `scope_source=envelope`); cross-book write pre-confirm + `allow_cross_book`; external fail-closed.
- **ai-gateway forwards `X-Book-Id`** — `book_structure_read` via :8218, no `book_id` → resolved, `scope_source=envelope`.
- chat-service sets `X-Book-Id` from the session book (unit: `test_mcp_execute_tool.py`).
