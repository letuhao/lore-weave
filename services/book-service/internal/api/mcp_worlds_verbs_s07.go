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
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"

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
	// #319: the prior values come from the UPDATE itself, via a self-join whose FROM side reads
	// the statement's snapshot and so cannot see this write. They used to come from a SELECT
	// issued just before it, which left a window: a concurrent rename landing in between made the
	// emitted undo_hint report a value that was no longer the prior one, so replaying the undo
	// would set the world to a name it never had at that moment and silently revert the other
	// edit to a third value. Worlds are single-owner, so that means the same user in two sessions
	// rather than two users — narrow, but this was the last tool still doing read-then-write, and
	// it is the one whose undo shape all five map tools were modelled on.
	//
	// The SET list is only parameters and now(), so nothing here is ambiguous across the two
	// aliases — the trap #315 hit is absent by construction, not by luck.
	query := fmt.Sprintf(
		`UPDATE worlds w SET %s FROM worlds old
		 WHERE w.id=old.id AND w.id=$1 AND w.owner_user_id=$2
		 RETURNING old.name, old.description`,
		strings.Join(setClauses, ", "))
	var priorName string
	var priorDesc *string
	err = s.pool.QueryRow(ctx, query, args...).Scan(&priorName, &priorDesc)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, worldUpdateOut{}, errNoSuchWorld // owner-scoped, no oracle
	}
	if err != nil {
		return nil, worldUpdateOut{}, errors.New("failed to update world")
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
	WorldID string `json:"world_id" jsonschema:"the world to delete (UUID; you must own it). NOT a name — if you have the world's NAME, call world_list first and match it to get the id. Hard delete — NOT reversible. Refused while it still contains member books."`
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
	//
	// `trashed` is excluded alongside `purge_pending` (#308). It counted before, which made the
	// refusal unsatisfiable: `delete_book` moves a book to `trashed`, so following the message's
	// own "delete them first" left the count unchanged, and at the time `world_move_book` required
	// a UUID world_id — there was no detach, so "move them out" only relocated the block to the
	// next world. (#318 has since added clear_world, so that half of the message now works too.)
	// The single state that cleared it was `purge_pending`, reachable only through
	// `purge_book` — an irreversible permanent destroy. A guard whose stated purpose is to keep
	// the user's books from being discarded must not have "destroy them forever" as its only
	// exit. A book the user has already thrown away is not one the agent is discarding on their
	// behalf; SET NULL leaves it intact in the trash, which is the "your own books survive"
	// behaviour the purge helper below describes.
	var memberBooks int
	if err := s.pool.QueryRow(ctx, `
SELECT count(*) FROM books
WHERE world_id=$1 AND owner_user_id=$2 AND is_bible=false
  AND lifecycle_state NOT IN ('purge_pending','trashed')`,
		worldID, ownerID).Scan(&memberBooks); err != nil {
		return nil, worldDeleteOut{}, errors.New("failed to resolve world")
	}
	if memberBooks > 0 {
		return nil, worldDeleteOut{}, fmt.Errorf(
			"world still has %d member book(s) — move or delete them first (deleting the world would orphan them)",
			memberBooks)
	}

	deleted, err := s.deleteWorldWithBiblePurge(ctx, worldID, ownerID)
	if err != nil {
		return nil, worldDeleteOut{}, errors.New("failed to delete world")
	}
	if !deleted {
		return nil, worldDeleteOut{}, errNoSuchWorld // owner-scoped, no oracle
	}
	return nil, worldDeleteOut{Deleted: true}, nil
}

// deleteWorldWithBiblePurge deletes a world AND routes its hidden bible book (+ that book's
// chapters) through the standard `purge_pending` lifecycle — atomically, owner-scoped. Shared
// by the MCP world_delete tool and the REST deleteWorld handler so both behave identically.
//
// Why not just `DELETE FROM worlds`? `books.world_id` is ON DELETE SET NULL, so a bare world
// delete leaves the bible as an ACTIVE, world-less hidden book that NO purge sweeper collects
// (it's `lifecycle_state='active'`) — a slow leak, and its KG/glossary anchors are stranded. A
// normal book delete instead flips the book + chapters to `purge_pending` (mcp_actions.go), so
// the sweeper + downstream cleanup handle them. We route the bible the same way. Member books
// (non-bible) are intentionally NOT purged — the world FK SET-NULLs them back to standalone,
// which is the intended "your own books survive" behaviour (and the MCP tool already refused
// the delete if any exist). Returns false when no world row matched (not found / not owned) —
// the whole tx rolls back, so a miss purges nothing.
func (s *Server) deleteWorldWithBiblePurge(ctx context.Context, worldID, ownerID uuid.UUID) (bool, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	// The bible book's chapters first, then the book — the same purge_pending transition a
	// normal delete uses. Owner-scoped; a non-owned world matches nothing here.
	if _, err := tx.Exec(ctx, `
UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now()
WHERE lifecycle_state!='purge_pending'
  AND book_id IN (SELECT id FROM books WHERE world_id=$1 AND owner_user_id=$2 AND is_bible=true)`,
		worldID, ownerID); err != nil {
		return false, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE books SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now()
WHERE world_id=$1 AND owner_user_id=$2 AND is_bible=true AND lifecycle_state!='purge_pending'`,
		worldID, ownerID); err != nil {
		return false, err
	}
	// The world's maps go with it via world_maps.world_id ON DELETE CASCADE — in the DATABASE.
	// Their base images do not (#311). world_map_delete removes a map's blob in application code,
	// and a cascade never runs that code, so every map image in a deleted world was orphaned in
	// storage permanently. This is not the failed-RemoveObject edge case #310 covered: no removal
	// was even attempted. It is the mechanism behind the orphans measured there — all 3 map images
	// in the bucket belonged to maps that no longer existed. Collect the keys while the rows still
	// exist; the removal happens after the commit.
	var imageKeys []string
	rows, err := tx.Query(ctx, `
SELECT image_object_key FROM world_maps
WHERE world_id=$1 AND owner_user_id=$2 AND image_object_key IS NOT NULL AND image_object_key<>''`,
		worldID, ownerID)
	if err != nil {
		return false, err
	}
	for rows.Next() {
		var k string
		if err := rows.Scan(&k); err != nil {
			rows.Close()
			return false, err
		}
		imageKeys = append(imageKeys, k)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return false, err
	}

	tag, err := tx.Exec(ctx, `DELETE FROM worlds WHERE id=$1 AND owner_user_id=$2`, worldID, ownerID)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, nil // not found / not owned → rollback (nothing purged)
	}
	if err := tx.Commit(ctx); err != nil {
		return false, err
	}

	// After the commit only: the rows are gone for good, so a storage failure must not fail the
	// delete — but it is logged with the key, never discarded (#310).
	if s.minio != nil {
		for _, k := range imageKeys {
			if err := s.minio.RemoveObject(ctx, mediaBucket, k, minio.RemoveObjectOptions{}); err != nil {
				slog.WarnContext(ctx, "world delete: orphaned map base image (world deleted, blob remains)",
					"world_id", worldID.String(), "object_key", k, "error", err)
			}
		}
	}
	return true, nil
}
