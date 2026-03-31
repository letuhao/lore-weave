// D0-04: Test pgx v5 JSONB scanning with json.RawMessage
// Run: cd infra/pg18test-go && go run main.go
// Requires: PG18 on localhost:5566 (docker run ... -p 5566:5432)

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, "postgres://loreweave:loreweave_dev@localhost:5566/loreweave_book")
	if err != nil {
		log.Fatalf("connect: %v", err)
	}
	defer pool.Close()

	// Setup
	_, err = pool.Exec(ctx, `
		DROP TABLE IF EXISTS test_jsonb;
		CREATE TABLE test_jsonb (
			id UUID PRIMARY KEY DEFAULT uuidv7(),
			body JSONB NOT NULL,
			body_format TEXT NOT NULL DEFAULT 'json'
		)
	`)
	if err != nil {
		log.Fatalf("setup: %v", err)
	}

	// Test input: Tiptap-like JSON doc
	inputJSON := `{"type":"doc","content":[{"type":"paragraph","_text":"Hello world","content":[{"type":"text","text":"Hello world"}]},{"type":"heading","attrs":{"level":2},"_text":"Chapter One","content":[{"type":"text","text":"Chapter One"}]}]}`

	// INSERT as json.RawMessage
	fmt.Println("=== TEST 1: INSERT json.RawMessage into JSONB column ===")
	var insertedID string
	err = pool.QueryRow(ctx,
		`INSERT INTO test_jsonb (body) VALUES ($1) RETURNING id`,
		json.RawMessage(inputJSON),
	).Scan(&insertedID)
	if err != nil {
		log.Fatalf("insert: %v", err)
	}
	fmt.Printf("PASS: inserted id=%s\n", insertedID)

	// SELECT as json.RawMessage
	fmt.Println("\n=== TEST 2: SELECT JSONB → scan as json.RawMessage ===")
	var body json.RawMessage
	var format string
	err = pool.QueryRow(ctx,
		`SELECT body, body_format FROM test_jsonb WHERE id = $1`, insertedID,
	).Scan(&body, &format)
	if err != nil {
		log.Fatalf("select: %v", err)
	}
	fmt.Printf("PASS: scanned %d bytes, format=%s\n", len(body), format)

	// TEST 3: json.Marshal with json.RawMessage in map → should NOT be base64
	fmt.Println("\n=== TEST 3: json.Marshal(map{body: RawMessage}) → inline JSON ===")
	response := map[string]any{
		"chapter_id":   insertedID,
		"body":         body,
		"draft_format": format,
	}
	serialized, err := json.Marshal(response)
	if err != nil {
		log.Fatalf("marshal: %v", err)
	}
	responseStr := string(serialized)
	fmt.Printf("Response: %s\n", responseStr)

	// Verify: body should be inline JSON, not base64
	if strings.Contains(responseStr, `"body":"eyJ`) {
		fmt.Println("FAIL: body is base64-encoded!")
		log.Fatal("json.RawMessage was serialized as base64")
	}
	if strings.Contains(responseStr, `"body":{"type":"doc"`) {
		fmt.Println("PASS: body is inline JSON object")
	} else {
		fmt.Println("FAIL: body format unexpected")
		log.Fatalf("unexpected body format in response: %s", responseStr)
	}

	// TEST 4: Round-trip — input == output
	fmt.Println("\n=== TEST 4: Round-trip verification ===")
	var roundtripped map[string]any
	json.Unmarshal(serialized, &roundtripped)
	bodyBytes, _ := json.Marshal(roundtripped["body"])
	// Normalize both for comparison (remove whitespace)
	inputNorm := strings.ReplaceAll(inputJSON, " ", "")
	outputNorm := strings.ReplaceAll(string(bodyBytes), " ", "")
	if inputNorm == outputNorm {
		fmt.Println("PASS: input JSON == output JSON (round-trip)")
	} else {
		fmt.Printf("FAIL: mismatch\n  input:  %s\n  output: %s\n", inputNorm, outputNorm)
		log.Fatal("round-trip mismatch")
	}

	// Cleanup
	pool.Exec(ctx, `DROP TABLE test_jsonb`)
	fmt.Println("\n=== ALL TESTS PASSED ===")
}
