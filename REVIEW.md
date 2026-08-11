# Outcome capture and review

Null treats Telegram as the end-to-end boundary. It does not import Aleph's
router, call its answer engine, or grade hidden state.

An Aleph message is correlated only when all of the following hold:

- it arrives in an allowlisted chat;
- Telegram identifies the sender as the configured Aleph username;
- it directly replies to a recorded Null delivery; and
- the reply has not already produced an outcome record.

The visible response shape is classified as answered, pointed, refused,
abstained, or failed. Null records the observable route, latency, citation URLs,
and a bounded error kind. It deliberately does **not** retain Aleph's answer
text. A delivery with no correlated answer after the configured timeout becomes
a `failed` outcome with `route=silence`.

Admission failures are not answer-quality evidence. Aleph's public rate-limit
message is recorded as `outcome=failed`, `route=rate_limited`, and
`error_kind=rate_limited`; reviewers discard that attempt and rerun it in a
later bounded wave rather than creating an Aleph regression candidate.

## Human judgement

A reviewer can reply to either the Null probe or the correlated Aleph response:

```text
/feedback@<NullBot> <decision> <expected_outcome> [note]
```

Basic Telegram groups do not provide direct links to old messages. When the
original response is difficult to find, the reviewer asks Null for its scrubbed
queue:

```text
/queue@<NullBot>
```

Each unresolved record receives a 12-character review code alongside only its
family, expected outcome, observed outcome, route, and whether it needs feedback
or finalisation. The reviewer can then work without a reply:

```text
/feedback@<NullBot> <review_code> <decision> <expected_outcome> [note]
```

An operator can review up to twenty queue entries in one standalone message.
The opening and closing braces surround ordinary code-based feedback arguments
separated by newlines or the copy-safe `|` character. Reply inference is
deliberately unavailable inside a batch:

```text
/feedback@<NullBot> {
<review_code> <decision> <expected_outcome> [note]
<review_code> <decision> <expected_outcome> [note]
}
```

For Telegram clients that collapse copied line breaks, send the entire batch
on one line with `|` separators. The pipe is reserved as a delimiter and cannot
appear inside a batch note:

```text
/feedback@<NullBot> {<code> regression answered note | <code> discard refused note}
```

Null processes the lines sequentially and returns an ordered receipt with one
line per submitted entry. An invalid or duplicate entry is reported on its own
receipt line and does not erase valid siblings. The operation is intentionally
not transactional across entries: successfully recorded feedback remains
recorded if a later line fails.

Decisions are `regression`, `corpus_gap`, `routing_change`,
`live_data_requirement`, `rejection_test`, `duplicate`, or `discard`.
Expected outcomes are `answered`, `pointed`, `refused`, `abstained`, or
`failed`.

Feedback is accepted only from allowlisted reviewers. The reviewer identifier
and note are raw records with the same exact 30-day expiry as other identifiable
data. Review changes the proposed expected outcome; it never edits Aleph's
corpus and never promotes a candidate automatically.

Finalised `regression` and `rejection_test` records are also the only positive
signals used by Null's question curriculum. They advance the relevant family
from foundation to contextual and then adversarial. Other decisions record a
gap, change request, duplicate, or discard and therefore do not certify mastery.
The observed Aleph outcome alone never advances the curriculum.

When the latest judgement is correct, the reviewer either replies once more or
uses the same review code:

```text
/finalize@<NullBot>
/finalize@<NullBot> <review_code>
```

Finalisation has the matching code-only batch form:

```text
/finalize@<NullBot> {
<review_code>
<review_code>
}
```

The same copy-safe form is accepted for finalisation:

```text
/finalize@<NullBot> {<review_code> | <review_code>}
```

Each successful line crosses the irreversible promotion boundary before the
next line is attempted. Null returns one ordered result per code; a failed line
does not roll back or hide successful finalisations. Each successful result
also reports the retained candidate-pile total after that entry. Duplicate and
discard judgements create no candidate, so their total remains unchanged.

The code grants no capability and contains no Telegram identifier. Commands
remain restricted to allowlisted operators in allowlisted chats. Finalisation
deletes the raw probe and makes its review code immediately unresolvable.

Finalisation is the explicit promotion boundary. Null creates a redacted,
non-linkable long-term question and proposal, then deletes the probe, delivery,
outcome, feedback, and delivery control before acknowledging success. Duplicate
and discard decisions create no candidate but still purge the raw linkage.
Without finalisation, raw state expires automatically at its exact deadline and
the latest eligible judgement is retained then.

The candidate pile is the durable count of retained, finalised
`export_candidate` records awaiting explicit downstream disposition. It is
visible through `/status`, survives restarts, and is not reduced merely because
the same set was published as an immutable export. Candidates remain proposals;
the counter never implies automatic Aleph ingestion. A complete report from
Aleph may resolve accepted, duplicate, and rejected candidates by adding
separate terminal disposition records. Deferred and `needs_review` candidates
remain in the pile.
