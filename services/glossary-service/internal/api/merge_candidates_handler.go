package api

// mui #1c G-cand — the merge-candidate review surface.
//
//	POST /internal/books/{book_id}/merge-candidates                      (knowledge → glossary, propose)
//	GET  /v1/glossary/books/{book_id}/merge-candidates?status=proposed   (FE inbox, list)
//	POST /v1/glossary/books/{book_id}/merge-candidates/{candidate_id}/dismiss
//
// knowledge's coref detector (K-detect) proposes clusters of likely-same
// entities here; the human reviews and confirms via the existing R5 merge
// endpoint. This file is storage + plumbing only — no scoring lives here.
//
// Idempotency: each cluster is keyed by its sorted-distinct member-id set
// (member_set_key). Re-proposing the same cluster updates a still-`proposed`
// row and is a no-op (suppressed) once it's been dismissed or merged.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// ── propose (internal) ──────────────────────────────────────────────────────

type proposeCandidatesRequest struct {
	Candidates []proposeCandidateInput `json:"candidates"`
}

type proposeCandidateInput struct {
	MemberEntityIDs         []string `json:"member_entity_ids"`
	SuggestedWinnerEntityID string   `json:"suggested_winner_entity_id"`
	Score                   float64  `json:"score"`
	Evidence                []any    `json:"evidence"`
	Rationale               string   `json:"rationale"`
}

type proposeCandidateResult struct {
	CandidateID string `json:"candidate_id,omitempty"`
	Status      string `json:"status"` // "proposed" | "suppressed" | "skipped"
	Reason      string `json:"reason,omitempty"`
}

// memberSetKey is the idempotency key: distinct member ids in canonical
// (lowercase) string form, sorted, joined by ','. Order-independent so the
// detector can emit members in any order and still hit the same row.
func memberSetKey(ids []uuid.UUID) string {
	strs := make([]string, 0, len(ids))
	for _, id := range ids {
		strs = append(strs, id.String())
	}
	sort.Strings(strs)
	return strings.Join(strs, ",")
}

// internalProposeMergeCandidates upserts proposed merge clusters from knowledge.
//
//	POST /internal/books/{book_id}/merge-candidates
//	body: { "candidates": [ { "member_entity_ids": [...], "suggested_winner_entity_id"?, "score"?, "evidence"?, "rationale"? } ] }
func (s *Server) internalProposeMergeCandidates(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req proposeCandidatesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}

	ctx := r.Context()
	results := make([]proposeCandidateResult, 0, len(req.Candidates))
	for _, c := range req.Candidates {
		results = append(results, s.proposeOneCandidate(ctx, bookID, c))
	}
	writeJSON(w, http.StatusOK, map[string]any{"results": results})
}

