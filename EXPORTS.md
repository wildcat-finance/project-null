# Aleph candidate exports

Exports are proposals for human review, never direct Aleph inputs.

Every content-addressed export directory contains:

- `regressions.json` — expected routing/outcome and rejection/live-data cases;
- `corpus-proposals.json` — reviewed questions that may expose missing
  documentation; and
- `manifest.json` — schema version, candidate IDs, counts, file hashes, and the
  export ID derived from those exact inputs.

The two queues stay separate inside an export because a regression test may need
no new corpus, while a corpus proposal must never be accepted as truth merely
because Null or a reviewer suggested it. Evidence targets are empty until a
reviewer approves specific source material. A version 2 acknowledgement covers
both queues atomically: accepted regressions name a golden test, while accepted
corpus proposals name the reviewed evidence or release that closes the gap.

The initial batching rule is to open an Aleph corpus-release review when ten
human-approved factual proposals have accumulated. This is a review trigger,
not automatic ingestion, and a consequential correction may be reviewed sooner.

Publishing the same candidate set returns the same immutable directory. If an
existing export contains different bytes, publication fails rather than
repairing history in place.

Publication alone does not mark candidates resolved. Aleph returns a complete,
export-bound disposition report after validating the immutable bytes. Null then
validates that report against its own export and adds separate terminal records
for accepted, duplicate, and rejected candidates. Deferred and `needs_review`
cases remain in `candidate_pile`; `/status` reports terminal records separately.
Neither acknowledgement nor publication edits or deletes candidate/export bytes.
Version 1 regression-only acknowledgements remain replayable. The current
explicit Ouroboros evolution is evolution 2,
`mixed-candidate-dispositions-v2`; it changes the loop's review vocabulary.
Generation starts at 1 inside each evolution. The separate Aleph
`activation_sequence` remains globally monotonic but is not part of Null's
human-facing identity. New candidates retain the exact evolution/generation
they tested; legacy immutable candidates remain unchanged.
