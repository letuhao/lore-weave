"""Co-write loop (§3.1) — build prompt → stream draft → meter real tokens.

Streams a drafter model via the llm SDK's `.sdk.stream` escape hatch (the
wrapper has no stream method). Relays token deltas as they arrive and harvests
the real `UsageEvent` frame. TOKEN METERING (enrichment complete.py lesson): an
ABSENT or ZERO usage frame is "not measured" → fall back to an over-estimating
char model + clamp ≥0; NEVER meter a stream as 0 (that silently weakens the cap).
A mid-stream output cap stops the stream + partial-saves (S3 budget-exhaustion).

De-bias (§2.6): the draft prompt carries the book's `source_language` + abstract
operation instructions — NO English-only illustrative phrases.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from loreweave_llm import ReasoningDirective
from loreweave_llm.errors import LLMError
from loreweave_llm.models import DoneEvent, ReasoningEvent, StreamRequest, TokenEvent, UsageEvent

from app.reasoning import wire_fields

from app.packer.profile import BookProfile, style_directive
from app.packer.sanitize import sanitize_guide

logger = logging.getLogger(__name__)

_OPERATION_INSTRUCTIONS = {
    "continue": "Continue the scene from where the recent prose ends, in the same voice.",
    # SCENE-BOUNDARY (2026-07-30, Mị Đế): the plan block shows the whole chapter, so
    # "draft this scene" alone let the drafter run straight through its neighbours —
    # scene 1's draft arrived carrying scene 3's and scene 4's material. The boundary
    # has to be stated, not implied by the singular "this".
    # D-SCENE-INTENT-NEVER-SHOWN — this named exactly the four fields the packer used to
    # send, which was honest then and starves the model now that all twelve arrive. An
    # author who fills `conflict`, `stakes` and `outcome` is describing the SHAPE of the
    # scene; saying "draft from the beat" leaves the model to infer a shape it was handed.
    # So name each one and what it is FOR — a label with no job attached gets skimmed.
    "draft_scene": "Draft ONLY this scene, using every field of its <beat>. Read them as a "
                   "brief, not a summary to paraphrase: `goal` is what the scene must "
                   "achieve; `conflict` is what stands in the way and must be FELT on the "
                   "page, not asserted; `stakes` is what it costs to lose, so let it press "
                   "on the characters; `outcome` is where the scene must arrive, so steer "
                   "there rather than stopping early; `tension` is its intensity out of "
                   "100, which should govern the rhythm; `value_shift` is the net "
                   "emotional change, so the reader must end somewhere different from "
                   "where they began; `leaves` is the state the next scene inherits, so "
                   "land on it. Other scenes appear in the plan for context: do NOT write "
                   "them. Stop when THIS scene's beat has played out, even if later beats "
                   "are visible.",
    # W6 — the conformance judge read the WRITTEN scene and found it did not realize its planned
    # beat. This is a second attempt with that knowledge, so it must not be a bare re-roll: the
    # plan above is unchanged and the beat is already in it, what failed was landing it ON THE
    # PAGE. Server-authored on purpose — the drift is a machine verdict, and letting the client
    # phrase the retry instruction would put the one part that matters in the least trustworthy
    # place. (`guide` still carries the AUTHOR's own words when they add any.)
    "regenerate_to_beat":
        "Draft this scene AGAIN from its beat, goal, POV, and synopsis. A previous draft of this "
        "scene did NOT realize its planned beat, so writing something merely competent is not "
        "enough: the beat named in the plan above must unmistakably HAPPEN in this passage — "
        "dramatised through action, dialogue and interiority, never summarised or asserted. Keep "
        "the scene's established POV, characters and continuity; change how the beat is played "
        "out, not which beat it is. If the plan also names a tension target, let the scene's "
        "rhythm actually reach it rather than staying flat.",
    # B2 chapter single-pass: the user prompt carries the chapter intent + every
    # scene beat in order; write the WHOLE chapter as one continuous narrative
    # (not a single scene) so the output isn't fragmented back into per-scene size.
    "draft_chapter": "Draft the ENTIRE chapter as one continuous narrative, covering "
                     "every scene beat in the outline in order, with smooth transitions.",
    "expand": "Expand the current passage with more sensory and interior detail.",
    "rewrite": "Rewrite the current passage, keeping its events but improving the prose.",
    "describe": "Write a vivid description for the current moment.",
    # M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — per-scene "adapt from source" for a
    # derivative Work. The packer's <source_scene> block carries the inherited
    # SOURCE scene's prose (gathered ONLY for this op, spoiler-bounded ≤ the branch);
    # the model rewrites it through the divergence + entity overrides. Plan-free
    # (like continue/rewrite): it does NOT require a derivative scene node/plan.
    "adapt_scene": "Adapt the SOURCE scene's prose (in the <source_scene> block) to "
                   "this branch: keep its structural function, but rewrite it to "
                   "honour the divergence and entity overrides. Do not copy the "
                   "source verbatim.",
}


@dataclass
class DraftMetering:
    input_tokens: int
    output_tokens: int
    measured: bool   # False → over-estimated from a char model (no real usage frame)
    # Raw model stop reason from the gateway (DoneEvent / job.result["finish_reason"]).
    # "length" ⇒ the model hit the output cap (truncated); None ⇒ not reported.
    # D-COMP-TRUNCATION-SURFACING: the authoritative truncation signal (replaces the
    # cycle-3 char-estimate heuristic that was dropped for being too biased).
    finish_reason: str | None = None


def char_estimate(text: str) -> int:
    """Over-estimating char→token model for the metering FALLBACK only. ~3 chars
    per token over-estimates English while staying close for CJK; clamped ≥0."""
    return max(0, math.ceil(len(text or "") / 3))


def estimate_prompt_tokens(messages: list[dict[str, Any]], counter: Callable[[str], int]) -> int:
    return sum(counter(str(m.get("content", ""))) for m in messages)


#: Default per-SCENE word target when the scene carries no `target_words` (2026-07-26). Without a
#: length target the drafter free-runs SHORT — a local gemma drafted an 83-word "scene" for a
#: 1400-token budget, nowhere near a readable ~1000-word scene (3 of which make a ~3000-word
#: chapter). Tunable; the scene's own `target_words` (when the planner sets it) always wins.
DEFAULT_SCENE_TARGET_WORDS = 1000

#: D-SCENE-OUTPUT-BUDGET-FLAT — tokens per WORD, by script family.
#:
#: A word is not a token, and the ratio is not close to 1 outside English. Latin-script
#: prose runs ~1.4 tokens/word; Vietnamese carries a diacritic on a large share of its
#: syllables and each one costs extra BPE pieces, so it runs closer to 2.6; CJK has no
#: spaces at all, so "words" split on whitespace under-counts badly.
#:
#: These are deliberately GENEROUS. Over-provisioning the ceiling costs nothing — a model
#: stops when the passage is done, and `max_tokens` is a ceiling, not a target (the LENGTH
#: directive is what asks for a length). Under-provisioning silently truncates mid-sentence,
#: which is the bug this table exists to end.
_TOKENS_PER_WORD: dict[str, float] = {"vi": 2.6, "th": 2.6, "zh": 3.2, "ja": 3.2, "ko": 3.0}
_TOKENS_PER_WORD_DEFAULT = 1.7

#: Scripts with no whitespace between words. Splitting these on spaces under-counts by an
#: order of magnitude — the same fact `_TOKENS_PER_WORD` above already encodes.
_SPACELESS = {"zh", "ja", "ko", "th"}

#: Characters per "word" for a spaceless script. Chinese words average ~1.5 hanzi; Japanese
#: and Korean land nearby once kana/particles are counted. Coarse ON PURPOSE — this exists to
#: tell "roughly the length asked for" from "a third of it", not to be a linguistic measure.
_CHARS_PER_WORD = 1.6


def realised_words(text: str, language: str | None = None) -> tuple[int, str]:
    """(count, method) — how long the draft ACTUALLY came out, measured the way its own
    LENGTH directive asks.

    The directive is `"write a FULL passage of approximately {target_words} words"`, and it is
    sent in that wording regardless of output language. For a space-separated script that is
    unambiguous and `split()` is exactly right. For a spaceless one it is NOT: neither the
    model nor this function can know what the author meant by "word", so the count is an
    ESTIMATE and says so in `method` rather than being passed off as a measurement.

    Returning the method matters more than the number. A shortfall detector comparing a
    `split()` count against a Chinese target would report every CJK scene as ~85% short — a
    false finding manufactured by the metric, which is precisely the class the eval instrument
    exists to avoid. A consumer that sees `method="cjk_chars_estimate"` can weigh it.
    """
    body = (text or "").strip()
    if not body:
        return 0, "empty"
    lang = (language or "").lower().split("-")[0]
    if lang in _SPACELESS:
        # Count CJK/Thai script characters, ignoring punctuation and any embedded Latin runs.
        chars = sum(1 for ch in body if not ch.isspace() and not ch.isascii())
        if chars:
            return max(1, round(chars / _CHARS_PER_WORD)), f"{lang}_chars_estimate"
        # Declared spaceless but written in ASCII — trust the text over the declaration.
    return len(body.split()), "whitespace"

#: Headroom over the computed need: a scene that lands slightly long must not be cut off
#: one sentence from its ending.
#:
#: Deliberately loose, because this is a CREATION tool. A tight ceiling on a drafting call
#: is a bad LLM usage pattern: `max_tokens` does not make prose shorter, it makes it STOP —
#: mid-sentence, with the tokens already paid for. The thing that should govern length is
#: the LENGTH directive in the prompt, which the model can weigh against the scene it is
#: actually writing. The ceiling's only job is to be too big to matter.
_OUTPUT_BUDGET_HEADROOM = 2.0

#: Reasoning tokens are spent BEFORE the visible prose and come out of the SAME budget.
#: Left unaccounted, turning thinking on silently halves the room for the passage — the
#: "empty ghost" failure this repo has already shipped once (a reasoning model spending its
#: whole allowance on hidden reasoning and returning text="", billed as a success). Scale by
#: effort rather than adding a flat number, because that is how the cost actually grows.
_REASONING_ALLOWANCE: dict[str, float] = {
    "none": 0.0, "off": 0.0, "low": 0.6, "medium": 1.2, "high": 2.0,
}
_REASONING_ALLOWANCE_UNKNOWN = 1.2

#: The hard ceiling. Not a budget — a runaway guard. Sized so no legitimate scene or
#: chapter can reach it, so that hitting it is a bug report rather than a quiet truncation.
SCENE_OUTPUT_CEILING = 32768


def scene_output_budget(
    target_words: int | None,
    source_language: str | None,
    *,
    reasoning: ReasoningDirective | None = None,
    ceiling: int = SCENE_OUTPUT_CEILING,
) -> int:
    """The output-token ceiling a scene draft needs to actually REACH `target_words`.

    D-SCENE-OUTPUT-BUDGET-FLAT. The scene path used a flat `_MAX_OUTPUT_DEFAULT = 1024`
    that had no relationship to the length it was asking for. In `job.input` the two sat
    ADJACENT and disagreed:

        "target_words": 900,     # what the LENGTH directive asks the model for
        "max_out": 1024,         # what the wire actually allows

    900 Vietnamese words is ~2300 tokens, so the model was cut off at roughly a third of
    the ask — and it looked like the model writing short. Measured on the Mị Đế book:
    targets of 900/850/800/750/800 produced 445/414/532/618/736 words.

    The chapter path already sizes its budget from the plan
    (`len(scenes) * chapter_gen_per_scene_tokens`, clamped). This is the same idea for the
    scene path, which simply never got it: **guidance and capability must move as one
    signal.** A prompt that asks for 900 words while the wire allows 1024 tokens is not a
    length instruction, it is a truncation.

    `reasoning` adds room for thinking tokens, which are spent BEFORE the prose and drawn
    from the same allowance — without it, enabling reasoning silently halves the space left
    for the passage. It takes the resolved `ReasoningDirective`, not a bare effort string:
    the reasoning-SSOT gate bans threading a loose effort through the engine, and it is
    right to — that is precisely how the sixteen drifting copies this session consolidated
    came about. The caller already holds the directive.

    The result is deliberately generous. A ceiling on a creative draft is a runaway guard,
    not a budget: over-provisioning costs nothing (a model stops when the passage is done
    and you are billed for what it emitted), while under-provisioning truncates mid-sentence
    and you are billed for that too.
    """
    words = target_words or DEFAULT_SCENE_TARGET_WORDS
    lang = (source_language or "").split("-")[0].lower()
    per_word = _TOKENS_PER_WORD.get(lang, _TOKENS_PER_WORD_DEFAULT)
    prose = words * per_word * _OUTPUT_BUDGET_HEADROOM
    effort = (getattr(reasoning, "effort", None) or "none").lower()
    thinking = prose * _REASONING_ALLOWANCE.get(effort, _REASONING_ALLOWANCE_UNKNOWN)
    return max(1, min(ceiling, int(prose + thinking)))


def build_messages(
    packed_prompt: str, profile: BookProfile, operation: str, guide: str = "",
    target_words: int | None = None,
) -> list[dict[str, str]]:
    """System + user messages for the drafter. The packer's structured blocks are
    the grounding; the wrapper carries language + the operation steer.

    ``target_words`` (scene-draft path only) appends an explicit LENGTH directive so the model
    writes a full scene instead of a sketch — a max_output_tokens cap is a ceiling, not a target,
    so with no directive a local model stops early. Callers that are NOT drafting a full scene
    (selection ops, revise) pass None and the prompt is unchanged."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5 — density/pace + present-character voices
    system = (
        "You are a co-writer continuing a novel. Use the provided canon, present "
        "characters, threads, beat, recent prose, and lore as grounding; never "
        "contradict the canon and never introduce facts beyond what is given. "
        "Everything in the context has ALREADY happened earlier in the novel and "
        "the reader has read it: CONTINUE the story forward from that point — do "
        "NOT re-introduce characters, re-describe the established setting, or "
        "re-narrate prior scenes/events already shown; advance new action instead. "
        # Anti-repetition (LOOM-69d): the model-vs-architecture diagnostic found the
        # local drafter reuses a small set of distinctive images/openings across
        # scenes (recurring weather/color motifs, a repeated opening construction).
        # Push for surface variety — a model-agnostic craft nudge.
        "Vary your prose: do NOT reuse a distinctive image, metaphor, or "
        "sentence-opening you have already used in this work (e.g. a recurring "
        "weather or colour motif, or a repeated opening line) — each passage should "
        "read freshly with its own sensory language. "
        # Pacing craft (2026-07-26 pacing diagnostic): mid-arc chapters scored low on
        # "fit to the beat" for three concrete reasons — beats crammed together
        # (whiplash escalation), a uniform action-then-reaction sentence cadence, and
        # emotional turns STATED rather than dramatised. A model-agnostic craft nudge,
        # not tied to any one chapter's content.
        "Control the PACING so the prose rhythm fits the beat: let a rising or "
        "high-tension beat BREATHE — build the dread or anticipation before the turn "
        "and do not rush several escalations together into a few lines. Vary your "
        "sentence rhythm and length — avoid a uniform action-then-reaction cadence "
        "that reads as rapid jump-cuts. And DRAMATISE emotional turning points "
        "through action, sensory detail, and interiority — do NOT state them outright "
        "(not \"the realisation hit her like a blow\"; show the blow landing)."
        + lang + voice + style
    )
    instruction = _OPERATION_INSTRUCTIONS.get(operation, "Write the next passage of the scene.")
    # FD-1 S3 — only fires when open promises were re-injected (the <open_promises>
    # block is present ⇒ narrative_thread is enabled + has open threads). Without a
    # steer the block is inert context; with it, the model advances/pays promises.
    # Gated by the block's presence so the default (flag-off) prompt is unchanged.
    promise_steer = (
        "\n\nThe <open_promises> are unresolved narrative promises/foreshadows the "
        "reader is waiting on: advance or pay one off where it fits this scene; do "
        "NOT silently drop them, and do not contradict canon to force one."
    ) if "<open_promises>" in packed_prompt else ""
    # LENGTH directive — a max_output_tokens cap is a CEILING, not a target; without an explicit
    # word goal the model free-runs short (measured: 83 words). Only on the scene-draft path
    # (target_words passed); selection/revise ops pass None and stay unchanged.
    # SCENE-BOUNDARY — the previous wording ended "keep writing until the planned beats are
    # fully played out", plural and unscoped, while the plan block shows the WHOLE chapter.
    # Length is the more concrete instruction, so it WON: the drafter ran through the
    # neighbouring scenes' beats to reach the word count (measured — scene 1 came back
    # carrying scenes 3 and 4).
    #
    # The repair stays GENERIC on purpose. This directive is shared with `draft_chapter`,
    # where covering every scene is exactly right, so the boundary itself cannot live here
    # — it belongs to the per-operation instruction (see `draft_scene` above). What this
    # must do is stop TELLING the model to widen its scope: reach the length by deepening
    # the passage it was asked for, never by annexing the next one.
    length_steer = (
        f"\n\nLENGTH: write a FULL passage of approximately {target_words} words. Dramatise it "
        "with concrete action, sensory detail, and dialogue where it fits — do NOT summarise, "
        "compress, or stop early; a short sketch is a failure. Reach that length by playing "
        "out the beats THIS passage covers more fully — deeper interiority, sharper sensory "
        "detail, real dialogue — never by extending past the material you were asked to write. "
        # D-LENGTH-DIRECTIVE-INERT (2026-07-31) — the sentence that used to close this
        # directive was "If those beats are genuinely finished, stop: ending a little short is
        # correct, writing beyond your assigned scope is not."
        #
        # MEASURED, 5 live runs on throwaway books (gemma-26b): targets 200/400/900/900/1500
        # produced 565/673/497/625/559 words — ~580 mean, UNCORRELATED with the ask across a
        # 7.5x range, every run finish_reason="stop". The directive was not being ignored; it
        # was being OVERRIDDEN by its own last sentence. A model handed one fuzzy numeric
        # target and an explicit permission to stop early takes the permission, and
        # `draft_scene` separately ends "Stop when THIS scene's beat has played out" — two
        # stop instructions against one soft number.
        #
        # The clause was added by the 2026-07-30 SCENE-BOUNDARY fix, and it was RIGHT to add:
        # before it, length won and the drafter annexed its neighbours' beats to reach the
        # count. That fix over-corrected. What follows keeps the anti-annexation guarantee —
        # the only sanctioned way to gain length is still depth, never scope — while removing
        # the free pass: stopping short now has to be earned, and "a little short" is given a
        # magnitude so a third of the target cannot pass as it.
        "Do not pad, and do not annex the next scene. Stop short ONLY if you have genuinely "
        "exhausted the interiority, sensory detail and dialogue these beats can carry — and a "
        "passage under half the target has not been written fully, it has been summarised."
    ) if target_words and target_words > 0 else ""
    # D-COWRITE-GUIDE-UNSANITIZED (2026-07-31): the SAME `guide` value reaches this
    # function and `build_pack`. The pack neutralises it into a protected `<guide>`
    # segment (assemble.py) — and then this wrapper appended the RAW original again,
    # LAST, which is the strongest position in the prompt for an injection payload.
    # `sanitize_guide` had exactly ONE call site; the wrapper bypassed it twice (here
    # and in `build_revise_messages`), so the guard §13 SEC3 describes was defeated on
    # the live prose path.
    #
    # Sanitising here is a no-op for legitimate guidance (it fullwidth-escapes angle
    # brackets and BRACKETS directive spans rather than deleting them), so the model
    # reads the same instruction — it just can no longer read a forged `<canon>` tag or
    # an "ignore previous instructions" as a command.
    user = packed_prompt + "\n\n" + instruction + promise_steer + length_steer + (
        f"\n\nAuthor guidance: {sanitize_guide(guide)}" if guide else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# T3.2 — selection-scoped operations. DISTINCT from _OPERATION_INSTRUCTIONS (scene
# drafting): these act on a SELECTED passage the author highlighted, not a scene beat.
# build_selection_messages RAISES on an unregistered op (no draft_scene fallback) —
# the LOOM-39 dict.get(key, DEFAULT)-hides-a-missing-enum lesson: a typo'd op must
# NOT silently draft a whole scene over the selection.
_SELECTION_INSTRUCTIONS = {
    "rewrite": "Rewrite the SELECTED PASSAGE below, preserving its events and meaning "
               "but improving the prose. Keep roughly the same length.",
    "expand": "Expand the SELECTED PASSAGE below with more sensory and interior detail, "
              "preserving its meaning and continuity. It should grow longer.",
    "describe": "Enrich the SELECTED PASSAGE below with vivid sensory and scene "
                "description, keeping its events and meaning intact.",
}

# Generous backstop cap (chars). The FE disables the tools above this; the request
# model's Field(max_length=...) 422s a bypass. ~8k chars ≈ a long paragraph or two.
SELECTION_MAX_CHARS = 8000


def build_selection_messages(
    selection: str, profile: BookProfile, operation: str,
    guide: str = "", grounding: str = "",
) -> list[dict[str, str]]:
    """T3.2 — (system, user) for a SELECTION-scoped edit (rewrite/expand/describe).
    EXPLICIT dispatch: an unregistered operation RAISES (never falls back to a scene
    draft — LOOM-39). `grounding` is the packer's structured blocks (canon/lore) when
    a scene_context was supplied; empty → voice-only. Output is ONLY the revised
    passage so the FE can replace the selection verbatim."""
    if operation not in _SELECTION_INSTRUCTIONS:
        raise ValueError(f"unregistered selection operation: {operation!r}")
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5
    system = (
        "You are a co-writer editing a specific passage of a novel. Use any provided "
        "canon, characters, and lore as grounding; never contradict the canon and "
        "never introduce facts beyond what is given. Output ONLY the revised passage "
        "— no preamble, no quotation marks, no commentary." + lang + voice + style
    )
    parts: list[str] = []
    if grounding:
        parts.append(grounding)
    parts.append(_SELECTION_INSTRUCTIONS[operation])
    parts.append("SELECTED PASSAGE:\n" + selection)
    if guide:
        parts.append("Author guidance: " + sanitize_guide(guide))  # D-COWRITE-GUIDE-UNSANITIZED
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]


