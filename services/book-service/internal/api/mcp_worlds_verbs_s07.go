package api

// S-07 §2 — the missing world agent verbs. REST already had UPDATE (patchWorld) and
// DELETE (deleteWorld); the MCP layer registered only list/get/create/move, so an agent
// that created a mis-named world could not rename or clean it up (and world_create's own
// "reversible" claim was unbacked). These add the two verbs, owner-scoped like every world
// tool (no E0 sharing — worlds are single-owner), mirroring the REST handlers.
//
// world_delete carries ONE guard the naked REST route lacks: it REFUSES while the world
// still holds member books. `books.world_id` is ON DELETE SET NULL, so a REST delete of a
// populated world silently ORPHANS those books (world_id → NULL) — a footgun for an agent
// acting on a fuzzy instruction. Requiring the books be moved/removed first keeps the tool
// to its stated use (clean up a world you just mis-created) without a one-shot nuke. Sealed
// as D-S07-world-delete-guard.

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ── world_update ──────────────────────────────────────────────────────────────
type worldUpdateIn struct {
	WorldID     string  `json:"world_id" jsonschema:"the world to update (UUID; you must own it)"`
	Name        *string `json:"name,omitempty" jsonschema:"new name; omit to leave unchanged"`
	Description *string `json:"description,omitempty" jsonschema:"new one-line description; omit to leave unchanged (pass an empty string to clear it)"`
}
type worldUpdateOut struct {
	World worldToolDetail `json:"world"`
}

func (s *Server) toolWorldUpdate(ctx context.Context, _ *mcp.CallToolRequest, in worldUpdateIn) (*mcp.CallToolResult, worldUpdateOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldUpdateOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, worldUpdateOut{}, errors.New("world_id must be a UUID")
	}
	if in.Name == nil && in.Description == nil {
		return nil, worldUpdateOut{}, errors.New("provide name and/or description to update")
	}

	// Capture the prior values for the undo hint (owner-scoped; a foreign/missing world
	// yields ErrNoRows → uniform "world not found", no existence oracle).
	var priorName string
	var priorDesc *string
	if err := s.pool.QueryRow(ctx,
		`SELECT name, description FROM worlds WHERE id=$1 AND owner_user_id=$2`, worldID, ownerID,
	).Scan(&priorName, &priorDesc); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, worldUpdateOut{}, errors.New("world not found")
		}
		return nil, worldUpdateOut{}, errors.New("failed to resolve world")
	}

	setClauses := []string{"updated_at=now()"}
	args := []any{worldID, ownerID}
	idx := 3
	if in.Name != nil {
		name := strings.TrimSpace(*in.Name)
		if name == "" {
			return nil, worldUpdateOut{}, errors.New("name cannot be empty")
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", idx))
		args = append(args, name)
		idx++
	}
	if in.Description != nil {
		setClauses = append(setClauses, fmt.Sprintf("description=$%d", idx))
		args = append(args, nullableString(strings.TrimSpace(*in.Description)))
		idx++
	}
	query := fmt.Sprintf(`UPDATE worlds SET %s WHERE id=$1 AND owner_user_id=$2`, strings.Join(setClauses, ", "))
	tag, err := s.pool.Exec(ctx, query, args...)
	if err != nil {
		return nil, worldUpdateOut{}, errors.New("failed to update world")
	}
	if tag.RowsAffected() == 0 {
		return nil, worldUpdateOut{}, errors.New("world not found") // owner-scoped, no oracle
	}

	d, err := scanWorldDetail(s.pool.QueryRow(ctx, worldSelectSQL+`
WHERE w.id=$1 AND w.owner_user_id=$2`, worldID, ownerID))
	if err != nil {
		return nil, worldUpdateOut{}, errors.New("failed to load updated world")
	}
	// Undo hint: world_update back to the prior name + description.
	var priorDescArg any
	if priorDesc != nil {
		priorDescArg = *priorDesc
	} else {
		priorDescArg = "" // reverse clears it (empty → NULL on write)
	}
	res := undoResult("world_update", map[string]any{
		"world_id": worldID.String(), "name": priorName, "description": priorDescArg,
	})
	return res, worldUpdateOut{World: d}, nil
}

// ── world_delete ──────────────────────────────────────────────────────────────
type worldDeleteIn struct {
	WorldID string `json:"world_id" jsonschema:"the world to delete (UUID; you must own it). Hard delete — NOT reversible. Refused while it still contains member books."`
}
type worldDeleteOut struct {
	Deleted bool `json:"deleted"`
}

func (s *Server) toolWorldDelete(ctx context.Context, _ *mcp.CallToolRequest, in worldDeleteIn) (*mcp.CallToolResult, worldDeleteOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldDeleteOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, worldDeleteOut{}, errors.New("world_id must be a UUID")
	}

	// Guard (D-S07-world-delete-guard): refuse while non-bible member books remain — a
	// world delete SET-NULLs them (orphaning the user's books), which an agent must not do
	// implicitly. The count is owner-scoped, so a non-owner sees 0 and falls through to the
	// owner-scoped DELETE below → uniform "world not found" (no existence oracle).
	var memberBooks int
	if err := s.pool.QueryRow(ctx, `
SELECT count(*) FROM books
WHERE world_id=$1 AND owner_user_id=$2 AND is_bible=false AND lifecycle_state!='purge_pending'`,
		worldID, ownerID).Scan(&memberBooks); err != nil {
		return nil, worldDeleteOut{}, errors.New("failed to resolve world")
	}
	if memberBooks > 0 {
		return nil, worldDeleteOut{}, fmt.Errorf(
			"world still has %d member book(s) — move or delete them first (deleting the world would orphan them)",
			memberBooks)
	}

	tag, err := s.pool.Exec(ctx, `DELETE FROM worlds WHERE id=$1 AND owner_user_id=$2`, worldID, ownerID)
	if err != nil {
		return nil, worldDeleteOut{}, errors.New("failed to delete world")
	}
	if tag.RowsAffected() == 0 {
		return nil, worldDeleteOut{}, errors.New("world not found") // owner-scoped, no oracle
	}
	return nil, worldDeleteOut{Deleted: true}, nil
}
