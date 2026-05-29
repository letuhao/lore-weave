package meta

import (
	"context"
	"errors"
	"fmt"
	"sort"

	"github.com/google/uuid"
)

// Tx is a minimal interface that the library uses to execute writes inside a
// transaction. Production callers wrap *sql.Tx; tests provide an in-memory
// fake (see tx_fake_test.go).
//
// Keeping the interface tiny (Exec + audit hook) means the library has no
// driver dependency, so it builds cleanly with only stdlib + uuid + yaml.
type Tx interface {
	// Exec runs a parameterized statement and returns rowsAffected.
	Exec(ctx context.Context, query string, args ...any) (rowsAffected int64, err error)
}

// DB abstracts the bare minimum to begin/commit/rollback a transaction.
type DB interface {
	// BeginTx starts a new transaction. The returned Commit/Rollback funcs
	// finalize the TX exactly once each.
	BeginTx(ctx context.Context) (tx Tx, commit func() error, rollback func() error, err error)
}

// OutboxAppender appends one outbox event row inside the same TX. The library
// asks the caller for this via the Config to avoid hard-coding the outbox
// table name (R06).
type OutboxAppender interface {
	// Append writes ONE outbox event row using the supplied Tx.
	Append(ctx context.Context, tx Tx, event OutboxEvent) error
}

// OutboxEvent is the minimal envelope handed to the OutboxAppender.
type OutboxEvent struct {
	EventID      uuid.UUID
	EventName    string
	AggregateID  string
	Payload      map[string]any
	RecordedAt   int64 // unix nanos
}

// QueryBuilder generates the SQL for a single MetaWriteIntent. Driver-agnostic
// (kept private) so the library can stay stdlib-clean; tests inject fakes.
type QueryBuilder interface {
	BuildInsert(intent MetaWriteIntent) (query string, args []any, err error)
	BuildUpdate(intent MetaWriteIntent) (query string, args []any, err error)
	BuildDelete(intent MetaWriteIntent) (query string, args []any, err error)
	BuildAuditInsert(row MetaWriteAuditRow) (query string, args []any, err error)
	BuildLifecycleAuditInsert(row LifecycleTransitionAuditRow) (query string, args []any, err error)
}

// MetaWriteAuditRow is what audit_writer.go inserts into meta_write_audit
// in the same TX as the data write. Fields mirror S04 §12T.5.
type MetaWriteAuditRow struct {
	AuditID         uuid.UUID
	TableName       string
	Operation       MetaWriteOp
	RowPK           map[string]any
	BeforeValues    map[string]any
	AfterValues     map[string]any
	ActorType       ActorType
	ActorID         string
	Reason          string
	RequestContext  RequestContext
	CreatedAtNanos  int64
}

// LifecycleTransitionAuditRow mirrors lifecycle_transition_audit (L1A §1.4).
type LifecycleTransitionAuditRow struct {
	AuditID          uuid.UUID
	ResourceID       string
	FromStatus       string
	ToStatus         string
	ActorID          string
	ActorType        ActorType
	Succeeded        bool
	FailureReason    string // empty when succeeded
	Payload          map[string]any
	AttemptedAtNanos int64
}

// Clock lets tests inject a deterministic time source.
type Clock interface {
	NowUnixNano() int64
}

// UUIDGen lets tests inject a deterministic UUID source.
type UUIDGen interface {
	New() uuid.UUID
}

// Config plumbs the library's runtime collaborators.
type Config struct {
	DB             DB
	Allowlist      Allowlist
	Transitions    *TransitionGraph
	Outbox         OutboxAppender // optional; nil = events skipped
	QueryBuilder   QueryBuilder
	Clock          Clock
	UUIDGen        UUIDGen
}

// Validate checks Config has the required collaborators.
func (c *Config) Validate() error {
	if c == nil {
		return fmt.Errorf("meta: Config is nil")
	}
	if c.DB == nil {
		return fmt.Errorf("meta: Config.DB is nil")
	}
	if c.Allowlist == nil {
		return fmt.Errorf("meta: Config.Allowlist is nil")
	}
	if c.QueryBuilder == nil {
		return fmt.Errorf("meta: Config.QueryBuilder is nil")
	}
	if c.Clock == nil {
		return fmt.Errorf("meta: Config.Clock is nil")
	}
	if c.UUIDGen == nil {
		return fmt.Errorf("meta: Config.UUIDGen is nil")
	}
	return nil
}

// MetaWrite executes one MetaWriteIntent inside its own TX, writes a
// meta_write_audit row in the SAME TX, and (when applicable) emits one
// outbox event via the configured OutboxAppender.
//
// On CAS mismatch (UPDATE matches 0 rows when ExpectedBefore is set),
// returns ErrConcurrentStateTransition.
func MetaWrite(ctx context.Context, cfg *Config, intent MetaWriteIntent) (*MetaWriteResult, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if err := intent.Validate(cfg.Allowlist); err != nil {
		return nil, err
	}
	res, err := metaWriteOne(ctx, cfg, intent)
	return res, err
}

