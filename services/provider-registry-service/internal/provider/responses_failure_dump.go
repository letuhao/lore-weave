package provider

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
)

// dumpMarkerPath — when this file exists, a failed /v1/responses request is written verbatim to
// dumpOutputPath. OFF unless the marker is placed by hand.
//
// A MARKER FILE RATHER THAN AN ENV VAR, for a mundane reason worth writing down: setting an env
// var on a running container requires RECREATING it, and a file can be dropped in with
// `docker cp` on the container that is already reproducing the fault. An investigation tool that
// cannot be switched on without disturbing the thing under investigation is not much of a tool.
const (
	dumpMarkerPath = "/tmp/lw_dump_failed_request"
	dumpOutputPath = "/tmp/lw_failed_request.json"
	// EVERY request while the marker is present, failed or not, one file per call in order.
	// The failing call is the SECOND of a pair and chains on the first, so replaying it alone
	// is not replaying what happened: by the time a replay runs, the provider has long since
	// stored the chain the live call was still asking for. Both halves are needed to reproduce
	// the pair as the platform sent it.
	dumpSeqPathFmt = "/tmp/lw_request_%d.json"
)

var dumpSeq int

// dumpFailedResponsesBody writes the outbound body to a FILE inside the container when the
// marker is present. Never to the log.
//
// 🔴 WHY THIS EXISTS, AND WHY IT IS OFF BY DEFAULT. D-UPSTREAM-ERROR-WITH-NO-MESSAGE has now
// defeated more than twenty hypotheses, and a reconstruction carrying all 65 real tool schemas,
// the real tool_choice, the real prompt, the real tool call and its real result, chained with
// store=true over a reused keep-alive connection, SUCCEEDS where the live request dies. Every
// difference the failure-shape log can describe has been matched. What is left is the body
// itself, and the only way to stop guessing is to replay it exactly.
//
// It is off by default and writes to a file rather than the log because `instructions` is the
// assembled system prompt and can carry the author's own material. A file inside the container
// is the same trust boundary as the database this platform already holds it in; a log line is
// not.
func dumpFailedResponsesBody(body map[string]any) {
	if _, err := os.Stat(dumpMarkerPath); err != nil {
		return
	}
	b, err := json.Marshal(body)
	if err != nil {
		slog.Warn("failed-request dump: could not marshal the body", "err", err)
		return
	}
	if err := os.WriteFile(dumpOutputPath, b, 0o600); err != nil {
		slog.Warn("failed-request dump: could not write", "path", dumpOutputPath, "err", err)
		return
	}
	slog.Warn("failed-request dump written", "path", dumpOutputPath, "bytes", len(b))
}

// dumpEveryResponsesBody writes each outbound body in order while the marker is present, so a
// chained PAIR can be replayed as a pair. Not concurrency-safe by design: it exists for a
// single-scenario investigation at concurrency 1, and a mutex here would imply a durability it
// does not have.
func dumpEveryResponsesBody(body map[string]any) {
	if _, err := os.Stat(dumpMarkerPath); err != nil {
		return
	}
	b, err := json.Marshal(body)
	if err != nil {
		return
	}
	dumpSeq++
	path := fmt.Sprintf(dumpSeqPathFmt, dumpSeq)
	if err := os.WriteFile(path, b, 0o600); err != nil {
		slog.Warn("request dump: could not write", "path", path, "err", err)
		return
	}
	slog.Warn("request dump written", "path", path, "bytes", len(b),
		"chained", body["previous_response_id"] != nil)
}
