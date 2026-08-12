import copy
import json

import pytest

from project_null.coverage import CoverageError, compute_id, load
from project_null.curriculum import derive, remember_exposure
from project_null.generator import COVERAGE_INTERVAL, ChallengeTier, Generator
from project_null.schema import ScenarioFamily
from project_null.store import Store

NOW = "2026-08-11T00:00:00Z"
RELEASE = "1" * 20


def silhouette():
    value = {
        "schema_version": 2,
        "silhouette_id": "",
        "created": NOW,
        "binding": {
            "evolution": 2,
            "generation": 1,
            "evolution_contract": "mixed-candidate-dispositions-v2",
            "release_id": RELEASE,
            "release_sha256": "2" * 64,
            "manifest_sha256": "3" * 64,
            "corpus_build_id": "4" * 16,
            "corpus_chunks_sha256": "5" * 64,
            "evaluation_id": "6" * 20,
            "evaluation_sha256": "7" * 64,
            "questions_sha256": "8" * 64,
            "topic_map_sha256": "9" * 64,
        },
        "corpus": {
            "total_chunks": 3,
            "sources": [{
                "source": "v2-protocol", "chunk_count": 3,
                "document_count": 1, "tiers": ["A"],
                "source_types": ["markdown"],
                "protocol_versions": ["v2.0"],
                "deployment_statuses": ["deployed"],
            }],
            "topics": [{
                "topic_id": "a" * 16, "source": "v2-protocol",
                "topic": "withdrawal-lifecycle", "chunk_count": 3,
                "document_count": 1, "tiers": ["A"],
                "source_types": ["markdown"],
                "protocol_versions": ["v2.0"],
                "deployment_statuses": ["deployed"],
                "answer_case_count": 0,
            }],
        },
        "evaluation": {
            "total": 3, "known_gaps": 1,
            "routes": {"corpus": 2, "correct": 1},
            "risks": {"high": 1, "medium": 2},
            "frequencies": {"common": 2, "rare": 1},
            "registers": {"ordinary": 3},
            "live_operations": {},
            "question_shapes": {"length-short": 3},
            "topics": [
                {"topic": "withdrawal-lifecycle", "total": 2,
                 "known_gaps": 1, "routes": {"corpus": 2},
                 "risks": {"medium": 2}, "live_operations": {}},
                {"topic": "false-premises", "total": 1,
                 "known_gaps": 0, "routes": {"correct": 1},
                 "risks": {"high": 1}, "live_operations": {}},
            ],
        },
        "boundary": {
            "answer_content": "excluded", "corpus_content": "excluded",
            "question_content": "excluded", "human_identity": "excluded",
            "purpose": "question-generation-only",
            "factual_grading": "forbidden",
            "autonomous_corpus_writes": "forbidden",
        },
    }
    value["silhouette_id"] = compute_id(value)
    return value


def write(tmp_path, value=None):
    path = tmp_path / "silhouette.json"
    path.write_text(json.dumps(value or silhouette(), sort_keys=True))
    return path


def test_valid_silhouette_yields_only_scrubbed_shape_targets(tmp_path):
    path = write(tmp_path)
    plan = load(str(path), RELEASE)

    assert plan.silhouette_id == silhouette()["silhouette_id"]
    assert plan.release_id == RELEASE
    assert {item.topic for item in plan.targets}.issuperset({
        "withdrawal-lifecycle", "false-premises", "corpus-edge",
        "question-shapes"})
    assert plan.targets[0].kind == "declared-gap"
    assert plan.uncovered_corpus_topics == 1
    assert plan.rare_question_shape == "length-short"
    public = json.dumps(plan.public())
    assert "withdrawal batch is partly paid" not in public
    assert '"text"' not in public and '"answer"' not in public


@pytest.mark.parametrize("mutation, message", [
    (lambda value: value.update(silhouette_id="0" * 20), "identity"),
    (lambda value: value["boundary"].update(factual_grading="allowed"),
     "boundary"),
    (lambda value: value["evaluation"].update(total=4), "reconcile"),
    (lambda value: value["evaluation"].update(
        question="leaked reviewed question"), "forbidden content"),
    (lambda value: value["corpus"]["sources"][0]["tiers"].__setitem__(
        0, "this is arbitrary prose"), "safe labels"),
])
def test_tampered_incompatible_or_leaking_silhouettes_fail_closed(
        tmp_path, mutation, message):
    value = silhouette()
    mutation(value)
    if message != "identity":
        value["silhouette_id"] = compute_id(value)
    with pytest.raises(CoverageError, match=message):
        load(str(write(tmp_path, value)), RELEASE)


