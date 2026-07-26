//! The AGT-A2 closed vocabulary — loaded from `contracts/agent/` (data, not
//! code: one declaration serves the model as tool schemas AND commit-service
//! as the validation set; a drift between the two is impossible because there
//! is only one file).
//!
//! Validation is the chaos limiter: a Decision naming a tool outside the set,
//! a stance outside the enum, or a target outside the OFFERED candidates
//! (THR-A4 — the model cannot name anyone the engine did not offer) REJECTS
//! to the vocabulary's `fallback_tool`. Never silent (CS-A4 discipline).

use serde::Deserialize;
use sim_core::EntityId;

use crate::domain::{CombatPayload, Stance};

#[derive(Debug, Deserialize)]
pub struct Vocabulary {
    pub vocabulary_id: String,
    pub fallback_tool: String,
    pub tools: Vec<ToolDef>,
}

#[derive(Debug, Deserialize)]
pub struct ToolDef {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
}

/// Why a decision was rejected — recorded per AGT-A2 (reject → fallback),
/// aggregated into the POC validity-rate metric.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum Reject {
    #[error("tool '{0}' is not in the closed vocabulary")]
    UnknownTool(String),
    #[error("arguments are not valid JSON: {0}")]
    BadArgumentsJson(String),
    #[error("strike.target '{0}' was not among the offered candidates")]
    TargetNotOffered(String),
    #[error("move.stance '{0}' is outside the closed enum")]
    BadStance(String),
    #[error("no tool call in the model response (finish={0})")]
    NoToolCall(String),
}

impl Vocabulary {
    /// Load a vocabulary file (e.g. `contracts/agent/vocabularies/combat_v1.json`).
    pub fn from_json(json: &str) -> anyhow::Result<Self> {
        let v: Vocabulary = serde_json::from_str(json)?;
        anyhow::ensure!(
            v.tools.iter().any(|t| t.name == v.fallback_tool),
            "vocabulary '{}' declares fallback_tool '{}' outside its own closed set",
            v.vocabulary_id,
            v.fallback_tool
        );
        Ok(v)
    }

    /// The tool definitions as OpenAI-shaped function tools — exactly what
    /// `ChatStreamRequest.tools` wants (the gateway translates per provider).
    pub fn openai_tools(&self) -> Vec<serde_json::Value> {
        self.tools
            .iter()
            .map(|t| {
                serde_json::json!({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                })
            })
            .collect()
    }

    pub fn contains(&self, tool: &str) -> bool {
        self.tools.iter().any(|t| t.name == tool)
    }

    /// Validate a raw tool-call against the closed set + the offered
    /// candidates, and map it to the domain payload for `actor`.
    ///
    /// `candidates` are the entity ids the DecisionContext OFFERED — the
    /// only legal strike targets (anti-hallucination gate at validation,
    /// mirroring THR-Q7's guard-at-accrual principle).
    pub fn validate(
        &self,
        actor: EntityId,
        tool_name: &str,
        raw_arguments: &str,
        candidates: &[(EntityId, String)],
    ) -> Result<CombatPayload, Reject> {
        if !self.contains(tool_name) {
            return Err(Reject::UnknownTool(tool_name.to_string()));
        }
        // Empty arguments are legal for zero-arg tools (defend/flee).
        let args: serde_json::Value = if raw_arguments.trim().is_empty() {
            serde_json::json!({})
        } else {
            serde_json::from_str(raw_arguments)
                .map_err(|e| Reject::BadArgumentsJson(e.to_string()))?
        };

        match tool_name {
            "strike" => {
                let target_label = args
                    .get("target")
                    .and_then(|t| t.as_str())
                    .unwrap_or_default()
                    .to_string();
                let target = candidates
                    .iter()
                    .find(|(_, label)| *label == target_label)
                    .map(|(id, _)| *id)
                    .ok_or(Reject::TargetNotOffered(target_label))?;
                Ok(CombatPayload::Strike { attacker: actor, target })
            }
            "defend" => Ok(CombatPayload::Defend { actor }),
            "move" => {
                let raw = args.get("stance").cloned().unwrap_or(serde_json::Value::Null);
                let stance: Stance = serde_json::from_value(raw.clone())
                    .map_err(|_| Reject::BadStance(raw.to_string()))?;
                Ok(CombatPayload::Move { actor, stance })
            }
            "flee" => Ok(CombatPayload::Flee { actor }),
            other => Err(Reject::UnknownTool(other.to_string())),
        }
    }

    /// The AGT-A2 context fallback as a domain payload (combat: Defend).
    pub fn fallback_payload(&self, actor: EntityId) -> CombatPayload {
        // combat_v1 pins fallback_tool = "defend"; the constructor validated
        // membership, and defend is total.
        CombatPayload::Defend { actor }
    }
}
