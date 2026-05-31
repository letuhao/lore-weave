//! **v4.3a SCAFFOLD** — LLM-driven dispatch trait + cache trait + reference
//! implementations.
//!
//! v4.3a wires the abstraction skeleton; v4.3b adds typed parameter
//! overrides; v4.3c plugs the first real provider (Anthropic Claude via
//! tool-use); v4.3d adds OpenAI + Ollama; v4.3e adds the Postgres cache
//! when platform integration ships.
//!
//! ## Concept
//!
//! `DispatchMode::Llm` consults an [`LlmProvider`] for a `ShapeKind` (and,
//! from v4.3b on, parameter overrides) per dispatched entity. Calls are
//! routed through a [`DispatchCache`] keyed by `entity_path` so a re-run
//! over the same world is byte-deterministic and free of round-trip cost.
//!
//! The interfaces are intentionally `Send + Sync` and reference-counted via
//! `Arc` so a single provider/cache pair can be shared across all the
//! dispatch sites in a `flatworld::generate` call without copies.

use std::collections::HashMap;
use std::fmt;
use std::sync::Mutex;

use crate::shape::csg::BooleanTemplate;
use crate::shape::{ParamOverride, ShapeContext, ShapeKind, SizeRank};

// ---------- v4.3d: shared system prompt + user-message + schema +
// parsing helpers used by all three concrete providers (Anthropic,
// OpenAI, Ollama). Pub(crate) so the provider modules see them but the
// crate's external surface stays clean. ----------

/// Catalog + dispatch rubric. Identical across providers — Anthropic
/// tags it `cache_control: ephemeral`, OpenAI / Ollama rely on their
/// own automatic prompt caching. Update bumps an effective cache key
/// because the text contents flow into the prefix hash.
pub(crate) fn shape_dispatch_system_prompt() -> String {
    String::from(
        "You are a procedural-world-generation dispatcher. For each \
         entity (plate, zone, sub-zone) you pick one shape generator \
         from a fixed catalog and emit a structured `pick_shape` call. \
         Output ONLY the structured call — no prose.\n\
         \n\
         ## Catalog (return one of these as `kind`):\n\
         - `Ellipse` — smooth anisotropic ellipsoid with fbm warp. \
           Defaults; works for any rank.\n\
         - `BezierSpine` — cubic Bezier spine + variable-radius sweep. \
           Good for long thin continents (Italy / Korea / Madagascar \
           shapes).\n\
         - `Polar` — superformula closed curve. Picks small-rank \
           rotationally-symmetric continents (Iceland / Hispaniola).\n\
         - `Boolean` — polygon CSG (union / difference / wedge cut). \
           Good for inland seas, gulfs, peanut shapes.\n\
         - `SdfCapsuleChain` — chained capsules + smooth-min. Branching \
           or limb-like landmasses.\n\
         - `MarchingNoise` — noise field contoured. Best for archipelagos \
           and irregular coastlines.\n\
         - `Slime` — multi-agent random walk + concave hull. Most \
           organic / tendrilly continents.\n\
         - `Stamp` — pre-authored signature templates (Italy boot, Japan \
           4-arc, Cuba crescent, etc.). Picks via `template_id`.\n\
         \n\
         ## Parameter overrides (return matching variant in `params`):\n\
         - For `Ellipse` set `params.ellipse.aspect_ratio` in [0.5, 3.0].\n\
         - For `Boolean` set `params.boolean.template` to one of \
           [`EllipseUnion`, `EllipseDifference`, `WedgeCut`].\n\
         - For `Stamp` set `params.stamp.template_id` to a u32 in [0, 9].\n\
         - Other kinds: leave `params` null.\n\
         \n\
         ## Picking rules:\n\
         - Bias by `depth`: plates (0) prefer interesting Bezier/Boolean/\
           Stamp variety; zones (1) skew Ellipse/Polar for cleaner \
           subdivisions; sub-zones (2) lean Ellipse/Polar minimal.\n\
         - Bias by `size_rank`: Giant → branched (Slime, SDF, Bezier); \
           Micro → simple (Ellipse, Polar).\n\
         - Latitude `lat_norm` is `0..1` (north=0). Tropical mid-band \
           may favour archipelagos (MarchingNoise).\n\
         - Stay coherent within a `parent_path` family — sister zones of \
           the same plate should share a stylistic register.",
    )
}

pub(crate) fn shape_dispatch_user_message(prompt: &LlmPrompt) -> String {
    let parent = if prompt.parent_path.is_empty() {
        "(root)".to_string()
    } else {
        prompt
            .parent_path
            .iter()
            .map(|p| p.to_string())
            .collect::<Vec<_>>()
            .join(".")
    };
    let allowed = prompt
        .allowed_kinds
        .iter()
        .map(|k| format!("{k:?}"))
        .collect::<Vec<_>>()
        .join(", ");
    format!(
        "Entity:\n\
         - path: {path}\n\
         - depth: {depth}\n\
         - size_rank: {rank:?}\n\
         - lat_norm: {lat:.3}\n\
         - parent: {parent}\n\
         - allowed_kinds: [{allowed}]\n\
         \n\
         Pick a shape via the structured call.",
        path = prompt.entity_path,
        depth = prompt.depth,
        rank = prompt.size_rank,
        lat = prompt.lat_norm,
    )
}

