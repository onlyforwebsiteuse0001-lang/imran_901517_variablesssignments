"""Configuration and defaults.

Every free-tier provider lives here so the system can be re-pointed in one place
when a provider changes its limits (they do, often, and without notice).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


# --------------------------------------------------------------------------
# LLM providers (all have genuinely free, no-credit-card tiers as of Oct 2026)
# --------------------------------------------------------------------------

@dataclass
class Provider:
    name: str
    base_url: str
    env_key: str
    default_model: str
    rpd_limit: int          # requests per day (free tier)
    rpm_limit: int          # requests per minute (free tier)
    tier: str = "standard"  # "fast" = routine turns, "strong" = diagnosis/planning
    enabled: bool = True

    def key(self) -> Optional[str]:
        return os.environ.get(self.env_key) or None

    def available(self) -> bool:
        return self.enabled and bool(self.key())


# Priority order matters: cheapest abundant capacity first, strongest last.
PROVIDERS: List[Provider] = [
    Provider("groq",       "https://api.groq.com/openai/v1",
             "GROQ_API_KEY", "llama-3.3-70b-versatile", 14_400, 30, "fast"),
    Provider("cerebras",   "https://api.cerebras.ai/v1",
             "CEREBRAS_API_KEY", "llama3.1-8b", 14_400, 30, "fast"),
    Provider("gemini",     "https://generativelanguage.googleapis.com/v1beta/openai/",
             "GEMINI_API_KEY", "gemini-2.5-flash", 1_500, 15, "strong"),
    Provider("openrouter", "https://openrouter.ai/api/v1",
             "OPENROUTER_API_KEY", "openrouter/free", 50, 20, "strong"),
    Provider("mistral",    "https://api.mistral.ai/v1",
             "MISTRAL_API_KEY", "mistral-small-latest", 1_000, 60, "standard"),
    Provider("github",     "https://models.inference.ai.azure.com",
             "GITHUB_TOKEN", "gpt-4o-mini", 150, 15, "standard"),
    Provider("huggingface", "https://router.huggingface.co/v1",
             "HF_TOKEN", "meta-llama/Llama-3.1-8B-Instruct", 500, 20, "fast"),
]


@dataclass
class SearchProvider:
    name: str
    endpoint: str
    env_key: str
    monthly_free: int
    kind: str  # "tavily" | "serper" | "brave" | "jina"


SEARCH_PROVIDERS: List[SearchProvider] = [
    SearchProvider("tavily", "https://api.tavily.com/search", "TAVILY_API_KEY", 1_000, "tavily"),
    SearchProvider("serper", "https://google.serper.dev/search", "SERPER_API_KEY", 2_500, "serper"),
    SearchProvider("brave",  "https://api.search.brave.com/res/v1/web/search", "BRAVE_API_KEY", 1_000, "brave"),
]


# --------------------------------------------------------------------------
# Learning-science constants (see docs/RESEARCH.md for sources)
# --------------------------------------------------------------------------

@dataclass
class Learning:
    """Knobs grounded in the research. Change carefully; each one is cited."""
    # BKT priors
    p_init: float = 0.05          # prior mastery of an unseen skill
    p_transit: float = 0.12       # learning rate per opportunity
    p_slip: float = 0.10          # mistake despite mastery
    p_guess_mcq4: float = 0.25    # guess rate for 4-option MCQ
    p_guess_free: float = 0.05    # guess rate for constructed response

    # Per-student parameter adaptation (BBKT-lite)
    # Real fitted BKT transit rates sit around 0.05-0.20; anything near 0.5
    # means the model believes a student learns a skill in two questions,
    # which is how you end up certifying mastery nobody has earned.
    adapt_rate: float = 0.07      # EMA weight for online transit/slip fitting
    transit_min: float = 0.02
    transit_max: float = 0.30
    slip_min: float = 0.02
    slip_max: float = 0.35

    # Forgetting (spacing): half-life grows with successful repetitions
    forget_base_days: float = 1.0
    forget_growth: float = 1.6    # half-life *= growth per successful rep
    forget_cap_days: float = 180.0

    # Spaced-repetition scheduling
    interval_min_days: float = 1.0
    interval_max_days: float = 180.0
    ease_init: float = 2.2
    ease_min: float = 1.3
    ease_max: float = 2.8
    target_accuracy: float = 0.85  # the "desirable difficulty" sweet spot

    # Mastery
    mastery_threshold: float = 0.85
    review_threshold: float = 0.60   # below this we re-teach, not just review

    # Session shape
    max_new_items_per_session: int = 3
    review_cap_per_session: int = 12
    default_budget_minutes: int = 25


@dataclass
class MotivationCfg:
    """Self-Determination-Theory-grounded settings. Anti-dark-pattern by default."""
    grace_days_per_month: int = 2       # streaks must be survivable
    praise_strategy_not_ability: bool = True
    leaderboards_public: bool = False   # shaming mechanics are off
    rest_days_per_week_min: int = 1
    late_night_hour: int = 1            # activity after 01:00 counts as late
    #: Local time = UTC + this. Pakistan is UTC+5. Getting this wrong means a
    #: student studying at 2am PKT gets logged as 9pm and the burnout guard
    #: never sees the signal that matters most.
    utc_offset_hours: float = 5.0
    max_session_minutes: int = 90
    # Calibrated so that the burnout *triad* (high volume + no rest days +
    # late nights) crosses the rest threshold on its own, without waiting for
    # accuracy to collapse — by then the damage is already done.
    burnout_reduce_load: float = 0.40
    burnout_mandate_rest: float = 0.65


@dataclass
class Config:
    db_path: str = "raasta.db"
    providers: List[Provider] = field(default_factory=lambda: list(PROVIDERS))
    search: List[SearchProvider] = field(default_factory=lambda: list(SEARCH_PROVIDERS))
    learning: Learning = field(default_factory=Learning)
    motivation: MotivationCfg = field(default_factory=MotivationCfg)
    offline: bool = False            # force the deterministic offline engine
    request_timeout_s: int = 45
    cache_enabled: bool = True
    research_enabled: bool = True
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        db = os.environ.get("RAASTA_DB", "raasta.db")
        return cls(
            db_path=db,
            offline=os.environ.get("RAASTA_OFFLINE", "") == "1",
            cache_enabled=os.environ.get("RAASTA_NO_CACHE", "") != "1",
            research_enabled=os.environ.get("RAASTA_NO_RESEARCH", "") != "1",
            verbose=os.environ.get("RAASTA_VERBOSE", "") == "1",
        )

    def to_dict(self) -> Dict:
        d = asdict(self)
        # never serialise secrets; we only ever read them from the environment
        return d


DEFAULT_CONFIG = Config()
