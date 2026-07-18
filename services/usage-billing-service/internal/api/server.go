package api

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"
	"github.com/loreweave/usage-billing-service/internal/config"
)

type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
	// secretKey is the DEDICATED payload KEK (from LLM_PAYLOAD_ENCRYPTION_KEY):
	// wraps the per-row session key. ALL new writes use this (LOG-5).
	secretKey []byte
	// legacySecretKey is the old JWT-derived KEK. Kept for BACK-COMPAT decrypt
	// only — rows written before the dedicated-key migration were wrapped with
	// it. Never used for new writes. Empty when JWT_SECRET is unset (tests).
	legacySecretKey []byte
	// retiredKeys are previous dedicated KEKs, tried on the READ path only so a
	// rotation of LLM_PAYLOAD_ENCRYPTION_KEY does not orphan rows wrapped under an
	// older value (B-MED-1). New rows always wrap under secretKey.
	retiredKeys [][]byte
	// adminPub verifies RS256 admin JWTs for the System-tier admin endpoints
	// (adminListUsage + createReconciliation — D-JWT-ROLE-GATE, contracts/adminjwt).
	// nil when ADMIN_JWT_PUBLIC_KEY_PEM is unset → those endpoints fail closed (503).
	// adminKID = KeyFingerprint(adminPub).
	adminPub *rsa.PublicKey
	adminKID string
}

// aesKeySHA256Prefix marks a KEK value whose 32-byte AES key is SHA-256-derived
// from the passphrase after the prefix (D-REVIEW-AESKEY-DERIVE). Its presence is
// what version-gates the derivation PER KEY: a marked active key can be rotated in
// while older unmarked keys (in the retired keyring) keep the legacy pad/truncate
// coercion, so the read-path try-all still decrypts every prior row — no re-encrypt
// migration needed.
const aesKeySHA256Prefix = "sha256:"

// deriveAESKey turns a KEK value into a 32-byte AES-256 key. A value marked with
// aesKeySHA256Prefix is SHA-256-derived (full passphrase entropy → a fixed 32-byte
// key regardless of length). An UNMARKED value keeps the legacy normalizeAESKey
// coercion for backward compatibility with rows wrapped before this change.
func deriveAESKey(secret string) []byte {
	if strings.HasPrefix(secret, aesKeySHA256Prefix) {
		sum := sha256.Sum256([]byte(secret[len(aesKeySHA256Prefix):]))
		return sum[:]
	}
	return normalizeAESKey(secret)
}

// normalizeAESKey coerces a secret string into a 32-byte AES-256 key (truncate
// if longer, zero-pad if shorter). The LEGACY derivation, kept only so unmarked
// keys (and rows wrapped under them) stay decryptable; new keys should use the
// aesKeySHA256Prefix marker. An empty input yields an all-zero key (only happens
// in tests where the secret is unset).
func normalizeAESKey(secret string) []byte {
	key := []byte(secret)
	if len(key) >= 32 {
		return key[:32]
	}
	padded := make([]byte, 32)
	copy(padded, key)
	return padded
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	var legacy []byte
	if cfg.JWTSecret != "" {
		legacy = deriveAESKey(cfg.JWTSecret)
	}
	var retired [][]byte
	for _, k := range cfg.LLMPayloadEncryptionKeysRetired {
		retired = append(retired, deriveAESKey(k))
	}
	s := &Server{
		pool:            pool,
		cfg:             cfg,
		secret:          []byte(cfg.JWTSecret),
		secretKey:       deriveAESKey(cfg.LLMPayloadEncryptionKey),
		legacySecretKey: legacy,
		retiredKeys:     retired,
	}
	// D-JWT-ROLE-GATE — enable RS256 admin verification for the System-tier admin
	// endpoints when the public key is configured. Fail closed + log loudly on a
	// misconfigured key (leave admin disabled → those endpoints return 503).
	if raw := strings.TrimSpace(cfg.AdminJWTPublicKeyPEM); raw != "" {
		if pub, err := adminjwt.ParseRSAPublicKeyPEM(pemOrBase64(raw)); err != nil {
			slog.Error("usage-billing: ADMIN_JWT_PUBLIC_KEY_PEM parse failed; admin endpoints DISABLED", "err", err)
		} else if kid, err := adminjwt.KeyFingerprint(pub); err != nil {
			slog.Error("usage-billing: admin key fingerprint failed; admin endpoints DISABLED", "err", err)
		} else {
			s.adminPub = pub
			s.adminKID = kid
			slog.Info("usage-billing: admin endpoints ENABLED", "kid", kid)
		}
	}
	return s
}

