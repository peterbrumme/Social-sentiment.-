"""Nuanced, per-item analysis with OpenAI GPT-4o (structured JSON output)."""
from __future__ import annotations

import asyncio
import json
import logging
import os

from collectors.base import Item

from .dimensions import DIMENSIONS
from .result import ItemAnalysis

log = logging.getLogger(__name__)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
BATCH = 12

SYSTEM = f"""You analyse public online comments about a residential homebuilder for a marketing consultancy.
For EACH numbered item return JSON. Only judge what the text actually says about the BUILDER
(not the mortgage market, other builders, or unrelated topics).

Dimensions (use these exact keys): {json.dumps(DIMENSIONS)}

Return {{"items": [{{"i": <number>, "relevant": bool, "overall": "positive|neutral|negative",
 "dimensions": {{"<key>": {{"sentiment": "positive|neutral|negative",
                           "quote": "<verbatim excerpt copied exactly from the item, max 200 chars>"}}}},
 "praise_themes": ["short noun phrase", ...], "complaint_themes": ["short noun phrase", ...],
 "competitors": ["other homebuilder names mentioned", ...]}}]}}
Only include dimensions the item actually addresses. Quotes MUST be copied character-for-character from the item.
Use consistent lowercase theme labels (e.g. "drywall defects", "responsive warranty team")."""


async def analyze(items: list[Item], builder: str) -> list[ItemAnalysis]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    sem = asyncio.Semaphore(4)
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]

    async def run(batch: list[Item]) -> list[ItemAnalysis]:
        payload = "\n\n".join(f"[{n}] ({it.source}) {it.text[:1500]}" for n, it in enumerate(batch))
        async with sem:
            for attempt in range(5):
                try:
                    resp = await client.chat.completions.create(
                        model=MODEL, temperature=0, response_format={"type": "json_object"},
                        messages=[{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": f"Builder: {builder}\n\n{payload}"}])
                    data = json.loads(resp.choices[0].message.content)
                    break
                except Exception as exc:  # openai SDK also retries internally; this covers JSON/rate errors
                    if attempt == 4:
                        log.error("llm batch failed permanently: %s", exc)
                        return []
                    await asyncio.sleep(2 ** attempt)
        out = []
        for row in data.get("items", []):
            try:
                it = batch[int(row["i"])]
            except (KeyError, ValueError, IndexError):
                continue
            if not row.get("relevant", True):
                continue
            dims = {}
            for key, d in (row.get("dimensions") or {}).items():
                if key in DIMENSIONS and d.get("sentiment") in ("positive", "neutral", "negative"):
                    q = (d.get("quote") or "").strip()
                    dims[key] = (d["sentiment"], q if q and q in it.text else "")  # reject non-verbatim quotes
            out.append(ItemAnalysis(
                item=it, overall=row.get("overall", "neutral"), dimensions=dims,
                praise=[t.lower() for t in row.get("praise_themes", [])],
                complaints=[t.lower() for t in row.get("complaint_themes", [])],
                competitors=row.get("competitors", [])))
        return out

    results = await asyncio.gather(*(run(b) for b in batches))
    return [a for r in results for a in r]
