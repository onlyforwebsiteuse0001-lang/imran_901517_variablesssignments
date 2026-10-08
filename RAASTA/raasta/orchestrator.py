"""The orchestrator: one deterministic state machine that runs a study session.

Deliberately NOT a free-roaming agent loop. Students need reliability, and every
stochastic hop is an opportunity to lose them. The LLM is consulted for *wording*;
the *policy* — which move, which assistance level, whether help is allowed at all —
is decided by code that can be tested.

Flow per item:
    PRIME (unaided) → PROBE (unaided, attempt required) → POINT → ATTACH
      → STRENGTHEN → TEST (unaided, this is the measurement)
with an impasse ladder that escalates and never repeats a failed move, an
answer-leak guard on every outgoing message, and a wellbeing gate over the whole
session.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bkt import KnowledgeModel
from .config import Config, Learning, MotivationCfg
from .playbook import Playbook
from .language import LANGUAGE_CONTRACT, prepare_input
from .pedagogy import (Assistance, ImpasseType, Move, SixMoveEngine, check_leak,
                       enforce, tutor_contract)
from .psychology import (BurnoutAssessment, MotivationEngine, MotivationProfile,
                         Streak, WellbeingGuard, update_streak)
from .router import Router, offline_reply
from .scheduler import PlanItem, Scheduler, SessionPlan, Skill
from .store import Store


# ---------------------------------------------------------------------------
# Student profile
# ---------------------------------------------------------------------------

@dataclass
class StudentProfile:
    id: str
    name: str = "Student"
    language: str = "roman_urdu"          # roman_urdu | urdu | english | mixed
    board: str = ""                        # e.g. "BISE Karachi", "CIE"
    stage: str = ""                        # e.g. "Matric (Class 10)"
    class_year: str = ""
    target_exams: List[Dict[str, Any]] = field(default_factory=list)
    device_tier: str = "low"               # low | mid | high
    network_tier: str = "3g"               # 2g | 3g | 4g | wifi
    daily_minutes: int = 25
    study_slots: List[str] = field(default_factory=list)
    motivation: MotivationProfile = field(default_factory=MotivationProfile)
    streak: Streak = field(default_factory=Streak)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "language": self.language,
            "board": self.board, "stage": self.stage, "class_year": self.class_year,
            "target_exams": self.target_exams, "device_tier": self.device_tier,
            "network_tier": self.network_tier, "daily_minutes": self.daily_minutes,
            "study_slots": self.study_slots,
            "motivation": self.motivation.to_dict(),
            "streak": self.streak.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StudentProfile":
        d = dict(d)
        d["motivation"] = MotivationProfile.from_dict(d.get("motivation", {}))
        d["streak"] = Streak.from_dict(d.get("streak", {}))
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class TurnRecord:
    move: str
    assistance: str
    student_text: str
    tutor_text: str
    correct: Optional[bool]
    impasse_depth: int
    impasse_type: str
    leaked: bool = False
    blocked: bool = False
    source: str = "offline"     # offline | provider name | cache

    def to_dict(self) -> Dict[str, Any]:
        return {"move": self.move, "assistance": self.assistance,
                "student_text": self.student_text, "tutor_text": self.tutor_text,
                "correct": self.correct, "impasse_depth": self.impasse_depth,
                "impasse_type": self.impasse_type, "leaked": self.leaked,
                "blocked": self.blocked, "source": self.source}


@dataclass
class ItemResult:
    skill_id: str
    kind: str
    mastery_before: float
    mastery_after: float
    turns: List[TurnRecord] = field(default_factory=list)
    finished: bool = False
    passed_unaided_test: Optional[bool] = None
    hints_used: int = 0
    max_impasse: int = 0
    leaks_blocked: int = 0
    #: A model that *tries* to hand over the answer is worse than one that never
    #: does, even when the guardrail catches every attempt: it means the prompt
    #: and the playbook are not doing their job.
    leak_attempts: int = 0
    assisted_turns: int = 0
    assistance_given_before_attempt: int = 0

    @property
    def gain(self) -> float:
        return self.mastery_after - self.mastery_before

    def to_dict(self) -> Dict[str, Any]:
        return {"skill_id": self.skill_id, "kind": self.kind,
                "mastery_before": self.mastery_before,
                "mastery_after": self.mastery_after,
                "gain": self.gain, "finished": self.finished,
                "passed_unaided_test": self.passed_unaided_test,
                "hints_used": self.hints_used, "max_impasse": self.max_impasse,
                "leaks_blocked": self.leaks_blocked,
                "leak_attempts": self.leak_attempts,
                "assisted_turns": self.assisted_turns,
                "assistance_before_attempt": self.assistance_given_before_attempt,
                "turns": [t.to_dict() for t in self.turns]}


@dataclass
class SessionResult:
    student_id: str
    started_at: float
    ended_at: float
    plan: SessionPlan
    items: List[ItemResult]
    mastery_before: Dict[str, float]
    mastery_after: Dict[str, float]
    streak_msg: str = ""
    wellbeing: Optional[BurnoutAssessment] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    rest_day: bool = False

    @property
    def minutes(self) -> float:
        return self.plan.minutes

    def to_dict(self) -> Dict[str, Any]:
        return {"student_id": self.student_id, "started_at": self.started_at,
                "ended_at": self.ended_at, "minutes": self.minutes,
                "rest_day": self.rest_day, "streak_msg": self.streak_msg,
                "items": [i.to_dict() for i in self.items],
                "mastery_before": self.mastery_before,
                "mastery_after": self.mastery_after,
                "wellbeing": ({"risk": self.wellbeing.risk,
                               "signals": self.wellbeing.signals,
                               "actions": self.wellbeing.actions,
                               "rest_mandated": self.wellbeing.rest_mandated}
                              if self.wellbeing else None),
                "metrics": self.metrics}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    def __init__(self, profile: StudentProfile, catalog: Dict[str, Skill],
                 km: Optional[KnowledgeModel] = None,
                 store: Optional[Store] = None,
                 router: Optional[Router] = None,
                 cfg: Optional[Config] = None,
                 playbook: Optional[Playbook] = None):
        self.profile = profile
        self.catalog = catalog
        self.cfg = cfg or Config.from_env()
        self.store = store or Store(self.cfg.db_path)
        self.router = router or Router(self.cfg, self.store)
        self.km = km or KnowledgeModel(profile.id, self.cfg.learning,
                                       self.store.load_skills(profile.id))
        self.scheduler = Scheduler(catalog, self.cfg.learning)
        #: The playbook is injected into every tutor prompt, which is what makes
        #: the self-improvement loop able to change behaviour at all.
        self.playbook = playbook if playbook is not None else Playbook(self.store)
        self.motivation = MotivationEngine(self.cfg.motivation)
        self.guard = WellbeingGuard(self.cfg.motivation)

    # -- persistence --------------------------------------------------------
    def save(self) -> None:
        self.store.upsert_student(self.profile.id, self.profile.to_dict())
        for sid, st in self.km.skills.items():
            self.store.save_skill(self.profile.id, sid, st.to_dict())

    # -- wellbeing gate ------------------------------------------------------
    def assess_wellbeing(self, now: Optional[float] = None) -> BurnoutAssessment:
        now = now if now is not None else time.time()
        sessions = []
        for ev in self.store.events(self.profile.id, kind="session", limit=40):
            if now - ev["ts"] > 14 * 86400:
                continue
            p = ev["payload"]
            sessions.append({"ts": ev["ts"], "minutes": p.get("minutes", 0),
                             "accuracy": p.get("metrics", {}).get("accuracy")})
        exam_days = None
        if self.profile.target_exams:
            soonest = min((e.get("date_ts", 0) for e in self.profile.target_exams
                           if e.get("date_ts")), default=0)
            if soonest:
                exam_days = int((soonest - now) / 86400)
        return self.guard.assess(sessions, now=now, exam_days_away=exam_days)

    # -- planning ------------------------------------------------------------
    def plan_session(self, now: Optional[float] = None,
                     budget_minutes: Optional[int] = None
                     ) -> Tuple[SessionPlan, BurnoutAssessment]:
        now = now if now is not None else time.time()
        wb = self.assess_wellbeing(now)
        budget = budget_minutes or self.profile.daily_minutes
        if wb.rest_mandated:
            budget = 0
        elif "reduce_load_40pct" in wb.actions:
            budget = max(8, int(budget * 0.6))
        plan = self.scheduler.plan(self.km, now=now, budget_minutes=budget,
                                   rest_day=wb.rest_mandated)
        plan.note = "; ".join(wb.signals) if wb.signals else plan.note
        return plan, wb  # type: ignore[return-value]

    # -- one item ------------------------------------------------------------
    def run_item(self, item: PlanItem, turns: Sequence[Tuple[str, Optional[bool]]],
                 expected_answer: Optional[str] = None,
                 options: Optional[int] = None,
                 now: Optional[float] = None,
                 max_turns: int = 10) -> ItemResult:
        """Turns are (student_text, correct_or_None) pairs supplied by the caller.

        In production these arrive from the UI; in evaluation they are scripted,
        which is what makes the whole system testable without an LLM.
        """
        now = now if now is not None else time.time()
        eng = SixMoveEngine(item.skill_id, now=now)
        res = ItemResult(item.skill_id, item.kind,
                         self.km.mastery(item.skill_id), self.km.mastery(item.skill_id))
        attempted_any = False

        for i, (raw_text, correct) in enumerate(turns[:max_turns]):
            student_text, lang = prepare_input(raw_text)
            plan = eng.plan_turn()
            move = Move(plan["move"])
            assistance = Assistance(plan["assistance"])

            # ---- the attempt-first gate -------------------------------------
            if assistance != Assistance.NONE and not attempted_any:
                res.assistance_given_before_attempt += 1

            # ---- compose the tutor's message ---------------------------------
            if plan["unaided"] or assistance == Assistance.NONE:
                tutor_text = offline_reply(move.value)
                source = "policy"
            else:
                contract = tutor_contract(assistance, move,
                                          ImpasseType(plan["impasse_type"]),
                                          self.profile.language)
                contract += "\n" + LANGUAGE_CONTRACT.format(
                    register=self.profile.language.replace("_", " "))
                allow = assistance == Assistance.FULL_WORKED
                contract += "\n" + self.playbook.as_prompt_block()
                raw = self.router.reply(
                    contract, assistance, move, student_text,
                    impasse_type=ImpasseType(plan["impasse_type"]),
                    language=self.profile.language,
                    context=self._context(item, res),
                    expected_answer=expected_answer,
                    playbook_block=self.playbook.as_prompt_block(),
                    tier=("strong" if assistance in
                          (Assistance.PARTIAL_WORKED, Assistance.FULL_WORKED) else "fast"))
                res.assisted_turns += 1
                tutor_text, verdict = enforce(raw, expected_answer, allow_answer=allow)
                source = "llm"
                if not verdict.ok:
                    res.leak_attempts += 1
                    res.leaks_blocked += 1
                    if not tutor_text:
                        tutor_text = offline_reply("point")

            # ---- record ------------------------------------------------------
            rec = TurnRecord(move=move.value, assistance=assistance.value,
                             student_text=raw_text, tutor_text=tutor_text,
                             correct=correct, impasse_depth=eng.state.impasse_depth,
                             impasse_type=plan["impasse_type"],
                             leaked=res.leaks_blocked > 0, source=source)
            res.turns.append(rec)

            # ---- update mastery when there is a verdict ------------------------
            if correct is not None:
                hinted = assistance in (Assistance.CONCRETE_HINT,
                                        Assistance.PARTIAL_WORKED,
                                        Assistance.FULL_WORKED)
                if hinted:
                    res.hints_used += 1
                self.km.update(item.skill_id, bool(correct), now=now + i * 30,
                               options=options, hint_used=hinted)

            # ---- advance the state machine ------------------------------------
            st = eng.observe(student_text, correct, now=now + i * 30)
            res.max_impasse = max(res.max_impasse, st.impasse_depth)
            if st.student_attempts:
                attempted_any = True
            if st.finished:
                res.finished = True
                if st.move == Move.TEST:
                    res.passed_unaided_test = bool(correct)
                break

        res.mastery_after = self.km.mastery(item.skill_id)
        self.store.log_event(self.profile.id, "item", res.to_dict())
        return res

    def _context(self, item: PlanItem, res: ItemResult) -> str:
        st = self.km.state(item.skill_id)
        return (f"Skill: {item.title} ({item.skill_id})\n"
                f"Subject: {item.subject}\n"
                f"Estimated mastery: {st.p_mastery:.2f}\n"
                f"Attempts so far this item: {len(res.turns)}\n"
                f"Hints already used: {res.hints_used}\n"
                f"Student's language: {self.profile.language}")

    # -- full session ---------------------------------------------------------
    def run_session(self, script: Optional[Dict[str, Sequence[Tuple[str, Optional[bool]]]]] = None,
                    now: Optional[float] = None,
                    budget_minutes: Optional[int] = None,
                    expected_answers: Optional[Dict[str, str]] = None,
                    options: Optional[Dict[str, int]] = None) -> SessionResult:
        """Run today's plan end-to-end.

        `script` maps skill_id → list of (student_text, correct) turns. It is how
        both the UI and the evaluation harness drive a session.
        """
        now = now if now is not None else time.time()
        plan, wb = self.plan_session(now, budget_minutes)  # type: ignore[misc]
        before = {s: st.p_mastery for s, st in self.km.skills.items()}

        items: List[ItemResult] = []
        if not plan.rest_day:
            for idx, item in enumerate(plan.items):
                turns = (script or {}).get(item.skill_id) or self._default_script(item, idx)
                items.append(self.run_item(
                    item, turns,
                    expected_answer=(expected_answers or {}).get(item.skill_id),
                    options=(options or {}).get(item.skill_id),
                    now=now + idx * 120))

        after = {s: st.p_mastery for s, st in self.km.skills.items()}
        streak_payload = update_streak(self.profile.streak, now, self.cfg.motivation)
        result = SessionResult(
            student_id=self.profile.id, started_at=now, ended_at=time.time(),
            plan=plan, items=items, mastery_before=before, mastery_after=after,
            streak_msg=streak_payload.get("message", ""), wellbeing=wb,
            rest_day=plan.rest_day)
        result.metrics = self._metrics(result)
        self.store.log_event(self.profile.id, "session", result.to_dict(), ts=now)
        self.save()
        return result

    @staticmethod
    def _default_script(item: PlanItem, idx: int) -> List[Tuple[str, Optional[bool]]]:
        """A plausible default when nobody scripts the session (demo mode).

        It must be able to *complete* the six-move sequence, otherwise the
        default path silently depresses the completion metric and hides real
        regressions behind a fake floor.
        """
        # six moves, six turns: PRIME → PROBE → POINT → ATTACH → STRENGTHEN
        # → TEST. The last turn is the unaided check, and it is the only one
        # that counts as evidence of learning.
        return [("mujhe thoda aata hai, try karta hoon", None),
                ("pehla step karke dekhta hoon: 12", False),
                ("theek hai samajh gaya, dobara karta hoon", None),
                ("ab 15 aata hai", True),
                ("15", True),
                ("15", True)]

    # -- metrics ---------------------------------------------------------------
    @staticmethod
    def _metrics(res: SessionResult) -> Dict[str, float]:
        turns = [t for i in res.items for t in i.turns]
        if not turns:
            return {"items": 0.0, "turns": 0.0, "accuracy": 0.0}
        graded = [t for t in turns if t.correct is not None]
        gains = [i.gain for i in res.items]
        return {
            "items": float(len(res.items)),
            "turns": float(len(turns)),
            "accuracy": (sum(1 for t in graded if t.correct) / len(graded)) if graded else 0.0,
            "mean_mastery_gain": (sum(gains) / len(gains)) if gains else 0.0,
            "hints_per_item": (sum(i.hints_used for i in res.items) / len(res.items))
            if res.items else 0.0,
            "leaks_blocked": float(sum(i.leaks_blocked for i in res.items)),
            "leak_attempts": float(sum(i.leak_attempts for i in res.items)),
            "leak_attempt_rate": (sum(i.leak_attempts for i in res.items) /
                                  max(1, sum(i.assisted_turns for i in res.items))),
            "assistance_before_attempt": float(
                sum(i.assistance_given_before_attempt for i in res.items)),
            "unaided_test_pass_rate": (
                sum(1 for i in res.items if i.passed_unaided_test) /
                max(1, sum(1 for i in res.items if i.passed_unaided_test is not None))),
            "completion": (sum(1 for i in res.items if i.finished) / len(res.items))
            if res.items else 0.0,
            "max_impasse": float(max((i.max_impasse for i in res.items), default=0)),
        }
