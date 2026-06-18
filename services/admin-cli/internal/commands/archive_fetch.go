package commands

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

// archiveBucket is the cold-storage bucket the archive-worker writes archived
// Parquet blobs to (object_store key shape events/<reality_id>/<YYYY>-<MM>.parquet).
const archiveBucket = "lw-event-archive"

// archiveMonthRe validates the YYYY-MM operator input (month 01-12) before it is used
// to build an object key — the archive-worker only ever emits months via
// time.Format("2006-01"), so an impossible month (00, 13+) can never match a real key.
var archiveMonthRe = regexp.MustCompile(`^[0-9]{4}-(0[1-9]|1[0-2])$`)

// LWP1 envelope ABI (frozen) — DUPLICATED from the canonical definition in
// services/archive-worker/pkg/parquet_writer (Magic / SchemaVersion / MinBlobSize) to
// avoid a service→service code dependency: the repo pattern is that each service owns
// its object-store access (D4/D5 in docs/plans/2026-06-01-admin-readcmd-batch.md). The
// ABI is documented as "unchanged across the stub→Parquet swap so archive_state rows
// stay valid", so this duplication is low-drift. Full Parquet row-decode is deferred
// (D-ARCHIVE-FETCH-DECODE) — this command's job is fetch + header-integrity + persist.
var lwp1Magic = [4]byte{'L', 'W', 'P', '1'}

const lwp1SchemaVersion uint32 = 2

// lwp1MinBlobSize is the smallest valid blob (envelope only, zero rows).
const lwp1MinBlobSize = 20

// ArchiveObject is the archive_state manifest row for one (reality, month) partition.
type ArchiveObject struct {
	ObjectKey    string
	ByteSize     int64
	RowCount     int64
	FormatHeader []byte
	ArchivedAt   time.Time
}

// ArchiveMetaReader resolves the archive_state manifest row for (reality, object key).
// Prod: PgArchiveMetaReader (per-reality DB); tests use a fake. The bool is false when
// nothing is archived for that key (not an error).
type ArchiveMetaReader interface {
	LookupArchive(ctx context.Context, realityID uuid.UUID, objectKey string) (ArchiveObject, bool, error)
}

// ArchiveBlobFetcher fetches a stored blob by (bucket, key). Prod: miniofetch.Store;
// tests use a fake.
type ArchiveBlobFetcher interface {
	Fetch(ctx context.Context, bucket, key string) ([]byte, error)
}

// archiveObjectKey builds the canonical archive key shape (frozen):
// events/<reality_id>/<YYYY>-<MM>.parquet.
func archiveObjectKey(realityID uuid.UUID, month string) string {
	return fmt.Sprintf("events/%s/%s.parquet", realityID, month)
}

// RunArchiveFetch resolves the object key for (reality, month), confirms it is in the
// archive_state manifest, fetches the blob, validates the LWP1 header against the
// manifest's recorded row_count, and (with outPath) writes the raw blob. Without
// outPath it reports metadata only — framework output is text, unfit for binary on
// stdout (D6; D-ARCHIVE-FETCH-STDOUT-STREAM). The only side effect is a local file
// write when outPath is set; nothing in the system is mutated. Under dryRun the file
// write is suppressed (the fetch+header preview still runs) so a --dry-run-labelled
// audit row stays truthful — i.e. the command performed NO side effect.
func RunArchiveFetch(ctx context.Context, realityID uuid.UUID, month, outPath string, dryRun bool, meta ArchiveMetaReader, fetcher ArchiveBlobFetcher) (string, error) {
	if meta == nil || fetcher == nil {
		return "", fmt.Errorf("archive fetch: not wired (meta/fetcher)")
	}
	if !archiveMonthRe.MatchString(month) {
		return "", fmt.Errorf("archive fetch: bad month %q (want YYYY-MM)", month)
	}
	key := archiveObjectKey(realityID, month)
	obj, found, err := meta.LookupArchive(ctx, realityID, key)
	if err != nil {
		return "", err
	}
	if !found {
		return "", fmt.Errorf("archive fetch: nothing archived for reality %s month %s (key %s)", realityID, month, key)
	}
	blob, err := fetcher.Fetch(ctx, archiveBucket, key)
	if err != nil {
		return "", fmt.Errorf("archive fetch: fetch %s/%s: %w", archiveBucket, key, err)
	}
	hdrErr := verifyLWP1Header(blob, obj.RowCount)

	var b strings.Builder
	fmt.Fprintf(&b, "archive fetch — reality %s month %s\n", realityID, month)
	fmt.Fprintf(&b, "  object_key:   %s\n", obj.ObjectKey)
	fmt.Fprintf(&b, "  byte_size:    %d (manifest) / %d (fetched)\n", obj.ByteSize, len(blob))
	fmt.Fprintf(&b, "  row_count:    %d (manifest)\n", obj.RowCount)
	fmt.Fprintf(&b, "  archived_at:  %s\n", obj.ArchivedAt.UTC().Format(time.RFC3339))
	if hdrErr != nil {
		fmt.Fprintf(&b, "  header_valid: NO — %s\n", hdrErr)
	} else {
		fmt.Fprintf(&b, "  header_valid: yes (LWP1 v%d, row_count matches manifest)\n", lwp1SchemaVersion)
	}
	if outPath == "" {
		fmt.Fprintf(&b, "  blob:         not written (pass --out_path to save the .parquet blob; binary is not streamed to stdout)\n")
		return b.String(), nil
	}
	if dryRun {
		fmt.Fprintf(&b, "  blob:         dry-run — would write %d bytes -> %s (not written)\n", len(blob), outPath)
		return b.String(), nil
	}
	if err := os.WriteFile(outPath, blob, 0o600); err != nil {
		return "", fmt.Errorf("archive fetch: write %s: %w", outPath, err)
	}
	fmt.Fprintf(&b, "  blob:         wrote %d bytes -> %s\n", len(blob), outPath)
	return b.String(), nil
}

// verifyLWP1Header checks the frozen LWP1 envelope (magic header+footer, schema
// version, and footer row_count vs the manifest's recorded row_count). Mirrors
// parquet_writer.VerifyHeader — intentionally a HEADER-integrity check only: it does
// NOT compare len(blob) to the manifest byte_size, nor the footer body_byte_size
// field (canonical VerifyHeader skips it too; only Decode() enforces it). Full body
// validation is deferred (D-ARCHIVE-FETCH-DECODE).
func verifyLWP1Header(blob []byte, expectedRowCount int64) error {
	if len(blob) < lwp1MinBlobSize {
		return fmt.Errorf("blob too small (%d < %d)", len(blob), lwp1MinBlobSize)
	}
	if !bytes.Equal(blob[0:4], lwp1Magic[:]) {
		return fmt.Errorf("bad header magic")
	}
	if !bytes.Equal(blob[len(blob)-4:], lwp1Magic[:]) {
		return fmt.Errorf("bad footer magic")
	}
	if got := binary.BigEndian.Uint32(blob[4:8]); got != lwp1SchemaVersion {
		return fmt.Errorf("schema_version=%d want=%d", got, lwp1SchemaVersion)
	}
	rc := int64(binary.BigEndian.Uint32(blob[len(blob)-12 : len(blob)-8]))
	if rc != expectedRowCount {
		return fmt.Errorf("row_count footer=%d expected=%d", rc, expectedRowCount)
	}
	return nil
}
