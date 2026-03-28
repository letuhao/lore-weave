package api

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/provider"
)

type Server struct {
	pool         *pgxpool.Pool
	cfg          *config.Config
	secret       []byte
	secretKey    []byte
	client       *http.Client // short-timeout: sync/billing calls (15s)
	invokeClient *http.Client // no timeout: AI generation can take minutes
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
		pool:         pool,
		cfg:          cfg,
		secret:       []byte(cfg.JWTSecret),
		secretKey:    key,
		client:       &http.Client{Timeout: 15 * time.Second},
		invokeClient: &http.Client{}, // no Timeout — context deadline from request controls cancellation
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

	r.Route("/v1/model-registry", func(r chi.Router) {
		r.Get("/providers", s.listProviderCredentials)
		r.Post("/providers", s.createProviderCredential)
		r.Patch("/providers/{provider_credential_id}", s.patchProviderCredential)
		r.Delete("/providers/{provider_credential_id}", s.deleteProviderCredential)
		r.Post("/providers/{provider_credential_id}/health", s.providerHealth)
		r.Get("/providers/{provider_credential_id}/models", s.listProviderInventory)

		r.Get("/user-models", s.listUserModels)
		r.Post("/user-models", s.createUserModel)
		r.Patch("/user-models/{user_model_id}", s.patchUserModel)
		r.Delete("/user-models/{user_model_id}", s.deleteUserModel)
		r.Patch("/user-models/{user_model_id}/activation", s.patchUserModelActivation)
		r.Patch("/user-models/{user_model_id}/favorite", s.patchUserModelFavorite)
		r.Put("/user-models/{user_model_id}/tags", s.putUserModelTags)
		r.Post("/user-models/{user_model_id}/verify", s.verifyUserModel)

		r.Get("/platform-models", s.listPlatformModels)
		r.Post("/platform-models", s.createPlatformModel)
		r.Patch("/platform-models/{platform_model_id}", s.patchPlatformModel)
		r.Delete("/platform-models/{platform_model_id}", s.deletePlatformModel)

		r.Post("/invoke", s.invokeModel)
		r.Get("/models/{model_ref}/context-window", s.getModelContextWindow)
	})

	// Internal service-to-service routes — NOT proxied by api-gateway-bff.
	// Protected by X-Internal-Token header instead of user JWT.
	r.Route("/internal", func(r chi.Router) {
		r.Get("/credentials/{model_source}/{model_ref}", s.getInternalCredentials)
	})

	return r
}

func (s *Server) getInternalCredentials(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
		writeError(w, http.StatusUnauthorized, "INTERNAL_UNAUTHORIZED", "invalid internal token")
		return
	}

	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid user_id")
		return
	}

	modelSource := chi.URLParam(r, "model_source")
	modelRefStr := chi.URLParam(r, "model_ref")
	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid model_ref")
		return
	}

	type credResponse struct {
		ProviderKind      string  `json:"provider_kind"`
		ProviderModelName string  `json:"provider_model_name"`
		BaseURL           string  `json:"base_url"`
		APIKey            string  `json:"api_key"`
		ContextLength     *int    `json:"context_length"`
	}

	var out credResponse

	if modelSource == "user_model" {
		var secretCipher string
		var contextLength *int
		err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name, um.context_length,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&out.ProviderKind, &out.ProviderModelName, &contextLength, &out.BaseURL, &secretCipher)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "INTERNAL_MODEL_NOT_FOUND", "user model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_QUERY_FAILED", "failed to resolve user model")
			return
		}
		secret, err := s.decryptSecret(secretCipher)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_DECRYPT_FAILED", "failed to decrypt secret")
			return
		}
		out.APIKey = secret
		out.ContextLength = contextLength
	} else if modelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind, provider_model_name
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&out.ProviderKind, &out.ProviderModelName)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "INTERNAL_MODEL_NOT_FOUND", "platform model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_QUERY_FAILED", "failed to resolve platform model")
			return
		}
	} else {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid model_source")
		return
	}

	writeJSON(w, http.StatusOK, out)
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

