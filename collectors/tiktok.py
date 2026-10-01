"""TikTok collector. Uses the official Research API when credentials exist, else the Apify fallback.

The Research API requires an approved application (academic/non-profit; commercial use is generally not
permitted) — hence the Apify fallback for a consultancy. Only public video descriptions and comments are read.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from .apify import run_actor
from .base import BaseCollector, Item, SourceUnavailable, mentions, raise_for_status, with_retry

log = logging.getLogger(__name__)
ACTOR = "clockworks/tiktok-scraper"


class TikTokCollector(BaseCollector):
    name = "tiktok"

    async def collect(self) -> list[Item]:
        if os.getenv("TIKTOK_CLIENT_KEY") and os.getenv("TIKTOK_CLIENT_SECRET"):
            try:
                return await self._research_api()
            except SourceUnavailable as exc:
                log.warning("tiktok: Research API unavailable (%s); falling back to Apify", exc)
        return await self._apify()

    async def _research_api(self) -> list[Item]:
        async with httpx.AsyncClient(timeout=30) as client:
            async def tok():
                r = await client.post("https://open.tiktokapis.com/v2/oauth/token/", data={
                    "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
                    "grant_type": "client_credentials"})
                raise_for_status(r)
                return r.json()["access_token"]
            token = await with_retry(tok, what="tiktok token")
            headers = {"Authorization": f"Bearer {token}"}
            end = datetime.now(timezone.utc)
            conds = [{"operation": "IN", "field_name": "keyword", "field_values": [self.builder]}]
            if self.market:
                conds.append({"operation": "IN", "field_name": "keyword", "field_values": [self.market]})
            body = {"query": {"and": conds}, "max_count": 100,
                    "start_date": self.since.strftime("%Y%m%d"), "end_date": end.strftime("%Y%m%d")}
            items: list[Item] = []
            fields = "id,video_description,create_time,like_count,comment_count"
            while len(items) < self.limit:
                async def call():
                    r = await client.post(f"https://open.tiktokapis.com/v2/research/video/query/?fields={fields}",
                                          json=body, headers=headers)
                    raise_for_status(r)
                    return r.json()["data"]
                data = await with_retry(call, what="tiktok research")
                for v in data.get("videos", []):
                    items.append(self.make_item(str(v["id"]), "video_description", v.get("video_description", ""),
                                                created_at=datetime.fromtimestamp(v["create_time"], tz=timezone.utc),
                                                likes=v.get("like_count"), replies=v.get("comment_count")))
                if not data.get("has_more"):
                    break
                body["cursor"], body["search_id"] = data["cursor"], data.get("search_id")
            return items[: self.limit]

    async def _apify(self) -> list[Item]:
        q = self.builder + (f" {self.market}" if self.market else "")
        rows = await run_actor(ACTOR, {"searchQueries": [q], "resultsPerPage": min(self.limit, 100),
                                       "commentsPerPost": 5, "shouldDownloadVideos": False})
        items: list[Item] = []
        for r in rows:
            text = r.get("text") or ""
            when = None
            if r.get("createTimeISO"):
                when = datetime.fromisoformat(r["createTimeISO"].replace("Z", "+00:00"))
            if not text or not mentions(text, self.builder) or not self.in_window(when):
                continue
            items.append(self.make_item(str(r.get("id")), "video_description", text, created_at=when,
                                        likes=r.get("diggCount"), replies=r.get("commentCount")))
        return items[: self.limit]
