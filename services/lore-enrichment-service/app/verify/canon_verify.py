"""Canon-verify (RAID C12, M2) — consistency check at proposal creation.

When the C11 generator mints enriched facts for a proposal, this module runs a
THREE-CHECK consistency pass over them and ANNOTATES the proposal with the
result. It does NOT judge correctness (that rests on the human PROMOTE gate, H0)
and it NEVER lifts quarantine — a "passed" verify is a note, not an admission.

Three checks (each emits typed :class:`VerifyFlag` evidence, never an opaque
boolean):

  1. **Contradiction** — does a generated fact assert something INCOMPATIBLE with
     existing canon (a ``source_type='glossary'`` entity/fact) read through the C1
     :class:`~app.clients.port.KnowledgeReadPort` + an injected canon-fact lookup?
     Detected via canon-term presence + a negation/contradiction marker in the
     generated content for the SAME entity+dimension. When the KG-read port is
     unavailable / empty (Q6), the check records ``verify_degraded=True`` and does
     NOT auto-pass — a down KG can never produce a false-green.
  2. **Anachronism** — does the generated CHINESE content reference concepts/eras
     outside the locked 商周 / 封神演义 cosmology frame (e.g. modern tech, post-Han
     dynasties, foreign religions)? Operates on Chinese text via a curated
     out-of-era marker table (NOT an English wordlist); each flag carries the
     matched span as evidence.
  3. **Injection-defense** — neutralize prompt-injection / canon-spoofing /
     control sequences embedded in the entity name, dimension label, generated
     content, AND retrieved grounding excerpts (mirror knowledge-service
     ``pending_facts``, Q1). A hit raises an ``injection`` flag AND the verifier
     surfaces the neutralized text so downstream consumers never see the live
     directive.

H0 / scope boundary (LOCKED): this module ONLY annotates. It sets no
``source_type``, never raises ``confidence`` to 1.0, never clears
``pending_validation``, never writes back to glossary / Neo4j / KG (that is C13),
and resolves no model name. A flagged proposal is MARKED (quarantined harder, not
silently dropped); the human gate decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Sequence
from uuid import UUID

from app.clients.knowledge import GraphStats
from app.clients.port import KnowledgeReadPort
from app.generation.provenance import EnrichedFact
from app.retrieval.strategy import GroundedProposal
from app.verify.sanitize import (
    _prenormalize,
    neutralize_proposal_text,
    scan_injection,
)

__all__ = [
    "FlagKind",
    "Severity",
    "VerifyFlag",
    "VerifyResult",
    "CanonFact",
    "CanonLookupFn",
    "CanonVerifier",
    "ANACHRONISM_MARKERS",
]


class FlagKind(str, Enum):
    """The three consistency dimensions C12 checks (the ``kind`` of a flag)."""

    CONTRADICTION = "contradiction"
    ANACHRONISM = "anachronism"
    INJECTION = "injection"


class Severity(str, Enum):
    """How hard a flag should weigh on the human review. Advisory only — even a
    ``high`` flag never auto-rejects; it raises the proposal's review priority."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class VerifyFlag:
    """One consistency concern found in a proposal — evidence, not a boolean.

    ``kind``      — contradiction | anachronism | injection.
    ``dimension`` — the dimension (or field name) the concern is in.
    ``evidence``  — a human-readable string (matched span / canon term / pattern
                    name) so a reviewer can SEE why it fired, never an opaque bit.
    ``severity``  — advisory weight for review prioritisation.
    """

    kind: FlagKind
    dimension: str
    evidence: str
    severity: Severity = Severity.MEDIUM


@dataclass(frozen=True)
class CanonFact:
    """An existing authored-canon assertion for an entity+dimension (read-only).

    The contradiction check compares a generated fact against these. They are
    ``source_type='glossary'`` canon (confidence 1.0) — the verifier reads them,
    never writes them (Q2). ``assertion`` is the canon text; ``terms`` are the
    salient canon tokens (names/values) a contradicting generated fact would have
    to negate.
    """

    entity_name: str
    dimension: str
    assertion: str
    terms: tuple[str, ...] = ()


#: Injected canon-fact lookup: (entity_name, dimension) → the canon assertions for
#: that pair, read through the glossary/KG SSOT. Returns ``[]`` when nothing is
#: known. Async so a real impl can hit the C1 glossary client; tests inject a
#: deterministic stub. The verifier NEVER writes through this seam.
CanonLookupFn = Callable[[str, str], Awaitable[Sequence[CanonFact]]]


