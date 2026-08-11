#!/usr/bin/env python3
"""One-shot dependency and state monitor for Project Null."""

import json

from project_null.coverage import CoverageError, load as load_coverage
from project_null.operations import Config, OperationsError, health_report
from project_null.store import Store, StoreError
from project_null.telegram import TelegramError, TelegramHTTP


def main() -> int:
    try:
        config = Config.from_env()
        coverage = (load_coverage(
            config.coverage_path, config.coverage_release_id)
            if config.coverage_path is not None else None)
        store = Store(config.db_path)
        try:
            report = health_report(
                store, TelegramHTTP(timeout=10), config, coverage)
        finally:
            store.close()
    except (CoverageError, OperationsError, StoreError, TelegramError,
            OSError) as error:
        print(json.dumps({"ok": False, "monitor_error": str(error)}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
