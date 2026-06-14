// Command roleplay-load — S12 (Inc-3) I6 LOAD-SKELETON.
//
// ┌────────────────────────────────────────────────────────────────────────┐
// │ THIS IS NOT services/roleplay-service. The real roleplay-service is      │
// │ `missing` in contracts/language-rule.yaml (ships L4 cycle 17+). This is  │
// │ a Cycle-0 *load skeleton* that stands in for its ONE scaling-relevant    │
// │ behavior — the I6 session command-processor — to validate the I6         │
// │ CONCURRENCY ASSUMPTION, NOT to implement the service. (Creating          │
// │ services/roleplay-service/ now would trip language-rule-lint, which      │
// │ FAILs on a present service mapped `missing`, and would falsely imply the │
// │ service exists — so the skeleton lives here under tests/perf/ instead.)  │
// └────────────────────────────────────────────────────────────────────────┘
//
// I6 (invariants §I6): "One command processor per session. Serial FIFO
// in-session." The router holds a per-session lock so exactly one processor
// appends a session's events — giving a gap-free, monotonic aggregate_version
// sequence. There is NO storage-level uniqueness on (aggregate_id,
// aggregate_version) (the events PK includes recorded_at, a partition-key
// requirement), so the routing serialization is the ONLY thing that keeps a
// session's stream serial. This skeleton:
//
//   - models the I6 router as ONE goroutine per session doing the real
//     read-then-write append (SELECT max(version)+1 → INSERT) at the per-session
//     rate, and asserts every session's stream is contiguous 1..M (serial FIFO);
//   - measures p99 DATA-PLANE ack (the INSERT commit latency, LLM mocked/absent)
//     against the DP-T3 <50ms target — NOT user-perceived latency;
//   - with -bite, gives ONE session TWO uncoordinated processors (a router bug:
//     two processors got the same session) → their non-atomic read-then-write
//     races → the session's version sequence forks (duplicate/lost versions) →
//     the serial-FIFO assertion MUST fail for that session. That proves the I6
//     routing serialization is what holds correctness — it is NOT a re-test of
//     the kernel append CAS (there is no storage uniqueness here to lean on).
package main

import (
	"database/sql"
	"flag"
	"fmt"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/google/uuid"
	_ "github.com/lib/pq"
)

func main() {
	dsn := flag.String("dsn", "", "shard Postgres DSN (events table migrated)")
	sessions := flag.Int("sessions", 50, "concurrent sessions (a hot reality ≈ 50 small sessions on one shard)")
	events := flag.Int("events", 20, "events appended per session")
	rate := flag.Float64("rate", 10, "per-session events/sec (DP per-session ~10 T2/T3/s); 0 = unpaced")
	targetMs := flag.Float64("target-ms", 50, "DP-T3 ack target (p99 reported against it)")
	bite := flag.Bool("bite", false, "give ONE session two uncoordinated processors → I6 violation MUST surface")
	flag.Parse()
	if *dsn == "" {
		die("-dsn required")
	}
	os.Exit(run(*dsn, *sessions, *events, *rate, *targetMs, *bite))
}

