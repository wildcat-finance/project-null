"""Derive a scrubbed challenge curriculum from retained human reviews."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .generator import (
    CURRICULUM_VERSION, ChallengeTier, challenge_text, normalise_question,
)
from .schema import (
    ChallengeExposure, ReviewDecision, ScenarioFamily, stable_id,
)
from .store import Store

_MASTERY = {ReviewDecision.REGRESSION.value,
            ReviewDecision.REJECTION_TEST.value}


@dataclass(frozen=True)
class Curriculum:
    tiers: dict[ScenarioFamily, ChallengeTier]
    seen_texts: frozenset[str]
    reviewed: int
    mastery: int
    gaps: int

    def public(self) -> dict:
        counts = Counter(tier.value for tier in self.tiers.values())
        return {
            "version": CURRICULUM_VERSION,
            "reviewed": self.reviewed,
            "mastery": self.mastery,
            "gaps": self.gaps,
            "seen_questions": len(self.seen_texts),
            "tier_counts": {tier.value: counts.get(tier.value, 0)
                            for tier in ChallengeTier},
            "family_tiers": {family.value: self.tiers[family].value
                             for family in ScenarioFamily},
        }


def derive(store: Store) -> Curriculum:
    retained = store.list("anonymized_question")
    mastery = Counter(
        item["family"] for item in retained if item["decision"] in _MASTERY)
    tiers = {}
    for family in ScenarioFamily:
        score = mastery.get(family.value, 0)
        tiers[family] = (ChallengeTier.ADVERSARIAL if score >= 2
                         else ChallengeTier.CONTEXTUAL if score == 1
                         else ChallengeTier.FOUNDATION)
    texts = [item["text"] for item in retained]
    texts.extend(item["text"] for item in store.list("probe"))
    texts.extend(
        rendered for item in store.list("challenge_exposure")
        if (rendered := challenge_text(item["challenge_id"])) is not None)
    gaps = sum(item["decision"] not in _MASTERY for item in retained)
    return Curriculum(
        tiers=tiers,
        seen_texts=frozenset(normalise_question(text) for text in texts),
        reviewed=len(retained), mastery=sum(mastery.values()), gaps=gaps,
    )


def remember_exposure(store: Store, generated) -> None:
    """Persist only catalogue provenance, never raw question or user identity."""
    metadata = generated.probe.generator
    challenge_id = metadata["challenge_id"]
    catalog_sha256 = metadata["catalog_sha256"]
    exposure_id = stable_id("exposure", {
        "challenge_id": challenge_id,
        "catalog_sha256": catalog_sha256,
    })
    if store.get(exposure_id) is not None:
        return
    store.append(ChallengeExposure(
        exposure_id=exposure_id,
        challenge_id=challenge_id,
        catalog_sha256=catalog_sha256,
        family=generated.scenario.family,
        tier=metadata["tier"],
        created_at=generated.probe.generated_at,
    ))
