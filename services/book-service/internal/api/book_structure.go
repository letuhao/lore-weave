package api

// P1.1 (book-structure-pipeline spec §4.2) — the unified manuscript-structure read.
//
// book-service OWNS this read: it holds the chapter SSOT + the `structure_node_id` join key +
// lifecycle, and calls composition for the small parts list + the active Work. Parts are ALWAYS
// read (they are book_id-scoped and Work-INDEPENDENT), so Bug 4 — a manuscript Part vanishing
// because the FE was in outline mode — cannot recur. A skeleton (parts + counts, NOT inline
// chapters): the FE lazy-loads a group's chapters on expand, preserving today's pagination.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"sort"
	"strings"

	"github.com/google/uuid"
)

type structurePart struct {
	PartID       string `json:"part_id"`
	Title        string `json:"title"`
	SortOrder    int    `json:"sort_order"`
	ChapterCount int    `json:"chapter_count"`
}

type structureKinds struct {
	Parts   bool `json:"parts"`
	Outline bool `json:"outline"`
}

type structureWork struct {
	ProjectID *string `json:"project_id"`
}

// structureSources surfaces a composition outage instead of silently flattening the manuscript
// (spec §4.5 "no silent seams"): "ok" | "unavailable".
type structureSources struct {
	Parts string `json:"parts"`
	Work  string `json:"work"`
}

type bookStructureResponse struct {
	BookID          string           `json:"book_id"`
	BookLifecycle   string           `json:"book_lifecycle"` // active | trashed | purge_pending (spec §4.6 read-side gate)
	KindsPresent    structureKinds   `json:"kinds_present"`
	Parts           []structurePart  `json:"parts"`
	UnassignedCount int              `json:"unassigned_count"`
	ActiveWork      structureWork    `json:"active_work"`
	Sources         structureSources `json:"sources"`
}

// structureChapterLink is the only chapter field grouping needs: its (nullable) part link.
type structureChapterLink struct {
	StructureNodeID *string
}

// structurePartInput is a composition part node (structure_node kind='part').
type structurePartInput struct {
	PartID    string
	Title     string
	SortOrder int
	Active    bool
}

// buildBookStructure — the LEFT-JOIN-safe grouping (spec §4.2). PURE + deterministic (unit-tested).
// A chapter whose structure_node_id is null, OR points at a part not in THIS book's ACTIVE set
// (an arc node, a foreign-book part, an archived/deleted/dangling part), falls to Unassigned —
// never dropped, never filed under a foreign/arc node. Chapter conservation is an invariant:
// sum(part counts) + unassigned == len(chapters).
func buildBookStructure(
	bookID string,
	chapters []structureChapterLink,
	parts []structurePartInput,
	work structureWork,
	sources structureSources,
) bookStructureResponse {
	active := make([]structurePartInput, 0, len(parts))
	for _, p := range parts {
		if p.Active {
			active = append(active, p)
		}
	}
	sort.SliceStable(active, func(i, j int) bool { return active[i].SortOrder < active[j].SortOrder })
	idxByID := make(map[string]int, len(active))
	for i, p := range active {
		idxByID[p.PartID] = i
	}
	counts := make([]int, len(active))
	unassigned := 0
	for _, ch := range chapters {
		if ch.StructureNodeID != nil {
			if i, ok := idxByID[*ch.StructureNodeID]; ok {
				counts[i]++
				continue
			}
		}
		unassigned++
	}
	outParts := make([]structurePart, len(active))
	for i, p := range active {
		outParts[i] = structurePart{PartID: p.PartID, Title: p.Title, SortOrder: p.SortOrder, ChapterCount: counts[i]}
	}
	return bookStructureResponse{
		BookID:          bookID,
		KindsPresent:    structureKinds{Parts: len(active) > 0, Outline: work.ProjectID != nil},
		Parts:           outParts,
		UnassignedCount: unassigned,
		ActiveWork:      work,
		Sources:         sources,
	}
}

