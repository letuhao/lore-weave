// Package redisconsume is the go-redis implementation of
// consumer.MessageSource (XREADGROUP + XACK).
//
// The publisher's xreality fanout writes the domain payload as a JSON-encoded
// `payload` field (Redis stream values are scalars). The meta-worker writers
// (canon_writer) read the domain fields at the TOP level, so Read() flattens
// the `payload` + `metadata` JSON back into the message fields — envelope
// fields (event_id, event_type, aggregate_version) win over payload keys.
package redisconsume

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
)

// RedisSource reads xreality messages via a consumer group.
type RedisSource struct {
	rdb      redis.Cmdable
	streams  []string
	group    string
	consumer string
	block    time.Duration
}

// Config is the constructor input.
type Config struct {
	RDB      redis.Cmdable
	Streams  []string // xreality stream names this worker consumes
	Group    string   // consumer group (e.g. "meta-worker")
	Consumer string   // unique consumer id within the group
	// Block is the XREADGROUP block duration (0 = non-blocking poll).
	Block time.Duration
}

// New constructs a RedisSource.
func New(c Config) (*RedisSource, error) {
	if c.RDB == nil {
		return nil, errors.New("redisconsume: nil RDB")
	}
	if len(c.Streams) == 0 {
		return nil, errors.New("redisconsume: no streams")
	}
	if c.Group == "" || c.Consumer == "" {
		return nil, errors.New("redisconsume: group/consumer required")
	}
	return &RedisSource{
		rdb:      c.RDB,
		streams:  c.Streams,
		group:    c.Group,
		consumer: c.Consumer,
		block:    c.Block,
	}, nil
}

// EnsureGroups creates the consumer group on each stream (MKSTREAM), tolerating
// BUSYGROUP (already exists). Call once at startup.
func (s *RedisSource) EnsureGroups(ctx context.Context) error {
	for _, stream := range s.streams {
		// "$" = only new messages from group-create time onward; "0" would
		// replay history. New deployments start fresh.
		if err := s.rdb.XGroupCreateMkStream(ctx, stream, s.group, "$").Err(); err != nil {
			if !isBusyGroup(err) {
				return fmt.Errorf("redisconsume: XGROUP CREATE %s/%s: %w", stream, s.group, err)
			}
		}
	}
	return nil
}

func isBusyGroup(err error) bool {
	return err != nil && (err.Error() == "BUSYGROUP Consumer Group name already exists" ||
		containsBusyGroup(err.Error()))
}

func containsBusyGroup(s string) bool {
	const tag = "BUSYGROUP"
	for i := 0; i+len(tag) <= len(s); i++ {
		if s[i:i+len(tag)] == tag {
			return true
		}
	}
	return false
}

// Read pulls up to batchSize NEW messages (">") across the configured streams.
func (s *RedisSource) Read(ctx context.Context, batchSize int) ([]consumer.Message, error) {
	// XReadGroup wants Streams = [stream1, stream2, …, id1, id2, …].
	args := make([]string, 0, len(s.streams)*2)
	args = append(args, s.streams...)
	for range s.streams {
		args = append(args, ">")
	}
	res, err := s.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group:    s.group,
		Consumer: s.consumer,
		Streams:  args,
		Count:    int64(batchSize),
		Block:    s.block,
	}).Result()
	if errors.Is(err, redis.Nil) {
		return nil, nil // no messages this poll
	}
	if err != nil {
		return nil, fmt.Errorf("redisconsume: XREADGROUP: %w", err)
	}

	var msgs []consumer.Message
	for _, st := range res {
		for _, m := range st.Messages {
			msgs = append(msgs, consumer.Message{
				Stream: st.Stream,
				ID:     m.ID,
				Fields: flatten(m.Values),
			})
		}
	}
	return msgs, nil
}

// Ack XACKs the message on its source stream.
func (s *RedisSource) Ack(ctx context.Context, m consumer.Message) error {
	if err := s.rdb.XAck(ctx, m.Stream, s.group, m.ID).Err(); err != nil {
		return fmt.Errorf("redisconsume: XACK %s/%s: %w", m.Stream, m.ID, err)
	}
	return nil
}

// flatten copies the raw stream fields, then merges the JSON-encoded `payload`
// + `metadata` objects up to the top level so domain fields surface for the
// writers. Envelope fields already present take precedence over payload keys.
func flatten(vals map[string]interface{}) map[string]any {
	out := make(map[string]any, len(vals)+8)
	for k, v := range vals {
		out[k] = v
	}
	for _, nested := range []string{"payload", "metadata"} {
		s, ok := out[nested].(string)
		if !ok || s == "" {
			continue
		}
		var m map[string]any
		if json.Unmarshal([]byte(s), &m) != nil {
			continue
		}
		for k, v := range m {
			if _, exists := out[k]; !exists {
				out[k] = v
			}
		}
	}
	return out
}
