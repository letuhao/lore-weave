package api

// Catalog-unification 2026-07-22, Part C — glossary_propose_curation.
//
// The four class-C entity-curation PROPOSE tools (propose_status_change /
// propose_restore_revision / propose_reassign_kind / propose_merge) were the exact same
// shape — "propose ONE curation action → mint a confirm card the human approves." A
// mid-tier model juggling four near-identical propose verbs mis-picks. This UNIFIES them
// behind ONE tool with a closed-set `op` enum (the same op-dispatch shape propose_batch
// already ships). Each op REUSES the SAME post-grant core the legacy tool uses (the
// curation*Core funcs below) — the legacy handlers in pipeline_propose_tools.go are now
// thin wrappers over these cores, so the mint/validation/gate logic has ONE home and can
// never diverge (spec §6). The write itself was already single-sourced through the
// descriptor + gateOrCard.
//
// Deliberately a SIBLING of propose_batch (not folded in): propose_batch is ontology-
// scoped (kinds/genres/attributes); mixing entity-curation ops would muddy both.

import (
	"context"
	"errors"
	"strings"

	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterCurationProposeTools adds glossary_propose_curation to the user/book /mcp server.
func (s *Server) RegisterCurationProposeTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_curation",
		Description: "Propose ONE entity-curation action — mints a confirm card a human approves (nothing " +
			"changes until confirmed; pass the confirm_token to glossary_confirm_action). Pick an `op`:\n" +
			"  • status_change — set entities' status (approve drafts, retire, reject). Needs: status " +
			"(active|inactive|draft|rejected) + entity_ids[]. Reversible.\n" +
			"  • restore_revision — restore an entity to a prior revision (see glossary_get_entity " +
			"include=revisions). Needs: entity_id + revision_id. DESTRUCTIVE (prunes-then-restores to the " +
			"snapshot); itself a new revision, so reversible.\n" +
			"  • reassign_kind — move an entity to a different kind (triage the unknown bucket — see " +
			"glossary_curation_list view=unknowns). Needs: entity_id + kind_code. DESTRUCTIVE (attribute " +
			"values with no counterpart in the new kind are dropped; the card previews which). Recoverable " +
			"via revision restore.\n" +
			"  • merge — merge duplicates (see glossary_curation_list view=merge_candidates). Needs: " +
			"winner_id + loser_ids[] (same kind as the winner). DESTRUCTIVE (losers soft-deleted, children " +
			"fold into the winner); journaled + reversible.\n" +
			"book_id is optional inside a book studio. Manage grant required.",
		InputSchema: closedSetSchemaFor[proposeCurationToolIn](map[string][]any{
			"op":     {"status_change", "restore_revision", "reassign_kind", "merge"},
			"status": {"active", "inactive", "draft", "rejected"},
		}),
		// Mints a grant confirm_token (no direct write) ⇒ Tier W. WithAmbientBook: book_id resolves
		// from X-Book-Id when omitted inside a studio.
		Meta: lwmcp.WithAmbientBook(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{
			"approve entity", "reject entity", "retire entity", "restore entity revision",
			"reassign entity kind", "merge duplicate entities", "triage the review inbox",
		})),
	}, s.toolProposeCuration)
}

// proposeCurationToolIn is a flat superset keyed by `op`; each op reads only its own fields
// (validated in the core). A flat shape beats a freeform `params` object here — a weak model
// can SEE which fields an op needs (named + described), not guess an opaque blob.
type proposeCurationToolIn struct {
	// book_id OPTIONAL (ambient_book) — omitted inside a book studio, resolves from the envelope.
	BookID string `json:"book_id,omitempty" jsonschema:"the book (UUID). Omit inside a book studio — the current book is used."`
	Op     string `json:"op" jsonschema:"which curation action: status_change | restore_revision | reassign_kind | merge"`
	// op=status_change
	Status    string   `json:"status,omitempty" jsonschema:"for status_change — the new status: active | inactive | draft | rejected"`
	EntityIDs []string `json:"entity_ids,omitempty" jsonschema:"for status_change — the entities to change (UUIDs)"`
	// op=restore_revision | reassign_kind
	EntityID   string `json:"entity_id,omitempty" jsonschema:"for restore_revision or reassign_kind — the entity (UUID)"`
	RevisionID string `json:"revision_id,omitempty" jsonschema:"for restore_revision — the revision to restore to (UUID; see glossary_get_entity include revisions)"`
	KindCode   string `json:"kind_code,omitempty" jsonschema:"for reassign_kind — the target kind's code (see glossary_book_ontology_read)"`
	// op=merge
	WinnerID string   `json:"winner_id,omitempty" jsonschema:"for merge — the entity to KEEP (UUID)"`
	LoserIDs []string `json:"loser_ids,omitempty" jsonschema:"for merge — the entities to merge away (UUIDs; same kind as the winner)"`
}

