#!/usr/bin/env python
"""A throwaway book per scenario — built, seeded, and torn down around every run.

🔴 WHY THIS EXISTS, IN ONE INCIDENT. On 2026-08-13 five read-intent turns against the shared
loop book took `outline_node` from 3 to 6: the model created three chapters and then described
them back as "your current plan". Because every scenario shared one book, the store diff could
not say WHICH scenario wrote — and because the book persisted between runs, the next run started
from the contaminated state and read as if nothing had happened. A per-scenario book fixes both:
the diff is attributable, and every run starts from the same substrate.

🔴 AND WHY IT SEEDS. A read-intent scenario against an EMPTY store cannot tell the two outcomes
apart that this loop most needs to separate:

    the model reached the tool and truthfully reported nothing
    the model never reached the tool and fabricated "you have nothing yet"

Both print the same sentence. Seeding makes the truthful answer specific — three named outline
nodes, a named canon rule — so a fabricated one is visibly wrong rather than merely unverifiable.
This is the same failure as `composition_list_canon_rules` answering "you haven't declared any"
with one row in the store.

Substrate is built by DIRECT MCP calls, never by the model: setup must be deterministic, or the
thing under test is the setup. The model only ever drives the TURN.

The teardown boundary is the title prefix. `teardown()` refuses to delete a book that this module
did not name, so no bug in a scenario file can reach a real book.

Usage (normally called by fe_runner, but runnable alone to inspect a fixture):
    python scripts/toolloop/provision.py --label smoke --keep
"""
from __future__ import annotations

import argparse
import json
import re
import pathlib
import subprocess
import sys
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from scripts.eval.tool_liveness.mcp_direct import MCPDirect  # noqa: E402
from scripts.eval.tool_liveness.auth import Auth as _TLEAuth  # noqa: E402
from scripts.eval.tool_liveness import oracle  # noqa: E402

#: Every book this module creates carries this prefix, and teardown deletes nothing without it.
#: A constant rather than a parameter on purpose — a caller that can choose the prefix can choose
#: one that matches a real book.
TITLE_PREFIX = "LOOP-THROWAWAY-"

#: Where a running fixture writes down what it created, so a LATER process can remove it by id.
#: Git-ignored: it is live state about this machine's runs, not a fact about the repo. A file
#: here means a fixture that was built and never torn down.
MANIFEST_DIR = pathlib.Path(__file__).resolve().parent / ".fixtures"

#: The account the loop runs as. Read from the same place the runner reads it so the two cannot
#: drift into provisioning as one user and driving turns as another — which would present as
#: "the tool returned nothing" for every single scenario.
from scripts.eval.tool_liveness import config as _tle_config  # noqa: E402

OWNER_ID = _tle_config.USER_ID

_AUTH_SINGLETON = None


def _tle_auth():
    """One cached bearer for the whole process — the token is good for 2h and re-logging in per
    fixture would make provisioning the slowest part of a batch."""
    global _AUTH_SINGLETON
    if _AUTH_SINGLETON is None:
        _AUTH_SINGLETON = _TLEAuth()
    return _AUTH_SINGLETON

CONTAINER = _tle_config.PG_CONTAINER
PG_USER = _tle_config.PG_USER

BOOK_DB = "loreweave_book"
COMP_DB = "loreweave_composition"


class ProvisionError(RuntimeError):
    pass


# No hex letters (a-f) among the consonants, so a generated word ALWAYS contains a character
# that cannot appear in a hex id. Without that, "00000000" rendered as "Babababa" — every
# letter of which is a valid hex digit, which is precisely the thing this is here to avoid.
_CONSONANTS = "gklmnprstvz"
_VOWELS = "aeiou"


