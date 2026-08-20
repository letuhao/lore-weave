"""D-CANON-GUARD-SKIPPED-WHOLE-CHAPTER — the guard that did not run, and the check that now does.

The measurement, on a real chapter rather than a probe: FullArc book (10k words of existing
prose, a 31-scene plan), four authored scenes, 8,116 words generated 2026-08-01. The drafter
invented **"Mira"** — 7 mentions across 3 of the 4 scenes, given the mentor role that explains
the chapter's central mechanic. The book contains **"Mina"** twice and **"Mira" zero times**;
its cast is Cassius (36) and Silas (29).

Every scene reported `canon=skipped_no_cast`, because `run_canon_reflect` returned a green
before doing anything whenever the book had no bound glossary entities. "Nothing to check" was
exactly backwards: a book whose cast was never extracted is the book where the model has
nothing to anchor a name against.

These tests hold two things: the check itself (including its negative control and its blind
spot), and — more importantly — that it runs on the path that used to return early.
"""
from __future__ import annotations

import pytest

from app.engine.name_grounding import NEAR_MISS_MAX_DISTANCE, audit_names, extract_names, known_names_from_cast

GROUNDING = (
    "<beat>goal=anchor the street</beat>\n"
    "<present>Elara, the cartographer. Cassius, her master. Silas the Traveler. "
    "Mina, a junior scribe.</present>\n"
    "<recent>Elara knelt in the Void. Cassius had not followed her down. "
    "Oakhaven was gone from every map.</recent>"
)


# ══ extraction ══

def test_a_mid_sentence_capital_is_a_name():
    assert "Elara" in extract_names("The room was cold. Elara did not move. Beside Elara, ash.")


def test_a_sentence_opening_word_is_not_a_name():
    """No stoplist: a proper name occurs capitalised MID-sentence, an ordinary word does not.
    That one property does the work, and does not need to enumerate English."""
    names = extract_names("The door opened. She waited. But nothing came. Then it did.")
    assert names == set()


def test_a_name_that_also_opens_a_sentence_still_counts():
    assert "Cassius" in extract_names("Cassius spoke. The room went quiet, and Cassius sat.")


def test_extraction_is_empty_on_empty_text():
    assert extract_names("") == set()


# ══ the finding this was built for ══

def test_the_invented_name_from_the_real_chapter_is_reported():
    """The case this module exists for, verbatim from the run that exposed it."""
    a = audit_names("Elara knelt. Beside her, Mira lifted the quill.", GROUNDING)
    assert a.method == "capitalised_latin"
    assert "Mira" in a.unanchored


def test_a_four_letter_name_gets_NO_near_miss_claim_even_though_one_looks_obvious():
    """"Mira" IS one edit from "Mina" — and the claim is still withheld, on purpose.

    The same run produced "Weaver's **Lane**" → near miss of "**Vane**": also length 4, also
    distance 1, and a completely false accusation about a load-bearing character. No threshold
    separates those two pairs, so claiming either means claiming both. Withdrawing the claim
    costs an annotation; making it costs the author's trust in every annotation.

    `Mira` is still REPORTED — as unanchored, which is the actionable half."""
    a = audit_names("Elara knelt. Beside her, Mira lifted the quill. The Lane was empty.",
                    GROUNDING + " Vane holds the Ledger.")
    assert "Mira" in a.unanchored and "Lane" in a.unanchored
    assert a.near_misses == []


def test_a_near_miss_is_claimed_where_the_name_is_long_enough_to_mean_it():
    """At seven characters a two-edit coincidence is no longer cheap."""
    a = audit_names("She turned to Cassuis and waited.", GROUNDING)
    hit = next(n for n in a.near_misses if n["name"] == "Cassuis")
    assert hit["closest"] == "Cassius" and hit["distance"] <= 2


def test_a_possessive_is_not_a_different_name_from_the_name():
    """Measured: the first version reported `Elara’s` as a NEAR MISS of `Elara` — the check
    accusing a name of being a corruption of itself — and `Don't`, `He's`, `You'll` as
    invented characters. Roughly half of all its findings on the real chapter."""
    a = audit_names("The ink took Elara’s hand. Cassius's shadow fell. He's gone, she said.",
                    GROUNDING)
    assert a.clean, f"{a.unanchored} {a.near_misses}"


