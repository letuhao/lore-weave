package api

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

// canonical_translation_handler.go — the per-episode translation surface (spec §6B/§7.6).
//
// On-demand, immutable TRANSLATION of an entity's as-of folded canonical into the reader's
// display language, cached in canonical_snapshot_translations (migration 0050). Mirror of
// knowledge-service's KG-TL M3 event-text cache: read-through with a single-flight background
// fill that calls translation-service (BYOK MT via provider-registry — no LLM in glossary).
//
//	GET /internal/books/{book_id}/entities/{entity_id}/canonical-translation?as_of=&lang=
//
// The `lang` is a REAL target language (the FE shows the original canonical directly when the
// reader picks the book's source/as-authored language, so this path never gets source==target).
// `as_of` is accepted for parity with get_canonical; the underlying snapshot read returns the
// fresh head (as get_canonical does today — as-of-N projection is a later foundation slice).
//
// Statuses (FE polls while `translating`): ready | translating | failed | unbuildable.

// getCanonicalContent returns the entity's current canonical prose (fresh head snapshot, else the
// degrade-to-canon-content fallback) — the same read internalGetCanonical serves, hoisted so the
// translation surface reuses it byte-for-byte. content is "" only when nothing is buildable.
func (s *Server) getCanonicalContent(ctx context.Context, entityID, bookID uuid.UUID) (content string, asOf int64, canonStatus string) {
	err := s.pool.QueryRow(ctx, `
		SELECT cs.content, cs.as_of_ordinal, cs.canonical_status
		FROM canonical_snapshot cs
		WHERE cs.entity_id = $1 AND cs.attr_scope = 'narrative'
		  AND cs.fact_coverage_xid IS NOT NULL
		  AND NOT EXISTS (
		    SELECT 1 FROM entity_facts ef
		    WHERE ef.entity_id = cs.entity_id AND ef.invalidated_at IS NULL
		      AND ef.coverage_xid > cs.fact_coverage_xid
		  )
		ORDER BY cs.as_of_ordinal DESC, cs.built_at DESC
		LIMIT 1`, entityID).Scan(&content, &asOf, &canonStatus)
	if err == nil {
		return content, asOf, canonStatus
	}
	// Degrade: the existing canon-content (short_description) is a real, bounded canonical.
	var degraded *string
	_ = s.pool.QueryRow(ctx,
		`SELECT short_description FROM glossary_entities WHERE entity_id = $1 AND book_id = $2`,
		entityID, bookID).Scan(&degraded)
	if degraded != nil {
		return *degraded, 0, "stale"
	}
	return "", 0, "unbuildable"
}

func md5hex(s string) string {
	sum := md5.Sum([]byte(s))
	return hex.EncodeToString(sum[:])
}

// writeCanonicalTranslation emits the uniform response shape the KAL forwards to the FE.
func writeCanonicalTranslation(w http.ResponseWriter, entityID uuid.UUID, lang, content string,
	translated bool, status, errCode string, asOf int64, canonStatus string, cached bool) {
	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":        entityID.String(),
		"language_code":    lang,
		"content":          content,
		"translated":       translated,
		"status":           status,
		"error_code":       errCode,
		"as_of_ordinal":    asOf,
		"canonical_status": canonStatus,
		"cached":           cached,
		"source":           "snapshot-translation",
	})
}