/// Strict JSON Schema for the `pick_shape` structured-output call. Used
/// by OpenAI's `strict: true` mode and accepted (with strictness ignored)
/// by Anthropic's tool_use and Ollama's `format`. `additionalProperties:
/// false` everywhere so the strict mode validates.
pub(crate) fn pick_shape_schema_strict() -> serde_json::Value {
    serde_json::json!({
        "type": "object",
        "additionalProperties": false,
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "Ellipse",
                    "BezierSpine",
                    "Polar",
                    "Boolean",
                    "SdfCapsuleChain",
                    "MarchingNoise",
                    "Slime",
                    "Stamp"
                ],
                "description": "Which generator from the catalog to use."
            },
            "params": {
                "type": ["object", "null"],
                "additionalProperties": false,
                "properties": {
                    "ellipse": {
                        "type": ["object", "null"],
                        "additionalProperties": false,
                        "properties": {
                            "aspect_ratio": { "type": "number", "minimum": 0.5, "maximum": 3.0 }
                        }
                    },
                    "boolean": {
                        "type": ["object", "null"],
                        "additionalProperties": false,
                        "properties": {
                            "template": {
                                "type": "string",
                                "enum": ["EllipseUnion", "EllipseDifference", "WedgeCut"]
                            }
                        }
                    },
                    "stamp": {
                        "type": ["object", "null"],
                        "additionalProperties": false,
                        "properties": {
                            "template_id": { "type": "integer", "minimum": 0, "maximum": 9 }
                        }
                    }
                }
            }
        },
        "required": ["kind"]
    })
}

pub(crate) fn parse_shape_kind_str(s: &str) -> Result<ShapeKind, LlmError> {
    Ok(match s {
        "Ellipse" => ShapeKind::Ellipse,
        "BezierSpine" => ShapeKind::BezierSpine,
        "Polar" => ShapeKind::Polar,
        "Boolean" => ShapeKind::Boolean,
        "SdfCapsuleChain" => ShapeKind::SdfCapsuleChain,
        "MarchingNoise" => ShapeKind::MarchingNoise,
        "Slime" => ShapeKind::Slime,
        "Stamp" => ShapeKind::Stamp,
        other => {
            return Err(LlmError::InvalidResponse(format!(
                "unknown ShapeKind `{other}`"
            )));
        }
    })
}

pub(crate) fn parse_boolean_template_str(s: &str) -> Result<BooleanTemplate, LlmError> {
    Ok(match s {
        "EllipseUnion" => BooleanTemplate::EllipseUnion,
        "EllipseDifference" => BooleanTemplate::EllipseDifference,
        "WedgeCut" => BooleanTemplate::WedgeCut,
        other => {
            return Err(LlmError::InvalidResponse(format!(
                "unknown BooleanTemplate `{other}`"
            )));
        }
    })
}

pub(crate) fn parse_params_from_value(
    kind: ShapeKind,
    params_node: Option<&serde_json::Value>,
) -> Result<Option<ParamOverride>, LlmError> {
    let Some(params_node) = params_node.filter(|v| !v.is_null()) else {
        return Ok(None);
    };
    let obj = match params_node.as_object() {
        Some(o) => o,
        None => return Ok(None),
    };
    Ok(match kind {
        ShapeKind::Ellipse => obj.get("ellipse").and_then(|e| e.as_object()).map(|e| {
            ParamOverride::Ellipse {
                aspect_ratio: e
                    .get("aspect_ratio")
                    .and_then(|v| v.as_f64())
                    .map(|n| n as f32),
            }
        }),
        ShapeKind::Boolean => match obj.get("boolean").and_then(|b| b.as_object()) {
            Some(b) => {
                let template = match b.get("template").and_then(|v| v.as_str()) {
                    Some(s) => Some(parse_boolean_template_str(s)?),
                    None => None,
                };
                Some(ParamOverride::Boolean { template })
            }
            None => None,
        },
        ShapeKind::Stamp => obj
            .get("stamp")
            .and_then(|s| s.as_object())
            .map(|s| ParamOverride::Stamp {
                template_id: s.get("template_id").and_then(|v| v.as_u64()).map(|n| n as u32),
            }),
        _ => None,
    })
}

