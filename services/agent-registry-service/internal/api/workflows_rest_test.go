package api

import (
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

// S-12 (G-WORKFLOWS) — the REST get-one / delete / enablement routes, mirroring the
// skills surface. pgxmock harness (newMockServer / newMockAdminServer / doJSON / mintJWT).

const wfBase = "/v1/agent-registry/workflows/"

// the 11 columns scanRestWorkflowByID selects, in order.
var restWorkflowCols = []string{
	"workflow_id", "slug", "title", "description", "tier", "surfaces",
	"inputs", "steps", "notes_md", "status", "enabled",
}

func addVisibleWorkflowRow(id, tier string, enabled *bool) *pgxmock.Rows {
	return pgxmock.NewRows(restWorkflowCols).AddRow(
		id, "my-recipe", "My Recipe", "does things", tier, []string{"chat"},
		[]byte(`{}`), []byte(`[]`), "notes", "published", enabled,
	)
}

func TestGetWorkflow_Unauthenticated(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	rec := doJSON(s, http.MethodGet, wfBase+uuid.NewString(), "", "")
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("want 401, got %d", rec.Code)
	}
}

func TestGetWorkflow_Own_OK(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(addVisibleWorkflowRow(wfID, "user", nil)) // no override → enabled via published-default

	rec := doJSON(s, http.MethodGet, wfBase+wfID, mintJWT(t, uid, ""), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	var out restWorkflow
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out.WorkflowID != wfID {
		t.Errorf("workflow_id = %q, want %q", out.WorkflowID, wfID)
	}
	if !out.Enabled {
		t.Errorf("a published workflow with no override must be enabled=true")
	}
}

func TestGetWorkflow_NotVisible_404(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	// visibleOnly pass → no row; book-tier fallback pass → no row.
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows(restWorkflowCols))
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows(restWorkflowCols))

	rec := doJSON(s, http.MethodGet, wfBase+wfID, mintJWT(t, uid, ""), "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404, got %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestDeleteWorkflow_Own_204(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.MustParse("019d6000-0000-7000-8000-0000000000aa")
	wfID := uuid.NewString()
	mock.ExpectQuery("SELECT tier, owner_user_id, slug, book_id FROM workflows").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"tier", "owner_user_id", "slug", "book_id"}).
			AddRow("user", &uid, "my-recipe", (*uuid.UUID)(nil)))
	mock.ExpectExec("DELETE FROM workflows WHERE workflow_id").
		WithArgs(pgxmock.AnyArg()).WillReturnResult(pgxmock.NewResult("DELETE", 1))
	mock.ExpectExec("INSERT INTO registry_audit").
		WithArgs(anyArgs(8)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("UPDATE registry_meta SET catalog_version").
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	rec := doJSON(s, http.MethodDelete, wfBase+wfID, mintJWT(t, uid.String(), ""), "")
	if rec.Code != http.StatusNoContent {
		t.Fatalf("want 204, got %d (%s)", rec.Code, rec.Body.String())
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestDeleteWorkflow_OtherUsersRow_404(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	caller := uuid.NewString()
	otherOwner := uuid.MustParse("019d6000-0000-7000-8000-0000000000bb")
	wfID := uuid.NewString()
	// Owner isolation: the row belongs to another user → authorizeRowWrite false → 404 (no DELETE).
	mock.ExpectQuery("SELECT tier, owner_user_id, slug, book_id FROM workflows").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"tier", "owner_user_id", "slug", "book_id"}).
			AddRow("user", &otherOwner, "theirs", (*uuid.UUID)(nil)))

	rec := doJSON(s, http.MethodDelete, wfBase+wfID, mintJWT(t, caller, ""), "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404 (owner isolation), got %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestDeleteWorkflow_SystemTier_RegularUserBlocked(t *testing.T) {
	// admin-enabled server; a REGULAR HS256 user token cannot satisfy the RS256 admin
	// gate authorizeRowWrite requires for a System-tier row → blocked (401), no DELETE.
	// (An admin token lacking scopeAdminWrite would 403; either way a regular user cannot
	// delete a System workflow — the User-Boundaries guard, spec §4.)
	s, mock, _ := newMockAdminServer(t)
	defer mock.Close()
	wfID := uuid.NewString()
	mock.ExpectQuery("SELECT tier, owner_user_id, slug, book_id FROM workflows").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"tier", "owner_user_id", "slug", "book_id"}).
			AddRow("system", (*uuid.UUID)(nil), "sys-recipe", (*uuid.UUID)(nil)))

	rec := doJSON(s, http.MethodDelete, wfBase+wfID, mintJWT(t, uuid.NewString(), ""), "")
	if rec.Code == http.StatusNoContent {
		t.Fatalf("a regular user must NOT be able to delete a System workflow (got 204)")
	}
	if rec.Code != http.StatusUnauthorized && rec.Code != http.StatusForbidden {
		t.Fatalf("want 401/403 (System delete blocked), got %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestSetWorkflowEnabled_Own_disables(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	// visibility pass (System∪own) succeeds → then upsert the per-user override.
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(addVisibleWorkflowRow(wfID, "user", nil))
	mock.ExpectExec("INSERT INTO workflow_enablement").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg(), false).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("INSERT INTO registry_audit").
		WithArgs(anyArgs(8)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("UPDATE registry_meta SET catalog_version").
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	rec := doJSON(s, http.MethodPut, wfBase+wfID+"/enablement", mintJWT(t, uid, ""), `{"enabled":false}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	var out map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if out["enabled"] != false {
		t.Errorf("enabled = %v, want false", out["enabled"])
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestListWorkflowRevisions_Own_OK(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	// visibility (System∪own) passes → then the revisions read.
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(addVisibleWorkflowRow(wfID, "user", nil))
	mock.ExpectQuery("FROM workflow_revisions").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"revision_id", "title", "description", "notes_md", "created_at"}).
			AddRow(uuid.New(), "My Recipe", "v2", "notes", time.Now()))

	rec := doJSON(s, http.MethodGet, wfBase+wfID+"/revisions", mintJWT(t, uid, ""), "")
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200, got %d (%s)", rec.Code, rec.Body.String())
	}
	var out struct {
		Items []map[string]any `json:"items"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if len(out.Items) != 1 || out.Items[0]["title"] != "My Recipe" {
		t.Errorf("revisions body wrong: %s", rec.Body.String())
	}
}

func TestListWorkflowRevisions_NotVisible_404(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	// visibility miss → book probe returns a non-book row → not visible → 404 (no revisions read).
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows(restWorkflowCols))
	mock.ExpectQuery("SELECT tier, book_id FROM workflows").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"tier", "book_id"}).AddRow("user", (*uuid.UUID)(nil)))

	rec := doJSON(s, http.MethodGet, wfBase+wfID+"/revisions", mintJWT(t, uid, ""), "")
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404, got %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestSetWorkflowEnabled_NotVisible_404(t *testing.T) {
	s, mock := newMockServer(t)
	defer mock.Close()
	uid := uuid.NewString()
	wfID := uuid.NewString()
	// visibility SELECT (System∪own) misses → the book-tier probe returns a non-book row → 404.
	mock.ExpectQuery("SELECT wf.workflow_id, wf.slug, wf.title").
		WithArgs(pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows(restWorkflowCols))
	mock.ExpectQuery("SELECT tier, book_id FROM workflows").
		WithArgs(pgxmock.AnyArg()).
		WillReturnRows(pgxmock.NewRows([]string{"tier", "book_id"}).AddRow("user", (*uuid.UUID)(nil)))

	rec := doJSON(s, http.MethodPut, wfBase+wfID+"/enablement", mintJWT(t, uid, ""), `{"enabled":true}`)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404, got %d (%s)", rec.Code, rec.Body.String())
	}
}
