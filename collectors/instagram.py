"""Instagram collector (Apify fallback; the official APIs cannot search other accounts' public posts).

Two actors, public content only:
  1. apify/instagram-hashtag-scraper  -> post captions (returns comment *counts* but not comment text)
  2. apify/instagram-comment-scraper  -> comment text, run only for posts that actually have comments
Review Instagram's and Apify's terms before using results commercially.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from .apify import run_actor
from .base import BaseCollector, Item, mentions
from .voice import classify_comment, classify_post

log = logging.getLogger(__name__)
POST_ACTOR = "apify/instagram-hashtag-scraper"
COMMENT_ACTOR = "apify/instagram-comment-scraper"
MAX_POSTS_FOR_COMMENTS = 30
COMMENTS_PER_POST = 25


class InstagramCollector(BaseCollector):
    name = "instagram"

    async def collect(self) -> list[Item]:
        slug = re.sub(r"[^a-z0-9]", "", self.builder.lower())
        hashtags = [slug, f"{slug}owner", f"{slug}review"]
        rows = await run_actor(POST_ACTOR, {"hashtags": hashtags, "resultsType": "posts", "resultsLimit": self.limit})
        items: list[Item] = []
        owners: dict[str, str] = {}      # post url -> owner handle (transient, for brand-reply detection only)
        with_comments: list[str] = []
        for r in rows:
            caption = r.get("caption") or ""
            when = _ts(r.get("timestamp"))
            if not caption or not mentions(caption + " " + " ".join(r.get("hashtags", [])), self.builder):
                continue
            if self.market and self.market.lower() not in caption.lower() and self.market.lower() not in (r.get("locationName") or "").lower():
                continue
            if not self.in_window(when):
                continue
            owner = f"{r.get('ownerUsername') or ''} {r.get('ownerFullName') or ''}".strip()
            likes = r.get("likesCount")
            items.append(self.make_item(
                str(r.get("id") or r.get("shortCode")), "caption", caption, created_at=when,
                likes=likes if isinstance(likes, int) and likes >= 0 else None, replies=r.get("commentsCount"),
                voice=classify_post(caption, owner, self.builder)))
            url = r.get("url")
            if url:
                owners[url] = r.get("ownerUsername") or ""
                if (r.get("commentsCount") or 0) > 0:
                    with_comments.append(url)

        items = items[: self.limit]
        if with_comments:   # --limit caps captions and comments separately so comments are never crowded out
            items += (await self._comments(with_comments[:MAX_POSTS_FOR_COMMENTS], owners))[: self.limit]
        return items

    async def _comments(self, urls: list[str], owners: dict[str, str]) -> list[Item]:
        try:
            rows = await run_actor(COMMENT_ACTOR, {"directUrls": urls, "resultsLimit": COMMENTS_PER_POST})
        except Exception as exc:        # comments are a bonus; never lose the posts because of them
            log.warning("instagram: comment actor failed (%s); continuing with captions only", exc)
            return []
        out: list[Item] = []
        for c in rows:
            text = c.get("text")
            if not text:
                continue
            post_url = c.get("postUrl") or ""
            owner = next((o for u, o in owners.items() if u.rstrip("/") == post_url.rstrip("/")), "")
            likes = c.get("likesCount")
            out.append(self.make_item(
                str(c.get("id") or f"{post_url}:{text[:30]}"), "comment", text, created_at=_ts(c.get("timestamp")),
                likes=likes if isinstance(likes, int) and likes >= 0 else None,
                voice=classify_comment(text, c.get("ownerUsername") or "", owner, self.builder)))
        log.info("instagram: %d comments from %d posts", len(out), len(urls))
        return out


def _ts(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
