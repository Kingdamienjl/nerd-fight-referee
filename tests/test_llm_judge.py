import json
import unittest
import httpx

from battlebot.fight.llm_judge import build_prompt, judge_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet


def contender(name, character_id, attack, speed, durability, abilities=None, weaknesses=None):
    return {
        "canonical_name": name,
        "character_id": character_id,
        "franchise": "Test",
        "category": "comic",
        "power_scale": {
            "attack_potency": attack,
            "speed": speed,
            "durability": durability,
            "range": "Extended melee",
        },
        "abilities": abilities or [],
        "equipment": [],
        "weaknesses": weaknesses or [],
    }


def packet():
    return {
        "errors": [],
        "contender_a": contender(
            "Batman",
            "batman",
            "Building level",
            "Peak Human",
            "Building level",
            abilities=[{"name": "Martial Arts", "description": "Close combat skill"}],
        ),
        "contender_b": contender(
            "Superman",
            "superman",
            "Solar System level",
            "Massively FTL+",
            "Solar System level",
            abilities=[{"name": "Flight", "description": "Can fly"}],
        ),
        "warnings": [],
    }


class LlmJudgeTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_contains_do_not_invent_feats(self):
        messages = build_prompt(packet(), smoke_judge_packet(packet()))

        self.assertIn("Do not invent feats", messages[0]["content"])
        self.assertIn("evidence packet is source of truth", messages[1]["content"])

    async def test_llm_judge_returns_valid_schema_from_mocked_ollama_response(self):
        async def caller(messages, env=None):
            return json.dumps(
                {
                    "title": "Nerd Fight Referee Decision",
                    "winner": "Superman",
                    "confidence": "strong",
                    "summary": "Superman controls the fight from the listed packet advantages.",
                    "win_condition": "He wins through speed, power, and durability pressure.",
                    "loser_best_path": "Batman needs a listed weakness exploit, but none is present.",
                    "deciding_factors": [
                        {
                            "factor": "Range control",
                            "evidence": "Superman has Flight and leads speed.",
                            "tactical_effect": "He can deny close combat and choose exchanges.",
                        }
                    ],
                    "warnings": [],
                    "judge_notes": [],
                }
            )

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["title"], "Nerd Fight Referee Decision")
        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["deciding_factors"][0]["tactical_effect"], "He can deny close combat and choose exchanges.")

    async def test_malformed_llm_json_falls_back_to_smoke_judge(self):
        async def caller(messages, env=None):
            return "not json"

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["title"], "Nerd Fight Referee Decision")
        self.assertEqual(result["diagnostics"]["fallback_reason"], "malformed JSON")
        self.assertTrue(any("LLM judge unavailable" in note for note in result["judge_notes"]))

    async def test_disabled_llm_records_fallback_reason(self):
        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "false"},
        )

        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["diagnostics"]["fallback_reason"], "LLM disabled")

    async def test_timeout_records_fallback_reason(self):
        async def caller(messages, env=None):
            raise httpx.TimeoutException("timed out")

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["diagnostics"]["fallback_reason"], "timeout")

    async def test_ollama_unavailable_records_fallback_reason(self):
        async def caller(messages, env=None):
            raise httpx.ConnectError("connection refused")

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], "Superman")
        self.assertEqual(result["diagnostics"]["fallback_reason"], "Ollama unavailable")

    async def test_schema_validation_failure_records_fallback_reason(self):
        async def caller(messages, env=None):
            return json.dumps({"winner": "Superman", "confidence": "strong"})

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["diagnostics"]["fallback_reason"], "schema validation failed")

    async def test_conflicting_llm_winner_falls_back_to_smoke_winner(self):
        async def caller(messages, env=None):
            return json.dumps(
                {
                    "winner": "Batman",
                    "confidence": "high",
                    "summary": "Contradiction.",
                    "win_condition": "Contradiction.",
                    "loser_best_path": "Contradiction.",
                    "deciding_factors": [],
                    "warnings": [],
                    "judge_notes": [],
                }
            )

        result = await judge_fight_packet(
            packet(),
            smoke_judge_packet(packet()),
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], "Superman")
        self.assertIn("judge_conflict", result["warnings"])
        self.assertEqual(result["diagnostics"]["fallback_reason"], "winner conflict")

    def test_smoke_deciding_factors_include_tactical_effect(self):
        result = smoke_judge_packet(packet())

        self.assertTrue(result["deciding_factors"])
        self.assertIn("tactical_effect", result["deciding_factors"][0])


if __name__ == "__main__":
    unittest.main()
