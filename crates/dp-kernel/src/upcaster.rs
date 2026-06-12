//! L2.H Upcaster chain library (R03 §12C.3).
//!
//! # Design
//!
//! An [`Upcaster`] is a function from `(payload_json_at_vN)` →
//! `payload_json_at_vN+1`. Each registered upcaster declares a SINGLE
//! one-step hop. The library composes hops into chains automatically:
//!
//! ```text
//!   upcast(payload, type="npc.said", from=1, to=3)
//!     = upcaster_v2(upcaster_v1to2(payload))   (transitively v1→v2→v3)
//! ```
//!
//! # Invariants
//!
//! - **Forward-only.** `from >= to` is rejected (no downcast). Downcasting
//!   would lose information added in later versions; replay determinism would
//!   break.
//! - **Idempotent at the no-op step.** `upcast(payload, from=v, to=v)` returns
//!   the payload unchanged (no upcaster lookup).
//! - **Total-chain or fail-loud.** A missing intermediate hop (e.g. v2→v3 not
//!   registered while v1→v2 and v3→v4 are) causes [`EventError::MissingUpcaster`]
//!   — the chain composer does NOT silently skip.
//! - **Replay-safe.** Upcasters MUST be pure (no IO, no global state). The
//!   library cannot enforce purity at compile time; the L2.H test suite
//!   asserts byte-determinism (`upcast(v1,3) == upcast(upcast(v1,2),3)`).
//!
//! # Wire compatibility
//!
//! The Go side at `contracts/events/upcasters_go/` mirrors this trait shape.
//! Both sides operate on `serde_json::Value` (Rust) / `map[string]any` (Go)
//! payloads. The L2.G `eventgen` tool can stitch a per-language dispatch
//! table from `@upcast` annotations in cycle 9+ — for cycle 8 we register
//! upcasters by hand at service init.

use std::collections::HashMap;

use serde_json::Value;

use crate::errors::EventError;

/// A single one-step upcaster: payload at `version_from` → payload at
/// `version_from + 1`. Implementors are typically free functions:
///
/// ```rust,ignore
/// fn npc_said_v1_to_v2(p: Value) -> Result<Value, String> {
///     // add the `tone` field with default "neutral"
///     let mut obj = p.as_object().cloned().unwrap_or_default();
///     obj.insert("tone".into(), Value::String("neutral".into()));
///     Ok(Value::Object(obj))
/// }
/// ```
pub trait Upcaster: Send + Sync {
    /// Source schema version this upcaster reads from.
    fn version_from(&self) -> u32;

    /// Apply the transformation. Returns the new payload at `version_from + 1`.
    /// Errors are surfaced as `String` so concrete impls don't need a shared
    /// error type; the registry wraps into [`EventError::UpcasterFailed`].
    fn apply(&self, payload: Value) -> Result<Value, String>;
}

/// FnUpcaster is a thin adapter so callers can register a plain `fn` or
/// closure without writing a struct.
pub struct FnUpcaster<F: Fn(Value) -> Result<Value, String> + Send + Sync + 'static> {
    from: u32,
    func: F,
}

impl<F> FnUpcaster<F>
where
    F: Fn(Value) -> Result<Value, String> + Send + Sync + 'static,
{
    pub fn new(version_from: u32, func: F) -> Self {
        Self { from: version_from, func }
    }
}

impl<F> Upcaster for FnUpcaster<F>
where
    F: Fn(Value) -> Result<Value, String> + Send + Sync + 'static,
{
    fn version_from(&self) -> u32 {
        self.from
    }
    fn apply(&self, payload: Value) -> Result<Value, String> {
        (self.func)(payload)
    }
}

/// UpcasterChain is the per-event_type ordered series of one-step upcasters.
/// Use [`UpcasterRegistry`] to build it from individually-registered hops.
pub struct UpcasterChain<'a> {
    pub event_type: &'a str,
    pub steps: Vec<&'a dyn Upcaster>, // each step.version_from() = N; produces N+1
}

