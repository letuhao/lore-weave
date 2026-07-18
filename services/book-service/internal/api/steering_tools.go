package api

// S-BOOK — 28 AN-6 steering MCP tools. The per-book steering store (RAID C1,
// steering.go) has REST CRUD + a GUI panel + a chat-render path, but NO agent
// surface: the agent is steered by rules it can neither read, author, nor
// update. These three tools close that hole (the `.cursorrules` analogue + the
// S06 F4 "write that down" canon-persist lever).
//
// They are thin MCP ADAPTERS over the same store, caps, and grants steering.go
// owns — NOT a second engine. They reuse steering.go's constants
// (maxSteeringBodyChars/RowsPerBook/NameChars), validSteeringMode,
// steeringAutoModeNote, isUniqueViolation, and the steeringRow shape. The engine
// (steering.go) is untouched; the only new logic here is (a) an error-returning
// validator (steering.go's writes to an http.ResponseWriter, which an MCP
// handler has none of) and (b) the upsert-by-name discriminator.
//
// Tiers (28 AN-6): list = R (VIEW), set/delete = A (EDIT grant, same as REST) +
// a verified undo_hint. A steering row is small, visible in the shipped panel,
// and the inverse op is exact — reversibility determines autonomy (07S §5), so
// A not W. Identity is from the envelope (SEC-1); the by-name/by-id mutation
// gates on the ROW's own book (never a body book_id) — book_id IS the scope key
// on every query.

