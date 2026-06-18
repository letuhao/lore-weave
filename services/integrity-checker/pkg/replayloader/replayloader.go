// Package replayloader invokes the world-service `replay-aggregate` binary (the
// L3.E/F keystone) to re-derive ONE sampled projection row, and parses its JSON
// result. It is the live backing for the comparator's AggregateLoader (wired in
// slice 2b): given a sampled row's owning aggregate(s), boundary event, and PK,
// it returns the row's canonical `to_jsonb - meta` payload as the replay
// believes it should be — which the comparator byte-compares against the live
// projection row.
//
// The bin's contract (see services/world-service/src/bin/replay-aggregate.rs):
// exit 0 ⇒ exactly one [ReplayResult] JSON on stdout (status "ok" or "error");
// exit non-zero ⇒ a bad invocation (treated as a HARD error here → the caller
// SKIPs the sample). REALITY_DB_URL carries the per-reality DSN (password off
// the arg vector / `ps`).
package replayloader

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/tablemap"
)

// ReplayRequest is one row's replay invocation.
type ReplayRequest struct {
	RealityID uuid.UUID
	// DSN is the per-reality shard DSN, passed to the bin as REALITY_DB_URL.
	DSN string
	// Projection is the target L3.A table.
	Projection string
	// Owning is the aggregate(s) to replay: one for single-aggregate tables,
	// two for npc_session_memory_projection (session + npc).
	Owning []tablemap.OwningAggregate
	// BoundaryEventID is the sampled row's event_id — replay stops at this event.
	BoundaryEventID uuid.UUID
	// PK is the sampled row's primary key (column → text value).
	PK map[string]string
}

// ReplayResult mirrors the replay-aggregate bin's stdout JSON.
type ReplayResult struct {
	// Found is true when the replay produced a row at the requested PK.
	Found bool `json:"found"`
	// EventsReplayed counts events replayed (≤ boundary). 0 ⇒ no in-bound
	// events (pruned / never existed / boundary missing) ⇒ SKIP.
	EventsReplayed uint64 `json:"events_replayed"`
	// Status is "ok" on a clean replay, "error" on a replay failure (⇒ SKIP).
	Status string `json:"status"`
	// Payload is the replayed row's canonical `to_jsonb - meta` (nil when not
	// found). Raw so the comparator can canonicalize + byte-compare it.
	Payload json.RawMessage `json:"payload,omitempty"`
	// Error is set only when Status == "error".
	Error string `json:"error,omitempty"`
}

// Skippable reports whether the result cannot yield a drift verdict and must be
// counted SKIPPED rather than clean/drifted: a replay error, or zero in-bound
// events (the aggregate's history could not be replayed at the boundary). A
// `found:false` with events > 0 is NOT skippable — it is an orphan-row DRIFT.
func (r ReplayResult) Skippable() (bool, string) {
	if r.Status != "ok" {
		if r.Error != "" {
			return true, "replay error: " + r.Error
		}
		return true, "replay status " + r.Status
	}
	if r.EventsReplayed == 0 {
		return true, "no in-bound events for the aggregate(s) (pruned / boundary missing)"
	}
	return false, ""
}

// Runner executes the replay-aggregate bin. Abstracted so the Loader is
// unit-testable without a child process or a DB.
type Runner interface {
	// Run executes the bin with `args`, exporting REALITY_DB_URL=dsn, and
	// returns stdout. A non-nil error means the process failed to start or
	// exited non-zero (a HARD failure — the caller SKIPs the sample).
	Run(ctx context.Context, dsn string, args []string) ([]byte, error)
}

// Loader builds the bin's args, runs it, and parses the result.
type Loader struct {
	runner Runner
}

// New constructs a Loader.
func New(r Runner) (*Loader, error) {
	if r == nil {
		return nil, errors.New("replayloader: Runner nil")
	}
	return &Loader{runner: r}, nil
}

// Replay runs the bin for one row and returns the parsed result. A run error
// (bad invocation / non-zero exit) is returned as an error; a soft replay error
// surfaces as a ReplayResult with Status=="error" (caller inspects Skippable).
func (l *Loader) Replay(ctx context.Context, req ReplayRequest) (ReplayResult, error) {
	args, err := buildArgs(req)
	if err != nil {
		return ReplayResult{}, err
	}
	out, err := l.runner.Run(ctx, req.DSN, args)
	if err != nil {
		return ReplayResult{}, fmt.Errorf("replayloader: run replay-aggregate: %w", err)
	}
	var res ReplayResult
	if err := json.Unmarshal(out, &res); err != nil {
		return ReplayResult{}, fmt.Errorf("replayloader: parse output: %w (stdout=%q)", err, string(out))
	}
	return res, nil
}

// buildArgs assembles the bin's flag vector (pure — unit-tested).
func buildArgs(req ReplayRequest) ([]string, error) {
	if req.Projection == "" {
		return nil, errors.New("replayloader: empty Projection")
	}
	if len(req.Owning) == 0 {
		return nil, errors.New("replayloader: no owning aggregates")
	}
	if len(req.PK) == 0 {
		return nil, errors.New("replayloader: empty PK")
	}
	pkJSON, err := json.Marshal(req.PK)
	if err != nil {
		return nil, fmt.Errorf("replayloader: marshal PK: %w", err)
	}
	args := []string{
		"--reality-id", req.RealityID.String(),
		"--projection", req.Projection,
		"--boundary-event-id", req.BoundaryEventID.String(),
		"--pk", string(pkJSON),
	}
	for _, o := range req.Owning {
		if o.Type == "" || o.ID == "" {
			return nil, fmt.Errorf("replayloader: invalid owning aggregate %+v (empty type or id)", o)
		}
		args = append(args, "--aggregate", o.Type+":"+o.ID)
	}
	return args, nil
}

// ExecRunner is the production Runner — it spawns the replay-aggregate binary.
type ExecRunner struct {
	// BinPath is the path to (or name on PATH of) the replay-aggregate binary.
	BinPath string
}

// Run executes the bin with REALITY_DB_URL=dsn in its environment.
func (e ExecRunner) Run(ctx context.Context, dsn string, args []string) ([]byte, error) {
	if e.BinPath == "" {
		return nil, errors.New("replayloader: ExecRunner.BinPath empty")
	}
	cmd := exec.CommandContext(ctx, e.BinPath, args...)
	// REALITY_DB_URL keeps the password out of the arg vector (off `ps`).
	cmd.Env = append(os.Environ(), "REALITY_DB_URL="+dsn)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("replay-aggregate %v: %w (stderr=%q)", args, err, stderr.String())
	}
	return stdout.Bytes(), nil
}
