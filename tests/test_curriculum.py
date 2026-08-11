import json

from project_null.curriculum import derive, remember_exposure
from project_null.generator import Generator
from project_null.schema import (
    AnonymizedQuestion, OutcomeKind, Provenance, ReviewDecision,
    ScenarioFamily, stable_id,
)
from project_null.store import Store

NOW = "2026-08-11T00:00:00Z"


def retained_question(unique, decision):
    return AnonymizedQuestion(
        question_id=stable_id("question", {"unique": unique}),
        text=f"Reviewed synthetic question {unique}",
        provenance=Provenance.SYNTHETIC,
        family=ScenarioFamily.ORDINARY,
        expected_outcome=OutcomeKind.ANSWERED,
        decision=decision,
        source_date="2026-08-11",
        anonymized_at=NOW,
    )


def test_reviewed_evidence_advances_family_and_gaps_do_not(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    initial = derive(store)
    assert set(initial.public()["family_tiers"].values()) == {"foundation"}

    store.append(retained_question(1, ReviewDecision.CORPUS_GAP))
    gap = derive(store)
    assert gap.tiers[ScenarioFamily.ORDINARY].value == "foundation"
    assert gap.public()["gaps"] == 1

    store.append(retained_question(2, ReviewDecision.REGRESSION))
    contextual = derive(store)
    assert contextual.tiers[ScenarioFamily.ORDINARY].value == "contextual"

    store.append(retained_question(3, ReviewDecision.REJECTION_TEST))
    adversarial = derive(store)
    assert adversarial.tiers[ScenarioFamily.ORDINARY].value == "adversarial"
    assert adversarial.public()["mastery"] == 2


def test_catalogue_exposure_survives_raw_deletion_without_question_text(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    generator = Generator(clock=lambda: NOW)
    first = generator.generate(
        seed=30, family=ScenarioFamily.NOVICE)
    store.append_many([first.scenario, first.probe])
    remember_exposure(store, first)

    store.delete_records([first.scenario.scenario_id, first.probe.probe_id])
    curriculum = derive(store)
    second = generator.generate(
        seed=31, family=ScenarioFamily.NOVICE,
        seen_texts=curriculum.seen_texts)

    assert first.probe.text != second.probe.text
    exposures = store.list("challenge_exposure")
    assert len(exposures) == 1
    serialized = json.dumps(exposures)
    assert first.probe.text not in serialized
    assert "chat_id" not in serialized and "user_id" not in serialized


def test_public_curriculum_is_scrubbed_and_counts_seen_questions(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    generated = Generator(clock=lambda: NOW).generate(seed=40)
    remember_exposure(store, generated)

    public = derive(store).public()
    serialized = json.dumps(public)
    assert public["seen_questions"] == 1
    assert generated.probe.text not in serialized
    assert generated.probe.generator["challenge_id"] not in serialized
