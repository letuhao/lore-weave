"""D-CANON-GUARD-SKIPPED-WHOLE-CHAPTER — which names in this draft the story was never given.

What this can and cannot claim
------------------------------
**It cannot say a name is WRONG.** That needs a source of truth about who exists, and the book
that exposed this has zero glossary entities — nothing declares its cast at all. Fiction
legitimately introduces characters, and a scene whose authored intent names no interlocutor
still needs someone to speak to. So an unanchored name is a **fact about the inputs**, never a
verdict about the prose:

    "this name appears nowhere in what the model was given"   ← checkable
    "this name is wrong"                                      ← not checkable here

The distinction is not pedantry. The run that motivated this module produced "Mira", one edit
from the book's minor character "Mina", and it was tempting to call that a corruption. The same
run produced "Weaver's **Lane**", one edit from the antagonist "**Vane**" — same length, same
distance, and a completely false accusation. No threshold separates them, which is why
`near_misses` withholds the claim below `_NEAR_MISS_STRICT_UNDER` and why nothing here is a
violation or triggers a revise.

Where the truth comes from, and why it is named
-----------------------------------------------
`truth_source` is the field that matters most. With `prompt_proxy` the comparison is against
THE DRAFTER'S OWN INPUT — every gap in what the generator was given is inherited exactly, so a
wrong name the prompt happens to contain passes, and a real character outside the recent-prose
window is accused. That is the self-witness failure this session has found repeatedly: **a check
whose input and whose expectation come from the same place verifies nothing.** Reporting the
source is what keeps a proxy from reading as a verification.

The check that needs no ground truth at all
--------------------------------------------
Also measured on that chapter, and strictly stronger than anything here: scene 2 ended "**He**
is the anchor… **he** has been waiting for someone to take **his** place" and scene 3 opened
"**She's** a Scribe… **she** was a sentinel, waiting for the next hand". Same character, same
chapter, consecutive scenes. That is the text contradicting ITSELF — provable with no glossary,
no cast, and no external fact. Intra-text consistency is the real check for an ungrounded book;
this module is the weaker, cheaper half. See D-CROSS-SCENE-CONTRADICTION.

Script honesty
--------------
Proper names are discriminated by CAPITALISATION, which does not exist in Chinese, Japanese,
Korean or Thai. Rather than report every CJK draft as clean — a silent blind spot — the method
is reported and the finding list is empty, the discipline `realised_words` follows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from loreweave_extraction.name_normalize import normalize_entity_name

# ⚠️ UNICODE-AWARE, AND CASE IS DECIDED IN PYTHON — NOT BY A CHARACTER RANGE.
#
# This was `[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ\-]+…`: Latin-1 only. Vietnamese is a CASED LATIN script whose
# letters live in Latin Extended Additional (U+1E00-U+1EFF), so codepoints such as U+1EE5 and
# U+1ED9 fall outside those ranges and the tokeniser could not see words containing them.
#
# Measured on the QC-5 acceptance draft (job `019ff423`), which invented a character with ZERO
# canon entities: the extractor emitted nothing for it, `unanchored_names` came back `[]`, and
# the envelope reported `name_grounding: "checked"`. **A check that cannot see the name it
# exists to catch, reporting that it checked.** The LLM canon check caught the invention; this
# one — the cheap deterministic one whose whole job it is — did not.
#
# Ranges cannot fix this: Latin Extended-A/Additional interleave upper and lower case, so no
# range expresses "a capital". The tail is therefore matched permissively as word characters
# (`\w` is Unicode-aware in Python 3) and CASE is checked in `_is_capitalised`, which uses
# `str.isupper()`/`str.islower()` and so works for any cased script. A caseless script (CJK)
# yields False from `.isupper()` and is excluded here — which is correct, because those books
# take the `caseless_script` branch that says so honestly rather than pretending to check.
_TOKEN = re.compile(r"([^\W\d_][\w\-]*(?:['’](?:s|t|ll|re|ve|m|d))?)", re.UNICODE)


def _is_capitalised(word: str) -> bool:
    """A leading capital followed by no other capital — the shape a name takes in a cased
    script. Rejects ALLCAPS (which is emphasis, not a name) and rejects caseless scripts,
    whose `.isupper()` is False for every character."""
    core = word.split("'")[0].split("’")[0].replace("-", "")
    if len(core) < 2 or not core[0].isupper():
        return False
    return not any(c.isupper() for c in core[1:])


_SENTENCE_START = re.compile(r"(?:^|[.!?;:\n\"“”‘’()\[\]—–\-]\s*)$")

#: Possessive and contraction tails. Run against the REAL chapter, the first version of this
#: module reported `Elara's`, `Elara’s`, `Scribe's`, `He's`, `Don't`, `You'll` and `I'm` as
#: unanchored names — roughly half of all its findings — because the apostrophe form is a
#: distinct token from the name. `Elara’s` was even reported as a NEAR MISS of `Elara`, which
#: is the check accusing a name of being a corruption of itself.
_TAIL = re.compile(r"['’](?:s|t|ll|re|ve|m|d)$")


def _normalise(word: str) -> str:
    return _TAIL.sub("", word)

#: Words that are capitalised by POSITION, not because they name anything.
#:
#: A first attempt used one rule — "a name occurs capitalised mid-sentence" — and it was wrong
#: in both directions at once, which the tests caught immediately. It missed a name that only
#: ever opens a sentence ("Mira turned to Elara…"), and it flagged Cassius as invented because
#: the packer's `<present>` block lists the cast as "Elara, the cartographer. Cassius, her
#: master. Silas the Traveler." — every name sentence-initial, so none of them counted as known.
#:
#: This list is a FALSE-POSITIVE SUPPRESSOR, not an authority on what a name is. A word missing
#: from it costs one advisory line in a report an author skims; nothing here decides a verdict.
#:
#: The tradeoff it makes, stated rather than discovered later: a character actually NAMED with
#: one of these words ("Will", "May", "Grace") would be treated as already-known and never
#: reported. That is the right way round for a check whose false positives an author has to
#: read and dismiss one by one — but it is a real hole, not an absence of one.
_FUNCTION_WORDS = frozenset("""
the a an and or but nor so then than that this these those there here now when while
after before if though although because however yet still just only even once since until
he she it they we you his her hers its their theirs our your my him them us me mine
what who whom whose which where why how all some any each every both few many most
no not never always inside outside above below beyond across through into onto upon
one two three four five six seven eight nine ten first second third last next another
nothing something anything everything nobody somebody someone anyone everyone none
neither either such much more less own same other very too also again already
perhaps maybe instead meanwhile later soon finally suddenly slowly together alone
for from with without against toward towards between among behind beneath beside
under over off out down back away about around during despite within
was were been being have has had did does done will would can could should must
""".split())


#: A capitalised word INSIDE quoted dialogue is almost always an opener or an onomatopoeia,
#: not a name. Measured over 19,494 words of real chapters: the unanchored list came back as
#: `Draft, Great, Take, Anchor, Hold, Self, Old, Feel, Please, Scritch, Shhh, Tear, Thump` —
#: every single one from dialogue or a sound effect, and not one real name among them. An
#: author reading a column that noisy stops reading the column.
#: Two spans, one rule. Quoted dialogue AND markdown emphasis both capitalise by convention
#: rather than by naming, and on the real chapters emphasis was the LARGER source: `*Thump.
#: Thump.*`, `*Scritch.*`, `*Shhh.*`, `*Tear. Silence.*`, `*Feel the weight.*`, `*Take it,*`,
#: `*Self*` — seven of twelve findings, every one an onomatopoeia or an interior shout.
_QUOTED = re.compile(r"""["“][^"”\n]{0,400}["”]|\*[^*\n]{1,200}\*""")


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTED.finditer(text)]