def test_a_wholly_new_name_is_unanchored_not_a_near_miss():
    a = audit_names("Elara met Thornwick at the bridge.", GROUNDING)
    assert "Thornwick" in a.unanchored
    assert not any(n["name"] == "Thornwick" for n in a.near_misses)


# ══ the negative control — a detector that only ever fires is not a detector ══

def test_a_draft_using_only_known_names_is_clean():
    a = audit_names(
        "Elara knelt in the Void. Cassius watched. Silas had gone ahead to Oakhaven.",
        GROUNDING)
    assert a.clean, f"false positives: {a.unanchored} {a.near_misses}"


def test_prose_with_no_names_at_all_is_clean():
    a = audit_names("The ink bled from the air. Nothing moved. The cold did not lift.",
                    GROUNDING)
    assert a.clean


def test_case_differences_do_not_manufacture_a_finding():
    assert audit_names("ELARA screamed. elara wept.", GROUNDING).clean is True


# ══ the blind spot, declared rather than hidden ══

@pytest.mark.parametrize("lang", ["zh", "ja", "ko", "th", "zh-Hant"])
def test_a_caseless_script_reports_that_it_cannot_see(lang):
    """Capitalisation does not exist in these scripts. Reporting "clean" would be a silent
    blind spot and reporting findings would be manufactured — so it reports the METHOD.
    Same discipline `realised_words` follows."""
    a = audit_names("妲己走進大殿。", GROUNDING, language=lang)
    assert a.method == "caseless_script" and a.clean


def test_no_grounding_names_claims_nothing():
    """An empty book would make every name unanchored — true, useless, and a flood on exactly
    the runs where the model was given nothing."""
    a = audit_names("Elara met Cassius.", "no capitalised names here at all")
    assert a.method == "empty" and a.clean


def test_a_short_token_is_not_near_missed_into_anything():
    """At 3 characters an edit distance of 2 relates almost any two words."""
    a = audit_names("She saw Ash fall.", "<present>Ana</present> The road went on past Ana.")
    assert not a.near_misses


def test_the_near_miss_threshold_is_tight_enough_to_mean_something():
    assert NEAR_MISS_MAX_DISTANCE <= 2


# ══ THE REGRESSION: it must run where the old code returned early ══

@pytest.mark.asyncio
async def test_a_book_with_no_bound_cast_is_still_checked():
    """The whole finding in one test. `run_canon_reflect` opened with

        if not cast_glossary_ids:
            return draft, ReflectResult(resolved=True, status="skipped_no_cast"), 0

    so the 8,116-word chapter that exposed this was generated with ZERO checking, and the
    invented character passed unremarked in three scenes."""
    from types import SimpleNamespace

    from app.engine.canon_reflect import run_canon_reflect

    text, result, tokens = await run_canon_reflect(
        knowledge=None, llm=None, user_id=__import__("uuid").uuid4(),
        project_id=__import__("uuid").uuid4(),
        cast_glossary_ids=[],                       # ← the branch that skipped everything
        scene_sort_order=1,
        draft="Elara knelt. Beside her, Mira lifted the quill.", packed_prompt=GROUNDING,
        profile=SimpleNamespace(source_language="en"),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100,
    )
    assert result.status == "skipped_no_cast"        # the gone-cast check still cannot run
    assert result.coverage == ["name_grounding"], "…but SOMETHING must have run"
    assert "Mira" in result.unanchored_names, "the invented name must be reported"
    assert tokens == 0 and text == "Elara knelt. Beside her, Mira lifted the quill."


