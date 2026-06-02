// Package store binds the controller's DeployStore port to deploy_audit
// (migration 023). Reads go through the raw pgx pool (a SELECT needs no audit);
// writes go through contracts/meta MetaWrite() so each stage advance / rollback
// / completion lands a same-TX meta_write_audit row — the service_acl matrix
// requires it (canary-controller is the SOLE writer, SELECT+UPDATE, NO DELETE).
// CAS on canary_stage / rolled_back / completed_at guards concurrent ticks.
package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
)

// deployAuditTable is the meta table this store reads + (via MetaWrite) updates.
const deployAuditTable = "deploy_audit"

// serviceActorID stamps meta_write_audit.actor_id for the controller's writes.
const serviceActorID = "canary-controller"

// PgDeployStore implements controller.DeployStore.
type PgDeployStore struct {
	pool *pgxpool.Pool
	cfg  *meta.Config
}

var _ controller.DeployStore = (*PgDeployStore)(nil)

// NewPgDeployStore binds a caller-owned pool + a MetaWrite Config (whose DB
// SHOULD wrap the SAME pool via metapg.New so reads + audited writes share a
// connection source).
func NewPgDeployStore(pool *pgxpool.Pool, cfg *meta.Config) *PgDeployStore {
	return &PgDeployStore{pool: pool, cfg: cfg}
}

// historyEntry is one canary_history JSONB element. baseline_burn is captured
// by the deploy pipeline on the stage-0 entry (D-CANARY-BASELINE-CAPTURE);
// absent until that lands.
type historyEntry struct {
	Stage        int     `json:"stage"`
	At           string  `json:"at"` // RFC3339
	Reason       string  `json:"reason"`
	BaselineBurn float64 `json:"baseline_burn,omitempty"`
}

// ActiveCanary returns the single in-progress major deploy, or ok=false.
// canary.yml's concurrency group enforces one major canary at a time; LIMIT 1
// ORDER BY started_at DESC is the safety net.
func (s *PgDeployStore) ActiveCanary(ctx context.Context) (controller.DeployRecord, bool, error) {
	var (
		deployID    string
		class       string
		stage       int
		historyJSON []byte
		rolledBack  bool
		startedAt   time.Time
	)
	err := s.pool.QueryRow(ctx, `
		SELECT deploy_id, class, canary_stage, canary_history, rolled_back, started_at
		FROM deploy_audit
		WHERE class = 'major' AND completed_at IS NULL AND rolled_back = FALSE
		ORDER BY started_at DESC
		LIMIT 1`).Scan(&deployID, &class, &stage, &historyJSON, &rolledBack, &startedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return controller.DeployRecord{}, false, nil
		}
		return controller.DeployRecord{}, false, fmt.Errorf("store: query active canary: %w", err)
	}

	hist, err := parseHistory(historyJSON)
	if err != nil {
		return controller.DeployRecord{}, false, fmt.Errorf("store: deploy %s: %w", deployID, err)
	}
	// NOTE: the query filters rolled_back = FALSE, so RolledBack is ALWAYS false
	// on the live path — canary.Decide's `if st.Aborted` branch is therefore
	// unreachable in production (it's defensive, exercised only by unit tests).
	// We still pass it through honestly rather than hardcoding false.
	return controller.DeployRecord{
		DeployID:     deployID,
		Class:        class,
		Stage:        canary.Stage(stage),
		StageEntered: stageEnteredAt(hist, stage, startedAt),
		BaselineBurn: baselineBurn(hist),
		RolledBack:   rolledBack,
	}, true, nil
}

// AdvanceStage persists a stage advance + appends a canary_history entry, CAS on
// the prior stage so a concurrent tick cannot double-advance.
func (s *PgDeployStore) AdvanceStage(ctx context.Context, deployID string, to canary.Stage, at time.Time, reason string) error {
	curStage, hist, err := s.readStageHistory(ctx, deployID)
	if err != nil {
		return err
	}
	intent, err := buildAdvanceIntent(deployID, curStage, to, at, reason, hist)
	if err != nil {
		return err
	}
	if _, err := meta.MetaWrite(ctx, s.cfg, intent); err != nil {
		return fmt.Errorf("store: advance %s to stage %d: %w", deployID, int(to), err)
	}
	return nil
}

// MarkRolledBack sets rolled_back + reason + completed_at, CAS on rolled_back=false.
func (s *PgDeployStore) MarkRolledBack(ctx context.Context, deployID, reason string, at time.Time) error {
	if _, err := meta.MetaWrite(ctx, s.cfg, buildRollbackIntent(deployID, reason, at)); err != nil {
		return fmt.Errorf("store: mark rolled back %s: %w", deployID, err)
	}
	return nil
}

// MarkComplete sets completed_at on a finished rollout, CAS on completed_at IS NULL.
func (s *PgDeployStore) MarkComplete(ctx context.Context, deployID string, at time.Time) error {
	if _, err := meta.MetaWrite(ctx, s.cfg, buildCompleteIntent(deployID, at)); err != nil {
		return fmt.Errorf("store: mark complete %s: %w", deployID, err)
	}
	return nil
}

