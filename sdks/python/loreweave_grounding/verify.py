"""Canon-verify — consistency check over generated facts (mui #3 grounding port).

Lifted from lore-enrichment-service `app/verify/canon_verify.py`, generalized to
be service-agnostic:
  • the dead `read_port`/GraphStats coupling is DROPPED (FIX-1 had already removed
    the graph-stats gate; `_read_stats` was uncalled), so the SDK verifier needs
    no knowledge client.
  • inputs are duck-typed Protocols (ProposalLike + FactLike) — a consumer passes
    its own domain objects unchanged.
  • the anachronism markers + canon lookup are INJECTED (no hardcoded worldview —
    honours the NEUTRAL_PROFILE invariant). The 封神 marker table ships as a named
    constant a consumer may opt into.

Four checks, each emitting typed `VerifyFlag` evidence (never an opaque bool):
contradiction (vs authored canon), anachronism (injected denylist), injection
(neutralize), regurgitation (copyright). ANNOTATES only — never writes canon,
never lifts quarantine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Sequence

from .ports import FactLike, ProposalLike
from .regurgitation import detect_regurgitation
from .sanitize import _prenormalize, neutralize_proposal_text, scan_injection

__all__ = [
    "FlagKind",
    "Severity",
    "VerifyFlag",
    "VerifyResult",
    "CanonFact",
    "CanonLookupFn",
    "CanonVerifier",
    "ANACHRONISM_MARKERS",
    "FENGSHEN_ANACHRONISM_MARKERS",
]


class FlagKind(str, Enum):
    """The consistency dimensions checked (the ``kind`` of a flag)."""

    CONTRADICTION = "contradiction"
    ANACHRONISM = "anachronism"
    INJECTION = "injection"
    REGURGITATION = "regurgitation"


class Severity(str, Enum):
    """Advisory weight for human review. Even ``high`` never auto-rejects here."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class VerifyFlag:
    """One consistency concern — evidence, not a boolean."""

    kind: FlagKind
    dimension: str
    evidence: str
    severity: Severity = Severity.MEDIUM


@dataclass(frozen=True)
class CanonFact:
    """An existing authored-canon assertion for an entity+dimension (read-only).

    ``assertion`` is the canon text; ``terms`` are the salient canon tokens a
    contradicting generated fact would have to negate."""

    entity_name: str
    dimension: str
    assertion: str
    terms: tuple[str, ...] = ()


#: Injected canon-fact lookup: (entity_name, dimension) → canon assertions, read
#: through the glossary/KG SSOT. Returns ``[]`` when nothing is known. Async so a
#: real impl can hit a client; tests inject a deterministic stub.
CanonLookupFn = Callable[[str, str], Awaitable[Sequence[CanonFact]]]


