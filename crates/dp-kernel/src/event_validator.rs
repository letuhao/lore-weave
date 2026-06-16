//! L2.I Schema validation on write (R03 §12C.4).
//!
//! # Contract
//!
//! Every event-append code path MUST call [`ValidatorRegistry::validate`]
//! BEFORE writing the event to durable storage. A malformed event rejected
//! here (returns [`crate::errors::EventError::SchemaViolation`] or
//! `UnknownSchema`) is preferable in every dimension to a malformed event
//! caught at projection-rebuild time months later.
//!
//! Per R03 §12C.4: `storage.events.schema_validation.enabled=true` is
//! enforced in ALL envs — there is NO dev bypass. Local-dev gets the same
//! validation as production.
//!
//! # Why a "descriptor" instead of a schema language
//!
//! V1 ships a minimal field-presence + type-tag descriptor. We did NOT pick
//! JSON Schema / Protobuf / Avro for V1 because:
//!
//! - The L2.F registry already names the canonical Go struct; the validator's
//!   job is to confirm the payload deserializes into that struct cleanly.
//!   (Cycle 9+ can add a `serde`-derived deserializer step that subsumes the
//!   descriptor entirely.)
//! - JSON Schema in Rust adds 5+ deps and runtime cost we don't need yet.
//! - V2+ may swap to a richer schema language (tracked
//!   D-DP-KERNEL-RICH-SCHEMA in DEFERRED).
//!
//! # Wire compatibility
//!
//! Go side mirrors at `contracts/events/validators_go/`. Both implementations
//! consult the same `_registry.yaml` so behavior matches across languages.

use std::collections::{HashMap, HashSet};

use serde_json::Value;

use crate::errors::EventError;

/// One descriptor per (event_type, event_version). Field presence + a tiny
/// type-tag set. The Go side has the equivalent struct.
#[derive(Debug, Clone)]
pub struct SchemaDescriptor {
    pub event_type: String,
    pub event_version: u32,
    /// Required fields. Must all be present in the payload object.
    pub required_fields: Vec<RequiredField>,
}