// payloadKeyRef names the master key version that wrapped a row's session key,
// so a stored row is decryptable after key rotation (LOG-5: "a real, rotatable
// key version"). It is a stable fingerprint of the active dedicated KEK — NOT a
// random per-row UUID (the old behavior, which referenced nothing).
func (s *Server) payloadKeyRef() string {
	return keyRefForKey(s.secretKey)
}

func keyRefForKey(key []byte) string {
	sum := sha256.Sum256(key)
	return "llm-payload-key-v1:" + hex.EncodeToString(sum[:8])
}

// decodePayloadBytes decodes decrypted payload plaintext back into its stored
// shape, symmetric with marshalPayload on the write side (LOG-4). An
// object-shaped row (`{...}`) reads back as a map; a string-shaped row (a JSON
// string, the legacy jobs-path shape) reads back as its string content; bytes
// that are not valid JSON at all (oldest legacy rows) read back as the raw
// string. This is the P0-1 root fix: the old read unmarshalled unconditionally
// into map[string]any, so any string-shaped row failed → empty {}.
func decodePayloadBytes(plain []byte) any {
	if len(plain) == 0 {
		return nil
	}
	var v any
	if err := json.Unmarshal(plain, &v); err != nil {
		return string(plain)
	}
	return v
}

// marshalPayload serializes a payload for storage. Objects → JSON object,
// strings → JSON string; symmetric with decodePayloadBytes.
func marshalPayload(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("null")
	}
	return b
}

// unwrapSessionKey decrypts a row's wrapped session key, trying the dedicated
// KEK first, then the legacy JWT-derived KEK (rows written before the
// dedicated-key migration), then each retired KEK (rows written before a key
// rotation — B-MED-1). Returns an error only if ALL candidates fail. New rows
// always wrap under the primary key; retired keys are decrypt-only.
func unwrapSessionKey(primary, legacy []byte, retired [][]byte, keyCipher string) ([]byte, error) {
	sessionKey, err := decryptWithKey(primary, keyCipher)
	if err == nil {
		return sessionKey, nil
	}
	if len(legacy) > 0 {
		if sk, e2 := decryptWithKey(legacy, keyCipher); e2 == nil {
			return sk, nil
		}
	}
	for _, rk := range retired {
		if len(rk) == 0 {
			continue
		}
		if sk, e2 := decryptWithKey(rk, keyCipher); e2 == nil {
			return sk, nil
		}
	}
	// Return the primary-key error: the most useful diagnostic (a corrupt row or
	// a key that was never registered), not a stale retired-key mismatch.
	return nil, err
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before Recoverer so the span
	// survives (and is marked 500) when a handler panics.
	r.Use(observability.ChiMiddleware())
	r.Use(middleware.Recoverer)

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Post("/model-billing/record", s.recordInvocation)
		// Phase 6a — spend guardrail (Subsystem A).
		r.Post("/billing/guardrail/reserve", s.guardrailReserve)
		r.Post("/billing/guardrail/reconcile", s.guardrailReconcile)
		r.Post("/billing/guardrail/release", s.guardrailRelease)
		// WS-2.8 (spec 10) — a read of a user's guardrail so a background worker (the diary distiller)
		// can degrade gracefully before spending when the daily cap is exhausted. Internal-token gated;
		// owner_user_id is an explicit query arg (same posture as mcp-key-usage below).
		r.Get("/billing/guardrail/status", s.getGuardrailStatusInternal)
		// Public MCP P3 (H-C/PUB-11) — per-key spend rollup for an owner. The MCP
		// edge calls this to surface per-key usage (owner audit view, H-O) and feeds
		// the future per-key sub-cap (H-K). Internal-token gated; owner_user_id is an
		// explicit query arg (the caller already authenticated the owner).
		r.Get("/billing/mcp-key-usage", s.getMcpKeyUsage)
		// B1 (D-LANE-BUDGET-ENFORCE) — the per-lane spend report (assistant vs interactive), joining the
		// per-user lane budget. Internal-token gated; owner_user_id is an explicit query arg.
		r.Get("/billing/usage/by-lane", s.getUsageByLane)
	})

	r.Route("/v1/model-billing", func(r chi.Router) {
		r.Get("/usage-logs", s.listUsageLogs)
		r.Get("/usage-logs/{usage_log_id}", s.getUsageLogDetail)
		r.Get("/usage-summary", s.getUsageSummary)
		// D-S4C-ACCOUNTBALANCES-DROP — the token-quota `/account-balance` endpoint
		// is removed with its inert `account_balances` table; USD enforcement lives
		// on the guardrail + platform-balance endpoints below.
		// Phase 6a-γ — user-facing spend guardrail + platform balance.
		r.Get("/guardrail", s.getGuardrail)
		r.Patch("/guardrail", s.patchGuardrail)
		r.Get("/platform-balance", s.getPlatformBalance)
		r.Get("/admin/usage", s.adminListUsage)
		r.Post("/admin/reconciliation", s.createReconciliation)
	})
	return r
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

