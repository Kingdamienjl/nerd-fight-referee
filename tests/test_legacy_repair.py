import unittest
from services.repair_legacy_profiles import identity_matches, pinned_source

class RepairIdentityTests(unittest.TestCase):
    def test_publisher_label_preserves_identity(self):
        self.assertTrue(identity_matches('Luke Cage','Luke Cage (Marvel Comics)','Marvel'))
        self.assertFalse(identity_matches('Luke Cage','Luke Cage (Marvel Cinematic Universe)','Marvel'))
        self.assertFalse(identity_matches('Kratos (Norse Era)','Kratos','God of War'))

    def test_pinned_page_requires_revision_and_identity(self):
        profile={'name':'Luke Cage','franchise':'Marvel','sources':[{'title':'Luke Cage (Marvel Comics)','url':'https://vsbattles.fandom.com/wiki/Luke_Cage','page_id':'2236','revision_id':'9490799'}]}
        self.assertIsNotNone(pinned_source(profile))
        profile['sources'][0]['revision_id']=''
        self.assertIsNone(pinned_source(profile))

    def test_multiple_distinct_pinned_pages_require_review(self):
        base={'title':'Luke Cage','url':'https://vsbattles.fandom.com/wiki/Luke_Cage','revision_id':'123'}
        profile={'name':'Luke Cage','franchise':'Marvel','sources':[{**base,'page_id':'1'},{**base,'page_id':'2'}]}
        self.assertIsNone(pinned_source(profile))

    def test_shared_name_cannot_cross_franchises(self):
        from battlebot.profiles.source_identity import origin_matches
        self.assertFalse(origin_matches('Cyberpunk 2077','Devil May Cry'))
        self.assertTrue(origin_matches('Marvel','Marvel Comics'))
        self.assertTrue(origin_matches('Attack on Titan','Shingeki no Kyojin'))

class PromotionRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_failure_restores_original_file(self):
        from contextlib import asynccontextmanager
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from services import repair_legacy_profiles as repair
        class Transaction:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): raise RuntimeError('Commit failed')
        db=SimpleNamespace(transaction=Transaction,fetchrow=AsyncMock(return_value=None))
        @asynccontextmanager
        async def connection(*args): yield db
        with TemporaryDirectory() as folder:
            root=Path(folder); path=root/'profile.yaml'; original=b'id: example\nprofile_hash: old\n'
            path.write_bytes(original)
            compiled=SimpleNamespace(profile={'battle_eligible':True})
            with patch.object(repair.CharacterProfile,'model_validate',return_value=object()),patch.object(repair,'compile_profile',return_value=compiled),patch.object(repair,'connect_database',connection),patch.object(repair,'upsert_compiled_profile',AsyncMock()):
                with self.assertRaisesRegex(RuntimeError,'Commit failed'):
                    await repair.promote({'id':'example'},path,original,SimpleNamespace(root=root),root/'archive')
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual((root/'archive'/'original.yaml').read_bytes(),original)

class TitleRecoveryTests(unittest.TestCase):
    def test_discovery_candidate_is_not_repair_evidence(self):
        from services.repair_legacy_profiles import title_source
        p={'name':'Example','franchise':'Test','sources':[{'title':'Example','url':'https://vsbattles.fandom.com/wiki/Example','notes':'enrich_sources_candidate'}]}
        self.assertIsNone(title_source(p))
        p['sources'][0]['raw_cache_key']='previously-fetched'
        self.assertIsNotNone(title_source(p))


class CuratedRosterRecoveryTests(unittest.TestCase):
    def test_unique_curated_roster_mapping_is_repairable_and_fingerprinted(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from services.repair_legacy_profiles import roster_source, source_identity_fingerprint
        with TemporaryDirectory() as folder:
            roster_dir = Path(folder)
            (roster_dir / 'roster.csv').write_text(
                'category,franchise,name,aliases,wiki_title,wiki_url\n'
                'anime,Dragon Ball,Son Goku,Goku,Son Goku (Dragon Ball),\n',
                encoding='utf-8',
            )
            source = roster_source({'name': 'Son Goku', 'franchise': 'Dragon Ball'}, roster_dir)
            self.assertIsNotNone(source)
            self.assertEqual(source['mapping_kind'], 'curated_roster')
            self.assertEqual(source['title'], 'Son Goku (Dragon Ball)')
            first = source_identity_fingerprint(source)
            source['title'] = 'Son Goku'
            self.assertNotEqual(first, source_identity_fingerprint(source))

    def test_conflicting_curated_titles_still_require_review(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from services.repair_legacy_profiles import roster_source
        with TemporaryDirectory() as folder:
            roster_dir = Path(folder)
            (roster_dir / 'roster.csv').write_text(
                'category,franchise,name,aliases,wiki_title,wiki_url\n'
                'comic,Marvel,Luke Cage,,Luke Cage (Marvel Comics),\n'
                'comic,Marvel,Luke Cage,,Luke Cage (Marvel Cinematic Universe),\n',
                encoding='utf-8',
            )
            self.assertIsNone(roster_source({'name': 'Luke Cage', 'franchise': 'Marvel'}, roster_dir))
