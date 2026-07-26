package api

// Unified manuscript-structure MCP tools (docs/specs/2026-07-22-manuscript-structure-tool.md).
//
//	book_structure_read = the manuscript GRAPH view. L1 (no part_id): the parts skeleton
//	  (parts[{part_id,title,sort_order,chapter_count}] + unassigned_count) — reference-first, the whole
//	  tree in one read. L2 (part_id, or "unassigned"): that group's chapter refs, paged, with the
//	  is_complete + guidance stop-signal. Reuses buildBookStructure (chapter conservation) for L1.
//	book_structure_edit = ONE write over the structure ops an agent needs: create_part / rename_part /
//	  reorder_parts (parts, via composition's NEW internal routes — the MCP path has no user bearer) +
//	  home_chapter / reorder_chapters (chapters, delegating to the existing engines). Closed `op` set
//	  (switch-default = a clean refusal, never a 5xx — IN-2), per-op Undo. Destructive part-archive is the
//	  separate visibility:legacy book_structure_part_archive (CAT-2 destructive split).

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// ── composition internal part-write helpers (mirror fetchStructurePartsInternal) ─────────────────────
// The public part routes (arc.py) are bearer-gated; the agent MCP path has only X-Internal-Token + the
// acting user_id. These POST/PATCH the NEW /internal/composition/**/parts routes. Each returns the HTTP
// status (0 = transport failure) so the caller distinguishes "composition down, retry" (0/503) from
// "not accessible" (404) from "bad reorder set" (409).

type partWriteResult struct {
	PartID    string `json:"part_id"`
	Title     string `json:"title"`
	SortOrder int    `json:"sort_order"`
}

func decodePartWrite(r io.Reader) *partWriteResult {
	var o partWriteResult
	if err := json.NewDecoder(r).Decode(&o); err != nil {
		return nil
	}
	return &o
}

func (s *Server) compositionInternalBase() (string, bool) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || s.cfg.InternalServiceToken == "" {
		return "", false
	}
	return base, true
}

func (s *Server) doInternalWrite(ctx context.Context, method, url string, body []byte) (*http.Response, int) {
	req, err := http.NewRequestWithContext(ctx, method, url, bytes.NewReader(body))
	if err != nil {
		return nil, 0
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, 0
	}
	return resp, resp.StatusCode
}

func (s *Server) createPartInternal(ctx context.Context, bookID, userID uuid.UUID, title string) (*partWriteResult, int) {
	base, ok := s.compositionInternalBase()
	if !ok {
		return nil, 0
	}
	body, _ := json.Marshal(map[string]string{"title": title})
	url := base + "/internal/composition/books/" + bookID.String() + "/parts?caller_user_id=" + userID.String()
	resp, status := s.doInternalWrite(ctx, http.MethodPost, url, body)
	if resp == nil {
		return nil, 0
	}
	defer resp.Body.Close()
	if status != http.StatusCreated {
		return nil, status
	}
	return decodePartWrite(resp.Body), status
}

func (s *Server) renamePartInternal(ctx context.Context, partID, userID uuid.UUID, title string) (*partWriteResult, int) {
	base, ok := s.compositionInternalBase()
	if !ok {
		return nil, 0
	}
	body, _ := json.Marshal(map[string]string{"title": title})
	url := base + "/internal/composition/parts/" + partID.String() + "?caller_user_id=" + userID.String()
	resp, status := s.doInternalWrite(ctx, http.MethodPatch, url, body)
	if resp == nil {
		return nil, 0
	}
	defer resp.Body.Close()
	if status != http.StatusOK {
		return nil, status
	}
	return decodePartWrite(resp.Body), status
}

