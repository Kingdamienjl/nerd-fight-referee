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
        self.assertIn("fight scene", user_prompt)
        self.assertIn("opening exchange", user_prompt)
        self.assertIn("loser's best counterplay", user_prompt)
        self.assertIn("safe tactical inference", user_prompt)
        self.assertIn("past tense", user_prompt)
        self.assertIn("post-fight referee explanation", user_prompt)
        self.assertIn("not live play-by-play", user_prompt)
        self.assertIn("loser must make at least one concrete counterplay attempt", user_prompt)
        self.assertIn("Do not require both fighter names in every paragraph", user_prompt)
        self.assertIn('"the opponent"', user_prompt)
        self.assertIn('"his opponent"', user_prompt)
        self.assertIn('"their opponent"', user_prompt)
        self.assertIn("Use fighter names naturally at phase transitions", user_prompt)
        self.assertIn("identify each fighter's combat mode", user_prompt)
        self.assertIn("magic user", user_prompt)
        self.assertIn("cosmic/reality hax user", user_prompt)
        self.assertIn("Do not describe a fighter as relying on punches, kicks, grappling, or mundane melee", user_prompt)
        self.assertIn("signature magic, transformation, ranged powers, purification, barriers", user_prompt)
        self.assertIn("Do not flatten magical, cosmic, ranged, tech, or hax-based fighters into generic brawlers", user_prompt)
        self.assertIn("Only name a technique", user_prompt)
        self.assertIn("exact name appears in the compact evidence packet", user_prompt)
        self.assertIn("invented named techniques", user_prompt)
        self.assertIn("Do not name any technique, form, weapon, power source, eye power", user_prompt)
        self.assertIn('Itachi may use "Sharingan" only if "Sharingan" appears', user_prompt)
        self.assertIn('Itachi may NOT use "Byakugan" unless "Byakugan" appears', user_prompt)
        self.assertIn('Green Lantern may NOT use "Speed Force" unless "Speed Force" appears', user_prompt)
        self.assertIn("Naruto may NOT use invented chakra techniques", user_prompt)
        self.assertIn("as evidenced by the packet", user_prompt)
        self.assertIn("main route stabilizes", user_prompt)
        self.assertIn("Never use these phrases", user_prompt)
        self.assertIn("No JSON.", user_prompt)
        self.assertIn("No bullet lists.", user_prompt)
        self.assertIn("No markdown headings.", user_prompt)
        self.assertNotIn("Referee verdict:", user_prompt)
        self.assertNotIn("Upset justification:", user_prompt)
        self.assertIn("evidence packet is source of truth", user_prompt)
        self.assertIn("tactical_profile", user_prompt)

    def test_prompt_surfaces_sailor_moon_like_non_physical_options(self):
        sailor_packet = {
            "errors": [],
            "contender_a": {
                "canonical_name": "Usagi Tsukino",
                "character_id": "sailor-moon",
                "franchise": "Sailor Moon",
                "category": "anime",
                "power_scale": {"attack_potency": "Moon level", "speed": "Subsonic", "durability": "Building level"},
                "abilities": [
                    {"name": "Transformation"},
                    {"name": "Magic"},
                    {"name": "Purification"},
                    {"name": "Healing"},
                    {"name": "Energy Projection"},
                    {"name": "Barriers"},
                ],
                "equipment": [{"name": "Silver Crystal"}, {"name": "Moon Stick"}, {"name": "{{Border|No|Yes|Content}}"}],
                "tactical_profile": {"combat_style": "magical ranged escalation"},
            },
            "contender_b": contender("Street Fighter", "street-fighter", "Wall level", "Human", "Wall level"),
            "warnings": [],
        }
        smoke = smoke_judge_packet(sailor_packet)
        user_prompt = build_prompt(sailor_packet, smoke)[1]["content"]

        self.assertIn("Silver Crystal", user_prompt)
        self.assertIn("Moon Stick", user_prompt)
        self.assertIn("Purification", user_prompt)
        self.assertIn("Barriers", user_prompt)
        self.assertIn("magical ranged escalation", user_prompt)
        self.assertNotIn("{{Border", user_prompt)

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
