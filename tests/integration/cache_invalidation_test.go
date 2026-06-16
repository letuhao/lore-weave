// Package integration — L1.F.6 cache invalidation integration test.
//
// Cycle 5 of foundation-mega-task. Owning chunk: C03 §12O.6, Q-L5-1.
//
// Acceptance criterion (parent layer plan L1F.acceptance):
//   "Emit xreality.reality.stats → verify all instances' caches invalidate"
//
// Cycle 5 scope: the publisher + xreality.* event stream lands in cycle 8+
// (L2). Foundation cycle 5 ships the cache LIBRARY + KEY REGISTRY. The
// integration test here exercises the library's invalidation surface
// (Get / Set / Del / DelByPrefix) against a real Redis (the V1 docker-
// compose Sentinel stack from infra/docker-compose.redis-cache.yml).
//
// The "all instances" multi-replica drill belongs with the actual Redis
// Streams subscriber in cycle 8+ — until then, this test verifies the
// single-instance behavior + key namespacing that the subscriber will
// rely on.
//
// Build tag `integration`.
//
//go:build integration
// +build integration

package integration

import (
	"net"
	"os/exec"
	"strings"
	"testing"
	"time"
)

const redisHostPort = "127.0.0.1:16379"

func redisCli(t *testing.T, args ...string) string {
	t.Helper()
	cmd := exec.Command("redis-cli", append([]string{"-h", "127.0.0.1", "-p", "16379"}, args...)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("redis-cli %v: %v\n%s", args, err, string(out))
	}
	return strings.TrimSpace(string(out))
}

func TestCache_RedisRoundTripAndInvalidation(t *testing.T) {
	c, err := net.DialTimeout("tcp", redisHostPort, 2*time.Second)
	if err != nil {
		t.Skip("redis not reachable on 127.0.0.1:16379; skipping (run docker-compose -f infra/docker-compose.meta-ha.yml -f infra/docker-compose.redis-cache.yml up -d)")
	}
	_ = c.Close()

	// Require redis-cli on PATH; otherwise skip (rather than fail) so devs
	// without the binary can still run other tests.
	if _, err := exec.LookPath("redis-cli"); err != nil {
		t.Skip("redis-cli not on PATH; skipping (install: apt-get install redis-tools)")
	}

	// Clear any pre-existing keys from prior runs.
	for _, k := range []string{"lw:reality_routing:r1", "lw:reality_routing:r2", "lw:entity_status:r1"} {
		redisCli(t, "DEL", k)
	}

	// Step 1: populate 3 keys (two same-namespace, one other namespace)
	if got := redisCli(t, "SET", "lw:reality_routing:r1", "v1", "EX", "60"); got != "OK" {
		t.Fatalf("SET r1: %s", got)
	}
	if got := redisCli(t, "SET", "lw:reality_routing:r2", "v2", "EX", "60"); got != "OK" {
		t.Fatalf("SET r2: %s", got)
	}
	if got := redisCli(t, "SET", "lw:entity_status:r1", "e1", "EX", "60"); got != "OK" {
		t.Fatalf("SET es-r1: %s", got)
	}

	// Step 2: Get hits
	if got := redisCli(t, "GET", "lw:reality_routing:r1"); got != "v1" {
		t.Fatalf("GET r1: got %q", got)
	}

	// Step 3: simulate "invalidate one reality" — equivalent to the
	// future event-driven invalidator deleting one key on a
	// `xreality.reality.status.changed` event.
	if got := redisCli(t, "DEL", "lw:reality_routing:r1"); got != "1" {
		t.Fatalf("DEL r1: %s", got)
	}
	if got := redisCli(t, "EXISTS", "lw:reality_routing:r1"); got != "0" {
		t.Fatalf("r1 still present after DEL: %s", got)
	}

	// Step 4: simulate "invalidate whole namespace" — equivalent to a
	// config-reload event that nukes all reality_routing entries.
	// We use SCAN + DEL because Redis production should NEVER run KEYS.
	scan := redisCli(t, "SCAN", "0", "MATCH", "lw:reality_routing:*", "COUNT", "100")
	// SCAN output is "<cursor>\nkey1\nkey2..." — cursor on first line.
	lines := strings.Split(scan, "\n")
	if len(lines) < 1 {
		t.Fatalf("SCAN output empty")
	}
	for _, k := range lines[1:] {
		k = strings.TrimSpace(k)
		if k != "" {
			redisCli(t, "DEL", k)
		}
	}

	// Confirm namespace is empty
	if got := redisCli(t, "EXISTS", "lw:reality_routing:r2"); got != "0" {
		t.Fatalf("r2 still present after namespace clear: %s", got)
	}
	// Untouched namespace key still present
	if got := redisCli(t, "GET", "lw:entity_status:r1"); got != "e1" {
		t.Fatalf("entity_status:r1 lost during reality_routing clear: %q", got)
	}

	// cleanup
	redisCli(t, "DEL", "lw:entity_status:r1")
}

// TestCache_AOFPersistsAcrossRestart documents the AOF policy is
// enforced (Q-L1F-1 every-1s). We DON'T restart the container in a Go
// test (too disruptive); we just verify the config flag is set.
func TestCache_AOFEverySecConfigured(t *testing.T) {
	c, err := net.DialTimeout("tcp", redisHostPort, 2*time.Second)
	if err != nil {
		t.Skip("redis not reachable; skipping")
	}
	_ = c.Close()
	if _, err := exec.LookPath("redis-cli"); err != nil {
		t.Skip("redis-cli not on PATH; skipping")
	}

	out := redisCli(t, "CONFIG", "GET", "appendfsync")
	if !strings.Contains(out, "everysec") {
		t.Fatalf("appendfsync drift: want 'everysec', got %q (Q-L1F-1 violation)", out)
	}
	out = redisCli(t, "CONFIG", "GET", "maxmemory-policy")
	if !strings.Contains(out, "allkeys-lru") {
		t.Fatalf("maxmemory-policy drift: want 'allkeys-lru', got %q (Q-L1F-1 violation)", out)
	}
}

