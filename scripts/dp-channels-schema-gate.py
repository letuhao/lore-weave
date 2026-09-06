#!/usr/bin/env python3
"""dp-channels-schema-gate — `1b.3`, the `V.2` oracle for the channel registry.

**Spec and code are BOTH SQL here, which is rare and worth exploiting.**

`FLOW-2` is this project's recurring defect: a correction decided, applied where
the author was looking, and not applied where they were not. It has now been
measured five times in this corpus, and `REC-103` is the sharpest instance —
`REC-102a` ruled `ChannelId` to be `i64`, that ruling reached the newtype and the
Rust code in the same commit, and it **never reached the schema thirty lines
below it**. The one artifact a migration would be written from still declared
`UUID`, and nothing said so for the eight weeks in between.

WHAT `1b.5` FOUND ABOUT THE FIRST VERSION OF THIS GATE
-----------------------------------------------------
Three findings, and all three are the same defect — *a check that reads a PROXY
for its subject*:

  * `1b5-H1` — **the gate read ONE file.** `REC-103`/`REC-105` reached
    `12_channel_primitives.md` and **not** `13_channel_ordering_and_writer.md:209`,
    `16_bubble_up_aggregator.md:339`, or the second locked `ALTER TABLE channels`
    in `17_channel_lifecycle.md:63`. *The gate built to stop `FLOW-2` was scoped
    to the one file where `FLOW-2` did not happen this time.* It now scans every
    `.md` in `06_data_plane/`, so a file created tomorrow is covered by default
    rather than by an author remembering to add it (`NV-3`).

  * `1b5-H4` — **the gate was blind to `PRIMARY KEY`, `NOT NULL`, `DEFAULT`, the
    bodies of foreign keys, and every index but one.** A four-way mutant —
    `ON DELETE CASCADE`, `level_name` losing `NOT NULL`, `metadata` losing its
    `DEFAULT`, an extra `UNIQUE` — applied cleanly and the gate said OK. The
    primary key is `REC-105`'s ENTIRE SUBJECT and the gate did not look at it.
    It now parses the table structurally instead of line by line.

  * `1b5-M5` — **the gate cried wolf on formatting.** Lowercasing a type, or
    deleting one space in `ON channels (reality_id)`, reddened it — and the
    no-space form is what the spec itself used for its other three indexes. A
    gate that reds on a normalisation is a gate that gets switched off within a
    day. Everything is normalised before comparison: keyword and type case,
    whitespace, `IF NOT EXISTS`, and the space before `(`.

WHAT IT COMPARES
----------------
  * every column: NAME, TYPE, `NOT NULL`, `DEFAULT`, `GENERATED ... STORED`
  * the `PRIMARY KEY` column list
  * every named constraint, and for `FOREIGN KEY`/`UNIQUE` its full body —
    columns, referenced table and columns, referential actions, deferrability
  * every index: name, uniqueness, table, column list, and partial predicate
  * the `DP-Ch31`/`DP-Ch33` lifecycle trigger's name and firing event
  * across ALL of `06_data_plane/`: every `REFERENCES channels (...)` agrees with
    the shipped key, and every `ALTER TABLE channels` is either in the migration
    or in `PENDING_ALTERS` below

WHAT IT DOES NOT COMPARE, AND WHY
---------------------------------
`CHECK` bodies and the trigger's plpgsql body. `(depth >= 0 AND depth <= 16)` and
`(depth BETWEEN 0 AND 16)` are the same predicate and different text, and a
comparison that called them different would cry wolf until someone switched it
off — which is `1b5-M5` arriving through the other door. **Stated rather than
glossed:** a constraint can be present on both sides under one name and mean two
things, and this gate would not know. Closing that needs the live smoke
(`scripts/dp-channels-live-smoke.py`), which asks each constraint to actually
reject a row — which is why that script exists and why `1b` does not close
without it.

Run: ``python scripts/dp-channels-schema-gate.py`` — wired pre-commit.
Exit 0 = they agree; 1 = they do not; 2 = one of them could not be parsed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DP_DOCS = REPO / "docs/03_planning/LLM_MMO_RPG/06_data_plane"
SPEC = DP_DOCS / "12_channel_primitives.md"
MIGRATION = REPO / "contracts/migrations/per_reality/0019_channels.up.sql"

# The shipped key of `channels`. Every `REFERENCES channels (...)` in the tier's
# documents must name one of these, or it is `REC-105`'s defect somewhere new.
#
#   (reality_id, id)        — the primary key. What ANY other table references.
#   (reality_id, id, depth) — `channels_parent_fk`'s own target (`REC-106`). It
#                             carries `depth` so that a cycle is unrepresentable,
#                             and `channels_id_depth_uq` exists to be it.
#
# A closed set rather than a prefix rule, deliberately: a fourth form arriving is
# a decision someone should have to make on purpose, not a shape that slips
# through because it happened to start with the right two columns.
CHANNELS_KEYS = {("REALITY_ID", "ID"), ("REALITY_ID", "ID", "DEPTH")}

# ---------------------------------------------------------------------------
# `1b5-H1` · the PENDING register.
#
# `17_channel_lifecycle.md:63` holds a SECOND locked `ALTER TABLE channels` whose
# five columns have no writer and no reader anywhere in the tree. Migrating them
# would be apparatus with no subject. Ignoring them is how `FLOW-2` happens. So
# they are named here, and the register is built to SHRINK: if one of these
# appears in the migration, this gate REDS until the row is retired.
# ---------------------------------------------------------------------------
PENDING_ALTERS = {
    "17_channel_lifecycle.md": {
        "columns": {
            "PAUSED_UNTIL", "PAUSED_REASON", "PAUSED_BY",
            "BECAME_DORMANT_AT", "DISSOLVED_AT_EID",
        },
        "constraints": {"CHANNELS_PAUSE_ACTIVE_ONLY"},
        "trigger": "the first DP-Ch32 auto-dormant scheduler or pause_channel caller",
    },
}

# The lifecycle rules `DP-Ch31`/`DP-Ch33`/`DP-Ch34` state and no CHECK can
# express, because all three are about a TRANSITION. `1b5-L5`, widened to INSERT
# by `1b7gap-H3` — an `UPDATE OF lifecycle` trigger does not fire on an INSERT,
# nor when only `parent` changes, and both were live holes.
#
# TWO triggers, not one, and the second one's SHAPE is load-bearing: a
# `BEFORE`-row check of DP-Ch33 makes a one-statement subtree dissolve impossible
# in every row order (`1b7db-07`), because a BEFORE-row trigger cannot see the
# other rows its own command is updating. Only a CONSTRAINT trigger, which fires
# at end-of-statement, can express "no live child" over a multi-row UPDATE. So
# the timing is compared, not just the name — downgrading it to `BEFORE` would
# silently re-break the operation.
EXPECT_TRIGGERS = {
    "CHANNELS_LIFECYCLE_GUARD_TRG": "BEFORE INSERT OR UPDATE ON CHANNELS",
    # `INSERT` is load-bearing (`1b12-01`): an `AFTER UPDATE`-only trigger never
    # fires on a row written already-dissolved, which let the reverse-insert
    # order smuggle a dissolved parent in under a live child.
    "CHANNELS_DISSOLVE_ORDER_TRG":
        "AFTER INSERT OR UPDATE OF LIFECYCLE ON CHANNELS DEFERRABLE INITIALLY IMMEDIATE",
}

# ---------------------------------------------------------------------------
# `1b7gap-M3`/`M4` · the scan's blast radius.
#
# The first cross-file scan read ONLY ```sql fences and ONLY two patterns, and a
# cold-start refuter found FOUR more sites still declaring `UUID` after
# `REC-103` — two of them within 200 lines of blocks this very gate's commit
# amended, one in a ```rust fence, one in an unlabelled fence in the file the
# gate parses as schema authority. `1b5-H1` said "one of FOUR locked SQL sites";
# there are at least EIGHT.
#
# So: every fence of every language, AND the prose between them. A declaration
# does not become invisible by being written in a sentence — `13:209`'s form is
# exactly what prose looks like.
#
# THE ESCAPE HATCH AND ITS REASON. An "⚠ AMENDED" block legitimately QUOTES the
# old wrong form in order to explain the correction, and a gate that cannot tell
# a quotation from a declaration would make every fix unshippable. A line may
# carry `schema-gate: ok — <reason>` on itself or up to 3 lines above. `NV`'s
# fourth shape is *"the escape hatch cannot reach its reason"*, so the reason is
# REQUIRED: a bare marker with nothing after the dash does not exempt anything.
_SQLISH = {"sql", "postgresql", "postgres", "psql", "plpgsql", ""}
_EXEMPT = re.compile(r"schema-gate:\s*ok\s*[—\-]\s*(\S.*)$")
_EXEMPT_WINDOW = 3
# Declarations that contradict `REC-103` (`ChannelId` is `i64`, so the column is
# BIGINT). Deliberately narrow patterns: a false positive here is a gate that
# gets switched off, which is `1b5-M5`.
_UUID_FORMS = [
    (re.compile(r"\bchannel_id\s+UUID\b", re.I), "`channel_id UUID` — REC-103 settled ChannelId as i64, so the column is BIGINT"),
    (re.compile(r"\bparent_channel\s+UUID\b", re.I), "`parent_channel UUID` — REC-103 settled ChannelId as i64, so the column is BIGINT"),
    (re.compile(r"\bchannel_id\b[^\n]{0,20}as_uuid\(\)", re.I), "`channel_id.as_uuid()` — ChannelId has no UUID payload; `grep as_uuid crates/` finds nothing"),
    (re.compile(r'"(?:channel_id|parent)"\s*:\s*"<\s*uuid', re.I), "a wire shape typing a channel id as `<uuid>` — REC-103"),
]

_TYPE_ALIASES = {
    "INT8": "BIGINT", "INT4": "INTEGER", "INT": "INTEGER", "INT2": "SMALLINT",
    "BOOL": "BOOLEAN", "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
    "CHARACTER VARYING": "VARCHAR",
}
_COL_STOP = {"NOT", "NULL", "DEFAULT", "GENERATED", "PRIMARY", "UNIQUE",
             "REFERENCES", "CHECK", "COLLATE", "CONSTRAINT"}
_ITEM_KEYWORDS = {"CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "EXCLUDE"}


def strip_sql_comments(text: str) -> str:
    """Drop `--` comments, without eating a `--` inside a string literal."""
    out = []
    for line in text.splitlines():
        res, i, in_str = [], 0, False
        while i < len(line):
            ch = line[i]
            if ch == "'":
                in_str = not in_str
            if not in_str and ch == "-" and line[i:i + 2] == "--":
                break
            res.append(ch)
            i += 1
        out.append("".join(res))
    return "\n".join(out)


def norm(sql: str) -> str:
    """`1b5-M5`: case, whitespace and `IF NOT EXISTS` are not schema facts.

    Uppercases outside single-quoted literals, collapses runs of whitespace, and
    removes the space before `(` so `channels (a)` and `channels(a)` are one
    string. Literals keep their case: `'active'` is a VALUE.
    """
    res, in_str = [], False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
            res.append(ch)
        else:
            res.append(ch if in_str else ch.upper())
    s = "".join(res)
    s = re.sub(r"\bIF NOT EXISTS\b", " ", s)
    s = re.sub(r"\bOR REPLACE\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+\(", "(", s)
    return s


def _norm_type(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return _TYPE_ALIASES.get(t, t)


def split_top_level(body: str) -> list[str]:
    depth, in_str, cur, out = 0, False, [], []
    for ch in body:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def _cols(paren: str) -> list[str]:
    return [c.strip() for c in split_top_level(paren.strip()) if c.strip()]


def _extract_table(text: str, who: str) -> str:
    m = re.search(r"CREATE TABLE(?: IF NOT EXISTS)? CHANNELS\((.*?)\);",
                  norm(strip_sql_comments(sql_only(text))), re.S)
    if not m:
        print(f"dp-channels-schema-gate: MISUSE — no `CREATE TABLE channels (..)` in {who}. "
              f"The parse found nothing, and a comparison against nothing agrees with anything.",
              file=sys.stderr)
        sys.exit(2)
    return m.group(1)


def parse_table(text: str, who: str) -> dict:
    """Structural, not line-shaped. `1b5-H4` is what line-shaped cost."""
    body = _extract_table(text, who)
    columns, constraints, pk = [], {}, []

    for item in split_top_level(body):
        head = item.split("(")[0].split()
        if not head:
            continue
        kw = head[0]

        if kw == "PRIMARY":
            pk = _cols(re.search(r"\((.*)\)", item, re.S).group(1))
            continue
        if kw in _ITEM_KEYWORDS:
            if kw == "CONSTRAINT":
                name = head[1]
                rest = item[item.index(name) + len(name):].strip()
            else:                       # an UNNAMED table constraint
                name, rest = f"<unnamed {kw}>", item
            constraints[name] = _parse_constraint(rest)
            continue

        # a column
        toks = item.split()
        name = toks[0]
        ty, i = [], 1
        while i < len(toks) and toks[i] not in _COL_STOP:
            ty.append(toks[i])
            i += 1
            if ty and ty[-1].endswith(")"):
                break
        rest = " ".join(toks[i:])
        gen = re.search(r"GENERATED ALWAYS AS\((.*)\) STORED", rest, re.S)
        dfl = re.search(r"\bDEFAULT (.+?)(?=\s+(?:NOT NULL|NULL|CHECK|REFERENCES|"
                        r"GENERATED|UNIQUE|PRIMARY|COLLATE)\b|$)", rest, re.S)
        columns.append({
            "name": name,
            "type": _norm_type(" ".join(ty)),
            "not_null": bool(re.search(r"\bNOT NULL\b", rest)),
            "default": dfl.group(1).strip() if dfl else None,
            "generated": re.sub(r"\s+", " ", gen.group(1)).strip() if gen else None,
        })

    return {"columns": columns, "pk": pk, "constraints": constraints}


def _parse_constraint(rest: str) -> tuple:
    """CHECK bodies are deliberately not compared — see the module docstring."""
    if rest.startswith("FOREIGN KEY"):
        m = re.match(r"FOREIGN KEY\((.*?)\) REFERENCES (\w+)\((.*?)\)(.*)$", rest, re.S)
        if not m:
            return ("FOREIGN KEY", "UNPARSED", rest)
        tail = m.group(4).strip()
        actions = tuple(sorted(re.findall(r"ON (?:DELETE|UPDATE) (?:NO ACTION|RESTRICT|"
                                          r"CASCADE|SET NULL|SET DEFAULT)", tail)))
        deferrable = "DEFERRABLE" in tail and "NOT DEFERRABLE" not in tail
        initially = "DEFERRED" if re.search(r"INITIALLY DEFERRED", tail) else "IMMEDIATE"
        return ("FOREIGN KEY", tuple(_cols(m.group(1))), m.group(2),
                tuple(_cols(m.group(3))), actions, deferrable, initially)
    if rest.startswith("UNIQUE"):
        return ("UNIQUE", tuple(_cols(re.search(r"\((.*)\)", rest, re.S).group(1))))
    if rest.startswith("CHECK"):
        return ("CHECK",)
    return ("OTHER", rest)


def parse_indexes(text: str) -> dict:
    out = {}
    pat = re.compile(
        r"CREATE (UNIQUE )?INDEX(?: IF NOT EXISTS)? (\w+) ON (\w+)\((.*?)\)"
        r"(?: WHERE (.*?))?;", re.S)
    for m in pat.finditer(norm(strip_sql_comments(sql_only(text)))):
        out[m.group(2)] = (bool(m.group(1)), m.group(3), tuple(_cols(m.group(4))),
                           re.sub(r"\s+", " ", m.group(5)).strip() if m.group(5) else None)
    return out


def parse_triggers(text: str) -> dict[str, str]:
    """Every trigger, with its full timing clause — not just the first one.

    `re.search` returned ONE, which is how a second trigger could have been added
    on one side and not the other without a word. Same defect class as
    `_extract_table` taking the first `CREATE TABLE` (`1b7gap-M4`).
    """
    out = {}
    pat = re.compile(r"CREATE(?: OR REPLACE)?(?: CONSTRAINT)? TRIGGER (\w+)\s+(.*?)"
                     r"\s+(?:WHEN\s*\(.*?\)\s+)?(?:FOR EACH ROW|EXECUTE)", re.S)
    for m in pat.finditer(norm(strip_sql_comments(sql_only(text)))):
        out[m.group(1)] = re.sub(r"\s+FOR EACH ROW$", "", m.group(2).strip())
    return out


# ---------------------------------------------------------------------------
# `1b5-H1` · the cross-file scan
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"```sql\n(.*?)```", re.S)


def sql_blocks(md: str) -> str:
    return "\n".join(_FENCE.findall(md))


def sql_only(text: str) -> str:
    """A markdown file is PROSE with SQL in it, and the prose is hostile input.

    Found while wiring `1b5-L5`: `parse_trigger` was reading the whole document,
    and English prose contains apostrophes — ``DP-Ch1`'s`` is one. `norm()`
    tracks single-quoted literals so that `'active'` keeps its case, so ONE
    unbalanced apostrophe in a sentence puts the rest of the file inside a string
    literal and silently stops normalising it. The gate then reported a
    case-difference as a schema disagreement, which is `1b5-M5` wearing a
    different coat. Parse the fences, never the file.
    """
    return sql_blocks(text) if "```sql" in text else text


