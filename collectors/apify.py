"""Shared Apify actor runner, used as the documented fallback for Instagram and TikTok."""
from __future__ import annotations

import os

import httpx

from .base import SourceUnavailable, raise_for_status, with_retry

API = "https://api.apify.com/v2"


async def run_actor(actor: str, run_input: dict, *, timeout_s: int = 240) -> list[dict]:
    """Run an Apify actor synchronously and return its dataset items."""
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise SourceUnavailable("APIFY_API_TOKEN not set")
    async with httpx.AsyncClient(timeout=timeout_s + 30) as client:
        async def call():
            r = await client.post(
                f"{API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items",
                params={"token": token, "timeout": timeout_s}, json=run_input)
            raise_for_status(r)
            return r.json()
        return await with_retry(call, what=f"apify {actor}", attempts=3, base_delay=5)
