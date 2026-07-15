# PA DEBT-CLEARANCE — BUILD RUN-STATE (the durable commitment)

## 0 · Resuming after a compaction — do THIS first
Re-read THIS file, then `git log --oneline -20`, then continue at the first ⬜ slice.
Plan + audit rationale: [`2026-07-15-PA-DEBT-CLEARANCE-plan.md`](2026-07-15-PA-DEBT-CLEARANCE-plan.md).
Never re-litigate a sealed decision from memory (SD-C1..8/H1..4 in the completion seal; SD-7 quarantine).

## 1 · The GOAL
Clear EVERY code-doable PA remainder in the plan's §2 slice board (Groups R·P·B·F, ~11 slices) so the
Personal Assistant is genuinely complete AND reachable. **Autonomous exit** = every slice ✅-with-evidence
(pasted green tests + a pasted cross-service live-smoke where it crosses services + a cold `/review-impl`
with findings fixed), commits pushed; the §3 parked list stays parked with its gate; SD-7 stays human.
**NOT in scope (unchanged):** SD-7 safety-eval cert + numeric-eval QWK clearance (human milestones; scorer
stays quarantine-tier — R2 makes it VISIBLE, never clears the number).

## 2 · Standing invariants (never lower silently)
- Never `git add -A` (shared checkout — explicit pathspec per slice). Commit each slice promptly.
- Per slice: PASTED green tests + a PASTED cross-service live-smoke (where it crosses services) + a cold
  `/review-impl` with findings fixed + re-verified. Rebuild stale images before a live-smoke.
- **SD-7:** coaching SCORE stays quarantine-tier; a committed QWK / "safety passing" is a DRIFT VIOLATION.
- Settings/Config Boundary (per-user, fail-closed, effective-value-visible); Provider-gateway (pricing/models
  from provider-registry, never hardcoded); Tenancy (owner/scope key on every table); no hardcoded secrets
  (DEK key ≠ JWT_SECRET). D13 (assistant session has no working-memory charter — F3).
- Stop + ask ONLY if a sealed decision turns out wrong, an action is destructive/irreversible/risks real
  user data, or you reach the SD-7 human boundary. Otherwise keep going.

## 3 · SLICE BOARD (evidence string, not a checkmark)
`⬜ todo · 🔵 wip · ✅ done (evidence)`

