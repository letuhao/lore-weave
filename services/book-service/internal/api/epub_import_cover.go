package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"

	"github.com/loreweave/epubimport"
)

const maxEPUBImportCoverBytes = 10 << 20

type epubImportCoverEffect struct {
	ContentType string `json:"content_type"`
	ByteSize    int64  `json:"byte_size"`
	StorageKey  string `json:"storage_key"`
	Data        []byte `json:"data"`
}

func shouldApplyEPUBImportCover(targetMode string, optionsJSON []byte) bool {
	var options struct {
		MetadataPolicy map[string]string `json:"metadata_policy"`
	}
	_ = json.Unmarshal(optionsJSON, &options)
	policy := strings.ToLower(strings.TrimSpace(options.MetadataPolicy["cover"]))
	if targetMode == "new_book" {
		return policy != "keep_existing" && policy != "skip"
	}
	return policy == "use_source"
}

// applyEPUBImportCover journals the prior cover before changing it. Source
// read/validation failures are non-critical import warnings; database failures
// remain transactional errors because an unjournaled metadata mutation cannot
// be safely rolled back.
func (s *Server) applyEPUBImportCover(ctx context.Context, tx pgx.Tx, jobID, bookID uuid.UUID, sourceObjectKey string, inspection epubimport.Inspection) (bool, *epubimport.Diagnostic, error) {
	if inspection.Cover == nil {
		return false, nil, nil
	}
	if s.minio == nil {
		return false, &epubimport.Diagnostic{Code: epubimport.CodeUnsupportedResource, Message: "EPUB cover storage is unavailable"}, nil
	}
	object, err := s.minio.GetObject(ctx, s.cfg.BooksStorageBucket, sourceObjectKey, minio.GetObjectOptions{})
	if err != nil {
		return false, &epubimport.Diagnostic{Code: epubimport.CodeContentUnavailable, Message: "EPUB cover source cannot be read"}, nil
	}
	defer object.Close()
	source, err := io.ReadAll(io.LimitReader(object, maxImportSize+1))
	if err != nil || len(source) > maxImportSize {
		return false, &epubimport.Diagnostic{Code: epubimport.CodeContentUnavailable, Message: "EPUB cover source exceeds import limit"}, nil
	}
	cover, err := epubimport.ExtractCover(source, *inspection.Cover, s.cfg.EPUBImportLimits)
	if err != nil || cover.SizeBytes > maxEPUBImportCoverBytes {
		return false, &epubimport.Diagnostic{Code: epubimport.CodeUnsupportedResource, Message: "EPUB cover could not be imported"}, nil
	}
	var before epubImportCoverEffect
	err = tx.QueryRow(ctx, `SELECT content_type,byte_size,storage_key,data FROM book_cover_assets WHERE book_id=$1 FOR UPDATE`, bookID).
		Scan(&before.ContentType, &before.ByteSize, &before.StorageKey, &before.Data)
	if err != nil && err != pgx.ErrNoRows {
		return false, nil, err
	}
	var beforeJSON []byte
	if err == nil {
		beforeJSON, err = json.Marshal(before)
		if err != nil {
			return false, nil, err
		}
	} else {
		beforeJSON = []byte("null")
	}
	afterJSON, err := json.Marshal(map[string]any{"source_path": cover.SourcePath, "sha256": cover.SHA256})
	if err != nil {
		return false, nil, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,before_json,after_json) VALUES($1,'book_cover','cover',$2,$3) ON CONFLICT (job_id,effect_type,effect_key) DO NOTHING`, jobID, beforeJSON, afterJSON); err != nil {
		return false, nil, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO book_cover_assets(book_id,content_type,byte_size,storage_key,data,updated_at) VALUES($1,$2,$3,$4,$5,now()) ON CONFLICT(book_id) DO UPDATE SET content_type=EXCLUDED.content_type,byte_size=EXCLUDED.byte_size,storage_key=EXCLUDED.storage_key,data=EXCLUDED.data,updated_at=now()`, bookID, cover.MediaType, cover.SizeBytes, fmt.Sprintf("covers/%s", bookID), cover.Data); err != nil {
		return false, nil, err
	}
	return true, nil, nil
}

func rollbackEPUBImportCover(ctx context.Context, tx pgx.Tx, jobID, bookID uuid.UUID, conflicts *[]any) error {
	var beforeJSON []byte
	var appliedAt time.Time
	err := tx.QueryRow(ctx, `SELECT before_json,applied_at FROM import_job_effects WHERE job_id=$1 AND effect_type='book_cover' AND effect_key='cover' AND rolled_back_at IS NULL FOR UPDATE`, jobID).Scan(&beforeJSON, &appliedAt)
	if err == pgx.ErrNoRows {
		return nil
	}
	if err != nil {
		return err
	}
	var updatedAt time.Time
	err = tx.QueryRow(ctx, `SELECT updated_at FROM book_cover_assets WHERE book_id=$1`, bookID).Scan(&updatedAt)
	if err == nil && updatedAt.After(appliedAt) {
		*conflicts = append(*conflicts, map[string]any{"code": "rollback_conflict_user_modified_cover"})
		return nil
	}
	if err != nil && err != pgx.ErrNoRows {
		return err
	}
	if string(beforeJSON) == "null" {
		if _, err := tx.Exec(ctx, `DELETE FROM book_cover_assets WHERE book_id=$1`, bookID); err != nil {
			return err
		}
	} else {
		var before epubImportCoverEffect
		if err := json.Unmarshal(beforeJSON, &before); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `INSERT INTO book_cover_assets(book_id,content_type,byte_size,storage_key,data,updated_at) VALUES($1,$2,$3,$4,$5,now()) ON CONFLICT(book_id) DO UPDATE SET content_type=EXCLUDED.content_type,byte_size=EXCLUDED.byte_size,storage_key=EXCLUDED.storage_key,data=EXCLUDED.data,updated_at=now()`, bookID, before.ContentType, before.ByteSize, before.StorageKey, before.Data); err != nil {
			return err
		}
	}
	_, err = tx.Exec(ctx, `UPDATE import_job_effects SET rolled_back_at=now() WHERE job_id=$1 AND effect_type='book_cover' AND effect_key='cover'`, jobID)
	return err
}
