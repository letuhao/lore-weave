"""WS-5.11 (spec 08 §Gate-3, X-5 SEALED) — the platform SAFETY FLOOR.

The repo had NOTHING here (verified: zero self-harm/distress/crisis hits across services/).
Reflection + coaching are the first features that read a person's emotional life, so a
non-goal is not a control — this is a real, deterministic gate.

Design (X-5, SEALED):
- **Deterministic and FAIL-CLOSED.** A curated lexicon PLUS paraphrase patterns. The spec's
  own worked example — *"I don't know how much longer I can do this"* — contains NONE of the
  obvious keywords, so a bare keyword list fails open exactly where it must not. The patterns
  are the floor's teeth.
- **An LLM classifier may WIDEN the net, never NARROW the floor.** `screen()` is the floor; a
  model verdict is OR-ed in via `combine_with_model()` — it can only add a trip, never remove
  the deterministic one. A $0 quantized model is never the sole gate (it "can contradict its
  own reasoning" — the repo's canon-check finding).

This module is intentionally PURE (no I/O, no deps) so it screens identically wherever it
runs. It is the primary gate before weekly reflection pattern-surfacing (X-2) and before
practice source-material (WS-5.13). PROMOTE to a shared package when the chat-service practice
gate consumes it — a second copy of a safety lexicon is a drift this repo must not ship.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ── Categories ───────────────────────────────────────────────────────────────
CAT_SELF_HARM = "self_harm"
CAT_DISTRESS = "distress"
CAT_HARASSMENT_ABUSE = "harassment_abuse"

# ── The curated lexicon (substring match on normalized text) ─────────────────
# Kept deliberately high-precision; the paraphrase patterns below carry the recall
# the plain terms miss. Each entry is a normalized (lowercased) substring.
_LEXICON: dict[str, tuple[str, ...]] = {
    CAT_SELF_HARM: (
        "suicide", "suicidal", "kill myself", "killing myself", "end my life",
        "ending my life", "take my own life", "want to die", "wish i was dead",
        "wish i were dead", "better off dead", "self-harm", "self harm",
        "hurt myself", "harm myself", "cut myself", "cutting myself",
        "no reason to live", "don't want to live", "dont want to live",
        "everyone would be better off without me", "better off without me",
    ),
    CAT_DISTRESS: (
        "hopeless", "worthless", "no way out", "can't go on", "cant go on",
        "give up on everything", "breaking point", "at my breaking point",
        "nothing matters anymore", "nothing helps anymore",
    ),
    CAT_HARASSMENT_ABUSE: (
        # NB: bare "hit me" is deliberately NOT here — it is idiom-prone ("the flu hit me",
        # "it hit me that…") and would false-short-circuit reflection; the violence sense is a
        # PATTERN below (subject + verb + me). Safety fails closed, but a floor that trips on
        # idiom makes reflection unusable — the wrong kind of fail-closed.
        "harassed", "harassing me", "sexually harassed", "assaulted me",
        "abused me", "abusing me", "threatened me", "threatening me",
        "unsafe around", "afraid of my", "stalking me", "stalked me",
    ),
}

# ── Paraphrase patterns (regex on normalized text) — the recall the lexicon lacks.
# The spec example "I don't know how much longer I can do this" matches here, not above.
_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = tuple(
    (cat, re.compile(rx))
    for cat, rx in (
        # distress / can't-continue paraphrases (no obvious keyword)
        (CAT_DISTRESS, r"how much (longer|more) i can (do|take|keep|handle|last|go)"),
        (CAT_DISTRESS, r"(don'?t|do not) know how much (longer|more)"),
        (CAT_DISTRESS, r"can'?t (do|take|handle|keep doing|keep going with) (this|it)( any\s?more)?"),
        (CAT_DISTRESS, r"(can'?t|cannot) keep (doing|going) (this|on) (like this|any\s?more)"),
        (CAT_DISTRESS, r"(don'?t|do not) (see|know) (the|a|any) (point|reason) (in|to|of)"),
        (CAT_DISTRESS, r"(everything|it all) (is|feels) (pointless|hopeless|too much)"),
        (CAT_DISTRESS, r"drowning (in|under) (work|it all|everything)"),
        # self-harm paraphrases
        (CAT_SELF_HARM, r"(no|not any) (point|reason) (in|to) (living|go(ing)? on|be(ing)? here)"),
        (CAT_SELF_HARM, r"(don'?t|do not) want to (be here|wake up|exist)( any\s?more)?"),
        (CAT_SELF_HARM, r"(disappear|vanish) (forever|and never come back)"),
        # harassment / abuse paraphrases
        (CAT_HARASSMENT_ABUSE, r"(makes|made) me feel unsafe"),
        (CAT_HARASSMENT_ABUSE, r"(won'?t|will not) (leave me alone|stop (texting|messaging|calling) me)"),
        (CAT_HARASSMENT_ABUSE, r"(touched|grabbed) me without (my )?(consent|permission)"),
        # the violence sense of "hit me" — requires a human subject, so idioms don't trip it
        (CAT_HARASSMENT_ABUSE, r"(he|she|they|my \w+|partner|husband|wife|boss|manager) (hit|hits|beat|beats|punched|punches|slapped|slaps) me"),
    )
)


@dataclass(frozen=True)
class SafetyVerdict:
    """The floor's decision. `tripped=True` short-circuits the pipeline fail-closed.
    `category` names WHICH floor tripped (for the acknowledgement + resources); `reason`
    is the matched term/pattern (for logging — never surfaced to the user)."""

    tripped: bool
    category: str | None = None
    reason: str | None = None


def _normalize(text: str) -> str:
    """Lowercase + NFKC-fold so unicode look-alikes and width variants don't slip a
    disclosure past the floor. Collapse whitespace so line breaks don't split a phrase."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", t)


