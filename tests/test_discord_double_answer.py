"""Discord double-answer fix: defer resilience, replay dedupe, bounded LLM wait.

Covers the 2026-11-17 00:33 fight failure (audit row 69): the /fight
command died at the defer with HTTP 40060 after a gateway resume
redelivered the interaction, and the related failure mode where a
wedged Ollama burns ~38 minutes of retries past Discord's 15-minute
followup window.
"""

import asyncio
import time
import unittest
from unittest.mock import patch

import discord
import httpx

from battlebot.bot.commands import fight as fight_module
from battlebot.bot.commands.fight import (
    _interaction_already_seen,
    defer_fight_response,
)
from battlebot.fight import cached_judge, llm_judge
from battlebot.fight.llm_judge import call_ollama, judge_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet


class _FakeHTTPResponse:
    def __init__(self, status=400):
        self.status = status
        self.reason = "Bad Request"


def _discord_http_error(code):
    return discord.HTTPException(_FakeHTTPResponse(), {"code": code, "message": "test error"})


class _FakeResponse:
    def __init__(self, *, done=False, defer_exc=None):
        self._done = done
        self.defer_exc = defer_exc
        self.defer_calls = []

    def is_done(self):
        return self._done

    async def defer(self, **kwargs):
        self.defer_calls.append(kwargs)
        if self.defer_exc is not None:
            raise self.defer_exc


class _FakeInteraction:
    def __init__(self, interaction_id=123, response=None):
        self.id = interaction_id
        self.response = response if response is not None else _FakeResponse()


def _contender(name, character_id, attack, speed, durability):
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
        "abilities": [],
        "equipment": [],
        "weaknesses": [],
    }


def _packet():
    return {
        "errors": [],
        "contender_a": _contender(
            "Batman", "batman", "Building level", "Peak Human", "Building level"
        ),
        "contender_b": _contender(
            "Superman", "superman", "Solar System level", "Massively FTL+", "Solar System level"
        ),
        "warnings": [],
    }


class _FakeHTTPReply:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHTTPClient:
    """Stand-in for httpx.AsyncClient with scripted post() behavior."""

    def __init__(self, behavior):
        self._behavior = behavior

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return await self._behavior()


def _client_factory(behavior, created):
    def factory(*args, **kwargs):
        client = _FakeHTTPClient(behavior)
        created.append(client)
        return client

    return factory


class DeferResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_defer_success_calls_defer_once(self):
        inter = _FakeInteraction(response=_FakeResponse())
        await defer_fight_response(inter, ephemeral=False)
        self.assertEqual(len(inter.response.defer_calls), 1)
        self.assertTrue(inter.response.defer_calls[0]["thinking"])

    async def test_defer_already_done_skips_defer(self):
        inter = _FakeInteraction(response=_FakeResponse(done=True))
        await defer_fight_response(inter, ephemeral=False)
        self.assertEqual(inter.response.defer_calls, [])

    async def test_defer_40060_is_swallowed_and_continues(self):
        inter = _FakeInteraction(response=_FakeResponse(defer_exc=_discord_http_error(40060)))
        await defer_fight_response(inter, ephemeral=False)
        self.assertEqual(len(inter.response.defer_calls), 1)

    async def test_defer_other_http_error_reraises(self):
        inter = _FakeInteraction(response=_FakeResponse(defer_exc=_discord_http_error(10062)))
        with self.assertRaises(discord.HTTPException):
            await defer_fight_response(inter, ephemeral=False)

    async def test_defer_non_http_error_reraises(self):
        inter = _FakeInteraction(response=_FakeResponse(defer_exc=RuntimeError("boom")))
        with self.assertRaises(RuntimeError):
            await defer_fight_response(inter, ephemeral=False)


class ReplayDedupeTests(unittest.TestCase):
    def setUp(self):
        fight_module._SEEN_INTERACTION_IDS.clear()

    def tearDown(self):
        fight_module._SEEN_INTERACTION_IDS.clear()

    def test_first_seen_returns_false_second_returns_true(self):
        self.assertFalse(_interaction_already_seen(111))
        self.assertTrue(_interaction_already_seen(111))
        self.assertFalse(_interaction_already_seen(222))

    def test_expired_entries_are_pruned(self):
        fight_module._SEEN_INTERACTION_IDS[111] = time.monotonic() - 901.0
        self.assertFalse(_interaction_already_seen(111))

    def test_set_stays_bounded(self):
        for i in range(1005):
            _interaction_already_seen(i)
        self.assertLessEqual(len(fight_module._SEEN_INTERACTION_IDS), 1000)


class FightReplayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fight_module._SEEN_INTERACTION_IDS.clear()

    def tearDown(self):
        fight_module._SEEN_INTERACTION_IDS.clear()

    def _register(self):
        captured = {}

        class FakeTree:
            def command(self, *args, **kwargs):
                def deco(fn):
                    def _autocomplete(*a, **k):
                        def _wrap(f):
                            return f

                        return _wrap

                    fn.autocomplete = _autocomplete
                    captured["fight"] = fn
                    return fn

                return deco

        fight_module.register_fight_command(FakeTree(), database_url="<redacted>")
        return captured["fight"]

    async def test_replayed_interaction_skips_audited_handler(self):
        fight_cb = self._register()
        calls = []

        async def fake_audited(*args, **kwargs):
            calls.append(1)
            return "ok"

        interaction = _FakeInteraction(interaction_id=777)
        fight_module._SEEN_INTERACTION_IDS[777] = time.monotonic()
        with patch.object(fight_module, "run_audited_command", fake_audited):
            await fight_cb(interaction, "Batman", "Superman")
        self.assertEqual(calls, [])

    async def test_fresh_interaction_runs_audited_handler(self):
        fight_cb = self._register()
        calls = []

        async def fake_audited(*args, **kwargs):
            calls.append(1)
            return "ok"

        interaction = _FakeInteraction(interaction_id=778)
        with patch.object(fight_module, "run_audited_command", fake_audited):
            await fight_cb(interaction, "Batman", "Superman")
        self.assertEqual(len(calls), 1)
        self.assertIn(778, fight_module._SEEN_INTERACTION_IDS)


class CallOllamaBudgetTests(unittest.IsolatedAsyncioTestCase):
    def _direct_env(self, **extra):
        env = {"OLLAMA_BASE_URL": "http://127.0.0.1:9"}
        env.update(extra)
        return env

    async def test_wedged_backend_bounded_by_call_budget(self):
        async def slow_wedge():
            await asyncio.sleep(1.5)
            raise httpx.ReadTimeout("wedged")

        created = []
        start = time.monotonic()
        with (
            patch.object(llm_judge.httpx, "AsyncClient", _client_factory(slow_wedge, created)),
            self.assertRaises(httpx.TimeoutException),
        ):
            await call_ollama(
                [{"role": "user", "content": "hi"}],
                env=self._direct_env(),
                timeout=2.0,
            )
        elapsed = time.monotonic() - start
        # Budget defaults to 2x the per-attempt timeout (4s): the stacked
        # unbounded worst case would be 3 attempts + backoffs (~24s).
        self.assertLessEqual(len(created), 2)
        self.assertLess(elapsed, 8.0)

    async def test_call_budget_is_env_tunable(self):
        async def slow_wedge():
            await asyncio.sleep(1.5)
            raise httpx.ReadTimeout("wedged")

        created = []
        start = time.monotonic()
        with (
            patch.object(llm_judge.httpx, "AsyncClient", _client_factory(slow_wedge, created)),
            self.assertRaises(httpx.TimeoutException),
        ):
            await call_ollama(
                [{"role": "user", "content": "hi"}],
                env=self._direct_env(BATTLEBOT_LLM_CALL_BUDGET_SECONDS="1.0"),
                timeout=60.0,
            )
        elapsed = time.monotonic() - start
        self.assertEqual(len(created), 1)
        self.assertLess(elapsed, 5.0)

    async def test_retries_still_run_when_budget_allows(self):
        async def instant_fail():
            raise httpx.ReadTimeout("wedged")

        created = []
        with (
            patch.object(llm_judge.httpx, "AsyncClient", _client_factory(instant_fail, created)),
            self.assertRaises(httpx.TimeoutException),
        ):
            await call_ollama(
                [{"role": "user", "content": "hi"}],
                env=self._direct_env(BATTLEBOT_LLM_CALL_BUDGET_SECONDS="1000"),
                timeout=60.0,
            )
        self.assertEqual(len(created), 3)

    async def test_successful_call_returns_content_unchanged(self):
        async def ok():
            return _FakeHTTPReply({"message": {"content": "hello from the model"}})

        created = []
        with patch.object(llm_judge.httpx, "AsyncClient", _client_factory(ok, created)):
            result = await call_ollama(
                [{"role": "user", "content": "hi"}],
                env=self._direct_env(),
                timeout=60.0,
            )
        self.assertEqual(result, "hello from the model")
        self.assertEqual(len(created), 1)


class JudgeTotalBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_hanging_caller_falls_back_fast_with_timeout_reason(self):
        async def hanging_caller(messages, model=None, env=None):
            await asyncio.sleep(3600)
            return "never"

        hanging_caller.is_2llm = True
        packet = _packet()
        start = time.monotonic()
        result = await judge_fight_packet(
            packet,
            smoke_judge_packet(packet),
            env={
                "BATTLEBOT_LLM_ENABLED": "true",
                "REFEREE_ANALYST_MODEL": "qwen3:8b",
                "REFEREE_VOICE_MODEL": "hermes3:8b",
                "BATTLEBOT_JUDGE_TOTAL_TIMEOUT_SECONDS": "0.5",
            },
            ollama_caller=hanging_caller,
        )
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10.0)
        self.assertTrue(result["diagnostics"]["fallback"])
        self.assertEqual(result["diagnostics"]["fallback_reason"], "timeout")
        self.assertEqual(result["winner"], "Superman")

    async def test_healthy_caller_returns_decision_through_wrapper(self):
        async def multi_caller(messages, model=None, env=None):
            if model == "qwen3:8b":
                return "1. STAT COMPARISON: Superman massively outstats Batman."
            return (
                "Predicted winner: Superman\n"
                "Quick Verdict: Superman overpowers Batman [1].\n"
                "Phase 1: Probing\nSuperman probes [1].\n"
                "Phase 2: Escalation\nBatman counters [1].\n"
                "Phase 3: Climax\nSuperman finishes [1].\n"
                "Difficulty: Extreme Diff"
            )

        multi_caller.is_2llm = True
        packet = _packet()
        result = await judge_fight_packet(
            packet,
            smoke_judge_packet(packet),
            env={
                "BATTLEBOT_LLM_ENABLED": "true",
                "REFEREE_ANALYST_MODEL": "qwen3:8b",
                "REFEREE_VOICE_MODEL": "hermes3:8b",
            },
            ollama_caller=multi_caller,
        )
        self.assertEqual(result["winner"], "Superman")
        self.assertFalse(result["diagnostics"]["fallback"])


class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *args, **kwargs):
        return self._row

    async def execute(self, *args, **kwargs):
        return "UPDATE 1"


class _FakeConnCM:
    def __init__(self, row):
        self._conn = _FakeConn(row)

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class CacheHitStaysOllamaFreeTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_hit_never_calls_judge_fn(self):
        row = {
            "id": 1,
            "verdict_winner": "Superman",
            "difficulty": "Mid Diff",
            "confidence": "high",
            "draft_json": {
                "analyst_breakdown": "cached analysis",
                "fight_verdict": None,
                "diagnostics": {"engine_verdict": "cached engine verdict"},
            },
            "rewritten_json": {
                "phase_1": "cached phase one",
                "phase_2": "cached phase two",
                "phase_3": "cached phase three",
                "quick_verdict": "Superman wins.",
            },
        }
        packet = {
            "contender_a": {
                "character_id": "superman",
                "profile_hash": "hash-a",
                "canonical_name": "Superman",
            },
            "contender_b": {
                "character_id": "batman",
                "profile_hash": "hash-b",
                "canonical_name": "Batman",
            },
        }
        smoke = {
            "winner": "Superman",
            "loser": "Batman",
            "difficulty": "Mid Diff",
            "confidence": "high",
        }

        async def exploding_judge(packet_arg, smoke_arg):
            raise AssertionError("judge_fn must not run on a cache hit")

        with patch.object(cached_judge, "connect_database", lambda *a, **k: _FakeConnCM(row)):
            result = await cached_judge.judge_fight_packet_cached(
                packet, smoke, judge_fn=exploding_judge
            )
        self.assertTrue(result["diagnostics"]["cache_hit"])
        self.assertEqual(result["winner"], "Superman")


if __name__ == "__main__":
    unittest.main()
