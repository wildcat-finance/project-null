# Project Null

Project Null is the Bizarro counterpart to [Project Aleph](https://github.com/wildcat-finance/project-aleph): a Telegram bot that asks questions instead of answering them.

Its job is to continuously invent plausible, awkward, ambiguous, irrelevant, and adversarial Wildcat-shaped questions, send them through the same surface real users use, and turn the resulting failures into a stronger Aleph corpus and evaluation set.

Every run targets one explicit Aleph identity, written **evolution N/generation
M**. Evolution changes Aleph and Null's shared interpretation contract;
generation counts activations within that evolution. Null refuses to start with
an absent or mismatched pair and stamps it onto every new probe and retained
candidate.

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

[`OUROBOROS.MD`](OUROBOROS.MD) is the cold-read operator handoff for continuing
this loop. It defines the one-operator lease, organisation-authenticated local
model tunnel, controlled burst/review/finalization process, Aleph handoff,
privacy boundaries, and emergency revocation without distributing production
credentials.

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

The interface stays deliberately small. In groups, every command uses the
explicit `@<NullBot>` form:

- `/probe@<NullBot>` — generate and send one question;
- `/burst@<NullBot> <n>` — send a bounded batch of one to ten questions;
- `/mode@<NullBot> mixed|<family>` — select the mixed catalogue or one family;
- `/queue@<NullBot>` — show unresolved probes with short review codes and only
  their family, expected outcome, observed outcome, route, and review state;
- `/feedback@<NullBot> [review_code] <decision> <expected_outcome> [note]` —
  attach a human judgement by code or by replying to the stored probe or answer;
- `/feedback@<NullBot> { ... }` — process up to twenty coded judgements
  separated by newlines or the Telegram-safe `|`, returning one ordered result
  line for each entry;
- `/finalize@<NullBot> [review_code]` — anonymise a reviewed probe, purge its
  raw linkage, and place it in the appropriate proposal queue;
- `/finalize@<NullBot> { ... }` — finalise up to twenty codes separated by
  newlines or `|`, in order, with an independent result line for each entry;
- `/pause@<NullBot>` and `/resume@<NullBot>` — disable or enable generation
  without losing state; and
- `/status@<NullBot>` — show the current run, mode, rate limit, checkpoint,
  unresolved reviews, unresolved finalised-candidate pile, and downstream
  resolved count, plus the active Aleph coverage identity when configured.
- `/ping@<NullBot>` — return `Pong!` plus process uptime, loop state, the active
  Aleph `evolution N/generation M`,
  run/generator/source identities, current coverage and curriculum pins, and
  scrubbed queue counts without generating a probe.

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

Live and historical templates receive an explicitly configured, validated
market and account context in production. The built-in deterministic addresses
exist only for isolated tests: the Telegram service has no fixture fallback.
Public run metadata binds the configured pair by digest without publishing the
raw addresses, which remain subject to the normal 30-day review boundary.

Mixed mode uses a versioned, seeded stratified cycle. Each family appears once
before any family repeats, so a bounded burst of up to ten probes spends every
slot on a different question family. Explicit single-family mode remains
available for targeted regression rehearsals. The policy version and catalogue
hash are recorded with the run and each generated probe.

Within each family, the checked-in challenge catalogue progresses through
foundation, contextual, and adversarial tiers. Null prefers an unseen challenge
at the family's current tier, then unseen higher-tier challenges, and repeats
only after every eligible challenge has been exercised. A durable exposure
record retains only catalogue ID, tier, family, hash, and time, so this novelty
memory survives raw-question deletion without retaining Telegram identity or
question text.

Progression is based on retained human review, not Aleph's self-assessment.
One reviewed `regression` or `rejection_test` advances a family to contextual;
two advance it to adversarial. Corpus gaps, routing changes, live-data
requirements, duplicates, and discards remain useful evidence but do not count
as mastery. `/status` exposes only scrubbed counts and the active curriculum
version.

### Coverage-guided sophistication

Null can consume Aleph's answer-free coverage silhouette to look for neglected
topics and route boundaries without seeing Aleph's questions, answers, corpus
text, citations, or human identities. The artifact is content-addressed and
must match an explicitly configured active Aleph evolution/generation and release. Null rejects changed
hashes, inconsistent counts, leaked content fields, addresses, URLs, or a
boundary that permits factual grading or autonomous corpus writes.

In mixed mode, every third slot is selected from the silhouette-derived target
set. Declared-gap topics are exercised before other unseen route, live, sparse,
or coverage edges. The actual questions still come from Null's checked-in local
templates; the silhouette supplies shape, never facts or expected answer text.
Single-family mode remains catalogue-only so a reviewer can rehearse one family
without the coverage scheduler intervening. If no silhouette is configured,
generation is the ordinary novelty curriculum.

Every probe records the active Aleph evolution/generation. Each coverage-guided
probe additionally records the silhouette, release, evaluation, topic,
and target kind in raw generator provenance. Long-term exposure memory retains
only the target ID and silhouette file hash, not the rendered question. Human
review remains the only path from a result to a regression or factual proposal.

## Data and privacy

Raw inbound questions and associated Telegram identifiers may be retained for at most **30 days** for debugging and review.

Before longer retention:

- remove Telegram user, chat, and message identifiers;
- remove usernames, links, wallet addresses, and other direct identifiers unless a reviewer explicitly marks them as necessary public test data;
- separate the anonymised question from operational logs;
- retain provenance that says whether a question was synthetic, production-derived, or human-authored; and
- preserve reviewer decisions and expected outcomes without preserving identity.

Anonymised questions and regression cases may then be retained indefinitely. Deletion and anonymisation must be automated, testable, and auditable. Generated questions are synthetic even when they resemble real traffic; they must never be relabelled as user questions.

`PRIVACY.md` defines the executable deletion boundary. `EXPORTS.md` defines the
separate, content-addressed regression and corpus-proposal artifacts.

## Build order and current rollout

Stages 1–7 are implemented. Stage 8 is active: the single-probe production
rehearsal and paused restart test pass, while the small developer-group mixed
batch and wider rollout remain. This dependency order still governs future
changes.

### 1. Define the records — implemented

Specify versioned schemas for scenarios, probes, Telegram deliveries, Aleph outcomes, reviewer feedback, anonymised questions, export candidates, and terminal downstream dispositions. Define the outcome taxonomy and the exact 30-day retention clock before collecting anything.

### 2. Build the Telegram shell — implemented

Implement polling, command handling, reply-based feedback, deduplication, rate limits, pause/resume, durable checkpoints, and loop prevention. Prove that restarts do not resend probes or lose feedback.

Long-poll read timeouts are empty, uncheckpointed iterations rather than
process failures. A send timeout remains an uncertain delivery boundary: Null
confirms no delivery record and never retries that prepared probe automatically.

### 3. Build deterministic generation — implemented

Use a versioned three-tier challenge catalogue for each family, deterministic
seeded selection, durable novelty memory, and advancement based only on human
review. An optional validated Aleph coverage silhouette schedules unseen
boundary probes at a fixed interval while preserving catalogue fallback. Add
model-generated variants only behind a strict envelope: declared
intent, bounded length, provenance, reproducible settings, and no claim that
generated facts are real.

### 4. Capture Aleph outcomes — implemented

Correlate a probe with Aleph's response or silence without coupling Null to Aleph's internals. Record route, citations, latency, and terminal outcome where exposed, while treating Telegram as the end-to-end truth.

### 5. Add human review — implemented

Make feedback fast enough to happen in the group. Support expected-outcome
corrections, notes, duplicate marking, and explicit finalisation into a proposed
regression or corpus-gap queue. No automatic corpus writes.

### 6. Enforce anonymisation — implemented

Run and test the 30-day purge/anonymisation job. Demonstrate that retained fixtures cannot be joined back to Telegram identities through Null's own stores.

### 7. Export evaluation candidates — implemented

Produce reviewable, versioned artifacts that Aleph can ingest deliberately: questions, expected routes/outcomes, rationale, provenance class, and any approved evidence targets. Keep corpus proposals separate from regression tests. Import Aleph's complete acknowledgement report explicitly so accepted, duplicate, and rejected cases leave the unresolved pile without rewriting the candidate or export.

### 8. Operate the loop — active rollout

Health checks, immutable run manifests, audit summaries, failure alerts,
hardened services, and safe rollout controls are implemented. The remaining
order is: run a bounded mixed batch with the small developer group, review and
finalise every useful case, tune the mix from those results, then widen the
trial only after the privacy and loop-prevention boundaries continue to hold.

## Non-goals

Null is not:

- an oracle or a second source of Wildcat truth;
- an autonomous corpus editor;
- a licence to store identifiable Telegram history forever;
- a benchmark that can grade factual answers without approved evidence; or
- a bot that floods public groups for entertainment.

## First milestone

The reference deployment has completed the single-probe path: Bot-to-Bot
delivery, Aleph outcome capture, reply-based review, explicit finalisation,
immediate raw-link purge, immutable export publication, and a paused restart
without duplication. The remaining first-milestone acceptance step is a
reproducible mixed batch with the small developer group. It does not need an
elaborate generative model. The feedback loop is the product; creative question
generation is one component.

## Implementation status

The repository implements the full first-milestone system: versioned records,
durable checkpoints, deterministic generation, Telegram commands and loop
prevention, observable Aleph outcome capture, human review, secure
anonymisation, immutable exports, downstream candidate acknowledgements, run
manifests, scrubbed audits, monitoring, maintenance, hardened service units,
and optional answer-free Aleph coverage targeting.

The reference deployment has its separate token and allowlists installed,
Bot-to-Bot Communication Mode enabled for Null, and Null's numeric ID authorized
through Aleph's default-closed peer allowlist. It is persistent but deliberately
paused between controlled batches. `OPERATIONS.md` records the passed rehearsal
and the remaining rollout sequence.

## License

Project Null is licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Wildcat Labs.
