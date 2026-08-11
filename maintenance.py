#!/usr/bin/env python3
"""Run Null's retention and immutable-export maintenance once."""

import json

from project_null.anonymize import Anonymizer
from project_null.export import publish
from project_null.operations import Config
from project_null.store import Store


def main() -> int:
    config = Config.from_env()
    store = Store(config.db_path)
    try:
        report = Anonymizer(store).run()
        destination = publish(store, config.artifacts_path)
    finally:
        store.close()
    print(json.dumps({
        "anonymized": report.anonymized, "candidates": report.candidates,
        "deleted_raw": report.deleted_raw,
        "deleted_controls": report.deleted_controls,
        "export_id": destination.name,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