def _in_quotes(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def _is_name(word: str, mid_sentence: bool, lowercase_corpus: frozenset[str]) -> bool:
    """A capitalised token names something if it is not capitalised merely by POSITION.

    Only one piece of evidence is accepted: the token appears capitalised MID-sentence, which
    an ordinary word does not reach by accident.

    A second rule was tried — "or the word is never seen lowercase anywhere" — and measuring it
    on a real 8,116-word chapter killed it. Narrative prose opens quoted dialogue constantly,
    and a quote opening is a sentence start, so it admitted `Give`, `Stop`, `Let`, `Please`,
    `Listen`, `Close`, `Thump` and `Panic` as invented names. The cost of keeping it was ~10
    false accusations per scene; the benefit was catching a name that appears ONLY at sentence
    starts, which over four real scenes never happened once (the invented "Mira" appeared as
    "Mira’s" mid-sentence). Weak evidence in the wrong error direction is worse than none.
    """
    if word.lower() in _FUNCTION_WORDS:
        return False
    return mid_sentence

#: Scripts with no letter case — the capitalisation heuristic cannot apply.
_CASELESS = ("zh", "ja", "ko", "th")

#: A name this far from a known one is more likely a corruption of it than a new invention.
#: 1-2 edits catches Mira/Mina, Cassius/Casius, Elara/Elera. Beyond that the claim gets weak.
NEAR_MISS_MAX_DISTANCE = 2

#: Below this length an edit distance of 2 relates almost any two words, so a near-miss claim
#: on a short name is noise. Measured on the real chapter at 4: it reported the street
#: "Weaver's **Lane**" as a near miss of the antagonist "**Vane**" — one edit at length four,
#: and a completely false accusation about a load-bearing character. Short names additionally
#: require an EXACT-adjacent single edit.
_NEAR_MISS_MIN_LEN = 5
#: Under this length, only a distance of 1 may be claimed.
_NEAR_MISS_STRICT_UNDER = 7


#: WHERE the set of legitimate names came from. The most important field on the result.
#:
#: `glossary` — the authored entity SSOT for this book. An independent source of truth: it was
#:   written by the author, not handed to the drafter, so disagreeing with it means something.
#: `prompt_proxy` — the packed prompt, i.e. THE DRAFTER'S OWN INPUT. This is not verification.
#:   A name the prompt happens to mention passes even if it is wrong, and a real character the
#:   prompt's recent-prose window did not reach is accused of being invented. Every gap in what
#:   the generator was given is inherited exactly.
#: `none` — nothing to compare against; no claim is made.
#:
#: The first version of this module used the proxy and reported as though it had verified. That
#: is the self-witness failure this session has now found five times: **a check whose input and
#: whose expectation come from the same author verifies nothing.** The generator invented "Mira"
#: BECAUSE the book has no entity ground truth; a checker built on the generator's own input
#: cannot be the thing that catches it. Naming the source is what makes the difference legible
#: instead of silently reassuring.
TRUTH_SOURCES = ("glossary", "prompt_proxy", "none")


@dataclass
class NameAudit:
    """What the check could see, where its truth came from, and what it found."""

    method: str                                    # capitalised_latin | caseless_script | empty
    #: See TRUTH_SOURCES. `prompt_proxy` means these findings are UNVERIFIED — a consistency
    #: observation against the drafter's own input, not a check against anything authoritative.
    truth_source: str = "none"
    unanchored: list[str] = field(default_factory=list)
    #: {"name": "Mira", "closest": "Mina", "distance": 1} — a likely corruption, not an invention.
    near_misses: list[dict] = field(default_factory=list)
    known_count: int = 0

    @property
    def clean(self) -> bool:
        return not self.unanchored and not self.near_misses


def _edit_distance(a: str, b: str, cap: int = NEAR_MISS_MAX_DISTANCE) -> int:
    """Levenshtein, abandoned once it provably exceeds `cap` (all we ever ask)."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def extract_names(text: str, corpus: str | None = None) -> set[str]:
    """The capitalised tokens in `text` that name something — see `_is_name`.

    `corpus` is the material the lowercase evidence is drawn from; it defaults to `text`, and
    `audit_names` passes draft+grounding together so a word seen lowercase in either counts.
    """
    if not text:
        return set()
    # Same widening as `_TOKEN`, and for the same reason: a lowercase Vietnamese word
    # must count as lowercase evidence, or a word that also appears lowercased
    # mid-sentence is misjudged as a name.
    lowercase = frozenset(
        w for w in re.findall(r"\b([^\W\d_]{2,})\b", corpus if corpus is not None else text)
        if w[:1].islower())
    spans = _quoted_spans(text)
    seen: dict[str, bool] = {}
    for m in _TOKEN.finditer(text):
        word = _normalise(m.group(1))
        # `_TOKEN` is permissive on purpose now; capitalisation is the real predicate and it
        # is decided here, where `str.isupper()` works for every cased script.
        if len(word) < 3 or not _is_capitalised(word) or _in_quotes(m.start(), spans):
            continue
        mid = not _SENTENCE_START.search(text[max(0, m.start() - 3):m.start()])
        seen[word] = seen.get(word, False) or mid
    return {w for w, mid in seen.items() if _is_name(w, mid, lowercase)}


def known_names_from_cast(rows: list[dict] | None) -> set[str] | None:
    """The authored surface forms for a book, as `audit_names(known_names=…)` wants them.

    Accepts both cast shapes this codebase has: the KAL `cast` read returns `name`/`aliases`,
    while by-ids and select-for-context return `cached_name`/`cached_aliases`. Reading only one
    of them is how "36 entities, 0 with a surface form" shipped once already, so both are taken.

    Returns **None** for an empty or absent cast rather than an empty set, and the distinction
    is load-bearing: `audit_names` treats a falsy `known_names` as "fall back to the prompt
    proxy", whereas an empty set that reached the glossary branch would mean "this book has no
    names" and accuse every proper noun in the draft.
    """
    if not rows:
        return None
    out: set[str] = set()
    for e in rows:
        for raw in (e.get("name"), e.get("cached_name"),
                    *(e.get("aliases") or []), *(e.get("cached_aliases") or [])):
            if isinstance(raw, str) and raw.strip():
                out.add(raw.strip())
    return out or None


def audit_names(draft: str, grounding: str, language: str | None = None,
                known_names: set[str] | None = None) -> NameAudit:
    """Which names in `draft` appear nowhere in the story's known names.

    `known_names`, when given, is the AUTHORED entity SSOT for the book (glossary canonical
    names + aliases) — an independent source, so a disagreement means something. Without it the
    comparison falls back to `grounding`, the packed prompt, which is **the drafter's own
    input**: a proxy that inherits every gap the generator had and can only report a
    consistency observation. `truth_source` on the result says which happened, because a proxy
    that does not announce itself reads exactly like a verification.
    """
    lang = (language or "").lower().split("-")[0]
    if lang in _CASELESS:
        return NameAudit(method="caseless_script")
    corpus = f"{grounding}\n{draft}"
    # The two sides are extracted with DIFFERENT strictness, and the asymmetry is deliberate.
    # A name missing from `known` becomes a false accusation an author reads; a spurious extra
    # entry in `known` only suppresses one advisory line. For a check nobody is blocked by, the
    # error direction that matters is the first — so grounding is read permissively, treating
    # every capitalised non-function token as something the story knows about.
    if known_names:
        truth = "glossary"
        # ⚠️ A MULTI-WORD CANON NAME MUST ALSO ANCHOR ITS PARTS.
        #
        # The extractor emits single WORDS; the glossary holds full names. So `Lâm Uyên` in
        # `known` never matched the extracted `Lâm` or `Uyên`, and both were reported as
        # unanchored — the check accusing the book's own protagonist. Not Vietnamese-specific:
        # `Zaphod Beeblebrox` breaks identically in English. It stayed invisible only because
        # the Latin-1 tokeniser could not see Vietnamese words at all, so this book produced
        # no extractions to mismatch.
        #
        # Expanding to components is the right direction for THIS check by its own stated
        # rule — *"a name missing from `known` becomes a false accusation an author reads; a
        # spurious extra entry in `known` only suppresses one advisory line"*. The cost, said
        # plainly: an invented full name whose FAMILY name matches a canon character will
        # now anchor on that part, trading some recall for a large precision gain.
        known = set()
        for w in known_names:
            norm = _normalise(w)
            if len(norm) >= 3:
                known.add(norm)
            for part in norm.replace("-", " ").split():
                if len(part) >= 3:
                    known.add(part)
    else:
        truth = "prompt_proxy"
        known = {_normalise(m.group(1)) for m in _TOKEN.finditer(grounding)
                 if _is_capitalised(_normalise(m.group(1)))
                 if _normalise(m.group(1)).lower() not in _FUNCTION_WORDS
                 and len(_normalise(m.group(1))) >= 3}
    if not known:
        # No grounding names at all (an empty book, a plan-free op). Everything would read as
        # unanchored, which is true but useless — and would flood the field on exactly the runs
        # where nothing was given. Report the method, claim nothing.
        return NameAudit(method="empty", truth_source="none")
    drafted = extract_names(draft, corpus=corpus)
    # ML-2 — the equivalence key is NFKC + casefold + Han-simplified fold, not `.lower()`.
    #
    # Caught by `language-bias-gate`, RED since this module was written on 2026-08-01 and
    # unnoticed because the gate set being run was a subset of CI's.
    #
    # WHAT THIS FIXES, stated honestly: nothing observable TODAY. I first wrote that `.lower()`
    # would report an equivalent name as unanchored — a fabricated finding — and then measured
    # it: over every name `_TOKEN` can produce (basic Latin + Latin-1 capitals, per the module
    # docstring's "Script honesty" note), `.lower()` and `normalize_entity_name` agree on
    # **0 disagreements**. The failure needs a full-width or Han name, and the extractor cannot
    # emit one, so it is unreachable through this path.
    #
    # It is still the right primitive, for one reason: the extractor's alphabet is the ONLY
    # thing making `.lower()` safe here. Widening `_TOKEN` — which the docstring already names
    # as the obvious next step for CJK books — would silently make it wrong, in the check whose
    # job is deciding whether the model invented a name. The pinning test asserts both halves:
    # that the swap changed nothing now, and that the fold is what CJK/full-width needs.
    lowered = {normalize_entity_name(k): k for k in known}
    unanchored, near = [], []
    for name in sorted(drafted):
        low = normalize_entity_name(name)
        # `Scribes` is not a near miss of `Scribe`; it is the plural of it. Measured: this
        # single case accounted for two of the run's four near-miss claims.
        if low in lowered or low.rstrip("s") in lowered or (low + "s") in lowered:
            continue
        closest, best = None, NEAR_MISS_MAX_DISTANCE + 1
        if len(name) >= _NEAR_MISS_MIN_LEN:
            for k_low, k in lowered.items():
                if len(k) < _NEAR_MISS_MIN_LEN:
                    continue
                d = _edit_distance(low, k_low)
                if d < best:
                    closest, best = k, d
        limit = 1 if len(name) < _NEAR_MISS_STRICT_UNDER else NEAR_MISS_MAX_DISTANCE
        if closest is not None and best <= limit:
            near.append({"name": name, "closest": closest, "distance": best})
        else:
            unanchored.append(name)
    return NameAudit(method="capitalised_latin", truth_source=truth, unanchored=unanchored,
                     near_misses=near, known_count=len(known))
