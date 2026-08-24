package api

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T2 — book Sync MCP tools. Registered together via RegisterSyncTools so the sync
// stream owns its own file (the per-tier parallelism enabler — appends to mcpHandler
// without touching book_tools.go). The agent reconciles a book against the standards
// it adopted from: read the diff (R), then propose a per-row choice set the human
// confirms as a class-C action (§3b, §12.4).
//
// Gating: read diff = GrantView; apply = class C (confirm-token) — it overwrites
// adopted rows, so the LLM proposes and a human confirms via glossary_confirm_action.

// RegisterSyncTools adds the sync-tier tools to the user/book MCP server.
func (s *Server) RegisterSyncTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_book_sync_available",
		Description: "List the standard updates AVAILABLE for a book: for each genre/kind/attribute the " +
			"book adopted from System or your user-tier standards, whether the source has since changed " +
			"(an update is available) or been retired. Read this before proposing a sync. Returns each " +
			"row's current (mine) vs upstream (theirs) values so you can recommend per-row choices.",
		// R2 (2026-08-14) — DECLARED so a user's words can reach it. tool_list fired ONCE in
		// 30 live runs and tool_load never, so the answerability pre-filter is the only
		// dynamic path onto the wire; an undeclared tool cannot be pre-filtered in. These
		// are phrasings a PERSON types, not the feature's name.
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, []string{"are there ontology updates", "is my story bible out of date", "what standard updates are available"}),
	}, s.toolBookSyncAvailable)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_book_sync_apply",
		Description: "Propose APPLYING a set of per-row sync choices to a book (take_theirs = overwrite the " +
			"book row from its source; keep_mine = keep the book's value but stop prompting). High-impact: it " +
			"does NOT apply; it returns a confirm_token + a preview, which a human reviews (and may flip any " +
			"row) before confirming via glossary_confirm_action. Pass items from glossary_book_sync_available: " +
			"each {entity, id, choice}. id is the BOOK row id from the available list.",
		InputSchema: closedSetSchemaFor[syncApplyToolIn](map[string][]any{
			"items[].entity": enumLevels,
			"items[].choice": {"take_theirs", "keep_mine"},
		}),
		// Mints a grant confirm_token (no direct write) ⇒ Tier W.
		// R2 (2026-08-14) — DECLARED so a user's words can reach it. tool_list fired ONCE in
		// 30 live runs and tool_load never, so the answerability pre-filter is the only
		// dynamic path onto the wire; an undeclared tool cannot be pre-filtered in. These
		// are phrasings a PERSON types, not the feature's name.
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{"apply the standard updates", "take the upstream changes", "sync my ontology"}),
	}, s.toolBookSyncApply)
}

// ── sync_available (R) ────────────────────────────────────────────────────────

type syncAvailableToolIn struct {
	BookID string `json:"book_id,omitempty" jsonschema:"the book to diff against its standards (UUID)"`
}

func (s *Server) toolBookSyncAvailable(ctx context.Context, _ *mcp.CallToolRequest, in syncAvailableToolIn) (*mcp.CallToolResult, syncAvailableResp, error) {
	userID, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, syncAvailableResp{}, err
	}
	out := syncAvailableResp{BookID: bookID.String(), Updates: []syncUpdateItem{}}
	g, err := s.syncGenresAvailable(ctx, bookID, userID)
	if err != nil {
		return nil, syncAvailableResp{}, errors.New("genre diff failed")
	}
	out.Updates = append(out.Updates, g...)
	k, err := s.syncKindsAvailable(ctx, bookID, userID)
	if err != nil {
		return nil, syncAvailableResp{}, errors.New("kind diff failed")
	}
	out.Updates = append(out.Updates, k...)
	a, err := s.syncAttributesAvailable(ctx, bookID, userID)
	if err != nil {
		return nil, syncAvailableResp{}, errors.New("attribute diff failed")
	}
	out.Updates = append(out.Updates, a...)
	return nil, out, nil
}

// ── sync_apply (C) ────────────────────────────────────────────────────────────

type syncApplyItemToolIn struct {
	Entity string `json:"entity" jsonschema:"genre | kind | attribute"`
	ID     string `json:"id" jsonschema:"the BOOK row id from glossary_book_sync_available"`
	Choice string `json:"choice" jsonschema:"take_theirs | keep_mine"`
}

type syncApplyToolIn struct {
	BookID string                `json:"book_id,omitempty" jsonschema:"the book to sync (UUID)"`
	Items  []syncApplyItemToolIn `json:"items" jsonschema:"the per-row choices to apply"`
}

