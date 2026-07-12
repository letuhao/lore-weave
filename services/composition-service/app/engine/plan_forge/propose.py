"""Propose a NovelSystemSpec from a PlanDocument — RULES mode (deterministic, no LLM).

27 V2-G · the fixture severing (the P-06 correctness bug).
=========================================================

This module used to be a fixture with a parser bolted on. For ANY input document it returned, as if
it had read them:

  * four `planner_variables` (PA / HA / CD / THR) with Vietnamese transition rules — `_variable_defs`
    took a `var_body` argument and **ignored it entirely**;
  * six `consistency_anchors` from one specific novel's protagonist, defaulting to the first four
    when nothing matched;
  * four `forbids` about that novel's plot secrets;
  * a protagonist named "[TBD]" with that novel's traits and its transmigration backstory;
  * arcs — but ONLY if the document literally contained the headers `## Arc 1` / `## Arc 2` — whose
    titles, themes and summaries were hardcoded (arc 2 was titled "Bước Lên Tiên Lộ").

So rules mode did not fail on a book it had never seen. It **silently produced a plan for a
different book**, and every downstream pass — cast, world, beats, scenes — then planned faithfully
against that other book's charter. That is the "silent success is a bug" law at its worst: not a
crash, not an empty result, but a confident wrong answer.

The rule now, everywhere in this file: **parse what the document says; emit nothing where it says
nothing.** An absent variable list is `[]`. An arc with no stated theme has `theme: ""`. A book with
no character section gets no characters. Absent ≠ invented — and an honest empty tells the author
exactly what their braindump is missing, which is the entire job of the self-check they are about to
run against it.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.engine.plan_forge.normalize import post_normalize_spec

logger = logging.getLogger(__name__)

#: `**Key:** value` — the one convention this format leans on. Everything else is plain markdown.
_FIELD = r"\*\*{key}[^:]*:\*\*\s*(.+)"

#: A story has a handful of state variables. `_var_deltas` runs every declared code against every
#: line of every event — O(lines x codes) — and `source_markdown` is unbounded on the way in.
_MAX_VARIABLES = 24


def _section(doc: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for s in doc.get("sections", []):
        if s["kind"] == kind:
            return s
    return None


def _sections(doc: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in doc.get("sections", []) if s["kind"] == kind]


def _field(body: str, key: str) -> str:
    """The value of a `**Key:** …` line, or "" — never a default drawn from somewhere else."""
    m = re.search(_FIELD.format(key=re.escape(key)), body, re.I)
    return m.group(1).strip() if m else ""


def _bullets(body: str, limit: int = 12) -> list[str]:
    """The `- ` / `* ` bullet lines, in order. `[]` when there are none."""
    out: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            text = m.group(1).strip()
            # a markdown checkbox is an open QUESTION, not a statement — it has its own extractor
            if not re.match(r"^\[\s*[xX ]?\s*\]", text):
                out.append(text)
        if len(out) >= limit:
            break
    return out


def _prose(body: str, limit: int = 500) -> str:
    """The first prose lines of a block — no headers, no bullets, no `**Key:**` lines.

    BLOCKQUOTES ARE KEPT. A `> **This is not a power arc. It is a discovery arc.**` line is the
    author telling the planner what this arc IS — it is the most load-bearing sentence in the block,
    which is exactly why they emphasised it. Dropping it as "markup" threw away the one thing the
    old hardcode had bothered to transcribe (that is where its `arc_kind: "discovery"` came from),
    and the compiled premise then never mentioned what kind of arc it was.
    """
    lines: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith(">"):
            s = s.lstrip(">").strip().strip("*").strip()
            if s:
                lines.append(s)
            if len(lines) >= 3:
                break
            continue
        if not s or s.startswith(("#", "-", "*", "|", "`")) or s.startswith("**"):
            continue
        lines.append(s)
        if len(lines) >= 3:
            break
    return " ".join(lines)[:limit]


def _extract_open_questions(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^-\s+\[\s*\]\s+(.+)$", line.strip())
        if m:
            items.append(m.group(1).strip())
    return items


# ── the charter ──────────────────────────────────────────────────────────────────────────────────

def _extract_consistency_anchors(char_body: str) -> list[str]:
    """The character's invariants, AS THE DOCUMENT STATES THEM.

    This used to return a hardcoded list of six Vietnamese personality traits belonging to one
    novel's protagonist — and, when the crude keyword match found nothing, it returned the first
    FOUR of them anyway. Every book got someone else's character as its charter.

    Now: the `### ` sub-headings of the character section (the POC writes each trait as one), else
    its bullets. An empty character section yields an empty charter, which is the truth.
    """
    if not char_body.strip():
        return []
    anchors: list[str] = []
    for line in char_body.splitlines():
        m = re.match(r"^###\s+(.+)$", line.strip())
        if m:
            # strip a leading enumerator (①②③ / 1. / a) ) and any trailing *(parenthetical)*
            t = re.sub(r"^[①-⑳\d]+[\.\)]?\s*", "", m.group(1).strip())
            t = re.sub(r"\s*\*\(.*?\)\*\s*$", "", t).strip()
            if t:
                anchors.append(t)
    return anchors[:8] if anchors else _bullets(char_body, limit=8)


def _extract_forbids(doc: dict[str, Any]) -> list[str]:
    """What the planner must NOT do — from the document's own words.

    Was four hardcoded Vietnamese lines about another book's plot secrets, handed to every book.
    """
    out: list[str] = []
    for s in doc.get("sections", []):
        for line in s.get("body", "").splitlines():
            t = line.strip().lstrip("-*").strip()
            if re.match(r"^(không|đừng|never|do not|don'?t|avoid|forbid)\b", t, re.I):
                out.append(t[:300])
    return out[:10]


# ── the variables ────────────────────────────────────────────────────────────────────────────────

def _variable_defs(var_body: str) -> list[dict[str, Any]]:
    """The state variables the document DECLARES.

    The old body of this function was a `return [ …four hardcoded variables… ]`. It took `var_body`
    and never looked at it. So every book in the system ran on PA/HA/CD/THR — one novel's
    perfection-addiction system — and pass 4's var_deltas, and the `links` graph, were all computed
    against variables the author had never heard of.

    Recognised, in order of preference:
        **Biến trạng thái:** `PA` (Perfection Addiction)
        **Variable:** `HA` — Humanity Anchor
        - `CD` — Corruption Debt: accumulates silently
    A document that declares none gets `[]`. A plan with no variables is a perfectly good plan; a
    plan with someone else's variables is not.
    """
    if not var_body.strip():
        return []

    lines = var_body.splitlines()
    defs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw in lines:
        # A story has a handful of state variables. This cap is not about taste — `_var_deltas` runs
        # every declared code against every line of every event, so the parse is O(lines × codes),
        # and `source_markdown` has no length limit on the way in. Without a bound, a document that
        # declares thousands of `CODE = …` lines turns the compile into a CPU sink.
        if len(defs) >= _MAX_VARIABLES:
            logger.warning(
                "propose: the document declares more than %d state variables — parsing the first "
                "%d and ignoring the rest",
                _MAX_VARIABLES, _MAX_VARIABLES,
            )
            break
        # A DECLARATION starts at column 0:   CODE = Name   [range]
        # Anything indented under it is a rule ABOUT it. (`PA  = Perfection_Addiction  [0 → 100+]`
        # followed by `      ↑ mỗi lần đạt "hoàn mỹ"` — which is exactly how the POC document, and
        # every braindump written like it, states a state variable.)
        decl = re.match(
            r"^([A-Z][A-Z0-9_]{0,7})\s*=\s*([^\[\n]+?)\s*(?:\[([^\]]*)\])?\s*$", raw,
        )
        if decl:
            current = {
                "code": decl.group(1),
                "name": decl.group(2).strip(),
                "range": (decl.group(3) or "").strip(),
                "transition_rules": [],
                "not_coupled_to": [],
            }
            defs.append(current)
            continue
        if current is not None and raw.startswith((" ", "\t")) and raw.strip():
            rule = raw.strip().lstrip("↑↓-*•").strip()
            if rule and len(current["transition_rules"]) < 6:
                current["transition_rules"].append(rule)
            continue
        if raw.strip().startswith("```") or not raw.strip():
            current = None  # the block ended; a later bullet is prose, not a rule

    if not defs:
        return []

    # The operating PRINCIPLES below the block ("PA and HA do NOT move with cultivation realm") are
    # what `not_coupled_to` means. Parse them; do not assume them. The old code hardcoded
    # `["cultivation_realm", "cảnh giới"]` onto three of its four invented variables.
    by_code = {d["code"]: d for d in defs}
    for raw in lines:
        line = raw.strip().lstrip("-*").strip()
        if not re.search(r"không\s+(?:tăng|giảm|thay đổi)|not?\s+coupled|independent of", line, re.I):
            continue
        m = re.search(r"theo\s+(.+?)(?:\s*—|$)|(?:coupled to|of)\s+(.+?)(?:\s*—|$)", line, re.I)
        target = (m.group(1) or m.group(2) or "").strip(" .*_`") if m else ""
        if not target:
            continue
        for code, d in by_code.items():
            if re.search(rf"\b{re.escape(code)}\b", line) and target not in d["not_coupled_to"]:
                d["not_coupled_to"].append(target)
    return defs


# ── arcs + events ────────────────────────────────────────────────────────────────────────────────

def _parse_events_in_block(arc_id: str, body: str, var_codes: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    # `[1:]` for the same reason as the arc split: element 0 is the arc's own preamble, not an
    # event. Without it the arc's intro prose became a phantom "event 1" that then COLLIDED with the
    # real Event 1 — two events sharing one id, which the linker's run-scoped unique index would
    # have arbitrated into one node, silently losing a chapter. (The old parser dodged this only by
    # requiring the literal word "Event" in the header — which is also why a document written in any
    # other vocabulary produced no events at all.)
    for part in re.split(r"(?m)^###\s+", body)[1:]:
        if not part.strip():
            continue
        lines = part.strip().splitlines()
        header = lines[0].strip()
        # The LAST event in a block has no following "### " to split on, so without this it swallows
        # the arc's trailing "---"-delimited closing summary as part of its own body.
        ev_body = "\n".join(lines[1:]).split("\n---", 1)[0]

        # An event is any `### ` block that is not obviously a non-event heading. The old parser
        # required the literal word "Event", so a document using "### Scene 1" or "### Chapter 3" —
        # or any other language — produced ZERO events, and the compiler compiled nothing.
        m = re.match(r"(?:event|scene|chapter|beat|sự kiện)\s*(\d+)", header, re.I)
        num = m.group(1) if m else str(len(events) + 1)
        ev_id = f"{arc_id}_event_{num}"
        events.append(_parse_event_block(ev_id, arc_id, header, ev_body, var_codes))
    return events


def _parse_arcs_and_events(
    arc_body: str, var_codes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every `## ` block in the arc section is an arc — whatever it is called.

    The old version matched the literal headers `## Arc 1` and `## Arc 2` (case-insensitively) and
    hardcoded each one's title, theme, arc_kind and summary. A document with `## Arc 3`, `## Act
    One`, `## Phần 1`, or any real arc title produced NO arcs at all — and a document that DID say
    "Arc 1" got another novel's theme and summary attached to it.
    """
    arcs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    # `[1:]` — element 0 is whatever PRECEDED the first `## ` header (the section's own preamble
    # prose, a `---` rule, an intro paragraph). It is by definition not an arc. Minting it as one
    # shifted every real arc up by a slot, so `arc_1` was the preamble and the author's Arc 1 became
    # `arc_2` — and `compile(arc_id="arc_1")` then compiled an arc with no events. The old parser
    # skipped it only by accident, because it matched the literal header "Arc 1".
    for block in re.split(r"(?m)^##\s+", arc_body)[1:]:
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        header = lines[0].strip()
        body = "\n".join(lines[1:])

        if re.match(r"\[?TRANSITION\]?", header, re.I):
            # A transition is a bridge BETWEEN arcs, not an arc. It keeps its events (they are real
            # story) but mints no arc — an arc with no chapters would link as an empty node.
            events.extend(_parse_events_in_block("transition", body, var_codes))
            continue

        ordinal = len(arcs) + 1
        arc_id = f"arc_{ordinal}"
        arcs.append({
            "id": arc_id,
            # The header IS the title. "Arc 1: The Iron Court" → "The Iron Court"; a bare "Arc 1"
            # stays "Arc 1", because that is genuinely all the author wrote.
            "title": _arc_title(header),
            # Stated or absent. NEVER inherited from another book.
            "theme": _field(body, "Theme") or _field(body, "Chủ đề"),
            "arc_kind": _field(body, "Kind") or _field(body, "Arc kind") or "",
            "summary": _field(body, "Summary") or _field(body, "Tóm tắt") or _prose(body),
        })
        events.extend(_parse_events_in_block(arc_id, body, var_codes))

    return arcs, events


