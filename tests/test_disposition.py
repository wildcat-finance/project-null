import hashlib
import json

import pytest

from project_null.disposition import (
    DispositionError, apply, candidate_counts,
)
from project_null.export import publish
from project_null.schema import (
    ExportCandidate, ExportKind, OutcomeKind, Provenance, stable_id,
)
from project_null.store import Store


def retained(index: int, question: str) -> ExportCandidate:
    question_id = stable_id("question", {"index": index})
    return ExportCandidate(
        candidate_id=stable_id("candidate", {"index": index}),
        question_id=question_id,
        kind=ExportKind.REGRESSION,
        question=question,
        expected_outcome=OutcomeKind.ANSWERED,
        rationale="Reviewed regression fixture.",
        provenance=Provenance.SYNTHETIC,
        evidence_targets=(),
        created_at="2026-08-11T00:00:00Z",
    )


def retained_corpus(index: int, question: str) -> ExportCandidate:
    question_id = stable_id("question", {"index": index})
    return ExportCandidate(
        candidate_id=stable_id("candidate", {"index": index}),
        question_id=question_id,
        kind=ExportKind.CORPUS_PROPOSAL,
        question=question,
        expected_outcome=OutcomeKind.ANSWERED,
        rationale="Reviewed corpus gap.",
        provenance=Provenance.SYNTHETIC,
        evidence_targets=(),
        created_at="2026-08-11T00:00:00Z",
    )


def setup(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    candidates = [
        retained(1, "Accepted question?"),
        retained(2, "Duplicate question?"),
        retained(3, "Deferred question?"),
    ]
    store.append_many(candidates)
    export = publish(store, str(tmp_path / "artifacts"))
    return store, candidates, export


def report(candidates, export_id, statuses=None):
    statuses = statuses or ("accepted", "duplicate", "deferred")
    cases = []
    for index, (candidate, status) in enumerate(zip(candidates, statuses), 1):
        golden_id = f"q{index:02d}" if status in ("accepted", "duplicate") else None
        issue = ("https://github.com/wildcat-finance/project-aleph/issues/60"
                 if status == "deferred" else None)
        cases.append({
            "candidate_id": candidate.candidate_id,
            "expected": "corpus" if status != "deferred" else "clarify",
            "golden_id": golden_id,
            "issue": issue,
            "question": candidate.question,
            "status": status,
        })
    names = ("accepted", "deferred", "duplicate", "needs_review", "rejected")
    counts = {name: statuses.count(name) for name in names}
    return {
        "candidate_count": len(candidates),
        "cases": cases,
        "counts": counts,
        "export_id": export_id,
        "ready": counts["needs_review"] == 0,
    }


def mixed_report(candidates, export_id, statuses):
    cases = []
    for index, (candidate, status) in enumerate(zip(candidates, statuses), 1):
        regression = candidate.kind == ExportKind.REGRESSION
        cases.append({
            "candidate_id": candidate.candidate_id,
            "expected": "corpus",
            "golden_id": f"q{index:02d}" if regression and status in (
                "accepted", "duplicate") else None,
            "kind": candidate.kind.value,
            "question": candidate.question,
            "reference": (
                "wildcat-docs@aleph-v0.5" if not regression and status in (
                    "accepted", "duplicate") else None),
            "status": status,
        })
    names = ("accepted", "deferred", "duplicate", "needs_review", "rejected")
    counts = {name: statuses.count(name) for name in names}
    return {
        "candidate_count": len(candidates),
        "cases": cases,
        "counts": counts,
        "evolution": "mixed-candidate-dispositions-v2",
        "export_id": export_id,
        "ready": counts["needs_review"] == 0,
        "schema_version": 2,
    }


def write_report(tmp_path, value, name="report.json"):
    path = tmp_path / name
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return path


def snapshot(path):
    return {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
            for item in path.iterdir() if item.is_file()}


def test_apply_resolves_only_terminal_cases_and_is_idempotent(tmp_path):
    store, candidates, export = setup(tmp_path)
    before = snapshot(export)
    path = write_report(tmp_path, report(candidates, export.name))

    first = apply(
        store, str(tmp_path / "artifacts"), str(path),
        "2026-08-11T01:00:00Z")
    repeated = apply(
        store, str(tmp_path / "artifacts"), str(path),
        "2026-08-11T02:00:00Z")

    assert first.applied == 2 and first.reused == 0
    assert first.deferred == 1 and first.needs_review == 0
    assert first.counts.total == 3
    assert first.counts.resolved == 2 and first.counts.unresolved == 1
    assert repeated.applied == 0 and repeated.reused == 2
    assert candidate_counts(store).unresolved == 1
    assert len(store.list("export_candidate")) == 3
    assert len(store.list("candidate_disposition")) == 2
    assert snapshot(export) == before


def test_later_terminal_report_can_resolve_a_deferred_candidate(tmp_path):
    store, candidates, export = setup(tmp_path)
    first = write_report(tmp_path, report(candidates, export.name), "first.json")
    apply(store, str(tmp_path / "artifacts"), str(first),
          "2026-08-11T01:00:00Z")
    updated_value = report(
        candidates, export.name, ("accepted", "duplicate", "accepted"))
    updated = write_report(tmp_path, updated_value, "updated.json")

    result = apply(store, str(tmp_path / "artifacts"), str(updated),
                   "2026-08-11T02:00:00Z")

    assert result.applied == 1 and result.reused == 2
    assert result.counts.unresolved == 0 and result.counts.resolved == 3


def test_partial_unknown_and_conflicting_reports_fail_closed(tmp_path):
    store, candidates, export = setup(tmp_path)
    original = report(candidates, export.name)
    path = write_report(tmp_path, original, "original.json")
    apply(store, str(tmp_path / "artifacts"), str(path),
          "2026-08-11T01:00:00Z")

    partial = json.loads(json.dumps(original))
    partial["cases"].pop()
    partial["counts"]["deferred"] = 0
    with pytest.raises(DispositionError, match="partial"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, partial, "partial.json")))

    unknown = json.loads(json.dumps(original))
    unknown["cases"][2]["candidate_id"] = stable_id(
        "candidate", {"unknown": True})
    with pytest.raises(DispositionError, match="unknown candidate"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, unknown, "unknown.json")))

    conflict = report(
        candidates, export.name, ("duplicate", "duplicate", "deferred"))
    conflict["cases"][0]["golden_id"] = "different-case"
    with pytest.raises(DispositionError, match="conflicting acknowledgement"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, conflict, "conflict.json")))
    assert candidate_counts(store).resolved == 2


