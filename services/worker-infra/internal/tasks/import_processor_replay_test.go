package tasks

// #297 follow-up (Codex P1) — processImport redelivery must be replay-safe.
//
// A worker killed mid-import (the fail-fast AMQP watcher exits the process
// on a broker drop) leaves committed chapters behind, and Run reclaims the
// unacked Redis message — so processImport runs again for the same job. The
// L9 (book_id, import_job_id, structural_path) guard must make the second
// run a no-op for already-written chapters instead of duplicating them.
//
// Requires BOOK_TEST_DATABASE_URL (a migrated book DB), else skipped —
// same gating as writeback_db_test.go / fb2_metadata_db_test.go. The
// MinIO / pandoc / parse backends are local httptest fakes; only Postgres
// is real. The fakes return a fixed two-chapter document, so a redelivery
// re-parses to the identical tree — the same determinism the guard relies
// on in production.

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/loreweave/worker-infra/internal/config"
)

// replayTree is the fixed two-chapter document the parse fake returns.
const replayTree = `{"source_format":"html","parts":[{"sort_order":1,"path":"book/part-1","chapters":[
{"sort_order":1,"title":"One","path":"book/chapter-1","html":"<p>Body one.</p>","scenes":[{"sort_order":1,"path":"book/chapter-1/scene-1","leaf_text":"Body one.","content_hash":"h1"}]},
{"sort_order":2,"title":"Two","path":"book/chapter-2","html":"<p>Body two.</p>","scenes":[{"sort_order":1,"path":"book/chapter-2/scene-1","leaf_text":"Body two.","content_hash":"h2"}]}
]}]}`

// fakeMinio serves GetObject (the import file) and records every write so
// the test can prove a redelivery uploads nothing twice. minio-go signs
// requests; the fake ignores auth and answers path- and virtual-host-style
// paths alike.
type fakeMinio struct {
	mu      sync.Mutex
	gets    []string
	puts    []string
	deletes []string
}

func (f *fakeMinio) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	key := strings.TrimPrefix(r.URL.Path, "/")
	key = strings.TrimPrefix(key, "test-bucket/")
	f.mu.Lock()
	defer f.mu.Unlock()
	switch r.Method {
	case http.MethodGet:
		f.gets = append(f.gets, key)
		w.Header().Set("Content-Type", "application/octet-stream")
		_, _ = w.Write([]byte("fake docx bytes"))
	case http.MethodPut:
		f.puts = append(f.puts, key)
		w.Header().Set("ETag", `"fakeetag"`)
		w.WriteHeader(http.StatusOK)
	case http.MethodDelete:
		f.deletes = append(f.deletes, key)
		w.WriteHeader(http.StatusNoContent)
	default:
		w.WriteHeader(http.StatusMethodNotAllowed)
	}
}

func (f *fakeMinio) counts() (gets, puts, deletes int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.gets), len(f.puts), len(f.deletes)
}

// bookRowCounts returns (chapters, drafts, revisions, scenes) for one book.
func bookRowCounts(t *testing.T, ctx context.Context, pool *pgxpool.Pool, bookID uuid.UUID) (int, int, int, int) {
	t.Helper()
	var ch, dr, rev, sc int
	q := func(sql string, args ...any) int {
		var n int
		if err := pool.QueryRow(ctx, sql, args...).Scan(&n); err != nil {
			t.Fatalf("count %q: %v", sql, err)
		}
		return n
	}
	ch = q(`SELECT count(*) FROM chapters WHERE book_id=$1`, bookID)
	dr = q(`SELECT count(*) FROM chapter_drafts WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id=$1)`, bookID)
	rev = q(`SELECT count(*) FROM chapter_revisions WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id=$1)`, bookID)
	sc = q(`SELECT count(*) FROM scenes WHERE book_id=$1`, bookID)
	return ch, dr, rev, sc
}

