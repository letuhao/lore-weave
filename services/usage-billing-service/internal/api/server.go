package api

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/usage-billing-service/internal/config"
)

type Server struct {
	pool      *pgxpool.Pool
	cfg       *config.Config
	secret    []byte
	secretKey []byte
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	key := []byte(cfg.JWTSecret)
	if len(key) > 32 {
		key = key[:32]
	}
	if len(key) < 32 {
		padded := make([]byte, 32)
		copy(padded, key)
		key = padded
	}
	return &Server{
		pool:      pool,
		cfg:       cfg,
		secret:    []byte(cfg.JWTSecret),
		secretKey: key,
	}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)

	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	r.Post("/internal/model-billing/record", s.recordInvocation)

	r.Route("/v1/model-billing", func(r chi.Router) {
		r.Get("/usage-logs", s.listUsageLogs)
		r.Get("/usage-logs/{usage_log_id}", s.getUsageLogDetail)
		r.Get("/usage-summary", s.getUsageSummary)
		r.Get("/account-balance", s.getAccountBalance)
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

type accessClaims struct {
	jwt.RegisteredClaims
	Role string `json:"role,omitempty"`
}

func (s *Server) auth(r *http.Request) (uuid.UUID, string, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, "", false
	}
	tokenStr := strings.TrimPrefix(auth, "Bearer ")
	tok, err := jwt.ParseWithClaims(tokenStr, &accessClaims{}, func(t *jwt.Token) (any, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.secret, nil
	})
	if err != nil || !tok.Valid {
		return uuid.Nil, "", false
	}
	claims, ok := tok.Claims.(*accessClaims)
	if !ok {
		return uuid.Nil, "", false
	}
	id, err := uuid.Parse(claims.Subject)
	if err != nil {
		return uuid.Nil, "", false
	}
	return id, claims.Role, true
}

func (s *Server) encryptPayload(v map[string]any) (cipherText string, keyCipher string, keyRef string, err error) {
	plain, err := json.Marshal(v)
	if err != nil {
		return "", "", "", err
	}
	sessionKey := make([]byte, 32)
	if _, err := rand.Read(sessionKey); err != nil {
		return "", "", "", err
	}
	bodyCipher, err := encryptWithKey(sessionKey, plain)
	if err != nil {
		return "", "", "", err
	}
	keyCipherRaw, err := encryptWithKey(s.secretKey, sessionKey)
	if err != nil {
		return "", "", "", err
	}
	return bodyCipher, keyCipherRaw, uuid.NewString(), nil
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

func (s *Server) recordInvocation(w http.ResponseWriter, r *http.Request) {
	var in struct {
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
	}
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

	if _, err := tx.Exec(r.Context(), `INSERT INTO account_balances(owner_user_id) VALUES ($1) ON CONFLICT(owner_user_id) DO NOTHING`, in.OwnerUserID); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_BALANCE_FAILED", "failed to ensure balance row")
		return
	}
	totalTokens := in.InputTokens + in.OutputTokens
	costUSD := float64(totalTokens) * 0.000002
	decision := "quota"
	requestStatus := in.RequestStatus
	if requestStatus == "" {
		requestStatus = "success"
	}
	var quotaRemaining int
	var credits int
	var policyVersion string
	err = tx.QueryRow(r.Context(), `
SELECT month_quota_remaining_tokens, credits_balance, billing_policy_version
FROM account_balances
WHERE owner_user_id=$1
FOR UPDATE
`, in.OwnerUserID).Scan(&quotaRemaining, &credits, &policyVersion)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_BALANCE_FAILED", "failed to load balance")
		return
	}
	if quotaRemaining >= totalTokens {
		_, err = tx.Exec(r.Context(), `
UPDATE account_balances SET month_quota_remaining_tokens = month_quota_remaining_tokens - $2, updated_at=now()
WHERE owner_user_id=$1
`, in.OwnerUserID, totalTokens)
	} else {
		over := totalTokens - quotaRemaining
		if credits >= over {
			decision = "credits"
			_, err = tx.Exec(r.Context(), `
UPDATE account_balances
SET month_quota_remaining_tokens = 0, credits_balance = credits_balance - $2, updated_at=now()
WHERE owner_user_id=$1
`, in.OwnerUserID, over)
		} else {
			decision = "rejected"
			requestStatus = "billing_rejected"
		}
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_BALANCE_FAILED", "failed to update balance")
		return
	}

	inputCipher, inputKeyCipher, keyRef, err := s.encryptPayload(in.InputPayload)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_ENCRYPTION_FAILED", "failed to encrypt input payload")
		return
	}
	outputCipher, outputKeyCipher, _, err := s.encryptPayload(in.OutputPayload)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_ENCRYPTION_FAILED", "failed to encrypt output payload")
		return
	}
	if inputKeyCipher != outputKeyCipher {
		outputKeyCipher = inputKeyCipher
	}

	var usageLogID uuid.UUID
	err = tx.QueryRow(r.Context(), `
INSERT INTO usage_logs(
  request_id, owner_user_id, provider_kind, model_source, model_ref,
  input_tokens, output_tokens, total_tokens, total_cost_usd, billing_decision, request_status, policy_version,
  input_payload_ciphertext, output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'AES-256-GCM')
ON CONFLICT (request_id) DO UPDATE SET request_id = EXCLUDED.request_id
RETURNING usage_log_id
`, in.RequestID, in.OwnerUserID, in.ProviderKind, in.ModelSource, in.ModelRef,
		in.InputTokens, in.OutputTokens, totalTokens, costUSD, decision, requestStatus, policyVersion,
		inputCipher, outputCipher, keyRef).Scan(&usageLogID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_RECORD_FAILED", "failed to write usage log")
		return
	}
	_, err = tx.Exec(r.Context(), `
INSERT INTO usage_log_details(usage_log_id, payload_encryption_key_ciphertext, input_payload_ciphertext, output_payload_ciphertext)
VALUES ($1,$2,$3,$4)
ON CONFLICT (usage_log_id) DO UPDATE SET
  payload_encryption_key_ciphertext = EXCLUDED.payload_encryption_key_ciphertext,
  input_payload_ciphertext = EXCLUDED.input_payload_ciphertext,
  output_payload_ciphertext = EXCLUDED.output_payload_ciphertext
`, usageLogID, inputKeyCipher, inputCipher, outputCipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_RECORD_FAILED", "failed to write usage log details")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BILLING_TX_FAILED", "failed to commit")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"usage_log_id":   usageLogID,
		"billing_mode":   decision,
		"total_cost_usd": costUSD,
	})
}

