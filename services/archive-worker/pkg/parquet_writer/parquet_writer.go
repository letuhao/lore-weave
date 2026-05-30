// Package parquet_writer encodes a stream of types.EventRow into a binary
// blob: a real Parquet body (ZSTD column compression via parquet-go) wrapped
// in a small LWP1 header/footer envelope so archive_loop's cheap
// verify-after-upload step can confirm the upload without parsing Parquet.
//
// Blob layout (the LWP1 ABI — unchanged across the stub→Parquet swap so
// archive_state rows stay valid):
//
//	[0:4]                 magic = 'LWP1'
//	[4:8]                 schema_version (big-endian uint32) = 2 (Parquet body)
//	[8:N-12]              body = Parquet file (ZSTD-compressed columns)
//	[N-12:N-8]            row_count   = big-endian uint32
//	[N-8:N-4]             body_byte_size = big-endian uint32 (= len of body)
//	[N-4:N]               magic = 'LWP1' (footer marker)
//
// schema_version 1 (the cycle-11 JSONL stub) has no production data; v2 is the
// only format the decoder accepts. An EMPTY partition encodes to a zero-length
// body (no Parquet file) so the minimum blob stays the 20-byte envelope.
package parquet_writer

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/google/uuid"
	"github.com/parquet-go/parquet-go"
	"github.com/parquet-go/parquet-go/compress/zstd"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// errEOF aliases io.EOF — parquet-go's GenericReader.Read returns io.EOF once
// it has read the final batch; that's a clean end, not a failure.
var errEOF = io.EOF

func uuidParse(s string) (uuid.UUID, error) { return uuid.Parse(s) }

func unixNanosUTC(n int64) time.Time { return time.Unix(0, n).UTC() }

// Magic is the 4-byte file marker (header AND footer).
var Magic = [4]byte{'L', 'W', 'P', '1'}

// SchemaVersion is the on-disk schema version. v2 = Parquet+ZSTD body.
const SchemaVersion uint32 = 2

// MinBlobSize is the smallest valid blob (envelope only, zero rows): 20.
const MinBlobSize = 20

// Writer is the producer interface.
type Writer interface {
	Encode(rows []types.EventRow) ([]byte, error)
}

// Reader is the inverse.
type Reader interface {
	Decode(blob []byte) ([]types.EventRow, error)
}

// parquetRow is the Parquet column schema. Tricky source types are flattened
// to primitives (uuid→string, time→unix-nanos int64, []byte JSONB→string,
// nullable→optional pointer) so parquet-go's struct mapping is unambiguous.
type parquetRow struct {
	EventID          string  `parquet:"event_id"`
	RealityID        string  `parquet:"reality_id"`
	AggregateType    string  `parquet:"aggregate_type"`
	AggregateID      string  `parquet:"aggregate_id"`
	AggregateVersion int64   `parquet:"aggregate_version"`
	EventType        string  `parquet:"event_type"`
	EventVersion     int32   `parquet:"event_version"`
	Payload          string  `parquet:"payload"`
	Metadata         *string `parquet:"metadata,optional"`
	OccurredAtNanos  int64   `parquet:"occurred_at_nanos"`
	RecordedAtNanos  int64   `parquet:"recorded_at_nanos"`
	AuditRef         *string `parquet:"audit_ref,optional"`
	RegistryVersion  *int32  `parquet:"registry_version,optional"`
}

func toParquet(r types.EventRow) parquetRow {
	pr := parquetRow{
		EventID:          r.EventID.String(),
		RealityID:        r.RealityID.String(),
		AggregateType:    r.AggregateType,
		AggregateID:      r.AggregateID,
		AggregateVersion: int64(r.AggregateVersion),
		EventType:        r.EventType,
		EventVersion:     int32(r.EventVersion),
		Payload:          string(r.Payload),
		OccurredAtNanos:  r.OccurredAt.UTC().UnixNano(),
		RecordedAtNanos:  r.RecordedAt.UTC().UnixNano(),
	}
	if r.Metadata != nil {
		s := string(r.Metadata)
		pr.Metadata = &s
	}
	if r.AuditRef != nil {
		s := r.AuditRef.String()
		pr.AuditRef = &s
	}
	if r.RegistryVersion != nil {
		v := int32(*r.RegistryVersion)
		pr.RegistryVersion = &v
	}
	return pr
}