def _arc_title(header: str) -> str:
    """"Arc 2: Bước Lên Tiên Lộ" → "Bước Lên Tiên Lộ"; "Arc 1" → "Arc 1"."""
    m = re.match(r"(?:arc|act|part|phần)\s*\d+\s*[:—\-–]\s*(.+)$", header, re.I)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return header.strip()


def _parse_event_block(
    ev_id: str, arc_id: str, header: str, body: str, var_codes: list[str],
) -> dict[str, Any]:
    title = re.sub(r"^###\s*", "", header).strip()
    goal = _field(body, "Goal") or _field(body, "Mục tiêu")

    notes: list[str] = []
    for m in re.finditer(r"\*\*Planner note[^:]*:\*\*\s*(.+)", body, re.I):
        notes.append(m.group(1).strip())

    return {
        "id": ev_id,
        "arc_id": arc_id,
        "title": title,
        "synopsis": _prose(body) or title,
        "goal": goal,
        "planner_notes": notes,
        "var_deltas": _var_deltas(body, var_codes),
    }


def _var_deltas(body: str, var_codes: list[str]) -> list[dict[str, Any]]:
    """State changes this event asserts, over the variables THIS DOCUMENT DECLARED.

    The old version ran five hardcoded regexes — `HA\\s*=\\s*100`, `PA \\+lớn`, `PA khởi động`,
    `CD tăng`, `THR` — against every event of every book, with hardcoded English reasons ("first
    perfection sensation", "past-life pattern"). A book without those four variables got nothing; a
    book that happened to use the letters "THR" got a delta about someone else's reincarnation.

    Now the codes come from the document's own variable list, and the delta is quoted from the line
    that stated it. No declared variables ⇒ no deltas, which is correct: you cannot assert a change
    to a variable that does not exist.
    """
    if not var_codes:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in body.splitlines():
        for code in var_codes:
            if code in seen:
                continue
            # the code as a WHOLE word, followed by an assertion of change
            m = re.search(
                rf"\b{re.escape(code)}\b\s*(=\s*\d+|[+\-]\s*\S+|\S*(?:tăng|giảm|up|down|rise|drop)\S*)",
                line, re.I,
            )
            if not m:
                continue
            seen.add(code)
            out.append({
                "variable": code,
                "delta": m.group(1).strip(),
                # The document's own sentence, not a phrase invented for another story.
                "reason": line.strip().lstrip("-*").strip()[:200],
                "coupled_to_realm": False,
            })
    return out


