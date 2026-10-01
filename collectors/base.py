"""Shared types and helpers for all collectors: the Item record, retry/backoff, PII scrubbing."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, TypeVar

import httpx

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class Item:
    """One piece of public user-generated content. Deliberately carries no author identity."""

    source: str                      # reddit | google_reviews | twitter | instagram | tiktok
    item_id: str                     # salted hash of the platform ID, never the raw author/handle
    kind: str                        # post | comment | review | tweet | caption | video_description
    text: str
    created_at: datetime | None = None
    rating: float | None = None      # star rating where the platform has one
    likes: int | None = None
    replies: int | None = None
    url: str | None = None           # only set when the URL cannot identify the author
    voice: str = "customer"          # customer | promotional (brand/agent/listing marketing)
    extra: dict[str, Any] = field(default_factory=dict)


class SourceUnavailable(Exception):
    """Raised when a source is not configured (missing keys) or permanently fails."""


class RetryableError(Exception):
    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


def hash_id(source: str, raw_id: str) -> str:
    return hashlib.sha256(f"{source}:{raw_id}".encode()).hexdigest()[:16]


def cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# --- PII scrubbing -----------------------------------------------------------------------------

_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"), "[phone]"),
    (re.compile(r"(?<![\w/])/?u/[\w-]{3,}", re.I), "[user]"),       # reddit usernames
    (re.compile(r"(?<![\w@])@[\w.]{2,30}"), "[user]"),              # @handles
    (re.compile(r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Way|Blvd|Cir|Circle|Pl|Place|Ter|Terrace)\b\.?"), "[address]"),
]


def scrub_pii(text: str) -> str:
    for pattern, repl in _PII_PATTERNS:
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


# --- Retry with exponential backoff -------------------------------------------------------------

async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    what: str,
    attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> T:
    """Run `fn`, retrying on RetryableError / transient network errors with jittered backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except (RetryableError, httpx.TransportError) as exc:
            if attempt == attempts:
                raise
            delay = getattr(exc, "retry_after", None) or min(max_delay, base_delay * 2 ** (attempt - 1))
            delay += random.uniform(0, delay * 0.25)
            log.warning("%s: %s — retry %d/%d in %.1fs", what, exc, attempt, attempts - 1, delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


def raise_for_status(resp: httpx.Response) -> None:
    """Translate HTTP status into RetryableError (429/5xx) or SourceUnavailable (auth/other 4xx)."""
    if resp.status_code == 429 or resp.status_code >= 500:
        ra = resp.headers.get("retry-after") or resp.headers.get("x-rate-limit-reset")
        retry_after = None
        if ra and ra.isdigit():
            val = float(ra)
            # x-rate-limit-reset is an epoch timestamp, retry-after is seconds
            retry_after = max(1.0, val - datetime.now(timezone.utc).timestamp()) if val > 1e9 else val
            retry_after = min(retry_after, 120.0)
        raise RetryableError(f"HTTP {resp.status_code}", retry_after)
    if resp.status_code in (401, 403):
        raise SourceUnavailable(f"HTTP {resp.status_code} — check credentials/access tier: {resp.text[:200]}")
    if resp.status_code >= 400:
        raise SourceUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")


def mentions(text: str, builder: str) -> bool:
    """Loose relevance check: the builder name (ignoring spaces/case) appears in the text."""
    norm = re.sub(r"[^a-z0-9]", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", builder.lower()) in norm


class BaseCollector:
    name: str = "base"

    def __init__(self, builder: str, market: str | None, days: int, limit: int):
        self.builder = builder
        self.market = market
        self.days = days
        self.limit = limit
        self.since = cutoff(days)

    async def collect(self) -> list[Item]:
        raise NotImplementedError

    def make_item(self, raw_id: str, kind: str, text: str, **kw: Any) -> Item:
        return Item(source=self.name, item_id=hash_id(self.name, raw_id), kind=kind, text=scrub_pii(text), **kw)

    def in_window(self, dt: datetime | None) -> bool:
        return dt is None or dt >= self.since