@pytest.mark.asyncio
async def test_coverage_is_empty_when_nothing_could_be_verified():
    """An empty `coverage` is the honest report for a run that checked nothing — and it is
    what a caller can act on, unlike `resolved=True` with `violations=[]`."""
    from types import SimpleNamespace

    from app.engine.canon_reflect import run_canon_reflect

    _t, result, _n = await run_canon_reflect(
        knowledge=None, llm=None, user_id=__import__("uuid").uuid4(),
        project_id=__import__("uuid").uuid4(),
        cast_glossary_ids=[], scene_sort_order=1,
        draft="妲己走進大殿。", packed_prompt=GROUNDING,
        profile=SimpleNamespace(source_language="zh"),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100,
    )
    assert result.coverage == []
    assert result.name_check_method == "caseless_script"
    assert result.resolved is True, "still not a blocker — but now it says it verified nothing"


def test_the_prompt_forbids_inventing_a_name_and_offers_the_alternative():
    """A model writing fiction does not read a NAME as a "fact", so "never introduce facts
    beyond what is given" did not cover it. Forbidding alone is also not enough — the passage
    may genuinely need someone the context never named."""
    from app.engine.cowrite import build_messages
    from app.packer.profile import NEUTRAL

    system = build_messages("ctx", NEUTRAL, "draft_scene")[0]["content"]
    assert "do NOT invent a new proper name" in system.replace("Do NOT", "do NOT")
    assert "role or description" in system, "must offer the unnamed-role alternative"


# ══ noise filtering — measured on 19,494 words of real chapters, not invented ══

def test_onomatopoeia_in_emphasis_is_not_a_name():
    """The single biggest false-positive source on the real run: `*Thump. Thump.*`,
    `*Scritch.*`, `*Shhh.*`, `*Tear. Silence.*` — seven of twelve findings, all emphasis."""
    a = audit_names("The sound came again. *Thump. Thump.* Then *Scritch. Scritch.* below.",
                    GROUNDING)
    assert a.clean, f"{a.unanchored}"


def test_an_interior_shout_in_emphasis_is_not_a_name():
    a = audit_names("The pressure forced her down. *Take it,* the sensation screamed. "
                    "She grasped the concept of *Self*.", GROUNDING)
    assert a.clean, f"{a.unanchored}"


def test_a_dialogue_opener_is_not_a_name():
    a = audit_names('"Please," she choked out. "Hold. Stay." Elara did not move.', GROUNDING)
    assert a.clean, f"{a.unanchored}"


def test_a_plural_of_a_known_name_is_the_same_name():
    """`Scribes` is not a near miss of `Scribe`; it is the plural. Two of the run's four
    near-miss claims were this one case."""
    a = audit_names("The Scribes had kept the secret for a century.",
                    GROUNDING + " <lore>The Scribe lineage guards the maps.</lore>")
    assert a.clean, f"{a.unanchored} {a.near_misses}"


def test_the_filters_do_NOT_silence_a_real_invention():
    """The control for all of the above. Over-filtering would turn this module back into the
    thing it replaced — a check that cannot fail."""
    a = audit_names('Elara knelt. Beside her, Mira lifted the quill. "Now," Mira said.',
                    GROUNDING)
    assert "Mira" in a.unanchored, "narrative-position invented name must still fire"


def test_a_coined_concept_outside_quotes_still_fires():
    """The one survivor on the real run, and it is a TRUE positive: the model coined "the
    Unmaking", a capitalised concept appearing nowhere in what it was given."""
    a = audit_names("She would introduce the concept of the Unmaking to a young world.",
                    GROUNDING)
    assert "Unmaking" in a.unanchored


# ── ML-2: the equivalence key is a fold, and what that does and does not buy ──────────────

