package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// S-SETTINGS MCP server (Wave 2, provider gateway). Exposes the user's settings —
// profile + AI model registry — as MCP tools so a chat agent can manage them from
// chat. Hosted HERE (provider-registry-service), not auth-service, because 10 of
// the 12 tools are model-registry operations whose data + secret-encryption + DB
// already live in this service; the two profile tools reach auth-service over its
// existing /internal route (each service owns its own DB — no cross-service SQL).
//
// scope=user (UserScopeGuard): a tool may only read/mutate rows the ENVELOPE's
// caller owns. Identity comes from X-User-Id (kit IdentityMiddleware), NEVER from a
// tool arg (SEC-1). H13: 403/404 collapse to one uniform "not accessible" error.
//
// H13 SECRET REDACTION (load-bearing): the read tools are written so a credential
// secret can NEVER appear in a result — they simply do not SELECT
// secret_ciphertext (let alone decrypt it). There is deliberately no tool that
// returns, accepts, or even references a raw provider secret. provider_create /
// provider_update_secret are NOT tools (OD-S1): a secret must never be an
// LLM-visible tool argument, so the agent routes the user to the UI via
// ui_navigate('/settings') instead.
//
// Tool NAMING (C-GW): the ai-gateway DROPS any tool whose name does not start with
// the provider's prefix — for settings that prefix is "settings_". The §4 catalog's
// logical names (model_register, model_delete, …) are therefore wired on the wire
// with the mandatory settings_ prefix: settings_model_register, settings_model_delete,
// etc. Reads use their catalog names (settings_get_profile, …) which already match.

const (
	// settingsConfirmDescriptor binds the Tier-W model-delete confirm token to its
	// one action (confused-deputy guard: a token minted for this descriptor can
	// confirm NOTHING else).
	settingsConfirmDescriptor = "settings.model_delete"
	settingsConfirmTTL        = 10 * time.Minute
)

// mcpHandler builds the settings MCP server wrapped in the kit identity
// middleware (SEC-1: X-Internal-Token check + X-User-Id → ctx). Mounted at /mcp by
// Router(). Every tool's _meta carries tier+scope (C-TOOL), validated at
// registration via the kit (a malformed tool fails boot, not a request).
func (s *Server) mcpHandler() http.Handler {
	srv := mcp.NewServer(&mcp.Implementation{Name: "settings", Version: "0.1.0"}, nil)

	// ── Tier R (reads; secrets redacted by construction) ───────────────────────
	registerTool(srv, &mcp.Tool{
		Name:        "settings_get_profile",
		Description: "Get the signed-in user's account profile: display name, locale, avatar URL, bio, languages, email, and email-verified status. Read-only.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"account", "profile", "my info", "display name", "languages", "bio"}),
	}, s.toolGetProfile)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_list_providers",
		Description: "List the user's configured AI provider credentials (e.g. OpenAI, Anthropic, a local LM Studio). Returns provider kind, display name, endpoint, status, and whether a secret is set — but NEVER the secret itself. Use to see which providers exist before registering a model.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"providers", "credentials", "api keys", "byok", "list providers"}),
	}, s.toolListProviders)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_list_models",
		Description: "List the user's registered AI models (their BYOK 'user models'). Returns model alias, provider kind, provider model name, context length, capabilities, tags, active/favorite flags. No secrets.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"models", "my models", "list models", "registered models", "llm"}),
	}, s.toolListModels)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_get_defaults",
		Description: "Get the user's per-capability default models (e.g. which model is the default for rerank or embedding).",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"defaults", "default model", "default rerank", "default embedding"}),
	}, s.toolGetDefaults)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_provider_inventory",
		Description: "List the upstream models a configured provider credential currently offers (its live inventory), so the user can pick one to register. Takes a provider_credential_id. No secrets returned.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, []string{"inventory", "models this provider offers", "provider models", "what models"}),
	}, s.toolProviderInventory)

	// ── Tier R, PAID (universal web research — Track D CD5) ────────────────────
	// Not `settings_`-prefixed: `web_search` is this server's SECOND namespace, so
	// ai-gateway's EXTRA_PREFIX_MAP.settings must list `web_` or the C-GW prefix gate
	// silently drops it. See mcp_web_search_tool.go.
	s.registerWebSearchTool(srv)

	// ── Tier A (auto-commit + Undo; all free/reversible) ───────────────────────
	registerTool(srv, &mcp.Tool{
		Name:        "settings_update_profile",
		Description: "Update the user's profile fields (display_name, locale, avatar_url, bio, languages). Only the provided fields change. Free and reversible.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update profile", "change name", "set bio", "edit profile", "set languages"}),
	}, s.toolUpdateProfile)

	// model_register — wire name carries the mandatory settings_ prefix (C-GW).
	// NO secret arg (OD-S1): registering a model that needs a key still requires
	// the key to be entered via the UI; this tool only records the model row
	// against an EXISTING provider credential.
	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_register",
		Description: "Register a new AI model the user can use, against one of their EXISTING provider credentials. Does NOT take an API key — if the provider needs a secret, the user adds it in Settings first. Provide the provider_credential_id and the provider_model_name (and optional alias, context_length, capability_flags). Free and reversible (delete to undo).",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"register model", "add model", "new model", "create model"}),
	}, s.toolModelRegister)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_update",
		Description: "Update an existing registered model's editable fields (alias, context_length, capability_flags, notes). Only provided fields change.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"update model", "rename model", "edit model", "set context length"}),
	}, s.toolModelUpdate)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_set_favorite",
		Description: "Mark a registered model as a favorite (or un-favorite it). Free and reversible.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"favorite", "mark model as favorite", "pin model", "unfavorite"}),
	}, s.toolModelSetFavorite)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_set_active",
		Description: "Activate or deactivate a registered model (an inactive model is hidden from pickers but not deleted). Free and reversible.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"activate model", "deactivate model", "enable model", "disable model"}),
	}, s.toolModelSetActive)

	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_set_default",
		Description: "Set (or clear) the user's default model for a capability (rerank or embedding). Free and reversible — set it back to the previous default to undo.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, []string{"set default", "set my default model", "make default", "clear default"}),
	}, s.toolModelSetDefault)

	// ── Tier W (confirm_action; descriptor settings.model_delete) ──────────────
	registerTool(srv, &mcp.Tool{
		Name:        "settings_model_delete",
		Description: "Delete a registered model permanently. High-impact: this does NOT delete immediately — it returns a confirm_token + a preview that the user must explicitly confirm. Pass the confirm_token to confirm_action with domain='settings'.",
		Meta:        lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeUser, nil, []string{"delete model", "remove model", "drop model"}),
	}, s.toolModelDelete)

	return lwmcp.NewStatelessHandler(srv, s.cfg.InternalServiceToken)
}

