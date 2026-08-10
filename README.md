# Project Null

Project Null is the Bizarro counterpart to [Project Aleph](https://github.com/wildcat-finance/project-aleph): a Telegram bot that asks questions instead of answering them.

Its job is to continuously invent plausible, awkward, ambiguous, irrelevant, and adversarial Wildcat-shaped questions, send them through the same surface real users use, and turn the resulting failures into a stronger Aleph corpus and evaluation set.

“Hallucinate” here means generating questions and scenarios. Null must not present invented protocol facts, positions, transactions, or people as real.

## Why it exists

Aleph should become more robust as it is used. A useful support agent needs to distinguish between:

1. a question it can answer with evidence;
2. a question that needs a human;
3. a question that should be rejected; and
4. a question that exposes a genuine gap in its corpus, retrieval, routing, or live-data tools.

Production traffic is valuable but uneven. Null supplies a steady stream of synthetic pressure: normal questions, half-remembered terminology, missing context, false premises, obscure borrower situations, nonsense, prompt injection, and abuse. The goal is not to make Aleph agree with Null. The goal is to make every Aleph outcome legible and useful.

## The loop

```text
scenario seed → Null question → Telegram → Aleph outcome → review → corpus/eval candidate
```

Each probe carries a private correlation ID and a declared test intent. The Telegram message itself should read like an ordinary user question; hidden metadata records what Null meant to test.

An outcome is classified as one of:

- **answered** — supported by the current corpus or live data;
- **pointed** — correctly handed to a human or specialist tool;
- **refused** — correctly rejected as unsafe or out of scope;
- **abstained** — insufficient evidence;
- **failed** — wrong route, unsupported claim, irrelevant citations, silence, or an operational error.

Reviewer feedback decides what happens next. A failure may become a regression question, a corpus proposal, a routing change, a live-data requirement, or simply a better rejection test. Generated text never enters Aleph's trusted corpus merely because Null produced it.

## Telegram behaviour

Null lives in a dedicated Telegram group alongside Aleph and its human reviewers.

The first interface should stay deliberately small:

- `/probe` — generate and send one question;
- `/burst <n>` — schedule a bounded mixed batch;
- `/mode <name>` — select a scenario family;
- `/feedback <result> [note]` — attach a human judgement to the replied-to probe;
- `/pause` and `/resume` — stop or restart generation without losing state;
- `/status` — show the current run, mix, rate limit, and unresolved reviews.

Null must be rate-limited, visibly identifiable, and unable to respond recursively to its own output or another bot's output. Group delivery should use explicit bot commands and replies rather than relying on plain `@mentions`, which Telegram privacy mode does not reliably deliver to bots.

Null-to-Aleph delivery additionally requires Telegram's
[Bot-to-Bot Communication Mode](https://core.telegram.org/api/bots%2Fbot-to-bot)
for at least one bot. Null sends an explicit `/ask@ProjectAlephWildcat_bot`
command, so Group Privacy can remain enabled and neither bot needs group-admin
access. `TELEGRAM.md` defines the operational boundary and loop safeguards.

## Question mix

A run samples from an explicit, versioned mix rather than unconstrained randomness:

- ordinary protocol and market questions;
- novice vocabulary and malformed terminology;
- questions that need current on-chain or borrower data;
- historical activity questions;
- incomplete, ambiguous, or contradictory requests;
- plausible false premises and invented edge cases;
- requests outside Wildcat's scope;
- prompt injection and attempts to override policy;
- abusive, coercive, or otherwise rejectable input; and
- pure noise.

Safety probes should exercise categories without repeatedly emitting slurs, threats, or graphic content into a human group. Store the category and expected behaviour; use minimally sufficient test language by default.

The mix, seeds, model, prompt version, and sampling settings must be recorded so a run can be reproduced.

## Data and privacy

Raw inbound questions and associated Telegram identifiers may be retained for at most **30 days** for debugging and review.

Before longer retention:

- remove Telegram user, chat, and message identifiers;
- remove usernames, links, wallet addresses, and other direct identifiers unless a reviewer explicitly marks them as necessary public test data;
- separate the anonymised question from operational logs;
- retain provenance that says whether a question was synthetic, production-derived, or human-authored; and
- preserve reviewer decisions and expected outcomes without preserving identity.

Anonymised questions and regression cases may then be retained indefinitely. Deletion and anonymisation must be automated, testable, and auditable. Generated questions are synthetic even when they resemble real traffic; they must never be relabelled as user questions.

## What must be built, in order

### 1. Define the records

Specify versioned schemas for scenarios, probes, Telegram deliveries, Aleph outcomes, reviewer feedback, anonymised questions, and export candidates. Define the outcome taxonomy and the exact 30-day retention clock before collecting anything.

### 2. Build the Telegram shell

Implement polling, command handling, reply-based feedback, deduplication, rate limits, pause/resume, durable checkpoints, and loop prevention. Prove that restarts do not resend probes or lose feedback.

### 3. Build deterministic generation

Start with templates and seeded mutations for each question family. Add model-generated variants only behind a strict envelope: declared intent, bounded length, provenance, reproducible settings, and no claim that generated facts are real.

### 4. Capture Aleph outcomes

Correlate a probe with Aleph's response or silence without coupling Null to Aleph's internals. Record route, citations, latency, and terminal outcome where exposed, while treating Telegram as the end-to-end truth.

### 5. Add human review

Make feedback fast enough to happen in the group. Support expected-outcome corrections, notes, duplicate marking, and promotion into a proposed regression or corpus-gap queue. No automatic corpus writes.

### 6. Enforce anonymisation

Run and test the 30-day purge/anonymisation job. Demonstrate that retained fixtures cannot be joined back to Telegram identities through Null's own stores.

### 7. Export evaluation candidates

Produce reviewable, versioned artifacts that Aleph can ingest deliberately: questions, expected routes/outcomes, rationale, provenance class, and any approved evidence targets. Keep corpus proposals separate from regression tests.

### 8. Operate the loop

Add health checks, immutable run manifests, audit summaries, failure alerts, and safe rollout controls. Begin with a tiny developer group, tune the mix, then widen the trial.

## Non-goals

Null is not:

- an oracle or a second source of Wildcat truth;
- an autonomous corpus editor;
- a licence to store identifiable Telegram history forever;
- a benchmark that can grade factual answers without approved evidence; or
- a bot that floods public groups for entertainment.

## First milestone

The first useful release sends a reproducible mixed batch to a private Telegram group, survives a restart without duplication, captures reply-based human judgements, and exports an anonymised review artifact. It does not need an elaborate generative model. The feedback loop is the product; creative question generation is one component.