def test_swapping_lower_for_the_FOLD_changed_nothing_on_this_extractors_alphabet():
    """The honest half, and it is a RETRACTION.

    I wrote that `.lower()` would report an equivalent name as unanchored — a fabricated
    finding — then measured it. Over every name `_TOKEN` can emit (basic Latin + Latin-1
    capitals, per the module docstring's "Script honesty" note) the two agree on **every**
    input. The failure needs a full-width or Han name and this extractor cannot produce one,
    so it was unreachable through this path.

    Pinned so the next reader does not re-derive the overclaim from the gate's message, and so
    that a widening of `_TOKEN` shows up here as a CHANGED answer rather than as silence.
    """
    from loreweave_extraction.name_normalize import normalize_entity_name
    from app.engine.name_grounding import _TOKEN

    heads = [chr(c) for c in list(range(0x41, 0x5B)) + list(range(0xC0, 0xD7)) + list(range(0xD8, 0xDF))]
    tails = [chr(c) for c in list(range(0x61, 0x7B)) + list(range(0xE0, 0xF7)) + list(range(0xF8, 0x100))]
    disagreements = [
        n for h in heads for t in tails
        if _TOKEN.fullmatch(n := f"{h}{t}ra") and n.lower() != normalize_entity_name(n)
    ]
    assert disagreements == [], (
        f"`.lower()` and the fold now DISAGREE on {len(disagreements)} extractable name(s) — "
        f"e.g. {disagreements[:3]}. The swap is no longer neutral; re-read what changed."
    )


def test_the_FOLD_is_the_primitive_a_widened_extractor_would_need():
    """Why the swap is still right despite buying nothing today: the extractor's Latin-only
    alphabet is the ONLY thing that made `.lower()` safe. These are the cases that appear the
    moment `_TOKEN` widens for CJK books — which the module docstring already names as the
    obvious next step."""
    from loreweave_extraction.name_normalize import normalize_entity_name

    for a, b in (("Ｅｌａｒａ", "Elara"),   # full-width vs ASCII
                 ("靈石", "灵石"),          # traditional vs simplified Han
                 ("STRASSE", "Strasse")):  # case
        assert normalize_entity_name(a) == normalize_entity_name(b), f"{a!r} vs {b!r}"
        if a.lower() == b.lower():
            continue
        assert True, "and `.lower()` does NOT equate them — which is the point"
    # the discriminating one, asserted rather than implied:
    assert "Ｅｌａｒａ".lower() != "Elara".lower()
    assert normalize_entity_name("Ｅｌａｒａ") == normalize_entity_name("Elara")


# ── D-NAME-GROUNDING-USES-PROMPT-PROXY-IN-PRODUCTION ────────────────────────────────────────
# The live call was `audit_names(draft, packed_prompt, language)` with `known_names` never
# passed, so production compared the draft against the DRAFTER'S OWN INPUT. This module's
# docstring already said what that is worth — "a check whose input and whose expectation come
# from the same place verifies nothing" — and the deferral measured it: with the authored cast
# the invented name is caught, through the live path it reported `unanchored: []`.


def test_known_names_from_cast_reads_BOTH_cast_shapes():
    """The KAL `cast` read returns `name`/`aliases`; by-ids and select-for-context return
    `cached_name`/`cached_aliases`. Reading only one of them is how "36 entities, 0 with a
    surface form" shipped once already — the gateway carries a comment about exactly that.
    """
    got = known_names_from_cast([
        {"entity_id": "1", "name": "Aurelia", "aliases": ["The Grey Wren"]},
        {"entity_id": "2", "cached_name": "Halvard", "cached_aliases": ["Hal"]},
    ])
    assert got == {"Aurelia", "The Grey Wren", "Halvard", "Hal"}


def test_an_empty_cast_yields_NONE_not_an_empty_set():
    """Load-bearing, and not a style choice. `audit_names` treats a falsy `known_names` as
    "fall back to the prompt proxy"; an EMPTY SET that reached the glossary branch would mean
    "this book has no names at all" and would accuse every proper noun in the draft. A glossary
    outage must degrade to a weaker check, never to a false-accusation machine.
    """
    assert known_names_from_cast([]) is None
    assert known_names_from_cast(None) is None
    assert known_names_from_cast([{"entity_id": "1", "name": "   "}]) is None


