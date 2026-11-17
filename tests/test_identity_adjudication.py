"""Focused tests for the gated identity-adjudication rescue step.

Proves: (a) flag OFF = identical behavior, zero calls; (b) flag ON + mocked
YES = rescued into the pipeline; (c) NO/UNCERTAIN/error = stays rejected;
(d) per-cycle cap enforced; plus memo reuse, URL omission, and pre-filtering.
All LLM calls and intro fetches are faked; no network, no DB writes.
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebot.review import identity_adjudication
from battlebot.review.auto_repair import (
    IDENTITY_MATCH_THRESHOLD,
    SourceAttempt,
    eligible_primary_attempts,
)


def _profile():
    return {
        "name": "Batman",
        "franchise": "DC",
        "aliases": ["The Dark Knight"],
        "identity": {"aliases": ["Bruce Wayne"]},
    }


def _attempt(**overrides):
    fields = {
        "source_id": "src-batman-1",
        "url": "https://vsbattles.fandom.com/wiki/Batman",
        "ok": True,
        "note": "ok",
        "normalized_page_title": "Batman",
        "fetch_status": "fetched",
        "identity_score": 0,
        "identity_match": False,
        "variant_score": 0,
        "core_field_count": 3,
        "ability_count": 1,
        "promotion_allowed": True,
        "continuity_mismatch": False,
        "extracted_fields": ["attack_potency", "speed", "durability", "powers_and_abilities"],
        "duplicate_key": "dup-batman",
    }
    fields.update(overrides)
    return SourceAttempt(**fields)


class FakeCaller:
    """Stand-in for call_ollama: returns preset JSON verdicts, records calls."""

    def __init__(self, verdicts, *, fail=False):
        self.verdicts = list(verdicts)
        self.fail = fail
        self.calls = []

    async def __call__(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        request_info = kwargs.get("request_info")
        if isinstance(request_info, dict):
            request_info["model_group"] = "referee-rewrite-together"
        if self.fail:
            raise RuntimeError("judge exploded")
        verdict = self.verdicts.pop(0) if self.verdicts else "uncertain"
        return json.dumps({"verdict": verdict, "reason": f"fake {verdict}"})


async def _fake_intro(api_url, title):
    return ("Batman is a DC Comics superhero who fights crime in Gotham City.", "ok", title)


class AdjudicationTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "adjudications.jsonl"
        identity_adjudication.reset_cycle_budget()
        identity_adjudication._reset_memo_cache()

    def tearDown(self):
        identity_adjudication.reset_cycle_budget()
        identity_adjudication._reset_memo_cache()
        self._tmp.cleanup()

    def _env(self, **overrides):
        env = {"IDENTITY_ADJUDICATION_ENABLED": "1", "IDENTITY_ADJUDICATION_MAX_CALLS": "10"}
        env.update(overrides)
        return patch.dict(os.environ, env, clear=True)

    def _audit_records(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]


class FlagOffTests(AdjudicationTestBase):
    async def test_flag_off_is_pure_noop(self):
        caller = FakeCaller(["yes"])
        attempt = _attempt()
        with patch.dict(os.environ, {}, clear=True):
            result = await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertIs(result[0], attempt)
        self.assertEqual(caller.calls, [])
        self.assertFalse(attempt.identity_match)
        self.assertEqual(attempt.identity_score, 0)
        self.assertEqual(attempt.adjudication_verdict, "")
        self.assertFalse(self.audit_path.exists())


class RescueTests(AdjudicationTestBase):
    async def test_yes_rescues_into_pipeline(self):
        caller = FakeCaller(["yes"])
        attempt = _attempt()
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertEqual(len(caller.calls), 1)
        self.assertTrue(attempt.identity_match)
        self.assertEqual(attempt.identity_score, IDENTITY_MATCH_THRESHOLD)
        self.assertEqual(attempt.adjudication_original_score, 0)
        self.assertEqual(attempt.adjudication_verdict, "yes")
        self.assertEqual(attempt.adjudication_backend, "referee-rewrite-together")
        self.assertFalse(attempt.adjudication_cached)
        # The rescued attempt is now eligible for primary selection.
        self.assertIn(attempt, eligible_primary_attempts([attempt]))
        records = self._audit_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verdict"], "yes")
        self.assertEqual(records[0]["identity_score"], 0)
        self.assertEqual(records[0]["source_id"], "src-batman-1")

    async def test_no_stays_rejected(self):
        caller = FakeCaller(["no"])
        attempt = _attempt()
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertFalse(attempt.identity_match)
        self.assertEqual(attempt.identity_score, 0)
        self.assertIsNone(attempt.adjudication_original_score)
        self.assertEqual(attempt.adjudication_verdict, "no")
        self.assertEqual(eligible_primary_attempts([attempt]), [])

    async def test_uncertain_stays_rejected(self):
        caller = FakeCaller(["uncertain"])
        attempt = _attempt()
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertFalse(attempt.identity_match)
        self.assertEqual(attempt.adjudication_verdict, "uncertain")
        self.assertEqual(eligible_primary_attempts([attempt]), [])

    async def test_judge_error_stays_rejected_and_is_not_memoized(self):
        caller = FakeCaller([], fail=True)
        attempt = _attempt()
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        # Both passes called the judge: errors are never memoized.
        self.assertEqual(len(caller.calls), 2)
        self.assertFalse(attempt.identity_match)
        self.assertEqual(attempt.adjudication_verdict, "error")
        records = self._audit_records()
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r["verdict"] == "error" for r in records))


class CapAndMemoTests(AdjudicationTestBase):
    async def test_cap_enforced_and_reset_reopens_budget(self):
        caller = FakeCaller(["yes", "yes", "yes"])
        attempts = [_attempt(source_id=f"src-{i}", duplicate_key=f"dup-{i}") for i in range(3)]
        with self._env(IDENTITY_ADJUDICATION_MAX_CALLS="2"):
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), attempts, caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertEqual(len(caller.calls), 2)
        self.assertTrue(attempts[0].identity_match)
        self.assertTrue(attempts[1].identity_match)
        self.assertFalse(attempts[2].identity_match)
        self.assertEqual(attempts[2].adjudication_verdict, "")
        identity_adjudication.reset_cycle_budget()
        with self._env(IDENTITY_ADJUDICATION_MAX_CALLS="2"):
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), attempts[2:], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertEqual(len(caller.calls), 3)
        self.assertTrue(attempts[2].identity_match)

    async def test_memo_reuse_applies_verdict_without_calling(self):
        record = {
            "timestamp": "2026-11-16T00:00:00+00:00",
            "profile": "batman",
            "source_id": "src-batman-1",
            "served_title": "Batman",
            "identity_score": 0,
            "evidence": {"name": "Batman"},
            "verdict": "yes",
            "reason": "recorded yes",
            "parse_note": None,
            "backend": "referee-rewrite-together",
            "model": "referee-rewrite-together",
            "usage": None,
            "estimated_cost_usd": 0.0005,
            "cached": False,
        }
        self.audit_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        caller = FakeCaller(["no"])
        attempt = _attempt()
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [attempt], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertEqual(caller.calls, [])
        self.assertTrue(attempt.identity_match)
        self.assertTrue(attempt.adjudication_cached)
        self.assertEqual(attempt.adjudication_reason, "recorded yes")


class EvidenceAndPrefilterTests(AdjudicationTestBase):
    def test_user_prompt_omits_url(self):
        prompt = identity_adjudication.build_user_prompt(
            name="Batman",
            franchise="DC",
            aliases=["The Dark Knight"],
            served_title="Batman",
            intro="Batman is a DC Comics superhero.",
        )
        self.assertIn("Title: Batman", prompt)
        self.assertIn("Batman is a DC Comics superhero.", prompt)
        self.assertNotIn("vsbattles.fandom.com", prompt)
        self.assertNotIn("http", prompt.lower())

    async def test_audit_record_evidence_has_no_url(self):
        caller = FakeCaller(["yes"])
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), [_attempt()], caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        records = self._audit_records()
        self.assertEqual(len(records), 1)
        self.assertNotIn("url", records[0]["evidence"])
        self.assertNotIn("url", json.dumps(records[0]["evidence"]))

    async def test_prefilter_skips_ineligible_attempts(self):
        caller = FakeCaller(["yes", "yes", "yes"])
        cases = [
            _attempt(core_field_count=2),
            _attempt(identity_match=True, identity_score=100),
            _attempt(continuity_mismatch=True),
            _attempt(fetch_status="failed"),
            _attempt(promotion_allowed=False),
        ]
        with self._env():
            await identity_adjudication.maybe_adjudicate_attempts(
                _profile(), cases, caller=caller, intro_fetcher=_fake_intro,
                audit_path=self.audit_path,
            )
        self.assertEqual(caller.calls, [])
        self.assertFalse(self.audit_path.exists())


class ParseTests(unittest.TestCase):
    def test_clean_json(self):
        verdict, reason, note = identity_adjudication.parse_adjudication(
            '{"verdict": "yes", "reason": "same guy"}'
        )
        self.assertEqual((verdict, reason, note), ("yes", "same guy", None))

    def test_brace_extraction(self):
        verdict, _, note = identity_adjudication.parse_adjudication(
            'Here is my verdict:\n{"verdict": "no", "reason": "different"}\nDone.'
        )
        self.assertEqual(verdict, "no")
        self.assertEqual(note, "brace-extracted")

    def test_bad_verdict_degrades_to_uncertain(self):
        verdict, _, note = identity_adjudication.parse_adjudication(
            '{"verdict": "maybe", "reason": "unsure"}'
        )
        self.assertEqual(verdict, "uncertain")
        self.assertIn("bad-verdict", note)

    def test_garbage_degrades_to_uncertain(self):
        verdict, _, note = identity_adjudication.parse_adjudication("not json at all")
        self.assertEqual(verdict, "uncertain")
        self.assertIn("parse-failed", note)


if __name__ == "__main__":
    unittest.main()
