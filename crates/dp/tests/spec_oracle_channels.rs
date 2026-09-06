//! `G3` — **`13_channel_ordering_and_writer.md` and `17_channel_lifecycle.md`
//! get an oracle.**
//!
//! Fourth and fifth payments against `scripts/dp-oracle-coverage-gate.py`'s
//! ratchet. Both documents specify **SQL**, and in this repo the SQL they
//! specify has actually shipped — `0014_channel_ordering.up.sql` and
//! `0019_channels.up.sql` — so both sides of the comparison exist and neither
//! rule is an orphan.
//!
//! # Why the migrations are compared as TEXT and not against a live database
//!
//! The question these rules ask is *"does the migration this repo declares
//! match the document that governs it"*, and that is answerable from a
//! checkout. `scripts/dp-channels-live-smoke.py` asks the other question —
//! whether a real Postgres enforces it — and needs a stack. Two questions, two
//! mechanisms; conflating them would make this one unrunnable in CI and answer
//! neither well.
//!
//! # What each document already had, and what it did not
//!
//! `0019_channels.up.sql` cites `17_channel_lifecycle.md` **by line number**, in
//! comments, five times. That is the most fragile citation there is: it names a
//! file, a line and a claim, and nothing checks any of the three. `0014`'s
//! header carries a *"SPEC CORRECTION"* that lived eleven days as a SQL comment
//! before the LOCKED file learned about it (`REC-99b`, recorded in the document
//! itself). Both are the `FLOW-2` shape — a document and a fact drifting apart
//! with nothing watching — and both are watched now.
//!
//! # The finding this file shipped with — PAID 2026-08-11
//!
//! `DP-Ch11`'s schema block declares **five** columns on `events`. The shipped
//! migration added **four**: `turn_number` was specified by a LOCKED document
//! and created by no migration in this repo, measured rather than assumed. It
//! got a [`DEFERRED_EVENT_COLUMNS`] row naming what it waited on, and the row
//! failed the day a migration added the column — which is the whole difference
//! between a register and a comment.
//!
//! `0020_turn_boundary` is that day, and the register is now **empty**.
//!
//! ⚠ **The arm did not fire on its own, and that is the lesson.** The shipped
//! side read ONE HARDCODED FILE — `0014_channel_ordering.up.sql` — so the
//! promise *"fails the day a migration adds the column"* was true only for
//! `0014`. `0020` added the column, the suite stayed green, and the row
//! recording it as unshipped survived. `NV-3`: an enumerated scope is
//! **default-uncovered**, and the unasked question was *"what about a migration
//! that does not exist yet?"* — which is the only question a deferral register
//! is FOR. The forward direction now walks every per-reality migration
//! (`columns_added_to_events_anywhere`, with a reach floor); the reverse arm
//! still reads `0014` alone, deliberately, because DP-Ch11 governs that
//! migration's columns and not another document's.

use std::fs;
use std::path::PathBuf;

