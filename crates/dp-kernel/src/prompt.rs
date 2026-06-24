//! Cycle 21 / L4.D — `prompt` Rust mirror of `contracts/prompt/` (Go).
//!
//! # Purpose (Q-L4-1 parity)
//!
//! Rust services (world-service, future roleplay-service Rust shards) need
//! the same prompt-assembly contract surface — same 7 intents, same 8-section
//! structure, same FAIL-not-best-effort Composer (Q-L6H-1), same no-op safety
//! stubs V1 (Q-L6L-1), same opaque ProviderPayload (Q-L4D-1).
//!
//! # Q-IDs honored
//!
//! - **Q-L4-1**: byte-equal wire format with Go side
//!   (`#[serde(rename_all = "snake_case")]` on Intent; UPPERCASE on
//!   Section to match S09 §12Y.4 vocabulary).
//! - **Q-L4D-1**: `ProviderPayload = serde_json::Value` (opaque). V2+ may
//!   introduce a typed enum per provider.
//! - **Q-L6H-1**: [`Composer::assemble_prompt`] returns
//!   `Result<PromptBundle, ComposerError>`; FAIL produces no partial
//!   bundle (zero-value bundle is never paired with `Ok`).
//! - **Q-L6L-1**: [`SafetyHooks`] + [`ConsentGate`] + [`TokenBudgetGate`]
//!   ship as traits with `Noop*` default impls returning `Ok(())`.
//! - **Q-L6K-1**: no template strings shipped (LLM-logic sub-program owns).
//!
//! # Body-never-stored invariant
//!
//! Mirrors the Go side: [`PromptBundle`] has NO `body`/`rendered`/`prompt_text`
//! field. The rendered prompt bytes exist only inside the Composer's
//! [`Composer::assemble_prompt`] stack frame; what crosses the boundary is
//! [`PromptBundle::provider_payload`] (opaque) + [`PromptBundle::context_hash`]
//! (SHA-256). Forensics reconstruct via (hash + template + version +
//! deterministic context retrieval) per S09 §12Y.

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};
use thiserror::Error;

// ── Intent (7-variant) ──────────────────────────────────────────────────

/// LLM-call purpose enum. Wire format = canonical snake_case (matches Go
/// `contracts/prompt::Intent`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Intent {
    /// A player's turn in an active session.
    SessionTurn,
    /// An NPC's response composition.
    NpcReply,
    /// Validate a proposed canon entry.
    CanonCheck,
    /// Batch entity/fact extraction from a book chunk.
    CanonExtraction,
    /// Admin-initiated prompt (carries AdminTier).
    AdminTriggered,
    /// One-shot reality bootstrap.
    WorldSeed,
    /// Memory compaction prompt.
    Summary,
}

impl Intent {
    /// Canonical snake_case string form.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::SessionTurn => "session_turn",
            Self::NpcReply => "npc_reply",
            Self::CanonCheck => "canon_check",
            Self::CanonExtraction => "canon_extraction",
            Self::AdminTriggered => "admin_triggered",
            Self::WorldSeed => "world_seed",
            Self::Summary => "summary",
        }
    }

    /// All 7 enumerated intents.
    pub fn all() -> &'static [Intent] {
        &[
            Self::SessionTurn,
            Self::NpcReply,
            Self::CanonCheck,
            Self::CanonExtraction,
            Self::AdminTriggered,
            Self::WorldSeed,
            Self::Summary,
        ]
    }

    /// Returns true iff this intent requires a session_id.
    pub fn requires_session(&self) -> bool {
        matches!(self, Self::SessionTurn | Self::NpcReply)
    }
}

// ── Section (8-variant, fixed order) ────────────────────────────────────

/// Section enum per S09 §12Y.4. Wire format = UPPERCASE (matches Go side).
/// **Order is fixed** — see [`Section::all`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Section {
    #[serde(rename = "SYSTEM")]
    System,
    #[serde(rename = "WORLD_CANON")]
    WorldCanon,
    #[serde(rename = "SESSION_STATE")]
    SessionState,
    #[serde(rename = "ACTOR_CONTEXT")]
    ActorContext,
    #[serde(rename = "MEMORY")]
    Memory,
    #[serde(rename = "HISTORY")]
    History,
    #[serde(rename = "INSTRUCTION")]
    Instruction,
    #[serde(rename = "INPUT")]
    Input,
}

