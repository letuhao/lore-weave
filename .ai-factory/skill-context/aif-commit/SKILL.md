# LoreWeave overrides for `aif-commit`

Read [`.ai-factory/skill-context/aif/SKILL.md`](../aif/SKILL.md) first. This file covers only committing.

## Never bypass the hooks

`.githooks/pre-commit` runs the workflow gate plus the provider-rule, DB-safety, closed-set,
doc-language, deferral, gate-wiring and agent-skills-parity checks. Enable them once per
checkout:

```bash
git config core.hooksPath .githooks
```

A blocked commit is the system working. **Do not pass `--no-verify`**, and do not "fix" a
gate by weakening it — a check that cannot fail is worse than no check.

## Do not push, and do not commit on `main`

`git.skip_push_after_commit: false` in AI Factory's defaults means "push after commit".
**On this repository, do not push unless the human explicitly asks.** If you are on the
default branch, branch first.

## What goes in a commit

- **Stage only the files you changed** — never `git add -A`.
- The message names the phase and the review fixes, and is **English**, like every other
  persisted artifact here. So is the PR body.
- The `SESSION_HANDOFF.md` update lands in the **same commit** as the code it describes.
  Work not recorded there does not exist for the next session.
- End the message with the trailer the harness expects:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` when Claude authored it.

## Before the commit exists

COMMIT is phase 11 of 12. VERIFY (6), REVIEW (7), QC (8), POST-REVIEW (9) and SESSION (10)
come first, and POST-REVIEW is a human checkpoint that is never skippable. The workflow gate
enforces this; do not route around it by committing from a different tool.