// auth verifies the platform-user HS256 JWT via the shared contracts/platformjwt
// verifier and returns the authenticated user id. It NO LONGER returns a role:
// the platform user token never carries one (D-JWT-ROLE-GATE) — admin authority
// is the RS256 admin token's job (see requireAdminScope).
func (s *Server) auth(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	claims, err := platformjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.secret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// scopeAdminWrite is the admin scope required to invoke the System-tier admin
// endpoints (admin usage listing + reconciliation). Mirrors glossary /
// provider-registry's System-tier admin gate.
const scopeAdminWrite = "admin:write"

// requireAdminScope verifies the Bearer admin RS256 JWT and that it carries the
// required scope, writing the error + returning false on any failure. The admin
// endpoints are platform-owned (cross-tenant): only an admin principal (never a
// regular user) may reach them (CLAUDE.md › User Boundaries). Fail closed when the
// verify key is unconfigured. A regular HS256 user token never satisfies
// adminjwt.Verify (RS256 only), so this is not bypassable with a normal login.
func (s *Server) requireAdminScope(w http.ResponseWriter, r *http.Request, scope string) (adminjwt.AdminClaims, bool) {
	if s.adminPub == nil {
		writeError(w, http.StatusServiceUnavailable, "M03_ADMIN_UNAVAILABLE", "admin endpoints are not configured")
		return adminjwt.AdminClaims{}, false
	}
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "M03_ADMIN_UNAUTHORIZED", "valid admin Bearer token required")
		return adminjwt.AdminClaims{}, false
	}
	claims, err := adminjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.adminPub, s.adminKID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "M03_ADMIN_UNAUTHORIZED", "invalid admin token")
		return adminjwt.AdminClaims{}, false
	}
	if !slices.Contains(claims.Scopes, scope) {
		writeError(w, http.StatusForbidden, "M03_ADMIN_FORBIDDEN", "missing required admin scope")
		return adminjwt.AdminClaims{}, false
	}
	return claims, true
}

// pemOrBase64 accepts either a raw PEM ("BEGIN") or a base64-encoded PEM (an
// env-var-friendly single line).
func pemOrBase64(v string) []byte {
	if strings.Contains(v, "BEGIN") {
		return []byte(v)
	}
	if dec, err := base64.StdEncoding.DecodeString(strings.TrimSpace(v)); err == nil {
		return dec
	}
	return []byte(v)
}

func encryptWithKey(key []byte, plain []byte) (string, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", err
	}
	body := gcm.Seal(nil, nonce, plain, nil)
	joined := append(nonce, body...)
	return base64.StdEncoding.EncodeToString(joined), nil
}

func decryptWithKey(key []byte, cipherText string) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	joined, err := base64.StdEncoding.DecodeString(cipherText)
	if err != nil {
		return nil, err
	}
	if len(joined) < gcm.NonceSize() {
		return nil, fmt.Errorf("invalid cipher text")
	}
	nonce := joined[:gcm.NonceSize()]
	body := joined[gcm.NonceSize():]
	return gcm.Open(nil, nonce, body, nil)
}

// flatCostPerToken is the legacy flat price. S4c keeps it ONLY as the fallback
// when an event carries no real cost_usd (unpriced model) and for the streaming
// /record path (which has no per-model cost). The real per-model cost arrives on
// the usage stream (provider-registry actualUSD).
const flatCostPerToken = 0.000002

// recordCostUSD resolves the billable USD for an invocation: the authoritative
// per-model `override` when present AND non-negative is honored verbatim (incl. a
// free/local model's 0); otherwise a flat per-token fallback. A negative override
// is a provider/parse bug and falls back to the flat rate (defensive). This is the
// single source for the cost decision on BOTH the /record streaming path (no
// override → always flat) and the usage-stream consumer (override = stream cost_usd).
func recordCostUSD(tokens int, override *float64) float64 {
	if override != nil && *override >= 0 {
		return *override
	}
	return float64(tokens) * flatCostPerToken
}

// billingDecisionRecorded is the billing_decision for audit-only rows. The token
// quota/credits/rejected decisions are retired (S4c) — USD enforcement is the
// Phase-6a guardrail (pre-flight reserve), not this post-hoc path.
const billingDecisionRecorded = "recorded"

