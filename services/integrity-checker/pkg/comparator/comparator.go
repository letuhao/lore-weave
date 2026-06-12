// Package comparator canonicalizes JSON so two semantically-equal documents
// compare byte-equal, which is how the L3.E/F integrity checker decides drift.
//
// CRITICAL: drift detection is BYTE-EQUAL (after canonical JSON normalization) —
// NOT approximate / NOT semantic. The whole point of the integrity checker is to
// catch the cases where the projection runner produced different output than the
// replay would; approximate matching would mask real bugs.
//
// Both sides of the comparison are produced by Postgres `to_jsonb(t) - meta`
// (the live row in pgsource, the replayed row in the replay-aggregate bin), so
// this only needs to reconcile object key ordering (and recurse through arrays).
// [pkg/live.CheckRow] (daily + monthly) calls [Canonicalize] on each side and
// compares the bytes.
//
// (Pre-row-centric this package also hosted the (aggregate_id, version)
// CompareOne/AggregateLoader model shared with the deleted daily_loop/sampler;
// that is gone — the row-centric model re-derives via the replay-aggregate bin.)
package comparator

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
)

// Canonicalize re-serializes a JSON value with sorted keys + stripped whitespace,
// so two semantically-equal JSON documents compare byte-equal.
func Canonicalize(in []byte) ([]byte, error) { return canonicalize(in) }

// canonicalize re-serializes a JSON value with sorted keys + stripped whitespace.
// Empty input canonicalizes to `null`. Arrays are walked recursively so nested
// objects within arrays are canonicalized too. `json.Number` is used so int vs
// float is preserved (1 and 1.0 must NOT compare equal — losing the integer type
// is itself projection drift).
func canonicalize(in []byte) ([]byte, error) {
	if len(in) == 0 {
		return []byte("null"), nil
	}
	var raw interface{}
	dec := json.NewDecoder(bytes.NewReader(in))
	dec.UseNumber() // preserve int vs float distinction
	if err := dec.Decode(&raw); err != nil {
		return nil, fmt.Errorf("canonicalize: decode: %w", err)
	}
	return marshalCanonical(raw)
}

func marshalCanonical(v interface{}) ([]byte, error) {
	switch x := v.(type) {
	case map[string]interface{}:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var buf bytes.Buffer
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			kb, err := json.Marshal(k)
			if err != nil {
				return nil, err
			}
			buf.Write(kb)
			buf.WriteByte(':')
			vb, err := marshalCanonical(x[k])
			if err != nil {
				return nil, err
			}
			buf.Write(vb)
		}
		buf.WriteByte('}')
		return buf.Bytes(), nil
	case []interface{}:
		var buf bytes.Buffer
		buf.WriteByte('[')
		for i, item := range x {
			if i > 0 {
				buf.WriteByte(',')
			}
			ib, err := marshalCanonical(item)
			if err != nil {
				return nil, err
			}
			buf.Write(ib)
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	default:
		return json.Marshal(v)
	}
}
