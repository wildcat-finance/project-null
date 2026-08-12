# Operations and rollout

The reference deployment is installed and persistent. It completed its
private-group single-probe rehearsal on 11 August 2026 and remains paused between
controlled batches.

Its proven path is Null probe → authenticated Aleph reply → operator feedback →
explicit finalisation → immediate raw-link purge → immutable regression export.
The first published export is `2805b88f4d91f2890e03`. A controlled paused
restart preserved every record count and produced no duplicate delivery.

## Per-deployment external inputs

Each new deployment requires these eight external values:

1. a separate Telegram Bot API token in `NULL_TELEGRAM_TOKEN`;
2. the private developer-group chat ID;
3. one or more reviewer/operator Telegram user IDs; and
4. Bot-to-Bot Communication Mode enabled for Null in BotFather.
5. `NULL_PROBE_MARKET_ADDRESS`, one current public Wildcat market used only by
   generated live and historical probes; and
6. `NULL_PROBE_ACCOUNT_ADDRESS`, one non-zero public account used only by
   account-scoped probes.
7. `NULL_ALEPH_EVOLUTION`, the active Aleph evolution number; and
8. `NULL_ALEPH_GENERATION`, the active generation within that evolution.

Both probe addresses are validated before the database or Telegram connection
opens. They remain in the 30-day raw review boundary and never appear in public
run metadata; the run binds only their joint SHA-256. Fixture addresses are
reserved for deterministic unit tests and are never a production fallback.

The repository already defaults to `ProjectAlephWildcat_bot`. Group Privacy
stays enabled. Neither bot needs group administrator access.

Coverage-guided generation adds two optional, paired inputs:

- `NULL_ALEPH_COVERAGE`, the path to one published Aleph silhouette; and
- `NULL_ALEPH_COVERAGE_RELEASE`, the exact active Aleph release ID it must
  describe.

Set neither to keep catalogue-only generation. The evolution/generation pair is
still mandatory because ordinary catalogue probes also need provenance. Setting
only one coverage input is a startup failure. Null validates the content address,
release and evolution/generation binding, count
reconciliation, and exclusion boundary before opening the database or Telegram
connection. A stale silhouette therefore cannot silently guide a newer Aleph
release.

## Filesystem boundary

- `/opt/project-null` — root-owned, read-only source and virtual environment;
- `/etc/project-null/project-null.env` — root-owned `0600` configuration;
- `/etc/project-null/aleph-coverage.json` — optional root-owned `0444`
  answer-free coverage silhouette;
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
4. If coverage guidance is enabled, copy the silhouette published by the active
   Aleph release to `/etc/project-null/aleph-coverage.json`, set both paired
   variables, and run `monitor.py` once before starting the bot. Never copy
   Aleph chunks, golden questions, answers, citations, or evaluation cases.
5. Run the full test suite.
6. Run `monitor.py`; verify database integrity, token identity, Group Privacy,
   and absent webhook.
7. Read Null's numeric bot ID from `getMe`. On the Aleph host, set
   `ALEPH_PEER_BOT_IDS=<NullBotId>` in `/etc/aleph/telegram.env`, restart Aleph,
   and require its monitor to report `peer_bot_count: 1`. Aleph's peer path is
   default-closed and accepts only an explicitly targeted `/ask@AlephBot`.
8. Add Null and Aleph to the private group and enable Bot-to-Bot Communication
   Mode for Null.
9. Start the service and confirm `/status@<NullBot>` reports paused and either
   the exact `evolution N/generation M`, silhouette/release pair or
   `coverage=disabled`.
10. Send `/mode@<NullBot> ordinary`, then `/resume@<NullBot>`, then one
   `/probe@<NullBot>`.
11. Confirm Aleph directly replies, Null records one outcome, and no loop occurs.
12. Reply with `/feedback@<NullBot> regression answered rehearsal` and inspect
    the count-only audit.
