"""Discord Webhook Dispatcher for Nerd Fight Referee."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)


def build_confidence_color(confidence: str) -> int:
    norm = str(confidence or "").casefold()
    if norm in {"strong", "high"}:
        return 0x10B981  # Emerald
    if "medium" in norm:
        return 0xF59E0B  # Amber
    if "low" in norm or "close" in norm:
        return 0xF97316  # Orange
    if "upset" in norm or "uncertain" in norm:
        return 0xD946EF  # Fuchsia
    return 0x64748B  # Slate


def build_discord_webhook_payload(
    decision: dict[str, Any],
    *,
    contender_a_name: str,
    contender_b_name: str,
    image_a_url: str | None = None,
    image_b_url: str | None = None,
    custom_note: str | None = None,
) -> dict[str, Any]:
    """Assemble a rich, beautifully structured Discord embed payload for webhook delivery."""
    title = decision.get("display_title") or f"⚔️ {contender_a_name.upper()} VS {contender_b_name.upper()}"
    winner = decision.get("winner") or "Undetermined"
    loser = decision.get("loser") or ""
    confidence = decision.get("confidence") or "Moderate"
    color = build_confidence_color(confidence)
    odds = decision.get("battle_odds_text") or "Even odds"
    summary = decision.get("public_summary") or decision.get("summary") or "Matchup evaluated under standard conditions."

    card_a = decision.get("contender_a_card") or {}
    card_b = decision.get("contender_b_card") or {}

    tools_a = " • ".join(card_a.get("key_tools", [])[:3]) or "Standard combat capabilities"
    tools_b = " • ".join(card_b.get("key_tools", [])[:3]) or "Standard combat capabilities"
    win_a = card_a.get("win_path") or "Presses combat advantages to control the pace."
    win_b = card_b.get("win_path") or "Presses combat advantages to control the pace."

    embed_fields = [
        {
            "name": f"🥊 {contender_a_name} — Fight Card",
            "value": f"**Signature Tools**: {tools_a}\n**Win Route**: {win_a[:280]}",
            "inline": True,
        },
        {
            "name": f"🥊 {contender_b_name} — Fight Card",
            "value": f"**Signature Tools**: {tools_b}\n**Win Route**: {win_b[:280]}",
            "inline": True,
        },
        {
            "name": "⚡ Quick Verdict",
            "value": f"{summary[:800]}",
            "inline": False,
        },
        {
            "name": "📊 Battle Assessment",
            "value": f"**Victor**: {winner} ({confidence.title()} Confidence)\n**Odds**: {odds}",
            "inline": False,
        },
    ]

    # Add play-by-play excerpt if available
    sections = decision.get("sections") or {}
    full_battle = sections.get("full_battle") or ""
    if full_battle:
        excerpt = full_battle.strip().replace("\n\n", "\n")[:450]
        embed_fields.append({
            "name": "🥊 Play-by-Play Climax",
            "value": excerpt + "...",
            "inline": False,
        })

    embed_fields.append({
        "name": "🌐 Live Battle Arena",
        "value": "[Open Nerd Referee Web Portal](https://altprox.tail4e8997.ts.net/)\n*Simulate custom conditions, active forms & arenas in real time.*",
        "inline": False,
    })

    embed: dict[str, Any] = {
        "title": title,
        "url": "https://altprox.tail4e8997.ts.net/",
        "description": "Evidence-backed matchup arbitrated by Nerd Fight Referee.",
        "color": color,
        "fields": embed_fields,
        "footer": {
            "text": "Nerd Fight Referee • Web Portal & Match Simulator",
            "icon_url": "https://cdn.discordapp.com/embed/avatars/0.png",
        },
    }


    if image_a_url and image_a_url.startswith("http"):
        embed["thumbnail"] = {"url": image_a_url}
    elif image_b_url and image_b_url.startswith("http"):
        embed["thumbnail"] = {"url": image_b_url}

    payload: dict[str, Any] = {
        "username": "Nerd Fight Referee",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/1.png",
        "content": custom_note or f"🚨 **DUEL SIMULATED**: `{contender_a_name}` vs `{contender_b_name}`! Results in:",
        "embeds": [embed],
    }
    return payload


async def dispatch_discord_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Post match embed payload directly to Discord Webhook."""
    if not webhook_url:
        return {"ok": False, "error": "No DISCORD_WEBHOOK_URL configured."}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code in (200, 204):
                LOGGER.info("Successfully dispatched duel result to Discord webhook.")
                return {"ok": True, "status_code": response.status_code}
            LOGGER.warning("Discord webhook returned %d: %s", response.status_code, response.text)
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:400],
            }
    except Exception as exc:
        LOGGER.error("Failed to post to Discord webhook: %s", exc)
        return {"ok": False, "error": str(exc)}
