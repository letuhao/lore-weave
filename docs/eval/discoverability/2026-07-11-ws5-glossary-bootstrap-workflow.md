# WS-5 — the `glossary-bootstrap` workflow rail flips S01 (0 → ~75%)

**Date:** 2026-07-11 · **model:** gemma-4-26b-a4b-qat · **scenario:** S01 "set up my world".
**What shipped:** the first authored System workflow + the steering that makes a mid-tier model use it.

## The result

S01 baseline (and re-test): **always ❌** — the agent proposed *entities* before any category existed,
looped on `unknown kind`, and left `book_kinds=0`. With WS-5:

| | tools the agent runs | `book_kinds` |
|---|---|---|
| baseline | `list_standards` → `propose_entities` ×N (loop) | **0** (always) |
| WS-5 | `workflow_list` → `workflow_load` → `list_standards` → `adopt_standards` → `confirm_action` | **10–13** (character, location, item, event, terminology, **power_system**, organization, species, relationship, plot_arc, trope, …) |

Measured pass rate: **≈3 of 4 fresh runs** create the categories (the rest: gemma stalls before the
confirm — see "What's left"). The world is real: opening the book shows the categories, and S02 can now
populate into them.

## What was built (four parts)

1. **The workflow object** (`agent-registry-service/internal/migrate/migrate.go`) — a System-tier C3 rail
   seeded idempotently:
   `see-standards (glossary_list_system_standards) → adopt (glossary_adopt_standards) →
    apply (glossary_confirm_action, gate=confirm) → read-back (glossary_book_ontology_read)`.
   Its `notes_md` owns the plain-language vocabulary ("categories" not "kinds") and the **hard ordering
   rule** — adopt categories FIRST, never propose entities before they exist. This is exactly the discipline
   the mid-tier model could not reconstruct on its own.

2. **A surface fix** — the workflow's `surfaces` must be **empty** (visible everywhere). A book-scoped chat
   turn resolves the runtime surface key `book` (not `chat`), so a `['chat']` workflow is filtered out on
   the very turn that needs it. (Authoring allows chat/compose/translate/admin; runtime uses
   admin/editor/book/chat — a real seam mismatch; empty surfaces sidesteps it.)

3. **A steering directive** (`chat-service/stream_service.py`) — advertising `workflow_list` is **not
   enough**: gemma had it advertised yet never called it and reconstructed the steps wrong. When the turn
   has curated workflows, we now inject a short system note naming them and telling the agent to
   `workflow_load(<slug>)` and follow the rail FIRST. **This is what flipped the behavior** — with it,
   gemma calls `workflow_load` and walks the steps in order.

4. **The silent-success prerequisite** (committed separately, `531e2e6d3`) — `propose_entities` no longer
   returns `ok:true` when all items fail, so the loop the workflow steers away from is also *detectable*.

## Harness additions (so a confirm-gated workflow is testable headlessly)

A propose→confirm gate suspends for the human to click Confirm; a headless driver can't. The driver
(`run_discoverability_scenario.py`) now plays the human faithfully:
- **auto-approve** a `tool_approval` card (`approved_always`);
- **commit** a domain confirm — POST the token to the committing endpoint (glossary:
  `/v1/glossary/actions/confirm`, reachable in-container) exactly as the FE does, then resume;
- **authentic-token**: commit with the token captured from the *adopt result*, not the model's copy —
  gemma corrupts the 519-char token when it copies it into the `confirm_action` arg (right length + ends,
  one wrong middle char → 422). The real FE commits the card's server-authored token, so this is faithful,
  not a workaround;
- **cross-turn carry**: the propose and its confirm can land in different user turns, so the authentic
  token persists across the turn boundary.

Without these, a warm pass stalls on the first card and every write scenario reads as a false ❌.

## What's left (honest)

- **Model reliability (~25% of runs)**: gemma sometimes stalls (a 150s+ no-output turn) or reverts to
  `propose_entities` and never reaches the confirm. The rail makes the *right* path available and default;
  it does not make a mid-tier model deterministic. Levers to raise the rate: a stronger/earlier directive,
  a shorter rail, or the product fix below.
- **Token-threading is a latent PRODUCT bug, not just a harness one.** In the current design the agent puts
  the confirm_token into the `confirm_action` arg; a mid-tier model corrupts it. Whether real users hit
  this depends on whether the FE commits the *card's* token (server-authored → fine) or the *arg's* token
  (model-copied → broken). Worth confirming in the FE; if the latter, auto-injecting the authentic token
  server-side (like the `book_id` injection) is the fix.
- **Only W1 authored.** This proves the mechanism end-to-end. The rest of the W2–W12 catalog (populate,
  triage, kg-build, translation, the S06 vision-to-book flagship) can now be authored against the same
  seed pattern + directive, and re-tested with this harness.

## Bottom line

WS-5 works: an authored rail + the steering directive turns S01 from a guaranteed failure (entities-first
loop, jargon, nothing saved) into a mostly-successful, jargon-free, genuinely-persisting setup — and does
it with a mid-tier model. The pattern (seed a C3 workflow + let the directive surface it) is now proven and
ready to extend to the rest of the catalog.