// registerTool validates the tool's C-TOOL _meta (tier+scope required — a malformed
// tool panics at boot, not at request time) and then registers it. Generic over the
// handler's In/Out so each call site infers types from its typed handler; mcp.AddTool
// can't be threaded through an `any`, hence this helper.
func registerTool[In, Out any](srv *mcp.Server, t *mcp.Tool, h func(context.Context, *mcp.CallToolRequest, In) (*mcp.CallToolResult, Out, error)) {
	lwmcp.MustValidateToolMeta(t)
	lwmcp.RegisterTool(srv, t, h)
}

// callerID extracts the envelope user id; a tool MUST refuse on absence rather than
// proceed with uuid.Nil (SEC-1).
func callerID(ctx context.Context) (uuid.UUID, error) {
	uid, ok := lwmcp.UserIDFromCtx(ctx)
	if !ok {
		return uuid.Nil, errors.New("missing caller identity")
	}
	return uid, nil
}

// userModelGuard returns the kit UserScopeGuard for user_models: it resolves a
// model id → its owner_user_id and checks owner == caller. A missing row collapses
// to ErrNotAccessible (H13 — no existence oracle). Used by every per-model mutation.
func (s *Server) userModelGuard() lwmcp.Guard {
	return lwmcp.UserScopeGuard(func(ctx context.Context, resID uuid.UUID) (uuid.UUID, error) {
		var owner uuid.UUID
		err := s.pool.QueryRow(ctx, `SELECT owner_user_id FROM user_models WHERE user_model_id=$1`, resID).Scan(&owner)
		if err != nil {
			return uuid.Nil, err // UserScopeGuard runs UniformNotAccessible over this
		}
		return owner, nil
	})
}

// providerCredGuard is the same shape for provider_credentials (used by
// settings_provider_inventory).
func (s *Server) providerCredGuard() lwmcp.Guard {
	return lwmcp.UserScopeGuard(func(ctx context.Context, resID uuid.UUID) (uuid.UUID, error) {
		var owner uuid.UUID
		err := s.pool.QueryRow(ctx, `SELECT owner_user_id FROM provider_credentials WHERE provider_credential_id=$1`, resID).Scan(&owner)
		if err != nil {
			return uuid.Nil, err
		}
		return owner, nil
	})
}

