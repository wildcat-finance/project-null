import json

import pytest

from project_null.generator import Generator, MIXED_POLICY_VERSION
from project_null.operations import (
    Config, OperationsError, health_report, publish_run,
    record_peer_reply_evidence, write_audit,
)
from project_null.store import Store


class API:
    def call(self, method, payload=None):
        if method == "getMe":
            return {"id": 8, "username": "ProjectNull_bot",
                    "can_read_all_group_messages": False}
        return {"url": ""}


def environment(tmp_path):
    return {
        "NULL_DB": str(tmp_path / "state/null.db"),
        "NULL_ARTIFACTS": str(tmp_path / "artifacts"),
        "NULL_ALLOWED_CHAT_IDS": "-100987654321",
        "NULL_OPERATOR_USER_IDS": "987654321",
        "NULL_ALEPH_USERNAME": "ProjectAlephWildcat_bot",
        "NULL_ALEPH_BOT_ID": "8728174629",
        "NULL_SOURCE_REVISION": "abc1234",
        "NULL_TELEGRAM_TOKEN": "must-never-appear",
    }


def test_public_configuration_and_run_hide_identity_and_token(tmp_path):
    config = Config.from_env(environment(tmp_path))
    record = publish_run(config, "2026-08-11T00:00:00Z")
    serialized = json.dumps(record)
    assert "must-never-appear" not in serialized
    assert "987654321" not in serialized
    assert record["configuration"]["allowed_chat_count"] == 1
    assert record["configuration"]["aleph_bot_id"] == 8728174629
    assert (record["configuration"]["mixed_policy_version"]
            == MIXED_POLICY_VERSION)
    assert publish_run(config, "2026-08-11T00:00:00Z") == record


def test_config_requires_explicit_allowlists(tmp_path):
    with pytest.raises(OperationsError, match="non-empty"):
        Config.from_env({"NULL_ALLOWED_CHAT_IDS": "",
                         "NULL_OPERATOR_USER_IDS": "7",
                         "NULL_ALEPH_BOT_ID": "8728174629"})
    with pytest.raises(OperationsError, match="group chat IDs"):
        Config.from_env({"NULL_ALLOWED_CHAT_IDS": "100",
                         "NULL_OPERATOR_USER_IDS": "7",
                         "NULL_ALEPH_BOT_ID": "8728174629"})
    with pytest.raises(OperationsError, match="positive user IDs"):
        Config.from_env({"NULL_ALLOWED_CHAT_IDS": "-100",
                         "NULL_OPERATOR_USER_IDS": "-7",
                         "NULL_ALEPH_BOT_ID": "8728174629"})


def test_health_and_audit_are_scrubbed(tmp_path):
    config = Config.from_env(environment(tmp_path))
    store = Store(config.db_path)
    store.set_control("paused", "true")
    report = health_report(store, API(), config)
    assert report["ok"] is True
    assert report["candidates"] == {
        "total": 0, "resolved": 0, "unresolved": 0}
    assert report["telegram"]["bot_to_bot_mode"] == "not_exposed_by_bot_api"
    assert report["telegram"]["peer_reply_evidence"] == {
        "captured": False, "count": 0, "last_observed_at": None}
    path = write_audit(store, config, "run_123", "2026-08-11T00:00:00Z")
    data = path.read_text()
    assert "987654321" not in data and "must-never-appear" not in data
    assert path.stat().st_mode & 0o777 == 0o600


def test_audit_writes_only_run_and_state_transitions(tmp_path):
    config = Config.from_env(environment(tmp_path))
    store = Store(config.db_path)
    store.set_control("paused", "true")

    first = write_audit(
        store, config, "run_123", "2026-08-11T00:00:00Z")
    unchanged = write_audit(
        store, config, "run_123", "2026-08-11T00:01:00Z")
    store.set_control("mode", "ordinary")
    changed = write_audit(
        store, config, "run_123", "2026-08-11T00:02:00Z")
    store.set_control("paused", "false")
    resumed = write_audit(
        store, config, "run_123", "2026-08-11T00:03:00Z")
    generated = Generator(
        clock=lambda: "2026-08-11T00:03:30Z").generate(seed=1)
    store.append(generated.scenario)
    counted = write_audit(
        store, config, "run_123", "2026-08-11T00:04:00Z")
    new_run = write_audit(
        store, config, "run_456", "2026-08-11T00:05:00Z")

    assert first is not None
    assert unchanged is None
    assert changed is not None and changed != first
    assert resumed is not None and resumed != changed
    assert counted is not None and counted != resumed
    assert new_run is not None and new_run != counted
    assert len(list((tmp_path / "artifacts" / "audit").rglob("*.json"))) == 5
    for path in (first, changed, resumed, counted, new_run):
        record = json.loads(path.read_text())
        assert record["state_sha256"]
        assert "987654321" not in path.read_text()


def test_health_reports_durable_scrubbed_peer_reply_evidence(tmp_path):
    config = Config.from_env(environment(tmp_path))
    store = Store(config.db_path)
    observed_at = "2026-08-11T00:39:43Z"
    record_peer_reply_evidence(store, observed_at)

    report = health_report(store, API(), config)

    assert report["telegram"]["peer_reply_evidence"] == {
        "captured": True, "count": 1, "last_observed_at": observed_at}
    assert "987654321" not in json.dumps(report)


def test_health_fails_loud_on_malformed_peer_reply_evidence(tmp_path):
    config = Config.from_env(environment(tmp_path))
    store = Store(config.db_path)
    store.set_control("peer_reply_evidence", "not-json")

    with pytest.raises(OperationsError, match="peer reply evidence is malformed"):
        health_report(store, API(), config)


def test_production_units_keep_state_bounded():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    for name in ("project-null.service", "project-null-monitor.service",
                 "project-null-maintenance.service",
                 "project-null-disposition.service"):
        text = (root / "ops/systemd" / name).read_text()
        assert "NoNewPrivileges=true" in text
        assert "CapabilityBoundingSet=" in text
        assert "ProtectSystem=strict" in text
        assert "ReadWritePaths=/var/lib/project-null" in text
        assert "UMask=0077" in text
