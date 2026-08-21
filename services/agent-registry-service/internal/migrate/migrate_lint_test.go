package migrate

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"testing"
)

// The seed prose in schemaSQL lives inside Postgres E'...' literals. A BARE apostrophe
// inside one terminates the string and the whole migration dies with a syntax error at
// boot — while every unit test stays green, because nothing here talks to a database.
//
// This has now bitten twice while authoring the System workflow seeds:
//   1. a backtick in a comment terminated the Go raw string (compile error — caught fast),
//   2. an apostrophe in notes_md terminated the SQL string (runtime error — caught ONLY by
//      reading the container logs, after a full rebuild and a 4-minute eval run).
//
// So: lint it statically — but lint the RIGHT THING. The obvious check ("is there a bare
// quote inside the body?") is TAUTOLOGICALLY GREEN and was shipped that way for one
// commit: the scanner stops AT the first bare quote (that is what "terminator" means), so
// the body it hands you can never contain one. A test that cannot fail on its own bug
// class is worse than no test.
//
// What a bare apostrophe actually does is MIS-TERMINATE the literal early, which leaves
// the following prose sitting in SQL statement position ("…Saying 'first I" + `ll look…`).
// So check what FOLLOWS the closing quote: a correctly-terminated literal in this schema
// is always followed by `,` `)` `;` or `::`. Prose is not.
func TestSchemaSQL_NoBareApostropheInsideEStringLiterals(t *testing.T) {
	for _, lit := range eStringLiterals(t, schemaSQL) {
		if !legalAfterLiteral(lit.after) {
			t.Errorf("an E'...' literal at offset %d is MIS-TERMINATED — the text after its "+
				"closing quote is %q, which is prose, not SQL. That means a BARE APOSTROPHE "+
				"inside the literal ended it early; the migration will die at boot with a "+
				"syntax error while every unit test stays green. Write '' or \\' (or reword).\n"+
				"Literal ends: …%s", lit.start, head(strings.TrimSpace(lit.after), 40),
				tail(lit.body, 60))
		}
	}
}

// A negative control — the lint above must actually FAIL on the exact bug that shipped.
// Without this, "the lint is green" says nothing (see the tautology it replaced).
func TestTheApostropheLint_CatchesTheRealBug(t *testing.T) {
	bad := `INSERT INTO workflows (notes_md) VALUES
  (E'Saying 'first I will look' is not doing it.')
ON CONFLICT DO NOTHING;`
	lits := eStringLiterals(t, bad)
	if len(lits) == 0 {
		t.Fatal("scanner found no literal in the control")
	}
	if legalAfterLiteral(lits[0].after) {
		t.Fatalf("the lint would MISS the real bug: literal body %q, after %q",
			lits[0].body, head(lits[0].after, 20))
	}

	good := `INSERT INTO workflows (notes_md) VALUES
  (E'Saying ''first I will look'' is not doing it.')
ON CONFLICT DO NOTHING;`
	for _, lit := range eStringLiterals(t, good) {
		if !legalAfterLiteral(lit.after) {
			t.Errorf("the lint FALSE-POSITIVES on correctly-escaped prose: after=%q",
				head(lit.after, 20))
		}
	}
}

// legalAfterLiteral: what may legitimately follow a closing quote in this schema.
func legalAfterLiteral(after string) bool {
	s := strings.TrimLeft(after, " \t\r\n")
	if s == "" {
		return true
	}
	switch s[0] {
	case ',', ')', ';', ':':
		return true
	}
	return false
}

