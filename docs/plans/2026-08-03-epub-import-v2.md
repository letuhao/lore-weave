# EPUB Import V2 — implementation plan and status

**Spec:** [`docs/specs/2026-08-03-epub-import-v2.md`](../specs/2026-08-03-epub-import-v2.md)
**Status:** implementation and local acceptance in `opt_in` are complete. Production rollout is
a separate future operations decision, not a completion condition for this early-stage EPUB V2
refactor.

## Delivered

- The shared EPUB parser preserves EPUB 3 `nav`, EPUB 2 NCX, and spine fallback
  hierarchy instead of flattening a source into one chapter.
- Book Service owns inspection, durable jobs/items, chapter provenance, assets,
  metadata/cover journals, finalize, resume, cancel, and rollback.
- Worker-infra claims/checkpoints items, reclaims idle Redis deliveries, and
  forwards only opaque scene and hierarchy mappings across service boundaries.
- Composition persists the lossless ToC closure and projects manuscript-part
  mappings without writing Book Service tables.
- The Chapters tab exposes the retained-source inspection and selection wizard,
  including title overrides and durable progress/recovery/report state.
- FB2 remains a separate import path and is not routed through the EPUB pipeline.

### GUI scope — complete (2026-08-04)

The EPUB wizard is closed as an implementation-plan item: inspection, nested
chapter selection, title overrides, metadata and import options, durable
progress/recovery/report actions, EN/RU copy, focused tests, and browser smoke
evidence are complete. The self-closing-XHTML extraction regression was fixed
in the shared importer and the local worker has been rebuilt. Future work here
is limited to defects found in operation, not planned GUI scope.

## Verification snapshot

The current handoff records passing targeted Go parser/service tests and frontend
build checks. Full Knowledge pytest still has unrelated pre-existing failures and
the Book OpenAPI Spectral run is blocked by duplicate FB2 response keys in the
base contract; these are tracked separately and are not EPUB V2 regressions.

### Reliability and observability — complete (2026-08-04)

- The shared parser test suite exercises malformed manifests, compression-ratio
  limits, ZIP traversal, encrypted archives, invalid MIME, missing anchors, and
  unsupported or missing assets. The self-closing XHTML `<title/>` regression
  from the operational EPUB is covered by a focused extraction test.
- Worker tests prove retry after transient MinIO failure, Redis redelivery
  without duplicate parsing or staging, best-effort Composition outage handling,
  and the absence of implicit provider/model calls. Book DB tests prove
  cancel/resume/parser recovery plus idempotent finalize, and retry MinIO asset
  deletion after a transient failure.
- The live Book Service metrics endpoint exposes the documented bounded-label
  EPUB counters and histograms. The parser-only 50-chapter/10 MiB and
  500-chapter/100 MiB benchmarks were rerun after the parser fix; current
  measured values are recorded in the operations runbook.

### Authenticated retry evidence (2026-08-04)

The reported failed local job was resumed through its authenticated browser
session using the normal public resume endpoint. Its durable status became
`completed`: all 8 selected items are `active`, the 13 unselected items remain
`skipped`, eight chapters and eight provenance records exist, and the persisted
report has no errors. The generic Jobs detail now exposes Resume for a failed
or cancelled Book import and routes it through the owner-verified Jobs control
plane to the same retained-source recovery command.

### Live shadow evidence (2026-08-03)

- Rebuilt the local `book-service` image with the shared `pkg/epubimport` module
  included in the Docker build context. The prior image failed because the Go
  replacement target was absent; `services/book-service/Dockerfile` now copies it.
- Started the rebuilt service with `EPUB_IMPORT_V2_MODE=shadow` against local
  Compose PostgreSQL/MinIO. `GET http://localhost:8205/health` returned `ok`.
- The live `/metrics` endpoint exposed EPUB jobs/items/assets/warnings counters
  and duration/uncompressed-byte histograms. Values were zero because no
  authenticated upload was generated during this check.
- Container inspection confirmed the runtime shadow mode and asset retention
  configuration. Shadow inspection remains source-scoped and non-mutating for
  jobs/chapters.
