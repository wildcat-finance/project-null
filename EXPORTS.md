# Aleph candidate exports

Exports are proposals for human review, never direct Aleph inputs.

Every content-addressed export directory contains:

- `regressions.json` — expected routing/outcome and rejection/live-data cases;
- `corpus-proposals.json` — reviewed questions that may expose missing
  documentation; and
- `manifest.json` — schema version, candidate IDs, counts, file hashes, and the
  export ID derived from those exact inputs.

The two queues stay separate because a regression test may need no new corpus,
while a corpus proposal must never be accepted as truth merely because Null or a
reviewer suggested it. Evidence targets are empty until a reviewer approves
specific source material.

The initial batching rule is to open an Aleph corpus-release review when ten
human-approved factual proposals have accumulated. This is a review trigger,
not automatic ingestion, and a consequential correction may be reviewed sooner.

Publishing the same candidate set returns the same immutable directory. If an
existing export contains different bytes, publication fails rather than
repairing history in place.