func (s *Server) reorderPartsInternal(ctx context.Context, bookID, userID uuid.UUID, orderedIDs []uuid.UUID) ([]partWriteResult, int) {
	base, ok := s.compositionInternalBase()
	if !ok {
		return nil, 0
	}
	ids := make([]string, len(orderedIDs))
	for i, id := range orderedIDs {
		ids[i] = id.String()
	}
	body, _ := json.Marshal(map[string]any{"ordered_ids": ids})
	url := base + "/internal/composition/books/" + bookID.String() + "/parts/reorder?caller_user_id=" + userID.String()
	resp, status := s.doInternalWrite(ctx, http.MethodPost, url, body)
	if resp == nil {
		return nil, 0
	}
	defer resp.Body.Close()
	if status != http.StatusOK {
		return nil, status
	}
	var out struct {
		Items []partWriteResult `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, status
	}
	return out.Items, status
}

func (s *Server) archivePartInternal(ctx context.Context, partID, userID uuid.UUID) int {
	base, ok := s.compositionInternalBase()
	if !ok {
		return 0
	}
	url := base + "/internal/composition/parts/" + partID.String() + "?caller_user_id=" + userID.String()
	resp, status := s.doInternalWrite(ctx, http.MethodDelete, url, nil)
	if resp == nil {
		return 0
	}
	defer resp.Body.Close()
	return status
}

// compWriteErr maps a composition internal-write status to the uniform MCP error surface (no owner oracle).
func compWriteErr(status int, action string) error {
	switch status {
	case 0, http.StatusServiceUnavailable:
		return fmt.Errorf("could not %s — composition is unavailable; try again shortly", action)
	case http.StatusNotFound:
		return errBookNotAccessible
	case http.StatusConflict:
		return errors.New("the part order must be EXACTLY the book's active parts, each listed once")
	default:
		return fmt.Errorf("failed to %s", action)
	}
}

// ── book_structure_read ──────────────────────────────────────────────────────────────────────────

type bookStructureReadIn struct {
	// book_id is OPTIONAL in the schema (ambient_book): on a book-bound studio surface it resolves from
	// the envelope (X-Book-Id) when omitted; the handler (ResolveBookScope) fail-closes if neither an arg
	// nor an ambient book is present, so an external caller still effectively needs it. Do NOT re-mark it
	// `required` — the SDK would then reject an omitted id before the envelope resolution can run.
	BookID string `json:"book_id,omitempty" jsonschema:"the book (UUID). Omit inside a book studio — the current book is used."`
	PartID string `json:"part_id,omitempty" jsonschema:"omit for the parts overview (L1); pass a part UUID to list that part's chapters, or the literal \"unassigned\" for chapters in no part (L2)"`
	Offset int    `json:"offset,omitempty" jsonschema:"L2 paging: chapter index to start at (default 0)"`
	Limit  int    `json:"limit,omitempty" jsonschema:"L2 paging: chapters to return (default 50, max 100)"`
}

type structurePartRef struct {
	PartID       string `json:"part_id"`
	Title        string `json:"title"`
	SortOrder    int    `json:"sort_order"`
	ChapterCount int    `json:"chapter_count"`
}

type structureChapterRef struct {
	ChapterID string `json:"chapter_id"`
	Title     string `json:"title"`
	SortOrder int    `json:"sort_order"`
}

type bookStructureReadOut struct {
	View            string                `json:"view"` // "parts" (L1) | "chapters" (L2)
	Parts           []structurePartRef    `json:"parts,omitempty"`
	UnassignedCount *int                  `json:"unassigned_count,omitempty"`
	PartID          string                `json:"part_id,omitempty"`
	Chapters        []structureChapterRef `json:"chapters,omitempty"`
	Page            *pageEnvelope         `json:"page,omitempty"`
	ScopeSource     string                `json:"scope_source,omitempty"` // "arg" | "envelope" — which book this call resolved (SET transparency)
	Guidance        string                `json:"guidance"`
}

func (s *Server) toolBookStructureRead(ctx context.Context, _ *mcp.CallToolRequest, in bookStructureReadIn) (*mcp.CallToolResult, bookStructureReadOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookStructureReadOut{}, errMissingIdentity
	}
	// Ambient scope (spec 2026-07-22): on a book-bound surface book_id resolves from the envelope
	// when the model omits it. The resolved book is grant-checked below EXACTLY like an explicit arg.
	scope, sok := lwmcp.ResolveBookScope(ctx, in.BookID)
	if !sok {
		return nil, bookStructureReadOut{}, errors.New("book_id is required (a UUID)")
	}
	bookID := scope.BookID
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantView); err != nil {
		return nil, bookStructureReadOut{}, mcpOwnershipError(err)
	}

	parts, reachable := s.fetchStructurePartsInternal(ctx, bookID.String(), userID.String())
	if !reachable {
		return nil, bookStructureReadOut{}, errors.New("could not read the manuscript structure — composition is unavailable; try again shortly")
	}
	activeIDs := make([]uuid.UUID, 0, len(parts))
	for _, p := range parts {
		if !p.Active {
			continue
		}
		if id, perr := uuid.Parse(p.PartID); perr == nil {
			activeIDs = append(activeIDs, id)
		}
	}

	var res *mcp.CallToolResult
	var out bookStructureReadOut
	var rerr error
	if target := strings.TrimSpace(in.PartID); target == "" {
		res, out, rerr = s.structureReadL1(ctx, bookID, parts)
	} else {
		res, out, rerr = s.structureReadL2(ctx, bookID, target, parts, activeIDs, in.Offset, in.Limit)
	}
	if rerr != nil {
		return nil, bookStructureReadOut{}, rerr
	}
	// Cross-book READ is advisory (never blocking): note we're showing a different book than the studio.
	out.ScopeSource = scope.Source
	if scope.CrossBook {
		out.Guidance = "NOTE: this is a DIFFERENT book than the studio is bound to. " + out.Guidance
	}
	return res, out, nil
}

// structureReadL1 — the parts skeleton (reuse buildBookStructure so the counts match /structure exactly).
func (s *Server) structureReadL1(ctx context.Context, bookID uuid.UUID, parts []structurePartInput) (*mcp.CallToolResult, bookStructureReadOut, error) {
	rows, err := s.pool.Query(ctx, `SELECT structure_node_id FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID)
	if err != nil {
		return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
	}
	defer rows.Close()
	chapters := []structureChapterLink{}
	for rows.Next() {
		var snid *uuid.UUID
		if serr := rows.Scan(&snid); serr != nil {
			return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
		}
		var link *string
		if snid != nil {
			v := snid.String()
			link = &v
		}
		chapters = append(chapters, structureChapterLink{StructureNodeID: link})
	}
	if err := rows.Err(); err != nil {
		return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
	}
	built := buildBookStructure(bookID.String(), chapters, parts, structureWork{}, structureSources{Parts: "ok", Work: "ok"})
	refs := make([]structurePartRef, len(built.Parts))
	for i, p := range built.Parts {
		refs[i] = structurePartRef{PartID: p.PartID, Title: p.Title, SortOrder: p.SortOrder, ChapterCount: p.ChapterCount}
	}
	unassigned := built.UnassignedCount
	out := bookStructureReadOut{
		View:            "parts",
		Parts:           refs,
		UnassignedCount: &unassigned,
	}
	out.Guidance = fmt.Sprintf(
		"the manuscript has %d part(s) and %d unassigned chapter(s) — this IS the full overview, do NOT call again for it. "+
			"To list a part's chapters call book_structure_read with part_id=<id>; for the unassigned chapters use part_id=\"unassigned\". "+
			"To reorganize, call book_structure_edit.", len(refs), unassigned)
	return nil, out, nil
}

