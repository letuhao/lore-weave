package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

type proposalRow struct {
	ProposalID    uuid.UUID       `json:"proposal_id"`
	OwnerUserID   uuid.UUID       `json:"owner_user_id"`
	Action        string          `json:"action"`
	TargetSkillID *uuid.UUID      `json:"target_skill_id,omitempty"`
	Slug          string          `json:"slug"`
	Description   string          `json:"description"`
	Frontmatter   json.RawMessage `json:"frontmatter"`
	BodyMD        string          `json:"body_md"`
	Surfaces      []string        `json:"surfaces"`
	Status        string          `json:"status"`
	RejectReason  string          `json:"reject_reason"`
	SessionID     string          `json:"from_session_id"`
	SessionLabel  string          `json:"from_session_label"`
	ConfirmToken  string          `json:"confirm_token,omitempty"`
	CreatedAt     time.Time       `json:"created_at"`
	ExpiresAt     time.Time       `json:"expires_at"`
}

const proposalCols = `proposal_id, owner_user_id, action, target_skill_id, slug, description,
	frontmatter, body_md, surfaces, status, reject_reason, from_session_id, from_session_label, created_at, expires_at`

func scanProposal(row interface{ Scan(...any) error }, p *proposalRow) error {
	return row.Scan(&p.ProposalID, &p.OwnerUserID, &p.Action, &p.TargetSkillID, &p.Slug, &p.Description,
		&p.Frontmatter, &p.BodyMD, &p.Surfaces, &p.Status, &p.RejectReason, &p.SessionID, &p.SessionLabel,
		&p.CreatedAt, &p.ExpiresAt)
}

// doProposeSkill inserts a pending proposal (called by the registry_propose_skill
// / registry_update_skill MCP tools). Owner is always the envelope user.
func (s *Server) doProposeSkill(ctx context.Context, uid uuid.UUID, action string, target *uuid.UUID, in *skillInput, sessionID, sessionLabel string) (*proposalRow, string) {
	if msg, ok := validateSkill(in); !ok {
		return nil, msg
	}
	fm := in.Frontmatter
	if len(fm) == 0 {
		fm = json.RawMessage(`{}`)
	}
	surfaces := in.Surfaces
	if surfaces == nil {
		surfaces = []string{}
	}
	token := uuid.NewString()
	var p proposalRow
	err := scanProposal(s.db.QueryRow(ctx,
		`INSERT INTO skill_proposals (owner_user_id, action, target_skill_id, slug, description, frontmatter, body_md, surfaces, confirm_token, from_session_id, from_session_label)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING `+proposalCols,
		uid, action, target, in.Slug, in.Description, string(fm), in.BodyMD, surfaces, token, sessionID, sessionLabel), &p)
	if err != nil {
		return nil, "could not store proposal"
	}
	s.audit(ctx, uid, "agent", "proposal", "propose", &p.ProposalID, in.Slug, "user", map[string]any{"action": action})
	return &p, ""
}