13. Reply with `/finalize@<NullBot>`, run one maintenance pass, and verify the
    immutable regression export contains one candidate while the raw probe link
    is gone.
14. Re-pause before changing the question mix or widening access.

If the rehearsal is abandoned, remove Null's ID from `ALEPH_PEER_BOT_IDS` and
restart Aleph. Do not leave a peer authorized merely because both bots have been
removed from the group.

## Small-group rollout order

The reference deployment is at this boundary. Keep Null paused while adding the
small developer group, then:

1. confirm `/status@<NullBot>` reports paused and the intended rate limit;
   also record the curriculum version and foundation/contextual/adversarial
   family counts plus the active silhouette/release pair as the wave's starting
   boundary;
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

Curriculum advancement is deliberately conservative. Only finalised retained
reviews marked `regression` or `rejection_test` count as family mastery; volume,
Aleph's observed route, and Null's declared expectation do not. A gap remains a
gap until a human review changes the evidence. The catalogue exposure ledger is
non-identifying and survives raw deletion, so a restart or finalisation does not
make an old synthetic challenge look unseen.

When coverage mode is active, mixed bursts reserve every third slot for an
unseen silhouette-derived target. Declared-gap topics come first; route, live,
sparse, and other coverage edges follow. The remaining slots still use the
review-driven family curriculum. An explicit single-family mode bypasses
coverage targeting. Change the configured silhouette only while paused, rerun
the monitor, restart the service, and verify the new identity in `/status`
before resuming.

## Acknowledge Aleph dispositions

Aleph's importer emits a complete JSON report bound to one immutable Null
export. Copy the reviewed report to the fixed service-owned inbox, then run the
manual one-shot unit:

```bash
sudo install -o project-null -g project-null -m 600 \
  /path/to/reviewed-report.json \
  /var/lib/project-null/disposition-report.json
sudo systemctl start project-null-disposition.service
sudo journalctl -u project-null-disposition.service --since today --no-pager
```

The command rejects a wrong Aleph evolution/generation, export ID, modified
export bytes, missing or extra
candidates, inconsistent counts, changed question text, and conflicting
terminal replays before committing anything. An identical replay is idempotent.
Accepted, duplicate, and rejected cases become resolved; deferred and
`needs_review` cases remain in `candidate_pile`. The immutable export and every
candidate record remain unchanged.

## Monitoring and failure alerts

`monitor.py` emits scrubbed JSON and exits nonzero when the database, bot
identity, Group Privacy, webhook, or configured coverage boundary fails. The
five-minute systemd timer makes that status available to the host's alerting
agent. Bot-to-Bot mode
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

Scrubbed audit snapshots are transition records rather than heartbeats. The
service writes one for each process run, then another only when its paused
state, mode, or record counts change. The five-minute monitor remains the
heartbeat. Existing snapshots are immutable; unchanged long-poll iterations do
not create redundant files.

## Local Ouroboros snapshot

`snapshot.py` is the read-only handoff from Null to Aleph's local Ouroboros
controller. Invoke it through a service-manager wrapper that supplies the same
root-owned environment file as the bot; do not expand secrets into shell
history.

The command opens the existing SQLite database in read-only/query-only mode and
emits one canonical JSON object. It contains the source revision, run ID, pause
and mode state, exact unreviewed and candidate counts, and the coverage
release's evolution/generation. It has no wall clock, so unchanged state
produces identical bytes and the same `snapshot_sha256`.

The snapshot contains no question, answer, feedback note, Telegram identifier,
address, token, model output, or reasoning. It fails when database integrity,
run identity, pause/mode state, coverage, or configured Aleph identity cannot be
proven. The Aleph controller consumes this object as a state assertion; it does
not receive Null's database or credentials.

## Backups

Backups of `/var/lib/project-null` contain identifiable raw data until each
record's 30-day deadline. Backup retention must therefore be no longer than 30
days, or backups must run the same expiry/deletion policy. Long-term exports can
be backed up separately because their schemas forbid Telegram identifiers.