def flow19_trigger(writers: set[str] | None = None,
                   fk_declared: bool | None = None) -> list[str]:
    """`1b7gap-H4` — `FLOW-19` gets a MECHANISM instead of four sentences.

    `FLOW-19` is *"`channel_writer_state.channel_id` has no foreign key to
    `channels`"*. It was called discharged in two artifacts, still-open in two
    others, and **`FLOW-*` appears nowhere in `scripts/deferral-gate.py`** — 30
    tracked ids, all `D-*`. Nothing would have noticed if the key never landed.

    It cannot land TODAY and the reason is measurable rather than rhetorical
    (`1b.9`): `dp-kernel::acquire_writer_lease` INSERTs into
    `channel_writer_state` on every lease acquisition, and **nothing anywhere
    writes `channels`**. Adding the key now would make every lease acquisition
    fail against an empty table.

    So this is the trigger, not the fix: **the moment `channels` gains a
    non-test writer, this reds** and the key becomes owed. An asserted trigger
    that fires when its subject arrives is the shape `deferral-gate` accepts as
    mechanical, and it is the shape a prose row is not.
    """
    if writers is None:
        writers = set()
        for root in ("crates", "services"):
            base = REPO / root
            if not base.is_dir():
                continue
            for p in base.rglob("*.rs"):
                rel = p.relative_to(REPO).as_posix()
                if "/tests/" in rel or "/benches/" in rel or p.name.startswith("test_"):
                    continue
                try:
                    body = p.read_bytes().decode("utf-8", "replace")
                except OSError:
                    continue
                # Only a WRITE counts. A read cannot violate referential
                # integrity, and counting reads would red on the first consumer.
                if re.search(r"(?i)\b(INSERT\s+INTO|UPDATE)\s+channels\b", body):
                    writers.add(rel)
    if fk_declared is None:
        fk_declared = any(
            re.search(r"(?is)ALTER\s+TABLE\s+channel_writer_state.*?REFERENCES\s+channels",
                      p.read_bytes().decode("utf-8", "replace"))
            or re.search(r"(?is)CREATE\s+TABLE[^;]*channel_writer_state.*?REFERENCES\s+channels",
                         p.read_bytes().decode("utf-8", "replace"))
            for p in (REPO / "contracts/migrations/per_reality").glob("*.up.sql"))

    if writers and not fk_declared:
        return [f"FLOW-19 is now OWED. `channels` has {len(writers)} non-test writer(s) "
                f"({sorted(writers)[:3]}), so the foreign key "
                f"`channel_writer_state (reality_id, channel_id) -> channels (reality_id, id)` "
                f"is no longer blocked by an empty table — the reason 1b.9 recorded for NOT "
                f"adding it has expired. Add the key in a new migration, or record a new "
                f"reason here."]
    return []


