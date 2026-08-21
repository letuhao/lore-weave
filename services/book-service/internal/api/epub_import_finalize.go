package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/epubimport"
)

type epubStagingPayload struct {
	SourceKey  string            `json:"source_key"`
	Title      string            `json:"title"`
	TiptapJSON json.RawMessage   `json:"tiptap_json"`
	Links      []epubStagingLink `json:"links"`
	Scenes     []struct {
		SortOrder   int    `json:"sort_order"`
		Path        string `json:"path"`
		LeafText    string `json:"leaf_text"`
		ContentHash string `json:"content_hash"`
	} `json:"scenes"`
}

type materializedEPUBImportChapter struct {
	itemID         uuid.UUID
	chapterID      uuid.UUID
	revisionID     uuid.UUID
	sourceKey      string
	sourceHref     string
	sourceFragment string
	tiptapJSON     json.RawMessage
	links          []epubStagingLink
}

type stagedEPUBImportItem struct {
	itemID         uuid.UUID
	sourceKey      string
	title          string
	sourceHref     *string
	sourceFragment *string
	sourceHash     *string
	stagingPayload []byte
}

func (s *Server) finalizeEPUBImport(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	defer func() { EPUBImportDurationSeconds.Observe(time.Since(started).Seconds()) }()
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	created, err := s.materializeEPUBImport(r.Context(), jobID)
	if err != nil {
		EPUBImportJobsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusConflict, "IMPORT_FINALIZE_FAILED", err.Error())
		return
	}
	EPUBImportJobsTotal.WithLabelValues("success").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"job_id": jobID, "chapters_created": created, "status": "completed"})
}