// proposeOneCandidate validates + upserts a single cluster. Never errors out the
// whole batch — a bad cluster is reported as "skipped" with a reason.
func (s *Server) proposeOneCandidate(ctx context.Context, bookID uuid.UUID, c proposeCandidateInput) proposeCandidateResult {
	// Parse + dedup members.
	seen := map[uuid.UUID]struct{}{}
	members := make([]uuid.UUID, 0, len(c.MemberEntityIDs))
	for _, raw := range c.MemberEntityIDs {
		id, err := uuid.Parse(raw)
		if err != nil {
			continue
		}
		if _, dup := seen[id]; dup {
			continue
		}
		seen[id] = struct{}{}
		members = append(members, id)
	}
	if len(members) < 2 {
		return proposeCandidateResult{Status: "skipped", Reason: "need >=2 distinct members"}
	}

	// Validate: every member must be live, in this book, and the SAME kind — a
	// cluster spanning kinds or books is incoherent (you can't merge across kind).
	rows, err := s.pool.Query(ctx,
		`SELECT entity_id, kind_id, book_id, deleted_at FROM glossary_entities WHERE entity_id = ANY($1::uuid[])`,
		members)
	if err != nil {
		return proposeCandidateResult{Status: "skipped", Reason: "member lookup failed"}
	}
	defer rows.Close()
	found := map[uuid.UUID]uuid.UUID{} // entity_id → kind_id
	var commonKind uuid.UUID
	for rows.Next() {
		var id, kind, book uuid.UUID
		var del *time.Time
		if rows.Scan(&id, &kind, &book, &del) != nil {
			continue
		}
		if book != bookID || del != nil {
			continue // dropped → will fail the count check below
		}
		found[id] = kind
		commonKind = kind
	}
	if rows.Err() != nil {
		return proposeCandidateResult{Status: "skipped", Reason: "member iteration failed"}
	}
	if len(found) != len(members) {
		return proposeCandidateResult{Status: "skipped", Reason: "member missing/soft-deleted/wrong book"}
	}
	for _, kind := range found {
		if kind != commonKind {
			return proposeCandidateResult{Status: "skipped", Reason: "members span multiple kinds"}
		}
	}

	// suggested_winner is honoured only if it is one of the members.
	var winnerPtr *uuid.UUID
	if c.SuggestedWinnerEntityID != "" {
		if wid, err := uuid.Parse(c.SuggestedWinnerEntityID); err == nil {
			if _, isMember := found[wid]; isMember {
				winnerPtr = &wid
			}
		}
	}

	evidenceJSON, err := json.Marshal(c.Evidence)
	if err != nil || c.Evidence == nil {
		evidenceJSON = []byte("[]")
	}
	key := memberSetKey(members)

	// Idempotent upsert. The WHERE on DO UPDATE means a dismissed/merged row is
	// NOT resurrected — the conflict updates nothing, RETURNING yields no row,
	// and we report "suppressed".
	var candidateID uuid.UUID
	err = s.pool.QueryRow(ctx, `
		INSERT INTO merge_candidates
		  (book_id, kind_id, member_entity_ids, member_set_key,
		   suggested_winner_entity_id, score, evidence_json, rationale)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		ON CONFLICT (book_id, member_set_key) DO UPDATE
		  SET suggested_winner_entity_id = EXCLUDED.suggested_winner_entity_id,
		      score        = EXCLUDED.score,
		      evidence_json = EXCLUDED.evidence_json,
		      rationale    = EXCLUDED.rationale,
		      updated_at   = now()
		  WHERE merge_candidates.status = 'proposed'
		RETURNING candidate_id`,
		bookID, commonKind, members, key, winnerPtr, c.Score, evidenceJSON, c.Rationale,
	).Scan(&candidateID)
	if errors.Is(err, pgx.ErrNoRows) {
		return proposeCandidateResult{Status: "suppressed", Reason: "cluster already dismissed or merged"}
	}
	if err != nil {
		slog.Warn("propose merge-candidate upsert failed", "book_id", bookID.String(), "err", err)
		return proposeCandidateResult{Status: "skipped", Reason: "upsert failed"}
	}
	return proposeCandidateResult{CandidateID: candidateID.String(), Status: "proposed"}
}

// ── list (public) ───────────────────────────────────────────────────────────

type mergeCandidateMember struct {
	EntityID     string   `json:"entity_id"`
	Name         string   `json:"name"`
	Aliases      []string `json:"aliases"`
	ChapterLinks int      `json:"chapter_link_count"`
}

type mergeCandidateView struct {
	CandidateID     string                 `json:"candidate_id"`
	KindCode        string                 `json:"kind_code"`
	Score           float64                `json:"score"`
	Rationale       string                 `json:"rationale"`
	Evidence        json.RawMessage        `json:"evidence"`
	SuggestedWinner string                 `json:"suggested_winner_entity_id,omitempty"`
	Status          string                 `json:"status"`
	CreatedAt       string                 `json:"created_at"`
	Members         []mergeCandidateMember `json:"members"`
}

// listMergeCandidates returns proposed (default) clusters with member detail so
// the FE inbox renders without per-member round-trips.
//
//	GET /v1/glossary/books/{book_id}/merge-candidates?status=proposed
func (s *Server) listMergeCandidates(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	status := r.URL.Query().Get("status")
	if status == "" {
		status = "proposed"
	}
	if status != "proposed" && status != "dismissed" && status != "merged" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_STATUS", "status must be proposed|dismissed|merged")
		return
	}
	out, err := s.loadMergeCandidates(r.Context(), bookID, status)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "candidate query failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"candidates": out})
}

