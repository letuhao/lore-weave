// services/archive-worker/cmd/archive-restore — operator CLI for restoring
// archived events back to a queryable form.
//
// V1 ships a SKELETON. Two sub-commands:
//   list   — list archived months for a reality (reads archive_state)
//   fetch  — download an archived Parquet blob from MinIO + decode header
//
// Real restore-into-temp-table workflow is DEFERRED — see
// runbooks/archive/restore.md for the manual procedure until the full CLI
// wiring lands alongside D-PUBLISHER-LIVE-WIRING.
//
// The skeleton is enough to:
//   * confirm the binary builds + ships
//   * validate the parquet_writer ABI (magic + schema_version)
//   * print the expected key shape for an operator running mc-cli manually

package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
)

func usage() {
	fmt.Fprintln(os.Stderr, "Usage:")
	fmt.Fprintln(os.Stderr, "  archive-restore list   --reality <uuid>")
	fmt.Fprintln(os.Stderr, "  archive-restore fetch  --reality <uuid> --month YYYY-MM [--out FILE]")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "Both commands V1 SKELETON — print expected key shape.")
	fmt.Fprintln(os.Stderr, "Production wiring deferred (runbooks/archive/restore.md).")
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}
	cmd := os.Args[1]
	args := os.Args[2:]

	switch cmd {
	case "list":
		fs := flag.NewFlagSet("list", flag.ExitOnError)
		reality := fs.String("reality", "", "reality UUID")
		_ = fs.Parse(args)
		if *reality == "" {
			fmt.Fprintln(os.Stderr, "list: --reality required")
			os.Exit(1)
		}
		fmt.Printf("[archive-restore] SKELETON — would SELECT * FROM archive_state WHERE reality_id = %q\n", *reality)
		fmt.Printf("[archive-restore] expected key prefix: events/%s/\n", *reality)
		fmt.Printf("[archive-restore] manual: mc ls lw-platform/lw-event-archive/events/%s/\n", *reality)
	case "fetch":
		fs := flag.NewFlagSet("fetch", flag.ExitOnError)
		reality := fs.String("reality", "", "reality UUID")
		month := fs.String("month", "", "YYYY-MM")
		out := fs.String("out", "", "local output path (default stdout)")
		_ = fs.Parse(args)
		if *reality == "" || *month == "" {
			fmt.Fprintln(os.Stderr, "fetch: --reality and --month required")
			os.Exit(1)
		}
		key := object_store.ObjectKey(*reality, *month)
		fmt.Printf("[archive-restore] SKELETON — would download bucket=lw-event-archive key=%s\n", key)
		if *out != "" {
			fmt.Printf("[archive-restore] would write decoded rows to %s\n", *out)
		}
		fmt.Printf("[archive-restore] expected blob ABI: magic=%q schema_version=%d\n",
			parquet_writer.Magic[:], parquet_writer.SchemaVersion)
		fmt.Printf("[archive-restore] manual: mc cp lw-platform/lw-event-archive/%s ./%s.parquet\n", key, *month)
	default:
		usage()
		os.Exit(1)
	}
}
