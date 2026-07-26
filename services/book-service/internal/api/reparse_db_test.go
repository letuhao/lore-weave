package api

// 26 IX-2/IX-3/IX-4/IX-5/IX-9/IX-10 DB-gated tests (Build 26 Phase B). Gated on
// BOOK_TEST_DATABASE_URL via dbTestServer — SKIPPED when unset so `go test` stays
// green with no DB. These cover the real seams the nil-pool unit tests cannot:
//   - publish re-parses the index and emits chapter.published + chapter.scenes_reparsed
//     in ONE Tx, and returns the IX-4 delta counts (silent-success-is-a-bug);
//   - the IX-3 sweeper heals a stale marker and emits scenes_reparsed;
//   - the IX-9 canon-markers batch returns the four markers, book-scoped;
//   - a parse failure does NOT block publish (OQ-1) and leaves the marker stale;
//   - IX-5 rule 2: a one-word edit preserves every existing back-link.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// mockParseServer returns an httptest server whose /internal/parse always answers
// with treeJSON (a StructuralTree). Wire it via s.cfg.KnowledgeServiceURL.
func mockParseServer(t *testing.T, treeJSON string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(treeJSON))
	}))
}

// twoSceneTreeJSON builds a single-chapter tiptap StructuralTree JSON with two
// scenes. anchorSceneID, if non-empty, is set as scene-2's data-scene-id anchor.
func twoSceneTreeJSON(anchorSceneID string) string {
	anchor := ""
	if anchorSceneID != "" {
		anchor = `,"anchor_scene_id":"` + anchorSceneID + `"`
	}
	return `{"source_format":"tiptap","walker_path":"headings","detected_language":null,"book_title":null,
"parts":[{"sort_order":1,"title":null,"path":"book/part-1","chapters":[
 {"sort_order":1,"title":"C1","path":"book/part-1/chapter-1","html":"","scenes":[
   {"sort_order":1,"path":"book/part-1/chapter-1/scene-1","leaf_text":"scene one","content_hash":"h1"},
   {"sort_order":2,"path":"book/part-1/chapter-1/scene-2","leaf_text":"scene two","content_hash":"h2"` + anchor + `}
 ]}
]}]}`
}

func publishViaRouter(t *testing.T, s *Server, userID, bookID, chID uuid.UUID) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost,
		"/v1/books/"+bookID.String()+"/chapters/"+chID.String()+"/publish", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, userID))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	var out map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	return rr.Code, out
}