// structureReadL2 — one group's chapter refs, paged. "unassigned" = chapters with no live-part home (IS
// NULL or pointing at an arc/foreign/archived node — the same fall-through buildBookStructure uses, so the
// L2 unassigned set is consistent with the L1 unassigned_count: chapter conservation across the two reads.
func (s *Server) structureReadL2(ctx context.Context, bookID uuid.UUID, target string, parts []structurePartInput, activeIDs []uuid.UUID, offset, limit int) (*mcp.CallToolResult, bookStructureReadOut, error) {
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}
	var where string
	var args []any
	retry := "book_structure_read part_id=\"unassigned\""
	if strings.EqualFold(target, "unassigned") {
		where = "book_id=$1 AND lifecycle_state='active' AND (structure_node_id IS NULL OR structure_node_id <> ALL($2::uuid[]))"
		args = []any{bookID, activeIDs}
	} else {
		partID, err := uuid.Parse(target)
		if err != nil {
			return nil, bookStructureReadOut{}, errors.New("part_id must be a part UUID or the literal \"unassigned\"")
		}
		if !partIsLiveTarget(parts, partID) {
			return nil, bookStructureReadOut{}, errors.New("that is not a live part of this book — call book_structure_read (no part_id) for the valid part ids")
		}
		where = "book_id=$1 AND lifecycle_state='active' AND structure_node_id=$2"
		args = []any{bookID, partID}
		retry = "book_structure_read part_id=" + partID.String()
	}

	var total int
	if err := s.pool.QueryRow(ctx, "SELECT COUNT(*) FROM chapters WHERE "+where, args...).Scan(&total); err != nil {
		return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
	}
	q := "SELECT id,title,sort_order FROM chapters WHERE " + where + fmt.Sprintf(" ORDER BY sort_order, created_at LIMIT $%d OFFSET $%d", len(args)+1, len(args)+2)
	rows, err := s.pool.Query(ctx, q, append(args, limit, offset)...)
	if err != nil {
		return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
	}
	defer rows.Close()
	chapters := []structureChapterRef{}
	for rows.Next() {
		var c structureChapterRef
		if serr := rows.Scan(&c.ChapterID, &c.Title, &c.SortOrder); serr != nil {
			return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
		}
		chapters = append(chapters, c)
	}
	if err := rows.Err(); err != nil {
		return nil, bookStructureReadOut{}, errors.New("failed to read chapters")
	}
	env, guidance := listPage("chapters", len(chapters), total, offset, retry)
	out := bookStructureReadOut{View: "chapters", PartID: target, Chapters: chapters, Page: &env, Guidance: guidance}
	return nil, out, nil
}

