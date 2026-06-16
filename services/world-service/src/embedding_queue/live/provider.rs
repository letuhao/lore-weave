//! Fail-closed [`EmbeddingProvider`] placeholder.
//!
//! The real BYOK provider-gateway binding is the **deferred** task
//! `D-EMBEDDING-PROVIDER-WIRING`: a reqwest client to provider-registry-service
//! `POST /internal/embed` (the route + its internal s2s auth already exist —
//! see `provider-registry-service/internal/api/server.go`), plus `reality_id →
//! owner user_id` resolution (the endpoint needs `?user_id=` to pick the
//! owner's BYOK credential) and embedding `model_ref` selection. It is the
//! first `reqwest` use in world-service. Until it lands, the `embedding-worker`
//! binary wires THIS provider, which fails every call closed — mirroring the
//! admin-cli `NotWiredHandler` pattern: a deployed binary is observable and
//! drains its queue, but every attempt is audited as a `ProviderError`
//! (never silently a no-op, never a fake success).

use async_trait::async_trait;

use crate::embedding_queue::{EmbedResult, EmbeddingProvider};

/// Provider that refuses every call with a clear, greppable reason. Wired by
/// the binary so production is fail-closed until `D-EMBEDDING-PROVIDER-WIRING`.
#[derive(Debug, Default, Clone)]
pub struct NotWiredProvider;

#[async_trait]
impl EmbeddingProvider for NotWiredProvider {
    async fn embed(&self, _text: &str) -> (String, EmbedResult) {
        (
            "not-wired".to_string(),
            EmbedResult::ProviderError(
                "embedding provider not wired (D-EMBEDDING-PROVIDER-WIRING): \
                 needs a reqwest client to provider-registry POST /internal/embed \
                 + reality->owner user_id resolution + model_ref selection"
                    .to_string(),
            ),
        )
    }

    fn provider_name(&self) -> &str {
        "not-wired"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn not_wired_provider_always_errors() {
        let p = NotWiredProvider;
        let (model, result) = p.embed("anything").await;
        assert_eq!(model, "not-wired");
        assert!(matches!(result, EmbedResult::ProviderError(_)));
        assert_eq!(p.provider_name(), "not-wired");
    }
}