// MetaWriteBatch executes a slice of MetaWriteIntents inside a SINGLE TX
// — Q-L1B-3 resolution: multi-table TX helper.  Each intent contributes one
// meta_write_audit row in the same TX; on ANY failure the TX is rolled back
// and ErrConcurrentStateTransition / ErrBadIntent / ... bubbles up.
//
// Returns the per-intent results in the same order as input; nil on failure.
func MetaWriteBatch(ctx context.Context, cfg *Config, intents []MetaWriteIntent) ([]*MetaWriteResult, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if len(intents) == 0 {
		return nil, fmt.Errorf("%w: empty batch", ErrBadIntent)
	}
	// Validate all up front so we don't write a partial batch into the audit.
	for i, in := range intents {
		if err := in.Validate(cfg.Allowlist); err != nil {
			return nil, fmt.Errorf("intent[%d]: %w", i, err)
		}
	}

	tx, commit, rollback, err := cfg.DB.BeginTx(ctx)
	if err != nil {
		return nil, fmt.Errorf("meta: BeginTx: %w", err)
	}
	defer func() { _ = rollback() }()

	results := make([]*MetaWriteResult, 0, len(intents))
	for i, in := range intents {
		r, err := writeOneInTx(ctx, cfg, tx, in)
		if err != nil {
			return nil, fmt.Errorf("intent[%d]: %w", i, err)
		}
		results = append(results, r)
	}
	if err := commit(); err != nil {
		return nil, fmt.Errorf("meta: commit: %w", err)
	}
	return results, nil
}

// metaWriteOne wraps the single-intent path with its own TX.
func metaWriteOne(ctx context.Context, cfg *Config, in MetaWriteIntent) (*MetaWriteResult, error) {
	tx, commit, rollback, err := cfg.DB.BeginTx(ctx)
	if err != nil {
		return nil, fmt.Errorf("meta: BeginTx: %w", err)
	}
	defer func() { _ = rollback() }()

	res, err := writeOneInTx(ctx, cfg, tx, in)
	if err != nil {
		return nil, err
	}
	if err := commit(); err != nil {
		return nil, fmt.Errorf("meta: commit: %w", err)
	}
	return res, nil
}

// writeOneInTx executes intent inside the supplied tx, returns the result;
// caller is responsible for tx commit/rollback.
func writeOneInTx(ctx context.Context, cfg *Config, tx Tx, in MetaWriteIntent) (*MetaWriteResult, error) {
	var (
		query string
		args  []any
		err   error
	)
	switch in.Operation {
	case OpInsert:
		query, args, err = cfg.QueryBuilder.BuildInsert(in)
	case OpUpdate:
		query, args, err = cfg.QueryBuilder.BuildUpdate(in)
	case OpDelete:
		query, args, err = cfg.QueryBuilder.BuildDelete(in)
	default:
		return nil, fmt.Errorf("%w: operation=%q", ErrBadIntent, in.Operation)
	}
	if err != nil {
		return nil, fmt.Errorf("meta: build %s: %w", in.Operation, err)
	}
	rows, err := tx.Exec(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("meta: exec %s on %s: %w", in.Operation, in.Table, err)
	}
	if in.Operation == OpUpdate && len(in.ExpectedBefore) > 0 && rows == 0 {
		return nil, ErrConcurrentStateTransition
	}
	if in.Operation == OpDelete && rows == 0 {
		// Treat 0-row delete as concurrent — caller wanted to remove a row
		// that's no longer there.
		return nil, ErrConcurrentStateTransition
	}

	// Audit row in same TX
	auditID := cfg.UUIDGen.New()
	auditRow := MetaWriteAuditRow{
		AuditID:        auditID,
		TableName:      in.Table,
		Operation:      in.Operation,
		RowPK:          in.PK,
		BeforeValues:   in.ExpectedBefore,
		AfterValues:    in.NewValues,
		ActorType:      in.Actor.Type,
		ActorID:        in.Actor.ID,
		Reason:         in.Reason,
		RequestContext: in.RequestContext,
		CreatedAtNanos: cfg.Clock.NowUnixNano(),
	}
	auditQuery, auditArgs, err := cfg.QueryBuilder.BuildAuditInsert(auditRow)
	if err != nil {
		return nil, fmt.Errorf("meta: build audit: %w", err)
	}
	if _, err := tx.Exec(ctx, auditQuery, auditArgs...); err != nil {
		return nil, fmt.Errorf("meta: exec audit: %w", err)
	}

	// Outbox event in same TX (if registered + appender configured)
	if cfg.Outbox != nil {
		if eventName, ok := cfg.Allowlist.EmitsEvent(in.Table, in.Operation); ok {
			ev := OutboxEvent{
				EventID:     cfg.UUIDGen.New(),
				EventName:   eventName,
				AggregateID: pkAsString(in.PK),
				Payload: map[string]any{
					"table":     in.Table,
					"operation": string(in.Operation),
					"pk":        in.PK,
					"after":     in.NewValues,
				},
				RecordedAt: cfg.Clock.NowUnixNano(),
			}
			if err := cfg.Outbox.Append(ctx, tx, ev); err != nil {
				return nil, fmt.Errorf("meta: outbox append: %w", err)
			}
		}
	}

	return &MetaWriteResult{
		AuditID:      auditID,
		RowsAffected: int(rows),
		NewValues:    in.NewValues,
	}, nil
}

// pkAsString joins PK fields into a stable string aggregate ID for outbox.
// Multi-column PKs are sorted by key name to keep the aggregate_id stable
// across processes (outbox consumers rely on stable aggregate_id for ordering).
func pkAsString(pk map[string]any) string {
	if len(pk) == 0 {
		return ""
	}
	if len(pk) == 1 {
		for _, v := range pk {
			return fmt.Sprintf("%v", v)
		}
	}
	keys := make([]string, 0, len(pk))
	for k := range pk {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := ""
	for _, k := range keys {
		if out != "" {
			out += "|"
		}
		out += fmt.Sprintf("%s=%v", k, pk[k])
	}
	return out
}

// IsConcurrent reports whether err signals a CAS lost race; callers can
// switch on this to decide refresh-and-retry vs surface to user.
func IsConcurrent(err error) bool { return errors.Is(err, ErrConcurrentStateTransition) }
