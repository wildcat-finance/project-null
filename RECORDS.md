# Records and retention

Project Null records every stage of a probe without treating generated text as
truth. `project_null/schema.py` is the executable schema. Every record carries
`schema_version: 1` when serialized.

| Record | Purpose | Raw/identifying data | Retention |
|---|---|---:|---:|
| Scenario | Reproducible intent, family, seed and variables | No | Indefinite |
| Probe | Generated question and generator identity | Question text | 30 days |
| Delivery | Telegram correlation | Chat/message/thread IDs | 30 days |
| Aleph outcome | End-to-end observed response classification | Reply ID and URLs | 30 days |
| Feedback | Human judgement | Reviewer ID and note | 30 days |
| Anonymized question | Reviewed long-term question | Forbidden | Indefinite |
| Challenge exposure | Catalogue ID, hash, family and tier already exercised | Forbidden | Indefinite |
| Export candidate | Proposed regression or corpus gap | Forbidden | Indefinite |
| Candidate disposition | Terminal downstream acceptance, duplicate, or rejection | Forbidden | Indefinite |

The raw clock is exact: `raw_expires_at = created_at + 30 × 24 hours` in UTC.
It is not “the end of the month” and cannot be extended by a later review.
Long-term records have no Telegram identifiers and preserve provenance so
synthetic material cannot be relabelled as production traffic.

`ChallengeExposure` is the narrow record that lets novelty survive deletion: it
stores no rendered question and no Telegram linkage, only identifiers from the
public checked-in synthetic catalogue. It is idempotent per challenge and
catalogue hash. It cannot be used as factual evidence or an Aleph answer.

The SQLite store is append-only for records. Checkpoints may move only forward;
pause/mode controls are explicit mutable state. Later anonymisation deletes raw
records only after producing and validating their permitted long-term form.
Downstream acknowledgement adds a separate terminal record; it never edits or
deletes the candidate it resolves.
