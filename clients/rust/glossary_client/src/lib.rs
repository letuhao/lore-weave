//! L5.F.4 Rust HTTP/JSON client for glossary-service canon RPCs.
//!
//! RAID cycle 25 DPS 2. Mirror of `clients/go/glossary_client` for Rust
//! consumers (world-service Rust shards, roleplay-service Rust shards
//! when those land).
//!
//! # Q-IDs honored
//!
//! - **Q-L5-4**: HTTP/JSON V1 (matches existing LoreWeave platform).
//!   gRPC V2+ if perf demands; not in scope this cycle.
//! - **Q-L5-5**: [`Client::write_canon_entry`] surfaces HTTP 409
//!   responses as [`Error::GuardrailRejected`] with the full
//!   [`GuardrailViolation`] payload.
//! - **Q-L5-3**: `canon_layer` enum strings match cycle-23 contract
//!   (`"L1_axiom"` | `"L2_seeded"`).
//!
//! # Retry policy (cycle 18 resilience integration)
//!
//! The client itself is RETRY-FREE. Callers wrap with their own
//! resilience layer (retry budget, bulkhead, timeout) — keeping the
//! client surface inspectable and tests deterministic.

use serde::{Deserialize, Serialize};
use std::time::Duration;
use uuid::Uuid;

/// Errors returned by [`Client`] methods.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("glossary_client: canon entry not found")]
    NotFound,
    #[error("glossary_client: caller SVID not authorized")]
    Forbidden,
    #[error("glossary_client: missing or invalid SVID")]
    Unauthorized,
    #[error("glossary_client: HTTP {status} code={code} msg={message}")]
    Http {
        status: u16,
        code: String,
        message: String,
    },
    /// Q-L5-5: server rejected the proposed write because it conflicts
    /// with L1 axiom canon. Callers MUST surface this to the user.
    #[error("glossary_client: guardrail rejected (Q-L5-5) book={book} attr={attr} reason={reason}",
        book = .0.axiom.book_id, attr = .0.axiom.attribute_path, reason = .0.reason)]
    GuardrailRejected(GuardrailViolation),
    #[error("glossary_client: transport: {0}")]
    Transport(String),
    #[error("glossary_client: decode: {0}")]
    Decode(String),
    #[error("glossary_client: SVID provider: {0}")]
    Svid(String),
    #[error("glossary_client: validation: {0}")]
    Validation(String),
}

/// Q-L5-5 GuardrailViolation payload (HTTP 409 body shape).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GuardrailViolation {
    pub code: String,
    pub axiom: CanonReference,
    pub proposed_value: serde_json::Value,
    pub reason: String,
}

/// L1 axiom info inside a [`GuardrailViolation`].
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CanonReference {
    pub book_id: String,
    pub attribute_path: String,
    pub canon_layer: String,
    pub value: serde_json::Value,
}

/// Per-canon response wire shape.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanonEntry {
    pub canon_entry_id: String,
    pub book_id: String,
    pub attribute_path: String,
    pub value: serde_json::Value,
    /// Q-L5-3 enum.
    pub canon_layer: String,
    pub lock_level: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub reality_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub overridden_by_l3_event_id: Option<String>,
    /// Q-L5-1 cache invalidation key (RFC3339 string on the wire).
    pub last_synced_at: String,
}

/// Bulk-read response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanonEntryPage {
    pub entries: Vec<CanonEntry>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub next_cursor: Option<String>,
}

/// POST /v1/canon request body.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanonWriteRequest {
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub canon_entry_id: Option<String>,
    pub book_id: String,
    pub attribute_path: String,
    pub value: serde_json::Value,
    pub canon_layer: String,
    #[serde(skip_serializing_if = "String::is_empty", default)]
    pub lock_level: String,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub reality_id: Option<String>,
}

/// POST /v1/canon success body.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanonWriteResponse {
    pub canon_entry_id: String,
    pub written_at: String,
    pub canon_layer: String,
}

