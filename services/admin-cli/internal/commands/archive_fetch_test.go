package commands

import (
	"context"
	"encoding/binary"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeArchiveMeta struct {
	obj   ArchiveObject
	found bool
	err   error
}

func (f fakeArchiveMeta) LookupArchive(_ context.Context, _ uuid.UUID, _ string) (ArchiveObject, bool, error) {
	return f.obj, f.found, f.err
}

type fakeFetcher struct {
	blob []byte
	err  error
}

func (f fakeFetcher) Fetch(_ context.Context, _, _ string) ([]byte, error) {
	return f.blob, f.err
}

// spyFetcher captures the (bucket, key) it was asked for, to assert the wiring.
type spyFetcher struct {
	bucket, key string
	blob        []byte
}

func (s *spyFetcher) Fetch(_ context.Context, bucket, key string) ([]byte, error) {
	s.bucket, s.key = bucket, key
	return s.blob, nil
}

// lwp1Blob builds a well-formed LWP1 envelope with the given row_count + body size.
func lwp1Blob(rowCount uint32, bodySize int) []byte {
	out := []byte{'L', 'W', 'P', '1'}
	out = binary.BigEndian.AppendUint32(out, lwp1SchemaVersion)
	out = append(out, make([]byte, bodySize)...)
	out = binary.BigEndian.AppendUint32(out, rowCount)
	out = binary.BigEndian.AppendUint32(out, uint32(bodySize))
	out = append(out, 'L', 'W', 'P', '1')
	return out
}

func okMeta(rowCount int64) fakeArchiveMeta {
	return fakeArchiveMeta{found: true, obj: ArchiveObject{
		ObjectKey: "events/r/2025-11.parquet", ByteSize: 1024, RowCount: rowCount,
		ArchivedAt: time.Unix(0, 0).UTC(),
	}}
}

func TestRunArchiveFetch_HappyPath_MetadataOnly(t *testing.T) {
	out, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false,
		okMeta(3), fakeFetcher{blob: lwp1Blob(3, 10)})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{"header_valid: yes", "row_count:    3 (manifest)", "not written"} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q\n%s", want, out)
		}
	}
}

func TestRunArchiveFetch_WritesBlobToOutPath(t *testing.T) {
	blob := lwp1Blob(2, 8)
	dst := filepath.Join(t.TempDir(), "out.parquet")
	out, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", dst, false,
		okMeta(2), fakeFetcher{blob: blob})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "wrote") {
		t.Errorf("output should report the write: %s", out)
	}
	got, rerr := os.ReadFile(dst)
	if rerr != nil {
		t.Fatalf("read written blob: %v", rerr)
	}
	if len(got) != len(blob) {
		t.Errorf("written blob size: want %d, got %d", len(blob), len(got))
	}
}

// TestRunArchiveFetch_DryRunSkipsWrite proves --dry-run performs the fetch+header
// preview but does NOT write the file — so a dry-run-labelled audit row is truthful.
func TestRunArchiveFetch_DryRunSkipsWrite(t *testing.T) {
	dst := filepath.Join(t.TempDir(), "out.parquet")
	out, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", dst, true,
		okMeta(2), fakeFetcher{blob: lwp1Blob(2, 8)})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "dry-run") || !strings.Contains(out, "not written") {
		t.Errorf("dry-run output should say it would write but did not:\n%s", out)
	}
	if _, statErr := os.Stat(dst); !os.IsNotExist(statErr) {
		t.Errorf("dry-run must NOT create the file %s (stat err: %v)", dst, statErr)
	}
}

func TestRunArchiveFetch_BadMonth(t *testing.T) {
	_, err := RunArchiveFetch(context.Background(), uuid.New(), "2025/11", "", false,
		okMeta(1), fakeFetcher{blob: lwp1Blob(1, 4)})
	if err == nil || !strings.Contains(err.Error(), "bad month") {
		t.Fatalf("want bad-month error, got %v", err)
	}
}

func TestRunArchiveFetch_NotArchived(t *testing.T) {
	_, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false,
		fakeArchiveMeta{found: false}, fakeFetcher{blob: lwp1Blob(1, 4)})
	if err == nil || !strings.Contains(err.Error(), "nothing archived") {
		t.Fatalf("want nothing-archived error, got %v", err)
	}
}

func TestRunArchiveFetch_BadHeaderMagic(t *testing.T) {
	bad := lwp1Blob(1, 4)
	bad[0] = 'X' // corrupt header magic
	out, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false,
		okMeta(1), fakeFetcher{blob: bad})
	if err != nil {
		t.Fatalf("header mismatch must be reported, not error: %v", err)
	}
	if !strings.Contains(out, "header_valid: NO") || !strings.Contains(out, "bad header magic") {
		t.Errorf("output should flag bad header:\n%s", out)
	}
}

func TestRunArchiveFetch_RowCountMismatch(t *testing.T) {
	// manifest says 5 rows, blob footer says 3 → header invalid (integrity catch).
	out, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false,
		okMeta(5), fakeFetcher{blob: lwp1Blob(3, 6)})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "header_valid: NO") || !strings.Contains(out, "footer=3 expected=5") {
		t.Errorf("output should flag row_count mismatch:\n%s", out)
	}
}

func TestRunArchiveFetch_NilDeps(t *testing.T) {
	_, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false, nil, nil)
	if err == nil || !strings.Contains(err.Error(), "not wired") {
		t.Fatalf("want not-wired error, got %v", err)
	}
}

func TestRunArchiveFetch_FetchError(t *testing.T) {
	_, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-11", "", false,
		okMeta(1), fakeFetcher{err: context.DeadlineExceeded})
	if err == nil || !strings.Contains(err.Error(), "fetch") {
		t.Fatalf("want fetch error, got %v", err)
	}
}

func TestRunArchiveFetch_UsesCanonicalBucketAndKey(t *testing.T) {
	rid := uuid.New()
	spy := &spyFetcher{blob: lwp1Blob(1, 4)}
	if _, err := RunArchiveFetch(context.Background(), rid, "2025-11", "", false, okMeta(1), spy); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if spy.bucket != "lw-event-archive" {
		t.Errorf("bucket: want lw-event-archive, got %q", spy.bucket)
	}
	wantKey := "events/" + rid.String() + "/2025-11.parquet"
	if spy.key != wantKey {
		t.Errorf("object key: want %q, got %q", wantKey, spy.key)
	}
}

func TestRunArchiveFetch_RejectsImpossibleMonth(t *testing.T) {
	// shape-valid but impossible (month 13) → rejected by the tightened regex before
	// any lookup, so it never builds a bogus key.
	_, err := RunArchiveFetch(context.Background(), uuid.New(), "2025-13", "", false,
		okMeta(1), fakeFetcher{blob: lwp1Blob(1, 4)})
	if err == nil || !strings.Contains(err.Error(), "bad month") {
		t.Fatalf("want bad-month error for 2025-13, got %v", err)
	}
}