### Group R — Reachability (turn 3 shipped-but-unreachable features on)
| Slice | Status | Evidence / note |
|---|---|---|
| **R1** reflection patterns feed + live dismiss | ✅ | chat `reflection_patterns` table (owner-scoped, get-or-replace/week) + PUT (worker-ai) + tombstone-filtered GET; worker-ai `run_weekly_reflection` returns `structured_patterns` → consumer PUTs them (best-effort; short-circuit clears); BFF `GET /v1/assistant/reflection-patterns?week_end` (owner from JWT); FE `useReflection` fetches chips FOR THE DRAFT'S WEEK. **Tests:** chat DB 3 (get-or-replace, tombstone-filter, owner-scope, calm-week-no-fallback) + worker-ai consumer 10 (persist + short-circuit-clears) + FE hook 3 + components 16 + BFF/FE tsc. **Live-smoke (PASTED):** worker-ai→chat PUT → FE→BFF→chat GET (2 chips) → dismiss → GET (dismissed EXCLUDED) → cross-tenant 0; H1 re-smoke: calm week returns [] not a stale prior week. **Cold review:** HIGH-1 (calm-latest-week fell back to a stale prior week via `max(week_end)`) FIXED — chips now pinned to the draft's `entry_date`, no fallback; L1 (patterns user-scoped, card per-book) = conscious (assistant diary is one book/user; chips tie to the shown draft). Crosses worker-ai/chat/BFF/FE. |
| **R2** coaching scorecard read + minimal mount | ✅ | chat `GET /assistant/scorecards` (owner-scoped read of chat_outputs 'scorecard' rows, **SD-7 quarantine coerced fail-closed at read**) → BFF `GET /v1/assistant/scorecards` (owner from JWT) → FE `useScorecards` (normalizes quarantine fail-closed) → `CoachingScorecard` MOUNTED in AssistantHomeStrip w/ quarantine badge. **Tests:** chat router 4 (owner-scope, token-gate, legacy-null→true, malformed-metadata-no-500) + FE hook 3 + component 7. **Live-smoke (PASTED):** FE→BFF→chat read of 3 REAL persisted scorecards, every one quarantine=true (legacy nulls coerced), cross-tenant 0. **Cold review:** SD-7 VERIFIED clean (no trendable-quarantine path — triple defense: read-coerce + FE-normalize + trend-exclude; no trend UI even renders); MED (non-dict metadata 500'd the feed) FIXED + LOW (`==null` dim guard) FIXED. Crosses chat/BFF/FE. |
| **R3** proactive delivery notification | ✅ | chat `_notify_proactive_checkin` POSTs a CONTENT-FREE notification to notification-service AFTER the proactive turn commits (best-effort; the message stands regardless); NEW `assistant` notification category (SoT enum) for per-category opt-out; FE icon/tint. **Tests:** chat proactive 9 (content-free payload, best-effort blip, notify-fired, fail-closed, dedup) + notification category Go test. **Live-smoke (PASTED):** enabled → `notified:true` + a content-free `assistant` row landed (0 rows w/ diary text) → 2nd fire deduped → opt-out fail-closed no-op. **Cold review:** no HIGH (content-free VERIFIED — no content param, static strings, server re-redacts; best-effort outside the txn; tenancy + dedup clean; category SoT single-source, no CHECK constraint); LOW-2 (FE category metadata) FIXED; LOW-1 (18-locale i18n for `assistant.proactive_checkin`) → parked (i18n-tooling pass, English fallback works). Crosses chat/notification-service. |

### Group P — Privacy / safety / crypto (fix-now default)
| Slice | Status | Evidence / note |
|---|---|---|
| **P1** wiki is_person on USER tier | ✅ | threaded is_person across user_kind create/update (HTTP) + MCP create + both read queries + response (effective-value-visible). **Tests:** glossary is_person suite 5/5 incl. a NEW full-HTTP `TestUserKindHTTP_IsPerson_CloneInheritsAndClearGuard` + `TestUserTierPersonKind_CreateThenAdopt_ExcludedFromWikiGen` (create→adopt→wiki-gen exclusion). **Cold review:** HIGH (clone path dropped is_person → re-opened the leak) FIXED — clone inherits from the system source; parity clear-guard added (can't clear is_person on a system-cloned person kind — third-party protection, MED-2 parity); MED (no client-level branch test) → covered by the HTTP e2e. Single service (glossary) — no cross-service seam. |
| **P2** reflection facts fail-closed | ✅ | `recall_facts_range(fail_closed=True)` raises `KnowledgeUnavailable` on transport/non-200 for `reflect_week` (facts feed the Gate-3 safety screen); the orchestrator turns it into a retryable status → consumer un-ACKs → retry; `roll_up_week` stays best-effort (default). Empty 200 still `[]` in both modes. **Tests:** reflection+rollup 28/28 incl. a client-level 4-branch httpx test + orchestrator-retries-writes-nothing + reflect_week-raises. **Cold review:** MED (no client-level branch test) FIXED; verified both safety-screen halves (notes C2 + facts P2) now fail-closed, no circular import, rollup untouched. Single-service worker-ai (mirrors the already-live-smoked C2 down-endpoint shape). |
| **P3** DEK hardening bundle | ✅ | (a) `TestDEK_IsStillSingleConsumer` repo-scan tripwire (reds if a 2nd service touches the user-DEK substrate → forces a conscious erase-scope decision); (b) `dek_shred_audit` table (NO FK — outlives the user) + the shred DELETE+audit now ONE atomic tx (no un-audited shred; converges on retry); (c) `getChapterContent` decrypts a diary chapter owner-gated (403 non-owner, fail-closed) instead of returning ciphertext. **Tests:** auth `TestUserDEK_ShredWritesDurableAuditRow_PG` (real PG: audit written, no-op recorded, SURVIVES user-delete) + tripwire (proven meaningful: signals in book/auth only) + build/vet. **Cold review:** no HIGH/MED (convergence preserved, audit durable, owner-gating fail-safe, no plaintext regression, tripwire catches); 2 LOW (t.Fatal-not-skip, +.rs/.tsx) FIXED. (b) is auth-only real-PG-tested; (c) reuses the C5-live-proven book→auth DEK decrypt seam (LOW display-bug). Dedicated DEK_SHRED_TOKEN → parked (cross-service config). |
| **P4** diary shred durable retry | ⬜ | ride the existing book-service outbox → retried idempotent auth DELETE |

### Group B — Billing / correctness
| Slice | Status | Evidence / note |
|---|---|---|
| **B1** lane budget enforce + by-lane report | ⬜ | thread purpose→lane into reserve; per-lane cap mirror mcp_key sub-cap; by-lane report |
| **B2** distiller model-aware window | ⬜ | resolve model ctx in distill consumer (get_context_length exists); window=min(12k, ctx−ovh−rsv) |

### Group F — FE polish (DBT-14)
| Slice | Status | Evidence / note |
|---|---|---|
| **F1** onboarding fifth-intent (C22) | ⬜ | assistant intent id + tile + route |
| **F2** FE timezone-confirm UI | ⬜ | confirm control; BE already accepts timezone |
| **F3** assistant session-template seed (WS-1.7) | ⬜ | seed WITHOUT a working-memory charter (D13) |

## 4 · Decision register (ordinary build-time calls appended as the run goes)
- *(none yet)*

## 5 · Parked (stay parked — each earns a gate; see plan §3)
D-PROACTIVE-LLM-CONTENT (#2) · D-STT-METER-UNIFY (#4 policy) · DBT-7 KEK re-wrap (#2 ops) ·
DBT-10 trashed-diary UX (blocked on E14) · DBT-2 (#2) · DBT-3 (#3) · DBT-4 (#2) · P-2 · P-4 tail · P-11.
Mobile home-strip surface (`md:block` desktop-only) → QC/product decision, not auto-scoped.
- **D-DEK-SHRED-TOKEN** (P3, #2 cross-service config) — gate the DEK shred behind a dedicated
  DEK_SHRED_TOKEN distinct from the shared INTERNAL_SERVICE_TOKEN (mirror ADMIN_TOKEN_ISSUER_SECRET),
  with a safe fallback + the token plumbed into book-service + admin-cli + compose. Defense-in-depth on
  an already-internal-token-gated, network-isolated route; the durable audit row (the higher-value half)
  shipped in P3. Also carry the optional rate/anomaly brake here.
- **D-PROACTIVE-NOTIF-I18N** (R3 cold-review LOW-1, #2 i18n-tooling) — the `assistant.proactive_checkin`
  message_key has no locale entry, so non-English users see the English title/body fallback. Fold into a
  targeted notification i18n pass (with DBT-4). English fallback works; no broken behavior.

## 6 · Drift log (record the near-misses — an empty drift log is dishonest)
- *(none yet)*

## 7 · Human milestone (NOT code)
SD-7 safety-eval cert + numeric-eval QWK clearance. Scorer quarantine-tier until a person certifies it.
