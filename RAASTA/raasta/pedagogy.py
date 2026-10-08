"""Pedagogy: the six-move sequence, the impasse ladder, and answer guardrails.

This module is the reason the system is not just another chatbot.

Three research results drive every line here:

1. **The six-move sequence.** A new idea is acquired as
   Prime → Probe → Point → Attach → Strengthen → Test. AI scaffolding belongs
   *only* in the middle four. The first hard attempt and the final unaided check
   must be protected. Diagnostic: if letting AI in makes the task feel effortless,
   the AI is in the wrong place.

2. **Graduated, impasse-sensitive assistance.** Across 1,260 authentic sessions the
   benefit of *questioning* decayed as an impasse persisted (AOR 0.78) while
   *error-directed feedback* grew more useful (AOR 1.14). Repeating a failed
   scripted question recovered 28.1% of impasses; addressing the error recovered
   39.8%. So: escalate, never repeat.

3. **Guardrails beat both extremes.** Unrestricted GPT-4 produced +48% during
   practice but −17% on the later unaided exam. A version that withheld answers
   removed the harm; a well-engineered tutor roughly doubled learning.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class Move(str, Enum):
    PRIME = "prime"            # activate prior knowledge — student alone
    PROBE = "probe"            # first genuine attempt — student alone
    POINT = "point"            # name the specific error
    ATTACH = "attach"          # connect to what they already know
    STRENGTHEN = "strengthen"  # varied practice
    TEST = "test"              # unaided retrieval check


# The two moves the AI may never help with.
PROTECTED_MOVES = {Move.PRIME, Move.PROBE, Move.TEST}
AI_ASSISTED_MOVES = {Move.POINT, Move.ATTACH, Move.STRENGTHEN}

SEQUENCE: Tuple[Move, ...] = (
    Move.PRIME, Move.PROBE, Move.POINT, Move.ATTACH, Move.STRENGTHEN, Move.TEST,
)


class ImpasseType(str, Enum):
    NONE = "none"
    CONCEPTUAL_ERROR = "conceptual_error"   # wrong idea, confidently applied
    UNCERTAINTY = "uncertainty"             # "I don't know", "samajh nahi aya"
    HELP_SEEKING = "help_seeking"           # "answer bata do", "just tell me"
    OFF_TASK = "off_task"                   # says something unrelated
    PROCEDURAL_ERROR = "procedural_error"    # right idea, arithmetic/algebra slip


class Assistance(str, Enum):
    """What the tutor is allowed to do at this moment. Ordered by intrusiveness."""
    NONE = "none"                       # stay silent; it is their turn to think
    PROBE_QUESTION = "probe_question"   # a question that points at the concept
    ERROR_DIRECTED = "error_directed"   # name the specific error, do not solve it
    CONCRETE_HINT = "concrete_hint"     # next step, without the result
    PARTIAL_WORKED = "partial_worked"   # first half of a worked example
    FULL_WORKED = "full_worked"         # complete worked example, then re-test


# Impasse depth → what to do. Never repeat a move that already failed.
ESCALATION: Dict[int, Assistance] = {
    0: Assistance.NONE,
    1: Assistance.PROBE_QUESTION,
    2: Assistance.ERROR_DIRECTED,
    3: Assistance.CONCRETE_HINT,
    4: Assistance.PARTIAL_WORKED,
}
MAX_ESCALATION = Assistance.FULL_WORKED


# ---------------------------------------------------------------------------
# Impasse type detection (works on Roman Urdu / Urdu / English, offline)
# ---------------------------------------------------------------------------

_UNCERTAINTY_PAT = re.compile(
    r"\b(nahi\s+aata|nahi\s+aata|samajh\s+(nahi|ni)\s*(aaya|aata|aya)|"
    r"i\s+don'?t\s+know|idk|no\s+idea|confused|pata\s+nahi|"
    r"kuch\s+nahi\s+aata|not\s+sure|lost|stuck|kuch\s+samajh\s+nahi)\b", re.I)

_HELP_SEEK_PAT = re.compile(
    r"\b(answer\s+(bata|do|batao|dedo)|just\s+(tell|give)|sirf\s+answer|"
    r"give\s+me\s+the\s+answer|bata\s+do|batao|shortcut|solution\s+(do|bhej|dedo)|"
    r"ans\b|answer\s+hi\s+(bata|do))\b", re.I)

_OFF_TASK_PAT = re.compile(
    r"^\s*(hi+|hello+|helo+|salam+|assalamualaikum|kese\s+ho|"
    r"how\s+are\s+you|what'?s\s+up|ok+|hmm+|lol+|bye)\s*[.!?]?\s*$", re.I)

_PROCEDURAL_HINT_PAT = re.compile(
    r"\b(calculate|multiply|divide|add|subtract|sign|minus|plus|arithmetic|"
    r"calculation|galti\s+se|silly\s+mistake|copy|likhne)\b", re.I)


def classify_impasse(student_text: str, correct: Optional[bool] = None,
                     has_attempt: bool = False) -> ImpasseType:
    """Guess why the student is stuck. Runs offline, no LLM needed."""
    t = (student_text or "").strip()
    if not t:
        return ImpasseType.UNCERTAINTY
    if _OFF_TASK_PAT.match(t):
        return ImpasseType.OFF_TASK
    if _HELP_SEEK_PAT.search(t):
        return ImpasseType.HELP_SEEKING
    if _UNCERTAINTY_PAT.search(t):
        return ImpasseType.UNCERTAINTY
    if correct is False and has_attempt:
        return (ImpasseType.PROCEDURAL_ERROR if _PROCEDURAL_HINT_PAT.search(t)
                else ImpasseType.CONCEPTUAL_ERROR)
    return ImpasseType.NONE


def has_attempt(text: str) -> bool:
    """Did the student actually try, or just ask for the answer?

    The attempt-first gate is the single cheapest guardrail we have: no help
    until there is something to build on.
    """
    t = (text or "").strip()
    if len(t) < 3:
        return False
    if _HELP_SEEK_PAT.search(t) or _UNCERTAINTY_PAT.search(t):
        return False
    # any number, or a reasonably long utterance, counts as an attempt
    return bool(re.search(r"\d", t)) or len(t.split()) >= 3


# ---------------------------------------------------------------------------
# Tutoring state machine
# ---------------------------------------------------------------------------

@dataclass
class TutoringState:
    skill_id: str
    move: Move = Move.PRIME
    impasse_depth: int = 0
    impasse_type: ImpasseType = ImpasseType.NONE
    attempts_this_move: int = 0
    used_assistance: List[str] = field(default_factory=list)
    student_attempts: int = 0
    correct_streak: int = 0
    hints_used: int = 0
    started_at: float = 0.0
    finished: bool = False
    history: List[Dict] = field(default_factory=list)

    def record(self, event: str, **kw) -> None:
        kw["event"] = event
        kw["move"] = self.move.value
        kw["impasse_depth"] = self.impasse_depth
        self.history.append(kw)

    @property
    def ai_allowed(self) -> bool:
        return self.move in AI_ASSISTED_MOVES

    def assistance(self) -> Assistance:
        """Which level of help is permitted *right now*."""
        if not self.ai_allowed:
            return Assistance.NONE
        level = ESCALATION.get(min(self.impasse_depth, 4), MAX_ESCALATION)
        # once we have committed to a level, never go backwards within an impasse
        if self.used_assistance:
            try:
                prev = Assistance(self.used_assistance[-1])
            except ValueError:
                prev = level
            order = list(Assistance)
            if order.index(prev) > order.index(level):
                level = prev
        return level

    def next_unused_assistance(self) -> Assistance:
        """Escalate to the next level that has not already failed here."""
        order = list(Assistance)
        cur = self.assistance()
        i = order.index(cur)
        while i < len(order) - 1:
            i += 1
            cand = order[i]
            if cand.value not in self.used_assistance:
                return cand
        return MAX_ESCALATION


class SixMoveEngine:
    """Drives one (student, item) interaction through the six moves."""

    def __init__(self, skill_id: str, now: float = 0.0):
        self.state = TutoringState(skill_id=skill_id, started_at=now)

    # -- transitions --------------------------------------------------------
    def advance(self) -> Move:
        s = self.state
        i = SEQUENCE.index(s.move)
        if i < len(SEQUENCE) - 1:
            s.move = SEQUENCE[i + 1]
            s.attempts_this_move = 0
            s.record("advance")
        else:
            s.finished = True
            s.record("finished")
        return s.move

    def observe(self, student_text: str, correct: Optional[bool] = None,
                now: float = 0.0) -> TutoringState:
        """Fold one student turn into the state and decide what happens next."""
        s = self.state
        attempted = has_attempt(student_text)
        kind = classify_impasse(student_text, correct, attempted)
        s.attempts_this_move += 1
        if attempted:
            s.student_attempts += 1

        if s.move in (Move.PRIME, Move.PROBE):
            if attempted or correct is not None:
                # they engaged → move into the assisted middle of the sequence
                s.move = Move.POINT if correct is False else Move.ATTACH
                s.record("attempt", correct=correct, kind=kind.value)
            else:
                s.impasse_type = kind
                s.impasse_depth += 1
                s.record("no_attempt", kind=kind.value)
            return s

        if s.move in AI_ASSISTED_MOVES:
            if correct:
                s.impasse_depth = 0
                s.correct_streak += 1
                s.used_assistance.clear()
                s.record("progress", correct=True)
                if s.correct_streak >= 2:
                    s.move = Move.TEST
            else:
                s.correct_streak = 0
                s.impasse_type = kind
                s.impasse_depth += 1
                lvl = s.assistance()
                if lvl.value not in s.used_assistance:
                    s.used_assistance.append(lvl.value)
                s.record("struggle", correct=False, kind=kind.value, level=lvl.value)
            return s

        # TEST — unaided. Correct → done. Wrong → back to POINT, not to the answer.
        if correct:
            s.finished = True
            s.record("passed_test")
        else:
            s.impasse_depth += 1
            s.correct_streak = 0
            s.used_assistance.clear()
            s.move = Move.POINT
            s.record("failed_test", kind=kind.value)
        return s

    def plan_turn(self) -> Dict:
        """What the tutor should do next — consumed by the Tutor agent."""
        s = self.state
        lvl = s.assistance()
        return {
            "move": s.move.value,
            "ai_allowed": s.ai_allowed,
            "assistance": lvl.value,
            "impasse_depth": s.impasse_depth,
            "impasse_type": s.impasse_type.value,
            "attempt_required": s.move in (Move.PRIME, Move.PROBE),
            "unaided": s.move in PROTECTED_MOVES,
            "finished": s.finished,
        }


# ---------------------------------------------------------------------------
# Answer guardrails
# ---------------------------------------------------------------------------

_LEAK_PATTERNS = [
    re.compile(r"\bthe answer is\b", re.I),
    re.compile(r"\banswer\s*(is|:|=)\s*[-+]?[\d./]", re.I),
    re.compile(r"\b(jawab|ans)\s*(hai|:)\s*[-+]?[\d.]", re.I),
    re.compile(r"\b(equals?|=)\s*[-+]?\d+(\.\d+)?\s*(is)?\s*(the)?\s*(final|answer)", re.I),
    re.compile(r"\bfinal answer\b", re.I),
    re.compile(r"\boption\s*[\(\[]?\s*[a-dA-D]\s*[\)\]]?\s*(is)?\s*(correct|right|the answer)\b", re.I),
    re.compile(r"\b(correct option|right option|sahi option)\b", re.I),
    re.compile(r"^\s*[-+]?\d+(\.\d+)?\s*$"),        # a bare number
    re.compile(r"\b(it'?s|it is|value is|value)\s+[-+]?\d", re.I),
    re.compile(r"\b(jawab|ans)\b[^0-9]{0,12}\d", re.I),
    re.compile(r"[-+]?\d+(\.\d+)?\s*(hai|hoga|ho ga|is the answer)", re.I),
]


@dataclass
class GuardVerdict:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    action: str = "allow"        # allow | rewrite | block

    def __bool__(self) -> bool:
        return self.ok


def check_leak(text: str, expected_answer: Optional[str] = None,
               allow_answer: bool = False) -> GuardVerdict:
    """Detect whether a tutor message leaks the answer.

    `allow_answer=True` is only ever set by the impasse ladder at depth 4+,
    *after* a genuine attempt and immediately before a re-test.
    """
    reasons: List[str] = []
    if allow_answer:
        return GuardVerdict(True, ["answer disclosure permitted by escalation policy"], "allow")

    t = (text or "").strip()
    if not t:
        return GuardVerdict(False, ["empty message"], "block")

    for pat in _LEAK_PATTERNS:
        if pat.search(t):
            reasons.append(f"answer-leak pattern: {pat.pattern[:48]}")

    if expected_answer:
        ea = str(expected_answer).strip().lower()
        if ea and len(ea) > 1 and ea in t.lower():
            # allow it if it appears inside a question or a "what do you think" frame
            soft = re.search(r"(\?|kya|what do you think|soch|guess|karo)", t, re.I)
            if not soft:
                reasons.append("expected answer appears verbatim outside a question frame")

    if reasons:
        return GuardVerdict(False, reasons, "rewrite")
    return GuardVerdict(True, [], "allow")


SAFE_REWRITE_INSTRUCTION = (
    "Your last draft gave away the answer. Rewrite it so the student still has to think: "
    "ask what they already tried, name the specific error they made, or give ONLY the next "
    "step — never the result. One short question. Nothing else."
)


def enforce(text: str, expected_answer: Optional[str] = None,
            allow_answer: bool = False) -> Tuple[str, GuardVerdict]:
    """Guard the outgoing message. Returns (text_to_send, verdict)."""
    verdict = check_leak(text, expected_answer, allow_answer)
    if verdict.ok:
        return text, verdict
    if verdict.action == "block":
        return "", verdict
    # rewrite: strip the offending tail and end on a question
    stripped = re.split(r"(?i)\b(the answer is|final answer|jawab hai)\b", text)[0].strip()
    if len(stripped) < 20:
        stripped = ""
    return stripped, verdict


# ---------------------------------------------------------------------------
# Prompt contract handed to the LLM
# ---------------------------------------------------------------------------

def tutor_contract(assistance: Assistance, move: Move, impasse_type: ImpasseType,
                   language_register: str = "English") -> str:
    """The pedagogical policy, expressed as instructions the model must follow."""
    rules = {
        Assistance.NONE: "Do NOT help yet. It is the student's turn to think.",
        Assistance.PROBE_QUESTION:
            "Ask ONE short question that points at the concept. Do not explain, do not solve.",
        Assistance.ERROR_DIRECTED:
            "Name the exact error the student made and why it is wrong. Do not solve the problem. "
            "Then ask them to try that step again.",
        Assistance.CONCRETE_HINT:
            "Give the next single step as an action (\"pehle denominator ko common karo\"), "
            "without any result or number that finishes the problem.",
        Assistance.PARTIAL_WORKED:
            "Show the first half of a worked example for a SIMILAR problem, stop before the result, "
            "then ask the student to apply it to theirs.",
        Assistance.FULL_WORKED:
            "The student has genuinely tried and is deep in an impasse. Walk through the full "
            "solution step by step, then immediately ask them to redo a similar item unaided.",
    }
    return f"""You are RAASTA, a study companion for a Pakistani student.
Language: reply in {language_register}. Short sentences. Spoken, not written, tone.

CURRENT MOVE: {move.value.upper()}
ASSISTANCE LEVEL: {assistance.value}
IMPASSE TYPE: {impasse_type.value}
IMPASSE DEPTH RULE: if a question already failed here, never repeat it — escalate.

YOUR ONE JOB RIGHT NOW:
{rules[assistance]}

HARD RULES:
- Never give the final answer unless the assistance level is 'full_worked'.
- Never write a bare number or a bare option letter as the whole reply.
- If the student has not attempted yet, ask for their attempt first.
- Praise the strategy they used, never their intelligence.
- Two sentences maximum unless the assistance level is 'full_worked'.
"""