/// L5.F.2 NDJSON final-line envelope returned by
/// [`Client::export_canon_for_seed`]. Sentinel `_envelope` field is
/// always `"seed_export_complete"` (matches OpenAPI spec).
///
/// `next_cursor`, when present, signals the caller to repeat the call
/// with `cursor=<value>` to drain the next page (used only by very
/// large books).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SeedExportEnvelope {
    #[serde(rename = "_envelope")]
    pub envelope: String,
    pub snapshot_at: String,
    pub entry_count: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

/// Async SVID provider.
pub type SvidProvider =
    Box<dyn Fn() -> futures_returning_string::BoxedSvidFuture + Send + Sync + 'static>;

// We avoid pulling in the `futures` crate; use a small re-export module
// for the async return type. Internally we just use a Pin<Box<dyn ...>>.
mod futures_returning_string {
    use std::future::Future;
    use std::pin::Pin;

    pub type BoxedSvidFuture =
        Pin<Box<dyn Future<Output = Result<String, String>> + Send + 'static>>;
}

/// Configuration for [`Client::new`].
pub struct ClientConfig {
    pub base_url: String,
    pub svid: SvidProvider,
    pub client_id: Option<String>,
    pub timeout: Option<Duration>,
}

/// HTTP/JSON client.
pub struct Client {
    base_url: String,
    http: reqwest::Client,
    svid: SvidProvider,
    client_id: Option<String>,
}

impl Client {
    /// Construct a client. `base_url` + `svid` are required.
    pub fn new(cfg: ClientConfig) -> Result<Self, Error> {
        if cfg.base_url.is_empty() {
            return Err(Error::Validation("base_url empty".into()));
        }
        let http = reqwest::Client::builder()
            .timeout(cfg.timeout.unwrap_or(Duration::from_secs(5)))
            .build()
            .map_err(|e| Error::Transport(e.to_string()))?;
        Ok(Self {
            base_url: cfg.base_url.trim_end_matches('/').to_string(),
            http,
            svid: cfg.svid,
            client_id: cfg.client_id,
        })
    }

    async fn svid_token(&self) -> Result<String, Error> {
        let fut = (self.svid)();
        fut.await.map_err(Error::Svid)
    }

    fn auth_headers(&self, token: &str) -> reqwest::header::HeaderMap {
        let mut h = reqwest::header::HeaderMap::new();
        h.insert(
            reqwest::header::AUTHORIZATION,
            reqwest::header::HeaderValue::from_str(&format!("Bearer {token}")).unwrap(),
        );
        if let Some(id) = &self.client_id {
            if let Ok(v) = reqwest::header::HeaderValue::from_str(id) {
                h.insert("X-Client-ID", v);
            }
        }
        h.insert(
            reqwest::header::ACCEPT,
            reqwest::header::HeaderValue::from_static("application/json"),
        );
        h
    }

    /// GET /v1/canon/{book_id}/{attribute_path} — single read.
    pub async fn get_canon_entry(
        &self,
        book_id: &str,
        attribute_path: &str,
        reality_id: Option<&str>,
    ) -> Result<CanonEntry, Error> {
        if book_id.is_empty() || attribute_path.is_empty() {
            return Err(Error::Validation("book_id + attribute_path required".into()));
        }
        let mut url = format!(
            "{}/v1/canon/{}/{}",
            self.base_url,
            urlencode(book_id),
            urlencode(attribute_path)
        );
        if let Some(r) = reality_id {
            url.push_str(&format!("?reality_id={}", urlencode(r)));
        }
        let token = self.svid_token().await?;
        let resp = self
            .http
            .get(&url)
            .headers(self.auth_headers(&token))
            .send()
            .await
            .map_err(|e| Error::Transport(e.to_string()))?;
        classify(resp).await.and_then(|body| {
            serde_json::from_slice::<CanonEntry>(&body).map_err(|e| Error::Decode(e.to_string()))
        })
    }