// usageLogParams is one model-level usage event for writeUsageLog.
type usageLogParams struct {
	RequestID     uuid.UUID
	OwnerUserID   uuid.UUID
	ProviderKind  string
	ModelSource   string
	ModelRef      uuid.UUID
	InputTokens   int
	OutputTokens  int
	CostUSD       float64
	RequestStatus string
	Purpose       string
	// McpKeyID (H-C/PUB-11) — the public MCP API key that incurred this spend, or
	// nil for first-party traffic. Persisted to usage_logs.mcp_key_id for per-key
	// attribution / monthly rollup.
	McpKeyID *uuid.UUID
	// `any`, not `map[string]any`, so BOTH callers fit: the /record HTTP path passes
	// a structured object (map), while the jobs path (#32) passes the truncated
	// request/response JSON as a STRING. writeUsageLog json.Marshal-s either shape
	// before encrypting. nil ⇒ no payload (encrypts to `null`).
	InputPayload  any
	OutputPayload any
}

// writeUsageLog writes the audit row (usage_logs + usage_log_details) idempotently
// on request_id, inside the caller's tx. It is the shared core for the /record HTTP
// path (streaming) and the usage stream consumer (jobs). S4c: the legacy
// account_balances token deduction is GONE — USD enforcement is the Phase-6a
// guardrail's job. billing_decision is the constant "recorded". On a duplicate
// request_id it re-reads the original cost (idempotent — a redelivered event/retry
// writes nothing new). Returns the persisted usage_log_id, the effective cost, and
// whether the insert was fresh.
func (s *Server) writeUsageLog(ctx context.Context, tx pgx.Tx, p usageLogParams) (uuid.UUID, float64, bool, error) {
	totalTokens := p.InputTokens + p.OutputTokens
	costUSD := p.CostUSD
	requestStatus := p.RequestStatus
	if requestStatus == "" {
		requestStatus = "success"
	}
	purpose := p.Purpose
	if purpose == "" {
		purpose = "unknown"
	}
	const policyVersion = "m03-v1" // was account_balances.billing_policy_version; token ledger retired

	// One session key encrypts both payloads (single stored key). Empty payloads
	// (jobs path) encrypt to ciphertext of `{}` so the NOT-NULL columns stay valid.
	sessionKey := make([]byte, 32)
	if _, err := rand.Read(sessionKey); err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("session key: %w", err)
	}
	inputPlain := marshalPayload(p.InputPayload)
	outputPlain := marshalPayload(p.OutputPayload)
	inputCipher, err := encryptWithKey(sessionKey, inputPlain)
	if err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("encrypt input: %w", err)
	}
	outputCipher, err := encryptWithKey(sessionKey, outputPlain)
	if err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("encrypt output: %w", err)
	}
	keyCipherRaw, err := encryptWithKey(s.secretKey, sessionKey)
	if err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("encrypt key: %w", err)
	}
	// LOG-5: name the real (rotatable) master-key version, not a random UUID.
	keyRef := s.payloadKeyRef()

	// Idempotency gate: ON CONFLICT DO NOTHING RETURNING yields a row only on a
	// FRESH insert; a duplicate request_id returns no row → re-read + skip details.
	var usageLogID uuid.UUID
	err = tx.QueryRow(ctx, `
INSERT INTO usage_logs(
  request_id, owner_user_id, provider_kind, model_source, model_ref,
  input_tokens, output_tokens, total_tokens, total_cost_usd, billing_decision, request_status, policy_version,
  input_payload_ciphertext, output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, purpose, lane, mcp_key_id
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'AES-256-GCM',$16,
  COALESCE((SELECT lane_code FROM lane_purpose_map WHERE purpose=$16), 'interactive'), $17)
ON CONFLICT (request_id) DO NOTHING
RETURNING usage_log_id
`, p.RequestID, p.OwnerUserID, p.ProviderKind, p.ModelSource, p.ModelRef,
		p.InputTokens, p.OutputTokens, totalTokens, costUSD, billingDecisionRecorded, requestStatus, policyVersion,
		inputCipher, outputCipher, keyRef, purpose, p.McpKeyID).Scan(&usageLogID)
	if err == pgx.ErrNoRows {
		// Duplicate request_id — already recorded. Re-read so the response/cost is
		// identical across retries; write no details.
		if e := tx.QueryRow(ctx, `
SELECT usage_log_id, total_cost_usd FROM usage_logs WHERE request_id=$1`,
			p.RequestID).Scan(&usageLogID, &costUSD); e != nil {
			return uuid.Nil, 0, false, fmt.Errorf("re-read existing: %w", e)
		}
		return usageLogID, costUSD, false, nil
	}
	if err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("insert usage log: %w", err)
	}
	if _, err = tx.Exec(ctx, `
INSERT INTO usage_log_details(usage_log_id, payload_encryption_key_ciphertext, input_payload_ciphertext, output_payload_ciphertext)
VALUES ($1,$2,$3,$4)
ON CONFLICT (usage_log_id) DO NOTHING
`, usageLogID, keyCipherRaw, inputCipher, outputCipher); err != nil {
		return uuid.Nil, 0, false, fmt.Errorf("insert usage log details: %w", err)
	}
	return usageLogID, costUSD, true, nil
}