// loadMergeCandidates is the auth-free core of listMergeCandidates (so it is
// DB-testable without book-service). Returns candidates of the given status
// with member detail, ordered by score then recency.
func (s *Server) loadMergeCandidates(ctx context.Context, bookID uuid.UUID, status string) ([]mergeCandidateView, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT mc.candidate_id, ek.code, mc.member_entity_ids,
		       mc.suggested_winner_entity_id, mc.score, mc.evidence_json,
		       mc.rationale, mc.status, mc.created_at
		FROM merge_candidates mc
		JOIN system_kinds ek ON ek.kind_id = mc.kind_id
		WHERE mc.book_id = $1 AND mc.status = $2
		ORDER BY mc.score DESC, mc.created_at DESC`, bookID, status)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	type rawCand struct {
		view    mergeCandidateView
		members []uuid.UUID
	}
	cands := []rawCand{}
	allMembers := map[uuid.UUID]struct{}{}
	for rows.Next() {
		var (
			cid       uuid.UUID
			kindCode  string
			members   []uuid.UUID
			winner    *uuid.UUID
			score     float64
			evidence  []byte
			rationale string
			st        string
			createdAt time.Time
		)
		if err := rows.Scan(&cid, &kindCode, &members, &winner, &score, &evidence, &rationale, &st, &createdAt); err != nil {
			return nil, err
		}
		v := mergeCandidateView{
			CandidateID: cid.String(), KindCode: kindCode, Score: score,
			Rationale: rationale, Evidence: json.RawMessage(evidence), Status: st,
			CreatedAt: createdAt.UTC().Format(time.RFC3339), Members: []mergeCandidateMember{},
		}
		if winner != nil {
			v.SuggestedWinner = winner.String()
		}
		for _, m := range members {
			allMembers[m] = struct{}{}
		}
		cands = append(cands, rawCand{view: v, members: members})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	detail := s.loadMemberDetail(ctx, allMembers)

	out := make([]mergeCandidateView, 0, len(cands))
	for _, c := range cands {
		for _, m := range c.members {
			md := detail[m] // zero value (empty) if the member vanished since proposal
			md.EntityID = m.String()
			c.view.Members = append(c.view.Members, md)
		}
		out = append(out, c.view)
	}
	return out, nil
}

// loadMemberDetail batch-loads name/aliases/chapter-count for a set of member
// ids in 2 queries (no N+1). Reads name/aliases from the EAV (same source the
// merge path uses) so it is consistent regardless of cached_* trigger timing.
func (s *Server) loadMemberDetail(ctx context.Context, ids map[uuid.UUID]struct{}) map[uuid.UUID]mergeCandidateMember {
	detail := map[uuid.UUID]mergeCandidateMember{}
	if len(ids) == 0 {
		return detail
	}
	idList := make([]uuid.UUID, 0, len(ids))
	for id := range ids {
		idList = append(idList, id)
	}

	// name + aliases from EAV
	if rows, err := s.pool.Query(ctx, `
		SELECT eav.entity_id, ad.code, eav.original_value
		FROM entity_attribute_values eav
		JOIN system_kind_attributes ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id = ANY($1::uuid[]) AND ad.code IN ('name','aliases')`, idList); err == nil {
		for rows.Next() {
			var id uuid.UUID
			var code, val string
			if rows.Scan(&id, &code, &val) != nil {
				continue
			}
			md := detail[id]
			switch code {
			case "name":
				md.Name = val
			case "aliases":
				_ = json.Unmarshal([]byte(val), &md.Aliases)
			}
			detail[id] = md
		}
		rows.Close()
	}

	// chapter link counts
	if rows, err := s.pool.Query(ctx, `
		SELECT entity_id, count(*) FROM chapter_entity_links
		WHERE entity_id = ANY($1::uuid[]) GROUP BY entity_id`, idList); err == nil {
		for rows.Next() {
			var id uuid.UUID
			var n int
			if rows.Scan(&id, &n) != nil {
				continue
			}
			md := detail[id]
			md.ChapterLinks = n
			detail[id] = md
		}
		rows.Close()
	}

	for id, md := range detail {
		if md.Aliases == nil {
			md.Aliases = []string{}
			detail[id] = md
		}
	}
	return detail
}

// ── dismiss (public) ─────────────────────────────────────────────────────────

// dismissMergeCandidate marks a proposed cluster dismissed (re-propose then
// suppressed). Idempotent on an already-dismissed row; 409 on a merged one.
//
//	POST /v1/glossary/books/{book_id}/merge-candidates/{candidate_id}/dismiss
func (s *Server) dismissMergeCandidate(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	candidateID, ok := parsePathUUID(w, r, "candidate_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	reason, err := s.dismissMergeCandidateCore(r.Context(), bookID, candidateID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "dismiss failed")
		return
	}
	switch reason {
	case "":
		writeJSON(w, http.StatusOK, map[string]any{"candidate_id": candidateID.String(), "status": "dismissed"})
	case "not_found":
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "merge candidate not found")
	case "already_merged":
		writeError(w, http.StatusConflict, "GLOSS_ALREADY_MERGED", "candidate already merged; cannot dismiss")
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", reason)
	}
}

// dismissMergeCandidateCore is the auth-free core of dismiss. Returns ("", nil)
// on success (including idempotent re-dismiss), (businessReason, nil) for a 4xx
// condition, or (_, err) for a 500.
func (s *Server) dismissMergeCandidateCore(ctx context.Context, bookID, candidateID uuid.UUID) (string, error) {
	var jBook uuid.UUID
	var status string
	if err := s.pool.QueryRow(ctx,
		`SELECT book_id, status FROM merge_candidates WHERE candidate_id = $1`, candidateID,
	).Scan(&jBook, &status); err != nil {
		return "not_found", nil
	}
	if jBook != bookID {
		return "not_found", nil
	}
	if status == "merged" {
		return "already_merged", nil
	}
	if status == "dismissed" {
		return "", nil // idempotent
	}
	// Guard the write on status='proposed' (not just candidate_id): a concurrent
	// merge could flip the row to 'merged' between the read above and this write,
	// and an unguarded UPDATE would clobber 'merged'→'dismissed'. If the merge
	// won the race, 0 rows change and we surface 'already_merged'.
	tag, err := s.pool.Exec(ctx,
		`UPDATE merge_candidates SET status='dismissed', updated_at=now()
		 WHERE candidate_id=$1 AND status='proposed'`, candidateID)
	if err != nil {
		return "", err
	}
	if tag.RowsAffected() == 0 {
		return "already_merged", nil
	}
	return "", nil
}

// ── mark-merged (called best-effort by the merge endpoint) ───────────────────

// markCandidatesMerged flips a still-`proposed` candidate to 'merged' only when
// THIS merge fully resolves it: the winner is a member AND every member is
// covered by {winner} ∪ {merged losers}. A partial merge of a larger cluster
// leaves it proposed (review-impl MED-1 — don't hide an unresolved duplicate).
// Best-effort: a failure is logged, never propagated — the merge already
// committed; a `dismissed` cluster is untouched (WHERE status='proposed').
func (s *Server) markCandidatesMerged(ctx context.Context, bookID, winnerID uuid.UUID, loserIDs []uuid.UUID) {
	if len(loserIDs) == 0 {
		return
	}
	covered := append([]uuid.UUID{winnerID}, loserIDs...)
	if _, err := s.pool.Exec(ctx, `
		UPDATE merge_candidates SET status='merged', updated_at=now()
		WHERE book_id=$1 AND status='proposed'
		  AND member_entity_ids @> ARRAY[$2]::uuid[]
		  AND member_entity_ids <@ ($3::uuid[])`, bookID, winnerID, covered); err != nil {
		slog.Warn("markCandidatesMerged failed (non-fatal)",
			"book_id", bookID.String(), "winner", winnerID.String(), "err", err)
	}
}
