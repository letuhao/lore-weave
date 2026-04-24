<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 00_overview_philosophy.md
byte_range: 0-2979
sha256: b8dc9ba4fe7d76ba080c70c3e4d40b01b31dc9b6459fedc0e7c0b14b0efc0261
generated_by: scripts/chunk_doc.py
-->

# 03 — Multiverse Model

> **Status:** Exploratory — conceptual foundation for the world-persistence layer. Companion to [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) (engineering) and [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) (risks).
> **Created:** 2026-04-23
> **Supersedes:** The "root reality" framing in early drafts of 02. Each reality is a peer; none is privileged.

---

## 1. Philosophy

In parallel-universe / multiverse theory (and in SCP-style fiction), there is no privileged "true" reality. Universes share only an **origin point** (khởi nguyên); from there each evolves independently, with its own logic, its own history, its own outcomes.

LoreWeave adopts this literally:

- **The Book is not a reality.** The book is a body of canonical source material — characters, locations, lore, axiomatic facts. It is the origin, not a universe.
- **Every reality is a universe.** Each one is a complete, independent timeline. No reality is "more canonical" than another just because it was created first or hews closer to the book.
- **Logic can diverge.** Alice being alive in one reality and dead in another is normal. Magic working in one and not in another is normal. The book defines what is *possible*; reality defines what *happened*.

```
                     📖 BOOK
              (canon source material;
               characters, world concepts, axioms)
                        │
                        │ seeds each reality's initial state
                        │
    ┌─────────┬─────────┼─────────┬──────────┬──────────┐
    │         │         │         │          │          │
   R_α       R_β       R_γ       R_δ        R_ε        R_ζ
  alive     dead-at-  queen-at  assassin-   pirate-    librarian-
  @T=200    T=50      T=500     T=120       T=300      @T=∞
  (peer)    (peer)    (peer)    (peer)      (peer)     (peer)
```

None of R_α…R_ζ is "main." They are sibling universes that happen to share an origin.

## 2. What a reality is

A **reality** is a complete, self-contained simulation with:

- Its own timeline of events (event log scoped to `reality_id`)
- Its own NPCs (instances of glossary entities — same canonical persona, divergent history)
- Its own player characters (PCs do not cross realities by default; see §9)
- Its own regions, items, world state
- Its own local canon (facts established within it, immutable within it)
- Its own divergence record (when/why it forked, if applicable)

A reality is always born from somewhere:
- **From the book**: seeded directly from book's initial state. A fresh universe on the same origin.
- **From another reality** (snapshot fork): inherits the ancestor's event chain up to the fork point, then diverges.

Both are valid ways to start a reality. Neither produces a "root."

