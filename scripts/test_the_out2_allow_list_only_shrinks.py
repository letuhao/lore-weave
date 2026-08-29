"""DQ-T52's build note, which is the part that keeps the rest honest.

    Owner 2026-08-28: "TRIGGER ON LIST SHAPE, seed today's offenders as a flip-pending ALLOW, and
    EXTEND TO THE GO REGISTRATIONS … BUILD NOTE: the allow-list may only SHRINK. That is this
    loop's standing rule and it is what stops a seeded baseline from becoming a place to hide new
    violations."

🔴 A SEEDED BASELINE WITHOUT A RATCHET IS AN INVITATION. The widened lint goes red on 21 tools
today; seeding them is what lets it go green on this tree and RED on the next new one. But the
same row that records debt is one line away from being where the next offender is buried, and the
person burying it will be under time pressure and will mean well.

So the seed is recorded in contracts/out2-allow-baseline.json and this guard fails on any key
that was not in it. Removing a key — draining the debt — is always allowed, which is the only
direction the list is supposed to move.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "contracts" / "out2-allow-baseline.json").read_text(encoding="utf-8"))


def _lint():
    spec = importlib.util.spec_from_file_location(
        "out2lint", ROOT / "scripts" / "context-budget-defaults-lint.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


LINT = _lint()


class TestTheAllowListOnlyShrinks:
    def test_no_key_was_added_after_the_seed(self):
        added = sorted(set(LINT.ALLOW) - set(BASELINE["seeded"]))
        assert not added, (
            f"{len(added)} tool(s) were ADDED to the OUT-2 allow-list after the DQ-T52 seed: "
            f"{added}. The list may only SHRINK — a new offender is a defect to fix or a "
            "decision to record, never a row to append here."
        )

    def test_draining_a_row_is_allowed(self):
        """The ratchet must not freeze the debt in place. Removing keys is the POINT."""
        drained = set(BASELINE["seeded"]) - set(LINT.ALLOW)
        assert drained or True  # never fails; documents that shrinking is legal
        assert len(LINT.ALLOW) <= BASELINE["count"], (
            f"the allow-list grew from {BASELINE['count']} to {len(LINT.ALLOW)}"
        )

    def test_the_baseline_is_not_empty_so_the_guard_is_not_vacuous(self):
        """🔴 A GUARD OVER AN EMPTY SET PASSES FOREVER. This loop has shipped one of those before,
        so the baseline's own size is asserted."""
        assert BASELINE["count"] == 21
        assert len(BASELINE["seeded"]) == 21


class TestTheWidenedTriggerIsRealAndScoped:
    def test_it_recognises_a_list_shape(self):
        for name in ("glossary_list_unknown_entities", "book_search", "composition_arc_list",
                     "glossary_curation_list", "kg_list_templates"):
            assert LINT.is_list_shaped(name), name

    def test_it_does_NOT_fire_on_a_single_item_tool(self):
        """The standard's own stated exemption: 'a single-item tool — has detail, no limit — is
        EXEMPT'. Widening the trigger must not swallow it."""
        for name in ("book_read", "glossary_get_entity", "composition_get_work",
                     "kg_view_read", "jobs_get"):
            assert not LINT.is_list_shaped(name), name

    def test_a_substring_is_not_a_shape(self):
        """`_listener`/`blocklist` contain "list" and are not list tools. The pattern is anchored
        on word boundaries for the same reason CP-4.d was deleted — a substring is not a
        declaration."""
        assert not LINT.is_list_shaped("book_blocklist_read")
        assert not LINT.is_list_shaped("registry_listener_create")


class TestTheGoHalfIsActuallyWired:
    """The owner: 'the Go half is the larger part and is the point … a Python-only version would
    report a clean bill of health over a minority of the population.'"""

    def test_go_registration_files_are_found(self):
        files = LINT.iter_go_files()
        assert len(files) >= 20, f"only {len(files)} Go registration files found"
        assert any("glossary-service" in f for f in files)

    def test_the_seed_contains_GO_tools_not_only_python(self):
        go_seeded = [k for k in BASELINE["seeded"]
                     if k.startswith(("glossary-service::", "agent-registry-service::"))]
        assert len(go_seeded) >= 10, (
            f"only {len(go_seeded)} Go tools in the seed — the Go scanner is not reaching them, "
            "and a Python-only lint is exactly what the ruling rejected"
        )
