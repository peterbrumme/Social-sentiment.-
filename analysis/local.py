"""Local fallback: HuggingFace transformers sentiment model (no API cost).

The model scores each sentence; sentences are routed to dimensions by keyword. Theme extraction is
keyword-based and coarser than the GPT-4o path — expect less nuance (sarcasm, mixed sentiment).
"""
from __future__ import annotations

import asyncio
import logging
import re

from collectors.base import Item

from .dimensions import DIMENSIONS, KEYWORDS
from .result import ItemAnalysis

log = logging.getLogger(__name__)
MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

KNOWN_BUILDERS = ["Lennar", "D.R. Horton", "DR Horton", "Pulte", "Ryan Homes", "NVR", "KB Home", "Toll Brothers",
                  "Meritage", "Taylor Morrison", "Beazer", "Centex", "M/I Homes", "Clayton", "Mattamy", "Fischer Homes",
                  "Drees", "Dream Finders", "Del Webb", "Shea Homes", "Brookfield", "Century Communities", "Tri Pointe",
                  "Hovnanian", "Perry Homes", "Highland Homes", "David Weekley", "Ashton Woods", "Smith Douglas"]

THEMES = {  # (label, keywords) — polarity comes from the sentence's sentiment
    "build quality defects": ["defect", "crack", "poor quality", "shoddy", "sloppy", "leak", "mold", "workmanship"],
    "construction delays": ["delay", "behind schedule", "pushed back", "months late", "waiting"],
    "warranty responsiveness": ["warranty", "repair", "callback", "ignored", "responsive"],
    "pricing and hidden costs": ["price", "overpriced", "upgrade", "hidden", "cost", "fees"],
    "sales experience": ["sales", "salesperson", "agent", "closing", "contract"],
    "neighborhood and location": ["neighborhood", "community", "location", "hoa", "schools"],
    "communication": ["communication", "communicate", "updates", "responsive"],
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 15]


async def analyze(items: list[Item], builder: str) -> list[ItemAnalysis]:
    return await asyncio.to_thread(_analyze_sync, items, builder)


def _analyze_sync(items: list[Item], builder: str) -> list[ItemAnalysis]:
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError("Local analysis needs `pip install transformers torch` (or set OPENAI_API_KEY)") from exc
    clf = pipeline("text-classification", model=MODEL, top_k=1, truncation=True, max_length=256)
    label_map = {"positive": "positive", "neutral": "neutral", "negative": "negative"}

    own = re.sub(r"[^a-z0-9]", "", builder.lower())
    comps = [b for b in KNOWN_BUILDERS if re.sub(r"[^a-z0-9]", "", b.lower()) not in own and own not in re.sub(r"[^a-z0-9]", "", b.lower())]

    all_sents: list[tuple[int, str]] = [(i, s) for i, it in enumerate(items) for s in (_sentences(it.text) or [it.text])]
    preds = clf([s for _, s in all_sents], batch_size=32)
    by_item: dict[int, list[tuple[str, str]]] = {}
    for (i, s), p in zip(all_sents, preds):
        by_item.setdefault(i, []).append((s, label_map[p[0]["label"].lower()]))

    out = []
    for i, it in enumerate(items):
        sents = by_item.get(i, [])
        if not sents:
            continue
        pos = sum(1 for _, l in sents if l == "positive")
        neg = sum(1 for _, l in sents if l == "negative")
        overall = "positive" if pos > neg else "negative" if neg > pos else "neutral"
        if it.rating is not None:  # a star rating is a stronger signal than model inference on a review
            overall = "positive" if it.rating >= 4 else "negative" if it.rating <= 2 else overall
        dims: dict[str, tuple[str, str]] = {}
        for key, kws in KEYWORDS.items():
            hits = [(s, l) for s, l in sents if any(k in s.lower() for k in kws)]
            if hits:
                p_, n_ = sum(l == "positive" for _, l in hits), sum(l == "negative" for _, l in hits)
                sent = "positive" if p_ > n_ else "negative" if n_ > p_ else "neutral"
                best = next((s for s, l in hits if l == sent), hits[0][0])
                dims[key] = (sent, best[:200])
        praise, complaints = [], []
        for s, l in sents:
            for label, kws in THEMES.items():
                if any(k in s.lower() for k in kws):
                    (praise if l == "positive" else complaints if l == "negative" else []).append(label)
        out.append(ItemAnalysis(
            item=it, overall=overall, dimensions=dims, praise=praise, complaints=complaints,
            competitors=[c for c in comps if c.lower() in it.text.lower()]))
    return out