// recordUsageRequest is the /record HTTP body (the streaming + direct-caller path).
type recordUsageRequest struct {
	RequestID     uuid.UUID      `json:"request_id"`
	OwnerUserID   uuid.UUID      `json:"owner_user_id"`
	ProviderKind  string         `json:"provider_kind"`
	ModelSource   string         `json:"model_source"`
	ModelRef      uuid.UUID      `json:"model_ref"`
	InputTokens   int            `json:"input_tokens"`
	OutputTokens  int            `json:"output_tokens"`
	InputPayload  map[string]any `json:"input_payload"`
	OutputPayload map[string]any `json:"output_payload"`
	RequestStatus string         `json:"request_status"`
	Purpose       string         `json:"purpose"`
	// TotalCostUSD (P2·B2, closes D-S4C-STREAMING-REALCOST) — the authoritative
	// per-model cost the /record caller computed: streaming's tallied `actual`
	// (stream_billing.go) and embed's PriceEmbedding cost (B2·c). nil ⇒ the caller
	// has no real cost → flat fallback. This is the Route-A twin of the usage
	// stream's `cost_usd`, so both routes record the same authoritative cost.
	TotalCostUSD *float64 `json:"total_cost_usd"`
}

// recordUsageParams maps a /record request to the audit params. Pure + tested so a
// field transposition (or a cost-drop regression) is caught without a live handler.
// Cost parity: the authoritative TotalCostUSD (when present + non-negative) is
// honored verbatim via recordCostUSD — exactly as the usage-stream consumer honors
// `cost_usd` — else a flat per-token fallback. Both routes converge on writeUsageLog
// with the SAME cost, closing the streaming-real-cost gap (D-S4C-STREAMING-REALCOST).
func recordUsageParams(in recordUsageRequest) usageLogParams {
	return usageLogParams{
		RequestID:     in.RequestID,
		OwnerUserID:   in.OwnerUserID,
		ProviderKind:  in.ProviderKind,
		ModelSource:   in.ModelSource,
		ModelRef:      in.ModelRef,
		InputTokens:   in.InputTokens,
		OutputTokens:  in.OutputTokens,
		CostUSD:       recordCostUSD(in.InputTokens+in.OutputTokens, in.TotalCostUSD),
		RequestStatus: in.RequestStatus,
		Purpose:       in.Purpose,
		InputPayload:  in.InputPayload,
		OutputPayload: in.OutputPayload,
	}
}

func (s *Server) recordInvocation(w http.ResponseWriter, r *http.Request) {
	var in recordUsageRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_BILLING_RECORD_INVALID", "invalid payload")
		return
	}
	if in.RequestID == uuid.Nil || in.OwnerUserID == uuid.Nil || in.ModelRef == uuid.Nil {
		writeError(w, http.StatusBadRequest, "M03_BILLING_RECORD_INVALID", "request_id/owner_user_id/model_ref required")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_TX_FAILED", "failed to start tx")
		return
	}
	defer tx.Rollback(r.Context())

	// S4c: the legacy account_balances token deduction is RETIRED — USD spend
	// enforcement is the Phase-6a guardrail's job (pre-flight reserve). /record now
	// only writes the usage audit. P2·B2 (closes D-S4C-STREAMING-REALCOST): the cost
	// is the caller's authoritative total_cost_usd when supplied (streaming's tallied
	// cost, embed's PriceEmbedding cost), else the flat fallback — so the committed-
	// spend rollup (guardrail SUM(total_cost_usd)) reflects real cost, not a flat proxy.
	usageLogID, costUSD, _, err := s.writeUsageLog(r.Context(), tx, recordUsageParams(in))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_RECORD_FAILED", "failed to write usage log")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_TX_FAILED", "failed to commit")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"usage_log_id":   usageLogID,
		"billing_mode":   billingDecisionRecorded,
		"total_cost_usd": costUSD,
	})
}

