package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

func seedEPUBP0Job(t *testing.T, ctx context.Context, s *Server, owner, bookID uuid.UUID, options string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	sourceID := uuid.New()
	jobID := uuid.New()
	if _, err := s.pool.Exec(ctx, `INSERT INTO import_sources(id,owner_user_id,original_filename,object_key,sha256,compressed_size,metadata_json) VALUES($1,$2,'book.epub','imports/source.epub',$3,10,'{}')`, sourceID, owner, uuid.NewString()); err != nil {
		t.Fatal(err)
	}
	if _, err := s.pool.Exec(ctx, `INSERT INTO import_jobs(id,book_id,user_id,status,filename,file_format,file_size,file_storage_key,source_id,target_mode,options_json,pipeline_version) VALUES($1,$2,$3,'completed','book.epub','epub',10,'imports/source.epub',$4,'existing_book',$5,'epub-v2')`, jobID, bookID, owner, sourceID, options); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = s.pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	return jobID, sourceID
}

func TestEPUBImportStrategiesAndRollback_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chapterID := seedChapter(t, ctx, pool, owner)
	jobID, _ := seedEPUBP0Job(t, ctx, s, owner, bookID, `{"strategy":"replace_all"}`)

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.applyEPUBImportStrategy(ctx, tx, jobID, bookID, []byte(`{"strategy":"replace_all"}`)); err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	// A retry before rollback sees the already-trashed row and creates no second effect.
	tx, _ = pool.Begin(ctx)
	if err := s.applyEPUBImportStrategy(ctx, tx, jobID, bookID, []byte(`{"strategy":"replace_all"}`)); err != nil {
		t.Fatal(err)
	}
	_ = tx.Commit(ctx)
	var effects int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM import_job_effects WHERE job_id=$1 AND effect_type='replace_all_chapter'`, jobID).Scan(&effects); err != nil || effects != 1 {
		t.Fatalf("replace_all effects = %d, err=%v; want one", effects, err)
	}
	var state string
	if err := pool.QueryRow(ctx, `SELECT lifecycle_state FROM chapters WHERE id=$1`, chapterID).Scan(&state); err != nil || state != "trashed" {
		t.Fatalf("replace_all lifecycle = %q, err=%v; want trashed", state, err)
	}

	tx, err = pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	conflicts := make([]any, 0)
	if err := s.rollbackEPUBImportStrategy(ctx, tx, jobID, bookID, &conflicts); err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT lifecycle_state FROM chapters WHERE id=$1`, chapterID).Scan(&state); err != nil || state != "active" {
		t.Fatalf("rollback lifecycle = %q, err=%v; want active", state, err)
	}

}

func TestEPUBImportMetadataMergeAndUserConflict_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	jobID, _ := seedEPUBP0Job(t, ctx, s, owner, bookID, `{"metadata_policy":{"title":"use_source","description":"use_source","language":"use_source","subjects":"merge"}}`)
	inspection := []byte(`{"metadata":{"title":"Source title","description":"Source description","language":"ru","subjects":["fantasy","history"]}}`)
	policy := []byte(`{"metadata_policy":{"title":"use_source","description":"use_source","language":"use_source","subjects":"merge"}}`)
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.applyEPUBImportMetadata(ctx, tx, jobID, bookID, "existing_book", policy, inspection); err != nil {
		t.Fatal(err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	var title, description, language string
	var subjects []string
	if err := pool.QueryRow(ctx, `SELECT title,description,original_language,genre_tags FROM books WHERE id=$1`, bookID).Scan(&title, &description, &language, &subjects); err != nil {
		t.Fatal(err)
	}
	if title != "Source title" || description != "Source description" || language != "ru" || len(subjects) != 2 {
		t.Fatalf("metadata = %q/%q/%q/%v", title, description, language, subjects)
	}

	// A later title edit must survive rollback and become a durable conflict.
	if _, err := pool.Exec(ctx, `UPDATE books SET title='User title' WHERE id=$1`, bookID); err != nil {
		t.Fatal(err)
	}
	tx, _ = pool.Begin(ctx)
	conflicts := make([]any, 0)
	if err := s.rollbackEPUBImportMetadata(ctx, tx, jobID, bookID, &conflicts); err != nil {
		t.Fatal(err)
	}
	_ = tx.Commit(ctx)
	if len(conflicts) != 1 {
		t.Fatalf("metadata rollback conflicts = %d, want one", len(conflicts))
	}
	var got string
	_ = pool.QueryRow(ctx, `SELECT title FROM books WHERE id=$1`, bookID).Scan(&got)
	if got != "User title" {
		t.Fatalf("user title was overwritten: %q", got)
	}
}

func TestEPUBImportReportIncludesWorkerWarning_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	jobID, sourceID := seedEPUBP0Job(t, ctx, s, owner, bookID, `{"strategy":"append"}`)
	warning := map[string]any{"code": "composition_materialization_pending", "message": "retry"}
	raw, _ := json.Marshal(warning)
	if _, err := pool.Exec(ctx, `INSERT INTO import_job_effects(job_id,effect_type,effect_key,after_json) VALUES($1,'job_warning','composition:composition_materialization_pending',$2)`, jobID, raw); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `UPDATE import_jobs SET report_json='{}'::jsonb WHERE id=$1`, jobID); err != nil {
		t.Fatal(err)
	}
	report, err := s.buildEPUBImportReport(ctx, jobID)
	if err != nil {
		t.Fatal(err)
	}
	if report["source_id"] != sourceID {
		t.Fatalf("report source_id = %v, want %s", report["source_id"], sourceID)
	}
	warnings, _ := report["warnings"].([]any)
	if len(warnings) != 1 {
		t.Fatalf("report warnings = %#v, want one worker warning", report["warnings"])
	}
}