impl Section {
    /// UPPERCASE wire form.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::System => "SYSTEM",
            Self::WorldCanon => "WORLD_CANON",
            Self::SessionState => "SESSION_STATE",
            Self::ActorContext => "ACTOR_CONTEXT",
            Self::Memory => "MEMORY",
            Self::History => "HISTORY",
            Self::Instruction => "INSTRUCTION",
            Self::Input => "INPUT",
        }
    }

    /// 8 sections in canonical render order. **Do not reorder.**
    pub fn all() -> &'static [Section] {
        &[
            Self::System,
            Self::WorldCanon,
            Self::SessionState,
            Self::ActorContext,
            Self::Memory,
            Self::History,
            Self::Instruction,
            Self::Input,
        ]
    }

    /// Only [`Section::Input`] is the user-authored sandbox.
    pub fn is_user_sandbox(&self) -> bool {
        matches!(self, Self::Input)
    }
}

// ── PromptContext + PromptBundle ────────────────────────────────────────

/// Input to [`Composer::assemble_prompt`]. Carries WHO + WHAT-FOR; no body.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptContext {
    pub reality_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    pub actor_user_ref_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub actor_pc_id: Option<String>,
    pub intent: Intent,
    pub retrieval_hints: RetrievalHints,
    #[serde(default)]
    pub admin_tier: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub consent_snapshot_id: Option<String>,
    #[serde(default)]
    pub template_id: String,
    #[serde(default)]
    pub template_version: u32,
}

impl PromptContext {
    /// Fail loudly on missing / invalid required fields (mirrors Go).
    pub fn validate(&self) -> Result<(), String> {
        if self.reality_id.is_empty() {
            return Err("RealityID is empty".into());
        }
        if self.actor_user_ref_id.is_empty() {
            return Err("ActorUserRefID is empty".into());
        }
        if self.intent.requires_session() && self.session_id.is_none() {
            return Err(format!("intent {:?} requires session_id", self.intent));
        }
        if matches!(self.intent, Intent::AdminTriggered) && self.admin_tier.is_empty() {
            return Err("admin_triggered requires admin_tier".into());
        }
        Ok(())
    }
}

/// Retrieval depth caps (caller overrides; per-template defaults supersede 0).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RetrievalHints {
    #[serde(default)]
    pub max_memories: u32,
    #[serde(default)]
    pub max_history_events: u32,
    #[serde(default)]
    pub relevance_query: String,
}

/// `AssemblePrompt` return type. **No body field** (S09 §12Y).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptBundle {
    /// **OPAQUE** per Q-L4D-1. Provider-specific JSON, already redacted.
    pub provider_payload: JsonValue,

    /// SHA-256 of the rendered prompt; 32 raw bytes. Wire form = base64
    /// via serde's default for Vec<u8>; we keep it inline since the Go
    /// counterpart serializes as base64-via-byte-array.
    pub context_hash: [u8; 32],

    /// UUID string of the audit row this bundle produced.
    pub prompt_audit_id: String,

    pub estimated_cost_usd: String,
    pub template_id: String,
    pub template_version: u32,
    pub provider_name: String,
    pub model_ref: String,
}

impl PromptBundle {
    /// Body-never-stored invariant + minimal shape.
    pub fn validate(&self) -> Result<(), String> {
        if self.provider_payload.is_null() {
            return Err("ProviderPayload empty (null)".into());
        }
        if self.context_hash == [0u8; 32] {
            return Err("ContextHash is zero".into());
        }
        if self.prompt_audit_id.is_empty() {
            return Err("PromptAuditID empty".into());
        }
        if self.template_id.is_empty() {
            return Err("TemplateID empty".into());
        }
        if self.template_version < 1 {
            return Err("TemplateVersion must be >= 1".into());
        }
        Ok(())
    }
}

// ── Composer ────────────────────────────────────────────────────────────

