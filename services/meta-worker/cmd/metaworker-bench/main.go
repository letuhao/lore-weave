// services/meta-worker/cmd/metaworker-bench — S12 (Inc-2) I7 consume-ceiling probe.
//
// The meta-worker is the SOLE consumer of the xreality.* streams (I7): every
// cross-reality event from EVERY shard funnels into this one consumer. So the
// scale question for the I7 path is "how many xreality msgs/s can ONE consumer
// drain" vs the aggregate DP-S5 T3 target (<=50k/s).
//
// This bench reuses the EXACT production consume machinery — redisconsume
// (XREADGROUP + flatten + XACK) + consumer.ProcessOne + dispatch — with a NO-OP
// handler. That deliberately isolates the I7 CONSUME-LOOP ceiling from the canon
// projection PG write the real handler does: the handler write is a per-reality
// canon_projection upsert, whose ceiling is the SAME shard write path Inc-1
// already measured. The meta-worker's real ceiling is min(this consume ceiling,
// the canon PG-write ceiling); this binary supplies the consume half, which is
// the NEW information and the actual I7 architectural limit.
//
// Modes:
//   -mode both  -n N   create group, XADD N synthetic xreality events (untimed),
//                      then TIME the drain loop -> {n, secs, throughput}
//   -mode preload -n N just XADD N events
//   -mode drain   -n N just drain N (group must exist + be behind)
//
// Run with GOMAXPROCS=1 to measure the single-core serial ceiling (the I7
// consumer is one ProcessOne loop -> intrinsically serial; more cores do not
// help a single consumer, a FASTER core does). Sweep -batch to tell a CPU-bound
// ceiling (flat across batch) from a Redis-RTT-bound one (rises with batch).
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
	"github.com/loreweave/foundation/services/meta-worker/pkg/redisconsume"
)

// benchEventType is an allowlisted (xreality.* prefix) synthetic type so the
// real ValidateAllowlist passes and dispatch routes to our no-op.
const benchEventType = "xreality.bench.tick"

func main() {
	redisURL := flag.String("redis", "redis://127.0.0.1:56510/0", "Redis URL")
	stream := flag.String("stream", "xreality.bench.tick", "stream to preload/drain")
	group := flag.String("group", "meta-worker-bench", "consumer group")
	mode := flag.String("mode", "both", "both | preload | drain")
	n := flag.Int("n", 50000, "number of events")
	batch := flag.Int("batch", 200, "XREADGROUP batch size")
	flag.Parse()

	opts, err := redis.ParseURL(*redisURL)
	if err != nil {
		die("redis url: %v", err)
	}
	rdb := redis.NewClient(opts)
	defer rdb.Close()
	ctx := context.Background()
	if err := rdb.Ping(ctx).Err(); err != nil {
		die("redis ping: %v", err)
	}

	src, err := redisconsume.New(redisconsume.Config{
		RDB: rdb, Streams: []string{*stream}, Group: *group, Consumer: "bench-1", Block: 500 * time.Millisecond,
	})
	if err != nil {
		die("redisconsume: %v", err)
	}
	// Group MUST exist before preload so XADDs land after the "$" group head and
	// are delivered to ">".
	if err := src.EnsureGroups(ctx); err != nil {
		die("ensure groups: %v", err)
	}

	if *mode == "preload" || *mode == "both" {
		preload(ctx, rdb, *stream, *n)
	}
	if *mode == "preload" {
		fmt.Printf(`{"mode":"preload","n":%d}`+"\n", *n)
		return
	}

	// Real dispatch + no-op handler (isolates the consume loop).
	d := dispatch.New().Register(benchEventType, func(context.Context, map[string]any) error { return nil })
	if err := d.ValidateAllowlist(); err != nil {
		die("allowlist: %v", err) // proves the synthetic type is I7-legal
	}
	cons, err := consumer.New(src, d)
	if err != nil {
		die("consumer: %v", err)
	}

	// Drain: loop ProcessOne until N acked or a quiet timeout.
	acked := 0
	start := time.Now()
	idle := 0
	for acked < *n {
		stats, perr := cons.ProcessOne(ctx, *batch)
		if perr != nil {
			die("process: %v", perr)
		}
		acked += stats.Acked
		if stats.Read == 0 {
			idle++
			if idle > 6 { // ~3s of empty blocking polls -> backlog drained/short
				break
			}
			continue
		}
		idle = 0
	}
	secs := time.Since(start).Seconds()
	tput := 0.0
	if secs > 0 {
		tput = float64(acked) / secs
	}
	fmt.Printf(`{"mode":"drain","n":%d,"acked":%d,"secs":%.3f,"batch":%d,"gomaxprocs":%d,"throughput":%.1f}`+"\n",
		*n, acked, secs, *batch, gomaxprocs(), tput)
}

// preload XADDs n synthetic xreality envelopes with a JSON payload (so the
// consume path pays the same flatten/json-decode cost as production).
func preload(ctx context.Context, rdb *redis.Client, stream string, n int) {
	payload, _ := json.Marshal(map[string]any{"canon_id": "bench", "title": "t", "body": "lorem ipsum dolor"})
	pipe := rdb.Pipeline()
	for i := range n {
		pipe.XAdd(ctx, &redis.XAddArgs{Stream: stream, Values: map[string]any{
			"event_id":      fmt.Sprintf("bench-%d", i),
			"event_type":    benchEventType,
			"event_version": 1,
			"payload":       string(payload),
		}})
		if i%1000 == 999 {
			if _, err := pipe.Exec(ctx); err != nil {
				die("preload xadd: %v", err)
			}
			pipe = rdb.Pipeline()
		}
	}
	if _, err := pipe.Exec(ctx); err != nil {
		die("preload xadd (tail): %v", err)
	}
}

func gomaxprocs() int {
	if v := os.Getenv("GOMAXPROCS"); v != "" {
		var p int
		_, _ = fmt.Sscanf(v, "%d", &p)
		if p > 0 {
			return p
		}
	}
	return 0 // runtime default
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "metaworker-bench: "+format+"\n", a...)
	os.Exit(1)
}
