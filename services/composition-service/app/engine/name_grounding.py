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

_TOKEN = re.compile(r"([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ\-]+(?:['’](?:s|t|ll|re|ve|m|d))?)")
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
    lowercase = frozenset(re.findall(r"\b([a-zà-öø-ÿ]{2,})\b", corpus if corpus is not None else text))
    spans = _quoted_spans(text)
    seen: dict[str, bool] = {}
    for m in _TOKEN.finditer(text):
        word = _normalise(m.group(1))
        if len(word) < 3 or _in_quotes(m.start(), spans):
            continue
        mid = not _SENTENCE_START.search(text[max(0, m.start() - 3):m.start()])
        seen[word] = seen.get(word, False) or mid
    return {w for w, mid in seen.items() if _is_name(w, mid, lowercase)}


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
        known = {_normalise(w) for w in known_names if len(_normalise(w)) >= 3}
    else:
        truth = "prompt_proxy"
        known = {_normalise(m.group(1)) for m in _TOKEN.finditer(grounding)
                 if _normalise(m.group(1)).lower() not in _FUNCTION_WORDS
                 and len(_normalise(m.group(1))) >= 3}
    if not known:
        # No grounding names at all (an empty book, a plan-free op). Everything would read as
        # unanchored, which is true but useless — and would flood the field on exactly the runs
        # where nothing was given. Report the method, claim nothing.
        return NameAudit(method="empty", truth_source="none")
    drafted = extract_names(draft, corpus=corpus)
    # `ML-2` — the shared NFKC + casefold + Han spine, not `.lower()`.
    #
    # BOTH SIDES MOVE TOGETHER OR NEITHER DOES. This is a symmetric fold key: the
    # dict is keyed by the fold and VALUED by the original, and it is the original
    # that is reported. Fold one side differently from the other and every
    # comparison below silently stops matching — which is why the swap is one edit
    # covering the map, the membership test and the edit distance, rather than the
    # two lines the gate happened to name.
    #
    # `.lower()` is not merely unfashionable here: it is wrong for `ß`/`İ` and it
    # leaves full-width Latin unfolded, so `Ｅｌａｒａ` and `Elara` read as two
    # different characters. The spine folds those and deliberately preserves
    # accents, so `ma`/`má` and `Müller`/`Muller` stay distinct — exactly the
    # property a near-miss check must not lose.
    lowered = {normalize_entity_name(k): k for k in known}
    unanchored, near = [], []
    for name in sorted(drafted):
        low = normalize_entity_name(name)
        # `Scribes` is not a near miss of `Scribe`; it is the plural of it. Measured: this
        # single case accounted for two of the run's four near-miss claims.
        if low in lowered or low.rstrip("s") in lowered or (low + "s") in lowered:
            continue
        closest, best = None, NEAR_MISS_MAX_DISTANCE + 1
        # Lengths read off the FOLDED strings, because the distance below is
        # measured on the folded strings. `.lower()` preserved length so raw and
        # folded were interchangeable; the spine does not — `Straße` (6) folds to
        # `strasse` (7). Gating on one string and measuring on another is the
        # adjacent-decision shape: both halves individually correct, the pair
        # wrong. A no-op for ASCII names, which is all of them today
        # (/review-impl).
        if len(low) >= _NEAR_MISS_MIN_LEN:
            for k_low, k in lowered.items():
                if len(k_low) < _NEAR_MISS_MIN_LEN:
                    continue
                d = _edit_distance(low, k_low)
                if d < best:
                    closest, best = k, d
        limit = 1 if len(low) < _NEAR_MISS_STRICT_UNDER else NEAR_MISS_MAX_DISTANCE
        if closest is not None and best <= limit:
            near.append({"name": name, "closest": closest, "distance": best})
        else:
            unanchored.append(name)
    return NameAudit(method="capitalised_latin", truth_source=truth, unanchored=unanchored,
                     near_misses=near, known_count=len(known))