// IX-2/IX-4/IX-10: publishing a chapter parses its pinned body, upserts scenes,
// advances last_parsed_revision_id, and emits BOTH events in one Tx; the response
// carries the IX-4 delta counts.
func TestPublishReparsesIndexAndEmitsBothEvents_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	anchor := uuid.New()
	parseSrv := mockParseServer(t, twoSceneTreeJSON(anchor.String()))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	code, out := publishViaRouter(t, s, uuid.New(), bookID, chID)
	if code != http.StatusOK {
		t.Fatalf("publish = %d, want 200; body=%v", code, out)
	}
	rp, _ := out["reparse"].(map[string]any)
	if rp == nil {
		t.Fatalf("publish response missing reparse counts: %v", out)
	}
	if rp["inserted"].(float64) != 2 {
		t.Fatalf("reparse.inserted = %v, want 2 (%v)", rp["inserted"], rp)
	}
	if rp["parse_version"].(float64) != 1 {
		t.Fatalf("reparse.parse_version = %v, want 1", rp["parse_version"])
	}

	// Two scenes now exist; scene-2 carries the anchor as source_scene_id (rule 1).
	var sceneCount, anchored int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active'`, chID).Scan(&sceneCount)
	if sceneCount != 2 {
		t.Fatalf("scenes = %d, want 2", sceneCount)
	}
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE chapter_id=$1 AND source_scene_id=$2`, chID, anchor).Scan(&anchored)
	if anchored != 1 {
		t.Fatalf("anchored scenes = %d, want 1 (IX-5 rule 1)", anchored)
	}

	// last_parsed_revision_id advanced to the pinned published revision (fresh).
	var lastParsed, publishedRev *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT last_parsed_revision_id, published_revision_id FROM chapters WHERE id=$1`, chID).Scan(&lastParsed, &publishedRev)
	if lastParsed == nil || publishedRev == nil || *lastParsed != *publishedRev {
		t.Fatalf("index not marked fresh: last_parsed=%v published=%v", lastParsed, publishedRev)
	}

	// Both events emitted in the same Tx.
	var pubEvt, reparseEvt int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.published'`, chID).Scan(&pubEvt)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&reparseEvt)
	if pubEvt != 1 || reparseEvt != 1 {
		t.Fatalf("events: published=%d scenes_reparsed=%d, want 1/1", pubEvt, reparseEvt)
	}
	// The scenes_reparsed payload carries the frozen shape.
	var payload string
	_ = pool.QueryRow(ctx, `SELECT payload::text FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&payload)
	var pm map[string]any
	_ = json.Unmarshal([]byte(payload), &pm)
	if pm["parse_version"].(float64) != 1 {
		t.Fatalf("scenes_reparsed parse_version = %v, want 1", pm["parse_version"])
	}
	if pm["published_revision_id"] != publishedRev.String() {
		t.Fatalf("scenes_reparsed published_revision_id = %v, want %s", pm["published_revision_id"], publishedRev)
	}
	if pm["book_id"] != bookID.String() {
		t.Fatalf("scenes_reparsed book_id = %v, want %s", pm["book_id"], bookID)
	}
}

// RB5-1: a re-publish that produces NO index change (identical body → all scenes
// Unchanged) must NOT emit chapter.scenes_reparsed a second time. That event's
// knowledge consumer wipes the WHOLE book's extraction cache, so a no-op emit is a
// costly re-extract for zero change. chapter.published still fires each publish.
func TestNoOpRepublishDoesNotEmitScenesReparsed_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	parseSrv := mockParseServer(t, twoSceneTreeJSON(uuid.New().String()))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	// First publish: indexes 2 scenes, emits scenes_reparsed once.
	if code, out := publishViaRouter(t, s, uuid.New(), bookID, chID); code != http.StatusOK {
		t.Fatalf("first publish = %d; body=%v", code, out)
	}
	var reparseEvt int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&reparseEvt)
	if reparseEvt != 1 {
		t.Fatalf("after first publish: scenes_reparsed=%d, want 1", reparseEvt)
	}

	// Re-publish the SAME body (the mock parse server returns the identical tree) →
	// every scene Unchanged → counts.changed()==false → NO second scenes_reparsed.
	if code, out := publishViaRouter(t, s, uuid.New(), bookID, chID); code != http.StatusOK {
		t.Fatalf("re-publish = %d; body=%v", code, out)
	}
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&reparseEvt)
	if reparseEvt != 1 {
		t.Fatalf("after no-op re-publish: scenes_reparsed=%d, want STILL 1 (no whole-book cache wipe)", reparseEvt)
	}
}

// OQ-1: a parse failure must NOT block publish. The chapter still publishes; the
// index is left stale (last_parsed_revision_id NULL) for the sweeper, and no
// scenes_reparsed event fires.
func TestPublishParseFailureDoesNotBlock_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID, chID := seedChapter(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	s.resolveBook = func(_ context.Context, _, _ uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, owner, "active", nil
	}
	parseSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("parser down"))
	}))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	code, _ := publishViaRouter(t, s, uuid.New(), bookID, chID)
	if code != http.StatusOK {
		t.Fatalf("publish with parser down = %d, want 200 (must not block)", code)
	}
	var status string
	var lastParsed *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT editorial_status, last_parsed_revision_id FROM chapters WHERE id=$1`, chID).Scan(&status, &lastParsed)
	if status != "published" {
		t.Fatalf("editorial_status = %q, want published", status)
	}
	if lastParsed != nil {
		t.Fatalf("last_parsed_revision_id = %v, want NULL (index left stale for the sweeper)", lastParsed)
	}
	var sceneCount, reparseEvt, pubEvt int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE chapter_id=$1`, chID).Scan(&sceneCount)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&reparseEvt)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.published'`, chID).Scan(&pubEvt)
	if sceneCount != 0 || reparseEvt != 0 {
		t.Fatalf("on parse failure: scenes=%d scenes_reparsed=%d, want 0/0", sceneCount, reparseEvt)
	}
	if pubEvt != 1 {
		t.Fatalf("chapter.published = %d, want 1 (publish still proceeds)", pubEvt)
	}
}