fn doc(name: &str) -> String {
    let p: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/03_planning/LLM_MMO_RPG/06_data_plane")
        .join(name);
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

fn migration(name: &str) -> String {
    let p: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../contracts/migrations/per_reality")
        .join(name);
    fs::read_to_string(&p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

/// `DP-Ch11` columns that no migration creates, each with what they wait on.
/// **EMPTY as of 2026-08-11**, and that is the register working rather than the
/// register being unnecessary.
///
/// Its one row was `turn_number`, deferred because *"15_turn_boundary.md's turn
/// machinery has no implementation and nothing would advance the counter, so
/// the column would be a NOT NULL DEFAULT 0 that never moves."* That reason
/// named its own unblocking condition, `0020_turn_boundary` met it, and the row
/// is gone — the register shrank, which is the only direction it may move.
///
/// An empty slice is deliberate rather than a deletion of the machinery: the
/// arms above still run, so the next LOCKED column that no migration creates
/// gets caught on arrival instead of needing this apparatus rebuilt.
const DEFERRED_EVENT_COLUMNS: &[(&str, &str)] = &[];

/// Drop `--` comments so a column named in prose is not read as a column.
///
/// Load-bearing here rather than tidy: `DP-Ch11`'s own block contains an
/// AMENDMENT comment that quotes the migration and names columns, and `0014`'s
/// header comment names `channel_event_id` four times while describing what it
/// could **not** create.
fn sql_code(text: &str) -> String {
    text.lines()
        .map(|l| l.split("--").next().unwrap_or(""))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Every `ADD COLUMN [IF NOT EXISTS] <name>` in a chunk of SQL.
fn added_columns(sql: &str) -> Vec<String> {
    let code = sql_code(sql);
    let mut out = Vec::new();
    let mut rest = code.as_str();
    while let Some(i) = rest.find("ADD COLUMN") {
        let after = rest[i + "ADD COLUMN".len()..].trim_start();
        let after = after.strip_prefix("IF NOT EXISTS").unwrap_or(after).trim_start();
        let name: String =
            after.chars().take_while(|c| c.is_alphanumeric() || *c == '_').collect();
        if !name.is_empty() {
            out.push(name);
        }
        rest = &rest[i + "ADD COLUMN".len()..];
    }
    out
}

/// Every column added to `events` by ANY per-reality migration.
///
/// # Why this is not `added_columns(migration("0014_channel_ordering.up.sql"))`
///
/// It was, and that made `DEFERRED_EVENT_COLUMNS`'s promise false. The register
/// says a row *"fails the day a migration adds the column"* — but the shipped
/// side read **one hardcoded file**, so the day arrived in `0020_turn_boundary`
/// and nothing happened. Measured: the migration added `events.turn_number`,
/// the suite stayed green, and the row recording it as unshipped survived.
///
/// `NV-3` — an enumerated scope is **default-uncovered**: the question "what
/// about a column added tomorrow, in a migration that does not exist yet?" had
/// the answer "invisible". Which is exactly what a deferral register cannot
/// afford, because its whole value is noticing the day its subject arrives.
///
/// **The reverse arm deliberately still reads only `0014`** — see its call
/// site. The two directions have different scopes on purpose: DP-Ch11 governs
/// what `0014` puts on the event log, so a column added by a DIFFERENT
/// migration (`0013`'s `content_sha256`, `0016`'s `ruleset_digest`,
/// `0020`'s `turn_number`) is another document's subject and flagging it here
/// would be this oracle claiming authority it does not have.
fn columns_added_to_events_anywhere() -> Vec<String> {
    let dir: PathBuf =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality");
    let mut out = Vec::new();
    let mut seen_files = 0usize;
    let Ok(entries) = fs::read_dir(&dir) else {
        panic!("cannot read {}", dir.display());
    };
    let mut paths: Vec<PathBuf> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.to_string_lossy().ends_with(".up.sql"))
        .collect();
    paths.sort();
    for p in &paths {
        let Ok(sql) = fs::read_to_string(p) else { continue };
        seen_files += 1;
        // Only `ALTER TABLE events` blocks — `ADD COLUMN` on a sibling table is
        // not a column on the event log.
        let code = sql_code(&sql);
        let mut rest = code.as_str();
        while let Some(i) = rest.find("ALTER TABLE events") {
            let tail = &rest[i..];
            let end = tail.find(';').unwrap_or(tail.len());
            out.extend(added_columns(&tail[..end]));
            rest = &tail[end.min(tail.len())..];
            if rest.is_empty() {
                break;
            }
            rest = &rest[1.min(rest.len())..];
        }
    }
    // Reach floor: a walk that finds nothing and a tree with no event columns
    // are byte-identical, and this function's whole job is seeing the arrival.
    assert!(
        seen_files >= 15,
        "the per-reality migration walk read only {seen_files} file(s) — it is pointed at nothing, \
         and every arm resting on it would report clean forever"
    );
    out
}

/// The column list of the first `PRIMARY KEY (...)` after `anchor`.
fn primary_key_after(sql: &str, anchor: &str) -> Vec<String> {
    let code = sql_code(sql);
    let Some(a) = code.find(anchor) else {
        return Vec::new();
    };
    let rest = &code[a..];
    let Some(p) = rest.find("PRIMARY KEY") else {
        return Vec::new();
    };
    let tail = &rest[p..];
    let (Some(open), Some(close)) = (tail.find('('), tail.find(')')) else {
        return Vec::new();
    };
    if close < open {
        return Vec::new();
    }
    tail[open + 1..close].split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect()
}

/// The fenced sql block that follows `heading`.
///
/// # A fence is a LINE, and scanning for the delimiter anywhere defeats itself
///
/// The first version searched for the closing delimiter as a plain substring.
/// `DP-Ch11`'s block contains an amendment comment that *describes a fence*:
///
/// ```text
/// -- read only ```sql blocks containing `REFERENCES channels`, and this
/// ```
///
/// — so the block ended after 341 characters, `ADD COLUMN` matched **zero**
/// times, and both `DP-Ch11` rules failed their own non-vacuity guards on the
/// first run. That is the cheap version of this bug. The expensive version is a
/// parser that truncates a block and still finds *something*, agrees with the
/// code, and reports green — which is why the guards that caught it are worth
/// more than the fix.
///
/// A CommonMark fence is a line whose first non-space characters are the
/// delimiter. Matching that is reading the format rather than special-casing
/// the one document that broke it.
fn sql_block_after(text: &str, heading: &str) -> String {
    let Some(h) = text.find(heading) else {
        return String::new();
    };
    let mut lines = text[h..].lines();
    let opened = lines.by_ref().any(|l| l.trim_start().starts_with("```"));
    if !opened {
        return String::new();
    }
    lines
        .take_while(|l| !l.trim_start().starts_with("```"))
        .collect::<Vec<_>>()
        .join("\n")
}

/// `DP-Ch11` — **the event-log columns the spec declares, against the ones the
/// migration adds.**
///
/// Three arms, and the third is what stops [`DEFERRED_EVENT_COLUMNS`] becoming
/// permanent: a row whose column gains a migration FAILS.
#[test]
fn the_event_log_columns_match_dp_ch11_or_declare_why_not() {
    let spec = doc("13_channel_ordering_and_writer.md");
    let shipped_sql = migration("0014_channel_ordering.up.sql");

    let declared = added_columns(&sql_block_after(&spec, "### Event log schema extension"));
    let shipped = added_columns(&shipped_sql);

    // Non-vacuity on both sides — an empty parse agrees with anything, and the
    // shipped side is the one that fails silently, because "found none" and
    // "found all four" are the same green.
    assert!(
        declared.len() >= 4,
        "DP-Ch11's schema block parsed only {} ADD COLUMN(s) {declared:?} — the block's shape \
         moved and this oracle is no longer reading it",
        declared.len()
    );
    assert!(
        shipped.len() >= 4,
        "0014_channel_ordering.up.sql parsed only {} ADD COLUMN(s) {shipped:?} — the migration's \
         shape moved and this oracle is no longer reading it",
        shipped.len()
    );

    let deferred: Vec<&str> = DEFERRED_EVENT_COLUMNS.iter().map(|(c, _)| *c).collect();
    let mut problems: Vec<String> = Vec::new();

    // The FORWARD direction asks "does this column exist anywhere yet?", so it
    // must see every migration — `shipped` (0014 only) is the reverse arm's
    // scope and using it here made the register's promise false. See
    // `columns_added_to_events_anywhere`.
    let shipped_anywhere = columns_added_to_events_anywhere();

    for col in &declared {
        let is_shipped = shipped_anywhere.iter().any(|s| s == col);
        let is_deferred = deferred.contains(&col.as_str());
        if !is_shipped && !is_deferred {
            problems.push(format!(
                "DP-Ch11 declares `events.{col}` and 0014_channel_ordering.up.sql does not add \
                 it, nor does DEFERRED_EVENT_COLUMNS say why. A column a LOCKED document \
                 specifies and no migration creates is read by nothing and written by nothing."
            ));
        }
        if is_shipped && is_deferred {
            problems.push(format!(
                "`{col}` IS added by the migration and is still in DEFERRED_EVENT_COLUMNS — \
                 delete the row. The register shrinks or it rots."
            ));
        }
    }

    for col in &shipped {
        if !declared.iter().any(|d| d == col) {
            problems.push(format!(
                "0014_channel_ordering.up.sql adds `events.{col}` and DP-Ch11 does not declare \
                 it. A column on the event log that no LOCKED document governs is a schema \
                 decision made in a migration file."
            ));
        }
    }

    for (col, why) in DEFERRED_EVENT_COLUMNS {
        if why.trim().is_empty() {
            problems.push(format!("deferred column `{col}` names no blocker"));
        }
        if !declared.iter().any(|d| d == col) {
            problems.push(format!(
                "DEFERRED_EVENT_COLUMNS defers `{col}` and DP-Ch11 does not declare it — the row \
                 defers nothing."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "13_channel_ordering_and_writer.md DP-Ch11 declares {declared:?} and \
         0014_channel_ordering.up.sql adds {shipped:?}:\n  - {}",
        problems.join("\n  - ")
    );
}

/// `DP-Ch11` — **the uniqueness triple, which is where `DP-A15` actually
/// lives.**
///
/// `events` is `PARTITION BY RANGE (recorded_at)`, so the unique constraint the
/// spec originally asked for cannot exist on it; `REC-99b` moved the guarantee
/// to `channel_event_index`'s primary key. That key **is** the per-channel
/// gapless total order — so its column list, and their ORDER, is a contract and
/// not a detail.
#[test]
fn the_channel_event_index_key_matches_dp_ch11() {
    let spec = doc("13_channel_ordering_and_writer.md");
    let shipped_sql = migration("0014_channel_ordering.up.sql");

    let want = primary_key_after(
        &sql_block_after(&spec, "### Event log schema extension"),
        "channel_event_index",
    );
    let got = primary_key_after(&shipped_sql, "channel_event_index");

    assert_eq!(
        want,
        vec!["reality_id", "channel_id", "channel_event_id"],
        "DP-Ch11's channel_event_index primary key changed shape; this oracle's expectation must \
         follow the document, and a reader must decide whether the change was intended"
    );
    assert_eq!(
        got, want,
        "0014_channel_ordering.up.sql's channel_event_index PRIMARY KEY is {got:?} and \
         13_channel_ordering_and_writer.md DP-Ch11 specifies {want:?}. That key is where DP-A15's \
         per-channel gapless total order is enforced — REC-99b moved it here precisely because \
         `events` is partitioned and could not carry it — so a differing column list is the \
         invariant, not an index"
    );
}

/// `DP-Ch31` — **the lifecycle states, against the CHECK constraint that is the
/// only thing enforcing them.**
///
/// `0019_channels.up.sql` cites this document by LINE NUMBER in five comments.
/// A citation naming a file, a line and a claim, checked by nothing, is three
/// things that can rot independently. This checks the one that matters: the
/// closed set.
#[test]
fn the_channel_lifecycle_states_match_dp_ch31() {
    let spec = doc("17_channel_lifecycle.md");
    let shipped_sql = migration("0019_channels.up.sql");

    // The state table: rows whose first cell is a single backticked word,
    // bounded by the transitions table that follows it.
    let a = spec.find("### State machine").expect("DP-Ch31's state machine section");
    let b = spec[a..]
        .find("### Transitions table")
        .map(|i| a + i)
        .expect("DP-Ch31's transitions table");
    let states: Vec<String> = spec[a..b]
        .lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .filter_map(|l| {
            let cells: Vec<&str> = l.split('|').map(str::trim).collect();
            if cells.len() < 3 {
                return None;
            }
            cells[1]
                .strip_prefix('`')
                .and_then(|r| r.strip_suffix('`'))
                .filter(|n| n.chars().all(char::is_alphabetic))
                .map(|n| n.to_ascii_lowercase())
        })
        .collect();

    // The CHECK is the enforcement. Everything else about `lifecycle` is a TEXT
    // column, so this constraint is the entire closed set.
    let code = sql_code(&shipped_sql);
    let anchor = "CHECK (lifecycle IN (";
    let i = code
        .find(anchor)
        .unwrap_or_else(|| panic!("0019_channels.up.sql no longer has a `{anchor}…` constraint"));
    let tail = &code[i + anchor.len()..];
    let close = tail.find(')').expect("the CHECK's value list is unterminated");
    let enforced: Vec<String> = tail[..close]
        .split(',')
        .map(|s| s.trim().trim_matches('\'').to_string())
        .filter(|s| !s.is_empty())
        .collect();

    assert!(
        states.len() >= 3,
        "DP-Ch31's state table parsed only {} state(s) {states:?} — the table's shape moved and \
         this oracle is no longer reading it",
        states.len()
    );

    let (mut d, mut e) = (states.clone(), enforced.clone());
    d.sort();
    d.dedup();
    e.sort();
    assert_eq!(
        d, e,
        "17_channel_lifecycle.md DP-Ch31 defines the states {states:?} and \
         0019_channels.up.sql's channels_lifecycle_known CHECK enforces {enforced:?}. That CHECK \
         is the whole closed set — `lifecycle` is a bare TEXT column otherwise — so a state the \
         document defines and the constraint rejects is unreachable, and one the constraint \
         accepts and the document does not define is a state no rule governs"
    );
}

/// `DP-Ch31` — **the transitions table against the state table, which is a
/// document checked against itself.**
///
/// `FLOW-2`'s shape, and the corpus has been measured to contain it: a
/// transition naming a state the state machine does not define drifts with no
/// code change at all, so no doc↔code check could ever see it.
#[test]
fn every_dp_ch31_transition_names_a_state_dp_ch31_defines() {
    let spec = doc("17_channel_lifecycle.md");
    let a = spec.find("### State machine").expect("DP-Ch31's state machine section");
    let b = spec[a..].find("### Transitions table").map(|i| a + i).expect("transitions table");
    let c = spec[b..].find("### Schema additions").map(|i| b + i).unwrap_or(spec.len());

    let defined: Vec<String> = spec[a..b]
        .lines()
        .filter_map(|l| {
            let cells: Vec<&str> = l.split('|').map(str::trim).collect();
            (cells.len() >= 3)
                .then(|| cells[1])?
                .strip_prefix('`')
                .and_then(|r| r.strip_suffix('`'))
                .filter(|n| n.chars().all(char::is_alphabetic))
                .map(|n| n.to_ascii_lowercase())
        })
        .collect();

    // `(none)` and `(any)` are the table's own notation for "outside the state
    // machine" — a creation with no prior state, and a terminal row that
    // forbids every successor. Skipping cells that open with `(` is reading the
    // notation, not making an exception for two strings.
    let mut mentioned: Vec<String> = Vec::new();
    for line in spec[b..c].lines() {
        let cells: Vec<&str> = line.split('|').map(str::trim).collect();
        if cells.len() < 4 || cells[1] == "From" || cells[1].starts_with("---") {
            continue;
        }
        for cell in [cells[1], cells[2]] {
            if cell.starts_with('(') {
                continue;
            }
            let token: String =
                cell.chars().take_while(|ch| ch.is_alphabetic()).collect::<String>().to_lowercase();
            if !token.is_empty() {
                mentioned.push(token);
            }
        }
    }

    assert!(
        mentioned.len() >= 6,
        "DP-Ch31's transitions table parsed only {} state mention(s) {mentioned:?} — the table's \
         shape moved and a comparison against nothing agrees with anything",
        mentioned.len()
    );

    let unknown: Vec<&String> = mentioned.iter().filter(|m| !defined.contains(m)).collect();
    assert!(
        unknown.is_empty(),
        "17_channel_lifecycle.md DP-Ch31's transitions table names state(s) {unknown:?} that its \
         own state machine does not define ({defined:?}). The document contradicts itself, and \
         no document-to-code check could see it — the state exists in neither the schema nor the \
         code, so both agree with the half of the file that is right"
    );
}

// ───────────────────── DP-Ch21 / DP-Ch22 — 15_turn_boundary.md ──────────────────────

/// `DP-Ch22`'s schema block against the migration that ships it.
///
/// This document left `dp-oracle-coverage-gate`'s `NO_PRODUCER` table on
/// 2026-08-11: `ChannelWriter::advance_turn` exists, so an oracle over it is no
/// longer the orphan shape §0.6c forbids.
///
/// # What it compares, and the one thing it deliberately does not
///
/// DP-Ch22 declares two columns and an index. All three are read out of the
/// document's own SQL block and checked against `0020_turn_boundary.up.sql` —
/// so renaming either side reds, and the message names both.
///
/// It does **not** compare the index's *shape*. DP-Ch22's original text
/// specified a partial UNIQUE index, which Postgres cannot create on a
/// partitioned table; the doc carries an `AMENDED` block saying so and giving a
/// conformant form. Pinning the shape here would pin the amendment's prose, not
/// the schema — and the property that actually matters (the DDL runs) is proven
/// by executing it, which `T1` did.
#[test]
fn dp_ch22_turn_columns_are_shipped_by_a_migration() {
    let spec = doc("15_turn_boundary.md");
    let migration_sql = migration("0020_turn_boundary.up.sql");

    // Every `ADD COLUMN` the document's schema section declares.
    let declared = added_columns(&spec);
    assert!(
        declared.len() >= 2,
        "15_turn_boundary.md parsed only {} ADD COLUMN(s) {declared:?} — DP-Ch22's schema blocks \
         moved and this oracle is reading nothing",
        declared.len()
    );

    let shipped = added_columns(&migration_sql);
    let mut problems: Vec<String> = Vec::new();
    for col in &declared {
        if !shipped.iter().any(|s| s == col) {
            problems.push(format!(
                "DP-Ch22 declares `{col}` and 0020_turn_boundary.up.sql does not add it. The \
                 turn counter's schema and its specification have drifted."
            ));
        }
    }
    for col in &shipped {
        if !declared.iter().any(|d| d == col) {
            problems.push(format!(
                "0020_turn_boundary.up.sql adds `{col}` and 15_turn_boundary.md does not declare \
                 it — a schema decision made in a migration file."
            ));
        }
    }

    // DP-Ch24: turn 0 is the never-advanced sentinel, so the column must
    // default to it. A NULLable or 1-defaulted column would make "this channel
    // does not use turns" indistinguishable from "turn one is in progress".
    // ⚠ Anchored on `EXISTS turn_number`, NOT on `turn_number BIGINT NOT NULL
    // DEFAULT 0` — because `last_turn_number BIGINT NOT NULL DEFAULT 0`
    // CONTAINS that substring. The looser form was satisfied by the sibling
    // column, so `events.turn_number`'s default could change to 1 and this arm
    // would still pass. Found by a bite harness refusing an ambiguous anchor.
    if !migration_sql.contains("EXISTS turn_number BIGINT NOT NULL DEFAULT 0") {
        problems.push(
            "DP-Ch24 makes turn 0 the 'never advanced' sentinel, and the migration no longer \
             declares `turn_number BIGINT NOT NULL DEFAULT 0`. Without that default, a channel \
             with no boundary is indistinguishable from one mid-turn-one."
                .to_string(),
        );
    }

    assert!(
        problems.is_empty(),
        "15_turn_boundary.md declares {declared:?}; 0020 ships {shipped:?}:\n  - {}",
        problems.join("\n  - ")
    );
}

/// `SF-3` — `channel_turn_index` is specified as OPTIONAL and is not built.
///
/// The register is one row and its shrink arm is the point: the day a migration
/// creates the table, this reds and the row must go. That is what stops a
/// "deliberately unbuilt" note from ageing into a stale claim nobody rechecks.
#[test]
fn the_optional_turn_index_is_still_unbuilt_and_still_optional() {
    let spec = doc("15_turn_boundary.md");

    // The doc must still CALL it optional. If DP-Ch22 is amended to require the
    // table, SF-3's reasoning evaporates and this row is no longer a choice.
    assert!(
        spec.contains("OPTIONAL and currently unbuilt"),
        "15_turn_boundary.md no longer describes `channel_turn_index` as optional — SF-3 rests on \
         that sentence, so the fork must be re-decided rather than inherited"
    );

    // THE SHRINK ARM: nothing may create it while the row says nothing does.
    let dir: PathBuf =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality");
    let mut creators: Vec<String> = Vec::new();
    let mut seen = 0usize;
    let mut paths: Vec<PathBuf> = fs::read_dir(&dir)
        .expect("per_reality migrations")
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.to_string_lossy().ends_with(".up.sql"))
        .collect();
    paths.sort();
    for p in &paths {
        let Ok(sql) = fs::read_to_string(p) else { continue };
        seen += 1;
        if sql_code(&sql).contains("CREATE TABLE IF NOT EXISTS channel_turn_index")
            || sql_code(&sql).contains("CREATE TABLE channel_turn_index")
        {
            creators.push(p.file_name().unwrap_or_default().to_string_lossy().to_string());
        }
    }
    assert!(
        seen >= 15,
        "the migration walk read only {seen} file(s) — pointed at nothing, and the arm below \
         would report clean forever"
    );
    assert!(
        creators.is_empty(),
        "`channel_turn_index` is recorded as deliberately unbuilt (SF-3) and {creators:?} now \
         creates it. Either the failover anomaly it prevents was observed — in which case say so \
         and retire SF-3 — or the table arrived without the decision being revisited."
    );
}

// ───────────────────── DP-Ch51..53 — 21_llm_turn_slot.md ──────────────────────

/// `DP-Ch51`'s schema block against the migration that ships it, plus the
/// property the whole document rests on.
///
/// This document left `NO_PRODUCER` on 2026-08-11 when
/// `ChannelWriter::claim_turn_slot` shipped.
#[test]
fn dp_ch51_turn_slot_columns_are_shipped_and_the_slot_stays_advisory() {
    let spec = doc("21_llm_turn_slot.md");
    let migration_sql = migration("0021_turn_slot.up.sql");

    let declared = added_columns(&spec);
    assert!(
        declared.len() >= 4,
        "21_llm_turn_slot.md parsed only {} ADD COLUMN(s) {declared:?} — DP-Ch51's schema block \
         moved and this oracle is reading nothing",
        declared.len()
    );
    let shipped = added_columns(&migration_sql);
    let mut problems: Vec<String> = Vec::new();
    for col in &declared {
        if !shipped.iter().any(|s| s == col) {
            problems.push(format!(
                "DP-Ch51 declares `channel_writer_state.{col}` and 0021_turn_slot.up.sql does not \
                 add it."
            ));
        }
    }
    for col in &shipped {
        if !declared.iter().any(|d| d == col) {
            problems.push(format!(
                "0021_turn_slot.up.sql adds `{col}` and 21_llm_turn_slot.md does not declare it."
            ));
        }
    }

    // THE LOAD-BEARING PROPERTY. DP-Ch51 says twice that the slot does not
    // block writes, and it is the single most likely thing to be "improved"
    // into a lock by someone who reads only the column names. If the document
    // ever stops saying it, that is a design change and must not be inherited.
    if !spec.contains("does **not** block other writes") {
        problems.push(
            "21_llm_turn_slot.md no longer states that the slot does NOT block other writes. \
             Every consumer — and `a_held_turn_slot_does_not_block_writes` — depends on the slot \
             being advisory; blocking is channel_pause's job (DP-Ch35)."
                .to_string(),
        );
    }

    // ...and the migration must not have grown a constraint that makes it one.
    // A NOT NULL or a UNIQUE on the occupant would turn the hint into a mutex
    // without anybody editing the prose.
    for forbidden in ["current_turn_actor JSONB NOT NULL", "UNIQUE (current_turn_actor"] {
        if migration_sql.contains(forbidden) {
            problems.push(format!(
                "0021_turn_slot.up.sql contains `{forbidden}` — that makes an ADVISORY hint behave \
                 like a lock, which DP-Ch51 explicitly forbids."
            ));
        }
    }

    assert!(
        problems.is_empty(),
        "21_llm_turn_slot.md declares {declared:?}; 0021 ships {shipped:?}:\n  - {}",
        problems.join("\n  - ")
    );
}

/// `SF-4` — DP-Ch52's auto-timeout and DP-Ch53's three patterns are unbuilt,
/// and the reason is a dependency the document itself names.
///
/// The register is prose-plus-a-shrink-arm: the day `channel_pause` exists, the
/// patterns become buildable and this reds so the fork is re-decided rather
/// than quietly inherited.
#[test]
fn the_unbuilt_half_of_dp_ch5x_still_has_its_reason() {
    let spec = doc("21_llm_turn_slot.md");

    // The document's own justification for shipping the primitives without the
    // patterns. If this sentence goes, SF-4's scope decision has no source.
    assert!(
        spec.contains("not strictly required for any pattern to work"),
        "21_llm_turn_slot.md no longer says the two primitives are optional to the patterns — \
         SF-4 split the scope on that sentence"
    );

    // THE SHRINK ARM: `channel_pause` is what DP-Ch53's patterns compose.
    let mut producers: Vec<String> = Vec::new();
    let mut seen = 0usize;
    for root in ["crates", "services"] {
        let dir: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(root);
        let mut stack = vec![dir];
        while let Some(d) = stack.pop() {
            let Ok(entries) = fs::read_dir(&d) else { continue };
            for e in entries.flatten() {
                let p = e.path();
                if p.is_dir() {
                    let n = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if n != "target" && n != "node_modules" {
                        stack.push(p);
                    }
                } else if p.extension().is_some_and(|x| x == "rs") {
                    seen += 1;
                    let Ok(src) = fs::read_to_string(&p) else { continue };
                    // This file NAMES the symbol, so it would match itself.
                    if p.ends_with("spec_oracle_channels.rs") {
                        continue;
                    }
                    let code: String = src
                        .lines()
                        .filter(|l| !l.trim_start().starts_with("//"))
                        .collect::<Vec<_>>()
                        .join("\n");
                    if code.contains("fn channel_pause") || code.contains("channel_pause(") {
                        producers.push(p.display().to_string());
                    }
                }
            }
        }
    }
    assert!(
        seen > 200,
        "the source walk found only {seen} .rs file(s) — pointed at nothing, and the arm below \
         would report clean forever"
    );
    assert!(
        producers.is_empty(),
        "`channel_pause` (DP-Ch35) now exists in {producers:?}. SF-4 excluded DP-Ch53's three \
         patterns BECAUSE it did not — that reason has expired, so re-decide the scope instead of \
         inheriting it."
    );
}

// ─────────────────── DP-Ch16 / DP-Ch17 — 14_durable_subscribe.md ────────────────────

/// `DP-Ch16`'s stream-item variants against the enum that ships them.
///
/// This document left `NO_PRODUCER` on 2026-08-12 when
/// `ChannelWriter::read_channel_events_durable` shipped.
///
/// The variants are the doc↔code pair worth pinning, and not for tidiness:
/// `Heartbeat` and `StreamEnd` are NOT produced by the catch-up read, so
/// nothing else in the tree would notice if they were dropped from the enum —
/// and dropping them is exactly what a later author would do on seeing two
/// variants nothing constructs. They exist so the `match` a consumer writes
/// today still compiles when the live tail lands.
#[test]
fn dp_ch16_stream_item_variants_match_the_shipped_enum() {
    let spec = doc("14_durable_subscribe.md");
    let src = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../dp-kernel/src/channel.rs"),
    )
    .expect("dp-kernel channel.rs");

    // The variants DP-Ch16's `DurableStreamItem` block declares.
    let block = sql_block_after(&spec, "pub enum DurableStreamItem");
    let declared: Vec<&str> = ["Event", "Heartbeat", "StreamEnd"]
        .into_iter()
        .filter(|v| block.contains(v) || spec.contains(&format!("{v} {{")))
        .collect();
    assert!(
        declared.len() >= 3,
        "14_durable_subscribe.md declares only {declared:?} stream-item variant(s) — DP-Ch16's \
         enum moved and this oracle is reading nothing"
    );

    let mut problems: Vec<String> = Vec::new();
    for v in &declared {
        if !src.contains(&format!("{v} {{")) && !src.contains(&format!("{v},")) {
            problems.push(format!(
                "DP-Ch16 declares `DurableStreamItem::{v}` and `dp-kernel::channel` does not. A \
                 consumer's `match` is written against the LOCKED shape; removing a variant \
                 nothing constructs yet is a breaking change deferred, not avoided."
            ));
        }
    }

    // DP-Ch16: resume is EXCLUSIVE of the token, and 0 means "from the
    // beginning of retention". Both are in the SQL, and both are the kind of
    // off-by-one that a test with a single event cannot see.
    if !src.contains("channel_event_id > $3") {
        problems.push(
            "the reader's resume bound is no longer `channel_event_id > $3`. DP-Ch16 says to pass \
             the last successfully-processed id, so an inclusive bound re-delivers an item the \
             consumer already acknowledged."
                .to_string(),
        );
    }
    if !src.contains("ORDER BY channel_event_id") {
        problems.push(
            "the reader no longer orders by `channel_event_id`. DP-A15's per-channel total order \
             is the ONE thing this stream promises; without the ORDER BY, Postgres may return any \
             order and the tests would still pass on small pages."
                .to_string(),
        );
    }

    assert!(problems.is_empty(), "14_durable_subscribe.md:\n  - {}", problems.join("\n  - "));
}

/// `DF-1` — DP-Ch17's Redis live tail is unbuilt, and the register shrinks.
///
/// `dp:events:{reality}:{channel}` is DP-Ch16's *"default subscribe path"* and
/// appears in four documents and no source file. The day it appears, this reds
/// and `DF-1` must be re-decided rather than inherited.
#[test]
fn dp_ch17_live_tail_is_still_unbuilt_and_the_doc_still_calls_postgres_canonical() {
    let spec = doc("14_durable_subscribe.md");

    // DF-1 rests on this: the tail is best-effort, the DB is canonical. If
    // DP-Ch17 is amended to make Redis authoritative, the fork's reasoning is
    // gone and the reader is pointed at the wrong store.
    assert!(
        spec.contains("stream is best-effort live;") || spec.contains("DB is canonical"),
        "14_durable_subscribe.md no longer says the Redis tail is best-effort and the DB \
         canonical — DF-1 chose the Postgres tier on that sentence"
    );

    let mut producers: Vec<String> = Vec::new();
    let mut seen = 0usize;
    for root in ["crates", "services"] {
        let mut stack = vec![PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(root)];
        while let Some(d) = stack.pop() {
            let Ok(entries) = fs::read_dir(&d) else { continue };
            for e in entries.flatten() {
                let p = e.path();
                if p.is_dir() {
                    let n = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if n != "target" && n != "node_modules" {
                        stack.push(p);
                    }
                } else if p.extension().is_some_and(|x| x == "rs") {
                    seen += 1;
                    // THIS FILE names the stream key in order to search for it,
                    // so it matches itself — and it did, on the first run. A
                    // gate must never be its own witness. (Comment-stripping is
                    // not enough here: the key is in a string literal, which is
                    // `TL-STRING-PRODUCER`'s shape seen from the other side.)
                    if p.ends_with("spec_oracle_channels.rs") {
                        continue;
                    }
                    let Ok(src) = fs::read_to_string(&p) else { continue };
                    let code: String = src
                        .lines()
                        .filter(|l| !l.trim_start().starts_with("//"))
                        .collect::<Vec<_>>()
                        .join("\n");
                    if code.contains("dp:events:") {
                        producers.push(p.display().to_string());
                    }
                }
            }
        }
    }
    assert!(
        seen > 200,
        "the source walk found only {seen} .rs file(s) — pointed at nothing, and the arm below \
         would report clean forever"
    );
    assert!(
        producers.is_empty(),
        "DP-Ch17's Redis stream `dp:events:*` now exists in {producers:?}. DF-1 deferred the live \
         tail BECAUSE it did not — re-decide the fork, and make DP-Ch21 step 8 true while you are \
         there (DS-CH21-STEP8)."
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// TWENTY channel invariants — SPECIFIED, NOT BUILT.
// Ch3 Ch8 Ch10 Ch14 Ch19 Ch25 Ch27 Ch29 Ch30 Ch36 Ch39 Ch40 Ch43 Ch44 Ch45
// Ch46 Ch47 Ch48 Ch49 Ch50.
//
// Twenty channel invariants whose named primitive does not exist in this repo. An
// invariant with no subject cannot be violated and cannot be guarded; recording
// that is the honest classification, and recording it as PROSE is what this
// project has been burned by. So each row names the SYMBOL, and the test asserts
// it is still absent — the row reds the day the primitive arrives, which is
// precisely the day the rule becomes violable and needs a real guard.
//
// `route_to_writer` earns a note: it occurs exactly once in the tree, inside
// `spec_oracle_rules.rs`, which counts it at zero. A subject check that merely
// grepped would read that mention as the primitive existing, and retire the row
// for the opposite of its reason. Excluding test paths is what prevents that.
const CHANNEL_SPECIFIED_NOT_BUILT: &[(&str, &str, &str)] = &[
    (
        "DP-Ch30",
        "RedactionFilter",
        "privacy + redaction patterns for bubble-up. The visibility flag it reads is set at channel creation via DP-Ch8, which is itself unbuilt.",
    ),
    (
        "DP-Ch36",
        "channel_pause",
        "pause + lifecycle composition. Every occurrence of the symbol in this tree is a comment recording that DP-Ch35's pause is unbuilt; there is no code.",
    ),
    (
        "DP-Ch39",
        "wait_for_token",
        "wait_for_token semantics + projection-apply checkpoint. The symbol occurs 0 times; DEFERRED_READ_FORMS records the related wait_for as not built.",
    ),
    (
        "DP-Ch40",
        "causality_timeout",
        "extending the read primitives with a wait_for parameter. read.rs states the reason it is absent: taking the parameter and ignoring it would be worse than omitting it.",
    ),
    (
        "DP-Ch43",
        "RedactionPolicy",
        "the RedactionPolicy enum and its templates. 0 occurrences; the generator matched the bare word Transparent in an ai-gateway README.",
    ),
    (
        "DP-Ch44",
        "RedactionPolicy",
        "application semantics for redaction in the runtime loop. It cannot exist before the policy type in DP-Ch43 does.",
    ),
    (
        "DP-Ch45",
        "RedactionPolicy",
        "redaction audit, observability and the cascading visibility rule. Same subject as DP-Ch43; all three retire together.",
    ),
    (
        "DP-Ch46",
        "histogram_buckets",
        "histogram bucket layouts for DP telemetry. No bucket layout is declared anywhere in the tree.",
    ),
    (
        "DP-Ch47",
        "metric_labels",
        "telemetry cardinality control — which labels a DP metric may carry. There is no DP metrics module to carry them.",
    ),
    (
        "DP-Ch48",
        "signing_key_rotation",
        "capability signing key rotation policy. CapabilityToken exists; nothing rotates the key that signs it.",
    ),
    (
        "DP-Ch49",
        "fan_out_batch",
        "subscription fan-out batching. 0 occurrences; DP-Ch17's single-subscriber delivery is what shipped.",
    ),
    (
        "DP-Ch50",
        "channel_retention",
        "per-channel-level retention (cell 30d, tavern 1y, town+ 1y). The events tables have a general retention worker; nothing reads a per-level policy.",
    ),
    (
        "DP-Ch3",
        "channel_tree",
        "the control plane's cached snapshot of a reality's channel tree, for fast bind_session and ancestor resolution. bind_session shipped; the cache did not.",
    ),
    (
        "DP-Ch10",
        "channel_changes",
        "channel-tree-change invalidation via the Redis stream dp:channel_changes:{reality_id}. The stream name occurs nowhere in the tree.",
    ),
    (
        "DP-Ch27",
        "channel_event_rng",
        "a deterministic RNG seeded from (channel_id, channel_event_id), handed to BubbleUpAggregator::on_event. It cannot exist before DP-Ch25 does; game-rules' DetRng is a different RNG for a different purpose.",
    ),
    (
        "DP-Ch8",
        "channel_create",
        "channel CRUD primitives. The document gives their signatures; the SDK exports none. Retires when a channel_create/channel_delete door appears.",
    ),
    (
        "DP-Ch14",
        "route_to_writer",
        "cross-node write routing. The rule routes a write to the owning node's writer; there is no router. Retires when the symbol appears outside a test.",
    ),
    (
        "DP-Ch19",
        "subscribe_many",
        "multi-channel batch subscribe, a convenience over DP-Ch17's single-channel form. The single form shipped; this did not.",
    ),
    (
        "DP-Ch25",
        "BubbleUpAggregator",
        "the aggregator trait plus register/unregister. Its document specifies the whole surface and no Rust names it.",
    ),
    (
        "DP-Ch29",
        "BubbleUpAggregator",
        "cascading + recursive bubble-up, a PROPERTY of the DP-Ch25 aggregator. It cannot exist before its subject; both rows retire together.",
    ),
];

/// Collect `.rs` files under `dir`, skipping build output.
fn snb_rs_files(dir: &std::path::Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else { return };
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            let n = p.file_name().unwrap_or_default().to_string_lossy().to_string();
            if n != "target" && n != "node_modules" {
                snb_rs_files(&p, out);
            }
        } else if p.extension().map(|x| x == "rs").unwrap_or(false) {
            out.push(p);
        }
    }
}

/// Every `CHANNEL_SPECIFIED_NOT_BUILT` subject must still be absent.
///
/// **An asserted trigger, not a note.** A row whose symbol has arrived is a rule
/// that became violable while its register still said it could not be — exactly
/// the state this repo has shipped as prose and then cited as an open blocker
/// after it was no longer true.
#[test]
fn channel_primitives_specified_but_not_built_are_still_absent() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut files: Vec<PathBuf> = Vec::new();
    for dir in ["crates", "services"] {
        snb_rs_files(&root.join(dir), &mut files);
    }

    // REACH FLOOR on the walk itself: zero files read means every row "passes"
    // for a reason that has nothing to do with the rules.
    assert!(
        files.len() >= 200,
        "the subject walk reached only {} .rs file(s); a walk that reads nothing \
         reports every specified-not-built row as still absent",
        files.len()
    );

    let mut arrived: Vec<String> = Vec::new();
    for (id, symbol, why) in CHANNEL_SPECIFIED_NOT_BUILT {
        let mut hits: Vec<String> = Vec::new();
        for f in &files {
            let p = f.to_string_lossy().replace('\\', "/");
            if p.contains("/tests/") || p.contains("/target/") {
                continue;
            }
            let Ok(text) = fs::read_to_string(f) else { continue };
            // CODE ONLY. `channel_pause` appears in a doc comment reading
            // "blocking is channel_pause's job (DP-Ch35), unbuilt" — a sentence
            // recording that the thing does NOT exist. Counting it as existence
            // would retire the row by quoting its own reason back at it.
            //
            // Note this is the OPPOSITE of the coverage gate's rule, on purpose:
            // there the question is "can I grep this id to its guard", and a
            // comment beside the guard is the answer. Here the question is "does
            // this primitive exist", and only code answers that.
            let code: String = text
                .lines()
                .map(|l| match l.find("//") {
                    Some(i) => &l[..i],
                    None => l,
                })
                .collect::<Vec<_>>()
                .join("\n");
            let found = code
                .split(|c: char| !c.is_alphanumeric() && c != '_')
                .any(|w| w == *symbol);
            if found {
                hits.push(p);
            }
        }
        if !hits.is_empty() {
            arrived.push(format!(
                "{id}: `{symbol}` has ARRIVED ({}). The invariant is now violable and this row is \
                 stale — give {id} a real guard and delete the row. Reason was: {why}",
                hits[..hits.len().min(2)].join(", ")
            ));
        }
    }

    assert!(
        arrived.is_empty(),
        "specified-not-built rows whose subject now exists:\n  {}",
        arrived.join("\n  ")
    );

    // The floor was a COUNT, and a count cannot see a NEUTERED row. Renaming a
    // symbol to something that matches nothing leaves the length at five and
    // kills that row's trigger in silence — measured by the bite that found it.
    // The ids are asserted as a SET, and each row's shape is checked, so a
    // deletion, a rename and a blanked symbol all red.
    let ids: std::collections::BTreeSet<&str> =
        CHANNEL_SPECIFIED_NOT_BUILT.iter().map(|(i, _, _)| *i).collect();
    let want: std::collections::BTreeSet<&str> =
        ["DP-Ch3", "DP-Ch8", "DP-Ch10", "DP-Ch14", "DP-Ch19", "DP-Ch25", "DP-Ch27",
         "DP-Ch29", "DP-Ch30", "DP-Ch36", "DP-Ch39", "DP-Ch40", "DP-Ch43", "DP-Ch44",
         "DP-Ch45", "DP-Ch46", "DP-Ch47", "DP-Ch48", "DP-Ch49", "DP-Ch50"]
            .into_iter().collect();
    assert_eq!(
        ids, want,
        "the specified-not-built register no longer covers exactly the twenty channel \
         invariants it was written for. Reading each subject killed every BUILT a candidate \
         generator offered across docs 16-20. A row leaves ONLY when its subject ARRIVES, and \
         that path asserts above — so any other change here is one nobody justified"
    );

    for (id, symbol, why) in CHANNEL_SPECIFIED_NOT_BUILT {
        assert!(
            symbol.len() >= 3 && symbol.chars().all(|c| c.is_alphanumeric() || c == '_'),
            "{id}: `{symbol}` is not a searchable identifier, so its trigger can never fire"
        );
        assert!(
            why.len() >= 40,
            "{id}: the reason is {} chars. A row without a reason is the prose this register \
             replaces",
            why.len()
        );
    }
}
