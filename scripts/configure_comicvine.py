#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from getpass import getpass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = PROJECT_ROOT / "secrets"
KEY_FILE = SECRETS_DIR / "comicvine_api_key.txt"
ENV_FILE = SECRETS_DIR / "comicvine.env"

API_BASE_URL = "https://comicvine.gamespot.com/api"


def validate_key(api_key: str) -> dict:
    params = {
        "api_key": api_key,
        "format": "json",
        "limit": "1",
        "field_list": "id,name,publisher",
    }

    url = f"{API_BASE_URL}/characters/?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": "NerdFightReferee/0.1",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Comic Vine returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not contact Comic Vine: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Comic Vine returned invalid JSON") from exc

    status_code = payload.get("status_code")
    if status_code != 1:
        error = payload.get("error") or "Unknown Comic Vine error"
        raise RuntimeError(f"Comic Vine rejected the key: {error} ({status_code})")

    return payload


def main() -> int:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SECRETS_DIR, stat.S_IRWXU)

    existing_key = ""
    if KEY_FILE.is_file():
        existing_key = KEY_FILE.read_text(encoding="utf-8").strip()

    if existing_key:
        entered = getpass(
            "Comic Vine API key "
            "[press Enter to keep and revalidate the existing key]: "
        ).strip()
        api_key = entered or existing_key
    else:
        api_key = getpass("Paste Comic Vine API key: ").strip()

    if not api_key:
        print("No API key supplied.", file=sys.stderr)
        return 2

    print("Validating Comic Vine API key...")

    try:
        payload = validate_key(api_key)
    except RuntimeError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        print("The existing secret file was not changed.", file=sys.stderr)
        return 1

    KEY_FILE.write_text(f"{api_key}\n", encoding="utf-8")
    os.chmod(KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)

    quoted_key_file = shlex.quote(str(KEY_FILE))
    quoted_cache_dir = shlex.quote(
        str(PROJECT_ROOT / "data" / "cache" / "comicvine")
    )

    # The raw key is not written into this file.
    ENV_FILE.write_text(
        "\n".join(
            [
                f"export COMICVINE_API_KEY_FILE={quoted_key_file}",
                'export COMICVINE_API_KEY="$(tr -d \'\\r\\n\' '
                '"< \\"$COMICVINE_API_KEY_FILE\\")"',
                f"export COMICVINE_API_BASE_URL={API_BASE_URL}",
                f"export COMICVINE_CACHE_DIR={quoted_cache_dir}",
                "export COMICVINE_MAX_REQUESTS_PER_HOUR=180",
                "export COMICVINE_MIN_INTERVAL_SECONDS=2",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)

    results = payload.get("results") or []
    sample = results[0].get("name") if results else "no sample result"

    print("Comic Vine key validated.")
    print(f"Sample API result: {sample}")
    print(f"Key stored securely: {KEY_FILE}")
    print(f"Environment loader: {ENV_FILE}")
    print()
    print(f"Run: source {shlex.quote(str(ENV_FILE))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