func (s *Server) listUsageLogs(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	q := r.URL.Query()
	limit := parseIntDefault(q.Get("limit"), 20, 1, 100)
	offset := parseIntDefault(q.Get("offset"), 0, 0, 1000000)

	// Build dynamic WHERE clauses
	conditions := []string{"owner_user_id=$1"}
	args := []any{userID}
	argIdx := 2

	if v := q.Get("provider_kind"); v != "" {
		conditions = append(conditions, fmt.Sprintf("provider_kind=$%d", argIdx))
		args = append(args, v)
		argIdx++
	}
	if v := q.Get("request_status"); v != "" {
		conditions = append(conditions, fmt.Sprintf("request_status=$%d", argIdx))
		args = append(args, v)
		argIdx++
	}
	if v := q.Get("purpose"); v != "" {
		conditions = append(conditions, fmt.Sprintf("purpose=$%d", argIdx))
		args = append(args, v)
		argIdx++
	}
	if v := q.Get("from"); v != "" {
		if t, err := time.Parse(time.RFC3339, v); err == nil {
			conditions = append(conditions, fmt.Sprintf("created_at >= $%d", argIdx))
			args = append(args, t)
			argIdx++
		}
	}
	if v := q.Get("to"); v != "" {
		if t, err := time.Parse(time.RFC3339, v); err == nil {
			conditions = append(conditions, fmt.Sprintf("created_at <= $%d", argIdx))
			args = append(args, t)
			argIdx++
		}
	}

	where := strings.Join(conditions, " AND ")

	// Query items
	queryArgs := append(args, limit, offset)
	rows, err := s.pool.Query(r.Context(), fmt.Sprintf(`
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, purpose, created_at
FROM usage_logs
WHERE %s
ORDER BY created_at DESC
LIMIT $%d OFFSET $%d
`, where, argIdx, argIdx+1), queryArgs...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to list usage logs")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		item, err := scanUsageLogRow(rows)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to parse usage log row")
			return
		}
		items = append(items, item)
	}

	// Count with same filters
	var total int
	_ = s.pool.QueryRow(r.Context(), fmt.Sprintf(`SELECT COUNT(*) FROM usage_logs WHERE %s`, where), args...).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanUsageLogRow(s rowScanner) (map[string]any, error) {
	var usageLogID, requestID, ownerID, modelRef uuid.UUID
	var providerKind, modelSource, billingDecision, requestStatus, policyVersion, inputCipher, outputCipher, keyRef, algo, purpose string
	var inputTokens, outputTokens, totalTokens, decryptAuditCount int
	var totalCost float64
	var createdAt time.Time
	if err := s.Scan(&usageLogID, &requestID, &ownerID, &providerKind, &modelSource, &modelRef, &inputTokens, &outputTokens,
		&totalTokens, &totalCost, &billingDecision, &requestStatus, &policyVersion, &inputCipher, &outputCipher, &keyRef, &algo, &decryptAuditCount, &purpose, &createdAt); err != nil {
		return nil, err
	}
	return map[string]any{
		"usage_log_id":               usageLogID,
		"request_id":                 requestID,
		"owner_user_id":              ownerID,
		"provider_kind":              providerKind,
		"model_source":               modelSource,
		"model_ref":                  modelRef,
		"input_tokens":               inputTokens,
		"output_tokens":              outputTokens,
		"total_tokens":               totalTokens,
		"total_cost_usd":             totalCost,
		"billing_decision":           billingDecision,
		"request_status":             requestStatus,
		"policy_version":             policyVersion,
		"input_payload_ciphertext":   inputCipher,
		"output_payload_ciphertext":  outputCipher,
		"payload_encryption_key_ref": keyRef,
		"payload_encryption_algo":    algo,
		"decrypt_access_audit_count": decryptAuditCount,
		"purpose":                    purpose,
		"created_at":                 createdAt,
	}, nil
}