// getBookStructure — GET /v1/books/{book_id}/structure (VIEW-gated).
func (s *Server) getBookStructure(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, lifecycle, ok := s.authBook(w, r, bookID, GrantView)
	if !ok {
		return
	}
	ctx := r.Context()
	// Spec §4.6 read-side gate — the resolver joins the book's OWN lifecycle so it never renders LIVE
	// structure over a trashed / purge_pending book. A non-active book returns an empty skeleton with the
	// lifecycle marker + NO composition fetch (nothing live to show). This is the book-service half of the
	// lifecycle cascade; composition's book_lifecycle column mirror (P3.2) is the composition-side half.
	if lifecycle != "active" {
		writeJSON(w, http.StatusOK, bookStructureResponse{
			BookID:        bookID.String(),
			BookLifecycle: lifecycle,
			Parts:         []structurePart{},
			ActiveWork:    structureWork{},
			Sources:       structureSources{Parts: "ok", Work: "ok"},
		})
		return
	}
	// Local chapters — the SSOT + the join key. Active only, and NO cap (book-service owns chapters;
	// the composition-side 2000 ceiling is exactly the silent truncation this resolver avoids).
	rows, err := s.pool.Query(ctx,
		`SELECT structure_node_id FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_INTERNAL", "failed to read chapters")
		return
	}
	defer rows.Close()
	chapters := []structureChapterLink{}
	for rows.Next() {
		var snid *uuid.UUID
		if err := rows.Scan(&snid); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_INTERNAL", "failed to scan chapters")
			return
		}
		var link *string
		if snid != nil {
			v := snid.String()
			link = &v
		}
		chapters = append(chapters, structureChapterLink{StructureNodeID: link})
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_INTERNAL", "failed to read chapters")
		return
	}

	bearer := r.Header.Get("Authorization")
	parts, partsOK := s.fetchStructureParts(ctx, bookID.String(), bearer)
	work, workOK := s.fetchStructureWork(ctx, bookID.String(), bearer)
	sources := structureSources{Parts: sourceStatus(partsOK), Work: sourceStatus(workOK)}
	resp := buildBookStructure(bookID.String(), chapters, parts, work, sources)
	resp.BookLifecycle = lifecycle
	writeJSON(w, http.StatusOK, resp)
}

func sourceStatus(ok bool) string {
	if ok {
		return "ok"
	}
	return "unavailable"
}

// fetchStructureParts calls composition GET /v1/composition/books/{id}/parts (bearer-forwarded).
// ok=false ⇒ sources.parts="unavailable" (surfaced, never a silent flatten).
func (s *Server) fetchStructureParts(ctx context.Context, bookID, bearer string) ([]structurePartInput, bool) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || bearer == "" {
		return nil, false
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, base+"/v1/composition/books/"+bookID+"/parts", nil)
	if err != nil {
		return nil, false
	}
	req.Header.Set("Authorization", bearer)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, false
	}
	return decodeStructureParts(resp.Body), true
}

// decodeStructureParts parses composition's {items:[{part_id,title,sort_order,lifecycle_state}]} shape —
// shared by the bearer-forwarded public fetch and the internal-token fetch so both parse one contract.
func decodeStructureParts(r io.Reader) []structurePartInput {
	var out struct {
		Items []struct {
			PartID         string `json:"part_id"`
			Title          string `json:"title"`
			SortOrder      int    `json:"sort_order"`
			LifecycleState string `json:"lifecycle_state"`
		} `json:"items"`
	}
	if err := json.NewDecoder(r).Decode(&out); err != nil {
		return nil
	}
	parts := make([]structurePartInput, 0, len(out.Items))
	for _, it := range out.Items {
		parts = append(parts, structurePartInput{
			PartID: it.PartID, Title: it.Title, SortOrder: it.SortOrder,
			Active: it.LifecycleState == "active",
		})
	}
	return parts
}

// fetchStructurePartsInternal calls composition's INTERNAL parts route (X-Internal-Token + caller_user_id).
// The AGENT/MCP write path has a user_id but NO user bearer, so it cannot use the bearer-gated public
// /parts; this is how book_chapter_set_part validates a target part for an agent. ok=false ⇒ composition
// unreachable OR the caller has no grant (uniform 404) — surface, never accept a bad write on a blind spot.
func (s *Server) fetchStructurePartsInternal(ctx context.Context, bookID, userID string) ([]structurePartInput, bool) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || s.cfg.InternalServiceToken == "" {
		return nil, false
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet,
		base+"/internal/composition/books/"+bookID+"/parts?caller_user_id="+userID, nil)
	if err != nil {
		return nil, false
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, false
	}
	return decodeStructureParts(resp.Body), true
}

// validatePartTargetInternal is validatePartTarget for the agent MCP write path (no user bearer): it
// reaches composition via the internal parts route (X-Internal-Token + the acting user_id). Same
// (valid, reachable) contract — reachable=false ⇒ composition down/unauthorized (don't accept the write).
func (s *Server) validatePartTargetInternal(ctx context.Context, bookID, userID, partID uuid.UUID) (valid bool, reachable bool) {
	parts, ok := s.fetchStructurePartsInternal(ctx, bookID.String(), userID.String())
	if !ok {
		return false, false
	}
	want := partID.String()
	for _, p := range parts {
		if p.Active && p.PartID == want {
			return true, true
		}
	}
	return false, true
}

// validatePartTarget verifies partID is a LIVE kind='part' of bookID (via composition). It closes the
// "no silent seam" write gap (spec §4.5): setChapterPart / book_chapter_set_part used to accept ANY UUID
// (an arc node id, a foreign book's part) and the chapter would then silently read as Unassigned. Returns
// (valid, reachable): reachable=false ⇒ composition is down (surface a 502, don't accept a bad write).
func (s *Server) validatePartTarget(ctx context.Context, bookID uuid.UUID, bearer string, partID uuid.UUID) (valid bool, reachable bool) {
	parts, ok := s.fetchStructureParts(ctx, bookID.String(), bearer)
	if !ok {
		return false, false
	}
	want := partID.String()
	for _, p := range parts {
		if p.Active && p.PartID == want {
			return true, true
		}
	}
	return false, true
}

// fetchStructureWork calls composition GET /v1/composition/books/{id}/work (bearer-forwarded) and
// returns the active Work's project_id (null when pending/unresolved) — the kinds_present.outline
// signal (a project-backed Work has a compiled outline). ok=false ⇒ sources.work="unavailable".
func (s *Server) fetchStructureWork(ctx context.Context, bookID, bearer string) (structureWork, bool) {
	base := strings.TrimRight(s.cfg.CompositionServiceURL, "/")
	if base == "" || bearer == "" {
		return structureWork{}, false
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, base+"/v1/composition/books/"+bookID+"/work", nil)
	if err != nil {
		return structureWork{}, false
	}
	req.Header.Set("Authorization", bearer)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return structureWork{}, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return structureWork{}, false
	}
	return decodeStructureWork(resp.Body)
}

// decodeStructureWork parses composition's GET /books/{id}/work response for the active Work's
// project_id. That id is NESTED under `work` (the resolved work) — the top-level `book_project_id` is a
// DIFFERENT field that is null for a normally-resolved work, and reading it made kinds.outline ALWAYS
// false (a real bug caught by the Work-book e2e). This mirrors the FE, which reads the resolved work's
// project_id (useWorkResolution → resolveActiveWork(...).project_id). A null project (a lazy/pending
// Work) correctly yields outline=false, matching the FE's 'chapters' mode. Extracted for unit testing.
func decodeStructureWork(r io.Reader) (structureWork, bool) {
	var out struct {
		Work *struct {
			ProjectID *string `json:"project_id"`
		} `json:"work"`
	}
	if err := json.NewDecoder(r).Decode(&out); err != nil {
		return structureWork{}, false
	}
	if out.Work != nil {
		return structureWork{ProjectID: out.Work.ProjectID}, true
	}
	return structureWork{}, true
}