func (s *Server) listUsageLogs(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	limit := parseIntDefault(r.URL.Query().Get("limit"), 20, 1, 100)
	offset := parseIntDefault(r.URL.Query().Get("offset"), 0, 0, 1000000)
	rows, err := s.pool.Query(r.Context(), `
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, created_at
FROM usage_logs
WHERE owner_user_id=$1
ORDER BY created_at DESC
LIMIT $2 OFFSET $3
`, userID, limit, offset)
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
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM usage_logs WHERE owner_user_id=$1`, userID).Scan(&total)
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
	var providerKind, modelSource, billingDecision, requestStatus, policyVersion, inputCipher, outputCipher, keyRef, algo string
	var inputTokens, outputTokens, totalTokens, decryptAuditCount int
	var totalCost float64
	var createdAt time.Time
	if err := s.Scan(&usageLogID, &requestID, &ownerID, &providerKind, &modelSource, &modelRef, &inputTokens, &outputTokens,
		&totalTokens, &totalCost, &billingDecision, &requestStatus, &policyVersion, &inputCipher, &outputCipher, &keyRef, &algo, &decryptAuditCount, &createdAt); err != nil {
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
		"created_at":                 createdAt,
	}, nil
}

func (s *Server) getUsageLogDetail(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
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
	var keyCipher, inputCipher, outputCipher string
	err = s.pool.QueryRow(r.Context(), `
SELECT payload_encryption_key_ciphertext, input_payload_ciphertext, output_payload_ciphertext
FROM usage_log_details WHERE usage_log_id=$1
`, usageLogID).Scan(&keyCipher, &inputCipher, &outputCipher)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusConflict, "M03_CIPHERTEXT_UNAVAILABLE", "ciphertext unavailable")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_QUERY_FAILED", "failed to load encrypted payload")
		return
	}
	sessionKey, err := decryptWithKey(s.secretKey, keyCipher)
	if err != nil {
		writeError(w, http.StatusConflict, "M03_CIPHERTEXT_UNAVAILABLE", "ciphertext unavailable")
		return
	}
	inputPlain, err := decryptWithKey(sessionKey, inputCipher)
	if err != nil {
		writeError(w, http.StatusConflict, "M03_CIPHERTEXT_UNAVAILABLE", "ciphertext unavailable")
		return
	}
	outputPlain, err := decryptWithKey(sessionKey, outputCipher)
	if err != nil {
		writeError(w, http.StatusConflict, "M03_CIPHERTEXT_UNAVAILABLE", "ciphertext unavailable")
		return
	}
	inputPayload := map[string]any{}
	outputPayload := map[string]any{}
	_ = json.Unmarshal(inputPlain, &inputPayload)
	_ = json.Unmarshal(outputPlain, &outputPayload)
	tx, err := s.pool.Begin(r.Context())
	if err == nil {
		_, _ = tx.Exec(r.Context(), `INSERT INTO usage_log_decrypt_audits(usage_log_id, owner_user_id) VALUES ($1,$2)`, usageLogID, userID)
		_, _ = tx.Exec(r.Context(), `UPDATE usage_logs SET decrypt_access_audit_count=decrypt_access_audit_count+1 WHERE usage_log_id=$1`, usageLogID)
		_ = tx.Commit(r.Context())
	}
	row := s.pool.QueryRow(r.Context(), `
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, created_at
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
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	period := r.URL.Query().Get("period")
	if period == "" {
		period = "current_month"
	}
	var where string
	switch period {
	case "last_24h":
		where = "created_at >= now() - interval '24 hours'"
	case "last_7d":
		where = "created_at >= now() - interval '7 days'"
	default:
		where = "date_trunc('month', created_at) = date_trunc('month', now())"
	}
	var requestCount, totalTokens int
	var totalCost float64
	var creditCount int
	err := s.pool.QueryRow(r.Context(), `
SELECT COUNT(*), COALESCE(SUM(total_tokens),0), COALESCE(SUM(total_cost_usd),0),
       COALESCE(SUM(CASE WHEN billing_decision='credits' THEN total_tokens ELSE 0 END),0)
FROM usage_logs
WHERE owner_user_id=$1 AND `+where, userID).Scan(&requestCount, &totalTokens, &totalCost, &creditCount)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USAGE_SUMMARY_FAILED", "failed to read summary")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"period":                period,
		"request_count":         requestCount,
		"total_tokens":          totalTokens,
		"total_cost_usd":        totalCost,
		"charged_credits":       creditCount,
		"quota_consumed_tokens": totalTokens - creditCount,
	})
}