#[derive(Debug, Clone)]
pub struct RequiredField {
    pub name: String,
    pub ty: FieldType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FieldType {
    /// Any JSON string. Includes UUIDs + RFC3339 timestamps (we don't
    /// validate the inner format here; the consuming `serde_json::from_value`
    /// step into the typed struct does).
    String,
    /// `serde_json::Number` — int or float.
    Number,
    /// `true` or `false`.
    Bool,
    /// JSON object.
    Object,
    /// JSON array.
    Array,
}

impl FieldType {
    pub fn matches(&self, v: &Value) -> bool {
        match self {
            FieldType::String => v.is_string(),
            FieldType::Number => v.is_number(),
            FieldType::Bool => v.is_boolean(),
            FieldType::Object => v.is_object(),
            FieldType::Array => v.is_array(),
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            FieldType::String => "string",
            FieldType::Number => "number",
            FieldType::Bool => "boolean",
            FieldType::Object => "object",
            FieldType::Array => "array",
        }
    }
}

/// EventValidator validates a single event payload against its descriptor.
///
/// Split into its own trait so callers can stub it in tests (without going
/// through [`ValidatorRegistry`]). Default impl uses field-presence + type-tag
/// matching; cycle 9+ may add a `serde`-deserialize-into-struct step.
pub trait EventValidator: Send + Sync {
    fn validate(&self, descriptor: &SchemaDescriptor, payload: &Value) -> Result<(), EventError>;
}

/// Default field-presence + type-tag validator. Behavior:
///
/// 1. Payload MUST be a JSON object.
/// 2. Every `descriptor.required_fields[*].name` MUST be present.
/// 3. Field type must match the descriptor `FieldType`.
/// 4. NO unknown-field rejection (additive-first per R03 §12C.5 — new fields
///    appear in vN+1, but vN payloads carrying them must still validate
///    against vN — though typically they wouldn't, since the event_version
///    is wire-pinned by the producer).
///
/// "Strict mode" (reject unknown fields) is a flag the
/// [`StructuralValidator::strict`] constructor enables — opt-in per service
/// (defaults to false since V1 prioritizes additive evolution).
pub struct StructuralValidator {
    pub strict_unknown_fields: bool,
}

impl Default for StructuralValidator {
    fn default() -> Self {
        Self { strict_unknown_fields: false }
    }
}

impl StructuralValidator {
    pub fn strict() -> Self {
        Self { strict_unknown_fields: true }
    }
}

impl EventValidator for StructuralValidator {
    fn validate(&self, descriptor: &SchemaDescriptor, payload: &Value) -> Result<(), EventError> {
        let obj = payload.as_object().ok_or_else(|| EventError::SchemaViolation {
            event_type: descriptor.event_type.clone(),
            event_version: descriptor.event_version,
            detail: "payload not an object".to_string(),
        })?;
        // 1+2: required fields present
        for f in &descriptor.required_fields {
            let Some(v) = obj.get(&f.name) else {
                return Err(EventError::SchemaViolation {
                    event_type: descriptor.event_type.clone(),
                    event_version: descriptor.event_version,
                    detail: format!("missing required field {}", f.name),
                });
            };
            if !f.ty.matches(v) {
                return Err(EventError::SchemaViolation {
                    event_type: descriptor.event_type.clone(),
                    event_version: descriptor.event_version,
                    detail: format!(
                        "field {} expected {} got {}",
                        f.name,
                        f.ty.as_str(),
                        type_name_of(v)
                    ),
                });
            }
        }
        // 4: strict mode -> reject unknown fields
        if self.strict_unknown_fields {
            let known: HashSet<&str> = descriptor.required_fields.iter().map(|f| f.name.as_str()).collect();
            for k in obj.keys() {
                if !known.contains(k.as_str()) {
                    return Err(EventError::SchemaViolation {
                        event_type: descriptor.event_type.clone(),
                        event_version: descriptor.event_version,
                        detail: format!("unknown field {} (strict mode)", k),
                    });
                }
            }
        }
        Ok(())
    }
}

/// ValidatorRegistry holds descriptors per (event_type, event_version) and
/// dispatches `validate()` calls through a shared [`EventValidator`].
///
/// The expected wiring at service init is:
///
/// ```rust,ignore
/// let mut reg = ValidatorRegistry::with_validator(StructuralValidator::default());
/// reg.register(SchemaDescriptor { … npc.said v1 … });
/// reg.register(SchemaDescriptor { … npc.said v2 … });
/// // …
/// // On event-append:
/// reg.validate("npc.said", 2, &payload)?;
/// ```
pub struct ValidatorRegistry {
    validator: Box<dyn EventValidator>,
    descriptors: HashMap<(String, u32), SchemaDescriptor>,
}

impl ValidatorRegistry {
    pub fn with_validator(v: impl EventValidator + 'static) -> Self {
        Self {
            validator: Box::new(v),
            descriptors: HashMap::new(),
        }
    }

    pub fn register(&mut self, d: SchemaDescriptor) {
        let key = (d.event_type.clone(), d.event_version);
        self.descriptors.insert(key, d);
    }

    pub fn validate(&self, event_type: &str, event_version: u32, payload: &Value) -> Result<(), EventError> {
        let d = self
            .descriptors
            .get(&(event_type.to_string(), event_version))
            .ok_or_else(|| EventError::UnknownSchema {
                event_type: event_type.to_string(),
                event_version,
            })?;
        self.validator.validate(d, payload)
    }