@dataclass
class VerifyResult:
    """The outcome of verifying one proposal's generated facts.

    ``passed``          — True iff NO flags fired AND the contradiction check ran
                          against real canon (not degraded). A degraded run is
                          NOT a pass (no false-green).
    ``flags``           — every concern found, with evidence.
    ``verify_degraded`` — True when the KG/canon read was unavailable/empty, so
                          the contradiction check could not be performed. Recorded
                          explicitly — a degraded verify is conservative, never a
                          silent green.
    ``neutralized``     — per-field neutralized text for any field that carried
                          injection (so the caller persists the SAFE form).
    """

    flags: list[VerifyFlag] = field(default_factory=list)
    verify_degraded: bool = False
    neutralized: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """A proposal PASSES only if it is flag-free AND was verified against real
        canon. Degradation never counts as a pass (H0 / no-false-green)."""
        return not self.flags and not self.verify_degraded

    def as_provenance(self) -> dict[str, object]:
        """Serialize for persistence into ``provenance_json`` / a verify field.

        Annotation only — carries NO ``source_type`` / ``confidence`` / canon
        marker. A later cycle merges this into the proposal's provenance; it can
        never move the proposal toward canon.
        """
        return {
            "canon_verify": {
                "passed": self.passed,
                "verify_degraded": self.verify_degraded,
                "flags": [
                    {
                        "kind": f.kind.value,
                        "dimension": f.dimension,
                        "evidence": f.evidence,
                        "severity": f.severity.value,
                    }
                    for f in self.flags
                ],
            }
        }


# ═══════════════════════════════════════════════════════════════════════════
# Anachronism frame — locked 商周 / 封神演义 cosmology.
#
# Out-of-era CONCEPT markers in CHINESE (the locked output language). These are
# eras / technologies / institutions / faiths that postdate or sit outside the
# Shang–Zhou + 封神 mythological frame, so their appearance in generated lore is
# an anachronism worth flagging for the human reviewer. NOT an English wordlist;
# each entry is the Chinese term plus a short reason used as flag evidence.
#
# Deliberately CONSERVATIVE: only unambiguous out-of-era tokens, to avoid
# over-reach on legitimate Classical-Chinese vocabulary. The list is data (not
# code) so it can grow without touching the check logic.
# ═══════════════════════════════════════════════════════════════════════════
ANACHRONISM_MARKERS: tuple[tuple[str, str], ...] = (
    # ── later dynasties / post-Zhou polities (era-inappropriate) ─────────────
    ("秦始皇", "秦朝晚于商周封神纪元"),
    ("汉朝", "汉朝晚于商周封神纪元"),
    ("唐朝", "唐朝晚于商周封神纪元"),
    ("宋朝", "宋朝晚于商周封神纪元"),
    ("明朝", "明朝晚于商周封神纪元"),
    ("清朝", "清朝晚于商周封神纪元"),
    ("科举", "科举制始于隋唐，非商周"),
    # ── modern technology / industry ─────────────────────────────────────────
    ("火车", "火车为近代工业产物"),
    ("飞机", "飞机为近现代产物"),
    ("电话", "电话为近现代产物"),
    ("电脑", "电脑为现代产物"),
    ("手机", "手机为现代产物"),
    ("电视", "电视为现代产物"),
    ("汽车", "汽车为近现代产物"),
    ("枪炮", "火器枪炮非商周冷兵器时代"),
    ("火药", "火药发明远晚于商周"),
    ("互联网", "互联网为现代产物"),
    # NOTE: deliberately NOT a bare "电" marker — it false-positives on
    # era-appropriate Classical words like 雷电 (thunder & lightning). The
    # compound modern-tech markers above (电话/电脑/电视) cover the real cases.
    ("电灯", "电灯为近现代产物"),
    ("电力", "电力应用为近现代，非商周"),
    # ── foreign / later faiths + currency anachronisms ───────────────────────
    ("佛祖", "佛教东传远晚于商周封神纪元"),
    ("和尚", "佛教僧侣晚于商周"),
    ("寺庙", "佛寺晚于商周"),
    ("基督", "基督教非东方上古封神体系"),
    ("耶稣", "基督教非东方上古封神体系"),
    ("银两", "白银货币流通远晚于商周"),
    ("纸币", "纸币远晚于商周"),
)

