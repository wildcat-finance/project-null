"""Small transactional store for raw and long-term Null records."""

from __future__ import annotations

import json
import pathlib
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .schema import Record, record_id, to_dict


class StoreError(RuntimeError):
    """The durable state cannot preserve Null's invariants."""


class Store:
    def __init__(self, path: str):
        self.path = pathlib.Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                record_type TEXT NOT NULL,
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT,
                raw_expires_at TEXT,
                probe_id TEXT
            );
            CREATE INDEX IF NOT EXISTS records_type
                ON records(record_type, record_id);
            CREATE INDEX IF NOT EXISTS records_expiry
                ON records(raw_expires_at) WHERE raw_expires_at IS NOT NULL;
            CREATE INDEX IF NOT EXISTS records_probe
                ON records(probe_id) WHERE probe_id IS NOT NULL;
            CREATE TABLE IF NOT EXISTS checkpoints (
                name TEXT PRIMARY KEY,
                next_id INTEGER NOT NULL CHECK(next_id >= 0)
            );
            CREATE TABLE IF NOT EXISTS controls (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            with self.connection:
                yield self.connection
        except sqlite3.Error as error:
            raise StoreError(f"transaction failed: {error}") from error

    def append(self, record: Record) -> None:
        self.append_many([record])

    def append_many(self, records: list[Record]) -> None:
        rows = []
        for record in records:
            payload = to_dict(record)
            identifier = record_id(record)
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False)
            rows.append((record.record_type, identifier, encoded,
                         payload.get("created_at") or payload.get("generated_at")
                         or payload.get("delivered_at") or payload.get("observed_at")
                         or payload.get("anonymized_at"),
                         payload.get("raw_expires_at"), payload.get("probe_id")))
        try:
            with self.connection:
                self.connection.executemany(
                    "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)", rows)
        except sqlite3.IntegrityError as error:
            raise StoreError("record already exists") from error

    def get(self, identifier: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload FROM records WHERE record_id = ?", (identifier,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, record_type: str, *, probe_id: str | None = None) -> list[dict]:
        query = "SELECT payload FROM records WHERE record_type = ?"
        params: tuple = (record_type,)
        if probe_id is not None:
            query += " AND probe_id = ?"
            params += (probe_id,)
        query += " ORDER BY record_id"
        return [json.loads(row["payload"]) for row in
                self.connection.execute(query, params)]

    def delivery_for_message(self, chat_id: int, message_id: int) -> dict | None:
        return next((item for item in self.list("delivery")
                     if item["chat_id"] == chat_id
                     and item["message_id"] == message_id), None)

    def outcome_for_reply(self, reply_message_id: int) -> dict | None:
        return next((item for item in self.list("aleph_outcome")
                     if item["reply_message_id"] == reply_message_id), None)

    def scenario_for_probe(self, probe_id: str) -> dict | None:
        probe = self.get(probe_id)
        return self.get(probe["scenario_id"]) if probe else None

    def expired_raw(self, cutoff: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT payload FROM records WHERE raw_expires_at IS NOT NULL "
            "AND raw_expires_at <= ? ORDER BY raw_expires_at, record_id",
            (cutoff,))
        return [json.loads(row["payload"]) for row in rows]

    def delete_records(self, identifiers: list[str]) -> int:
        if not identifiers:
            return 0
        placeholders = ",".join("?" for _ in identifiers)
        with self.connection:
            cursor = self.connection.execute(
                f"DELETE FROM records WHERE record_id IN ({placeholders})",
                tuple(identifiers))
        return cursor.rowcount

    def checkpoint(self, name: str) -> int:
        row = self.connection.execute(
            "SELECT next_id FROM checkpoints WHERE name = ?", (name,)).fetchone()
        return int(row["next_id"]) if row else 0

    def save_checkpoint(self, name: str, next_id: int) -> None:
        if not isinstance(next_id, int) or next_id < 0:
            raise StoreError("checkpoint must be a nonnegative integer")
        current = self.checkpoint(name)
        if next_id < current:
            raise StoreError("checkpoint cannot move backwards")
        with self.connection:
            self.connection.execute(
                "INSERT INTO checkpoints(name, next_id) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET next_id=excluded.next_id",
                (name, next_id))

    def control(self, name: str, default: str | None = None) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM controls WHERE name = ?", (name,)).fetchone()
        return row["value"] if row else default

    def set_control(self, name: str, value: str) -> None:
        if not name or not isinstance(value, str):
            raise StoreError("control name and value must be strings")
        with self.connection:
            self.connection.execute(
                "INSERT INTO controls(name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (name, value))
