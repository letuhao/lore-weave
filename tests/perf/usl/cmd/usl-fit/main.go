// Command usl-fit reads a (N,throughput) concurrency series and prints the
// fitted USL coefficients + saturation point as JSON.
//
// S7 deliverable F1 — the CLI the hyperfine harness (F3) pipes its measured
// throughput-at-concurrency series into. N is CONCURRENCY (parallel workers),
// not load size.
//
// Input (stdin or -in <file>), auto-detected:
//   - CSV  : lines "N,throughput" (a leading "n,throughput"/"#" header is skipped)
//   - JSON : array of {"n":N,"throughput":X}
//
// Output (stdout): the usl.Fit as indented JSON. Exit 1 on a fit/parse error.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/loreweave/foundation/tests/perf/usl"
)

func main() {
	inPath := flag.String("in", "", "input file (default stdin)")
	flag.Parse()

	var r io.Reader = os.Stdin
	if *inPath != "" {
		f, err := os.Open(*inPath)
		if err != nil {
			fatal("open %s: %v", *inPath, err)
		}
		defer f.Close()
		r = f
	}

	raw, err := io.ReadAll(r)
	if err != nil {
		fatal("read input: %v", err)
	}
	samples, err := parse(raw)
	if err != nil {
		fatal("parse: %v", err)
	}

	fit, err := usl.FitUSL(samples)
	if err != nil {
		fatal("fit: %v", err)
	}

	out, err := json.MarshalIndent(fit, "", "  ")
	if err != nil {
		fatal("marshal: %v", err)
	}
	fmt.Println(string(out))
}

// parse auto-detects JSON (input starts with '[') vs CSV.
func parse(raw []byte) ([]usl.Sample, error) {
	trimmed := strings.TrimSpace(string(raw))
	if strings.HasPrefix(trimmed, "[") {
		var samples []usl.Sample
		if err := json.Unmarshal([]byte(trimmed), &samples); err != nil {
			return nil, fmt.Errorf("json: %w", err)
		}
		return samples, nil
	}
	return parseCSV(trimmed)
}

func parseCSV(s string) ([]usl.Sample, error) {
	var samples []usl.Sample
	sc := bufio.NewScanner(strings.NewReader(s))
	for line := 1; sc.Scan(); line++ {
		txt := strings.TrimSpace(sc.Text())
		if txt == "" || strings.HasPrefix(txt, "#") {
			continue
		}
		parts := strings.Split(txt, ",")
		if len(parts) < 2 {
			return nil, fmt.Errorf("line %d: want 'N,throughput', got %q", line, txt)
		}
		nStr := strings.TrimSpace(parts[0])
		n, err := strconv.Atoi(nStr)
		if err != nil {
			// Tolerate a single header row ("n,throughput").
			if line == 1 {
				continue
			}
			return nil, fmt.Errorf("line %d: bad N %q: %w", line, nStr, err)
		}
		x, err := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: bad throughput %q: %w", line, parts[1], err)
		}
		samples = append(samples, usl.Sample{N: n, Throughput: x})
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	return samples, nil
}

func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "usl-fit: "+format+"\n", args...)
	os.Exit(1)
}
