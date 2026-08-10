"""Versioned records and privacy boundaries for Project Null."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, ClassVar, Mapping

SCHEMA_VERSION = 1
RAW_RETENTION = timedelta(days=30)
_ID = re.compile(r"^[a-z][a-z0-9_-]*_[0-9a-f]{20}$")
_FORBIDDEN_LONG_TERM_KEYS = {
    "chat_id", "user_id", "reviewer_user_id", "message_id",
    "reply_message_id", "thread_id", "username", "telegram_id",
}


class SchemaError(ValueError):
    """A record cannot cross the declared schema or privacy boundary."""


class ScenarioFamily(str, Enum):
    ORDINARY = "ordinary"
    NOVICE = "novice"
    LIVE_DATA = "live_data"
    HISTORICAL = "historical"
    AMBIGUOUS = "ambiguous"
    FALSE_PREMISE = "false_premise"
    OUT_OF_SCOPE = "out_of_scope"
    PROMPT_INJECTION = "prompt_injection"
    ABUSIVE = "abusive"
    NOISE = "noise"


class OutcomeKind(str, Enum):
    ANSWERED = "answered"
    POINTED = "pointed"
    REFUSED = "refused"
    ABSTAINED = "abstained"
    FAILED = "failed"


class Provenance(str, Enum):
    SYNTHETIC = "synthetic"
    PRODUCTION_DERIVED = "production_derived"
    HUMAN_AUTHORED = "human_authored"


class ReviewDecision(str, Enum):
    REGRESSION = "regression"
    CORPUS_GAP = "corpus_gap"
    ROUTING_CHANGE = "routing_change"
    LIVE_DATA_REQUIREMENT = "live_data_requirement"
    REJECTION_TEST = "rejection_test"
    DUPLICATE = "duplicate"
    DISCARD = "discard"


class ExportKind(str, Enum):
    REGRESSION = "regression"
    CORPUS_PROPOSAL = "corpus_proposal"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SchemaError("timestamps must be UTC ISO-8601 values ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise SchemaError(f"invalid timestamp {value!r}") from error
    if parsed.tzinfo != timezone.utc:
        raise SchemaError("timestamps must be UTC")
    return parsed


def raw_expiry(created_at: str) -> str:
    return (parse_utc(created_at) + RAW_RETENTION).isoformat().replace(
        "+00:00", "Z")


def stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", prefix):
        raise SchemaError(f"invalid ID prefix {prefix!r}")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:20]}"


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SchemaError(f"{label} is not a stable Project Null ID")


def _nonempty(value: str, label: str, maximum: int | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} must be non-empty")
    if maximum is not None and len(value) > maximum:
        raise SchemaError(f"{label} exceeds {maximum} characters")


def _raw_window(created_at: str, expires_at: str) -> None:
    if parse_utc(expires_at) - parse_utc(created_at) != RAW_RETENTION:
        raise SchemaError("raw expiry must be exactly 30 days after creation")


@dataclass(frozen=True)
class Scenario:
    record_type: ClassVar[str] = "scenario"
    scenario_id: str
    family: ScenarioFamily
    expected_outcome: OutcomeKind
    seed: int
    template_version: str
    created_at: str
    variables: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.scenario_id, "scenario_id")
        if not isinstance(self.family, ScenarioFamily):
            raise SchemaError("family must be a ScenarioFamily")
        if not isinstance(self.expected_outcome, OutcomeKind):
            raise SchemaError("expected_outcome must be an OutcomeKind")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise SchemaError("seed must be a nonnegative integer")
        _nonempty(self.template_version, "template_version", 80)
        parse_utc(self.created_at)
        if any(not isinstance(k, str) or not isinstance(v, str)
               for k, v in self.variables.items()):
            raise SchemaError("scenario variables must be string pairs")


@dataclass(frozen=True)
class Probe:
    record_type: ClassVar[str] = "probe"
    probe_id: str
    scenario_id: str
    run_id: str
    text: str
    provenance: Provenance
    generated_at: str
    raw_expires_at: str
    generator: Mapping[str, Any]

    def __post_init__(self) -> None:
        for value, label in ((self.probe_id, "probe_id"),
                             (self.scenario_id, "scenario_id"),
                             (self.run_id, "run_id")):
            _identifier(value, label)
        _nonempty(self.text, "probe text", 1000)
        if not isinstance(self.provenance, Provenance):
            raise SchemaError("provenance must be declared")
        _raw_window(self.generated_at, self.raw_expires_at)
        if not isinstance(self.generator, Mapping):
            raise SchemaError("generator metadata must be a mapping")


@dataclass(frozen=True)
class Delivery:
    record_type: ClassVar[str] = "delivery"
    delivery_id: str
    probe_id: str
    chat_id: int
    message_id: int
    thread_id: int | None
    delivered_at: str
    raw_expires_at: str

    def __post_init__(self) -> None:
        _identifier(self.delivery_id, "delivery_id")
        _identifier(self.probe_id, "probe_id")
        if not isinstance(self.chat_id, int) or not isinstance(self.message_id, int):
            raise SchemaError("Telegram delivery identifiers must be integers")
        if self.thread_id is not None and not isinstance(self.thread_id, int):
            raise SchemaError("thread_id must be an integer or null")
        _raw_window(self.delivered_at, self.raw_expires_at)


@dataclass(frozen=True)
class AlephOutcome:
    record_type: ClassVar[str] = "aleph_outcome"
    outcome_id: str
    probe_id: str
    outcome: OutcomeKind
    observed_at: str
    raw_expires_at: str
    reply_message_id: int | None
    latency_ms: int | None
    route: str | None = None
    citation_urls: tuple[str, ...] = ()
    error_kind: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.outcome_id, "outcome_id")
        _identifier(self.probe_id, "probe_id")
        if not isinstance(self.outcome, OutcomeKind):
            raise SchemaError("outcome must be an OutcomeKind")
        _raw_window(self.observed_at, self.raw_expires_at)
        if self.reply_message_id is not None and not isinstance(
                self.reply_message_id, int):
            raise SchemaError("reply_message_id must be an integer or null")
        if self.latency_ms is not None and (
                not isinstance(self.latency_ms, int) or self.latency_ms < 0):
            raise SchemaError("latency_ms must be nonnegative or null")
        if any(not url.startswith("https://") for url in self.citation_urls):
            raise SchemaError("citation URLs must use HTTPS")


@dataclass(frozen=True)
class Feedback:
    record_type: ClassVar[str] = "feedback"
    feedback_id: str
    probe_id: str
    reviewer_user_id: int
    decision: ReviewDecision
    expected_outcome: OutcomeKind
    note: str
    created_at: str
    raw_expires_at: str

    def __post_init__(self) -> None:
        _identifier(self.feedback_id, "feedback_id")
        _identifier(self.probe_id, "probe_id")
        if not isinstance(self.reviewer_user_id, int):
            raise SchemaError("reviewer_user_id must be an integer")
        if not isinstance(self.decision, ReviewDecision):
            raise SchemaError("decision must be a ReviewDecision")
        if not isinstance(self.expected_outcome, OutcomeKind):
            raise SchemaError("expected_outcome must be an OutcomeKind")
        _nonempty(self.note, "feedback note", 2000)
        _raw_window(self.created_at, self.raw_expires_at)


@dataclass(frozen=True)
class AnonymizedQuestion:
    record_type: ClassVar[str] = "anonymized_question"
    question_id: str
    text: str
    provenance: Provenance
    family: ScenarioFamily
    expected_outcome: OutcomeKind
    decision: ReviewDecision
    source_created_at: str
    anonymized_at: str

    def __post_init__(self) -> None:
        _identifier(self.question_id, "question_id")
        _nonempty(self.text, "anonymized text", 1000)
        if not isinstance(self.provenance, Provenance):
            raise SchemaError("provenance must be declared")
        if not isinstance(self.family, ScenarioFamily):
            raise SchemaError("family must be declared")
        if not isinstance(self.expected_outcome, OutcomeKind):
            raise SchemaError("expected_outcome must be declared")
        if not isinstance(self.decision, ReviewDecision):
            raise SchemaError("decision must be declared")
        parse_utc(self.source_created_at)
        parse_utc(self.anonymized_at)


@dataclass(frozen=True)
class ExportCandidate:
    record_type: ClassVar[str] = "export_candidate"
    candidate_id: str
    question_id: str
    kind: ExportKind
    question: str
    expected_outcome: OutcomeKind
    rationale: str
    provenance: Provenance
    evidence_targets: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        _identifier(self.candidate_id, "candidate_id")
        _identifier(self.question_id, "question_id")
        if not isinstance(self.kind, ExportKind):
            raise SchemaError("kind must be an ExportKind")
        _nonempty(self.question, "candidate question", 1000)
        _nonempty(self.rationale, "candidate rationale", 2000)
        if not isinstance(self.expected_outcome, OutcomeKind):
            raise SchemaError("expected_outcome must be declared")
        if not isinstance(self.provenance, Provenance):
            raise SchemaError("provenance must be declared")
        parse_utc(self.created_at)


Record = (Scenario | Probe | Delivery | AlephOutcome | Feedback |
          AnonymizedQuestion | ExportCandidate)


def to_dict(record: Record) -> dict[str, Any]:
    if not dataclasses.is_dataclass(record):
        raise SchemaError("record must be a Project Null dataclass")

    def convert(value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return [convert(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): convert(item) for key, item in value.items()}
        return value

    payload = {key: convert(value)
               for key, value in dataclasses.asdict(record).items()}
    result = {"schema_version": SCHEMA_VERSION,
              "record_type": record.record_type, **payload}
    if record.record_type in ("anonymized_question", "export_candidate"):
        forbidden = _FORBIDDEN_LONG_TERM_KEYS.intersection(result)
        if forbidden:
            raise SchemaError(
                f"long-term record contains identifiers: {sorted(forbidden)}")
    return result


def record_id(record: Record) -> str:
    primary = {
        "scenario": "scenario_id", "probe": "probe_id",
        "delivery": "delivery_id", "aleph_outcome": "outcome_id",
        "feedback": "feedback_id", "anonymized_question": "question_id",
        "export_candidate": "candidate_id",
    }.get(record.record_type)
    if primary is None or not hasattr(record, primary):
        raise SchemaError("record has no primary identifier")
    return getattr(record, primary)
