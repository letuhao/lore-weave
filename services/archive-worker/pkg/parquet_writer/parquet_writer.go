// Package parquet_writer encodes a stream of types.EventRow into a binary
// blob.
//
// CYCLE-11 V1 SCOPE: ships a SKELETON encoder that produces a deterministic
// binary blob with shape:
//
//	[0:4]                 magic = 'LWP1' (LoreWeave Parquet v1 marker)
//	[4:8]                 schema_version = 1 (big-endian uint32)
//	[8:N-12]              ZSTD-compressed JSONL bytes (one EventRow per line)
//	[N-12:N-8]            row_count = big-endian uint32
//	[N-8:N-4]             body_byte_size = big-endian uint32 (= len of ZSTD bytes)
//	[N-4:N]               magic = 'LWP1' (footer marker for verify-after-upload)
//
// The header+footer pair is enough for pkg/archive_loop's verify step to
// confirm the upload is well-formed without needing a full Parquet parser.
//
// REAL PARQUET-GO BINDING is DEFERRED to cycle 11/L4 alongside the other
// production wirings (see D-ARCHIVE-PARQUET-PROD-WIRING below). Reasons to
// ship a skeleton now:
//   1. Pulls no heavy deps into the cycle-11 commit (parquet-go has a large
//      transitive surface; we want a small commit footprint).
//   2. Establishes the ABI: header+footer markers + row_count let downstream
//      code (cmd/archive-restore, the integrity-checker in L3) treat the
//      blob as an opaque manifest+body unit.
//   3. ZSTD here is a STUB — V1 encodes JSONL bytes verbatim (the "zstd"
//      payload is just the raw bytes). When the parquet-go wiring lands,
//      the compress.Codec interface lets the producer + consumer agree on
//      either raw JSONL (cheap fallback) or true ZSTD-Parquet.
//
// Why this gates correctly in cycle 11:
//   - Round-trip test: encode rows → decode rows → assert equality (drives
//     the contract).
//   - Verify-after-upload test: corrupt a byte in the blob → reader rejects
//     (drives the integrity guard).
//
// DEFERRED FOLLOW-UP (add to docs/deferred/DEFERRED.md as
// D-ARCHIVE-PARQUET-PROD-WIRING): wire parquet-go encoder + klauspost/zstd
// compressor; keep this package's BinaryHeader+Footer ABI so existing
// archive_state rows remain readable.
package parquet_writer

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// Magic is the 4-byte file marker. Same value lives in the header AND the
// footer so verify-after-upload can detect a truncated blob.
var Magic = [4]byte{'L', 'W', 'P', '1'}

// SchemaVersion is the on-disk schema version. Bump if the JSONL layout
// changes incompatibly; the reader rejects unknown versions.
const SchemaVersion uint32 = 1

// MinBlobSize is the smallest valid blob (header + footer, zero rows).
// 4 (magic) + 4 (version) + 4 (rowcount) + 4 (bodysize) + 4 (magic) = 20.
const MinBlobSize = 20

// Writer is the interface a producer satisfies. The real impl below is
// Encoder; tests can substitute a captureWriter to inspect emitted bytes.
type Writer interface {
	Encode(rows []types.EventRow) ([]byte, error)
}

// Reader is the inverse — decode a previously-encoded blob into the row
// list. Used by cmd/archive-restore + the verify-after-upload check.
type Reader interface {
	Decode(blob []byte) ([]types.EventRow, error)
}

// Encoder is the V1 skeleton encoder.
type Encoder struct{}

// NewEncoder returns the V1 encoder. Cycle 11/L4 swaps for a real
// parquet-go-backed impl behind the same Writer interface.
func NewEncoder() *Encoder { return &Encoder{} }

