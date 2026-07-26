package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// projectionWithKindAndWiki is a fake book-service /projection that returns a given kind AND a
// public wiki_settings blob — the residual-drift shape PP-2 must neutralize (a diary whose blob
// still says visibility=public, e.g. written before book-service's EGRESS GUARD #3 landed).
func projectionWithKindAndWiki(book, owner uuid.UUID, kind string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.HasSuffix(r.URL.Path, "/access") {
			lvl := "none"
			if r.URL.Query().Get("user_id") == owner.String() {
				lvl = "owner"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": lvl, "lifecycle_state": "active"})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":       book.String(),
			"owner_user_id": owner.String(),
			"kind":          kind,
			"wiki_settings": map[string]any{"visibility": "public", "community_mode": "open"},
		})
	}
}

// PP-2 (spec 08 R5) — the projection chokepoint. Every wiki/enrichment/community reader resolves
// the book through fetchBookProjection, so nulling WikiSettings for a diary HERE closes them all —
// including a residual `visibility=public` blob. A novel's wiki_settings must pass through untouched.
func TestFetchBookProjection_NullsWikiSettingsForADiary(t *testing.T) {
	owner, book := uuid.New(), uuid.New()

	// A DIARY whose blob still carries visibility=public → the chokepoint must strip WikiSettings.
	sDiary := ownershipTestServer(t, projectionWithKindAndWiki(book, owner, "diary"))
	proj, status := sDiary.fetchBookProjection(context.Background(), book)
	if status != http.StatusOK || proj == nil {
		t.Fatalf("diary projection fetch: status=%d proj=%v", status, proj)
	}
	if proj.Kind != "diary" {
		t.Fatalf("expected kind=diary, got %q", proj.Kind)
	}
	if proj.WikiSettings != nil {
		t.Fatalf("PP-2 BREACH: a diary's WikiSettings survived the chokepoint (%+v) — a residual "+
			"visibility=public blob would serve a colleague's page to the public", proj.WikiSettings)
	}

	// A NOVEL with the same blob → WikiSettings preserved (a legitimate public wiki still works).
	sNovel := ownershipTestServer(t, projectionWithKindAndWiki(book, owner, "novel"))
	np, nstatus := sNovel.fetchBookProjection(context.Background(), book)
	if nstatus != http.StatusOK || np == nil {
		t.Fatalf("novel projection fetch: status=%d", nstatus)
	}
	if np.WikiSettings == nil || np.WikiSettings.Visibility != "public" {
		t.Fatalf("a novel's public wiki_settings must pass through, got %+v", np.WikiSettings)
	}
}

// PP-3 (spec 08 R5) — the auto-WRITE surfaces (generateWikiStubs, internalUpsertEnrichments) share
// refuseDiaryWikiSurface, which must refuse a diary (403), allow a novel, and FAIL CLOSED when the
// book is unresolvable (a wiki/enrichment write must not proceed on a transient projection miss).
func TestRefuseDiaryWikiSurface(t *testing.T) {
	owner, book := uuid.New(), uuid.New()

	// diary → refused (true) + 403
	sDiary := ownershipTestServer(t, projectionWithKindAndWiki(book, owner, "diary"))
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/x", nil)
	if refused := sDiary.refuseDiaryWikiSurface(rr, req, book); !refused {
		t.Fatal("PP-3 BREACH: a diary was NOT refused for a wiki/enrichment write")
	}
	if rr.Code != http.StatusForbidden {
		t.Fatalf("diary refuse: status=%d want 403", rr.Code)
	}

	// novel → allowed (false)
	sNovel := ownershipTestServer(t, projectionWithKindAndWiki(book, owner, "novel"))
	if refused := sNovel.refuseDiaryWikiSurface(httptest.NewRecorder(), req, book); refused {
		t.Fatal("a novel must be allowed to generate wiki/enrichment")
	}

	// unresolvable book (projection 500) → fail CLOSED (refused, 503)
	sBad := ownershipTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/access") {
			_ = json.NewEncoder(w).Encode(map[string]any{"grant_level": "owner", "lifecycle_state": "active"})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
	})
	rr2 := httptest.NewRecorder()
	if refused := sBad.refuseDiaryWikiSurface(rr2, req, book); !refused {
		t.Fatal("an unresolvable book must FAIL CLOSED (refuse), not allow the write")
	}
	if rr2.Code != http.StatusServiceUnavailable {
		t.Fatalf("fail-closed status=%d want 503", rr2.Code)
	}
}