func (s *Server) getAccountBalance(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	if _, err := s.pool.Exec(r.Context(), `INSERT INTO account_balances(owner_user_id) VALUES ($1) ON CONFLICT(owner_user_id) DO NOTHING`, userID); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BALANCE_FAILED", "failed to initialize balance")
		return
	}
	var tier string
	var quota, quotaRemaining, credits int
	var policyVersion string
	err := s.pool.QueryRow(r.Context(), `
SELECT tier_name, month_quota_tokens, month_quota_remaining_tokens, credits_balance, billing_policy_version
FROM account_balances
WHERE owner_user_id=$1
`, userID).Scan(&tier, &quota, &quotaRemaining, &credits, &policyVersion)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_BALANCE_FAILED", "failed to read balance")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"tier_name":                    tier,
		"month_quota_tokens":           quota,
		"month_quota_remaining_tokens": quotaRemaining,
		"credits_balance":              credits,
		"billing_policy_version":       policyVersion,
	})
}

func (s *Server) adminListUsage(w http.ResponseWriter, r *http.Request) {
	_, role, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	if role != "admin" {
		writeError(w, http.StatusForbidden, "M03_FORBIDDEN", "admin only")
		return
	}
	limit := parseIntDefault(r.URL.Query().Get("limit"), 50, 1, 200)
	offset := parseIntDefault(r.URL.Query().Get("offset"), 0, 0, 1000000)
	rows, err := s.pool.Query(r.Context(), `
SELECT usage_log_id, request_id, owner_user_id, provider_kind, model_source, model_ref, input_tokens, output_tokens,
       total_tokens, total_cost_usd, billing_decision, request_status, policy_version, input_payload_ciphertext,
       output_payload_ciphertext, payload_encryption_key_ref, payload_encryption_algo, decrypt_access_audit_count, created_at
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
	_, role, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	if role != "admin" {
		writeError(w, http.StatusForbidden, "M03_FORBIDDEN", "admin only")
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