// ── book_structure_edit ──────────────────────────────────────────────────────────────────────────

type bookStructureEditIn struct {
	Op             string   `json:"op" jsonschema:"the structure operation: create_part | rename_part | reorder_parts | home_chapter | reorder_chapters"`
	// book_id OPTIONAL (ambient_book) — omitted inside a studio, it resolves from the envelope; the handler
	// fail-closes if neither arg nor ambient book is present. See bookStructureReadIn.BookID.
	BookID         string   `json:"book_id,omitempty" jsonschema:"the book (UUID; edit access). Omit inside a book studio — the current book is used."`
	Title          string   `json:"title,omitempty" jsonschema:"create_part / rename_part: the part title"`
	PartID         string   `json:"part_id,omitempty" jsonschema:"rename_part: the part to rename; home_chapter: the target part (or omit / \"unassigned\" to un-home into the flat manuscript)"`
	OrderedPartIDs []string `json:"ordered_part_ids,omitempty" jsonschema:"reorder_parts: the book's active parts in the NEW order — EXACTLY the active set, each once"`
	ChapterID      string   `json:"chapter_id,omitempty" jsonschema:"home_chapter: the chapter to (re)home"`
	ChapterIDs     []string `json:"chapter_ids,omitempty" jsonschema:"reorder_chapters: the COMPLETE new order for one language track, each active chapter once"`
	AllowCrossBook bool     `json:"allow_cross_book,omitempty" jsonschema:"set true ONLY to confirm editing a book different from the studio you're in (normally omit — the current book is used)"`
}

type bookStructureEditOut struct {
	Op                     string             `json:"op"`
	Part                   *partWriteResult   `json:"part,omitempty"`     // create_part / rename_part
	Parts                  []partWriteResult  `json:"parts,omitempty"`    // reorder_parts
	Chapter                string             `json:"chapter_id,omitempty"`
	PartRef                *string            `json:"part_id,omitempty"`  // home_chapter result home (null = unassigned)
	Chapters               []reorderedChapter `json:"chapters,omitempty"` // reorder_chapters
	CrossBookConfirmTarget string             `json:"cross_book_confirm_required,omitempty"` // set (book_id) when a cross-book WRITE was NOT applied
	ScopeSource            string             `json:"scope_source,omitempty"`                // "arg" | "envelope"
	Guidance               string             `json:"guidance"`
}

