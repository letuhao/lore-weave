package meta

import (
	"errors"
	"testing"
)

// pool_test.go — L1.G.4 Go DbPoolRegistry tests (cycle 5).
//
// Mirrors the Rust db_pool tests in services/world-service/src/db_pool.rs.
// Where the Rust port has a test, the Go port has the same test — the
// two registries are in lockstep on the (validate, conflict, per-host
// aggregate) invariants.

func cfg(defaultPool, reserve uint32) DbPoolConfig {
	return DbPoolConfig{
		PgbouncerEndpoint: "pg-shard-0:6432",
		MaxClientConn:     1000,
		DefaultPoolSize:   defaultPool,
		ReservePoolSize:   reserve,
		MinPoolSize:       5,
	}
}

func key(host string, role PoolRole) DbPoolKey {
	return DbPoolKey{Host: host, Role: role}
}

func TestPool_RegisterLookupRoundtrip(t *testing.T) {
	reg := NewDbPoolRegistry()
	k := key("pg-shard-0", PoolWriter)
	if err := reg.Register(k, cfg(25, 5)); err != nil {
		t.Fatalf("register: %v", err)
	}
	got, err := reg.Lookup(k)
	if err != nil {
		t.Fatalf("lookup: %v", err)
	}
	if got.DefaultPoolSize != 25 {
		t.Fatalf("got default %d, want 25", got.DefaultPoolSize)
	}
}

func TestPool_IdempotentReregisterSameConfig(t *testing.T) {
	reg := NewDbPoolRegistry()
	k := key("pg-shard-0", PoolWriter)
	if err := reg.Register(k, cfg(25, 5)); err != nil {
		t.Fatalf("first: %v", err)
	}
	if err := reg.Register(k, cfg(25, 5)); err != nil {
		t.Fatalf("idempotent re-register: %v", err)
	}
}

func TestPool_ConflictOnDifferentConfig(t *testing.T) {
	reg := NewDbPoolRegistry()
	k := key("pg-shard-0", PoolWriter)
	if err := reg.Register(k, cfg(25, 5)); err != nil {
		t.Fatalf("register: %v", err)
	}
	err := reg.Register(k, cfg(50, 5))
	if !errors.Is(err, ErrDbPoolConflict) {
		t.Fatalf("want ErrDbPoolConflict, got %v", err)
	}
}

func TestPool_RejectsZeroMaxClientConn(t *testing.T) {
	reg := NewDbPoolRegistry()
	c := cfg(25, 5)
	c.MaxClientConn = 0
	err := reg.Register(key("pg-shard-0", PoolWriter), c)
	if !errors.Is(err, ErrDbPoolInvalid) {
		t.Fatalf("want ErrDbPoolInvalid, got %v", err)
	}
}

func TestPool_RejectsClientConnOver5000Cap(t *testing.T) {
	reg := NewDbPoolRegistry()
	c := cfg(25, 5)
	c.MaxClientConn = MaxVirtualConnections + 1
	err := reg.Register(key("pg-shard-0", PoolWriter), c)
	if !errors.Is(err, ErrDbPoolInvalid) {
		t.Fatalf("want ErrDbPoolInvalid, got %v", err)
	}
}

func TestPool_RejectsMinOverDefault(t *testing.T) {
	reg := NewDbPoolRegistry()
	c := cfg(10, 5)
	c.MinPoolSize = 20
	err := reg.Register(key("pg-shard-0", PoolWriter), c)
	if !errors.Is(err, ErrDbPoolInvalid) {
		t.Fatalf("want ErrDbPoolInvalid, got %v", err)
	}
}

func TestPool_PerHostAggregateCapEnforced(t *testing.T) {
	reg := NewDbPoolRegistry()
	if err := reg.Register(key("pg-shard-0", PoolWriter), cfg(250, 5)); err != nil {
		t.Fatalf("writer: %v", err)
	}
	err := reg.Register(key("pg-shard-0", PoolReader), cfg(250, 5))
	if !errors.Is(err, ErrDbPoolInvalid) {
		t.Fatalf("want ErrDbPoolInvalid (aggregate cap), got %v", err)
	}
}

func TestPool_PerHostAggregateCapUnderLimitOK(t *testing.T) {
	reg := NewDbPoolRegistry()
	// 200 + 50 = 250 each role; 2 roles = 500 total → exactly at cap.
	if err := reg.Register(key("pg-shard-0", PoolWriter), cfg(200, 50)); err != nil {
		t.Fatalf("writer: %v", err)
	}
	if err := reg.Register(key("pg-shard-0", PoolReader), cfg(200, 50)); err != nil {
		t.Fatalf("reader: %v", err)
	}
}

func TestPool_DifferentHostsIndependentCaps(t *testing.T) {
	reg := NewDbPoolRegistry()
	if err := reg.Register(key("pg-shard-0", PoolWriter), cfg(250, 5)); err != nil {
		t.Fatalf("h0: %v", err)
	}
	if err := reg.Register(key("pg-shard-1", PoolWriter), cfg(250, 5)); err != nil {
		t.Fatalf("h1 (independent): %v", err)
	}
	if reg.Len() != 2 {
		t.Fatalf("expected 2 pools, got %d", reg.Len())
	}
}

func TestPool_MissingKeyReturnsTypedError(t *testing.T) {
	reg := NewDbPoolRegistry()
	_, err := reg.Lookup(key("nothere", PoolReader))
	if !errors.Is(err, ErrDbPoolMissing) {
		t.Fatalf("want ErrDbPoolMissing, got %v", err)
	}
}

func TestPool_RejectsBadRole(t *testing.T) {
	reg := NewDbPoolRegistry()
	err := reg.Register(DbPoolKey{Host: "pg-shard-0", Role: PoolRole("bogus")}, cfg(25, 5))
	if !errors.Is(err, ErrDbPoolInvalid) {
		t.Fatalf("want ErrDbPoolInvalid for bad role, got %v", err)
	}
}

func TestPool_CapsMatchRustConstants(t *testing.T) {
	// Defense-in-depth: these constants MUST equal the Rust constants in
	// services/world-service/src/db_pool.rs::MAX_VIRTUAL_CONNECTIONS +
	// MAX_BACKEND_CONNECTIONS. If you change one, change both.
	if MaxVirtualConnections != 5000 {
		t.Fatalf("MaxVirtualConnections drift: want 5000, got %d", MaxVirtualConnections)
	}
	if MaxBackendConnections != 500 {
		t.Fatalf("MaxBackendConnections drift: want 500, got %d", MaxBackendConnections)
	}
}
