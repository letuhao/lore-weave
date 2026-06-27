package jobs

// S4b — DB-mock coverage (review-impl MED) for the previously-untested SQL paths:
// the FinalizeWithUsageOutbox atomic finalize+outbox tx and the relay drainOnce
// SELECT→dual-XADD→mark flow. Uses pgxmock (pool) + redismock (streams) so the tx
// boundary, the rowsAffected/race gate, the conditional INSERT, and the
// per-stream routing are verified without a live stack. (SKIP-LOCKED disjointness
// across replicas + real MAXLEN trim remain → D-S4B-RELAY-LIVE-SMOKE.)

import (
	"context"
	"fmt"
	"testing"

	"github.com/go-redis/redismock/v9"
	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
	"github.com/redis/go-redis/v9"
)

// orderlessArgs compares two redis command arg sequences as multisets. go-redis
// flattens an XADD Values MAP into positional args in random iteration order, so
// redismock's default positional DeepEqual is flaky; a multiset compare still
// verifies the stream, MAXLEN, and every field key/value — just order-free.
// NOTE: redismock's CustomMatch RETURNS A CLONE (clone.parent=m) — the caller
// MUST use the returned mock for Expect* calls, not the original.
func orderlessArgs(expected, actual []any) error {
	if len(expected) != len(actual) {
		return fmt.Errorf("arg count %d != %d", len(expected), len(actual))
	}
	counts := map[string]int{}
	for _, e := range expected {
		counts[fmt.Sprint(e)]++
	}
	for _, a := range actual {
		counts[fmt.Sprint(a)]--
	}
	for k, v := range counts {
		if v != 0 {
			return fmt.Errorf("arg multiset mismatch on %q", k)
		}
	}
	return nil
}

func floatPtr(f float64) *float64 { return &f }

// anyArgs builds n AnyArg matchers — pgxmock requires WithArgs to declare the
// arg count; the args themselves are exercised by the unit tests (e.g.
// parseJobMetaCampaignID, buildUsageFields), so here we match the FLOW not values.
func anyArgs(n int) []any {
	a := make([]any, n)
	for i := range a {
		a[i] = pgxmock.AnyArg()
	}
	return a
}

func TestFinalizeWithUsageOutbox_CompletedWritesOutboxInTx(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	defer mock.Close()
	repo := &Repo{pool: mock}

	jobID, owner, modelRef, camp := uuid.New(), uuid.New(), uuid.New(), uuid.New()
	jobMeta := []byte(`{"campaign_id":"` + camp.String() + `","chunk_idx":0}`)

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow(jobMeta))
	mock.ExpectExec("INSERT INTO usage_outbox").WithArgs(anyArgs(9)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	usage := &UsageOutbox{ModelSource: "user_model", ModelRef: modelRef,
		Operation: "translation", InputTokens: 120, OutputTokens: 30, CostUSD: floatPtr(0.0001)}
	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), jobID, owner,
		"completed", map[string]any{"x": 1}, "", "", "", usage, nil)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

// bug #24 — the usage-billing `purpose` (the Usage-GUI label) overrides the
// overloaded `operation` from job_meta.usage_purpose. Capture the 6th INSERT arg
// (operation column) to prove the label that lands is the purpose, NOT the
// chat-shaped operation the worker used.
func TestFinalizeWithUsageOutbox_UsagePurposeOverridesOperationLabel(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	jobMeta := []byte(`{"usage_purpose":"glossary_extraction","chapter_id":"x"}`)
	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow(jobMeta))
	// args[5] (0-based) is the `operation` column — assert the overridden label.
	insertArgs := anyArgs(9)
	insertArgs[5] = "glossary_extraction"
	mock.ExpectExec("INSERT INTO usage_outbox").WithArgs(insertArgs...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	usage := &UsageOutbox{ModelSource: "user_model", ModelRef: uuid.New(),
		Operation: "chat", InputTokens: 10, OutputTokens: 5, CostUSD: floatPtr(0.002)}
	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"completed", map[string]any{"x": 1}, "", "", "", usage, nil)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