@dataclass
class VerifyResult:
    """The outcome of verifying one proposal's generated facts.

    ``passed`` is True iff NO flags fired AND the contradiction check ran against
    real canon (not degraded). A degraded run is NOT a pass (no false-green)."""

    flags: list[VerifyFlag] = field(default_factory=list)
    verify_degraded: bool = False
    neutralized: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.flags and not self.verify_degraded

    def as_provenance(self) -> dict[str, object]:
        """Serialize for persistence. Annotation only — carries no source_type /
        confidence / canon marker."""
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
# Anachronism frame — the 商周 / 封神演义 cosmology denylist (OPT-IN data).
# A consumer that wants the Fengshen frame passes FENGSHEN_ANACHRONISM_MARKERS;
# a different book supplies its own (or none → the check is off). No hardcoded
# worldview in the check logic itself.
# ═══════════════════════════════════════════════════════════════════════════
FENGSHEN_ANACHRONISM_MARKERS: tuple[tuple[str, str], ...] = (
    ("秦始皇", "秦朝晚于商周封神纪元"),
    ("汉朝", "汉朝晚于商周封神纪元"),
    ("唐朝", "唐朝晚于商周封神纪元"),
    ("宋朝", "宋朝晚于商周封神纪元"),
    ("明朝", "明朝晚于商周封神纪元"),
    ("清朝", "清朝晚于商周封神纪元"),
    ("科举", "科举制始于隋唐，非商周"),
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
    ("雷达", "雷达为现代科技产物"),
    ("坦克", "坦克为近现代军事产物"),
    ("卫星", "人造卫星为现代科技产物"),
    ("无人机", "无人机为现代科技产物"),
    ("疫苗", "疫苗为近现代医学产物"),
    ("电灯", "电灯为近现代产物"),
    ("电力", "电力应用为近现代，非商周"),
    ("佛祖", "佛教东传远晚于商周封神纪元"),
    ("和尚", "佛教僧侣晚于商周"),
    ("寺庙", "佛寺晚于商周"),
    ("基督", "基督教非东方上古封神体系"),
    ("耶稣", "基督教非东方上古封神体系"),
    ("银两", "白银货币流通远晚于商周"),
    ("纸币", "纸币远晚于商周"),
    ("隋朝", "隋朝晚于商周封神纪元"),
    ("电报", "电报为近代产物"),
    ("电影", "电影为近现代产物"),
    ("电梯", "电梯为近现代产物"),
    ("收音机", "收音机为现代产物"),
    ("冰箱", "冰箱为现代产物"),
    ("空调", "空调为现代产物"),
    ("照相机", "照相机为近现代产物"),
    ("高铁", "高铁为现代产物"),
    ("地铁", "地铁为现代产物"),
    ("导弹", "导弹为现代军事产物"),
    ("核弹", "核武器为现代军事产物"),
    ("原子弹", "原子弹为现代军事产物"),
    ("机器人", "机器人为现代产物"),
    ("抗生素", "抗生素为现代医学产物"),
    ("显微镜", "显微镜为近现代科学仪器"),
    ("望远镜", "望远镜为近现代科学仪器"),
    ("伊斯兰", "伊斯兰教非东方上古封神体系"),
    ("教堂", "基督教堂非商周封神体系"),
    ("牧师", "基督教牧师非商周封神体系"),
    ("圣经", "基督教圣经非东方上古封神体系"),
    ("喇嘛", "藏传佛教喇嘛远晚于商周"),
    ("股票", "股票为近现代金融产物"),
)

#: Back-compat alias (de-bias C1 demoted this from a GLOBAL default to opt-in).
ANACHRONISM_MARKERS = FENGSHEN_ANACHRONISM_MARKERS

# Chinese contradiction / negation markers — a negation directly governing a canon
# term means the generated fact asserts the OPPOSITE of canon.
_NEGATION_MARKERS: tuple[str, ...] = (
    "不是", "并非", "并不是", "绝非", "从未", "从来不", "没有", "毫无",
    "而非", "并无",
)
#: Proximity bound: a negation marker only contradicts a canon term when it
#: appears within this many chars IMMEDIATELY BEFORE the term.
_NEGATION_WINDOW: int = 10
# Latin-script negation (in case grounding/excerpt leaked English).
_EN_NEGATION_RE = re.compile(
    r"\b(?:is\s+not|was\s+not|never|no\s+longer|not\s+a|isn't|wasn't|"
    r"contrary\s+to|rather\s+than)\b",
    re.IGNORECASE,
)