func (s *Server) toolBookSyncApply(ctx context.Context, req *mcp.CallToolRequest, in syncApplyToolIn) (*mcp.CallToolResult, any, error) {
	userID, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	if len(in.Items) == 0 {
		return nil, confirmCardOut{}, errors.New("items is required (read glossary_book_sync_available first)")
	}
	// Mint-time validation (§11 #8): reject a malformed proposal up front so the agent
	// never shows a card destined to 4xx. Confirm-time re-validation still runs in the
	// effect (rows whose source retired since are reported, not errored).
	items := make([]syncApplyItemReq, 0, len(in.Items))
	var takeN, keepN int
	for _, it := range in.Items {
		entity := strings.TrimSpace(it.Entity)
		choice := strings.TrimSpace(it.Choice)
		if entity != "genre" && entity != "kind" && entity != "attribute" {
			return nil, confirmCardOut{}, fmt.Errorf("invalid entity %q (genre|kind|attribute)", it.Entity)
		}
		if choice != "keep_mine" && choice != "take_theirs" {
			return nil, confirmCardOut{}, fmt.Errorf("invalid choice %q (take_theirs|keep_mine)", it.Choice)
		}
		if _, perr := uuid.Parse(strings.TrimSpace(it.ID)); perr != nil {
			return nil, confirmCardOut{}, fmt.Errorf("invalid id %q (use the id from glossary_book_sync_available)", it.ID)
		}
		if choice == "take_theirs" {
			takeN++
		} else {
			keepN++
		}
		items = append(items, syncApplyItemReq{Entity: entity, ID: strings.TrimSpace(it.ID), Choice: choice})
	}
	// 🔴 MINT-TIME VALIDATION STOPPED AT THE SHAPE OF AN ID. Measured 2026-08-24 over MCP, each
	// of these MINTED A CARD: an item id that exists nowhere, a book with ZERO available updates,
	// and book A's sync row applied against book B. Every row on this card decides whether the
	// author's own value is overwritten, so a card for rows that are not available updates asks
	// them to approve a change that cannot happen — approve-then-fail on a Tier-W write.
	//
	// The set to check against is the one the READER returns, computed here by the same three
	// functions glossary_book_sync_available runs. One membership test covers all three cases: an
	// unknown id, another book's id, and an id that is already up to date are all simply absent
	// from this book's available set. Same principle as the entity/choice/UUID checks above,
	// extended from the shape of an id to whether it names something to apply.
	//
	// A query failure FAILS THE PROPOSAL rather than skipping the check: this is the same pool
	// and the same service, so a failure here is a database failure, not a degraded dependency to
	// route around. (Contrast the liveness lookup below, which is best-effort because it only
	// decorates a card that is already valid.)
	avail := map[string]bool{}
	for _, fn := range []func(context.Context, uuid.UUID, uuid.UUID) ([]syncUpdateItem, error){
		s.syncGenresAvailable, s.syncKindsAvailable, s.syncAttributesAvailable,
	} {
		got, aerr := fn(ctx, bookID, userID)
		if aerr != nil {
			return nil, confirmCardOut{}, errors.New("could not read this book's available updates to validate the proposal")
		}
		for _, av := range got {
			avail[av.ID] = true
		}
	}
	for _, it := range items {
		if !avail[it.ID] {
			return nil, confirmCardOut{}, fmt.Errorf(
				"%s %s is not an available update for this book — read "+
					"glossary_book_sync_available first and use the ids it returns",
				it.Entity, it.ID)
		}
	}
	rows := []previewRow{
		{Label: "rows to update from source", Value: fmt.Sprint(takeN), Note: "take_theirs"},
		{Label: "rows to keep as-is", Value: fmt.Sprint(keepN), Note: "keep_mine (accept divergence)"},
	}
	params := syncApplyParams{Items: items}
	_, card, cerr := s.mintGrantActionCard(userID, bookID, descSyncApply, "Apply standard updates to this book", params, rows, true)
	// External MCP discoverability audit #11 — applySyncRow (book_sync_handler.go) only
	// affects a row whose recorded source is STILL LIVE (its UPDATE joins FROM the live
	// source row); a retired/purged source matches nothing regardless of take_theirs vs
	// keep_mine. So if EVERY proposed row's source has already retired, confirming this
	// card is guaranteed to apply zero rows. bookSyncSourceLiveByID is the SAME liveness
	// predicate previewSyncApply/applySyncRow use — best-effort here (a lookup failure
	// just skips the warning rather than failing an otherwise-valid proposal).
	if cerr == nil {
		if liveMap, lerr := s.bookSyncSourceLiveByID(ctx, bookID, userID); lerr == nil {
			liveCount := 0
			for _, it := range items {
				if liveMap[it.ID] {
					liveCount++
				}
			}
			if liveCount == 0 {
				card.Warning = fmt.Sprintf(
					"none of the %d proposed row(s) still have a live source — applying will change nothing", len(items))
			}
		}
	}
	return s.gateOrCard(ctx, req, descSyncApply, bookID, userID, params, card, cerr)
}
