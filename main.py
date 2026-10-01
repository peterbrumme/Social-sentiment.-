#!/usr/bin/env python3
"""On-demand market sentiment research for residential homebuilders."""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from analysis.aggregate import summarize  # noqa: E402
from analysis.engine import analyze  # noqa: E402
from analysis.report import write_csv, write_report  # noqa: E402
from collectors import COLLECTORS  # noqa: E402
from collectors.base import Item, SourceUnavailable  # noqa: E402

log = logging.getLogger("main")
REPORTS = Path(__file__).parent / "reports"
BUILDER_SUFFIXES = ("homes", "home", "builders", "builder", "communities", "construction", "properties", "residential", "co", "company")


def is_ambiguous(name: str) -> bool:
    """A single bare word (e.g. 'Harbor', 'Century') is likely to match unrelated content."""
    words = re.findall(r"[A-Za-z0-9&'.]+", name)
    return len(words) < 2 or (len(words) == 2 and words[1].lower() not in BUILDER_SUFFIXES and len(words[0]) <= 3)


def confirm_name(name: str, assume_yes: bool) -> bool:
    if not is_ambiguous(name) or assume_yes:
        return True
    print(f"\n'{name}' is a short/common name and may match unrelated content (not just the homebuilder).")
    print("Tip: use the full legal or marketing name, e.g. 'Pulte Homes' rather than 'Pulte'.")
    if not sys.stdin.isatty():
        print("Non-interactive session: re-run with --yes to proceed anyway.")
        return False
    return input("Proceed with this name? [y/N] ").strip().lower() in ("y", "yes")


async def collect_all(builder: str, market: str | None, days: int, limit: int) -> tuple[list[Item], dict[str, tuple[int, str]]]:
    collectors = [C(builder, market, days, limit) for C in COLLECTORS]

    async def run(c):
        try:
            items = await c.collect()
            return c.name, items, "OK" if items else "No results"
        except SourceUnavailable as exc:
            log.warning("%s: skipped — %s", c.name, exc)
            return c.name, [], f"Skipped: {exc}"
        except Exception as exc:  # never let one source crash the run
            log.exception("%s: failed", c.name)
            return c.name, [], f"Failed: {type(exc).__name__}: {exc}"

    results = await asyncio.gather(*(run(c) for c in collectors))
    items = [i for _, its, _ in results for i in its]
    return items, {name: (len(its), msg) for name, its, msg in results}


async def amain(args) -> int:
    if not confirm_name(args.builder, args.yes):
        print("Aborted.")
        return 1
    if args.sample_data:
        from sample_data import sample_items
        items = sample_items()
        status = {c.name: (sum(1 for i in items if i.source == c.name), "SYNTHETIC SAMPLE") for c in COLLECTORS}
    else:
        print(f"Collecting: {args.builder}" + (f" / {args.market}" if args.market else "") + f" (last {args.days} days, ≤{args.limit}/source)")
        items, status = await collect_all(args.builder, args.market, args.days, args.limit)

    analyses, engine = ([], "n/a")
    customer = [i for i in items if i.voice == "customer"]
    if items:
        print(f"Analyzing {len(customer)} customer-voice items ({len(items) - len(customer)} promotional excluded)…")
    if customer:
        analyses, engine = await analyze(customer, args.builder, args.engine)
    # the LLM may re-label items it judges promotional; those drop out of the scores too
    analyses = [a for a in analyses if a.item.voice == "customer"]
    summary = summarize(analyses)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", f"{args.builder}_{args.market or 'all'}".lower()).strip("_")
    base = REPORTS / f"{slug}_{stamp}"
    REPORTS.mkdir(exist_ok=True)
    write_report(base.with_suffix(".md"), builder=args.builder, market=args.market, days=args.days, summary=summary,
                 status=status, engine=engine, synthetic=args.sample_data, items=items)
    write_csv(base.with_suffix(".csv"), items, {a.item.item_id: a for a in analyses})
    print(f"Report: {base.with_suffix('.md')}\nCSV:    {base.with_suffix('.csv')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--builder", required=True, help='Homebuilder name, e.g. "Ryan Homes"')
    ap.add_argument("--market", help='City/metro to narrow results, e.g. "Dallas"')
    ap.add_argument("--days", type=int, default=90, help="Days back to collect (default 90)")
    ap.add_argument("--limit", type=int, default=200, help="Max items per source (default 200)")
    ap.add_argument("--engine", choices=["auto", "openai", "local"], default="auto",
                    help="Sentiment engine: auto = GPT-4o if OPENAI_API_KEY set, else local HuggingFace")
    ap.add_argument("--yes", action="store_true", help="Skip the ambiguous-name confirmation")
    ap.add_argument("--sample-data", action="store_true", help="Use built-in SYNTHETIC data (pipeline test only)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