func TestSchemaSQL_HasTheSystemWorkflowSeeds(t *testing.T) {
	// A rail that never seeds is a pin that never fires.
	for _, slug := range []string{
		"glossary-bootstrap", "entity-triage", "vision-to-book",
		"populate-from-notes", "kg-build",
	} {
		if !strings.Contains(schemaSQL, "'"+slug+"'") {
			t.Errorf("System workflow %q is not seeded", slug)
		}
	}
	// And every one must be able to CORRECT an already-seeded row: DO NOTHING would freeze
	// a bad rail forever (the "migration never revisits its default" trap). Checked per
	// INSERT INTO workflows statement — the `skills` seed legitimately still uses DO
	// NOTHING (its bodies are served by chat-service, not this table), so a blanket
	// substring check over the whole schema would false-positive on it.
	// NB: the statement cannot be split on ";" — the seed PROSE contains semicolons
	// ("…returns a confirm_token; pass that exact token…"), which is what made the first
	// version of this lint report false failures. Bound each seed by the next statement.
	const ins = "INSERT INTO workflows ("
	seen := 0
	for at := 0; ; {
		i := strings.Index(schemaSQL[at:], ins)
		if i < 0 {
			break
		}
		i += at
		rest := schemaSQL[i+len(ins):]
		end := len(rest)
		for _, next := range []string{"\nINSERT INTO ", "\nCREATE TABLE ", "\nCREATE INDEX ", "\nCREATE UNIQUE "} {
			if k := strings.Index(rest, next); k >= 0 && k < end {
				end = k
			}
		}
		stmt := rest[:end]
		if !strings.Contains(stmt, "DO UPDATE SET") {
			t.Errorf("a System workflow seed does not DO UPDATE — an already-seeded row can "+
				"never be corrected by a deploy:\n%s", head(stmt, 120))
		}
		seen++
		at = i + len(ins) + end
	}
	if seen < 3 {
		t.Errorf("expected at least 3 System workflow seeds, scanned %d", seen)
	}
}

// NOTES_SEED_BUDGET_CHARS mirrors chat-service's pinned-rail prose ceiling
// (workflow_runner.NOTES_CHAR_CAP = 6000) with headroom. A seeded System workflow whose
// notes_md exceeds the CONSUMER's cap is silently TRUNCATED when the rail is pinned into
// the prompt — and the end of a rail's prose is exactly where its vocabulary and honesty
// rules live.
//
// This is not hypothetical: 2026-07-11, the flagship vision-to-book rail's notes were 3218 chars against
// a 3000 cap, so the SPEAK-PLAINLY block ("never say workflow/glossary/spec…") was cut.
// The jargon leak those rules were written to fix therefore survived the fix, and nothing
// said a word. The author of a workflow cannot see the consumer's cap, so assert it here.
const notesSeedBudgetChars = 5000

func TestSchemaSQL_SeededWorkflowNotesFitTheConsumerCap(t *testing.T) {
	for _, lit := range eStringLiterals(t, schemaSQL) {
		// The only E'…' literals in this schema are workflow notes_md bodies.
		if n := len(lit.body); n > notesSeedBudgetChars {
			t.Errorf("a seeded workflow's notes_md is %d chars, over the %d budget — chat-service "+
				"TRUNCATES the pinned rail at NOTES_CHAR_CAP, and the tail is where the "+
				"vocabulary/honesty rules live. Shorten it (or raise both constants together).",
				n, notesSeedBudgetChars)
		}
	}
}

