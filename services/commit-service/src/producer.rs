//! PID-A2..A4 — producer identity: prove who sent a proposal, then DERIVE its
//! trust tier from that.
//!
//! ## The defect this closes (doc 25)
//!
//! `Proposal.event_category` was read straight off the wire and selected which
//! validator subset ran — so a message could elect its own trust tier. A
//! proposal writing `"event_category": "T1"` got the reduced player subset and
//! skipped `a5-intent`, `a6-sanitize`, `a6-output` and `canon-drift`: the whole
//! LLM-safety tier, escaped by an LLM-originated proposal claiming to be a
//! player. `producer_service` authorised nothing — it was one third of the
//! dedup triple and never compared to anything.
//!
//! It is the confused-deputy bug already fixed at the WS edge, one layer in.
//! The fix there was not to validate the claim harder; it was to stop reading
//! it. Same here (PID-A1).
//!
//! ## Why a MAC over RAW BYTES (PID-D2)
//!
//! The signature is a polyglot contract — `game-server` is TypeScript, this is
//! Rust — and signing a *structure* would force both languages to agree on a
//! canonical JSON form. Key order, number formatting, and whitespace all
//! differ between `serde_json` and `JSON.stringify`, and every one of them
//! silently invalidates a signature. So the producer MACs the exact bytes it
//! sends and ships the signature as a SIBLING stream field; the verifier MACs
//! those same bytes back. There is no canonical form to disagree about.
//!
//! ## Why HMAC-SHA256 and not blake3 (PID-D1)
//!
//! blake3 is already a dependency here and `keyed_hash` is a fine MAC — but
//! the other end is Node, which has HMAC-SHA256 built in and would need a
//! native/WASM binding for blake3. Put the cost where it is cheapest to carry.

use std::collections::BTreeMap;

use hmac::{Hmac, Mac};
use sha2::Sha256;

use crate::admission::Category;

type HmacSha256 = Hmac<Sha256>;

/// A producer the bus will accept, and the tier its output is admitted under.
#[derive(Debug, Clone)]
pub struct Producer {
    pub name: String,
    /// PID-A3 — the trust tier is a property of WHO SIGNED, so a producer
    /// cannot elect its own validator subset.
    pub category: Category,
    key: Vec<u8>,
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum ProducerError {
    /// Default-DENY (PID-A4): a name not in the registry is refused, never
    /// admitted under some permissive default.
    #[error("unknown producer {0:?}")]
    Unknown(String),
    #[error("missing producer signature")]
    MissingSignature,
    #[error("signature is not valid hex")]
    MalformedSignature,
    #[error("signature does not verify for producer {0:?}")]
    BadSignature(String),
}

/// The set of producers allowed onto the proposal bus.
#[derive(Debug, Clone, Default)]
pub struct ProducerRegistry {
    by_name: BTreeMap<String, Producer>,
}

impl ProducerRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with(mut self, name: &str, category: Category, key: &[u8]) -> Self {
        self.by_name.insert(
            name.to_string(),
            Producer { name: name.to_string(), category, key: key.to_vec() },
        );
        self
    }

    pub fn is_empty(&self) -> bool {
        self.by_name.is_empty()
    }

    /// Load from env (PID-D7). One variable per producer; a producer with no
    /// key is simply ABSENT from the registry rather than present-and-unsigned,
    /// so a misconfiguration fails closed at the first proposal instead of
    /// silently accepting unauthenticated input.
    ///
    /// `LW_PRODUCER_KEY_GAME_SERVER` → `game-server`  (T1 Submitted)
    /// `LW_PRODUCER_KEY_LLM_DRIVER`  → `llm-driver`   (T6 Proposal)
    pub fn from_env() -> Self {
        let mut reg = Self::new();
        if let Ok(k) = std::env::var("LW_PRODUCER_KEY_GAME_SERVER")
            && !k.is_empty()
        {
            reg = reg.with("game-server", Category::T1, k.as_bytes());
        }
        if let Ok(k) = std::env::var("LW_PRODUCER_KEY_LLM_DRIVER")
            && !k.is_empty()
        {
            reg = reg.with("llm-driver", Category::T6, k.as_bytes());
        }
        reg
    }

    /// Verify `sig_hex` over `raw` for the producer named by `hint`, and return
    /// the DERIVED category.
    ///
    /// `hint` comes off the wire and is treated as exactly that — a key-lookup
    /// hint. It selects which key to try; the MAC decides whether the claim was
    /// true. Naming another producer therefore fails at the signature instead
    /// of being believed, and no branch here trusts `hint` for anything but the
    /// lookup.
    pub fn verify_and_derive(
        &self,
        hint: &str,
        raw: &[u8],
        sig_hex: Option<&str>,
    ) -> Result<Category, ProducerError> {
        let producer = self
            .by_name
            .get(hint)
            .ok_or_else(|| ProducerError::Unknown(hint.to_string()))?;

        let sig_hex = sig_hex.ok_or(ProducerError::MissingSignature)?;
        let sig = decode_hex(sig_hex).ok_or(ProducerError::MalformedSignature)?;

        let mut mac = HmacSha256::new_from_slice(&producer.key)
            .expect("HMAC accepts a key of any length");
        mac.update(raw);
        // `verify_slice` is constant-time. A byte-wise `==` here would leak the
        // signature one comparison at a time to anyone able to measure.
        mac.verify_slice(&sig)
            .map_err(|_| ProducerError::BadSignature(producer.name.clone()))?;

        Ok(producer.category)
    }
}

/// Compute the signature a producer must send. Exposed so tests and the
/// polyglot fixture use the SAME function the verifier checks against, rather
/// than a second implementation that could drift into agreement with nothing.
pub fn sign(key: &[u8], raw: &[u8]) -> String {
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC accepts a key of any length");
    mac.update(raw);
    encode_hex(&mac.finalize().into_bytes())
}

fn encode_hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        use std::fmt::Write;
        let _ = write!(s, "{b:02x}");
    }
    s
}

/// Lowercase-or-uppercase hex → bytes. Returns `None` on anything malformed,
/// so a truncated or padded signature is a clean rejection rather than a
/// partial comparison.
fn decode_hex(s: &str) -> Option<Vec<u8>> {
    // `% 2` rather than `is_multiple_of`: the latter post-dates this
    // workspace's MSRV and clippy flags it.
    if s.len() % 2 != 0 {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(s.get(i..i + 2)?, 16).ok())
        .collect()
}
