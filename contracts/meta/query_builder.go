package meta

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

// PostgresQueryBuilder builds Postgres-flavored parameterized SQL for the
// supported MetaWrite operations + audit inserts. Sufficient for cycle 2;
// driver-flavor variants can wrap or replace as needed.
type PostgresQueryBuilder struct{}

// BuildInsert returns INSERT INTO <table> (cols...) VALUES (placeholders...).
func (PostgresQueryBuilder) BuildInsert(in MetaWriteIntent) (string, []any, error) {
	if len(in.NewValues) == 0 && len(in.PK) == 0 {
		return "", nil, fmt.Errorf("%w: BuildInsert needs values", ErrBadIntent)
	}
	// Merge PK + NewValues (NewValues wins on overlap).
	merged := make(map[string]any, len(in.PK)+len(in.NewValues))
	for k, v := range in.PK {
		merged[k] = v
	}
	for k, v := range in.NewValues {
		merged[k] = v
	}
	cols := sortedKeys(merged)
	placeholders := make([]string, len(cols))
	args := make([]any, len(cols))
	for i, c := range cols {
		placeholders[i] = fmt.Sprintf("$%d", i+1)
		args[i] = merged[c]
	}
	q := fmt.Sprintf(`INSERT INTO %s (%s) VALUES (%s)`,
		quoteIdent(in.Table), joinIdents(cols), strings.Join(placeholders, ", "))
	return q, args, nil
}

// BuildUpdate returns UPDATE <table> SET <newvals> WHERE <pk> [AND <expected>].
func (PostgresQueryBuilder) BuildUpdate(in MetaWriteIntent) (string, []any, error) {
	if len(in.NewValues) == 0 {
		return "", nil, fmt.Errorf("%w: BuildUpdate needs NewValues", ErrBadIntent)
	}
	if len(in.PK) == 0 {
		return "", nil, fmt.Errorf("%w: BuildUpdate needs PK", ErrBadIntent)
	}
	setCols := sortedKeys(in.NewValues)
	args := make([]any, 0, len(in.NewValues)+len(in.PK)+len(in.ExpectedBefore))

	setClauses := make([]string, len(setCols))
	idx := 1
	for i, c := range setCols {
		setClauses[i] = fmt.Sprintf("%s = $%d", quoteIdent(c), idx)
		args = append(args, in.NewValues[c])
		idx++
	}

	pkCols := sortedKeys(in.PK)
	whereParts := make([]string, 0, len(pkCols)+len(in.ExpectedBefore))
	for _, c := range pkCols {
		whereParts = append(whereParts, fmt.Sprintf("%s = $%d", quoteIdent(c), idx))
		args = append(args, in.PK[c])
		idx++
	}
	expCols := sortedKeys(in.ExpectedBefore)
	for _, c := range expCols {
		// A nil expected-value means "column IS NULL". `col = NULL` is never
		// true in SQL, so render it as an IS NULL predicate (no bound arg).
		// This lets callers CAS on an as-yet-unset column — e.g. revoke a
		// consent row only while revoked_at IS NULL (migration 011's documented
		// single-transition), or pseudonymize a ledger row only once.
		if in.ExpectedBefore[c] == nil {
			whereParts = append(whereParts, fmt.Sprintf("%s IS NULL", quoteIdent(c)))
			continue
		}
		whereParts = append(whereParts, fmt.Sprintf("%s = $%d", quoteIdent(c), idx))
		args = append(args, in.ExpectedBefore[c])
		idx++
	}
	q := fmt.Sprintf(`UPDATE %s SET %s WHERE %s`,
		quoteIdent(in.Table), strings.Join(setClauses, ", "), strings.Join(whereParts, " AND "))
	return q, args, nil
}