def build_revise_messages(
    packed_prompt: str, profile: BookProfile, draft: str,
    violations: list[Any],
) -> list[dict[str, str]]:
    """A2-S3b — (system, user) for a canon REVISE pass. The drafter rewrites
    `draft` to remove the confirmed contradictions while preserving the scene.
    Abstract + multilingual-safe (no English-only illustrative phrases)."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5
    system = (
        "You are a co-writer revising a passage to fix continuity errors. The "
        "listed characters are GONE (dead, destroyed, departed, or lost) before "
        "this passage and MUST NOT be portrayed as an active presence — not "
        "acting, speaking, perceiving, or bodily present. Rewrite the passage to "
        "remove these contradictions while preserving its events, intent, voice, "
        "and length. Output ONLY the revised prose." + lang + voice + style
    )
    listed = "\n".join(
        f'- {getattr(v, "name", None) or getattr(v, "entity_id", "?")}'
        f'{(": " + v.span) if getattr(v, "span", "") else ""}'
        for v in violations
    )
    user = (
        f"{packed_prompt}\n\nGONE CHARACTERS WRONGLY PRESENT (fix these):\n{listed}"
        f"\n\nPASSAGE TO REVISE:\n{draft}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def revise_draft(
    sdk: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, Any]], prompt_token_estimate: int,
    max_output_tokens: int, temperature: float = 0.7,
    trace_id: str | None = None, reasoning: ReasoningDirective | None = None,
) -> tuple[str, "DraftMetering"]:
    """One-shot (non-stream) revise: drives `stream_draft` and harvests the
    terminal usage frame. Returns (revised_text, metering). Empty text on LLM
    error (the caller keeps the prior draft → reflect treats it as give-up)."""
    text = ""
    metering = DraftMetering(input_tokens=prompt_token_estimate, output_tokens=0, measured=False)
    async for ev in stream_draft(
        sdk, user_id=user_id, model_source=model_source, model_ref=model_ref,
        messages=messages, prompt_token_estimate=prompt_token_estimate,
        max_output_tokens=max_output_tokens, hard_cap_output=max_output_tokens * 2,
        temperature=temperature, trace_id=trace_id, reasoning=reasoning,
    ):
        if ev["type"] == "usage":
            text, metering = ev["text"], ev["metering"]
    return text, metering


async def stream_draft(
    sdk: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, Any]], prompt_token_estimate: int,
    max_output_tokens: int, hard_cap_output: int | None = None,
    temperature: float = 0.7, trace_id: str | None = None,
    reasoning: ReasoningDirective | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Async generator of stream events for the router to relay as SSE:
      {"type":"token","delta":...} · {"type":"reasoning","delta":...}
      {"type":"capped"} (mid-stream output cap hit) · {"type":"error","error":...}
      {"type":"usage","text":<full prose>,"metering":DraftMetering} (terminal).
    """
    req = StreamRequest(
        model_source=model_source, model_ref=model_ref, messages=messages,
        temperature=temperature, max_tokens=max_output_tokens or None,
        trace_id=trace_id,
        # BOTH reasoning knobs, or neither — via the one seam. This call site used to take a
        # bare effort string, which structurally could not carry `chat_template_kwargs`, and
        # treated "no directive" as "send nothing". A local drafter the platform had
        # misclassified as non-reasoning then kept its template's thinking ON and spent the
        # entire budget on hidden reasoning: an empty draft, billed, reported as success.
        **wire_fields(reasoning),
    )
    parts: list[str] = []
    measured = False
    in_tok = out_tok = 0
    est_out = 0
    capped = False
    finish_reason: str | None = None
    error: str | None = None
    try:
        async for ev in sdk.stream(req, user_id=user_id):
            if isinstance(ev, TokenEvent):
                parts.append(ev.delta)
                yield {"type": "token", "delta": ev.delta}
                est_out += char_estimate(ev.delta)
                if hard_cap_output and est_out > hard_cap_output and not measured:
                    capped = True
                    yield {"type": "capped"}
                    break
            elif isinstance(ev, ReasoningEvent):
                yield {"type": "reasoning", "delta": ev.delta}
            elif isinstance(ev, UsageEvent):
                measured = True
                in_tok = ev.input_tokens or 0
                out_tok = ev.output_tokens or 0
            elif isinstance(ev, DoneEvent):
                # D-COMP-TRUNCATION-SURFACING: the model's stop reason ("length" ⇒
                # hit the cap). Previously discarded.
                finish_reason = ev.finish_reason
    except LLMError as exc:
        logger.warning("stream_draft LLM error: %s", exc)
        error = str(exc)
        yield {"type": "error", "error": error}

    text = "".join(parts)
    # Gate OUTPUT metering on a non-zero output frame specifically: an absent OR
    # zero-output frame is "not measured" → over-estimate from the char model
    # (never meter 0 — the enrichment lesson). A frame may report input but
    # zero output, so the two axes are decided independently.
    out_measured = measured and out_tok > 0
    metering = DraftMetering(
        input_tokens=in_tok if (measured and in_tok > 0) else prompt_token_estimate,
        output_tokens=out_tok if out_measured else char_estimate(text),
        measured=out_measured,
        finish_reason=finish_reason,
    )
    # `error` rides the terminal frame so the router can distinguish a real failure
    # (an LLMError with NO content — a resolve failure metered at 0 → the job is marked
    # FAILED) from a clean finish. A mid-stream error AFTER partial content keeps `text`
    # non-empty: the router keeps the partial work as `completed` but sets truncated=True
    # and carries `error` (finish_reason is None on an error interruption, so the error is
    # what marks it incomplete — the consumers OR it into `truncated`).
    yield {"type": "usage", "text": text, "metering": metering, "capped": capped,
           "error": error}
