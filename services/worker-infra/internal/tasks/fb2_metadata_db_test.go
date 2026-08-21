package tasks

import (
	"context"
	"encoding/base64"
	"testing"

	"github.com/google/uuid"
)

// This integration regression proves the data-consistency boundary between the
// two FB2 modes. It needs an already-migrated isolated book database through
// BOOK_TEST_DATABASE_URL; bookTestPool skips it safely when that service is not
// available, matching the other worker DB regressions.
func TestPersistFB2Metadata_ProjectsOnlyCreatedBooks(t *testing.T) {
	pool := bookTestPool(t)
	ctx := context.Background()
	owner := uuid.New()
	createdBook, existingBook := uuid.New(), uuid.New()
	createdJob, existingJob := uuid.New(), uuid.New()
	for _, seed := range []struct {
		book, job uuid.UUID
		title     string
		create    bool
	}{
		{createdBook, createdJob, "placeholder", true},
		{existingBook, existingJob, "authored title", false},
	} {
		if _, err := pool.Exec(ctx, `INSERT INTO books(id,owner_user_id,title) VALUES($1,$2,$3)`, seed.book, owner, seed.title); err != nil {
			t.Fatalf("seed book: %v", err)
		}
		if _, err := pool.Exec(ctx, `INSERT INTO import_jobs(id,book_id,user_id,status,filename,file_format,file_size,file_storage_key,create_book_from_metadata) VALUES($1,$2,$3,'pending','fixture.fb2','fb2',1,'fixture',$4)`, seed.job, seed.book, owner, seed.create); err != nil {
			t.Fatalf("seed import job: %v", err)
		}
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, createdBook)
		_, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, existingBook)
	})
	cover, err := base64.StdEncoding.DecodeString("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9xJvQAAAAASUVORK5CYII=")
	if err != nil {
		t.Fatal(err)
	}
	doc := &fb2Document{Title: "Source title", Language: "ru", Summary: "Source summary", Genres: []string{"sf_fantasy"}, Metadata: map[string]any{"title_info": map[string]any{"title": "Source title"}}, Cover: &fb2Binary{ContentType: "image/png", Data: cover}}
	processor := &ImportProcessor{BookDB: pool}
	if err := processor.persistFB2Metadata(ctx, importRequestedPayload{JobID: createdJob.String(), BookID: createdBook.String(), CreateBookFromMetadata: true}, doc); err != nil {
		t.Fatalf("persist create-mode: %v", err)
	}
	if err := processor.persistFB2Metadata(ctx, importRequestedPayload{JobID: existingJob.String(), BookID: existingBook.String(), CreateBookFromMetadata: false}, doc); err != nil {
		t.Fatalf("persist existing-mode: %v", err)
	}

	var createdTitle, existingTitle string
	if err := pool.QueryRow(ctx, `SELECT title FROM books WHERE id=$1`, createdBook).Scan(&createdTitle); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT title FROM books WHERE id=$1`, existingBook).Scan(&existingTitle); err != nil {
		t.Fatal(err)
	}
	if createdTitle != "Source title" {
		t.Errorf("created title=%q, want source metadata", createdTitle)
	}
	if existingTitle != "authored title" {
		t.Errorf("existing title=%q, metadata overwrite", existingTitle)
	}
	var applied, metadataRows, covers int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM book_import_metadata WHERE import_job_id IN ($1,$2)`, createdJob, existingJob).Scan(&metadataRows); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM book_import_metadata WHERE import_job_id=$1 AND applied_to_book`, createdJob).Scan(&applied); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM book_cover_assets WHERE book_id=$1`, createdBook).Scan(&covers); err != nil {
		t.Fatal(err)
	}
	if metadataRows != 2 || applied != 1 || covers != 1 {
		t.Errorf("metadata rows=%d applied=%d covers=%d, want 2/1/1", metadataRows, applied, covers)
	}
}