import (
	"context"
	"errors"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// steeringToolRow is the agent-facing projection (28 AN-6 list shape): the row
// minus book_id (implicit in the call) and author_user_id (an audit field the
// agent doesn't act on). Timestamps render RFC3339.
type steeringToolRow struct {
	ID            string  `json:"id"`
	Name          string  `json:"name"`
	Body          string  `json:"body"`
	InclusionMode string  `json:"inclusion_mode"`
	MatchPattern  *string `json:"match_pattern"`
	Enabled       bool    `json:"enabled"`
	UpdatedAt     string  `json:"updated_at"`
}

func steeringRowToTool(r steeringRow) steeringToolRow {
	return steeringToolRow{
		ID:            r.ID.String(),
		Name:          r.Name,
		Body:          r.Body,
		InclusionMode: r.InclusionMode,
		MatchPattern:  r.MatchPattern,
		Enabled:       r.Enabled,
		UpdatedAt:     r.UpdatedAt.Format(time.RFC3339),
	}
}

// steeringSetUndoArgs builds the argument template that reconstructs r via
// book_steering_set (the verified inverse of a replace, and of a delete). name
// is the upsert key, so a set with these args restores the prior body/mode/
// pattern/enabled under the same name.
func steeringSetUndoArgs(r steeringRow) map[string]any {
	args := map[string]any{
		"book_id":        r.BookID.String(),
		"name":           r.Name,
		"body":           r.Body,
		"inclusion_mode": r.InclusionMode,
		"enabled":        r.Enabled,
	}
	if r.MatchPattern != nil {
		args["match_pattern"] = *r.MatchPattern
	}
	return args
}

// steeringScanCols is the shared RETURNING/SELECT column list for a full row.
const steeringScanCols = `id, book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id, created_at, updated_at`

func scanSteeringRow(row pgx.Row, r *steeringRow) error {
	return row.Scan(&r.ID, &r.BookID, &r.Name, &r.Body, &r.InclusionMode, &r.MatchPattern, &r.Enabled, &r.AuthorUserID, &r.CreatedAt, &r.UpdatedAt)
}

// validateSteeringToolInput mirrors steering.go's validateSteeringInput but
// RETURNS the error (the HTTP validator writes to an http.ResponseWriter an MCP
// handler doesn't have). Reuses the engine's caps + validSteeringMode +
// steeringAutoModeNote so the two front doors can't drift. Char caps count runes
// (matches Postgres char_length) so CJK bodies aren't unfairly truncated.
func validateSteeringToolInput(name, body, mode, pattern string) (rName, rBody, rMode string, rPattern *string, err error) {
	rName = strings.TrimSpace(name)
	if rName == "" {
		return "", "", "", nil, errors.New("name is required")
	}
	if utf8.RuneCountInString(rName) > maxSteeringNameChars {
		return "", "", "", nil, errors.New("name exceeds 200 characters")
	}
	if strings.TrimSpace(body) == "" {
		return "", "", "", nil, errors.New("body is required")
	}
	if utf8.RuneCountInString(body) > maxSteeringBodyChars {
		return "", "", "", nil, errors.New("body exceeds 8000 characters (steering is injected into every matching turn — keep it tight)")
	}
	rBody = body
	rMode = "always"
	if mode != "" {
		rMode = mode
	}
	if !validSteeringMode(rMode) {
		return "", "", "", nil, errors.New("inclusion_mode must be one of always|scene_match|manual|auto (" + steeringAutoModeNote + ")")
	}
	if trimmed := strings.TrimSpace(pattern); trimmed != "" {
		rPattern = &trimmed
	}
	if rMode == "scene_match" && rPattern == nil {
		return "", "", "", nil, errors.New("scene_match requires a non-empty match_pattern")
	}
	return rName, rBody, rMode, rPattern, nil
}

// ── book_steering_list ─────────────────────────────────────────────────────────

type steeringListIn struct {
	BookID string `json:"book_id" jsonschema:"the book whose steering rules to list (UUID)"`
}
type steeringListOut struct {
	Rules []steeringToolRow `json:"rules"`
	Total int               `json:"total"`
}

func (s *Server) toolBookSteeringList(ctx context.Context, _ *mcp.CallToolRequest, in steeringListIn) (*mcp.CallToolResult, steeringListOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, steeringListOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, steeringListOut{}, errors.New("book_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, steeringListOut{}, mcpOwnershipError(err)
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, name, body, inclusion_mode, match_pattern, enabled, updated_at
FROM book_steering WHERE book_id=$1 ORDER BY created_at, id`, bookID)
	if err != nil {
		return nil, steeringListOut{}, errors.New("failed to list steering rules")
	}
	defer rows.Close()
	out := steeringListOut{Rules: []steeringToolRow{}}
	for rows.Next() {
		var r steeringToolRow
		var id uuid.UUID
		var updated time.Time
		if err := rows.Scan(&id, &r.Name, &r.Body, &r.InclusionMode, &r.MatchPattern, &r.Enabled, &updated); err != nil {
			return nil, steeringListOut{}, errors.New("failed to scan steering rule")
		}
		r.ID = id.String()
		r.UpdatedAt = updated.Format(time.RFC3339)
		out.Rules = append(out.Rules, r)
	}
	if err := rows.Err(); err != nil {
		return nil, steeringListOut{}, errors.New("failed to list steering rules")
	}
	out.Total = len(out.Rules)
	return nil, out, nil
}

// ── book_steering_set ──────────────────────────────────────────────────────────

type steeringSetIn struct {
	BookID        string `json:"book_id" jsonschema:"the book to author the steering rule on (UUID)"`
	Name          string `json:"name" jsonschema:"rule name — the upsert key (1..200 chars). Absent-in-book ⇒ create; present ⇒ full replace (PUT semantics)"`
	Body          string `json:"body" jsonschema:"the rule text, injected into every matching turn (1..8000 chars — keep it tight)"`
	InclusionMode string `json:"inclusion_mode,omitempty" jsonschema:"when the rule fires: always|scene_match|manual|auto (default always). 'auto' v1: triggered like manual (#name); model-pull is a follow-up"`
	MatchPattern  string `json:"match_pattern,omitempty" jsonschema:"case-insensitive substring over the active chapter/scene title — required (and only meaningful) when inclusion_mode=scene_match"`
	Enabled       *bool  `json:"enabled,omitempty" jsonschema:"whether the rule is active (default true)"`
}
type steeringSetOut struct {
	Row      steeringToolRow  `json:"row"`
	Replaced bool             `json:"replaced"`
	Prior    *steeringToolRow `json:"prior"`
}

func (s *Server) toolBookSteeringSet(ctx context.Context, _ *mcp.CallToolRequest, in steeringSetIn) (*mcp.CallToolResult, steeringSetOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, steeringSetOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, steeringSetOut{}, errors.New("book_id must be a UUID")
	}
	name, body, mode, pattern, verr := validateSteeringToolInput(in.Name, in.Body, in.InclusionMode, in.MatchPattern)
	if verr != nil {
		return nil, steeringSetOut{}, verr
	}
	enabled := true
	if in.Enabled != nil {
		enabled = *in.Enabled
	}
	// E0 book grant BEFORE the repo (tenancy law); EDIT to write, same as REST.
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, steeringSetOut{}, mcpOwnershipError(err)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, steeringSetOut{}, errors.New("failed to set steering rule")
	}
	defer tx.Rollback(ctx)

	// UNIQUE(book_id, name) is the CAT-1 discriminator: an existing name ⇒ full
	// replace, an absent one ⇒ create. Snapshot the prior row first (for the
	// `replaced`/`prior` result + the undo_hint).
	var prior steeringRow
	priorErr := scanSteeringRow(tx.QueryRow(ctx, `
SELECT `+steeringScanCols+` FROM book_steering WHERE book_id=$1 AND name=$2`, bookID, name), &prior)

	var newRow steeringRow
	replaced := false
	switch {
	case priorErr == nil:
		// Full replace (PUT semantics). author_user_id is preserved (the original
		// author), mirroring the REST PUT.
		if err := scanSteeringRow(tx.QueryRow(ctx, `
UPDATE book_steering SET body=$3, inclusion_mode=$4, match_pattern=$5, enabled=$6, updated_at=now()
WHERE book_id=$1 AND name=$2
RETURNING `+steeringScanCols, bookID, name, body, mode, pattern, enabled), &newRow); err != nil {
			return nil, steeringSetOut{}, errors.New("failed to update steering rule")
		}
		replaced = true
	case errors.Is(priorErr, pgx.ErrNoRows):
		// Create. Re-enforce the row cap (soft; COUNT-then-INSERT race is acceptable
		// for a human-authored resource, matching the REST create).
		var n int
		if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM book_steering WHERE book_id=$1`, bookID).Scan(&n); err != nil {
			return nil, steeringSetOut{}, errors.New("failed to check steering cap")
		}
		if n >= maxSteeringRowsPerBook {
			return nil, steeringSetOut{}, errors.New("steering limit reached (20 entries per book) — delete or merge a rule first")
		}
		insErr := scanSteeringRow(tx.QueryRow(ctx, `
INSERT INTO book_steering (book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id)
VALUES ($1,$2,$3,$4,$5,$6,$7)
RETURNING `+steeringScanCols, bookID, name, body, mode, pattern, enabled, userID), &newRow)
		if isUniqueViolation(insErr) {
			// A concurrent create won the race — the caller should re-read + retry.
			return nil, steeringSetOut{}, errors.New("a steering rule with this name was just created — re-read and retry")
		}
		if insErr != nil {
			return nil, steeringSetOut{}, errors.New("failed to create steering rule")
		}
	default:
		return nil, steeringSetOut{}, errors.New("failed to load steering rule")
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, steeringSetOut{}, errors.New("failed to set steering rule")
	}

	out := steeringSetOut{Row: steeringRowToTool(newRow), Replaced: replaced}
	var res *mcp.CallToolResult
	if replaced {
		priorTool := steeringRowToTool(prior)
		out.Prior = &priorTool
		// Undo of a replace = set back to the prior row.
		res = undoResult("book_steering_set", steeringSetUndoArgs(prior))
	} else {
		// Undo of a create = delete it.
		res = undoResult("book_steering_delete", map[string]any{"book_id": bookID.String(), "name": name})
	}
	return res, out, nil
}

