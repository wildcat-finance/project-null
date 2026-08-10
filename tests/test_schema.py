from datetime import datetime, timezone

import pytest

from project_null.schema import (
    AnonymizedQuestion, OutcomeKind, Provenance, ReviewDecision,
    ScenarioFamily, SchemaError, Probe, raw_expiry, stable_id, to_dict,
)

NOW = "2026-08-11T00:00:00Z"


def test_stable_ids_and_exact_retention():
    payload = {"seed": 7, "family": "ordinary"}
    assert stable_id("probe", payload) == stable_id("probe", payload)
    assert raw_expiry(NOW) == "2026-09-10T00:00:00Z"


def test_probe_serializes_version_and_provenance():
    scenario_id = stable_id("scenario", {"x": 1})
    probe = Probe(
        probe_id=stable_id("probe", {"x": 1}), scenario_id=scenario_id,
        run_id=stable_id("run", {"x": 1}), text="How does capacity work?",
        provenance=Provenance.SYNTHETIC, generated_at=NOW,
        raw_expires_at=raw_expiry(NOW),
        generator={"kind": "template", "version": "v1", "seed": 7},
    )
    payload = to_dict(probe)
    assert payload["schema_version"] == 1
    assert payload["record_type"] == "probe"
    assert payload["provenance"] == "synthetic"


def test_raw_window_cannot_slide():
    with pytest.raises(SchemaError, match="exactly 30 days"):
        Probe(
            probe_id=stable_id("probe", {"x": 2}),
            scenario_id=stable_id("scenario", {"x": 2}),
            run_id=stable_id("run", {"x": 2}), text="Question",
            provenance=Provenance.SYNTHETIC, generated_at=NOW,
            raw_expires_at="2026-09-11T00:00:00Z", generator={},
        )


def test_timestamp_requires_explicit_utc():
    with pytest.raises(SchemaError, match="ending in Z"):
        raw_expiry("2026-08-11T00:00:00")


def test_long_term_record_has_no_identity_fields():
    record = AnonymizedQuestion(
        question_id=stable_id("question", {"x": 1}),
        text="When does a withdrawal cycle begin?",
        provenance=Provenance.SYNTHETIC,
        family=ScenarioFamily.ORDINARY,
        expected_outcome=OutcomeKind.ANSWERED,
        decision=ReviewDecision.REGRESSION,
        source_created_at=NOW, anonymized_at=NOW,
    )
    payload = to_dict(record)
    assert not {"chat_id", "user_id", "message_id"}.intersection(payload)
    assert payload["provenance"] == "synthetic"