# ── characters ───────────────────────────────────────────────────────────────────────────────────

def _characters(char_body: str, anchors: list[str]) -> list[dict[str, Any]]:
    """The protagonist as the document describes them — or NOBODY.

    Was a hardcoded `[{"id": "protagonist", "name": "[TBD]", "traits": [5 Vietnamese traits],
    "baseline_notes": "<another novel's premise>"}]`, returned for every book. The `cast` pass then
    ran with that person in its prompt.

    A document with no character section now yields `[]`. The cast pass proposes the cast; that is
    its entire job, and it does it from the premise. A fabricated placeholder is worse than an empty
    roster, because the roster is honest about what it does not know.
    """
    if not char_body.strip():
        return []
    name = _field(char_body, "Name") or _field(char_body, "Tên") or ""
    role = _field(char_body, "Role") or _field(char_body, "Vai trò") or "protagonist"
    return [{
        "id": "protagonist",
        # "[TBD]" is what this format says for "not yet named" — but only if the author left it so.
        "name": name or "[TBD]",
        "role": role,
        # The anchors ARE the traits — they are what the document says is invariant about them.
        "traits": anchors[:6],
        "baseline_notes": _field(char_body, "Baseline") or _prose(char_body),
    }]


# ── the spec ─────────────────────────────────────────────────────────────────────────────────────