def test_release_identity_is_an_explicit_startup_boundary(tmp_path):
    with pytest.raises(CoverageError, match="configured active release"):
        load(str(write(tmp_path)), "f" * 20)


def test_mixed_bursts_insert_deterministic_coverage_slots(tmp_path):
    plan = load(str(write(tmp_path)), RELEASE)
    generator = Generator(clock=lambda: NOW, aleph_identity={
        "evolution": plan.evolution, "generation": plan.generation})
    left = generator.burst(seed=77, count=6, coverage=plan)
    right = generator.burst(seed=77, count=6, coverage=plan)

    assert left == right
    coverage = [item for item in left
                if item.probe.generator["kind"] == "coverage_challenge"]
    assert len(coverage) == 6 // COVERAGE_INTERVAL
    assert all(item.probe.generator["silhouette_id"] == plan.silhouette_id
               and item.probe.generator["aleph_release_id"] == RELEASE
               for item in coverage)
    assert len({item.probe.text for item in coverage}) == len(coverage)
    assert {item.probe.text for item in coverage}.issubset({
        target.text.format(
            market_address="0x0000000000000000000000000000000000000001",
            account_address="0x0000000000000000000000000000000000000002")
        for target in plan.targets})


def test_configured_context_reaches_coverage_guided_slots(tmp_path):
    plan = load(str(write(tmp_path)), RELEASE)
    variables = {
        "market_address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "account_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }
    generated = Generator(
        clock=lambda: NOW, variables=variables, aleph_identity={
            "evolution": plan.evolution,
            "generation": plan.generation}).burst(
            seed=77, count=6, coverage=plan)
    coverage = [item for item in generated
                if item.probe.generator["kind"] == "coverage_challenge"]

    assert {item.probe.text for item in coverage}.issubset({
        target.text.format(**variables) for target in plan.targets})
    assert all("0x0000000000000000000000000000000000000001"
               not in item.probe.text for item in generated)


def test_review_tier_is_bound_to_coverage_probe_identity(tmp_path):
    plan = load(str(write(tmp_path)), RELEASE)
    generator = Generator(clock=lambda: NOW, aleph_identity={
        "evolution": plan.evolution, "generation": plan.generation})
    foundation = generator.burst(seed=78, count=3, coverage=plan)[2]
    adversarial = generator.burst(
        seed=78, count=3, coverage=plan,
        tiers={family: ChallengeTier.ADVERSARIAL
               for family in ScenarioFamily})[2]

    assert foundation.probe.text == adversarial.probe.text
    assert foundation.probe.probe_id != adversarial.probe.probe_id
    assert foundation.scenario.scenario_id != adversarial.scenario.scenario_id
    assert adversarial.probe.generator["tier"] == "adversarial"


def test_missing_coverage_and_explicit_family_keep_catalogue_behavior(tmp_path):
    plan = load(str(write(tmp_path)), RELEASE)
    generator = Generator(clock=lambda: NOW, aleph_identity={
        "evolution": plan.evolution, "generation": plan.generation})
    ordinary = generator.burst(seed=88, count=6)
    explicit = generator.burst(
        seed=88, count=6, family=ScenarioFamily.NOVICE, coverage=plan)

    assert all(item.probe.generator["kind"] == "challenge"
               for item in ordinary + explicit)
    assert {item.scenario.family for item in explicit} == {
        ScenarioFamily.NOVICE}


def test_scrubbed_exposure_prevents_repeat_after_raw_deletion(tmp_path):
    plan = load(str(write(tmp_path)), RELEASE)
    store = Store(str(tmp_path / "null.db"))
    generator = Generator(clock=lambda: NOW, aleph_identity={
        "evolution": plan.evolution, "generation": plan.generation})
    first = generator.burst(seed=90, count=3, coverage=plan)[2]
    store.append_many([first.scenario, first.probe])
    remember_exposure(store, first)
    store.delete_records([first.scenario.scenario_id, first.probe.probe_id])

    curriculum = derive(store)
    second = generator.burst(
        seed=91, count=3, coverage=plan,
        seen_texts=curriculum.seen_texts)[2]

    assert first.probe.text != second.probe.text
    serialized = json.dumps(store.list("challenge_exposure"))
    assert first.probe.text not in serialized
    assert plan.silhouette_id not in serialized