func TestProcessImport_RedeliverySkipsAlreadyWrittenChapters(t *testing.T) {
	pool := bookTestPool(t)
	ctx := context.Background()

	// Seed a book + import job (same columns as fb2_metadata_db_test.go).
	owner, bookID, jobID := uuid.New(), uuid.New(), uuid.New()
	if _, err := pool.Exec(ctx, `INSERT INTO books(id,owner_user_id,title) VALUES($1,$2,'replay')`, bookID, owner); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO import_jobs(id,book_id,user_id,status,filename,file_format,file_size,file_storage_key,create_book_from_metadata) VALUES($1,$2,$3,'pending','fixture.docx','docx',1,'fixture.docx',false)`, jobID, bookID, owner); err != nil {
		t.Fatalf("seed import job: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM books WHERE id=$1`, bookID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM import_jobs WHERE id=$1`, jobID)
	})

	// MinIO fake: serves the import file; records writes.
	mini := &fakeMinio{}
	minioSrv := httptest.NewServer(mini)
	defer minioSrv.Close()
	mc, err := minio.New(minioSrv.Listener.Addr().String(), &minio.Options{
		Creds:  credentials.NewStaticV4("testkey", "testsecret", ""),
		Secure: false,
	})
	if err != nil {
		t.Fatalf("minio client: %v", err)
	}

	// Pandoc fake: the HTML the parser will decompose.
	pandocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"output":"<h1>One</h1><p>Body one.</p><h1>Two</h1><p>Body two.</p>"}`))
	}))
	defer pandocSrv.Close()

	// Parse fake: the same two-chapter tree on every call.
	parseSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/parse" {
			t.Errorf("unexpected parse path %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(replayTree))
	}))
	defer parseSrv.Close()

	proc := &ImportProcessor{
		BookDB: pool,
		Cfg: &config.Config{
			MinioBucket:           "test-bucket",
			PandocURL:             pandocSrv.URL,
			CompositionServiceURL: "", // writeBackSceneLinks is a no-op without it
		},
		Minio:       mc,
		parseClient: NewParseClient(parseSrv.URL, "tok"),
	}
	payload := importRequestedPayload{
		JobID: jobID.String(), BookID: bookID.String(), UserID: owner.String(),
		FileFormat: "docx", FileStorageKey: "fixture.docx", OriginalLanguage: "en",
	}

	// First run: the two chapters land exactly once.
	n1, err := proc.processImport(ctx, payload)
	if err != nil {
		t.Fatalf("first run: %v", err)
	}
	if n1 != 2 {
		t.Fatalf("first run: chapters=%d, want 2", n1)
	}
	ch1, dr1, rev1, sc1 := bookRowCounts(t, ctx, pool, bookID)
	if ch1 != 2 || dr1 != 2 || rev1 != 2 || sc1 != 2 {
		t.Fatalf("first run: chapters=%d drafts=%d revisions=%d scenes=%d, want 2/2/2/2", ch1, dr1, rev1, sc1)
	}

	// Second run: the same job redelivered (the crash scenario). Nothing
	// new may appear, and the reported count is the job total, not the
	// (zero) newly written chapters.
	n2, err := proc.processImport(ctx, payload)
	if err != nil {
		t.Fatalf("second run: %v", err)
	}
	if n2 != 2 {
		t.Fatalf("second run: chapters=%d, want 2 (job total)", n2)
	}
	ch2, dr2, rev2, sc2 := bookRowCounts(t, ctx, pool, bookID)
	if ch2 != 2 || dr2 != 2 || rev2 != 2 || sc2 != 2 {
		t.Fatalf("second run: chapters=%d drafts=%d revisions=%d scenes=%d, want 2/2/2/2 — redelivery duplicated content", ch2, dr2, rev2, sc2)
	}
	var dupPaths int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM (SELECT structural_path FROM chapters WHERE book_id=$1 GROUP BY structural_path HAVING count(*)>1) d`,
		bookID).Scan(&dupPaths); err != nil {
		t.Fatalf("duplicate-path check: %v", err)
	}
	if dupPaths != 0 {
		t.Fatalf("second run: %d structural paths occur more than once", dupPaths)
	}
	var sorts []int
	rows, err := pool.Query(ctx, `SELECT sort_order FROM chapters WHERE book_id=$1 ORDER BY sort_order`, bookID)
	if err != nil {
		t.Fatalf("read sort orders: %v", err)
	}
	for rows.Next() {
		var s int
		if err := rows.Scan(&s); err != nil {
			t.Fatalf("scan sort order: %v", err)
		}
		sorts = append(sorts, s)
	}
	rows.Close()
	if fmt.Sprint(sorts) != "[1 2]" {
		t.Fatalf("sort orders=%v, want [1 2] (no gaps, no duplicates)", sorts)
	}
	// No MinIO writes on the redelivery: the pre-check skips already-written
	// chapters before their images could be re-uploaded under fresh keys.
	if _, puts, _ := mini.counts(); puts != 0 {
		t.Fatalf("redelivery uploaded %d objects to MinIO, want 0", puts)
	}
}
