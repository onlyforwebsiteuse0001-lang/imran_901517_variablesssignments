"""The playbook: the system's accumulated, evidenced teaching knowledge.

Append-only, diffable, revertable. This is the layer the self-improvement loop
writes to — the model weights never change, the *context* does.

Kept in its own module because both the orchestrator (which reads it into every
prompt) and the evolution loop (which writes to it) need it, and a circular
import between them would otherwise be unavoidable.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .store import Store


PLAYBOOK_SEED: List[Tuple[str, str, str]] = [
    ("opener", "Open with a real choice of three concrete options, never 'what do you "
               "want to study?'. Reframing the invitation raised first-session take-up "
               "from 45.3% to 82.5%.", "Khanmigo RCT (Oreopoulos & Low, NBER w35620)"),
    ("attempt_gate", "Never assist before the student has produced an attempt or named a "
                     "specific confusion. This is the cheapest guardrail that measurably "
                     "protects learning.", "Bastani et al. 2025; six-move sequence"),
    ("escalation", "Escalate: probe question → name the error → concrete next step → "
                   "partial worked example → full worked example + immediate re-test. "
                   "Never repeat a move that already failed at the same impasse depth.",
     "20,462-turn impasse study: questioning AOR 0.78 vs error-directed AOR 1.14"),
    ("spacing", "Schedule reviews on expanding intervals and target ~85% accuracy. "
                "Spaced vs massed retrieval practice g = 0.74; expanding vs uniform "
                "makes no difference, so keep it simple.",
     "Latimier et al. meta-analysis; Cepeda 10-20% rule"),
    ("praise", "Praise the strategy ('you isolated the variable first'), never the "
               "ability ('you're smart'). Ability praise collapses at the first hard "
               "item and is the mechanism behind the burnout stories.",
     "SDT; K-12 gamification meta-analysis (Kurnaz & Koçtürk 2025)"),
    ("answer_seeker", "When a student demands the answer: acknowledge the time pressure "
                      "out loud, then ask for just the first step. Do not moralise about "
                      "cheating. Answer-seeking was 39.4% of all real tutor messages.",
     "Khanmigo usage analysis"),
    ("burnout", "If accuracy slides while effort stays high, and sessions run late or "
                "without rest days, mandate rest. Do not apologise for it.",
     "BMC Med Educ 2025 (Pakistani medical students)"),
    ("language", "Reply in the student's register — Roman Urdu is normal and welcome. "
                 "Never switch to formal English because the topic is academic.",
     "Roman-Urdu has no orthographic standard; normalise before reasoning"),
]


class Playbook:
    """The system's accumulated teaching knowledge. Append-only, diffable, revertable.

    Entries are never overwritten. Each new version carries its evidence and score,
    and an entry that stops earning its place gets deprecated rather than deleted —
    otherwise the playbook rots and the system confidently repeats dead advice.
    """

    def __init__(self, store: Store, scope: str = "global"):
        self.store = store
        self.scope = scope
        self.seed()

    # -- bootstrap -----------------------------------------------------------
    def seed(self) -> int:
        n = 0
        for key, value, evidence in PLAYBOOK_SEED:
            if not self.store.playbook_has_key(self.scope, key):
                self.store.playbook_put(self.scope, key, value, evidence, score=1.0)
                n += 1
        return n

    # -- reads ----------------------------------------------------------------
    def entries(self) -> List[Dict[str, Any]]:
        return self.store.playbook_scope(self.scope)

    def get(self, key: str) -> Optional[str]:
        row = self.store.playbook_get(self.scope, key)
        return row["value"] if row else None

    def version(self) -> int:
        return self.store.playbook_version(self.scope)

    def as_prompt_block(self, keys: Optional[Sequence[str]] = None) -> str:
        rows = self.entries()
        if keys:
            rows = [r for r in rows if r["key"] in set(keys)]
        if not rows:
            return ""
        lines = ["PLAYBOOK (accumulated, evidenced rules — follow these):"]
        for r in rows:
            lines.append(f"- [{r['key']}] {r['value']}")
        return "\n".join(lines)

    # -- writes ----------------------------------------------------------------
    def propose(self, key: str, value: str, evidence: str,
                score: float = 0.0) -> int:
        """Stage a new version. It is not trusted until `promote` says so."""
        return self.store.playbook_put(self.scope, key, value, evidence, score)

    def deprecate(self, key: str, reason: str) -> bool:
        return self.store.playbook_deprecate(self.scope, key, reason)

    # -- promotion gate ---------------------------------------------------------
    @staticmethod
    def should_promote(before: EvalResult, after: EvalResult,
                       min_delta: float = 0.005) -> Tuple[bool, str]:
        """Promote only on measured improvement, and never with any violation."""
        if after.violations:
            return False, f"blocked: {len(after.violations)} invariant violation(s)"
        if before.violations and not after.violations:
            return True, "fixed invariant violations"
        delta = after.score - before.score
        if delta >= min_delta:
            return True, f"score {before.score:.4f} → {after.score:.4f} (+{delta:.4f})"
        return False, f"no improvement ({delta:+.4f} < {min_delta})"
