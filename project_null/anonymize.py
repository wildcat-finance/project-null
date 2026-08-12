"""Create permitted long-term records and securely purge expired raw data."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import (
    AnonymizedQuestion, ExportCandidate, ExportKind, OutcomeKind, Provenance,
    ReviewDecision, ScenarioFamily, stable_id, utc_now,
)
from .store import Store

_URL = re.compile(r"https?://\S+", re.I)
_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_USERNAME = re.compile(r"(?<!\w)@[A-Za-z0-9_]{5,32}\b")
_LONG_ID = re.compile(r"(?<!\w)-?\d{7,}(?!\w)")


class AnonymizationError(RuntimeError):
    """Raw review state cannot cross the long-term retention boundary."""


def redact(text: str) -> str:
    value = _URL.sub("[url]", text)
    value = _ADDRESS.sub("[address]", value)
    value = _USERNAME.sub("[username]", value)
    value = _LONG_ID.sub("[identifier]", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class PurgeReport:
    anonymized: int
    candidates: int
    deleted_raw: int
    deleted_controls: int


class Anonymizer:
    def __init__(self, store: Store):
        self.store = store

    def run(self, cutoff: str | None = None) -> PurgeReport:
        boundary = cutoff or utc_now()
        expired = self.store.expired_raw(boundary)
        expired_probes = [item for item in expired
                          if item["record_type"] == "probe"]
        anonymized = candidates = 0
        for probe in expired_probes:
            try:
                retained = self._retain(probe, boundary)
            except AnonymizationError:
                # Corrupt or incomplete raw state must not outlive its deadline.
                # No long-term candidate is created, but deletion still proceeds.
                retained = (0, 0)
            anonymized += retained[0]
            candidates += retained[1]

        identifiers = [self._primary_id(item) for item in expired]
        deleted = self.store.delete_records(identifiers)
        deleted_controls = sum(
            self.store.delete_controls(f"delivery:{item['probe_id']}")
            for item in expired_probes)
        if deleted or deleted_controls:
            self.store.compact()
        return PurgeReport(anonymized, candidates, deleted, deleted_controls)

    def finalize(self, probe_id: str,
                 finalized_at: str | None = None) -> PurgeReport:
        """Finalize one reviewed probe early and irreversibly purge its raw link."""
        boundary = finalized_at or utc_now()
        probe = self.store.get(probe_id)
        if probe is None or probe.get("record_type") != "probe":
            raise AnonymizationError("probe is absent or already finalized")
        feedback = self.store.list("feedback", probe_id=probe_id)
        if not feedback:
            raise AnonymizationError("probe has no reviewer feedback")
        anonymized, candidates = self._retain(probe, boundary)
        raw = []
        for record_type in ("probe", "delivery", "aleph_outcome", "feedback"):
            raw.extend(self.store.list(record_type, probe_id=probe_id))
        identifiers = [self._primary_id(item) for item in raw]
        deleted = self.store.delete_records(identifiers)
        deleted_controls = self.store.delete_controls(f"delivery:{probe_id}")
        if deleted or deleted_controls:
            self.store.compact()
        return PurgeReport(
            anonymized, candidates, deleted, deleted_controls)

    def _retain(self, probe: dict, boundary: str) -> tuple[int, int]:
        feedback = self.store.list("feedback", probe_id=probe["probe_id"])
        if not feedback:
            return 0, 0
        reviewed = max(feedback, key=lambda item: item["created_at"])
        decision = ReviewDecision(reviewed["decision"])
        if decision in (ReviewDecision.DUPLICATE, ReviewDecision.DISCARD):
            return 0, 0
        scenario = self.store.get(probe["scenario_id"])
        if scenario is None:
            raise AnonymizationError("reviewed probe has no scenario")
        question_text = redact(probe["text"])
        aleph_identity = probe.get("generator", {}).get("aleph_identity")
        basis = {
            "text": question_text,
            "provenance": probe["provenance"],
            "family": scenario["family"],
            "expected": reviewed["expected_outcome"],
            "decision": decision.value,
            "aleph_identity": aleph_identity,
        }
        question_id = stable_id("question", basis)
        question = AnonymizedQuestion(
            question_id=question_id, text=question_text,
            provenance=Provenance(probe["provenance"]),
            family=ScenarioFamily(scenario["family"]),
            expected_outcome=OutcomeKind(reviewed["expected_outcome"]),
            decision=decision,
            source_date=probe["generated_at"][:10],
            anonymized_at=boundary, aleph_identity=aleph_identity)
        anonymized = 0
        if self.store.get(question_id) is None:
            self.store.append(question)
            anonymized = 1
        kind = (ExportKind.CORPUS_PROPOSAL
                if decision == ReviewDecision.CORPUS_GAP
                else ExportKind.REGRESSION)
        rationale = redact(
            f"Reviewer decision: {decision.value}. {reviewed['note']}")
        candidate_id = stable_id("candidate", {
            **basis, "kind": kind.value, "rationale": rationale})
        candidate = ExportCandidate(
            candidate_id=candidate_id, question_id=question_id, kind=kind,
            question=question_text,
            expected_outcome=OutcomeKind(reviewed["expected_outcome"]),
            rationale=rationale,
            provenance=Provenance(probe["provenance"]),
            evidence_targets=(), created_at=boundary,
            aleph_identity=aleph_identity)
        candidates = 0
        if self.store.get(candidate_id) is None:
            self.store.append(candidate)
            candidates = 1
        return anonymized, candidates

    @staticmethod
    def _primary_id(item: dict) -> str:
        fields = {
            "probe": "probe_id", "delivery": "delivery_id",
            "aleph_outcome": "outcome_id", "feedback": "feedback_id",
        }
        return item[fields[item["record_type"]]]
