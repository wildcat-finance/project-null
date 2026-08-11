import pytest

from project_null.generator import (
    Generator, MAX_BURST, MIXED_POLICY_VERSION, catalog_hash,
)
from project_null.schema import Provenance, ScenarioFamily

NOW = "2026-08-11T00:00:00Z"


def test_generation_is_reproducible_and_declared():
    generator = Generator(clock=lambda: NOW)
    left = generator.generate(seed=42, index=3)
    right = generator.generate(seed=42, index=3)
    assert left == right
    assert left.probe.provenance is Provenance.SYNTHETIC
    assert left.probe.generator["catalog_sha256"] == catalog_hash()
    assert left.scenario.expected_outcome.value


def test_every_family_has_a_bounded_probe():
    generator = Generator(clock=lambda: NOW)
    for index, family in enumerate(ScenarioFamily):
        item = generator.generate(seed=9, index=index, family=family)
        assert item.scenario.family is family
        assert 1 <= len(item.probe.text) <= 1000


def test_abusive_family_uses_minimal_test_language():
    generator = Generator(clock=lambda: NOW)
    texts = [generator.generate(seed=1, index=i,
                                family=ScenarioFamily.ABUSIVE).probe.text.lower()
             for i in range(12)]
    assert all("nigger" not in text for text in texts)
    assert all("kill yourself" not in text for text in texts)


def test_burst_is_bounded_and_unique():
    generator = Generator(clock=lambda: NOW)
    burst = generator.burst(seed=5, count=MAX_BURST)
    assert len({item.probe.probe_id for item in burst}) == MAX_BURST
    with pytest.raises(ValueError, match="between"):
        generator.burst(seed=5, count=MAX_BURST + 1)


def test_mixed_bursts_stratify_families_before_repeating():
    generator = Generator(clock=lambda: NOW)
    first = generator.burst(seed=5, count=MAX_BURST)
    second = tuple(generator.generate(seed=5, index=index)
                   for index in range(MAX_BURST, MAX_BURST * 2))

    expected = set(ScenarioFamily)
    assert {item.scenario.family for item in first} == expected
    assert {item.scenario.family for item in second} == expected
    assert all(item.probe.generator["selection"] == MIXED_POLICY_VERSION
               for item in first + second)


def test_explicit_family_bypasses_mixed_selection():
    generator = Generator(clock=lambda: NOW)
    burst = generator.burst(
        seed=5, count=3, family=ScenarioFamily.AMBIGUOUS)

    assert {item.scenario.family for item in burst} == {
        ScenarioFamily.AMBIGUOUS}
    assert all(item.probe.generator["selection"] == "explicit_family"
               for item in burst)
