"""Non-fatal audit logging for Discord slash commands."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from battlebot.common.db import apply_schema, connect_database


FALLBACK_AUDIT_LOG = Path("logs/discord_command_audit.jsonl")
SECRET_ENV_KEYS = ("DISCORD_TOKEN", "DATABASE_URL")
MAX_TEXT_LENGTH = 4000


@dataclass
class DiscordCommandAuditEntry:
    command_name: str
    guild_id: str
    channel_id: str
    user_id: str
    user_display_name: str
    options: dict[str, Any]
    response_text: str
    response_is_private: bool
    success: bool
    error_type: str
    error_message: str
    duration_ms: int
    llm_enabled: bool
    llm_model: str


def llm_enabled_from_env(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return str(values.get("BATTLEBOT_LLM_ENABLED") or "").casefold() in {"1", "true", "yes", "on"}


def llm_model_from_env(env: dict[str, str] | None = None) -> str:
    values = env or os.environ
    return sanitize_text(values.get("BATTLEBOT_LLM_MODEL") or values.get("REFEREE_MODEL") or "")


def secret_values() -> list[str]:
    values = []
    for key in SECRET_ENV_KEYS:
        value = os.getenv(key)
        if value:
            values.append(value)
    return values


def sanitize_text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for secret in secret_values():
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"postgres(?:ql)?://\S+", "[REDACTED_DATABASE_URL]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(discord[_ -]?token|bot[_ -]?token)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    return text[:limit]


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {sanitize_text(key, limit=120): sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [sanitize_json(item) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return sanitize_text(value) if isinstance(value, str) else value
    return sanitize_text(value)


def interaction_id(interaction: Any, attr: str) -> str:
    value = getattr(interaction, attr, None)
    return sanitize_text(getattr(value, "id", value), limit=120)


def user_display_name(interaction: Any) -> str:
    user = getattr(interaction, "user", None)
    return sanitize_text(
        getattr(user, "display_name", None)
        or getattr(user, "global_name", None)
        or getattr(user, "name", None)
        or "",
        limit=240,
    )


def user_id(interaction: Any) -> str:
    user = getattr(interaction, "user", None)
    return sanitize_text(getattr(user, "id", ""), limit=120)


def entry_as_json(entry: DiscordCommandAuditEntry) -> dict[str, Any]:
    return {
        "command_name": sanitize_text(entry.command_name, limit=120),
        "guild_id": sanitize_text(entry.guild_id, limit=120),
        "channel_id": sanitize_text(entry.channel_id, limit=120),
        "user_id": sanitize_text(entry.user_id, limit=120),
        "user_display_name": sanitize_text(entry.user_display_name, limit=240),
        "options": sanitize_json(entry.options),
        "response_text": sanitize_text(entry.response_text),
        "response_is_private": bool(entry.response_is_private),
        "success": bool(entry.success),
        "error_type": sanitize_text(entry.error_type, limit=120),
        "error_message": sanitize_text(entry.error_message, limit=1000),
        "duration_ms": max(0, int(entry.duration_ms)),
        "llm_enabled": bool(entry.llm_enabled),
        "llm_model": sanitize_text(entry.llm_model, limit=240),
    }


async def insert_audit_row(connection: Any, entry: DiscordCommandAuditEntry) -> None:
    data = entry_as_json(entry)
    await connection.execute(
        """
INSERT INTO discord_command_audit (
    command_name,
    guild_id,
    channel_id,
    user_id,
    user_display_name,
    options_json,
    response_text,
    response_is_private,
    success,
    error_type,
    error_message,
    duration_ms,
    llm_enabled,
    llm_model
) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14)
""",
        data["command_name"],
        data["guild_id"],
        data["channel_id"],
        data["user_id"],
        data["user_display_name"],
        json.dumps(data["options"]),
        data["response_text"],
        data["response_is_private"],
        data["success"],
        data["error_type"],
        data["error_message"],
        data["duration_ms"],
        data["llm_enabled"],
        data["llm_model"],
    )


def write_jsonl_fallback(entry: DiscordCommandAuditEntry, *, path: Path = FALLBACK_AUDIT_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry_as_json(entry)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


async def record_discord_command_audit(
    entry: DiscordCommandAuditEntry,
    *,
    database_url: str | None = None,
    fallback_path: Path = FALLBACK_AUDIT_LOG,
) -> None:
    try:
        if database_url or os.getenv("DATABASE_URL"):
            async with connect_database(database_url) as connection:
                await apply_schema(connection)
                await insert_audit_row(connection, entry)
            return
    except Exception:
        pass
    try:
        write_jsonl_fallback(entry, path=fallback_path)
    except Exception:
        pass


async def run_audited_command(
    interaction: Any,
    *,
    command_name: str,
    options: dict[str, Any],
    response_is_private: bool,
    database_url: str | None,
    handler: Callable[[], Awaitable[str]],
) -> str:
    started = time.perf_counter()
    response_text = ""
    success = False
    error_type = ""
    error_message = ""
    try:
        response_text = await handler()
        success = True
        return response_text
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = sanitize_text(exc, limit=1000)
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            await record_discord_command_audit(
                DiscordCommandAuditEntry(
                    command_name=command_name,
                    guild_id=interaction_id(interaction, "guild"),
                    channel_id=interaction_id(interaction, "channel"),
                    user_id=user_id(interaction),
                    user_display_name=user_display_name(interaction),
                    options=dict(sanitize_json(options)),
                    response_text=response_text,
                    response_is_private=response_is_private,
                    success=success,
                    error_type=error_type,
                    error_message=error_message,
                    duration_ms=duration_ms,
                    llm_enabled=llm_enabled_from_env(),
                    llm_model=llm_model_from_env(),
                ),
                database_url=database_url,
            )
        except Exception:
            pass
