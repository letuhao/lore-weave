# FB2 Book Import

Status: implemented in source; live browser validation requires a rebuilt local stack and browser runtime.

## Scope

Support FictionBook (`.fb2`) import in two modes:

1. `POST /v1/books/import/fb2` creates an owned novel and queues the source for asynchronous import.
2. `POST /v1/books/{book_id}/import` queues `.fb2` chapters for an existing editable book.

The book service owns the public API, authentication, book/job rows, and import metadata. `worker-infra` owns deterministic source parsing and uses the established asynchronous import path. No new public service or LLM flow is required.

## Fidelity and safety contract

- The worker parses FB2 directly rather than passing it through Pandoc. A parent `<section>` with child sections becomes an HTML part heading; child and leaf sections become chapter/scene heading boundaries consumed by the existing structural parser.
- `title-info` supplies title, annotation, language, genres, authors/translators/keywords; `document-info` and `publish-info` are retained in `book_import_metadata.metadata`.
- Create-mode projects title, annotation, language, genres, and a detected-image cover into `books`/`book_cover_assets`. Existing-book mode records metadata with `applied_to_book=false` and leaves existing book metadata untouched.
- Only the default FB2 body is imported. Named auxiliary bodies, unsafe external links, DTD declarations, non-image binaries, malformed XML, excessive nesting, an image over 10 MiB, or more than 40 MiB decoded image data are rejected or excluded as appropriate.
- Embedded content images are converted to data URIs and pass through the established worker image upload path. The import source and manuscript text are never emitted in logs.

## Schema provenance

FictionBook 2.2 XSD files are vendored in `contracts/schemas/fb2/2.2/` with source URLs, checksums, and upstream licensing. FB2 2.2 retains the 2.0 namespace, which is the runtime compatibility guard. The importer is intentionally a bounded structural parser, not a generic XSD executor.

## Verification

- Synthetic worker tests cover hierarchy, title/description/language/genre metadata, inline images, invalid namespace, DTD rejection, malformed XML, and image limits.
- A PostgreSQL integration regression (gated by `BOOK_TEST_DATABASE_URL`) proves create-mode metadata projection and existing-book preservation.
- A local compatibility smoke accepts `FB2_LOCAL_SMOKE_PATH` so user-provided books can be checked without adding their content to the repository.
