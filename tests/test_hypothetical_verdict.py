import unittest
from battlebot.fight.llm_judge import llm_explained_decision
from battlebot.fight.evidence_verdict_guard import assumes_decisive_power

class HypotheticalVerdictTests(unittest.TestCase):
    def test_reported_goku_result_cannot_award_win(self):
        raw="Predicted winner: Goku\nQuick Verdict: Goku Black's Time Ring and Kai Kai grant him interdimensional teleportation and time manipulation, allowing him to bypass Goku's speed and power. However, if Goku possesses time resistance, he could counter these tools and secure a win.\nDifficulty: Extreme Diff"
        result=llm_explained_decision({'winner':'Goku','winner_probability':0.8},raw,packet={})
        self.assertEqual(result['winner'],'Unresolved')
        self.assertEqual(result['difficulty'],'Unresolved')
        self.assertIsNone(result['winner_probability'])
        self.assertEqual(result['narrative_phases'],[])

    def test_tactical_condition_is_not_an_invented_power(self):
        self.assertFalse(assumes_decisive_power('If Goku closes the distance, he could win with a documented strike.'))
        self.assertFalse(assumes_decisive_power('If Goku has enough ki, the documented ability could secure a win.'))

    def test_pronoun_assumption_is_also_rejected(self):
        self.assertTrue(assumes_decisive_power('Assuming he has temporal immunity, he could win.'))
