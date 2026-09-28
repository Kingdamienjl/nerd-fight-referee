import unittest
from types import SimpleNamespace
from unittest.mock import patch
from battlebot.harvest.loop import import_if_changed

class ImportSnapshotTests(unittest.TestCase):
    def test_unchanged_profiles_import_only_once(self):
        state={}
        with patch('battlebot.harvest.loop.generated_snapshot',return_value='same'),patch('battlebot.harvest.loop.run_bounded',return_value=SimpleNamespace(returncode=0)) as run:
            import_if_changed(state);import_if_changed(state)
        self.assertEqual(run.call_count,1)

    def test_failed_import_is_retried_without_new_harvest(self):
        state={}
        with patch('battlebot.harvest.loop.generated_snapshot',return_value='same'),patch('battlebot.harvest.loop.run_bounded',side_effect=[SimpleNamespace(returncode=1),SimpleNamespace(returncode=0)]) as run:
            import_if_changed(state);self.assertNotIn('last_import_snapshot',state);import_if_changed(state)
        self.assertEqual(run.call_count,2)
        self.assertEqual(state['last_import_snapshot'],'same')

    def test_changed_profiles_trigger_import(self):
        state={'last_import_snapshot':'old'}
        with patch('battlebot.harvest.loop.generated_snapshot',return_value='new'),patch('battlebot.harvest.loop.run_bounded',return_value=SimpleNamespace(returncode=0)) as run:
            import_if_changed(state)
        run.assert_called_once()
        self.assertEqual(state['last_import_snapshot'],'new')