func parseUUIDParam(w http.ResponseWriter, r *http.Request, name string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, name))
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) encryptSecret(raw string) (string, string, error) {
	block, err := aes.NewCipher(s.secretKey)
	if err != nil {
		return "", "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", "", err
	}
	ciphertext := gcm.Seal(nil, nonce, []byte(raw), nil)
	joined := append(nonce, ciphertext...)
	return base64.StdEncoding.EncodeToString(joined), uuid.NewString(), nil
}

func (s *Server) decryptSecret(ciphertext string) (string, error) {
	if ciphertext == "" {
		return "", nil
	}
	block, err := aes.NewCipher(s.secretKey)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	joined, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}
	if len(joined) < gcm.NonceSize() {
		return "", fmt.Errorf("invalid ciphertext")
	}
	nonce := joined[:gcm.NonceSize()]
	body := joined[gcm.NonceSize():]
	plain, err := gcm.Open(nil, nonce, body, nil)
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

func (s *Server) createProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		ProviderKind    string `json:"provider_kind"`
		DisplayName     string `json:"display_name"`
		Secret          string `json:"secret"`
		EndpointBaseURL string `json:"endpoint_base_url"`
		Active          *bool  `json:"active"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	if in.ProviderKind != "openai" && in.ProviderKind != "anthropic" && in.ProviderKind != "ollama" && in.ProviderKind != "lm_studio" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid provider_kind")
		return
	}
	if strings.TrimSpace(in.DisplayName) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "display_name is required")
		return
	}
	if (in.ProviderKind == "openai" || in.ProviderKind == "anthropic") && strings.TrimSpace(in.Secret) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "secret is required for cloud providers")
		return
	}
	if (in.ProviderKind == "ollama" || in.ProviderKind == "lm_studio") && strings.TrimSpace(in.EndpointBaseURL) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "endpoint_base_url is required for local providers")
		return
	}
	encryptedSecret, keyRef, err := s.encryptSecret(in.Secret)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_SECRET_ENCRYPT_FAILED", "failed to encrypt secret")
		return
	}
	status := "active"
	if in.Active != nil && !*in.Active {
		status = "disabled"
	}
	var out struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
	}
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO provider_credentials(owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, secret_key_ref, status)
VALUES ($1,$2,$3,$4,$5,$6,$7)
RETURNING provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at
`, userID, in.ProviderKind, in.DisplayName, nullableString(in.EndpointBaseURL), encryptedSecret, keyRef, status).
		Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.DisplayName, &out.EndpointBaseURL, &out.Status, &out.CreatedAt, &out.UpdatedAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_SAVE_FAILED", "failed to create provider credential")
		return
	}
	writeJSON(w, http.StatusCreated, out)
}

func nullableString(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return v
}

func (s *Server) listProviderCredentials(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at,
       (secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret
FROM provider_credentials
WHERE owner_user_id=$1 AND status <> 'archived'
ORDER BY created_at DESC
`, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to list providers")
		return
	}
	defer rows.Close()
	type row struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
		HasSecret            bool      `json:"has_secret"`
	}
	items := make([]row, 0)
	for rows.Next() {
		var item row
		if err := rows.Scan(&item.ProviderCredentialID, &item.ProviderKind, &item.DisplayName, &item.EndpointBaseURL, &item.Status, &item.CreatedAt, &item.UpdatedAt, &item.HasSecret); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to parse provider row")
			return
		}
		items = append(items, item)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) patchProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return
	}
	var in struct {
		DisplayName     *string `json:"display_name"`
		Secret          *string `json:"secret"`
		EndpointBaseURL *string `json:"endpoint_base_url"`
		Active          *bool   `json:"active"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	var encryptedSecret any
	var keyRef any
	if in.Secret != nil {
		cipherText, ref, err := s.encryptSecret(*in.Secret)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_SECRET_ENCRYPT_FAILED", "failed to encrypt secret")
			return
		}
		encryptedSecret = cipherText
		keyRef = ref
	}
	statusPatch := any(nil)
	if in.Active != nil {
		if *in.Active {
			statusPatch = "active"
		} else {
			statusPatch = "disabled"
		}
	}
	cmdTag, err := s.pool.Exec(r.Context(), `
UPDATE provider_credentials
SET
  display_name = COALESCE($3, display_name),
  endpoint_base_url = COALESCE($4, endpoint_base_url),
  secret_ciphertext = COALESCE($5, secret_ciphertext),
  secret_key_ref = COALESCE($6, secret_key_ref),
  status = COALESCE($7, status),
  updated_at = now()
WHERE provider_credential_id = $1 AND owner_user_id = $2 AND status <> 'archived'
`, id, userID, in.DisplayName, in.EndpointBaseURL, encryptedSecret, keyRef, statusPatch)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_UPDATE_FAILED", "failed to update provider credential")
		return
	}
	if cmdTag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	s.getProviderCredentialByID(w, r, userID, id)
}

