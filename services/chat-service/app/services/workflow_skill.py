"""MCP-fanout S-WORKFLOW (Wave 3) — the cross-service ORDERING fragment.

A small static instruction block appended to the universal skill on the agui
``/chat`` surface. The universal skill teaches *how* to act safely (tool_list/tool_load,
tiers, async "started not done", partial-failure honesty); this fragment teaches
*in what order* multi-service requests must run — the lazy-user chains like
"import this book, translate it, build the glossary, make the wiki" only work in
a fixed sequence, and a dependent step must wait for the prior async job to
finish. It also pins H4 scope honesty (no silent half-done bulk mutations).

Composes with ``UNIVERSAL_SKILL_PROMPT`` by concatenation (no overlap). Static +
cacheable.

2026-07-07 (Part B, spec §8b.6): the translate step used to teach the propose→confirm→
watch detail inline; trimmed to a one-clause pointer now that ``translation_skill.py``
owns that domain's tool-use detail — this fragment keeps owning cross-domain ORDERING
only (translate-after-chapters-exist), never duplicating what a domain skill teaches.
Also fixed two stale tool-name references found in the same pass (``chapter_publish``/
``chapter_save_draft`` — missing their ``book_`` prefix; the real names are
``book_chapter_publish``/``book_chapter_save_draft``).
"""

WORKFLOW_SKILL_PROMPT = """\
# Cross-service workflows (ordering)

Some requests span several services and only work in a REQUIRED order. Do each \
step only after the previous step's result is actually in — never fire the whole \
chain at once.

## Build a book end-to-end
1. **Books & chapters first** — create or locate the book and its chapters \
(`book_*`). Everything downstream operates on chapters that already exist.
2. **Translate** — start translation on those chapters. See the Translation skill for \
the propose→confirm→watch flow and the version/coverage tools; don't translate before \
the chapters/source text exist.
3. **Glossary / lore** — extract or build glossary entities AFTER the source/ \
translated text is in place. Running it first yields empty or wrong results.
4. **Wiki** — generate wiki articles LAST, from the settled glossary.

Jumping ahead (glossary before chapters, wiki before glossary) is the most common \
way to produce nonsense — keep the order.

## Publishing
Draft → publish: `book_chapter_save_draft` (auto) then `book_chapter_publish` \
(confirm). Publishing a chapter with no prose is rejected — write or translate it first.

## Async ordering (the big one)
A step that STARTS a job (translate, retranslate, media) is not done when the tool \
returns — it is QUEUED. Say "started" with the job id and call `ui_watch_job`. Do \
NOT begin a step that DEPENDS on that job's output (e.g. glossary extraction over \
the translated text) until the job has actually finished. If the user asks for the \
whole chain, start step 1, watch it, and continue only when it completes.

## Scope honesty (don't half-do)
Some bulk operations are intentionally NOT single tools — there is no "translate or \
rewrite every chapter's prose in one call." If a request needs a bulk mutation you \
have no tool for, say so plainly and offer the per-item path or the relevant page, \
rather than doing a few items and implying you did them all.

## Partial chains
In a multi-step chain, if a step fails, STOP — report which steps completed and \
which didn't, and don't proceed to the next step as if it succeeded or claim the \
chain finished.
"""
