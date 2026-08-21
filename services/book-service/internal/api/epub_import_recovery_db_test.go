package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func TestEPUBImportCancelResumeAndFinalizeRedeliveryE2E_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, _ := seedChapter(t, ctx, pool, owner)
	sourceID := uuid.New()
	jobID := uuid.New()
	itemID := uuid.New()
	if _, err := pool.Exec(ctx, `INSERT INTO import_sources(id,owner_user_id,original_filename,object_key,sha256,compressed_size,metadata_json,inspection_json) VALUES($1,$2,'book.epub','imports/source.epub',$3,10,'{}','{}')`, sourceID, owner, uuid.NewString()); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO import_jobs(id,book_id,user_id,status,filename,file_format,file_size,file_storage_key,source_id,target_mode,options_json,pipeline_version,progress_total) VALUES($1,$2,$3,'queued','book.epub','epub',10,'imports/source.epub',$4,'existing_book','{"strategy":"append"}','epub-v2',1)`, jobID, bookID, owner, sourceID); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO import_job_items(id,job_id,source_key,ordinal,title,status) VALUES($1,$2,'chapter-1',1,'Chapter one','pending')`, itemID, jobID); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })

	h := s.Router()
	call := func(method, path string, body []byte, internal bool) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(method, path, bytes.NewReader(body))
		if len(body) > 0 {
			req.Header.Set("Content-Type", "application/json")
		}
		if internal {
			req.Header.Set("X-Internal-Token", mcpTestToken)
		} else {
			req.Header.Set("Authorization", "Bearer "+mcpJWT(t, owner))
		}
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, req)
		return rr
	}

	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/claim-next", nil, true); rr.Code != http.StatusOK {
		t.Fatalf("initial claim status = %d, body=%s", rr.Code, rr.Body.String())
	}
	if rr := call(http.MethodPost, "/v1/import-jobs/"+jobID.String()+"/cancel", nil, false); rr.Code != http.StatusAccepted {
		t.Fatalf("cancel status = %d, body=%s", rr.Code, rr.Body.String())
	}
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/claim-next", nil, true); rr.Code != http.StatusOK {
		t.Fatalf("cancel acknowledgement claim status = %d, body=%s", rr.Code, rr.Body.String())
	}
	if rr := call(http.MethodPost, "/v1/import-jobs/"+jobID.String()+"/resume", nil, false); rr.Code != http.StatusAccepted {
		t.Fatalf("resume status = %d, body=%s", rr.Code, rr.Body.String())
	}
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/claim-next", nil, true); rr.Code != http.StatusOK {
		t.Fatalf("resumed claim status = %d, body=%s", rr.Code, rr.Body.String())
	} else {
		var claim struct {
			Done   bool      `json:"done"`
			ItemID uuid.UUID `json:"item_id"`
		}
		if err := json.Unmarshal(rr.Body.Bytes(), &claim); err != nil {
			t.Fatal(err)
		}
		if claim.Done || claim.ItemID != itemID {
			t.Fatalf("resumed claim = %#v, want item %s", claim, itemID)
		}
	}
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/items/"+itemID.String()+"/fail", []byte(`{"code":"epub_parse_failed","message":"transient parser outage"}`), true); rr.Code != http.StatusNoContent {
		t.Fatalf("parser outage status = %d, body=%s", rr.Code, rr.Body.String())
	}
	foreignOwner := uuid.New()
	foreignResume, _ := json.Marshal(map[string]string{"owner_user_id": foreignOwner.String()})
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/resume", foreignResume, true); rr.Code != http.StatusNotFound {
		t.Fatalf("foreign internal resume status = %d, body=%s", rr.Code, rr.Body.String())
	}
	ownerResume, _ := json.Marshal(map[string]string{"owner_user_id": owner.String()})
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/resume", ownerResume, true); rr.Code != http.StatusAccepted {
		t.Fatalf("owner internal resume status = %d, body=%s", rr.Code, rr.Body.String())
	}
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/claim-next", nil, true); rr.Code != http.StatusOK {
		t.Fatalf("outage recovery claim status = %d, body=%s", rr.Code, rr.Body.String())
	} else {
		var claim struct {
			Done   bool      `json:"done"`
			ItemID uuid.UUID `json:"item_id"`
		}
		if err := json.Unmarshal(rr.Body.Bytes(), &claim); err != nil {
			t.Fatal(err)
		}
		if claim.Done || claim.ItemID != itemID {
			t.Fatalf("outage recovery claim = %#v, want item %s", claim, itemID)
		}
	}

	staging := []byte(`{"staging_payload":{"source_key":"chapter-1","title":"Chapter one","tiptap_json":{"type":"doc","content":[{"type":"paragraph"}]},"scenes":[]},"warnings":null}`)
	if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/items/"+itemID.String()+"/stage", staging, true); rr.Code != http.StatusNoContent {
		t.Fatalf("stage status = %d, body=%s", rr.Code, rr.Body.String())
	}
	for attempt := 1; attempt <= 2; attempt++ {
		if rr := call(http.MethodPost, "/internal/epub-import-jobs/"+jobID.String()+"/finalize", nil, true); rr.Code != http.StatusOK {
			t.Fatalf("finalize attempt %d status = %d, body=%s", attempt, rr.Code, rr.Body.String())
		}
	}
	var chapters, provenance int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID).Scan(&chapters); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM chapter_import_provenance WHERE import_job_id=$1`, jobID).Scan(&provenance); err != nil {
		t.Fatal(err)
	}
	if chapters != 2 || provenance != 1 {
		t.Fatalf("active chapters/provenance = %d/%d, want 2/1", chapters, provenance)
	}
}