// ── Tier R: profile ───────────────────────────────────────────────────────────

type emptyIn struct{}

// profileObject decodes the auth-service profile body into a plain object.
//
// It must NOT be `json.RawMessage`. That type is `[]byte`, so the MCP Go SDK's schema
// inference declares the field as `["null","array"]` — while `encoding/json` marshals it
// as the raw JSON it holds, an OBJECT. The SDK then validates the tool's OUTPUT against
// its own declared schema and rejects every call:
//
//	validating /properties/profile: type: map[...] has type "object", want one of "null, array"
//
// Both settings_get_profile and settings_update_profile were broken this way — 100% of
// calls, for every user, since the tools were written. Nothing caught it: the wire gates
// assert over `tools/list` metadata and never call `tools/call`, and no NL probe covered
// them. A deterministic capability sweep (scripts/eval/tool_liveness/sweep.py) found it.
//
// Rule: an MCP tool's Out struct must never carry a `json.RawMessage` field.
func profileObject(body json.RawMessage) map[string]any {
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		return map[string]any{}
	}
	return m
}

type getProfileOut struct {
	Profile map[string]any `json:"profile"`
}

func (s *Server) toolGetProfile(ctx context.Context, _ *mcp.CallToolRequest, _ emptyIn) (*mcp.CallToolResult, getProfileOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, getProfileOut{}, err
	}
	body, err := s.authProfileRequest(ctx, http.MethodGet, uid, nil)
	if err != nil {
		return nil, getProfileOut{}, err
	}
	return nil, getProfileOut{Profile: profileObject(body)}, nil
}

// ── Tier R: providers (NO secret) ──────────────────────────────────────────────

type providerRow struct {
	ProviderCredentialID string `json:"provider_credential_id"`
	ProviderKind         string `json:"provider_kind"`
	DisplayName          string `json:"display_name"`
	EndpointBaseURL      string `json:"endpoint_base_url,omitempty"`
	Status               string `json:"status"`
	HasSecret            bool   `json:"has_secret"` // boolean ONLY — never the secret
	APIStandard          string `json:"api_standard"`
}
type listProvidersOut struct {
	Providers []providerRow `json:"providers"`
}

func (s *Server) toolListProviders(ctx context.Context, _ *mcp.CallToolRequest, _ emptyIn) (*mcp.CallToolResult, listProvidersOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, listProvidersOut{}, err
	}
	// H13 secret redaction: this SELECT never reads secret_ciphertext. has_secret
	// is computed server-side as a boolean existence flag only.
	rows, err := s.pool.Query(ctx, `
SELECT provider_credential_id, provider_kind, display_name, COALESCE(endpoint_base_url,''), status,
       (secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret, api_standard
FROM provider_credentials
WHERE owner_user_id=$1 AND status <> 'archived'
ORDER BY created_at DESC`, uid)
	if err != nil {
		return nil, listProvidersOut{}, errors.New("failed to list providers")
	}
	defer rows.Close()
	out := listProvidersOut{Providers: []providerRow{}}
	for rows.Next() {
		var p providerRow
		if err := rows.Scan(&p.ProviderCredentialID, &p.ProviderKind, &p.DisplayName, &p.EndpointBaseURL, &p.Status, &p.HasSecret, &p.APIStandard); err != nil {
			return nil, listProvidersOut{}, errors.New("failed to read provider row")
		}
		out.Providers = append(out.Providers, p)
	}
	if err := rows.Err(); err != nil {
		return nil, listProvidersOut{}, errors.New("failed to read providers")
	}
	return nil, out, nil
}

// ── Tier R: models (NO secret) ─────────────────────────────────────────────────

type listModelsIn struct {
	OnlyFavorites bool   `json:"only_favorites,omitempty" jsonschema:"return only favorited models"`
	ActiveOnly    bool   `json:"active_only,omitempty" jsonschema:"return only active models (default false — inactive models are included)"`
	ProviderKind  string `json:"provider_kind,omitempty" jsonschema:"filter by provider kind (e.g. openai, anthropic)"`
}
type listModelsOut struct {
	Models []map[string]any `json:"models"`
}

