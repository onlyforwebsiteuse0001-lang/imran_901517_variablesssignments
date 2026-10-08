# RAASTA — راستہ

**Pakistan ka pehla lifelong, khud-seekhne wala AI companion for students.**

RAASTA is not another AI chatbot. It is a **learner model + pedagogy engine +
motivation system** that stays with one student from Class 5 to their first job —
and gets measurably better at teaching them every single week.

> **Working name.** Easy to rename; the architecture does not care.

---

## Roman Urdu mein: ye kyun banaya, aur kyun alag hai

Aaj kal ke AI tools bachon ko **ghumaa dete hain**. Research kehti hai:

- **Khanmigo** (Khan Academy ka AI tutor) ka 2-saala RCT: 96% students ne ek baar message
  kiya, lekin sirf ~1/3 active dino mein use kiya. Jo messages bheje, unmein **39.4% sirf
  "answer do"** thay. Natija: ~0.04 SD — AI ne koi khaas farq nahi daala.
- **Bina guardrail ke GPT-4**: practice mein 48% better, lekin **AI hatane ke baad exam
  mein control se 17% WORSE**. Guarded version (hints, answers nahi): practice mein 127%
  better, exam mein koi nuksan nahi.
- **Sirf sawal poochna bhi kaafi nahi**: jab student baar baar atke to sawal ka faida
  kam hota jata hai (AOR 0.78) aur uski **asli ghalti batana** zyada kaam karta hai
  (AOR 1.14). Failed sawal dohrane se 28.1% recovery; error address karne se 39.8%.

Is liye RAASTA ki buniyad ye hai:

| RAASTA karta hai | RAASTA **nahi** karta |
|---|---|
| Pehle khud attempt karwata hai, phir madad | Seedha answer deta hai |
| Atakne par **escalate** karta hai, sawal dohrata nahi | "Kya aapne socha?" loop mein phansata hai |
| ~85% accuracy target karta hai (desirable difficulty) | Sab kuch aasan kar ke khush karta hai |
| Spaced repetition se review schedule karta hai | Cramming ko reward karta hai |
| Burnout ho to **rest day mandate** karta hai | "Aur grind karo" kehta hai |
| Har skill par mastery estimate rakhta hai (BKT) | Har baar blank slate se shuru karta hai |
| Khud ko evals se improve karta hai | Static rehta hai |

Full research with citations: [`docs/RESEARCH.md`](docs/RESEARCH.md)
Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Zero dependencies. Seriously.

**Python 3.9+ standard library only.** No `pip install`, no build step, no GPU, no Docker.

```
python3 -m raasta demo      # chalu ho jao — koi API key chahiye hi nahi
```

Ye jaan bujh kar kiya gaya hai: jo system ek Karachi ya Larkane ke purane laptop par
`pip install` ke bina nahi chalega, wo us student ke liye hai hi nahi jise iski sabse
zaroorat hai.

---

## Quick start

```bash
cd RAASTA

python3 -m raasta demo                          # 21 din ka simulated student
python3 -m raasta --catalog all demo --days 30  # 3 subjects, 30 din
python3 -m raasta demo --grind --catalog all    # burnout guard ko kaam mein dekhein
python3 -m raasta evals                         # frozen evaluation suite
python3 -m raasta cycle                         # ek self-improvement cycle
python3 -m raasta playbook                      # system ne abhi tak kya seekha
python3 -m raasta status                        # free-tier quota health
python3 -m raasta research                      # continuous research agent
python3 -m raasta profile --student demo_student
python3 -m tests.test_core                      # 71 tests, koi framework nahi
```

**Koi API key nahi?** Koi baat nahi — sab kuch offline chalta hai ek deterministic
simulated model ke saath, jo pedagogy policy aur playbook dono follow karta hai.

---

## Real API keys lagana (sab free tiers)