func (s *Server) getProviderCredentialByID(w http.ResponseWriter, r *http.Request, userID, id uuid.UUID) {
	var out struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
		HasSecret            bool      `json:"has_secret"`
	}
	err := s.pool.QueryRow(r.Context(), `
SELECT provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at,
       (secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret
FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2
`, id, userID).Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.DisplayName, &out.EndpointBaseURL, &out.Status, &out.CreatedAt, &out.UpdatedAt, &out.HasSecret)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to fetch provider credential")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) deleteProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return
	}
	cmdTag, err := s.pool.Exec(r.Context(), `
UPDATE provider_credentials
SET status='archived', updated_at=now()
WHERE provider_credential_id=$1 AND owner_user_id=$2
`, id, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_DELETE_FAILED", "failed to delete provider credential")
		return
	}
	if cmdTag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) providerHealth(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	cred, ok := s.getCredentialOwned(r.Context(), userID, w, r)
	if !ok {
		return
	}
	adapter, err := provider.ResolveAdapter(cred.ProviderKind, s.client)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_PROVIDER_KIND_UNSUPPORTED", "unsupported provider kind")
		return
	}
	if err := adapter.HealthCheck(r.Context(), cred.EndpointBaseURL, cred.Secret); err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"provider_credential_id": cred.ProviderCredentialID,
			"healthy":                false,
			"message":                err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"provider_credential_id": cred.ProviderCredentialID,
		"healthy":                true,
		"message":                "ok",
	})
}

type credentialRow struct {
	ProviderCredentialID uuid.UUID
	ProviderKind         string
	EndpointBaseURL      string
	Secret               string
}

func (s *Server) getCredentialOwned(ctx context.Context, userID uuid.UUID, w http.ResponseWriter, r *http.Request) (*credentialRow, bool) {
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return nil, false
	}
	var out credentialRow
	var secretCipher string
	err := s.pool.QueryRow(ctx, `
SELECT provider_credential_id, provider_kind, COALESCE(endpoint_base_url,''), COALESCE(secret_ciphertext,'')
FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2 AND status='active'
`, id, userID).Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.EndpointBaseURL, &secretCipher)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return nil, false
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to load provider credential")
		return nil, false
	}
	secret, err := s.decryptSecret(secretCipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt secret")
		return nil, false
	}
	out.Secret = secret
	return &out, true
}

