# Anonymisation and deletion

`project_null/anonymize.py` enforces the 30-day boundary; it is not a policy
reminder for an operator to perform manually.

At a raw probe's expiry:

1. unreviewed, duplicate, and discarded probes receive no long-term copy;
2. reviewed candidates have URLs, Telegram usernames, Ethereum addresses, and
   long numeric identifiers replaced with category markers;
3. new question and candidate IDs are derived only from permitted long-term
   fields, never raw probe, message, chat, or reviewer IDs;
4. the permitted records are validated and appended;
5. expired raw records and delivery controls are deleted; and
6. SQLite secure deletion, WAL truncation, and vacuuming remove deleted bytes
   from Null's own storage.

Each raw record keeps its own non-sliding deadline. A review one second after a
probe therefore expires one second later; it does not extend the probe's life.
Long-term records preserve whether the source was synthetic,
production-derived, or human-authored.

The test suite searches the compacted database bytes for unique fixture chat
IDs and usernames after expiry. This demonstrates that Null's retained stores
cannot join an anonymised candidate back to a Telegram identity.