# Chinese contradiction / negation markers — when one of these co-occurs with a
# canon term in a generated value for the same entity+dimension, the generated
# fact is asserting the OPPOSITE of canon → contradiction.
_NEGATION_MARKERS: tuple[str, ...] = (
    "不是", "并非", "并不是", "绝非", "从未", "从来不", "没有", "毫无",
    "实为", "实则", "其实是", "而非", "并无",
)
# Latin-script negation (in case grounding/excerpt leaked English).
_EN_NEGATION_RE = re.compile(
    r"\b(?:is\s+not|was\s+not|never|no\s+longer|not\s+a|isn't|wasn't|"
    r"contrary\s+to|rather\s+than)\b",
    re.IGNORECASE,
)


class CanonVerifier:
    """Run the three C12 consistency checks over a proposal's generated facts.

    Construct with the C1 :class:`KnowledgeReadPort` (graph reachability /
    degradation) and an injected :data:`CanonLookupFn` (canon assertions for an
    entity+dimension, read through glossary/KG SSOT). :meth:`verify` returns a
    :class:`VerifyResult`. It ANNOTATES only — H0: no write-back, no canon, no
    quarantine lift, no model name.
    """

    def __init__(
        self,
        *,
        read_port: KnowledgeReadPort,
        canon_lookup: CanonLookupFn,
    ) -> None:
        self._port = read_port
        self._canon_lookup = canon_lookup

    async def verify(
        self,
        proposal: GroundedProposal,
        facts: Sequence[EnrichedFact],
        *,
        jwt: str = "",
    ) -> VerifyResult:
        """Verify a proposal + its generated facts; return an annotation result.

        Runs injection-defense (multi-field), anachronism (Chinese content), and
        contradiction (vs canon read through the C1 port). NEVER mutates the
        proposal or the facts; NEVER lifts quarantine; degrades safely when the KG
        is down (records ``verify_degraded``, no false-green).
        """
        result = VerifyResult()

        # ── (c) injection-defense — entity name + grounding excerpts + per-fact
        #        dimension label + content. Run FIRST so neutralized text is what
        #        the other checks (and downstream persistence) see. ────────────
        self._check_injection_field(
            "canonical_name", proposal.canonical_name, result
        )
        for g in proposal.grounding:
            self._check_injection_field(
                f"grounding:{g.corpus_id}#{g.chunk_index}", g.excerpt, result
            )
        for fact in facts:
            self._check_injection_field(
                f"dimension_label:{fact.dimension}", fact.dimension, result
            )
            self._check_injection_field(
                f"content:{fact.dimension}", fact.content, result
            )

        # ── (b) anachronism — Chinese generated content, locked 商周/封神 frame ──
        for fact in facts:
            self._check_anachronism(fact, result)

        # ── (a) contradiction — vs canon read through the C1 port (Q6 degrade) ─
        await self._check_contradiction(proposal, facts, result, jwt=jwt)

        return result

    # ── (c) injection ─────────────────────────────────────────────────────────
    def _check_injection_field(
        self, field_name: str, text: str, result: VerifyResult
    ) -> None:
        """Neutralize one untrusted field; on a hit, flag + record the safe text.

        Multi-field by design — called for the entity name, every dimension
        label, every content value, and every grounding excerpt, so a payload in
        ANY of them is caught (not just the obvious content field).
        """
        safe, hits = neutralize_proposal_text(text)
        if hits > 0:
            result.neutralized[field_name] = safe
            spans = scan_injection(text)
            patterns = ", ".join(sorted({name for name, _s, _e in spans})) or "control"
            result.flags.append(
                VerifyFlag(
                    kind=FlagKind.INJECTION,
                    dimension=field_name,
                    evidence=f"neutralized {hits} injection span(s) [{patterns}]",
                    severity=Severity.HIGH,
                )
            )

    # ── (b) anachronism ───────────────────────────────────────────────────────
    def _check_anachronism(self, fact: EnrichedFact, result: VerifyResult) -> None:
        """Flag out-of-era CONCEPT markers in the generated Chinese content.

        Operates on the Chinese text (locked: anachronism on Chinese). Each marker
        is an unambiguous post-商周 / non-封神 concept; a hit carries the matched
        term + the reason as evidence (never an opaque boolean).

        Scans the PRE-NORMALIZED content (strip zero-width / bidi + NFKC) exactly
        like the injection scanner, so a zero-width-smuggled marker such as
        ``火‍车`` (火 + ZWJ + 车) cannot evade the denylist via a substring miss.
        """
        content = _prenormalize(fact.content)
        for term, reason in ANACHRONISM_MARKERS:
            if term in content:
                result.flags.append(
                    VerifyFlag(
                        kind=FlagKind.ANACHRONISM,
                        dimension=fact.dimension,
                        evidence=f"出现「{term}」：{reason}",
                        severity=Severity.MEDIUM,
                    )
                )

    # ── (a) contradiction ─────────────────────────────────────────────────────
    async def _check_contradiction(
        self,
        proposal: GroundedProposal,
        facts: Sequence[EnrichedFact],
        result: VerifyResult,
        *,
        jwt: str,
    ) -> None:
        """Flag a generated fact that NEGATES an existing canon assertion.

        Reachability/degradation is decided through the C1 read port: if the graph
        is unavailable or empty (Q6), the canon read cannot be trusted, so we
        record ``verify_degraded=True`` and DO NOT pass — a down KG never yields a
        false-green. When canon IS available, a generated value that mentions a
        canon term together with a negation marker (Chinese or English) for the
        same entity+dimension is flagged as a contradiction with evidence.
        """
        stats = await self._read_stats(proposal, jwt=jwt)
        if stats is None or stats.is_empty:
            # No reachable / non-empty canon graph → cannot verify contradiction.
            result.verify_degraded = True
            return

        for fact in facts:
            canon_facts = await self._lookup_canon(
                proposal.canonical_name, fact.dimension, result
            )
            for canon in canon_facts:
                term = self._contradicted_term(fact.content, canon)
                if term is not None:
                    result.flags.append(
                        VerifyFlag(
                            kind=FlagKind.CONTRADICTION,
                            dimension=fact.dimension,
                            evidence=(
                                f"与既有正典「{canon.entity_name}·{canon.dimension}」"
                                f"相抵触（正典断言：{canon.assertion}；冲突词：{term}）"
                            ),
                            severity=Severity.HIGH,
                        )
                    )
                    break  # one contradiction per (fact, canon) is enough evidence

    async def _read_stats(
        self, proposal: GroundedProposal, *, jwt: str
    ) -> GraphStats | None:
        """Read graph-stats through the C1 port; None on a degraded read.

        The port itself degrades typed-errors to empties (Q6), so a None here only
        happens on a project_id that is not a UUID (a malformed proposal) — also a
        degradation signal, not a hard crash.
        """
        try:
            project_uuid = UUID(proposal.project_id)
        except (ValueError, AttributeError):
            return None
        return await self._port.get_graph_stats(jwt=jwt, project_id=project_uuid)

    async def _lookup_canon(
        self, entity_name: str, dimension: str, result: VerifyResult
    ) -> Sequence[CanonFact]:
        """Look up canon assertions for an entity+dimension through the seam.

        Never raises into the verifier, but a lookup ERROR is NOT the same as an
        empty result: a swallowed exception means the canon read could not run for
        this dimension, so we MUST mark the verify degraded (``verify_degraded``
        forces ``passed=False``). Returning ``()`` silently on an error would make
        a "couldn't check" run indistinguishable from "no canon known" and let the
        contradiction loop find nothing → a false-green ``verified_clean``. A
        genuinely-empty lookup (no exception) returns ``()`` without degrading."""
        try:
            return await self._canon_lookup(entity_name, dimension)
        except Exception:
            result.verify_degraded = True
            return ()

    @staticmethod
    def _contradicted_term(content: str, canon: CanonFact) -> str | None:
        """Return the canon term the content negates, or None.

        Heuristic (consistency, not correctness): a contradiction is a canon term
        appearing in the generated content alongside a negation/contradiction
        marker (Chinese ``不是/并非/实为…`` or English ``is not/never/rather than``).
        Returns the first such canon term as evidence; None when no canon term is
        negated.
        """
        if not canon.terms:
            return None
        has_negation = any(neg in content for neg in _NEGATION_MARKERS) or bool(
            _EN_NEGATION_RE.search(content)
        )
        if not has_negation:
            return None
        for term in canon.terms:
            if term and term in content:
                return term
        return None