func (s *Server) listProviderInventory(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	cred, ok := s.getCredentialOwned(r.Context(), userID, w, r)
	if !ok {
		return
	}
	refresh := r.URL.Query().Get("refresh") == "true"
	if refresh || cred.ProviderKind == "openai" || cred.ProviderKind == "anthropic" {
		if err := s.syncInventory(r.Context(), cred); err != nil {
			writeError(w, http.StatusBadGateway, "M03_PROVIDER_SYNC_FAILED", "failed to sync provider inventory")
			return
		}
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT provider_model_name, context_length, capability_flags, synced_at
FROM provider_inventory_models
WHERE provider_credential_id=$1
ORDER BY provider_model_name ASC
`, cred.ProviderCredentialID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_INVENTORY_QUERY_FAILED", "failed to list provider inventory")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	var syncedAt *time.Time
	for rows.Next() {
		var modelName string
		var contextLength *int
		var flagsBytes []byte
		var rowSyncedAt time.Time
		if err := rows.Scan(&modelName, &contextLength, &flagsBytes, &rowSyncedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_INVENTORY_QUERY_FAILED", "failed to parse inventory row")
			return
		}
		flags := map[string]any{}
		_ = json.Unmarshal(flagsBytes, &flags)
		items = append(items, map[string]any{
			"provider_model_name": modelName,
			"context_length":      contextLength,
			"capability_flags":    flags,
		})
		syncedAt = &rowSyncedAt
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "synced_at": syncedAt})
}

func (s *Server) syncInventory(ctx context.Context, cred *credentialRow) error {
	adapter, err := provider.ResolveAdapter(cred.ProviderKind, s.client)
	if err != nil {
		return err
	}
	models, err := adapter.ListModels(ctx, cred.EndpointBaseURL, cred.Secret)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `DELETE FROM provider_inventory_models WHERE provider_credential_id=$1`, cred.ProviderCredentialID); err != nil {
		return err
	}
	for _, m := range models {
		flags, _ := json.Marshal(m.CapabilityFlags)
		if _, err := tx.Exec(ctx, `
INSERT INTO provider_inventory_models(provider_credential_id, provider_model_name, context_length, capability_flags, synced_at)
VALUES ($1,$2,$3,$4,now())
`, cred.ProviderCredentialID, m.ProviderModelName, m.ContextLength, flags); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *Server) createUserModel(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		ProviderCredentialID string         `json:"provider_credential_id"`
		ProviderModelName    string         `json:"provider_model_name"`
		ContextLength        *int           `json:"context_length"`
		Alias                string         `json:"alias"`
		CapabilityFlags      map[string]any `json:"capability_flags"`
		Tags                 []modelTag     `json:"tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	credentialID, err := uuid.Parse(in.ProviderCredentialID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid provider_credential_id")
		return
	}
	if strings.TrimSpace(in.ProviderModelName) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "provider_model_name is required")
		return
	}
	var providerKind string
	err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2 AND status='active'
`, credentialID, userID).Scan(&providerKind)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to resolve provider")
		return
	}
	if (providerKind == "ollama" || providerKind == "lm_studio") && (in.ContextLength == nil || *in.ContextLength <= 0) {
		writeError(w, http.StatusBadRequest, "M03_MODEL_CONTEXT_REQUIRED", "context_length is required for ollama/lm_studio")
		return
	}
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)
	var out userModelRow
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO user_models(owner_user_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, capability_flags)
VALUES ($1,$2,$3,$4,$5,$6,$7)
RETURNING user_model_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, is_active, is_favorite, capability_flags, created_at, updated_at
`, userID, credentialID, providerKind, in.ProviderModelName, in.ContextLength, nullableString(in.Alias), flagsBytes).
		Scan(&out.UserModelID, &out.ProviderCredentialID, &out.ProviderKind, &out.ProviderModelName, &out.ContextLength, &out.Alias, &out.IsActive, &out.IsFavorite, &out.CapabilityFlags, &out.CreatedAt, &out.UpdatedAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_CREATE_FAILED", "failed to create user model")
		return
	}
	if err := s.replaceUserModelTags(r.Context(), out.UserModelID, in.Tags); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_TAGS_FAILED", "failed to save tags")
		return
	}
	s.writeUserModel(w, r, userID, out.UserModelID)
}

type modelTag struct {
	TagName string `json:"tag_name"`
	Note    string `json:"note"`
}

type userModelRow struct {
	UserModelID          uuid.UUID
	ProviderCredentialID uuid.UUID
	ProviderKind         string
	ProviderModelName    string
	ContextLength        *int
	Alias                *string
	IsActive             bool
	IsFavorite           bool
	CapabilityFlags      []byte
	CreatedAt            time.Time
	UpdatedAt            time.Time
}

