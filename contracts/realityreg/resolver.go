// Package realityreg resolves the set of per-reality databases the publisher
// must drain, and the DSN to reach each one.
//
// Two concerns, split for testability:
//   - Resolver (this file): PURE shard-host→DSN mapping. The meta
//     `reality_registry.db_host` is a logical name
//     (`pg-shard-N.{internal|prod|staging}`, never `localhost`), so a
//     resolver turns (db_host, db_name) into a physical DSN. A dev override
//     remaps logical hosts to the foundation-dev Postgres.
//   - Registry (registry.go): pgx query against the meta DB for the active
//     realities. Lives behind a tiny Querier interface so it binds to
//     *pgxpool.Pool in production.
package realityreg

import (
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

// DSNConfig is the publisher's connection template for per-reality shards.
// User/Password/SSLMode are platform-wide (one app role across shards);
// the per-reality DB name comes from the registry row.
type DSNConfig struct {
	User     string
	Password string
	// Port is the shard Postgres port. Defaults to 5432 when zero.
	Port int
	// SSLMode maps to libpq sslmode. Defaults to "require" when empty
	// (prod-shaped); dev overrides to "disable".
	SSLMode string
	// HostOverride remaps a logical db_host → "host:port". A "*" key remaps
	// EVERY host (dev convenience: point all shards at one local Postgres).
	// An explicit db_host key wins over "*".
	HostOverride map[string]string
}

// ErrEmptyDBName is returned when a registry row carries an empty db_name.
var ErrEmptyDBName = errors.New("realityreg: empty db_name")

// ErrEmptyDBHost is returned when a registry row carries an empty db_host
// and no "*" override is configured.
var ErrEmptyDBHost = errors.New("realityreg: empty db_host and no wildcard override")

// DSN builds the libpq URL for one reality DB. The effective host:port is
// resolved as: explicit override for db_host → "*" override → db_host:Port.
func (c DSNConfig) DSN(dbHost, dbName string) (string, error) {
	if dbName == "" {
		return "", ErrEmptyDBName
	}

	hostPort, err := c.resolveHostPort(dbHost)
	if err != nil {
		return "", err
	}

	sslmode := c.SSLMode
	if sslmode == "" {
		sslmode = "require"
	}

	u := url.URL{
		Scheme:   "postgres",
		User:     url.UserPassword(c.User, c.Password),
		Host:     hostPort,
		Path:     "/" + dbName,
		RawQuery: "sslmode=" + url.QueryEscape(sslmode),
	}
	return u.String(), nil
}

// resolveHostPort returns the "host:port" to dial for a logical db_host.
func (c DSNConfig) resolveHostPort(dbHost string) (string, error) {
	port := c.Port
	if port == 0 {
		port = 5432
	}

	if c.HostOverride != nil {
		if hp, ok := c.HostOverride[dbHost]; ok && hp != "" {
			return hp, nil
		}
		if hp, ok := c.HostOverride["*"]; ok && hp != "" {
			return hp, nil
		}
	}
	if dbHost == "" {
		return "", ErrEmptyDBHost
	}
	return dbHost + ":" + strconv.Itoa(port), nil
}

// ParseHostOverride parses a comma-separated `host=host:port` list into a
// HostOverride map. Empty input yields a nil map (no overrides).
//
//	"pg-shard-0.internal=localhost:55432,*=localhost:55432"
//
// A bare `*=localhost:55432` remaps every shard host — the dev default.
func ParseHostOverride(s string) (map[string]string, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil, nil
	}
	out := map[string]string{}
	for _, pair := range strings.Split(s, ",") {
		pair = strings.TrimSpace(pair)
		if pair == "" {
			continue
		}
		k, v, ok := strings.Cut(pair, "=")
		k, v = strings.TrimSpace(k), strings.TrimSpace(v)
		if !ok || k == "" || v == "" {
			return nil, fmt.Errorf("realityreg: malformed host override %q (want host=host:port)", pair)
		}
		out[k] = v
	}
	if len(out) == 0 {
		return nil, nil
	}
	return out, nil
}
