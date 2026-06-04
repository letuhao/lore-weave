// Command workload-gen produces seeded foundation event streams (slice S3).
//
//	workload-gen -seed 1 -profile single-reality            # JSONL to stdout (dry-run)
//	workload-gen -seed 1 -profile single-reality -emit -dsn …  # write via the real outbox path
//
// The stream is ALWAYS validated (referential + causal + monotonic) before
// anything is printed or written — a generator bug must never reach a DB.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"

	_ "github.com/lib/pq"

	"github.com/loreweave/foundation/tests/workload-gen/internal/emit"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

func main() {
	seed := flag.Int64("seed", 1, "RNG seed (a given seed+profile is byte-deterministic)")
	profile := flag.String("profile", "single-reality", "micro | single-reality | multi-reality | multi-user-session")
	doEmit := flag.Bool("emit", false, "write the stream via the real outbox path (requires -dsn); default is dry-run JSONL")
	dsn := flag.String("dsn", "", "Postgres DSN for -emit (a per-reality DB with the events + outbox migrations applied)")
	flag.Parse()

	os.Exit(run(os.Stdout, *seed, *profile, *doEmit, *dsn))
}

func run(out io.Writer, seed int64, profileName string, doEmit bool, dsn string) int {
	p, ok := gen.Profiles[profileName]
	if !ok {
		fmt.Fprintf(os.Stderr, "workload-gen: unknown profile %q (have: micro, single-reality, multi-reality, multi-user-session)\n", profileName)
		return 2
	}
	stream := gen.New(seed).Generate(p)

	// Validate before printing OR writing — never let a generator bug reach a DB.
	if err := gen.Validate(stream); err != nil {
		fmt.Fprintf(os.Stderr, "workload-gen: generated stream failed validation: %v\n", err)
		return 1
	}

	if doEmit {
		if dsn == "" {
			fmt.Fprintln(os.Stderr, "workload-gen: -emit requires -dsn")
			return 2
		}
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: open db: %v\n", err)
			return 1
		}
		defer db.Close()
		if err := emit.Stream(context.Background(), db, stream); err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: emit: %v\n", err)
			return 1
		}
		fmt.Fprintf(os.Stderr, "workload-gen: emitted %d events (seed=%d profile=%s)\n", len(stream), seed, profileName)
		return 0
	}

	enc := json.NewEncoder(out)
	for _, e := range stream {
		if err := enc.Encode(e); err != nil {
			fmt.Fprintf(os.Stderr, "workload-gen: encode: %v\n", err)
			return 1
		}
	}
	fmt.Fprintf(os.Stderr, "workload-gen: %d events (seed=%d profile=%s, dry-run)\n", len(stream), seed, profileName)
	return 0
}
