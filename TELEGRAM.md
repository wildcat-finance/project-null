# Telegram shell

Null uses Telegram long polling and keeps Group Privacy enabled. It sends each
synthetic probe as an explicit command:

```text
/ask@ProjectAlephWildcat_bot <generated question>
```

Telegram normally hides bot messages from other bots. Current Telegram supports
[Bot-to-Bot Communication Mode](https://core.telegram.org/api/bots%2Fbot-to-bot):
in a group, an explicitly addressed command is delivered when at least one of
the two bots has that mode enabled. The reference deployment has the mode enabled
for Null. For a new bot, open BotFather, send `/mybots`, select the bot, then use
the blue **Open** button to launch BotFather's management Mini App and enable
**Bot-to-Bot Communication Mode** there. The switch is not present in the
classic **Bot Settings** button list. Aleph does not need administrator access
and neither bot needs Group Privacy disabled.

Aleph separately keeps bot-authored input default-closed. Before a new rehearsal, add
Null's numeric bot ID to Aleph's `ALEPH_PEER_BOT_IDS` setting and require Aleph's
dependency monitor to report one approved peer. The allowlist does not broaden
Null's capability: Aleph accepts only the explicit command form above.

## Commands

- `/probe@<NullBot>` sends one probe using the active mode.
- `/burst@<NullBot> <n>` sends 1–10 bounded probes.
- `/mode@<NullBot> mixed|<family>` changes the versioned scenario mix.
- `/pause@<NullBot>` and `/resume@<NullBot>` control generation durably.
- `/status@<NullBot>` reports mode, checkpoint, unresolved raw reviews, the
  durable finalised-candidate pile, curriculum version, and scrubbed family-tier
  counts. When coverage guidance is configured it also reports the exact
  silhouette/release pair and target count, never target question text.
- `/ping@<NullBot>` is a read-only liveness poll. It replies with `Pong!`,
  monotonic process uptime, running/paused generation state, immutable run and
  generator identities, source revision, curriculum and coverage pins,
  Telegram checkpoint, and scrubbed review/candidate counts. It does not
  generate a probe, consume the generation rate limit, read raw question text,
  or expose operator and chat identifiers.
- `/queue@<NullBot>` reports unresolved records with short review codes and no
  question text or Telegram identifiers.
- `/feedback@<NullBot> [review_code] <decision> <expected_outcome> [note]`
  records a judgement by code or by reply to a probe or its Aleph response.
- `/feedback@<NullBot> { ... }` records up to twenty explicitly coded
  judgements separated by newlines or `|`, sequentially, and returns one
  ordered receipt line per entry. Prefer `|` when copying into Telegram because
  it remains explicit if the client collapses line breaks.
- `/finalize@<NullBot> [review_code]` finalises the latest judgement selected by
  code or reply, creates its anonymised candidate, and irreversibly purges the
  raw correlation.
- `/finalize@<NullBot> { ... }` sequentially finalises up to twenty review
  codes separated by newlines or `|`, with one ordered receipt line per entry.

Use the explicit `@<NullBot>` form in groups. Under Group Privacy, a bare
general command may be delivered to whichever bot most recently spoke instead.

Commands are accepted only from allowlisted operator IDs in allowlisted chats.
Ambient text, commands for other bots, unapproved users, and bot-authored
commands are ignored.

Review codes are 12 hexadecimal characters derived from the existing private
probe identifier. They confer no authority: chat and operator allowlists still
gate every command. Codes resolve only while the raw probe exists, become
invalid immediately after finalisation, and avoid dependence on historical
message links that basic Telegram groups do not provide.

Brace batches require explicit review codes; they never infer a probe from a
reply. Newlines remain supported, while a single `|` is the copy-safe separator
for a one-line Telegram message. The `|` character is therefore reserved and
must not appear inside a batch note. Blank lines are ignored in newline mode;
empty pipe entries and ambiguous mixtures of line and pipe separators are
rejected before processing. A one-line batch containing multiple code-shaped
fragments but no separator is likewise rejected as probably collapsed. Nested
braces are rejected, and one malformed,
unknown, duplicate, or already-finalised code fails only its own entry. Batch
execution is ordered but not atomic: an accepted feedback record or completed
finalisation is never rolled back because a later entry fails.

Every successful batch-finalisation receipt reports `candidate pile=<n>` after
that entry. `/status` reports the same `candidate_pile=<n>` value after a
restart. The pile counts retained `export_candidate` records, not raw probes or
automatic corpus additions. Publishing an immutable export does not clear or
resolve the pile; a downstream disposition workflow must do that explicitly.

## Delivery semantics

Before calling `sendMessage`, Null persists the scenario and probe and marks its
delivery state as `sending`. If the process dies around that network boundary,
it will not automatically send the same probe again. An operator may need to
reconcile a `sending` or `uncertain` probe, but restarts cannot cause a bot loop
or duplicate flood.

Preparing a catalogue or coverage-guided challenge also writes one
non-identifying exposure marker for that challenge ID and source hash. The
marker contains no question text or Telegram identifier and is not removed with
raw data. It stops Null from forgetting a duplicate or discarded challenge
after finalisation. A monotonic checkpoint is checked before every update in a
returned batch, so duplicate copies of one Telegram update cannot consume two
novelty slots or send twice.

A Bot API read timeout during `getUpdates` is treated as an empty poll: no
update is observed and the durable checkpoint does not advance. The same
timeout during `sendMessage` is not treated as success; the prepared probe stays
`uncertain` and is never automatically retried.

The adapter also enforces:

- a monotonic update checkpoint;
- per-chat/operator rate limits;
- a maximum burst of ten;
- explicit Aleph command addressing;
- no reaction to bot-authored generation commands; and
- startup refusal when a webhook is active or Group Privacy is disabled.

This follows Telegram's own [loop-prevention requirements](https://core.telegram.org/bots/features#bot-to-bot-communication).

## Runtime inputs

Each live process requires:

- `NULL_TELEGRAM_TOKEN` — Null's separate Bot API token;
- the allowlisted developer-group chat ID;
- the allowlisted reviewer/operator user IDs; and
- Aleph's bot username, defaulting to `ProjectAlephWildcat_bot`;
- Aleph's stable numeric bot ID in `NULL_ALEPH_BOT_ID`;
- a current public market in `NULL_PROBE_MARKET_ADDRESS`; and
- a non-zero public account in `NULL_PROBE_ACCOUNT_ADDRESS`.

Null requires both Aleph identity fields to match before recording a bot reply.
Group commands without an explicit `@<NullBot>` target are ignored.
The two probe addresses are validated at startup and remain inside the raw
30-day review boundary. Public run records retain only their joint digest, and
the deterministic fixture addresses used by unit tests are not a live fallback.

Tokens never enter the SQLite store, logs, generated records, or repository.
