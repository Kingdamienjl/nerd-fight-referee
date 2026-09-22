import asyncio
import json
import unittest
from unittest.mock import patch
from battlebot.fight.llm_judge import compact_evidence_packet, build_referee_stage2_prompt, call_ollama, _invoke_caller, referee_winner_from_text
from battlebot.fight.presentation import present_decision
from battlebot.fight.personality import generate_fallback_phases
from battlebot.fight.citations import power_summary
from battlebot.profiles.readiness import assess_readiness
from battlebot.profiles.store import resolve_character
from tests.test_profile_store import FakeProfileConnection, profile_row


def evidence():
    return {'power_scale': {axis: {'text': 'Building level' if axis != 'speed' else 'Supersonic', 'source_ids': ['s']} for axis in ('attack_potency', 'speed', 'durability')},
            'sources': [{'id': 's', 'url': 'https://example.com/evidence', 'title': 'Test evidence'}],
            'abilities': [{'name': 'Shield', 'description': 'Protects against the documented attack only while powered.', 'source_ids': ['s'], 'activation_requirements': ['Must be raised'], 'counters': ['Power disruption'], 'resource_dependencies': ['Battery'], 'scope_limitations': ['Forward arc only']}]}


class ProductionReadinessTests(unittest.IsolatedAsyncioTestCase):
    def test_readiness_rejects_mixed_eras(self):
        p = evidence()
        self.assertTrue(assess_readiness(p)['battle_ready'])
        p['power_scale']['speed']['text'] = 'Supersonic | FTL'
        self.assertFalse(assess_readiness(p)['battle_ready'])

    def test_broken_source_reference_cannot_qualify(self):
        p = evidence(); p['abilities'][0]['source_ids'] = ['absent']
        self.assertFalse(assess_readiness(p)['battle_ready'])

    async def test_form_does_not_relabel_base(self):
        result = await resolve_character(FakeProfileConnection([profile_row('kratos', 'Kratos')]), 'Kratos (Norse Era)')
        self.assertEqual(result['status'], 'not_found')
        self.assertEqual(result['reason'], 'version_evidence_unavailable')

    def test_evidence_preserves_conditions_and_references(self):
        p = evidence(); c = {'canonical_name': 'Test', 'abilities': p['abilities'], 'sources': p['sources'], 'power_scale': {'speed': 'Supersonic'}, 'power_scale_source_ids': {'speed': ['s']}}
        packet = {'contender_a': c, 'contender_b': c, 'rules': {'arena': 'Underwater', 'energy_equalization': True}}
        compact = compact_evidence_packet(packet, {})
        item = compact['contenders']['contender_a']['abilities'][0]
        for key in ('activation_requirements', 'counters', 'resource_dependencies', 'scope_limitations', 'source_refs'):
            self.assertTrue(item[key])
        self.assertEqual(compact['rules']['arena'], 'Underwater')
        prompt = build_referee_stage2_prompt(packet, {}, 'Analyst draft')
        self.assertIn('EVIDENCE PACKET', prompt[1]['content'])
        self.assertIn('Must be raised', prompt[1]['content'])

    async def test_actual_request_uses_selected_model(self):
        calls=[]
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'message': {'content': 'ok'}}
        class Client:
            def __init__(self,*a,**kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*a): pass
            async def post(self,url,json): calls.append(json); return Response()
        with patch('battlebot.fight.llm_judge.httpx.AsyncClient',Client):
            await _invoke_caller(call_ollama, [], model='hermes3:8b', env={'BATTLEBOT_LLM_MODEL':'qwen3:8b'})
        self.assertEqual(calls[0]['model'], 'hermes3:8b')

    def test_unknown_winner_and_stats_are_not_filled_in(self):
        self.assertEqual(referee_winner_from_text('No complete result.', ['A','B']), 'Unresolved')
        self.assertIn('Unresolved', power_summary('Building | Planet'))
        for text in generate_fallback_phases({}):
            self.assertIn('unavailable', text)
            self.assertNotIn('concluding strike', text)

    def test_shared_presentation_keeps_actual_phases_and_difficulty(self):
        d={'winner':'A','confidence':'medium','difficulty':'Low Diff','quick_verdict':'A could counter B. [1]', 'narrative_phases':['Opening [1]','Tools [1]','Finish [1]'], 'presentation_packet': {'contender_a':{'canonical_name':'A','sources':[{'id':'s','title':'Test','url':'https://example.com'}]},'contender_b':{'canonical_name':'B'}}}
        result=present_decision(d)
        self.assertEqual(result['difficulty'],'Low Diff')
        self.assertIn('Opening',result['sections']['phase_0'])
        self.assertTrue(result['sources'])

class SourceScopeTests(unittest.TestCase):
    def test_source_scope_never_inherits_unscoped_abilities(self):
        from battlebot.harvest.version_scope import scope_extracted_fields
        fields={'keys':'Early | Late','attack_potency':'Building | Planet','speed':'Subsonic | FTL','durability':'Building | Planet','powers_and_abilities':'Shared-looking unspecific powers'}
        self.assertIsNone(scope_extracted_fields(fields,'Late'))
        fields['powers_and_abilities']='Early=First skill | Late=Later skill'
        result=scope_extracted_fields(fields,'Late')
        self.assertEqual(result['speed'],'FTL')
        self.assertEqual(result['powers_and_abilities'],'Later skill')

    def test_keys_stop_at_identity_fields(self):
        from battlebot.harvest.auto_profile_harvester import build_forms
        forms=build_forms({'keys':'Early | Late Name: Example Age: 30'})
        self.assertEqual([x['name'] for x in forms],['Early','Late'])

class WebIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_delivers_phases_without_webhook(self):
        import httpx
        from contextlib import asynccontextmanager
        from battlebot.web import server
        from unittest.mock import AsyncMock
        @asynccontextmanager
        async def connection(*a,**kw):yield object()
        packet={'errors':[], 'contender_a':{'canonical_name':'A','abilities':[],'power_scale':{}},'contender_b':{'canonical_name':'B','abilities':[],'power_scale':{}}}
        decision={'winner':'A','difficulty':'Low Diff','quick_verdict':'Controlled test response.','narrative_phases':['Actual opening','Actual escalation','Actual finish'],'presentation_packet':packet}
        with patch.object(server,'connect_database',connection),patch.object(server,'build_fight_packet',AsyncMock(return_value=packet)),patch.object(server,'judge_fight_packet',AsyncMock(return_value=decision)),patch.object(server,'dispatch_discord_webhook',AsyncMock()) as dispatch:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.create_app()),base_url='http://test') as client:
                response=await client.post('/api/fight',json={'contender_a':'A','contender_b':'B','dispatch_webhook':False})
            self.assertEqual(response.status_code,200)
            result=response.json()['decision']
            self.assertEqual(result['difficulty'],'Low Diff')
            self.assertIn('Actual opening',result['sections']['phase_0'])
            dispatch.assert_not_awaited()

class ResistanceEvidenceTests(unittest.TestCase):
    def test_defensive_list_never_creates_offensive_items(self):
        from battlebot.harvest.auto_profile_harvester import split_listish
        parts = split_listish("Superhuman strength, Resistance to Fire Manipulation, Electricity Manipulation (limited to low voltage), Mind Manipulation")
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[1].startswith("Resistance to"))
        self.assertIn("limited to low voltage", parts[1])

    def test_model_receives_defense_as_defense(self):
        p = evidence()
        c = {'canonical_name': 'Test', 'resistances': p['abilities'], 'sources': p['sources']}
        packet = compact_evidence_packet({'contender_a': c, 'contender_b': c}, {})
        side = packet['contenders']['contender_a']
        self.assertEqual(side['abilities'], [])
        self.assertEqual(side['resistances'][0]['source_refs'], [1])

class SearchReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_profile_is_discoverable_but_not_ready(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import yaml
        from battlebot.profiles.search import search_characters
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'example.yaml').write_text(yaml.safe_dump({'name':'Example', 'battle_eligible':True}), encoding='utf-8')
            rows = await search_characters('Example', generated_dir=root, needs_review_dir=root/'absent', rosters_dir=root/'absent')
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]['battle_ready'])
            self.assertTrue(rows[0]['reason'])

class CitationIntegrityTests(unittest.TestCase):
    def test_grouped_references_preserve_every_number(self):
        from battlebot.fight.citations import normalize_references, cited_numbers
        self.assertEqual(normalize_references('A [1, 2, 999]'), 'A [1] [2] [999]')
        self.assertEqual(cited_numbers('A [1, 2, 999]'), [1, 2, 999])

    def test_model_link_cannot_override_catalog(self):
        from battlebot.fight.citations import linked_citations
        packet = {'contender_a': {'sources': [{'id':'s', 'url':'https://example.com/real'}]}}
        rendered = linked_citations('Claim [1](https://untrusted.invalid/fake) [2]', packet)
        self.assertIn('[1](https://example.com/real)', rendered)
        self.assertNotIn('untrusted.invalid', rendered)
        self.assertIn('[source unavailable]', rendered)
        self.assertEqual(linked_citations(rendered, packet), rendered)

class LegacyExtractionReadinessTests(unittest.TestCase):
    def test_detached_clause_is_not_fight_ready(self):
        p = evidence()
        p['abilities'][0]['description'] = 'Can breathe underwater.) Water manipulation'
        self.assertIn('fragmented_ability_evidence', assess_readiness(p)['blockers'])

    def test_legacy_mixed_defense_requires_reextraction(self):
        p = evidence()
        p['abilities'][0]['description'] = 'Strength, Resistance to Fire Manipulation'
        self.assertIn('unclassified_defensive_evidence', assess_readiness(p)['blockers'])

    def test_defense_in_its_own_section_is_allowed(self):
        p = evidence()
        p['resistances'] = [{'name':'Fire resistance','description':'Resistance to Fire Manipulation','source_ids':['s']}]
        self.assertTrue(assess_readiness(p)['battle_ready'])

    def test_source_id_cannot_refer_to_two_pages(self):
        p = evidence()
        p['sources'].append({'id':'s','url':'https://example.com/different'})
        self.assertIn('ambiguous_source_identity', assess_readiness(p)['blockers'])

class SourceBulletTests(unittest.TestCase):
    def test_wiki_bullets_keep_complete_abilities(self):
        from battlebot.harvest.auto_profile_harvester import split_listish
        items = split_listish('*Strength *Regeneration (Mid-Low) *Vibration (Thunderclap.) *Resistance to Fire, Cold')
        self.assertEqual(items, ['Strength','Regeneration (Mid-Low)','Vibration (Thunderclap.)','Resistance to Fire, Cold'])
