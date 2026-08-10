#!/usr/bin/env python3
"""One-shot dependency and state monitor for Project Null."""

import json

from project_null.operations import Config, health_report
from project_null.store import Store
from project_null.telegram import TelegramHTTP


def main() -> int:
    config = Config.from_env()
    store = Store(config.db_path)
    try:
        report = health_report(store, TelegramHTTP(timeout=10), config)
    finally:
        store.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
