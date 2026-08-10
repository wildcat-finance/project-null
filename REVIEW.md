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

## Human judgement

A reviewer replies to either the Null probe or the correlated Aleph response:

```text
/feedback@<NullBot> <decision> <expected_outcome> [note]
```

Decisions are `regression`, `corpus_gap`, `routing_change`,
`live_data_requirement`, `rejection_test`, `duplicate`, or `discard`.
Expected outcomes are `answered`, `pointed`, `refused`, `abstained`, or
`failed`.

Feedback is accepted only from allowlisted reviewers. The reviewer identifier
and note are raw records with the same exact 30-day expiry as other identifiable
data. Review changes the proposed expected outcome; it never edits Aleph's
corpus and never promotes a candidate automatically.
