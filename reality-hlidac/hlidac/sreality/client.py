"""Minimal HTTP client for the Sreality JSON API (standard library only)."""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.sreality.cz/api/v1"
TIMEOUT_S = 20


class SrealityError(Exception):
    """Network problem or unexpected HTTP status."""


class RateLimited(SrealityError):
    """Sreality answered 429 or 403 – we must slow down."""


class SrealityClient:
    def __init__(self, user_agent: str, base_url: str = BASE_URL):
        self.user_agent = user_agent
        self.base_url = base_url

    def search(self, region_ids: tuple[int, ...], offset: int, limit: int) -> dict:
        params = {
            "category_type_cb": 1,  # sale
            "category_main_cb": 1,  # flats
            "locality_region_id": ",".join(str(r) for r in region_ids),
            "sort": "-date",
            "limit": limit,
            "offset": offset,
            "lang": "cs",
        }
        return self._get("/estates/search", params)

    def detail(self, listing_id: int) -> dict | None:
        """Return the detail JSON, or None if the listing no longer exists."""
        try:
            return self._get(f"/estates/{listing_id}", {"lang": "cs"})
        except _NotFound:
            return None

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params, safe=',')}"
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Accept-Language": "cs-CZ,cs;q=0.9",
        })
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise RateLimited(f"HTTP {exc.code} for {path}") from exc
            if exc.code == 404:
                raise _NotFound(path) from exc
            raise SrealityError(f"HTTP {exc.code} for {path}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SrealityError(f"network error for {path}: {exc}") from exc
        try:
            return json.loads(body)
        except ValueError as exc:
            raise SrealityError(f"invalid JSON from {path}") from exc


class _NotFound(SrealityError):
    pass
