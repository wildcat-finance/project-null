#!/usr/bin/env python3
"""Apply one reviewed Aleph disposition report to retained Null candidates."""

from __future__ import annotations

import argparse
import dataclasses
import json

from project_null.disposition import DispositionError, apply
from project_null.operations import Config, OperationsError
from project_null.store import Store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        config = Config.from_env()
        store = Store(config.db_path)
        try:
            result = apply(
                store, config.artifacts_path, args.report,
                expected_evolution=config.aleph_evolution,
                expected_generation=config.aleph_generation)
        finally:
            store.close()
    except (DispositionError, OperationsError) as error:
        parser.error(str(error))
    payload = dataclasses.asdict(result)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
