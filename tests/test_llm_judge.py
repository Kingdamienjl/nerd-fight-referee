import unittest
import httpx

from battlebot.fight.decision_formatter import format_decision
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
    def test_prompt_is_referee_briefing_not_verdict_schema(self):
        messages = build_prompt(packet(), smoke_judge_packet(packet()))
        user_prompt = messages[1]["content"]

        self.assertIn("You are the official Nerd Fight Referee.", user_prompt)
        self.assertIn("Winner: Superman", user_prompt)
        self.assertIn("Confidence:", user_prompt)
        self.assertIn("Win condition / route to victory:", user_prompt)
        self.assertIn("Loser's best path:", user_prompt)
        self.assertIn("Deciding factors:", user_prompt)
        self.assertIn("advantage_breakdown:", user_prompt)
        self.assertIn("fight_flow:", user_prompt)
        self.assertIn("engine_reasoning:", user_prompt)
        self.assertIn("swing_factors:", user_prompt)
        self.assertIn("Compact packet evidence for both contenders:", user_prompt)
        self.assertIn("Do not change the winner.", user_prompt)
        self.assertIn("Do not invent feats.", user_prompt)
        self.assertIn("concrete supplied terms", user_prompt)
        self.assertIn("at least two concrete listed traits", user_prompt)
        self.assertIn("complete sentence", user_prompt)
        self.assertIn("Write 2-4 concise paragraphs.", user_prompt)
        self.assertIn("No JSON.", user_prompt)
        self.assertIn("No bullet lists.", user_prompt)
        self.assertIn("No markdown headings.", user_prompt)
        self.assertNotIn("Referee verdict:", user_prompt)
        self.assertNotIn("Upset justification:", user_prompt)
        self.assertIn("evidence packet is source of truth", user_prompt)

    async def test_llm_judge_uses_plain_text_as_referee_explanation_only(self):
        async def caller(messages, env=None):
            return "Superman wins because speed, power, and durability let him control every exchange."

        smoke = smoke_judge_packet(packet())
        result = await judge_fight_packet(
            packet(),
            smoke,
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["title"], "Nerd Fight Referee Decision")
        self.assertEqual(result["winner"], smoke["winner"])
        self.assertEqual(result["confidence"], smoke["confidence"])
        self.assertEqual(result["deciding_factors"], smoke["deciding_factors"])
        self.assertEqual(result["fight_flow"], smoke["fight_flow"])
        self.assertEqual(result["engine_reasoning"], smoke["engine_reasoning"])
        self.assertEqual(result["engine_verdict"]["fight_flow"], smoke["fight_flow"])
        self.assertEqual(result["engine_verdict"]["engine_reasoning"], smoke["engine_reasoning"])
        self.assertIn("Superman wins because", result["summary"])
        self.assertIn("Superman wins because", format_decision(result))
        self.assertEqual(result["diagnostics"]["fallback_reason"], "llm_explanation")

    async def test_json_shaped_llm_output_is_treated_as_plain_explanation(self):
        async def caller(messages, env=None):
            return '{"winner":"Batman","summary":"Batman wins, but this is just prose now."}'

        smoke = smoke_judge_packet(packet())
        result = await judge_fight_packet(
            packet(),
            smoke,
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], smoke["winner"])
        self.assertNotEqual(result["winner"], "Batman")
        self.assertIn('"winner":"Batman"', result["summary"])
        self.assertEqual(result["diagnostics"]["fallback_reason"], "llm_explanation")

    async def test_strong_engine_confidence_locks_referee_winner(self):
        async def caller(messages, env=None):
            return "Referee verdict: Batman\nUpset justification: Batman has a path, but this should be locked."

        smoke = smoke_judge_packet(packet())
        result = await judge_fight_packet(
            packet(),
            smoke,
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], smoke["winner"])
        self.assertEqual(result["engine_verdict"]["winner"], smoke["winner"])
        self.assertEqual(result["referee_verdict"]["winner"], smoke["winner"])
        self.assertFalse(result["referee_verdict"]["changed_winner"])
        self.assertFalse(result["referee_verdict"]["upset_allowed"])

    async def test_medium_engine_confidence_allows_referee_upset_recommendation(self):
        async def caller(messages, env=None):
            return (
                "Batman survives the first exchange by avoiding direct trades.\n"
                "Referee verdict: Batman\n"
                "Upset justification: Batman's listed martial arts gives him a narrow tactical path."
            )

        smoke = {**smoke_judge_packet(packet()), "confidence": "medium"}
        result = await judge_fight_packet(
            packet(),
            smoke,
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], smoke["winner"])
        self.assertEqual(result["engine_verdict"]["winner"], smoke["winner"])
        self.assertEqual(result["referee_verdict"]["winner"], "Batman")
        self.assertTrue(result["referee_verdict"]["changed_winner"])
        self.assertTrue(result["referee_verdict"]["upset_allowed"])
        self.assertIn("martial arts", result["referee_verdict"]["upset_justification"])
        self.assertEqual(result["diagnostics"]["engine_verdict"]["winner"], smoke["winner"])

    async def test_empty_llm_text_falls_back_to_deterministic_explanation(self):
        async def caller(messages, env=None):
            return "   "

        smoke = smoke_judge_packet(packet())
        result = await judge_fight_packet(
            packet(),
            smoke,
            env={"BATTLEBOT_LLM_ENABLED": "true"},
            ollama_caller=caller,
        )

        self.assertEqual(result["winner"], smoke["winner"])
        self.assertEqual(result["summary"], smoke["summary"])
        self.assertEqual(result["overall_probability"], smoke["overall_probability"])
        self.assertEqual(result["winner_probability"], smoke["winner_probability"])
        self.assertEqual(result["loser_probability"], smoke["loser_probability"])
        self.assertEqual(result["advantage_breakdown"], smoke["advantage_breakdown"])
        self.assertEqual(result["swing_factors"], smoke["swing_factors"])
        self.assertEqual(result["fight_flow"], smoke["fight_flow"])
        self.assertEqual(result["engine_reasoning"], smoke["engine_reasoning"])
        self.assertEqual(result["engine_verdict"]["fight_flow"], smoke["fight_flow"])
        self.assertEqual(result["engine_verdict"]["engine_reasoning"], smoke["engine_reasoning"])
        self.assertEqual(result["diagnostics"]["fallback_reason"], "Ollama unavailable")

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

    def test_smoke_deciding_factors_include_tactical_effect(self):
        result = smoke_judge_packet(packet())

        self.assertTrue(result["deciding_factors"])
        self.assertIn("tactical_effect", result["deciding_factors"][0])


if __name__ == "__main__":
    unittest.main()
