"""Reddit collector (official API via PRAW). PRAW is synchronous, so it runs in a worker thread."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from .base import BaseCollector, Item, SourceUnavailable, mentions

log = logging.getLogger(__name__)

SUBREDDITS = ["FirstTimeHomeBuyer", "RealEstate", "Mortgages", "HomeImprovement", "BuildingHomes"]
MAX_COMMENTS_PER_POST = 15


class RedditCollector(BaseCollector):
    name = "reddit"

    async def collect(self) -> list[Item]:
        cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if not (cid and secret):
            raise SourceUnavailable("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set")
        return await asyncio.to_thread(self._collect_sync, cid, secret)

    def _collect_sync(self, cid: str, secret: str) -> list[Item]:
        import praw
        from prawcore.exceptions import PrawcoreException

        reddit = praw.Reddit(
            client_id=cid,
            client_secret=secret,
            user_agent=os.getenv("REDDIT_USER_AGENT", "builder-sentiment-research/1.0"),
            ratelimit_seconds=300,  # PRAW sleeps through rate limits (up to 5 min) instead of raising
        )
        reddit.read_only = True

        query = f'"{self.builder}"' + (f" {self.market}" if self.market else "")
        time_filter = "week" if self.days <= 7 else "month" if self.days <= 31 else "year"
        items: dict[str, Item] = {}
        scopes = [("all", reddit.subreddit("all"))] + [(s, reddit.subreddit(s)) for s in SUBREDDITS]
        per_scope = max(10, self.limit // len(scopes) * 2)

        for label, sub in scopes:
            if len(items) >= self.limit:
                break
            try:
                for post in sub.search(query, sort="relevance", time_filter=time_filter, limit=per_scope):
                    if len(items) >= self.limit:
                        break
                    created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    if not self.in_window(created):
                        continue
                    body = f"{post.title}. {post.selftext or ''}".strip()
                    if not mentions(body, self.builder) and label == "all":
                        pass  # comments may still mention it; keep thread
                    pid = f"post_{post.id}"
                    if pid not in items:
                        items[pid] = self.make_item(
                            pid, "post", body, created_at=created, likes=post.score,
                            replies=post.num_comments, extra={"subreddit": str(post.subreddit)},
                        )
                    # top-level comments only
                    post.comment_sort = "top"
                    post.comments.replace_more(limit=0)
                    for c in list(post.comments)[:MAX_COMMENTS_PER_POST]:
                        if len(items) >= self.limit:
                            break
                        if not getattr(c, "body", None) or c.body in ("[deleted]", "[removed]"):
                            continue
                        cid_ = f"comment_{c.id}"
                        items.setdefault(cid_, self.make_item(
                            cid_, "comment", c.body, likes=c.score,
                            created_at=datetime.fromtimestamp(c.created_utc, tz=timezone.utc),
                            extra={"subreddit": str(post.subreddit)},
                        ))
            except PrawcoreException as exc:
                log.warning("reddit: search in r/%s failed: %s", label, exc)
        return list(items.values())