/// What the LLM gets as input. Captures the dispatch context as a
/// provider-agnostic struct so a single provider impl can serve every
/// dispatch site (plates, zones, sub-zones) without leaking
/// world-gen-specific types into the provider crate.
#[derive(Debug, Clone)]
pub struct LlmPrompt {
    /// Stable string identity (e.g. `"plate.0"`, `"plate.3.zone.1.subzone.0"`)
    /// — the cache key and the LLM's "what is this entity" handle.
    pub entity_path: String,
    /// `0` = plate, `1` = zone, `2` = sub-zone. Lets the LLM bias by depth.
    pub depth: u32,
    pub size_rank: SizeRank,
    /// Normalised latitude in `[0, 1]` (`0` = north, `1` = south) — handed
    /// in by the dispatcher from `ctx.edge_jitter` per the v4.0 piggyback
    /// convention. v4.1 will add a typed `ctx.lat_norm` field; until then
    /// this carries the current world's lat for the prompt builder.
    pub lat_norm: f32,
    /// Parent identity path (e.g. `[plate_id]` for a zone, `[plate_id,
    /// zone_id]` for a sub-zone). Empty for plates. Helps the LLM keep
    /// stylistic coherence per family.
    pub parent_path: Vec<usize>,
    /// Which kinds the registry actually has registered — the LLM MUST
    /// return one of these (provider impls should grammar-constrain the
    /// decode). Listed in registry insertion order.
    pub allowed_kinds: Vec<ShapeKind>,
}

impl LlmPrompt {
    /// Build a prompt from the dispatcher's per-call context.
    pub fn from_context(ctx: &ShapeContext, entity_path: &str, allowed_kinds: Vec<ShapeKind>) -> Self {
        LlmPrompt {
            entity_path: entity_path.to_string(),
            depth: ctx.depth,
            size_rank: ctx.size_rank,
            lat_norm: ctx.edge_jitter, // v4.0 piggyback convention
            parent_path: ctx.parent_path.clone(),
            allowed_kinds,
        }
    }
}

/// What the LLM returns. `kind` is the selected `ShapeKind`; `params` is
/// the typed [`ParamOverride`] that the matching generator reads from
/// [`ShapeContext::params`] when the dispatcher threads the decision
/// through.
#[derive(Debug, Clone)]
pub struct LlmDecision {
    pub kind: ShapeKind,
    /// **v4.3b**: typed per-generator parameter override. Set to a variant
    /// matching `kind` (e.g. `kind = Ellipse` → `params =
    /// Some(ParamOverride::Ellipse { .. })`). `None` means "use generator
    /// defaults". Mismatched variant + kind pairings are silently ignored
    /// by generators — they only match their own variant. v4.3b ships
    /// variants for Ellipse / Boolean / Stamp; remaining generators
    /// receive `None` until v4.3d.
    pub params: Option<ParamOverride>,
}

/// Error returned by [`LlmProvider::pick`]. `DispatchMode::Llm` treats any
/// error as an abstain so the caller's `Layered` fallback can recover
/// (typical pairing: `Layered([Llm, Weighted(...)])`).
#[derive(Debug)]
pub enum LlmError {
    /// Network or transport failure.
    Transport(String),
    /// Provider returned a value that wasn't a registered `ShapeKind`.
    InvalidResponse(String),
    /// Provider refused to answer (rate-limit, content policy, etc.).
    Refused(String),
    /// Catch-all for impl-specific errors.
    Other(String),
}

impl fmt::Display for LlmError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LlmError::Transport(m) => write!(f, "LLM transport error: {m}"),
            LlmError::InvalidResponse(m) => write!(f, "LLM invalid response: {m}"),
            LlmError::Refused(m) => write!(f, "LLM refused: {m}"),
            LlmError::Other(m) => write!(f, "LLM error: {m}"),
        }
    }
}

impl std::error::Error for LlmError {}

/// The provider-side interface. v4.3a ships [`MockLlmProvider`]; the
/// gateway-backed [`GatewayLlmProvider`] (added 2026-05-30) replaced the
/// deleted v4.3c-d `AnthropicProvider` / `OpenAIProvider` /
/// `OllamaProvider` direct-call impls.
///
/// Implementations MUST be `Send + Sync` so a single `Arc<dyn LlmProvider>`
/// can be cloned across the per-plate Rayon par-iter in
/// `flatworld::generate`. Implementations MUST be `Debug` so
/// `DispatchMode` keeps its `Debug` derive.
pub trait LlmProvider: fmt::Debug + Send + Sync {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError>;
}

/// The cache-side interface. `get` returns a previously-stored decision;
/// `put` stores a fresh one. Interior mutability (the impl owns the lock)
/// so the dispatcher can borrow the cache shared.
pub trait DispatchCache: fmt::Debug + Send + Sync {
    fn get(&self, key: &str) -> Option<LlmDecision>;
    fn put(&self, key: &str, value: LlmDecision);
}

/// In-process `HashMap`-backed cache. The CLI uses this; the platform will
/// add a `PostgresDispatchCache` in v4.3e once the dispatcher is invoked
/// from a deployed service.
#[derive(Debug, Default)]
pub struct InMemoryDispatchCache {
    inner: Mutex<HashMap<String, LlmDecision>>,
}