- Added `TestEPUBShadowCorpusComparison` covering EPUB 3 nested navigation,
  EPUB 2 NCX, and spine fallback through the real inspector and shadow projection.
  The test asserts legacy/V2 chapter counts, delta, navigation source, and the
  fallback warning. This is fixture evidence, not a substitute for authenticated
  production-sample evidence.
- Added a Chromium browser smoke for the authenticated wizard context. It runs
  against the real React route with mocked Book API responses and verifies nested
  ToC preview, selection flow, destructive-strategy warning, durable completion,
  warning summary/details, and report rendering. The runner accepts a system
  Chrome path and optional DevTools port. Local BFF host forwarding currently
  resets connections and the supplied account is not present in the local auth
  database, so a real JWT-backed EPUB upload remains an environment-gated check.

### Authenticated local corpus shadow evidence (2026-08-04)

- Ran every EPUB in the mounted Vasilyev-Andrey corpus (20 files) through the
  authenticated `POST /v1/epub-imports/inspect` and per-source
  `GET /v1/epub-imports/{source_id}/shadow-comparison` flow while the local
  Book Service was explicitly in `shadow` mode.
- All inspections completed. The aggregate legacy projection contains 588
  chapters and the V2 projection contains 570 (net delta: -18). Thirteen files
  had identical count and no recorded structural differences; five had a count
  delta and seven reported one or more structural differences.
- The recorded categories are deterministic: the five count deltas are
  `logical_navigation_count_differs_from_document_projection`, while the two
  same-count structural differences are `navigation_fallback_used`. This
  describes the comparison mechanism; it is not acceptance of a source's
  fallback hierarchy or a reason to discard V2 navigation.
- The disposable authenticated account had zero books after the run. This
  confirms the shadow path retained sources and comparisons only, without
  creating imports, chapters, or books. The service was then recreated with
  `EPUB_IMPORT_V2_MODE=opt_in`; `/health` returned `ok` and container inspection
  confirmed the restored mode.
- This is local corpus evidence, not production approval. The seven differences
  are classified in the EPUB operations runbook: five are accepted
  NCX-authoritative logical-chapter differences and two are accepted
  count-preserving spine fallbacks. Production-cohort differences still require
  the same source-scoped classification before an opt-in cohort can be promoted
  to `default`.

### Local feature-completion gate

The EPUB V2 refactor is complete after a small fixed local corpus passes the
acceptance matrix in `opt_in`: structural selection, import/report, generic
Jobs Resume, cancel/rollback/retry idempotency, assets/links/metadata,
Composition degradation, security limits, and reload/localized UI behavior.
Every failure discovered by that run must be fixed and the relevant regression
rerun. This gate deliberately does not require production traffic, a
production shadow cohort, `default`, `legacy_disabled`, or deleting the legacy
path.

Local evidence recorded on 2026-08-04: shared parser tests, the full Book API
suite on the throwaway Book database, the full worker suite, and Jobs Resume
control tests passed. The wizard's four component regressions, TypeScript/Vite
build, all-locale EPUB translation-key parity, and a Chrome smoke against a
fresh Vite build also passed. English and Russian are translated; the remaining
locales explicitly use the English EPUB fallback. The repository-wide
localization parity command remains red for pre-existing non-EPUB namespace
gaps; it is not an EPUB V2 regression.

### Deferred production promotion

Production must not switch directly from `shadow` to `default`. First collect
authenticated shadow inspections across the fixture corpus and a representative
production sample, and archive chapter counts, deltas, navigation source, and
warnings. Promotion is allowed only when every accepted delta is explained and
there are no unexplained missing/duplicated navigation items or security-limit
violations. Apply the rollout in order: `shadow` evidence window, `opt_in` for a
small cohort with rollback to `shadow`, `default` after a clean cohort window,
then `legacy_disabled` after the retention period. Keep local Compose at
`opt_in`; production `default` requires explicit deployment review and evidence.

## Next checks

1. Keep the legacy combined-HTML chapter path disabled for EPUB V2 and retain
   the opt-in rollout guard until authenticated shadow corpus checks and the
   staged promotion gate above are green.
