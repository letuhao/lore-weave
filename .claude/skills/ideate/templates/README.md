# Ideas — the IDEATE phase

This folder is where product ideas are recorded, explored and decided **before** they become work.
It is the phase in front of CLARIFY: AUDIT-EXISTING → **IDEATE** → CLARIFY → DESIGN → …

Before it existed, ideas arrived in chat, were half-discussed, and were either lost or built without
anyone comparing them to the alternatives.

## How to use it

| You want to… | Run |
|---|---|
| explore a topic properly: brainstorm, research, then choose | `/ideate <topic>` |
| jot down an idea before you forget it | `/ideate capture <one line>` |
| see every idea and its status | `/ideate list` |
| clean up: stale, duplicate or already-built ideas | `/ideate review` |
| hand a chosen idea to CLARIFY | `/ideate promote IDEA-NNN` |
| stop an idea, and keep the reason | `/ideate park IDEA-NNN <reason>` or `/ideate reject IDEA-NNN <reason>` |

## The rules

- One idea, one file: `YYYY-MM-DD-<slug>.md`, id `IDEA-NNN`. Ids are never reused.
- Every idea has a status: `seed` → `explored` → `shortlisted` → `promoted`, or `parked` / `rejected`.
- Every status change is logged in the file **and** updated in [INDEX.md](INDEX.md), together.
- Nothing is deleted. A rejected idea keeps its reason, which answers the next person who proposes it.
- Brainstorming is free and unjudged; judging happens after, with a scored table and written reasons.
- Every outside claim is cited with a link and the date it was read.
- Written in English (the doc-language gate enforces this on commit).
- Only the PO promotes, parks or rejects. Anyone can capture.

## What "promoted" means

A promoted idea gets a spec draft in `docs/specs/`. That draft is an **input to CLARIFY**, not an
approved design — CLARIFY, DESIGN and the PO checkpoint still happen as usual.