// BuildDelete returns DELETE FROM <table> WHERE <pk>.
func (PostgresQueryBuilder) BuildDelete(in MetaWriteIntent) (string, []any, error) {
	if len(in.PK) == 0 {
		return "", nil, fmt.Errorf("%w: BuildDelete needs PK", ErrBadIntent)
	}
	pkCols := sortedKeys(in.PK)
	whereParts := make([]string, len(pkCols))
	args := make([]any, len(pkCols))
	for i, c := range pkCols {
		whereParts[i] = fmt.Sprintf("%s = $%d", quoteIdent(c), i+1)
		args[i] = in.PK[c]
	}
	q := fmt.Sprintf(`DELETE FROM %s WHERE %s`,
		quoteIdent(in.Table), strings.Join(whereParts, " AND "))
	return q, args, nil
}

// BuildAuditInsert builds the INSERT for meta_write_audit. Columns match
// the S04 §12T.5 schema; payload columns marshaled to JSON.
func (PostgresQueryBuilder) BuildAuditInsert(row MetaWriteAuditRow) (string, []any, error) {
	pkJSON, err := marshalJSON(row.RowPK)
	if err != nil {
		return "", nil, fmt.Errorf("audit row_pk marshal: %w", err)
	}
	beforeJSON, err := marshalJSON(row.BeforeValues)
	if err != nil {
		return "", nil, fmt.Errorf("audit before marshal: %w", err)
	}
	afterJSON, err := marshalJSON(row.AfterValues)
	if err != nil {
		return "", nil, fmt.Errorf("audit after marshal: %w", err)
	}
	ctxJSON, err := marshalJSON(map[string]any{
		"trace_id":       row.RequestContext.TraceID,
		"request_id":     row.RequestContext.RequestID,
		"source_service": row.RequestContext.SourceService,
	})
	if err != nil {
		return "", nil, fmt.Errorf("audit context marshal: %w", err)
	}
	q := `INSERT INTO meta_write_audit
		(audit_id, table_name, operation, row_pk, before_values, after_values,
		 actor_type, actor_id, reason, request_context, created_at_nanos, scrub_version)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`
	args := []any{
		row.AuditID, row.TableName, string(row.Operation),
		pkJSON, beforeJSON, afterJSON,
		string(row.ActorType), row.ActorID, row.Reason, ctxJSON, row.CreatedAtNanos,
		row.ScrubVersion, // "" when no Scrubber configured (column is NOT NULL DEFAULT '')
	}
	return q, args, nil
}

// BuildLifecycleAuditInsert builds INSERT for lifecycle_transition_audit.
// Schema matches migrations/meta/004_lifecycle_transition_audit.up.sql.
func (PostgresQueryBuilder) BuildLifecycleAuditInsert(row LifecycleTransitionAuditRow) (string, []any, error) {
	payloadJSON, err := marshalJSON(row.Payload)
	if err != nil {
		return "", nil, fmt.Errorf("lifecycle payload marshal: %w", err)
	}
	q := `INSERT INTO lifecycle_transition_audit
		(audit_id, reality_id, from_status, to_status, actor_id, actor_type,
		 succeeded, failure_reason, payload, attempted_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, NULLIF($8, ''), $9, to_timestamp($10::double precision / 1e9))`
	args := []any{
		row.AuditID, row.ResourceID, row.FromStatus, row.ToStatus,
		row.ActorID, string(row.ActorType),
		row.Succeeded, row.FailureReason, payloadJSON, row.AttemptedAtNanos,
	}
	return q, args, nil
}

// --- helpers ---------------------------------------------------------------

func sortedKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

// quoteIdent quotes an identifier with double quotes (Postgres convention).
// Rejects identifiers containing double quotes (defense-in-depth — these
// table names come from caller code, not user input, but we still guard).
func quoteIdent(name string) string {
	if strings.Contains(name, `"`) {
		// We can't safely quote an identifier with embedded quotes; produce
		// a deliberately-broken SQL string so tests fail loudly. Real fix
		// is to reject at intent.Validate() time, but tables are static so
		// this branch is unreachable in normal flow.
		return `"<<invalid-identifier>>"`
	}
	return `"` + name + `"`
}

func joinIdents(cols []string) string {
	parts := make([]string, len(cols))
	for i, c := range cols {
		parts[i] = quoteIdent(c)
	}
	return strings.Join(parts, ", ")
}

func marshalJSON(v any) ([]byte, error) {
	if v == nil {
		return []byte("{}"), nil
	}
	return json.Marshal(v)
}
