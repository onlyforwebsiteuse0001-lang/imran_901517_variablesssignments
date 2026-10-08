# RAASTA — System Architecture

> **RAASTA** (راستہ) — *har student ka apna raasta.* A lifelong, self-improving AI companion for students.
> Working name; easily renamed. Zero third-party dependencies (Python stdlib only).

---

## 1. Ten layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L9  INTERFACES      Web PWA · WhatsApp · SMS/USSD · Voice · Print         │
├──────────────────────────────────────────────────────────────────────────┤
│ L8  SELF-EVOLUTION  Evals → Reflector → Playbook (ACE) → A/B → Promote    │
│                     + Nightly consolidation ("sleep-time compute")        │
├──────────────────────────────────────────────────────────────────────────┤
│ L7  RESEARCH AGENT  Continuous web research: pedagogy · careers · cohort  │
│                     + self-research (what is failing, for whom)           │
├──────────────────────────────────────────────────────────────────────────┤
│ L6  AGENTS          Tutor · Diagnostician · Planner · Motivator ·         │
│                     Evaluator · Guardian · Curator · Researcher           │
├──────────────────────────────────────────────────────────────────────────┤
│ L5  MODEL ROUTER    Free-tier pool · quota ledger · failover · cache ·    │
│                     difficulty routing · on-device SLM · offline stub     │
├──────────────────────────────────────────────────────────────────────────┤
│ L4  DECISION ENGINE What to study, when, how much, in what order          │
│                     (spaced retrieval + interleaving + load caps)         │
├──────────────────────────────────────────────────────────────────────────┤
│ L3  PSYCHOLOGY      Motivation (SDT) · Wellbeing/burnout guard · Nudges   │
├──────────────────────────────────────────────────────────────────────────┤
│ L2  PEDAGOGY        Six-move engine · Impasse ladder · Answer guardrails  │
├──────────────────────────────────────────────────────────────────────────┤
│ L1  LEARNER BRAIN   BKT mastery · forgetting · cognitive & motivation     │
│                     profile · lifespan context · immutable event log      │
├──────────────────────────────────────────────────────────────────────────┤
│ L0  FOUNDATION      SQLite store · Roman-Urdu language layer · config     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. L1 — The Learner Brain (the asset nobody else has)

Everything else is replaceable. **This is the moat.** One row per student, growing for years, and it is
the student's property — exportable, deletable, portable.

```python
StudentProfile
├── identity       : id, name, preferred_name, language, script, voice_enabled
├── stage          : board (BISE/CIE/AQA), class, stream, target exams + dates
├── knowledge      : {skill_id -> SkillState}          # BKT, see below
├── cognition      : reading_level, working_memory_estimate, preferred_modality,
│                    pace (items/min), error_profile (careless vs conceptual)
├── motivation     : autonomy_score, competence_score, relatedness_score,
│                    self_efficacy, goal_orientation, identity_statement
├── wellbeing      : burnout_risk, sleep_debt, load_today, rest_days_used
├── context        : device_tier, network_tier, data_budget, study_slots,
│                    family_constraints, safe_hours
├── episodes       : append-only log of every interaction (immutable)
└── reflections    : what the system learned about teaching this student
```

### SkillState (BKT + forgetting + per-student parameters)

| Field | Meaning |
|---|---|
| `p_mastery` | P(student has mastered this skill right now) |
| `p_transit` | Learning rate — **fitted per student online** (BBKT-lite) |
| `p_slip` | P(mistake despite mastery) |
| `p_guess` | P(correct without mastery) — derived from number of MCQ options |
| `last_seen` | Used by the forgetting decay |
| `interval`, `reps` | Spaced-repetition schedulers |