func (s *Server) getUsageLogDetail(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	usageLogID, err := uuid.Parse(chi.URLParam(r, "usage_log_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid usage_log_id")
		return
	}
	var ownerID uuid.UUID
	err = s.pool.QueryRow(r.Context(), `SELECT owner_user_id FROM usage_logs WHERE usage_log_id=$1`, usageLogID).Scan(&ownerID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_USAGE_LOG_NOT_FOUND", "usage log not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to load usage log owner")
		return
	}
	if ownerID != userID {
		writeError(w, http.StatusForbidden, "M03_LOG_DECRYPT_FORBIDDEN", "forbidden")
		return
	}
	// Read == write symmetric (LOG-4): payloads decode back into whatever shape
	// was stored (object → map, string → string). `any`, not map[string]any, so
	// a string-shaped (jobs-path / legacy) row is no longer silently dropped to
	// {} (the P0-1 defect). nil until successfully decrypted.
	var inputPayload, outputPayload any
	// Try to decrypt payloads — gracefully handle missing/empty/corrupt ciphertext
	var keyCipher, inputCipher, outputCipher string
	err = s.pool.QueryRow(r.Context(), `
SELECT payload_encryption_key_ciphertext, input_payload_ciphertext, output_payload_ciphertext
FROM usage_log_details WHERE usage_log_id=$1
`, usageLogID).Scan(&keyCipher, &inputCipher, &outputCipher)
	if err == nil && keyCipher != "" {
		// Unwrap with the dedicated KEK; fall back to the legacy JWT-derived KEK
		// (rows before the dedicated-key migration, P0-3) and then any retired KEK
		// (rows before a key rotation, B-MED-1).
		if sessionKey, err2 := unwrapSessionKey(s.secretKey, s.legacySecretKey, s.retiredKeys, keyCipher); err2 == nil {
			if inputPlain, err3 := decryptWithKey(sessionKey, inputCipher); err3 == nil {
				inputPayload = decodePayloadBytes(inputPlain)
			} else {
				slog.Error("input decrypt failed", "error", err3)
			}
			if outputPlain, err3 := decryptWithKey(sessionKey, outputCipher); err3 == nil {
				outputPayload = decodePayloadBytes(outputPlain)
			} else {
				slog.Error("output decrypt failed", "error", err3)
			}
		} else {
			slog.Error("session key decrypt failed", "error", err2)
		}
	}
	tx, err := s.pool.Begin(r.Context())
	if err == nil {
		_, _ = tx.Exec(r.Context(), `INSERT INTO usage_log_decrypt_audits(usage_log_id, owner_user_id) VALUES ($1,$2)`, usageLogID, userID)
		_, _ = tx.Exec(r.Context(), `UPDATE usage_logs SET decrypt_access_audit_count=decrypt_access_audit_count+1 WHERE usage_log_id=$1`, usageLogID)
		_ = tx.Commit(r.Context())
	}
	row := s.pool.QueryRow(r.Context(), `
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, purpose, created_at
FROM usage_logs WHERE usage_log_id=$1
`, usageLogID)
	logBody, err := scanUsageLogRow(row)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to parse usage log row")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"usage_log":      logBody,
		"input_payload":  inputPayload,
		"output_payload": outputPayload,
		"viewed_at":      time.Now().UTC(),
	})
}

func parseIntDefault(raw string, def, min, max int) int {
	if raw == "" {
		return def
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return def
	}
	if n < min {
		return min
	}
	if n > max {
		return max
	}
	return n
}

