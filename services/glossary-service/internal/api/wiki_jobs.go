package api

import (
	"log/slog"
	"net/http"
)

// wiki-llm M7b — the wiki-gen JOB proxy. The PO chose a glossary-proxy surface
// (option B) so the FE talks to a single origin (/v1/glossary/...) for all wiki
// ops; glossary forwards status/resume/cancel to knowledge-service's internal
// job API. The generation TRIGGER still rides on generateWikiStubs (the model_ref
// delegate); these three cover the job lifecycle that follows it.
//
// Trust boundary: glossary does the JWT + book-owner check, then passes the owner
// user_id to knowledge over the internal token. Knowledge re-asserts ownership
// (defense-in-depth) but glossary is the authoritative gate here.

// getWikiGenJobStatus — GET /v1/glossary/books/{book_id}/wiki/job. Proxies the
// latest job status for the FE poll; the upstream 404 ("no job yet") is forwarded
// verbatim so the FE can distinguish it from a live job.
func (s *Server) getWikiGenJobStatus(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	status, body, err := s.getWikiGenJob(r.Context(), bookID, userID)
	if err != nil {
		slog.Error("getWikiGenJobStatus proxy", "error", err)
		writeError(w, http.StatusBadGateway, "WIKI_DELEGATE", "generation service unavailable")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

// getWikiGenConfig — GET /v1/glossary/books/{book_id}/wiki/gen-config. Proxies the
// flat per-article wiki-gen cost estimate so the FE can show a pre-flight cost
// estimate next to the spend cap (D-WIKI-P2B-COST-ESTIMATE). Owner-gated like the
// sibling wiki proxies; the value itself is global config, but the route lives
// under the book context the dialog is always opened in.
func (s *Server) getWikiGenConfigStatus(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	status, body, err := s.getWikiGenConfig(r.Context())
	if err != nil {
		slog.Error("getWikiGenConfig proxy", "error", err)
		writeError(w, http.StatusBadGateway, "WIKI_DELEGATE", "generation service unavailable")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

// resumeWikiGenJob — POST /v1/glossary/books/{book_id}/wiki/job/{job_id}/resume.
// Re-drives a budget-paused job. Propagates 202 / 404 (not owner) / 409 (not
// paused).
func (s *Server) resumeWikiGenJob(w http.ResponseWriter, r *http.Request) {
	s.wikiGenJobActionProxy(w, r, "resume")
}

// cancelWikiGenJob — POST /v1/glossary/books/{book_id}/wiki/job/{job_id}/cancel.
// Cancels a pending|paused job (releasing the per-book lock). Propagates 200 /
// 404 / 409.
func (s *Server) cancelWikiGenJob(w http.ResponseWriter, r *http.Request) {
	s.wikiGenJobActionProxy(w, r, "cancel")
}

func (s *Server) wikiGenJobActionProxy(w http.ResponseWriter, r *http.Request, action string) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
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
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	status, body, err := s.wikiGenJobAction(r.Context(), bookID, userID, jobID, action)
	if err != nil {
		slog.Error("wikiGenJobActionProxy", "action", action, "error", err)
		writeError(w, http.StatusBadGateway, "WIKI_DELEGATE", "generation service unavailable")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}