    /// GET /v1/canon/{book_id}/entries — bulk read with optional since= filter.
    pub async fn list_canon_entries(
        &self,
        book_id: &str,
        since_rfc3339: Option<&str>,
        limit: Option<u32>,
        cursor: Option<&str>,
    ) -> Result<CanonEntryPage, Error> {
        if book_id.is_empty() {
            return Err(Error::Validation("book_id required".into()));
        }
        let mut url = format!(
            "{}/v1/canon/{}/entries",
            self.base_url,
            urlencode(book_id)
        );
        let mut q = Vec::new();
        if let Some(s) = since_rfc3339 {
            q.push(format!("since={}", urlencode(s)));
        }
        if let Some(l) = limit {
            q.push(format!("limit={l}"));
        }
        if let Some(c) = cursor {
            q.push(format!("cursor={}", urlencode(c)));
        }
        if !q.is_empty() {
            url.push('?');
            url.push_str(&q.join("&"));
        }
        let token = self.svid_token().await?;
        let resp = self
            .http
            .get(&url)
            .headers(self.auth_headers(&token))
            .send()
            .await
            .map_err(|e| Error::Transport(e.to_string()))?;
        classify(resp).await.and_then(|body| {
            serde_json::from_slice::<CanonEntryPage>(&body)
                .map_err(|e| Error::Decode(e.to_string()))
        })
    }

    /// POST /v1/canon — write canon entry. Q-L5-5: 409 → [`Error::GuardrailRejected`].
    pub async fn write_canon_entry(
        &self,
        req: CanonWriteRequest,
    ) -> Result<CanonWriteResponse, Error> {
        if req.book_id.is_empty() || req.attribute_path.is_empty() || req.canon_layer.is_empty() {
            return Err(Error::Validation(
                "book_id + attribute_path + canon_layer required".into(),
            ));
        }
        let token = self.svid_token().await?;
        let resp = self
            .http
            .post(format!("{}/v1/canon", self.base_url))
            .headers(self.auth_headers(&token))
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .json(&req)
            .send()
            .await
            .map_err(|e| Error::Transport(e.to_string()))?;

        if resp.status().as_u16() == 409 {
            // Q-L5-5 guardrail rejection.
            let bytes = resp
                .bytes()
                .await
                .map_err(|e| Error::Transport(e.to_string()))?;
            let v: GuardrailViolation = serde_json::from_slice(&bytes)
                .map_err(|e| Error::Decode(format!("GuardrailViolation: {e}")))?;
            return Err(Error::GuardrailRejected(v));
        }

        classify(resp).await.and_then(|body| {
            serde_json::from_slice::<CanonWriteResponse>(&body)
                .map_err(|e| Error::Decode(e.to_string()))
        })
    }

