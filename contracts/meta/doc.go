// Package meta is the canonical Go library for accessing the `loreweave_meta`
// database. Every service that needs to read or write meta tables imports this
// package; direct SQL on meta tables outside this package is a CI lint error
// (I8 invariant — see L1.B layer plan §1).
//
// Cycle 2 (L1.B) ships the foundational artifacts:
//
//   - MetaWrite() / MetaWriteBatch() — canonical write + audit path (Q-L1B-3)
//   - AttemptStateTransition()       — CAS-based reality state machine
//   - transitions.yaml               — per-resource transition graph + validator
//   - events_allowlist.yaml          — which MetaWrite ops emit outbox events (Q-L1B-1)
//   - meta-sensitive-read-paths.yml  — which read paths trigger meta_read_audit (Q-L1B-2)
//
// Cycle 3 (L1.A-2) extends with the PII + identity + consent surface:
//
//   - KMSClient interface + OpenPII()      — crypto-shred decrypt path
//   - DeterministicTestKMS                 — test-only stand-in (NEVER prod)
//   - pkColumnFor() extended               — pii_registry / pii_kek /
//                                            user_consent_ledger / player_character_index
//   - events_allowlist.yaml extended       — user.created, user.erased,
//                                            user.consent.granted/revoked,
//                                            pc.index.created/status.changed
//   - migrations/meta/009..012             — DDL for the 4 tables
//
// Hot-path read accessors (cache, routing, entity_status) ship in later cycles
// alongside their dependent kernel infrastructure (Redis, etc.).
//
// Cycle 4 (L1.A-3) ships the audit infrastructure that MetaWrite has always
// depended on:
//
//   - meta_write_audit  + meta_read_audit       (DPS 1) — universal write audit + enumerated read audit
//   - admin_action_audit + service_to_service_audit (DPS 2) — admin command + RPC audit
//   - prompt_audit                                (DPS 3) — LLM prompt context (NEVER body)
//   - Scrubber interface stub (S08 §12X.5)        — admin_action_audit.error_detail path
//   - PromptAudit interface                       — type-level enforcement that bodies cannot
//                                                    flow into the audit (only context_hash)
//   - pkColumnFor() extended                      — meta_write_audit / meta_read_audit /
//                                                    admin_action_audit / service_to_service_audit /
//                                                    prompt_audit (audit_id PKs)
//   - migrations/meta/013..017                    — DDL for the 5 audit tables
//                                                    + REVOKE UPDATE/DELETE append-only enforcement
//
// As of cycle 4, MetaWrite()'s same-TX audit insert path is fully wired end-to-end:
// real production stacks no longer fall over on the audit step. Cycles 2+3's
// fake-Tx test pattern remains for unit coverage.
//
// Parent layer plan:
//   docs/plans/2026-05-29-foundation-mega-task/L1B_meta_access_library.md
//
// LOCKED decisions consumed across cycles 2+3+4:
//   Q-L1A-1, Q-L1A-2 (canon OUT — no canon tables in meta),
//   Q-L1A-3 (full audit V1, no sampling — service_to_service_audit sized accordingly),
//   Q-L1B-1, Q-L1B-2, Q-L1B-3, Q-L1B-4,
//   Q-L5H-1 (consent ledger shape — force-propagate timeout enforced later)
package meta
