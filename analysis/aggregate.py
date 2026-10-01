"""Roll per-item analyses up into dimension scores, themes and competitor counts."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .dimensions import DIMENSIONS
from .result import ItemAnalysis


@dataclass
class DimensionSummary:
    key: str
    label: str
    n: int = 0
    pct: dict[str, float] = field(default_factory=dict)
    verdict: str = "No data"
    quotes: list[tuple[str, str, str]] = field(default_factory=list)  # (sentiment, quote, source)


@dataclass
class Summary:
    total: int
    overall_pct: dict[str, float]
    overall_verdict: str
    dimensions: list[DimensionSummary]
    praise: list[tuple[str, int, list[tuple[str, str]]]]       # (theme, count, [(quote, source)])
    complaints: list[tuple[str, int, list[tuple[str, str]]]]
    competitors: list[tuple[str, int]]
    competitor_quotes: dict[str, tuple[str, str]]


def _pct(counter: Counter, n: int) -> dict[str, float]:
    return {k: round(100 * counter.get(k, 0) / n, 1) if n else 0.0 for k in ("positive", "neutral", "negative")}


def verdict(pct: dict[str, float], n: int) -> str:
    if n == 0:
        return "No data"
    p, neg = pct["positive"], pct["negative"]
    if p >= 40 and neg >= 25:
        return "Mixed"
    if p - neg >= 15:
        return "Positive"
    if neg - p >= 15:
        return "Negative"
    return "Mixed" if p >= 25 and neg >= 25 else "Neutral"


def _best_quotes(cands: list[tuple[str, str, str, int]], k: int = 5):
    """Prefer substantive quotes with engagement; de-duplicate."""
    seen, out = set(), []
    for sent, q, src, eng in sorted(cands, key=lambda c: (-min(len(c[1]), 160), -c[3])):
        key = q.lower()[:60]
        if key in seen or len(q) < 25:
            continue
        seen.add(key)
        out.append((sent, q, src))
    return out[:k]


def summarize(analyses: list[ItemAnalysis]) -> Summary:
    n = len(analyses)
    overall = Counter(a.overall for a in analyses)
    overall_pct = _pct(overall, n)

    dims: list[DimensionSummary] = []
    for key, label in DIMENSIONS.items():
        counts, cands = Counter(), []
        for a in analyses:
            if key in a.dimensions:
                s, q = a.dimensions[key]
                counts[s] += 1
                if q:
                    cands.append((s, q, a.item.source, a.item.likes or 0))
        total = sum(counts.values())
        pct = _pct(counts, total)
        # balance quotes: lead with the majority sentiment, include the opposing view for context
        maj = max(("positive", "negative", "neutral"), key=lambda s: counts[s]) if total else "neutral"
        mq = _best_quotes([c for c in cands if c[0] == maj], 3)
        oq = _best_quotes([c for c in cands if c[0] != maj and c[0] != "neutral"], 2)
        dims.append(DimensionSummary(key, label, total, pct, verdict(pct, total), mq + oq))

    def themes(attr: str, sentiment: str):
        c: Counter = Counter()
        quotes: dict[str, list[tuple[str, str]]] = {}
        for a in analyses:
            for t in set(getattr(a, attr)):
                c[t] += 1
                # best verbatim evidence: a dimension quote with matching sentiment, else item text excerpt
                q = next((q for s, q in a.dimensions.values() if s == sentiment and q), "")
                if q:
                    quotes.setdefault(t, []).append((q, a.item.source))
        return [(t, cnt, quotes.get(t, [])[:2]) for t, cnt in c.most_common(6)]

    comp, comp_q = Counter(), {}
    for a in analyses:
        for name in set(a.competitors):
            comp[name] += 1
            comp_q.setdefault(name, (a.item.text[:220], a.item.source))
    return Summary(n, overall_pct, verdict(overall_pct, n), dims, themes("praise", "positive"),
                   themes("complaints", "negative"), comp.most_common(8), comp_q)