func TestEPUBImportAssetReferencesConvergeForRetentionGC_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chapterID := seedChapter(t, ctx, pool, owner)
	jobID, sourceID := seedEPUBP0Job(t, ctx, s, owner, bookID, `{"strategy":"append"}`)
	assetID := uuid.New()
	if _, err := pool.Exec(ctx, `INSERT INTO import_assets(id,source_id,source_path,source_media_type,sha256,size_bytes,object_key,public_url,status) VALUES($1,$2,'Images/a.png','image/png',$3,3,'imports/assets/x/a.png','/media/books/imports/assets/x/a.png','imported')`, assetID, sourceID, uuid.NewString()); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO import_job_items(id,job_id,source_key,ordinal,status,chapter_id) VALUES($1,$2,'chapter-1',1,'active',$3)`, uuid.New(), jobID, chapterID); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_import_provenance(chapter_id,book_id,import_job_id,import_item_id,source_id,source_sha256,source_key) SELECT $1,$2,$3,id,$4,$5,'chapter-1' FROM import_job_items WHERE job_id=$3`, chapterID, bookID, jobID, sourceID, uuid.NewString()); err != nil {
		t.Fatal(err)
	}
	tx, _ := pool.Begin(ctx)
	if err := refreshEPUBImportAssetReferences(ctx, tx, sourceID); err != nil {
		t.Fatal(err)
	}
	_ = tx.Commit(ctx)
	var refs int
	var status string
	if err := pool.QueryRow(ctx, `SELECT reference_count,status FROM import_assets WHERE id=$1`, assetID).Scan(&refs, &status); err != nil {
		t.Fatal(err)
	}
	if refs != 0 || status != "orphaned" {
		t.Fatalf("unreferenced asset refs/status = %d/%s, want 0/orphaned", refs, status)
	}
	if _, err := pool.Exec(ctx, `UPDATE chapter_drafts SET body=$2 WHERE chapter_id=$1`, chapterID, `{"type":"doc","content":[{"type":"image","attrs":{"src":"/media/books/imports/assets/x/a.png"}}]}`); err != nil {
		t.Fatal(err)
	}
	tx, _ = pool.Begin(ctx)
	if err := refreshEPUBImportAssetReferences(ctx, tx, sourceID); err != nil {
		t.Fatal(err)
	}
	_ = tx.Commit(ctx)
	if err := pool.QueryRow(ctx, `SELECT reference_count,status FROM import_assets WHERE id=$1`, assetID).Scan(&refs, &status); err != nil {
		t.Fatal(err)
	}
	if refs != 1 || status != "active" {
		t.Fatalf("referenced asset refs/status = %d/%s, want 1/active", refs, status)
	}
}

func TestEPUBAssetRetentionRetriesMinIODeletion_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	_, sourceID := seedEPUBP0Job(t, ctx, s, owner, bookID, `{"strategy":"append"}`)
	assetID := uuid.New()
	const objectKey = "imports/assets/source/orphan.png"
	if _, err := pool.Exec(ctx, `
INSERT INTO import_assets(id,source_id,source_path,source_media_type,sha256,size_bytes,object_key,public_url,status,reference_count,created_at)
VALUES($1,$2,'Images/orphan.png','image/png',$3,3,$4,'/media/books/imports/assets/source/orphan.png','orphaned',0,now()-interval '8 days')
`, assetID, sourceID, uuid.NewString(), objectKey); err != nil {
		t.Fatal(err)
	}

	deleteAttempts := 0
	var allowDelete atomic.Bool
	objectStore := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet && r.URL.Path == "/book-assets/" && r.URL.Query().Has("location") {
			w.Header().Set("Content-Type", "application/xml")
			_, _ = w.Write([]byte(`<LocationConstraint>us-east-1</LocationConstraint>`))
			return
		}
		if r.Method != http.MethodDelete || r.URL.Path != "/book-assets/"+objectKey {
			t.Fatalf("unexpected object-store request: %s %s", r.Method, r.URL.Path)
		}
		deleteAttempts++
		if !allowDelete.Load() {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer objectStore.Close()
	client, err := minio.New(strings.TrimPrefix(objectStore.URL, "http://"), &minio.Options{
		Creds:  credentials.NewStaticV4("key", "secret", ""),
		Secure: false,
	})
	if err != nil {
		t.Fatal(err)
	}
	s.minio = client
	s.cfg.BooksStorageBucket = "book-assets"

	if _, err := s.reapOrphanedEPUBAssets(ctx, time.Now(), 10); err != nil {
		t.Fatalf("first retention sweep error = %v", err)
	}
	var status string
	if err := pool.QueryRow(ctx, `SELECT status FROM import_assets WHERE id=$1`, assetID).Scan(&status); err != nil {
		t.Fatal(err)
	}
	if status != "orphaned" {
		t.Fatalf("asset status after failed delete = %q, want orphaned", status)
	}
	allowDelete.Store(true)

	if _, err := s.reapOrphanedEPUBAssets(ctx, time.Now(), 10); err != nil {
		t.Fatalf("retry retention sweep error = %v", err)
	}
	if err := pool.QueryRow(ctx, `SELECT status FROM import_assets WHERE id=$1`, assetID).Scan(&status); err != nil {
		t.Fatal(err)
	}
	if status != "deleted" || deleteAttempts < 2 {
		t.Fatalf("asset status/delete attempts = %q/%d, want deleted/at least 2", status, deleteAttempts)
	}
}