func (s *Server) listUserModels(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	includeInactive := r.URL.Query().Get("include_inactive") != "false"
	onlyFavorites := r.URL.Query().Get("only_favorites") == "true"
	providerFilter := r.URL.Query().Get("provider_kind")
	query := `
SELECT user_model_id FROM user_models WHERE owner_user_id=$1
`
	args := []any{userID}
	argPos := 2
	if !includeInactive {
		query += fmt.Sprintf(" AND is_active=$%d", argPos)
		args = append(args, true)
		argPos++
	}
	if onlyFavorites {
		query += fmt.Sprintf(" AND is_favorite=$%d", argPos)
		args = append(args, true)
		argPos++
	}
	if providerFilter != "" {
		query += fmt.Sprintf(" AND provider_kind=$%d", argPos)
		args = append(args, providerFilter)
		argPos++
	}
	query += " ORDER BY created_at DESC"
	rows, err := s.pool.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to list user models")
		return
	}
	defer rows.Close()
	items := make([]any, 0)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to parse user model")
			return
		}
		model, err := s.readUserModel(r.Context(), userID, id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to fetch user model detail")
			return
		}
		if model != nil {
			items = append(items, model)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) readUserModel(ctx context.Context, userID, id uuid.UUID) (map[string]any, error) {
	var row userModelRow
	err := s.pool.QueryRow(ctx, `
SELECT user_model_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, is_active, is_favorite, capability_flags, created_at, updated_at
FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2
`, id, userID).Scan(&row.UserModelID, &row.ProviderCredentialID, &row.ProviderKind, &row.ProviderModelName, &row.ContextLength, &row.Alias, &row.IsActive, &row.IsFavorite, &row.CapabilityFlags, &row.CreatedAt, &row.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	flags := map[string]any{}
	_ = json.Unmarshal(row.CapabilityFlags, &flags)
	tags, err := s.loadTags(ctx, row.UserModelID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"user_model_id":          row.UserModelID,
		"provider_credential_id": row.ProviderCredentialID,
		"provider_kind":          row.ProviderKind,
		"provider_model_name":    row.ProviderModelName,
		"context_length":         row.ContextLength,
		"alias":                  row.Alias,
		"is_active":              row.IsActive,
		"is_favorite":            row.IsFavorite,
		"capability_flags":       flags,
		"tags":                   tags,
		"created_at":             row.CreatedAt,
		"updated_at":             row.UpdatedAt,
	}, nil
}

func (s *Server) loadTags(ctx context.Context, userModelID uuid.UUID) ([]modelTag, error) {
	rows, err := s.pool.Query(ctx, `SELECT tag_name, COALESCE(note,'') FROM user_model_tags WHERE user_model_id=$1 ORDER BY tag_name ASC`, userModelID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	tags := make([]modelTag, 0)
	for rows.Next() {
		var t modelTag
		if err := rows.Scan(&t.TagName, &t.Note); err != nil {
			return nil, err
		}
		tags = append(tags, t)
	}
	return tags, nil
}

func (s *Server) patchUserModel(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in struct {
		Alias           *string        `json:"alias"`
		ContextLength   *int           `json:"context_length"`
		CapabilityFlags map[string]any `json:"capability_flags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)
	cmd, err := s.pool.Exec(r.Context(), `
UPDATE user_models
SET alias=COALESCE($3, alias),
    context_length=COALESCE($4, context_length),
    capability_flags=CASE WHEN $5::jsonb IS NULL THEN capability_flags ELSE $5 END,
    updated_at=now()
WHERE user_model_id=$1 AND owner_user_id=$2
`, id, userID, in.Alias, in.ContextLength, nullJSON(flagsBytes, in.CapabilityFlags != nil))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_UPDATE_FAILED", "failed to patch user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func nullJSON(b []byte, valid bool) any {
	if !valid {
		return nil
	}
	return b
}

func (s *Server) deleteUserModel(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	cmd, err := s.pool.Exec(r.Context(), `DELETE FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`, id, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_DELETE_FAILED", "failed to delete user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) patchUserModelActivation(w http.ResponseWriter, r *http.Request) {
	s.patchUserModelBoolField(w, r, "is_active", "M03_USER_MODEL_ACTIVATION_FAILED")
}

func (s *Server) patchUserModelFavorite(w http.ResponseWriter, r *http.Request) {
	s.patchUserModelBoolField(w, r, "is_favorite", "M03_USER_MODEL_FAVORITE_FAILED")
}

func (s *Server) patchUserModelBoolField(w http.ResponseWriter, r *http.Request, field, errorCode string) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in map[string]bool
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	value, ok := in[field]
	if !ok {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", field+" is required")
		return
	}
	cmd, err := s.pool.Exec(r.Context(), fmt.Sprintf(`
UPDATE user_models SET %s=$3, updated_at=now()
WHERE user_model_id=$1 AND owner_user_id=$2
`, field), id, userID, value)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errorCode, "failed to patch user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func (s *Server) putUserModelTags(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in struct {
		Tags []modelTag `json:"tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	var exists bool
	err := s.pool.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2)`, id, userID).Scan(&exists)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to check user model")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	if err := s.replaceUserModelTags(r.Context(), id, in.Tags); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_TAGS_FAILED", "failed to save tags")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func (s *Server) replaceUserModelTags(ctx context.Context, userModelID uuid.UUID, tags []modelTag) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `DELETE FROM user_model_tags WHERE user_model_id=$1`, userModelID); err != nil {
		return err
	}
	for _, t := range tags {
		name := strings.TrimSpace(t.TagName)
		if name == "" {
			continue
		}
		if _, err := tx.Exec(ctx, `INSERT INTO user_model_tags(user_model_id, tag_name, note) VALUES ($1,$2,$3)`, userModelID, name, nullableString(t.Note)); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *Server) writeUserModel(w http.ResponseWriter, r *http.Request, userID, id uuid.UUID) {
	item, err := s.readUserModel(r.Context(), userID, id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to fetch user model")
		return
	}
	if item == nil {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) createPlatformModel(w http.ResponseWriter, r *http.Request) {
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
		ProviderKind    string         `json:"provider_kind"`
		ProviderModel   string         `json:"provider_model_name"`
		DisplayName     string         `json:"display_name"`
		Status          string         `json:"status"`
		PricingPolicy   map[string]any `json:"pricing_policy"`
		QuotaPolicyRef  string         `json:"quota_policy_ref"`
		CapabilityFlags map[string]any `json:"capability_flags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	pricing, _ := json.Marshal(in.PricingPolicy)
	flags, _ := json.Marshal(in.CapabilityFlags)
	_, err := s.pool.Exec(r.Context(), `
INSERT INTO platform_models(provider_kind, provider_model_name, display_name, status, pricing_policy, quota_policy_ref, capability_flags)
VALUES ($1,$2,$3,$4,$5,$6,$7)
`, in.ProviderKind, in.ProviderModel, in.DisplayName, in.Status, pricing, nullableString(in.QuotaPolicyRef), flags)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_CREATE_FAILED", "failed to create platform model")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) listPlatformModels(w http.ResponseWriter, r *http.Request) {
	_, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) writePlatformModelList(w http.ResponseWriter, r *http.Request) {
	rows, err := s.pool.Query(r.Context(), `
SELECT platform_model_id, provider_kind, provider_model_name, display_name, status, pricing_policy, quota_policy_ref, capability_flags, created_at, updated_at
FROM platform_models
ORDER BY created_at DESC
`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_QUERY_FAILED", "failed to list platform models")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id uuid.UUID
		var kind, modelName, displayName, status string
		var pricingRaw []byte
		var quotaRef *string
		var flagsRaw []byte
		var createdAt, updatedAt time.Time
		if err := rows.Scan(&id, &kind, &modelName, &displayName, &status, &pricingRaw, &quotaRef, &flagsRaw, &createdAt, &updatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_QUERY_FAILED", "failed to parse platform model")
			return
		}
		pricing := map[string]any{}
		flags := map[string]any{}
		_ = json.Unmarshal(pricingRaw, &pricing)
		_ = json.Unmarshal(flagsRaw, &flags)
		items = append(items, map[string]any{
			"platform_model_id":   id,
			"provider_kind":       kind,
			"provider_model_name": modelName,
			"display_name":        displayName,
			"status":              status,
			"pricing_policy":      pricing,
			"quota_policy_ref":    quotaRef,
			"capability_flags":    flags,
			"created_at":          createdAt,
			"updated_at":          updatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) patchPlatformModel(w http.ResponseWriter, r *http.Request) {
	_, role, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	if role != "admin" {
		writeError(w, http.StatusForbidden, "M03_FORBIDDEN", "admin only")
		return
	}
	id, ok := parseUUIDParam(w, r, "platform_model_id")
	if !ok {
		return
	}
	var in struct {
		DisplayName     *string        `json:"display_name"`
		Status          *string        `json:"status"`
		PricingPolicy   map[string]any `json:"pricing_policy"`
		QuotaPolicyRef  *string        `json:"quota_policy_ref"`
		CapabilityFlags map[string]any `json:"capability_flags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	pricing, _ := json.Marshal(in.PricingPolicy)
	flags, _ := json.Marshal(in.CapabilityFlags)
	cmd, err := s.pool.Exec(r.Context(), `
UPDATE platform_models
SET
  display_name=COALESCE($2, display_name),
  status=COALESCE($3, status),
  pricing_policy=CASE WHEN $4::jsonb IS NULL THEN pricing_policy ELSE $4 END,
  quota_policy_ref=COALESCE($5, quota_policy_ref),
  capability_flags=CASE WHEN $6::jsonb IS NULL THEN capability_flags ELSE $6 END,
  updated_at=now()
WHERE platform_model_id=$1
`, id, in.DisplayName, in.Status, nullJSON(pricing, in.PricingPolicy != nil), in.QuotaPolicyRef, nullJSON(flags, in.CapabilityFlags != nil))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_UPDATE_FAILED", "failed to patch platform model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PLATFORM_MODEL_NOT_FOUND", "platform model not found")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) deletePlatformModel(w http.ResponseWriter, r *http.Request) {
	_, role, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	if role != "admin" {
		writeError(w, http.StatusForbidden, "M03_FORBIDDEN", "admin only")
		return
	}
	id, ok := parseUUIDParam(w, r, "platform_model_id")
	if !ok {
		return
	}
	cmd, err := s.pool.Exec(r.Context(), `DELETE FROM platform_models WHERE platform_model_id=$1`, id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_DELETE_FAILED", "failed to delete platform model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PLATFORM_MODEL_NOT_FOUND", "platform model not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) invokeModel(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		ModelSource string         `json:"model_source"`
		ModelRef    string         `json:"model_ref"`
		Input       map[string]any `json:"input"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid model_ref")
		return
	}
	var providerKind, providerModelName, endpointBaseURL, secret string
	var modelID uuid.UUID
	if in.ModelSource == "user_model" {
		var secretCipher string
		err = s.pool.QueryRow(r.Context(), `
SELECT um.user_model_id, um.provider_kind, um.provider_model_name, COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&modelID, &providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "M03_MODEL_NOT_FOUND", "user model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_MODEL_QUERY_FAILED", "failed to resolve user model")
			return
		}
		secret, err = s.decryptSecret(secretCipher)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt provider secret")
			return
		}
	} else if in.ModelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT platform_model_id, provider_kind, provider_model_name
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&modelID, &providerKind, &providerModelName)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "M03_MODEL_NOT_FOUND", "platform model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_MODEL_QUERY_FAILED", "failed to resolve platform model")
			return
		}
		// Platform model route intentionally requires adapter path only; secret/endpoint handled by adapter config.
	} else {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid model_source")
		return
	}
	adapter, err := provider.ResolveAdapter(providerKind, s.invokeClient)
	if err != nil {
		writeError(w, http.StatusConflict, "M03_PROVIDER_ROUTE_VIOLATION", "model route violation")
		return
	}
	output, usage, err := adapter.Invoke(r.Context(), endpointBaseURL, secret, providerModelName, in.Input)
	if err != nil {
		writeError(w, http.StatusBadGateway, "M03_PROVIDER_INVOKE_FAILED", "provider invoke failed")
		return
	}
	requestID := uuid.New()
	logID, decision, billedCost, err := s.recordInvocation(r.Context(), map[string]any{
		"request_id":     requestID,
		"owner_user_id":  userID,
		"provider_kind":  providerKind,
		"model_source":   in.ModelSource,
		"model_ref":      modelID,
		"input_tokens":   usage.InputTokens,
		"output_tokens":  usage.OutputTokens,
		"input_payload":  in.Input,
		"output_payload": output,
		"request_status": "success",
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, "M03_BILLING_RECORD_FAILED", "failed to write usage log")
		return
	}
	if decision == "rejected" {
		writeError(w, http.StatusPaymentRequired, "M03_BILLING_REJECTED", "quota and credits exhausted")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"request_id":    requestID,
		"usage_log_id":  logID,
		"output":        output,
		"billing_cost":  billedCost,
		"billing_mode":  decision,
		"provider_kind": providerKind,
	})
}

func (s *Server) verifyUserModel(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	modelID, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}

	var providerKind, providerModelName, endpointBaseURL, secretCipher string
	err := s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelID, userID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_MODEL_NOT_FOUND", "user model not found or inactive")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_MODEL_QUERY_FAILED", "failed to resolve user model")
		return
	}

	secret, err := s.decryptSecret(secretCipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt provider secret")
		return
	}

	verifyClient := &http.Client{Timeout: 5 * time.Minute}
	adapter, err := provider.ResolveAdapter(providerKind, verifyClient)
	if err != nil {
		writeError(w, http.StatusConflict, "M03_PROVIDER_ROUTE_VIOLATION", "unsupported provider kind")
		return
	}

	pingInput := map[string]any{
		"messages": []map[string]any{
			{"role": "user", "content": "Hi"},
		},
	}

	// Give the model up to 5 minutes to respond.
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	start := time.Now()
	output, _, invokeErr := adapter.Invoke(ctx, endpointBaseURL, secret, providerModelName, pingInput)

	latencyMs := time.Since(start).Milliseconds()

	if invokeErr != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"verified":   false,
			"latency_ms": latencyMs,
			"error":      invokeErr.Error(),
		})
		return
	}

	// Extract a short preview from the output.
	preview := ""
	if content, ok := output["content"]; ok {
		preview = fmt.Sprintf("%v", content)
	} else if choices, ok := output["choices"]; ok {
		preview = fmt.Sprintf("%v", choices)
	}
	if len(preview) > 200 {
		preview = preview[:200] + "…"
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"verified":         true,
		"latency_ms":       latencyMs,
		"response_preview": preview,
	})
}

// getModelContextWindow returns the context window size (in tokens) for a given model.
// Called internally by the translation-worker before chunking a chapter.
// No auth required — this endpoint is internal only and returns a safe fallback on any error.
func (s *Server) getModelContextWindow(w http.ResponseWriter, r *http.Request) {
	modelRefStr := chi.URLParam(r, "model_ref")
	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"context_window": 8192})
		return
	}
	modelSource := r.URL.Query().Get("model_source")

	const fallback = 8192

	if modelSource == "platform_model" {
		var providerKind, providerModelName string
		err = s.pool.QueryRow(r.Context(),
			"SELECT provider_kind, provider_model_name FROM platform_models WHERE platform_model_id=$1 AND status='active'",
			modelRef,
		).Scan(&providerKind, &providerModelName)
		if err != nil {
			writeJSON(w, http.StatusOK, map[string]any{"context_window": fallback})
			return
		}
		adapter, err := provider.ResolveAdapter(providerKind, s.client)
		if err != nil {
			writeJSON(w, http.StatusOK, map[string]any{"context_window": fallback})
			return
		}
		models, err := adapter.ListModels(r.Context(), "", "")
		if err != nil {
			writeJSON(w, http.StatusOK, map[string]any{"context_window": fallback})
			return
		}
		for _, m := range models {
			if m.ProviderModelName == providerModelName && m.ContextLength != nil {
				writeJSON(w, http.StatusOK, map[string]any{"context_window": *m.ContextLength})
				return
			}
		}
		writeJSON(w, http.StatusOK, map[string]any{"context_window": fallback})
		return
	}

	// user_model — look up context_length stored during inventory sync
	var contextLength *int
	err = s.pool.QueryRow(r.Context(),
		"SELECT context_length FROM user_models WHERE user_model_id=$1 AND is_active=true",
		modelRef,
	).Scan(&contextLength)
	if err != nil || contextLength == nil {
		writeJSON(w, http.StatusOK, map[string]any{"context_window": fallback})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"context_window": *contextLength})
}

func (s *Server) recordInvocation(ctx context.Context, payload map[string]any) (uuid.UUID, string, float64, error) {
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(s.cfg.UsageBillingServiceURL, "/")+"/internal/model-billing/record", bytes.NewReader(body))
	if err != nil {
		return uuid.Nil, "", 0, err
	}
	req.Header.Set("Content-Type", "application/json")
	res, err := s.client.Do(req)
	if err != nil {
		return uuid.Nil, "", 0, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusCreated && res.StatusCode != http.StatusOK {
		return uuid.Nil, "", 0, fmt.Errorf("billing status %d", res.StatusCode)
	}
	var out struct {
		UsageLogID   uuid.UUID `json:"usage_log_id"`
		BillingMode  string    `json:"billing_mode"`
		TotalCostUSD float64   `json:"total_cost_usd"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return uuid.Nil, "", 0, err
	}
	return out.UsageLogID, out.BillingMode, out.TotalCostUSD, nil
}
