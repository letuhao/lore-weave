"""A hex nonce in a fixture's NAME is a plausible wrong answer handed to the model.

FOUND 2026-08-21, batch 29's second arm. The account-scoped scenarios need their fixture to be
unique among the account's 200 worlds, so they named it "Emberfall Reach {run_id}" and the seed
duly created "Emberfall Reach 1d76719e". Then the model read that sentence and passed the hex
suffix as the identifier:

    "I'm having trouble accessing the map 'The Ashen Coast' (ID: `a671b6c9`)."
    "It appears the ID provided might not be a valid UUID."

The tools refused, correctly. But nothing about the TOOLS was measured: the fixture had put an
id-shaped token in a human-readable name, and the run only established that the model will
reach for one when it is offered. A measurement whose fixture supplies a convincing wrong answer
is measuring the fixture.

THE FIRST ARM OF THIS SAME BATCH failed the other way -- the prompt was not substituted at all,
so the model saw the literal "{run_id}" and said so. Both arms are kept. Together they are a
small lesson about nonces: the seed and the prompt must agree (fixed in fe_runner), AND the
token they agree on must be shaped like the thing it is standing in for.

SO THERE ARE NOW TWO. `{run_id}` stays hex and belongs in CODES -- motif slugs, steering-rule
names, anything machine-keyed, where a hex tail is exactly right and no one reads it as prose.
`{run_word}` is the same nonce rendered consonant-vowel ("Sitamanu", "Kamaremo", "Latamite") and
belongs in anything a person would read as a NAME.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import provision  # noqa: E402

SCENARIOS = sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json"))

_UUIDISH = re.compile(r"^[0-9a-f]{6,}$", re.IGNORECASE)


class TestTheWordNonceCannotBeMistakenForAnId:
    def test_it_is_not_hex(self):
        for seed in ("1d76719e", "a671b6c9", "568f3b71", "00000000", "ffffffff"):
            w = provision._pronounceable(seed)
            assert not _UUIDISH.match(w), f"{seed} -> {w!r} still reads as an id"

    def test_it_alternates_consonant_and_vowel(self):
        w = provision._pronounceable("1d76719e").lower()
        for i, ch in enumerate(w):
            in_vowels = ch in provision._VOWELS
            assert in_vowels == (i % 2 == 1), f"{w!r} is not consonant-vowel shaped at {i}"

    def test_it_is_deterministic(self):
        assert provision._pronounceable("1d76719e") == provision._pronounceable("1d76719e")

    def test_different_runs_get_different_words(self):
        """Five repeats of one batch must not collide — that is the whole point of a nonce."""
        words = {provision._pronounceable(h) for h in
                 ("1d76719e", "a671b6c9", "568f3b71", "deadbeef", "01234567")}
        assert len(words) == 5

    def test_it_reads_as_a_name(self):
        w = provision._pronounceable("1d76719e")
        assert w[0].isupper() and w[1:].islower(), f"{w!r} is not capitalised like a name"


class TestTheSubstitutionKnowsBothForms:
    def _fixture(self):
        t = provision.Throwaway.__new__(provision.Throwaway)
        t.run_id, t.run_word = "1d76719e", provision._pronounceable("1d76719e")
        t.book_id = t.chapter_id = t.project_id = ""
        t._steps = []
        return t

    def test_run_word_is_substituted(self):
        word = provision._pronounceable("1d76719e")
        assert self._fixture().substitute_text("Emberfall Reach {run_word}") == (
            f"Emberfall Reach {word}")
        assert word.isalpha(), "the name nonce must be letters only"

    def test_run_id_still_works_for_codes(self):
        assert self._fixture().substitute_text("emberfall-vein-b27-{run_id}") == (
            "emberfall-vein-b27-1d76719e")

    def test_run_word_does_not_eat_run_id(self):
        """Naive ordering would leave a dangling '{run_word}' -> '<hex>word}'."""
        out = self._fixture().substitute_text("{run_word}/{run_id}")
        assert out == f"{provision._pronounceable('1d76719e')}/1d76719e"
        assert "{" not in out


#: Scenario files written BEFORE {run_word} existed that suffix a display name with the hex
#: nonce. FROZEN, and it may only SHRINK. These are batches already run and concluded; their
#: evidence is what it is and rewriting the file now would not change a measurement that has
#: already happened, so they are grandfathered rather than edited. A NEW scenario doing this
#: fails, and a listed file that has been fixed also fails, so the list cannot rot upward.
#:
#: Worth knowing when reading those arms: batch 27's motif was seeded as
#: "Emberfall Vein {run_id}", so the same id-shaped-name trap was present for
#: composition_motif_bind_edit's sixteen arms. That is NOT the diagnosis for them — their
#: failure was the model's degenerate `<tool_call|>` output, measured repeatedly — but a
#: display name carrying a hex tail was in the prompt each time, and anyone re-opening that
#: investigation should know it was there.
GRANDFATHERED_HEX_NAMES = {
    "scenarios-b20-more.json", "scenarios-b20-rerun.json", "scenarios-b20-search.json",
    "scenarios-b22-rerun.json", "scenarios-b23-rerun.json", "scenarios-batch20.json",
    "scenarios-batch21.json", "scenarios-batch22.json", "scenarios-batch23.json",
    "scenarios-batch24.json", "scenarios-batch25.json", "scenarios-batch26.json",
    "scenarios-batch27.json",
}

#: VERBATIM RE-RUN ARMS of a grandfathered file: {extract -> the file it was lifted from}.
#:
#: 🔴 TWO CORRECT RULES COLLIDE HERE. The nonce rule says a NEW scenario must not put a hex
#: nonce in a display name. The re-measurement rule says an arm that exists to be compared with
#: an older batch must be byte-faithful to it — scenarios-c-bindarc1.json says so in its own
#: note: "extracted VERBATIM ... Nothing in the scenario is changed: same prompt, same seed,
#: same falsifier." Editing the name to obey the nonce rule would silently destroy the only
#: thing the file is for, and the comparison would go on being quoted as if it still held.
#:
#: So the exemption is granted to the EXTRACT because its SOURCE already has it — and it is
#: granted only for as long as the extract really is an extract. The test below re-reads both
#: files and compares the fields that decide a run. Edit the copy and the exemption evaporates,
#: which is the same shape as the override rule in the measured-turn gate: an escape hatch that
#: verifies its own justification is not an escape hatch.
VERBATIM_EXTRACTS = {
    "scenarios-c-bindarc1.json": ("scenarios-batch26.json", "composition-motif-bind-edit"),
}

#: The fields that decide what a run DOES. Two files agreeing on these are the same experiment;
#: `_note` and `prompt_source` are commentary and may differ.
_VERBATIM_FIELDS = ("prompt", "seed", "tool_under_test", "expect_tool", "tier", "intent")


class TestScenariosDoNotPutAHexNonceInAName:
    """The rule this was written for, applied to every scenario file in the loop."""

    def _offenders(self):
        # A NAME here means a value under a "name"/"title"/"label" key.
        pat = re.compile(r'"(?:name|title|label)"\s*:\s*"[^"]*\{run_id\}')
        return {f.name for f in SCENARIOS if pat.search(f.read_text(encoding="utf-8"))}

    def test_no_new_scenario_suffixes_a_display_name_with_run_id(self):
        new = self._offenders() - GRANDFATHERED_HEX_NAMES - set(VERBATIM_EXTRACTS)
        assert not new, (
            "these scenarios put the HEX nonce in a display name, which the model reads as an "
            f"identifier — use {{run_word}}: {sorted(new)}")

    def test_the_baseline_only_shrinks(self):
        stale = GRANDFATHERED_HEX_NAMES - self._offenders()
        assert not stale, (
            "these files no longer put a hex nonce in a name — drop them from "
            f"GRANDFATHERED_HEX_NAMES so the list cannot rot upward: {sorted(stale)}")

    def test_a_verbatim_extract_is_STILL_verbatim(self):
        """🔴 THE EXEMPTION VERIFIES ITSELF, or it is just a place to hide an offender.

        An extract keeps the nonce exemption only because it is a faithful copy of a file that
        already had one. The moment someone edits the copy — reasonably, to fix the very nonce
        this rule is about — it stops being the experiment it claims to re-run, and it loses the
        exemption here rather than keeping it silently."""
        assert VERBATIM_EXTRACTS, "the extract list is empty — the exemption has been undone"
        for extract, (source, sid) in sorted(VERBATIM_EXTRACTS.items()):
            assert source in GRANDFATHERED_HEX_NAMES, (
                f"{extract} claims to extract {source}, which is NOT grandfathered — the "
                "exemption has nothing to inherit")
            a = self._scenario(extract, sid)
            b = self._scenario(source, sid)
            assert a is not None, f"{extract} has no scenario {sid!r}"
            assert b is not None, f"{source} has no scenario {sid!r}"
            differing = [f for f in _VERBATIM_FIELDS if a.get(f) != b.get(f)]
            assert not differing, (
                f"{extract}::{sid} is no longer verbatim against {source} — it differs on "
                f"{differing}. It cannot claim {source}'s nonce exemption, and any comparison "
                "drawn between the two batches is no longer like-for-like.")

    @staticmethod
    def _scenario(filename, sid):
        for f in SCENARIOS:
            if f.name != filename:
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            return next((s for s in d.get("scenarios", []) if s.get("id") == sid), None)
        return None

    def test_prompts_do_not_carry_the_hex_nonce(self):
        offenders = [f.name for f in SCENARIOS
                     if re.search(r'"prompt"\s*:\s*"[^"]*\{run_id\}', f.read_text(encoding="utf-8"))]
        assert not offenders, (
            f"a prompt sentence must not contain the hex nonce — use {{run_word}}: {offenders}")
