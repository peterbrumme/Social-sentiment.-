"""Google Reviews via the Places API (New). Text Search finds listings; Place Details returns reviews.

Limitation: the Places API returns at most 5 "most relevant"/"newest" reviews per place. We query every matching listing (e.g. regional sales offices / model homes).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime

import httpx

from .base import BaseCollector, Item, SourceUnavailable, brand_core, mentions, raise_for_status, with_retry

log = logging.getLogger(__name__)
BASE = "https://places.googleapis.com/v1"


class GoogleReviewsCollector(BaseCollector):
    name = "google_reviews"

    async def collect(self) -> list[Item]:
        key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not key:
            raise SourceUnavailable("GOOGLE_PLACES_API_KEY not set")
        items: dict[str, Item] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            if self.communities:
                await self._collect_communities(client, key, items)
            else:
                query = f"{self.builder} new home builder" + (f" in {self.market}" if self.market else "")
                places = [p for p in await self._search(client, key, query)
                          if mentions(p.get("displayName", {}).get("text", ""), self.builder)]
                log.info("google_reviews: %d matching listings", len(places))
                await self._add_reviews(client, key, places, items, community=None)
        cap = max(self.limit, 10 * len(self.communities))   # in community mode, --limit is per-run floor, not a hard cap
        return list(items.values())[:cap]

    async def _collect_communities(self, client, key, items) -> None:
        sem = asyncio.Semaphore(4)
        matched = 0

        async def one(community: str):
            nonlocal matched
            async with sem:
                try:
                    found = await self._search(client, key, f"{self.builder} {community}", pages=1)
                except SourceUnavailable as exc:
                    log.warning("google_reviews: search failed for %s: %s", community, exc)
                    return
                want = re.sub(r"[^a-z0-9]", "", community.lower())
                core = brand_core(self.builder)
                norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
                # the listing must name the builder (brand core is enough) AND the community
                places = [p for p in found
                          if core in norm(p.get("displayName", {}).get("text", ""))
                          and want in norm(p.get("displayName", {}).get("text", ""))]
                if places:
                    matched += 1
                    await self._add_reviews(client, key, places, items, community=community)

        await asyncio.gather(*(one(c) for c in self.communities))
        log.info("google_reviews: found a listing for %d of %d communities", matched, len(self.communities))

    async def _add_reviews(self, client, key, places, items, community) -> None:
        for place in places:
            for rev in await self._reviews(client, key, place["id"]):
                when = _parse(rev.get("publishTime"))
                text = (rev.get("text") or rev.get("originalText") or {}).get("text", "")
                if not text or not self.in_window(when):
                    continue
                rid = rev.get("name", f"{place['id']}:{rev.get('publishTime')}:{text[:30]}")
                items.setdefault(rid, self.make_item(
                    rid, "review", text, created_at=when, rating=rev.get("rating"),
                    extra={"listing": place.get("displayName", {}).get("text"),
                           "address": place.get("formattedAddress", ""), "community": community or ""}))

    async def _search(self, client: httpx.AsyncClient, key: str, query: str, pages: int = 3) -> list[dict]:
        places: list[dict] = []
        page_token = None
        for _ in range(pages):
            body: dict = {"textQuery": query, "pageSize": 20}
            if page_token:
                body["pageToken"] = page_token

            async def call():
                r = await client.post(f"{BASE}/places:searchText", json=body, headers={
                    "X-Goog-Api-Key": key,
                    "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,nextPageToken"})
                raise_for_status(r)
                return r.json()

            data = await with_retry(call, what="google places search")
            places += data.get("places", [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return places

    async def _reviews(self, client: httpx.AsyncClient, key: str, place_id: str) -> list[dict]:
        async def call():
            r = await client.get(f"{BASE}/places/{place_id}", headers={
                "X-Goog-Api-Key": key, "X-Goog-FieldMask": "reviews"})
            raise_for_status(r)
            return r.json()
        try:
            return (await with_retry(call, what="google place details")).get("reviews", [])
        except SourceUnavailable as exc:
            log.warning("google_reviews: details failed for a listing: %s", exc)
            return []


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    except ValueError:
        return None
