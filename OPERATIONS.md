# Operations and rollout

Null is deployable but must remain paused until its private-group rehearsal.

## Human-supplied launch inputs

The live launch requires exactly these external values:

1. a separate Telegram Bot API token in `NULL_TELEGRAM_TOKEN`;
2. the private developer-group chat ID;
3. one or more reviewer/operator Telegram user IDs; and
4. Bot-to-Bot Communication Mode enabled for Null in BotFather.

The repository already defaults to `ProjectAlephWildcat_bot`. Group Privacy
stays enabled. Neither bot needs group administrator access.

## Filesystem boundary

- `/opt/project-null` — root-owned, read-only source and virtual environment;
- `/etc/project-null/project-null.env` — root-owned `0600` configuration;
- `/var/lib/project-null/null.db` — service-owned raw and review state; and
- `/var/lib/project-null/artifacts` — run manifests, scrubbed audits, and
  immutable exports.

`Store` enforces mode `0600` on the SQLite database and its WAL/shared-memory
sidecars even when an operator initializes it outside the systemd `UMask`.

The service starts paused on a fresh database. Only an allowlisted, explicitly
addressed `/resume@<NullBot>` command can enable probe generation.

## Rehearsal order

1. Install source and dependencies without the token.
2. Create the service user and writable state directory.
3. Place the root-only environment file.
4. Run the full test suite.
5. Run `monitor.py`; verify database integrity, token identity, Group Privacy,
   and absent webhook.
6. Read Null's numeric bot ID from `getMe`. On the Aleph host, set
   `ALEPH_PEER_BOT_IDS=<NullBotId>` in `/etc/aleph/telegram.env`, restart Aleph,
   and require its monitor to report `peer_bot_count: 1`. Aleph's peer path is
   default-closed and accepts only an explicitly targeted `/ask@AlephBot`.
7. Add Null and Aleph to the private group and enable Bot-to-Bot Communication
   Mode for Null.
8. Start the service and confirm `/status@<NullBot>` reports paused.
9. Send `/mode@<NullBot> ordinary`, then `/resume@<NullBot>`, then one
   `/probe@<NullBot>`.
10. Confirm Aleph directly replies, Null records one outcome, and no loop occurs.
11. Reply with `/feedback@<NullBot> regression answered rehearsal` and inspect
    the count-only audit.
12. Re-pause before changing the question mix or widening access.

If the rehearsal is abandoned, remove Null's ID from `ALEPH_PEER_BOT_IDS` and
restart Aleph. Do not leave a peer authorized merely because both bots have been
removed from the group.

## Monitoring and failure alerts

`monitor.py` emits scrubbed JSON and exits nonzero when the database, bot
identity, Group Privacy, or webhook boundary fails. The five-minute systemd
timer makes that status available to the host's alerting agent. Bot-to-Bot mode
is not exposed by `getMe`, so the monitor reports it as requiring operator
attestation and the rehearsal proves actual delivery.

The daily maintenance timer independently enforces retention and publishes the
current immutable export. Service, monitor, and maintenance units run without
capabilities, with read-only system paths, closed devices, restricted
namespaces, and owner-only file creation.

## Backups

Backups of `/var/lib/project-null` contain identifiable raw data until each
record's 30-day deadline. Backup retention must therefore be no longer than 30
days, or backups must run the same expiry/deletion policy. Long-term exports can
be backed up separately because their schemas forbid Telegram identifiers.
