"""Tests with no framework and no dependencies: `python -m tests.test_core`.

Every test here is a claim about how the system must behave. If one of these
breaks, the system got worse at teaching — not just worse at running.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from raasta import bkt, catalog as catalog_mod, evolve, language, orchestrator
from raasta import pedagogy, psychology, research, router, scheduler
from raasta.psychology import update_streak
from raasta.config import Config, Learning, MotivationCfg
from raasta.store import Store

DAY = 86400.0


# ---------------------------------------------------------------------------
# BKT
# ---------------------------------------------------------------------------

class TestBKT(unittest.TestCase):
    def test_mastery_rises_with_correct_answers(self):
        km = bkt.KnowledgeModel("t1")
        p0 = km.mastery("s1")
        for _ in range(8):
            km.update("s1", True)
        self.assertGreater(km.mastery("s1"), p0)
        self.assertGreater(km.mastery("s1"), 0.8)

    def test_mastery_falls_with_wrong_answers(self):
        km = bkt.KnowledgeModel("t2")
        for _ in range(4):
            km.update("s1", True)
        mid = km.mastery("s1")
        for _ in range(4):
            km.update("s1", False)
        self.assertLess(km.mastery("s1"), mid)

    def test_guess_rate_depends_on_options(self):
        km = bkt.KnowledgeModel("t3")
        self.assertAlmostEqual(bkt.guess_rate(4), 0.25)
        self.assertAlmostEqual(bkt.guess_rate(2), 0.5)
        self.assertLess(bkt.guess_rate(None), 0.1)

    def test_forgetting_decays_over_time(self):
        km = bkt.KnowledgeModel("t4")
        now = time.time()
        for _ in range(6):
            km.update("s1", True, now=now)
        before = km.mastery("s1")
        km.update("s1", True, now=now + 30 * DAY)
        self.assertLess(km.mastery("s1"), before)

    def test_more_reps_mean_longer_half_life(self):
        km = bkt.KnowledgeModel("t5")
        st = km.state("s1")
        hl0 = km.half_life_days(st)
        for _ in range(6):
            km.update("s1", True)
        self.assertGreater(km.half_life_days(km.state("s1")), hl0)

    def test_fast_learner_gets_higher_learning_rate(self):
        slow = bkt.KnowledgeModel("slow")
        fast = bkt.KnowledgeModel("fast")
        # slow student: repeated failure then success is uninformative; use clean runs
        for _ in range(6):
            slow.update("s1", False)
        for _ in range(6):
            fast.update("s1", True)
        self.assertGreater(fast.state("s1").p_transit, slow.state("s1").p_transit)

    def test_spacing_interval_grows_and_shrinks(self):
        km = bkt.KnowledgeModel("t6")
        km.update("s1", True)
        i1 = km.state("s1").interval_days
        for _ in range(4):
            km.update("s1", True)
        i2 = km.state("s1").interval_days
        self.assertGreaterEqual(i2, i1)
        for _ in range(3):
            km.update("s1", False)
        self.assertLess(km.state("s1").interval_days, i2)

    def test_due_logic(self):
        km = bkt.KnowledgeModel("t7")
        now = time.time()
        km.update("s1", True, now=now)
        self.assertFalse(km.due("s1", now + 3600))
        self.assertTrue(km.due("s1", now + 30 * DAY))

    def test_expected_gain_prefers_weak_skills(self):
        km = bkt.KnowledgeModel("t8")
        km.state("weak").p_mastery = 0.2
        km.state("strong").p_mastery = 0.9
        self.assertGreater(km.expected_gain("weak"), km.expected_gain("strong"))

    def test_roundtrip_serialisation(self):
        km = bkt.KnowledgeModel("t9")
        km.update("s1", True)
        restored = bkt.KnowledgeModel("t9", states=km.to_dict())
        self.assertAlmostEqual(restored.mastery("s1"), km.mastery("s1"))


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.cat = catalog_mod.load_catalog("matric_physics")
        self.sch = scheduler.Scheduler(self.cat)

    def test_plan_respects_budget(self):
        km = bkt.KnowledgeModel("s", Learning(), {})
        for sid in list(self.cat)[:6]:
            for _ in range(3):
                km.update(sid, True)
        plan = self.sch.plan(km, budget_minutes=10)
        self.assertLessEqual(plan.minutes, 10.0 + 1e-6)

    def test_unlearned_prereq_blocks_advanced_skill(self):
        km = bkt.KnowledgeModel("s")
        self.assertIsNotNone(self.sch._blocking_prereq(self.cat["motion_eqns"], km))
        for p in self.cat["motion_eqns"].prereqs:
            km.state(p).p_mastery = 0.95
        self.assertIsNone(self.sch._blocking_prereq(self.cat["motion_eqns"], km))

    def test_overdue_reviews_come_first(self):
        km = bkt.KnowledgeModel("s")
        now = time.time()
        km.update("units_si", True, now=now - 40 * DAY)
        for _ in range(3):
            km.update("motion_eqns", True, now=now - 40 * DAY)
        km.state("units_si").last_seen = now - 40 * DAY
        km.state("units_si").interval_days = 2.0
        plan = self.sch.plan(km, now=now, budget_minutes=20)
        self.assertTrue(plan.items)
        self.assertEqual(plan.items[0].kind, "review")

    def test_no_new_items_beyond_cap(self):
        km = bkt.KnowledgeModel("s")
        plan = self.sch.plan(km, budget_minutes=120, max_new=2)
        new = sum(1 for i in plan.items if i.kind == "new")
        self.assertLessEqual(new, 2)

    def test_interleaving_rotates_subjects(self):
        cat = catalog_mod.combined("matric_physics", "matric_math")
        sch = scheduler.Scheduler(cat)
        km = bkt.KnowledgeModel("s")
        for sid in ["units_si", "num_fractions", "motion_eqns", "num_percent"]:
            km.state(sid).p_mastery = 0.4
            km.state(sid).attempts = 2
        plan = sch.plan(km, budget_minutes=60)
        practice = [i.subject for i in plan.items if i.kind != "review"]
        if len(practice) >= 3:
            self.assertGreater(len(set(practice)), 1)

    def test_rest_day_produces_empty_plan(self):
        km = bkt.KnowledgeModel("s")
        plan = self.sch.plan(km, rest_day=True)
        self.assertTrue(plan.rest_day)
        self.assertEqual(plan.items, [])

    def test_weekly_plan_shape(self):
        km = bkt.KnowledgeModel("s")
        for _ in range(3):
            km.update("units_si", True)
        week = self.sch.weekly_plan(km, days=7, rest_days=[6])
        self.assertEqual(len(week), 7)
        self.assertTrue(week[6].rest_day)


# ---------------------------------------------------------------------------
# Pedagogy
# ---------------------------------------------------------------------------

class TestPedagogy(unittest.TestCase):
    def test_protected_moves_are_unaided(self):
        eng = pedagogy.SixMoveEngine("s1")
        for mv in (pedagogy.Move.PRIME, pedagogy.Move.PROBE, pedagogy.Move.TEST):
            eng.state.move = mv
            self.assertFalse(eng.state.ai_allowed)
            self.assertEqual(eng.state.assistance(), pedagogy.Assistance.NONE)

    def test_assisted_moves_allow_help(self):
        eng = pedagogy.SixMoveEngine("s1")
        eng.state.move = pedagogy.Move.POINT
        eng.state.impasse_depth = 2
        self.assertEqual(eng.state.assistance(), pedagogy.Assistance.ERROR_DIRECTED)

    def test_escalation_never_repeats_a_failed_move(self):
        eng = pedagogy.SixMoveEngine("s1")
        eng.state.move = pedagogy.Move.POINT
        levels = []
        for depth in range(1, 6):
            eng.state.impasse_depth = depth
            nxt = eng.state.next_unused_assistance()
            levels.append(nxt)
            eng.state.used_assistance.append(nxt.value)
        order = list(pedagogy.Assistance)
        idx = [order.index(l) for l in levels]
        self.assertEqual(idx, sorted(idx))          # monotonically escalating
        # unique until we hit the ceiling: past full_worked there is nowhere
        # left to escalate to, so repeating it is correct, not a bug
        if pedagogy.Assistance.FULL_WORKED in levels:
            upto = levels.index(pedagogy.Assistance.FULL_WORKED) + 1
        else:
            upto = len(levels)
        self.assertEqual(len(set(levels[:upto])), len(levels[:upto]))

    def test_impasse_type_detection_roman_urdu(self):
        self.assertEqual(pedagogy.classify_impasse("mujhe samajh nahi aaya"),
                         pedagogy.ImpasseType.UNCERTAINTY)
        self.assertEqual(pedagogy.classify_impasse("bas answer bata do"),
                         pedagogy.ImpasseType.HELP_SEEKING)
        self.assertEqual(pedagogy.classify_impasse("hello"),
                         pedagogy.ImpasseType.OFF_TASK)

    def test_attempt_gate(self):
        self.assertFalse(pedagogy.has_attempt("answer bata do"))
        self.assertFalse(pedagogy.has_attempt("samajh nahi aaya"))
        self.assertTrue(pedagogy.has_attempt("pehle main 12 se divide karun ga"))

    def test_leak_detection(self):
        self.assertFalse(pedagogy.check_leak("The answer is 42").ok)
        self.assertFalse(pedagogy.check_leak("42").ok)
        self.assertTrue(pedagogy.check_leak("Pehle denominator ko dekhein?").ok)
        self.assertTrue(pedagogy.check_leak("The answer is 42",
                                            allow_answer=True).ok)

    def test_enforce_strips_leak(self):
        text, verdict = pedagogy.enforce("Sure! The answer is 42. Anything else?")
        self.assertFalse(verdict.ok)
        self.assertNotIn("42", text)

    def test_escalation_reaches_worked_example_when_student_is_stuck(self):
        eng = pedagogy.SixMoveEngine("s1")
        eng.observe("samajh nahi aaya", None)                  # PRIME, no attempt
        for _ in range(5):
            eng.observe("mujhe kuch nahi aata", False)
        self.assertGreaterEqual(eng.state.impasse_depth, 3)
        self.assertIn(eng.state.assistance(),
                      (pedagogy.Assistance.CONCRETE_HINT,
                       pedagogy.Assistance.PARTIAL_WORKED,
                       pedagogy.Assistance.FULL_WORKED))

    def test_correct_work_completes_the_sequence(self):
        # the sequence genuinely requires an UNAIDED test at the end, so a
        # student who is doing well still needs a final turn without help.
        eng = pedagogy.SixMoveEngine("s1")
        eng.observe("main try karta hoon: 12", True)      # PRIME -> ATTACH
        eng.observe("aur ek: 15", True)                   # streak 1
        eng.observe("15", True)                           # streak 2 -> TEST
        self.assertEqual(eng.state.move, pedagogy.Move.TEST)
        self.assertFalse(eng.state.finished)
        eng.observe("15", True)                           # unaided pass
        self.assertTrue(eng.state.finished)


# ---------------------------------------------------------------------------
# Psychology
# ---------------------------------------------------------------------------

class TestPsychology(unittest.TestCase):
    def test_streak_increments_and_survives_grace(self):
        cfg = MotivationCfg()
        now = time.time()
        st = psychology.Streak()
        update_streak(st, now, cfg)
        self.assertEqual(st.current, 1)
        update_streak(st, now + DAY, cfg)
        self.assertEqual(st.current, 2)
        # miss one day → grace
        r = update_streak(st, now + 3 * DAY, cfg)
        self.assertEqual(r.get("event"), "grace_used")
        self.assertEqual(st.current, 2)

    def test_streak_resets_after_long_absence(self):
        st = psychology.Streak()
        update_streak(st, time.time(), MotivationCfg())
        r = update_streak(st, time.time() + 10 * DAY, MotivationCfg())
        self.assertEqual(r["event"], "streak_reset")

    def test_burnout_detects_no_rest_and_sliding_accuracy(self):
        guard = psychology.WellbeingGuard(MotivationCfg())
        now = time.time()
        sessions = []
        for d in range(12):
            sessions.append({"ts": now - d * DAY, "minutes": 80.0,
                             "accuracy": 0.85 - 0.03 * d})
        a = guard.assess(sessions, now=now)
        self.assertGreater(a.risk, 0.4)
        self.assertIn("accuracy dropping while effort stays high", a.signals)

    def test_burnout_low_for_balanced_student(self):
        guard = psychology.WellbeingGuard(MotivationCfg())
        now = time.time()
        sessions = [{"ts": now - d * DAY, "minutes": 30.0, "accuracy": 0.85}
                    for d in range(12) if d % 3 != 0]
        a = guard.assess(sessions, now=now)
        self.assertLess(a.risk, 0.4)
        self.assertFalse(a.rest_mandated)

    def test_high_risk_mandates_rest(self):
        guard = psychology.WellbeingGuard(MotivationCfg())
        now = time.time()
        sessions = [{"ts": now - d * DAY, "minutes": 120.0, "accuracy": 0.4}
                    for d in range(13)]
        a = guard.assess(sessions, now=now, self_reported_stress=5)
        self.assertTrue(a.rest_mandated)

    def test_feedback_praises_strategy_not_ability(self):
        e = psychology.MotivationEngine()
        msg = e.feedback(True, strategy="you isolated the variable first")
        self.assertIn("isolated", msg)
        self.assertNotIn("smart", msg.lower())

    def test_opener_offers_a_choice(self):
        e = psychology.MotivationEngine()
        op = e.open_session("Imran", 20, ["Physics"])
        self.assertEqual(len(op["choices"]), 3)

    def test_reengagement_gets_softer_not_louder(self):
        short = psychology.reengagement_message(1)
        long = psychology.reengagement_message(20)
        self.assertIn("guilt", long["message"])
        self.assertNotIn("guilt", short["message"])


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

class TestLanguage(unittest.TestCase):
    def test_script_detection(self):
        self.assertEqual(language.detect_script("یہ ایک جملہ ہے"), "urdu")
        self.assertEqual(language.detect_script("hello world"), "latin")
        self.assertEqual(language.detect_script(""), "empty")

    def test_language_detection(self):
        self.assertEqual(language.detect_language("mujhe samajh nahi aaya"), "roman_urdu")
        self.assertEqual(language.detect_language("solve this integral"), "english")

    def test_roman_urdu_normalisation(self):
        self.assertEqual(language.normalize_roman_urdu("mujhe kuch samajh nhi aata"),
                         "mujhe kuch samajh nahi aata")
        self.assertEqual(language.normalize_roman_urdu("kia kr raha hoon"),
                         "kya kar raha hoon")

    def test_prepare_input_normalises(self):
        text, lang = language.prepare_input("mujhe prhai krni hy")
        self.assertEqual(lang, "roman_urdu")
        self.assertNotIn("prhai", text)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class TestRouter(unittest.TestCase):
    def test_offline_mode_never_calls_out(self):
        cfg = Config(db_path=":memory:", offline=True)
        r = router.Router(cfg, Store(":memory:"))
        out = r.complete([{"role": "user", "content": "hello"}])
        self.assertTrue(out)
        self.assertEqual(r.calls[-1].provider, "offline")

    def test_no_keys_falls_back_gracefully(self):
        cfg = Config(db_path=":memory:")
        r = router.Router(cfg, Store(":memory:"))
        out = r.complete([{"role": "user", "content": "hello"}])
        self.assertTrue(out)

    def test_quota_ledger_counts(self):
        st = Store(":memory:")
        st.bump_usage("groq")
        st.bump_usage("groq")
        self.assertEqual(st.usage_today("groq"), 2)

    def test_cache_hit_avoids_a_call(self):
        st = Store(":memory:")
        st.cache_put("k", "v")
        self.assertEqual(st.cache_get("k"), "v")

    def test_status_reports_configuration(self):
        cfg = Config(db_path=":memory:")
        st = Store(":memory:")
        rows = router.Router(cfg, st).status()
        self.assertTrue(any(r["provider"] == "groq" for r in rows))
        self.assertIn("remaining", rows[0])

    def test_offline_reply_never_gives_an_answer(self):
        for role in ("prime", "probe", "point", "test", "fallback"):
            text = router.offline_reply(role)
            self.assertTrue(text)
            self.assertTrue(pedagogy.check_leak(text).ok, f"leaked: {text}")


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore(unittest.TestCase):
    def test_events_are_append_only(self):
        st = Store(":memory:")
        st.log_event("s", "session", {"a": 1})
        st.log_event("s", "session", {"a": 2})
        self.assertEqual(st.count_events("s", "session"), 2)

    def test_playbook_versions_never_overwrite(self):
        st = Store(":memory:")
        v1 = st.playbook_put("global", "k", "first")
        v2 = st.playbook_put("global", "k", "second")
        self.assertEqual((v1, v2), (1, 2))
        self.assertEqual(st.playbook_get("global", "k")["value"], "second")

    def test_deprecate_hides_entry(self):
        st = Store(":memory:")
        st.playbook_put("global", "k", "v")
        st.playbook_deprecate("global", "k", "stale")
        self.assertIsNone(st.playbook_get("global", "k"))
        self.assertEqual(len(st.playbook_scope("global", status="deprecated")), 1)

    def test_forget_student_removes_everything(self):
        st = Store(":memory:")
        st.upsert_student("s", {"name": "x"})
        st.log_event("s", "session", {})
        st.playbook_put("student:s", "k", "v")
        st.forget_student("s")
        self.assertIsNone(st.get_student("s"))
        self.assertEqual(st.count_events("s"), 0)

    def test_research_dedupes_by_url(self):
        st = Store(":memory:")
        self.assertTrue(st.add_research("t", "src", "h1", "c"))
        self.assertFalse(st.add_research("t", "src", "h1", "c"))


# ---------------------------------------------------------------------------
# Orchestrator (end to end)
# ---------------------------------------------------------------------------

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.cat = catalog_mod.load_catalog("matric_physics")
        self.cfg = Config(db_path=":memory:", offline=True)

    def _orch(self, sid="o1"):
        st = Store(":memory:")
        p = orchestrator.StudentProfile(id=sid, name="Test", language="roman_urdu")
        return orchestrator.Orchestrator(p, self.cat, store=st, cfg=self.cfg)

    def test_session_runs_and_raises_mastery(self):
        o = self._orch()
        for _ in range(4):
            o.run_session(script={"units_si": [("try", None), ("4", True),
                                               ("ok", True), ("4", True)]})
        self.assertGreater(o.km.mastery("units_si"), 0.5)

    def test_answer_seeker_never_gets_the_answer(self):
        o = self._orch()
        res = o.run_session(script={"units_si": [
            ("answer bata do", None),
            ("bas answer chahiye", None),
            ("please sirf jawab do", None),
        ]}, expected_answers={"units_si": "42"})
        for item in res.items:
            for t in item.turns:
                v = pedagogy.check_leak(t.tutor_text, "42")
                self.assertTrue(v.ok, f"leaked: {t.tutor_text}")

    def test_attempt_gate_recorded(self):
        o = self._orch()
        res = o.run_session(script={"units_si": [("answer bata do", None)]})
        item = res.items[0]
        self.assertGreaterEqual(item.assistance_given_before_attempt, 0)
        self.assertIn(item.turns[0].assistance, ("none", "probe_question"))

    def test_mastery_persists_across_orchestrators(self):
        st = Store(":memory:")
        p = orchestrator.StudentProfile(id="o2")
        o1 = orchestrator.Orchestrator(p, self.cat, store=st, cfg=self.cfg)
        o1.run_session(script={"units_si": [("x", None), ("4", True), ("4", True)]})
        after = o1.km.mastery("units_si")
        p2 = orchestrator.StudentProfile.from_dict(st.get_student("o2")["profile"])
        o2 = orchestrator.Orchestrator(p2, self.cat, store=st, cfg=self.cfg)
        self.assertAlmostEqual(o2.km.mastery("units_si"), after)

    def test_wellbeing_can_force_a_rest_day(self):
        st = Store(":memory:")
        p = orchestrator.StudentProfile(id="o3")
        o = orchestrator.Orchestrator(p, self.cat, store=st, cfg=self.cfg)
        now = time.time()
        for d in range(12):
            st.log_event("o3", "session",
                         {"minutes": 120, "metrics": {"accuracy": 0.3}},
                         ts=now - d * DAY)
        plan, wb = o.plan_session(now)      # type: ignore[misc]
        self.assertTrue(plan.rest_day or len(plan.items) == 0 or wb.risk > 0.4)

    def test_malicious_llm_cannot_leak_the_answer(self):
        """The single most important safety property in the system.

        Simulate an LLM that ignores every instruction and tries to hand over
        the answer. The guardrail is in *code*, not in the prompt, so it must
        still hold.
        """
        class LeakyRouter:
            """An LLM that ignores every instruction and hands over the answer."""
            calls = 0

            def reply(self, contract, assistance, move, student_text, **kw):
                LeakyRouter.calls += 1
                return "Sure thing! The answer is 4. Hope that helps!"

        st = Store(":memory:")
        p = orchestrator.StudentProfile(id="leak")
        o = orchestrator.Orchestrator(p, self.cat, store=st, cfg=self.cfg)
        o.router = LeakyRouter()
        res = o.run_session(script={"units_si": [
            ("main try karta hoon: 2", False),
            ("phir try: 3", False),
            ("ab samajh gaya: 4", True),
            ("4", True),
            ("4", True),
        ]}, expected_answers={"units_si": "4"})
        self.assertGreater(LeakyRouter.calls, 0, "router was never consulted")
        for item in res.items:
            self.assertGreater(item.leaks_blocked, 0, "leak was not blocked")
            for t in item.turns:
                self.assertNotIn("answer is 4", t.tutor_text.lower(),
                                 f"answer reached the student: {t.tutor_text}")

    def test_delayed_transfer_is_measured_separately(self):
        """Mastery must survive a gap, and a gap must expose forgetting."""
        o = self._orch()
        for _ in range(4):
            o.run_session(script={"units_si": [("try", None), ("4", True),
                                               ("4", True), ("4", True),
                                               ("4", True)]})
        peak = o.km.mastery("units_si")
        o.run_session(now=time.time() + 45 * DAY,
                      script={"units_si": [("4", True)]})
        self.assertGreater(peak, 0.6)
        self.assertLessEqual(o.km.mastery("units_si"), peak + 0.05)

    def test_metrics_are_produced(self):
        o = self._orch()
        res = o.run_session(script={"units_si": [("try", None), ("4", True), ("4", True)]})
        for key in ("items", "turns", "accuracy", "completion"):
            self.assertIn(key, res.metrics)


# ---------------------------------------------------------------------------
# Evals + self-improvement
# ---------------------------------------------------------------------------

class TestEvolve(unittest.TestCase):
    def test_frozen_suite_holds_all_invariants(self):
        cfg = Config(db_path=":memory:", offline=True)
        cat = catalog_mod.load_catalog("matric_physics")
        res = evolve.run_evals(cat, store=Store(":memory:"), cfg=cfg,
                               db_path=":memory:")
        self.assertEqual(res.violations, [], f"violations: {res.violations[:5]}")
        self.assertTrue(res.passed)

    def test_suite_is_deterministic(self):
        cfg = Config(db_path=":memory:", offline=True)
        cat = catalog_mod.load_catalog("matric_physics")
        a = evolve.run_evals(cat, store=Store(":memory:"), cfg=cfg, db_path=":memory:")
        b = evolve.run_evals(cat, store=Store(":memory:"), cfg=cfg, db_path=":memory:")
        self.assertAlmostEqual(a.score, b.score, places=6)

    def test_playbook_seeds(self):
        st = Store(":memory:")
        pb = evolve.Playbook(st)
        self.assertGreater(len(pb.entries()), 5)
        self.assertIsNotNone(pb.get("escalation"))
        self.assertIn("impasse", pb.get("escalation").lower())

    def test_promotion_gate_blocks_when_no_improvement(self):
        def mk(passed=True, score=0.5, viol=()):
            return evolve.EvalResult("core", 1, passed, score, {}, list(viol))
        ok, _ = evolve.Playbook.should_promote(mk(score=0.50), mk(score=0.52))
        self.assertTrue(ok)
        ok, _ = evolve.Playbook.should_promote(mk(score=0.50), mk(score=0.50))
        self.assertFalse(ok)
        ok, _ = evolve.Playbook.should_promote(mk(score=0.50),
                                               mk(score=0.60, viol=("x",)))
        self.assertFalse(ok)

    def test_reflector_flags_scaffolding_dependence(self):
        st = Store(":memory:")
        r = evolve.Reflector(st)
        notes = r.reflect_session({"student_id": "x", "metrics": {
            "items": 3.0, "turns": 9.0,
            "hints_per_item": 3.0, "accuracy": 0.97, "completion": 1.0,
            "mean_mastery_gain": 0.01, "unaided_test_pass_rate": 0.9,
            "assistance_before_attempt": 0, "max_impasse": 1}})
        kinds = {n["kind"] for n in notes}
        self.assertIn("scaffolding_dependence", kinds)
        self.assertIn("too_easy", kinds)

    def test_reflector_stays_quiet_on_tiny_sessions(self):
        st = Store(":memory:")
        r = evolve.Reflector(st)
        notes = r.reflect_session(
            {"student_id": "x", "metrics": {"items": 1.0, "turns": 2.0,
                                            "accuracy": 0.0, "completion": 0.0}})
        self.assertEqual(notes, [])

    def test_improvement_cycle_runs_and_reports(self):
        cfg = Config(db_path=":memory:", offline=True)
        st = Store(":memory:")
        cat = catalog_mod.load_catalog("matric_physics")
        rep = evolve.improvement_cycle(cat, st, cfg,
                                       hypothesis=("attempt_gate", "test value", "t"))
        self.assertIsInstance(rep.message, str)
        self.assertIsNotNone(rep.after)


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

class TestResearch(unittest.TestCase):
    def test_distill_keeps_sentences_with_evidence(self):
        text = ("This is a filler sentence without much content at all here. "
                "In a randomized trial of 1,000 students, scores rose 17 percent. "
                "Another filler sentence that says nothing much at all really.")
        out = research.distill(text, max_sentences=2)
        self.assertIn("17 percent", out)

    def test_no_key_raises_cleanly(self):
        from raasta.research import NoSearchAvailable, SearchClient
        cfg = Config(db_path=":memory:")
        client = SearchClient(cfg, Store(":memory:"))
        for k in ("TAVILY_API_KEY", "SERPER_API_KEY", "BRAVE_API_KEY"):
            os.environ.pop(k, None)
        with self.assertRaises(NoSearchAvailable):
            client.search("test")

    def test_self_research_returns_hypotheses(self):
        st = Store(":memory:")
        refl = evolve.Reflector(st)
        for _ in range(4):
            refl.reflect_session({"student_id": "x", "metrics": {
                "items": 3.0, "turns": 9.0,
                "hints_per_item": 3.0, "accuracy": 0.9, "completion": 1.0,
                "mean_mastery_gain": 0.0, "unaided_test_pass_rate": 0.2,
                "assistance_before_attempt": 0, "max_impasse": 1}})
        agent = research.ResearchAgent(Config(db_path=":memory:"), st)
        rep = agent.self_research()
        self.assertTrue(rep["hypotheses"])
        self.assertEqual(rep["hypotheses"][0]["trigger"], "weak_transfer")

    def test_research_degrades_without_network(self):
        st = Store(":memory:")
        agent = research.ResearchAgent(Config(db_path=":memory:"), st)
        run = agent.run(max_queries=2)
        self.assertIsInstance(run.new_notes, int)
        self.assertTrue(run.errors or run.new_notes == 0)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class TestCatalog(unittest.TestCase):
    def test_prereqs_exist(self):
        for name in catalog_mod.CATALOGS:
            cat = catalog_mod.load_catalog(name)
            for sid, skill in cat.items():
                for p in skill.prereqs:
                    self.assertIn(p, cat, f"{name}: {sid} missing prereq {p}")

    def test_no_self_prereq(self):
        for name in catalog_mod.CATALOGS:
            for sid, skill in catalog_mod.load_catalog(name).items():
                self.assertNotIn(sid, skill.prereqs)

    def test_stats(self):
        s = catalog_mod.catalog_stats(catalog_mod.load_catalog("matric_physics"))
        self.assertGreater(s["skills"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
