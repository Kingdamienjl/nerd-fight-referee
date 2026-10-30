
"""Tests for the demotion-stamp placement (frag-4 Part 2).

Through frag-3 the demote tooling wrote stamps as top-level
profile keys, which CharacterProfile (extra="forbid") rejects --
every demoted file failed the importer's schema validation. The
stamps now live under the profile's ``review`` block (a
FlexibleObject), payload unchanged, with a legacy read fallback
and a migration for the 19 already-stamped files.
"""

import unittest

from pydantic import ValidationError

from battlebot.profiles.demotion import (
    DEMOTION_STAMP_KEYS,
    apply_demotion_stamp,
    demotion_stamps,
    migrate_demotion_stamps,
    record_ineligible_reason,
)
from battlebot.schemas.profile import CharacterProfile

STAMP = {
    "rule": "continuity_demotion",
    "at": "2026-10-22T17:37:16+00:00",
    "tainted_source_ids": ["src-1"],
    "previous_status": "auto_generated",
}


def minimal_profile(**overrides):
    """Smallest ineligible profile dict CharacterProfile accepts."""
    entry = {"text": None, "source_ids": [], "confidence": 0.0}
    profile = {
        "schema_version": "1.0",
        "id": "test-profile",
        "name": "Test Profile",
        "franchise": "DC",
        "category": "comic",
        "aliases": [],
        "profile_type": "needs_review",
        "status": "needs_review",
        "battle_eligible": False,
        "generation": {
            "confidence": 0.4,
            "ineligible_reasons": ["missing_attack_potency"],
        },
        "identity": {},
        "canon_policy": {},
        "battle_policy": {},
        "variant": None,
        "forms": [],
        "sources": [],
        "power_scale": {
            axis: dict(entry)
            for axis in (
                "tier", "attack_potency", "speed", "lifting_strength",
                "striking_strength", "durability", "stamina", "range",
                "intelligence",
            )
        },
        "claims": [],
        "abilities": [],
        "equipment": [],
        "summons": [],
        "resistances": [],
        "weaknesses": [],
        "win_conditions": [],
        "loss_conditions": [],
        "battlefield_dependencies": [],
        "interaction_tags": [],
        "resource_dependencies": [],
        "scope_limitations": {},
        "review": {},
        "profile_hash": "deadbeef",
    }
    profile.update(overrides)
    return profile


class DemotionStampPlacementTests(unittest.TestCase):
    def test_apply_writes_under_review(self):
        profile = apply_demotion_stamp(
            minimal_profile(), "continuity_demotion", dict(STAMP)
        )
        self.assertNotIn("continuity_demotion", profile)
        self.assertEqual(
            profile["review"]["continuity_demotion"]["rule"],
            "continuity_demotion",
        )

    def test_apply_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            apply_demotion_stamp(minimal_profile(), "bogus_demotion", {})

    def test_apply_replaces_legacy_top_level_copy(self):
        profile = minimal_profile(continuity_demotion=dict(STAMP))
        profile = apply_demotion_stamp(
            profile, "continuity_demotion", dict(STAMP)
        )
        self.assertNotIn("continuity_demotion", profile)
        self.assertIn("continuity_demotion", demotion_stamps(profile))

    def test_read_new_location(self):
        profile = minimal_profile(
            review={"continuity_demotion": dict(STAMP)}
        )
        self.assertEqual(
            demotion_stamps(profile)["continuity_demotion"]["rule"],
            "continuity_demotion",
        )

    def test_read_legacy_fallback(self):
        profile = minimal_profile(continuity_demotion=dict(STAMP))
        self.assertIn("continuity_demotion", demotion_stamps(profile))

    def test_migrate_moves_top_level_stamp(self):
        profile = minimal_profile(template_cleanup_demotion=dict(STAMP))
        moved = migrate_demotion_stamps(profile)
        self.assertEqual(moved, ["template_cleanup_demotion"])
        self.assertNotIn("template_cleanup_demotion", profile)
        self.assertEqual(
            profile["review"]["template_cleanup_demotion"], STAMP
        )

    def test_migrate_noop_without_stamps(self):
        profile = minimal_profile()
        self.assertEqual(migrate_demotion_stamps(profile), [])

    def test_all_known_keys_migrate(self):
        profile = minimal_profile(
            **{key: dict(STAMP) for key in DEMOTION_STAMP_KEYS}
        )
        self.assertEqual(
            sorted(migrate_demotion_stamps(profile)),
            sorted(DEMOTION_STAMP_KEYS),
        )

    def test_apply_records_reason_when_ineligible_without_reasons(self):
        # The second latent defect: demote runs flipped
        # battle_eligible without recording an ineligible reason,
        # which the eligibility contract also rejects. Applying a
        # stamp to an ineligible profile records the rule.
        profile = minimal_profile(
            generation={"confidence": 0.4, "ineligible_reasons": []}
        )
        with self.assertRaises(ValidationError):
            CharacterProfile.model_validate(profile)
        profile = apply_demotion_stamp(
            profile, "continuity_demotion", dict(STAMP)
        )
        self.assertIn(
            "continuity_demotion",
            profile["generation"]["ineligible_reasons"],
        )
        CharacterProfile.model_validate(profile)

    def test_record_ineligible_reason_idempotent(self):
        profile = minimal_profile()
        self.assertFalse(
            record_ineligible_reason(profile, "missing_attack_potency")
        )
        self.assertTrue(
            record_ineligible_reason(profile, "continuity_demotion")
        )
        self.assertFalse(
            record_ineligible_reason(profile, "continuity_demotion")
        )

    def test_stamped_profile_validates(self):
        # The frag-3 failure mode: a top-level stamp fails
        # validation; the migrated placement must pass.
        legacy = minimal_profile(continuity_demotion=dict(STAMP))
        with self.assertRaises(ValidationError):
            CharacterProfile.model_validate(legacy)
        migrate_demotion_stamps(legacy)
        validated = CharacterProfile.model_validate(legacy)
        self.assertFalse(validated.battle_eligible)
        self.assertEqual(
            demotion_stamps(legacy)["continuity_demotion"]["rule"],
            "continuity_demotion",
        )


if __name__ == "__main__":
    unittest.main()
