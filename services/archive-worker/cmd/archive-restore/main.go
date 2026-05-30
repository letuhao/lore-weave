// services/archive-worker/cmd/archive-restore — operator CLI for restoring
// archived events back to a queryable form.
//
//	archive-restore list    --reality <uuid>
//	archive-restore restore --reality <uuid> --month YYYY-MM
//
// Connects to the per-reality DB (RESTORE_DB_URL) + MinIO (MINIO_* env).
//   - list:    SELECT from archive_state → print archived partitions.
//   - restore: download the Parquet blob from MinIO, decode it, and re-INSERT
//     the rows into `events_restore_<YYYYMM>` on the per-reality DB.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/archive-worker/pkg/miniostore"
	"github.com/loreweave/foundation/services/archive-worker/pkg/restore"
)

const bucketName = "lw-event-archive"

func usage() {
	fmt.Fprintln(os.Stderr, "Usage:")
	fmt.Fprintln(os.Stderr, "  archive-restore list    --reality <uuid>")
	fmt.Fprintln(os.Stderr, "  archive-restore restore --reality <uuid> --month YYYY-MM")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "Env: RESTORE_DB_URL (per-reality DSN), MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY [, MINIO_USE_SSL]")
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "[archive-restore] error: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}
	cmd, args := os.Args[1], os.Args[2:]
	ctx := context.Background()

	switch cmd {
	case "list":
		fs := flag.NewFlagSet("list", flag.ExitOnError)
		reality := fs.String("reality", "", "reality UUID")
		_ = fs.Parse(args)
		rid, err := requireReality(*reality)
		if err != nil {
			return err
		}
		pool, err := openPool(ctx)
		if err != nil {
			return err
		}
		defer pool.Close()
		objs, err := restore.List(ctx, pool, rid)
		if err != nil {
			return err
		}
		if len(objs) == 0 {
			fmt.Printf("[archive-restore] no archived partitions for reality %s\n", rid)
			return nil
		}
		for _, o := range objs {
			fmt.Println(restore.FormatArchived(o))
		}
		return nil

	case "restore":
		fs := flag.NewFlagSet("restore", flag.ExitOnError)
		reality := fs.String("reality", "", "reality UUID")
		month := fs.String("month", "", "YYYY-MM")
		_ = fs.Parse(args)
		rid, err := requireReality(*reality)
		if err != nil {
			return err
		}
		if *month == "" {
			return fmt.Errorf("restore: --month required")
		}
		pool, err := openPool(ctx)
		if err != nil {
			return err
		}
		defer pool.Close()
		store, err := openMinio(ctx)
		if err != nil {
			return err
		}
		res, err := restore.RestoreMonth(ctx, pool, store, bucketName, rid, *month)
		if err != nil {
			return err
		}
		fmt.Printf("[archive-restore] restored %d rows from %s → table %s\n", res.RowCount, res.ObjectKey, res.Table)
		return nil

	default:
		usage()
		os.Exit(1)
		return nil
	}
}

func requireReality(s string) (uuid.UUID, error) {
	if s == "" {
		return uuid.Nil, fmt.Errorf("--reality required")
	}
	return uuid.Parse(s)
}

func openPool(ctx context.Context) (*pgxpool.Pool, error) {
	dsn := os.Getenv("RESTORE_DB_URL")
	if dsn == "" {
		return nil, fmt.Errorf("RESTORE_DB_URL not set")
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, fmt.Errorf("restore db: %w", err)
	}
	return pool, nil
}

func openMinio(ctx context.Context) (*miniostore.Store, error) {
	ep, ak, sk := os.Getenv("MINIO_ENDPOINT"), os.Getenv("MINIO_ACCESS_KEY"), os.Getenv("MINIO_SECRET_KEY")
	if ep == "" || ak == "" || sk == "" {
		return nil, fmt.Errorf("MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY required")
	}
	return miniostore.New(ctx, miniostore.Config{
		Endpoint: ep, AccessKey: ak, SecretKey: sk, UseSSL: os.Getenv("MINIO_USE_SSL") == "true",
	})
}