// materializeEPUBImport is idempotent by immutable chapter provenance. It is
// intentionally Book-owned: workers submit staging JSON but never write book
// tables directly.
func (s *Server) materializeEPUBImport(ctx context.Context, jobID uuid.UUID) (int, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)
	var bookID, sourceID, userID uuid.UUID
	var sourceSHA, language, status, targetMode, sourceObjectKey string
	var optionsJSON, inspectionJSON []byte
	var progressTotal int
	err = tx.QueryRow(ctx, `
SELECT j.book_id,j.source_id,j.user_id,s.sha256,COALESCE(s.metadata_json->>'language','und'),j.status,j.progress_total,j.target_mode,j.options_json,s.object_key,s.inspection_json
FROM import_jobs j JOIN import_sources s ON s.id=j.source_id
WHERE j.id=$1 AND j.pipeline_version=$2 FOR UPDATE`, jobID, epubImportPipelineVersion).
		Scan(&bookID, &sourceID, &userID, &sourceSHA, &language, &status, &progressTotal, &targetMode, &optionsJSON, &sourceObjectKey, &inspectionJSON)
	if err != nil {
		return 0, fmt.Errorf("load import job: %w", err)
	}
	if status == "completed" || status == "completed_with_warnings" {
		var existing int
		_ = tx.QueryRow(ctx, `SELECT chapters_created FROM import_jobs WHERE id=$1`, jobID).Scan(&existing)
		return existing, tx.Commit(ctx)
	}
	var pending, processing, failed int
	if err := tx.QueryRow(ctx, `SELECT count(*) FILTER (WHERE selected AND status='pending'), count(*) FILTER (WHERE selected AND status='processing'), count(*) FILTER (WHERE selected AND status='failed') FROM import_job_items WHERE job_id=$1`, jobID).Scan(&pending, &processing, &failed); err != nil {
		return 0, err
	}
	if !canFinalizeEPUBImport(pending, processing, failed) {
		return 0, fmt.Errorf("import items are not ready")
	}
	if err := s.applyEPUBImportStrategy(ctx, tx, jobID, bookID, optionsJSON); err != nil {
		return 0, err
	}
	var nextSort int
	if err := tx.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0)+1 FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID).Scan(&nextSort); err != nil {
		return 0, err
	}
	rows, err := tx.Query(ctx, `
SELECT id,source_key,COALESCE(title,''),source_href,source_fragment,source_hash,staging_payload
FROM import_job_items
WHERE job_id=$1 AND selected AND status='import_ready'
ORDER BY ordinal
`, jobID)
	if err != nil {
		return 0, err
	}
	defer rows.Close()
	stagedItems := make([]stagedEPUBImportItem, 0)
	for rows.Next() {
		var item stagedEPUBImportItem
		if err := rows.Scan(&item.itemID, &item.sourceKey, &item.title, &item.sourceHref, &item.sourceFragment, &item.sourceHash, &item.stagingPayload); err != nil {
			return 0, err
		}
		stagedItems = append(stagedItems, item)
	}
	if err := rows.Err(); err != nil {
		return 0, err
	}
	rows.Close()

	created := 0
	materialized := make([]materializedEPUBImportChapter, 0, len(stagedItems))
	for _, item := range stagedItems {
		var existing uuid.UUID
		err := tx.QueryRow(ctx, `SELECT chapter_id FROM chapter_import_provenance WHERE book_id=$1 AND source_sha256=$2 AND source_key=$3`, bookID, sourceSHA, item.sourceKey).Scan(&existing)
		if err == nil {
			if _, err := tx.Exec(ctx, `UPDATE import_job_items SET chapter_id=$2,status='active',updated_at=now() WHERE id=$1`, item.itemID, existing); err != nil {
				return 0, err
			}
			continue
		}
		if err != pgx.ErrNoRows {
			return 0, err
		}
		var staging epubStagingPayload
		if err := json.Unmarshal(item.stagingPayload, &staging); err != nil || !json.Valid(staging.TiptapJSON) {
			return 0, fmt.Errorf("invalid staging payload")
		}
		if staging.Title != "" {
			item.title = staging.Title
		}
		chapterID := uuid.New()
		storageKey := fmt.Sprintf("chapters/%s/import-%s-%d", bookID, jobID, nextSort)
		if _, err := tx.Exec(ctx, `INSERT INTO chapters(id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,draft_updated_at,updated_at) VALUES($1,$2,$3,$4,$5,'application/json',$6,$7,$8,'active',now(),now())`, chapterID, bookID, nullableString(item.title), "epub-import.epub", importedLanguage(language), len(staging.TiptapJSON), nextSort, storageKey); err != nil {
			return 0, err
		}
		if _, err := tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id,body,draft_format,draft_updated_at,draft_version) VALUES($1,$2,'json',now(),1)`, chapterID, staging.TiptapJSON); err != nil {
			return 0, err
		}
		var revisionID uuid.UUID
		if err := tx.QueryRow(ctx, `INSERT INTO chapter_revisions(chapter_id,body,body_format,message,author_user_id) VALUES($1,$2,'json','imported from EPUB',$3) RETURNING id`, chapterID, staging.TiptapJSON, userID).Scan(&revisionID); err != nil {
			return 0, err
		}
		if _, err := tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1,editorial_status='published',published_revision_id=$2,kg_indexed_revision_id=$2,last_parsed_revision_id=$2 WHERE id=$1`, chapterID, revisionID); err != nil {
			return 0, err
		}
		for _, scene := range staging.Scenes {
			if _, err := tx.Exec(ctx, `INSERT INTO scenes(chapter_id,book_id,sort_order,path,leaf_text,content_hash,parse_version) VALUES($1,$2,$3,$4,$5,$6,1)`, chapterID, bookID, scene.SortOrder, scene.Path, scene.LeafText, scene.ContentHash); err != nil {
				return 0, err
			}
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO chapter_import_provenance(
  chapter_id,book_id,import_job_id,import_item_id,source_id,source_sha256,source_key,
  source_href,source_fragment,source_hash,finalized_at
) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,now())
`, chapterID, bookID, jobID, item.itemID, sourceID, sourceSHA, item.sourceKey, item.sourceHref, item.sourceFragment, item.sourceHash); err != nil {
			return 0, err
		}
		if _, err := tx.Exec(ctx, `UPDATE import_job_items SET chapter_id=$2,status='active',updated_at=now() WHERE id=$1`, item.itemID, chapterID); err != nil {
			return 0, err
		}
		materialized = append(materialized, materializedEPUBImportChapter{
			itemID: item.itemID, chapterID: chapterID, revisionID: revisionID,
			sourceKey:  item.sourceKey,
			sourceHref: dereferenceString(item.sourceHref), sourceFragment: dereferenceString(item.sourceFragment),
			tiptapJSON: staging.TiptapJSON, links: staging.Links,
		})
		created++
		nextSort++
	}
	if err := rewriteMaterializedEPUBLinks(ctx, tx, bookID, jobID, materialized); err != nil {
		return 0, err
	}
	if err := refreshEPUBImportAssetReferences(ctx, tx, sourceID); err != nil {
		return 0, err
	}
	metadataApplied, err := s.applyEPUBImportMetadata(ctx, tx, jobID, bookID, targetMode, optionsJSON, inspectionJSON)
	if err != nil {
		return 0, err
	}
	var coverWarning *epubimport.Diagnostic
	if shouldApplyEPUBImportCover(targetMode, optionsJSON) {
		var inspection epubimport.Inspection
		if err := json.Unmarshal(inspectionJSON, &inspection); err != nil {
			return 0, fmt.Errorf("decode EPUB source inspection: %w", err)
		}
		coverApplied, warning, err := s.applyEPUBImportCover(ctx, tx, jobID, bookID, sourceObjectKey, inspection)
		if err != nil {
			return 0, err
		}
		if coverApplied {
			metadataApplied = append(metadataApplied, "cover")
		}
		coverWarning = warning
	}
	var warningCount int
	if err := tx.QueryRow(ctx, `
