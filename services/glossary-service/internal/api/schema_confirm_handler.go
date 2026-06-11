package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Tier-S (P4) — propose MCP tools (mint a confirm token, NO write) + the
// token-gated /v1 confirm endpoint (the ONLY schema-create path). See
// schema_confirm_token.go for the un-bypassability argument (no MCP create route).

// ── propose tools (gateway-routed; mint token only) ──────────────────────────

type proposeKindToolIn struct {
	BookID      string   `json:"book_id" jsonschema:"the book whose schema to extend (UUID; ownership-checked)"`
	Code        string   `json:"code" jsonschema:"machine code for the kind, e.g. power_system"`
	Name        string   `json:"name" jsonschema:"display name, e.g. Power System"`
	Description string   `json:"description,omitempty" jsonschema:"optional description"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	GenreTags   []string `json:"genre_tags,omitempty"`
}

type proposeAttrToolIn struct {
	BookID      string   `json:"book_id" jsonschema:"the book whose schema to extend (UUID; ownership-checked)"`
	KindCode    string   `json:"kind_code" jsonschema:"the kind to add the attribute to (code — see glossary_list_kinds)"`
	Code        string   `json:"code" jsonschema:"machine code for the attribute, e.g. cultivation_realm"`
	Name        string   `json:"name" jsonschema:"display name"`
	FieldType   string   `json:"field_type,omitempty" jsonschema:"text|textarea|select|number|date|tags|url|boolean (default text)"`
	IsRequired  bool     `json:"is_required,omitempty"`
	Options     []string `json:"options,omitempty" jsonschema:"options for a select field"`
	Description string   `json:"description,omitempty"`
}

// proposeSchemaToolOut is the propose result fed to the LLM: a confirm token to
// hand to glossary_confirm_schema, plus a human-readable preview for the card.
type proposeSchemaToolOut struct {
	ConfirmToken string `json:"confirm_token"`
	ExpiresAt    string `json:"expires_at"`
	Preview      string `json:"preview"`
	// Op + a short label echo back so the confirm card can render without re-deriving.
	Op string `json:"op"`
}

func (s *Server) toolProposeNewKind(ctx context.Context, _ *mcp.CallToolRequest, in proposeKindToolIn) (*mcp.CallToolResult, proposeSchemaToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, proposeSchemaToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, proposeSchemaToolOut{}, errors.New("book_id must be a UUID")
	}
	code := strings.TrimSpace(in.Code)
	name := strings.TrimSpace(in.Name)
	if code == "" || name == "" {
		return nil, proposeSchemaToolOut{}, errors.New("code and name are required")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, proposeSchemaToolOut{}, uniformOwnershipError(err)
	}
	var desc *string
	if d := strings.TrimSpace(in.Description); d != "" {
		desc = &d
	}
	params := kindCreateParams{Code: code, Name: name, Description: desc, Icon: in.Icon, Color: in.Color, GenreTags: in.GenreTags}
	return s.mintSchemaProposal(userID, bookID, schemaOpKind, params,
		fmt.Sprintf("Create kind %q (code: %s)", name, code))
}

func (s *Server) toolProposeNewAttribute(ctx context.Context, _ *mcp.CallToolRequest, in proposeAttrToolIn) (*mcp.CallToolResult, proposeSchemaToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, proposeSchemaToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, proposeSchemaToolOut{}, errors.New("book_id must be a UUID")
	}
	code := strings.TrimSpace(in.Code)
	name := strings.TrimSpace(in.Name)
	kindCode := strings.TrimSpace(in.KindCode)
	if code == "" || name == "" || kindCode == "" {
		return nil, proposeSchemaToolOut{}, errors.New("kind_code, code and name are required")
	}
	if in.FieldType != "" && !isValidFieldType(in.FieldType) {
		return nil, proposeSchemaToolOut{}, errors.New("invalid field_type: " + in.FieldType +
			" (text|textarea|select|number|date|tags|url|boolean)")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, proposeSchemaToolOut{}, uniformOwnershipError(err)
	}
	kindMap, err := s.loadKindMap(ctx)
	if err != nil {
		return nil, proposeSchemaToolOut{}, errors.New("failed to resolve kinds")
	}
	kindID, ok := kindMap[kindCode]
	if !ok {
		return nil, proposeSchemaToolOut{}, errors.New("unknown kind: " + kindCode)
	}
	var desc *string
	if d := strings.TrimSpace(in.Description); d != "" {
		desc = &d
	}
	params := attrCreateParams{
		KindID: kindID.String(), Code: code, Name: name, Description: desc,
		FieldType: in.FieldType, IsRequired: in.IsRequired, Options: in.Options,
	}
	return s.mintSchemaProposal(userID, bookID, schemaOpAttribute, params,
		fmt.Sprintf("Add attribute %q (code: %s) to kind %q", name, code, kindCode))
}

// mintSchemaProposal serializes the create params, mints the confirm token, and
// returns the propose result. An empty token means SCHEMA secret/JWT is missing
// (fail closed — no proposal can proceed).
func (s *Server) mintSchemaProposal(userID, bookID uuid.UUID, op string, params any, preview string) (*mcp.CallToolResult, proposeSchemaToolOut, error) {
	raw, err := json.Marshal(params)
	if err != nil {
		return nil, proposeSchemaToolOut{}, errors.New("failed to encode proposal")
	}
	now := time.Now()
	token := mintSchemaToken(s.cfg.JWTSecret, userID, bookID, op, raw, now)
	if token == "" {
		return nil, proposeSchemaToolOut{}, errors.New("schema confirmation is unavailable")
	}
	return nil, proposeSchemaToolOut{
		ConfirmToken: token,
		ExpiresAt:    now.Add(schemaTokenTTL).UTC().Format(time.RFC3339),
		Preview:      preview,
		Op:           op,
	}, nil
}

// ── confirm endpoint (JWT-only; the single schema-create path) ───────────────

// confirmSchema handles POST /v1/glossary/schema/confirm — the token-gated Tier-S
// create. Reachable only with the user's JWT (browser), so the gateway/MCP path
// (mint-only) can never reach it. Validates the token, re-checks ownership, then
// runs the create via the shared core.
func (s *Server) confirmSchema(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var body struct {
		ConfirmToken string `json:"confirm_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.ConfirmToken) == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "confirm_token is required")
		return
	}

	claims, err := verifySchemaToken(s.cfg.JWTSecret, body.ConfirmToken, time.Now())
	if errors.Is(err, ErrSchemaTokenExpired) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_SCHEMA_TOKEN", "confirmation expired — propose again")
		return
	}
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_SCHEMA_TOKEN", "invalid confirmation")
		return
	}
	// The token is bound to the user who proposed it — a different signed-in user
	// cannot redeem it even if they obtain the string.
	if claims.UserID != userID {
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "confirmation not valid for this user")
		return
	}
	// Defense-in-depth: re-check the manage grant at confirm time (the grant may
	// have changed since propose). requireGrant writes the error response on failure.
	if !s.requireGrant(w, r.Context(), claims.BookID, userID, grantclient.GrantManage) {
		return
	}

	switch claims.Op {
	case schemaOpKind:
		var p kindCreateParams
		if err := json.Unmarshal(claims.Params, &p); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
			return
		}
		k, err := s.createKindFromParams(r.Context(), p)
		if err != nil {
			if isUniqueViolation(err) {
				writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "kind code already exists")
				return
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create kind")
			return
		}
		writeJSON(w, http.StatusCreated, k)
	case schemaOpAttribute:
		var p attrCreateParams
		if err := json.Unmarshal(claims.Params, &p); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
			return
		}
		a, err := s.createAttrDefFromParams(r.Context(), p)
		if err != nil {
			if isUniqueViolation(err) {
				writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "attribute code already exists for this kind")
				return
			}
			if isForeignKeyViolation(err) {
				// The kind was deleted between propose and confirm — clean 422, not 500.
				writeError(w, http.StatusUnprocessableEntity, "GLOSS_SCHEMA_TOKEN", "the target kind no longer exists — propose again")
				return
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create attribute")
			return
		}
		writeJSON(w, http.StatusCreated, a)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_SCHEMA_TOKEN", "unknown schema operation")
	}
}
