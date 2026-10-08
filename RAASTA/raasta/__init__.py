"""
RAASTA (راستہ) — a lifelong, self-improving AI companion for students.

Design constraint: **Python standard library only.** No pip install, no build step,
no GPU. It has to run on a ten-year-old laptop in a small Pakistani town.

Public surface:
    from raasta import config, store, bkt, scheduler, pedagogy, psychology
    from raasta import router, agents, orchestrator, evolve, research, language
"""

__version__ = "0.1.0"
__all__ = [
    "config", "store", "language", "bkt", "scheduler", "pedagogy",
    "psychology", "router", "agents", "orchestrator", "evolve",
    "research", "cli",
]