func (s *Server) toolBookStructureEdit(ctx context.Context, req *mcp.CallToolRequest, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, bookStructureEditOut{}, errMissingIdentity
	}
	op := strings.ToLower(strings.TrimSpace(in.Op))
	// Ambient scope (spec 2026-07-22): resolve the book from the envelope when the model omits it.
	scope, sok := lwmcp.ResolveBookScope(ctx, in.BookID)
	if !sok {
		return nil, bookStructureEditOut{}, errors.New("book_id is required (a UUID)")
	}
	bookID := scope.BookID
	// Cross-book WRITE pre-confirm (§2.2): a write to a DIFFERENT book than the studio is bound to is
	// allowed but must be confirmed FIRST — never silently mutate the wrong manuscript. Grant is checked
	// inside each op; we gate on cross-book before dispatching so nothing is applied without allow_cross_book.
	if scope.CrossBook && !in.AllowCrossBook {
		return nil, bookStructureEditOut{
			Op:                     op,
			CrossBookConfirmTarget: bookID.String(),
			ScopeSource:            scope.Source,
			Guidance: "NOT APPLIED — this would edit a DIFFERENT book (book_id=" + bookID.String() +
				") than the studio you're in. If that is intended, re-issue the SAME call with allow_cross_book=true.",
		}, nil
	}

	var res *mcp.CallToolResult
	var out bookStructureEditOut
	var rerr error
	switch op {
	case "create_part":
		res, out, rerr = s.editCreatePart(ctx, bookID, userID, in)
	case "rename_part":
		res, out, rerr = s.editRenamePart(ctx, bookID, userID, in)
	case "reorder_parts":
		res, out, rerr = s.editReorderParts(ctx, bookID, userID, in)
	case "home_chapter":
		res, out, rerr = s.editHomeChapter(ctx, req, bookID, in)
	case "reorder_chapters":
		res, out, rerr = s.editReorderChapters(ctx, req, bookID, in)
	default:
		return nil, bookStructureEditOut{}, fmt.Errorf("unknown op %q — use one of: create_part, rename_part, reorder_parts, home_chapter, reorder_chapters", in.Op)
	}
	if rerr != nil {
		return nil, bookStructureEditOut{}, rerr
	}
	out.ScopeSource = scope.Source
	return res, out, nil
}

func (s *Server) editCreatePart(ctx context.Context, bookID, userID uuid.UUID, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, bookStructureEditOut{}, mcpOwnershipError(err)
	}
	part, status := s.createPartInternal(ctx, bookID, userID, strings.TrimSpace(in.Title))
	if part == nil {
		return nil, bookStructureEditOut{}, compWriteErr(status, "create the part")
	}
	// Undo a create by archiving the new part (the destructive op is the legacy tool, still callable by name).
	res := undoResult("book_structure_part_archive", map[string]any{"book_id": bookID.String(), "part_id": part.PartID})
	out := bookStructureEditOut{Op: "create_part", Part: part}
	out.Guidance = fmt.Sprintf("created part '%s' (part_id=%s). To file chapters into it call book_structure_edit op=home_chapter chapter_id=<id> part_id=%s. Done — do NOT call create_part again for this part.", part.Title, part.PartID, part.PartID)
	return res, out, nil
}

func (s *Server) editRenamePart(ctx context.Context, bookID, userID uuid.UUID, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, bookStructureEditOut{}, mcpOwnershipError(err)
	}
	partID, err := uuid.Parse(strings.TrimSpace(in.PartID))
	if err != nil {
		return nil, bookStructureEditOut{}, errors.New("rename_part needs part_id (a part UUID)")
	}
	// Capture the prior title (for Undo) and validate it's a LIVE part of this book, in one internal read.
	parts, reachable := s.fetchStructurePartsInternal(ctx, bookID.String(), userID.String())
	if !reachable {
		return nil, bookStructureEditOut{}, compWriteErr(0, "rename the part")
	}
	priorTitle, live := "", false
	for _, p := range parts {
		if p.Active && p.PartID == partID.String() {
			priorTitle, live = p.Title, true
			break
		}
	}
	if !live {
		return nil, bookStructureEditOut{}, errors.New("that is not a live part of this book — call book_structure_read for the valid part ids")
	}
	part, status := s.renamePartInternal(ctx, partID, userID, strings.TrimSpace(in.Title))
	if part == nil {
		return nil, bookStructureEditOut{}, compWriteErr(status, "rename the part")
	}
	res := undoResult("book_structure_edit", map[string]any{"op": "rename_part", "book_id": bookID.String(), "part_id": part.PartID, "title": priorTitle})
	out := bookStructureEditOut{Op: "rename_part", Part: part}
	out.Guidance = fmt.Sprintf("renamed the part to '%s'. Done — do NOT call again.", part.Title)
	return res, out, nil
}

