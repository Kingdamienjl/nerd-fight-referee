"""FastAPI Server for Nerd Fight Referee Web Portal."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from battlebot.common.db import connect_database
from battlebot.profiles.search import search_characters
from battlebot.profiles.variants import CURATED_VARIANTS, split_variant_name
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.decision_formatter import structured_decision_output
from battlebot.web.webhook import build_discord_webhook_payload, dispatch_discord_webhook
from battlebot.web.image_finder import find_character_image

LOGGER = logging.getLogger("battlebot.web")
STATIC_DIR = Path(__file__).resolve().parent / "static"


def available_forms_for_query(query: str) -> list[str]:
    """Return all available canonical forms/variants for a character name."""
    if not query:
        return []
    parent, _ = split_variant_name(query)
    target = (parent or query).strip().casefold()
    forms: list[str] = []
    for seed in CURATED_VARIANTS:
        if (
            seed.parent_name.casefold() == target
            or seed.name.casefold() == target
            or any(target == a.casefold() for a in seed.aliases.split("|") if a)
        ):
            if seed.variant_name and seed.variant_name not in forms:
                forms.append(seed.variant_name)
    return forms


class FightRequest(BaseModel):
    contender_a: str
    form_a: str | None = None
    image_a: str | None = None
    contender_b: str
    form_b: str | None = None
    image_b: str | None = None
    arena: str = "Neutral Arena"
    prep_time: str = "Standard Encounter"
    energy_equalization: bool = False
    dispatch_webhook: bool = True
    custom_note: str | None = None


class WebhookDispatchRequest(BaseModel):
    decision: dict[str, Any]
    contender_a: str
    contender_b: str
    image_a_url: str | None = None
    image_b_url: str | None = None
    custom_note: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nerd Fight Referee Portal",
        description="Interactive fight commands, search, live simulation, and webhook dispatcher.",
        version="1.0.0",
    )

    # Enable CORS for cross-origin or local port requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/api/health")
    async def health_check():
        db_url = os.getenv("DATABASE_URL")
        webhook_set = bool(os.getenv("DISCORD_WEBHOOK_URL"))
        return {
            "status": "online",
            "service": "Nerd Fight Referee Portal",
            "database_configured": bool(db_url),
            "webhook_configured": webhook_set,
            "llm_model": os.getenv("BATTLEBOT_LLM_MODEL", "qwen3:8b"),
        }

    @app.get("/api/search")
    async def search_fighters(q: str = Query("", min_length=1), limit: int = Query(12, ge=1, le=30)):
        database_url = os.getenv("DATABASE_URL")
        try:
            if database_url:
                async with connect_database(database_url) as connection:
                    results = await search_characters(q, connection=connection, limit=limit)
            else:
                results = await search_characters(q, limit=limit)
        except Exception as exc:
            LOGGER.warning("Search failed with db, falling back without db: %s", exc)
            results = await search_characters(q, limit=limit)

        payload = []
        for r in results:
            name = r.get("canonical_name") or ""
            forms = available_forms_for_query(name)
            payload.append({
                "name": name,
                "franchise": r.get("franchise") or "Unknown Franchise",
                "category": r.get("category") or "Unknown Category",
                "battle_ready": r.get("battle_ready", False),
                "status": r.get("status") or "stub",
                "reason": r.get("reason") or "",
                "forms": forms,
            })
        return {"query": q, "count": len(payload), "results": payload}

    @app.get("/api/forms")
    async def get_forms(name: str = Query(..., min_length=1)):
        forms = available_forms_for_query(name)
        return {"name": name, "forms": forms}

    @app.get("/api/character-image")
    async def get_character_image(name: str = Query(..., min_length=1), franchise: str = Query("")):
        image_url = await find_character_image(name, franchise=franchise)
        return {
            "name": name,
            "image_url": image_url or "https://placehold.co/400x550/111827/06B6D4?text=" + name.replace(" ", "+"),
        }

    @app.post("/api/fight")
    async def execute_fight(request: FightRequest):
        name_a = request.contender_a.strip()
        name_b = request.contender_b.strip()

        if not name_a or not name_b:
            raise HTTPException(status_code=400, detail="Both contenders must be specified.")

        query_a = f"{name_a} ({request.form_a})" if request.form_a and request.form_a.lower() != "base" else name_a
        query_b = f"{name_b} ({request.form_b})" if request.form_b and request.form_b.lower() != "base" else name_b

        rules = {
            "energy_equalization": request.energy_equalization,
            "arena": request.arena,
            "prep_time": request.prep_time,
        }
        database_url = os.getenv("DATABASE_URL")
        async with connect_database(database_url) as connection:
            packet = await build_fight_packet(
                connection,
                query_a,
                query_b,
                rules=rules,
            )

        if packet.get("errors"):
            return {
                "ok": False,
                "errors": packet["errors"],
                "message": "One or more characters are not battle-ready yet.",
                "packet": packet,
            }

        smoke_result = smoke_judge_packet(packet)
        decision = await judge_fight_packet(packet, smoke_result)
        from battlebot.fight.presentation import present_decision
        structured = present_decision(decision)

        webhook_result: dict[str, Any] | None = None
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

        if request.dispatch_webhook and webhook_url:
            webhook_payload = build_discord_webhook_payload(
                structured,
                contender_a_name=name_a,
                contender_b_name=name_b,
                image_a_url=request.image_a,
                image_b_url=request.image_b,
                custom_note=request.custom_note,
            )
            webhook_result = await dispatch_discord_webhook(webhook_url, webhook_payload)

        return {
            "ok": True,
            "contender_a": name_a,
            "query_a": query_a,
            "image_a": request.image_a,
            "contender_b": name_b,
            "query_b": query_b,
            "image_b": request.image_b,
            "decision": structured,
            "raw_decision": decision,
            "smoke_result": smoke_result,
            "webhook_result": webhook_result,
        }

    @app.post("/api/webhook/dispatch")
    async def dispatch_webhook_manual(req: WebhookDispatchRequest):
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            raise HTTPException(status_code=400, detail="DISCORD_WEBHOOK_URL is not set.")

        payload = build_discord_webhook_payload(
            req.decision,
            contender_a_name=req.contender_a,
            contender_b_name=req.contender_b,
            image_a_url=req.image_a_url,
            image_b_url=req.image_b_url,
            custom_note=req.custom_note,
        )
        res = await dispatch_discord_webhook(webhook_url, payload)
        return res

    @app.get("/")
    async def serve_index():
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse({"message": "Nerd Fight Referee Web API online. Visit /docs for OpenAPI docs."})

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("battlebot.web.server:app", host="0.0.0.0", port=8080, reload=True)