    /// True if a descriptor is registered for (event_type, event_version).
    pub fn knows(&self, event_type: &str, event_version: u32) -> bool {
        self.descriptors.contains_key(&(event_type.to_string(), event_version))
    }
}

fn type_name_of(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn npc_said_v2_descriptor() -> SchemaDescriptor {
        SchemaDescriptor {
            event_type: "npc.said".into(),
            event_version: 2,
            required_fields: vec![
                RequiredField { name: "npc_id".into(), ty: FieldType::String },
                RequiredField { name: "text".into(), ty: FieldType::String },
                RequiredField { name: "scene_id".into(), ty: FieldType::String },
                RequiredField { name: "said_at".into(), ty: FieldType::String },
                RequiredField { name: "tone".into(), ty: FieldType::String },
            ],
        }
    }

    fn registry() -> ValidatorRegistry {
        let mut r = ValidatorRegistry::with_validator(StructuralValidator::default());
        r.register(npc_said_v2_descriptor());
        r
    }

    #[test]
    fn happy_path_validates() {
        let r = registry();
        let payload = json!({
            "npc_id": "00000000-0000-0000-0000-000000000001",
            "text": "hello world",
            "scene_id": "00000000-0000-0000-0000-000000000002",
            "said_at": "2026-05-29T12:00:00Z",
            "tone": "neutral",
        });
        assert!(r.validate("npc.said", 2, &payload).is_ok());
    }

    #[test]
    fn missing_required_field_rejected() {
        let r = registry();
        let payload = json!({
            "npc_id": "00000000-0000-0000-0000-000000000001",
            "text": "hello",
            // missing scene_id, said_at, tone
        });
        let err = r.validate("npc.said", 2, &payload).unwrap_err();
        match err {
            EventError::SchemaViolation { detail, .. } => assert!(detail.contains("missing required field")),
            other => panic!("expected SchemaViolation, got {:?}", other),
        }
    }

    #[test]
    fn wrong_field_type_rejected() {
        let r = registry();
        let payload = json!({
            "npc_id": 12345, // expected string, got number
            "text": "hi",
            "scene_id": "x",
            "said_at": "x",
            "tone": "x",
        });
        let err = r.validate("npc.said", 2, &payload).unwrap_err();
        match err {
            EventError::SchemaViolation { detail, .. } => {
                assert!(detail.contains("npc_id"));
                assert!(detail.contains("string"));
                assert!(detail.contains("number"));
            }
            other => panic!("expected SchemaViolation, got {:?}", other),
        }
    }

    #[test]
    fn payload_not_object_rejected() {
        let r = registry();
        let err = r.validate("npc.said", 2, &json!([1,2,3])).unwrap_err();
        match err {
            EventError::SchemaViolation { detail, .. } => assert!(detail.contains("not an object")),
            other => panic!("expected SchemaViolation, got {:?}", other),
        }
    }

    #[test]
    fn unknown_event_type_rejected_with_typed_error() {
        let r = registry();
        let err = r.validate("nonexistent", 1, &json!({})).unwrap_err();
        match err {
            EventError::UnknownSchema { event_type, event_version } => {
                assert_eq!(event_type, "nonexistent");
                assert_eq!(event_version, 1);
            }
            other => panic!("expected UnknownSchema, got {:?}", other),
        }
    }

    #[test]
    fn unknown_event_version_rejected() {
        let r = registry();
        // we registered v2 only; v99 unknown
        let err = r.validate("npc.said", 99, &json!({})).unwrap_err();
        assert!(matches!(err, EventError::UnknownSchema { .. }));
    }

    #[test]
    fn lenient_mode_accepts_extra_fields() {
        let r = registry();
        let payload = json!({
            "npc_id": "x",
            "text": "x",
            "scene_id": "x",
            "said_at": "x",
            "tone": "x",
            "future_field": "ignored",
        });
        assert!(r.validate("npc.said", 2, &payload).is_ok());
    }

    #[test]
    fn strict_mode_rejects_unknown_fields() {
        let mut r = ValidatorRegistry::with_validator(StructuralValidator::strict());
        r.register(npc_said_v2_descriptor());
        let payload = json!({
            "npc_id": "x",
            "text": "x",
            "scene_id": "x",
            "said_at": "x",
            "tone": "x",
            "future_field": "rejected_in_strict",
        });
        let err = r.validate("npc.said", 2, &payload).unwrap_err();
        match err {
            EventError::SchemaViolation { detail, .. } => assert!(detail.contains("unknown field")),
            other => panic!("expected SchemaViolation, got {:?}", other),
        }
    }

    #[test]
    fn knows_returns_truth() {
        let r = registry();
        assert!(r.knows("npc.said", 2));
        assert!(!r.knows("npc.said", 1));
        assert!(!r.knows("nonexistent", 1));
    }
}