// A malformed usage_purpose (illegal chars) must fail-soft → the real operation
// label is used, never the injected string.
func TestFinalizeWithUsageOutbox_MalformedUsagePurposeFallsBack(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	jobMeta := []byte(`{"usage_purpose":"Robert'); DROP TABLE usage_logs;--"}`)
	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow(jobMeta))
	insertArgs := anyArgs(9)
	insertArgs[5] = "chat" // fell back to the real operation
	mock.ExpectExec("INSERT INTO usage_outbox").WithArgs(insertArgs...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	usage := &UsageOutbox{ModelSource: "user_model", ModelRef: uuid.New(),
		Operation: "chat", InputTokens: 1, OutputTokens: 1, CostUSD: floatPtr(0.1)}
	if _, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"completed", nil, "", "", "", usage, nil); err != nil {
		t.Fatalf("err: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestParseJobMetaUsagePurpose(t *testing.T) {
	cases := []struct {
		name string
		meta string
		want string
	}{
		{"valid", `{"usage_purpose":"glossary_extraction"}`, "glossary_extraction"},
		{"valid_with_digits", `{"usage_purpose":"prose_draft2"}`, "prose_draft2"},
		{"absent", `{"campaign_id":"x"}`, ""},
		{"empty_meta", ``, ""},
		{"non_object", `["a"]`, ""},
		{"non_string", `{"usage_purpose":42}`, ""},
		{"leading_digit", `{"usage_purpose":"1bad"}`, ""},
		{"leading_underscore", `{"usage_purpose":"_bad"}`, ""},
		{"uppercase", `{"usage_purpose":"Chat"}`, ""},
		{"spaces", `{"usage_purpose":"glossary extraction"}`, ""},
		{"injection", `{"usage_purpose":"a'; DROP TABLE x;--"}`, ""},
		{"too_long", `{"usage_purpose":"` + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" + `"}`, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var meta []byte
			if c.meta != "" {
				meta = []byte(c.meta)
			}
			if got := parseJobMetaUsagePurpose(meta); got != c.want {
				t.Fatalf("parseJobMetaUsagePurpose=%q want %q", got, c.want)
			}
		})
	}
}

func TestFinalizeWithUsageOutbox_RaceLost_NoOutbox(t *testing.T) {
	// UPDATE matches 0 rows (cancel won the race) → QueryRow.Scan → ErrNoRows →
	// commit + return 0, and NO outbox INSERT (no ExpectExec; an unexpected call
	// would fail the mock).
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"})) // empty → ErrNoRows
	mock.ExpectCommit()

	usage := &UsageOutbox{ModelSource: "user_model", ModelRef: uuid.New(),
		Operation: "translation", InputTokens: 1, OutputTokens: 1, CostUSD: floatPtr(0.1)}
	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"completed", nil, "", "", "", usage, nil)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 0 {
		t.Fatalf("rows=%d want 0 (race lost)", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestFinalizeWithUsageOutbox_Failed_NoOutbox(t *testing.T) {
	// failed → usage nil → finalize UPDATE only, NO outbox INSERT.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow([]byte(`{}`)))
	mock.ExpectCommit()

	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"failed", nil, "LLM_ERR", "boom", "", nil, nil)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestDrainOnce_RoutesToStreamsAndMarksPublished(t *testing.T) {
	// Two unpublished rows: one campaign-tagged (→ usage + campaign streams), one
	// not (→ usage only). Verifies the dual-stream routing + per-row mark, all in
	// one tx. db-mock and redis-mock each validate their own ordered sequence.
	db, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	defer db.Close()
	rdb, rmock := redismock.NewClientMock()
	rxm := rmock.CustomMatch(orderlessArgs) // returns a clone — use it for ExpectXAdd
	relay := NewUsageRelay(rdb, db, RelayConfig{
		UsageStream: "u", CampaignUsageStream: "c",
		UsageMaxLen: 10, CampaignMaxLen: 10, BatchSize: 50,
	}, nil)

	camp := uuid.New().String()
	cost1 := "0.001"
	req1, req2 := uuid.New().String(), uuid.New().String()
	owner, modelRef := uuid.New().String(), uuid.New().String()

	cols := []string{"id", "request_id", "owner_user_id", "campaign_id", "model_source",
		"model_ref", "operation", "input_tokens", "output_tokens", "cost_usd"}
	db.ExpectBegin()
	// campaign_id + cost_usd scan into *string (nullable ::text); pgxmock needs the
	// row value to be a *string (real pgx coerces, the mock does not).
	db.ExpectQuery("SELECT").WithArgs(anyArgs(1)...).WillReturnRows(
		pgxmock.NewRows(cols).
			AddRow(int64(1), req1, owner, &camp, "user_model", modelRef, "translation", 10, 5, &cost1).
			AddRow(int64(2), req2, owner, (*string)(nil), "user_model", modelRef, "chat", 3, 2, (*string)(nil)),
	)

	f1 := buildUsageFields(req1, owner, camp, "user_model", modelRef, "translation", "0.001", 10, 5)
	f2 := buildUsageFields(req2, owner, "", "user_model", modelRef, "chat", "", 3, 2)
	// Row 1: usage + campaign. Row 2: usage only.
	rxm.ExpectXAdd(&redis.XAddArgs{Stream: "u", MaxLen: 10, Approx: true, Values: f1}).SetVal("1-0")
	rxm.ExpectXAdd(&redis.XAddArgs{Stream: "c", MaxLen: 10, Approx: true, Values: f1}).SetVal("1-0")
	db.ExpectExec("UPDATE usage_outbox SET published_at").WithArgs(anyArgs(1)...).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	rxm.ExpectXAdd(&redis.XAddArgs{Stream: "u", MaxLen: 10, Approx: true, Values: f2}).SetVal("2-0")
	db.ExpectExec("UPDATE usage_outbox SET published_at").WithArgs(anyArgs(1)...).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	db.ExpectCommit()

	n, err := relay.drainOnce(context.Background())
	if err != nil {
		t.Fatalf("drainOnce: %v", err)
	}
	if n != 2 {
		t.Fatalf("published=%d want 2", n)
	}
	if err := db.ExpectationsWereMet(); err != nil {
		t.Fatalf("db expectations: %v", err)
	}
	if err := rmock.ExpectationsWereMet(); err != nil {
		t.Fatalf("redis expectations: %v", err)
	}
}

func TestDrainOnce_EmptyBatch_NoXAddCommitsClean(t *testing.T) {
	db, _ := pgxmock.NewPool()
	defer db.Close()
	rdb, rmock := redismock.NewClientMock()
	relay := NewUsageRelay(rdb, db, RelayConfig{UsageStream: "u", CampaignUsageStream: "c", BatchSize: 50}, nil)

	cols := []string{"id", "request_id", "owner_user_id", "campaign_id", "model_source",
		"model_ref", "operation", "input_tokens", "output_tokens", "cost_usd"}
	db.ExpectBegin()
	db.ExpectQuery("SELECT").WithArgs(anyArgs(1)...).WillReturnRows(pgxmock.NewRows(cols)) // empty
	db.ExpectCommit()
	// No XADD expected.

	n, err := relay.drainOnce(context.Background())
	if err != nil {
		t.Fatalf("drainOnce: %v", err)
	}
	if n != 0 {
		t.Fatalf("published=%d want 0", n)
	}
	if err := db.ExpectationsWereMet(); err != nil {
		t.Fatalf("db expectations: %v", err)
	}
	if err := rmock.ExpectationsWereMet(); err != nil {
		t.Fatalf("redis expectations: %v", err)
	}
}

// ── LLM re-arch Phase 1 — durable terminal-event outbox ──────────────────────

func TestFinalizeWithUsageOutbox_WritesTerminalEvent(t *testing.T) {
	// A FAILED job (no usage) with a non-nil term → finalize UPDATE + the
	// job_event_outbox INSERT (every terminal status emits), NO usage INSERT.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow([]byte(`{}`)))
	mock.ExpectExec("INSERT INTO job_event_outbox").WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	term := &TerminalOutbox{Operation: "translation", ErrorCode: "LLM_ERR", ErrorMessage: "boom"}
	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"failed", nil, "LLM_ERR", "boom", "", nil, term)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestFinalizeWithUsageOutbox_CompletedWritesBothOutboxes(t *testing.T) {
	// completed + usage + term → usage_outbox INSERT THEN job_event_outbox INSERT,
	// both in the one tx.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(6)...).
		WillReturnRows(pgxmock.NewRows([]string{"job_meta"}).AddRow([]byte(`{}`)))
	mock.ExpectExec("INSERT INTO usage_outbox").WithArgs(anyArgs(9)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec("INSERT INTO job_event_outbox").WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	usage := &UsageOutbox{ModelSource: "user_model", ModelRef: uuid.New(),
		Operation: "chat", InputTokens: 10, OutputTokens: 5, CostUSD: floatPtr(0.002)}
	term := &TerminalOutbox{Operation: "chat", CostUSD: floatPtr(0.002)}
	rows, err := repo.FinalizeWithUsageOutbox(context.Background(), uuid.New(), uuid.New(),
		"completed", map[string]any{"x": 1}, "", "", "", usage, term)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestCancel_WritesTerminalEventInTx(t *testing.T) {
	// A real cancel transition → UPDATE…RETURNING operation,job_meta + the
	// job_event_outbox INSERT (status=cancelled), all in one tx.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"operation", "job_meta"}).
			AddRow("entity_extraction", []byte(`{}`)))
	mock.ExpectExec("INSERT INTO job_event_outbox").WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	rows, err := repo.Cancel(context.Background(), uuid.New(), uuid.New())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 1 {
		t.Fatalf("rows=%d want 1", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestCancel_NoRow_NoEventNoOp(t *testing.T) {
	// Already-terminal / not-found → UPDATE matches 0 rows → ErrNoRows → commit,
	// NO job_event INSERT, returns 0.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	repo := &Repo{pool: mock}

	mock.ExpectBegin()
	mock.ExpectQuery("UPDATE llm_jobs").WithArgs(anyArgs(2)...).
		WillReturnRows(pgxmock.NewRows([]string{"operation", "job_meta"})) // empty → ErrNoRows
	mock.ExpectCommit()

	rows, err := repo.Cancel(context.Background(), uuid.New(), uuid.New())
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if rows != 0 {
		t.Fatalf("rows=%d want 0", rows)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestDrainTerminalOnce_PublishesAndMarks(t *testing.T) {
	// One unpublished terminal row → XADD to the terminal stream + mark published,
	// in one tx. Nullable columns (cost_usd, error_*, campaign_id, correlation_id)
	// scan into *string.
	db, _ := pgxmock.NewPool()
	defer db.Close()
	rdb, rmock := redismock.NewClientMock()
	rxm := rmock.CustomMatch(orderlessArgs)
	relay := NewUsageRelay(rdb, db, RelayConfig{TerminalStream: "t", TerminalMaxLen: 10, BatchSize: 50}, nil)

	jobID, owner, camp := uuid.New().String(), uuid.New().String(), uuid.New().String()
	cost := "0.004"
	cols := []string{"id", "job_id", "owner_user_id", "operation", "status", "kind",
		"cost_usd", "error_code", "error_message", "campaign_id", "correlation_id"}
	db.ExpectBegin()
	db.ExpectQuery("SELECT").WithArgs(anyArgs(1)...).WillReturnRows(
		pgxmock.NewRows(cols).AddRow(int64(1), jobID, owner, "entity_extraction", "completed",
			"lm_studio", &cost, (*string)(nil), (*string)(nil), &camp, (*string)(nil)),
	)
	want := buildTerminalFields(jobID, owner, "entity_extraction", "completed", "lm_studio",
		"0.004", "", "", camp, "")
	rxm.ExpectXAdd(&redis.XAddArgs{Stream: "t", MaxLen: 10, Approx: true, Values: want}).SetVal("1-0")
	db.ExpectExec("UPDATE job_event_outbox SET published_at").WithArgs(anyArgs(1)...).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	db.ExpectCommit()

	n, err := relay.drainTerminalOnce(context.Background())
	if err != nil {
		t.Fatalf("drainTerminalOnce: %v", err)
	}
	if n != 1 {
		t.Fatalf("published=%d want 1", n)
	}
	if err := db.ExpectationsWereMet(); err != nil {
		t.Fatalf("db expectations: %v", err)
	}
	if err := rmock.ExpectationsWereMet(); err != nil {
		t.Fatalf("redis expectations: %v", err)
	}
}

func TestBuildTerminalFields_WireContract(t *testing.T) {
	f := buildTerminalFields("job-1", "owner-1", "translation", "failed", "openai",
		"0.01", "LLM_ERR", "boom", "camp-1", "corr-1")
	want := map[string]any{
		"job_id": "job-1", "owner_user_id": "owner-1", "operation": "translation",
		"status": "failed", "kind": "openai", "result_ref": "job-1",
		"cost_usd": "0.01", "error_code": "LLM_ERR", "error_message": "boom",
		"campaign_id": "camp-1", "correlation_id": "corr-1",
	}
	if len(f) != len(want) {
		t.Fatalf("field count %d != %d", len(f), len(want))
	}
	for k, v := range want {
		if f[k] != v {
			t.Fatalf("field %q = %v want %v", k, f[k], v)
		}
	}
	if f["result_ref"] != f["job_id"] {
		t.Fatalf("result_ref %v != job_id %v", f["result_ref"], f["job_id"])
	}
}
