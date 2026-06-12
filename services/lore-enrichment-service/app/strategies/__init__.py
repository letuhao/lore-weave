"""Strategy CORE (RAID C8) — the plugin framework every enrichment technique
registers into.

This package is pure scaffolding: the ``EnrichmentStrategy`` interface, a
register-by-key ``StrategyRegistry``, config-driven feature-flags that gate which
techniques are active, and the per-strategy ``CostEstimate`` shape. The concrete
technique bodies land in later cycles (template → C9, retrieval → C10,
fabrication → C16, recook → C17) and are explicitly OUT of scope here.

Locked decisions honoured (OPEN_QUESTIONS_LOCKED.md):
  * Q-R2 — 4 pluggable strategies, phased P1→P2→P3. Only P1 (``template`` +
    ``retrieval``) is ACTIVE by default; ``fabrication``/``recook`` (P2/P3)
    register but stay INACTIVE behind feature-flags until the C15 gate.
  * H0 — this cycle produces NO canon and NO content. A strategy's ``run`` is a
    signature only here; nothing sets ``source_type='glossary'`` or
    confidence=1.0.
  * No hardcoded model names — strategies resolve models via provider-registry
    in their own (later) cycles; there are zero model strings in this package.
"""

from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
    Tier,
)
from app.strategies.feature_flags import (
    DEFAULT_ACTIVE_TECHNIQUES,
    FeatureFlags,
    load_feature_flags,
)
from app.strategies.registry import (
    InactiveStrategyError,
    StrategyRegistry,
    UnknownStrategyError,
)
from app.strategies.template import (
    SCAFFOLD_CONFIDENCE,
    SCAFFOLD_PLACEHOLDER,
    ScaffoldedProposal,
    TemplateStrategy,
)
from app.strategies.factory import (
    GateAwareStrategyFactory,
    GateStatusReader,
    LiveGateStatus,
)
from app.strategies.fabrication import (
    FABRICATION_CONFIDENCE,
    FABRICATION_GAP_COST,
    FabricatedProposal,
    FabricationError,
    FabricationStrategy,
    NeighborFact,
)
from app.strategies.licensing import (
    ADMISSIBLE_LICENSES,
    LicenseStatus,
    SourceLicense,
    UnlicensedSourceError,
    check_admissible,
    is_admissible,
    normalize_license,
)
from app.strategies.recook import (
    RECOOK_CONFIDENCE,
    RECOOK_GAP_COST,
    ReCookedProposal,
    ReCookError,
    ReCookStrategy,
)

__all__ = [
    "CostEstimate",
    "EnrichmentStrategy",
    "StrategyContext",
    "Technique",
    "Tier",
    "FeatureFlags",
    "DEFAULT_ACTIVE_TECHNIQUES",
    "load_feature_flags",
    "StrategyRegistry",
    "UnknownStrategyError",
    "InactiveStrategyError",
    "TemplateStrategy",
    "ScaffoldedProposal",
    "SCAFFOLD_CONFIDENCE",
    "SCAFFOLD_PLACEHOLDER",
    # C16 — fabrication (P2) + gate-aware factory (DEFERRED-054)
    "GateAwareStrategyFactory",
    "GateStatusReader",
    "LiveGateStatus",
    "FabricationStrategy",
    "FabricatedProposal",
    "FabricationError",
    "NeighborFact",
    "FABRICATION_CONFIDENCE",
    "FABRICATION_GAP_COST",
    # C17 — re-cook (P3) + licensing gate
    "ReCookStrategy",
    "ReCookedProposal",
    "ReCookError",
    "RECOOK_CONFIDENCE",
    "RECOOK_GAP_COST",
    "LicenseStatus",
    "SourceLicense",
    "UnlicensedSourceError",
    "ADMISSIBLE_LICENSES",
    "normalize_license",
    "is_admissible",
    "check_admissible",
]
