#!/usr/bin/env python3
"""Run Project Null's Telegram feedback loop."""

from __future__ import annotations

import signal
import sys
import threading

from project_null.anonymize import Anonymizer
from project_null.export import publish
from project_null.generator import Generator
from project_null.operations import Config, OperationsError, publish_run, write_audit
from project_null.store import Store, StoreError
from project_null.telegram import TelegramError, TelegramHTTP, TelegramShell


def main() -> int:
    store = None
    try:
        config = Config.from_env()
        store = Store(config.db_path)
        # A fresh deployment starts paused; an allowlisted human explicitly
        # resumes it after the private-group rehearsal.
        if store.control("paused") is None:
            store.set_control("paused", "true")
        api = TelegramHTTP()
        shell = TelegramShell(
            store, Generator(), api, aleph_username=config.aleph_username,
            aleph_bot_id=config.aleph_bot_id,
            allowed_chat_ids=set(config.allowed_chat_ids),
            operator_user_ids=set(config.operator_user_ids),
            poll_timeout=config.poll_timeout)
        identity = shell.startup()
        run = publish_run(config)
        store.set_control("run_id", run["run_id"])
        print(f"Project Null @{identity.username} run={run['run_id']} paused="
              f"{store.control('paused')}", flush=True)
        stop = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stop.set())
        ticks = 0
        while not stop.is_set():
            shell.poll_once()
            ticks += 1
            if ticks % 2 == 0:
                shell.capture.mark_timeouts()
                Anonymizer(store).run()
                publish(store, config.artifacts_path)
                write_audit(store, config, run["run_id"])
        return 0
    except (OperationsError, StoreError, TelegramError, OSError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
