import unittest
from services.repair_legacy_profiles import failed_attempt, SourceIdentityReview

class FailureClassificationTests(unittest.TestCase):
    def test_identity_failure_waits_for_evidence_review(self):
        result=failed_attempt(SourceIdentityReview('Missing source identity'))
        self.assertEqual(result['status'],'needs_review')
        self.assertNotIn('retry_after',result)
        self.assertEqual(result['blockers'],['source_identity_unresolved'])

    def test_transient_failure_remains_retryable(self):
        result=failed_attempt(TimeoutError('Source timed out'))
        self.assertEqual(result['status'],'error')
        self.assertGreater(result['retry_after'],0)