func (s *Server) toolListModels(ctx context.Context, _ *mcp.CallToolRequest, in listModelsIn) (*mcp.CallToolResult, listModelsOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, listModelsOut{}, err
	}
	q := `SELECT user_model_id FROM user_models WHERE owner_user_id=$1`
	args := []any{uid}
	n := 2
	// Default lists ALL models (active + inactive) — the friendly default for "show
	// me my models". active_only is opt-in (zero value false → include inactive).
	if in.ActiveOnly {
		q += fmt.Sprintf(" AND is_active=$%d", n)
		args = append(args, true)
		n++
	}
	if in.OnlyFavorites {
		q += fmt.Sprintf(" AND is_favorite=$%d", n)
		args = append(args, true)
		n++
	}
	if in.ProviderKind != "" {
		q += fmt.Sprintf(" AND provider_kind=$%d", n)
		args = append(args, in.ProviderKind)
		n++
	}
	// Honor the user's custom sort order ((8)-residual) so an agent's model list
	// matches the shared ModelPicker; un-ordered models keep the historical
	// newest-first fallback.
	q += " ORDER BY sort_order ASC NULLS LAST, created_at DESC"
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, listModelsOut{}, errors.New("failed to list models")
	}
	ids := []uuid.UUID{}
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return nil, listModelsOut{}, errors.New("failed to read model row")
		}
		ids = append(ids, id)
	}
	rows.Close()
	out := listModelsOut{Models: []map[string]any{}}
	// readUserModel SELECTs an explicit column list; a credential SECRET is never
	// in it — and user_models never holds a secret anyway (secrets live only in
	// provider_credentials). So this read is secret-free by construction. (It DOES
	// now return the caller's own `pricing` + `sort_order` — not secrets.)
	for _, id := range ids {
		m, err := s.readUserModel(ctx, uid, id)
		if err != nil {
			return nil, listModelsOut{}, errors.New("failed to read model")
		}
		if m != nil {
			out.Models = append(out.Models, m)
		}
	}
	return nil, out, nil
}

// ── Tier R: defaults ───────────────────────────────────────────────────────────

type getDefaultsOut struct {
	Defaults map[string]string `json:"defaults"`
}

func (s *Server) toolGetDefaults(ctx context.Context, _ *mcp.CallToolRequest, _ emptyIn) (*mcp.CallToolResult, getDefaultsOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, getDefaultsOut{}, err
	}
	rows, err := s.pool.Query(ctx, `
SELECT d.capability, d.user_model_id
FROM user_default_models d
JOIN user_models um ON um.user_model_id = d.user_model_id
WHERE d.owner_user_id = $1`, uid)
	if err != nil {
		return nil, getDefaultsOut{}, errors.New("failed to load defaults")
	}
	defer rows.Close()
	out := getDefaultsOut{Defaults: map[string]string{}}
	for rows.Next() {
		var cap string
		var modelID uuid.UUID
		if err := rows.Scan(&cap, &modelID); err != nil {
			return nil, getDefaultsOut{}, errors.New("failed to read defaults")
		}
		out.Defaults[cap] = modelID.String()
	}
	return nil, out, nil
}

// ── Tier R: provider inventory ─────────────────────────────────────────────────

type providerInventoryIn struct {
	ProviderCredentialID string `json:"provider_credential_id" jsonschema:"the provider credential whose live model inventory to list (UUID)"`
}
type providerInventoryOut struct {
	Models []map[string]any `json:"models"`
}

func (s *Server) toolProviderInventory(ctx context.Context, _ *mcp.CallToolRequest, in providerInventoryIn) (*mcp.CallToolResult, providerInventoryOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, providerInventoryOut{}, err
	}
	credID, err := uuid.Parse(in.ProviderCredentialID)
	if err != nil {
		return nil, providerInventoryOut{}, errors.New("provider_credential_id must be a UUID")
	}
	if err := s.providerCredGuard().Check(ctx, uid, credID); err != nil {
		return nil, providerInventoryOut{}, uniformGuardError(err)
	}
	// Read the cached inventory only (no upstream sync — that would need the
	// secret; the agent reads what's already synced). No secret touched.
	rows, err := s.pool.Query(ctx, `
SELECT provider_model_name, context_length, capability_flags
FROM provider_inventory_models
WHERE provider_credential_id=$1
ORDER BY provider_model_name ASC`, credID)
	if err != nil {
		return nil, providerInventoryOut{}, errors.New("failed to list inventory")
	}
	defer rows.Close()
	out := providerInventoryOut{Models: []map[string]any{}}
	for rows.Next() {
		var name string
		var ctxLen *int
		var flagsBytes []byte
		if err := rows.Scan(&name, &ctxLen, &flagsBytes); err != nil {
			return nil, providerInventoryOut{}, errors.New("failed to read inventory row")
		}
		flags := map[string]any{}
		_ = json.Unmarshal(flagsBytes, &flags)
		out.Models = append(out.Models, map[string]any{
			"provider_model_name": name,
			"context_length":      ctxLen,
			"capability_flags":    flags,
		})
	}
	return nil, out, nil
}

