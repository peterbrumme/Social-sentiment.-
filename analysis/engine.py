from __future__ import annotations

import logging
import os

from collectors.base import Item

from .result import ItemAnalysis

log = logging.getLogger(__name__)


async def analyze(items: list[Item], builder: str, engine: str = "auto") -> tuple[list[ItemAnalysis], str]:
    """Run GPT-4o if OPENAI_API_KEY is set (or engine=openai), otherwise the local HuggingFace fallback."""
    if engine == "auto":
        engine = "openai" if os.getenv("OPENAI_API_KEY") else "local"
    if engine == "openai":
        from . import llm
        try:
            res = await llm.analyze(items, builder)
            if res:
                return res, f"OpenAI {llm.MODEL}"
            log.error("OpenAI analysis returned nothing; falling back to local model")
        except Exception as exc:
            log.error("OpenAI analysis failed (%s); falling back to local model", exc)
    from . import local
    return await local.analyze(items, builder), f"HuggingFace {local.MODEL} (local)"