// internalGetCanonicalTranslation is the KAL get_canonical_translation target.
func (s *Server) internalGetCanonicalTranslation(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}
	lang := strings.TrimSpace(r.URL.Query().Get("lang"))
	if lang == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "lang query param is required")
		return
	}
	userID := strings.TrimSpace(r.Header.Get("X-User-Id"))

	ctx := r.Context()
	content, asOf, canonStatus := s.getCanonicalContent(ctx, entityID, bookID)
	content = strings.TrimSpace(content)
	if content == "" {
		writeCanonicalTranslation(w, entityID, lang, "", false, "unbuildable", "", asOf, canonStatus, false)
		return
	}
	hash := md5hex(content)

	// Cache lookup.
	var (
		cStatus, cValue, cErr string
		cAttempts             int
	)
	err := s.pool.QueryRow(ctx, `
		SELECT status, value, error_code, attempts
		FROM canonical_snapshot_translations
		WHERE entity_id=$1 AND attr_scope='narrative' AND language_code=$2 AND source_content_hash=$3`,
		entityID, lang, hash).Scan(&cStatus, &cValue, &cErr, &cAttempts)
	if err == nil {
		switch cStatus {
		case "ready":
			writeCanonicalTranslation(w, entityID, lang, cValue, true, "ready", "", asOf, canonStatus, true)
			return
		case "pending":
			writeCanonicalTranslation(w, entityID, lang, content, false, "translating", "", asOf, canonStatus, false)
			return
		case "failed":
			// Re-claim a failed row while attempts remain AND a fill is actually possible.
			if cAttempts < foldRetryBudget && userID != "" && s.cfg.TranslationServiceURL != "" {
				tag, uerr := s.pool.Exec(ctx, `
					UPDATE canonical_snapshot_translations
					   SET status='pending', error_code='', attempts=attempts+1, updated_at=now()
					 WHERE entity_id=$1 AND attr_scope='narrative' AND language_code=$2 AND source_content_hash=$3
					   AND status='failed'`, entityID, lang, hash)
				if uerr == nil && tag.RowsAffected() == 1 {
					s.launchSnapshotFill(entityID, lang, hash, content, userID)
					writeCanonicalTranslation(w, entityID, lang, content, false, "translating", "", asOf, canonStatus, false)
					return
				}
			}
			writeCanonicalTranslation(w, entityID, lang, content, false, "failed", cErr, asOf, canonStatus, false)
			return
		}
	}

	// Cache miss. A fill needs the user (BYOK model) + a configured translation-service.
	if userID == "" {
		writeCanonicalTranslation(w, entityID, lang, content, false, "failed", "no_user", asOf, canonStatus, false)
		return
	}
	if s.cfg.TranslationServiceURL == "" {
		writeCanonicalTranslation(w, entityID, lang, content, false, "failed", "unconfigured", asOf, canonStatus, false)
		return
	}
	// Single-flight claim: only the request that wins the INSERT launches the fill.
	tag, ierr := s.pool.Exec(ctx, `
		INSERT INTO canonical_snapshot_translations
		  (entity_id, attr_scope, language_code, source_content_hash, as_of_ordinal, status, attempts, minted_by_user_id, book_id)
		VALUES ($1,'narrative',$2,$3,$4,'pending',1,$5,$6)
		ON CONFLICT (entity_id, attr_scope, language_code, source_content_hash) DO NOTHING`,
		entityID, lang, hash, asOf, userID, bookID)
	if ierr != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "translation claim failed")
		return
	}
	if tag.RowsAffected() == 1 {
		s.launchSnapshotFill(entityID, lang, hash, content, userID)
	}
	// Whether we claimed or a concurrent request did, the row is now pending → translating.
	writeCanonicalTranslation(w, entityID, lang, content, false, "translating", "", asOf, canonStatus, false)
}

// launchSnapshotFill runs the (bounded) MT off the request goroutine and settles the cache row to
// 'ready' (value) or 'failed' (error_code). Detached context so a client disconnect doesn't cancel
// the fill mid-flight (the next poll picks up the settled row). Best-effort — errors are absorbed.
func (s *Server) launchSnapshotFill(entityID uuid.UUID, lang, hash, content, userID string) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
		defer cancel()
		out, errCode := s.translateText(ctx, userID, content, "auto", lang)
		if errCode != "" {
			_, _ = s.pool.Exec(ctx, `
				UPDATE canonical_snapshot_translations
				   SET status='failed', error_code=$4, updated_at=now()
				 WHERE entity_id=$1 AND attr_scope='narrative' AND language_code=$2 AND source_content_hash=$3
				   AND status='pending'`, entityID, lang, hash, errCode)
			return
		}
		_, _ = s.pool.Exec(ctx, `
			UPDATE canonical_snapshot_translations
			   SET status='ready', value=$4, error_code='', updated_at=now()
			 WHERE entity_id=$1 AND attr_scope='narrative' AND language_code=$2 AND source_content_hash=$3`,
			entityID, lang, hash, out)
	}()
}