// ── Tier A: profile update ─────────────────────────────────────────────────────

type updateProfileIn struct {
	DisplayName *string  `json:"display_name,omitempty" jsonschema:"new display name"`
	Locale      *string  `json:"locale,omitempty" jsonschema:"new locale (e.g. en, vi)"`
	AvatarURL   *string  `json:"avatar_url,omitempty" jsonschema:"new avatar URL"`
	Bio         *string  `json:"bio,omitempty" jsonschema:"new bio (max 1000 chars)"`
	Languages   []string `json:"languages,omitempty" jsonschema:"languages the user reads/writes (max 20)"`
}
type updateProfileOut struct {
	// map, not json.RawMessage — see profileObject. Same output-schema break.
	Profile  map[string]any `json:"profile"`
	UndoHint map[string]any `json:"_meta_undo_hint,omitempty"`
}

func (s *Server) toolUpdateProfile(ctx context.Context, _ *mcp.CallToolRequest, in updateProfileIn) (*mcp.CallToolResult, updateProfileOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, updateProfileOut{}, err
	}
	// Capture the BEFORE state so we can hand the agent a precise undo (C-ACTIVITY:
	// Tier-A undo_hint). The reverse op is settings_update_profile with the prior
	// values of exactly the fields this call changes.
	before, err := s.authProfileRequest(ctx, http.MethodGet, uid, nil)
	if err != nil {
		return nil, updateProfileOut{}, err
	}
	patch := map[string]any{}
	if in.DisplayName != nil {
		patch["display_name"] = *in.DisplayName
	}
	if in.Locale != nil {
		patch["locale"] = *in.Locale
	}
	if in.AvatarURL != nil {
		patch["avatar_url"] = *in.AvatarURL
	}
	if in.Bio != nil {
		patch["bio"] = *in.Bio
	}
	if in.Languages != nil {
		patch["languages"] = in.Languages
	}
	if len(patch) == 0 {
		return nil, updateProfileOut{}, errors.New("no profile fields provided to update")
	}
	body, err := s.authProfileRequest(ctx, http.MethodPatch, uid, patch)
	if err != nil {
		return nil, updateProfileOut{}, err
	}
	res := mcpResultWithUndo(undoHintForProfile(before, patch))
	return res, updateProfileOut{Profile: profileObject(body), UndoHint: undoHintForProfile(before, patch)}, nil
}

// undoHintForProfile builds the reverse settings_update_profile args from the
// before-snapshot, restoring exactly the fields this patch touched.
func undoHintForProfile(before json.RawMessage, patch map[string]any) map[string]any {
	var prev map[string]any
	_ = json.Unmarshal(before, &prev)
	reverse := map[string]any{}
	for k := range patch {
		if v, ok := prev[k]; ok {
			reverse[k] = v
		}
	}
	return map[string]any{"tool": "settings_update_profile", "args": reverse}
}

// ── Tier A: model register / update / flags / default ──────────────────────────

type modelRegisterIn struct {
	ProviderCredentialID string         `json:"provider_credential_id" jsonschema:"an EXISTING provider credential to register the model under (UUID)"`
	ProviderModelName    string         `json:"provider_model_name" jsonschema:"the upstream provider's model name (e.g. gpt-4o, claude-3-5-sonnet)"`
	Alias                string         `json:"alias,omitempty" jsonschema:"a friendly name for the model"`
	ContextLength        *int           `json:"context_length,omitempty" jsonschema:"the model's context window (required for ollama/lm_studio)"`
	CapabilityFlags      map[string]any `json:"capability_flags,omitempty" jsonschema:"capability map, e.g. {\"chat\": true}"`
	Notes                string         `json:"notes,omitempty"`
}
type modelMutationOut struct {
	Model    map[string]any `json:"model,omitempty"`
	UndoHint map[string]any `json:"_meta_undo_hint,omitempty"`
}

