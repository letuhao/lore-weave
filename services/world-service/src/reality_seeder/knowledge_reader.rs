//! L5.G.4 — Knowledge-service RPC reader trait.
//!
//! Reads NPC proxies (the entity-graph layer that anchors authored
//! glossary characters to fuzzy/semantic instances per CLAUDE.md
//! two-layer pattern). V1: trait surface only; production HTTP client
//! lands when knowledge-service is in foundation scope (currently
//! outside this cycle's reach per L5.G brief).
//!
//! ## Q-IDs honored
//!
//! - **Q-L5-4** — when knowledge-service ships, production binding
//!   uses HTTP/JSON V1 (matches the glossary_client cycle-25 pattern).

use crate::reality_seeder::SeederError;
use uuid::Uuid;

/// NPC proxy — fuzzy/semantic anchor that links a knowledge-service
/// entity to its authored glossary canon entry (per CLAUDE.md two-layer
/// pattern: glossary SSOT + knowledge-service fuzzy layer with
/// `glossary_entity_id` FK).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NpcProxy {
    /// Knowledge-service proxy UUID.
    pub proxy_id: Uuid,
    /// FK to glossary canon (matches CLAUDE.md two-layer pattern).
    pub glossary_entity_id: Option<Uuid>,
    /// Display name (audit + log convenience).
    pub display_name: String,
    /// Free-form role tags (e.g. `["protagonist", "merchant"]`).
    pub role_tags: Vec<String>,
}

/// Knowledge-service RPC trait — read-only surface used by L5.G.
/// Errors map to [`SeederError`].
pub trait KnowledgeReader {
    /// Returns NPC proxies for a given book. V1 default returns empty
    /// (knowledge-service path not in foundation scope yet); production
    /// override binds to the HTTP/JSON client.
    fn list_npcs(&self, _book_id: Uuid) -> Result<Vec<NpcProxy>, SeederError> {
        Ok(Vec::new())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Fixture {
        npcs: Vec<NpcProxy>,
    }
    impl KnowledgeReader for Fixture {
        fn list_npcs(&self, _book_id: Uuid) -> Result<Vec<NpcProxy>, SeederError> {
            Ok(self.npcs.clone())
        }
    }

    #[test]
    fn default_returns_empty() {
        struct F;
        impl KnowledgeReader for F {}
        let f = F;
        assert_eq!(f.list_npcs(Uuid::nil()).unwrap().len(), 0);
    }

    #[test]
    fn fixture_returns_npc_set() {
        let f = Fixture {
            npcs: vec![NpcProxy {
                proxy_id: Uuid::from_u128(0x1),
                glossary_entity_id: Some(Uuid::from_u128(0x2)),
                display_name: "Alice".into(),
                role_tags: vec!["protagonist".into()],
            }],
        };
        let got = f.list_npcs(Uuid::from_u128(0x10)).unwrap();
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].display_name, "Alice");
    }
}
