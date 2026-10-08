"""Knowledge tracing: Bayesian Knowledge Tracing + forgetting + per-student parameters.

Why BKT and not a deep KT model
-------------------------------
* A teacher or parent can read `p_mastery = 0.62` and act on it. Deep KT cannot explain itself.
* It works from the very first response — no training pipeline, no GPU, no data hunger.
* It gives calibrated uncertainty, which the planner needs.

Equity
------
A single fixed-parameter BKT cannot fit both slow and fast learners; it produces
persistent equity gaps. BBKT (Bayesian-Bayesian KT) fixes this by inferring
*per-student* parameter posteriors online, and it closes both mastery and effort
gaps. This module implements a lightweight online approximation of that idea:
`p_transit` and `p_slip` are fitted per student per skill as responses arrive.

Standard BKT update (Corbett & Anderson, 1994)
----------------------------------------------
    p_learned = p + (1 - p) * T                 # opportunity to learn
    if correct:  p' = p_learned * (1 - S) / (p_learned * (1 - S) + (1 - p_learned) * G)
    if wrong:    p' = p_learned * S       / (p_learned * S       + (1 - p_learned) * (1 - G))
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterable, List, Optional, Tuple

from .config import Learning


@dataclass
class SkillState:
    """Everything we believe about one (student, skill) pair."""
    skill_id: str
    p_mastery: float = 0.05
    p_transit: float = 0.12     # learned per student — fast learners get a bigger number
    p_slip: float = 0.10
    p_guess: float = 0.25

    attempts: int = 0
    correct: int = 0
    consecutive_correct: int = 0
    consecutive_wrong: int = 0

    # spaced-repetition scheduling
    reps: int = 0
    interval_days: float = 1.0
    ease: float = 2.2
    lapses: int = 0

    last_seen: Optional[float] = None
    first_seen: Optional[float] = None
    # rolling accuracy, used for the 85% targeting
    recent_window: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "SkillState":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def accuracy(self) -> float:
        return (sum(self.recent_window) / len(self.recent_window)) if self.recent_window else 0.0

    @property
    def mastered(self) -> bool:
        return self.p_mastery >= 0.85


def guess_rate(options: Optional[int]) -> float:
    """MCQ guess rate from the number of options; low for constructed response."""
    if options is None or options <= 1:
        return 0.05
    return max(0.02, 1.0 / options)


class KnowledgeModel:
    """Owns the mastery estimates for one student."""

    def __init__(self, student_id: str, cfg: Optional[Learning] = None,
                 states: Optional[Dict[str, Dict]] = None):
        self.student_id = student_id
        self.cfg = cfg or Learning()
        self.skills: Dict[str, SkillState] = {
            k: SkillState.from_dict(v) for k, v in (states or {}).items()
        }

    # -- access ------------------------------------------------------------
    def state(self, skill_id: str) -> SkillState:
        if skill_id not in self.skills:
            c = self.cfg
            self.skills[skill_id] = SkillState(
                skill_id=skill_id,
                p_mastery=c.p_init,
                p_transit=c.p_transit,
                p_slip=c.p_slip,
                p_guess=c.p_guess_mcq4,
                interval_days=c.interval_min_days,
                ease=c.ease_init,
            )
        return self.skills[skill_id]

    def mastery(self, skill_id: str) -> float:
        return self.state(skill_id).p_mastery

    def to_dict(self) -> Dict[str, Dict]:
        return {k: v.to_dict() for k, v in self.skills.items()}

    # -- forgetting --------------------------------------------------------
    def half_life_days(self, st: SkillState) -> float:
        c = self.cfg
        hl = c.forget_base_days * (c.forget_growth ** min(st.reps, 20))
        return min(hl, c.forget_cap_days)

    def apply_forgetting(self, st: SkillState, now: float) -> float:
        """Decay mastery since last_seen. Returns the decayed probability."""
        if st.last_seen is None:
            return st.p_mastery
        days = max(0.0, (now - st.last_seen) / 86400.0)
        if days <= 0:
            return st.p_mastery
        hl = self.half_life_days(st)
        st.p_mastery = st.p_mastery * (0.5 ** (days / hl))
        return st.p_mastery

    # -- prediction --------------------------------------------------------
    def predict(self, skill_id: str, options: Optional[int] = None) -> float:
        """P(student answers correctly right now)."""
        st = self.state(skill_id)
        g = guess_rate(options) if options else st.p_guess
        return st.p_mastery * (1 - st.p_slip) + (1 - st.p_mastery) * g

    # -- update ------------------------------------------------------------
    def update(self, skill_id: str, correct: bool, now: Optional[float] = None,
               options: Optional[int] = None,
               response_time_s: Optional[float] = None,
               hint_used: bool = False) -> SkillState:
        """Fold one observed response into the model."""
        now = now if now is not None else time.time()
        c = self.cfg
        st = self.state(skill_id)
        if st.first_seen is None:
            st.first_seen = now

        # 1) time has passed → some of what was learned has decayed
        self.apply_forgetting(st, now)

        # 2) guess rate follows the item format
        if options is not None:
            st.p_guess = guess_rate(options)

        # 3) what we expected, before seeing the answer (used to fit parameters)
        p_before = st.p_mastery
        expected = st.p_mastery * (1 - st.p_slip) + (1 - st.p_mastery) * st.p_guess

        # 4) opportunity to learn, then Bayes
        p_learned = p_before + (1 - p_before) * st.p_transit
        s, g = st.p_slip, st.p_guess
        if correct:
            num = p_learned * (1 - s)
            den = num + (1 - p_learned) * g
        else:
            num = p_learned * s
            den = num + (1 - p_learned) * (1 - g)
        st.p_mastery = (num / den) if den > 0 else p_learned

        # 5) per-student parameter fitting (BBKT-lite)
        #    Surprised by a correct answer when we expected failure? Raise the
        #    learning rate. Surprised by a wrong answer when we expected success?
        #    Raise the slip rate. Both are clamped so a single lucky guess cannot
        #    swing the model.
        surprise = (1.0 if correct else 0.0) - expected
        if correct and surprise > 0:
            st.p_transit = min(c.transit_max,
                               st.p_transit + c.adapt_rate * surprise * (1 - st.p_transit))
        elif (not correct) and surprise < 0:
            st.p_slip = min(c.slip_max,
                            st.p_slip + c.adapt_rate * abs(surprise) * (0.5 + 0.5 * (1 - st.p_mastery)))
            st.p_transit = max(c.transit_min, st.p_transit - c.adapt_rate * abs(surprise) * st.p_transit)
        else:
            # predicted well: gently relax slip toward the floor
            st.p_slip = max(c.slip_min, st.p_slip - c.adapt_rate * 0.05 * st.p_slip)

        # 6) counters
        st.attempts += 1
        st.correct += 1 if correct else 0
        st.recent_window.append(1 if correct else 0)
        if len(st.recent_window) > 8:
            st.recent_window.pop(0)
        if correct:
            st.consecutive_correct += 1
            st.consecutive_wrong = 0
        else:
            st.consecutive_wrong += 1
            st.consecutive_correct = 0

        # 7) schedule the next review (spacing)
        self._reschedule(st, correct, response_time_s, hint_used)

        st.last_seen = now
        return st

    def _reschedule(self, st: SkillState, correct: bool,
                    response_time_s: Optional[float], hint_used: bool) -> None:
        """Expanding-interval scheduling, nudged toward the ~85% accuracy target."""
        c = self.cfg
        acc = st.accuracy
        if correct:
            st.reps += 1
            st.ease = min(c.ease_max, st.ease + 0.05)
            factor = st.ease
            # desirable difficulty: if it is too easy, stretch; too hard, shorten
            if acc > c.target_accuracy + 0.10:
                factor *= 1.35
            elif acc < c.target_accuracy - 0.15:
                factor *= 0.75
            if hint_used:
                factor *= 0.8          # you got it, but with help → see it sooner
            if response_time_s is not None and response_time_s < 3.0:
                factor *= 0.85         # instant recall is not yet durable
            st.interval_days = min(c.interval_max_days,
                                   max(c.interval_min_days, st.interval_days * factor))
        else:
            st.lapses += 1
            st.reps = max(0, st.reps - 1)
            st.ease = max(c.ease_min, st.ease - 0.20)
            st.interval_days = max(0.4, st.interval_days * 0.40)

        # mastery modulates the interval: known things can wait
        if st.p_mastery >= 0.92:
            st.interval_days = min(c.interval_max_days, st.interval_days * 1.25)
        elif st.p_mastery < 0.50:
            st.interval_days = max(0.4, st.interval_days * 0.7)

    # -- scheduling queries -------------------------------------------------
    def due(self, skill_id: str, now: Optional[float] = None) -> bool:
        st = self.skills.get(skill_id)
        if st is None or st.last_seen is None:
            return True
        now = now if now is not None else time.time()
        return (now - st.last_seen) >= st.interval_days * 86400.0

    def due_skills(self, now: Optional[float] = None) -> List[str]:
        now = now if now is not None else time.time()
        return [sid for sid, st in self.skills.items()
                if st.last_seen is not None and self.due(sid, now)]

    def overload_days(self, skill_id: str, now: Optional[float] = None) -> float:
        """How overdue (in days) a skill is. Used to prioritise reviews."""
        st = self.skills.get(skill_id)
        if st is None or st.last_seen is None:
            return 0.0
        now = now if now is not None else time.time()
        return max(0.0, (now - st.last_seen) / 86400.0 - st.interval_days)

    # -- reporting ---------------------------------------------------------
    def weakest(self, n: int = 5, only_seen: bool = True) -> List[Tuple[str, float]]:
        items = [(sid, st.p_mastery) for sid, st in self.skills.items()
                 if (st.attempts > 0 or not only_seen)]
        items.sort(key=lambda kv: kv[1])
        return items[:n]

    def summary(self) -> Dict[str, float]:
        if not self.skills:
            return {"skills": 0.0, "mean_mastery": 0.0, "mastered": 0.0}
        ps = [s.p_mastery for s in self.skills.values()]
        return {
            "skills": float(len(ps)),
            "mean_mastery": sum(ps) / len(ps),
            "mastered": float(sum(1 for p in ps if p >= 0.85)),
            "attempts": float(sum(s.attempts for s in self.skills.values())),
            "overall_accuracy": (sum(s.correct for s in self.skills.values()) /
                                 max(1, sum(s.attempts for s in self.skills.values()))),
        }

    def expected_gain(self, skill_id: str) -> float:
        """Expected mastery gain from one more practice opportunity."""
        st = self.state(skill_id)
        return st.p_transit * (1.0 - st.p_mastery)