def test_the_authored_cast_CATCHES_an_invented_name_the_proxy_cannot():
    """The deferral's measurement, as a test. The draft invents a name that the packed prompt
    also contains — which is the whole point: the drafter wrote it into its own context, so a
    comparison against that context can never flag it.
    """
    # Varenne is IN the packed prompt and NOT in the glossary — the realistic shape of the
    # defect. The drafter had the name in its own context (a stray mention, a hallucination
    # carried forward from an earlier pass), so the proxy sees it on both sides and agrees with
    # itself. Only an independent truth side can say the book never authored this character.
    prompt = "Aurelia crossed the bridge. Lucian waited beyond it. Varenne is mentioned here."
    draft = "Aurelia crossed the bridge. Lucian waited beyond it, and so did Varenne."

    proxy = audit_names(draft, prompt, "en")
    assert proxy.truth_source == "prompt_proxy"
    assert "Varenne" not in proxy.unanchored, (
        "fixture is wrong: the proxy is supposed to MISS this, otherwise the test below "
        "proves nothing about the difference the cast makes")

    grounded = audit_names(draft, prompt, "en",
                           known_names=known_names_from_cast([
                               {"entity_id": "1", "name": "Aurelia"},
                               {"entity_id": "2", "name": "Lucian"},
                           ]))
    assert grounded.truth_source == "glossary"
    assert "Varenne" in grounded.unanchored, (
        f"the authored cast did not catch the invented name (got {grounded.unanchored}) — "
        "the check is still comparing the draft against the drafter's own input")


def test_an_ALIAS_in_the_draft_is_not_accused_when_the_cast_carries_it():
    """The reason `roster` could not be the source. It is deliberately projection-restricted to
    id+name+kind — the gateway says widening it "would put aliases and descriptions on the
    enumeration path every indexing pass walks" — so an alias-free name set turns every
    legitimate alias into an invented name. `name_grounding` says which error direction matters:
    "a name missing from `known` becomes a false accusation an author reads".
    """
    prompt = "Aurelia crossed the bridge."
    draft = "The Grey Wren crossed the bridge."
    names_without_aliases = known_names_from_cast([{"entity_id": "1", "name": "Aurelia"}])
    assert "Wren" in audit_names(draft, prompt, "en",
                                 known_names=names_without_aliases).unanchored, (
        "fixture is wrong: an alias-free cast is supposed to false-accuse here")

    with_aliases = known_names_from_cast(
        [{"entity_id": "1", "name": "Aurelia", "aliases": ["The Grey Wren"]}])
    accused = audit_names(draft, prompt, "en", known_names=with_aliases).unanchored
    assert not accused, f"an authored alias was reported as an invented name: {accused}"


@pytest.mark.asyncio
async def test_run_canon_reflect_ACTUALLY_PASSES_the_authored_cast_through():
    """The wiring, not the helper. `audit_names` has supported `known_names` all along and
    `truth_source` has always been on the envelope — the defect was that the live call never
    passed one, so production ran in `prompt_proxy` mode while the report looked like a
    verification.

    Drives the real `run_canon_reflect` (the same `cast_glossary_ids=[]` shortcut the test
    above uses, which still runs name grounding) and asserts the envelope says `glossary`.
    """
    from types import SimpleNamespace

    from app.engine.canon_reflect import run_canon_reflect

    kwargs = dict(
        knowledge=None, llm=None, user_id=__import__("uuid").uuid4(),
        project_id=__import__("uuid").uuid4(), cast_glossary_ids=[], scene_sort_order=1,
        # "Mira" is in the grounding, so the proxy cannot flag her; only an authored cast can.
        draft="Elara knelt. Beside her, Mira lifted the quill.", packed_prompt=GROUNDING,
        profile=SimpleNamespace(source_language="en"),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100,
    )

    _t, proxy, _n = await run_canon_reflect(**kwargs)
    assert proxy.name_truth_source == "prompt_proxy", (
        "without an authored cast the audit must SAY it fell back to the proxy")

    _t, grounded, _n = await run_canon_reflect(
        **kwargs, authored_cast=[{"entity_id": "1", "name": "Elara"}])
    assert grounded.name_truth_source == "glossary", (
        "run_canon_reflect did not pass the authored cast to audit_names — the check is back "
        "to comparing the draft against the drafter's own input")
    assert "Mira" in grounded.unanchored_names, (
        f"the authored cast reached the audit but the invented name was not caught "
        f"(got {grounded.unanchored_names})")