func (s *Server) editReorderParts(ctx context.Context, bookID, userID uuid.UUID, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, bookStructureEditOut{}, mcpOwnershipError(err)
	}
	if len(in.OrderedPartIDs) == 0 {
		return nil, bookStructureEditOut{}, errors.New("reorder_parts needs ordered_part_ids (the full new order)")
	}
	ordered := make([]uuid.UUID, 0, len(in.OrderedPartIDs))
	seen := map[uuid.UUID]bool{}
	for _, raw := range in.OrderedPartIDs {
		id, perr := uuid.Parse(strings.TrimSpace(raw))
		if perr != nil {
			return nil, bookStructureEditOut{}, errors.New("every ordered_part_ids entry must be a UUID")
		}
		if seen[id] {
			return nil, bookStructureEditOut{}, errors.New("ordered_part_ids must not repeat a part")
		}
		seen[id] = true
		ordered = append(ordered, id)
	}
	// Snapshot the FULL prior order for Undo (R3) before the write.
	prior, reachable := s.fetchStructurePartsInternal(ctx, bookID.String(), userID.String())
	if !reachable {
		return nil, bookStructureEditOut{}, compWriteErr(0, "reorder the parts")
	}
	priorOrder := activePartIDsBySort(prior)
	items, status := s.reorderPartsInternal(ctx, bookID, userID, ordered)
	if items == nil {
		return nil, bookStructureEditOut{}, compWriteErr(status, "reorder the parts")
	}
	res := undoResult("book_structure_edit", map[string]any{"op": "reorder_parts", "book_id": bookID.String(), "ordered_part_ids": priorOrder})
	out := bookStructureEditOut{Op: "reorder_parts", Parts: items}
	out.Guidance = fmt.Sprintf("reordered %d part(s). Done — do NOT call again.", len(items))
	return res, out, nil
}

// activePartIDsBySort returns the active part ids in current sort order — the reverse arg for a reorder Undo.
func activePartIDsBySort(parts []structurePartInput) []string {
	active := make([]structurePartInput, 0, len(parts))
	for _, p := range parts {
		if p.Active {
			active = append(active, p)
		}
	}
	// parts arrive from composition already rank-ordered; keep that order.
	ids := make([]string, len(active))
	for i, p := range active {
		ids[i] = p.PartID
	}
	return ids
}

func (s *Server) editHomeChapter(ctx context.Context, req *mcp.CallToolRequest, bookID uuid.UUID, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	if in.ChapterID == "" {
		return nil, bookStructureEditOut{}, errors.New("home_chapter needs chapter_id")
	}
	// "unassigned" (or empty part_id) means un-home into the flat manuscript.
	var partArg *string
	if pt := strings.TrimSpace(in.PartID); pt != "" && !strings.EqualFold(pt, "unassigned") {
		partArg = &pt
	}
	// Delegate to the existing set-part engine: it re-validates the target part (no silent Unassigned),
	// gates EDIT, and performs the move. We rebuild the Undo hint against book_structure_edit for one name.
	res, sp, err := s.toolChapterSetPart(ctx, req, chapterSetPartIn{BookID: bookID.String(), ChapterID: in.ChapterID, PartID: partArg})
	if err != nil {
		return nil, bookStructureEditOut{}, err
	}
	// Reuse the delegated result's undo_hint (it already captured the prior home) but re-point the tool name.
	if res != nil {
		if hint, ok := res.Meta["undo_hint"].(map[string]any); ok {
			args, _ := hint["args"].(map[string]any)
			priorPart := any(nil)
			if args != nil {
				priorPart = args["part_id"]
			}
			res = undoResult("book_structure_edit", map[string]any{"op": "home_chapter", "book_id": bookID.String(), "chapter_id": sp.ChapterID, "part_id": priorPart})
		}
	}
	out := bookStructureEditOut{Op: "home_chapter", Chapter: sp.ChapterID, PartRef: sp.PartID}
	if sp.PartID != nil {
		out.Guidance = "chapter homed into the part. Done — do NOT call again."
	} else {
		out.Guidance = "chapter un-homed into the flat manuscript (no part). Done — do NOT call again."
	}
	return res, out, nil
}