impl InMemoryDispatchCache {
    pub fn new() -> Self {
        Self::default()
    }

    /// Test helper: number of cached entries.
    pub fn len(&self) -> usize {
        self.inner.lock().expect("cache mutex poisoned").len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl DispatchCache for InMemoryDispatchCache {
    fn get(&self, key: &str) -> Option<LlmDecision> {
        self.inner
            .lock()
            .expect("cache mutex poisoned")
            .get(key)
            .cloned()
    }

    fn put(&self, key: &str, value: LlmDecision) {
        self.inner
            .lock()
            .expect("cache mutex poisoned")
            .insert(key.to_string(), value);
    }
}

/// **Civ Ship 7b** — what a [`TextProvider`] is asked to complete. Wraps
/// the system + user + optional JSON schema you would normally hand to
/// a Messages-style API into one provider-agnostic struct.
#[derive(Debug, Clone)]
pub struct TextPrompt {
    /// The system message — instruction-tuned models use this as the
    /// persistent role prompt.
    pub system: String,
    /// The user message — the per-call request body.
    pub user: String,
    /// Optional JSON Schema the response must validate against.
    /// Providers translate this into their structured-output mode
    /// (Anthropic tool_use, OpenAI response_format, Ollama format).
    pub schema: Option<serde_json::Value>,
    /// Optional schema name used by providers that need one (OpenAI
    /// `json_schema.name`). Defaults to `"response"`.
    pub schema_name: Option<String>,
}

impl TextPrompt {
    pub fn new(system: impl Into<String>, user: impl Into<String>) -> Self {
        Self {
            system: system.into(),
            user: user.into(),
            schema: None,
            schema_name: None,
        }
    }

    pub fn with_schema(mut self, schema: serde_json::Value, name: impl Into<String>) -> Self {
        self.schema = Some(schema);
        self.schema_name = Some(name.into());
        self
    }
}

/// **Civ Ship 7b** — free-form text generation interface. Parallel to
/// [`LlmProvider`] (which returns a constrained `ShapeKind`); this trait
/// returns a raw string so callers can parse domain-specific JSON
/// (naming, summarisation, etc).
///
/// Implementations MUST be `Send + Sync + Debug` for the same reasons
/// as [`LlmProvider`].
pub trait TextProvider: fmt::Debug + Send + Sync {
    /// Run the prompt; return the assistant's response as a string. The
    /// caller is responsible for parsing — typically `serde_json::from_str`
    /// when a schema was attached.
    fn complete(&self, prompt: &TextPrompt) -> Result<String, LlmError>;
}

/// Deterministic stand-in [`TextProvider`] for tests + offline runs.
/// Returns a stable JSON string when a schema is attached, otherwise a
/// short canned string. Output is keyed on the prompt content so the
/// same `TextPrompt` always yields the same response — the property
/// real providers preserve via cache + `temperature = 0`.
#[derive(Debug, Clone)]
pub struct MockTextProvider;

impl MockTextProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for MockTextProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl TextProvider for MockTextProvider {
    fn complete(&self, prompt: &TextPrompt) -> Result<String, LlmError> {
        // FNV-1a 32-bit hash of the user message to give deterministic
        // variety across distinct prompts.
        let mut h: u32 = 0x811C_9DC5;
        for byte in prompt.user.as_bytes() {
            h ^= *byte as u32;
            h = h.wrapping_mul(0x0100_0193);
        }
        if let Some(schema) = &prompt.schema {
            // Emit a minimal-but-valid object: for every property
            // declared in the schema, fill it with a synthetic value.
            // The civ-layer naming caller validates against its own
            // typed `WorldNames` struct so we only need to produce
            // string-array values (no nested type variety yet).
            let mut out = serde_json::Map::new();
            if let Some(props) = schema.get("properties").and_then(|p| p.as_object()) {
                for (key, prop_schema) in props {
                    let ty = prop_schema
                        .get("type")
                        .and_then(|t| t.as_str())
                        .unwrap_or("string");
                    let value = match ty {
                        "array" => {
                            // Default to 5 mock entries; the caller can
                            // request specifics via the prompt body.
                            let stems = ["alpha", "beta", "gamma", "delta", "epsilon"];
                            serde_json::Value::Array(
                                stems
                                    .iter()
                                    .enumerate()
                                    .map(|(i, s)| {
                                        serde_json::Value::String(format!(
                                            "{}-{}-{}",
                                            key,
                                            s,
                                            h.wrapping_add(i as u32)
                                        ))
                                    })
                                    .collect(),
                            )
                        }
                        "object" => serde_json::Value::Object(serde_json::Map::new()),
                        _ => serde_json::Value::String(format!(
                            "{}-{:08x}",
                            key, h
                        )),
                    };
                    out.insert(key.clone(), value);
                }
            }
            return Ok(
                serde_json::to_string(&serde_json::Value::Object(out)).expect("mock JSON"),
            );
        }
        // No schema — return a stable canned string keyed on the hash.
        Ok(format!("mock-response-{h:08x}"))
    }
}

/// Deterministic stand-in provider for testing + offline runs. Picks a
/// `ShapeKind` by hashing `prompt.entity_path` mod `allowed_kinds.len()`
/// so the same path always produces the same kind (the property the
/// real provider must preserve via cache + temperature=0). `params` is
/// always `None` for v4.3a; v4.3b extends this with a generator-aware
/// stub.
#[derive(Debug, Clone)]
pub struct MockLlmProvider;

impl MockLlmProvider {
    pub fn new() -> Self {
        Self
    }
}

impl Default for MockLlmProvider {
    fn default() -> Self {
        Self::new()
    }
}

impl LlmProvider for MockLlmProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        if prompt.allowed_kinds.is_empty() {
            return Err(LlmError::InvalidResponse(
                "registry has no kinds".to_string(),
            ));
        }
        // FNV-1a 32-bit so the choice is stable across runs without
        // pulling in a hash crate.
        let mut h: u32 = 0x811C_9DC5;
        for byte in prompt.entity_path.as_bytes() {
            h ^= *byte as u32;
            h = h.wrapping_mul(0x0100_0193);
        }
        let kind = prompt.allowed_kinds[(h as usize) % prompt.allowed_kinds.len()];
        // **v4.3b**: populate `params` per kind for the variants v4.3b
        // wires up (Ellipse / Boolean / Stamp). Other kinds receive
        // `None` — generators ignore unmatched variants anyway, so the
        // contract stays clean as more generators get LLM-tunable knobs.
        let params = mock_params_for_kind(kind, h);
        Ok(LlmDecision { kind, params })
    }
}

