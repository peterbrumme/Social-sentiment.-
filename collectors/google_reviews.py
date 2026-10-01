"""Google Reviews via the Places API (New). Text Search finds listings; Place Details returns reviews.

Limitation: the Places API returns at most 5 "most relevant"/"newest" reviews per place. We query both
sort orders and across every matching listing (e.g. regional sales offices / model homes).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from .base import BaseCollector, Item, SourceUnavailable, mentions, raise_for_status, with_retry

log = logging.getLogger(__name__)
BASE = "https://places.googleapis.com/v1"


class GoogleReviewsCollector(BaseCollector):
    name = "google_reviews"

    async def collect(self) -> list[Item]:
        key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not key:
            raise SourceUnavailable("GOOGLE_PLACES_API_KEY not set")
        query = f"{self.builder} new home builder" + (f" in {self.market}" if self.market else "")
        items: dict[str, Item] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            places = await self._search(client, key, query)
            places = [p for p in places if mentions(p.get("displayName", {}).get("text", ""), self.builder)]
            log.info("google_reviews: %d matching listings", len(places))
            for place in places:
                if len(items) >= self.limit:
                    break
                for sort in ("MOST_RELEVANT", "NEWEST"):
                    for rev in await self._reviews(client, key, place["id"], sort):
                        when = _parse(rev.get("publishTime"))
                        text = (rev.get("text") or rev.get("originalText") or {}).get("text", "")
                        if not text or not self.in_window(when):
                            continue
                        rid = rev.get("name", f"{place['id']}:{rev.get('publishTime')}:{text[:30]}")
                        items.setdefault(rid, self.make_item(
                            rid, "review", text, created_at=when, rating=rev.get("rating"),
                            extra={"listing": place.get("displayName", {}).get("text"),
                                   "address": place.get("formattedAddress", "")},
                        ))
        return list(items.values())[: self.limit]

    async def _search(self, client: httpx.AsyncClient, key: str, query: str) -> list[dict]:
        places: list[dict] = []
        page_token = None
        for _ in range(3):
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

    async def _reviews(self, client: httpx.AsyncClient, key: str, place_id: str, sort: str) -> list[dict]:
        async def call():
            r = await client.get(f"{BASE}/places/{place_id}", params={"reviewsSort": sort}, headers={
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
