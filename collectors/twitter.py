"""X / Twitter collector using API v2 recent search (retweets excluded)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from .base import BaseCollector, Item, SourceUnavailable, raise_for_status, with_retry

log = logging.getLogger(__name__)
URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterCollector(BaseCollector):
    name = "twitter"

    async def collect(self) -> list[Item]:
        token = os.getenv("X_BEARER_TOKEN")
        if not token:
            raise SourceUnavailable("X_BEARER_TOKEN not set")
        q = f'"{self.builder}"' + (f' "{self.market}"' if self.market else "") + " -is:retweet lang:en"
        # recent search only reaches back 7 days; the API rejects an older start_time
        start = max(self.since, datetime.now(timezone.utc) - timedelta(days=6, hours=23))
        params = {
            "query": q, "max_results": 100, "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tweet.fields": "created_at,public_metrics", "sort_order": "recency",
        }
        items: list[Item] = []
        async with httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {token}"}) as client:
            while len(items) < self.limit:
                async def call():
                    r = await client.get(URL, params=params)
                    raise_for_status(r)
                    return r.json()

                data = await with_retry(call, what="x search")
                for t in data.get("data", []):
                    m = t.get("public_metrics", {})
                    items.append(self.make_item(
                        t["id"], "tweet", t["text"],
                        created_at=datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")),
                        likes=m.get("like_count"), replies=m.get("reply_count"),
                        extra={"retweets": m.get("retweet_count"), "quotes": m.get("quote_count")},
                    ))
                nxt = data.get("meta", {}).get("next_token")
                if not nxt:
                    break
                params["next_token"] = nxt
        if self.days > 7:
            log.info("twitter: recent search covers only the last 7 days (requested %d)", self.days)
        return items[: self.limit]
