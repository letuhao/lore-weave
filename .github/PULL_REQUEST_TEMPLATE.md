## What this changes

<!-- One logical change per PR. What does this do, and why? -->

## Evidence

<!--
Actual command output, not "tests pass" — paste it. For a new check, lint, or gate: the
red-then-green proof (break the thing it guards, watch it go red, put it back, paste both).
See CONTRIBUTING.md §4 and docs/standards/non-vacuity.md.

If this touches two or more services: a real call across them on a live stack, and say so here.
Mock-only coverage has repeatedly hidden contract bugs in this repo. If the stack genuinely
would not boot for you, say that instead of a silent skip.
-->

## What I did not do

<!-- A known gap stated plainly is welcome; a silent one is the problem. "None" is a fine answer. -->

## Checklist

- [ ] I read [`AGENTS.md`](../AGENTS.md) for the areas this PR touches
- [ ] `git config core.hooksPath .githooks` is set, and the pre-commit gates passed locally
- [ ] Every user-facing table this touches is scoped by `owner_user_id`/`book_id` (if applicable)
- [ ] No hardcoded model names, pricing, or secrets were introduced
- [ ] If this is AI-assisted: I reviewed every line myself and can explain the whole diff
      (see [`CONTRIBUTING.md` §9](../CONTRIBUTING.md#9-ai-assisted-contributions))