def screen(text: str) -> SafetyVerdict:
    """The deterministic FLOOR. Returns the first trip (lexicon then patterns). Self-harm
    is checked before distress so the more urgent category wins when both would match."""
    norm = _normalize(text)
    if not norm:
        return SafetyVerdict(False)
    # lexicon — self-harm first (most urgent), then harassment, then distress
    for cat in (CAT_SELF_HARM, CAT_HARASSMENT_ABUSE, CAT_DISTRESS):
        for term in _LEXICON[cat]:
            if term in norm:
                return SafetyVerdict(True, cat, f"lexicon:{term}")
    # paraphrase patterns
    for cat, pat in _PATTERNS:
        if pat.search(norm):
            return SafetyVerdict(True, cat, f"pattern:{pat.pattern[:40]}")
    return SafetyVerdict(False)


# ── WS-5.14 — clinical/diagnostic deny-list on the PHRASING step's output ─────
# A coach describes behavior; it must NEVER diagnose. A phrased pattern whose text uses
# clinical/diagnostic vocabulary is DROPPED (not softened) — playing clinician is a harm even
# when the words are gentle. Deterministic word-boundary match on normalized text.
_CLINICAL_TERMS: frozenset[str] = frozenset({
    "depression", "depressive", "anxiety disorder", "anxious disorder", "ptsd", "trauma",
    "traumatized", "traumatised", "bipolar", "adhd", "ocd", "burnout syndrome", "clinical",
    "diagnose", "diagnosed", "diagnosis", "disorder", "mental illness", "mentally ill",
    "pathological", "neurosis", "neurotic", "psychosis", "psychotic", "manic", "mania",
})
_CLINICAL_RX = re.compile(r"\b(" + "|".join(re.escape(t) for t in _CLINICAL_TERMS) + r")\b")


def contains_clinical_language(text: str) -> bool:
    """WS-5.14 — True if `text` uses clinical/diagnostic vocabulary (word-boundary match).
    The phrasing step DROPS any pattern for which this is True."""
    return bool(_CLINICAL_RX.search(_normalize(text)))


def combine_with_model(floor: SafetyVerdict, model_tripped: bool, model_category: str | None = None) -> SafetyVerdict:
    """OR a model classifier's verdict ONTO the floor — it may WIDEN (add a trip) but NEVER
    NARROW (the deterministic trip always stands). This is how an LLM classifier is allowed to
    run on top (X-5) without ever becoming a way to talk the floor down."""
    if floor.tripped:
        return floor  # the floor is authoritative; a model cannot un-trip it
    if model_tripped:
        return SafetyVerdict(True, model_category or CAT_DISTRESS, "model")
    return floor
