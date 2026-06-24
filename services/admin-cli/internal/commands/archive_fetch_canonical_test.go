package commands

// Drift tripwire for the LWP1 envelope ABI that archive_fetch.go DUPLICATES from the
// canonical services/archive-worker/pkg/parquet_writer (D4/D5: admin-cli must not take
// a runtime/module dependency on another service, so the constants are copied). This
// test reads the canonical source FILE (no module import — boundary-clean) and asserts
// our copied constants still match, so a future SchemaVersion/Magic/MinBlobSize bump in
// the writer fails here and forces the admin-cli copy to be updated in lockstep.
//
// The byte-layout offsets in verifyLWP1Header were confirmed byte-identical to
// parquet_writer.VerifyHeader by inspection; the constants below are the realistic
// drift surface (esp. a schema_version bump), which this guards.

import (
	"os"
	"regexp"
	"strconv"
	"testing"
)

const canonicalParquetWriter = "../../../../services/archive-worker/pkg/parquet_writer/parquet_writer.go"

func TestLWP1Constants_MatchCanonical(t *testing.T) {
	src, err := os.ReadFile(canonicalParquetWriter)
	if err != nil {
		t.Fatalf("read canonical parquet_writer (%s): %v", canonicalParquetWriter, err)
	}
	s := string(src)

	// Magic = [4]byte{'L', 'W', 'P', '1'}
	magicRe := regexp.MustCompile(`Magic\s*=\s*\[4\]byte\{'L',\s*'W',\s*'P',\s*'1'\}`)
	if !magicRe.MatchString(s) {
		t.Errorf("canonical Magic literal not found / changed shape; our lwp1Magic=%v may have drifted", lwp1Magic)
	}
	// Symmetric guard: also catch an admin-cli-side edit of lwp1Magic (the canonical
	// regex above only catches a canonical-side reshape).
	if lwp1Magic != [4]byte{'L', 'W', 'P', '1'} {
		t.Errorf("admin-cli lwp1Magic drifted from the canonical LWP1 magic: got %v", lwp1Magic)
	}

	schemaRe := regexp.MustCompile(`SchemaVersion\s+uint32\s*=\s*(\d+)`)
	m := schemaRe.FindStringSubmatch(s)
	if m == nil {
		t.Fatalf("canonical SchemaVersion const not found (shape changed)")
	}
	if got, _ := strconv.Atoi(m[1]); uint32(got) != lwp1SchemaVersion {
		t.Errorf("schema_version drift: canonical=%d, admin-cli lwp1SchemaVersion=%d — update archive_fetch.go", got, lwp1SchemaVersion)
	}

	minRe := regexp.MustCompile(`MinBlobSize\s*=\s*(\d+)`)
	m = minRe.FindStringSubmatch(s)
	if m == nil {
		t.Fatalf("canonical MinBlobSize const not found (shape changed)")
	}
	if got, _ := strconv.Atoi(m[1]); got != lwp1MinBlobSize {
		t.Errorf("min_blob_size drift: canonical=%d, admin-cli lwp1MinBlobSize=%d — update archive_fetch.go", got, lwp1MinBlobSize)
	}
}