func (s *Server) toolModelRegister(ctx context.Context, _ *mcp.CallToolRequest, in modelRegisterIn) (*mcp.CallToolResult, modelMutationOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, modelMutationOut{}, err
	}
	credID, err := uuid.Parse(in.ProviderCredentialID)
	if err != nil {
		return nil, modelMutationOut{}, errors.New("provider_credential_id must be a UUID")
	}
	// Ownership: the credential must belong to the caller AND be active. Resolve the
	// provider_kind through the same scope check (H13: a foreign/missing credential
	// collapses to "not accessible").
	var providerKind string
	err = s.pool.QueryRow(ctx, `
SELECT provider_kind FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2 AND status='active'`, credID, uid).Scan(&providerKind)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, modelMutationOut{}, errors.New("provider credential not accessible")
	}
	if err != nil {
		return nil, modelMutationOut{}, errors.New("failed to resolve provider credential")
	}
	if strings.TrimSpace(in.ProviderModelName) == "" {
		return nil, modelMutationOut{}, errors.New("provider_model_name is required")
	}
	if (providerKind == "ollama" || providerKind == "lm_studio") && (in.ContextLength == nil || *in.ContextLength <= 0) {
		return nil, modelMutationOut{}, errors.New("context_length is required for ollama/lm_studio")
	}
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)
	if in.CapabilityFlags == nil {
		flagsBytes = []byte("{}")
	}
	var newID uuid.UUID
	err = s.pool.QueryRow(ctx, `
INSERT INTO user_models(owner_user_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, capability_flags, notes)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
RETURNING user_model_id`,
		uid, credID, providerKind, in.ProviderModelName, in.ContextLength, nullableString(in.Alias), flagsBytes, in.Notes).Scan(&newID)
	if err != nil {
		return nil, modelMutationOut{}, errors.New("failed to register model")
	}
	m, _ := s.readUserModel(ctx, uid, newID)
	undo := map[string]any{"tool": "settings_model_delete", "args": map[string]any{"user_model_id": newID.String()}}
	return mcpResultWithUndo(undo), modelMutationOut{Model: m, UndoHint: undo}, nil
}

type modelUpdateIn struct {
	UserModelID     string         `json:"user_model_id" jsonschema:"the model to update (UUID)"`
	Alias           *string        `json:"alias,omitempty"`
	ContextLength   *int           `json:"context_length,omitempty"`
	CapabilityFlags map[string]any `json:"capability_flags,omitempty"`
	Notes           *string        `json:"notes,omitempty"`
}

func (s *Server) toolModelUpdate(ctx context.Context, _ *mcp.CallToolRequest, in modelUpdateIn) (*mcp.CallToolResult, modelMutationOut, error) {
	uid, id, err := s.guardModel(ctx, in.UserModelID)
	if err != nil {
		return nil, modelMutationOut{}, err
	}
	// Snapshot before for undo.
	before, _ := s.readUserModel(ctx, uid, id)
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)
	_, err = s.pool.Exec(ctx, `
UPDATE user_models
SET alias=COALESCE($3, alias),
    context_length=COALESCE($4, context_length),
    capability_flags=CASE WHEN $5::jsonb IS NULL THEN capability_flags ELSE $5 END,
    notes=COALESCE($6, notes),
    updated_at=now()
WHERE user_model_id=$1 AND owner_user_id=$2`,
		id, uid, in.Alias, in.ContextLength, nullJSON(flagsBytes, in.CapabilityFlags != nil), in.Notes)
	if err != nil {
		return nil, modelMutationOut{}, errors.New("failed to update model")
	}
	m, _ := s.readUserModel(ctx, uid, id)
	undo := map[string]any{"tool": "settings_model_update", "args": undoArgsForUpdate(in, before)}
	return mcpResultWithUndo(undo), modelMutationOut{Model: m, UndoHint: undo}, nil
}

// undoArgsForUpdate restores exactly the fields this update changed, from the
// before-snapshot.
func undoArgsForUpdate(in modelUpdateIn, before map[string]any) map[string]any {
	args := map[string]any{"user_model_id": in.UserModelID}
	if in.Alias != nil && before != nil {
		args["alias"] = before["alias"]
	}
	if in.ContextLength != nil && before != nil {
		args["context_length"] = before["context_length"]
	}
	if in.CapabilityFlags != nil && before != nil {
		args["capability_flags"] = before["capability_flags"]
	}
	if in.Notes != nil && before != nil {
		args["notes"] = before["notes"]
	}
	return args
}

type modelBoolIn struct {
	UserModelID string `json:"user_model_id" jsonschema:"the model to change (UUID)"`
	Value       bool   `json:"value" jsonschema:"the new flag value"`
}

func (s *Server) toolModelSetFavorite(ctx context.Context, _ *mcp.CallToolRequest, in modelBoolIn) (*mcp.CallToolResult, modelMutationOut, error) {
	return s.setModelBool(ctx, in, "is_favorite", "settings_model_set_favorite")
}

func (s *Server) toolModelSetActive(ctx context.Context, _ *mcp.CallToolRequest, in modelBoolIn) (*mcp.CallToolResult, modelMutationOut, error) {
	return s.setModelBool(ctx, in, "is_active", "settings_model_set_active")
}