def _pronounceable(seed_hex: str) -> str:
    """A short name-shaped token from the run's hex nonce.

    Deterministic (same run -> same word) and reversible enough to correlate with run_id in
    logs, but consonant-vowel shaped so no reader -- human or model -- mistakes it for a UUID
    or an opaque id. Two syllables per 4 hex chars gives ~14^2*5^2 per pair, plenty to keep
    five repeats of one batch distinct.
    """
    out = []
    for i in range(0, min(len(seed_hex), 8), 2):
        b = int(seed_hex[i:i + 2], 16)
        out.append(_CONSONANTS[b % len(_CONSONANTS)] + _VOWELS[(b // len(_CONSONANTS)) % len(_VOWELS)])
    return "".join(out).capitalize()


class Throwaway:
    """One scenario's substrate. Build it, use it, tear it down."""

    def __init__(self, label: str, *, mcp: MCPDirect | None = None) -> None:
        self.label = label
        self.run_id = uuid.uuid4().hex[:8]
        # 🔴 `{run_word}` — the same per-run nonce, shaped so it CANNOT be mistaken for an id.
        # Measured 2026-08-21, batch 29: naming an account-scoped fixture "Emberfall Reach
        # {run_id}" put a bare 8-hex token in the sentence the model reads, and the model
        # passed THAT as the world_id -- "I'm having trouble accessing the map (ID:
        # `a671b6c9`)". A hex suffix in a NAME is indistinguishable from an identifier, so the
        # fixture was handing the model a plausible wrong answer and then measuring whether it
        # took it. Use {run_id} for CODES (slugs, machine keys) and {run_word} for anything a
        # person would read as a name.
        self.run_word = _pronounceable(self.run_id)
        self.title = f"{TITLE_PREFIX}{label}-{self.run_id}"
        self.mcp = mcp or MCPDirect()
        self.book_id: str | None = None
        self.chapter_id: str | None = None
        self.project_id: str | None = None
        # The world this fixture's seed created, if any. Exposed for the SNAPSHOT rather than for
        # teardown: the world/map store carries no `book_id`, so the DATA bar cannot see it
        # without being told which world belongs to this run. See store_snapshot._world_counts.
        self.world_id: str | None = None
        #: The registered model this fixture created, if any — exposed for the SNAPSHOT.
        self.user_model_id: str | None = None
        self.seeded: list[dict] = []

    # ── provenance manifest ──────────────────────────────────────────────────────────────
    def _manifest_path(self) -> pathlib.Path:
        return MANIFEST_DIR / f"{self.run_id}.json"

    def _record(self, entry: dict) -> None:
        """Append a seed result AND flush the run's manifest.

        🔴 THE PER-RUN TEARDOWN KNOWS ITS PROVENANCE; `--sweep` DOES NOT.
        D-HARNESS-sweep-DOES-NOT-COVER-ACCOUNT-SCOPED-FIXTURES: `teardown()` removes worlds,
        models, arc templates and motifs by the ids THIS object saw come back, and it works —
        seven runs of scenarios-c-arcapply left zero rows. But `--sweep` is a fresh process with
        no `self.seeded`, so it can only reach what a NAME PREFIX finds, and it reported "swept 1
        throwaway book(s) / 1 throwaway world(s)" with the seeded arc_template still sitting
        there. The gap is exactly the --keep-fixtures path: the one taken when something has
        already gone wrong and nobody is watching the store.

        A PREFIX WOULD NOT DO, and this loop has already paid for learning that twice —
        `_purge_worlds` matched nothing for 35 worlds, and the seeds name themselves
        `emberfall-vein-b27-`, `throwaway-loop-alpha-b19-`, `loop-arc-` and six other shapes with
        no common stem. Of the 57 arc templates on this account, 51 are account-scoped and only
        ONE carries a code any prefix list would match; the other 50 belong to earlier suites and
        must never be touched.

        So the provenance is WRITTEN DOWN instead of guessed. Flushed after every step rather
        than at the end of build(), because a crash mid-build is precisely when the sweep is
        needed. `teardown()` removes the file, so a manifest on disk means a fixture that was
        never torn down."""
        self.seeded.append(entry)
        try:
            MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
            self._manifest_path().write_text(json.dumps({
                "run_id": self.run_id, "label": self.label, "title": self.title,
                "book_id": self.book_id, "seeded": self.seeded,
            }, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError:
            # A manifest is a CONVENIENCE for a later sweep. Failing the run because the disk
            # would not take it would trade a cleanup aid for the measurement itself.
            pass

    @classmethod
    def from_manifest(cls, data: dict) -> "Throwaway":
        """Rebuild just enough of a fixture to run its OWN purges — no provisioning.

        The purge methods are reused rather than re-implemented: four families of DELETE, each
        with a hard-won guard in its docstring, and a second copy in the sweep would be a second
        chance to get one wrong."""
        fx = cls(str(data.get("label") or "sweep"))
        fx.run_id = str(data.get("run_id") or fx.run_id)
        fx.title = str(data.get("title") or fx.title)
        fx.book_id = data.get("book_id")
        fx.seeded = list(data.get("seeded") or [])
        return fx

    # ── build ────────────────────────────────────────────────────────────────────────────
    def build(self, seed: list[dict] | None = None, *, chapter: bool = True) -> "Throwaway":
        r = self.mcp.call("book_create", {
            "title": self.title,
            "original_language": "en",
            "description": "Tool-loop throwaway fixture — created and deleted by "
                           "scripts/toolloop/provision.py. Safe to delete.",
            "genre_tags": ["fantasy"],
        })
        self.book_id = r.get("book_id") or r.get("id")
        if not self.book_id:
            raise ProvisionError(f"book_create returned no id: {json.dumps(r)[:200]}")

        if chapter:
            self.chapter_id = self._make_chapter()

        # The composition Work is provisioned ASYNCHRONOUSLY off `book.created` (measured
        # 0.2s–8.0s on this stack). Polling rather than sleeping, because a fixed sleep is
        # either flaky or slow and this runs once per scenario per batch.
        self.project_id = self._await_project()

        for step in (seed or []):
            self._seed_step(step)
        return self

    def assert_seeded(self, checks: list[dict] | None) -> None:
        """Prove the fixture is in the state the scenario CLAIMS, by reading the store.

        🔴 THREE SCENARIOS IN A ROW MEASURED SOMETHING OTHER THAN WHAT THEY CLAIMED, AND THE THIRD
        INVERTED THE READING OF THREE EXPERIMENTS. The `glossary_list_ai_suggestions` fixture was
        supposed to hold three entities with exactly ONE tagged 'ai-suggested', so that a truthful
        answer ("one, Mira Solene") and a lazy one ("three") differ. It never did:
        `glossary_propose_entities` already tags everything it creates `ai-suggested+assistant`,
        so the SQL step that "tagged one" changed nothing observable. All three were always in the
        review queue.

        Every conclusion drawn on top of that was therefore wrong in the same direction: "3
        suggested entries" was the CORRECT answer being scored as a fabrication, and two fixes
        were evaluated against it — one of them reverted on that basis.

        A seed is a claim about the world. This makes the claim checkable at the moment it is
        made, against the store, before a single turn runs — so a scenario that cannot
        discriminate fails loudly instead of producing confident nonsense for an hour.
        """
        for c in (checks or []):
            sql = self._substitute(c["query"])
            rows = oracle.db_query(c["db"], sql)
            got = (rows[0][0] if rows and rows[0] else "")
            if str(got).strip() != str(c["expect"]).strip():
                raise ProvisionError(
                    f"SEED ASSERTION FAILED: {c.get('why', c['query'])}\n"
                    f"    expected {c['expect']!r}, store says {got!r}\n"
                    f"    The fixture is not in the state this scenario claims, so whatever it "
                    f"measures is not what it says it measures.")

    def _make_chapter(self) -> str | None:
        r = self.mcp.call("book_chapter_create", {
            "book_id": self.book_id,
            "original_language": "en",
            "title": "Chapter I — The Ember Codex",
            # `body`, not `content`. Guessed `content` on the first call and the gateway
            # rejected the whole request -- the schema is the authority, never the name.
            "body": "Aldric Vane climbed the black stair of Hollow Keep as the storm broke.",
        })
        return r.get("chapter_id") or r.get("id")

    def _await_project(self, timeout: float = 30.0) -> str | None:
        """Get the book's composition `project_id`, minting it if nobody has yet.

        🔴 WAITING FOR THIS IS WAITING FOREVER, AND THAT COST A WHOLE FIXTURE CYCLE. The
        `book.created` consumer DOES provision a composition Work within a second — but it
        provisions it LAZY: `project_id` NULL, `pending_project_backfill=true`, logged as
        "provisioned (pending project)". Nothing backfills it on a timer. The id is minted by
        the first caller that needs one, and `composition_create_work` is that caller: it
        resolves an existing book-typed knowledge project or creates one, then backfills THE
        pending row rather than minting a second Work.

        A poll therefore never converges, and the empty string it kept reading looked exactly
        like "composition is slow on this stack" — a provisioning bug wearing a performance
        bug's clothes. Ask for the thing instead of waiting for it.
        """
        r = self.mcp.call("composition_create_work", {"book_id": self.book_id})
        pid = r.get("project_id") or (r.get("work") or {}).get("project_id")
        if pid:
            return str(pid)
        # Fall back to the row: create_work is idempotent, so a Work that already existed with a
        # project comes back through the DB even if the response shape differs.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = oracle.db_query(
                COMP_DB, "SELECT project_id FROM composition_work WHERE "
                         f"book_id='{(self.book_id or '').replace(chr(39), chr(39) * 2)}' "
                         "AND project_id IS NOT NULL LIMIT 1")
            if rows and rows[0] and rows[0][0]:
                return rows[0][0]
            time.sleep(0.5)
        # Not fatal: plenty of tools never touch composition. But it IS reported, because a
        # silent None here would later look like "the composition tool found nothing" — a
        # provisioning failure wearing a defect's clothes.
        print(f"  ! composition project never minted for {self.book_id} within {timeout}s")
        return None

    def _seed_step(self, step: dict) -> None:
        """One deterministic setup call. `{book_id}` / `{chapter_id}` / `{project_id}` in any
        string value are substituted with this fixture's real ids.

        Two step kinds. `{"tool": ...}` is an MCP call. `{"rest": {...}}` is a direct service
        call, needed where the MCP tool cannot seed deterministically — `glossary_adopt_standards`
        mints a confirm_token and writes nothing at call time, so a fixture that used it would
        report "no entities were created — unknown kind: character" and look like a glossary bug.
        """
        if "wait" in step:
            # 🔴 A SEED STEP CAN BE ASYNC, AND A FIXTURE THAT DOES NOT WAIT SATISFIES ITS OWN
            # ASSERTION WHILE THE PRECONDITION IS STILL MISSING. Measured 2026-08-14:
            # `plan_propose_spec` creates the plan_run synchronously and produces the SPEC
            # artifact on a job. The seed asserted the run existed — true immediately — and
            # `plan_compile` then failed 3/3 with "no spec to compile". The tool was reached and
            # behaved correctly; the fixture was not ready, and nothing said so.
            #
            # Polls a SQL predicate until it returns the expected value or the timeout expires,
            # and RAISES on timeout. A wait that gives up quietly is the same defect one layer
            # further out.
            spec = self._substitute(step["wait"])
            deadline = time.monotonic() + float(spec.get("timeout", 90))
            want = str(spec.get("expect", "1")).strip()
            last = None
            while time.monotonic() < deadline:
                rows = oracle.db_query(spec["db"], spec["query"])
                last = str(rows[0][0]).strip() if rows and rows[0] else ""
                if last == want:
                    self._record({"wait": spec["query"][:80], "settled": last})
                    return
                time.sleep(float(spec.get("poll", 2)))
            raise ProvisionError(
                f"SEED WAIT TIMED OUT after {spec.get('timeout', 90)}s: {spec.get('why', spec['query'])}\n"
                f"    expected {want!r}, store still says {last!r}\n"
                f"    The async half of this fixture never landed, so the scenario would measure "
                f"a tool refusing a precondition that was never met.")
        if "sql" in step:
            # A third setup kind, for substrate NO tool can create. `glossary_list_ai_suggestions`
            # reads entities tagged 'ai-suggested' — a tag the extractor writes and no MCP tool
            # sets, so without this the scenario could only ever exercise the EMPTY case and
            # would report "the inbox is empty" as if that were the tool working. Setup only:
            # the thing under test is still the model's turn, never this.
            spec = self._substitute(step["sql"])
            oracle.db_query(spec["db"], spec["statement"])
            self._record({"sql": spec["db"], "ok": True})
            return
        if "rest" in step:
            spec = self._substitute(step["rest"])
            base = _tle_config.DOMAIN_BASE[spec["domain"]]
            r = httpx.request(spec.get("method", "POST"), f"{base}{spec['path']}",
                              headers=_tle_auth().bearer_header(),
                              json=spec.get("json") or {}, timeout=60)
            if r.status_code == 404:
                # 🔴 A 404 HERE IS AS LIKELY TO BE THE WRONG SERVICE AS THE WRONG PATH, and the
                # wrong service is the harder one to see. Measured 2026-08-14: DOMAIN_BASE
                # pointed "translation" at localhost:8207, which is catalog-service — and it
                # answers /health with 200, so nothing upstream could flag it. The Go services
                # all return a bare "ok" with no identity, so only a ROUTE probe distinguishes
                # them. Name both possibilities rather than letting this read as a bad path.
                raise ProvisionError(
                    f"SEED REST 404: {spec.get('method', 'POST')} {base}{spec['path']}\n"
                    f"    Either the path is wrong, OR DOMAIN_BASE[{spec['domain']!r}] = {base} "
                    f"points at a DIFFERENT service. Check by route, not by /health — several "
                    f"services answer /health with a bare 'ok' and cannot be told apart by it.")
            # 🔴 raise_for_status() THROWS AWAY THE REASON. A seed that fails with
            # "Client error '400 Bad Request' for url …" tells the reader the shape of the failure
            # and nothing about its cause, and the cause is sitting in the body. Measured
            # 2026-08-23: an authoring-run gate confirm 400'd and the detail — the thing that says
            # WHICH precondition is unmet — was discarded by this line.
            if r.status_code >= 400:
                raise ProvisionError(
                    f"SEED REST {r.status_code}: "
                    f"{spec.get('method', 'POST')} {base}{spec['path']} -> "
                    f"{str(r.text)[:400]}")
            # 🔴 RECORD THE RESPONSE BODY, so a later step can reference what this call CREATED.
            # Measured 2026-08-23 building composition_authoring_run_manage's fixture: a Tier-W seed
            # step mints a confirm_token and creates NOTHING until a REST redemption — and the thing
            # the redemption creates (the run's id) was unreachable, because this recorded only the
            # STATUS. `{step:N:key}` reads `result`, so a confirm step had nothing to offer and the
            # chain create -> confirm -> gate could not be expressed at all.
            #
            # Same shape as the two resolver gaps already fixed here: `{step:N:...}` existed because
            # a seed could not use what an earlier seed produced, and list indexing because half the
            # write tools answer with `results: [...]`. A confirm-gated seed step is the third.
            _body = None
            try:
                if (r.headers.get("content-type") or "").startswith("application/json"):
                    _body = r.json()
            except Exception:  # noqa: BLE001 — a body that will not parse is not a seed failure
                _body = None
            self._record({"rest": spec, "status": r.status_code, "result": _body})
            return
        tool = step["tool"]
        args = self._substitute(step.get("args") or {})
        r = self.mcp.call(tool, args)
        self._record({"tool": tool, "args": args, "result": r})
        # Remember the world this run created — the DATA bar cannot find it any other way, because
        # nothing in the world/map store carries a book_id.
        if tool == "world_create" and isinstance(r, dict):
            w = r.get("world") if isinstance(r.get("world"), dict) else r
            self.world_id = str(w.get("world_id") or w.get("id") or "") or None
        # Same reason as the world: user_models is account-scoped and the DATA bar cannot find it
        # without being told which model belongs to this run.
        if tool == "settings_model_register" and isinstance(r, dict):
            m = r.get("model") if isinstance(r.get("model"), dict) else r
            self.user_model_id = str(m.get("user_model_id") or m.get("id") or "") or None

    _STEP_REF = re.compile(r"\{step:(\d+):([A-Za-z0-9_.]+)\}")

    def _step_value(self, idx: int, path: str):
        """A value RETURNED by an earlier seed step, addressed as `{step:0:world.world_id}`.

        🔴 A SEED COULD NOT USE WHAT AN EARLIER SEED PRODUCED, AND THAT MADE WHOLE TOOL FAMILIES
        UNTESTABLE. The world/map tools are the case: `world_map_create` needs the `world_id`
        that `world_create` just minted, and `world_map_add_marker` needs the `map_id` from
        that. With only {book_id}/{chapter_id}/{project_id} available, the chain could not be
        expressed at all — the fixture had to be built by hand outside the scenario, which
        breaks the per-repeat isolation the whole harness rests on.

        Reads the RESULT the step recorded, so it cannot drift from what actually happened.
        Raises rather than substituting empty: a silently blank id produces a tool call that
        fails for a reason the evidence cannot explain.
        """
        try:
            rec = self.seeded[idx]
        except IndexError:
            raise ProvisionError(
                f"seed step {idx} has not run yet — {{step:{idx}:{path}}} can only reference an "
                f"EARLIER step (this fixture has {len(self.seeded)} so far)") from None
        cur = rec.get("result")
        for part in path.split("."):
            # 🔴 A LIST INDEX, because half the write tools answer with one. Measured 2026-08-23:
            # `glossary_propose_entities` returns {guidance, results: [{entity_id, ...}]}, and this
            # walk handled dicts ONLY — so `{step:1:results.0.entity_id}` was unreachable and the
            # idempotency probe for `glossary_create_chapter_link` could not be built at all. That
            # is the same gap `{step:N:...}` itself was written to close, one level down: a seed
            # cannot use what an earlier seed produced. `results`/`items` is the common shape for
            # any tool that writes more than one row, so this was never about one tool.
            if isinstance(cur, (list, tuple)):
                if not part.lstrip("-").isdigit():
                    raise ProvisionError(
                        f"seed step {idx}: {path!r} indexes a list with {part!r}, which is not a "
                        f"number. A list is addressed positionally — `results.0.entity_id`.")
                i = int(part)
                if not -len(cur) <= i < len(cur):
                    raise ProvisionError(
                        f"seed step {idx}: {path!r} wants index {i} of a {len(cur)}-item list. "
                        f"The tool returned fewer rows than the seed assumes.")
                cur = cur[i]
                continue
            if not isinstance(cur, dict) or part not in cur:
                raise ProvisionError(
                    f"seed step {idx} returned no {path!r} — got keys "
                    f"{sorted(cur) if isinstance(cur, dict) else type(cur).__name__}. The seed "
                    f"cannot reference a value the tool did not return.")
            cur = cur[part]
        return cur

    def substitute_text(self, text: str) -> str:
        """The public form of `_substitute` for a single string — used for scenario PROMPTS.

        Same nonce and same ids as the seeds, so a scenario can name the fixture it just
        created. See the note at the `turns = ...` line in fe_runner for what a prompt that
        did NOT get this substitution cost.
        """
        return self._substitute(text) if isinstance(text, str) else text

    def _substitute(self, obj):
        if isinstance(obj, str):
            def _ref(m):
                return str(self._step_value(int(m.group(1)), m.group(2)))
            obj = self._STEP_REF.sub(_ref, obj)
            # 🔴 `{run_id}` — a per-run nonce, and it is what makes an ACCOUNT-SCOPED seed
            # repeatable. Measured 2026-08-21, batch 20: composition_motif_link_list seeded a
            # motif with the fixed code 'emberfall-ascent-b20', which is unique PER OWNER — so
            # rep 0 created it and reps 1-4 all failed with "seed step 0 returned no 'id'".
            # 4 of 5 runs lost, and the scenario read as 0/5 called.
            #
            # A book-scoped seed never hits this because the throwaway book is new every run.
            # Anything living in the caller's own library (motifs, arc templates) does, and this
            # loop has already paid for it twice: batch 19's motifs survived across arms and
            # collided by NAME as well as by code.
            return (obj.replace("{book_id}", self.book_id or "")
                       .replace("{chapter_id}", self.chapter_id or "")
                       .replace("{project_id}", self.project_id or "")
                       .replace("{run_word}", self.run_word)
                       .replace("{run_id}", self.run_id))
        if isinstance(obj, dict):
            return {k: self._substitute(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._substitute(v) for v in obj]
        return obj

    # ── teardown ─────────────────────────────────────────────────────────────────────────
    def is_gone(self) -> bool:
        """Did teardown actually work? Asked of the DATABASE, not of the return value.

        A teardown that reports success and leaves the row is worse than one that fails loudly:
        the book stays on the account, `book_list` keeps offering it to the model, and the next
        batch inherits an extra write target that its store diff cannot see. 16 fixtures survived
        one batch exactly this way.
        """
        if not self.book_id:
            return True
        q = self.book_id.replace("'", "''")
        rows = oracle.db_query(BOOK_DB, f"SELECT 1 FROM books WHERE id='{q}'")
        return not rows

    def teardown(self) -> dict:
        """Delete ONLY this fixture, and only after re-reading the row to confirm it is ours.

        The check is deliberately made against the DATABASE rather than against this object's
        own memory of what it created. An in-process assertion only proves the object is
        self-consistent; re-reading proves the id on disk is a throwaway owned by the harness
        account. A DELETE in this loop already removed 10 rows where 3 were meant, and the
        difference was exactly this: trusting a remembered scope instead of confirming it.
        """
        # 🔴 ACCOUNT-SCOPED FIXTURES DO NOT DIE WITH THE BOOK. A seed that creates a WORLD leaves
        # it on the account: worlds are not book-scoped, so `purge_book` cannot see them and the
        # next batch inherits an extra, plausible, wrongly-scoped write target — the same shape
        # as the 16 leaked books, one scope up. Removed FIRST, name-guarded, and only ever the
        # ones this fixture minted.
        out = {}
        try:
            out["worlds"] = self._purge_worlds()
        except Exception as e:  # noqa: BLE001 — a world sweep must never mask a book teardown
            out["worlds_error"] = f"{type(e).__name__}: {e}"
        try:
            out["models"] = self._purge_models()
        except Exception as e:  # noqa: BLE001 — same rule: never mask the book teardown
            out["models_error"] = f"{type(e).__name__}: {e}"
        try:
            out["arc_templates"] = self._purge_arc_templates()
            out["motifs"] = self._purge_motifs()
            out["memories"] = self._purge_memories()
        except Exception as e:  # noqa: BLE001 — same rule: never mask the book teardown
            out["arc_templates_error"] = f"{type(e).__name__}: {e}"
        if self.book_id:
            out.update(purge_book(self.book_id))
        else:
            out.update({"deleted": 0, "reason": "no book was created"})
        # 🔴 LAST, AND ON EVERY PATH. A manifest on disk means "this fixture was never torn
        # down", so removing it before the purges would erase the only record of what still
        # needs removing — but an EARLY RETURN for the no-book case skipped it entirely, and a
        # manifest that is never removed is replayed by every later sweep forever. Caught by the
        # guard, not by reading: the bookless branch is the one a seed-only fixture takes.
        try:
            self._manifest_path().unlink(missing_ok=True)
        except OSError:
            pass
        return out

    def _purge_models(self) -> list[str]:
        """Delete the registered MODELS this fixture's seed created.

        🔴 A REGISTERED MODEL IS ACCOUNT-SCOPED, LIKE A WORLD, AND THIS IS THE SAME LEAK ONE STORE
        OVER. It exists so the four tools the owner's rule excludes — settings_model_update,
        _set_active, _set_favorite and registry_set_skill_enabled — can be measured against an
        object THE RUN OWNS instead of against the account's real models. Those tools were kept out
        of the approved arm precisely because their targets were pre-existing; a fixture that
        creates its own target brings them inside the rule, and a fixture that creates one it
        cannot remove would put them back outside it.

        🔴 AND `settings_model_delete` DOES NOT DELETE. It mints a `confirm_token` and returns —
        so a teardown that just calls it leaves the model in place while reporting success. This
        redeems the token, which the 2026-08-22 owner decision permits for an object the run's own
        fixture created and is tearing down.

        Guarded by PROVENANCE, not by name: the id came back from this fixture's own
        `settings_model_register`. That is the lesson `_purge_worlds` paid for — a name-prefix
        guard silently matched nothing for 35 worlds.
        """
        made = [r["result"] for r in self.seeded
                if r.get("tool") == "settings_model_register" and isinstance(r.get("result"), dict)]
        if not made:
            return []
        from scripts.eval.tool_liveness import confirm as _confirm
        gone = []
        for r in made:
            m = r.get("model") if isinstance(r.get("model"), dict) else r
            mid = m.get("user_model_id") or m.get("id")
            if not mid:
                continue
            res = self.mcp.call("settings_model_delete", {"user_model_id": str(mid)})
            tok = _confirm.find_confirm_token(res)
            if tok:
                ok, code, _ = _confirm.confirm(_tle_auth(), "settings_model_delete", tok)
                if not ok:
                    raise ProvisionError(
                        f"could not confirm the delete of throwaway model {mid} (HTTP {code}). "
                        "Leaving it would put an account-scoped fixture on the account, which is "
                        "the leak this method exists to prevent.")
            gone.append(str(mid))
        return gone

    def _purge_arc_templates(self) -> list[str]:
        """Remove the arc templates this fixture's seed created. THE THIRD ACCOUNT-SCOPED LEAK.

        🔴 MEASURED 2026-08-23: 51 of 57 arc_template rows carry book_id NULL, so `purge_book`
        cannot see them and nothing else ever did. The cost was not theoretical. Batch 15's
        template `throwaway-loop-skeleton-b15` was created 2026-08-20, ARCHIVED by the model on a
        later run — archiving is what that scenario asks for — and never restored. Every run after
        that failed its own seed assertion (`status <> 'archived'` reading 0) and the whole
        scenario provision-failed 5 of 5, which read in the report as a surfacing failure of
        `composition_arc_template_edit` rather than as fixture debris.

        SQL, BECAUSE THE CATALOGUE HAS NO DELETE. The family ships create/update/archive/restore
        and no `composition_arc_template_delete` — archiving would leave the row, and the row is
        what collides on `code`. So the removal is a DELETE by id through the same oracle path the
        seeds already use for their own SQL steps.

        PROVENANCE, NOT A NAME PREFIX — the lesson `_purge_worlds` paid 35 leaked worlds for. The
        ids come from THIS run's own seed results, so a renamed fixture cannot slip the guard and
        the sweep can never reach a row this fixture did not make.
        """
        ids: list[str] = []
        for r in self.seeded:
            if r.get("tool") not in ("composition_arc_extract_template",
                                     "composition_arc_template_create"):
                continue
            res = r.get("result")
            if not isinstance(res, dict):
                continue
            tid = res.get("arc_id") or res.get("id")
            if tid:
                ids.append(str(tid))
        if not ids:
            return []
        quoted = ",".join("'" + i.replace("'", "''") + "'" for i in ids)
        oracle.db_query("loreweave_composition",
                        f"DELETE FROM arc_template WHERE id IN ({quoted})")
        return ids

    def _purge_motifs(self) -> list[str]:
        """Remove the motifs this fixture's seed created. THE FOURTH ACCOUNT-SCOPED LEAK.

        🔴 MEASURED 2026-08-23, AND IT HAD ALREADY EATEN FIFTEEN RUNS. Four motifs seeded
        2026-08-21 06:43 were ARCHIVED by the model at 09:23 — archiving is what a sibling scenario
        asks for — and never restored. From that moment `composition_motif_link_edit` was measured
        against a fixture that was dead in three independent ways at once:

          * it CANNOT BE RECREATED. `uq_motif_user` is UNIQUE(owner_user_id, code) WHERE
            book_id IS NULL, with no status predicate — an archived row still owns its code, so
            every later seed create hits a unique violation.
          * it CANNOT BE RESOLVED. `get_by_codes` filters `status = 'active'`, so the two names
            the prompt asks the model to link resolve to nothing.
          * it ASSERTS GREEN. The seed_assert counted `code IN (...)` with NO status filter, so it
            read 2 off the archived rows and passed. A fixture assertion that cannot see the same
            rows the tool sees is not an assertion.

        That is the batch-15 arc-template defect exactly — D-SEED-FIXTURE-LEFT-ARCHIVED-BREAKS-
        EVERY-LATER-RUN — which was fixed as an INSTANCE and left as a CLASS. It cost the same
        thing twice: a tool that reads as broken in the report while the platform is fine.

        SQL, because archiving is what put the row here and archiving again would not free the
        code. PROVENANCE, not a name prefix: the ids come from THIS run's own seed results.
        """
        ids: list[str] = []
        for r in self.seeded:
            if r.get("tool") != "composition_motif_edit":
                continue
            if (r.get("args") or {}).get("op") != "create":
                continue
            res = r.get("result")
            if not isinstance(res, dict):
                continue
            mid = res.get("motif_id") or res.get("id")
            if mid:
                ids.append(str(mid))
        if not ids:
            return []
        quoted = ",".join("'" + i.replace("'", "''") + "'" for i in ids)
        oracle.db_query("loreweave_composition",
                        f"DELETE FROM motif_link WHERE from_motif_id IN ({quoted}) "
                        f"OR to_motif_id IN ({quoted})")
        oracle.db_query("loreweave_composition", f"DELETE FROM motif WHERE id IN ({quoted})")
        return ids

    def _purge_memories(self) -> list[str]:
        """Remove the memory FACTS this fixture's seed created. THE FIFTH ACCOUNT-SCOPED LEAK,
        and the first one that is not in Postgres at all.

        🔴 FOUND 2026-08-27 BY LEAKING TWO. Running the idempotency probe against
        `memory_forget` left two Fact nodes behind, and only a Cypher read found them: they are
        stored with `project_id` NULL — the account-scoped case `store_snapshot._neo4j`'s own
        docstring already flagged — so the throwaway book's teardown could never see them. They
        were deleted by hand after a SELECT, which is the third time this loop has done that.

        Cypher, because the catalogue's only removal for a fact is `memory_forget`, and forget
        INVALIDATES rather than deletes: the node would stay, carrying the run's content into
        every later memory_search. PROVENANCE, not a content match — the ids come from THIS
        fixture's own `memory_remember` results."""
        ids = [str(r["result"].get("fact_id"))
               for r in self.seeded
               if r.get("tool") == "memory_remember"
               and isinstance(r.get("result"), dict) and r["result"].get("fact_id")]
        if not ids:
            return []
        # 🔴 REFUSED, NOT ESCAPED. The first draft wrote `i.replace("'", "\'")`, which in Python
        # is `"'"` — a no-op that LOOKS like escaping and would have sat here forever, because a
        # fact id is hex and the branch never fires. A DETACH DELETE is not the place for a
        # quoting scheme: an id that is not the shape the tool returns is a bug upstream, and
        # deleting nothing while saying so is the safe answer.
        bad = [i for i in ids if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", i)]
        if bad:
            raise ProvisionError(
                f"memory_remember returned {len(bad)} fact id(s) that are not id-shaped "
                f"({bad[:2]}); refusing to build a DETACH DELETE around them.")
        quoted = ", ".join(f"'{i}'" for i in ids)
        oracle.cypher_query(f"MATCH (f:Fact) WHERE f.id IN [{quoted}] DETACH DELETE f;")
        return ids

    def _purge_worlds(self) -> list[str]:
        """Delete the worlds this fixture's seed created.

        🔴 THIS GUARD NEVER MATCHED, AND 35 WORLDS LEAKED BEHIND IT. It required the world's name
        to start with TITLE_PREFIX. The seeds name their world "Emberfall Reach {run_word}" — on
        purpose, and the reason is 90 lines above this one: an account-scoped fixture called
        "LOOP-THROWAWAY-…" got its NAME passed as a world_id by the model ("I'm having trouble
        accessing the map (ID: LOOP-THROWAWAY-…)"). So the naming decision is right and the
        teardown predicate was right, and between them nothing was ever deleted.

        Measured 2026-08-22: 63 worlds on the harness account, 35 of them "Emberfall Reach %"
        fixtures. `provision.py --sweep` could not see them either — it is scoped to book TITLES,
        and a world is not book-scoped. The same blind spot that hid this from teardown hid it
        from the DATA bar: `store_snapshot` sweeps tables carrying `book_id`, and `worlds`,
        `world_maps`, `map_regions` and `map_markers` carry none.

        THE FIX IS TO STOP GUARDING ON THE NAME. The id came back from THIS RUN'S OWN
        `world_create` call; that provenance is stronger evidence than any string prefix, and it
        cannot drift when someone renames a fixture. The name is still recorded for the log.
        """
        made = [r["result"] for r in self.seeded
                if r.get("tool") == "world_create" and isinstance(r.get("result"), dict)]
        if not made:
            return []
        ids = []
        for r in made:
            w = r.get("world") if isinstance(r.get("world"), dict) else r
            wid = w.get("world_id") or w.get("id")
            if wid:
                self.mcp.call("world_delete", {"world_id": str(wid)})
                ids.append(str(wid))
        return ids


def purge_book(book_id: str) -> dict:
    q = book_id.replace("'", "''")
    rows = oracle.db_query(
        BOOK_DB, f"SELECT title, owner_user_id FROM books WHERE id='{q}'")
    if not rows or not rows[0] or not rows[0][0]:
        return {"deleted": 0, "reason": "no such book"}
    title, owner = rows[0][0], rows[0][1]
    if not title.startswith(TITLE_PREFIX):
        raise ProvisionError(
            f"REFUSING to delete book {book_id}: its title is {title!r}, which this module did "
            f"not create (every fixture is named {TITLE_PREFIX}*). Nothing was deleted.")
    if owner != OWNER_ID:
        raise ProvisionError(
            f"REFUSING to delete book {book_id}: owned by {owner}, not the harness account "
            f"{OWNER_ID}. Nothing was deleted.")

    deleted = {"book_id": book_id, "title": title, "tables": {}}
    # Composition first: its rows reference the book, and a project orphaned by a deleted book
    # is invisible to the book-scoped snapshot — it would accumulate silently, run after run.
    prows = oracle.db_query(COMP_DB, f"SELECT project_id FROM composition_work WHERE book_id='{q}'")
    for pr in prows:
        pid = (pr[0] if pr else "") or ""
        if pid:
            deleted["tables"]["composition(project)"] = pid
            _delete_scoped(COMP_DB, "project_id", pid)
    _delete_scoped(COMP_DB, "book_id", q)
    for db in ("loreweave_glossary", "loreweave_knowledge"):
        _delete_scoped(db, "book_id", q)
    _delete_scoped(BOOK_DB, "book_id", q)
    oracle.db_query(BOOK_DB, f"DELETE FROM books WHERE id='{q}'")
    return deleted


def _delete_scoped(db: str, column: str, value: str) -> None:
    """Delete this book's rows from every table in `db` that carries `column`.

    Table-driven rather than a hand-written list, for the same reason `store_snapshot` is: a
    hand list goes stale the moment someone adds a table, and the failure mode is silent
    leftover rows that the NEXT run reads as pre-existing state.

    🔴 ONE ROUND TRIP PER DATABASE, NOT ONE PER TABLE. The first version issued a separate
    `docker exec psql` per table per pass — around 140 process spawns per database, so a single
    teardown took minutes. That is not merely slow: teardown runs in a `finally` while the next
    scenario is already provisioning, and a minutes-long teardown under concurrency is how 16
    fixtures survived one batch. The leak then handed the model a foreign book to write into on
    the following run. Batching the statements makes teardown fast enough to finish inside the
    window it actually has.

    FK order is unknowable up front, so the whole batch runs TWICE inside the same call and
    every statement is independent (`ON_ERROR_ROLLBACK=on`): a child blocked on the first pass is
    gone by the second, and one failing DELETE cannot abort the rest.
    """
    tables = [(t[0] if t else "") or "" for t in oracle.db_query(
        db, "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
            f"AND column_name='{column}' ORDER BY table_name")]
    tables = [t for t in tables if t]
    if not tables:
        return
    stmts = [f'DELETE FROM public."{t}" WHERE {column}=\'{value}\';' for t in tables]
    sql = "\\set ON_ERROR_ROLLBACK on\n" + "\n".join(stmts + stmts)
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", PG_USER, "-d", db, "-q", "-At"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )


# The name every world seed builds — "Emberfall Reach {run_word}". Deliberately NOT TITLE_PREFIX
# (see Fixture.__init__: a prefix in a NAME gets passed back as an id), which is exactly why the
# book-title-scoped sweep below could never see one.
WORLD_PREFIX = "Emberfall Reach "


def sweep_orphans(older_than_minutes: int = 0) -> list[str]:
    """Delete throwaway books left behind by a crashed run. Prefix-scoped, so it can never
    reach anything but this module's own fixtures."""
    rows = oracle.db_query(
        BOOK_DB, f"SELECT id FROM books WHERE title LIKE '{TITLE_PREFIX}%' "
                 f"AND owner_user_id='{OWNER_ID}' "
                 f"AND created_at < now() - interval '{int(older_than_minutes)} minutes'")
    out = []
    for r in rows:
        bid = (r[0] if r else "") or ""
        if bid:
            purge_book(bid)
            out.append(bid)
    return out


def sweep_orphan_translation_jobs() -> int:
    """Translation jobs whose BOOK no longer exists — debris this harness makes every run.

    🔴 MEASURED 2026-08-24: sixty translation jobs were visible to the test account and NOT ONE
    was controllable. Every translation scenario SQL-seeds a pending job on its throwaway book;
    teardown removes the book and the job row survives, because it lives in another database with
    no FK to it. `jobs_list` goes on listing all sixty with control_caps ["cancel"], while
    translation_job_control resolves through the job's book and refuses every one of them with
    "not found or not accessible" — correctly.

    That cost a probe: ids read straight from translation_jobs looked perfectly good and every
    call refused, and the reason was not the tool. A harness that leaves undeletable rows behind
    eventually measures its own debris.

    Book-scoped and conservative by construction: a job is removed ONLY when its book_id is absent
    from loreweave_book.books, so a live book's jobs are never touched.
    """
    rows = oracle.db_query("loreweave_translation",
                           "SELECT DISTINCT book_id::text FROM translation_jobs")
    book_ids = [r[0] for r in (rows or []) if r and r[0]]
    if not book_ids:
        return 0
    quoted = ",".join("'" + b.replace("'", "''") + "'" for b in book_ids)
    live = oracle.db_query("loreweave_book", f"SELECT id::text FROM books WHERE id IN ({quoted})")
    alive = {r[0] for r in (live or []) if r and r[0]}
    orphan = [b for b in book_ids if b not in alive]
    if not orphan:
        return 0
    oq = ",".join("'" + b.replace("'", "''") + "'" for b in orphan)
    n = oracle.db_query("loreweave_translation",
                        f"WITH d AS (DELETE FROM translation_jobs WHERE book_id IN ({oq}) "
                        f"RETURNING 1) SELECT count(*)::text FROM d")
    sweep_phantom_job_projections()
    try:
        return int(n[0][0])
    except (IndexError, TypeError, ValueError):
        return 0


def sweep_phantom_job_projections() -> int:
    """Projection rows whose JOB ROW is gone — debris the sweep above makes, on the surface that
    advertises control_caps.

    🔴 MEASURED 2026-08-28, AND THIS SWEEP IS WHAT CAUSED IT. `sweep_orphan_translation_jobs`
    deletes from `loreweave_translation.translation_jobs` and never touched
    `loreweave_jobs.job_projection`, which is a SEPARATE DATABASE with no FK to it. So every run
    turned an orphaned-book job into a PHANTOM: a projection row for a job that no longer exists
    anywhere.

        translation_jobs                                     6 rows, 0 controllable
        job_projection, service=translation, controllable    92 rows
        ...of those 92, job_id present in translation_jobs    0

    That is strictly worse than the debris it replaced. `job_projection` is the table `jobs_list`
    reads, so all 92 were advertised with control_caps ["cancel"] against a job row that cannot be
    found, and every cancel would fail. The row this sweep was written for —
    D-JOBS-LIST-ADVERTISES-CANCEL-ON-JOBS-THAT-CANNOT-BE-CANCELLED — is about exactly that, so the
    harness half of the fix was manufacturing fresh instances of the product half.

    CONSERVATIVE BY CONSTRUCTION, and deliberately narrower than the leak it repairs:
      * the HARNESS ACCOUNT only (`owner_user_id = OWNER_ID`) — a real user's rows are never read
        or written, which matters because a projection row is legitimately allowed to outlive
        nothing here except this harness's own deletes;
      * `service='translation'` only — the one producer this harness SQL-seeds and deletes;
      * and only where the job_id is genuinely ABSENT from `translation_jobs`, resolved by
        fetching the live ids and deleting by explicit id list rather than by a predicate, because
        the two tables live in different databases and no single statement can join them.

    A projection row is written AFTER its job row (producer -> outbox -> relay), so a row whose
    job_id is missing was deleted, never merely not-yet-created. There is no window this races.
    """
    proj = oracle.db_query(
        "loreweave_jobs",
        "SELECT job_id::text FROM job_projection "
        f"WHERE service='translation' AND owner_user_id='{OWNER_ID}'")
    proj_ids = [r[0] for r in (proj or []) if r and r[0]]
    if not proj_ids:
        return 0
    live = oracle.db_query("loreweave_translation", "SELECT job_id::text FROM translation_jobs")
    alive = {r[0] for r in (live or []) if r and r[0]}
    phantom = [j for j in proj_ids if j not in alive]
    if not phantom:
        return 0
    pq = ",".join("'" + j.replace("'", "''") + "'" for j in phantom)
    n = oracle.db_query(
        "loreweave_jobs",
        f"WITH d AS (DELETE FROM job_projection WHERE job_id IN ({pq}) "
        f"AND owner_user_id='{OWNER_ID}' RETURNING 1) SELECT count(*)::text FROM d")
    try:
        return int(n[0][0])
    except (IndexError, TypeError, ValueError):
        return 0


def sweep_orphan_worlds(older_than_minutes: int = 0) -> list[str]:
    """🔴 A WORLD IS NOT BOOK-SCOPED, SO THE BOOK SWEEP ABOVE NEVER SAW ONE.

    Measured 2026-08-22: 63 worlds on the harness account, 35 of them fixtures. Two separate
    guards both failed to reach them — `_purge_worlds` required a name prefix the seeds
    deliberately do not use, and this sweep is scoped to book TITLES. Every world/map arm this
    loop has ever run left its world behind.

    Scoped to the OPERATION rather than by a global predicate: this account's own worlds, named
    with the prefix these seeds build, and nothing else. The 28 remaining worlds on the account
    belong to earlier smoke suites (`C21 Gateway Smoke`, `S10 World …`, `E2E …`) — not this
    module's to delete, and left alone.
    """
    rows = oracle.db_query(
        BOOK_DB, f"SELECT id, name FROM worlds WHERE name LIKE '{WORLD_PREFIX}%' "
                 f"AND owner_user_id='{OWNER_ID}' "
                 f"AND created_at < now() - interval '{int(older_than_minutes)} minutes'")
    mcp = MCPDirect()
    out = []
    for r in rows:
        wid = (r[0] if r else "") or ""
        if not wid:
            continue
        try:
            mcp.call("world_delete", {"world_id": str(wid)})
            out.append(wid)
        except Exception as e:  # noqa: BLE001 — report, never mask the rest of the sweep
            print(f"  ! world {wid} ({r[1] if len(r) > 1 else '?'}): {type(e).__name__}: {e}")
    return out


def sweep_manifests() -> dict:
    """Run the per-run purges for every fixture that was built and never torn down.

    D-HARNESS-sweep-DOES-NOT-COVER-ACCOUNT-SCOPED-FIXTURES. The other sweeps in this file are
    scoped by NAME — book titles, world names — which is why none of them could reach an arc
    template or a motif: those seeds name themselves nine different ways and 50 of the 51
    account-scoped templates on this account belong to other suites. This one is scoped by
    PROVENANCE: it replays the ids the fixture itself recorded, through the fixture's own purge
    methods, so it can only ever remove a row this harness made.

    A failure on one manifest must not abandon the rest — the point of a sweep is that it runs
    when something has already gone wrong."""
    out: dict = {"manifests": 0, "purged": [], "errors": []}
    if not MANIFEST_DIR.is_dir():
        return out
    for f in sorted(MANIFEST_DIR.glob("*.json")):
        out["manifests"] += 1
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            out["errors"].append(f"{f.name}: unreadable ({type(e).__name__})")
            continue
        try:
            fx = Throwaway.from_manifest(data)
            res = fx.teardown()
            out["purged"].append({"run_id": data.get("run_id"), **{
                k: v for k, v in res.items() if v}})
        except Exception as e:  # noqa: BLE001 — one bad manifest must not end the sweep
            out["errors"].append(f"{f.name}: {type(e).__name__}: {e}"[:200])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="manual")
    ap.add_argument("--keep", action="store_true", help="build and print, do not tear down")
    ap.add_argument("--sweep", action="store_true", help="delete every leftover throwaway book")
    a = ap.parse_args()
    if a.sweep:
        # PROVENANCE FIRST, prefixes as the backstop. A manifest knows the fixture's book AND its
        # account-scoped rows, so replaying it removes both in the right order; running the
        # book sweep first would delete the book out from under a purge that still needed it.
        m = sweep_manifests()
        print(f"replayed {m['manifests']} un-torn-down fixture manifest(s): "
              f"{len(m['purged'])} purged, {len(m['errors'])} error(s)")
        for e in m["errors"]:
            print("  !", e)
        gone = sweep_orphans()
        print(f"swept {len(gone)} throwaway book(s)")
        # Worlds are NOT book-scoped, so they need their own pass — see sweep_orphan_worlds.
        w = sweep_orphan_worlds()
        print(f"swept {len(w)} throwaway world(s)")
        j = sweep_orphan_translation_jobs()
        print(f"swept {j} orphaned translation job(s)")
        return 0
    fx = Throwaway(a.label).build()
    print(json.dumps({"book_id": fx.book_id, "chapter_id": fx.chapter_id,
                      "project_id": fx.project_id, "title": fx.title}, indent=2))
    if not a.keep:
        print(json.dumps(fx.teardown(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
