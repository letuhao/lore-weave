package api

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// applyEPUBImportStrategy makes replace_all a durable, repeatable operation.
// append and merge_by_source_key deliberately leave existing chapters intact;
// immutable provenance then makes both a redelivery and a repeated import
// converge without duplicate source items.
func (s *Server) applyEPUBImportStrategy(ctx context.Context, tx pgx.Tx, jobID, bookID uuid.UUID, optionsJSON []byte) error {
	var options struct {
		Strategy string `json:"strategy"`
	}
	if err := json.Unmarshal(optionsJSON, &options); err != nil {
		return fmt.Errorf("decode import strategy: %w", err)
	}
	if options.Strategy != "replace_all" {
		return nil
	}
	rows, err := tx.Query(ctx, `
SELECT id,lifecycle_state,COALESCE(trashed_at::text,''),updated_at
FROM chapters
WHERE book_id=$1 AND lifecycle_state='active'
  AND NOT EXISTS (SELECT 1 FROM chapter_import_provenance p WHERE p.chapter_id=chapters.id AND p.import_job_id=$2)
FOR UPDATE`, bookID, jobID)
	if err != nil {
		return err
	}
	type replaceAllCandidate struct {
		chapterID uuid.UUID
		state     string
		trashedAt string
	}
	candidates := make([]replaceAllCandidate, 0)
	for rows.Next() {
		var candidate replaceAllCandidate
		var updatedAt interface{}
		if err := rows.Scan(&candidate.chapterID, &candidate.state, &candidate.trashedAt, &updatedAt); err != nil {
			return err
		}
		candidates = append(candidates, candidate)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	rows.Close()
	for _, candidate := range candidates {
		before, _ := json.Marshal(map[string]string{"lifecycle_state": candidate.state, "trashed_at": candidate.trashedAt})
		if _, err := tx.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,before_json,after_json) VALUES($1,'replace_all_chapter',$2,$3,'{"lifecycle_state":"trashed"}'::jsonb) ON CONFLICT (job_id,effect_type,effect_key) DO NOTHING`, jobID, candidate.chapterID.String(), before); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed',trashed_at=now(),updated_at=now() WHERE id=$1`, candidate.chapterID); err != nil {
			return err
		}
	}
	return nil
}
