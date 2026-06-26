package loreweave_llm

import (
	"bufio"
	"io"
	"strings"
)

// sseEvent is one decoded server-sent event: its `event:` type and raw `data:` JSON.
type sseEvent struct {
	Type string
	Data []byte
}

// scanSSE reads SSE frames from r and calls onEvent for each complete event (one
// terminated by a blank line). Multiple `data:` lines are joined with "\n" per the
// SSE spec. Returns onEvent's first error, or a read error; nil at clean EOF.
func scanSSE(r io.Reader, onEvent func(sseEvent) error) error {
	sc := bufio.NewScanner(r)
	// Allow large data lines — a full plan JSON can exceed the 64KB default.
	sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)

	var evType string
	var data []string
	flush := func() error {
		if evType == "" && len(data) == 0 {
			return nil
		}
		ev := sseEvent{Type: evType, Data: []byte(strings.Join(data, "\n"))}
		evType, data = "", nil
		return onEvent(ev)
	}

	for sc.Scan() {
		line := sc.Text()
		if line == "" { // blank line terminates the current event
			if err := flush(); err != nil {
				return err
			}
			continue
		}
		if strings.HasPrefix(line, ":") { // SSE comment / heartbeat
			continue
		}
		field, value, _ := strings.Cut(line, ":")
		value = strings.TrimPrefix(value, " ")
		switch field {
		case "event":
			evType = value
		case "data":
			data = append(data, value)
		}
		// `id` / `retry` fields are not used by the gateway protocol.
	}
	if err := sc.Err(); err != nil {
		return err
	}
	return flush() // flush a trailing event with no terminating blank line
}
