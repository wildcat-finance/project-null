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
from typing import Callable, Protocol

from .anonymize import AnonymizationError, Anonymizer
from .capture import OutcomeCapture
from .generator import Generator, MAX_BURST
from .operations import record_peer_reply_evidence
from .schema import (
    Delivery, Feedback, OutcomeKind, ReviewDecision, ScenarioFamily,
    raw_expiry, stable_id, utc_now,
)
from .store import Store, StoreError


class TelegramError(RuntimeError):
    """Telegram or command state cannot be handled safely."""


class TelegramTimeout(TelegramError):
    """Telegram transport timed out before returning a Bot API response."""


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
        except TimeoutError as error:
            raise TelegramTimeout(f"Telegram {method} timed out") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TelegramTimeout(f"Telegram {method} timed out") from error
            raise TelegramError(f"Telegram {method} failed: {error}")
        except json.JSONDecodeError as error:
            raise TelegramError(f"Telegram {method} failed: {error}")
        if body.get("ok") is not True:
            raise TelegramError(f"Telegram {method} refused the request")
        return body.get("result")


class RateLimiter:
    def __init__(self, limit: int = 6, window: int = 60,
                 clock: Callable[[], float] = time.monotonic):
        if limit < 1 or window < 1:
            raise TelegramError("rate limit and window must be positive")
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
    _REVIEW_CODE = re.compile(r"^[0-9a-f]{12}$")
    _REVIEW_BATCH_LIMIT = 20

    def __init__(self, store: Store, generator: Generator, api: BotAPI,
                 *, aleph_username: str, aleph_bot_id: int,
                 allowed_chat_ids: set[int],
                 operator_user_ids: set[int], clock: Callable[[], str] = utc_now,
                 limiter: RateLimiter | None = None, poll_timeout: int = 30):
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", aleph_username):
            raise TelegramError("aleph_username is invalid")
        if (isinstance(aleph_bot_id, bool) or not isinstance(aleph_bot_id, int)
                or aleph_bot_id <= 0):
            raise TelegramError("aleph_bot_id must be a positive integer")
        if not allowed_chat_ids or not operator_user_ids:
            raise TelegramError("chat and operator allowlists must be non-empty")
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value >= 0 for value in allowed_chat_ids):
            raise TelegramError("allowed chats must be group chat IDs")
        if any(isinstance(value, bool) or not isinstance(value, int)
               or value <= 0 for value in operator_user_ids):
            raise TelegramError("operators must be positive user IDs")
        if not 0 <= poll_timeout <= 50:
            raise TelegramError("poll_timeout must be between 0 and 50 seconds")
        self.store, self.generator, self.api = store, generator, api
        self.aleph_username = aleph_username
        self.aleph_bot_id = aleph_bot_id
        self.allowed_chat_ids = set(allowed_chat_ids)
        self.operator_user_ids = set(operator_user_ids)
        self.clock = clock
        self.limiter = limiter or RateLimiter()
        self.poll_timeout = poll_timeout
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
        if me["id"] == self.aleph_bot_id:
            raise TelegramError("Null and Aleph cannot have the same bot ID")
        self.identity = Identity(me["id"], username)
        return self.identity

    def poll_once(self) -> int:
        if self.identity is None:
            raise TelegramError("startup must pass before polling")
        offset = self.store.checkpoint("telegram")
        try:
            updates = self.api.call("getUpdates", {
                "offset": offset, "timeout": self.poll_timeout, "limit": 100,
                "allowed_updates": ["message"],
            })
        except TelegramTimeout:
            # A long-poll read timeout is an empty iteration. No update was
            # observed, so the durable checkpoint must remain unchanged.
            return 0
        handled = 0
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or update_id < offset:
                continue
            message = update.get("message") or {}
            try:
                self._handle(update_id, message)
            except TelegramError as error:
                self._report_command_error(message, str(error))
                # Fail closed and confirm the update. A prepared outbound stays
                # `sending`/`uncertain`, so a restart never duplicates it.
            except (StoreError, ValueError):
                self._report_command_error(
                    message, "Null could not safely complete that command.")
            self.store.save_checkpoint("telegram", update_id + 1)
            handled += 1
        return handled

    def _report_command_error(self, message: dict, text: str) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        message_id = message.get("message_id")
        if (chat.get("id") not in self.allowed_chat_ids
                or sender.get("id") not in self.operator_user_ids
                or sender.get("is_bot") is True
                or not isinstance(message_id, int)):
            return
        try:
            self._reply(chat["id"], message_id, text)
        except Exception:
            pass

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
        if chat.get("type") in ("group", "supergroup") and not addressed:
            return
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
        elif command == "queue":
            self._queue(chat_id, message_id)
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
        elif command == "finalize":
            self._finalize(chat_id, message_id, message, argument)

    def _observe_aleph(self, chat_id: int, sender: dict, message: dict) -> None:
        if (sender.get("id") != self.aleph_bot_id
                or str(sender.get("username") or "").casefold()
                != self.aleph_username.casefold()):
            return
        reply_id = (message.get("reply_to_message") or {}).get("message_id")
        text, message_id = message.get("text"), message.get("message_id")
        if not isinstance(reply_id, int) or not isinstance(message_id, int) \
                or not isinstance(text, str):
            return
        delivery = self.store.delivery_for_message(chat_id, reply_id)
        if delivery is None:
            return
        # Telegram's message date has whole-second precision. Delivery uses the
        # local UTC clock, so mixing those clocks can turn a valid sub-second
        # round trip into a misleading zero. Measure receipt on the same clock.
        observed = self.clock()
        outcome = self.capture.observe(
            probe_id=delivery["probe_id"], reply_message_id=message_id,
            text=text, observed_at=observed)
        if outcome is not None:
            record_peer_reply_evidence(self.store, observed)

    def _feedback(self, chat_id: int, user_id: int, message_id: int,
                  message: dict, argument: str) -> None:
        batch = self._review_batch(argument)
        if batch is not None:
            receipts = self._feedback_batch(user_id, message_id, batch)
            self._reply(chat_id, message_id,
                        "Feedback batch results:\n" + "\n".join(receipts))
            return
        response = self._record_feedback(
            user_id, message_id, argument,
            reply_probe=self._probe_from_reply(chat_id, message))
        self._reply(chat_id, message_id, response)

    def _record_feedback(self, user_id: int, message_id: int, argument: str,
                         *, reply_probe: str | None = None,
                         explicit_code: bool = False) -> str:
        parts = argument.split()
        code_probe = None
        decisions = {item.value for item in ReviewDecision}
        if parts and (explicit_code or parts[0].casefold() not in decisions):
            code_probe = self._probe_from_review_code(parts.pop(0))
        if reply_probe and code_probe and reply_probe != code_probe:
            raise TelegramError("review code does not match the replied-to probe")
        probe_id = code_probe or reply_probe
        if len(parts) < 2:
            raise TelegramError(
                "feedback requires: [review_code] <decision> "
                "<expected_outcome> [note]")
        try:
            decision, expected = ReviewDecision(parts[0]), OutcomeKind(parts[1])
        except ValueError as error:
            raise TelegramError("invalid feedback decision or outcome") from error
        note = " ".join(parts[2:]) or "Reviewed in Telegram."
        if not probe_id:
            raise TelegramError(
                "feedback needs a reply to a stored probe or a review code")
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
        return f"Recorded {decision.value}; expected={expected.value}."

    def _feedback_batch(self, user_id: int, message_id: int,
                        entries: tuple[str, ...]) -> list[str]:
        receipts = []
        seen = set()
        for index, entry in enumerate(entries, 1):
            parts = entry.split(maxsplit=1)
            candidate = parts[0].casefold() if parts else ""
            label = (candidate if self._REVIEW_CODE.fullmatch(candidate)
                     else "invalid-code")
            code = label
            try:
                code = self._entry_code(entry)
                label = code
                if code in seen:
                    raise TelegramError("duplicate review code in batch")
                seen.add(code)
                result = self._record_feedback(
                    user_id, message_id, entry, explicit_code=True)
            except TelegramError as error:
                result = f"Error: {error}"
            except (StoreError, ValueError):
                result = "Error: Null could not safely record this feedback."
            receipts.append(f"{index}. {label} — {result}")
        return receipts

    def _finalize(self, chat_id: int, message_id: int,
                  message: dict, argument: str) -> None:
        batch = self._review_batch(argument)
        if batch is not None:
            receipts = self._finalize_batch(batch)
            self._reply(chat_id, message_id,
                        "Finalize batch results:\n" + "\n".join(receipts))
            return
        reply_probe = self._probe_from_reply(chat_id, message)
        code_probe = self._probe_from_review_code(
            argument) if argument else None
        if reply_probe and code_probe and reply_probe != code_probe:
            raise TelegramError("review code does not match the replied-to probe")
        probe_id = code_probe or reply_probe
        if not probe_id:
            raise TelegramError(
                "finalize needs a reply to a stored probe or a review code")
        report = self._finalize_probe(probe_id)
        self._reply(
            chat_id, message_id,
            f"Finalized review; candidates={report.candidates}; "
            f"raw_deleted={report.deleted_raw}.")

    def _finalize_probe(self, probe_id: str):
        try:
            return Anonymizer(self.store).finalize(probe_id, self.clock())
        except AnonymizationError as error:
            raise TelegramError(str(error)) from error

    def _finalize_batch(self, entries: tuple[str, ...]) -> list[str]:
        receipts = []
        seen = set()
        for index, entry in enumerate(entries, 1):
            parts = entry.split(maxsplit=1)
            candidate = parts[0].casefold() if parts else ""
            label = (candidate if self._REVIEW_CODE.fullmatch(candidate)
                     else "invalid-code")
            code = label
            try:
                code = self._entry_code(entry, code_only=True)
                label = code
                if code in seen:
                    raise TelegramError("duplicate review code in batch")
                seen.add(code)
                probe_id = self._probe_from_review_code(code)
                report = self._finalize_probe(probe_id)
                result = self._batch_finalize_summary(report)
            except TelegramError as error:
                result = f"Error: {error}"
            except (StoreError, ValueError):
                result = "Error: Null could not safely finalize this review."
            receipts.append(f"{index}. {label} — {result}")
        return receipts

    @staticmethod
    def _batch_finalize_summary(report) -> str:
        candidate_label = ("review candidate" if report.candidates == 1
                           else "review candidates")
        raw_label = ("raw record" if report.deleted_raw == 1
                     else "raw records")
        return (f"Created {report.candidates} {candidate_label}; "
                f"purged {report.deleted_raw} {raw_label}.")

    @classmethod
    def _review_batch(cls, argument: str) -> tuple[str, ...] | None:
        value = argument.strip()
        if not value.startswith("{"):
            return None
        if not value.endswith("}"):
            raise TelegramError("review batch must end with }")
        body = value[1:-1]
        if "{" in body or "}" in body:
            raise TelegramError("nested review batch braces are not allowed")
        entries = tuple(line.strip() for line in body.splitlines()
                        if line.strip())
        if not entries:
            raise TelegramError("review batch must contain at least one entry")
        if len(entries) > cls._REVIEW_BATCH_LIMIT:
            raise TelegramError(
                f"review batch must contain at most {cls._REVIEW_BATCH_LIMIT} entries")
        return entries

    @classmethod
    def _entry_code(cls, entry: str, *, code_only: bool = False) -> str:
        parts = entry.split()
        if not parts or not cls._REVIEW_CODE.fullmatch(parts[0].casefold()):
            raise TelegramError("review code must be 12 hexadecimal characters")
        if code_only and len(parts) != 1:
            raise TelegramError("finalize batch entries must contain one review code")
        return parts[0].casefold()

    def _probe_from_reply(self, chat_id: int, message: dict) -> str | None:
        reply_id = (message.get("reply_to_message") or {}).get("message_id")
        if not isinstance(reply_id, int):
            return None
        delivery = self.store.delivery_for_message(chat_id, reply_id)
        outcome = self.store.outcome_for_reply(reply_id)
        return (delivery or outcome or {}).get("probe_id")

    @staticmethod
    def _review_code(probe_id: str) -> str:
        return probe_id.rsplit("_", 1)[-1][-12:]

    def _probe_from_review_code(self, value: str) -> str:
        code = value.strip().casefold()
        if not self._REVIEW_CODE.fullmatch(code):
            raise TelegramError("review code must be 12 hexadecimal characters")
        matches = [item["probe_id"] for item in self.store.list("probe")
                   if self._review_code(item["probe_id"]) == code]
        if not matches:
            raise TelegramError("review code is unknown or already finalized")
        if len(matches) != 1:
            raise TelegramError("review code is ambiguous")
        return matches[0]

    def _queue(self, chat_id: int, message_id: int) -> None:
        probes = sorted(
            self.store.list("probe"), key=lambda item: item["generated_at"])
        if not probes:
            self._reply(chat_id, message_id, "Review queue is empty.")
            return
        visible = probes[:20]
        lines = []
        for probe in visible:
            scenario = self.store.get(probe["scenario_id"]) or {}
            outcomes = self.store.list(
                "aleph_outcome", probe_id=probe["probe_id"])
            outcome = outcomes[-1] if outcomes else {}
            state = ("finalize" if self.store.list(
                "feedback", probe_id=probe["probe_id"]) else "feedback")
            lines.append(
                f"{self._review_code(probe['probe_id'])} "
                f"family={scenario.get('family', 'unknown')} "
                f"expected={scenario.get('expected_outcome', 'unknown')} "
                f"observed={outcome.get('outcome', 'waiting')} "
                f"route={outcome.get('route') or 'none'} state={state}")
        heading = f"Review queue ({len(visible)}/{len(probes)}):"
        username = self.identity.username
        footer = (
            f"Use /feedback@{username} <code> <decision> <expected> [note], "
            f"then /finalize@{username} <code>. "
            "Both commands accept brace batches with one coded entry per line.")
        self._reply(chat_id, message_id,
                    heading + "\n" + "\n".join(lines) + "\n" + footer)

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
            f"Null is {'paused' if paused else 'running'}; "
            f"run={self.store.control('run_id', 'not-started')}; "
            f"mode={self.store.control('mode', 'mixed')}; "
            f"rate={self.limiter.limit}/{self.limiter.window}s; "
            f"max_burst={MAX_BURST}; unreviewed={unresolved}; "
            f"checkpoint={self.store.checkpoint('telegram')}.")

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
