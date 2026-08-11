"""Content-addressed run records, scrubbed audits, and health checks."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Mapping

from .generator import CATALOG_VERSION, MAX_BURST, catalog_hash
from .schema import RAW_RETENTION, SCHEMA_VERSION, utc_now
from .store import Store


class OperationsError(RuntimeError):
    """Operational state cannot be recorded or verified safely."""


@dataclass(frozen=True)
class Config:
    db_path: str
    artifacts_path: str
    aleph_username: str
    aleph_bot_id: int
    allowed_chat_ids: frozenset[int]
    operator_user_ids: frozenset[int]
    poll_timeout: int = 30
    source_revision: str = "development"

    def __post_init__(self) -> None:
        if not 0 <= self.poll_timeout <= 50:
            raise OperationsError("NULL_POLL_TIMEOUT must be between 0 and 50")
        if (isinstance(self.aleph_bot_id, bool)
                or not isinstance(self.aleph_bot_id, int)
                or self.aleph_bot_id <= 0):
            raise OperationsError("NULL_ALEPH_BOT_ID must be a positive integer")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ):
        def ids(name: str) -> frozenset[int]:
            try:
                parsed = frozenset(int(value.strip()) for value in
                                   env.get(name, "").split(",") if value.strip())
            except ValueError as error:
                raise OperationsError(f"{name} must be comma-separated integers") from error
            if not parsed:
                raise OperationsError(f"{name} must be non-empty")
            if name == "NULL_ALLOWED_CHAT_IDS" and any(
                    value >= 0 for value in parsed):
                raise OperationsError(
                    "NULL_ALLOWED_CHAT_IDS must contain group chat IDs")
            if name == "NULL_OPERATOR_USER_IDS" and any(
                    value <= 0 for value in parsed):
                raise OperationsError(
                    "NULL_OPERATOR_USER_IDS must contain positive user IDs")
            return parsed

        try:
            poll_timeout = int(env.get("NULL_POLL_TIMEOUT", "30"))
            aleph_bot_id = int(env.get("NULL_ALEPH_BOT_ID", ""))
        except ValueError as error:
            raise OperationsError(
                "NULL_POLL_TIMEOUT and NULL_ALEPH_BOT_ID must be integers") from error
        return cls(
            db_path=env.get("NULL_DB", "state/null.db"),
            artifacts_path=env.get("NULL_ARTIFACTS", "artifacts"),
            aleph_username=env.get(
                "NULL_ALEPH_USERNAME", "ProjectAlephWildcat_bot"),
            aleph_bot_id=aleph_bot_id,
            allowed_chat_ids=ids("NULL_ALLOWED_CHAT_IDS"),
            operator_user_ids=ids("NULL_OPERATOR_USER_IDS"),
            poll_timeout=poll_timeout,
            source_revision=env.get("NULL_SOURCE_REVISION", "development"),
        )

    def public(self) -> dict:
        return {
            "aleph_username": self.aleph_username,
            "aleph_bot_id": self.aleph_bot_id,
            "allowed_chat_count": len(self.allowed_chat_ids),
            "operator_count": len(self.operator_user_ids),
            "poll_timeout": self.poll_timeout,
            "source_revision": self.source_revision,
            "catalog_version": CATALOG_VERSION,
            "catalog_sha256": catalog_hash(),
            "maximum_burst": MAX_BURST,
            "raw_retention_seconds": int(RAW_RETENTION.total_seconds()),
        }


def _bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic(path: pathlib.Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish_run(config: Config, started_at: str | None = None) -> dict:
    record = {"schema_version": SCHEMA_VERSION,
              "started_at": started_at or utc_now(),
              "configuration": config.public()}
    run_id = hashlib.sha256(_bytes(record)).hexdigest()[:20]
    record = {"run_id": run_id, **record}
    path = pathlib.Path(config.artifacts_path).resolve() / "runs" / run_id / "run.json"
    data = _bytes(record)
    if path.exists() and path.read_bytes() != data:
        raise OperationsError("immutable run manifest contains different bytes")
    if not path.exists():
        _atomic(path, data, 0o444)
    return record


def write_audit(store: Store, config: Config, run_id: str,
                observed_at: str | None = None) -> pathlib.Path:
    timestamp = observed_at or utc_now()
    record = {"schema_version": SCHEMA_VERSION, "run_id": run_id,
              "observed_at": timestamp, "record_counts": store.counts(),
              "paused": store.control("paused", "true") == "true",
              "mode": store.control("mode", "mixed")}
    audit_id = hashlib.sha256(_bytes(record)).hexdigest()[:20]
    path = pathlib.Path(config.artifacts_path).resolve() / "audit" / \
        timestamp[:10] / f"{audit_id}.json"
    if not path.exists():
        _atomic(path, _bytes(record), 0o600)
    return path


def health_report(store: Store, api, config: Config) -> dict:
    me = api.call("getMe")
    webhook = api.call("getWebhookInfo")
    return {
        "ok": bool(store.integrity()
                   and isinstance(me.get("id"), int)
                   and me.get("username")
                   and me.get("can_read_all_group_messages") is not True
                   and not webhook.get("url")),
        "database": {"integrity": store.integrity(),
                     "checkpoint": store.checkpoint("telegram")},
        "telegram": {"username": me.get("username"),
                     "privacy_mode": ("enabled" if
                                      me.get("can_read_all_group_messages") is not True
                                      else "disabled"),
                     "webhook": "absent" if not webhook.get("url") else "present",
                     "bot_to_bot_mode": "operator_attestation_required"},
        "configuration": config.public(),
    }