/// Composer error class (Q-L6H-1: FAIL not best-effort).
#[derive(Debug, Error)]
pub enum ComposerError {
    /// Missing or invalid PromptContext / SectionMap.
    #[error("composer failed: {0}")]
    Invalid(String),
    /// Safety / consent / token-budget hook denied.
    #[error("composer failed: hook denial: {0}")]
    HookDenial(String),
    /// ProviderEncoder error.
    #[error("composer failed: provider encode: {0}")]
    ProviderEncode(String),
    /// PromptAuditWriter error.
    #[error("composer failed: audit write: {0}")]
    AuditWrite(String),
    /// Composer dependency wiring error.
    #[error("composer failed: dep missing: {0}")]
    MissingDep(&'static str),
}

/// Section -> rendered bytes. Same boundary contract as Go's `SectionMap`.
pub type SectionMap = std::collections::HashMap<Section, Vec<u8>>;

/// Pre-assembly resolved context (filter chain V1 = empty).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ResolvedContext {
    pub allowed_events: Vec<ContextRef>,
    pub allowed_memories: Vec<ContextRef>,
    pub rejected_refs: Vec<RejectionRecord>,
}

/// Opaque (entity_type, entity_id) pair.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextRef {
    pub entity_type: String,
    pub entity_id: String,
}

/// **IDs + reasons only** — no content field (privacy invariant).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RejectionRecord {
    pub entity_type: String,
    pub entity_id: String,
    pub reason: String,
    pub filter: String,
}

/// Boundary between Composer's rendered text and a provider's wire shape.
/// **Opaque per Q-L4D-1** — foundation does not validate the bytes.
pub trait ProviderEncoder: Send + Sync {
    fn encode(&self, pc: &PromptContext, rendered: &[u8]) -> Result<JsonValue, String>;
    fn provider_name(&self) -> &str;
    fn model_ref(&self) -> &str;
}

/// Multi-layer injection defense (S09 §12Y.6). V1 default = [`NoopSafetyHooks`].
pub trait SafetyHooks: Send + Sync {
    fn pre_assembly(&self, pc: &PromptContext, sections: &SectionMap) -> Result<(), String>;
    fn post_assembly(&self, pc: &PromptContext, context_hash: &[u8; 32], payload: &JsonValue) -> Result<(), String>;
}

/// V1 no-op (Q-L6L-1).
pub struct NoopSafetyHooks;
impl SafetyHooks for NoopSafetyHooks {
    fn pre_assembly(&self, _: &PromptContext, _: &SectionMap) -> Result<(), String> { Ok(()) }
    fn post_assembly(&self, _: &PromptContext, _: &[u8; 32], _: &JsonValue) -> Result<(), String> { Ok(()) }
}

/// BYOK telemetry / training-on-input consent. V1 default = [`NoopConsentGate`].
pub trait ConsentGate: Send + Sync {
    fn check(&self, pc: &PromptContext) -> Result<(), String>;
}

/// V1 no-op (Q-L6L-1).
pub struct NoopConsentGate;
impl ConsentGate for NoopConsentGate {
    fn check(&self, _: &PromptContext) -> Result<(), String> { Ok(()) }
}

/// Per-intent token budget (S09 §12Y.7). V1 default = [`NoopTokenBudgetGate`].
pub trait TokenBudgetGate: Send + Sync {
    fn check(&self, pc: &PromptContext, rendered: &[u8]) -> Result<(), String>;
}

/// V1 no-op (Q-L6L-1).
pub struct NoopTokenBudgetGate;
impl TokenBudgetGate for NoopTokenBudgetGate {
    fn check(&self, _: &PromptContext, _: &[u8]) -> Result<(), String> { Ok(()) }
}

/// Foundation-internal audit-row shape. **No body field.**
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptAuditEntry {
    pub audit_id: String,
    /// SHA-256 of the rendered prompt — 32 bytes.
    pub prompt_context_hash: Vec<u8>,
    pub template_id: String,
    pub template_version: u32,
    pub intent: String,
    pub actor_user_ref_id: String,
    pub reality_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    pub estimated_cost_usd: String,
    #[serde(default)]
    pub rejected_refs: Vec<RejectionRecord>,
    pub created_at_nanos: i64,
}

impl PromptAuditEntry {
    pub fn validate(&self) -> Result<(), String> {
        if self.audit_id.is_empty() {
            return Err("audit_id empty".into());
        }
        if self.prompt_context_hash.len() != 32 {
            return Err(format!("prompt_context_hash must be 32 bytes; got {}", self.prompt_context_hash.len()));
        }
        if self.template_id.is_empty() { return Err("template_id empty".into()); }
        if self.template_version < 1 { return Err("template_version must be >= 1".into()); }
        if self.intent.is_empty() { return Err("intent empty".into()); }
        if self.actor_user_ref_id.is_empty() { return Err("actor_user_ref_id empty".into()); }
        if self.reality_id.is_empty() { return Err("reality_id empty".into()); }
        if self.created_at_nanos <= 1_577_836_800_000_000_000 {
            return Err(format!("created_at_nanos implausible: {}", self.created_at_nanos));
        }
        Ok(())
    }
}

