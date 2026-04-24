# Agent Guide — LLM_MMO_RPG

> **Read this before you edit anything in this folder.** Short, action-oriented.
> Pairs with [ORGANIZATION.md](ORGANIZATION.md).

---

## 1. Session start (2 minutes, mandatory)

1. Read [README.md](README.md) → tail of [SESSION_HANDOFF.md](SESSION_HANDOFF.md) (last 2–3 session entries) → this file.
2. Read the `_index.md` of the subfolder you plan to touch.
3. Decide your **work scope** — one subfolder, or one topic file inside it. Announce it in a SESSION_HANDOFF tail row **before** editing.

---

## 2. Avoiding conflicts (file-level locking by convention)

No real lock exists — we avoid collisions by shared convention:

- **One agent = one subfolder at a time.** Check the `Active:` header at the top of that subfolder's `_index.md`. If it names another agent with a timestamp < 2 hours old, pick a different subfolder or wait.
- **Claim the subfolder** by setting the header when you start:
  `Active: <agent-name> <ISO-UTC timestamp> <scope — which files you will touch>`.
  Clear it to empty string when you finish.
- **Never edit two subfolders in the same agent turn.** Cross-subfolder changes go through a SESSION_HANDOFF note to the next agent / session.
- **Never rewrite prior SESSION_HANDOFF entries.** Append to the tail only. Old rows are immutable history.

---

## 3. Editing rules

- **Size cap 500 soft / 1500 hard lines.** If your edit would cross the soft cap, split on the next `##` heading before adding content. Use the chunk tool for mechanical splits.
- **Preserve stable IDs.** Never renumber `R*`, `S*`, `C*`, `HMP`, `SR*`, `M*`, `DF*`, `PC-*`, `IF-*`, `WA-*`, `MV*`. Retired IDs get an `_withdrawn` suffix instead of reuse.
- **Cross-refs by ID, not path.** Write "see S9-D3 / §12Y" not "see line 4520". The chunk tool can rewrite paths; it cannot rewrite intent.
- **Append-only in session logs.** Rows in `SESSION_HANDOFF.md` are immutable once dated.
- **Same-commit index update.** Any change to a topic file updates the owning subfolder's `_index.md` in the same commit (new status, new date, new exported IDs).

---

## 4. Shared status vocabulary

Use only these — do not invent new ones without updating this guide:

`OPEN` · `PARTIAL` · `MITIGATED` · `SOLVED` · `ACCEPTED` · `DEFERRED` · `WITHDRAWN` · `KNOWN`.

For decisions specifically: `LOCKED` · `PENDING` · `SUPERSEDED BY <id>`.

---

## 5. When to split a file

Before editing, if the file:

- Is **> 500 lines** → split first, then edit the new smaller file.
- Has **≥ 2 substantive `##` headings** that could each stand alone → each heading becomes a candidate file.
- Mixes **locked (stable) + pending (churning)** material → split so read-mostly material stops blocking churn.

Always use the chunk tool — it verifies no data was lost.

---

## 6. End-of-work checklist

- [ ] `_index.md` updated with new/changed entries, statuses, last-touched date
- [ ] `Active:` header on `_index.md` cleared to empty string
- [ ] `SESSION_HANDOFF.md` has a tail row with: date · agent · subfolder · files touched · 1-line why
- [ ] All cross-refs by ID still resolve (grep for broken `§`, `DF`, `S*`, `R*` refs)
- [ ] No file in your scope exceeds 1500 lines
- [ ] Migration or split? Chunk tool's data-loss verifier ran green

---

## 7. Handling contention

If you open a subfolder's `_index.md` and `Active:` is set:

| Situation | Action |
|---|---|
| Different agent, different scope from yours | Pick another subfolder. |
| Different agent, same scope | Leave a SESSION_HANDOFF note and stop. Do not force through. |
| Timestamp older than 2 hours (stale lock) | Clear it, leave a SESSION_HANDOFF note naming the previous agent + what you observed. |
| You set it and crashed | On return, re-check file state before re-claiming. |

---

## 8. What NOT to do

- Do not batch large rewrites across multiple subfolders in one turn.
- Do not rename or renumber stable IDs to "clean up".
- Do not delete archive files (`*.ARCHIVED.md`) before the next session confirms the split is healthy.
- Do not write new monoliths. New material = new small file + index entry, not a dumping ground in an existing file.
- Do not invent new top-level subfolders without updating `ORGANIZATION.md` first.
