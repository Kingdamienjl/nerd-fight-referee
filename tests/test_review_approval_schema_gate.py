from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from battlebot.review.service import approval_blockers, approve_profile


def write_profile(path: Path, profile: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")


def test_explicit_approval_blockers_block_profile_approval():
    profile = {
        "id": "mixed-user-requests-homelander",
        "name": "Homelander",
        "category": "mixed",
        "franchise": "User Requests",
        "approval_blockers": ["user_request_skeleton_schema_incomplete"],
        "power_scale": {
            "attack_potency": {"text": "Building level", "source_ids": ["s1"]},
            "speed": {"text": "Supersonic", "source_ids": ["s1"]},
            "durability": {"text": "Building level", "source_ids": ["s1"]},
        },
        "abilities": [{"id": "flight", "name": "Flight", "source_ids": ["s1"]}],
        "sources": [{"id": "s1", "title": "Example", "url": "https://example.com"}],
    }

    blockers = approval_blockers(profile)

    assert "user_request_skeleton_schema_incomplete" in blockers


def test_schema_incomplete_profile_does_not_add_approval_blockers():
    profile = {
        "id": "mixed-user-requests-godzilla",
        "name": "Godzilla",
        "category": "mixed",
        "franchise": "User Requests",
        "power_scale": {
            "attack_potency": {"text": "City level", "source_ids": ["s1"]},
            "speed": {"text": "Subsonic", "source_ids": ["s1"]},
            "durability": {"text": "City level", "source_ids": ["s1"]},
        },
        "abilities": [{"id": "atomic-breath", "name": "Atomic Breath", "source_ids": ["s1"]}],
        "sources": [{"id": "s1", "title": "Example", "url": "https://example.com"}],
    }

    blockers = approval_blockers(profile)

    assert not any(blocker.startswith("schema_invalid:") for blocker in blockers)


def test_approve_profile_rejects_schema_invalid_sanitized_output():
    profile = {
        "id": "mixed-user-requests-godzilla",
        "name": "Godzilla",
        "category": "mixed",
        "franchise": "User Requests",
        "profile_type": "needs_review",
        "status": "needs_review",
        "battle_eligible": False,
        "generation": {"confidence": 0.8, "ineligible_reasons": ["needs_review"]},
        "power_scale": {
            "attack_potency": {"text": "City level", "source_ids": ["s1"], "confidence": 0.8},
            "speed": {"text": "Subsonic", "source_ids": ["s1"], "confidence": 0.8},
            "durability": {"text": "City level", "source_ids": ["s1"], "confidence": 0.8},
        },
        "abilities": [{"id": "atomic-breath", "name": "Atomic Breath", "source_ids": ["s1"]}],
        "sources": [{"id": "s1", "title": "Example", "url": "https://example.com"}],
    }

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        needs_review = root / "profiles" / "needs_review"
        generated = root / "profiles" / "generated"
        path = needs_review / "mixed" / "user-requests" / "godzilla.yaml"
        write_profile(path, profile)

        result = approve_profile(
            path,
            needs_review_dir=needs_review,
            generated_dir=generated,
            notes_path=root / "profiles" / "review_notes.yaml",
        )

    assert result["ok"] is False
    assert result["error"] == "schema_validation_blockers"
    assert "schema_invalid:sources.0.source_type" in result["schema_validation_blockers"]
    assert result["destination"] is None
