"""Markdown report + CSV export."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from collectors.base import Item

from .aggregate import Summary

EMOJI = {"Positive": "🟢", "Negative": "🔴", "Mixed": "🟠", "Neutral": "⚪", "No data": "—"}


def _pcts(p: dict[str, float]) -> str:
    return f"Positive {p['positive']}% · Neutral {p['neutral']}% · Negative {p['negative']}%"


def _q(text: str, source: str) -> str:
    return f"> “{text.strip()}” — *{source}*\n"


def executive_summary(s: Summary, builder: str, market: str | None, n_sources: int) -> str:
    if s.total == 0:
        return f"No analyzable content was collected for **{builder}**. See the Source Breakdown for per-source status."
    strongest = max((d for d in s.dimensions if d.n), key=lambda d: d.pct["positive"] - d.pct["negative"], default=None)
    weakest = min((d for d in s.dimensions if d.n), key=lambda d: d.pct["positive"] - d.pct["negative"], default=None)
    where = f" in {market}" if market else ""
    out = (f"Across {s.total} analyzed items from {n_sources} source(s), overall sentiment toward **{builder}**{where} is "
           f"**{s.overall_verdict.lower()}** ({_pcts(s.overall_pct)}). ")
    if strongest and weakest and strongest is not weakest:
        out += (f"The strongest dimension is *{strongest.label}* ({strongest.verdict.lower()}), while *{weakest.label}* "
                f"is the weakest ({weakest.verdict.lower()}). ")
    if s.complaints:
        out += f"The most frequent complaint theme is “{s.complaints[0][0]}”"
        out += f", and the most frequent praise theme is “{s.praise[0][0]}”. " if s.praise else ". "
    elif s.praise:
        out += f"The most frequent praise theme is “{s.praise[0][0]}”. "
    return out.strip()


def write_report(path: Path, *, builder: str, market: str | None, days: int, summary: Summary,
                 status: dict[str, tuple[int, str]], engine: str, synthetic: bool = False) -> None:
    L: list[str] = []
    title = f"# Market Sentiment Report: {builder}" + (f" — {market}" if market else "")
    L += [title, "",
          f"*Generated {datetime.now():%Y-%m-%d %H:%M} · window: last {days} days · analysis: {engine}*", ""]
    if synthetic:
        L += ["> ⚠️ **SYNTHETIC SAMPLE DATA** — produced with `--sample-data` to test the pipeline. "
              "These are NOT real customer comments and must not be used for client work.", ""]
    n_ok = sum(1 for c, _ in status.values() if c)
    L += ["## 1. Executive Summary", "", executive_summary(summary, builder, market, n_ok), ""]

    L += ["## 2. Sentiment by Dimension", ""]
    for i, d in enumerate(summary.dimensions, 1):
        L += [f"### 2.{i} {d.label}", ""]
        if not d.n:
            L += ["_No items addressed this dimension._", ""]
            continue
        L += [f"**Overall: {EMOJI[d.verdict]} {d.verdict}** (n={d.n})  ", _pcts(d.pct), "", "**Representative quotes**", ""]
        L += [_q(q, src) for _, q, src in d.quotes] or ["_No verbatim quotes captured._", ""]

    for heading, themes in (("3. Top Praise Themes", summary.praise), ("4. Top Complaint Themes", summary.complaints)):
        L += [f"## {heading}", ""]
        if not themes:
            L += ["_None identified._", ""]
        for t, cnt, quotes in themes:
            L += [f"### {t.capitalize()} ({cnt} mentions)", ""]
            L += [_q(q, src) for q, src in quotes]
            L += [""] if not quotes else []

    L += ["## 5. Competitive Signals", ""]
    if summary.competitors:
        L += ["| Competitor | Mentions |", "|---|---|"] + [f"| {n} | {c} |" for n, c in summary.competitors] + [""]
        for n, _ in summary.competitors[:3]:
            text, src = summary.competitor_quotes[n]
            L += [f"**{n}** — context:", _q(text, src)]
    else:
        L += ["_No competitor builders were mentioned._", ""]

    L += ["## 6. Source Breakdown", "", "| Source | Items collected | Status |", "|---|---|---|"]
    for src, (cnt, msg) in status.items():
        L.append(f"| {src} | {cnt} | {msg} |")
    L += ["", f"**Total collected:** {sum(c for c, _ in status.values())} · **Analyzed (relevant):** {summary.total}", ""]
    L += ["## 7. Raw Data Export", "", "All collected items are in the CSV saved next to this report "
          "(author identities are never collected; @handles, emails, phone numbers and street addresses are redacted).", ""]
    path.write_text("\n".join(L), encoding="utf-8")


def write_csv(path: Path, items: list[Item], analyses: dict[str, object] | None = None) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "item_id", "kind", "created_at", "rating", "likes", "replies", "url", "text", "analyzed_overall"])
        for it in items:
            a = analyses.get(it.item_id) if analyses else None
            w.writerow([it.source, it.item_id, it.kind, it.created_at.isoformat() if it.created_at else "",
                        it.rating if it.rating is not None else "", it.likes if it.likes is not None else "",
                        it.replies if it.replies is not None else "", it.url or "", it.text,
                        a.overall if a else ""])