/// Deterministic mock parameters for a given kind + entity-path hash.
/// `kind` selects the variant; `h` seeds the per-variant choice so different
/// paths get different param values. Pure function of inputs — calling it
/// twice with the same args returns the same params.
fn mock_params_for_kind(kind: ShapeKind, h: u32) -> Option<ParamOverride> {
    match kind {
        ShapeKind::Ellipse => {
            // aspect_ratio cycles through 1.0 / 1.5 / 2.0 / 2.5 across
            // adjacent entity paths so a default render visibly varies.
            let ratios = [1.0_f32, 1.5, 2.0, 2.5];
            Some(ParamOverride::Ellipse {
                aspect_ratio: Some(ratios[(h as usize) % ratios.len()]),
            })
        }
        ShapeKind::Boolean => {
            use crate::shape::csg::BooleanTemplate;
            let templates = [
                BooleanTemplate::EllipseUnion,
                BooleanTemplate::WedgeCut,
                BooleanTemplate::EllipseDifference,
            ];
            Some(ParamOverride::Boolean {
                template: Some(templates[(h as usize) % templates.len()]),
            })
        }
        ShapeKind::Stamp => Some(ParamOverride::Stamp {
            template_id: Some(h % 10),
        }),
        _ => None,
    }
}

// ---------- Gateway providers (CLAUDE.md provider gateway invariant) ----------
//
// All LLM calls in world-gen MUST go through the loreweave_llm SDK, which
// routes through provider-registry-service. The CLIENT never picks a
// provider — `model_ref: Uuid` selects a registered model and the gateway
// resolves the provider server-side. This replaces the deleted
// shape/{anthropic,openai,ollama}.rs direct-provider impls and the
// pre-existing `author::llm_json_request` direct call (which targeted an
// OpenAI-compatible URL via `--llm-url`).

use std::sync::Arc;

use loreweave_llm::{
    ChatStreamRequest, GatewayClient, LlmError as SdkLlmError, ModelSource, StreamEvent,
    StreamFormat, ToolCallAccumulator,
};
use tokio::runtime::Runtime;
use uuid::Uuid;

/// Map an [`SdkLlmError`] to our local [`LlmError`] so the dispatcher's
/// `Layered` fallback semantics stay uniform.
fn map_sdk_err(e: SdkLlmError) -> LlmError {
    match e {
        SdkLlmError::Http(_) => LlmError::Transport(e.to_string()),
        SdkLlmError::GatewayHttpStatus { status, body } => {
            if status == 429 {
                LlmError::Refused(format!("gateway rate-limited (status {status}): {body}"))
            } else {
                LlmError::Transport(format!("gateway HTTP {status}: {body}"))
            }
        }
        SdkLlmError::GatewayErrorEvent { code, message } => {
            LlmError::Refused(format!("gateway error event {code}: {message}"))
        }
        SdkLlmError::StreamParse(m) => LlmError::InvalidResponse(format!("stream parse: {m}")),
        SdkLlmError::ValidationExhausted { attempts } => {
            LlmError::InvalidResponse(format!("validation exhausted after {attempts} attempts"))
        }
        SdkLlmError::MissingInternalToken => LlmError::Other(e.to_string()),
        SdkLlmError::InvalidInternalToken(_) => LlmError::Other(e.to_string()),
        SdkLlmError::InvalidUrl(_) => LlmError::Other(e.to_string()),
    }
}

