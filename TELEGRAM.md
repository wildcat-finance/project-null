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
- `/status@<NullBot>` reports mode, checkpoint, and unresolved review count.
- `/queue@<NullBot>` reports unresolved records with short review codes and no
  question text or Telegram identifiers.
- `/feedback@<NullBot> [review_code] <decision> <expected_outcome> [note]`
  records a judgement by code or by reply to a probe or its Aleph response.
- `/finalize@<NullBot> [review_code]` finalises the latest judgement selected by
  code or reply, creates its anonymised candidate, and irreversibly purges the
  raw correlation.

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

## Delivery semantics

Before calling `sendMessage`, Null persists the scenario and probe and marks its
delivery state as `sending`. If the process dies around that network boundary,
it will not automatically send the same probe again. An operator may need to
reconcile a `sending` or `uncertain` probe, but restarts cannot cause a bot loop
or duplicate flood.

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
- Aleph's bot username, defaulting to `ProjectAlephWildcat_bot`; and
- Aleph's stable numeric bot ID in `NULL_ALEPH_BOT_ID`.

Null requires both Aleph identity fields to match before recording a bot reply.
Group commands without an explicit `@<NullBot>` target are ignored.

Tokens never enter the SQLite store, logs, generated records, or repository.
