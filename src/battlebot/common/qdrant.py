"""Isolated Qdrant vector client for Nerd Referee.

Guarantees 100% isolation from Athena's brain and Comic RAG by enforcing:
1. Connection to dedicated referee-qdrant on port 6335.
2. Mandatory 'nerd_referee_' prefix on all collections. Any attempt to access
   foreign collections is blocked at the client level.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_QDRANT_HOST = os.getenv("REFEREE_QDRANT_HOST", "192.168.1.206")
DEFAULT_QDRANT_PORT = int(os.getenv("REFEREE_QDRANT_PORT", "6335"))
REQUIRED_PREFIX = "nerd_referee_"

# Authorized Nerd Referee collections
COLLECTION_FEATS = "nerd_referee_feats"
COLLECTION_PROFILES = "nerd_referee_profiles"
COLLECTION_COSMOLOGY = "nerd_referee_cosmology"


def validate_collection_name(name: str) -> str:
    if not name.startswith(REQUIRED_PREFIX):
        raise ValueError(
            f"Security Violation: Collection '{name}' does not start with required prefix '{REQUIRED_PREFIX}'. "
            "Access to foreign collections (Athena / Comic RAG) is strictly forbidden."
        )
    return name


def qdrant_base_url() -> str:
    host = os.getenv("REFEREE_QDRANT_HOST", DEFAULT_QDRANT_HOST)
    port = int(os.getenv("REFEREE_QDRANT_PORT", DEFAULT_QDRANT_PORT))
    return f"http://{host}:{port}"


async def is_qdrant_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{qdrant_base_url()}/collections")
            return resp.status_code == 200
    except Exception:
        return False


async def list_referee_collections() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{qdrant_base_url()}/collections")
            if resp.status_code != 200:
                return []
            data = resp.json()
            collections = [
                c.get("name")
                for c in (data.get("result", {}).get("collections") or [])
                if str(c.get("name", "")).startswith(REQUIRED_PREFIX)
            ]
            return collections
    except Exception:
        return []


async def ensure_collection(
    name: str,
    *,
    vector_size: int = 1024,
    distance: str = "Cosine",
) -> bool:
    safe_name = validate_collection_name(name)
    async with httpx.AsyncClient(timeout=5.0) as client:
        check_resp = await client.get(f"{qdrant_base_url()}/collections/{safe_name}")
        if check_resp.status_code == 200:
            return True

        payload = {
            "vectors": {
                "size": vector_size,
                "distance": distance,
            }
        }
        create_resp = await client.put(f"{qdrant_base_url()}/collections/{safe_name}", json=payload)
        return create_resp.status_code in (200, 201)


async def upsert_points(
    collection_name: str,
    points: list[dict[str, Any]],
) -> bool:
    safe_name = validate_collection_name(collection_name)
    if not points:
        return True
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.put(
            f"{qdrant_base_url()}/collections/{safe_name}/points",
            json={"points": points},
        )
        return resp.status_code == 200


async def search_points(
    collection_name: str,
    vector: list[float],
    *,
    limit: int = 5,
    filter_dict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    safe_name = validate_collection_name(collection_name)
    payload: dict[str, Any] = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
    }
    if filter_dict:
        payload["filter"] = filter_dict
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{qdrant_base_url()}/collections/{safe_name}/points/search",
            json=payload,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("result") or []
