// services/meta-worker/cmd/bridge-server — standalone runner for the W1.5
// provisioner meta-write bridge (pkg/bridge).
//
// The bridge is normally hosted IN-PROCESS by cmd/meta-worker (alongside its
// consumer). This thin standalone runner serves ONLY the bridge over a meta DB
// pool — used by the W1.5 live drill (and a valid deployment option where the
// bridge runs as its own pod) without needing Redis / the consumer loop.
//
// Fail-closed: refuses to start without METAWORKER_BRIDGE_TOKEN.
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/services/meta-worker/pkg/bridge"
)

type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "bridge-server:", err)
		os.Exit(1)
	}
}

func run() error {
	dsn := os.Getenv("META_DB_URL")
	token := os.Getenv("METAWORKER_BRIDGE_TOKEN")
	addr := envOr("METAWORKER_BRIDGE_ADDR", "127.0.0.1:8090")
	allowPath := envOr("META_ALLOWLIST_PATH", "contracts/meta/events_allowlist.yaml")
	transPath := envOr("META_TRANSITIONS_PATH", "contracts/meta/transitions.yaml")
	if dsn == "" || token == "" {
		return errors.New("META_DB_URL and METAWORKER_BRIDGE_TOKEN required (fail-closed)")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return fmt.Errorf("meta pool: %w", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("meta ping: %w", err)
	}

	allow, err := meta.LoadAllowlist(allowPath)
	if err != nil {
		return fmt.Errorf("allowlist: %w", err)
	}
	graph, err := meta.LoadTransitions(transPath)
	if err != nil {
		return fmt.Errorf("transitions: %w", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, Transitions: graph,
		QueryBuilder: meta.PostgresQueryBuilder{}, Clock: sysClock{}, UUIDGen: randUUID{},
	}
	bsrv, err := bridge.New(
		bridge.MetaRegistrar{Cfg: cfg, Caller: bridge.WorldServiceActorID},
		bridge.PgAuditSink{Pool: pool, Callee: "meta-worker"},
		token, "world-service",
	)
	if err != nil {
		return err
	}
	srv := &http.Server{Addr: addr, Handler: bsrv.Handler(), ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			fmt.Fprintln(os.Stderr, "bridge-server http:", err)
		}
	}()
	fmt.Fprintf(os.Stderr, "bridge-server listening on %s\n", addr)

	<-ctx.Done()
	shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	return srv.Shutdown(shutCtx)
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