/// Build the OpenAI-shaped `pick_shape` function-tool definition the gateway
/// translates per provider. Schema mirrors [`pick_shape_schema_strict`].
fn pick_shape_function_tool() -> serde_json::Value {
    serde_json::json!({
        "type": "function",
        "function": {
            "name": "pick_shape",
            "description": "Choose a shape generator and (optionally) its \
                            parameter override for the described entity.",
            "parameters": pick_shape_schema_strict(),
        }
    })
}

/// Build the OpenAI-shaped function-tool for a free-form [`TextPrompt`]
/// with a JSON schema attached.
fn text_response_function_tool(name: &str, schema: &serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "type": "function",
        "function": {
            "name": name,
            "description": "Emit the structured response per the parameters schema.",
            "parameters": schema,
        }
    })
}

/// **Gateway-backed [`LlmProvider`]** (shape dispatch flow).
///
/// Streams `ChatStreamRequest` via [`GatewayClient`], assembles the
/// `pick_shape` tool call from streamed `tool_call` fragments, parses to
/// [`LlmDecision`]. `Send + Sync + Debug` per the trait contract.
///
/// **Sync→async bridge**: the dispatcher is sync, the SDK is async; the
/// provider owns its own `current_thread` tokio runtime and uses
/// `block_on` (same pattern as [`crate::shape::postgres_cache::PostgresDispatchCache`]).
pub struct GatewayLlmProvider {
    client: Arc<GatewayClient>,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    rt: Arc<Runtime>,
}

impl fmt::Debug for GatewayLlmProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GatewayLlmProvider")
            .field("model_source", &self.model_source)
            .field("model_ref", &self.model_ref)
            .field("user_id", &self.user_id)
            .finish_non_exhaustive()
    }
}

impl GatewayLlmProvider {
    /// Build with explicit client + runtime — production callers usually
    /// share one runtime + one client across providers.
    pub fn new(
        client: Arc<GatewayClient>,
        model_source: ModelSource,
        model_ref: Uuid,
        user_id: Uuid,
        rt: Arc<Runtime>,
    ) -> Self {
        Self {
            client,
            model_source,
            model_ref,
            user_id,
            rt,
        }
    }
}

impl LlmProvider for GatewayLlmProvider {
    fn pick(&self, prompt: &LlmPrompt) -> Result<LlmDecision, LlmError> {
        let messages = vec![
            serde_json::json!({ "role": "system", "content": shape_dispatch_system_prompt() }),
            serde_json::json!({ "role": "user",   "content": shape_dispatch_user_message(prompt) }),
        ];
        // `tool_choice: "required"` works against the broadest set of
        // providers (LM Studio rejects the OpenAI-spec `{type:function,
        // function:{name:...}}` object form with HTTP 400; "required"
        // forces some tool call). With a single registered tool the model
        // can only pick that one, so semantically equivalent to forcing
        // by name.
        let request = ChatStreamRequest::new_chat_with_tools(
            self.model_source,
            self.model_ref,
            messages,
            vec![pick_shape_function_tool()],
            StreamFormat::Openai,
        )
        .with_tool_choice(serde_json::json!("required"))
        .normalize();
        let client = self.client.clone();
        let user_id = self.user_id;
        let calls = self.rt.block_on(async move {
            let mut handle = client.stream(request, user_id).await.map_err(map_sdk_err)?;
            let mut acc = ToolCallAccumulator::new();
            while let Some(item) = handle.next().await {
                let event = item.map_err(map_sdk_err)?;
                match &event {
                    StreamEvent::ToolCall { .. } => acc.push(&event),
                    StreamEvent::Error { code, message } => {
                        return Err(LlmError::Refused(format!(
                            "gateway error event {code}: {message}"
                        )));
                    }
                    StreamEvent::Done { .. } => break,
                    _ => {}
                }
            }
            Ok::<Vec<loreweave_llm::CompletedToolCall>, LlmError>(acc.finish())
        })?;
        let pick = calls
            .into_iter()
            .find(|c| c.name.as_deref() == Some("pick_shape"))
            .ok_or_else(|| {
                LlmError::InvalidResponse("no `pick_shape` tool_call in stream".to_string())
            })?;
        let parsed: serde_json::Value = serde_json::from_str(&pick.arguments).map_err(|e| {
            LlmError::InvalidResponse(format!("tool_call arguments not JSON: {e}"))
        })?;
        let kind_str = parsed
            .get("kind")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                LlmError::InvalidResponse("tool_call.kind missing or not string".to_string())
            })?;
        let kind = parse_shape_kind_str(kind_str)?;
        if !prompt.allowed_kinds.contains(&kind) {
            return Err(LlmError::InvalidResponse(format!(
                "kind {kind:?} not in allowed_kinds {:?}",
                prompt.allowed_kinds
            )));
        }
        let params = parse_params_from_value(kind, parsed.get("params"))?;
        Ok(LlmDecision { kind, params })
    }
}