// ── book_steering_delete ───────────────────────────────────────────────────────

type steeringDeleteIn struct {
	BookID string `json:"book_id" jsonschema:"the book the rule belongs to (UUID)"`
	Name   string `json:"name,omitempty" jsonschema:"the rule name to delete (the upsert key). Provide name or id."`
	ID     string `json:"id,omitempty" jsonschema:"the rule id to delete (alternative to name)"`
}
type steeringDeleteOut struct {
	Deleted steeringToolRow `json:"deleted"`
}

func (s *Server) toolBookSteeringDelete(ctx context.Context, _ *mcp.CallToolRequest, in steeringDeleteIn) (*mcp.CallToolResult, steeringDeleteOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, steeringDeleteOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, steeringDeleteOut{}, errors.New("book_id must be a UUID")
	}
	name := strings.TrimSpace(in.Name)
	var byID uuid.UUID
	hasID := false
	if strings.TrimSpace(in.ID) != "" {
		byID, err = uuid.Parse(in.ID)
		if err != nil {
			return nil, steeringDeleteOut{}, errors.New("id must be a UUID")
		}
		hasID = true
	}
	if !hasID && name == "" {
		return nil, steeringDeleteOut{}, errors.New("provide name or id to delete")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, steeringDeleteOut{}, mcpOwnershipError(err)
	}

	// DELETE ... RETURNING the row so we can hand back the deleted row + an undo
	// that restores it. Scoped by id/name AND book_id (tenancy — never cross-book).
	var deleted steeringRow
	var delErr error
	if hasID {
		delErr = scanSteeringRow(s.pool.QueryRow(ctx, `
DELETE FROM book_steering WHERE id=$1 AND book_id=$2 RETURNING `+steeringScanCols, byID, bookID), &deleted)
	} else {
		delErr = scanSteeringRow(s.pool.QueryRow(ctx, `
DELETE FROM book_steering WHERE name=$1 AND book_id=$2 RETURNING `+steeringScanCols, name, bookID), &deleted)
	}
	if errors.Is(delErr, pgx.ErrNoRows) {
		// Never a silent no-op (IN-6): an unknown name/id is an explicit error.
		return nil, steeringDeleteOut{}, errors.New("no steering rule found with that name/id on this book")
	}
	if delErr != nil {
		return nil, steeringDeleteOut{}, errors.New("failed to delete steering rule")
	}
	res := undoResult("book_steering_set", steeringSetUndoArgs(deleted))
	return res, steeringDeleteOut{Deleted: steeringRowToTool(deleted)}, nil
}
