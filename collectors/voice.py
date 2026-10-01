"""Tag content as 'customer' voice or 'promotional' (builder / agent / listing marketing).

Heuristic, applied at collection time. It uses the post owner's handle/name only transiently (never stored).
When OpenAI is available the analysis step re-checks the label (see analysis/llm.py).
"""
from __future__ import annotations

import re

PROMO_PHRASES = [
    "grand opening", "model home", "move-in ready", "move in ready", "now selling", "now open", "quick move-in",
    "quick move in", "price improvement", "special incentive", "incentive", "schedule a tour", "book a tour",
    "link in bio", "dm us", "dm me", "call us", "contact us", "starting at", "starting in the", "from the $",
    "floor plan", "floorplan", "available now", "now available", "just listed", "open house", "ribbon cutting",
    "join us", "stop by", "come see", "visit us", "sales center", "sales office", "lunch & learn", "lunch and learn",
    "homesites", "lot available", "reserve your", "your story begins", "new construction homes in",
    "under contract", "closing day", "congratulations to", "congrats to", "my clients", "my amazing clients",
    "my buyers", "welcome to the stylecraft", "welcome to the family", "just sold", "sold!", "buyers of",
    "picking out selections", "design selections", "design appointment", "year of the", "work with me",
    "#realtor", "#realestateagent", "#justlisted", "#newlisting", "#openhouse", "#homeforsale", "#realestate",
]
PROMO_OWNER_WORDS = ["realty", "realtor", "real estate", "homes", "builders", "properties", "team", "group",
                     "sales", "new homes", "brokerage", "listing", "agent", "model home", "community", "executive",
                     "broker", "mortgage", "lender", "design center"]
PROMO_PHRASE_THRESHOLD = 2


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def classify_post(text: str, owner: str = "", builder: str = "") -> str:
    t = text.lower()
    owner_l = owner.lower()
    hits = sum(1 for p in PROMO_PHRASES if p in t)
    if builder and _norm(builder) and _norm(builder) in _norm(owner):
        return "promotional"                       # the builder's own account
    owner_commercial = any(w in owner_l for w in PROMO_OWNER_WORDS)
    if hits >= PROMO_PHRASE_THRESHOLD or (owner_commercial and hits >= 1):
        return "promotional"
    return "customer"


def classify_comment(text: str, author: str = "", post_owner: str = "", builder: str = "") -> str:
    """A reply from the post's own account, or the builder's, is brand voice; everyone else is customer."""
    if author and post_owner and author.lower() == post_owner.lower():
        return "promotional"
    if author and builder and _norm(builder) in _norm(author):
        return "promotional"
    return "customer"
