import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('referee_supervisor', Path(__file__).resolve().parents[1] / 'services' / 'referee_supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class SupervisorTests(unittest.TestCase):
    def test_stopped_service_is_recovered(self):
        self.assertEqual(supervisor.recovery_action({'Status': 'exited'}, 0, 1000), 'start')

    def test_missing_service_is_created(self):
        self.assertEqual(supervisor.recovery_action(None, 0, 1000), 'create')

    def test_restart_backoff_prevents_restart_storm(self):
        self.assertIsNone(supervisor.recovery_action({'Status': 'exited'}, 900, 1000))

    def test_healthy_running_and_restarting_are_not_interrupted(self):
        for state in [{'Status': 'running', 'Running': True}, {'Status': 'restarting'}]:
            self.assertIsNone(supervisor.recovery_action(state, 0, 1000))

    def test_unhealthy_service_is_restarted(self):
        self.assertEqual(supervisor.recovery_action({'Status': 'running', 'Running': True, 'Health': {'Status': 'unhealthy'}}, 0, 1000), 'restart')

    def test_dry_run_cannot_recover_or_notify(self):
        with patch.object(supervisor, 'inspect_service', return_value={'Status': 'exited'}), patch.object(supervisor, 'recover') as recover, patch.object(supervisor, 'notify') as notify:
            supervisor.check(Path('.'), {}, dry_run=True)
            recover.assert_not_called()
            notify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