// coalesceCurationEntityRef reconciles the singular/plural entity reference the FLAT SUPERSET
// makes it possible to confuse. It is pure so it can be tested without a Server or a database.
//
// 🔴 MEASURED, and it is this tool's entire genuine-failure population. Of 70 recorded calls,
// 42 are input_required suspensions (already typed `deferred` — not failures at all) and 26,
// across 15 sessions, sent `entity_id` — ONE syntactically valid UUID — alongside
// op=status_change, which reads only `entity_ids`. The schema ACCEPTS `entity_id`: it is a
// declared field OF THIS TOOL. Dispatch then silently drops it, and the core replies
// "at least one valid entity_id is required" — naming the exact field the caller DID send.
//
// A clearer sentence is NOT the fix. Three separate defects in this runtime shipped a correct,
// complete, actionable message and failed anyway (101 placeholder ids, 88 unknown kinds, 266
// missing arguments). The caller is not confused about intent; the DISPATCH is what narrows a
// pair of fields that mean the same thing, so the repair belongs where the narrowing happens.
//
// The reverse arm — a plural for a singular op — has ZERO measured occurrences and is written
// anyway because it is the same defect wearing the other shoe. It is gated to EXACTLY ONE
// element: a multi-element array for restore_revision/reassign_kind has no single coherent
// reading, and must keep refusing rather than pick one.
//
// Nothing is disguised (a repair that emits parseable-but-wrong output would need a
// post-condition): every op here MINTS A CONFIRM CARD whose preview states the entity count,
// and a human approves it before anything is written. The coalesced reading is shown before it
// can act.
func coalesceCurationEntityRef(in proposeCurationToolIn) proposeCurationToolIn {
	singular := strings.TrimSpace(in.EntityID)
	plural := make([]string, 0, len(in.EntityIDs))
	for _, raw := range in.EntityIDs {
		if v := strings.TrimSpace(raw); v != "" {
			plural = append(plural, v)
		}
	}
	switch strings.TrimSpace(in.Op) {
	case "status_change":
		if len(plural) == 0 && singular != "" {
			in.EntityIDs = []string{singular}
		}
	case "restore_revision", "reassign_kind":
		if singular == "" && len(plural) == 1 {
			in.EntityID = plural[0]
		}
	}
	return in
}

func (s *Server) toolProposeCuration(ctx context.Context, req *mcp.CallToolRequest, in proposeCurationToolIn) (*mcp.CallToolResult, any, error) {
	// Ambient book (studio context binding) + the uniform Manage gate all four ops require —
	// resolved ONCE here, then dispatched to the op's shared core.
	userID, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	in = coalesceCurationEntityRef(in)
	switch strings.TrimSpace(in.Op) {
	case "status_change":
		return s.curationStatusChangeCore(ctx, req, userID, bookID, in.Status, in.EntityIDs)
	case "restore_revision":
		return s.curationRestoreRevisionCore(ctx, req, userID, bookID, in.EntityID, in.RevisionID)
	case "reassign_kind":
		return s.curationReassignKindCore(ctx, req, userID, bookID, in.EntityID, in.KindCode)
	case "merge":
		return s.curationMergeCore(ctx, req, userID, bookID, in.WinnerID, in.LoserIDs)
	default:
		return nil, confirmCardOut{}, errors.New("op must be status_change, restore_revision, reassign_kind, or merge")
	}
}
