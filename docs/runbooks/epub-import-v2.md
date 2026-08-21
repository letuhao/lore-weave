# EPUB Import V2 Operations

## Signals

Book Service publishes only bounded-label EPUB metrics. Do not add book IDs, users, filenames, source paths, or source text to labels.

- `lw:epub_import_jobs:rate5m_by_outcome` — completed, failed, and warning job rate.
- `lw:epub_import_items:rate5m_by_outcome` — item-level outcome rate.
- `lw:epub_import_warnings:rate5m_by_stage` — durable warning rate for worker, assets, links, composition, and rollback.
- `lw:epub_import_finalize_duration_seconds:p95` — p95 finalization latency.

## Triage

1. Check `lw:epub_import_jobs:rate5m_by_outcome{outcome="failure"}` and the matching Book Service structured log by `job_id`.
2. For `composition` warnings, imports remain finalized; restore Composition and retry the durable job rather than re-uploading the EPUB.
3. For `assets` or `links` warnings, inspect the persisted import report. Do not render source HTML or fetch source URLs from an operator browser.
4. A V2 EPUB import never invokes a provider/model endpoint. Extraction, summaries, translation, and knowledge actions are separate user-confirmed workflows. Treat any provider trace correlated solely with an import job as an incident.

## Performance evidence

Run bounded fixtures in an isolated environment before changing archive limits or worker concurrency. Record fixture chapter count, compressed and uncompressed sizes, wall time, peak RSS, and outcomes; do not record source text. The release targets are 50 chapters / 10 MiB and 500 chapters / 100 MiB.

Baseline (2026-08-04, AMD Ryzen 7 7700, generated deterministic fixtures, one `Inspect` iteration after the XHTML self-closing-tag normalization fix):

| Fixture | Inspect wall time | Throughput |
| --- | ---: | ---: |
| 50 chapters / 10 MiB | 123 ms | 85.46 MiB/s |
| 500 chapters / 100 MiB | 1.25 s | 83.76 MiB/s |

These are parser-only measurements, not an end-to-end SLA. Repeat the command below after parser or limit changes:

```sh
cd pkg/epubimport
go test -run '^$' -bench BenchmarkInspectReferenceEPUBs -benchtime=1x
```

## Shadow rollout evidence

The 2026-08-04 authenticated local shadow run used every file in the mounted
Vasilyev-Andrey EPUB corpus (20 files). It completed all inspections without
creating a book for the disposable account. Legacy projection totalled 588
chapters; V2 totalled 570 (net delta: -18). Thirteen files had no recorded
comparison difference, five had a chapter-count delta, and seven had one or more
structural differences. The five count deltas reported
`logical_navigation_count_differs_from_document_projection`; the other two
reported `navigation_fallback_used` with equal counts.

### Local shadow classification (2026-08-04)

The following source-scoped differences were inspected from their EPUB package
topology only (OPF manifest/spine and NCX/navigation references; no source text
was recorded). They are accepted for the local shadow corpus under the V2
decision that declared navigation is authoritative over a legacy one-spine-file
projection. This is not production-cohort acceptance.

| Source SHA-256 prefix | Legacy | V2 | Classification | Rationale |
| --- | ---: | ---: | --- | --- |
| `a2bcc052` | 216 | 207 | Accepted navigation difference | Valid EPUB2 NCX has 207 selected logical leaves across 206 content documents; legacy counts document projection instead. |
| `2f94fc2f` | 42 | 40 | Accepted navigation difference | Valid EPUB2 NCX supplies 40 selected logical leaves; legacy counts two additional linear documents. |
| `57c4e159` | 20 | 18 | Accepted navigation difference | Valid EPUB2 NCX supplies 18 logical leaves across 17 documents, including one same-document fragment split. |
| `ac39ca62` | 26 | 22 | Accepted navigation difference | Valid EPUB2 NCX supplies 22 logical leaves across 20 documents, including fragment-level chapter boundaries. |
| `20bc0f74` | 35 | 34 | Accepted navigation difference | Valid EPUB2 NCX supplies 34 logical leaves across 33 documents, including one fragment-level chapter boundary. |
| `4d1f39a4` | 2 | 2 | Accepted fallback | No EPUB navigation was present; V2 spine fallback selected both linear documents. |
| `8a01592d` | 1 | 1 | Accepted fallback | No EPUB navigation was present; V2 spine fallback selected the single linear document. |

Some NCX cases include linear documents not referenced by the navigation. They
remain retained source material rather than implicit chapters: automatically
promoting them would contradict the selected-navigation contract and recreate
the legacy document-projection behavior. Any production source with an
incomplete or disputed table of contents must be corrected at the source or
handled through an explicitly reviewed import policy; do not silently change
V2 selection semantics during rollout.

### Local refactor acceptance

For early-stage development, close EPUB V2 after a fixed local corpus passes in
`EPUB_IMPORT_V2_MODE=opt_in`. Record evidence for: navigation and selection;
finalized chapter/provenance/report counts; generic Jobs Resume after a failure;
cancel, rollback, and retry idempotency; assets, links, metadata, and cover;
Composition success and degraded warning; typed unsafe-archive rejection; and
reload plus English/Russian UI behavior. A failure in this matrix is a product
defect and must receive a regression before feature closure.

Production `shadow`, cohort, `default`, and `legacy_disabled` decisions are a
separate operational follow-up. When that work is explicitly in scope, classify
each production-cohort difference using its source-scoped comparison and return
the service to `EPUB_IMPORT_V2_MODE=opt_in` after any shadow window unless a
reviewed deployment decision says otherwise.

### Local acceptance evidence (2026-08-04)

The shared parser suite, Book Service API suite against the throwaway
`loreweave_book_test` database, worker suite, and Jobs Resume control suite
passed. The EPUB wizard component regression (four cases), frontend
TypeScript/Vite build, all-locale EPUB translation-key parity, and Chrome smoke
against a fresh Vite build also passed. English and Russian are translated; the
remaining locales explicitly use the English EPUB fallback. The repository-wide
localization parity command remains red for existing non-EPUB namespace gaps;
that unrelated debt is not evidence of an EPUB V2 failure.
