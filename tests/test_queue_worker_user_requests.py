from battlebot.review.queue_worker import ensure_user_request_profile


def test_ensure_user_request_profile_creates_skeleton(tmp_path):
    profile_path = tmp_path / "profiles/needs_review/mixed/user-requests/homelander.yaml"

    ensure_user_request_profile(
        {
            "profile_path": str(profile_path),
            "target": "Homelander",
        }
    )

    text = profile_path.read_text(encoding="utf-8")
    assert "name: Homelander" in text
    assert "category: mixed" in text
    assert "franchise: User Requests" in text
    assert "queued_user_request" in text
    assert "user_request_skeleton_schema_incomplete" in text


def test_ensure_user_request_profile_ignores_non_user_request_paths(tmp_path):
    profile_path = tmp_path / "profiles/needs_review/comic/marvel/homelander.yaml"

    ensure_user_request_profile(
        {
            "profile_path": str(profile_path),
            "target": "Homelander",
        }
    )

    assert not profile_path.exists()
