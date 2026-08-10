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
//! # The finding this file shipped with
//!
//! `DP-Ch11`'s schema block declares **five** columns on `events`. The shipped
//! migration adds **four**: `turn_number` is specified by a LOCKED document and
//! created by no migration in this repo, measured rather than assumed. It gets
//! a [`DEFERRED_EVENT_COLUMNS`] row naming what it waits on, and the row fails
//! the day a migration adds the column — which is the whole difference between
//! a register and a comment.

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
const DEFERRED_EVENT_COLUMNS: &[(&str, &str)] = &[(
    "turn_number",
    "DP-A17 / DP-Ch22's per-channel turn counter — 15_turn_boundary.md's turn machinery has no \
     implementation and nothing would advance the counter, so the column would be a NOT NULL \
     DEFAULT 0 that never moves",
)];

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

    for col in &declared {
        let is_shipped = shipped.iter().any(|s| s == col);
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