Why BKT and not a deep KT model: a teacher or parent can read `p_mastery = 0.62`, it fits on a CPU with
zero training pipeline, it works from the first five responses, and per-student parameter posteriors are
what close equity gaps between slow and fast learners
([BBKT](https://www.emergentmind.com/topics/bayesian-knowledge-tracing-bkt)).

---

## 3. L2 — Pedagogy: the six-move engine

```
PRIME ──► PROBE ──► POINT ──► ATTACH ──► STRENGTHEN ──► TEST
  ✗AI       ✗AI       ✓AI       ✓AI         ✓AI          ✗AI
```

`PRIME` (recall prior knowledge unaided) and `TEST` (unaided retrieval check) are **protected**. AI may
only operate in the middle four moves. Diagnostic from research: *if letting AI in makes the task feel
effortless, it is in the wrong place.*

### Impasse ladder (never repeat a failed move)

| Impasse depth | Tutor move | Rationale |
|---|---|---|
| 0 | Ask student to attempt / show reasoning | Protect productive struggle |
| 1 | Probing question toward the concept | Cheapest, most autonomy-preserving |
| 2 | **Name and address the specific error** | Questioning decays (AOR 0.78) while error-directed feedback grows (AOR 1.14) |
| 3 | Concrete hint + partial worked step | Recovery 39.8% vs 28.1% for repeating a question |
| 4+ | Full worked example, then immediately re-test | End the impasse; never let a student quit in frustration |

Impasse **type** is tracked separately (conceptual error / uncertainty / help-seeking) because the type
predicts which move will land.

### Answer guardrails

- **Attempt-first gate**: no assistance until an attempt exists or the student names a specific confusion.
- **Leak classifier**: pattern + structural checks on every outgoing tutor message (final-answer
  patterns, full-solution dumps, "the answer is X"). Offending messages are blocked and rewritten.
- **Exam mode**: a hard switch that locks all assistance and logs integrity signals.

---

## 4. L3 — Psychology engine

Grounded in Self-Determination Theory, because gamification alone raises *extrinsic* motivation more
than intrinsic (g = 0.713 vs 0.638) and decays when basic needs are unmet.

| Need | Mechanism (concrete) |
|---|---|
| **Autonomy** | Always offer a choice of 2–3 next activities; student sets the goal; system never commands without a reason |
| **Competence** | Difficulty calibrated to ~85% success; feedback praises *strategy* ("you split the fraction first") not ability ("you're smart"); visible mastery bars |
| **Relatedness** | Study circles, accountability partners, cooperative goals; **no public shaming leaderboards** |

Extras that are deliberately *not* dark patterns:
- **Streak with 2 grace days/month** and a "never miss twice" rule — not a hostage-taking infinite streak.
- **Implementation intentions**: "I will study *Physics: Motion* at *7pm* in *my room*" — students commit
  to a specific time/place, which is the one planning mechanism with real evidence behind it.
- **Rest is a feature**: the wellbeing guard can *mandate* a rest day, and the system will not apologise.

### Wellbeing guard (burnout risk)

Inputs: session length, late-night activity (after 1am), consecutive days without rest, declining
accuracy, falling session frequency after a high-intensity period, self-reported stress, exam proximity.
Outputs: reduce load → insert lighter review-only day → mandate rest → escalate to a supportive
(non-clinical) check-in.

Pakistani medical students describe academic pressure, family expectation, financial guilt and career
uncertainty as their main burnout triggers
([BMC Med Educ 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12374339/)) — so this module is not
optional decoration.

---

## 5. L4 — Decision engine (scheduler)

Per day, given a time budget:

1. **Overdue reviews first** (spaced-retrieval due items, oldest overdue first, capped to avoid review doom).
2. **Highest expected-gain weaknesses**: rank by `Δmastery / estimated_minutes`, where
   `Δmastery ≈ p_transit × (1 − p_mastery)`, and gate on prerequisite mastery.
3. **New content last**, limited by the remaining cognitive-load budget.
4. **Interleave** subjects and problem types inside the session.

Spacing: expanding intervals, `interval = base × ease^reps`, adjusted by observed accuracy toward the
~85% target; `ease` adapts per student. Research shows expanding vs uniform makes no significant
difference (g = 0.034), so we use the simpler expanding rule.

---

## 6. L5 — Model router (surviving entirely on free tiers)

```
request(task, difficulty)
   │
   ├─ cache hit? ───────────────────────────────► return
   ├─ offline / no keys? ──► OfflineStub (deterministic) or on-device SLM
   └─ provider chain (config-driven priority):
        Groq → Gemini → OpenRouter → Cerebras → Mistral → GitHub → HF → Cloudflare
        each guarded by: quota ledger (SQLite, per-day), cooldown after 429,
        timeout, and automatic failover to the next provider
```

Difficulty routing: routine turns (hints, encouragement, formatting) → fast cheap model;
diagnosis and planning → strongest available free model.

With Groq (14,400 RPD) + Gemini (1,500 RPD) + OpenRouter (1,000 RPD) the ceiling is roughly
**16,900 free requests/day** — enough for a serious product if caching and difficulty routing are real.

---

## 7. L6 — Agents

| Agent | Job |
|---|---|
| **Diagnostician** | Decide *what* the student's error actually is (conceptual / procedural / careless / language) |
| **Tutor** | Produce the next move under the six-move + impasse + guardrail policy |
| **Planner** | Own the multi-week plan and today's session |
| **Motivator** | SDT-grounded opener, commitment, celebration, re-engagement |
| **Guardian** | Safety, privacy, wellbeing, integrity, answer-leak veto |
| **Evaluator** | Score every session against frozen evals (delayed/unaided/transfer, not in-session correctness) |
| **Curator** | Merge reflections into the versioned playbook (incremental, never a full rewrite) |
| **Researcher** | Continuous web research; distil into the knowledge base |

The **Orchestrator** is deliberately a deterministic state machine, not a free-roaming agent loop:
students need reliability, and every stochastic hop is an opportunity to lose them.

---

## 8. L7/L8 — Self-research and self-improvement

```
        ┌───────────────────────────────────────────────────────┐
        │  session → events → Evaluator (frozen eval suite)      │
        │            ↓                                          │
        │        Reflector  (what failed, for whom, why)         │
        │            ↓                                          │
        │        Curator    (playbook delta: add/merge/deprecate)│
        │            ↓                                          │
        │     shadow A/B → promote only if eval improves         │
        └───────────────────────────────────────────────────────┘
                     ↑                            ↓
        Researcher (web: pedagogy, careers,      Nightly consolidation
        syllabus changes, cohort outcomes)       ("sleep-time compute")
```

Rules that keep this honest:
1. **Evals ship before the loop is trusted.** No promotion without a measured delta.
2. **Playbook is versioned and diffable.** Every entry carries its evidence and its score.
3. **Deprecation is a first-class operation**, otherwise the playbook rots.
4. **The primary metric is delayed unaided transfer**, not in-session correctness — in-session correctness
   is exactly the metric that made AI tutors look good while harming learning.

---

## 9. L0/L9 — Foundation and interfaces

**Storage**: SQLite (stdlib), append-only event log as the source of truth; all other state is derived and
therefore rebuildable. Designed to survive 2G: tiny sync payloads, last-write-wins with vector clocks
on the few mutable records.

**Language layer**: script detection (Arabic/Urdu vs Latin vs Devanagari), Roman-Urdu normalization of
common spelling variants, optional transliteration, and a strict "answer in the student's language"
contract. Roman Urdu has no orthographic standard, so normalization happens *before* reasoning.

**Interfaces** (in priority order for Pakistan):
1. **WhatsApp / SMS-first** — where the students already are; works on 2G and feature phones.
2. **PWA** — installable, offline-capable, <200 KB initial payload.
3. **Voice** — for low-literacy and low-vision users; Urdu/English STT + TTS.
4. **Print** — auto-generated offline worksheets for when there is no connectivity at all.

---

## 10. Data ethics (non-negotiable)

- Student owns their profile: export and delete in one action.
- Local-first; cloud sync is opt-in and encrypted.
- No advertising, no behavioural resale, no dark patterns.
- Minimal collection: a child's data is not a growth metric.
- Guardian/parent views require the student's consent above a defined age.
- Every wellbeing escalation is supportive, never clinical advice.

---

## 11. Build order (what exists in this repo right now)

| Phase | Status | Contents |
|---|---|---|
| **R** Research | ✅ done | `docs/RESEARCH.md` |
| **A** Architecture | ✅ done | `docs/ARCHITECTURE.md` |
| **1** Core brain | ✅ done | BKT + forgetting + per-student params, scheduler, profile, event log |
| **2** Pedagogy | ✅ done | six-move engine, impasse ladder, answer guardrails |
| **3** Psychology | ✅ done | SDT motivation, wellbeing/burnout guard |
| **4** Router + memory | ✅ done | free-tier router with quota ledger, SQLite store |
| **5** Self-evolution | ✅ done | evals, reflector, versioned playbook |
| **6** Agents + CLI | ✅ done | orchestrator + a runnable end-to-end simulation (no API key needed) |
| **7** Interfaces | ⏳ next | FastAPI/WhatsApp adapter, PWA |
| **8** Content | ⏳ next | Pakistan syllabus skill graphs (Matric/Inter/MDCAT/ECAT) |
| **9** Evals at scale | ⏳ next | real-student pilot, delayed transfer measurement |
