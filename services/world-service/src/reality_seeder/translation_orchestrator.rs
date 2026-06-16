//! L5.G.5 — Translation orchestrator (M-REV-5 + Q-L5-2 gate).
//!
//! Per **Q-L5-2 LOCKED** (OPEN_QUESTIONS_LOCKED §7 line 106):
//!
//! > translation-service for reality seeding (M-REV-5) — V1 if
//! > reality.locale != book.source_locale per M-REV-5
//!
//! The orchestrator is constructed by the seeder ONLY when locales
//! differ; it then transforms each canon entry's `value` JSON via the
//! injected `TranslationGateway`. When locales match, no orchestrator
//! is constructed and the value bytes pass through untouched (saving
//! one RPC call per canon entry).
//!
//! ## Why a separate module vs inline in mod.rs?
//!
//! The orchestrator owns:
//! - the locale-pair state (from/to),
//! - the gateway lifetime borrow,
//! - audit hook integration (per-translation row),
//! - future retry/batch logic (translation-service may support batch
//!   translate-many-strings in a single RPC; that optimization lands in
//!   the translation-service sub-program without touching seeder code).
//!
//! Separating it now keeps the seeder orchestrator focused on flow
//! control and the translation orchestrator focused on per-entry
//! mutation.
//!
//! ## Q-IDs honored
//!
//! - **Q-L5-2** — translation ONLY when locales differ. Enforced
//!   structurally: orchestrator constructor takes both locales but the
//!   SEEDER (mod.rs) checks `req.requires_translation()` before
//!   constructing this type. Defensive: even if a caller constructs
//!   the orchestrator with equal locales, `translate_entry` becomes a
//!   no-op pass-through (see fast-path check).
//! - **Q-L5-4** — translation-service is talked to via HTTP/JSON in
//!   production (matches glossary_client pattern); the trait keeps
//!   the seeder testable without a tokio dependency.

use crate::reality_seeder::{CanonProjectionIntent, SeederError};

/// Translation-service RPC trait. Production binds to a translation-
/// service HTTP/JSON client; tests inject in-memory fakes that mutate
/// the value bytes deterministically so unit tests can assert the gate
/// fired.
pub trait TranslationGateway {
    /// Translate `value` JSON bytes from BCP-47 locale `from` to `to`.
    /// Returns the translated bytes (same JSON shape; only string-typed
    /// values are translated in production, but the trait surface is
    /// opaque — the gateway decides).
    fn translate(&mut self, from: &str, to: &str, value: Vec<u8>) -> Result<Vec<u8>, SeederError>;
}

/// L5.G.5 orchestrator. Borrows the gateway for the duration of the
/// seed run; constructed by the seeder when Q-L5-2 fires.
pub struct TranslationOrchestrator<'a, T: TranslationGateway> {
    gateway: &'a mut T,
    from_locale: String,
    to_locale: String,
}

impl<'a, T: TranslationGateway> TranslationOrchestrator<'a, T> {
    /// Construct. Caller guarantees `from_locale != to_locale` per
    /// Q-L5-2 — but we cache the comparison so the fast-path check in
    /// `translate_entry` is a single equality.
    pub fn new(gateway: &'a mut T, from_locale: String, to_locale: String) -> Self {
        Self { gateway, from_locale, to_locale }
    }

    /// Translate one canon entry's value field. If the locales happen
    /// to be equal (defensive fast-path), returns the intent unchanged
    /// without an RPC call.
    pub fn translate_entry(
        &mut self,
        mut intent: CanonProjectionIntent,
    ) -> Result<CanonProjectionIntent, SeederError> {
        if self.from_locale.eq_ignore_ascii_case(&self.to_locale) {
            // Defensive fast-path — Q-L5-2 says callers shouldn't
            // construct us when locales match, but be safe.
            return Ok(intent);
        }
        let translated = self.gateway.translate(
            &self.from_locale,
            &self.to_locale,
            intent.value.clone(),
        )?;
        intent.value = translated;
        Ok(intent)
    }

    /// Expose the locale pair for audit/log integration.
    pub fn locale_pair(&self) -> (&str, &str) {
        (&self.from_locale, &self.to_locale)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use uuid::Uuid;

    struct Recorder {
        calls: RefCell<Vec<(String, String, Vec<u8>)>>,
        fail: bool,
    }
    impl TranslationGateway for Recorder {
        fn translate(
            &mut self,
            from: &str,
            to: &str,
            value: Vec<u8>,
        ) -> Result<Vec<u8>, SeederError> {
            self.calls
                .borrow_mut()
                .push((from.into(), to.into(), value.clone()));
            if self.fail {
                return Err(SeederError::Translation("simulated".into()));
            }
            let mut v = value;
            v.extend(format!("::{from}->{to}").as_bytes());
            Ok(v)
        }
    }

    fn intent_with(value: &[u8]) -> CanonProjectionIntent {
        CanonProjectionIntent {
            reality_id: Uuid::from_u128(0x1),
            canon_entry_id: Uuid::from_u128(0x2),
            book_id: Uuid::from_u128(0x3),
            attribute_path: "world.climate".into(),
            value: value.to_vec(),
            canon_layer: "L2_seeded".into(),
            lock_level: "soft".into(),
            source_event_id: Uuid::from_u128(0x4),
            seed_marker: true,
        }
    }

    #[test]
    fn translates_when_locales_differ_q_l5_2() {
        let mut g = Recorder {
            calls: RefCell::new(Vec::new()),
            fail: false,
        };
        let mut t = TranslationOrchestrator::new(&mut g, "en-US".into(), "vi-VN".into());
        let out = t.translate_entry(intent_with(b"\"hello\"")).unwrap();
        assert!(out
            .value
            .windows(b"::en-US->vi-VN".len())
            .any(|w| w == b"::en-US->vi-VN"));
        assert_eq!(g.calls.borrow().len(), 1);
    }

    #[test]
    fn fast_path_no_op_when_locales_match() {
        let mut g = Recorder {
            calls: RefCell::new(Vec::new()),
            fail: false,
        };
        let mut t = TranslationOrchestrator::new(&mut g, "en-US".into(), "en-US".into());
        let inp = intent_with(b"\"hello\"");
        let out = t.translate_entry(inp.clone()).unwrap();
        assert_eq!(out.value, inp.value);
        assert!(g.calls.borrow().is_empty()); // no RPC call
    }

    #[test]
    fn fast_path_case_insensitive() {
        let mut g = Recorder {
            calls: RefCell::new(Vec::new()),
            fail: false,
        };
        let mut t = TranslationOrchestrator::new(&mut g, "en-US".into(), "en-us".into());
        let _ = t.translate_entry(intent_with(b"\"x\"")).unwrap();
        assert!(g.calls.borrow().is_empty());
    }

    #[test]
    fn translation_failure_bubbles_up() {
        let mut g = Recorder {
            calls: RefCell::new(Vec::new()),
            fail: true,
        };
        let mut t = TranslationOrchestrator::new(&mut g, "en-US".into(), "vi-VN".into());
        let err = t.translate_entry(intent_with(b"\"x\"")).unwrap_err();
        assert!(matches!(err, SeederError::Translation(_)));
    }

    #[test]
    fn locale_pair_exposed_for_audit() {
        let mut g = Recorder {
            calls: RefCell::new(Vec::new()),
            fail: false,
        };
        let t = TranslationOrchestrator::new(&mut g, "en-US".into(), "vi-VN".into());
        assert_eq!(t.locale_pair(), ("en-US", "vi-VN"));
    }
}
