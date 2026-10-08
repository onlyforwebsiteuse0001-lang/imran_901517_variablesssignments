"""A deterministic simulated model — the eval harness's stand-in for an LLM.

Why this exists
---------------
The self-improvement loop is only real if a change in the *playbook* can change
the *behaviour* that the eval suite measures. With no API key, a canned offline
reply makes every hypothesis score identically and the promotion gate can never
demonstrate that it works.

So: a rule-based model that actually reads the playbook and obeys it — including
obeying it *badly* when the playbook says something harmful. That is what lets us
prove the gate catches a regression before a real model is ever involved.

This is also how the suite stays free: 4 scenarios x 3 items x 6 turns per
self-improvement cycle, with zero API calls.
"""
from __future__ import annotations

from typing import Dict, Optional

from .pedagogy import Assistance, ImpasseType, Move

ROMAN = {
    Assistance.NONE: "Aapki baari. Jo bhi aata hai, likh dein — ghalat bhi chalega.",
    Assistance.PROBE_QUESTION: "Ek sawal: is mein pehla step kya hoga? Sirf step bataayein.",
    Assistance.ERROR_DIRECTED: "Yahan ghalti step 2 mein hai. Step 2 mein kya hona chahiye?",
    Assistance.CONCRETE_HINT: "Agla step: pehle denominator ko common karein. Result mat likhein.",
    Assistance.PARTIAL_WORKED: "Isi tarah ke ek sawal ka aadha hissa: pehle hum 3x = 12 ko "
                               "x = 12/3 likhte hain. Ab aap apne sawal par yehi karein.",
    Assistance.FULL_WORKED: "Theek hai, main poora solution samjhata hoon. Pehle hum denominator "
                            "common karte hain, phir cross-multiply, phir simplify. Ab aap ek "
                            "aisa hi sawal bina madad ke karein.",
}
ENGLISH = {
    Assistance.NONE: "Your turn. Write whatever you have — even if it's wrong.",
    Assistance.PROBE_QUESTION: "One question: what's the first step here? Just the step.",
    Assistance.ERROR_DIRECTED: "The error is in step 2. What should step 2 be?",
    Assistance.CONCRETE_HINT: "Next step: make the denominators common. Don't write the result.",
    Assistance.PARTIAL_WORKED: "Half of a similar problem: first we write 3x = 12 as x = 12/3. "
                               "Now do that on your problem.",
    Assistance.FULL_WORKED: "Alright, here's the full solution. First make the denominators "
                            "common, then cross-multiply, then simplify. Now try one like it "
                            "without help.",
}


class SimulatedModel:
    """Rule-based tutor. Deterministic. Playbook-aware. Free."""

    def __init__(self, playbook_block: str = "", language: str = "roman_urdu"):
        self.playbook_block = playbook_block or ""
        self.language = language

    # -- playbook interpretation -------------------------------------------
    @property
    def _gives_answers(self) -> bool:
        """Detect a playbook that has drifted into answer-giving.

        This is the failure mode the promotion gate exists to catch. If a
        proposed playbook entry tells the tutor to hand over the answer, the
        simulated model obeys, the invariant check fires, and the hypothesis is
        rejected.
        """
        b = self.playbook_block.lower()
        harmful = ("give the student the full answer", "give the answer immediately",
                   "answer as soon as they ask", "seedha answer dein", "sirf answer dein")
        return any(h in b for h in harmful)

    @property
    def _skips_attempt_gate(self) -> bool:
        b = self.playbook_block.lower()
        return "do not require an attempt" in b or "attempt ki zaroorat nahi" in b

    # -- the model ----------------------------------------------------------
    def reply(self, assistance: Assistance, move: Move,
              impasse_type: ImpasseType = ImpasseType.NONE,
              context: str = "", expected_answer: Optional[str] = None,
              student_text: str = "") -> str:
        table = ROMAN if self.language != "english" else ENGLISH

        if self._gives_answers and expected_answer:
            return f"The answer is {expected_answer}."
        if self._skips_attempt_gate and expected_answer:
            return f"It's {expected_answer} — don't worry about the steps."

        if move in (Move.PRIME, Move.PROBE, Move.TEST):
            return table[Assistance.NONE]

        if assistance == Assistance.NONE:
            return table[Assistance.NONE]
        return table.get(assistance, table[Assistance.PROBE_QUESTION])


# ---------------------------------------------------------------------------

def simulated_reply(assistance: Assistance, move: Move,
                    impasse_type: ImpasseType = ImpasseType.NONE,
                    language: str = "roman_urdu",
                    playbook_block: str = "",
                    context: str = "",
                    expected_answer: Optional[str] = None,
                    student_text: str = "") -> str:
    """Functional wrapper so callers do not have to hold model state."""
    return SimulatedModel(playbook_block, language).reply(
        assistance, move, impasse_type, context, expected_answer, student_text)
