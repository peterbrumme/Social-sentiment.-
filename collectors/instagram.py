"""Instagram collector.

The Instagram Basic Display API was shut down in Dec 2024 and the Graph API's hashtag search only works for
Business accounts and returns no comments on other people's posts, so the documented path here is an Apify
actor scraping *public* hashtag pages only (no logins, no private accounts). Review Instagram's ToS and the
actor's terms before using in production.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from .apify import run_actor
from .base import BaseCollector, Item, mentions

log = logging.getLogger(__name__)
ACTOR = "apify/instagram-hashtag-scraper"


class InstagramCollector(BaseCollector):
    name = "instagram"

    async def collect(self) -> list[Item]:
        slug = re.sub(r"[^a-z0-9]", "", self.builder.lower())
        hashtags = [slug, f"{slug}owner", f"{slug}review"]
        rows = await run_actor(ACTOR, {"hashtags": hashtags, "resultsType": "posts", "resultsLimit": self.limit})
        items: list[Item] = []
        for r in rows:
            caption = r.get("caption") or ""
            when = _ts(r.get("timestamp"))
            if not caption or not mentions(caption + " " + " ".join(r.get("hashtags", [])), self.builder):
                continue
            if self.market and self.market.lower() not in caption.lower() and self.market.lower() not in (r.get("locationName") or "").lower():
                continue
            if not self.in_window(when):
                continue
            items.append(self.make_item(str(r.get("id") or r.get("shortCode")), "caption", caption,
                                        created_at=when, likes=r.get("likesCount"), replies=r.get("commentsCount")))
            for c in (r.get("latestComments") or [])[:5]:
                if c.get("text"):
                    items.append(self.make_item(f"{r.get('id')}:{c.get('id')}", "comment", c["text"],
                                                created_at=_ts(c.get("timestamp")), likes=c.get("likesCount")))
        return items[: self.limit]


def _ts(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