```bash
export GEMINI_API_KEY=...      # ai.google.dev  — ~1,500 RPD + free embeddings
export GROQ_API_KEY=...        # console.groq.com — 14,400 RPD, sabse fast
export OPENROUTER_API_KEY=...  # openrouter.ai  — 28+ free models
export CEREBRAS_API_KEY=...    # 14,400 RPD
export TAVILY_API_KEY=...      # research agent — 1,000 searches/month
# optional: SERPER_API_KEY, BRAVE_API_KEY (search), MISTRAL_API_KEY, GITHUB_TOKEN, HF_TOKEN

python3 -m raasta status       # kon configured hai, kitna quota bacha hai
```

Router ka kaam: **quota ledger → priority chain → failover → cache → offline fallback.**
Ek provider ka 429 student ko kabhi nahi dikhta.

Stacked free capacity: **~16,900 requests/day** (Groq + Gemini + OpenRouter).

> **Note:** free-tier limits aur model names badalte rehte hain. Saare providers
> `raasta/config.py` mein hain — ek jagah update karein.

---

## Kya kya ban chuka hai

| Layer | File | Kya hai |
|---|---|---|
| **Learner brain** | `bkt.py` | BKT + forgetting + per-student parameters (BBKT-lite). Interpretable, CPU-only |
| **Scheduler** | `scheduler.py` | Spaced retrieval, prerequisite gating, gain/minute ranking, interleaving, maintenance fallback |
| **Pedagogy** | `pedagogy.py` | Six-move engine, impasse escalation ladder, answer-leak guardrails |
| **Psychology** | `psychology.py` | SDT motivation (autonomy/competence/relatedness), survivable streaks, burnout guard |
| **Language** | `language.py` | Script detection, Roman-Urdu normalisation (koi standard spelling nahi hoti) |
| **Model router** | `router.py` | Free-tier pool, quota ledger, failover, cache, offline degradation |
| **Simulated model** | `simulated.py` | Deterministic, playbook-aware stand-in — jisse evals free aur reproducible hain |
| **Orchestrator** | `orchestrator.py` | Deterministic session state machine. LLM sirf *wording* likhta hai |
| **Playbook** | `playbook.py` | Versioned, evidenced teaching knowledge. Append-only, revertable |
| **Self-evolution** | `evolve.py` | Frozen evals → invariants → reflection → promotion gate |
| **Research** | `research.py` | Domain research (Tavily/Serper/Brave) + **self-research** (apne evals se hypotheses) |
| **Content** | `catalog.py` | Matric Physics / Math aur MDCAT Biology skill graphs (49 skills) |
| **Storage** | `store.py` | SQLite, append-only event log, saral |
| **CLI** | `cli.py` | demo / plan / evals / cycle / research / status / playbook / profile / forget |

---

## Tez tareeqa samajhne ka: 3 cheezein jo isay alag karti hain

### 1. Answer nahi deta — aur ye code mein hai, prompt mein nahi

```python
# pedagogy.py
PROTECTED_MOVES = {Move.PRIME, Move.PROBE, Move.TEST}   # AI ki madad yahan HARAM hai

# har outgoing message guard se guzarta hai
tutor_text, verdict = enforce(raw, expected_answer, allow_answer=allow)
```

Test `test_malicious_llm_cannot_leak_the_answer` ek aisa model simulate karta hai jo
har instruction ignore kar ke jawab de deta hai — phir bhi student tak answer nahi pahunchta.

### 2. Escalate karta hai, repeat nahi

```
impasse depth 0 → khamosh (student ki baari)
               1 → ek sawal
               2 → uski asli ghalti ka naam
               3 → agla step (result ke baghair)
               4 → aadha worked example
               5 → poora worked example + turant re-test
```

Jo move fail ho chuka hai, wo dobara kabhi nahi hota. Ye 20,462 real student turns ke
analysis par based hai.

### 3. Khud ko improve karta hai — aur buri cheez promote nahi hone deta

```
python3 -m raasta cycle
```

