//! The canonical encoding a [`crate::RulesetDigest`] is taken over.
//!
//! **RLS-D5 — canonical encoding is part of the CONTRACT, not an implementation
//! detail.** Deterministic field order, no floats, no maps with
//! nondeterministic iteration order. The reason is stated in doc 16 and it is
//! the uncomfortable one: *a digest that varies by serializer version is worse
//! than no digest, because it fails loudly and WRONGLY* — every replay reports
//! a mismatch that isn't one, and the operator learns to ignore the alarm.
//!
//! So this is hand-written rather than `serde`-derived. `serde` would make the
//! bytes a function of a dependency's version and its attribute defaults; here
//! they are a function of exactly the code in this file.
//!
//! ## Why fixed-width big-endian, with no length prefixes
//!
//! Every value written is a fixed-width integer, which makes the stream
//! self-delimiting: there is no `("ab","c")` vs `("a","bc")` collision to
//! defend against because no field has a variable length. If a variable-length
//! field is ever added (a string ID, a `Vec<RaceDecl>`), it MUST be written
//! through [`Canon::bytes`] or [`Canon::seq_len`], which length-prefix — and
//! the doc comment on each says why.

/// A growable canonical byte buffer.
///
/// Deliberately not `Write`/`serde::Serializer`: the whole value of this type
/// is that the set of things it can encode is small and explicit.
#[derive(Debug, Default)]
pub struct Canon {
    buf: Vec<u8>,
}

impl Canon {
    /// Start a canonical stream for one artifact kind.
    ///
    /// The domain-separation tag is written first so that two DIFFERENT
    /// artifacts which happen to encode to the same field bytes (e.g. a
    /// `CombatRules` and some future `TravelRules` with the same integer
    /// layout) cannot collide onto one digest. Standard hash domain
    /// separation; cheap, and impossible to retrofit once digests are in a log.
    pub fn new(domain: &'static str) -> Self {
        let mut c = Self { buf: Vec::with_capacity(256) };
        c.bytes(domain.as_bytes());
        c
    }

    pub fn u8(&mut self, v: u8) {
        self.buf.push(v);
    }

    pub fn u32(&mut self, v: u32) {
        self.buf.extend_from_slice(&v.to_be_bytes());
    }

    /// Two's-complement big-endian. Negative rule values are legitimate
    /// (`resist_pm` could be negative in a ruleset that grants vulnerability),
    /// and `as u32` casts would encode `-1` and `u32::MAX` identically.
    pub fn i32(&mut self, v: i32) {
        self.buf.extend_from_slice(&v.to_be_bytes());
    }

    pub fn i64(&mut self, v: i64) {
        self.buf.extend_from_slice(&v.to_be_bytes());
    }

    /// Length-prefixed. Required for anything variable-length, so that
    /// concatenation is unambiguous.
    pub fn bytes(&mut self, v: &[u8]) {
        self.u32(v.len() as u32);
        self.buf.extend_from_slice(v);
    }

    /// Write the length of a sequence before its elements.
    ///
    /// A fixed-size array (`[i32; SLOT_COUNT]`) does not strictly need this,
    /// but writing it makes a change to `SLOT_COUNT` move the digest even if
    /// the added slot's default happens to be `0` — which is exactly the
    /// silent case a length-free encoding would miss.
    pub fn seq_len(&mut self, n: usize) {
        self.u32(n as u32);
    }

    pub fn i32_slice(&mut self, v: &[i32]) {
        self.seq_len(v.len());
        for x in v {
            self.i32(*x);
        }
    }

    pub fn finish(self) -> Vec<u8> {
        self.buf
    }

    /// Exposed for tests that assert on encoding shape rather than on the
    /// digest — `len()` moving is the cheap signal that a field was added.
    pub fn as_bytes(&self) -> &[u8] {
        &self.buf
    }
}

/// Anything that contributes to a ruleset digest.
///
/// **Every implementation MUST open with an exhaustive destructuring pattern —
/// `let Self { a, b, c } = self;` with NO `..`.** That is the mechanism which
/// makes "you added a field and forgot to hash it" a compile error (E0027,
/// *pattern does not mention field*) instead of a digest that silently stops
/// covering the new field.
///
/// It is not a complete mechanism and must not be described as one. The gap:
/// a field that is bound and then encoded from the WRONG binding still
/// compiles (an unused binding is only a warning). The per-field perturbation
/// test in each module closes that half. Two mechanisms, each catching what
/// the other misses — see §4 of the F1 plan.
///
/// This is the same shape as `ModifierSource::ALL` (a closed set with a
/// hand-written companion list), and the lesson from that bug (XST-D7) was
/// that calling a companion list a *guard* is the actual defect. So: the
/// destructuring IS a mechanism; the perturbation table is discipline that the
/// golden-digest test makes hard to skip.
pub trait CanonEncode {
    fn canon(&self, c: &mut Canon);
}
