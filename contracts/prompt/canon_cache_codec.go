package prompt

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// canonCacheWire is the serializable wire shape for a CacheEntry. We
// avoid encoding the CacheEntry struct directly so the wire format
// stays decoupled from in-process struct evolution.
type canonCacheWire struct {
	RealityID     uuid.UUID `json:"reality_id"`
	CanonEntryID  uuid.UUID `json:"canon_entry_id"`
	BookID        uuid.UUID `json:"book_id"`
	AttributePath string    `json:"attribute_path"`
	Value         []byte    `json:"value"`
	CanonLayer    string    `json:"canon_layer"`
	LastSyncedAt  time.Time `json:"last_synced_at"`
	ExpiresAt     time.Time `json:"expires_at"`
}

func jsonMarshalEntry(e CacheEntry) ([]byte, error) {
	w := canonCacheWire{
		RealityID:     e.RealityID,
		CanonEntryID:  e.CanonEntryID,
		BookID:        e.BookID,
		AttributePath: e.AttributePath,
		Value:         e.Value,
		CanonLayer:    e.CanonLayer,
		LastSyncedAt:  e.LastSyncedAt,
		ExpiresAt:     e.ExpiresAt,
	}
	return json.Marshal(w)
}

func jsonUnmarshalEntry(raw []byte) (CacheEntry, error) {
	var w canonCacheWire
	if err := json.Unmarshal(raw, &w); err != nil {
		return CacheEntry{}, fmt.Errorf("canon_cache_codec: %w", err)
	}
	return CacheEntry{
		RealityID:     w.RealityID,
		CanonEntryID:  w.CanonEntryID,
		BookID:        w.BookID,
		AttributePath: w.AttributePath,
		Value:         w.Value,
		CanonLayer:    w.CanonLayer,
		LastSyncedAt:  w.LastSyncedAt,
		ExpiresAt:     w.ExpiresAt,
	}, nil
}
