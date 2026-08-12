#!/usr/bin/env python3
"""Print Project Null's exact scrubbed Ouroboros state once."""

import json

from project_null.coverage import CoverageError, load as load_coverage
from project_null.operations import Config, OperationsError, ouroboros_snapshot
from project_null.store import Store, StoreError


def main() -> int:
    try:
        config = Config.from_env()
        if config.coverage_path is None:
            raise OperationsError("Ouroboros snapshot requires configured coverage")
        coverage = load_coverage(config.coverage_path, config.coverage_release_id)
        store = Store(config.db_path, read_only=True)
        try:
            value = ouroboros_snapshot(store, config, coverage)
        finally:
            store.close()
    except (CoverageError, OperationsError, StoreError, OSError) as error:
        print(json.dumps({"ok": False, "snapshot_error": str(error)},
                         sort_keys=True))
        return 1
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
