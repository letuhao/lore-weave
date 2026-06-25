package api

// D-BATCH-RESEARCH-JOB M2 — research-job lifecycle endpoints (pause / resume / cancel).
// These give the M2 worker its human controls. Grant tiers mirror wiki_jobs: resume is an
// Edit (re-drive), cancel is Manage (discard). Each returns the updated job view, 404 when
// the job isn't in this book, 409 when it isn't in a state the action allows.

import (
	"context"
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// pauseResearchJob — POST …/research-jobs/{job_id}/pause. running|pending → paused_user.
func (s *Server) pauseResearchJob(w http.ResponseWriter, r *http.Request) {
	s.researchJobTransition(w, r, grantclient.GrantEdit, "paused_user",
		[]string{"pending", "running"}, false, false)
}

// resumeResearchJob — POST …/research-jobs/{job_id}/resume. paused_user|failed → pending
// (the worker re-claims it and continues from cursor_entity_id). Clears any prior error.
func (s *Server) resumeResearchJob(w http.ResponseWriter, r *http.Request) {
	s.researchJobTransition(w, r, grantclient.GrantEdit, "pending",
		[]string{"paused_user", "failed"}, false, true)
}

// cancelResearchJob — POST …/research-jobs/{job_id}/cancel. any non-terminal → cancelled.
func (s *Server) cancelResearchJob(w http.ResponseWriter, r *http.Request) {
	s.researchJobTransition(w, r, grantclient.GrantManage, "cancelled",
		[]string{"pending", "running", "paused_user", "failed"}, true, false)
}

// researchJobTransition is the shared handler for the three lifecycle actions: auth,
// attempt a guarded status change, and return the updated view (or 404/409).
func (s *Server) researchJobTransition(w http.ResponseWriter, r *http.Request, need grantclient.GrantLevel, to string, from []string, setCompleted, clearError bool) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	jobID, ok := parsePathUUID(w, r, "job_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, need) {
		return
	}
	found, changed, err := s.transitionResearchJob(r.Context(), bookID, jobID, to, from, setCompleted, clearError)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "job update failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_JOB_NOT_FOUND", "research job not found")
		return
	}
	if !changed {
		writeError(w, http.StatusConflict, "GLOSS_JOB_STATE", "the job is not in a state that allows this action")
		return
	}
	view, _, lerr := s.loadResearchJob(r.Context(), bookID, jobID)
	if lerr != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "job reload failed")
		return
	}
	writeJSON(w, http.StatusOK, view)
}

// transitionResearchJob flips status to `to` iff the current status is in `from`. Returns
// found=false (→404) when the job isn't in this book, and changed=false (→409) when it
// exists but isn't in an allowed from-state. The `status = ANY(from)` guard makes the
// change atomic against a concurrent worker/lifecycle transition.
func (s *Server) transitionResearchJob(ctx context.Context, bookID, jobID uuid.UUID, to string, from []string, setCompleted, clearError bool) (found, changed bool, err error) {
	set := "status=$3, updated_at=now()"
	if setCompleted {
		set += ", completed_at=now()"
	}
	if clearError {
		set += ", error_message=NULL"
	}
	tag, err := s.pool.Exec(ctx,
		`UPDATE entity_research_jobs SET `+set+` WHERE book_id=$1 AND job_id=$2 AND status = ANY($4::text[])`,
		bookID, jobID, to, from)
	if err != nil {
		return false, false, err
	}
	if tag.RowsAffected() == 1 {
		return true, true, nil
	}
	var exists bool
	if e := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM entity_research_jobs WHERE book_id=$1 AND job_id=$2)`,
		bookID, jobID).Scan(&exists); e != nil {
		return false, false, e
	}
	return exists, false, nil
}
