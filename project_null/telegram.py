"""Long-polling Telegram shell with bounded bot-to-bot probes."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from .capture import OutcomeCapture
from .generator import Generator, MAX_BURST
from .schema import (
    Delivery, Feedback, OutcomeKind, ReviewDecision, ScenarioFamily,
    raw_expiry, stable_id, utc_now,
)
from .store import Store, StoreError


class TelegramError(RuntimeError):
    """Telegram or command state cannot be handled safely."""


class BotAPI(Protocol):
    def call(self, method: str, payload: dict | None = None): ...


class TelegramHTTP:
    def __init__(self, token: str | None = None, timeout: int = 45):
        self.token = token if token is not None else os.environ.get(
            "NULL_TELEGRAM_TOKEN", "")
        if not self.token:
            raise TelegramError("NULL_TELEGRAM_TOKEN is absent")
        self.timeout = timeout

    def call(self, method: str, payload: dict | None = None):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", method):
            raise TelegramError("invalid Bot API method")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload or {}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:
            raise TelegramError(f"Telegram {method} returned HTTP {error.code}")
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise TelegramError(f"Telegram {method} failed: {error}")
        if body.get("ok") is not True:
            raise TelegramError(f"Telegram {method} refused the request")
        return body.get("result")


class RateLimiter:
    def __init__(self, limit: int = 6, window: int = 60,
                 clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.events: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def allow(self, key: tuple[int, int]) -> bool:
        now = self.clock()
        events = self.events[key]
        while events and events[0] <= now - self.window:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True


@dataclass(frozen=True)
class Identity:
    bot_id: int
    username: str


class TelegramShell:
    _COMMAND = re.compile(r"^/(\w+)(?:@([A-Za-z0-9_]+))?(?:\s+(.*))?$", re.S)

    def __init__(self, store: Store, generator: Generator, api: BotAPI,
                 *, aleph_username: str, allowed_chat_ids: set[int],
                 operator_user_ids: set[int], clock: Callable[[], str] = utc_now,
                 limiter: RateLimiter | None = None):
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", aleph_username):
            raise TelegramError("aleph_username is invalid")
        if not allowed_chat_ids or not operator_user_ids:
            raise TelegramError("chat and operator allowlists must be non-empty")
        self.store, self.generator, self.api = store, generator, api
        self.aleph_username = aleph_username
        self.allowed_chat_ids = set(allowed_chat_ids)
        self.operator_user_ids = set(operator_user_ids)
        self.clock = clock
        self.limiter = limiter or RateLimiter()
        self.capture = OutcomeCapture(store, clock)
        self.identity: Identity | None = None

    def startup(self) -> Identity:
        me = self.api.call("getMe")
        webhook = self.api.call("getWebhookInfo")
        if webhook.get("url"):
            raise TelegramError("an active webhook blocks long polling")
        if me.get("can_read_all_group_messages") is True:
            raise TelegramError("Group Privacy must remain enabled")
        username = str(me.get("username") or "")
        if not username or not isinstance(me.get("id"), int):
            raise TelegramError("getMe returned an invalid bot identity")
        self.identity = Identity(me["id"], username)
        return self.identity

    def poll_once(self) -> int:
        if self.identity is None:
            raise TelegramError("startup must pass before polling")
        offset = self.store.checkpoint("telegram")
        updates = self.api.call("getUpdates", {
            "offset": offset, "timeout": 0, "limit": 100,
            "allowed_updates": ["message"],
        })
        handled = 0
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or update_id < offset:
                continue
            try:
                self._handle(update_id, update.get("message") or {})
            except (TelegramError, StoreError, ValueError):
                # Fail closed and confirm the update. A prepared outbound stays
                # `sending`/`uncertain`, so a restart never duplicates it.
                pass
            self.store.save_checkpoint("telegram", update_id + 1)
            handled += 1
        return handled

    def _handle(self, update_id: int, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id, user_id = chat.get("id"), sender.get("id")
        if chat_id not in self.allowed_chat_ids:
            return
        if sender.get("is_bot") is True:
            self._observe_aleph(chat_id, sender, message)
            return
        if user_id not in self.operator_user_ids:
            return
        text = message.get("text")
        message_id = message.get("message_id")
        if not isinstance(text, str) or not isinstance(message_id, int):
            return
        match = self._COMMAND.fullmatch(text.strip())
        if not match:
            return
        command, addressed, argument = match.groups()
        if addressed and addressed.casefold() != self.identity.username.casefold():
            return
        command = command.casefold()
        argument = (argument or "").strip()
        if command in {"probe", "burst"} and not self.limiter.allow(
                (chat_id, user_id)):
            self._reply(chat_id, message_id, "Rate limit reached; try again shortly.")
            return
        if command == "pause":
            self.store.set_control("paused", "true")
            self._reply(chat_id, message_id, "Null is paused.")
        elif command == "resume":
            self.store.set_control("paused", "false")
            self._reply(chat_id, message_id, "Null is running.")
        elif command == "mode":
            self._set_mode(chat_id, message_id, argument)
        elif command == "status":
            self._status(chat_id, message_id)
        elif command == "probe":
            self._generate(update_id, chat_id, message_id, 1)
        elif command == "burst":
            try:
                count = int(argument)
            except ValueError:
                raise TelegramError("burst count must be an integer")
            self._generate(update_id, chat_id, message_id, count)
        elif command == "feedback":
            self._feedback(chat_id, user_id, message_id, message, argument)

    def _observe_aleph(self, chat_id: int, sender: dict, message: dict) -> None:
        if str(sender.get("username") or "").casefold() != \
                self.aleph_username.casefold():
            return
        reply_id = (message.get("reply_to_message") or {}).get("message_id")
        text, message_id = message.get("text"), message.get("message_id")
        if not isinstance(reply_id, int) or not isinstance(message_id, int) \
                or not isinstance(text, str):
            return
        delivery = self.store.delivery_for_message(chat_id, reply_id)
        if delivery is None:
            return
        observed = self.clock()
        if isinstance(message.get("date"), int):
            observed = datetime.fromtimestamp(
                message["date"], timezone.utc).isoformat().replace("+00:00", "Z")
        self.capture.observe(
            probe_id=delivery["probe_id"], reply_message_id=message_id,
            text=text, observed_at=observed)

    def _feedback(self, chat_id: int, user_id: int, message_id: int,
                  message: dict, argument: str) -> None:
        parts = argument.split(maxsplit=2)
        if len(parts) < 2:
            raise TelegramError(
                "feedback requires: <decision> <expected_outcome> [note]")
        try:
            decision, expected = ReviewDecision(parts[0]), OutcomeKind(parts[1])
        except ValueError as error:
            raise TelegramError("invalid feedback decision or outcome") from error
        note = parts[2].strip() if len(parts) == 3 else "Reviewed in Telegram."
        reply_id = (message.get("reply_to_message") or {}).get("message_id")
        if not isinstance(reply_id, int):
            raise TelegramError("feedback must reply to a probe or Aleph response")
        delivery = self.store.delivery_for_message(chat_id, reply_id)
        outcome = self.store.outcome_for_reply(reply_id)
        probe_id = (delivery or outcome or {}).get("probe_id")
        if not probe_id:
            raise TelegramError("feedback reply is not correlated to a probe")
        created = self.clock()
        record = Feedback(
            feedback_id=stable_id("feedback", {
                "probe_id": probe_id, "reviewer": user_id,
                "message_id": message_id}),
            probe_id=probe_id, reviewer_user_id=user_id,
            decision=decision, expected_outcome=expected, note=note,
            created_at=created, raw_expires_at=raw_expiry(created))
        if self.store.get(record.feedback_id) is None:
            self.store.append(record)
        self._reply(chat_id, message_id,
                    f"Recorded {decision.value}; expected={expected.value}.")

    def _mode(self) -> ScenarioFamily | None:
        value = self.store.control("mode", "mixed")
        return None if value == "mixed" else ScenarioFamily(value)

    def _set_mode(self, chat_id: int, message_id: int, argument: str) -> None:
        value = argument.casefold() or "mixed"
        if value != "mixed":
            try:
                ScenarioFamily(value)
            except ValueError as error:
                raise TelegramError("unknown scenario family") from error
        self.store.set_control("mode", value)
        self._reply(chat_id, message_id, f"Null mode: {value}.")

    def _status(self, chat_id: int, message_id: int) -> None:
        paused = self.store.control("paused", "false") == "true"
        unresolved = sum(
            not self.store.list("feedback", probe_id=item["probe_id"])
            for item in self.store.list("probe"))
        self._reply(
            chat_id, message_id,
            f"Null is {'paused' if paused else 'running'}; mode={self.store.control('mode', 'mixed')}; "
            f"unreviewed={unresolved}; checkpoint={self.store.checkpoint('telegram')}.")

    def _generate(self, update_id: int, chat_id: int,
                  command_message_id: int, count: int) -> None:
        if self.store.control("paused", "false") == "true":
            self._reply(chat_id, command_message_id, "Null is paused.")
            return
        if not 1 <= count <= MAX_BURST:
            raise TelegramError(f"burst must be between 1 and {MAX_BURST}")
        generated = self.generator.burst(
            seed=update_id, count=count, family=self._mode())
        sent = 0
        for item in generated:
            if self._send_probe(chat_id, command_message_id, item):
                sent += 1
        self._reply(chat_id, command_message_id,
                    f"Prepared {count}; sent {sent}; duplicates skipped {count - sent}.")

    def _send_probe(self, chat_id: int, command_message_id: int, item) -> bool:
        probe_id = item.probe.probe_id
        if self.store.get(probe_id) is None:
            self.store.append_many([item.scenario, item.probe])
        state_key = f"delivery:{probe_id}"
        if self.store.control(state_key) is not None:
            return False
        # Mark before the network boundary. A crash may require manual
        # reconciliation but cannot produce a duplicate probe on restart.
        self.store.set_control(state_key, "sending")
        text = f"/ask@{self.aleph_username} {item.probe.text}"
        try:
            result = self.api.call("sendMessage", {
                "chat_id": chat_id, "text": text,
                "reply_parameters": {"message_id": command_message_id},
                "link_preview_options": {"is_disabled": True},
            })
        except Exception:
            self.store.set_control(state_key, "uncertain")
            raise
        delivered = self.clock()
        delivery = Delivery(
            delivery_id=stable_id("delivery", {
                "probe_id": probe_id, "chat_id": chat_id,
                "message_id": result["message_id"]}),
            probe_id=probe_id, chat_id=chat_id,
            message_id=result["message_id"], thread_id=None,
            delivered_at=delivered, raw_expires_at=raw_expiry(delivered))
        self.store.append(delivery)
        self.store.set_control(state_key, "sent")
        return True

    def _reply(self, chat_id: int, message_id: int, text: str) -> None:
        self.api.call("sendMessage", {
            "chat_id": chat_id, "text": text,
            "reply_parameters": {"message_id": message_id},
        })
