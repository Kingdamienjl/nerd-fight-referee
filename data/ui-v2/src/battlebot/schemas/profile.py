"""Validated enriched character profile schema."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileType(StrEnum):
    ROSTER_STUB = "roster_stub"
    AUTO_EVIDENCE_PROFILE = "auto_evidence_profile"
    GENERATED = "generated"
    NEEDS_REVIEW = "needs_review"
    APPROVED_OVERRIDE = "approved_override"
    REJECTED = "rejected"


class FlexibleObject(BaseModel):
    """Permissive object for schema areas that are not strict yet."""

    model_config = ConfigDict(extra="allow")


class Generation(FlexibleObject):
    confidence: float = Field(ge=0.0, le=1.0)
    ineligible_reasons: list[str] = Field(default_factory=list)


class Source(FlexibleObject):
    id: str
    title: str | None = None
    url: str | None = None
    source_type: str
    page_id: str | None = None
    revision_id: str | None = None
    revision_timestamp: str | None = None
    retrieved_at: str | None = None


class PowerScaleEntry(BaseModel):
    text: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class PowerScale(BaseModel):
    tier: PowerScaleEntry
    attack_potency: PowerScaleEntry
    speed: PowerScaleEntry
    lifting_strength: PowerScaleEntry
    striking_strength: PowerScaleEntry
    durability: PowerScaleEntry
    stamina: PowerScaleEntry
    range: PowerScaleEntry
    intelligence: PowerScaleEntry


class EnrichedItem(FlexibleObject):
    id: str
    description: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    tags: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    activation_requirements: list[str] = Field(default_factory=list)
    counters: list[str] = Field(default_factory=list)
    resource_dependencies: list[str] = Field(default_factory=list)
    scope_limitations: list[str] = Field(default_factory=list)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    name: str | None = None


class CharacterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    id: str
    name: str
    franchise: str
    category: str
    aliases: list[str]
    profile_type: ProfileType
    status: str
    battle_eligible: bool
    generation: Generation
    identity: FlexibleObject
    canon_policy: FlexibleObject
    battle_policy: FlexibleObject
    variant: FlexibleObject | None = None
    forms: list[dict[str, Any]]
    sources: list[Source]
    power_scale: PowerScale
    claims: list[dict[str, Any]]
    abilities: list[EnrichedItem]
    equipment: list[EnrichedItem]
    summons: list[EnrichedItem]
    resistances: list[EnrichedItem]
    weaknesses: list[EnrichedItem]
    win_conditions: list[Any]
    loss_conditions: list[Any]
    battlefield_dependencies: list[str]
    interaction_tags: list[str]
    resource_dependencies: list[str]
    scope_limitations: FlexibleObject
    review: FlexibleObject
    profile_hash: str

    # Existing enrichment tools attach these legacy display/research fields.
    # Preserve them, but combat and eligibility continue to use the structured,
    # source-backed power_scale/items contract above rather than these summaries.
    repair: Any = None
    attack_potency: Any = None
    speed: Any = None
    durability: Any = None
    weapon_power: Any = None
    key_tools: Any = None
    risk: Any = None
    best_route: Any = None
    slug: Any = None
    source_status: Any = None
    profile_status: Any = None
    queue: Any = None
    research: Any = None
    combat_identity: Any = None
    strengths: Any = None
    notes: Any = None
    qa_status: Any = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_items(cls, value: Any) -> Any:
        """Convert older scalar ability/equipment/weakness entries into evidence items.

        This preserves old harvested records for review without granting them
        eligibility: the normal eligibility validator still requires source
        revisions, core stats, confidence, and an admissible profile type.
        """
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for field in ("abilities", "equipment", "summons", "resistances", "weaknesses"):
            items = normalized.get(field)
            if not isinstance(items, list):
                continue
            converted = []
            for index, item in enumerate(items):
                if isinstance(item, str):
                    converted.append({
                        "id": f"legacy-{field}-{index}",
                        "name": item[:120],
                        "description": item,
                        "source_ids": [],
                        "confidence": 0.0,
                    })
                else:
                    converted.append(item)
            normalized[field] = converted
        return normalized

    @model_validator(mode="after")
    def validate_eligibility_contract(self) -> CharacterProfile:
        reasons = self.generation.ineligible_reasons
        if self.battle_eligible:
            missing = []
            if self.profile_type not in {
                ProfileType.AUTO_EVIDENCE_PROFILE,
                ProfileType.GENERATED,
                ProfileType.APPROVED_OVERRIDE,
            }:
                missing.append("battle_eligible_requires_auto_evidence_profile")
            if not self._has_revision_metadata():
                missing.append("missing_source_revision_metadata")
            if not self.power_scale.attack_potency.text:
                missing.append("missing_attack_potency")
            if not self.power_scale.speed.text:
                missing.append("missing_speed")
            if not self.power_scale.durability.text:
                missing.append("missing_durability")
            if not self.abilities:
                missing.append("missing_powers_and_abilities")
            if reasons:
                missing.append("battle_eligible_requires_empty_ineligible_reasons")
            if self.generation.confidence < 0.55:
                missing.append("confidence_below_0_55")
            if missing:
                raise ValueError("; ".join(missing))
        elif not reasons:
            raise ValueError("ineligible profile requires generation.ineligible_reasons")
        return self

    def _has_revision_metadata(self) -> bool:
        return any(
            source.source_type == "mediawiki"
            and bool(source.revision_id)
            and bool(source.revision_timestamp)
            for source in self.sources
        )