// IX-3: the sweeper's per-chapter heal indexes a stale published chapter and
// advances its marker. Drives reparseOneChapter directly (scoped to the seeded
// chapter) so the shared test DB's other rows are never touched.
func TestReparseSweeperHealsStaleMarker_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID, chID, revID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'sweep') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status,structural_path)
VALUES($1,'c.txt','en','text/plain',1,'k','active','published','book/part-1/chapter-1') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	body := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","_text":"prose"}]}`)
	if err := pool.QueryRow(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message) VALUES($1,$2,'json','publish') RETURNING id`, chID, body).Scan(&revID); err != nil {
		t.Fatalf("seed revision: %v", err)
	}
	// Pinned published, but last_parsed_revision_id stays NULL → stale by IX-3.
	// WS-0.5: the sweeper is re-keyed onto kg_indexed_revision_id, so a published
	// chapter must carry it too — which is exactly what the WS-0.2 migration backfill
	// (kg_indexed_revision_id := published_revision_id) guarantees on the real corpus,
	// and what all six publish writers now do going forward.
	if _, err := pool.Exec(ctx,
		`UPDATE chapters SET published_revision_id=$2, kg_indexed_revision_id=$2 WHERE id=$1`,
		chID, revID); err != nil {
		t.Fatalf("pin revision: %v", err)
	}

	parseSrv := mockParseServer(t, twoSceneTreeJSON(""))
	defer parseSrv.Close()
	s.cfg.KnowledgeServiceURL = parseSrv.URL

	if err := s.reparseOneChapter(ctx, sweepTarget{
		chapterID: chID, bookID: bookID, indexedRev: revID,
		lang: "en", structuralPath: "book/part-1/chapter-1", body: string(body),
	}); err != nil {
		t.Fatalf("reparseOneChapter: %v", err)
	}

	var lastParsed *uuid.UUID
	var sceneCount, reparseEvt int
	_ = pool.QueryRow(ctx, `SELECT last_parsed_revision_id FROM chapters WHERE id=$1`, chID).Scan(&lastParsed)
	if lastParsed == nil || *lastParsed != revID {
		t.Fatalf("marker not healed: last_parsed=%v, want %s", lastParsed, revID)
	}
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active'`, chID).Scan(&sceneCount)
	if sceneCount != 2 {
		t.Fatalf("healed scenes = %d, want 2", sceneCount)
	}
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='chapter.scenes_reparsed'`, chID).Scan(&reparseEvt)
	if reparseEvt != 1 {
		t.Fatalf("scenes_reparsed on sweep = %d, want 1", reparseEvt)
	}
	// Paths were rewritten from structural_path (F9).
	var pathN int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM scenes WHERE chapter_id=$1 AND path LIKE 'book/part-1/chapter-1/scene-%'`, chID).Scan(&pathN)
	if pathN != 2 {
		t.Fatalf("path-prefix rewrite: %d rows under structural_path, want 2", pathN)
	}
}

// IX-9: the canon-markers batch returns the four markers for chapters in the
// named book (and drops ids outside it).
func TestCanonMarkersReturnsMarkers_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID, chID, revID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'markers') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status)
VALUES($1,'c.txt','en','text/plain',1,'k','active','published') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	body := json.RawMessage(`{"type":"doc"}`)
	if err := pool.QueryRow(ctx, `INSERT INTO chapter_revisions(chapter_id, body, message) VALUES($1,$2,'p') RETURNING id`, chID, body).Scan(&revID); err != nil {
		t.Fatalf("seed rev: %v", err)
	}
	if _, err := pool.Exec(ctx, `UPDATE chapters SET published_revision_id=$2, last_parsed_revision_id=$2 WHERE id=$1`, chID, revID); err != nil {
		t.Fatalf("pin: %v", err)
	}
	// A scene with parse_version 3 → the chapter scalar MAX = 3.
	if _, err := pool.Exec(ctx, `INSERT INTO scenes(chapter_id,book_id,sort_order,path,leaf_text,content_hash,parse_version) VALUES($1,$2,1,'p','x','h',3)`, chID, bookID); err != nil {
		t.Fatalf("seed scene: %v", err)
	}

	reqBody, _ := json.Marshal(map[string]any{"chapter_ids": []string{chID.String(), uuid.NewString()}})
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID.String()+"/chapters/canon-markers", bytes.NewReader(reqBody))
	req.Header.Set("X-Internal-Token", mcpTestToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("canon-markers = %d, want 200; body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Markers map[string]struct {
			PublishedRevisionID  *string `json:"published_revision_id"`
			LastParsedRevisionID *string `json:"last_parsed_revision_id"`
			ParseVersion         int     `json:"parse_version"`
			EditorialStatus      string  `json:"editorial_status"`
		} `json:"markers"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(out.Markers) != 1 {
		t.Fatalf("markers len = %d, want 1 (foreign id dropped)", len(out.Markers))
	}
	m, ok := out.Markers[chID.String()]
	if !ok {
		t.Fatalf("marker for %s missing: %v", chID, out.Markers)
	}
	if m.EditorialStatus != "published" || m.ParseVersion != 3 {
		t.Fatalf("marker = %+v, want status=published parse_version=3", m)
	}
	if m.PublishedRevisionID == nil || *m.PublishedRevisionID != revID.String() {
		t.Fatalf("published_revision_id = %v, want %s", m.PublishedRevisionID, revID)
	}
	if m.LastParsedRevisionID == nil || *m.LastParsedRevisionID != revID.String() {
		t.Fatalf("last_parsed_revision_id = %v, want %s", m.LastParsedRevisionID, revID)
	}
}

// IX-5 rule 2: a one-word edit (one leaf's content_hash changes, no anchor)
// re-parses to {unchanged:1, updated:1} and PRESERVES every existing back-link.
func TestReparseRuleTwoOneWordEditPreservesLinks_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	var bookID, chID uuid.UUID
	if err := pool.QueryRow(ctx, `INSERT INTO books(owner_user_id,title) VALUES($1,'rule2') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	if err := pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state,editorial_status,structural_path)