def test_modified_export_and_wrong_identity_fail_before_database_write(tmp_path):
    store, candidates, export = setup(tmp_path)
    value = report(candidates, export.name)
    path = write_report(tmp_path, value)
    regression_path = export / "regressions.json"
    regression_path.chmod(0o644)
    regression_path.write_bytes(regression_path.read_bytes() + b" ")
    with pytest.raises(DispositionError, match="hash does not match"):
        apply(store, str(tmp_path / "artifacts"), str(path))
    assert store.list("candidate_disposition") == []

    value["export_id"] = "0" * 20
    with pytest.raises(DispositionError, match="cannot read"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, value, "wrong-export.json")))
    assert store.list("candidate_disposition") == []


def test_version_two_report_resolves_regression_and_corpus_candidates(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    candidates = [
        retained(1, "Regression question?"),
        retained_corpus(2, "Corpus gap question?"),
    ]
    store.append_many(candidates)
    export = publish(store, str(tmp_path / "artifacts"))
    value = mixed_report(candidates, export.name, ("accepted", "accepted"))

    result = apply(
        store, str(tmp_path / "artifacts"),
        str(write_report(tmp_path, value)), "2026-08-11T01:00:00Z")

    assert result.applied == 2
    assert result.counts.resolved == 2 and result.counts.unresolved == 0
    records = store.list("candidate_disposition")
    assert {item["reference"] for item in records} == {
        "q01", "wildcat-docs@aleph-v0.5"}


def test_version_one_report_fails_closed_for_mixed_export(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    candidates = [retained(1, "Regression?"), retained_corpus(2, "Corpus?")]
    store.append_many(candidates)
    export = publish(store, str(tmp_path / "artifacts"))
    value = report(candidates, export.name, ("accepted", "accepted"))

    with pytest.raises(DispositionError, match="version 1"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, value)))
    assert store.list("candidate_disposition") == []


def test_version_two_changed_kind_and_missing_evidence_fail_closed(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    candidates = [retained(1, "Regression?"), retained_corpus(2, "Corpus?")]
    store.append_many(candidates)
    export = publish(store, str(tmp_path / "artifacts"))
    original = mixed_report(candidates, export.name, ("accepted", "accepted"))

    changed_kind = json.loads(json.dumps(original))
    changed_kind["cases"][1]["kind"] = "regression"
    with pytest.raises(DispositionError, match="changed candidate kind"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, changed_kind, "changed-kind.json")))

    missing_evidence = json.loads(json.dumps(original))
    missing_evidence["cases"][1]["reference"] = None
    with pytest.raises(DispositionError, match="evidence reference"):
        apply(store, str(tmp_path / "artifacts"),
              str(write_report(tmp_path, missing_evidence, "missing-evidence.json")))
    assert store.list("candidate_disposition") == []