/// **Gateway-backed [`TextProvider`]** (naming / authoring flow).
///
/// Streams `ChatStreamRequest` via [`GatewayClient`]. When `prompt.schema`
/// is set: emits an OpenAI-shaped function tool with the schema as
/// `parameters`, forces tool_choice, returns the assembled tool_call
/// arguments JSON string. Otherwise: concatenates streamed `Token` deltas
/// into a plain-text response.
pub struct GatewayTextProvider {
    client: Arc<GatewayClient>,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    rt: Arc<Runtime>,
}

impl fmt::Debug for GatewayTextProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GatewayTextProvider")
            .field("model_source", &self.model_source)
            .field("model_ref", &self.model_ref)
            .field("user_id", &self.user_id)
            .finish_non_exhaustive()
    }
}

impl GatewayTextProvider {
    pub fn new(
        client: Arc<GatewayClient>,
        model_source: ModelSource,
        model_ref: Uuid,
        user_id: Uuid,
        rt: Arc<Runtime>,
    ) -> Self {
        Self {
            client,
            model_source,
            model_ref,
            user_id,
            rt,
        }
    }
}

impl TextProvider for GatewayTextProvider {
    fn complete(&self, prompt: &TextPrompt) -> Result<String, LlmError> {
        let messages = vec![
            serde_json::json!({ "role": "system", "content": prompt.system }),
            serde_json::json!({ "role": "user",   "content": prompt.user }),
        ];
        let (tools, tool_choice, schema_name) = if let Some(schema) = &prompt.schema {
            let name = prompt
                .schema_name
                .clone()
                .unwrap_or_else(|| "response".to_string());
            // See GatewayLlmProvider note — `"required"` instead of the
            // OpenAI-spec object form for LM Studio compatibility.
            (
                vec![text_response_function_tool(&name, schema)],
                Some(serde_json::json!("required")),
                Some(name),
            )
        } else {
            (vec![], None, None)
        };
        let mut request = ChatStreamRequest::new_chat_with_tools(
            self.model_source,
            self.model_ref,
            messages,
            tools,
            StreamFormat::Openai,
        );
        if let Some(tc) = tool_choice {
            request = request.with_tool_choice(tc);
        }
        let request = request.normalize();
        let client = self.client.clone();
        let user_id = self.user_id;
        let (tool_calls, text_buf) = self.rt.block_on(async move {
            let mut handle = client.stream(request, user_id).await.map_err(map_sdk_err)?;
            let mut acc = ToolCallAccumulator::new();
            let mut text = String::new();
            while let Some(item) = handle.next().await {
                match item.map_err(map_sdk_err)? {
                    StreamEvent::Token { delta, .. } => text.push_str(&delta),
                    StreamEvent::ToolCall {
                        index,
                        id,
                        name,
                        arguments_delta,
                    } => acc.push(&StreamEvent::ToolCall {
                        index,
                        id,
                        name,
                        arguments_delta,
                    }),
                    StreamEvent::Error { code, message } => {
                        return Err(LlmError::Refused(format!(
                            "gateway error event {code}: {message}"
                        )));
                    }
                    StreamEvent::Done { .. } => break,
                    _ => {}
                }
            }
            Ok::<(Vec<loreweave_llm::CompletedToolCall>, String), LlmError>((acc.finish(), text))
        })?;
        if let Some(name) = schema_name {
            let call = tool_calls
                .into_iter()
                .find(|c| c.name.as_deref() == Some(name.as_str()))
                .ok_or_else(|| {
                    LlmError::InvalidResponse(format!(
                        "schema-mode response missing `{name}` tool_call"
                    ))
                })?;
            Ok(call.arguments)
        } else if text_buf.is_empty() {
            Err(LlmError::InvalidResponse(
                "no text content in response (and no tool_call requested)".to_string(),
            ))
        } else {
            Ok(text_buf)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shape::ShapeContext;

    fn ctx() -> ShapeContext {
        ShapeContext {
            depth: 0,
            center: (100.0, 100.0),
            envelope: (50.0, 50.0),
            size_rank: SizeRank::Medium,
            seed: 42,
            plate_salt: 7,
            parent_path: vec![],
            world_theme: None,
            edge_jitter: 0.5,
            vertex_count_range: (32, 96),
            params: None,
        }
    }

    #[test]
    fn mock_provider_is_deterministic_per_path() {
        let mock = MockLlmProvider::new();
        let kinds = vec![ShapeKind::Ellipse, ShapeKind::BezierSpine, ShapeKind::Polar];
        let prompt = LlmPrompt::from_context(&ctx(), "plate.7", kinds.clone());
        let a = mock.pick(&prompt).expect("mock should pick");
        let b = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(a.kind, b.kind, "same entity_path must yield same kind");
    }

    #[test]
    fn mock_provider_spreads_across_paths() {
        // Across many paths the mock should hit ≥2 distinct kinds — proves
        // the FNV hash isn't degenerate.
        let mock = MockLlmProvider::new();
        let kinds = vec![ShapeKind::Ellipse, ShapeKind::BezierSpine, ShapeKind::Polar];
        let picked: std::collections::HashSet<ShapeKind> = (0..32)
            .map(|i| {
                let prompt = LlmPrompt::from_context(&ctx(), &format!("plate.{i}"), kinds.clone());
                mock.pick(&prompt).expect("mock should pick").kind
            })
            .collect();
        assert!(picked.len() >= 2, "mock provider should not collapse to one kind across 32 paths");
    }

    #[test]
    fn mock_provider_rejects_empty_registry() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![]);
        assert!(matches!(mock.pick(&prompt), Err(LlmError::InvalidResponse(_))));
    }