class CanonVerifier:
    """Run the four consistency checks over a proposal's generated facts.

    Construct with an injected `CanonLookupFn` (canon assertions for an
    entity+dimension, read through glossary/KG SSOT) and the anachronism marker
    denylist (empty = anachronism check off — a sci-fi/modern book is never
    flagged for 'modern tech'). `verify` returns a `VerifyResult`. Annotates
    only — no write-back, no canon, no quarantine lift, no model name."""

    def __init__(
        self,
        *,
        canon_lookup: CanonLookupFn,
        anachronism_markers: Sequence[tuple[str, str]] = (),
    ) -> None:
        self._canon_lookup = canon_lookup
        self._anachronism_markers = tuple(anachronism_markers)

    async def verify(
        self,
        proposal: ProposalLike,
        facts: Sequence[FactLike],
        *,
        jwt: str = "",  # accepted + ignored (migration compat; the dead graph-stats gate is gone)
    ) -> VerifyResult:
        """Verify a proposal + its generated facts; return an annotation result.

        Runs injection-defense (multi-field) FIRST, then anachronism, then
        regurgitation, then contradiction (vs canon read through the injected
        lookup). NEVER mutates inputs; degrades safely when the canon read fails
        (records ``verify_degraded``, no false-green)."""
        result = VerifyResult()

        # (c) injection — entity name + grounding excerpts + per-fact dimension
        #     label + content. Run FIRST so neutralized text is what the rest see.
        self._check_injection_field("canonical_name", proposal.canonical_name, result)
        for g in proposal.grounding:
            self._check_injection_field(
                f"grounding:{g.corpus_id}#{g.chunk_index}", g.excerpt, result
            )
        for fact in facts:
            self._check_injection_field(
                f"dimension_label:{fact.dimension}", fact.dimension, result
            )
            self._check_injection_field(f"content:{fact.dimension}", fact.content, result)

        # (b) anachronism — generated content vs the injected denylist.
        for fact in facts:
            self._check_anachronism(fact, result)

        # (d) regurgitation — copyright layer ③: raw generated content vs the
        #     source excerpts (verbatim-overlap detection).
        self._check_regurgitation(proposal, facts, result)

        # (a) contradiction — vs authored canon (injected lookup).
        await self._check_contradiction(proposal, facts, result)

        return result

    # ── (c) injection ─────────────────────────────────────────────────────────
    def _check_injection_field(
        self, field_name: str, text: str, result: VerifyResult
    ) -> None:
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
    def _check_anachronism(self, fact: FactLike, result: VerifyResult) -> None:
        content = _prenormalize(fact.content)
        for term, reason in self._anachronism_markers:
            if term in content:
                result.flags.append(
                    VerifyFlag(
                        kind=FlagKind.ANACHRONISM,
                        dimension=fact.dimension,
                        evidence=f"出现「{term}」：{reason}",
                        severity=Severity.MEDIUM,
                    )
                )

    # ── (d) regurgitation ─────────────────────────────────────────────────────
    def _check_regurgitation(
        self, proposal: ProposalLike, facts: Sequence[FactLike], result: VerifyResult
    ) -> None:
        excerpts = [g.excerpt for g in proposal.grounding if getattr(g, "excerpt", "")]
        if not excerpts:
            return
        for fact in facts:
            res = detect_regurgitation(fact.content, excerpts)
            if not res.flagged:
                continue
            result.flags.append(
                VerifyFlag(
                    kind=FlagKind.REGURGITATION,
                    dimension=fact.dimension,
                    evidence=res.evidence,
                    severity=Severity.HIGH if res.severity == "high" else Severity.MEDIUM,
                )
            )

    # ── (a) contradiction ─────────────────────────────────────────────────────
    async def _check_contradiction(
        self, proposal: ProposalLike, facts: Sequence[FactLike], result: VerifyResult
    ) -> None:
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

    async def _lookup_canon(
        self, entity_name: str, dimension: str, result: VerifyResult
    ) -> Sequence[CanonFact]:
        """Look up canon assertions through the injected seam. A lookup ERROR is
        NOT an empty result: it marks the verify degraded (forces passed=False) so
        a 'couldn't check' run is never a false-green. A genuinely-empty lookup
        (no exception) returns ``()`` without degrading."""
        try:
            return await self._canon_lookup(entity_name, dimension)
        except Exception:  # noqa: BLE001 — degrade, never raise into the verifier
            result.verify_degraded = True
            return ()

    @staticmethod
    def _contradicted_term(content: str, canon: CanonFact) -> str | None:
        """Return the canon term the content NEGATES, or None. A contradiction is
        a canon term placed within `_NEGATION_WINDOW` chars after a negation
        marker (并非东海 / rather than Dracula). Conservative — under-fires."""
        if not canon.terms:
            return None
        for term in canon.terms:
            if not term:
                continue
            start = 0
            while True:
                i = content.find(term, start)
                if i < 0:
                    break
                window = content[max(0, i - _NEGATION_WINDOW):i]
                if any(neg in window for neg in _NEGATION_MARKERS) or (
                    _EN_NEGATION_RE.search(window)
                ):
                    return term
                start = i + len(term)
        return None
