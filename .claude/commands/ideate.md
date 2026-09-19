---
description: IDEATE phase (before CLARIFY) — brainstorm freely, research prior art on the web, score and choose, then record the idea as a standard doc in docs/ideas/. Also capture, list, review, promote, park or reject ideas.
argument-hint: "[topic | capture <idea> | list | review | promote <IDEA-id> | park <IDEA-id> <reason> | reject <IDEA-id> <reason>]"
allowed-tools: Read Write Edit Glob Grep WebSearch WebFetch Bash(git log *) Bash(git status *) Bash(date *)
---

# /ideate — the phase before CLARIFY

Arguments: `$ARGUMENTS`

Read [`.claude/skills/ideate/SKILL.md`](../skills/ideate/SKILL.md) now and follow it exactly, with
`$ARGUMENTS` as its arguments. It routes the mode (session, `capture`, `list`, `review`, `promote`,
`park`, `reject`), and it loads its own references and templates from
[`.claude/skills/ideate/`](../skills/ideate/) when it needs them.

This file only registers the slash command. The workflow, the document standard and the templates
live in the skill, so there is one home for them — do not restate them here.

If `$ARGUMENTS` is empty: ask for a topic, and offer `/ideate list`.