impl<'a> UpcasterChain<'a> {
    /// Apply each step in order. `payload` is at version `from`; output is at
    /// version `from + steps.len()`.
    pub fn apply(&self, payload: Value, from: u32) -> Result<Value, EventError> {
        let mut v = payload;
        let mut cur = from;
        for s in &self.steps {
            if s.version_from() != cur {
                return Err(EventError::MissingUpcaster {
                    event_type: self.event_type.to_string(),
                    from: cur,
                    to: cur + 1,
                });
            }
            v = s.apply(v).map_err(|e| EventError::UpcasterFailed {
                event_type: self.event_type.to_string(),
                from: cur,
                to: cur + 1,
                detail: e,
            })?;
            cur += 1;
        }
        Ok(v)
    }
}

/// UpcasterRegistry maps `(event_type, from_version)` → upcaster instance.
/// Build at service init (one call per `@upcast` declaration), then look up
/// via [`UpcasterRegistry::chain`] when reading historical events.
#[derive(Default)]
pub struct UpcasterRegistry {
    by_key: HashMap<(String, u32), Box<dyn Upcaster>>,
}

impl UpcasterRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    /// Register one one-step upcaster. Panics on duplicate registration so
    /// drift is caught at service init (not in production).
    pub fn register(&mut self, event_type: impl Into<String>, upcaster: Box<dyn Upcaster>) {
        let key = (event_type.into(), upcaster.version_from());
        assert!(
            !self.by_key.contains_key(&key),
            "duplicate upcaster for {:?}",
            key
        );
        self.by_key.insert(key, upcaster);
    }

    /// Build the chain from `from` to `to`. Returns
    /// [`EventError::BackwardUpcast`] when `from >= to`. Returns
    /// [`EventError::MissingUpcaster`] on the first gap.
    pub fn chain<'a>(&'a self, event_type: &'a str, from: u32, to: u32) -> Result<UpcasterChain<'a>, EventError> {
        if from > to {
            return Err(EventError::BackwardUpcast {
                event_type: event_type.to_string(),
                from,
                to,
            });
        }
        if from == to {
            // no-op chain
            return Ok(UpcasterChain {
                event_type,
                steps: vec![],
            });
        }
        let mut steps: Vec<&dyn Upcaster> = Vec::with_capacity((to - from) as usize);
        let mut cur = from;
        while cur < to {
            let s = self
                .by_key
                .get(&(event_type.to_string(), cur))
                .ok_or_else(|| EventError::MissingUpcaster {
                    event_type: event_type.to_string(),
                    from: cur,
                    to: cur + 1,
                })?;
            steps.push(s.as_ref());
            cur += 1;
        }
        Ok(UpcasterChain {
            event_type,
            steps,
        })
    }

    /// Convenience: apply the registered chain end-to-end. Equivalent to
    /// `self.chain(t, from, to)?.apply(payload, from)`.
    pub fn upcast(&self, event_type: &str, payload: Value, from: u32, to: u32) -> Result<Value, EventError> {
        let chain = self.chain(event_type, from, to)?;
        chain.apply(payload, from)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn npc_said_v1_to_v2(p: Value) -> Result<Value, String> {
        let mut obj = p.as_object().cloned().unwrap_or_default();
        obj.insert("tone".into(), Value::String("neutral".into()));
        Ok(Value::Object(obj))
    }

    fn npc_said_v2_to_v3(p: Value) -> Result<Value, String> {
        let mut obj = p.as_object().cloned().unwrap_or_default();
        obj.insert("intent".into(), Value::String("statement".into()));
        Ok(Value::Object(obj))
    }

    fn registry_with_v1_v2_v3() -> UpcasterRegistry {
        let mut r = UpcasterRegistry::new();
        r.register("npc.said", Box::new(FnUpcaster::new(1, npc_said_v1_to_v2)));
        r.register("npc.said", Box::new(FnUpcaster::new(2, npc_said_v2_to_v3)));
        r
    }

    #[test]
    fn upcast_v1_to_v2() {
        let r = registry_with_v1_v2_v3();
        let out = r.upcast("npc.said", json!({"text": "hi"}), 1, 2).unwrap();
        assert_eq!(out["text"], "hi");
        assert_eq!(out["tone"], "neutral");
    }

    #[test]
    fn upcast_v1_to_v3_chains() {
        let r = registry_with_v1_v2_v3();
        let out = r.upcast("npc.said", json!({"text": "hi"}), 1, 3).unwrap();
        assert_eq!(out["text"], "hi");
        assert_eq!(out["tone"], "neutral");
        assert_eq!(out["intent"], "statement");
    }

    #[test]
    fn chain_byte_deterministic() {
        // upcast(v1, target=3) == upcast(upcast(v1, target=2), target=3)
        let r = registry_with_v1_v2_v3();
        let direct = r.upcast("npc.said", json!({"text": "hi"}), 1, 3).unwrap();
        let two_step = {
            let mid = r.upcast("npc.said", json!({"text": "hi"}), 1, 2).unwrap();
            r.upcast("npc.said", mid, 2, 3).unwrap()
        };
        assert_eq!(direct, two_step, "two-step != one-shot");
    }

    #[test]
    fn no_op_when_from_equals_to() {
        let r = registry_with_v1_v2_v3();
        let payload = json!({"text": "hi", "tone": "angry"});
        let out = r.upcast("npc.said", payload.clone(), 2, 2).unwrap();
        assert_eq!(out, payload, "from==to should be no-op");
    }

    #[test]
    fn backward_upcast_rejected() {
        let r = registry_with_v1_v2_v3();
        let err = r
            .upcast("npc.said", json!({"text": "hi"}), 3, 2)
            .unwrap_err();
        assert!(matches!(err, EventError::BackwardUpcast { .. }), "got {:?}", err);
    }

    #[test]
    fn missing_intermediate_upcaster_rejected() {
        let mut r = UpcasterRegistry::new();
        // only v2->v3 registered; v1->v2 missing
        r.register("npc.said", Box::new(FnUpcaster::new(2, npc_said_v2_to_v3)));
        let err = r
            .upcast("npc.said", json!({"text": "hi"}), 1, 3)
            .unwrap_err();
        match err {
            EventError::MissingUpcaster { event_type, from, to } => {
                assert_eq!(event_type, "npc.said");
                assert_eq!(from, 1);
                assert_eq!(to, 2);
            }
            other => panic!("expected MissingUpcaster, got {:?}", other),
        }
    }

    #[test]
    fn unknown_event_type_is_missing_upcaster() {
        let r = UpcasterRegistry::new();
        let err = r
            .upcast("nonexistent.event", json!({}), 1, 2)
            .unwrap_err();
        assert!(matches!(err, EventError::MissingUpcaster { .. }), "got {:?}", err);
    }

    #[test]
    #[should_panic(expected = "duplicate upcaster")]
    fn duplicate_registration_panics() {
        let mut r = UpcasterRegistry::new();
        r.register("npc.said", Box::new(FnUpcaster::new(1, npc_said_v1_to_v2)));
        // Re-register same from-version → panic at init.
        r.register("npc.said", Box::new(FnUpcaster::new(1, npc_said_v1_to_v2)));
    }

    #[test]
    fn upcaster_failure_wrapped() {
        fn failing(_p: Value) -> Result<Value, String> {
            Err("payload broken".to_string())
        }
        let mut r = UpcasterRegistry::new();
        r.register("foo.bar", Box::new(FnUpcaster::new(1, failing)));
        let err = r.upcast("foo.bar", json!({}), 1, 2).unwrap_err();
        match err {
            EventError::UpcasterFailed { event_type, from, to, detail } => {
                assert_eq!(event_type, "foo.bar");
                assert_eq!(from, 1);
                assert_eq!(to, 2);
                assert!(detail.contains("payload broken"));
            }
            other => panic!("expected UpcasterFailed, got {:?}", other),
        }
    }
}