VALUES($1,'c.txt','en','text/plain',1,'k','active','draft','book/part-1/chapter-1') RETURNING id`, bookID).Scan(&chID); err != nil {
		t.Fatalf("seed chapter: %v", err)
	}
	ssid1, ssid2 := uuid.New(), uuid.New()
	// Two existing indexed scenes, each with a back-link, parse_version 1.
	if _, err := pool.Exec(ctx, `INSERT INTO scenes(chapter_id,book_id,sort_order,path,leaf_text,content_hash,source_scene_id,parse_version) VALUES
($1,$2,1,'book/part-1/chapter-1/scene-1','one','hA',$3,1),
($1,$2,2,'book/part-1/chapter-1/scene-2','two','hB',$4,1)`, chID, bookID, ssid1, ssid2); err != nil {
		t.Fatalf("seed scenes: %v", err)
	}

	// Re-parse tree: scene-1 UNCHANGED (hA), scene-2 CHANGED (hB2), no anchors.
	tree := &parsedTree{Parts: []parsedPart{{SortOrder: 1, Path: "book/part-1", Chapters: []parsedChapter{{
		SortOrder: 1, Path: "book/part-1/chapter-1", Scenes: []parsedScene{
			{SortOrder: 1, Path: "book/part-1/chapter-1/scene-1", LeafText: "one", ContentHash: "hA"},
			{SortOrder: 2, Path: "book/part-1/chapter-1/scene-2", LeafText: "two point five", ContentHash: "hB2"},
		},
	}}}}}

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	counts, err := s.upsertChapterScenes(ctx, tx, bookID, chID, "book/part-1/chapter-1", tree)
	if err != nil {
		_ = tx.Rollback(ctx)
		t.Fatalf("upsert: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}
	if counts.Unchanged != 1 || counts.Updated != 1 || counts.Inserted != 0 || counts.Deleted != 0 {
		t.Fatalf("counts = %+v, want {unchanged:1, updated:1, inserted:0, deleted:0}", counts)
	}
	if counts.ParseVersion != 2 {
		t.Fatalf("chapter-scalar parse_version = %d, want 2 (bump)", counts.ParseVersion)
	}
	// Both back-links survived the edit (rule 2 positional stability).
	var got1, got2 *uuid.UUID
	_ = pool.QueryRow(ctx, `SELECT source_scene_id FROM scenes WHERE chapter_id=$1 AND sort_order=1`, chID).Scan(&got1)
	_ = pool.QueryRow(ctx, `SELECT source_scene_id FROM scenes WHERE chapter_id=$1 AND sort_order=2`, chID).Scan(&got2)
	if got1 == nil || *got1 != ssid1 {
		t.Fatalf("scene-1 lost its link: %v, want %s", got1, ssid1)
	}
	if got2 == nil || *got2 != ssid2 {
		t.Fatalf("scene-2 lost its link on a content edit: %v, want %s (IX-5 rule 2)", got2, ssid2)
	}
	// The changed leaf carries the bumped stamp; the untouched leaf keeps its old one.
	var pv1, pv2 int
	_ = pool.QueryRow(ctx, `SELECT parse_version FROM scenes WHERE chapter_id=$1 AND sort_order=1`, chID).Scan(&pv1)
	_ = pool.QueryRow(ctx, `SELECT parse_version FROM scenes WHERE chapter_id=$1 AND sort_order=2`, chID).Scan(&pv2)
	if pv1 != 1 || pv2 != 2 {
		t.Fatalf("parse_version mix = (%d,%d), want (1,2)", pv1, pv2)
	}
}

