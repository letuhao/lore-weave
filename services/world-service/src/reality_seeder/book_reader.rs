//! L5.G.2 — Book-service RPC reader trait.
//!
//! Reads book metadata (initial geography + source locale) needed for
//! the L5.G reality seed flow. The seeder consumes the trait; production
//! binds to a book-service HTTP/JSON client when book-service lands in
//! foundation scope (currently outside this cycle's reach per L5.G
//! brief — the trait keeps the seeder testable + ready for plug-in).
//!
//! ## Why a trait, not a client now?
//!
//! - Cycle-26 brief lists `book_reader.rs` as a stub-acceptable surface
//!   (the artifact ID exists in L5.G but the parent layer plan defers
//!   the live book-service HTTP wiring to the book-service sub-program).
//! - Foundation's interface-first discipline (per cycle-5 + cycle-25
//!   precedent) — depend on traits, bind to clients at wiring time.
//! - Tests inject in-memory fixtures; no Postgres/HTTP needed for unit
//!   coverage of the seeder orchestrator.
//!
//! ## Q-IDs honored
//!
//! - **Q-L5-4** — when book-service ships, the production binding uses
//!   HTTP/JSON V1 (matches glossary_client cycle-25 pattern).

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// Book metadata returned by [`BookReader::get_book`].
///
/// Only carries fields the seeder needs:
/// - `source_locale` — drives Q-L5-2 translation gate.
/// - `title` — audit-only convenience.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BookMetadata {
    /// Book UUID.
    pub book_id: Uuid,
    /// BCP-47 locale the book was authored in.
    pub source_locale: String,
    /// Display title (audit + log convenience; not load-bearing).
    pub title: String,
}

/// Region metadata streamed by [`BookReader::list_regions`].
///
/// V1: regions are not seeded by the canon path (canon entries cover
/// `world.*` and `lore.*` attributes; geography is per-book SSOT and
/// seeded separately by world-gen). The trait carries the surface so
/// downstream cycles can extend without redoing the seeder shape.
///
/// `Eq` is intentionally NOT derived because `area_sq_km` is `f64`
/// (NaN-safety). `PartialEq` is sufficient for fixture comparisons.
#[derive(Debug, Clone, PartialEq)]
pub struct Region {
    /// Region UUID.
    pub region_id: Uuid,
    /// Human-readable region name.
    pub name: String,
    /// Area in square kilometers (f64; NaN-safe — PartialEq only).
    pub area_sq_km: f64,
}

/// Book-service RPC trait — read-only surface used by the L5.G reality
/// seeder. Errors map to [`SeederError`] so the orchestrator routes
/// failures through the unified mark-failed path.
pub trait BookReader {
    /// Returns the book's metadata. The seeder cross-checks
    /// `source_locale` against the SeedRequest to catch caller drift.
    fn get_book(&self, book_id: Uuid) -> Result<BookMetadata, SeederError>;

    /// Streams the regions of a book. V1 default: empty Vec — the
    /// canon-only seeding path doesn't load regions. Override in
    /// production when world-gen is wired in.
    fn list_regions(&self, _book_id: Uuid) -> Result<Vec<Region>, SeederError> {
        Ok(Vec::new())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    struct Fixture {
        books: HashMap<Uuid, BookMetadata>,
    }
    impl BookReader for Fixture {
        fn get_book(&self, book_id: Uuid) -> Result<BookMetadata, SeederError> {
            self.books
                .get(&book_id)
                .cloned()
                .ok_or(SeederError::BookNotFound(book_id))
        }
    }

    #[test]
    fn fixture_returns_book_or_not_found() {
        let bid = Uuid::from_u128(0x1);
        let mut books = HashMap::new();
        books.insert(
            bid,
            BookMetadata {
                book_id: bid,
                source_locale: "en-US".into(),
                title: "T".into(),
            },
        );
        let f = Fixture { books };
        assert_eq!(f.get_book(bid).unwrap().source_locale, "en-US");
        let err = f.get_book(Uuid::from_u128(0x2)).unwrap_err();
        assert!(matches!(err, SeederError::BookNotFound(_)));
    }

    #[test]
    fn list_regions_default_is_empty() {
        struct F;
        impl BookReader for F {
            fn get_book(&self, _book_id: Uuid) -> Result<BookMetadata, SeederError> {
                Err(SeederError::BookNotFound(Uuid::nil()))
            }
        }
        let f = F;
        assert_eq!(f.list_regions(Uuid::from_u128(0x1)).unwrap().len(), 0);
    }
}
