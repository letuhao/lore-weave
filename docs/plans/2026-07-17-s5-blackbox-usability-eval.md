# S5 (What-If & Divergence) — blackbox usability evaluation

> Deliverable for the goal's "đánh giá nó có thực sự sử dụng được không? phải đứng dưới vai
> trò người dùng để test." Verdict is grounded in LIVE runs against the real stack (isolated
> S5 build on :5399 → gateway :3123 → composition + knowledge + book services), not a mock.

## Method

A real author, click-only, on a freshly-created book (test account `claude-test@loreweave.dev`).
Two Playwright suites drive the actual browser against the live stack:

- `studio-divergence.spec.ts` — 7 per-capability checks (list/spec/diff/switch/archive/canonview/what-if).
- `s5-blackbox-journey.spec.ts` — one end-to-end author journey: plan → branch → live on it → archive.

Both seed through the real `/derive` route (mints a knowledge partition) — so a green run proves the
whole cross-service chain, not just the FE.

## Result — LIVE, all green (2026-07-17)

```
studio-divergence.spec.ts .... 7 passed (≈1.1m)
s5-blackbox-journey.spec.ts .. 1 passed (21.8s)
```

The derivative seed SUCCEEDED on the live stack (knowledge-service minted the delta partition), so
every derivative-dependent assertion actually ran (no infra skips).

## Is it genuinely usable? — verdict per the §2 bar

| §2 bar dimension | Verdict | Evidence (live) |
|---|---|---|
| **Operable** | ✅ | The author spawns a dị bản through the 4-step wizard click-only and it lands. |
| **Reachable (GUI-only)** | ✅ | Divergence + Canon-view + What-if canvas all open from the command palette; no drop to `/edit` or the agent. |
| **CRUD** | ✅ | Create (wizard), Read (list + spec + diff), Switch (active-work), Archive (soft-delete) all drive live. |
| **No silent fail** | ✅ | Spec tab never shows `divergence-spec-error`; Diff never `branchdiff-error`; archive confirms via toast; on a real partition outage the wizard surfaces `divergence-error` (the test skips, doesn't lie). |
| **Named, not UUIDs** | ✅ | The BE-13a fix proven: the row shows the author's name (`Genderbend AU …`), not a raw project_id. |
| **Honesty about COW** | ✅ | Living on the dị bản and opening the manuscript editor shows the amber guard: *"edits here save to the canon manuscript, not the branch."* The one place a naive user could corrupt canon is signposted. |
| **Agent parity** | ◑ (v1) | The agent can OPEN the panel (`ui_open_studio_panel` divergence/canonview) and now LIST + ARCHIVE via `composition_list_derivatives` / `composition_archive_derivative`. CREATE (derive) stays behind the AN-8 confirm spine (spec'd, not shipped) — the honest v1. |

## Friction found (real-user lens) — and the call on each

1. **Deep-link needed to reach the editor once a Work exists.** The manuscript navigator switches to
   the composition OUTLINE after a Work is created, so a chapter is opened via `?chapter=` (or the
   outline), not a chapter row. This is existing studio behavior (not an S5 regression) — noted so the
   next author doesn't hunt for chapter rows that aren't there. **Not a defect; documented.**
2. **The dị bản's own prose isn't in the manuscript editor** — it lives on the what-if canvas →
   Promote (COW spec-branch model). The edit-guard banner is the entire mitigation in v1. Whether a
   derivative should hold a *full* forked manuscript is a **product decision**, spec'd in
   `docs/specs/2026-07-17-derivative-manuscript-fork.md` (recommended default: keep spec-branch). **Not
   a bug; a deliberate, documented product boundary.**
3. **Spec is write-once.** Editing a branch's taxonomy/branch-point isn't available; the UI says so
   ("archive and re-derive to change it"). Acceptable for v1; a future edit path is a small follow-up,
   not a blocker.

## Conclusion

**Yes — the S5 surface is genuinely usable by a GUI-only author.** A real user can branch a what-if,
understand what it is (spec), see what changed (diff), live on it safely (guard), consult canon, and
retire it — entirely in the Studio, proven by a live browser journey end-to-end. The remaining edges
(agent CREATE, manuscript fork, spec editing) are consciously scoped v1 boundaries with specs, not
gaps that block use.