func (s *Server) listProposals(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	where := []string{"owner_user_id = $1"}
	args := []any{uid}
	if v := q.Get("status"); v == "pending" || v == "approved" || v == "rejected" || v == "expired" {
		args = append(args, v)
		where = append(where, "status = $"+strconv.Itoa(len(args)))
	}
	orderBy := "created_at DESC"
	if q.Get("sort") == "expiring" {
		orderBy = "expires_at ASC"
	}
	// lazily expire stale pending rows so the inbox reflects reality
	_, _ = s.db.Exec(r.Context(), `UPDATE skill_proposals SET status='expired', updated_at=now() WHERE owner_user_id=$1 AND status='pending' AND expires_at < now()`, uid)
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM skill_proposals WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+proposalCols+` FROM skill_proposals WHERE `+whereSQL+` ORDER BY `+orderBy+
			` LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list proposals")
		return
	}
	defer rows.Close()
	items := []proposalRow{}
	for rows.Next() {
		var p proposalRow
		if err := scanProposal(rows, &p); err != nil {
			continue
		}
		p.ConfirmToken = "" // never echo the token in the list
		items = append(items, p)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) getProposal(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var p proposalRow
	err := scanProposal(s.db.QueryRow(r.Context(),
		`SELECT `+proposalCols+` FROM skill_proposals WHERE proposal_id = $1 AND owner_user_id = $2`, pid, uid), &p)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "proposal not found")
		return
	}
	p.ConfirmToken = ""
	writeJSON(w, http.StatusOK, p)
}

// approveProposal (JWT owner) — the human accepts; creates/updates the skill in
// the user's tier. This is the confirm effect (no JWT mint; the browser's own
// token authorizes the write to the user's own tier).
func (s *Server) approveProposal(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var p proposalRow
	err := scanProposal(s.db.QueryRow(r.Context(),
		`SELECT `+proposalCols+` FROM skill_proposals WHERE proposal_id = $1 AND owner_user_id = $2`, pid, uid), &p)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "proposal not found")
		return
	}
	if p.Status != "pending" {
		writeError(w, http.StatusConflict, "NOT_PENDING", "proposal is "+p.Status)
		return
	}
	if p.ExpiresAt.Before(time.Now()) {
		_, _ = s.db.Exec(r.Context(), `UPDATE skill_proposals SET status='expired', updated_at=now() WHERE proposal_id=$1`, pid)
		writeError(w, http.StatusConflict, "proposal_expired", "proposal expired")
		return
	}
	in := &skillInput{
		Slug: p.Slug, Description: p.Description, BodyMD: p.BodyMD,
		Surfaces: p.Surfaces, Frontmatter: p.Frontmatter, Tier: "user", Source: "agent",
	}
	if p.Action == "update" && p.TargetSkillID != nil {
		// update the target skill (must be the caller's own)
		var owner *uuid.UUID
		var tier string
		if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id FROM skills WHERE skill_id=$1`, *p.TargetSkillID).Scan(&tier, &owner); err != nil || !s.canWritePlugin(tier, owner, uid, role) {
			writeError(w, http.StatusConflict, "TARGET_GONE", "target skill not writable")
			return
		}
		fm := p.Frontmatter
		if len(fm) == 0 {
			fm = json.RawMessage(`{}`)
		}
		if _, err := s.db.Exec(r.Context(),
			`UPDATE skills SET description=$1, body_md=$2, frontmatter=$3, surfaces=$4, updated_at=now() WHERE skill_id=$5`,
			p.Description, p.BodyMD, string(fm), p.Surfaces, *p.TargetSkillID); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not apply update")
			return
		}
		s.audit(r.Context(), uid, "user", "skill", "update", p.TargetSkillID, p.Slug, "user", map[string]any{"via": "proposal"})
	} else {
		// create — reuse the create path but write result inline (avoid double response)
		if msg, ok := validateSkill(in); !ok {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", msg)
			return
		}
		// REG-X-02 (D2): the per-user skill cap applies to agent-proposed skills too.
		if s.skillQuotaExceeded(r.Context(), uid) {
			writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "skill limit reached (max 50 per user)")
			return
		}
		fm := in.Frontmatter
		if len(fm) == 0 {
			fm = json.RawMessage(`{}`)
		}
		surfaces := in.Surfaces
		if surfaces == nil {
			surfaces = []string{}
		}
		var newID uuid.UUID
		if err := s.db.QueryRow(r.Context(),
			`INSERT INTO skills (tier, owner_user_id, slug, description, frontmatter, body_md, surfaces, status, source)
			 VALUES ('user',$1,$2,$3,$4,$5,$6,'published','agent') RETURNING skill_id`,
			uid, in.Slug, in.Description, string(fm), in.BodyMD, surfaces).Scan(&newID); err != nil {
			if isUniqueViolation(err) {
				writeError(w, http.StatusConflict, "DUPLICATE", "a skill with this slug already exists")
				return
			}
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create skill")
			return
		}
		s.audit(r.Context(), uid, "user", "skill", "create", &newID, in.Slug, "user", map[string]any{"via": "proposal"})
	}
	_, _ = s.db.Exec(r.Context(), `UPDATE skill_proposals SET status='approved', updated_at=now() WHERE proposal_id=$1`, pid)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("proposal", "approve").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"proposal_id": pid, "status": "approved", "slug": p.Slug})
}

func (s *Server) rejectProposal(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "proposal_id")
	if !ok {
		return
	}
	var body struct {
		Reason string `json:"reason"`
	}
	_ = decodeJSON(w, r, &body)
	ct, err := s.db.Exec(r.Context(),
		`UPDATE skill_proposals SET status='rejected', reject_reason=$1, updated_at=now() WHERE proposal_id=$2 AND owner_user_id=$3 AND status='pending'`,
		body.Reason, pid, uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not reject")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "no pending proposal")
		return
	}
	s.audit(r.Context(), uid, "user", "proposal", "reject", &pid, "", "", nil)
	registryWrites.WithLabelValues("proposal", "reject").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"proposal_id": pid, "status": "rejected"})
}
