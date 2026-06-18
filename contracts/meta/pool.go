package meta

import (
	"fmt"
	"sync"
)

// pool.go — L1.G.4 Go extension for the per-shard-host pool registry.
//
// Mirrors `services/world-service/src/db_pool.rs` (Rust) so Go services
// that need to register pgbouncer-fronted pools at startup do so with the
// SAME capacity arithmetic. The Rust + Go ports share the per-host
// MAX_BACKEND_CONNECTIONS = 500 cap (matches infra/pgbouncer/pgbouncer.ini
// `max_db_connections = 500`).
//
// ## Why two ports
//
// Hot-path callers (world-service kernel) are Rust. Go services that ALSO
// need pgbouncer pools — meta-worker, publisher, migration-orchestrator —
// register here. Keeping the two registries SEPARATE (Rust process owns
// its own, Go process owns its own) is intentional: there is no shared
// process state to synchronize, and config drift is caught by the static
// pgbouncer.ini cap (max_db_connections) which both ports enforce locally.

// Pgbouncer / db_pool caps — keep IN SYNC with services/world-service/src/db_pool.rs.
const (
	// MaxVirtualConnections is the per-pgbouncer-instance client cap.
	MaxVirtualConnections uint32 = 5000
	// MaxBackendConnections is the per-pgbouncer-instance real-Postgres cap.
	MaxBackendConnections uint32 = 500
)

// PoolRole mirrors the Rust enum of the same name.
type PoolRole string

const (
	// PoolWriter routes to the Patroni leader.
	PoolWriter PoolRole = "writer"
	// PoolReader routes to the sync replica.
	PoolReader PoolRole = "reader"
	// PoolAsyncReader routes to the async replica.
	PoolAsyncReader PoolRole = "async_reader"
)

// IsValid reports whether r is one of the enumerated roles.
func (r PoolRole) IsValid() bool {
	switch r {
	case PoolWriter, PoolReader, PoolAsyncReader:
		return true
	}
	return false
}

// DbPoolKey is the composite registry key.
type DbPoolKey struct {
	// Host is the shard host (e.g. `pg-shard-0.internal`).
	Host string
	// Role is the connection role.
	Role PoolRole
}

// DbPoolConfig is the per-pool configuration.
type DbPoolConfig struct {
	// PgbouncerEndpoint is host:port — typically `<shard>:6432`.
	PgbouncerEndpoint string
	// MaxClientConn is the virtual client cap this pool requests.
	MaxClientConn uint32
	// DefaultPoolSize is the backend connection cap (pgbouncer default_pool_size).
	DefaultPoolSize uint32
	// ReservePoolSize is the spill above DefaultPoolSize (pgbouncer reserve_pool_size).
	ReservePoolSize uint32
	// MinPoolSize is the warm baseline.
	MinPoolSize uint32
}

// BackendCap computes the per-pool real-connection cap.
func (c DbPoolConfig) BackendCap() uint32 {
	return c.DefaultPoolSize + c.ReservePoolSize
}

// Validate runs the in-isolation invariant set.
func (c DbPoolConfig) Validate() error {
	if c.PgbouncerEndpoint == "" {
		return fmt.Errorf("%w: endpoint empty", ErrDbPoolInvalid)
	}
	if c.MaxClientConn == 0 {
		return fmt.Errorf("%w: max_client_conn must be > 0", ErrDbPoolInvalid)
	}
	if c.MaxClientConn > MaxVirtualConnections {
		return fmt.Errorf("%w: max_client_conn %d > MaxVirtualConnections %d",
			ErrDbPoolInvalid, c.MaxClientConn, MaxVirtualConnections)
	}
	if c.DefaultPoolSize == 0 {
		return fmt.Errorf("%w: default_pool_size must be > 0", ErrDbPoolInvalid)
	}
	if c.MinPoolSize > c.DefaultPoolSize {
		return fmt.Errorf("%w: min_pool_size %d > default_pool_size %d",
			ErrDbPoolInvalid, c.MinPoolSize, c.DefaultPoolSize)
	}
	if c.BackendCap() > MaxBackendConnections {
		return fmt.Errorf("%w: backend_cap %d > MaxBackendConnections %d",
			ErrDbPoolInvalid, c.BackendCap(), MaxBackendConnections)
	}
	return nil
}

// DbPoolRegistry is the Go-side mirror of the Rust DbPoolRegistry.
// Thread-safe via sync.RWMutex.
type DbPoolRegistry struct {
	mu    sync.RWMutex
	pools map[DbPoolKey]DbPoolConfig
}

// NewDbPoolRegistry returns an empty registry.
func NewDbPoolRegistry() *DbPoolRegistry {
	return &DbPoolRegistry{pools: make(map[DbPoolKey]DbPoolConfig)}
}

// Register adds a pool. Returns:
//   - nil on success (or idempotent re-register with identical config)
//   - ErrDbPoolConflict if the key is already registered with a DIFFERENT config
//   - ErrDbPoolInvalid if the config is malformed OR aggregate per-host
//     backend cap would be exceeded
func (r *DbPoolRegistry) Register(key DbPoolKey, cfg DbPoolConfig) error {
	if err := cfg.Validate(); err != nil {
		return err
	}
	if !key.Role.IsValid() {
		return fmt.Errorf("%w: role=%q", ErrDbPoolInvalid, key.Role)
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if existing, ok := r.pools[key]; ok {
		if existing == cfg {
			return nil
		}
		return fmt.Errorf("%w: %+v", ErrDbPoolConflict, key)
	}

	// Aggregate per-host backend count.
	var hostSum uint32
	for k, c := range r.pools {
		if k.Host == key.Host {
			hostSum += c.BackendCap()
		}
	}
	hostSum += cfg.BackendCap()
	if hostSum > MaxBackendConnections {
		return fmt.Errorf("%w: per-host %q aggregate backend_cap %d > %d",
			ErrDbPoolInvalid, key.Host, hostSum, MaxBackendConnections)
	}

	r.pools[key] = cfg
	return nil
}

// Lookup returns the pool config for key, or ErrDbPoolMissing.
func (r *DbPoolRegistry) Lookup(key DbPoolKey) (DbPoolConfig, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	c, ok := r.pools[key]
	if !ok {
		return DbPoolConfig{}, fmt.Errorf("%w: %+v", ErrDbPoolMissing, key)
	}
	return c, nil
}

// Len returns the total registered-pool count.
func (r *DbPoolRegistry) Len() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.pools)
}