/// Persists prompt-audit entries (production wires contracts/meta cycle 4).
pub trait PromptAuditWriter: Send + Sync {
    fn record_assembly(&self, entry: PromptAuditEntry) -> Result<(), String>;
}

/// In-memory recorder for foundation tests + downstream service unit tests.
#[derive(Debug, Default)]
pub struct InMemoryAuditWriter {
    inner: std::sync::Mutex<Vec<PromptAuditEntry>>,
}

impl InMemoryAuditWriter {
    pub fn new() -> Self { Self::default() }
    /// Returns a snapshot (clone) of all recorded entries.
    pub fn entries(&self) -> Vec<PromptAuditEntry> {
        self.inner.lock().unwrap().clone()
    }
}

impl PromptAuditWriter for InMemoryAuditWriter {
    fn record_assembly(&self, entry: PromptAuditEntry) -> Result<(), String> {
        entry.validate()?;
        self.inner.lock().unwrap().push(entry);
        Ok(())
    }
}

/// Composer trait. See module docs for FAIL discipline (Q-L6H-1).
pub trait Composer {
    fn assemble_prompt(&self, pc: &PromptContext, sections: &SectionMap) -> Result<PromptBundle, ComposerError>;
    fn resolve_context(&self, pc: &PromptContext) -> Result<ResolvedContext, ComposerError>;
}

/// Foundation skeleton Composer. Owns:
///   - Section-shape validation (FAIL on missing SYSTEM / unknown section).
///   - SHA-256 hashing of the rendered sections in canonical order.
///   - Safety / consent / token-budget hook dispatch (noop V1).
///   - Audit-row write (after successful post-assembly).
pub struct DefaultComposer {
    pub encoder: Box<dyn ProviderEncoder>,
    pub audit: Box<dyn PromptAuditWriter>,
    pub safety: Box<dyn SafetyHooks>,
    pub consent: Box<dyn ConsentGate>,
    pub token_budget: Box<dyn TokenBudgetGate>,
    pub new_audit_id: Box<dyn Fn() -> String + Send + Sync>,
    pub now_nanos: Box<dyn Fn() -> i64 + Send + Sync>,
}

impl Composer for DefaultComposer {
    fn assemble_prompt(&self, pc: &PromptContext, sections: &SectionMap) -> Result<PromptBundle, ComposerError> {
        pc.validate().map_err(ComposerError::Invalid)?;
        validate_sections(sections).map_err(ComposerError::Invalid)?;

        // Safety hooks BEFORE render. Denial → FAIL.
        self.safety.pre_assembly(pc, sections).map_err(ComposerError::HookDenial)?;
        self.consent.check(pc).map_err(ComposerError::HookDenial)?;

        // Render in canonical order. **Bytes never escape this function.**
        let rendered = render_in_order(sections);
        self.token_budget.check(pc, &rendered).map_err(ComposerError::HookDenial)?;

        // SHA-256.
        let mut hasher = Sha256::new();
        hasher.update(&rendered);
        let hash_bytes = hasher.finalize();
        let mut context_hash = [0u8; 32];
        context_hash.copy_from_slice(&hash_bytes);

        // Encode (opaque per Q-L4D-1).
        let payload = self.encoder.encode(pc, &rendered).map_err(ComposerError::ProviderEncode)?;
        if payload.is_null() {
            return Err(ComposerError::ProviderEncode("encoder returned null".into()));
        }

        // PostAssembly hook (canary, etc.). Denial → FAIL (before audit write).
        self.safety.post_assembly(pc, &context_hash, &payload).map_err(ComposerError::HookDenial)?;

        let audit_id = (self.new_audit_id)();
        if audit_id.is_empty() {
            return Err(ComposerError::MissingDep("new_audit_id returned empty"));
        }

        let entry = PromptAuditEntry {
            audit_id: audit_id.clone(),
            prompt_context_hash: context_hash.to_vec(),
            template_id: pick_template_id(pc),
            template_version: pick_template_version(pc),
            intent: pc.intent.as_str().to_string(),
            actor_user_ref_id: pc.actor_user_ref_id.clone(),
            reality_id: pc.reality_id.clone(),
            session_id: pc.session_id.clone(),
            estimated_cost_usd: "0".into(),
            rejected_refs: Vec::new(),
            created_at_nanos: (self.now_nanos)(),
        };
        self.audit.record_assembly(entry).map_err(ComposerError::AuditWrite)?;

        let bundle = PromptBundle {
            provider_payload: payload,
            context_hash,
            prompt_audit_id: audit_id,
            estimated_cost_usd: "0".into(),
            template_id: pick_template_id(pc),
            template_version: pick_template_version(pc),
            provider_name: self.encoder.provider_name().to_string(),
            model_ref: self.encoder.model_ref().to_string(),
        };
        bundle.validate().map_err(|e| ComposerError::Invalid(format!("bundle validate: {e}")))?;
        Ok(bundle)
    }

