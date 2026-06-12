# Enrichment Closure — Decision Log

> Every call made absent a human answer (the user delegated full autonomy and will not
> confirm/answer during the run). Review these; flag any you'd have decided differently.
> Append new rows as the work proceeds. Format: ID · decision · rationale · reversible?

## Locked at task start (the Q1–Q9 clarifications, self-answered)

| ID | Question | Decision | Rationale | Reversible? |
|---|---|---|---|---|
| D1 | Which write actions must the GUI support? | All backend-supported user actions, made reachable + functional: detect-gaps, auto-enrich (full config form), register-source, ingest-source, resume-job, + verify approve/reject/edit/promote/retract work e2e. | Done bar = users can actually run enrichment, not just view. | Yes (scope can be trimmed) |
| D2 | Where does the GUI get the model list for auto-enrich/ingest forms? | Reuse the app's existing provider-registry model picker/hook; no hardcoded names. Add a minimal models-list call only if none exists, and document. | CLAUDE.md "no hardcoded model names"; reuse over reinvent. | Yes |
| D3 | "Compare with draft HTML" test depth? | Behavioral/structural parity via vitest+RTL (sections/states/controls/copy/badges/empty-loading-error/a11y/no-unmount), not pixel-diff. + one Playwright pass. | Pixel-diff is brittle and not how this repo tests; intent-parity is the real spec. | Yes |
| D4 | Test bar for "other features"? | Layered: pytest unit/contract for BE gaps; FE vitest; one Playwright full-loop; live-stack smokes where bootable, documented skip otherwise. | Matches repo's existing layered evidence model. | Yes |
| D5 | The mandatory POST-REVIEW human gate, with the human away? | Keep 12-phase rigor per slice; convert each POST-REVIEW human checkpoint into a written decision record here, flagged each time. | Honors the gate's intent (a deliberate pause + record) while respecting "no confirmations". | n/a |
| D6 | Commit & push cadence? | Per the track's standing "push and continue": commit each slice (stage only changed files; SESSION_HANDOFF in the same commit) + push to `lore-enrichment/foundation`. Nothing beyond that (no PR/merge) without the human. | Standing authorization on this branch; push is the established cadence. | Push is hard to reverse → kept within authorized scope |
| D7 | Where do decisions/skips/blockers go? | `docs/plans/2026-06-03-enrichment-closure/` — CLOSURE_PLAN / AUDIT / DECISIONS / SKIPS_AND_BLOCKERS; + DEFERRED.md rows + track SESSION_HANDOFF. | Single discoverable closure dossier. | n/a |
| D8 | Env risks (provider-registry clobber, LM Studio eviction)? | Rebuild provider-registry via build-stack.sh before live runs; use the test account's same-owner models; on a block, fall back to seeded/mocked data for GUI+tests and defer the live-smoke with a documented reason. | Don't fight the shared daemon indefinitely; the user explicitly wants skip+document. | Yes (re-run live later) |
| D9 | Definition of "closure"? | The 7-point done bar in CLOSURE_PLAN.md. | Concrete, checkable exit criteria. | Yes |

## Run-time decisions (appended as work proceeds)

### Phase 1a (functional GUI) — built
| ID | Decision | Notes |
|---|---|---|
| D10 | **ingest-source**: new `useEnrichmentSources.ingest()` + a per-source `SourceCard` with a textarea + embed-model picker (from provider-registry). Extracted `SourceCard` so `SourcesPanel` stays ≤100 lines (MVC rule). | Registered corpora can now be populated. `chunk_count` surfaced on the card. |
| D11 | **retract**: surfaced in the `ProposalActions` interface + a Retract button on promoted proposals → shared `ConfirmDialog` (destructive). | Authors can now un-promote canon. |
| D12 | **auto-enrich cost-cap**: added `max_spend_usd` (empty = no cap, matches backend `None` default) + `top_k` (default 5 = backend default) inputs. Untouched ⇒ no behavior change. | The spend-safety control is now reachable. |
| D13 | **reject reason**: Reject now opens an inline reason textarea → `onReject(reason)`. | The supported (previously dead) reason capability is live. |

### Phase 1b (draft parity) — built
| ID | Decision | Notes |
|---|---|---|
| D14 | ProposalCard enriched: H0 chip · confidence · "N dimensions · grounded on N sources" · advisory-flag preview (needs_review) · auto_rejected dimming+reason · content clamp 2 lines. | Matches the review.html card. |
| D15 | Technique filter (P1/P2/P3 tier chips) added to ProposalList, filtered client-side by `tierOf()` in ProposalsPanel (mirrors the project filter; no new endpoint). | |
| D16 | ProposalDetail: static h0_note → a warning-colored **live** H0 banner (origin/confidence/review_status) + author-only caption. | |
| D17 | ProposalsPanel: added an `isError` branch (role="alert"). | Audit flagged a failed list query silently showing the empty state. |
| D18 | DimensionList: added a "N dimensions" count line. | |

### Accepted divergences from the mockup (deliberate — see SKIPS_AND_BLOCKERS.md)
| ID | Divergence | Why kept |
|---|---|---|
| D-PARITY-SIDEBAR | Enrichment is a book TAB, not the sidebar item review.html drew. | Locked in the architecture doc; per-book feature beside Glossary/Wiki. |
| D-PARITY-VERIFY-ROWS | VerifyPanel shows ONE combined "clean" line, not 4 separate ✓ rows. | The combined line names all four checks — same information, more compact. |
| D-PARITY-MAXGAPS | Auto-enrich uses a "Max gaps" top-N + cost-cap, not the mockup's per-row checkboxes. | Top-N-by-rank + USD cap is the implemented (and safer) design. |
| D-PARITY-STATUS-DEFAULT | Proposals default status filter = "All", not the mockup's "proposed". | A review surface should show the full picture by default. |
