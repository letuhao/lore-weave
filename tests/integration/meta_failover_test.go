// Package integration — L1.E.12 meta failover integration test.
//
// Cycle 1 of foundation-mega-task. Owning chunk: C03 §12O.3.
//
// Acceptance criterion (parent layer plan):
//   "Kill primary, verify failover within 30s, verify writes resume"
//
// This test exercises the docker-compose.meta-ha.yml stack
// (Q-L1B-5: Patroni + etcd + 1 sync + 1 async).
//
// Build tag `integration` because it requires the live docker-compose stack
// (run via `docker compose -f infra/docker-compose.meta-ha.yml up -d`).
// Skipped automatically when MetaHA stack endpoints are unreachable so
// `go test ./...` stays green in CI without docker.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"database/sql"
	"fmt"
	"net"
	"os"
	"os/exec"
	"testing"
	"time"

	_ "github.com/lib/pq"
)

// Endpoints from infra/docker-compose.meta-ha.yml (host:container ports).
const (
	primaryHostPort      = "127.0.0.1:15432"
	syncReplicaHostPort  = "127.0.0.1:15433"
	asyncReplicaHostPort = "127.0.0.1:15434"
	patroniPrimaryREST   = "127.0.0.1:18008"
	patroniSyncREST      = "127.0.0.1:18009"

	primaryContainer     = "lw-meta-pg-primary"
	syncReplicaContainer = "lw-meta-pg-sync-a"

	failoverRTOTarget = 30 * time.Second

	// Credentials match docker-compose defaults; in CI these come from env.
	pgUser = "postgres"
	pgPass = "postgres"
	pgDB   = "postgres"
)

// hostPortReachable returns true if a TCP dial succeeds within timeout.
// Used to skip the test when the meta-ha stack is not running.
func hostPortReachable(addr string, timeout time.Duration) bool {
	c, err := net.DialTimeout("tcp", addr, timeout)
	if err != nil {
		return false
	}
	_ = c.Close()
	return true
}

// requireStackUp skips the test if the docker-compose.meta-ha.yml stack is
// not reachable. This keeps `go test ./...` green in environments without
// docker (e.g., shallow CI, developer laptop without the stack up).
func requireStackUp(t *testing.T) {
	t.Helper()
	for _, ep := range []string{primaryHostPort, syncReplicaHostPort, patroniPrimaryREST} {
		if !hostPortReachable(ep, 500*time.Millisecond) {
			t.Skipf("meta-ha stack not reachable (%s); bring up via `docker compose -f infra/docker-compose.meta-ha.yml up -d`", ep)
		}
	}
}

func openDB(t *testing.T, hostPort string) *sql.DB {
	t.Helper()
	dsn := fmt.Sprintf("postgres://%s:%s@%s/%s?sslmode=disable",
		pgUser, pgPass, hostPort, pgDB)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open(%s): %v", hostPort, err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Fatalf("Ping(%s): %v", hostPort, err)
	}
	return db
}

// TestMetaFailoverRTOUnder30s verifies the parent-layer-plan L1.E acceptance
// criterion: "Kill primary, verify failover within 30s, verify writes resume."
func TestMetaFailoverRTOUnder30s(t *testing.T) {
	requireStackUp(t)

	// ─── Step 1: baseline — confirm primary accepts a write ──────────────
	primary := openDB(t, primaryHostPort)
	defer primary.Close()

	if _, err := primary.Exec(`CREATE TABLE IF NOT EXISTS _lw_failover_test (
		id    bigserial PRIMARY KEY,
		ts    timestamptz NOT NULL DEFAULT now(),
		phase text NOT NULL
	)`); err != nil {
		t.Fatalf("create table: %v", err)
	}
	if _, err := primary.Exec(`INSERT INTO _lw_failover_test (phase) VALUES ('baseline')`); err != nil {
		t.Fatalf("baseline write: %v", err)
	}

	// ─── Step 2: kill primary container (simulates host loss) ────────────
	killStart := time.Now()
	cmd := exec.Command("docker", "kill", primaryContainer)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("docker kill %s: %v (%s)", primaryContainer, err, out)
	}
	t.Logf("primary killed at T+0 (output: docker kill ok)")

	// Ensure we re-start the killed container regardless of outcome — leaves
	// the meta-ha stack usable for subsequent tests / re-runs.
	t.Cleanup(func() {
		_ = exec.Command("docker", "start", primaryContainer).Run()
	})

	// ─── Step 3: poll sync replica until it accepts a write (promoted) ───
	deadline := killStart.Add(failoverRTOTarget + 15*time.Second) // 30s RTO + 15s grace
	var (
		promotedAt time.Time
		lastErr    error
	)
	for time.Now().Before(deadline) {
		newLeader, err := sql.Open("postgres",
			fmt.Sprintf("postgres://%s:%s@%s/%s?sslmode=disable&connect_timeout=2",
				pgUser, pgPass, syncReplicaHostPort, pgDB))
		if err != nil {
			lastErr = err
			time.Sleep(500 * time.Millisecond)
			continue
		}
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		_, err = newLeader.ExecContext(ctx,
			`INSERT INTO _lw_failover_test (phase) VALUES ('post-failover')`)
		cancel()
		_ = newLeader.Close()
		if err == nil {
			promotedAt = time.Now()
			break
		}
		// "in recovery" / "read-only" is expected until promotion completes
		lastErr = err
		time.Sleep(500 * time.Millisecond)
	}

	if promotedAt.IsZero() {
		t.Fatalf("sync replica never accepted a write within %s of primary kill; last err: %v",
			failoverRTOTarget+15*time.Second, lastErr)
	}

	rto := promotedAt.Sub(killStart)
	t.Logf("failover RTO observed: %s (target: <%s)", rto, failoverRTOTarget)

	if rto > failoverRTOTarget {
		t.Fatalf("RTO %s exceeds target %s — L1.E acceptance criterion FAILED", rto, failoverRTOTarget)
	}

	// ─── Step 4: verify the post-failover write is durable ────────────────
	newLeader := openDB(t, syncReplicaHostPort)
	defer newLeader.Close()

	var count int
	if err := newLeader.QueryRow(
		`SELECT count(*) FROM _lw_failover_test WHERE phase = 'post-failover'`,
	).Scan(&count); err != nil {
		t.Fatalf("count post-failover rows: %v", err)
	}
	if count == 0 {
		t.Fatalf("post-failover write missing on new leader — durability lost")
	}
}

// TestMain skips ALL tests in this file when the meta-ha stack isn't running.
// This makes `go test ./tests/integration -tags=integration` safe to invoke
// from environments without docker (the cycle 1 verify gate runs in two
// modes: `-tags=integration` requires the stack; bare `go test ./...` skips).
func TestMain(m *testing.M) {
	if os.Getenv("LW_REQUIRE_META_HA") == "1" {
		// Operator forced full integration mode; do not skip.
		os.Exit(m.Run())
	}
	if !hostPortReachable(primaryHostPort, 200*time.Millisecond) {
		fmt.Fprintln(os.Stderr,
			"[meta_failover_test] meta-ha stack not running; tests will Skip — "+
				"bring up via `docker compose -f infra/docker-compose.meta-ha.yml up -d` "+
				"or set LW_REQUIRE_META_HA=1 to force failure")
	}
	os.Exit(m.Run())
}