// Encode serializes rows into the binary blob described in the package doc.
func (Encoder) Encode(rows []types.EventRow) ([]byte, error) {
	body := &bytes.Buffer{}
	enc := json.NewEncoder(body)
	for _, r := range rows {
		if err := enc.Encode(r); err != nil {
			return nil, fmt.Errorf("parquet_writer: encode row %s: %w", r.EventID, err)
		}
	}
	bodyBytes := body.Bytes() // V1 STUB: not actually ZSTD-compressed yet.

	if len(rows) > int(^uint32(0)) {
		return nil, fmt.Errorf("parquet_writer: row count %d exceeds uint32 max", len(rows))
	}
	if len(bodyBytes) > int(^uint32(0)) {
		return nil, fmt.Errorf("parquet_writer: body size %d exceeds uint32 max", len(bodyBytes))
	}

	out := make([]byte, 0, 20+len(bodyBytes))
	out = append(out, Magic[:]...)
	out = binary.BigEndian.AppendUint32(out, SchemaVersion)
	out = append(out, bodyBytes...)
	out = binary.BigEndian.AppendUint32(out, uint32(len(rows)))
	out = binary.BigEndian.AppendUint32(out, uint32(len(bodyBytes)))
	out = append(out, Magic[:]...)
	return out, nil
}

// Decoder is the V1 skeleton decoder — inverse of Encoder.
type Decoder struct{}

// NewDecoder returns the V1 decoder.
func NewDecoder() *Decoder { return &Decoder{} }

// Decode reverses Encode. Returns ErrCorrupt if any marker / size mismatches.
func (Decoder) Decode(blob []byte) ([]types.EventRow, error) {
	if len(blob) < MinBlobSize {
		return nil, fmt.Errorf("parquet_writer: blob too small (%d < %d)", len(blob), MinBlobSize)
	}
	if !bytes.Equal(blob[0:4], Magic[:]) {
		return nil, errors.New("parquet_writer: bad header magic")
	}
	if !bytes.Equal(blob[len(blob)-4:], Magic[:]) {
		return nil, errors.New("parquet_writer: bad footer magic")
	}
	ver := binary.BigEndian.Uint32(blob[4:8])
	if ver != SchemaVersion {
		return nil, fmt.Errorf("parquet_writer: unknown schema_version %d (want %d)", ver, SchemaVersion)
	}
	rowCount := binary.BigEndian.Uint32(blob[len(blob)-12 : len(blob)-8])
	bodySize := binary.BigEndian.Uint32(blob[len(blob)-8 : len(blob)-4])
	if int(bodySize) != len(blob)-MinBlobSize {
		return nil, fmt.Errorf("parquet_writer: body_size mismatch (footer=%d, computed=%d)",
			bodySize, len(blob)-MinBlobSize)
	}
	body := blob[8 : 8+bodySize]
	dec := json.NewDecoder(bytes.NewReader(body))
	rows := make([]types.EventRow, 0, rowCount)
	for {
		var r types.EventRow
		if err := dec.Decode(&r); err != nil {
			if errors.Is(err, io.EOF) {
				break
			}
			return nil, fmt.Errorf("parquet_writer: decode row: %w", err)
		}
		rows = append(rows, r)
	}
	if uint32(len(rows)) != rowCount {
		return nil, fmt.Errorf("parquet_writer: row count mismatch (footer=%d, decoded=%d)",
			rowCount, len(rows))
	}
	return rows, nil
}

// VerifyHeader is a cheap integrity check used by pkg/archive_loop's
// verify-after-upload step. It re-reads the (just-uploaded) blob's first
// 8 bytes + last 12 bytes and asserts the markers + rowcount match the
// archive_state row about to be written. Cheaper than a full Decode + safer
// than trusting the upload alone.
func VerifyHeader(blob []byte, expectedRowCount int64) error {
	if len(blob) < MinBlobSize {
		return fmt.Errorf("parquet_writer.VerifyHeader: blob too small")
	}
	if !bytes.Equal(blob[0:4], Magic[:]) {
		return errors.New("parquet_writer.VerifyHeader: bad header magic")
	}
	if !bytes.Equal(blob[len(blob)-4:], Magic[:]) {
		return errors.New("parquet_writer.VerifyHeader: bad footer magic")
	}
	if got := binary.BigEndian.Uint32(blob[4:8]); got != SchemaVersion {
		return fmt.Errorf("parquet_writer.VerifyHeader: schema_version=%d want=%d", got, SchemaVersion)
	}
	rc := int64(binary.BigEndian.Uint32(blob[len(blob)-12 : len(blob)-8]))
	if rc != expectedRowCount {
		return fmt.Errorf("parquet_writer.VerifyHeader: row_count footer=%d expected=%d", rc, expectedRowCount)
	}
	return nil
}
