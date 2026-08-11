# Telegram shell

Null uses Telegram long polling and keeps Group Privacy enabled. It sends each
synthetic probe as an explicit command:

```text
/ask@ProjectAlephWildcat_bot <generated question>
```

Telegram normally hides bot messages from other bots. Current Telegram supports
[Bot-to-Bot Communication Mode](https://core.telegram.org/api/bots%2Fbot-to-bot):
in a group, an explicitly addressed command is delivered when at least one of
the two bots has that mode enabled. Enable the mode for Null in BotFather before
the live rehearsal. Aleph does not need administrator access and neither bot
needs Group Privacy disabled.

Aleph separately keeps bot-authored input default-closed. Before rehearsal, add
Null's numeric bot ID to Aleph's `ALEPH_PEER_BOT_IDS` setting and require Aleph's
dependency monitor to report one approved peer. The allowlist does not broaden
Null's capability: Aleph accepts only the explicit command form above.

## Commands

- `/probe@<NullBot>` sends one probe using the active mode.
- `/burst@<NullBot> <n>` sends 1–10 bounded probes.
- `/mode@<NullBot> mixed|<family>` changes the versioned scenario mix.
- `/pause@<NullBot>` and `/resume@<NullBot>` control generation durably.
- `/status@<NullBot>` reports mode, checkpoint, and unresolved review count.
- `/feedback@<NullBot> <decision> <expected_outcome> [note]` records a judgement when
  sent as a reply to a probe or its Aleph response.

Use the explicit `@<NullBot>` form in groups. Under Group Privacy, a bare
general command may be delivered to whichever bot most recently spoke instead.

Commands are accepted only from allowlisted operator IDs in allowlisted chats.
Ambient text, commands for other bots, unapproved users, and bot-authored
commands are ignored.

## Delivery semantics

Before calling `sendMessage`, Null persists the scenario and probe and marks its
delivery state as `sending`. If the process dies around that network boundary,
it will not automatically send the same probe again. An operator may need to
reconcile a `sending` or `uncertain` probe, but restarts cannot cause a bot loop
or duplicate flood.

The adapter also enforces:

- a monotonic update checkpoint;
- per-chat/operator rate limits;
- a maximum burst of ten;
- explicit Aleph command addressing;
- no reaction to bot-authored generation commands; and
- startup refusal when a webhook is active or Group Privacy is disabled.

This follows Telegram's own [loop-prevention requirements](https://core.telegram.org/bots/features#bot-to-bot-communication).

## Runtime inputs

The live process will require:

- `NULL_TELEGRAM_TOKEN` — Null's separate Bot API token;
- the allowlisted developer-group chat ID;
- the allowlisted reviewer/operator user IDs; and
- Aleph's bot username, defaulting to `ProjectAlephWildcat_bot`.

Tokens never enter the SQLite store, logs, generated records, or repository.