def propose_spec(doc: dict[str, Any]) -> dict[str, Any]:
    char_sec = _section(doc, "character_seed")
    var_sec = _section(doc, "planner_variables")
    arc_sec = _section(doc, "arc_overview")
    principles_sec = _section(doc, "writing_principles")
    open_sec = _section(doc, "open_questions")
    mech_secs = _sections(doc, "mechanics")

    char_body = char_sec["body"] if char_sec else ""
    anchors = _extract_consistency_anchors(char_body)

    variables = _variable_defs(var_sec["body"] if var_sec else "")
    var_codes = [v["code"] for v in variables]

    mechanics: list[dict[str, Any]] = []
    for i, ms in enumerate(mech_secs):
        mechanics.append({
            "id": f"mechanic_{i + 1}",
            "name": ms["title"],
            "rules": _bullets(ms["body"], limit=8),
            "planner_secrets": [
                ln.strip()
                for ln in ms["body"].splitlines()
                if re.search(r"planner secret|không tiết lộ|do not reveal", ln, re.I)
            ],
        })

    arcs, events = _parse_arcs_and_events(arc_sec["body"] if arc_sec else "", var_codes)

    style = _bullets(principles_sec["body"], limit=10) if principles_sec else []

    # The links graph. Derived from what the events actually SAY, against what the document actually
    # DECLARED — never from keyword guesses about another book's motifs.
    #
    # The old version matched the literal strings "baseline", "hài hước" and "THR" in planner notes.
    # The CONCEPT was right (a planner note that references a variable or an anchor is a constraint
    # the compiler should carry), but the implementation could only ever fire on one novel's
    # vocabulary. Generalised: a note is linked to any variable code THIS document declared, and to
    # the charter when it echoes one of THIS document's own anchors.
    links: list[dict[str, Any]] = []
    anchor_words = {
        w.casefold()
        for a in anchors
        for w in re.findall(r"\w{4,}", a)
    }
    for ev in events:
        for nd in ev.get("var_deltas", []):
            links.append({
                "from": ev["id"],
                "to": nd["variable"],
                "kind": "event_constrains_variable",
                "note": nd.get("reason", ""),
            })
        for note in ev.get("planner_notes", []):
            for code in var_codes:
                if re.search(rf"\b{re.escape(code)}\b", note):
                    links.append({
                        "from": ev["id"],
                        "to": code,
                        "kind": "event_foreshadows",
                        "note": note,
                    })
            note_words = {w.casefold() for w in re.findall(r"\w{4,}", note)}
            if anchor_words and note_words & anchor_words:
                links.append({
                    "from": ev["id"],
                    "to": "charter.consistency_anchors",
                    "kind": "event_preserves_anchor",
                    "note": note,
                })

    return post_normalize_spec({
        "version": 1,
        "meta": {
            # The document's own title, not the literal string "STORY PLAN".
            "title": _doc_title(doc) or "STORY PLAN",
            "version_label": "v1.0",
            "source_checksum": doc["source"]["checksum_sha256"],
            "open_questions": _extract_open_questions(open_sec["body"]) if open_sec else [],
        },
        "charter": {
            "consistency_anchors": anchors,
            "forbids": _extract_forbids(doc),
            "style_constraints": style,
        },
        "layers": {
            "characters": _characters(char_body, anchors),
            "mechanics": mechanics,
            "variables": variables,
        },
        "arcs": arcs,
        "events": events,
        "links": links,
    })


def _doc_title(doc: dict[str, Any]) -> str:
    for s in doc.get("sections", []):
        t = (s.get("title") or "").strip()
        if t:
            return f"STORY PLAN — {t}" if not t.upper().startswith("STORY PLAN") else t
    return ""