    fn resolve_context(&self, pc: &PromptContext) -> Result<ResolvedContext, ComposerError> {
        pc.validate().map_err(ComposerError::Invalid)?;
        Ok(ResolvedContext::default())
    }
}

fn validate_sections(m: &SectionMap) -> Result<(), String> {
    if m.is_empty() {
        return Err("SectionMap is empty".into());
    }
    // Q-L6H-1: FAIL on missing SYSTEM section (always required V1).
    if !m.contains_key(&Section::System) {
        return Err("SectionSystem missing — every prompt MUST carry SYSTEM bytes".into());
    }
    Ok(())
}

fn render_in_order(m: &SectionMap) -> Vec<u8> {
    let mut out = Vec::new();
    for sec in Section::all() {
        out.extend_from_slice(b"\n[");
        out.extend_from_slice(sec.as_str().as_bytes());
        out.extend_from_slice(b"]\n");
        if let Some(bytes) = m.get(sec) {
            out.extend_from_slice(bytes);
        }
        out.push(b'\n');
    }
    out
}

fn pick_template_id(pc: &PromptContext) -> String {
    if !pc.template_id.is_empty() { pc.template_id.clone() } else { pc.intent.as_str().to_string() }
}

fn pick_template_version(pc: &PromptContext) -> u32 {
    if pc.template_version >= 1 { pc.template_version } else { 1 }
}

// ── Tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    fn ctx_session() -> PromptContext {
        PromptContext {
            reality_id: "00000000-0000-0000-0000-000000000001".into(),
            session_id: Some("00000000-0000-0000-0000-000000000002".into()),
            actor_user_ref_id: "00000000-0000-0000-0000-000000000003".into(),
            actor_pc_id: None,
            intent: Intent::SessionTurn,
            retrieval_hints: RetrievalHints::default(),
            admin_tier: String::new(),
            consent_snapshot_id: None,
            template_id: String::new(),
            template_version: 0,
        }
    }

    fn valid_sections() -> SectionMap {
        let mut m = SectionMap::new();
        m.insert(Section::System, b"you are a roleplay engine".to_vec());
        m.insert(Section::Instruction, b"describe the scene".to_vec());
        m.insert(Section::Input, b"the player swings their sword".to_vec());
        m
    }

    struct FakeEncoder { payload: JsonValue, fail: bool }
    impl ProviderEncoder for FakeEncoder {
        fn encode(&self, _: &PromptContext, _: &[u8]) -> Result<JsonValue, String> {
            if self.fail { Err("provider unreachable".into()) } else { Ok(self.payload.clone()) }
        }
        fn provider_name(&self) -> &str { "anthropic" }
        fn model_ref(&self) -> &str { "claude-test" }
    }

    struct DenyingSafety { pre: bool, post: bool }
    impl SafetyHooks for DenyingSafety {
        fn pre_assembly(&self, _: &PromptContext, _: &SectionMap) -> Result<(), String> {
            if self.pre { Err("jailbreak".into()) } else { Ok(()) }
        }
        fn post_assembly(&self, _: &PromptContext, _: &[u8; 32], _: &JsonValue) -> Result<(), String> {
            if self.post { Err("canary leaked".into()) } else { Ok(()) }
        }
    }

    fn build_composer() -> (DefaultComposer, std::sync::Arc<InMemoryAuditWriter>) {
        let aw = std::sync::Arc::new(InMemoryAuditWriter::new());
        let aw_cl = aw.clone();
        let counter = std::sync::Arc::new(AtomicU64::new(0));
        let counter_cl = counter.clone();
        let comp = DefaultComposer {
            encoder: Box::new(FakeEncoder { payload: serde_json::json!({"messages":[]}), fail: false }),
            audit: Box::new(AuditProxy(aw_cl)),
            safety: Box::new(NoopSafetyHooks),
            consent: Box::new(NoopConsentGate),
            token_budget: Box::new(NoopTokenBudgetGate),
            new_audit_id: Box::new(move || {
                let n = counter_cl.fetch_add(1, Ordering::SeqCst);
                format!("00000000-0000-0000-0000-{:012x}", n + 1)
            }),
            now_nanos: Box::new(|| 1_800_000_000_000_000_000_i64),
        };
        (comp, aw)
    }

    // small adapter so audit writer can be shared via Arc.
    struct AuditProxy(std::sync::Arc<InMemoryAuditWriter>);
    impl PromptAuditWriter for AuditProxy {
        fn record_assembly(&self, entry: PromptAuditEntry) -> Result<(), String> {
            self.0.record_assembly(entry)
        }
    }

    // ── Enum coverage ────────────────────────────────────────────────

    #[test]
    fn intent_count_is_seven() {
        assert_eq!(Intent::all().len(), 7);
    }

    #[test]
    fn section_count_and_order_fixed() {
        let all = Section::all();
        assert_eq!(all.len(), 8);
        assert_eq!(all[0], Section::System);
        assert_eq!(all[7], Section::Input);
    }

    #[test]
    fn only_input_is_user_sandbox() {
        for s in Section::all() {
            assert_eq!(s.is_user_sandbox(), matches!(s, Section::Input));
        }
    }

    #[test]
    fn intent_wire_format_snake_case() {
        let v = serde_json::to_string(&Intent::SessionTurn).unwrap();
        assert_eq!(v, "\"session_turn\"");
        let v2 = serde_json::to_string(&Intent::AdminTriggered).unwrap();
        assert_eq!(v2, "\"admin_triggered\"");
    }

    #[test]
    fn section_wire_format_uppercase() {
        let v = serde_json::to_string(&Section::WorldCanon).unwrap();
        assert_eq!(v, "\"WORLD_CANON\"");
    }

    // ── Validate ─────────────────────────────────────────────────────

    #[test]
    fn context_validate_session_required_for_session_turn() {
        let mut pc = ctx_session();
        pc.session_id = None;
        assert!(pc.validate().is_err());
    }

    #[test]
    fn context_validate_admin_tier_required() {
        let mut pc = ctx_session();
        pc.session_id = None;
        pc.intent = Intent::AdminTriggered;
        assert!(pc.validate().is_err());
        pc.admin_tier = "tier_1".into();
        assert!(pc.validate().is_ok());
    }

    // ── Happy path ────────────────────────────────────────────────────

    #[test]
    fn assemble_happy_path_writes_audit() {
        let (comp, aw) = build_composer();
        let bundle = comp.assemble_prompt(&ctx_session(), &valid_sections()).expect("happy path");
        bundle.validate().expect("bundle valid");
        let entries = aw.entries();
        assert_eq!(entries.len(), 1, "audit row not written");
        assert_eq!(entries[0].prompt_context_hash.len(), 32);
        assert_eq!(entries[0].prompt_context_hash.as_slice(), &bundle.context_hash[..]);
    }

    #[test]
    fn assemble_deterministic_hash() {
        let (c1, _) = build_composer();
        let (c2, _) = build_composer();
        let b1 = c1.assemble_prompt(&ctx_session(), &valid_sections()).unwrap();
        let b2 = c2.assemble_prompt(&ctx_session(), &valid_sections()).unwrap();
        assert_eq!(b1.context_hash, b2.context_hash);
    }

    // ── Q-L6H-1 FAIL discipline ──────────────────────────────────────

    #[test]
    fn fail_on_missing_system_section() {
        let (comp, aw) = build_composer();
        let mut bad = valid_sections();
        bad.remove(&Section::System);
        let res = comp.assemble_prompt(&ctx_session(), &bad);
        assert!(matches!(res, Err(ComposerError::Invalid(_))));
        assert_eq!(aw.entries().len(), 0, "audit must not write on FAIL");
    }

    #[test]
    fn fail_on_empty_sections() {
        let (comp, _) = build_composer();
        let res = comp.assemble_prompt(&ctx_session(), &SectionMap::new());
        assert!(matches!(res, Err(ComposerError::Invalid(_))));
    }

    #[test]
    fn fail_on_invalid_context() {
        let (comp, _) = build_composer();
        let mut pc = ctx_session();
        pc.actor_user_ref_id = String::new();
        let res = comp.assemble_prompt(&pc, &valid_sections());
        assert!(matches!(res, Err(ComposerError::Invalid(_))));
    }

    #[test]
    fn fail_on_safety_pre_denial_no_audit() {
        let (mut comp, aw) = build_composer();
        comp.safety = Box::new(DenyingSafety { pre: true, post: false });
        let res = comp.assemble_prompt(&ctx_session(), &valid_sections());
        assert!(matches!(res, Err(ComposerError::HookDenial(_))));
        assert_eq!(aw.entries().len(), 0);
    }

    #[test]
    fn fail_on_safety_post_denial_no_audit() {
        let (mut comp, aw) = build_composer();
        comp.safety = Box::new(DenyingSafety { pre: false, post: true });
        let res = comp.assemble_prompt(&ctx_session(), &valid_sections());
        assert!(matches!(res, Err(ComposerError::HookDenial(_))));
        assert_eq!(aw.entries().len(), 0, "post-denial must not commit audit");
    }

    #[test]
    fn fail_on_encoder_error() {
        let (mut comp, _) = build_composer();
        comp.encoder = Box::new(FakeEncoder { payload: serde_json::Value::Null, fail: true });
        let res = comp.assemble_prompt(&ctx_session(), &valid_sections());
        assert!(matches!(res, Err(ComposerError::ProviderEncode(_))));
    }

    #[test]
    fn fail_on_null_payload() {
        let (mut comp, _) = build_composer();
        comp.encoder = Box::new(FakeEncoder { payload: serde_json::Value::Null, fail: false });
        let res = comp.assemble_prompt(&ctx_session(), &valid_sections());
        assert!(matches!(res, Err(ComposerError::ProviderEncode(_))));
    }

    // ── ResolveContext skeleton ──────────────────────────────────────

    #[test]
    fn resolve_context_returns_empty_v1() {
        let (comp, _) = build_composer();
        let rc = comp.resolve_context(&ctx_session()).unwrap();
        assert!(rc.allowed_events.is_empty());
        assert!(rc.allowed_memories.is_empty());
        assert!(rc.rejected_refs.is_empty());
    }

    // ── Body-never-stored JSON shape gate ─────────────────────────────

    #[test]
    fn bundle_json_has_no_body_field() {
        let b = PromptBundle {
            provider_payload: serde_json::json!({"x":1}),
            context_hash: [1u8; 32],
            prompt_audit_id: "id".into(),
            estimated_cost_usd: "0".into(),
            template_id: "tpl".into(),
            template_version: 1,
            provider_name: "p".into(),
            model_ref: "m".into(),
        };
        let raw = serde_json::to_string(&b).unwrap();
        for bad in &["\"body\"", "\"rendered\"", "\"prompt_text\"", "\"assembled\""] {
            assert!(!raw.contains(bad), "PromptBundle JSON carries forbidden field {bad}");
        }
    }

    #[test]
    fn audit_entry_json_has_no_body_field() {
        let e = PromptAuditEntry {
            audit_id: "id".into(),
            prompt_context_hash: vec![0u8; 32],
            template_id: "tpl".into(),
            template_version: 1,
            intent: Intent::SessionTurn.as_str().into(),
            actor_user_ref_id: "a".into(),
            reality_id: "r".into(),
            session_id: None,
            estimated_cost_usd: "0".into(),
            rejected_refs: vec![],
            created_at_nanos: 1_800_000_000_000_000_000,
        };
        let raw = serde_json::to_string(&e).unwrap();
        for bad in &["\"body\"", "\"rendered\"", "\"prompt_text\"", "\"assembled\""] {
            assert!(!raw.contains(bad), "PromptAuditEntry JSON carries forbidden field {bad}");
        }
    }
}
