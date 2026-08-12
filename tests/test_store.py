import pytest

from project_null.schema import Probe, Provenance, raw_expiry, stable_id
from project_null.store import Store, StoreError

NOW = "2026-08-11T00:00:00Z"


def probe():
    return Probe(
        probe_id=stable_id("probe", {"seed": 1}),
        scenario_id=stable_id("scenario", {"seed": 1}),
        run_id=stable_id("run", {"seed": 1}), text="What is a market?",
        provenance=Provenance.SYNTHETIC, generated_at=NOW,
        raw_expires_at=raw_expiry(NOW),
        generator={"kind": "template", "version": "v1", "seed": 1},
    )


def test_records_are_immutable(tmp_path):
    path = tmp_path / "null.db"
    store = Store(str(path))
    assert path.stat().st_mode & 0o777 == 0o600
    for suffix in ("-wal", "-shm"):
        sidecar = tmp_path / ("null.db" + suffix)
        if sidecar.exists():
            assert sidecar.stat().st_mode & 0o777 == 0o600
    item = probe()
    store.append(item)
    assert store.get(item.probe_id)["text"] == "What is a market?"
    with pytest.raises(StoreError, match="already exists"):
        store.append(item)
    store.close()


def test_read_only_store_does_not_create_or_mutate_database(tmp_path):
    path = tmp_path / "null.db"
    writable = Store(str(path))
    writable.set_control("paused", "true")
    writable.close()
    read_only = Store(str(path), read_only=True)
    assert read_only.control("paused") == "true"
    with pytest.raises(StoreError):
        read_only.set_control("paused", "false")
    read_only.close()
    with pytest.raises(StoreError, match="absent"):
        Store(str(tmp_path / "missing.db"), read_only=True)


def test_expiry_and_probe_lookup(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    item = probe()
    store.append(item)
    assert store.expired_raw("2026-09-09T23:59:59Z") == []
    assert store.expired_raw("2026-09-10T00:00:00Z")[0]["probe_id"] == item.probe_id
    assert store.list("probe", probe_id=item.probe_id)[0]["probe_id"] == item.probe_id


def test_checkpoint_is_monotonic_and_controls_persist(tmp_path):
    path = tmp_path / "null.db"
    store = Store(str(path))
    store.save_checkpoint("telegram", 10)
    store.set_control("paused", "true")
    store.close()
    reopened = Store(str(path))
    assert reopened.checkpoint("telegram") == 10
    assert reopened.control("paused") == "true"
    with pytest.raises(StoreError, match="backwards"):
        reopened.save_checkpoint("telegram", 9)
