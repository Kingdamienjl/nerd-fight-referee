import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from battlebot.review import app as review_app
from battlebot.review.app import create_app


def profile_response(path: Path):
    return {
        "name": "Batman",
        "franchise": "DC",
        "category": "comic",
        "path": str(path),
        "status": "needs_review",
        "profile_type": "needs_review",
        "battle_eligible": False,
        "confidence": 0.35,
        "missing_core_fields": ["attack_potency"],
        "approval_blockers": ["missing_attack_potency"],
        "review_reasons": ["missing_attack"],
        "ineligible_reasons": ["missing_attack_potency"],
        "quality_warnings": [],
        "attack_potency": None,
        "speed": None,
        "durability": None,
        "abilities_count": 0,
        "abilities": [],
        "weaknesses_count": 0,
        "weaknesses": [],
        "sources": [],
        "editable_power_fields": [],
        "repair_debug": {},
        "repair": {},
        "repair_attempts": [],
    }


class ReviewAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        transport = httpx.ASGITransport(app=create_app())
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_get_index_returns_200(self):
        with patch("battlebot.review.app.service.list_profiles", return_value=[]):
            response = await self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Profile Review", response.text)

    async def test_get_profile_returns_controlled_response(self):
        path = Path("profiles/needs_review/comic/dc/batman.yaml")

        with patch(
            "battlebot.review.app.service.inspect_profile",
            return_value=profile_response(path),
        ):
            response = await self.client.get("/profile", params={"path": str(path)})

        self.assertIn(response.status_code, {200, 404})
        self.assertNotEqual(response.status_code, 500)

    def test_static_css_asset_exists(self):
        css_path = review_app.PACKAGE_DIR / "static" / "review.css"

        self.assertTrue(css_path.exists())
        self.assertIn("background", css_path.read_text(encoding="utf-8"))

    async def test_auto_repair_selected_route_calls_helper(self):
        path = "profiles/needs_review/comic/dc/batman.yaml"

        with patch(
            "battlebot.review.app.service.selected_auto_repair",
            new=AsyncMock(),
        ) as selected:
            response = await self.client.post(
                "/auto-repair-selected",
                data={
                    "path": path,
                    "source_id": "vsbattles-batman-post-crisis",
                    "promote_if_valid": "true",
                },
            )

        self.assertEqual(response.status_code, 303)
        selected.assert_awaited_once_with(
            path,
            "vsbattles-batman-post-crisis",
            promote_if_valid=True,
        )


if __name__ == "__main__":
    unittest.main()
