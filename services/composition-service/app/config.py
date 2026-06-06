"""composition-service settings (LOOM Composition V0 — M0).

pydantic-settings BaseSettings — the service fails to start if any
required secret/DSN is missing (CLAUDE.md: no hardcoded secrets).
Mirrors knowledge-service's config shape; single DB (loreweave_composition).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — service fails to start if any of these are missing.
    composition_db_url: str
    internal_service_token: str
    jwt_secret: str

    # Optional with defaults.
    redis_url: str = "redis://redis:6379"
    log_level: str = "INFO"
    port: int = 8093

    # Internal service URLs — consumed by the M3 client wrappers.
    knowledge_internal_url: str = "http://knowledge-service:8092"
    glossary_internal_url: str = "http://glossary-service:8088"
    book_internal_url: str = "http://book-service:8082"
    llm_gateway_internal_url: str = "http://provider-registry-service:8085"

    # Packer budget knobs (M4) — declared here so config is stable across
    # milestones; unused until the packer lands.
    pack_token_budget: int = 6000

    # V1 Phase A1 — diverge→converge. Number of candidate drafts per auto generate
    # (the only K-multiplied call; cost ~K drafts). A3 makes this adaptive per
    # scene; until then it's the fixed default. K=1 degenerates to the V0 loop.
    compose_diverge_k: int = 3
    compose_diverge_temperature: float = 0.8

    # V1 Phase A3 — decompose planner + adaptive K.
    # plan_max_chapters: refuse to decompose a book with more active chapters
    # than this (bounds the per-chapter Level-2 LLM fan-out). plan_*_scenes:
    # the LLM-chosen scene count per chapter is clamped to this range.
    # plan_high_tension_threshold: scene tension at/above which adaptive K spends
    # the full ceiling (climax/midpoint beats); below it spends less. Tension is
    # the EXISTING 0..100 scale (outline_node.tension / reasoning policy, which
    # gates "high dramatic tension" at >=70) — NOT 1-5.
    plan_max_chapters: int = 40
    plan_min_scenes_per_chapter: int = 1
    plan_max_scenes_per_chapter: int = 6
    plan_high_tension_threshold: int = 70

    # S2 compress — when the packer's raw "story so far" (prior-scene prose)
    # exceeds this many chars, compress the OLDER portion into a state summary
    # (keeping the last N immediate paragraphs verbatim) so long chapters don't
    # blow the prompt budget. ~4 chars/token → 6000 chars ≈ 1500 tokens.
    pack_compress_recent_threshold_chars: int = 6000
    pack_compress_keep_immediate: int = 2


settings = Settings()  # type: ignore[call-arg]