    /// L5.F.2 / L5.G — bulk export canon entries for reality seeding.
    ///
    /// Streams NDJSON: one [`CanonEntry`] per line, followed by exactly one
    /// [`SeedExportEnvelope`] sentinel line carrying the snapshot
    /// timestamp + entry count + optional pagination cursor.
    ///
    /// Returns `(Vec<CanonEntry>, SeedExportEnvelope)` so the L5.G reality
    /// seeder can drive its idempotent UPSERT in a single pass.
    ///
    /// # Pagination
    /// For large books, the server may set `envelope.next_cursor`. Callers
    /// (cycle 26 `reality_seeder/canon_reader.rs`) drain pages in a loop
    /// until `next_cursor` is `None`.
    ///
    /// # ACL (cycle 25 L5.F.3)
    /// Only `world-service` SVID is permitted (system_only principal mode).
    /// Other callers receive 403 → [`Error::Forbidden`].
    ///
    /// # Q-L5-4
    /// HTTP/JSON V1 (NDJSON is JSON-per-line, not a separate protocol).
    pub async fn export_canon_for_seed(
        &self,
        book_id: &str,
        cursor: Option<&str>,
    ) -> Result<(Vec<CanonEntry>, SeedExportEnvelope), Error> {
        if book_id.is_empty() {
            return Err(Error::Validation("book_id required".into()));
        }
        let mut url = format!(
            "{}/v1/canon/{}/seed_export",
            self.base_url,
            urlencode(book_id)
        );
        if let Some(c) = cursor {
            url.push_str(&format!("?cursor={}", urlencode(c)));
        }
        let token = self.svid_token().await?;
        let resp = self
            .http
            .get(&url)
            .headers(self.auth_headers(&token))
            .send()
            .await
            .map_err(|e| Error::Transport(e.to_string()))?;
        let body = classify(resp).await?;

        // NDJSON: split on newlines; tolerate trailing newline.
        let text = std::str::from_utf8(&body)
            .map_err(|e| Error::Decode(format!("ndjson utf8: {e}")))?;
        let mut entries: Vec<CanonEntry> = Vec::new();
        let mut envelope: Option<SeedExportEnvelope> = None;
        for (idx, line) in text.split('\n').enumerate() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            // Probe for the envelope sentinel before attempting CanonEntry
            // decode (CanonEntry fields would error on the envelope shape).
            #[derive(Deserialize)]
            struct Probe {
                #[serde(default, rename = "_envelope")]
                envelope: String,
            }
            let probe: Probe = serde_json::from_str(line).unwrap_or(Probe { envelope: String::new() });
            if probe.envelope == "seed_export_complete" {
                let env: SeedExportEnvelope = serde_json::from_str(line)
                    .map_err(|e| Error::Decode(format!("envelope line {idx}: {e}")))?;
                envelope = Some(env);
                continue;
            }
            let entry: CanonEntry = serde_json::from_str(line)
                .map_err(|e| Error::Decode(format!("entry line {idx}: {e}")))?;
            entries.push(entry);
        }
        let envelope = envelope.ok_or_else(|| {
            Error::Decode("seed_export NDJSON missing envelope sentinel".into())
        })?;
        Ok((entries, envelope))
    }
}

async fn classify(resp: reqwest::Response) -> Result<Vec<u8>, Error> {
    let status = resp.status();
    if status.is_success() {
        let bytes = resp
            .bytes()
            .await
            .map_err(|e| Error::Transport(e.to_string()))?;
        return Ok(bytes.to_vec());
    }
    match status.as_u16() {
        401 => Err(Error::Unauthorized),
        403 => Err(Error::Forbidden),
        404 => Err(Error::NotFound),
        _ => {
            let bytes = resp
                .bytes()
                .await
                .map_err(|e| Error::Transport(e.to_string()))?;
            #[derive(Deserialize, Default)]
            struct Env {
                #[serde(default)]
                code: String,
                #[serde(default)]
                message: String,
            }
            let env: Env = serde_json::from_slice(&bytes).unwrap_or_default();
            Err(Error::Http {
                status: status.as_u16(),
                code: env.code,
                message: env.message,
            })
        }
    }
}

fn urlencode(s: &str) -> String {
    // Minimal RFC3986 path/query escape — only the chars commonly in
    // UUIDs / attribute_paths / cursors. wiremock + reqwest test
    // coverage validates the chars we actually emit.
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' | '.' | '~' => out.push(c),
            _ => {
                let mut buf = [0u8; 4];
                for b in c.encode_utf8(&mut buf).as_bytes() {
                    out.push_str(&format!("%{:02X}", b));
                }
            }
        }
    }
    out
}

/// Convenience: a static-token SVID provider for tests / local dev.
pub fn static_svid(token: impl Into<String>) -> SvidProvider {
    let s = token.into();
    Box::new(move || {
        let s = s.clone();
        Box::pin(async move { Ok(s) })
    })
}

