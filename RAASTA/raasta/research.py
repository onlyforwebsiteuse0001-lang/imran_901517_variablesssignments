"""The research agent: keeps RAASTA's knowledge current, and keeps it honest.

Two jobs, both continuous:

1. **Domain research** — new findings in learning science, motivation, and the
   Pakistani education/ career landscape (syllabus changes, entry-test formats,
   scholarship deadlines, job-market signals). Free search tiers are enough:
   Tavily 1,000/month, Serper 2,500, Brave ~1,000/month, Jina Reader 1M tokens.

2. **Self-research** — the harder and more valuable half. The agent reads its own
   eval runs and reflections and asks *"what is failing, and for whom?"* then
   proposes ONE hypothesis at a time for the playbook to test.

Everything is quota-metered and degrades to "no network, no key" without breaking.
A research agent that silently burns the monthly quota in an hour is worse than
no research agent.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import Config, SearchProvider
from .store import Store


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@dataclass
class Result:
    title: str
    url: str
    snippet: str = ""
    content: str = ""

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:32]


class NoSearchAvailable(RuntimeError):
    pass


class SearchClient:
    """Thin client over the free search tiers. Metered, cached, failure-tolerant."""

    def __init__(self, cfg: Optional[Config] = None, store: Optional[Store] = None):
        self.cfg = cfg or Config.from_env()
        self.store = store or Store(self.cfg.db_path)
        self._month_key = time.strftime("%Y-%m", time.gmtime())

    def _quota_key(self, provider: str) -> str:
        return f"search:{provider}"

    def remaining(self, provider: str) -> int:
        used = self.store.usage_today(provider=self._quota_key(provider),
                                      day=self._month_key)
        for sp in self.cfg.search:
            if sp.name == provider:
                return max(0, sp.monthly_free - used)
        return 0

    def _bump(self, provider: str, ok: bool = True) -> None:
        self.store.bump_usage(self._quota_key(provider), ok=ok)

    def provider(self) -> Optional[SearchProvider]:
        for sp in self.cfg.search:
            import os
            if os.environ.get(sp.env_key) and self.remaining(sp.name) > 0:
                return sp
        return None

    def search(self, query: str, max_results: int = 5) -> List[Result]:
        sp = self.provider()
        if sp is None:
            raise NoSearchAvailable(
                "no search API key configured (set TAVILY_API_KEY / SERPER_API_KEY / "
                "BRAVE_API_KEY) — the research agent will idle until one is present")

        try:
            if sp.kind == "tavily":
                rows = self._tavily(sp, query, max_results)
            elif sp.kind == "serper":
                rows = self._serper(sp, query, max_results)
            else:
                rows = self._brave(sp, query, max_results)
            self._bump(sp.name, ok=True)
            return rows
        except Exception as e:                     # noqa: BLE001
            self._bump(sp.name, ok=False)
            raise NoSearchAvailable(str(e)) from e

    # -- provider adapters ---------------------------------------------------
    def _post_json(self, url: str, payload: Dict, headers: Dict) -> Dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))

    def _tavily(self, sp: SearchProvider, query: str, n: int) -> List[Result]:
        import os
        body = self._post_json(sp.endpoint, {
            "api_key": os.environ[sp.env_key],
            "query": query, "max_results": n, "search_depth": "basic",
        }, {"Content-Type": "application/json"})
        return [Result(r.get("title", ""), r.get("url", ""), r.get("content", ""))
                for r in body.get("results", [])]

    def _serper(self, sp: SearchProvider, query: str, n: int) -> List[Result]:
        import os
        body = self._post_json(sp.endpoint, {"q": query, "num": n},
                               {"X-API-KEY": os.environ[sp.env_key],
                                "Content-Type": "application/json"})
        out = []
        for r in body.get("organic", [])[:n]:
            out.append(Result(r.get("title", ""), r.get("link", ""), r.get("snippet", "")))
        for r in body.get("answerBox", []) if isinstance(body.get("answerBox"), list) else []:
            out.append(Result("answerBox", r.get("link", ""), r.get("snippet", "")))
        return out

    def _brave(self, sp: SearchProvider, query: str, n: int) -> List[Result]:
        import os
        url = f"{sp.endpoint}?q={urllib.parse.quote(query)}&count={n}"
        req = urllib.request.Request(url, headers={
            "X-Subscription-Token": os.environ[sp.env_key], "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as r:
            body = json.loads(r.read().decode("utf-8"))
        return [Result(w.get("title", ""), w.get("url", ""), w.get("description", ""))
                for w in body.get("web", {}).get("results", [])[:n]]


# ---------------------------------------------------------------------------
# Distillation (offline, no LLM required — regex + heuristics)
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NOISE = re.compile(r"(cookie|subscribe|newsletter|sign up|advertisement|all rights reserved)",
                    re.I)


def distill(text: str, max_sentences: int = 6,
            keywords: Optional[Sequence[str]] = None) -> str:
    """Cheap extractive summariser. Keeps sentences carrying signal.

    An LLM summariser is better — and the agent will use one when a key is
    present — but the offline path must still work on a 2G connection at 2am.
    """
    if not text:
        return ""
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if 25 < len(s.strip()) < 400]
    sents = [s for s in sents if not _NOISE.search(s)]
    if not sents:
        return text[:300]

    def score(s: str) -> float:
        val = 0.0
        if re.search(r"\d", s):
            val += 1.0                                   # numbers = evidence
        if re.search(r"\b(study|students|learning|effect|randomi[sz]ed|meta-analysis|"
                     r"improve|reduce|increase|significant)\b", s, re.I):
            val += 1.5
        if keywords:
            val += 1.2 * sum(1 for k in keywords if k.lower() in s.lower())
        return val

    ranked = sorted(sents, key=score, reverse=True)[:max_sentences]
    ranked.sort(key=lambda s: text.find(s))
    return " ".join(ranked)


# ---------------------------------------------------------------------------
# Research agent
# ---------------------------------------------------------------------------

DEFAULT_TOPICS: List[Tuple[str, str]] = [
    ("learning_science", "spaced retrieval practice classroom evidence 2026"),
    ("learning_science", "AI tutor guardrails hints versus answers learning outcomes"),
    ("motivation", "student motivation self-determination theory interventions 2026"),
    ("motivation", "gamification extrinsic rewards undermining intrinsic motivation"),
    ("pakistan_education", "Pakistan education ASER learning outcomes 2026"),
    ("pakistan_careers", "Pakistan MDCAT ECAT entry test changes syllabus 2026"),
    ("pakistan_careers", "Pakistan jobs skills demand graduates 2026"),
    ("wellbeing", "student burnout academic pressure intervention 2026"),
    ("edtech", "intelligent tutoring system knowledge tracing equity 2026"),
]


@dataclass
class ResearchRun:
    topic: str
    queries: int
    new_notes: int
    duplicates: int
    errors: List[str] = field(default_factory=list)
    provider: str = "none"
    quotes: Dict[str, int] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<Research {self.topic} via {self.provider}: {self.new_notes} new, "
                f"{self.duplicates} dup, {len(self.errors)} error(s)>")


class ResearchAgent:
    """Runs scheduled research, stores notes, and mines its own behaviour."""

    def __init__(self, cfg: Optional[Config] = None, store: Optional[Store] = None,
                 router=None):
        self.cfg = cfg or Config.from_env()
        self.store = store or Store(self.cfg.db_path)
        self.search = SearchClient(self.cfg, self.store)
        self.router = router

    # -- domain research ------------------------------------------------------
    def run(self, topics: Optional[Sequence[Tuple[str, str]]] = None,
            per_query_results: int = 4,
            max_queries: int = 6) -> ResearchRun:
        topics = list(topics or DEFAULT_TOPICS)[:max_queries]
        errors: List[str] = []
        new = dup = 0
        provider = "none"

        try:
            provider = (self.search.provider().name if self.search.provider() else "none")
        except Exception:                       # noqa: BLE001
            pass

        for topic, query in topics:
            try:
                results = self.search.search(query, max_results=per_query_results)
            except NoSearchAvailable as e:
                errors.append(f"{topic}: {e}")
                continue
            except Exception as e:              # noqa: BLE001
                errors.append(f"{topic}: {e}")
                continue
            for r in results:
                content = r.content or r.snippet
                distilled = distill(content, keywords=[topic.split("_")[0], "students"])
                if self.router is not None:
                    try:
                        distilled = self.router.complete(
                            [{"role": "user", "content":
                              f"Summarise for a student-tutoring system in 4 bullets, "
                              f"keeping any numbers and citing nothing:\n\n{content[:3000]}"}],
                            tier="fast", max_tokens=220)
                    except Exception:           # noqa: BLE001
                        pass                     # offline distillation stands
                if self.store.add_research(topic, r.title or r.url, r.url_hash,
                                           content[:6000], distilled):
                    new += 1
                else:
                    dup += 1

        return ResearchRun(topic="+".join(sorted({t for t, _ in topics})),
                           queries=len(topics), new_notes=new, duplicates=dup,
                           errors=errors, provider=provider,
                           quotes={sp.name: self.search.remaining(sp.name)
                                   for sp in self.cfg.search})

    def digest(self, topic: Optional[str] = None, limit: int = 20) -> str:
        notes = self.store.research(topic=topic, limit=limit)
        if not notes:
            return "No research notes yet. Run `raasta research` with a search API key."
        by_topic: Dict[str, List[str]] = {}
        for n in notes:
            by_topic.setdefault(n["topic"], []).append(
                f"- {n['source'][:70]}: {(n['distilled'] or n['content'])[:220]}")
        return "\n\n".join(f"## {t}\n" + "\n".join(v) for t, v in by_topic.items())

    # -- self research --------------------------------------------------------
    def self_research(self, since_days: int = 14) -> Dict[str, Any]:
        """Read our own eval history and reflections; return ranked hypotheses.

        This is the loop that makes the system *self*-improving rather than
        merely updatable: it decides what to try next based on where it is weak.
        """
        cutoff = time.time() - since_days * 86400
        history = [h for h in self.store.eval_history("core", limit=100)
                   if h["ts"] >= cutoff]
        reflections = [r for r in self.store.reflections(limit=500)
                       if r["ts"] >= cutoff]

        kinds: Dict[str, int] = {}
        for r in reflections:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        ranked = sorted(kinds.items(), key=lambda kv: -kv[1])

        trend = 0.0
        if len(history) >= 2:
            trend = history[0]["metrics"].get("score", 0) - history[-1]["metrics"].get("score", 0)

        hypotheses: List[Dict[str, Any]] = []
        template = {
            "scaffolding_dependence": (
                "hints", "Cap hints at one per item. Before the second hint, require the "
                "student to state in one sentence what they think the step is.",
                "reflections: repeated scaffolding dependence across sessions"),
            "weak_transfer": (
                "spacing", "Do not mark a skill mastered until it passes an unaided test "
                "48h after the last practice. Until then it stays in review rotation.",
                "reflections: unaided pass rate below 0.5"),
            "too_easy": (
                "spacing", "If accuracy >0.96 with near-zero mastery gain, stretch the "
                "interval by 1.35x and raise item difficulty one notch.",
                "reflections: high accuracy, no gain — work below the difficulty band"),
            "too_hard": (
                "attempt_gate", "If accuracy <0.55, stop introducing new items and "
                "re-teach the blocking prerequisite until mastery >= 0.60.",
                "reflections: accuracy below the desirable-difficulty band"),
            "drop_off": (
                "opener", "Cut the plan to two items and lead with the fastest win. "
                "Extend only after two consecutive completions.",
                "reflections: sessions finishing below 70% of planned items"),
            "deep_impasse": (
                "escalation", "At impasse depth >= 3, skip straight to a partial worked "
                "example. Questioning has decayed to near-zero value by then.",
                "reflections: impasse depth reached 4+"),
            "policy_violation": (
                "attempt_gate", "Block assistance at the router when no attempt exists "
                "yet, instead of relying on the prompt to refuse.",
                "reflections: assistance delivered before any student attempt"),
        }
        for kind, count in ranked[:3]:
            if kind in template:
                key, value, evidence = template[kind]
                hypotheses.append({"key": key, "value": value, "evidence": evidence,
                                   "trigger": kind, "count": count})

        return {
            "eval_runs": len(history),
            "score_trend": round(trend, 4),
            "latest_score": history[0]["metrics"].get("score") if history else None,
            "reflection_kinds": ranked,
            "hypotheses": hypotheses,
        }

    def status(self) -> List[Dict[str, Any]]:
        out = []
        for sp in self.cfg.search:
            import os
            out.append({"provider": sp.name, "configured": bool(os.environ.get(sp.env_key)),
                        "remaining_this_month": self.search.remaining(sp.name),
                        "monthly_free": sp.monthly_free})
        return out
