"""Comic Vine API adapter scaffold."""

from __future__ import annotations

import os
from typing import Any


def missing_api_key_metadata(env_name: str = "COMICVINE_API_KEY") -> tuple[dict[str, str], dict[str, Any]]:
    if not os.getenv(env_name):
        return {}, {"note": f"missing_api_key_env: {env_name}", "fetch_status": "skipped"}
    return {}, {"note": "comicvine_api_not_implemented", "fetch_status": "skipped"}
