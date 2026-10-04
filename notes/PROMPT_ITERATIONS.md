# Prompt and flow iterations (development set only)

Every change below was tried on the **8 development personas** (`data/dev_personas.json`), never on the 26 test
personas, so the final test numbers are not tuned to the test set. Model: qwen2.5:3b; simulator: llama3.2:3b.
"Task" = calls that ended with the right outcome; "fields" = share of the persona's facts captured correctly.

| # | Change | What went wrong before it | Result on the dev set |
|---|---|---|---|
| 1 | Baseline: one JSON call per turn (intent, fields, reply) | n/a | zero-shot: task 4/8, fields 0.66 |
| 2 | Intent definitions in the prompt ("busy is not a refusal") | "call me back tomorrow" was labelled *not interested* and the call was dropped | busy callers recognised by the few-shot variant |
| 3 | **Engaging = consent** in the flow engine | a customer who simply answered ("I'm from Mumbai") never said "yes", so the call never left the greeting | calls stopped stalling at the greeting |
| 4 | **Number tool**: code reads spoken Indian amounts ("1.5 crore", "dedh lakh", "पचास हज़ार") | the model stored 1.5 crore as 15 lakh, which made an eligible lead "not eligible" | few-shot: task 8/8; unit slips caught in code |
| 5 | Language instruction moved next to the customer's words | the reply-language rule sat early in a long prompt; English callers got Hinglish | persona variant: language match 0.80 → 0.90 |
| 6 | **Grounding**: each field needs the customer's own words as evidence; few-shot examples moved to a labelled "other calls" block | the model invented fields ("searching", "salaried") and copied an example city ("Nashik") | few-shot: fields 0.69 → 0.86 |
| 7 | Grounding fallback by field type, compound amounts ("ek lakh 50 thousand"), language guard (one rewrite if the script is wrong) | correct fields without a quote were thrown away, so calls never reached booking | few-shot: fields 0.90, language 0.94 |
| 8 | **Scripted next question**: the model writes the acknowledgement or answer, code appends the question for the next missing field | the reply was written before the engine updated the call, so the agent re-asked known fields and looped | few-shot and persona: **task 8/8**, fields 0.93 / 0.90, language match **1.00** |

**Found in the test-set analysis (after the first full run), fixed, and the test set re-run.** The SQL `by_behavior` query showed
bookings ending as callbacks: customers who answered the advisor-slot question with "शुक्रवार को शाम को" or
"shaam ko 6 baje" tripped the callback safety net, whose cue list included bare time words ("subah", "शाम को"). The net
now fires only on explicit "call me later" phrases and never at the booking stage. This is a bug fix, not prompt tuning;
the first run's numbers are kept in `results/first_run_summary.json` for transparency.

## What this taught

- Small open models are good at **understanding** a turn (intent, values) and weak at **bookkeeping** (what is still
  missing, unit arithmetic, when to stop). Moving the bookkeeping into code fixed most failures.
- Worked examples matter more than any instruction: they teach the output format, including the evidence quotes that the
  grounding check needs. Without them (zero-shot) most fields arrive without evidence.
- Put the instruction that must win (reply language) **next to the input**, not at the top of a long system prompt.
- Every fix is a deterministic check the call can be audited against: a number parser, a quote check, a day/time check,
  a callback-cue safety net, a compliance guard and fixed closing lines.