SELECT count(*)
FROM import_job_items
WHERE job_id=$1 AND selected
  AND jsonb_array_length(CASE WHEN jsonb_typeof(warnings_json) = 'array' THEN warnings_json ELSE '[]'::jsonb END) > 0
`, jobID).Scan(&warningCount); err != nil {
		return 0, err
	}
	finalStatus := "completed"
	if warningCount > 0 || coverWarning != nil {
		finalStatus = "completed_with_warnings"
	}
	warnings := []any{}
	if coverWarning != nil {
		warnings = append(warnings, coverWarning)
	}
	report, _ := json.Marshal(map[string]any{"job_id": jobID, "status": finalStatus, "chapters_created": created, "warnings": warnings, "errors": []any{}, "metadata_applied": metadataApplied})
	if _, err := tx.Exec(ctx, `UPDATE import_jobs SET status=$2,chapters_created=$3,report_json=$4,finalized_at=now(),completed_at=now(),updated_at=now() WHERE id=$1`, jobID, finalStatus, created, report); err != nil {
		return 0, err
	}
	if err := emitJobEvent(ctx, tx, jobID, userID, "book_import", finalStatus, map[string]any{"progress": map[string]any{"done": progressTotal, "total": progressTotal}}); err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return created, nil
}

func canFinalizeEPUBImport(pending, processing, failed int) bool {
	return pending == 0 && processing == 0 && failed == 0
}

func rewriteMaterializedEPUBLinks(ctx context.Context, tx pgx.Tx, bookID, jobID uuid.UUID, materialized []materializedEPUBImportChapter) error {
	if len(materialized) == 0 {
		return nil
	}
	rows, err := tx.Query(ctx, `
SELECT chapter_id,COALESCE(source_href,''),COALESCE(source_fragment,'')
FROM import_job_items
WHERE job_id=$1 AND selected AND status='active' AND chapter_id IS NOT NULL
ORDER BY ordinal
`, jobID)
	if err != nil {
		return err
	}
	targets := make([]epubChapterLinkTarget, 0)
	for rows.Next() {
		var target epubChapterLinkTarget
		if err := rows.Scan(&target.ChapterID, &target.SourceHref, &target.SourceFragment); err != nil {
			rows.Close()
			return err
		}
		targets = append(targets, target)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return err
	}
	rows.Close()
	for _, chapter := range materialized {
		rewritten, warnings, err := rewriteEPUBInternalLinks(chapter.tiptapJSON, bookID,
			epubChapterLinkTarget{ChapterID: chapter.chapterID, SourceHref: chapter.sourceHref, SourceFragment: chapter.sourceFragment}, chapter.links, targets)
		if err != nil {
			return fmt.Errorf("rewrite chapter links: %w", err)
		}
		if string(rewritten) != string(chapter.tiptapJSON) {
			if _, err := tx.Exec(ctx, `UPDATE chapter_drafts SET body=$2 WHERE chapter_id=$1`, chapter.chapterID, rewritten); err != nil {
				return err
			}
			if _, err := tx.Exec(ctx, `UPDATE chapter_revisions SET body=$2 WHERE id=$1`, chapter.revisionID, rewritten); err != nil {
				return err
			}
			if _, err := tx.Exec(ctx, `UPDATE chapters SET byte_size=$2 WHERE id=$1`, chapter.chapterID, len(rewritten)); err != nil {
				return err
			}
		}
		if len(warnings) > 0 {
			for index := range warnings {
				warnings[index].SourceKey = chapter.sourceKey
			}
			encoded, err := json.Marshal(warnings)
			if err != nil {
				return err
			}
			if _, err := tx.Exec(ctx, `UPDATE import_job_items SET warnings_json=warnings_json || $2::jsonb,updated_at=now() WHERE id=$1`, chapter.itemID, encoded); err != nil {
				return err
			}
		}
	}
	return nil
}

func dereferenceString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}
