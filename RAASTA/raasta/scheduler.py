"""Decision engine: what to study, when, how much, in what order.

Priority (grounded in the research):
  1. Overdue spaced reviews — the single highest-ROI mechanic we have
     (spaced vs massed retrieval practice: g = 0.74).
  2. Highest expected-gain weaknesses, ranked by Δmastery / estimated minutes,
     gated on prerequisite mastery.
  3. New content last, and capped — cognitive load is a real budget.

Interleaving: rotate subject and item type inside the session rather than blocking
by topic; it costs a little in-the-moment fluency and buys a lot of retention.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .bkt import KnowledgeModel
from .config import Learning


@dataclass
class Skill:
    """A node in the syllabus skill graph."""
    id: str
    subject: str
    title: str
    prereqs: Sequence[str] = field(default_factory=tuple)
    minutes: float = 4.0            # typical time for one practice opportunity
    difficulty: float = 0.5         # 0..1, used for load accounting
    exam_weight: float = 1.0        # how much this shows up in the target exam
    kind: str = "concept"           # concept | procedure | recall


@dataclass
class PlanItem:
    skill_id: str
    subject: str
    title: str
    kind: str                       # review | weakness | new
    minutes: float
    priority: float
    reason: str

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<{self.kind:8s} {self.skill_id:24s} {self.minutes:4.1f}m "
                f"prio={self.priority:5.3f} :: {self.reason}>")


@dataclass
class SessionPlan:
    student_id: str
    created_at: float
    budget_minutes: int
    items: List[PlanItem]
    rest_day: bool = False
    note: str = ""

    @property
    def minutes(self) -> float:
        return sum(i.minutes for i in self.items)

    def subjects(self) -> List[str]:
        seen: List[str] = []
        for i in self.items:
            if i.subject not in seen:
                seen.append(i.subject)
        return seen

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        head = (f"SessionPlan({self.student_id}, {self.minutes:.0f}/{self.budget_minutes} min, "
                f"{len(self.items)} items"
                + (", REST DAY" if self.rest_day else "") + ")")
        return "\n".join([head] + [f"  {i}" for i in self.items])


class Scheduler:
    def __init__(self, catalog: Dict[str, Skill], cfg: Optional[Learning] = None):
        self.catalog = catalog
        self.cfg = cfg or Learning()

    # -- helpers -----------------------------------------------------------
    def _prereq_ready(self, skill: Skill, km: KnowledgeModel, threshold: float = 0.60) -> bool:
        return all(km.mastery(p) >= threshold for p in skill.prereqs)

    def _blocking_prereq(self, skill: Skill, km: KnowledgeModel,
                         threshold: float = 0.60) -> Optional[str]:
        for p in skill.prereqs:
            if km.mastery(p) < threshold:
                return p
        return None

    # -- main entry --------------------------------------------------------
    def plan(self, km: KnowledgeModel, now: Optional[float] = None,
             budget_minutes: Optional[int] = None,
             max_new: Optional[int] = None,
             focus_subjects: Optional[Sequence[str]] = None,
             rest_day: bool = False) -> SessionPlan:
        now = now if now is not None else time.time()
        c = self.cfg
        budget = budget_minutes if budget_minutes is not None else c.default_budget_minutes
        max_new = max_new if max_new is not None else c.max_new_items_per_session

        if rest_day:
            return SessionPlan(km.student_id, now, budget, [], rest_day=True,
                               note="Mandated rest day. Light review only if the student asks.")

        items: List[PlanItem] = []
        used = 0.0

        # ---- 1) overdue reviews ------------------------------------------
        overdue = []
        for sid, st in km.skills.items():
            if st.last_seen is None or st.attempts == 0:
                continue
            if focus_subjects and self.catalog.get(sid) and \
                    self.catalog[sid].subject not in focus_subjects:
                continue
            od = km.overload_days(sid, now)
            if km.due(sid, now):
                skill = self.catalog.get(sid)
                # most overdue first, but never let a weak skill wait too long
                score = od + (1.0 - st.p_mastery) * 2.0
                overdue.append((score, sid, od))
        overdue.sort(reverse=True)

        for score, sid, od in overdue[: c.review_cap_per_session]:
            skill = self.catalog.get(sid)
            if skill is None:
                continue
            mins = min(skill.minutes, 3.0)   # reviews are quicker than first learning
            if used + mins > budget:
                continue
            items.append(PlanItem(
                sid, skill.subject, skill.title, "review", mins, score,
                f"overdue by {od:.1f}d · mastery {km.mastery(sid):.2f} · due now"))
            used += mins

        # ---- 2) weaknesses with the best gain-per-minute ------------------
        cands = []
        for sid, skill in self.catalog.items():
            st = km.skills.get(sid)
            if st is not None and st.p_mastery >= c.mastery_threshold:
                continue                                   # already learned
            if focus_subjects and skill.subject not in focus_subjects:
                continue
            blocked = self._blocking_prereq(skill, km)
            if blocked:
                # study the prerequisite instead — this is the "start below grade
                # level" rule that Pakistan's learning data demands
                bskill = self.catalog.get(blocked)
                if bskill is None:
                    continue
                gain = km.expected_gain(blocked) * 1.25     # unlocking value
                mins = bskill.minutes
                cands.append((gain / max(0.5, mins), blocked, bskill, mins,
                              f"prerequisite of '{skill.title}' · mastery {km.mastery(blocked):.2f}"))
                continue
            if st is not None and st.attempts > 0:
                gain = km.expected_gain(sid) * skill.exam_weight
                mins = skill.minutes
                cands.append((gain / max(0.5, mins), sid, skill, mins,
                              f"weak · mastery {km.mastery(sid):.2f} · gain/min {gain/max(0.5,mins):.3f}"))
            else:
                # unseen: value it by exam weight, but keep it behind real weaknesses
                gain = km.expected_gain(sid) * skill.exam_weight * 0.8
                mins = skill.minutes
                cands.append((gain / max(0.5, mins), sid, skill, mins,
                              f"new · exam weight {skill.exam_weight:.1f}"))

        cands.sort(key=lambda t: -t[0])

        new_used = 0
        for ratio, sid, skill, mins, reason in cands:
            if used + mins > budget:
                continue
            st = km.skills.get(sid)
            is_new = st is None or st.attempts == 0
            if is_new:
                if new_used >= max_new:
                    continue
                new_used += 1
            items.append(PlanItem(sid, skill.subject, skill.title,
                                  "new" if is_new else "weakness",
                                  mins, ratio, reason))
            used += mins

        # ---- 3) nothing due? never show the student an empty screen -------
        #     Everything can legitimately be "not yet due" — that is spacing
        #     working as designed. But an empty session is how a habit dies, so
        #     we fall back to short maintenance practice on the skills that are
        #     weakest or have gone longest without contact.
        if not items:
            items = self._maintenance(km, now, budget)

        # ---- 4) interleave ------------------------------------------------
        items = self._interleave(items)
        return SessionPlan(km.student_id, now, budget, items)

    def _maintenance(self, km: KnowledgeModel, now: float,
                     budget: float) -> List[PlanItem]:
        """Short mixed practice when nothing is scheduled yet."""
        if not km.skills:
            # brand-new student: start at the roots of the graph
            roots = [s for s in self.catalog.values() if not s.prereqs]
            out, used = [], 0.0
            for skill in sorted(roots, key=lambda s: -s.exam_weight):
                if used + skill.minutes > budget:
                    continue
                out.append(PlanItem(skill.id, skill.subject, skill.title, "new",
                                    skill.minutes, skill.exam_weight,
                                    "first session — starting at the foundations"))
                used += skill.minutes
            return out

        ranked = sorted(
            km.skills.items(),
            key=lambda kv: (kv[1].p_mastery, -(now - (kv[1].last_seen or 0))))
        out, used = [], 0.0
        for sid, st in ranked[:4]:
            skill = self.catalog.get(sid)
            if skill is None:
                continue
            mins = min(skill.minutes, 3.0)
            if used + mins > budget:
                break
            gap = (now - (st.last_seen or now)) / 86400.0
            out.append(PlanItem(sid, skill.subject, skill.title, "review", mins,
                                0.001,
                                f"maintenance — nothing due yet; last seen {gap:.0f}d ago"))
            used += mins
        return out

    @staticmethod
    def _interleave(items: List[PlanItem]) -> List[PlanItem]:
        """Rotate subjects so the session alternates rather than blocking.

        Reviews stay roughly first (they are time-critical), but within the
        practice block we alternate subject and kind.
        """
        reviews = [i for i in items if i.kind == "review"]
        practice = [i for i in items if i.kind != "review"]
        if len(practice) <= 2:
            return reviews + practice

        buckets: Dict[str, List[PlanItem]] = {}
        for it in practice:
            buckets.setdefault(it.subject, []).append(it)
        for lst in buckets.values():
            lst.sort(key=lambda i: -i.priority)

        out: List[PlanItem] = []
        while any(buckets.values()):
            for subject in list(buckets.keys()):
                if buckets[subject]:
                    out.append(buckets[subject].pop(0))
        return reviews + out

    # -- horizon planning ---------------------------------------------------
    def weekly_plan(self, km: KnowledgeModel, days: int = 7,
                    minutes_per_day: int = 25,
                    now: Optional[float] = None,
                    rest_days: Optional[Sequence[int]] = None) -> List[SessionPlan]:
        """Simulate the week forward (without mutating mastery) to show the shape."""
        now = now if now is not None else time.time()
        rest = set(rest_days or [])
        plans = []
        for d in range(days):
            t = now + d * 86400.0
            plans.append(self.plan(km, now=t, budget_minutes=minutes_per_day,
                                   rest_day=(d in rest)))
        return plans
