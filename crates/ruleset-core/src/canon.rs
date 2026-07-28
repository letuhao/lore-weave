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

/// Reads back what [`Canon`] wrote.
///
/// **This is the risky half of the encoding and it is worth saying why.** The
/// encoder defines the field order and widths; the decoder has to mirror them
/// exactly — a mirror hazard inside a single language, with no compiler
/// checking the correspondence. Neither exhaustive destructuring nor the
/// perturbation table helps here: both live on the encode side.
///
/// The mechanism is the **round-trip property test over randomised rulesets**
/// in `tests/digest.rs`. Any asymmetry surfaces on the first field that
/// disagrees, for arbitrary values rather than for the one default the golden
/// test pins.
///
/// It refuses rather than guesses: a wrong domain tag, an unknown schema
/// version, a short read, or TRAILING BYTES are all errors. A decoder that
/// tolerates trailing bytes will happily read a truncated artifact into
/// something plausible — and "plausible" is the failure mode this whole arc has
/// been eliminating.
#[derive(Debug)]
pub struct CanonReader<'a> {
    buf: &'a [u8],
    pos: usize,
}

/// Why a canonical stream could not be read.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CanonError {
    /// The stream does not begin with the expected domain-separation tag.
    WrongDomain { expected: &'static str },
    /// Ran out of bytes mid-field — a truncated artifact.
    ShortRead { need: usize, have: usize },
    /// Bytes remain after the last declared field. Either the artifact was
    /// written by a NEWER encoder, or it is not what it claims to be; both are
    /// refusals, because the alternative is decoding a prefix and calling it
    /// the whole ruleset.
    TrailingBytes { remaining: usize },
    /// A `schema_version` this build does not know how to read.
    UnknownSchemaVersion { found: u32, known: u32 },
    /// A length prefix that does not match the fixed-size array it decodes into.
    LengthMismatch { field: &'static str, expected: usize, found: usize },
}

impl core::fmt::Display for CanonError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::WrongDomain { expected } => {
                write!(f, "canonical stream is not a `{expected}`")
            }
            Self::ShortRead { need, have } => {
                write!(f, "truncated canonical stream: needed {need} more bytes, had {have}")
            }
            Self::TrailingBytes { remaining } => write!(
                f,
                "{remaining} trailing byte(s) after the last field - refusing to \
                 decode a prefix and call it the whole ruleset"
            ),
            Self::UnknownSchemaVersion { found, known } => write!(
                f,
                "ruleset schema version {found}, this build reads {known} - a stored \
                 ruleset is never reinterpreted (RLS-D18)"
            ),
            Self::LengthMismatch { field, expected, found } => {
                write!(f, "`{field}`: expected {expected} elements, stream declares {found}")
            }
        }
    }
}

impl<'a> CanonReader<'a> {
    /// Open a stream, checking the domain tag first.
    pub fn new(buf: &'a [u8], domain: &'static str) -> Result<Self, CanonError> {
        let mut r = Self { buf, pos: 0 };
        let tag = r.bytes()?;
        if tag != domain.as_bytes() {
            return Err(CanonError::WrongDomain { expected: domain });
        }
        Ok(r)
    }

    fn take(&mut self, n: usize) -> Result<&'a [u8], CanonError> {
        if self.pos + n > self.buf.len() {
            return Err(CanonError::ShortRead { need: n, have: self.buf.len() - self.pos });
        }
        let out = &self.buf[self.pos..self.pos + n];
        self.pos += n;
        Ok(out)
    }

    pub fn u8(&mut self) -> Result<u8, CanonError> {
        Ok(self.take(1)?[0])
    }

    pub fn u32(&mut self) -> Result<u32, CanonError> {
        Ok(u32::from_be_bytes(self.take(4)?.try_into().unwrap()))
    }

    pub fn i32(&mut self) -> Result<i32, CanonError> {
        Ok(i32::from_be_bytes(self.take(4)?.try_into().unwrap()))
    }

    pub fn i64(&mut self) -> Result<i64, CanonError> {
        Ok(i64::from_be_bytes(self.take(8)?.try_into().unwrap()))
    }

    pub fn bytes(&mut self) -> Result<&'a [u8], CanonError> {
        let n = self.u32()? as usize;
        self.take(n)
    }

    /// Read a length-prefixed sequence into a fixed-size array.
    ///
    /// The length is CHECKED, not skipped: an artifact written when
    /// `SLOT_COUNT` was 10 must not silently half-fill an 11-slot array.
    pub fn i32_array<const N: usize>(
        &mut self,
        field: &'static str,
    ) -> Result<[i32; N], CanonError> {
        let n = self.u32()? as usize;
        if n != N {
            return Err(CanonError::LengthMismatch { field, expected: N, found: n });
        }
        let mut out = [0i32; N];
        for slot in out.iter_mut() {
            *slot = self.i32()?;
        }
        Ok(out)
    }

    /// Assert the stream is fully consumed. Call at the end of every decode.
    pub fn finish(self) -> Result<(), CanonError> {
        let remaining = self.buf.len() - self.pos;
        if remaining != 0 {
            return Err(CanonError::TrailingBytes { remaining });
        }
        Ok(())
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
