"""Classify Aleph's observable Telegram behavior without internal coupling."""

from __future__ import annotations

import re
from typing import Callable

from .schema import (
    AlephOutcome, OutcomeKind, parse_utc, raw_expiry, stable_id, utc_now,
)
from .store import Store

_CITATION = re.compile(r"https://github\.com/wildcat-finance/[^\s)>]+")


def classify(text: str) -> tuple[OutcomeKind, str, str | None]:
    """Return outcome, observable route, and error kind from public text."""
    lower = text.casefold().strip()
    if "appropriate destination is" in lower:
        return OutcomeKind.POINTED, "refuse+point", None
    if lower.startswith(("i can't comply", "i can't help", "i can only answer",
                         "i can't infer", "i can't provide or compile")):
        return OutcomeKind.REFUSED, "refuse", None
    if lower.startswith("i can't produce a supported answer"):
        return OutcomeKind.ABSTAINED, "abstain", None
    if lower.startswith("i need "):
        return OutcomeKind.ABSTAINED, "needs_input", None
    if "internal error" in lower:
        return OutcomeKind.FAILED, "error", "internal_error"
    has_explanation = "explanation\n" in lower
    has_live = "current state\n" in lower
    if "premise correction\n" in lower:
        return OutcomeKind.ANSWERED, "correct", None
    if has_explanation and has_live:
        return OutcomeKind.ANSWERED, "corpus+live", None
    if has_live:
        return OutcomeKind.ANSWERED, "live", None
    if has_explanation or "sources\n" in lower:
        return OutcomeKind.ANSWERED, "corpus", None
    return OutcomeKind.FAILED, "unrecognized", "unrecognized_format"


class OutcomeCapture:
    def __init__(self, store: Store, clock: Callable[[], str] = utc_now):
        self.store, self.clock = store, clock

    def observe(self, *, probe_id: str, reply_message_id: int,
                text: str, observed_at: str | None = None) -> AlephOutcome | None:
        outcome_id = stable_id("outcome", {
            "probe_id": probe_id, "reply_message_id": reply_message_id})
        if self.store.get(outcome_id) is not None:
            return None
        delivery = self.store.list("delivery", probe_id=probe_id)
        if not delivery:
            return None
        observed = observed_at or self.clock()
        latency = max(0, int((parse_utc(observed) - parse_utc(
            delivery[0]["delivered_at"])).total_seconds() * 1000))
        kind, route, error = classify(text)
        record = AlephOutcome(
            outcome_id=outcome_id, probe_id=probe_id, outcome=kind,
            observed_at=observed, raw_expires_at=raw_expiry(observed),
            reply_message_id=reply_message_id, latency_ms=latency,
            route=route, citation_urls=tuple(dict.fromkeys(_CITATION.findall(text))),
            error_kind=error)
        self.store.append(record)
        return record

    def mark_timeouts(self, *, now: str | None = None,
                      timeout_seconds: int = 120) -> int:
        observed = now or self.clock()
        now_dt = parse_utc(observed)
        count = 0
        for delivery in self.store.list("delivery"):
            probe_id = delivery["probe_id"]
            if self.store.list("aleph_outcome", probe_id=probe_id):
                continue
            age = (now_dt - parse_utc(delivery["delivered_at"])).total_seconds()
            if age < timeout_seconds:
                continue
            outcome_id = stable_id("outcome", {
                "probe_id": probe_id, "timeout_at": observed})
            self.store.append(AlephOutcome(
                outcome_id=outcome_id, probe_id=probe_id,
                outcome=OutcomeKind.FAILED, observed_at=observed,
                raw_expires_at=raw_expiry(observed), reply_message_id=None,
                latency_ms=int(age * 1000), route="silence",
                error_kind="timeout"))
            count += 1
        return count