func (s *Server) editReorderChapters(ctx context.Context, req *mcp.CallToolRequest, bookID uuid.UUID, in bookStructureEditIn) (*mcp.CallToolResult, bookStructureEditOut, error) {
	if len(in.ChapterIDs) == 0 {
		return nil, bookStructureEditOut{}, errors.New("reorder_chapters needs chapter_ids (the full new order)")
	}
	// Snapshot the prior order for Undo (R3): the language track of the first listed chapter, current order.
	priorOrder := s.chapterTrackOrder(ctx, bookID, in.ChapterIDs[0])
	// Delegate to the existing reorder engine (permutation validation + two-phase renumber).
	_, ro, err := s.toolChapterReorder(ctx, req, chapterReorderIn{BookID: bookID.String(), ChapterIDs: in.ChapterIDs})
	if err != nil {
		return nil, bookStructureEditOut{}, err
	}
	out := bookStructureEditOut{Op: "reorder_chapters", Chapters: ro.Chapters}
	out.Guidance = fmt.Sprintf("reordered %d chapter(s) in the '%s' track. Done — do NOT call again.", len(ro.Chapters), ro.OriginalLanguage)
	var res *mcp.CallToolResult
	if len(priorOrder) > 0 {
		res = undoResult("book_structure_edit", map[string]any{"op": "reorder_chapters", "book_id": bookID.String(), "chapter_ids": priorOrder})
	}
	return res, out, nil
}

// ── book_structure_part_archive (visibility:legacy — destructive/lifecycle, CAT-2 split) ────────────

type partArchiveIn struct {
	BookID string `json:"book_id" jsonschema:"the book (UUID; edit access required)"`
	PartID string `json:"part_id" jsonschema:"the part to archive (trash). Its chapters keep their text and fall to Unassigned."`
}
type partArchiveOut struct {
	PartID   string `json:"part_id"`
	Archived bool   `json:"archived"`
	Guidance string `json:"guidance"`
}

func (s *Server) toolBookStructurePartArchive(ctx context.Context, _ *mcp.CallToolRequest, in partArchiveIn) (*mcp.CallToolResult, partArchiveOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, partArchiveOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, partArchiveOut{}, errors.New("book_id must be a UUID")
	}
	partID, err := uuid.Parse(strings.TrimSpace(in.PartID))
	if err != nil {
		return nil, partArchiveOut{}, errors.New("part_id must be a part UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, partArchiveOut{}, mcpOwnershipError(err)
	}
	status := s.archivePartInternal(ctx, partID, userID)
	if status != http.StatusNoContent {
		return nil, partArchiveOut{}, compWriteErr(status, "archive the part")
	}
	out := partArchiveOut{PartID: partID.String(), Archived: true,
		Guidance: "part archived (trashed) — its chapters keep their text and now read as Unassigned. Restore it from the trash if this was a mistake. Done — do NOT call again."}
	return nil, out, nil
}

// chapterTrackOrder returns the active chapters of firstChapterID's language track, in current order —
// the reverse arg for a reorder_chapters Undo. Best-effort: a bad/foreign first id yields nil (no Undo).
func (s *Server) chapterTrackOrder(ctx context.Context, bookID uuid.UUID, firstChapterID string) []string {
	chID, err := uuid.Parse(firstChapterID)
	if err != nil {
		return nil
	}
	rows, err := s.pool.Query(ctx, `
SELECT id FROM chapters
WHERE book_id=$1 AND lifecycle_state='active'
  AND original_language=(SELECT original_language FROM chapters WHERE id=$2 AND book_id=$1)
ORDER BY sort_order, created_at`, bookID, chID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var order []string
	for rows.Next() {
		var id uuid.UUID
		if rows.Scan(&id) == nil {
			order = append(order, id.String())
		}
	}
	return order
}