func (s *Server) setModelBool(ctx context.Context, in modelBoolIn, field, toolName string) (*mcp.CallToolResult, modelMutationOut, error) {
	uid, id, err := s.guardModel(ctx, in.UserModelID)
	if err != nil {
		return nil, modelMutationOut{}, err
	}
	var prev bool
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`SELECT %s FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`, field), id, uid).Scan(&prev); err != nil {
		return nil, modelMutationOut{}, errors.New("model not accessible")
	}
	if _, err := s.pool.Exec(ctx, fmt.Sprintf(`UPDATE user_models SET %s=$3, updated_at=now() WHERE user_model_id=$1 AND owner_user_id=$2`, field), id, uid, in.Value); err != nil {
		return nil, modelMutationOut{}, errors.New("failed to update model")
	}
	m, _ := s.readUserModel(ctx, uid, id)
	undo := map[string]any{"tool": toolName, "args": map[string]any{"user_model_id": in.UserModelID, "value": prev}}
	return mcpResultWithUndo(undo), modelMutationOut{Model: m, UndoHint: undo}, nil
}

type modelSetDefaultIn struct {
	Capability  string  `json:"capability" jsonschema:"the capability (rerank or embedding)"`
	UserModelID *string `json:"user_model_id,omitempty" jsonschema:"the model to make default; omit/null to CLEAR the default"`
}

func (s *Server) toolModelSetDefault(ctx context.Context, _ *mcp.CallToolRequest, in modelSetDefaultIn) (*mcp.CallToolResult, modelMutationOut, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return nil, modelMutationOut{}, err
	}
	if !defaultModelCapabilities[in.Capability] {
		return nil, modelMutationOut{}, errors.New(
			"unsupported capability (want one of: rerank, embedding, chat, planner)")
	}
	// Snapshot the PREVIOUS default for undo.
	var prevDefault *string
	var prev uuid.UUID
	err = s.pool.QueryRow(ctx, `SELECT user_model_id FROM user_default_models WHERE owner_user_id=$1 AND capability=$2`, uid, in.Capability).Scan(&prev)
	if err == nil {
		ps := prev.String()
		prevDefault = &ps
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return nil, modelMutationOut{}, errors.New("failed to read current default")
	}

	if in.UserModelID == nil || *in.UserModelID == "" {
		if _, err := s.pool.Exec(ctx, `DELETE FROM user_default_models WHERE owner_user_id=$1 AND capability=$2`, uid, in.Capability); err != nil {
			return nil, modelMutationOut{}, errors.New("failed to clear default")
		}
	} else {
		modelID, perr := uuid.Parse(*in.UserModelID)
		if perr != nil {
			return nil, modelMutationOut{}, errors.New("user_model_id must be a UUID")
		}
		// The model must be the caller's, active, and carry the capability —
		// via the SAME shared rule as the HTTP route (planner→chat mapping +
		// undeclared-'{}'-is-chat parity; review-impl W5 #2).
		capQuery, capJSON, validateCap := defaultModelCapQuery(in.Capability)
		var exists int
		err = s.pool.QueryRow(ctx, capQuery,
			modelID, uid, capJSON, validateCap).Scan(&exists)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, modelMutationOut{}, errors.New("model not found, inactive, or lacks the capability")
		}
		if err != nil {
			return nil, modelMutationOut{}, errors.New("failed to validate model")
		}
		if _, err := s.pool.Exec(ctx, `
INSERT INTO user_default_models (owner_user_id, capability, user_model_id, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (owner_user_id, capability)
DO UPDATE SET user_model_id = EXCLUDED.user_model_id, updated_at = now()`,
			uid, in.Capability, modelID); err != nil {
			return nil, modelMutationOut{}, errors.New("failed to set default")
		}
	}
	undo := map[string]any{"tool": "settings_model_set_default", "args": map[string]any{"capability": in.Capability, "user_model_id": prevDefault}}
	return mcpResultWithUndo(undo), modelMutationOut{UndoHint: undo}, nil
}

// guardModel validates the caller, parses the model id, and runs the user-scope
// ownership guard. Returns (caller, modelID) on success.
func (s *Server) guardModel(ctx context.Context, modelIDStr string) (uuid.UUID, uuid.UUID, error) {
	uid, err := callerID(ctx)
	if err != nil {
		return uuid.Nil, uuid.Nil, err
	}
	id, err := uuid.Parse(modelIDStr)
	if err != nil {
		return uuid.Nil, uuid.Nil, errors.New("user_model_id must be a UUID")
	}
	if err := s.userModelGuard().Check(ctx, uid, id); err != nil {
		return uuid.Nil, uuid.Nil, uniformGuardError(err)
	}
	return uid, id, nil
}