def tier_docs() -> list[tuple[str, str]]:
    """Every `.md` in the tier — a GLOB, not a list. `NV-3`: an enumerated file
    set is default-uncovered, and `1b5-H1` is what that cost."""
    return [(p.name, p.read_bytes().decode("utf-8")) for p in sorted(DP_DOCS.glob("*.md"))]


def exempt_at(lines: list[str], i: int) -> str | None:
    """`schema-gate: ok — <reason>` on this line or up to 3 above.

    A window rather than the line alone, because the marker usually belongs to a
    prose sentence introducing the quoted form. A window that is a FIXED single
    line is `NV`'s fourth shape and shipped three times in sibling gates here.
    """
    for j in range(max(0, i - _EXEMPT_WINDOW), i + 1):
        m = _EXEMPT.search(lines[j])
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def scan_line_regions(text: str) -> list[tuple[int, str]]:
    """(line_no, line) for every region a DECLARATION could hide in.

    Every fence whose language is SQL-ish or unlabelled, plus the prose between
    fences. Non-SQL fences (```rust, ```json) are included too — `1b7gap-M3`
    found `channel_id.as_uuid()` in a ```rust fence and a `"<uuid>"` wire shape
    in an unlabelled one, and both are declarations of the same fact.
    """
    out, fence_lang = [], None
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^```(\w*)", line.strip())
        if m:
            fence_lang = None if fence_lang is not None else m.group(1).lower()
            continue
        out.append((i, line))
    return out


def scan_tier_docs(migration_cols: set[str], migration_cons: set[str],
                   docs: list[tuple[str, str]] | None = None) -> list[str]:
    findings = []
    seen_alter_files = set()
    for name_, text_ in (tier_docs() if docs is None else docs):
        doc = type("D", (), {"name": name_})

        # `1b7gap-M3` — REC-103 violations, anywhere in the document, line by
        # line so the finding can point at one and an exemption can reach one.
        lines = text_.splitlines()
        for lineno, line in scan_line_regions(text_):
            # A COMMENT cannot declare a column type, and every amendment note in
            # this corpus quotes the form it is correcting — that is what makes
            # the correction legible. Skipping comments is not a loophole: a
            # commented-out declaration declares nothing. Bitten by un-amending
            # each of the four real sites and requiring the gate to red, which is
            # the only thing that shows the skip did not swallow the subject.
            if re.match(r"\s*(--|#|//|<!--|\*)", line):
                continue
            for pat, why in _UUID_FORMS:
                if pat.search(line):
                    reason = exempt_at(lines, lineno - 1)
                    if reason is None:
                        findings.append(f"{name_}:{lineno}: {why}. If this line QUOTES the old "
                                        f"form to explain a correction, mark it "
                                        f"`schema-gate: ok — <reason>`.")

        # `1b7gap-M4` — a SECOND `CREATE TABLE channels` is silently ignored by
        # `_extract_table`, which uses `re.search`: the first block wins and a
        # contradicting one anywhere else is invisible.
        creates = [(n, l) for n, l in scan_line_regions(text_)
                   if re.search(r"CREATE TABLE(?: IF NOT EXISTS)? channels\b", l, re.I)]
        if name_ == SPEC.name and len(creates) > 1:
            findings.append(f"{name_}: {len(creates)} `CREATE TABLE channels` blocks at lines "
                            f"{[n for n, _ in creates]}. `_extract_table` takes the FIRST and "
                            f"ignores the rest, so a contradicting one is invisible.")
        elif name_ != SPEC.name and creates:
            findings.append(f"{name_}:{creates[0][0]}: a `CREATE TABLE channels` outside "
                            f"{SPEC.name}, which is the one document this gate treats as schema "
                            f"authority. Two homes for one schema is FLOW-2 by construction.")

        sql = norm(strip_sql_comments(sql_blocks(text_)))

        for m in re.finditer(r"REFERENCES CHANNELS\((.*?)\)", sql, re.S):
            cols = tuple(_cols(m.group(1)))
            if cols not in CHANNELS_KEYS:
                allowed = " or ".join("(" + ", ".join(k).lower() + ")"
                                      for k in sorted(CHANNELS_KEYS))
                findings.append(
                    f"{doc.name}: `REFERENCES channels({', '.join(c.lower() for c in cols)})` — "
                    f"the shipped key is {allowed}. REC-103/REC-105 reached the migration and not "
                    f"this file, which is FLOW-2.")

        for m in re.finditer(r"ALTER TABLE CHANNELS\b(.*?);", sql, re.S):
            seen_alter_files.add(doc.name)
            reg = PENDING_ALTERS.get(doc.name)
            body = m.group(1)
            cols = set(re.findall(r"ADD COLUMN(?: IF NOT EXISTS)? (\w+)", body))
            cons = set(re.findall(r"ADD CONSTRAINT (\w+)", body))
            if reg is None:
                findings.append(
                    f"{doc.name}: an `ALTER TABLE channels` this gate has never been told about "
                    f"(columns {sorted(cols)}, constraints {sorted(cons)}). Either migrate it or "
                    f"add a PENDING_ALTERS row naming what would wake it up.")
                continue
            for extra in sorted(cols - reg["columns"]):
                findings.append(
                    f"{doc.name}: `ALTER TABLE channels` grew column `{extra.lower()}`, which the "
                    f"PENDING_ALTERS register does not name.")
            for extra in sorted(cons - reg["constraints"]):
                findings.append(
                    f"{doc.name}: `ALTER TABLE channels` grew constraint `{extra.lower()}`, which "
                    f"the PENDING_ALTERS register does not name.")

    # The register must SHRINK. A pending item the migration now has is a row to
    # retire, not a row to keep — a stale PENDING entry reads as "still owed".
    for name, reg in PENDING_ALTERS.items():
        if name not in seen_alter_files:
            findings.append(
                f"PENDING_ALTERS names `{name}`, and no `ALTER TABLE channels` was found in it. "
                f"The register is stale — retire the row.")
        for col in sorted(reg["columns"] & migration_cols):
            findings.append(
                f"PENDING_ALTERS still lists column `{col.lower()}` and 0019 now HAS it. "
                f"The register must shrink: retire the entry.")
        for con in sorted(reg["constraints"] & migration_cons):
            findings.append(
                f"PENDING_ALTERS still lists constraint `{con.lower()}` and 0019 now HAS it. "
                f"The register must shrink: retire the entry.")
    return findings


# ---------------------------------------------------------------------------
# self-test — every capability above, bitten in BOTH directions
# ---------------------------------------------------------------------------
_T = """CREATE TABLE channels (
    reality_id UUID NOT NULL,
    id BIGINT NOT NULL,
    parent BIGINT,
    depth SMALLINT NOT NULL,
    level_name TEXT NOT NULL,
    parent_depth SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (reality_id, id),
    CONSTRAINT channels_id_depth_uq UNIQUE (reality_id, id, depth),
    CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent, parent_depth)
        REFERENCES channels (reality_id, id, depth) DEFERRABLE INITIALLY IMMEDIATE,
    CONSTRAINT channels_depth_bounded CHECK (depth >= 0 AND depth <= 16)
);
CREATE UNIQUE INDEX channels_root_single ON channels (reality_id) WHERE parent IS NULL;
"""


def self_test() -> int:
    bad = []

    def t(sql=_T):
        return parse_table(sql, "self-test")

    base = t()

    # --- the parse reads what it claims to read -----------------------------
    if [c["name"] for c in base["columns"]] != ["REALITY_ID", "ID", "PARENT", "DEPTH",
                                                "LEVEL_NAME", "PARENT_DEPTH", "METADATA"]:
        bad.append(f"the column parse is wrong: {[c['name'] for c in base['columns']]}")
    if base["pk"] != ["REALITY_ID", "ID"]:
        bad.append(f"PRIMARY KEY not read — REC-105's whole subject ({base['pk']})")
    fk = base["constraints"].get("CHANNELS_PARENT_FK")
    if fk != ("FOREIGN KEY", ("REALITY_ID", "PARENT", "PARENT_DEPTH"), "CHANNELS",
              ("REALITY_ID", "ID", "DEPTH"), (), True, "IMMEDIATE"):
        bad.append(f"the FOREIGN KEY body is not read: {fk}")
    md = next(c for c in base["columns"] if c["name"] == "METADATA")
    if md["default"] != "'{}'::JSONB" or not md["not_null"]:
        bad.append(f"DEFAULT/NOT NULL not read: {md}")
    pd = next(c for c in base["columns"] if c["name"] == "PARENT_DEPTH")
    if pd["generated"] != "(DEPTH - 1)::SMALLINT":
        bad.append(f"GENERATED expression not read: {pd['generated']}")

    # --- MUTATIONS: each must be VISIBLE (1b5-H4) --------------------------
    mutants = {
        "PRIMARY KEY changed": ("PRIMARY KEY (reality_id, id)", "PRIMARY KEY (id)"),
        "NOT NULL dropped": ("level_name TEXT NOT NULL", "level_name TEXT"),
        "DEFAULT dropped": ("metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
                            "metadata JSONB NOT NULL"),
        "FK gained ON DELETE CASCADE": ("(reality_id, id, depth) DEFERRABLE",
                                        "(reality_id, id, depth) ON DELETE CASCADE DEFERRABLE"),
        "FK lost a key column": ("FOREIGN KEY (reality_id, parent, parent_depth)",
                                 "FOREIGN KEY (reality_id, parent)"),
        "FK target changed": ("REFERENCES channels (reality_id, id, depth)",
                              "REFERENCES channels (reality_id, id)"),
        "deferrability dropped": ("DEFERRABLE INITIALLY IMMEDIATE", "NOT DEFERRABLE"),
        "column TYPE changed (REC-103)": ("id BIGINT NOT NULL", "id UUID NOT NULL"),
        "column NAME changed": ("reality_id UUID", "realm_id UUID"),
        "generated expression changed": ("(depth - 1)::smallint", "(depth + 1)::smallint"),
        "a UNIQUE constraint appeared": ("PRIMARY KEY (reality_id, id),",
                                         "PRIMARY KEY (reality_id, id), "
                                         "CONSTRAINT extra_uq UNIQUE (level_name),"),
    }
    for label, (old, new) in mutants.items():
        if old not in _T:
            bad.append(f"MUTATION ANCHOR MISSING — `{old}` is not in the fixture, so the "
                       f"`{label}` leg tested nothing")
            continue
        if t(_T.replace(old, new, 1)) == base:
            bad.append(f"INVISIBLE mutation: {label}")

    # --- FORMATTING: each must be INVISIBLE (1b5-M5) ------------------------
    formats = {
        "type lowercased": ("id BIGINT NOT NULL", "id bigint NOT NULL"),
        "keyword lowercased": ("PRIMARY KEY (reality_id, id)", "primary key (reality_id, id)"),
        "space before paren removed": ("REFERENCES channels (reality_id, id, depth)",
                                       "REFERENCES channels(reality_id, id, depth)"),
        "IF NOT EXISTS added": ("CREATE TABLE channels", "CREATE TABLE IF NOT EXISTS channels"),
        "indentation changed": ("    id BIGINT NOT NULL", "\t\tid BIGINT NOT NULL"),
        "int8 alias for bigint": ("id BIGINT NOT NULL", "id int8 NOT NULL"),
    }
    for label, (old, new) in formats.items():
        if old not in _T:
            bad.append(f"FORMAT ANCHOR MISSING — `{old}` is not in the fixture")
            continue
        if t(_T.replace(old, new, 1)) != base:
            bad.append(f"CRIES WOLF on formatting: {label}")

    # --- indexes ------------------------------------------------------------
    idx = parse_indexes(_T)
    if idx.get("CHANNELS_ROOT_SINGLE") != (True, "CHANNELS", ("REALITY_ID",), "PARENT IS NULL"):
        bad.append(f"the partial unique index is not read: {idx}")
    if parse_indexes("CONSTRAINT channels_root_single UNIQUE (id)"):
        bad.append("a plain `UNIQUE (id)` reads as REC-104's partial index — REC-104 exactly")
    if parse_indexes(_T.replace("WHERE parent IS NULL", "WHERE parent IS NOT NULL")) == idx:
        bad.append("a changed partial PREDICATE is invisible")
    if parse_indexes(_T.replace("CREATE UNIQUE INDEX", "CREATE INDEX")) == idx:
        bad.append("UNIQUE-ness of an index is invisible")

    # --- the trigger (1b5-L5) ----------------------------------------------
    trg = ("CREATE OR REPLACE TRIGGER channels_lifecycle_guard_trg BEFORE UPDATE OF "
           "lifecycle ON channels FOR EACH ROW EXECUTE FUNCTION f();")
    if parse_triggers(trg) != {"CHANNELS_LIFECYCLE_GUARD_TRG":
                               "BEFORE UPDATE OF LIFECYCLE ON CHANNELS"}:
        bad.append(f"the lifecycle trigger is not read: {parse_triggers(trg)}")
    if parse_triggers(trg.replace("BEFORE UPDATE OF lifecycle", "AFTER UPDATE")) \
            == parse_triggers(trg):
        bad.append("a changed trigger EVENT is invisible — an AFTER trigger cannot refuse")
    # `1b7gap-M4`'s shape again: a SECOND trigger must not be swallowed.
    two = trg + ("\nCREATE CONSTRAINT TRIGGER channels_dissolve_order_trg AFTER UPDATE OF "
                 "lifecycle ON channels DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
                 "WHEN (NEW.lifecycle = 'dissolved') EXECUTE FUNCTION g();")
    if len(parse_triggers(two)) != 2:
        bad.append(f"a SECOND trigger is invisible — re.search took the first: "
                   f"{parse_triggers(two)}")
    if "DEFERRABLE INITIALLY IMMEDIATE" not in parse_triggers(two).get(
            "CHANNELS_DISSOLVE_ORDER_TRG", ""):
        bad.append(f"the constraint trigger's DEFERRABILITY is not read — downgrading it to a "
                   f"plain BEFORE trigger re-breaks the one-statement subtree dissolve "
                   f"(1b7db-07): {parse_triggers(two)}")
    if parse_triggers("Tree invariants, and `DP-Ch1`'s rule.\n\n```sql\n" + trg + "\n```") \
            != parse_triggers(trg):
        bad.append("an apostrophe in PROSE changes the trigger parse — this is the defect the "
                   "gate actually reported as a schema disagreement on its first real run")

    # --- FLOW-19's trigger (1b7gap-H4) -------------------------------------
    if flow19_trigger(writers=set(), fk_declared=False):
        bad.append("FLOW-19 reds with NO writer — it would fire today and be switched off")
    if not flow19_trigger(writers={"services/x/src/create.rs"}, fk_declared=False):
        bad.append("FLOW-19's trigger is BLIND: a writer arriving must make the key owed, and "
                   "that arrival is the whole reason the deferral is allowed to stand")
    if flow19_trigger(writers={"services/x/src/create.rs"}, fk_declared=True):
        bad.append("FLOW-19 still reds once the key IS declared — the trigger cannot be retired")

    # --- prose is hostile input (the sql_only bug, found wiring 1b5-L5) -----
    # ONE unbalanced apostrophe in an English sentence puts the rest of the file
    # inside a string literal as far as `norm()` is concerned, and it silently
    # stops normalising. The gate reported that as a schema disagreement.
    prose = "Tree invariants, and `DP-Ch1`'s rule.\n\n```sql\n" + _T + "```\n"
    if prose.split("```sql")[0].count("'") % 2 == 0:
        bad.append("the PROSE fixture has an even number of apostrophes, so nothing flips and "
                   "the leg below tests nothing")
    if parse_table(prose, "self-test") != base:
        bad.append("an apostrophe in PROSE changes the table parse — the gate is reading the "
                   "document instead of its SQL fences")
    if parse_indexes(prose) != parse_indexes(_T):
        bad.append("an apostrophe in PROSE changes the index parse")

    # --- the cross-file scan (1b5-H1) --------------------------------------
    # Synthetic documents, so each rule of the scan is bitten rather than
    # inferred from the tree happening to be clean today.
    def fence(sql):
        return "```sql\n" + sql + "\n```"

    lifecycle_doc = ("17_channel_lifecycle.md", fence(
        "ALTER TABLE channels ADD COLUMN paused_until TIMESTAMPTZ, "
        "ADD COLUMN paused_reason TEXT, ADD COLUMN paused_by TEXT, "
        "ADD COLUMN became_dormant_at TIMESTAMPTZ, ADD COLUMN dissolved_at_eid BIGINT;"
        "\nALTER TABLE channels ADD CONSTRAINT channels_pause_active_only CHECK (true);"))
    ok_ref = ("99_ok.md", fence("CREATE TABLE t (a UUID, b BIGINT, "
                                "FOREIGN KEY (a, b) REFERENCES channels (reality_id, id));"))
    clean = [lifecycle_doc, ok_ref]
    if scan_tier_docs(set(), set(), clean):
        bad.append(f"the scan reds on a CLEAN synthetic tree: "
                   f"{scan_tier_docs(set(), set(), clean)}")

    scan_bites = {
        "1b5-H1's actual finding — a single-column UUID reference":
            [lifecycle_doc, ("13.md", fence("CREATE TABLE w (channel_id UUID PRIMARY KEY "
                                            "REFERENCES channels(id));"))],
        "a reference with the right columns in the wrong order":
            [lifecycle_doc, ("x.md", fence("FOREIGN KEY (a,b) REFERENCES channels (id, "
                                           "reality_id);"))],
        "an ALTER TABLE channels in a file the register has never heard of":
            [lifecycle_doc, ("new.md", fence("ALTER TABLE channels ADD COLUMN colour TEXT;"))],
        "a registered ALTER growing an unregistered column":
            [("17_channel_lifecycle.md", lifecycle_doc[1].replace(
                "ADD COLUMN paused_by TEXT", "ADD COLUMN paused_by TEXT, ADD COLUMN sneak INT"))],
        "the register naming a file whose ALTER has gone":
            [ok_ref],
    }
    for label, docs in scan_bites.items():
        if not scan_tier_docs(set(), set(), docs):
            bad.append(f"the cross-file scan is BLIND to: {label}")
    if not scan_tier_docs({"PAUSED_UNTIL"}, set(), clean):
        bad.append("the PENDING register does not SHRINK: 0019 having `paused_until` must red")
    if not scan_tier_docs(set(), {"CHANNELS_PAUSE_ACTIVE_ONLY"}, clean):
        bad.append("the PENDING register does not SHRINK on a CONSTRAINT it now has")
    if scan_tier_docs(set(), set()):
        bad.append(f"the cross-file scan reds on the REAL tree, which it must not: "
                   f"{scan_tier_docs(set(), set())}")

    if bad:
        print("dp-channels-schema-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"dp-channels-schema-gate: SELF-TEST PASS — {len(mutants)} schema mutations are each "
          f"VISIBLE (PK, NOT NULL, DEFAULT, FK body, FK actions, deferrability, type, name, "
          f"GENERATED expr, an added UNIQUE), {len(formats)} formatting changes are each "
          f"INVISIBLE, index uniqueness and partial predicate are read, the lifecycle trigger's "
          f"event is read, and the PENDING register reds when it should shrink")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    for f in (SPEC, MIGRATION):
        if not f.is_file():
            print(f"dp-channels-schema-gate: MISUSE — {f} does not exist", file=sys.stderr)
            return 2

    spec = SPEC.read_bytes().decode("utf-8")
    mig = MIGRATION.read_bytes().decode("utf-8")

    findings = []
    s_t, m_t = parse_table(spec, "DP-Ch2"), parse_table(mig, "0019_channels.up.sql")

    if s_t["columns"] != m_t["columns"]:
        s_by = {c["name"]: c for c in s_t["columns"]}
        m_by = {c["name"]: c for c in m_t["columns"]}
        if list(s_by) != list(m_by):
            findings.append(f"COLUMN SET differs.\n      only in DP-Ch2      : "
                            f"{sorted(set(s_by) - set(m_by))}\n"
                            f"      only in 0019_channels: {sorted(set(m_by) - set(s_by))}\n"
                            f"      order DP-Ch2 : {list(s_by)}\n"
                            f"      order 0019   : {list(m_by)}")
        for name in s_by:
            if name in m_by and s_by[name] != m_by[name]:
                diff = [k for k in s_by[name] if s_by[name][k] != m_by[name][k]]
                findings.append(f"COLUMN `{name.lower()}` differs on {diff}.\n"
                                f"      DP-Ch2      : {s_by[name]}\n"
                                f"      0019_channels: {m_by[name]}")
    if s_t["pk"] != m_t["pk"]:
        findings.append(f"PRIMARY KEY differs — REC-105's subject.\n"
                        f"      DP-Ch2      : {s_t['pk']}\n      0019_channels: {m_t['pk']}")
    if s_t["constraints"] != m_t["constraints"]:
        s_c, m_c = s_t["constraints"], m_t["constraints"]
        only_s, only_m = sorted(set(s_c) - set(m_c)), sorted(set(m_c) - set(s_c))
        if only_s or only_m:
            findings.append(f"CONSTRAINT SET differs.\n      only in DP-Ch2      : {only_s}\n"
                            f"      only in 0019_channels: {only_m}")
        for name in sorted(set(s_c) & set(m_c)):
            if s_c[name] != m_c[name]:
                findings.append(f"CONSTRAINT `{name.lower()}` BODY differs.\n"
                                f"      DP-Ch2      : {s_c[name]}\n"
                                f"      0019_channels: {m_c[name]}")
    s_i, m_i = parse_indexes(spec), parse_indexes(mig)
    if s_i != m_i:
        for name in sorted(set(s_i) | set(m_i)):
            if s_i.get(name) != m_i.get(name):
                findings.append(f"INDEX `{name.lower()}` differs.\n"
                                f"      DP-Ch2      : {s_i.get(name)}\n"
                                f"      0019_channels: {m_i.get(name)}")
    s_g, m_g = parse_triggers(spec), parse_triggers(mig)
    if s_g != m_g:
        findings.append(f"the lifecycle TRIGGERS differ between spec and migration (1b5-L5).\n"
                        f"      DP-Ch2      : {s_g}\n      0019_channels: {m_g}")
    for name, event in EXPECT_TRIGGERS.items():
        if m_g.get(name) != event:
            findings.append(f"trigger `{name.lower()}` is absent or has the wrong timing.\n"
                            f"      0019_channels: {m_g.get(name)}\n      expected     : {event}")
    for extra in sorted(set(m_g) - set(EXPECT_TRIGGERS)):
        findings.append(f"trigger `{extra.lower()}` exists in the migration and this gate has "
                        f"never been told about it. Add it to EXPECT_TRIGGERS with its timing.")

    findings += scan_tier_docs({c["name"] for c in m_t["columns"]}, set(m_t["constraints"]))
    findings += flow19_trigger()

    if findings:
        print(f"dp-channels-schema-gate: {len(findings)} disagreement(s) between the LOCKED specs "
              f"and the migration\n")
        for f in findings:
            print(f"  {f}")
        print("\nDP-Ch2 in 12_channel_primitives.md and 0019_channels.up.sql are two statements of")
        print("one schema, and 06_data_plane/ holds THREE more sites that name the same table.")
        print("FLOW-2 is what happens when one moves and the others do not — REC-103 is that exact")
        print("defect, it went unnoticed for eight weeks, and 1b5-H1 is it happening again inside")
        print("the commit written to kill it.")
        return 1

    docs = len(list(DP_DOCS.glob("*.md")))
    print(f"dp-channels-schema-gate: OK — DP-Ch2 and 0019_channels agree on "
          f"{len(m_t['columns'])} column(s), PRIMARY KEY {m_t['pk']}, "
          f"{len(m_t['constraints'])} named constraint(s) including the FOREIGN KEY body, "
          f"{len(m_i)} index(es), and the lifecycle trigger; and {docs} document(s) in "
          f"06_data_plane/ were scanned for `REFERENCES channels` / `ALTER TABLE channels`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