func (s *Server) getUsageSummary(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	period := r.URL.Query().Get("period")
	if period == "" {
		period = "current_month"
	}
	var where, prevWhere string
	switch period {
	case "last_24h":
		where = "created_at >= now() - interval '24 hours'"
		prevWhere = "created_at >= now() - interval '48 hours' AND created_at < now() - interval '24 hours'"
	case "last_7d":
		where = "created_at >= now() - interval '7 days'"
		prevWhere = "created_at >= now() - interval '14 days' AND created_at < now() - interval '7 days'"
	case "last_30d":
		where = "created_at >= now() - interval '30 days'"
		prevWhere = "created_at >= now() - interval '60 days' AND created_at < now() - interval '30 days'"
	case "last_90d":
		where = "created_at >= now() - interval '90 days'"
		prevWhere = "created_at >= now() - interval '180 days' AND created_at < now() - interval '90 days'"
	default:
		where = "date_trunc('month', created_at) = date_trunc('month', now())"
		prevWhere = "date_trunc('month', created_at) = date_trunc('month', now() - interval '1 month')"
	}
	var requestCount, totalTokens, errorCount int
	var totalCost float64
	var creditCount int
	err := s.pool.QueryRow(r.Context(), `
SELECT COUNT(*), COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0),
       COALESCE(SUM(CASE WHEN billing_decision='credits' THEN total_tokens ELSE 0 END),0),
       COALESCE(SUM(CASE WHEN request_status!='success' THEN 1 ELSE 0 END),0)
FROM usage_logs
WHERE owner_user_id=$1 AND `+where, userID).Scan(&requestCount, &totalTokens, &totalCost, &creditCount, &errorCount)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_SUMMARY_FAILED", "failed to read summary")
		return
	}
	var errorRate float64
	if requestCount > 0 {
		errorRate = float64(errorCount) / float64(requestCount) * 100
	}

	// Previous period for trend comparison
	var prevRequestCount, prevTotalTokens, prevErrorCount int
	var prevTotalCost float64
	_ = s.pool.QueryRow(r.Context(), `
SELECT COUNT(*), COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0),
       COALESCE(SUM(CASE WHEN request_status!='success' THEN 1 ELSE 0 END),0)
FROM usage_logs
WHERE owner_user_id=$1 AND `+prevWhere, userID).Scan(&prevRequestCount, &prevTotalTokens, &prevTotalCost, &prevErrorCount)
	var prevErrorRate float64
	if prevRequestCount > 0 {
		prevErrorRate = float64(prevErrorCount) / float64(prevRequestCount) * 100
	}

	// Breakdown by provider
	providerBreakdown := make([]map[string]any, 0)
	if providerRows, err := s.pool.Query(r.Context(), `
SELECT provider_kind, COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0), COUNT(*)
FROM usage_logs
WHERE owner_user_id=$1 AND `+where+`
GROUP BY provider_kind ORDER BY SUM(total_tokens) DESC
`, userID); err == nil {
		defer providerRows.Close()
		for providerRows.Next() {
			var pk string
			var tokens, count int
			var cost float64
			if err := providerRows.Scan(&pk, &tokens, &cost, &count); err == nil {
				providerBreakdown = append(providerBreakdown, map[string]any{
					"provider_kind": pk, "total_tokens": tokens, "total_cost_usd": cost, "request_count": count,
				})
			}
		}
	}

	// Breakdown by purpose
	purposeBreakdown := make([]map[string]any, 0)
	if purposeRows, err := s.pool.Query(r.Context(), `
SELECT purpose, COALESCE(SUM(total_tokens),0), COUNT(*)
FROM usage_logs
WHERE owner_user_id=$1 AND `+where+`
GROUP BY purpose ORDER BY SUM(total_tokens) DESC
`, userID); err == nil {
		defer purposeRows.Close()
		for purposeRows.Next() {
			var p string
			var tokens, count int
			if err := purposeRows.Scan(&p, &tokens, &count); err == nil {
				purposeBreakdown = append(purposeBreakdown, map[string]any{
					"purpose": p, "total_tokens": tokens, "request_count": count,
				})
			}
		}
	}

	// Daily breakdown
	dailyBreakdown := make([]map[string]any, 0)
	if dailyRows, err := s.pool.Query(r.Context(), `
SELECT date_trunc('day', created_at)::date AS day,
       COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COUNT(*)
FROM usage_logs
WHERE owner_user_id=$1 AND `+where+`
GROUP BY day ORDER BY day
`, userID); err == nil {
		defer dailyRows.Close()
		for dailyRows.Next() {
			var day time.Time
			var input, output, count int
			if err := dailyRows.Scan(&day, &input, &output, &count); err == nil {
				dailyBreakdown = append(dailyBreakdown, map[string]any{
					"date": day.Format("2006-01-02"), "input_tokens": input, "output_tokens": output, "request_count": count,
				})
			}
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"period":                period,
		"request_count":         requestCount,
		"total_tokens":          totalTokens,
		"total_cost_usd":        totalCost,
		"charged_credits":       creditCount,
		"quota_consumed_tokens": totalTokens - creditCount,
		"error_count":           errorCount,
		"error_rate":            errorRate,
		"prev_request_count":    prevRequestCount,
		"prev_total_tokens":     prevTotalTokens,
		"prev_total_cost_usd":   prevTotalCost,
		"prev_error_rate":       prevErrorRate,
		"by_provider":           providerBreakdown,
		"by_purpose":            purposeBreakdown,
		"daily":                 dailyBreakdown,
	})
}

func (s *Server) adminListUsage(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	limit := parseIntDefault(r.URL.Query().Get("limit"), 50, 1, 200)
	offset := parseIntDefault(r.URL.Query().Get("offset"), 0, 0, 1000000)
	rows, err := s.pool.Query(r.Context(), `
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, purpose, created_at
FROM usage_logs
ORDER BY created_at DESC
LIMIT $1 OFFSET $2
`, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to list usage logs")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		item, err := scanUsageLogRow(rows)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to parse usage log row")
			return
		}
		items = append(items, item)
	}
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM usage_logs`).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func (s *Server) createReconciliation(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	var in struct {
		PeriodStart time.Time `json:"period_start"`
		PeriodEnd   time.Time `json:"period_end"`
		DryRun      bool      `json:"dry_run"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	var reportID uuid.UUID
	var status string
	var summary []byte
	var createdAt time.Time
	err := s.pool.QueryRow(r.Context(), `
INSERT INTO reconciliation_reports(period_start, period_end, dry_run, status, summary)
VALUES ($1,$2,$3,'completed',jsonb_build_object('note','auto generated'))
RETURNING report_id, status, summary, created_at
`, in.PeriodStart, in.PeriodEnd, in.DryRun).Scan(&reportID, &status, &summary, &createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_RECONCILIATION_FAILED", "failed to create reconciliation")
		return
	}
	var summaryObj map[string]any
	_ = json.Unmarshal(summary, &summaryObj)
	writeJSON(w, http.StatusAccepted, map[string]any{
		"report_id":    reportID,
		"period_start": in.PeriodStart,
		"period_end":   in.PeriodEnd,
		"status":       status,
		"summary":      summaryObj,
		"created_at":   createdAt,
	})
}
