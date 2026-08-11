import json

import pytest

from project_null.export import ExportError, publish
from project_null.schema import (
    ExportCandidate, ExportKind, OutcomeKind, Provenance, stable_id,
)
from project_null.store import Store


def test_exports_are_separate_content_addressed_and_immutable(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    question_id = stable_id("question", {"q": 1})
    candidate = ExportCandidate(
        candidate_id=stable_id("candidate", {"q": 1}),
        question_id=question_id, kind=ExportKind.REGRESSION,
        question="How does capacity work?",
        expected_outcome=OutcomeKind.ANSWERED,
        rationale="Reviewer decision: regression.",
        provenance=Provenance.SYNTHETIC, evidence_targets=(),
        created_at="2026-09-10T00:00:00Z")
    store.append(candidate)
    destination = publish(store, str(tmp_path / "artifacts"))
    assert publish(store, str(tmp_path / "artifacts")) == destination
    manifest = json.loads((destination / "manifest.json").read_text())
    regressions = json.loads((destination / "regressions.json").read_text())
    corpus = json.loads((destination / "corpus-proposals.json").read_text())
    assert manifest["export_id"] == destination.name
    assert regressions[0]["candidate_id"] == candidate.candidate_id
    assert corpus == []
    (destination / "manifest.json").chmod(0o644)
    (destination / "manifest.json").write_text("damage")
    with pytest.raises(ExportError, match="different bytes"):
        publish(store, str(tmp_path / "artifacts"))
