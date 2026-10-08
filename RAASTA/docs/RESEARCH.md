# RAASTA — Deep Research Report
### "Pakistan ka pehla lifelong, khud-seekhne wala AI companion for students"

**Date:** 8 October 2026
**Research scope:** student problems (global + Pakistan), failures of today's AI tools, learning science,
motivation psychology, knowledge tracing, self-improving agents, free API landscape, on-device constraints.

---

## 0. Roman Urdu mein poora khulasa (read this first)

Bhai, research ke baad ek baat bilkul saaf hai: **masla AI ka nahi hai, masla engagement aur design ka hai.**

1. **Bachay AI use hi nahi karte (ya galat karte hain).** Khanmigo (Khan Academy ka AI tutor) ka 2-saala
   RCT: 96% students ne ek baar to message kiya, lekin students sirf ~1/3 active dino mein use kiya.
   Jo messages bheje unmein **39.4% sirf "answer do"** thay, 12.6% low-effort, 9.3% off-task.
   Natija: sirf 0.04 SD improvement — AI ne kuch khaas farq nahi daala. [1](https://www.chalkbeat.org/2026/08/25/ai-tutoring-students-khanmigo-khan-academy-engagement-study/) [5](https://www.winssolutions.org/khanmigo-ai-tutoring-two-year-trial/)

2. **Lekin invitation ka style badla to participation 45% se 82% ho gaya.** Matlab: *kaise bulate ho* ye
   model se zyada matter karta hai. [5](https://www.winssolutions.org/khanmigo-ai-tutoring-two-year-trial/)

3. **Jo AI seedha answer deta hai wo nuksan karta hai.** Turkey ke ~1000 high-school students par experiment:
   bina guardrail ke GPT-4 se practice mein 48% better performance, lekin **AI hatane ke baad unaided exam
   mein control se 17% WORSE**. Guarded version (hints, answers nahi) se practice mein 127% better aur
   exam mein koi nuksan nahi. [5](https://www.psypost.org/unrestricted-generative-ai-harms-high-school-math-learning-by-acting-as-a-crutch/) [3](https://knowledge.wharton.upenn.edu/article/without-guardrails-generative-ai-can-harm-education/)

4. **Sirf sawal poochna bhi kaafi nahi.** 1,260 asli (authentic) sessions ke analysis se pata chala: jab student baar baar
   atak jaye (impasse gehra ho), to sawal poochna kam faida deta hai (AOR 0.78) aur **usi ghalti ko seedha
   address karna zyada faida deta hai** (AOR 1.14). Ek failed sawal ko dohrana se 28.1% recovery, jabke
   error address karne se 39.8%. [1](https://arxiv.org/html/2609.38346v1)

5. **Spacing + retrieval practice sabse solid cheez hai** jo humare paas hai (g = 0.74 vs massed practice).
   Expanding vs uniform schedule mein koi farq nahi (g = 0.034) — to simple schedule chalo.
   Rule of thumb: interval ≈ 10–20% of the time you want to retain it; accuracy target ~85%.
   [3](http://www.lscp.net/persons/ramus/docs/EPR20.pdf) [2](https://thelearnerlab.com/science-spaced-repetition-memory-retention/)

6. **Gamification kaam karti hai lekin nuksan bhi karti hai.** Meta-analysis: extrinsic motivation par asar
   (g = 0.713) intrinsic se zyada (g = 0.638). Matlab points/badges se bacha to aa jata hai lekin andar se
   seekhne ka shauk nahi badhta — jab tak **autonomy, competence, relatedness** (Self-Determination Theory)
   support na ho. [1](https://onlinelibrary.wiley.com/doi/10.1002/pits.70056)

7. **Sirf "nudges" (reminder messages) se kaam nahi chalta.** Nudge Units ke 126 trials ka average asar sirf
   **1.4 percentage points** (academic journals mein 8.7 pp — publication bias). Study-time reminders par to
   precise null results mile hain. [4](https://eml.berkeley.edu/~sdellavi/wp/NudgeToScale2020-03-20.pdf) [5](https://www.aeaweb.org/conference/2019/preliminary/paper/4aNaEzZ3)

8. **Pakistan ka ground reality:** enrolment to theek ho raha hai (6–16 mein 92.2%), lekin **Class 3 ke sirf
   7% bachay Urdu/Sindhi mein ek simple story padh sakte hain, aur sirf 8% division kar sakte hain.**
   Class 5 tak bhi aadhe bachay Class 2 ka text nahi padh sakte. Government + private dono mein yahi haal hai.
   Education spending 0.8% of GDP. [2](https://pakobserver.net/counting-children-measuring-learning/)
   Learning poverty 77%. [4](https://iol.co.za/the-star/news/2025-02-25-education-emergency-pakistan-grapples-with-severe-learning-poverty/)

9. **Device/internet:** Economic Survey ke mutabiq smartphone usage 71.6% [1](https://www.phoneworld.com.pk/pakistan-smartphone-usage-71-percent-economic-survey-2026/),
   lekin doosri report kehti hai **sirf 31% population ke paas smartphone hai** (~73M users) [4](https://www.phoneworld.com.pk/new-report-exposes-pakistans-low-smartphone-penetration-amid-ptas-200m-mobile-subscriber-celebrations/).
   HIES 2024-25: 70% households mein internet, individuals 57%, **aur mobile ownership mein gender gap 69% men / 31% women.**
   [5](https://www.dawn.com/news/1964568) Data sasta hai ($0.12/GB) [3](https://www.samenacouncil.org/samena_daily_news?news=109030), lekin **28% users abhi bhi 2G par hain** [1](https://www.phoneworld.com.pk/pakistan-smartphone-usage-71-percent-economic-survey-2026/).
   → **Design nateeja: offline-first, chhota payload, low-end Android, Roman Urdu, audio-first.**

10. **Burnout haqeeqi hai.** Pakistani medical students par study: academic pressure, family ki umeedein,
    financial guilt, career uncertainty, aur koi support nahi — "I'm carrying my whole family's hopes."
    [1](https://pmc.ncbi.nlm.nih.gov/articles/PMC12374339/)
    → **System ko "aur grind kar" nahi kehna chahiye; uske paas rest-day mandate hona chahiye.**

11. **Free APIs se poora system chal sakta hai.** Groq (14,400 RPD), Gemini free tier (1,500 RPD + free embeddings),
    OpenRouter (28+ free models, 50–1,000 RPD), Cerebras (14,400 RPD), Mistral, GitHub Models, HuggingFace.
    Sirf in teen ka stack: **~16,900 free requests/day** — ek serious product ke liye kaafi.
    [3](https://klymentiev.com/blog/best-free-llm-2026) [1](https://tokenmix.ai/blog/free-llm-api)
    Search ke liye: Tavily 1,000/mo, Serper 2,500, Jina Reader 1M tokens/mo. [1](https://parallel.ai/articles/best-free-web-search-api)

12. **Khud-seekhna (self-improvement) ab practical hai** — weights retrain kiye bina. ACE framework ne
    benchmark performance +10.6% improve ki with 86.9% lower adaptation latency; Reflexion ne HumanEval
    80% → 91%. Mechanism: **attempt → evaluate → reflect → playbook update → retry.**
    [2](https://upsolve.ai/blog/self-improving-agent) [3](https://stackviv.ai/blog/reflection-ai-agents-self-improvement)

**Ek line ka nateeja:** Humein ek aur chatbot nahi banana. Humein ek **AI study-mate** banana hai jo
(1) answer na de kar *seekhaye*, (2) student ke hisaab se schedule banaye, (3) psychology se engagement
banaye rakhe — na ke sirf notification bhej kar, (4) khud apne aap ko evals se improve karta rahe,
(5) 2G/Roman-Urdu/low-end phone par bhi chale.

---

## 1. Problem landscape

### 1.1 Student-side problems (what Pakistani students actually face)

| # | Problem | Evidence | System implication |
|---|---|---|---|
| P1 | **Foundational skills missing.** Class 3 ke sirf 7% story padh sakte hain, 8% division kar sakte hain [2](https://pakobserver.net/counting-children-measuring-learning/) | Placement/diagnostic must start *below* grade level, shame-free |
| P2 | **Rote learning culture.** Teacher-centred classes, syllabus khatam karna hi maqsad [5](https://blogs.lse.ac.uk/internationaldevelopment/2025/05/16/grassroots-responses-to-pakistans-education-crisis/) | Build conceptual models + "explain why", not just recall |
| P3 | **Extreme student:teacher ratio** (~44:1) aur tuition/academy par dependence [5](https://profit.pakistantoday.com.pk/2023/03/16/despite-global-downturn-ed-tech-sector-sees-hope-with-maqsads-2-8-million-round/) | 1:1 tutoring at zero marginal cost is the whole point |
| P4 | **Language barrier.** Ghar Roman Urdu/Urdu/Sindhi/Pashto, school English medium | Bilingual by default; Roman Urdu is a first-class input |
| P5 | **Burnout, family pressure, financial guilt** [1](https://pmc.ncbi.nlm.nih.gov/articles/PMC12374339/) | Wellbeing guard, rest days, no toxic streaks |
| P6 | **No career clarity.** Uncertainty about future prospects is a top burnout trigger [1](https://pmc.ncbi.nlm.nih.gov/articles/PMC12374339/) | Long-horizon career graph: school → entry test → degree → skills → job |
| P7 | **Device/network fragility.** 28% on 2G, disputed smartphone penetration 31–71% [1](https://www.phoneworld.com.pk/pakistan-smartphone-usage-71-percent-economic-survey-2026/) [4](https://www.phoneworld.com.pk/new-report-exposes-pakistans-low-smartphone-penetration-amid-ptas-200m-mobile-subscriber-celebrations/) | Offline-first, tiny payloads, on-device SLM fallback |
| P8 | **Gender access gap.** Mobile ownership 69% men / 31% women [5](https://www.dawn.com/news/1964568) | Low-data mode, audio-first, no camera requirement, privacy-first |
| P9 | **Fragmented systems.** Matric/Inter (BISE boards), O/A Levels, MDCAT/ECAT, CSS, university — alag alag silos | One longitudinal profile spanning every stage |

### 1.2 Why today's AI tools fail students (the "ghumaa dete hain" problem)

The user's exact complaint — *"aaj kal jo AI hain wo bachhon ko ghumaa dete hain"* — is precisely what the
research calls the **learning–performance paradox**:

> AI tutors tend to be optimised for task completion and actively undermine the processes through which
> durable learning happens. [2](https://drphilippahardman.substack.com/p/from-ai-tutors-to-ai-study-mates)

Mechanics of the failure:

- **Answer-giving → cognitive debt.** Unguarded GPT-4: +48% during practice, **−17% on the unaided exam**.
  The AI also gave the correct answer only 51% of the time; students copied flawed answers without
  understanding. [5](https://www.psypost.org/unrestricted-generative-ai-harms-high-school-math-learning-by-acting-as-a-crutch/)
- **Metacognitive illusion.** Students using the unguarded AI *felt* they had learned just as much, while
  objectively performing worse. [5](https://www.psypost.org/unrestricted-generative-ai-harms-high-school-math-learning-by-acting-as-a-crutch/)
- **Infinite Socratic questioning → disengagement.** Khan Academy's own transcripts showed students getting
  frustrated and walking away; they rebuilt Khanmigo around "attempt first → hint → worked example only
  after genuine effort." [2](https://drphilippahardman.substack.com/p/from-ai-tutors-to-ai-study-mates)
- **Passive availability ≈ no usage.** Access nearly universal, engagement thin; help-seeking "remained a
  choice, and most students declined it most of the time." [4](https://hechingerreport.org/proof-points-khanmigo-math-ai-tutor/)
- **Rigid guardrails are also wrong.** A generic "don't give the answer" instruction produced *uniform
  questioning*, not pedagogy. Repeating a failed scripted prompt recovered 28.1% vs 39.8% for
  error-directed feedback. [1](https://arxiv.org/html/2609.38346v1)

**Design conclusion:** the answer is neither "give the answer" nor "always ask a question." It is a
**state machine that escalates assistance based on measured impasse depth and type**, wrapped in a
six-move learning sequence that *protects* the first hard attempt and the final unaided check.

### 1.3 Structural problems with existing Pakistani edtech

Pakistan's edtech ecosystem is small: 17 startups, ~US$7.9M tracked funding, ecosystem value US$75.9M,
led by **Maqsad** ($4.9M), **Nearpeer**, **Edkasa**, **Taleemabad**, **Sabaq**.
[1](https://www.startupblink.com/top-startups/pakistan/edtech) [5](https://tracxn.com/d/explore/k-12-edtech-startups-in-pakistan/__r0AGlFoqHmMdPCBwc9ayf09KAaFcawjc0EeQrSEYaLo)

What they do well: localized Urdu/English video content, MCQs for MDCAT/ECAT/BCAT, gamified quizzes.
Where the gap is (and therefore our opening):

1. They are **content libraries**, not **learner models**. Almost none maintain a persistent,
   quantitative, per-skill mastery estimate per student over years.
2. They are **stage-scoped** (9–12 / entry test), not **lifespan-scoped** (school → career).
3. They have **no self-improvement loop** — content is static; nothing learns from cohort outcomes.
4. They are **not built for 2G / feature-phone / low-RAM reality**.
5. They are **not research agents** — nothing continuously re-reads the world and updates itself.

---

## 2. Solutions: the evidence base we will build on

### 2.1 The Six-Move learning sequence (Prime → Probe → Point → Attach → Strengthen → Test)

A new idea is acquired through six ordered moves; AI scaffolding belongs **only in the middle four**.
The first hard attempt and the final unaided check must stay protected. Diagnostic: *if letting AI in
makes the task feel effortless, it is in the wrong place.*
[3](https://pith.science/paper/2606.26181)

| Move | What happens | AI allowed? |
|---|---|---|
| **Prime** | Activate prior knowledge, set the goal | No — student recalls alone |
| **Probe** | Student's first genuine attempt | No — protect the struggle |
| **Point** | Target the specific error | Yes, guarded |
| **Attach** | Connect to what the student already knows | Yes, guarded |
| **Strengthen** | Varied, spaced practice | Yes, guarded |
| **Test** | Unaided retrieval check | No — this is the measurement |

### 2.2 Graduated, impasse-sensitive assistance

From 20,462 student turns / 1,260 authentic sessions with a guardrailed chemistry tutor
[1](https://arxiv.org/html/2609.38346v1):

- Impasse **types**: conceptual error / expressed uncertainty / help-seeking.
- Benefit of questioning **decays with impasse depth** (AOR 0.78); error-directed feedback **grows**
  more useful (AOR 1.14).
- After a failed scripted question, repeating it recovers 28.1%; addressing the error recovers 39.8%.

→ Our escalation ladder: *probe question → targeted error feedback → concrete hint → partial
worked example → full worked example → re-test*. Never repeat a failed move.

### 2.3 Spaced retrieval + interleaving

- Spaced vs massed retrieval practice: **g = 0.74**. [3](http://www.lscp.net/persons/ramus/docs/EPR20.pdf)
- Expanding vs uniform schedules: **no significant difference (g = 0.034)** → prefer the simpler
  expanding schedule. Same source.
- Optimal gap ≈ **10–20% of the desired retention interval**; aim for **~85% accuracy**; Bahrick's
  56-day spacing beat 14/28-day with *fewer* sessions. [2](https://thelearnerlab.com/science-spaced-repetition-memory-retention/)
- At least one day between repetitions for long-term retention; longer gaps survive longer.
  [5](https://theeducationhub.org.nz/spaced-practice-and-its-role-in-supporting-learning-and-retention/)

### 2.4 Knowledge tracing: how we model "what does this student know"

- **BKT (Bayesian Knowledge Tracing)**: HMM per skill, four interpretable parameters — p-init, p-transit
  (learn), p-slip, p-guess. Corbett & Anderson (1994); backbone of most ITS mastery learning.
  [4](https://en.wikipedia.org/wiki/Bayesian_Knowledge_Tracing) [1](https://www.emergentmind.com/topics/bayesian-knowledge-tracing)
- **Why BKT over DKT for us**: interpretable (a teacher can read "p_mastery = 0.62"), works with tiny
  per-student data, runs on CPU with no training pipeline, and gives calibrated uncertainty.
  Deep KT predicts slightly better but is opaque and data-hungry.
  [1](https://www.emergentmind.com/topics/bayesian-knowledge-tracing)
- **Equity**: a single fixed-parameter BKT cannot fit both slow and fast learners and produces persistent
  equity gaps. **BBKT (Bayesian–Bayesian KT)** infers per-student parameter posteriors online and closes
  both mastery and effort gaps — outperforming even DKT-derived policies on fairness.
  [2](https://www.emergentmind.com/topics/bayesian-knowledge-tracing-bkt)
- **pyBKT** provides scikit-learn-style EM fitting for core/item-specific/personalized variants.
  [2](https://www.emergentmind.com/topics/bayesian-knowledge-tracing-bkt)

→ **Decision: standard BKT + per-student adaptive transit/slip/guess (a BBKT-lite online approximation)
+ an explicit forgetting decay.** Zero dependencies, CPU-only, interpretable to parents and teachers.

### 2.5 Motivation psychology (Self-Determination Theory)

- Gamification meta-analysis (31 studies, K–12): extrinsic g = 0.713, intrinsic g = 0.638;
  **secondary school students gain the most**; without autonomy/competence/relatedness support,
  gamification risks "short-term compliance rather than deep, internalized engagement."
  [1](https://onlinelibrary.wiley.com/doi/10.1002/pits.70056)
- SDT: motivation quality depends on **autonomy, competence, relatedness**. Badges tied to explicit goals
  build competence; meaningful choice builds autonomy; cooperative (not purely competitive) features
  build relatedness. [2](https://rsisinternational.org/journals/ijriss/uploads/vol9-iss25-pg282-287-202511_pdf.pdf)
- Motivation **mediates** the need-satisfaction → performance relationship (201 undergrads, PLS-SEM).
  [4](https://rsisinternational.org/journals/ijriss/view/psychological-need-satisfaction-and-student-performance-in-gamified-learning-the-mediating-role-of-motivation-based-on-self-determination-theory)

→ Design rules: **choice menus (autonomy)**, **calibrated ~85% challenge (competence)**,
**study circles not shaming leaderboards (relatedness)**, rewards tied to *strategy and effort*, never
to innate ability.

### 2.6 What does NOT work (so we avoid wasting effort)

- **Nudges at scale are weak.** Average Nudge-Unit effect **1.4 pp** vs 8.7 pp in published academic
  trials — a publication-bias gap of ~6x. [4](https://eml.berkeley.edu/~sdellavi/wp/NudgeToScale2020-03-20.pdf)
- **Study-time reminders: precise null effects** on credits, grades, retention — despite high engagement
  with the planning module. Students did have schedule slack, so "no time" was not the cause;
  effort felt too costly and returns felt ambiguous. [5](https://www.aeaweb.org/conference/2019/preliminary/paper/4aNaEzZ3)
- **Text campaigns for college success** did not replicate at scale; content framing, timing, delivery
  method made little difference. [1](https://behavioralscientist.org/why-arent-text-message-interventions-designed-to-boost-college-success-working-at-scale/)

→ Therefore: **never ship "reminders" as the core product.** Reminders are a thin delivery layer on top
of something that genuinely reduces effort cost and raises belief in the return on effort — i.e. a tutor
that makes the next 15 minutes *actually work*.

### 2.7 Self-improvement: how the system gets better without retraining

- No production system today retrains weights for self-improvement. Improvement = **context, memory and
  eval loops**, which are cheap, immediate, interpretable and reversible.
  [2](https://upsolve.ai/blog/self-improving-agent)
- **ACE (Agentic Context Engineering)**: Generator / Reflector / Curator, with *incremental* playbook
  updates (never full rewrites). +10.6% benchmark performance, 86.9% lower adaptation latency.
  [2](https://upsolve.ai/blog/self-improving-agent)
- **Reflexion**: verbal self-critique stored in episodic memory; HumanEval 80% → 91%.
  [3](https://stackviv.ai/blog/reflection-ai-agents-self-improvement)
- **Voyager**: memory as *executable skills*, not just text reflections.
  [5](https://futureagi.com/blog/self-improving-ai-agents-open-source-frameworks/)
- **HyperAgents / DGM**: the meta-level (the improvement procedure itself) becomes editable; meta-skills
  compound across domains. [1](https://o-mega.ai/articles/self-improving-ai-agents-the-2026-guide)
- **Prerequisite**: a frozen evaluation set. "Add each layer only after the previous one demonstrably
  moves your eval numbers." [2](https://upsolve.ai/blog/self-improving-agent)

→ Our loop: **every session → deterministic evals → reflection → playbook delta (add/merge/deprecate,
versioned) → A/B shadow test → promote only if eval improves.** Plus a nightly "sleep-time compute"
consolidation job and a research agent.

### 2.8 Language: Roman Urdu is a real engineering problem

- Roman Urdu has **no orthographic standard** — many phonetic spellings for one word — which makes
  Urdu → Roman-Urdu inherently ambiguous. [1](https://arxiv.org/html/2503.21530v1)
- A transformer approach (m2m100 + MLM pretraining + Dakshina/RUP fine-tuning) reaches Char-BLEU 96.37
  (Urdu→Roman-Urdu) and 97.44 (Roman-Urdu→Urdu), beating RNN baselines **and GPT-4o Mini**.
  [1](https://arxiv.org/html/2503.21530v1) [2](https://aclanthology.org/2025.loresmt-1.13/)

→ Practical implication: do not assume the LLM handles Roman Urdu reliably. Normalize input
(detect script, canonicalize common variants, optionally transliterate) **before** it reaches reasoning,
and always allow the student to switch to Urdu script, English, or voice.

### 2.9 On-device fallback (for 2G / no-internet / privacy)

- Sub-3B models are now practical on mobile: **Qwen3 0.6B (614 MB, ≥2 GB RAM, ~5s init)** and
  **Gemma 4 E2B (~2.6B, 2.6 GB, ≥8 GB RAM)**, with Gemma 4 E4B (3.65 GB) too large to ship.
  [3](https://arxiv.org/html/2604.24636v2)
- Frameworks: LiteRT-LM (1 Gradle dep, any device w/ CPU fallback), MLC LLM, AICore.
  [3](https://arxiv.org/html/2604.24636v2)
- INT4 quantization is the mobile standard; Gemma-clas models run 30–45 tok/s on Snapdragon NPU.
  [4](https://renard-digital.fr/blog/en/small-language-models-edge-devices-2026/)

→ **Two-tier model policy**: on-device SLM handles routine hints/motivation/normalization offline;
cloud free-tier handles diagnosis, planning and hard reasoning. Sync when bandwidth appears.

---

## 3. The free API stack (verified as of Oct 2026)

### 3.1 LLM inference — permanent free tiers, no credit card

| Provider | Free quota | Notes | Priority |
|---|---|---|---|
| **Groq** | 30 RPM, 14,400 RPD (model-dependent), 6K TPM | Fastest; Llama/Qwen/GPT-OSS/Kimi | 1 (primary) |
| **Google Gemini API** | ~1,500 RPD on Flash; free embeddings; up to 1M context | Most capable free tier; multimodal | 2 |
| **OpenRouter** | 20 RPM / 50 RPD; 1,000 RPD after $10 top-up; 28+ `:free` models | Model variety, single OpenAI-compatible endpoint | 3 |
| **Cerebras** | 30 RPM, ~14,400 RPD | Very fast | 4 |
| **Mistral La Plateforme** | Free mode, account-specific limits | — | 5 |
| **GitHub Models** | 10–15 RPM, 50–150 RPD | Uses existing GitHub token | 6 |
| **HuggingFace** | Few hundred req/hr serverless, models <10B | Long tail | 7 |
| **Cloudflare Workers AI** | 10,000 neurons/day | Edge | 8 |
| **NVIDIA NIM** | 40 RPM | — | 9 |

Sources: [1](https://tokenmix.ai/blog/free-llm-api) [3](https://klymentiev.com/blog/best-free-llm-2026) [2](https://www.kdnuggets.com/5-free-llm-api-providers-you-can-use-in-2026)

Stacked: **Groq 14,400 + Gemini 1,500 + OpenRouter 1,000 ≈ 16,900 free requests/day.**
[3](https://klymentiev.com/blog/best-free-llm-2026)

### 3.2 Search / research (for the self-research agent)

| Provider | Free | Card? |
|---|---|---|
| **Tavily** | 1,000 credits/month (search + extract) | No |
| **Serper** | 2,500 queries (one-time) | No |
| **Brave Search API** | $5/month credits (~1,000 searches) | Yes |
| **Jina Reader** | 1M tokens/month (content extraction) | No |
| **Google CSE** | 100/day — **closed to new signups, shuts down 1 Jan 2027** | — |

Sources: [1](https://parallel.ai/articles/best-free-web-search-api) [3](https://apiserpent.com/blog/free-google-search-api-tested)

### 3.3 Zero-cost / local components (remove API dependency entirely)

| Need | Free option |
|---|---|
| Vector search / memory | SQLite + `sqlite-vec`, or FAISS — local, no API |
| Structured storage | SQLite (stdlib) |
| Embeddings | Gemini free embedding endpoint (fallback: hashed lexical vectors, offline) |
| TTS (Urdu/English audio for low literacy) | edge-tts / gTTS |
| STT (voice input) | Groq-hosted Whisper (free tier) |
| OCR (photo of a textbook page) | Gemini vision (free tier) |
| Offline inference | Qwen3 0.6B / Gemma 4 E2B via LiteRT-LM |

### 3.4 Engineering rules for free-tier survival

1. **Quota ledger in SQLite** — per provider, per day; hard stop before 429.
2. **Priority chain with automatic failover** on 429/5xx/timeout.
3. **Semantic + exact response cache** — a huge fraction of tutoring turns repeat across students.
4. **Route by difficulty**: cheap/fast model for routine turns, frontier model for diagnosis/planning.
5. **Batched background work** (research, reflection, consolidation) runs in off-peak, rate-limited.
6. **Graceful degradation → local SLM → cached content → offline worksheet.** Never a blank screen.

---

## 4. Competitive gap: what would make this "never built before in Pakistan"

| Capability | Pakistani edtech today | Global AI tutors today | **RAASTA** |
|---|---|---|---|
| Per-skill, persistent mastery model (BKT) | ✗ | Partial (Khan, ALEKS) | ✓ interpretable + per-student priors |
| Lifespan scope (school → career) | ✗ stage-scoped | ✗ | ✓ one profile, years |
| Guardrailed, impasse-aware tutoring | ✗ | Partial | ✓ six-move + escalation ladder |
| Roman Urdu / Urdu first-class | Partial (content) | ✗ | ✓ normalization + transliteration layer |
| SDT-grounded motivation engine | Badges only | Streaks only | ✓ autonomy/competence/relatedness |
| Wellbeing + burnout guard | ✗ | ✗ | ✓ mandatory rest, load caps |
| Self-improving playbook + evals | ✗ | ✗ | ✓ ACE-style, versioned |
| Continuous self-research agent | ✗ | ✗ | ✓ searches, distills, updates |
| 2G / low-RAM / offline-first | ✗ | ✗ | ✓ on-device SLM tier |
| Runs on free APIs only | n/a | ✗ paid | ✓ quota ledger + failover |

---

## 5. Open risks (must be handled, not ignored)

| Risk | Mitigation |
|---|---|
| **Hallucinated facts** in a system that students trust | Ground every factual claim in vetted syllabus sources; show source; "I'm not sure" is an allowed and rewarded answer |
| **Free-tier limits vanishing overnight** | Provider-agnostic router; config-driven model list; local SLM fallback |
| **Cheating / academic dishonesty** | Attempt-first gate; "exam mode" that locks assistance; integrity signals surfaced to teachers/parents with consent |
| **Child safety & data privacy** | Minimal data collection, local-first storage, no ad tech, explicit parental controls, encrypted profile |
| **Motivation hacks becoming manipulation** | Documented ethics policy: no shame mechanics, no infinite streaks, no dark patterns; rest is a feature |
| **Evaluation capture** ("next-item correctness" ≠ learning) | Delayed, unaided, transfer tests are the primary metric — not in-session correctness |
| **Language quality drift** | Gold-set Roman-Urdu eval suite; human review loop |

---

## 6. Research → build decisions (what we do about it)

1. **Engagement is the binding constraint, not model capability** → invest in the invitation, the session
   opener, proactive (not passive) assistance, and a session that *works* in 10 minutes.
2. **Protect the struggle** → six-move sequence; first attempt and final test are unaided.
3. **Escalate, never repeat** → impasse-depth ladder with measured types.
4. **Spacing is the single highest-ROI mechanic** → scheduler is a first-class module, not an afterthought.
5. **BKT + per-student posteriors + forgetting** → interpretable, CPU-only, equity-aware.
6. **SDT, not Skinner** → choice, calibrated challenge, relatedness; rest days are mandatory.
7. **Evals before self-improvement** → frozen eval suite ships before the reflection loop is trusted.
8. **Free-tier router with quota ledger** → the system must survive on ~16,900 free req/day.
9. **Offline-first, Roman Urdu, low-end device** → or it will not reach the student who needs it most.
