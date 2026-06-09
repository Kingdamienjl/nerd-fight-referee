import unittest

from battlebot.bot.commands.fight import discord_message_from_packet
from battlebot.fight.smoke_judge import smoke_judge_packet


class BotFightCommandTests(unittest.TestCase):
    def test_fight_message_uses_smoke_judge_label(self):
        packet = {
            "errors": [],
            "contender_a": {
                "canonical_name": "Batman",
                "character_id": "batman",
                "power_scale": {
                    "attack_potency": "Building level",
                    "speed": "Peak Human",
                    "durability": "Building level",
                },
            },
            "contender_b": {
                "canonical_name": "Superman",
                "character_id": "superman",
                "power_scale": {
                    "attack_potency": "Solar System level",
                    "speed": "Massively FTL+",
                    "durability": "Solar System level",
                },
            },
            "warnings": [],
        }

        message = discord_message_from_packet(packet, smoke_judge_packet(packet))

        self.assertIn("Smoke Test Decision", message)
        self.assertIn("winner: Superman", message)


if __name__ == "__main__":
    unittest.main()