// ── Tier W: model delete (mint confirm token; no write) ────────────────────────

type modelDeleteIn struct {
	UserModelID string `json:"user_model_id" jsonschema:"the model to delete (UUID)"`
}
type modelDeleteOut struct {
	ConfirmToken string `json:"confirm_token"`
	Descriptor   string `json:"descriptor"`
	Title        string `json:"title"`
	Domain       string `json:"domain"`
}

// toolModelDelete is Tier-W: it does NOT delete. It verifies ownership, then MINTS
// a confirm token (bound to user + model + the settings.model_delete descriptor +
// expiry) and returns {confirm_token, descriptor, title, domain}. The agent passes
// these to the confirm_action frontend tool; the human-confirmed
// POST /v1/settings/actions/confirm is the ONLY write path (INV-9).
func (s *Server) toolModelDelete(ctx context.Context, _ *mcp.CallToolRequest, in modelDeleteIn) (*mcp.CallToolResult, modelDeleteOut, error) {
	uid, id, err := s.guardModel(ctx, in.UserModelID)
	if err != nil {
		return nil, modelDeleteOut{}, err
	}
	// Render a friendly title from current state (alias/provider_model_name).
	var alias *string
	var providerModelName string
	_ = s.pool.QueryRow(ctx, `SELECT alias, provider_model_name FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`, id, uid).Scan(&alias, &providerModelName)
	label := providerModelName
	if alias != nil && *alias != "" {
		label = *alias
	}
	tok, err := lwmcp.MintConfirmToken(s.cfg.ConfirmTokenSigningSecret, uid, id, settingsConfirmDescriptor,
		map[string]any{"user_model_id": id.String()}, settingsConfirmTTL)
	if err != nil {
		return nil, modelDeleteOut{}, errors.New("failed to prepare confirmation")
	}
	return nil, modelDeleteOut{
		ConfirmToken: tok,
		Descriptor:   settingsConfirmDescriptor,
		Title:        fmt.Sprintf("Delete model %q", label),
		Domain:       "settings",
	}, nil
}

// ── helpers ────────────────────────────────────────────────────────────────────

// uniformGuardError maps the kit ownership sentinels to caller-visible messages:
// not-found / not-owner collapse to one "not accessible" (H13 — no existence
// oracle); an authority outage is distinct so the agent says "try again" (H10).
func uniformGuardError(err error) error {
	if errors.Is(err, lwmcp.ErrCheckUnavailable) {
		return errors.New("ownership check unavailable, try again")
	}
	return errors.New("not accessible")
}

// mcpResultWithUndo wraps an undo hint into the MCP result _meta so the consumer
// (S-CONSUMER) can surface the C-ACTIVITY Undo affordance. The undo hint is ALSO
// returned in the typed output so it survives JSON structured-content transport.
func mcpResultWithUndo(undo map[string]any) *mcp.CallToolResult {
	if undo == nil {
		return nil
	}
	return &mcp.CallToolResult{Meta: mcp.Meta{lwmcp.MetaKeyUndoHint: undo}}
}

// authProfileRequest calls auth-service's token-gated internal full-profile route
// on behalf of the envelope caller. method GET reads, PATCH updates (patch != nil).
// Returns the raw JSON profile body. This is the ONLY cross-service call S-SETTINGS
// makes — provider-registry never reads auth's `users` table directly.
func (s *Server) authProfileRequest(ctx context.Context, method string, userID uuid.UUID, patch map[string]any) (json.RawMessage, error) {
	base := strings.TrimRight(s.cfg.AuthServiceInternalURL, "/")
	if base == "" {
		return nil, errors.New("profile service not configured")
	}
	endpoint := base + "/internal/users/" + url.PathEscape(userID.String()) + "/full-profile"

	var bodyReader io.Reader
	if patch != nil {
		b, err := json.Marshal(patch)
		if err != nil {
			return nil, errors.New("failed to encode profile update")
		}
		bodyReader = strings.NewReader(string(b))
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, bodyReader)
	if err != nil {
		return nil, errors.New("failed to build profile request")
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	if patch != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, errors.New("profile service unavailable, try again")
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode == http.StatusNotFound {
		return nil, errors.New("profile not accessible")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, errors.New("profile request failed")
	}
	return json.RawMessage(body), nil
}