    #[test]
    fn in_memory_cache_round_trips_a_decision() {
        let cache = InMemoryDispatchCache::new();
        assert!(cache.is_empty());
        let decision = LlmDecision { kind: ShapeKind::Stamp, params: None };
        cache.put("plate.0.zone.0", decision.clone());
        let hit = cache.get("plate.0.zone.0").expect("cache should hit");
        assert_eq!(hit.kind, ShapeKind::Stamp);
        assert!(cache.get("plate.0.zone.1").is_none(), "cold path");
        assert_eq!(cache.len(), 1);
    }

    #[test]
    fn in_memory_cache_overwrites_on_repeat_put() {
        let cache = InMemoryDispatchCache::new();
        cache.put("plate.0", LlmDecision { kind: ShapeKind::Ellipse, params: None });
        cache.put("plate.0", LlmDecision { kind: ShapeKind::Slime, params: None });
        assert_eq!(cache.get("plate.0").unwrap().kind, ShapeKind::Slime);
        assert_eq!(cache.len(), 1, "second put must overwrite, not append");
    }

    #[test]
    fn v4_3b_mock_populates_ellipse_aspect_ratio() {
        // Mock provider must hand back `ParamOverride::Ellipse { aspect_ratio: Some(_) }`
        // whenever it picks `ShapeKind::Ellipse`.
        let mock = MockLlmProvider::new();
        // Force kind=Ellipse via allowed_kinds == [Ellipse].
        let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![ShapeKind::Ellipse]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Ellipse);
        let params = d.params.expect("Ellipse kind should carry params");
        match params {
            ParamOverride::Ellipse { aspect_ratio: Some(r) } => {
                assert!(r >= 0.5 && r <= 3.0, "aspect_ratio {r} out of expected mock range");
            }
            _ => panic!("expected ParamOverride::Ellipse with aspect_ratio, got {params:?}"),
        }
    }

    #[test]
    fn v4_3b_mock_populates_boolean_template() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.5", vec![ShapeKind::Boolean]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Boolean);
        let params = d.params.expect("Boolean kind should carry params");
        assert!(
            matches!(params, ParamOverride::Boolean { template: Some(_) }),
            "expected ParamOverride::Boolean with template, got {params:?}"
        );
    }

    #[test]
    fn v4_3b_mock_populates_stamp_template_id() {
        let mock = MockLlmProvider::new();
        let prompt = LlmPrompt::from_context(&ctx(), "plate.7", vec![ShapeKind::Stamp]);
        let d = mock.pick(&prompt).expect("mock should pick");
        assert_eq!(d.kind, ShapeKind::Stamp);
        let params = d.params.expect("Stamp kind should carry params");
        match params {
            ParamOverride::Stamp { template_id: Some(id) } => {
                assert!(id < 10, "mock template_id {id} should be in [0, 9]");
            }
            _ => panic!("expected ParamOverride::Stamp with template_id, got {params:?}"),
        }
    }

    #[test]
    fn v4_3b_mock_returns_none_params_for_unwired_kinds() {
        // BezierSpine / Polar / SDF / MarchingNoise / Slime are not wired
        // for LLM params yet — Mock must return None for those.
        let mock = MockLlmProvider::new();
        for kind in [
            ShapeKind::BezierSpine,
            ShapeKind::Polar,
            ShapeKind::SdfCapsuleChain,
            ShapeKind::MarchingNoise,
            ShapeKind::Slime,
        ] {
            let prompt = LlmPrompt::from_context(&ctx(), "plate.0", vec![kind]);
            let d = mock.pick(&prompt).expect("mock should pick");
            assert_eq!(d.kind, kind);
            assert!(
                d.params.is_none(),
                "kind {kind:?} should have None params in v4.3b, got {:?}",
                d.params,
            );
        }
    }
}