// The done_when grammar is enforced at the agent-authoring path (validateWorkflow), but the
// SEED path — the ONLY path shipping a done_when today, on vision-to-book — bypasses that
// validation entirely (it INSERTs the JSON literal straight into the table). So a typo in a
// seeded done_when would ship a predicate the chat-service consumer cannot parse, silently
// falling every step back to the call log — a stored-but-unread contract. Lint the seed here
// against the SAME closed grammar the writer enforces (mirrors doneWhenRe in workflows.go).
func TestSchemaSQL_SeededDoneWhenMatchesTheClosedGrammar(t *testing.T) {
	// D4 (Phase G · G0): the allowed key set is NOT hardcoded here — it is read from the ONE
	// SoT, contracts/book-state-keys.contract.json, which chat-service's BOOK_STATE_KEYS also
	// checks against (tests/test_book_state_contract.py). Duplicating the key list in this Go
	// regex is exactly the drift D4 exists to kill: a key renamed in the contract + the Python
	// probe would leave a STALE Go allow-list that green-lights a seed the consumer can't read.
	keys := loadBookStateKeys(t)
	keyAlt := strings.Join(keys, "|")
	seedDoneWhenRe := regexp.MustCompile(`"done_when"\s*:\s*"([^"]*)"`)
	grammar := regexp.MustCompile(`^\s*(` + keyAlt + `)\s*(>=|<=|==|>|<)\s*\d+\s*$`)
	found := 0
	for _, m := range seedDoneWhenRe.FindAllStringSubmatch(schemaSQL, -1) {
		found++
		if !grammar.MatchString(m[1]) {
			t.Errorf("seeded done_when %q does not match the closed grammar '<key> <op> <n>' "+
				"(key in %s; op in > >= < <= ==) — the chat-service consumer would silently ignore "+
				"it and fall back to the call log. If you added a key, add it to "+
				"contracts/book-state-keys.contract.json + chat-service BOOK_STATE_KEYS too.",
				m[1], keyAlt)
		}
	}
	if found == 0 {
		t.Error("no seeded done_when found — the vision-to-book rail should carry several; " +
			"if the seed was refactored, update this lint rather than letting it pass vacuously.")
	}
}

