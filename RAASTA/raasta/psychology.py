"""Motivation (Self-Determination Theory) and the wellbeing / burnout guard.

Two deliberate design choices, both evidence-driven:

1. **Gamification is a bridge, not the destination.** A K-12 meta-analysis found
   gamification lifts *extrinsic* motivation more than intrinsic (g = 0.713 vs
   0.638) and warns that, without support for autonomy / competence / relatedness,
   it produces "short-term compliance rather than deep, internalized engagement."
   So points exist, but they are always attached to a *strategy the student chose*.

2. **Nudges are a delivery layer, not the product.** Scaled Nudge-Unit trials
   average only ~1.4 pp effects, and study-time reminders produced precise null
   results on grades and retention. So reminders here always carry something real:
   a specific item, a specific time, a specific reason. No "keep going!" spam.

Anti-dark-pattern rules enforced in code:
  * streaks have grace days, so one bad day cannot destroy a month
  * leaderboards are private-by-default and never shame low performers
  * the wellbeing guard can *mandate* rest, and the system will not apologise
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .config import MotivationCfg


# ---------------------------------------------------------------------------
# Streak — survivable by design
# ---------------------------------------------------------------------------

@dataclass
class Streak:
    current: int = 0
    best: int = 0
    last_active_day: Optional[int] = None      # integer day number
    grace_used_this_month: int = 0
    grace_month: str = ""

    def to_dict(self) -> Dict:
        return {"current": self.current, "best": self.best,
                "last_active_day": self.last_active_day,
                "grace_used_this_month": self.grace_used_this_month,
                "grace_month": self.grace_month}

    @classmethod
    def from_dict(cls, d: Dict) -> "Streak":
        return cls(**{k: v for k, v in d.items()
                      if k in {"current", "best", "last_active_day",
                               "grace_used_this_month", "grace_month"}})


def _day_number(ts: float) -> int:
    return int(ts // 86400.0)


def update_streak(streak: Streak, now: float, cfg: MotivationCfg) -> Dict[str, str]:
    """Advance the streak. Returns a message payload (may be empty)."""
    today = _day_number(now)
    month = time.strftime("%Y-%m", time.gmtime(now))
    if streak.grace_month != month:
        streak.grace_month = month
        streak.grace_used_this_month = 0

    if streak.last_active_day is None:
        streak.current = 1
        streak.last_active_day = today
        streak.best = max(streak.best, 1)
        return {"event": "streak_start", "message": "Pehla din ho gaya. Kal phir milte hain."}

    gap = today - streak.last_active_day
    if gap <= 0:
        return {}
    if gap == 1:
        streak.current += 1
        streak.last_active_day = today
        streak.best = max(streak.best, streak.current)
        return ({"event": "streak_up", "message": f"{streak.current} din lagataar."}
                if streak.current % 5 == 0 else {})

    # gap >= 2 → did they have grace left?
    if streak.grace_used_this_month < cfg.grace_days_per_month and gap == 2:
        streak.grace_used_this_month += 1
        streak.last_active_day = today
        return {"event": "grace_used",
                "message": (f"Ek din chhoot gaya tha — main count continue kar raha hoon "
                            f"({cfg.grace_days_per_month - streak.grace_used_this_month} "
                            f"grace din is mahine baqi hain). Aaj chhota session karte hain.")}

    lost = streak.current
    streak.current = 1
    streak.last_active_day = today
    return {"event": "streak_reset",
            "message": ("Streak toot gayi — koi baat nahi. Ginti se zyada zaroori ye hai ke "
                        "aaj 10 minute nikal aaye. Shuru karein?"
                        if lost >= 3 else "Chalein, aaj se phir shuru.")}


# ---------------------------------------------------------------------------
# SDT motivation engine
# ---------------------------------------------------------------------------

@dataclass
class MotivationProfile:
    autonomy: float = 0.5      # does the student feel they choose?
    competence: float = 0.5    # do they feel capable?
    relatedness: float = 0.5   # do they feel connected?
    self_efficacy: float = 0.5
    identity: str = ""         # "main wo banda hoon jo har roz 20 minute nikalta hai"

    def to_dict(self) -> Dict:
        return {"autonomy": self.autonomy, "competence": self.competence,
                "relatedness": self.relatedness, "self_efficacy": self.self_efficacy,
                "identity": self.identity}

    @classmethod
    def from_dict(cls, d: Dict) -> "MotivationProfile":
        return cls(**{k: v for k, v in d.items()
                      if k in {"autonomy", "competence", "relatedness",
                               "self_efficacy", "identity"}})

    @property
    def need_support(self) -> float:
        return (self.autonomy + self.competence + self.relatedness) / 3.0


class MotivationEngine:
    """Turns learner state into the words that open, sustain and close a session."""

    def __init__(self, cfg: Optional[MotivationCfg] = None):
        self.cfg = cfg or MotivationCfg()

    # -- autonomy: always a real choice ------------------------------------
    def open_session(self, name: str, minutes: int, subjects: Sequence[str],
                     mastery_snapshot: Optional[Dict[str, float]] = None,
                     language: str = "roman_urdu") -> Dict:
        """Session opener. Research: *how* you invite decides whether they show up.

        Reframing the invitation and simplifying enrolment raised first-session
        take-up from 45.3% to 82.5% in the Khanmigo trial — bigger than any
        change to the model itself.
        """
        subj = ", ".join(subjects[:2]) if subjects else "aaj ka kaam"
        en = {
            "message": (f"Salam {name}! Aaj sirf {minutes} minute. "
                        f"Teen option hain — aap choose karein:"),
            "choices": [
                {"id": "a", "label": f"Jaldi win: {subj} se 2 aasan sawal",
                 "why": "confidence banata hai"},
                {"id": "b", "label": f"Zaroori: {subj} ki kamzor cheez pakrein",
                 "why": "sabse zyada marks isi se milte hain"},
                {"id": "c", "label": "Sirf review: jo seekha hai wo bhoolne se bachayein",
                 "why": "kamzor lag raha ho to ye best hai"},
            ],
            "note": "Choice aapki. Koi bhi choose karein, dono faida dete hain.",
        }
        if language == "english":
            en["message"] = f"Hi {name}! Just {minutes} minutes today. Pick one:"
        return en

    def commitment(self, subject: str, when: str, where: str,
                   language: str = "roman_urdu") -> str:
        """Implementation intention: when + where + what.

        The one planning mechanism with real evidence behind it. Vague goals
        ("I'll study more") do nothing; specific ones ("Physics, 7pm, my desk") do.
        """
        if language == "english":
            return (f"Lock it in: I will study {subject} at {when}, {where}. "
                    f"Reply 'done' when you sit down.")
        return (f"Pakka irada likh dein: main {when} baje {where} mein "
                f"{subject} parhunga/parhungi. Jab baith jayein to 'ho gaya' likh dein.")

    # -- competence: praise strategy, never ability -------------------------
    def feedback(self, correct: bool, strategy: Optional[str] = None,
                 streak: int = 0, mastery_delta: float = 0.0,
                 language: str = "roman_urdu") -> str:
        if correct:
            if strategy:
                base = (f"Sahi! Aur note karein *kaise*: {strategy}. "
                        f"Yehi tareeqa agle sawal mein bhi kaam aayega."
                        if language == "roman_urdu" else
                        f"Right — and note *how*: {strategy}. That move will work again.")
            else:
                base = ("Sahi jawab!" if language == "roman_urdu" else "Correct!")
            if mastery_delta > 0.05:
                base += (" Is hissa pe ab aap kaafi strong ho."
                         if language == "roman_urdu"
                         else " You're getting solid on this one.")
            return base
        # wrong: attribute to strategy + plan, never to ability
        return ("Galat jawab — iska matlab sirf itna hai ke ye step abhi pakka nahi hua. "
                "Hum isi step ko alag se karte hain."
                if language == "roman_urdu" else
                "Not yet — it just means this step isn't solid. Let's isolate it.")

    # -- relatedness --------------------------------------------------------
    def relatedness_nudge(self, partner_name: Optional[str] = None,
                          cohort_note: Optional[str] = None,
                          language: str = "roman_urdu") -> Optional[str]:
        if partner_name:
            return (f"{partner_name} aaj ka session khatam kar chuka hai. Aap?"
                    if language == "roman_urdu" else
                    f"{partner_name} already finished today's session. You?")
        if cohort_note:
            return cohort_note
        return None

    def celebrate(self, what: str, language: str = "roman_urdu") -> str:
        return (f"Ye bada kaam tha: {what}. Aapne wo kiya jo kal nahi kar sakte thay."
                if language == "roman_urdu" else
                f"That was real: {what}. You did something today you couldn't do yesterday.")


# ---------------------------------------------------------------------------
# Wellbeing / burnout guard
# ---------------------------------------------------------------------------

@dataclass
class BurnoutAssessment:
    risk: float                       # 0..1
    signals: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    rest_mandated: bool = False

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (f"<Burnout risk={self.risk:.2f} rest={self.rest_mandated} "
                f"signals={self.signals}>")


class WellbeingGuard:
    """Watches for burnout and is willing to say "stop".

    Pakistani medical students in a 2025 qualitative study named academic pressure,
    family expectation, financial guilt, career uncertainty and absent support as
    their main burnout triggers — one said "I'm carrying my whole family's hopes."
    A system that only ever says "grind more" becomes part of that problem.
    """

    def __init__(self, cfg: Optional[MotivationCfg] = None):
        self.cfg = cfg or MotivationCfg()

    def assess(self, sessions_last_14d: Sequence[Dict],
               now: Optional[float] = None,
               self_reported_stress: Optional[int] = None,
               exam_days_away: Optional[int] = None) -> BurnoutAssessment:
        now = now if now is not None else time.time()
        signals: List[str] = []
        risk = 0.0

        if not sessions_last_14d:
            return BurnoutAssessment(0.0, ["no recent activity"], ["gentle re-invitation"])

        # 1) intensity — averaged over *active* days, not over the whole window,
        #    otherwise a student who studies 2h on 4 days looks identical to a
        #    balanced one.
        total_min = sum(float(s.get("minutes", 0)) for s in sessions_last_14d)
        active_days = len({int(float(s.get("ts", now)) // 86400)
                           for s in sessions_last_14d}) or 1
        per_day = total_min / active_days
        if per_day > 75:
            risk += 0.22
            signals.append(f"high volume: {per_day:.0f} min/day on active days")

        # 2) late-night studying — measured in the student's LOCAL time, not UTC
        offset = getattr(self.cfg, "utc_offset_hours", 5.0) * 3600.0
        late = 0
        for s in sessions_last_14d:
            hour = time.gmtime(float(s.get("ts", now)) + offset).tm_hour
            if hour >= self.cfg.late_night_hour and hour < 5:
                late += 1
        if late >= 3:
            risk += min(0.22, 0.07 * late)
            signals.append(f"{late} late-night sessions (after 1am)")

        # 3) no rest days
        days = {int(float(s.get("ts", now)) // 86400) for s in sessions_last_14d}
        span = max(1, int(now // 86400) - min(days))
        rest_gap = span - len(days)
        if len(days) >= 10 and rest_gap <= 1:
            risk += 0.25
            signals.append(f"{len(days)} study days with {max(0, rest_gap)} days off "
                           "in two weeks")

        # 4) performance sliding while effort stays high (the classic signature)
        accs = [float(s.get("accuracy", 0.5)) for s in sessions_last_14d
                if s.get("accuracy") is not None]
        if len(accs) >= 6:
            half = len(accs) // 2
            early, late_acc = accs[:half], accs[half:]
            if early and late_acc and (sum(late_acc)/len(late_acc)) < (sum(early)/len(early)) - 0.10:
                risk += 0.18
                signals.append("accuracy dropping while effort stays high")

        # 5) shrinking sessions after a heavy period
        mins = [float(s.get("minutes", 0)) for s in sessions_last_14d]
        if len(mins) >= 6 and sum(mins[-3:]) < 0.5 * sum(mins[:3]):
            risk += 0.12
            signals.append("session length collapsed recently")

        # 6) self-report (most reliable signal when available)
        if self_reported_stress is not None:
            # self-report is the most reliable signal we get, so it is weighted
            # more heavily than any behavioural proxy
            risk += 0.35 * max(0.0, min(1.0, (self_reported_stress - 1) / 4.0))
            if self_reported_stress >= 4:
                signals.append(f"self-reported stress {self_reported_stress}/5")

        # 7) exam proximity amplifies everything
        if exam_days_away is not None and exam_days_away <= 7:
            risk *= 1.15

        risk = max(0.0, min(1.0, risk))

        actions: List[str] = []
        rest_mandated = False
        if risk >= self.cfg.burnout_mandate_rest:
            rest_mandated = True
            actions += ["mandate_rest_day",
                        "switch_to_review_only",
                        "send_supportive_checkin",
                        "suppress_streak_pressure"]
        elif risk >= self.cfg.burnout_reduce_load:
            actions += ["reduce_load_40pct", "prefer_review_over_new",
                        "suppress_streak_pressure"]
        elif risk >= 0.25:
            actions += ["keep_sessions_short", "offer_choice_not_command"]
        else:
            actions.append("proceed_normal")

        return BurnoutAssessment(risk, signals, actions, rest_mandated)

    def rest_day_message(self, language: str = "roman_urdu",
                         recovery: str = "kal") -> str:
        return ("Aaj ka din chhut raha hai — jaan bujh kar. Aap pichhle do hafton se "
                "lagataar push kar rahe hain aur isi liye results ulta ja rahe hain. "
                "Aaj rest karein, achchi neend lein. Main {} ready rahunga. "
                "Ye streak se zyada important hai."
                .format(recovery)
                if language == "roman_urdu" else
                f"Today is off — on purpose. You've been pushing hard for two weeks and "
                f"your accuracy is sliding because of it. Rest, sleep. I'll be ready {recovery}. "
                f"This matters more than the streak.")


# ---------------------------------------------------------------------------
# Re-engagement (for the student who went quiet)
# ---------------------------------------------------------------------------

def reengagement_message(days_away: int, last_topic: Optional[str] = None,
                         language: str = "roman_urdu") -> Dict:
    """Ladder that gets *softer*, not louder, the longer they are away.

    Guilt is a short-term motivator and a long-term churn engine.
    """
    if days_away <= 1:
        msg = ("Kal miss ho gaya. Aaj sirf 5 minute — jo bhi ho."
               if language == "roman_urdu" else "Missed yesterday. Just 5 minutes today.")
    elif days_away <= 4:
        msg = (f"{days_away} din ho gaye. Koi masla to hoga — waqai time nahi mila, "
               f"ya koi cheez mushkil lag rahi hai? Bataayein to main plan change kar deta hoon."
               if language == "roman_urdu" else
               f"{days_away} days. Something got in the way — time, or something felt too hard? "
               f"Tell me and I'll change the plan.")
    else:
        msg = ("Bohot din ho gaye. Koi guilt nahi — plan hi galat tha shayad. "
               "Agar wapas aana chahein to main bilkul chhote se shuru kar deta hoon: 5 minute, ek sawal."
               if language == "roman_urdu" else
               "It's been a while. No guilt — maybe the plan was wrong, not you. "
               "If you want back in, we start tiny: 5 minutes, one question.")
    out = {"days_away": days_away, "message": msg, "offer_minutes": 5}
    if last_topic:
        out["resume_hint"] = last_topic
    return out