func fromParquet(pr parquetRow) (types.EventRow, error) {
	eid, err := uuidParse(pr.EventID)
	if err != nil {
		return types.EventRow{}, fmt.Errorf("event_id: %w", err)
	}
	rid, err := uuidParse(pr.RealityID)
	if err != nil {
		return types.EventRow{}, fmt.Errorf("reality_id: %w", err)
	}
	r := types.EventRow{
		EventID:          eid,
		RealityID:        rid,
		AggregateType:    pr.AggregateType,
		AggregateID:      pr.AggregateID,
		AggregateVersion: uint64(pr.AggregateVersion),
		EventType:        pr.EventType,
		EventVersion:     int(pr.EventVersion),
		Payload:          []byte(pr.Payload),
		OccurredAt:       unixNanosUTC(pr.OccurredAtNanos),
		RecordedAt:       unixNanosUTC(pr.RecordedAtNanos),
	}
	if pr.Metadata != nil {
		r.Metadata = []byte(*pr.Metadata)
	}
	if pr.AuditRef != nil {
		u, perr := uuidParse(*pr.AuditRef)
		if perr != nil {
			return types.EventRow{}, fmt.Errorf("audit_ref: %w", perr)
		}
		r.AuditRef = &u
	}
	if pr.RegistryVersion != nil {
		v := int(*pr.RegistryVersion)
		r.RegistryVersion = &v
	}
	return r, nil
}

// Encoder is the production Parquet+ZSTD encoder.
type Encoder struct{}

// NewEncoder returns the encoder.
func NewEncoder() *Encoder { return &Encoder{} }

// Encode serializes rows into the LWP1-wrapped Parquet blob.
func (Encoder) Encode(rows []types.EventRow) ([]byte, error) {
	if len(rows) > int(^uint32(0)) {
		return nil, fmt.Errorf("parquet_writer: row count %d exceeds uint32 max", len(rows))
	}

	var body []byte
	if len(rows) > 0 {
		buf := &bytes.Buffer{}
		w := parquet.NewGenericWriter[parquetRow](buf, parquet.Compression(&zstd.Codec{}))
		prs := make([]parquetRow, len(rows))
		for i, r := range rows {
			prs[i] = toParquet(r)
		}
		if _, err := w.Write(prs); err != nil {
			return nil, fmt.Errorf("parquet_writer: parquet write: %w", err)
		}
		if err := w.Close(); err != nil {
			return nil, fmt.Errorf("parquet_writer: parquet close: %w", err)
		}
		body = buf.Bytes()
	}

	if len(body) > int(^uint32(0)) {
		return nil, fmt.Errorf("parquet_writer: body size %d exceeds uint32 max", len(body))
	}

	out := make([]byte, 0, MinBlobSize+len(body))
	out = append(out, Magic[:]...)
	out = binary.BigEndian.AppendUint32(out, SchemaVersion)
	out = append(out, body...)
	out = binary.BigEndian.AppendUint32(out, uint32(len(rows)))
	out = binary.BigEndian.AppendUint32(out, uint32(len(body)))
	out = append(out, Magic[:]...)
	return out, nil
}

// Decoder is the inverse.
type Decoder struct{}

// NewDecoder returns the decoder.
func NewDecoder() *Decoder { return &Decoder{} }

// Decode reverses Encode. Returns an error on any marker/size/version mismatch.
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
	if ver := binary.BigEndian.Uint32(blob[4:8]); ver != SchemaVersion {
		return nil, fmt.Errorf("parquet_writer: unknown schema_version %d (want %d)", ver, SchemaVersion)
	}
	rowCount := binary.BigEndian.Uint32(blob[len(blob)-12 : len(blob)-8])
	bodySize := binary.BigEndian.Uint32(blob[len(blob)-8 : len(blob)-4])
	if int(bodySize) != len(blob)-MinBlobSize {
		return nil, fmt.Errorf("parquet_writer: body_size mismatch (footer=%d, computed=%d)",
			bodySize, len(blob)-MinBlobSize)
	}
	if rowCount == 0 {
		return nil, nil
	}
	body := blob[8 : 8+bodySize]

	r := parquet.NewGenericReader[parquetRow](bytes.NewReader(body))
	defer r.Close()
	prs := make([]parquetRow, rowCount)
	n, err := r.Read(prs)
	if err != nil && !errors.Is(err, errEOF) {
		return nil, fmt.Errorf("parquet_writer: parquet read: %w", err)
	}
	if uint32(n) != rowCount {
		return nil, fmt.Errorf("parquet_writer: row count mismatch (footer=%d, decoded=%d)", rowCount, n)
	}
	out := make([]types.EventRow, 0, n)
	for i := 0; i < n; i++ {
		row, cerr := fromParquet(prs[i])
		if cerr != nil {
			return nil, fmt.Errorf("parquet_writer: row %d: %w", i, cerr)
		}
		out = append(out, row)
	}
	return out, nil
}

// VerifyHeader is the cheap integrity check used by archive_loop's
// verify-after-upload step (markers + version + rowcount; no Parquet parse).
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
