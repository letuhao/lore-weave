package api

// S4c — DB-mock coverage for the usage audit core + stream consumer handling.
// pgxmock verifies the writeUsageLog tx flow (idempotency, NO account_balances
// deduction — the retirement) + the consumer's handleMessage end-to-end. The
// XReadGroup→XAck loop is thin (statistics-service-templated) → D-S4C-CONSUMER-LIVE-SMOKE.

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"
)

const auditTestSecret = "01234567890123456789012345678901" // 32 chars → AES-256 key

func anyArgs(n int) []any {
	a := make([]any, n)
	for i := range a {
		a[i] = pgxmock.AnyArg()
	}
	return a
}

func sampleParams() usageLogParams {
	return usageLogParams{
		RequestID: uuid.New(), OwnerUserID: uuid.New(), ModelSource: "user_model",
		ModelRef: uuid.New(), InputTokens: 120, OutputTokens: 30, CostUSD: 0.0123,
		RequestStatus: "success", Purpose: "translation",
	}
}

func TestParseUsageEvent(t *testing.T) {
	req, owner, model := uuid.New().String(), uuid.New().String(), uuid.New().String()
	base := map[string]any{
		"request_id": req, "owner_user_id": owner, "model_source": "user_model",
		"model_ref": model, "operation": "translation", "input_tokens": "120",
		"output_tokens": "30", "cost_usd": "0.05", "request_status": "success",
	}
	p, err := parseUsageEvent(base)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if p.RequestID.String() != req || p.ModelSource != "user_model" || p.Purpose != "translation" {
		t.Fatalf("field mismatch: %+v", p)
	}
	if p.InputTokens != 120 || p.OutputTokens != 30 || p.CostUSD != 0.05 {
		t.Fatalf("numeric mismatch: %+v", p)
	}

	// cost_usd empty → flat fallback (totalTokens × flatCostPerToken).
	noCost := map[string]any{}
	for k, v := range base {
		noCost[k] = v
	}
	noCost["cost_usd"] = ""
	p2, err := parseUsageEvent(noCost)
	if err != nil {
		t.Fatalf("parse no-cost: %v", err)
	}
	if want := float64(150) * flatCostPerToken; p2.CostUSD != want {
		t.Fatalf("fallback cost: got %v want %v", p2.CostUSD, want)
	}

	// bad request_id → error (don't write a garbage audit row).
	bad := map[string]any{"request_id": "not-a-uuid", "owner_user_id": owner, "model_ref": model}
	if _, err := parseUsageEvent(bad); err == nil {
		t.Fatal("expected error on bad request_id")
	}
}

func TestRecordUsageParams_Mapping(t *testing.T) {
	// Guards the /record field mapping (no transposition) + the flat-cost compute,
	// without needing the HTTP handler (Server.pool is concrete).
	req, owner, model := uuid.New(), uuid.New(), uuid.New()
	p := recordUsageParams(recordUsageRequest{
		RequestID: req, OwnerUserID: owner, ProviderKind: "openai", ModelSource: "platform_model",
		ModelRef: model, InputTokens: 100, OutputTokens: 50, RequestStatus: "success", Purpose: "chat",
		InputPayload: map[string]any{"a": 1.0}, OutputPayload: map[string]any{"b": 2.0},
	})
	if p.RequestID != req || p.OwnerUserID != owner || p.ModelRef != model {
		t.Fatalf("uuid fields transposed: %+v", p)
	}
	if p.ProviderKind != "openai" || p.ModelSource != "platform_model" || p.Purpose != "chat" || p.RequestStatus != "success" {
		t.Fatalf("string fields: %+v", p)
	}
	if p.InputTokens != 100 || p.OutputTokens != 50 {
		t.Fatalf("token transposition: %+v", p)
	}
	if want := float64(150) * flatCostPerToken; p.CostUSD != want {
		t.Fatalf("flat cost: got %v want %v", p.CostUSD, want)
	}
	inMap, _ := p.InputPayload.(map[string]any)
	outMap, _ := p.OutputPayload.(map[string]any)
	if inMap["a"] != 1.0 || outMap["b"] != 2.0 {
		t.Fatalf("payloads dropped: %+v", p)
	}
}