func run(dsn string, sessions, events int, rate, targetMs float64, bite bool) int {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		die("open: %v", err)
	}
	defer db.Close()
	db.SetMaxOpenConns(sessions + 8)
	db.SetMaxIdleConns(sessions + 8)
	if err := db.Ping(); err != nil {
		die("ping: %v", err)
	}

	reality := uuid.New().String() // one hot reality holding all the sessions
	sessIDs := make([]string, sessions)
	for i := range sessIDs {
		sessIDs[i] = uuid.New().String()
	}

	var (
		mu   sync.Mutex
		lats []time.Duration
		wg   sync.WaitGroup
	)
	record := func(d time.Duration) { mu.Lock(); lats = append(lats, d); mu.Unlock() }

	var pace time.Duration
	if rate > 0 {
		pace = time.Duration(float64(time.Second) / rate)
	}

	// One goroutine per session = the I6 router guarantee (one processor/session).
	for i, sid := range sessIDs {
		wg.Add(1)
		go func(sid string) {
			defer wg.Done()
			appendSerial(db, reality, sid, events, pace, record)
		}(sid)
		// The bite: the FIRST session gets a SECOND, uncoordinated processor.
		if bite && i == 0 {
			wg.Add(1)
			go func(sid string) {
				defer wg.Done()
				appendSerial(db, reality, sid, events, pace, record)
			}(sid)
		}
	}
	wg.Wait()

	// Verify serial FIFO per session: n == distinct == max == events (contiguous).
	bad := 0
	var biteSessionForked bool
	for i, sid := range sessIDs {
		n, distinct, mx := sessionShape(db, reality, sid)
		serial := n == events && distinct == events && mx == events
		if !serial {
			bad++
			if bite && i == 0 {
				biteSessionForked = true
			}
		}
	}

	p50 := pct(lats, 50)
	p99 := pct(lats, 99)
	fmt.Printf(`{"sessions":%d,"events_per_session":%d,"appends":%d,"bad_sessions":%d,"p50_ms":%.2f,"p99_ms":%.2f,"target_ms":%.1f,"bite":%t}`+"\n",
		sessions, events, len(lats), bad, ms(p50), ms(p99), targetMs, bite)

	if bite {
		if biteSessionForked {
			fmt.Fprintln(os.Stderr, "PASS(bite): the dual-processor session's serial-FIFO sequence FORKED — I6 routing serialization is what holds correctness")
			return 0
		}
		fmt.Fprintln(os.Stderr, "FAIL(bite): the dual-processor session stayed serial — the I6 check is vacuous (no routing sensitivity)")
		return 1
	}
	if bad > 0 {
		fmt.Fprintf(os.Stderr, "FAIL: %d/%d sessions broke serial-FIFO under single-processor routing (I6 violated without a bite!)\n", bad, sessions)
		return 1
	}
	verdict := "p99 within DP-T3 target"
	if ms(p99) > targetMs {
		verdict = fmt.Sprintf("p99 %.2fms EXCEEDS DP-T3 target %.1fms (data-plane ack; report, no pre-baseline hard-fail)", ms(p99), targetMs)
	}
	fmt.Fprintf(os.Stderr, "PASS: all %d sessions serial-FIFO (contiguous 1..%d); %s\n", sessions, events, verdict)
	return 0
}

// appendSerial does the real read-then-write append loop for one processor.
// SELECT max(version)+1 then INSERT are SEPARATE statements (autocommit) — so
// two processors on one session genuinely race (the I6 failure mode), and one
// processor is genuinely serial.
func appendSerial(db *sql.DB, reality, sid string, events int, pace time.Duration, record func(time.Duration)) {
	types := []string{"turn.taken", "npc.acted", "pc.moved"}
	for i := 0; i < events; i++ {
		var next int64
		if err := db.QueryRow(
			`SELECT COALESCE(max(aggregate_version),0)+1 FROM events
			   WHERE reality_id=$1 AND aggregate_type='pc_session' AND aggregate_id=$2`,
			reality, sid).Scan(&next); err != nil {
			continue
		}
		start := time.Now()
		_, err := db.Exec(
			`INSERT INTO events
			   (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
			    event_type, event_version, payload, occurred_at, recorded_at)
			 VALUES ($1,$2,'pc_session',$3,$4,$5,1,'{"t":1}'::jsonb, now(), now())`,
			uuid.New().String(), reality, sid, next, types[i%len(types)])
		if err != nil {
			continue
		}
		record(time.Since(start))
		if pace > 0 {
			time.Sleep(pace)
		}
	}
}

func sessionShape(db *sql.DB, reality, sid string) (n, distinct, mx int) {
	_ = db.QueryRow(
		`SELECT count(*), count(DISTINCT aggregate_version), COALESCE(max(aggregate_version),0)
		   FROM events WHERE reality_id=$1 AND aggregate_type='pc_session' AND aggregate_id=$2`,
		reality, sid).Scan(&n, &distinct, &mx)
	return
}

func pct(ds []time.Duration, p int) time.Duration {
	if len(ds) == 0 {
		return 0
	}
	cp := append([]time.Duration(nil), ds...)
	sort.Slice(cp, func(i, j int) bool { return cp[i] < cp[j] })
	idx := (p * len(cp)) / 100
	if idx >= len(cp) {
		idx = len(cp) - 1
	}
	return cp[idx]
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000.0 }

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "roleplay-load: "+format+"\n", a...)
	os.Exit(2)
}