// readStageHistory reads the current canary_stage + canary_history for CAS.
func (s *PgDeployStore) readStageHistory(ctx context.Context, deployID string) (int, []historyEntry, error) {
	var (
		stage       int
		historyJSON []byte
	)
	err := s.pool.QueryRow(ctx,
		`SELECT canary_stage, canary_history FROM deploy_audit WHERE deploy_id = $1`, deployID).
		Scan(&stage, &historyJSON)
	if err != nil {
		return 0, nil, fmt.Errorf("store: read stage/history %s: %w", deployID, err)
	}
	hist, err := parseHistory(historyJSON)
	if err != nil {
		return 0, nil, fmt.Errorf("store: %s: %w", deployID, err)
	}
	return stage, hist, nil
}

// --- pure helpers (unit-tested without a DB) -------------------------------

// parseHistory unmarshals canary_history; an empty/NULL column is an empty slice.
func parseHistory(raw []byte) ([]historyEntry, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var hist []historyEntry
	if err := json.Unmarshal(raw, &hist); err != nil {
		return nil, fmt.Errorf("decode canary_history: %w", err)
	}
	return hist, nil
}

// stageEnteredAt finds when the current stage was entered: the timestamp of the
// most recent history entry for that stage, falling back to started_at (stage 0
// / no matching entry / unparseable timestamp).
func stageEnteredAt(hist []historyEntry, stage int, startedAt time.Time) time.Time {
	for i := len(hist) - 1; i >= 0; i-- {
		if hist[i].Stage == stage {
			if t, err := time.Parse(time.RFC3339, hist[i].At); err == nil {
				return t
			}
			break
		}
	}
	return startedAt
}

// baselineBurn reads the pre-deploy baseline from the first history entry that
// carries it; 0 when absent (D-CANARY-BASELINE-CAPTURE). A 0 baseline makes the
// 2× threshold 0 — any positive cohort burn aborts (fail-safe), but the
// deferral MUST clear before real rollouts or every canary aborts at stage 1.
func baselineBurn(hist []historyEntry) float64 {
	for _, h := range hist {
		if h.BaselineBurn > 0 {
			return h.BaselineBurn
		}
	}
	return 0
}

// buildAdvanceIntent builds the CAS UPDATE for a stage advance: set the new
// stage + the full appended history, expecting the prior stage unchanged.
func buildAdvanceIntent(deployID string, curStage int, to canary.Stage, at time.Time, reason string, hist []historyEntry) (meta.MetaWriteIntent, error) {
	next := append(append([]historyEntry(nil), hist...), historyEntry{
		Stage:  int(to),
		At:     at.UTC().Format(time.RFC3339),
		Reason: reason,
	})
	histJSON, err := json.Marshal(next)
	if err != nil {
		return meta.MetaWriteIntent{}, fmt.Errorf("store: marshal history: %w", err)
	}
	return meta.MetaWriteIntent{
		Table:     deployAuditTable,
		Operation: meta.OpUpdate,
		PK:        map[string]any{"deploy_id": deployID},
		NewValues: map[string]any{
			"canary_stage":   int(to),
			"canary_history": histJSON, // []byte -> jsonb (pgx)
		},
		// CAS: advance ONLY a row that is still live AND at the expected stage.
		// canary_stage alone is insufficient — a concurrent abort sets
		// rolled_back=true + completed_at WITHOUT changing canary_stage, so an
		// in-flight advance (read before the abort) would otherwise resurrect a
		// rolled-back deploy. Guarding rolled_back=false + completed_at IS NULL
		// makes the advance match 0 rows (ErrConcurrentStateTransition) once the
		// deploy has been aborted/completed by another tick.
		ExpectedBefore: map[string]any{
			"canary_stage": curStage,
			"rolled_back":  false,
			"completed_at": nil, // rendered as IS NULL
		},
		Actor:  meta.Actor{Type: meta.ActorService, ID: serviceActorID},
		Reason: reason,
	}, nil
}

// buildRollbackIntent builds the CAS UPDATE for an auto-abort rollback. The
// deploy_audit_rollback_reason_consistent CHECK requires reason NOT NULL when
// rolled_back=TRUE — both set here. CAS on rolled_back=false (idempotent abort).
func buildRollbackIntent(deployID, reason string, at time.Time) meta.MetaWriteIntent {
	return meta.MetaWriteIntent{
		Table:     deployAuditTable,
		Operation: meta.OpUpdate,
		PK:        map[string]any{"deploy_id": deployID},
		NewValues: map[string]any{
			"rolled_back":     true,
			"rollback_reason": reason,
			"completed_at":    at.UTC(),
		},
		ExpectedBefore: map[string]any{"rolled_back": false},
		Actor:          meta.Actor{Type: meta.ActorService, ID: serviceActorID},
		Reason:         reason,
	}
}

// buildCompleteIntent builds the CAS UPDATE that stamps completed_at on a
// finished (100%) rollout, only while completed_at IS NULL (idempotent).
//
// The CAS guards completed_at only — NOT rolled_back. That is safe by
// construction because buildRollbackIntent ALSO sets completed_at, so a
// rolled-back row already has completed_at NOT NULL and is excluded by this
// CAS. (If a future rollback path ever leaves completed_at NULL, add
// rolled_back:false here too.)
func buildCompleteIntent(deployID string, at time.Time) meta.MetaWriteIntent {
	return meta.MetaWriteIntent{
		Table:          deployAuditTable,
		Operation:      meta.OpUpdate,
		PK:             map[string]any{"deploy_id": deployID},
		NewValues:      map[string]any{"completed_at": at.UTC()},
		ExpectedBefore: map[string]any{"completed_at": nil}, // rendered as IS NULL
		Actor:          meta.Actor{Type: meta.ActorService, ID: serviceActorID},
		Reason:         "canary rollout complete",
	}
}
