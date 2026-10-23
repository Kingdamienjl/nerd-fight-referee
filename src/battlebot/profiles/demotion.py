"""Demotion stamps for profile files.

A demotion records why a formerly battle-eligible profile was sent
back to needs_review (continuity sweep, template cleanup, ...).
Through frag-3 the stamps were written as TOP-LEVEL profile keys
(``continuity_demotion:`` / ``template_cleanup_demotion:``) -- but
CharacterProfile forbids extra top-level keys, so every stamped
file fails the importer's schema validation and the eligibility-
gated importer freezes its DB row mid-state. The repair path loads
raw dicts and never noticed.

The schema-legal home is the profile's ``review`` block, a
FlexibleObject (extra="allow") that already carries review state.
Stamps now live at ``review.<key>`` with their payload unchanged.
Readers consult the review block first and fall back to the legacy
top-level placement, so stamps written before the migration stay
visible until their file is migrated.
"""

from __future__ import annotations

from typing import Any

DEMOTION_STAMP_KEYS = ("continuity_demotion", "template_cleanup_demotion")


def apply_demotion_stamp(
    profile: dict[str, Any], key: str, stamp: dict[str, Any]
) -> dict[str, Any]:
    """Write a demotion stamp at its schema-legal home.

    Removes any legacy top-level copy of the stamp and records the
    payload under ``review.<key>``. A demotion flips the profile to
    ineligible, and the schema's eligibility contract requires a
    non-empty ``generation.ineligible_reasons`` for ineligible
    profiles -- the Job-2 / frag-3 demote runs flipped the flag
    without recording one, a second latent validation failure the
    stamp error had masked. When the profile is already ineligible
    and has no recorded reasons, the stamp's rule is recorded as
    the reason. Returns the profile for chaining. Raises
    ValueError for an unknown stamp key.
    """
    if key not in DEMOTION_STAMP_KEYS:
        raise ValueError(f"unknown demotion stamp key: {key!r}")
    profile.pop(key, None)
    review = profile.get("review")
    if not isinstance(review, dict):
        review = {}
        profile["review"] = review
    review[key] = stamp
    if profile.get("battle_eligible") is False:
        record_ineligible_reason(profile, key)
    return profile


def record_ineligible_reason(profile: dict[str, Any], reason: str) -> bool:
    """Ensure ``reason`` appears in generation.ineligible_reasons.

    Returns True when the reason was added (the list was missing
    or did not contain it).
    """
    generation = profile.get("generation")
    if not isinstance(generation, dict):
        generation = {}
        profile["generation"] = generation
    reasons = generation.get("ineligible_reasons")
    if not isinstance(reasons, list):
        reasons = []
        generation["ineligible_reasons"] = reasons
    if reason in reasons:
        return False
    reasons.append(reason)
    return True


def demotion_stamps(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read all demotion stamps on a profile dict.

    The review block wins; a legacy top-level stamp is still
    returned for files not yet migrated.
    """
    found: dict[str, dict[str, Any]] = {}
    review = profile.get("review")
    for key in DEMOTION_STAMP_KEYS:
        stamp = None
        if isinstance(review, dict) and isinstance(review.get(key), dict):
            stamp = review[key]
        elif isinstance(profile.get(key), dict):
            stamp = profile[key]
        if stamp is not None:
            found[key] = stamp
    return found


def migrate_demotion_stamps(profile: dict[str, Any]) -> list[str]:
    """Move any top-level demotion stamps under ``review``.

    Returns the stamp keys that were moved (empty when the profile
    needed no migration). When both placements carry a stamp, the
    review copy wins and the top-level duplicate is dropped.
    """
    moved: list[str] = []
    for key in DEMOTION_STAMP_KEYS:
        if isinstance(profile.get(key), dict):
            stamp = profile.pop(key)
            review = profile.get("review")
            if not isinstance(review, dict):
                review = {}
                profile["review"] = review
            review.setdefault(key, stamp)
            moved.append(key)
    return moved
