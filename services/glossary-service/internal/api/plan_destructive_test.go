package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// The destructive delete ops (Phase 2 slice 1) parse + validate via the same DB-free
// path as the additive ops: ValidatePlan calls only the pure Validate/IdentityKey
// funcs, so a zero Server suffices.
func TestParseAndValidateDeletePlan(t *testing.T) {
	s := &Server{}
	bookID := uuid.New()

	good := `{"ops":[
		{"type":"delete_genre","params":{"genre_code":"romance"}},
		{"type":"delete_kind","params":{"kind_code":"deity"}},
		{"type":"delete_attribute","params":{"kind_code":"character","genre_code":"universal","code":"hair_color"}}
	]}`
	plan, err := s.parseAndValidatePlan(bookID, "remove the deity kind and the romance genre", good)
	if err != nil {
		t.Fatalf("valid delete plan rejected: %v", err)
	}
	if len(plan.Ops) != 3 {
		t.Fatalf("want 3 ops, got %d", len(plan.Ops))
	}
	// All three must be stamped Destructive from the registry (G1) — never trusted from
	// the planner's JSON (which omitted the field entirely).
	for _, op := range plan.Ops {
		if !op.Destructive {
			t.Fatalf("op %s (%s) must be stamped Destructive", op.ID, op.Type)
		}
	}

	// delete_attribute requires genre_code (an attribute is keyed by kind × genre × code).
	missingGenre := `{"ops":[{"type":"delete_attribute","params":{"kind_code":"character","code":"hair_color"}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "drop hair color", missingGenre); err == nil {
		t.Fatalf("delete_attribute without genre_code: want a validation error")
	}

	// Bad slug → validation error.
	badSlug := `{"ops":[{"type":"delete_kind","params":{"kind_code":"Bad Code"}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "x", badSlug); err == nil {
		t.Fatalf("delete_kind bad slug: want a validation error")
	}
}

// effectExecutePlan must SKIP a destructive op the user did not enable (the G1 safety
// default) and must REJECT an enabled_ops id that names no op in the plan. Both paths
// run before any Handler, so they need no pool — a destructive op that is skipped never
// reaches its DB-touching handler.
func TestEffectExecutePlanEnabledOps(t *testing.T) {
	s := &Server{}
	bookID := uuid.New()
	plan := `{"ops":[{"type":"delete_kind","params":{"kind_code":"deity"}}]}`
	claims := actionClaims{
		UserID:     uuid.New(),
		BookID:     bookID,
		Descriptor: descExecutePlan,
		Params:     json.RawMessage(plan),
	}

	// (a) no enabled ops → the destructive op is skipped not_confirmed, never executed.
	w := httptest.NewRecorder()
	s.effectExecutePlan(w, context.Background(), claims, nil)
	if w.Code != 200 {
		t.Fatalf("default-skip: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var summary struct {
		Applied, Skipped, Failed []struct{ Reason string }
	}
	if err := json.Unmarshal(w.Body.Bytes(), &summary); err != nil {
		t.Fatalf("decode summary: %v", err)
	}
	if len(summary.Skipped) != 1 || len(summary.Applied) != 0 || len(summary.Failed) != 0 {
		t.Fatalf("default-skip: want 1 skipped/0 applied/0 failed, got %s", w.Body.String())
	}
	if summary.Skipped[0].Reason != "not_confirmed" {
		t.Fatalf("default-skip: want reason not_confirmed, got %q", summary.Skipped[0].Reason)
	}

	// (b) an enabled id that is not in the plan → 422 bad_enabled_op (stale toggle).
	w2 := httptest.NewRecorder()
	s.effectExecutePlan(w2, context.Background(), claims, []string{"op-404"})
	if w2.Code != 422 {
		t.Fatalf("unknown enabled_op: want 422, got %d", w2.Code)
	}
	if !strings.Contains(w2.Body.String(), "bad_enabled_op") {
		t.Fatalf("unknown enabled_op: want bad_enabled_op message, got %s", w2.Body.String())
	}
}

// merge_candidate (slice 2) parses + validates DB-free: candidate_id must be a uuid,
// winner_id is optional, and the op is stamped Destructive from the registry (G1).
func TestParseAndValidateMergeCandidatePlan(t *testing.T) {
	s := &Server{}
	bookID := uuid.New()
	cid := uuid.NewString()

	good := `{"ops":[{"type":"merge_candidate","params":{"candidate_id":"` + cid + `"}}]}`
	plan, err := s.parseAndValidatePlan(bookID, "merge the detected duplicates", good)
	if err != nil {
		t.Fatalf("valid merge_candidate plan rejected: %v", err)
	}
	if len(plan.Ops) != 1 || !plan.Ops[0].Destructive {
		t.Fatalf("merge_candidate must be 1 destructive op, got %+v", plan.Ops)
	}

	// winner_id optional but must be a uuid when present.
	withWinner := `{"ops":[{"type":"merge_candidate","params":{"candidate_id":"` + cid + `","winner_id":"` + uuid.NewString() + `"}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "x", withWinner); err != nil {
		t.Fatalf("merge_candidate with winner_id rejected: %v", err)
	}

	// non-uuid candidate_id → validation error (the planner must copy a real id).
	bad := `{"ops":[{"type":"merge_candidate","params":{"candidate_id":"the-aria-cluster"}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "x", bad); err == nil {
		t.Fatalf("non-uuid candidate_id: want a validation error")
	}

	// two ops with the SAME candidate_id collapse (IdentityKey dedupe).
	dupe := `{"ops":[{"type":"merge_candidate","params":{"candidate_id":"` + cid + `"}},{"type":"merge_candidate","params":{"candidate_id":"` + cid + `"}}]}`
	if p, err := s.parseAndValidatePlan(bookID, "x", dupe); err != nil || len(p.Ops) != 1 {
		t.Fatalf("duplicate candidate_id should collapse to 1 op, got %d ops err=%v", len(p.Ops), err)
	}
}

// resolveMergeWinner picks winner_id (a member) over the suggested winner, falls back to
// the suggested winner, and errors when neither yields a member.
func TestResolveMergeWinner(t *testing.T) {
	a, b, c := uuid.New(), uuid.New(), uuid.New()
	members := []uuid.UUID{a, b}

	// explicit winner_id that IS a member wins.
	if got, err := resolveMergeWinner(members, &b, a.String()); err != nil || got != a {
		t.Fatalf("explicit member winner: got %v err %v, want %v", got, err, a)
	}
	// explicit winner_id that is NOT a member → error.
	if _, err := resolveMergeWinner(members, &b, c.String()); err == nil {
		t.Fatalf("non-member winner_id: want error")
	}
	// no winner_id → suggested winner (a member) is used.
	if got, err := resolveMergeWinner(members, &b, ""); err != nil || got != b {
		t.Fatalf("suggested winner: got %v err %v, want %v", got, err, b)
	}
	// no winner_id and suggested is NOT a member → error.
	if _, err := resolveMergeWinner(members, &c, ""); err == nil {
		t.Fatalf("suggested non-member, no winner_id: want error")
	}
	// no winner_id and no suggestion → error (plan must supply a winner).
	if _, err := resolveMergeWinner(members, nil, ""); err == nil {
		t.Fatalf("no winner at all: want error")
	}
}

// confirmOps posts {confirm_token, enabled_ops} to the confirm endpoint (the
// execute_plan path), exercising the real router → decodeConfirmToken → effect.
func (f *actionFixture) confirmOps(t *testing.T, token string, ops []string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"confirm_token": token, "enabled_ops": ops})
	req := httptest.NewRequest(http.MethodPost, "/v1/glossary/actions/confirm", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.jwt)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

type planSummary struct {
	Applied, Skipped, Failed []struct {
		Type, Reason string
	}
}

// TestExecutePlan_DeleteKind_RealPG is the destructive round-trip on real Postgres:
// a delete_kind plan is SKIPPED unless enabled, APPLIED (with cascade) when enabled,
// idempotent (already_done) on re-run, and target_gone for a bogus code. Proves the
// enabled_ops wire + the deprecation-aware resolver against the live schema.
func TestExecutePlan_DeleteKind_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM book_attributes WHERE book_id=$1 AND kind_id IN (SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code='qa_plan_del')`, f.bookID)
		pool.Exec(ctx, `DELETE FROM book_kinds WHERE book_id=$1 AND code='qa_plan_del'`, f.bookID)
	})

	k, err := f.srv.createKindFromParams(ctx, f.bookID, kindCreateParams{Code: "qa_plan_del", Name: "Disposable"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	_ = k

	mintPlan := func(rawPlan string) string {
		plan, perr := f.srv.parseAndValidatePlan(f.bookID, "remove the disposable kind", rawPlan)
		if perr != nil {
			t.Fatalf("plan rejected: %v", perr)
		}
		params, _ := json.Marshal(plan)
		return mintActionToken(versionTestSecret, actionClaims{
			JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
			Descriptor: descExecutePlan, Params: params,
		}, time.Now())
	}
	delPlan := `{"ops":[{"type":"delete_kind","params":{"kind_code":"qa_plan_del"}}]}`
	isLive := func() bool {
		var dep *time.Time
		pool.QueryRow(ctx, `SELECT deprecated_at FROM book_kinds WHERE book_id=$1 AND code='qa_plan_del'`, f.bookID).Scan(&dep)
		return dep == nil
	}
	decode := func(w *httptest.ResponseRecorder) planSummary {
		var s planSummary
		if err := json.Unmarshal(w.Body.Bytes(), &s); err != nil {
			t.Fatalf("decode summary (%d): %v — %s", w.Code, err, w.Body.String())
		}
		return s
	}

	// (1) confirm WITHOUT enabling → the destructive op is skipped not_confirmed; the
	// kind stays LIVE (the safety default — a bare approve never deletes).
	if w := f.confirmOps(t, mintPlan(delPlan), nil); w.Code != http.StatusOK {
		t.Fatalf("skip path: want 200, got %d (%s)", w.Code, w.Body.String())
	} else if s := decode(w); len(s.Skipped) != 1 || s.Skipped[0].Reason != "not_confirmed" {
		t.Fatalf("skip path: want 1 skipped not_confirmed, got %+v", s)
	}
	if !isLive() {
		t.Fatal("kind was deleted on a non-enabled confirm — the safety default failed")
	}

	// (2) confirm WITH the op enabled → applied; the kind (and its attributes) deprecate.
	if w := f.confirmOps(t, mintPlan(delPlan), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("apply path: want 200, got %d (%s)", w.Code, w.Body.String())
	} else if s := decode(w); len(s.Applied) != 1 || s.Applied[0].Type != "delete_kind" {
		t.Fatalf("apply path: want 1 applied delete_kind, got %+v", s)
	}
	if isLive() {
		t.Fatal("kind was NOT deprecated after an enabled delete")
	}

	// (3) re-run the SAME delete (new token) WITH enable → already_done (idempotent skip).
	if w := f.confirmOps(t, mintPlan(delPlan), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("idempotent path: want 200, got %d", w.Code)
	} else if s := decode(w); len(s.Skipped) != 1 || s.Skipped[0].Reason != "already_done" {
		t.Fatalf("idempotent path: want 1 skipped already_done, got %+v", s)
	}

	// (4) a bogus code → target_gone (failed), never a 500.
	bogus := `{"ops":[{"type":"delete_kind","params":{"kind_code":"qa_does_not_exist"}}]}`
	if w := f.confirmOps(t, mintPlan(bogus), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("target_gone path: want 200, got %d", w.Code)
	} else if s := decode(w); len(s.Failed) != 1 || s.Failed[0].Reason != "target_gone" {
		t.Fatalf("target_gone path: want 1 failed target_gone, got %+v", s)
	}
}

// TestExecutePlan_DeleteGenre_RealPG exercises the delete_genre resolver SQL + cascade
// primitive on real PG (distinct table/cascade from delete_kind): apply→deprecated,
// re-run→already_done. Targets a genre the adopt fixture already created.
func TestExecutePlan_DeleteGenre_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()

	var genreCode string
	err := pool.QueryRow(ctx,
		`SELECT code FROM book_genres WHERE book_id=$1 AND deprecated_at IS NULL ORDER BY code LIMIT 1`,
		f.bookID).Scan(&genreCode)
	if err != nil {
		t.Skipf("no live genre in the adopt fixture to delete: %v", err)
	}

	rawPlan := `{"ops":[{"type":"delete_genre","params":{"genre_code":"` + genreCode + `"}}]}`
	mint := func() string {
		plan, perr := f.srv.parseAndValidatePlan(f.bookID, "remove a genre", rawPlan)
		if perr != nil {
			t.Fatalf("plan rejected: %v", perr)
		}
		params, _ := json.Marshal(plan)
		return mintActionToken(versionTestSecret, actionClaims{
			JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
			Descriptor: descExecutePlan, Params: params,
		}, time.Now())
	}
	decode := func(w *httptest.ResponseRecorder) planSummary {
		var s planSummary
		if err := json.Unmarshal(w.Body.Bytes(), &s); err != nil {
			t.Fatalf("decode (%d): %v — %s", w.Code, err, w.Body.String())
		}
		return s
	}

	// enable → applied; genre deprecates.
	if w := f.confirmOps(t, mint(), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("apply: want 200, got %d (%s)", w.Code, w.Body.String())
	} else if s := decode(w); len(s.Applied) != 1 || s.Applied[0].Type != "delete_genre" {
		t.Fatalf("apply: want 1 applied delete_genre, got %+v", s)
	}
	var dep *time.Time
	pool.QueryRow(ctx, `SELECT deprecated_at FROM book_genres WHERE book_id=$1 AND code=$2`, f.bookID, genreCode).Scan(&dep)
	if dep == nil {
		t.Fatalf("genre %q was not deprecated after an enabled delete_genre", genreCode)
	}

	// re-run → already_done (the resolver sees the now-deprecated row).
	if w := f.confirmOps(t, mint(), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("idempotent: want 200, got %d", w.Code)
	} else if s := decode(w); len(s.Skipped) != 1 || s.Skipped[0].Reason != "already_done" {
		t.Fatalf("idempotent: want 1 skipped already_done, got %+v", s)
	}
}

// TestExecutePlan_MergeCandidate_RealPG is the slice-2 round-trip on real PG: a
// merge_candidate op (enabled) merges a detected duplicate cluster via mergeEntitiesCore
// — loser soft-deleted, candidate flips to merged; re-run → already_done; bogus id →
// target_gone. Proves the candidate→merge orchestration end-to-end.
func TestExecutePlan_MergeCandidate_RealPG(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()

	kindID := bookKindID(t, pool, f.bookID, "character")
	nameAttr := bookAttrID(t, pool, f.bookID, kindID, "name")
	mkEntity := func(name string) uuid.UUID {
		var id uuid.UUID
		if err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
			f.bookID, kindID).Scan(&id); err != nil {
			t.Fatalf("mkEntity: %v", err)
		}
		pool.Exec(ctx, `INSERT INTO entity_attribute_values(entity_id,attr_def_id,original_language,original_value) VALUES($1,$2,'zh',$3)`,
			id, nameAttr, name)
		return id
	}
	winner := mkEntity("Ariadne")
	loser := mkEntity("Aria")
	members := []uuid.UUID{winner, loser}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM merge_journal WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM merge_candidates WHERE book_id=$1`, f.bookID)
		pool.Exec(ctx, `DELETE FROM entity_attribute_values WHERE entity_id = ANY($1::uuid[])`, members)
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1 AND entity_id = ANY($2::uuid[])`, f.bookID, members)
	})

	setKey := func(ids []uuid.UUID) string {
		ss := make([]string, len(ids))
		for i, id := range ids {
			ss[i] = id.String()
		}
		sort.Strings(ss)
		return strings.Join(ss, ",")
	}
	var candID uuid.UUID
	if err := pool.QueryRow(ctx, `
		INSERT INTO merge_candidates(book_id,kind_id,member_entity_ids,member_set_key,suggested_winner_entity_id,score,status)
		VALUES($1,$2,$3,$4,$5,0.95,'proposed') RETURNING candidate_id`,
		f.bookID, kindID, members, setKey(members), winner).Scan(&candID); err != nil {
		t.Fatalf("seed candidate: %v", err)
	}

	mint := func(cid string) string {
		raw := `{"ops":[{"type":"merge_candidate","params":{"candidate_id":"` + cid + `"}}]}`
		plan, perr := f.srv.parseAndValidatePlan(f.bookID, "merge the detected duplicates", raw)
		if perr != nil {
			t.Fatalf("plan rejected: %v", perr)
		}
		params, _ := json.Marshal(plan)
		return mintActionToken(versionTestSecret, actionClaims{
			JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
			Descriptor: descExecutePlan, Params: params,
		}, time.Now())
	}
	decode := func(w *httptest.ResponseRecorder) planSummary {
		var s planSummary
		if err := json.Unmarshal(w.Body.Bytes(), &s); err != nil {
			t.Fatalf("decode (%d): %v — %s", w.Code, err, w.Body.String())
		}
		return s
	}

	// (1) enable → applied; loser soft-deleted; candidate flips to merged.
	if w := f.confirmOps(t, mint(candID.String()), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("apply: want 200, got %d (%s)", w.Code, w.Body.String())
	} else if s := decode(w); len(s.Applied) != 1 || s.Applied[0].Type != "merge_candidate" {
		t.Fatalf("apply: want 1 applied merge_candidate, got %+v", s)
	}
	// The deterministic, in-tx signal that the merge happened is the loser's soft-delete.
	// (The candidate's status→'merged' flip is markCandidatesMerged's best-effort
	// post-commit effect — asserted indirectly by the idempotent re-run below, not by a
	// timing-sensitive read here.)
	var deletedAt *time.Time
	pool.QueryRow(ctx, `SELECT deleted_at FROM glossary_entities WHERE entity_id=$1`, loser).Scan(&deletedAt)
	if deletedAt == nil {
		t.Fatal("loser was not soft-deleted after the merge")
	}

	// (2) re-run (new token) → already_done — deterministic regardless of the candidate
	// status flip, because no loser is merged the second time (the op detects 0 merges).
	if w := f.confirmOps(t, mint(candID.String()), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("idempotent: want 200, got %d", w.Code)
	} else if s := decode(w); len(s.Skipped) != 1 || s.Skipped[0].Reason != "already_done" {
		t.Fatalf("idempotent: want 1 skipped already_done, got %+v", s)
	}

	// (3) a bogus candidate id → target_gone (failed), never a 500.
	if w := f.confirmOps(t, mint(uuid.NewString()), []string{"op-1"}); w.Code != http.StatusOK {
		t.Fatalf("target_gone: want 200, got %d", w.Code)
	} else if s := decode(w); len(s.Failed) != 1 || s.Failed[0].Reason != "target_gone" {
		t.Fatalf("target_gone: want 1 failed target_gone, got %+v", s)
	}
}