// loadBookStateKeys reads the shared SoT contract (contracts/book-state-keys.contract.json) so
// this Go lint and chat-service's BOOK_STATE_KEYS can never drift. The path is resolved from THIS
// test file's location (runtime.Caller), not the process cwd, so it is stable under `go test`.
func loadBookStateKeys(t *testing.T) []string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed — cannot locate the contract")
	}
	// services/agent-registry-service/internal/migrate → repo root is 4 dirs up.
	root := filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "..")
	path := filepath.Join(root, "contracts", "book-state-keys.contract.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("cannot read the book-state-keys contract at %s: %v", path, err)
	}
	var doc struct {
		Keys map[string]json.RawMessage `json:"keys"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("cannot parse the book-state-keys contract: %v", err)
	}
	if len(doc.Keys) == 0 {
		t.Fatal("the book-state-keys contract has no keys — the lint would be vacuously permissive")
	}
	out := make([]string, 0, len(doc.Keys))
	for k := range doc.Keys {
		out = append(out, regexp.QuoteMeta(k))
	}
	return out
}

type eLit struct {
	start int
	body  string
	// after is the text immediately following the closing quote. This is the ONLY field
	// that can reveal a bare apostrophe: the scanner necessarily stops AT one (that is
	// what terminating means), so `body` can never contain it — checking `body` is the
	// tautology this lint originally shipped.
	after string
}

// eStringLiterals finds each E'...' literal's body. It walks the raw SQL and, on E',
// scans to the terminating quote while honoring the two legal escapes — which is exactly
// the rule Postgres itself applies, so a body we fail to terminate is a body Postgres
// would also mis-terminate.
func eStringLiterals(t *testing.T, sql string) []eLit {
	t.Helper()
	var out []eLit
	for i := 0; i+1 < len(sql); i++ {
		if sql[i] != 'E' || sql[i+1] != '\'' {
			continue
		}
		j := i + 2
		var b strings.Builder
		for j < len(sql) {
			c := sql[j]
			if c == '\\' && j+1 < len(sql) { // \' and friends
				b.WriteByte(c)
				b.WriteByte(sql[j+1])
				j += 2
				continue
			}
			if c == '\'' {
				if j+1 < len(sql) && sql[j+1] == '\'' { // '' escape
					b.WriteString("''")
					j += 2
					continue
				}
				break // real terminator
			}
			b.WriteByte(c)
			j++
		}
		// j points AT the terminating quote (or past the end). Capture what follows it —
		// that is where a mis-termination shows up.
		after := ""
		if j < len(sql) {
			end := j + 1 + 24
			if end > len(sql) {
				end = len(sql)
			}
			after = sql[j+1 : end]
		}
		out = append(out, eLit{start: i, body: b.String(), after: after})
		i = j
	}
	if len(out) == 0 {
		t.Fatal("no E'...' literals found — the lint would be vacuously green")
	}
	return out
}

func head(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

func tail(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[len(s)-n:]
}

// seededSteps parses every rail's `steps` array out of schemaSQL as real JSON, rather than
// regex-scraping step objects: one step carries a nested `inputs_map` object, so a
// `\{"id":[^}]*\}` scrape stops at the INNER brace and silently drops fields — the kind of
// half-reading that makes a lint quietly narrower than it claims to be.
func seededSteps(t *testing.T) []map[string]any {
	t.Helper()
	arrayRe := regexp.MustCompile(`'(\[[\s\S]*?\])'::jsonb`)
	var out []map[string]any
	for _, m := range arrayRe.FindAllStringSubmatch(schemaSQL, -1) {
		var steps []map[string]any
		if err := json.Unmarshal([]byte(m[1]), &steps); err != nil {
			continue // not a steps array (inputs, surfaces, …)
		}
		for _, st := range steps {
			if _, ok := st["tool"]; ok {
				out = append(out, st)
			}
		}
	}
	if len(out) < 20 {
		t.Fatalf("only %d seeded steps parsed — the lint would be vacuously permissive", len(out))
	}
	return out
}

// A rail step is a RECIPE ENTRY, and the same entry appears in more than one recipe: several
// rails walk the author through saving their cast, connecting it, proposing a plan. When two
// rails describe the SAME action — same tool, same done_when predicate — they must agree on
// whether it is repeatable, because `repeat` decides whether `done_suppress` takes the tool
// away. Nothing enforced that, and the seeds drifted into contradicting themselves:
//
//	glossary_propose_entities / "cast > 0"        save        no repeat
//	glossary_propose_entities / "cast > 0"        save-cast   repeat ✓
//	kg_add_nodes / "connections > 0"              place-cast  no repeat
//	kg_add_nodes / "connections > 0"              connect-people repeat ✓
//
// So whether an author could save a second batch of characters depended on which rail the
// intent router happened to pin. The `plan_propose_spec` pair was worse: BOTH were one-shot,
// which retired the only tool that can start a plan the moment a book had one — measured on
// the Mị Đế dogfood 2026-08-02, where the co-writer could not plan a second arc and invented
// a run_id to reach the downstream tools it could still see.
//
// This does not decide WHICH value is right — that is a judgement per action. It only refuses
// to let one action mean two things, which is the drift a seed edited rail-by-rail produces.
func TestSchemaSQL_SameActionMeansTheSameThingInEveryRail(t *testing.T) {
	type variant struct {
		repeat bool
		ids    []string
	}
	byAction := map[string]map[bool]*variant{}
	for _, st := range seededSteps(t) {
		dw, _ := st["done_when"].(string)
		if dw == "" {
			continue // no artifact predicate ⇒ nothing durable to disagree about
		}
		tool, _ := st["tool"].(string)
		id, _ := st["id"].(string)
		rep, _ := st["repeat"].(bool)
		key := tool + " / " + dw
		if byAction[key] == nil {
			byAction[key] = map[bool]*variant{}
		}
		if byAction[key][rep] == nil {
			byAction[key][rep] = &variant{repeat: rep}
		}
		byAction[key][rep].ids = append(byAction[key][rep].ids, id)
	}
	seen := 0
	for key, variants := range byAction {
		seen++
		if len(variants) < 2 {
			continue
		}
		var yes, no []string
		for rep, v := range variants {
			if rep {
				yes = v.ids
			} else {
				no = v.ids
			}
		}
		t.Errorf("the action %q is seeded with CONTRADICTORY repeat semantics: steps %v declare "+
			"repeat:true, steps %v do not. `repeat` decides whether done_suppress removes the "+
			"tool once the step is finished, so the same action would be re-runnable on one rail "+
			"and retired on another — an author hits whichever the router pinned. Pick one and "+
			"apply it to every occurrence.", key, yes, no)
	}
	if seen == 0 {
		t.Error("no done_when-bearing step found — the lint would pass vacuously; if the seeds " +
			"were refactored, update this lint rather than letting it go quiet.")
	}
}
