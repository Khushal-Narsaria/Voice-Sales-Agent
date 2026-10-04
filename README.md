# Voice Sales Agent — Hindi · Hinglish · English

[![tests](https://github.com/Khushal-Narsaria/Voice-Sales-Agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Khushal-Narsaria/Voice-Sales-Agent/actions/workflows/tests.yml)
[![Live page](https://img.shields.io/badge/live-results_%26_calls-2a78d6)](https://khushal-narsaria.github.io/Voice-Sales-Agent/)

A voice AI agent that calls home-loan leads, talks in **English, Hinglish or Hindi**, collects what a loan advisor needs,
handles interest-rate questions, refusals and prompt-injection attempts, and books a free advisor call. It runs on
**open-source models on a laptop** (Ollama: qwen2.5, llama3.2, gemma2; Whisper for speech-to-text; gTTS for speech) and
every part is measured: 26 held-out customer personas, 6 agent configurations, a speech-under-noise test and SQL analytics
over all the transcripts.

**Live page:** https://khushal-narsaria.github.io/Voice-Sales-Agent/ — results, every simulated call turn by turn (some with audio),
noisy audio samples, the SQL queries and the prompt-iteration log.

The lender ("Ghar Home Loans") and all customers are fictional.

## What it does

```
customer speech ──► Whisper (small, int8, CPU) ──► language: en / hinglish / hi
                                                           │
             ┌─────────────────────────────────────────────▼──────────────────────────────┐
             │ LLM turn (JSON): intent · fields the customer gave · the customer's words    │
             │                  each field came from · a short acknowledgement / answer     │
             └─────────────────────────────────────────────┬──────────────────────────────┘
                                                           ▼
  flow engine (code): keep a field only if its quote is in what was said · read Indian amounts
  ("1.5 crore", "पचास हज़ार") · slot must contain a day/time · eligibility rules · move the call
  greet → discover → qualify → book (or callback) · pick the next scripted question in the
  customer's language · fixed closing lines
                                                           ▼
  guardrails: voice-style clean-up · no rate/approval promises · never ask for OTP/PIN/ID ·
  language guard (one rewrite if the script is wrong)  ──►  gTTS  ──►  speech
```

- **Business goal → flow**: [`config/home_loan_flow.yaml`](config/home_loan_flow.yaml) holds the goal, product facts, the
  fields to collect, eligibility rules, scripted questions and closing lines in three languages. The flow engine
  ([`flow.py`](src/voiceagent/flow.py)) owns every decision; the model only understands the customer and phrases replies.
- **Prompt engineering** ([`prompts.py`](src/voiceagent/prompts.py)): three variants that build on each other —
  zero-shot, few-shot (worked examples in English, Hinglish and Hindi: a multi-field answer, a rate question, a refusal,
  a busy customer), and few-shot + a shaped **persona** (Priya: warm, respectful "aap", never pushy) with **voice-first rules**
  (two short sentences, amounts as people say them, the customer's own script).
- **Structured test cases** ([`data/personas.json`](data/personas.json)): 26 personas, 8-9 per language — cooperative,
  everything-at-once, corrects an amount, busy, not interested, wrong number, keeps pushing for the interest rate,
  not eligible, a prompt-injection attempt and an OTP offer — each with ground-truth facts and the outcome the business wants.
  A separate set of 8 **development** personas was used for all prompt iteration.
- **Customer simulator** ([`simulator.py`](src/voiceagent/simulator.py)): llama3.2:3b role-plays each persona in its language.
- **Success metrics** ([`metrics.py`](src/voiceagent/metrics.py)): task success, fields correct, spoken policy violations
  (and how many the guard caught), voice style, language match, JSON validity, turns and latency.
- **SQL analytics** ([`sql/analytics.sql`](sql/analytics.sql)): every call and turn goes into SQLite; queries report the
  scorecard, the booking funnel, results by language and by customer behaviour, intents, guardrail hits, field checks,
  latency percentiles and language rewrites.
- **Voice test** ([`run_voice_eval.py`](run_voice_eval.py)): 36 customer answers synthesized, mixed with call-centre
  babble at 20 / 10 / 5 dB SNR, transcribed by Whisper and passed to the agent.

## Results

<!-- results -->
### Simulated calls (26 held-out personas per row)

| Agent | Task success | Fields correct | Spoken violations | Caught by guard | Voice style | Language match | Valid JSON | Turns | Latency p50 / p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Zero-shot · qwen2.5:3b · flow engine in code | 92.3% | 77.0% | 0 | 0 | 99.6% | 100.0% | 90.2% | 6.6 | 2,487 / 9,828 |
| Few-shot · qwen2.5:3b · flow engine in code | 100.0% | 90.0% | 0 | 0 | 100.0% | 100.0% | 98.6% | 4.5 | 2,296 / 5,365 |
| Few-shot + persona & voice rules · qwen2.5:3b · flow engine in code | 92.3% | 85.7% | 0 | 0 | 100.0% | 100.0% | 96.2% | 5.0 | 2,326 / 5,097 |
| Few-shot + persona & voice rules · qwen2.5:3b · LLM runs the flow | 3.9% | 58.3% | 8 | 8 | 75.7% | 98.2% | 93.1% | 13.8 | 2,900 / 10,605 |
| Few-shot + persona & voice rules · llama3.2:3b · flow engine in code | 92.3% | 87.2% | 0 | 0 | 97.8% | 100.0% | 93.3% | 4.8 | 2,950 / 7,250 |
| Few-shot + persona & voice rules · gemma2:2b · flow engine in code | 76.9% | 83.2% | 0 | 0 | 100.0% | 100.0% | 100.0% | 6.6 | 1,689 / 2,191 |

### By language (deployed agent)

| language | calls | task_success_pct | field_accuracy_pct | avg_reply_words |
|---|---:|---:|---:|---:|
| en | 9 | 100.0 | 97.6 | 14.0 |
| hi | 8 | 100.0 | 80.6 | 15.4 |
| hinglish | 9 | 100.0 | 90.5 | 14.9 |

### By customer behaviour (deployed agent)

| behavior | calls | task_success_pct | avg_turns | failures |
|---|---:|---:|---:|---:|
| all_at_once | 3 | 100.0 | 6.0 | – |
| busy | 3 | 100.0 | 1.0 | – |
| cooperative | 3 | 100.0 | 6.7 | – |
| corrects | 3 | 100.0 | 7.3 | – |
| injection | 1 | 100.0 | 6.0 | – |
| not_eligible | 3 | 100.0 | 5.3 | – |
| not_interested | 3 | 100.0 | 1.0 | – |
| rate_pusher | 3 | 100.0 | 7.0 | – |
| sensitive | 1 | 100.0 | 4.0 | – |
| wrong_number | 3 | 100.0 | 1.0 | – |

### Voice: fact captured from audio (12 utterances per language)

Whisper either detects the language itself (auto) or is told the call's language (locked: Hindi for Hindi and Hinglish callers, English otherwise), as the agent already knows it from earlier turns.

| Language | Whisper | Typed text | Clean audio | 20 dB | 10 dB | 5 dB |
|---|---:|---:|---:|---:|---:|---:|
| English | auto-detect | 91.7% | 100.0% | 100.0% | 91.7% | 75.0% |
| English | language locked |  | 100.0% | 100.0% | 100.0% | 75.0% |
| Hinglish | auto-detect | 100.0% | 41.7% | 41.7% | 33.3% | 50.0% |
| Hinglish | language locked |  | 41.7% | 50.0% | 41.7% | 41.7% |
| Hindi | auto-detect | 83.3% | 41.7% | 33.3% | 41.7% | 33.3% |
| Hindi | language locked |  | 41.7% | 41.7% | 50.0% | 25.0% |

Word error rate, English: 9.7% clean, 35.6% at 5 dB; Hindi: 61.0% clean (61.0% locked), 104.4% at 5 dB (84.9% locked). Whisper small (int8, CPU) median 2.005 s for 3.12 s of audio (real-time factor 0.645); gTTS median 0.464 s per reply.
<!-- /results -->

**What the numbers say**

- **Code-owned flow beats a model-owned flow by a mile.** Given the whole flow and asked to manage it, qwen2.5:3b almost
  never finished a call correctly and spoke compliance breaks; with the same prompt and the flow engine in code, the agent
  ends most calls the right way with no spoken violations.
- **Worked examples matter most for extraction.** Zero-shot reaches the right outcome (the engine's checks carry it) but
  captures fewer facts and needs more turns; few-shot examples teach the output format, including the evidence quotes.
- **The persona and voice rules did not add accuracy** (a useful negative result): once code picks the next question
  and guards the reply language, the plain few-shot prompt was the most accurate, and all variants already speak short,
  clean replies in the customer's script. The persona prompt is longer, so it also costs a little latency.
- **Speech is the bottleneck for Hindi, not the agent.** From typed text the agent captures 83-100% of facts in every
  language; from clean audio it keeps 100% in English but only about 42% in Hindi and Hinglish, because Whisper small
  transcribes Hindi poorly (61% word error rate even on clean audio) and often writes it in Urdu script. Telling Whisper
  the call's language cuts the Hindi error rate under noise but barely moves the facts captured: a larger or
  Indic-tuned speech model is the next step.

## Run it

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-voice.txt pytest ruff
ollama pull qwen2.5:3b && ollama pull llama3.2:3b && ollama pull gemma2:2b
.venv/bin/python talk.py --voice                 # be the customer; hear Priya's replies
.venv/bin/python run_eval.py                     # 6 configurations x 26 personas (cached model calls)
.venv/bin/python analyze.py                      # SQLite + sql/analytics.sql -> results/analytics.json
.venv/bin/python run_voice_eval.py               # Whisper under noise
.venv/bin/python report.py                       # tables in this README
.venv/bin/python build_page.py --repo https://github.com/Khushal-Narsaria/Voice-Sales-Agent --author "Khushal Narsaria"
.venv/bin/pytest -q                              # 25 tests, scripted model, no LLM or audio needed
```

## Project layout

```
config/home_loan_flow.yaml   business goal, fields, rules, scripted questions, closings (en / hinglish / hi)
src/voiceagent/
  flow.py        flow engine: states, validation, eligibility, endings
  prompts.py     zero-shot / few-shot / persona prompts, LLM-owned-flow ablation, customer simulator prompt
  agent.py       one turn: model -> engine -> scripted question -> language guard -> compliance guard
  numbers.py     spoken Indian amounts (lakh / crore / hazaar, Hindi number words, Devanagari digits)
  cues.py        evidence check, callback / refusal cues, day-or-time check
  voice_rules.py speech clean-up, style checks, compliance guard
  lang.py        English / Hinglish / Hindi detection
  metrics.py     success metrics against persona ground truth
  store.py       transcripts -> SQLite
  voice/         gTTS, noise mixing at a target SNR, Whisper
data/            test personas, dev personas, voice utterances
sql/analytics.sql
notes/PROMPT_ITERATIONS.md   every prompt / flow change and what it fixed (dev set only)
```

## Limits

- Customers are simulated by a 3B model, which sometimes misstates its own facts; those slips count against the agent.
- 26 personas is a small test set; the numbers compare configurations on the same calls rather than claim a benchmark.
- Speech is turn-based (no streaming or barge-in), and latency is measured on a laptop CPU/GPU, not a production cluster.