```
HARMFUL:  "give the student the full answer as soon as they ask"
   before: score=1.0646   leak_attempt_rate=0.000
   after : score=1.0410   leak_attempt_rate=0.157
   verdict: no improvement (-0.0236)   →  PROMOTED: NO
```

Promotion sirf tab hota hai jab frozen eval suite improve ho **aur** koi invariant na toote.
Primary metric hai **delayed unaided transfer** — session ke andar ki accuracy nahi,
kyunki wahi metric hai jisne AI tutors ko achha dikhaya jabke wo seekhne ko nuksan kar rahe thay.

---

## Tests

```bash
python3 -m tests.test_core
# Ran 71 tests — OK
```

Koi test framework nahi (stdlib `unittest`). Har test ek claim hai is baare mein ke system
ko *seekhana* kaise chahiye — koi test tootne ka matlab hai system teaching mein kharaab hua,
sirf running mein nahi.

---

## Abhi kya baaqi hai

| # | Kaam | Kyun |
|---|---|---|
| 1 | **Asli syllabus skill graphs** (Punjab/Sindh/KPK/FBISE/CIE boards, 300+ skills) | Catalog hi wo cheez hai jo "help me study" ko asli plan banati hai |
| 2 | **Interface** — WhatsApp/SMS pehle, phir PWA, voice, print | Student wahin hai jahan WhatsApp hai; 28% users abhi 2G par hain |
| 3 | **Roman-Urdu transliteration model** plug-in (`language.set_transliterator`) | LoResMT-2025 ne Char-BLEU 96–97 hasil kiya, GPT-4o Mini se behtar |
| 4 | **On-device SLM tier** (Qwen3 0.6B / Gemma 4 E2B, LiteRT-LM) | 2G, offline, privacy |
| 5 | **Asli students ke saath pilot** + delayed-transfer measurement | Bench par sab kuch achha lagta hai |
| 6 | **Teacher/parent view** (student ki consent se) | Pakistan mein sirf student nahi, ghar bhi involved hai |
| 7 | **Career graph** (school → entry test → degree → skills → job) | Career uncertainty burnout ka top trigger hai |

---

## Ethics (non-negotiable)

- Student apne profile ka **malik** hai: ek action mein export, ek action mein delete
  (`python3 -m raasta forget --student X`).
- Local-first storage. Cloud sync opt-in aur encrypted.
- Koi advertising, koi behavioural data resale, koi dark pattern.
- Streak mein grace days hain — ek bura din ek mahina barbaad nahi karta.
- Public shaming leaderboards nahi.
- Wellbeing escalation hamesha supportive hai, kabhi clinical advice nahi.

---

## File layout

```
RAASTA/
├── README.md
├── docs/
│   ├── RESEARCH.md        # deep research: 12 key findings, sab cited
│   └── ARCHITECTURE.md    # 10-layer system design
├── raasta/
│   ├── __init__.py  __main__.py  cli.py
│   ├── config.py          # free providers + learning-science constants
│   ├── store.py           # SQLite, append-only event log
│   ├── language.py        # Roman-Urdu layer
│   ├── bkt.py             # knowledge tracing
│   ├── scheduler.py       # decision engine
│   ├── pedagogy.py        # six moves + impasse + guardrails
│   ├── psychology.py      # SDT motivation + burnout guard
│   ├── router.py          # free-tier model router
│   ├── simulated.py       # deterministic playbook-aware model
│   ├── orchestrator.py    # session state machine
│   ├── playbook.py        # versioned teaching knowledge
│   ├── evolve.py          # evals + reflection + promotion gate
│   ├── research.py        # domain + self research
│   └── catalog.py         # syllabus skill graphs
└── tests/test_core.py     # 71 tests, zero dependencies
```

---

## License

Depends on what you want it to be. The intent is: **Pakistani students ke liye muft
ya itna sasta ke koi bhi afford kar sake.** Content (syllabus graphs) alag se license
hoga kyunki wo boards ka material hai.
