"""Command line entry point.

Runs with zero API keys and zero installed packages:

    python -m raasta demo              # simulate a student for 3 weeks
    python -m raasta plan              # today's session plan
    python -m raasta evals             # the frozen evaluation suite
    python -m raasta cycle             # one self-improvement cycle
    python -m raasta research          # continuous research (needs a search key)
    python -m raasta status            # free-tier quota + provider health
    python -m raasta playbook          # what the system has learned so far
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from . import catalog as catalog_mod
from .bkt import KnowledgeModel
from .config import Config
from .evolve import (EvalResult, Playbook, Reflector, SCENARIOS, improvement_cycle,
                     run_evals)
from .orchestrator import Orchestrator, StudentProfile
from .research import ResearchAgent
from .router import Router
from .store import Store


# ---------------------------------------------------------------------------
# Demo: a simulated student over several weeks
# ---------------------------------------------------------------------------

def _simulate_turns(rng: random.Random, skill_id: str, mastery: float,
                    mood: str) -> List[Tuple[str, Optional[bool]]]:
    """Generate a plausible student script for one item.

    The point of the simulator is not realism for its own sake — it is to exercise
    the policy under the four failure modes the research identified: answer-seeking,
    going quiet, careless speed, and honest struggle.
    """
    p_correct = 0.18 + 0.68 * mastery
    if mood == "tired":
        p_correct -= 0.10
    elif mood == "focused":
        p_correct += 0.08

    style = rng.choice(["seeker", "quiet", "honest", "honest", "honest"])
    first = rng.random() < p_correct

    if style == "seeker":
        script = [("answer bata do", None), ("bas short answer chahiye", None)]
        if rng.random() < 0.55:
            script.append(("theek hai khud try karta hoon", None))
    elif style == "quiet":
        script = [("samajh nahi aaya", None), ("mujhe kuch nahi aata is mein", None)]
    else:
        script = [("pehle main try karta hoon", None)]

    script.append(("mujhe lagta hai answer 6 hai", first))
    if not first:
        # struggle, then possibly recover after help
        script.append(("acha, ek step phir se karta hoon", None))
        recovered = rng.random() < (p_correct + 0.30)
        script.append(("ab samajh aaya", recovered))
        script.append(("theek hai", recovered))
    else:
        script.append(("ek aur try karta hoon", rng.random() < (p_correct + 0.12)))
        script.append(("ho gaya", True))
    return script


def cmd_demo(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    cfg.offline = args.offline or cfg.offline
    if args.db:
        cfg.db_path = args.db
    if os.path.exists(cfg.db_path) and args.fresh:
        os.remove(cfg.db_path)
    store = Store(cfg.db_path)
    cat = catalog_mod.load_catalog(args.catalog)

    profile = StudentProfile(id=args.student, name=args.name,
                             language="roman_urdu",
                             board="BISE Karachi", stage="Matric (Class 10)",
                             device_tier="low", network_tier="3g",
                             daily_minutes=args.minutes)
    orch = Orchestrator(profile, cat, store=store, cfg=cfg)
    orch.save()

    rng = random.Random(args.seed)
    minutes = 100 if args.grind else args.minutes
    profile.daily_minutes = minutes
    print(f"\nRAASTA demo — {profile.name} ({args.catalog}), "
          f"{args.days} days, {minutes} min/day"
          + ("  [GRIND MODE: exercising the burnout guard]" if args.grind else ""))
    print("=" * 78)

    start = time.time() - args.days * 86400.0
    day = 0
    rest_days = 0
    while day < args.days:
        now = start + day * 86400.0 + (2 if args.grind else 19) * 3600  # 2am cramming
        if not args.grind and day % 7 == 6:          # one real day off a week
            print(f"day {day+1:3d}  — off (Friday)")
            day += 1
            continue
        if args.grind:
            mood = "tired" if day > args.days // 3 else "normal"
        else:
            mood = rng.choice(["focused", "normal", "normal", "tired"])
        script: Dict[str, List[Tuple[str, Optional[bool]]]] = {}

        plan, wb = orch.plan_session(now)              # type: ignore[misc]
        if plan.rest_day:
            rest_days += 1
        for item in plan.items:
            script[item.skill_id] = _simulate_turns(
                rng, item.skill_id, orch.km.mastery(item.skill_id), mood)

        res = orch.run_session(script=script, now=now,
                               budget_minutes=minutes)
        m = res.metrics

        if day % max(1, args.days // 12) == 0 or day == args.days - 1 or plan.rest_day:
            s = orch.km.summary()
            flag = "  [REST DAY — burnout guard]" if plan.rest_day else ""
            acc = m.get("accuracy", 0)
            acc_s = f"{acc:.2f}" if m.get("items", 0) else "  — "
            print(f"day {day+1:3d}  items {int(m.get('items',0)):2d}  "
                  f"acc {acc_s}  "
                  f"mastery {s['mean_mastery']:.3f}  "
                  f"mastered {int(s['mastered']):2d}/{int(s['skills']):2d}  "
                  f"burnout {wb.risk:.2f}{flag}")
            if res.streak_msg:
                print(f"         ↳ {res.streak_msg}")
        day += 1

    s = orch.km.summary()
    print("=" * 78)
    print(f"skills tracked   : {int(s['skills'])}")
    print(f"attempts         : {int(s['attempts'])}")
    print(f"mean mastery     : {s['mean_mastery']:.3f}")
    print(f"mastered (>=.85) : {int(s['mastered'])}")
    print(f"overall accuracy : {s['overall_accuracy']:.3f}")
    print(f"rest days taken  : {rest_days}")

    # reflections from the last sessions
    refl = Reflector(store)
    notes: List[Dict[str, str]] = []
    for ev in store.events(profile.id, kind="session", limit=5):
        notes.extend(refl.reflect_session(ev["payload"]))
    if notes:
        print("\nlatest reflections:")
        for n in notes[:5]:
            print(f"  · [{n['kind']}] {n['text'][:110]}")

    print("\nweakest skills (where we'd focus next):")
    for sid, p in orch.km.weakest(5):
        title = cat[sid].title if sid in cat else sid
        print(f"  · {sid:28s} {p:.2f}  {title[:44]}")
    store.close()
    return 0


# ---------------------------------------------------------------------------
# Other commands
# ---------------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    if args.db:
        cfg.db_path = args.db
    store = Store(cfg.db_path)
    cat = catalog_mod.load_catalog(args.catalog)
    row = store.get_student(args.student)
    profile = StudentProfile.from_dict(row["profile"]) if row else StudentProfile(args.student)
    orch = Orchestrator(profile, cat, store=store, cfg=cfg)
    plan, wb = orch.plan_session()      # type: ignore[misc]
    print(f"\nwellbeing risk {wb.risk:.2f}  signals={wb.signals}  actions={wb.actions}")
    print(plan)
    print()
    store.close()
    return 0


def cmd_evals(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    cfg.offline = True
    store = Store(args.db or ":memory:")
    cat = catalog_mod.load_catalog(args.catalog)
    res = run_evals(cat, store=store, cfg=cfg, db_path=store.path)
    print(f"\n{res}")
    print("-" * 78)
    for k, v in sorted(res.metrics.items()):
        print(f"  {k:30s} {v:.4f}")
    if res.violations:
        print("\nINVARIANT VIOLATIONS:")
        for v in res.violations[:25]:
            print(f"  ✗ {v}")
    else:
        print("\n✓ all invariants held")
    if args.verbose:
        print("\nper scenario:")
        for sid, d in res.per_scenario.items():
            print(f"  {sid:18s} score-ish {d['metrics']}")
    store.close()
    return 0 if res.passed else 1


def cmd_cycle(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    cfg.offline = True
    store = Store(args.db or ":memory:")
    cat = catalog_mod.load_catalog(args.catalog)
    Playbook(store).seed()

    agent = ResearchAgent(cfg, store)
    selfrep = agent.self_research()
    print("\nself-research:")
    print(f"  eval runs      : {selfrep['eval_runs']}")
    print(f"  latest score   : {selfrep['latest_score']}")
    print(f"  score trend    : {selfrep['score_trend']:+.4f}")
    print(f"  reflections    : {selfrep['reflection_kinds']}")

    hyp = None
    if selfrep["hypotheses"]:
        h = selfrep["hypotheses"][0]
        hyp = (h["key"], h["value"], h["evidence"])
        print(f"\ntesting hypothesis → [{h['key']}] (trigger: {h['trigger']}, "
              f"seen {h['count']}x)\n  {h['value']}")

    rep = improvement_cycle(cat, store, cfg, hypothesis=hyp)
    print(f"\nbefore : {rep.before}")
    print(f"after  : {rep.after}")
    print(f"verdict: {rep.message}")
    print(f"promoted: {rep.promoted}")
    store.close()
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    store = Store(args.db or cfg.db_path)
    agent = ResearchAgent(cfg, store)
    print("\nsearch providers:")
    for s in agent.status():
        print(f"  {s['provider']:10s} configured={s['configured']}  "
              f"remaining={s['remaining_this_month']}/{s['monthly_free']}")
    if args.digest:
        print("\n" + agent.digest(topic=args.topic))
        store.close()
        return 0
    run = agent.run(max_queries=args.queries)
    print(f"\n{run}")
    for e in run.errors[:5]:
        print(f"  ! {e[:140]}")
    if run.new_notes:
        print("\n" + agent.digest(limit=8)[:2500])
    store.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    store = Store(args.db or cfg.db_path)
    router = Router(cfg, store)
    print("\nLLM providers (free tiers):")
    print(f"  {'provider':<12} {'cfg':<5} {'tier':<9} {'used':>7} {'limit':>7} {'model'}")
    for s in router.status():
        print(f"  {s['provider']:<12} {str(s['configured']):<5} {s['tier']:<9} "
              f"{s['used_today']:>7} {s['limit_today']:>7} {s['model']}")
    print("\nSearch providers:")
    for s in ResearchAgent(cfg, store).status():
        print(f"  {s['provider']:<12} configured={s['configured']} "
              f"remaining={s['remaining_this_month']}/{s['monthly_free']}")
    print(f"\ndatabase: {store.path}")
    print(f"students: {len(store.list_students())}")
    store.close()
    return 0


def cmd_playbook(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    store = Store(args.db or cfg.db_path)
    pb = Playbook(store)
    rows = pb.entries()
    print(f"\nplaybook scope='{pb.scope}' version={pb.version()} entries={len(rows)}\n")
    for r in rows:
        print(f"[{r['key']}] v{r['version']} score={r['score']:.2f}")
        print(f"    {r['value']}")
        if r["evidence"]:
            print(f"    evidence: {r['evidence'][:120]}")
    store.close()
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    store = Store(args.db or cfg.db_path)
    row = store.get_student(args.student)
    if not row:
        print(f"no profile for {args.student}")
        return 1
    km = KnowledgeModel(args.student, cfg.learning,
                        store.load_skills(args.student))
    print(json.dumps(row["profile"], indent=2, ensure_ascii=False))
    print("\nknowledge summary:")
    for k, v in km.summary().items():
        print(f"  {k:20s} {v}")
    print("\nskills:")
    for sid, st in sorted(km.skills.items(), key=lambda kv: kv[1].p_mastery):
        print(f"  {sid:30s} p={st.p_mastery:.2f}  n={st.attempts:2d}  "
              f"acc={st.accuracy:.2f}  T={st.p_transit:.2f}  "
              f"interval={st.interval_days:.1f}d  due={km.due(sid)}")
    store.close()
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    store = Store(args.db or Config.from_env().db_path)
    store.forget_student(args.student)
    print(f"all data for {args.student} deleted (their right, not ours to keep)")
    store.close()
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # `common` is attached to the root parser AND to every subparser, so both
    # `raasta --db x demo` and `raasta demo --db x` work. The subparser value
    # wins because it is parsed last.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=None, help="sqlite path (default: raasta.db)")
    common.add_argument("--catalog", default=catalog_mod.DEFAULT_CATALOG,
                        choices=list(catalog_mod.CATALOGS))

    p = argparse.ArgumentParser(
        prog="raasta", description="RAASTA — a lifelong AI companion for students",
        parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=lambda **kw:
                           argparse.ArgumentParser(**{**kw, "parents": [common]}))

    d = sub.add_parser("demo", help="simulate a student over N days")
    d.add_argument("--days", type=int, default=21)
    d.add_argument("--minutes", type=int, default=25)
    d.add_argument("--student", default="demo_student")
    d.add_argument("--name", default="Imran")
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--fresh", action="store_true")
    d.add_argument("--grind", action="store_true",
                   help="simulate an over-studying student to exercise the "
                        "burnout guard")
    d.add_argument("--offline", action="store_true")
    d.set_defaults(func=cmd_demo)

    pl = sub.add_parser("plan", help="print today's session plan")
    pl.add_argument("--student", default="demo_student")
    pl.set_defaults(func=cmd_plan)

    e = sub.add_parser("evals", help="run the frozen evaluation suite")
    e.add_argument("--verbose", action="store_true")
    e.set_defaults(func=cmd_evals)

    c = sub.add_parser("cycle", help="run one self-improvement cycle")
    c.set_defaults(func=cmd_cycle)

    r = sub.add_parser("research", help="run the continuous research agent")
    r.add_argument("--queries", type=int, default=6)
    r.add_argument("--digest", action="store_true")
    r.add_argument("--topic", default=None)
    r.set_defaults(func=cmd_research)

    s = sub.add_parser("status", help="provider + quota health")
    s.set_defaults(func=cmd_status)

    pb = sub.add_parser("playbook", help="show accumulated teaching knowledge")
    pb.set_defaults(func=cmd_playbook)

    pr = sub.add_parser("profile", help="show a student profile and mastery")
    pr.add_argument("--student", default="demo_student")
    pr.set_defaults(func=cmd_profile)

    f = sub.add_parser("forget", help="delete all data for a student")
    f.add_argument("--student", required=True)
    f.set_defaults(func=cmd_forget)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":          # pragma: no cover
    sys.exit(main())
