#!/usr/bin/env python3
"""Merge several report CSVs into one combined report (no API calls to the data sources).

Usage: python merge_reports.py --builder "Stylecraft Builders" reports/a.csv reports/b.csv [--engine local]
Duplicates (same item_id) are collapsed; when one copy has a community tag, that copy wins.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from analysis.aggregate import summarize  # noqa: E402
from analysis.engine import analyze  # noqa: E402
from analysis.report import write_csv, write_report  # noqa: E402
from collectors.base import Item  # noqa: E402

REPORTS = Path(__file__).parent / "reports"


def load(path: str) -> list[Item]:
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            num = lambda k, cast: cast(r[k]) if r.get(k) not in (None, "") else None
            out.append(Item(
                source=r["source"], item_id=r["item_id"], kind=r["kind"], text=r["text"],
                created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else None,
                rating=num("rating", float), likes=num("likes", int), replies=num("replies", int),
                url=r.get("url") or None, voice=r.get("voice") or "customer",
                extra={"community": r["community"]} if r.get("community") else {}))
    return out


async def amain(args) -> None:
    merged: dict[str, Item] = {}
    for path in args.csvs:
        for it in load(path):
            old = merged.get(it.item_id)
            if old is None or (it.extra.get("community") and not old.extra.get("community")):
                merged[it.item_id] = it
    items = list(merged.values())
    print(f"Merged {len(items)} unique items from {len(args.csvs)} files")
    customer = [i for i in items if i.voice == "customer"]
    analyses, engine = await analyze(customer, args.builder, args.engine) if customer else ([], "n/a")
    analyses = [a for a in analyses if a.item.voice == "customer"]
    counts = Counter(i.source for i in items)
    status = {s: (counts.get(s, 0), "OK" if counts.get(s) else "No data in merged files")
              for s in ("reddit", "google_reviews", "twitter", "instagram", "tiktok")}
    base = REPORTS / f"{re.sub(r'[^a-z0-9]+', '_', args.builder.lower()).strip('_')}_combined_{datetime.now():%Y%m%d_%H%M%S}"
    write_report(base.with_suffix(".md"), builder=args.builder, market=None, days=args.days, summary=summarize(analyses),
                 status=status, engine=engine, items=items, analyses=analyses)
    write_csv(base.with_suffix(".csv"), items, {a.item.item_id: a for a in analyses})
    print(f"Report: {base.with_suffix('.md')}\nCSV:    {base.with_suffix('.csv')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csvs", nargs="+")
    ap.add_argument("--builder", required=True)
    ap.add_argument("--days", type=int, default=3650, help="window label shown in the report")
    ap.add_argument("--engine", choices=["auto", "openai", "local"], default="auto")
    asyncio.run(amain(ap.parse_args()))