func TestParseUsageEvent_CarriesPayloadsAndStatus(t *testing.T) {
	// #32 — the jobs-path stream now carries the traced request/response payloads
	// (truncated JSON text) + a real request_status. Absent payloads stay nil.
	owner, model := uuid.New(), uuid.New()
	ev := map[string]any{
		"request_id": uuid.New().String(), "owner_user_id": owner.String(),
		"model_ref": model.String(), "input_tokens": "10", "output_tokens": "5",
		"request_status": "failed", "operation": "glossary_extraction",
		"request_payload": `{"messages":[]}`, "response_payload": "",
	}
	p, err := parseUsageEvent(ev)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if p.RequestStatus != "failed" {
		t.Fatalf("request_status: got %q want failed", p.RequestStatus)
	}
	if p.InputPayload != `{"messages":[]}` {
		t.Fatalf("request payload not carried: %v", p.InputPayload)
	}
	if p.OutputPayload != nil {
		t.Fatalf("absent response payload must be nil, got %v", p.OutputPayload)
	}
}

func TestWriteUsageLog_FreshWritesAuditNoBalanceDeduction(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock: %v", err)
	}
	defer mock.Close()

	mock.ExpectBegin()
	mock.ExpectQuery("INSERT INTO usage_logs").WithArgs(anyArgs(16)...).
		WillReturnRows(pgxmock.NewRows([]string{"usage_log_id"}).AddRow(uuid.New()))
	mock.ExpectExec("INSERT INTO usage_log_details").WithArgs(anyArgs(4)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	// NO "UPDATE account_balances" expectation — the retirement means writeUsageLog
	// must NOT deduct; an unexpected Exec would fail the mock.

	tx, err := mock.Begin(context.Background())
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	id, cost, fresh, err := testServer(auditTestSecret).writeUsageLog(context.Background(), tx, sampleParams())
	if err != nil {
		t.Fatalf("writeUsageLog: %v", err)
	}
	if !fresh || id == uuid.Nil || cost != 0.0123 {
		t.Fatalf("unexpected: fresh=%v id=%v cost=%v", fresh, id, cost)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestWriteUsageLog_DuplicateRereadsNoDetails(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()

	existing := uuid.New()
	mock.ExpectBegin()
	mock.ExpectQuery("INSERT INTO usage_logs").WithArgs(anyArgs(16)...).
		WillReturnRows(pgxmock.NewRows([]string{"usage_log_id"})) // empty → ErrNoRows (dup)
	mock.ExpectQuery("SELECT usage_log_id, total_cost_usd FROM usage_logs").WithArgs(anyArgs(1)...).
		WillReturnRows(pgxmock.NewRows([]string{"usage_log_id", "total_cost_usd"}).AddRow(existing, 9.99))
	// NO details insert on a duplicate.

	tx, _ := mock.Begin(context.Background())
	id, cost, fresh, err := testServer(auditTestSecret).writeUsageLog(context.Background(), tx, sampleParams())
	if err != nil {
		t.Fatalf("writeUsageLog: %v", err)
	}
	if fresh || id != existing || cost != 9.99 {
		t.Fatalf("dup path: fresh=%v id=%v cost=%v", fresh, id, cost)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestHandleMessage_WritesAuditInTx(t *testing.T) {
	mock, _ := pgxmock.NewPool()
	defer mock.Close()

	mock.ExpectBegin()
	mock.ExpectQuery("INSERT INTO usage_logs").WithArgs(anyArgs(16)...).
		WillReturnRows(pgxmock.NewRows([]string{"usage_log_id"}).AddRow(uuid.New()))
	mock.ExpectExec("INSERT INTO usage_log_details").WithArgs(anyArgs(4)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	c := NewUsageConsumer(nil, mock, testServer(auditTestSecret), "", "", "", nil)
	values := map[string]any{
		"request_id": uuid.New().String(), "owner_user_id": uuid.New().String(),
		"model_source": "user_model", "model_ref": uuid.New().String(),
		"operation": "translation", "input_tokens": "10", "output_tokens": "5",
		"cost_usd": "0.001", "request_status": "success",
	}
	permanent, err := c.handleMessage(context.Background(), values)
	if err != nil || permanent {
		t.Fatalf("handleMessage: permanent=%v err=%v", permanent, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("expectations: %v", err)
	}
}

func TestHandleMessage_MalformedEventIsPermanent(t *testing.T) {
	// A bad event (unparseable request_id) is a PERMANENT failure → the loop drops
	// it (acks) rather than retrying forever. No DB work attempted.
	mock, _ := pgxmock.NewPool()
	defer mock.Close()
	c := NewUsageConsumer(nil, mock, testServer(auditTestSecret), "", "", "", nil)
	permanent, err := c.handleMessage(context.Background(), map[string]any{"request_id": "not-a-uuid"})
	if err == nil || !permanent {
		t.Fatalf("expected permanent error, got permanent=%v err=%v", permanent, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil { // no Begin expected — parse fails first
		t.Fatalf("expectations: %v", err)
	}
}
