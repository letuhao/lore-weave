# EPUB Import V2

Status: implementation contract

## Purpose

EPUB Import V2 preserves source-defined logical chapter boundaries. It supersedes the
heading-derived EPUB path described in `2026-05-23-p1-structural-decomposer.md` while
leaving the FB2, PDF, and plain-text import paths unchanged.

## Ownership and boundaries

| Concern | Owner | Boundary |
|---|---|---|
| Source objects, inspection, jobs, items, assets, provenance, metadata, and chapters | Book Service | Public API through api-gateway-bff; authenticated internal commands for worker-infra |
| EPUB archive inspection, navigation, and content-range normalization | Shared deterministic Go package | Imported by Book Service and worker-infra; no database access |
| Scene extraction within one selected chapter | Knowledge Service | Authenticated internal parse request |
| Outline hierarchy and scene materialization | Composition Service | Best-effort authenticated request after Book finalization |

All persisted source and job records are tenant-scoped. A source belongs to its uploader;
a job belongs to the target book and requires the normal book grant. Worker-infra must not
write the Book Service database directly for V2.

## Structure invariant

Navigation is authoritative, in this order:

1. EPUB 3 navigation document (`nav` manifest property and `epub:type="toc"`);
2. EPUB 2 NCX;
3. linear OPF spine fallback.

A selected leaf navigation node creates exactly one LoreWeave chapter. Parent nodes
materialize hierarchy unless inspection explicitly marks a parent as content-bearing.
Headings can provide a fallback title or split scenes inside that chapter, but cannot split
or merge logical EPUB chapters.

## Lifecycle

```text
uploaded -> inspected -> queued -> processing -> import_staging -> import_ready
                                                     |                    |
                                                     v                    v
                                                import_failed <--- finalized -> completed
                                                     |                    |
                                                     +--- resume ---------+--- completed_with_warnings

queued | processing | import_staging | import_ready | import_failed -- cancel --> cancelled
completed | completed_with_warnings | cancelled | import_failed -- rollback --> rolled_back
```

Only a Book Service command changes job or item state. Operations are idempotent by job,
source SHA-256, and source key. The worker checks cancellation before claiming each next
item. A cancelled job retains staging state for resume or rollback. The source EPUB is
retained by default and is never removed by successful finalization or rollback.

`replace_all` and rollback require an explicit caller confirmation and an audit record.
Rollback only affects effects owned by the job. It preserves a chapter that a user modified
after finalization and reports `rollback_conflict_user_modified`.

## Internal worker command contract

Worker-infra authenticates with the existing internal-service mechanism and uses a versioned
Book Service command surface. Each request includes `job_id`, `source_id`, `book_id`,
`item_id` when applicable, `source_key` when applicable, `stage`, and a request ID.

| Command | Preconditions | Idempotent result |
|---|---|---|
| `claim-item` | Job is queued/processing and item is pending | Returns one claim token and normalized source ranges, or no item/cancelled state |
| `checkpoint-item` | Valid claim token | Persists progress, warnings, asset/link intents, and staged chapter payload once |
| `fail-item` | Valid claim token | Records a typed error without discarding completed items |
| `finalize-job` | All mandatory selected items are ready | Activates order, applies approved metadata/cover, creates report, and returns final state |
| `record-materialization` | Job is finalized | Records best-effort Composition outcome without changing Book completion |

Commands return stable `status`, optional `retry_after_ms`, typed `error_code`, and durable
counts. They must not return manuscript HTML or object bytes. Structured logs include only
the identifiers above, `duration_ms`, and `error_code`.

## Event compatibility

The existing `import.requested` outbox event remains compatible during rollout. V2 adds
optional `source_id` and `pipeline_version: "epub-v2"`; consumers that do not understand
these fields continue to process legacy formats. The V2 worker treats `source_id` as
required for EPUB V2 and rejects a missing source with `import_source_missing`.

## Safety and configuration

`EPUB_IMPORT_V2_MODE` and archive limits are deployment configuration, not user settings.
The supported modes are `off`, `shadow`, `opt_in`, `default`, and `legacy_disabled`.
The deployment limits compressed bytes, uncompressed bytes, entry count, single-entry bytes,
compression ratio, content documents, navigation nodes, assets, and chapter HTML bytes.
`EPUB_IMPORT_ASSET_RETENTION_HOURS` controls the Book-owned orphaned-asset GC window (default
168 hours); failed object deletions remain retryable and retained source EPUBs are never removed.

The 2026-08-04 authenticated local shadow corpus run completed 20 inspections with a net
legacy-to-V2 chapter delta of -18. It found five
`logical_navigation_count_differs_from_document_projection` results and two
`navigation_fallback_used` results. These are diagnostic comparison outcomes, not a semantic
equivalence claim or approval to promote the deployment mode. V2 navigation remains authoritative.

The importer rejects encrypted/DRM EPUBs, unsafe archive paths, archive collisions, and
executable or externally fetched HTML content with typed diagnostics. No default EPUB action
can trigger a paid model or other provider request.
Book Service exposes bounded Prometheus series for import job/item/asset outcomes, warning
stages, finalize duration, and inspected uncompressed bytes. Labels contain only fixed
outcome/stage enums; source keys, filenames, book IDs, and manuscript content are never labels.

## Migration and recovery

Schema changes are additive. Every persisted V2 artifact has a compensating cleanup path:
unfinalized staging rows are job-owned, assets are reference-counted, metadata/cover changes
have a job-owned journal, and retained sources require explicit deletion outside rollback.
Migration validation covers both upgrade and cleanup/recovery paths before the rollout mode
is changed from `opt_in`.
