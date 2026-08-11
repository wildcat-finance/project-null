# Operations and rollout

The reference deployment is installed and persistent. It completed its
private-group single-probe rehearsal on 11 August 2026 and remains paused between
controlled batches.

Its proven path is Null probe → authenticated Aleph reply → operator feedback →
explicit finalisation → immediate raw-link purge → immutable regression export.
The first published export is `2805b88f4d91f2890e03`. A controlled paused
restart preserved every record count and produced no duplicate delivery.

## Per-deployment external inputs

Each new deployment requires exactly these external values:

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

## Rehearsal order for a new deployment

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
12. Reply with `/finalize@<NullBot>`, run one maintenance pass, and verify the
    immutable regression export contains one candidate while the raw probe link
    is gone.
13. Re-pause before changing the question mix or widening access.

If the rehearsal is abandoned, remove Null's ID from `ALEPH_PEER_BOT_IDS` and
restart Aleph. Do not leave a peer authorized merely because both bots have been
removed from the group.

## Small-group rollout order

The reference deployment is at this boundary. Keep Null paused while adding the
small developer group, then:

1. confirm `/status@<NullBot>` reports paused and the intended rate limit;
2. set `/mode@<NullBot> mixed`;
3. send `/resume@<NullBot>`, one `/burst@<NullBot> 3`, and immediately
   `/pause@<NullBot>`; the versioned mixed policy assigns three distinct
   families rather than sampling the same family twice;
4. run `/queue@<NullBot>`, review each correlated answer or timeout by its
   short code, and explicitly finalise only the cases worth retaining;
5. run maintenance and inspect candidate counts and manifest hashes, never raw
   question text in operational logs;
6. tune the family mix or Aleph behavior while still paused; and
7. widen the trial only after no duplicate/recursive delivery, no unauthorized
   command acceptance, no identifier-bearing export, and no unexplained outcome
   remain.

Do not run a second batch merely to increase volume. Every unresolved result is
reviewed or allowed to expire under the 30-day boundary first.

## Monitoring and failure alerts

`monitor.py` emits scrubbed JSON and exits nonzero when the database, bot
identity, Group Privacy, or webhook boundary fails. The five-minute systemd
timer makes that status available to the host's alerting agent. Bot-to-Bot mode
is not exposed by `getMe`, so the monitor labels the setting as not observable
through the Bot API. It separately reports count-only evidence of captured Aleph
replies and their latest observation time; this proves historical delivery but
does not claim that the current BotFather switch can be queried.

Telegram long-poll read timeouts are normal empty iterations and do not restart
the service or advance its checkpoint. Repeated process restarts therefore
indicate a different failure and require inspection; send-timeout probes remain
`uncertain` for manual reconciliation rather than automatic replay.

The daily maintenance timer independently enforces retention and publishes the
current immutable export. Service, monitor, and maintenance units run without
capabilities, with read-only system paths, closed devices, restricted
namespaces, and owner-only file creation.

## Backups

Backups of `/var/lib/project-null` contain identifiable raw data until each
record's 30-day deadline. Backup retention must therefore be no longer than 30
days, or backups must run the same expiry/deletion policy. Long-term exports can
be backed up separately because their schemas forbid Telegram identifiers.
