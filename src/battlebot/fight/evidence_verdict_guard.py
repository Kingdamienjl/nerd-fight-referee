"""Reject a decisive result whose reasoning assumes an unestablished capability."""
import re

ASSUMED_POWER = re.compile(
    r'\b(?:if|assuming(?: that)?|provided(?: that)?)\s+[^.!?\n]{0,90}?\b'
    r'(?:possesses?|has|had|were to have|could have)\s+'
    r'(?!enough\b|sufficient\b)[^.!?\n]{0,90}?\b'
    r'(?:resistance|immunity|immunities|ability|abilities|power|powers)\b', re.I)
WIN_CLAIM = re.compile(r'\b(?:win|wins|victory|secure a win|defeat|prevail|winner)\b', re.I)


def assumes_decisive_power(text):
    return bool(ASSUMED_POWER.search(str(text)) and WIN_CLAIM.search(str(text)))


def unresolved_assumption_result(packet):
    explanation = ('No winner established: the proposed winning counter depends on an '
                   'ability that the assessment treats as hypothetical. That assumption '
                   'cannot justify a victory; the selected versions need an evidence-backed comparison.')
    return {
        'title':'Nerd Fight Referee Decision','winner':'Unresolved','loser':None,
        'difficulty':'Unresolved','confidence':'needs_judge_review',
        'summary':explanation,'quick_verdict':explanation,'win_condition':explanation,
        'narrative_phases':[], 'presentation_packet':packet,
        'overall_probability':None,'winner_probability':None,'loser_probability':None,
        'referee_verdict':{'winner':'Unresolved','explanation':explanation,'changed_winner':False},
        'diagnostics':{'fallback':True,'fallback_reason':'hypothetical_winning_ability'},
        'warnings':['A hypothetical counter cannot establish the winner.']
    }
