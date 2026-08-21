package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/google/uuid"
)

type epubRollbackResult struct {
	JobID              uuid.UUID `json:"job_id"`
	Status             string    `json:"status"`
	ChaptersRolledBack int       `json:"chapters_rolled_back"`
	Conflicts          []any     `json:"conflicts"`
}

type rollbackEPUBImportRequest struct {
	Confirm bool `json:"confirm"`
}

// rollbackEpubImportJob compensates only results owned by this import. A
// chapter changed after its provenance was finalized is deliberately retained:
// rollback must never erase a user's later work.
func (s *Server) rollbackEpubImportJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantEdit); !allowed {
		return
	}
	var in rollbackEPUBImportRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || !in.Confirm {
		writeError(w, http.StatusBadRequest, "ROLLBACK_CONFIRMATION_REQUIRED", "confirm=true is required to roll back an import")
		return
	}
	result, err := s.rollbackEPUBImport(r.Context(), jobID)
	if err != nil {
		writeError(w, http.StatusConflict, "IMPORT_ROLLBACK_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, result)
}

// rollbackEPUBImport is safe to retry. Its row lock serializes concurrent
// attempts, and a completed rollback returns the original durable result.
func (s *Server) rollbackEPUBImport(ctx context.Context, jobID uuid.UUID) (epubRollbackResult, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return epubRollbackResult{}, err
	}
	defer tx.Rollback(ctx)

	var userID, bookID, sourceID uuid.UUID
	var status string
	var priorReport []byte
	if err := tx.QueryRow(ctx, `
SELECT user_id,book_id,source_id,status,COALESCE(report_json,'{}'::jsonb)
FROM import_jobs WHERE id=$1 AND pipeline_version=$2 FOR UPDATE
`, jobID, epubImportPipelineVersion).Scan(&userID, &bookID, &sourceID, &status, &priorReport); err != nil {
		return epubRollbackResult{}, fmt.Errorf("load import job: %w", err)
	}
	if status == "rolled_back" {
		var prior struct {
			ChaptersRolledBack int   `json:"chapters_rolled_back"`
			RollbackConflicts  []any `json:"rollback_conflicts"`
		}
		_ = json.Unmarshal(priorReport, &prior)
		if err := tx.Commit(ctx); err != nil {
			return epubRollbackResult{}, err
		}
		result := epubRollbackResult{JobID: jobID, Status: status, ChaptersRolledBack: prior.ChaptersRolledBack, Conflicts: prior.RollbackConflicts}
		if err := s.cleanupEPUBImportComposition(ctx, jobID, bookID, userID); err != nil {
			warning := map[string]any{"code": "composition_rollback_pending", "message": "Composition hierarchy cleanup will be retried.", "error": err.Error()}
			encoded, _ := json.Marshal(warning)
			_, _ = s.pool.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,after_json) VALUES($1,'rollback_warning','composition',$2) ON CONFLICT (job_id,effect_type,effect_key) DO UPDATE SET after_json=EXCLUDED.after_json,applied_at=now()`, jobID, encoded)
			result.Conflicts = append(result.Conflicts, warning)
		}
		return result, nil
	}
	if status != "completed" && status != "completed_with_warnings" {
		return epubRollbackResult{}, fmt.Errorf("import job is not rollbackable")
	}

	rows, err := tx.Query(ctx, `
SELECT p.chapter_id,p.import_item_id,
       c.updated_at > GREATEST(p.finalized_at, COALESCE(h.latest_hierarchy_applied_at, p.finalized_at))
FROM chapter_import_provenance p
JOIN chapters c ON c.id=p.chapter_id
LEFT JOIN LATERAL (
  SELECT max(applied_at) AS latest_hierarchy_applied_at
  FROM import_job_hierarchy_mappings h
  WHERE h.job_id=p.import_job_id AND h.chapter_id=p.chapter_id AND h.rolled_back_at IS NULL
) h ON true
WHERE p.import_job_id=$1
ORDER BY p.chapter_id
FOR UPDATE OF p,c
`, jobID)
	if err != nil {
		return epubRollbackResult{}, err
	}
	type rollbackCandidate struct {
		chapterID    uuid.UUID
		itemID       uuid.UUID
		userModified bool
	}
	candidates := make([]rollbackCandidate, 0)
	for rows.Next() {
		var candidate rollbackCandidate
		if err := rows.Scan(&candidate.chapterID, &candidate.itemID, &candidate.userModified); err != nil {
			rows.Close()
			return epubRollbackResult{}, err
		}
		candidates = append(candidates, candidate)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return epubRollbackResult{}, err
	}
	rows.Close()
	result := epubRollbackResult{JobID: jobID, Status: "rolled_back", Conflicts: make([]any, 0)}
	for _, candidate := range candidates {
		if candidate.userModified {
			conflict := map[string]any{"chapter_id": candidate.chapterID, "code": "rollback_conflict_user_modified"}
			result.Conflicts = append(result.Conflicts, conflict)
			conflictJSON, _ := json.Marshal(conflict)
			if _, err := tx.Exec(ctx, `
INSERT INTO import_job_effects(job_id,effect_type,effect_key,after_json)
VALUES($1,'rollback_conflict',$2,$3)
ON CONFLICT (job_id,effect_type,effect_key) DO NOTHING
	`, jobID, candidate.chapterID.String(), conflictJSON); err != nil {
				return epubRollbackResult{}, err
			}
			continue
		}
		if _, err := tx.Exec(ctx, `
UPDATE chapters c
SET structure_node_id=h.prior_structure_node_id,updated_at=now()
FROM import_job_hierarchy_mappings h
WHERE h.job_id=$1 AND h.chapter_id=c.id AND h.rolled_back_at IS NULL AND c.id=$2
`, jobID, candidate.chapterID); err != nil {
			return epubRollbackResult{}, err
		}
		if _, err := tx.Exec(ctx, `UPDATE import_job_hierarchy_mappings SET rolled_back_at=now() WHERE job_id=$1 AND chapter_id=$2 AND rolled_back_at IS NULL`, jobID, candidate.chapterID); err != nil {
			return epubRollbackResult{}, err
		}
		if _, err := tx.Exec(ctx, `DELETE FROM chapters WHERE id=$1`, candidate.chapterID); err != nil {
			return epubRollbackResult{}, err
		}
		if _, err := tx.Exec(ctx, `UPDATE import_job_items SET status='rolled_back',chapter_id=NULL,updated_at=now() WHERE id=$1`, candidate.itemID); err != nil {
			return epubRollbackResult{}, err
		}
		result.ChaptersRolledBack++
	}
	if err := s.rollbackEPUBImportStrategy(ctx, tx, jobID, bookID, &result.Conflicts); err != nil {
		return epubRollbackResult{}, err
	}
	if err := s.rollbackEPUBImportMetadata(ctx, tx, jobID, bookID, &result.Conflicts); err != nil {
		return epubRollbackResult{}, err
	}
	if err := refreshEPUBImportAssetReferences(ctx, tx, sourceID); err != nil {
		return epubRollbackResult{}, err
	}
	if err := rollbackEPUBImportCover(ctx, tx, jobID, bookID, &result.Conflicts); err != nil {
		return epubRollbackResult{}, err
	}
	report, err := json.Marshal(map[string]any{
		"status":               result.Status,
		"chapters_rolled_back": result.ChaptersRolledBack,
		"rollback_conflicts":   result.Conflicts,
	})
	if err != nil {
		return epubRollbackResult{}, err
	}
	if _, err := tx.Exec(ctx, `
UPDATE import_jobs
SET status='rolled_back',rolled_back_at=now(),report_json=report_json || $2::jsonb,updated_at=now()
WHERE id=$1
`, jobID, report); err != nil {
		return epubRollbackResult{}, err
	}
	if err := emitJobEvent(ctx, tx, jobID, userID, "book_import", "rolled_back", map[string]any{"progress": map[string]any{"done": result.ChaptersRolledBack}}); err != nil {
		return epubRollbackResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return epubRollbackResult{}, err
	}
	if err := s.cleanupEPUBImportComposition(ctx, jobID, bookID, userID); err != nil {
		warning := map[string]any{"code": "composition_rollback_pending", "message": "Composition hierarchy cleanup will be retried.", "error": err.Error()}
		encoded, _ := json.Marshal(warning)
		_, _ = s.pool.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,after_json) VALUES($1,'rollback_warning','composition',$2) ON CONFLICT (job_id,effect_type,effect_key) DO UPDATE SET after_json=EXCLUDED.after_json,applied_at=now()`, jobID, encoded)
		result.Conflicts = append(result.Conflicts, warning)
	}
	return result, nil
}

func (s *Server) cleanupEPUBImportComposition(ctx context.Context, jobID, bookID, userID uuid.UUID) error {
	if s.cfg == nil || strings.TrimSpace(s.cfg.CompositionServiceURL) == "" {
		return nil
	}
	endpoint := strings.TrimRight(s.cfg.CompositionServiceURL, "/") + "/internal/composition/books/" + url.PathEscape(bookID.String()) + "/epub-import-hierarchy/" + url.PathEscape(jobID.String()) + "?caller_user_id=" + url.QueryEscape(userID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, endpoint, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("composition cleanup returned status %d", resp.StatusCode)
	}
	return nil
}