/// Convenience: extract a `Uuid` from a wire-shape canon entry (best-effort).
pub fn parse_uuid(s: &str) -> Result<Uuid, Error> {
    Uuid::parse_str(s).map_err(|e| Error::Decode(format!("uuid: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{header, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn new_rejects_empty_base_url() {
        let res = Client::new(ClientConfig {
            base_url: "".into(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        });
        assert!(matches!(res, Err(Error::Validation(_))));
    }

    #[tokio::test]
    async fn get_canon_entry_happy_path() {
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/book-1/world.climate"))
            .and(header("Authorization", "Bearer test-svid"))
            .and(header("X-Client-ID", "test-cycle25"))
            .respond_with(ResponseTemplate::new(200).set_body_json(CanonEntry {
                canon_entry_id: "ce-1".into(),
                book_id: "book-1".into(),
                attribute_path: "world.climate".into(),
                value: serde_json::json!("arid"),
                canon_layer: "L1_axiom".into(),
                lock_level: "hard".into(),
                reality_id: None,
                overridden_by_l3_event_id: None,
                last_synced_at: "2026-05-29T12:00:00Z".into(),
            }))
            .mount(&srv)
            .await;

        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("test-svid"),
            client_id: Some("test-cycle25".into()),
            timeout: None,
        })
        .unwrap();

        let got = c
            .get_canon_entry("book-1", "world.climate", None)
            .await
            .expect("happy path");
        assert_eq!(got.canon_layer, "L1_axiom"); // Q-L5-3
        assert_eq!(got.value, serde_json::json!("arid"));
    }

    #[tokio::test]
    async fn get_canon_entry_with_reality_id() {
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/book-1/world.climate"))
            .and(query_param("reality_id", "reality-A"))
            .respond_with(ResponseTemplate::new(200).set_body_json(CanonEntry {
                canon_entry_id: "ce-1".into(),
                book_id: "book-1".into(),
                attribute_path: "world.climate".into(),
                value: serde_json::json!("tropical"),
                canon_layer: "L2_seeded".into(),
                lock_level: "soft".into(),
                reality_id: Some("reality-A".into()),
                overridden_by_l3_event_id: Some("l3-evt-99".into()),
                last_synced_at: "2026-05-29T12:00:00Z".into(),
            }))
            .mount(&srv)
            .await;

        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("test-svid"),
            client_id: None,
            timeout: None,
        })
        .unwrap();

        let got = c
            .get_canon_entry("book-1", "world.climate", Some("reality-A"))
            .await
            .expect("per-reality");
        assert_eq!(got.reality_id.as_deref(), Some("reality-A"));
        assert!(got.overridden_by_l3_event_id.is_some());
    }

    #[tokio::test]
    async fn get_canon_entry_not_found() {
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/book-x/world.climate"))
            .respond_with(ResponseTemplate::new(404))
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .get_canon_entry("book-x", "world.climate", None)
            .await
            .expect_err("expected NotFound");
        assert!(matches!(err, Error::NotFound));
    }

    #[tokio::test]
    async fn get_canon_entry_forbidden() {
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/book-x/world.climate"))
            .respond_with(ResponseTemplate::new(403))
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .get_canon_entry("book-x", "world.climate", None)
            .await
            .expect_err("expected Forbidden");
        assert!(matches!(err, Error::Forbidden));
    }

    #[tokio::test]
    async fn write_canon_entry_guardrail_rejected_q_l5_5() {
        let srv = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/canon"))
            .respond_with(
                ResponseTemplate::new(409).set_body_json(GuardrailViolation {
                    code: "canon_guardrail_l1_conflict".into(),
                    axiom: CanonReference {
                        book_id: "b1".into(),
                        attribute_path: "world.climate".into(),
                        canon_layer: "L1_axiom".into(),
                        value: serde_json::json!("arid"),
                    },
                    proposed_value: serde_json::json!("tropical"),
                    reason: "world.climate is L1 axiom = arid; cannot override".into(),
                }),
            )
            .mount(&srv)
            .await;

        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();

        let err = c
            .write_canon_entry(CanonWriteRequest {
                canon_entry_id: None,
                book_id: "b1".into(),
                attribute_path: "world.climate".into(),
                value: serde_json::json!("tropical"),
                canon_layer: "L2_seeded".into(),
                lock_level: String::new(),
                reality_id: None,
            })
            .await
            .expect_err("expected guardrail rejection");

        match err {
            Error::GuardrailRejected(v) => {
                assert_eq!(v.code, "canon_guardrail_l1_conflict");
                assert_eq!(v.axiom.canon_layer, "L1_axiom");
            }
            other => panic!("expected GuardrailRejected, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn write_canon_entry_happy_path() {
        let srv = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/v1/canon"))
            .respond_with(ResponseTemplate::new(201).set_body_json(CanonWriteResponse {
                canon_entry_id: "ce-new".into(),
                written_at: "2026-05-29T12:00:00Z".into(),
                canon_layer: "L2_seeded".into(),
            }))
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let resp = c
            .write_canon_entry(CanonWriteRequest {
                canon_entry_id: None,
                book_id: "b1".into(),
                attribute_path: "world.climate".into(),
                value: serde_json::json!("arid"),
                canon_layer: "L2_seeded".into(),
                lock_level: String::new(),
                reality_id: None,
            })
            .await
            .expect("happy");
        assert_eq!(resp.canon_entry_id, "ce-new");
    }

    #[tokio::test]
    async fn list_canon_entries_with_since_pagination() {
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/b1/entries"))
            .and(query_param("since", "2026-05-28T00:00:00Z"))
            .and(query_param("limit", "50"))
            .respond_with(ResponseTemplate::new(200).set_body_json(CanonEntryPage {
                entries: vec![CanonEntry {
                    canon_entry_id: "ce-1".into(),
                    book_id: "b1".into(),
                    attribute_path: "world.climate".into(),
                    value: serde_json::json!("arid"),
                    canon_layer: "L2_seeded".into(),
                    lock_level: "soft".into(),
                    reality_id: None,
                    overridden_by_l3_event_id: None,
                    last_synced_at: "2026-05-29T12:00:00Z".into(),
                }],
                next_cursor: Some("cursor-N".into()),
            }))
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let page = c
            .list_canon_entries("b1", Some("2026-05-28T00:00:00Z"), Some(50), None)
            .await
            .expect("list");
        assert_eq!(page.entries.len(), 1);
        assert_eq!(page.next_cursor.as_deref(), Some("cursor-N"));
    }

    #[tokio::test]
    async fn svid_failure_propagates() {
        let srv = MockServer::start().await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: Box::new(|| Box::pin(async { Err("workload api down".to_string()) })),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .get_canon_entry("b1", "world.climate", None)
            .await
            .expect_err("expected svid error");
        assert!(matches!(err, Error::Svid(_)));
    }

    #[tokio::test]
    async fn parse_uuid_helper() {
        let u = parse_uuid("00000000-0000-0000-0000-000000000001").expect("ok");
        assert_eq!(u.as_u128(), 1);
        assert!(matches!(parse_uuid("nope"), Err(Error::Decode(_))));
    }

    #[test]
    fn urlencode_preserves_uuid_chars() {
        // UUIDs are hex + dashes — should round-trip unchanged.
        let u = "deadbeef-1234-5678-90ab-1234567890ab";
        assert_eq!(urlencode(u), u);
    }

    #[test]
    fn urlencode_escapes_query_special_chars() {
        assert!(urlencode("a b").contains("%20"));
        assert!(urlencode("&").contains("%26"));
    }

    // ─────────────────────────────────────────────────────────────────────
    // L5.G / L5.F.2 — export_canon_for_seed NDJSON tests (cycle 26)
    // ─────────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn export_canon_for_seed_streams_ndjson() {
        let srv = MockServer::start().await;
        let ndjson = concat!(
            r#"{"canon_entry_id":"ce-1","book_id":"b1","attribute_path":"world.climate","value":"arid","canon_layer":"L1_axiom","lock_level":"hard","last_synced_at":"2026-05-29T12:00:00Z"}"#,
            "\n",
            r#"{"canon_entry_id":"ce-2","book_id":"b1","attribute_path":"world.gravity","value":1.0,"canon_layer":"L1_axiom","lock_level":"hard","last_synced_at":"2026-05-29T12:00:00Z"}"#,
            "\n",
            r#"{"_envelope":"seed_export_complete","snapshot_at":"2026-05-29T12:00:00Z","entry_count":2}"#,
            "\n",
        );
        Mock::given(method("GET"))
            .and(path("/v1/canon/b1/seed_export"))
            .and(header("Authorization", "Bearer test-svid"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(ndjson, "application/x-ndjson"),
            )
            .mount(&srv)
            .await;

        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("test-svid"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let (entries, env) = c
            .export_canon_for_seed("b1", None)
            .await
            .expect("ndjson stream");
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].canon_entry_id, "ce-1");
        assert_eq!(entries[1].attribute_path, "world.gravity");
        assert_eq!(env.envelope, "seed_export_complete");
        assert_eq!(env.entry_count, 2);
        assert!(env.next_cursor.is_none());
    }

    #[tokio::test]
    async fn export_canon_for_seed_paginates_with_cursor() {
        let srv = MockServer::start().await;
        let ndjson = concat!(
            r#"{"canon_entry_id":"ce-3","book_id":"b1","attribute_path":"world.x","value":"y","canon_layer":"L2_seeded","lock_level":"soft","last_synced_at":"2026-05-29T12:00:00Z"}"#,
            "\n",
            r#"{"_envelope":"seed_export_complete","snapshot_at":"2026-05-29T12:00:00Z","entry_count":1,"next_cursor":"page-2"}"#,
            "\n",
        );
        Mock::given(method("GET"))
            .and(path("/v1/canon/b1/seed_export"))
            .and(query_param("cursor", "page-1"))
            .respond_with(
                ResponseTemplate::new(200)
                    .set_body_raw(ndjson, "application/x-ndjson"),
            )
            .mount(&srv)
            .await;

        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let (_entries, env) = c
            .export_canon_for_seed("b1", Some("page-1"))
            .await
            .expect("paginated");
        assert_eq!(env.next_cursor.as_deref(), Some("page-2"));
    }

    #[tokio::test]
    async fn export_canon_for_seed_rejects_missing_envelope() {
        let srv = MockServer::start().await;
        let ndjson = r#"{"canon_entry_id":"ce-1","book_id":"b1","attribute_path":"a","value":1,"canon_layer":"L1_axiom","lock_level":"hard","last_synced_at":"2026-05-29T12:00:00Z"}"#;
        Mock::given(method("GET"))
            .and(path("/v1/canon/b1/seed_export"))
            .respond_with(
                ResponseTemplate::new(200).set_body_raw(ndjson, "application/x-ndjson"),
            )
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .export_canon_for_seed("b1", None)
            .await
            .expect_err("missing envelope");
        assert!(matches!(err, Error::Decode(_)));
    }

    #[tokio::test]
    async fn export_canon_for_seed_forbidden_without_acl() {
        // L5.F.3 ACL: only world-service is permitted; other SVIDs get 403.
        let srv = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/v1/canon/b1/seed_export"))
            .respond_with(ResponseTemplate::new(403))
            .mount(&srv)
            .await;
        let c = Client::new(ClientConfig {
            base_url: srv.uri(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .export_canon_for_seed("b1", None)
            .await
            .expect_err("acl reject");
        assert!(matches!(err, Error::Forbidden));
    }

    #[tokio::test]
    async fn export_canon_for_seed_rejects_empty_book_id() {
        // Validation only — no HTTP issued. Use a placeholder svid + base_url.
        let c = Client::new(ClientConfig {
            base_url: "http://localhost:0".into(),
            svid: static_svid("x"),
            client_id: None,
            timeout: None,
        })
        .unwrap();
        let err = c
            .export_canon_for_seed("", None)
            .await
            .expect_err("empty book_id");
        assert!(matches!(err, Error::Validation(_)));
    }
}
