"""Self-improvement: frozen evals → reflection → versioned playbook → promotion gate.

This is the part that makes RAASTA get better on its own. It follows the pattern
that actually works in production (ACE / Reflexion / Voyager): the model weights
never change; what changes is **context** — a playbook of accumulated, evidenced
teaching knowledge, updated incrementally and promoted only when a frozen eval
suite says it improved.

Order matters, and the research is blunt about it:
  "Start with evals... Add each layer only after the previous one demonstrably
   moves your eval numbers."

Primary metric is **delayed unaided transfer**, never in-session correctness.
In-session correctness is exactly the metric that made AI tutors look good while
quietly harming learning (unguarded GPT-4: +48% during practice, −17% on the
later unaided exam).
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .orchestrator import Orchestrator, StudentProfile
from .playbook import PLAYBOOK_SEED, Playbook   # re-exported for callers
from .pedagogy import Assistance, Move, check_leak
from .scheduler import Skill
from .store import Store


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

#: A tiny, purpose-built skill graph for the eval suite.
#:
#: The suite must not depend on a content catalog: if a scenario keys its script
#: to "skill_a" but the catalog only contains "units_si", every item silently
#: falls through to the default script and the primary metric (unaided transfer)
#: reads zero forever. Keeping the graph here makes that impossible.
EVAL_CATALOG: Dict[str, Skill] = {
    "skill_a": Skill("skill_a", "Test", "Core skill under evaluation",
                     minutes=3.0, difficulty=0.50, exam_weight=1.0),
    "skill_b": Skill("skill_b", "Test", "A second skill, for interleaving",
                     minutes=3.0, difficulty=0.50, exam_weight=0.8),
    "skill_c": Skill("skill_c", "Test", "A third skill, for interleaving",
                     minutes=3.0, difficulty=0.50, exam_weight=0.6),
}


@dataclass
class Scenario:
    """One scripted student. Deterministic → the eval suite is reproducible."""
    id: str
    name: str
    description: str
    script: Dict[str, List[Tuple[str, Optional[bool]]]]
    expected_answers: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, int] = field(default_factory=dict)
    difficulty_note: str = ""


# --- the four failure modes we most need to survive ------------------------

SCENARIOS: List[Scenario] = [
    Scenario(
        id="answer_seeker",
        name="The answer-seeker",
        description=("Asks for the answer directly, repeatedly, and tries to wear the "
                     "tutor down. This is 39.4% of real student messages to Khanmigo."),
        script={
            "skill_a": [("answer bata do", None),
                        ("bas answer chahiye, time nahi hai", None),
                        ("please sirf jawab", None),
                        ("theek hai khud try karta hoon, pehla step... 3?", False),
                        ("acha samajh aaya, dobara: 4", True),
                        ("4", True),
                        ("4", True)],
        },
        expected_answers={"skill_a": "4"},
        difficulty_note="must never leak the answer; must escalate past questioning",
    ),
    Scenario(
        id="confused_silent",
        name="The student who went quiet",
        description=("Says 'samajh nahi aaya' and stops. Endless Socratic questioning "
                     "is what made students abandon Khanmigo."),
        script={
            "skill_a": [("samajh nahi aaya", None),
                        ("mujhe kuch nahi aata", None),
                        ("?", None),
                        ("theek hai try karta hoon: 2", False),
                        ("ab samajh gaya: 5", True),
                        ("5", True),
                        ("5", True)],
        },
        expected_answers={"skill_a": "5"},
        difficulty_note="must escalate to error-directed then worked example, not repeat questions",
    ),
    Scenario(
        id="careless_fast",
        name="Fast but careless",
        description=("Knows the concept, slips on arithmetic. Should NOT be re-taught "
                     "from scratch — that is the fastest route to boredom and churn."),
        script={
            "skill_a": [("ye to aasan hai, 12", False),
                        ("haan sign ki ghalti hui thi, -12", True),
                        ("dobara: -12", True),
                        ("-12", True),
                        ("-12", True)],
        },
        expected_answers={"skill_a": "-12"},
        difficulty_note="should reach TEST quickly; hints should stay minimal",
    ),
    Scenario(
        id="genuine_learner",
        name="The engaged learner",
        description="Attempts honestly, gets it wrong once, then right. Baseline case.",
        script={
            "skill_a": [("pehle denominator common karte hain... 7?", False),
                        ("oh, 6 hona chahiye", True),
                        ("theek hai, 6", True),
                        ("6", True),
                        ("6", True)],
        },
        expected_answers={"skill_a": "6"},
        difficulty_note="should complete in few turns with high transfer",
    ),
]


# ---------------------------------------------------------------------------
# Invariants — hard gates. Violating any of these fails the build, not the score.
# ---------------------------------------------------------------------------

def _check_no_leak(result: Dict[str, Any]) -> List[str]:
    problems = []
    for item in result["items"]:
        for t in item["turns"]:
            if t["assistance"] in ("none",):
                continue
            if t["assistance"] == "full_worked":
                continue        # permitted only at the top of the escalation ladder
            v = check_leak(t["tutor_text"], None, allow_answer=False)
            if not v.ok:
                problems.append(f"{result['student_id']}/{item['skill_id']}: "
                                f"leak at {t['move']}/{t['assistance']}")
    return problems


def _check_attempt_gate(result: Dict[str, Any]) -> List[str]:
    problems = []
    for item in result["items"]:
        seen_attempt = False
        for t in item["turns"]:
            if t["correct"] is not None or len(t["student_text"].split()) >= 3:
                seen_attempt = True
            if not seen_attempt and t["assistance"] not in ("none",):
                problems.append(f"{result['student_id']}/{item['skill_id']}: "
                                f"assistance '{t['assistance']}' before any attempt")
                break
    return problems


def _check_protected_moves(result: Dict[str, Any]) -> List[str]:
    problems = []
    for item in result["items"]:
        for t in item["turns"]:
            if t["move"] in ("prime", "probe", "test") and t["assistance"] != "none":
                problems.append(f"{result['student_id']}/{item['skill_id']}: "
                                f"AI-assisted during protected move '{t['move']}'")
    return problems


def _check_no_repeat(result: Dict[str, Any]) -> List[str]:
    """Within one impasse the tutor must never repeat a move that already failed."""
    problems = []
    order = [a.value for a in Assistance]
    for item in result["items"]:
        depth_seen: Dict[int, List[str]] = {}
        for t in item["turns"]:
            d = t["impasse_depth"]
            if d < 2 or t["assistance"] == "none":
                continue
            seen = depth_seen.setdefault(d, [])
            if t["assistance"] in seen:
                problems.append(f"{result['student_id']}/{item['skill_id']}: "
                                f"repeated '{t['assistance']}' at impasse depth {d}")
            seen.append(t["assistance"])
    return problems


INVARIANTS: List[Callable[[Dict[str, Any]], List[str]]] = [
    _check_no_leak, _check_attempt_gate, _check_protected_moves, _check_no_repeat,
]


# ---------------------------------------------------------------------------
# Eval suite
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    suite: str
    playbook_version: int
    passed: bool
    score: float
    metrics: Dict[str, float]
    violations: List[str] = field(default_factory=list)
    per_scenario: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<Eval {self.suite} v{self.playbook_version} "
                f"{'PASS' if self.passed else 'FAIL'} score={self.score:.3f} "
                f"violations={len(self.violations)}>")


# Which metrics we want higher, and how much they count.
WEIGHTS = {
    "unaided_test_pass_rate": 0.35,     # the real thing: transfer without help
    "mean_mastery_gain": 0.20,
    "completion": 0.20,
    "efficiency": 0.15,                 # fewer turns to mastery is better
    "low_hint_rate": 0.10,              # independence, not scaffolding dependence
    "leak_free_rate": 0.15,             # 1 - share of assisted turns that tried to leak
}


def _score(metrics: Dict[str, float]) -> float:
    eff = 1.0 / (1.0 + max(0.0, metrics.get("turns_per_item", 6.0) - 3.0) / 6.0)
    low_hint = 1.0 / (1.0 + metrics.get("hints_per_item", 1.0))
    vals = {
        "unaided_test_pass_rate": metrics.get("unaided_test_pass_rate", 0.0),
        "mean_mastery_gain": min(1.0, max(0.0, metrics.get("mean_mastery_gain", 0.0))),
        "completion": metrics.get("completion", 0.0),
        "efficiency": eff,
        "low_hint_rate": low_hint,
        "leak_free_rate": 1.0 - min(1.0, metrics.get("leak_attempt_rate", 0.0)),
    }
    return sum(w * vals[k] for k, w in WEIGHTS.items())


def _reset_eval_students(store: Store) -> None:
    """Wipe eval student state so every run starts from zero.

    Without this, run #2 measures students who already know everything from
    run #1, and the promotion gate compares two numbers that mean different
    things — the most dangerous kind of eval bug, because it looks fine.
    """
    try:
        with store.tx() as c:
            c.execute("DELETE FROM skill_state WHERE student_id LIKE 'eval\_%' ESCAPE '\\'")
            c.execute("DELETE FROM events WHERE student_id LIKE 'eval\_%' ESCAPE '\\'")
    except Exception:                      # noqa: BLE001 - never fail an eval on cleanup
        pass


def run_evals(catalog: Optional[Dict[str, Skill]] = None, store: Optional[Store] = None,
              cfg=None, scenarios: Optional[Sequence[Scenario]] = None,
              db_path: str = ":memory:",
              playbook_scope: str = "global") -> EvalResult:
    """Run the frozen suite with fresh students against an isolated database."""
    from .config import Config
    cfg = cfg or Config()
    catalog = catalog or dict(EVAL_CATALOG)
    store = store or Store(db_path)
    scenarios = list(scenarios or SCENARIOS)
    _reset_eval_students(store)          # a run must never inherit the last run

    per_scenario: Dict[str, Dict[str, Any]] = {}
    violations: List[str] = []
    all_metrics: List[Dict[str, float]] = []

    for sc in scenarios:
        profile = StudentProfile(id=f"eval_{sc.id}", name=sc.name,
                                 language="roman_urdu")
        orch = Orchestrator(profile, catalog, store=store, cfg=cfg)
        res = orch.run_session(script=sc.script,
                               expected_answers=sc.expected_answers,
                               options=sc.options)
        d = res.to_dict()
        per_scenario[sc.id] = {"name": sc.name, "metrics": res.metrics,
                               "items": len(res.items)}
        for inv in INVARIANTS:
            violations.extend(inv(d))
        all_metrics.append(res.metrics)

    agg: Dict[str, float] = {}
    if all_metrics:
        keys = set().union(*(m.keys() for m in all_metrics))
        for k in keys:
            agg[k] = statistics.mean([m.get(k, 0.0) for m in all_metrics])
        agg["turns_per_item"] = statistics.mean(
            [m.get("turns", 0) / max(1, m.get("items", 1)) for m in all_metrics])

    score = _score(agg)
    pb_v = store.playbook_version(playbook_scope)
    store.record_eval("core", pb_v, {**agg, "score": score,
                                     "violations": len(violations)})
    return EvalResult("core", pb_v, not violations, score, agg, violations, per_scenario)


# ---------------------------------------------------------------------------
# Reflection
# ---------------------------------------------------------------------------

class Reflector:
    """Turns session data into a written lesson. Reflexion-style, but measured.

    A reflection is only worth storing if it is attached to numbers; otherwise the
    system accumulates confident-sounding nonsense.
    """

    def __init__(self, store: Store):
        self.store = store

    #: Do not draw conclusions from a session with fewer items than this.
    #: A one-item session with 0% accuracy is not evidence of anything.
    MIN_ITEMS = 2

    def reflect_session(self, result: Dict[str, Any]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        m = result.get("metrics", {})
        sid = result.get("student_id", "?")
        if m.get("items", 0) < self.MIN_ITEMS:
            return out

        if m.get("assistance_before_attempt", 0) > 0:
            out.append({"kind": "policy_violation",
                        "text": ("Tutor gave help before the student attempted on "
                                 f"{m['assistance_before_attempt']:.0f} occasion(s). "
                                 "Enforce the attempt-first gate at the router level, "
                                 "not only in the prompt."),
                        "metrics": {"value": m["assistance_before_attempt"]}})

        if m.get("hints_per_item", 0) > 2.0:
            out.append({"kind": "scaffolding_dependence",
                        "text": (f"Hints per item = {m['hints_per_item']:.2f}. The student is "
                                 "leaning on hints. Next session: open with a recall-only "
                                 "item and raise the attempt bar before any hint."),
                        "metrics": {"value": m["hints_per_item"]}})

        if m.get("accuracy", 1.0) > 0.92 and m.get("mean_mastery_gain", 0) < 0.02:
            out.append({"kind": "too_easy",
                        "text": ("Accuracy ~perfect with no mastery gain — the work is too "
                                 "easy to produce learning. Raise difficulty one notch and "
                                 "stretch the review interval."),
                        "metrics": {"accuracy": m.get("accuracy", 0),
                                    "gain": m.get("mean_mastery_gain", 0)}})

        if m.get("accuracy", 1.0) < 0.55 and m.get("turns", 0) >= 4:
            out.append({"kind": "too_hard",
                        "text": (f"Accuracy {m['accuracy']:.2f} is below the desirable-"
                                 "difficulty band (~0.85). Drop to the blocking "
                                 "prerequisite and re-teach from there."),
                        "metrics": {"accuracy": m.get("accuracy", 0)}})

        if m.get("max_impasse", 0) >= 4:
            out.append({"kind": "deep_impasse",
                        "text": ("Student hit impasse depth ≥4. Check whether the "
                                 "escalation ladder fired in order, or whether the same "
                                 "move repeated. Never repeat a failed move."),
                        "metrics": {"max_impasse": m["max_impasse"]}})

        if m.get("unaided_test_pass_rate", 1.0) < 0.5:
            out.append({"kind": "weak_transfer",
                        "text": (f"Unaided test pass rate {m['unaided_test_pass_rate']:.2f}. "
                                 "Performance during the session is not transferring. "
                                 "Add a delayed re-test 48h later before counting a skill "
                                 "as mastered."),
                        "metrics": {"rate": m["unaided_test_pass_rate"]}})

        if m.get("completion", 1.0) < 0.7:
            out.append({"kind": "drop_off",
                        "text": (f"Only {m['completion']:.0%} of items finished. Shorten the "
                                 "plan: fewer items, faster wins, then extend."),
                        "metrics": {"completion": m["completion"]}})

        for r in out:
            self.store.add_reflection(sid, r["kind"], r["text"], r.get("metrics", {}))
        return out

    def reflect_cohort(self, since_days: int = 7) -> List[Dict[str, Any]]:
        """Look across students — this is where the *system-level* lessons live."""
        cutoff = time.time() - since_days * 86400
        kinds: Dict[str, int] = {}
        for r in self.store.reflections(limit=1000):
            if r["ts"] < cutoff:
                continue
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        total = sum(kinds.values()) or 1
        return [{"kind": k, "count": v, "share": v / total}
                for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])]


# ---------------------------------------------------------------------------
# Playbook (ACE-style: incremental, evidenced, versioned)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The night loop
# ---------------------------------------------------------------------------

@dataclass
class CycleReport:
    reflections: int
    proposals: int
    promoted: int
    before: EvalResult
    after: EvalResult
    message: str
    ts: float = field(default_factory=time.time)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<Cycle reflections={self.reflections} proposals={self.proposals} "
                f"promoted={self.promoted} :: {self.message}>")


def improvement_cycle(catalog: Dict[str, Skill], store: Store, cfg=None,
                      hypothesis: Optional[Tuple[str, str, str]] = None,
                      min_delta: float = 0.005) -> CycleReport:
    """One full self-improvement cycle.

    1. reflect on recent sessions
    2. measure the current playbook on the frozen suite   (before)
    3. stage ONE hypothesis as a new playbook version
    4. measure again                                       (after)
    5. promote if — and only if — the score moved and no invariant broke
       otherwise deprecate the candidate and keep the old one

    One hypothesis at a time. If you change five things and the score moves, you
    have learned nothing.
    """
    pb = Playbook(store)
    before = run_evals(catalog, store=store, cfg=cfg, db_path=store.path)

    reflector = Reflector(store)
    # Cohort-level reflection is driven by ResearchAgent.self_research(); here we
    # only need to know how much evidence exists.
    reflections = len(store.reflections(limit=50))

    proposals = 0
    if hypothesis:
        key, value, evidence = hypothesis
        pb.propose(key, value, evidence)
        proposals = 1

    after = run_evals(catalog, store=store, cfg=cfg, db_path=store.path)
    promote, msg = Playbook.should_promote(before, after, min_delta)

    if hypothesis and not promote:
        key = hypothesis[0]
        # keep the newest version but mark it dead, so history still shows the attempt
        pb.deprecate(key, f"failed promotion gate: {msg}")

    return CycleReport(reflections, proposals, 1 if promote else 0,
                       before, after, msg)
