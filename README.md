# Homebuilder Market Sentiment Tool

CLI that collects public user-generated content about a residential homebuilder from Reddit, Google Reviews,
X/Twitter, Instagram and TikTok, scores it across six homebuilder-specific dimensions, and writes a Markdown
report plus a CSV of every collected item.

## Setup (Python 3.11+)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in the keys you have
```

Any source whose keys are missing is skipped with a logged warning; the run continues with the rest.
`torch`/`transformers` (~2 GB) are only needed for the free local sentiment fallback — drop them from
`requirements.txt` if you always set `OPENAI_API_KEY`.

## Usage

```bash
python main.py --builder "Ryan Homes"
python main.py --builder "Pulte Homes" --market Phoenix --days 60 --limit 300
python main.py --builder "Ryan Homes" --sample-data     # synthetic data, pipeline test only
```

Flags: `--builder` (required), `--market`, `--days` (default 90), `--limit` per source (default 200),
`--engine auto|openai|local`, `--yes` (skip ambiguous-name prompt), `-v`.
`--communities FILE` takes a CSV with a `CommunityName` column (or a text file, one name per line). Sub-communities
("Yaupon Trails - Townhomes") collapse to their parent. Google Places is searched once per community and the report
gains a per-community breakdown. Example: `python main.py --builder "Stylecraft Builders" --communities communities.csv --days 3650`.

Output lands in `reports/<builder>_<market>_<timestamp>.md` and `.csv`.

## API keys

| Source | Env vars | How to get them | Notes |
|---|---|---|---|
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | reddit.com/prefs/apps → "create app" → type **script** | Read-only. Searches r/all plus the five target subreddits; collects posts and top-level comments. |
| Google Reviews | `GOOGLE_PLACES_API_KEY` | Google Cloud Console → enable **Places API (New)** → Credentials → API key (billing required) | **The Places API returns at most 5 reviews per listing per sort order.** Coverage comes from many listings (offices/communities), not deep pagination. For full review history use a licensed review-data provider. |
| X / Twitter | `X_BEARER_TOKEN` | developer.x.com → project → app → Bearer Token | Recent search only covers the last 7 days, and the free tier has very low read quotas; expect thin data. Retweets excluded. |
| Instagram | `APIFY_API_TOKEN` | console.apify.com → Settings → Integrations | The Basic Display API was retired (Dec 2024) and the Graph API can't search others' public posts/comments, so this uses an Apify actor on **public hashtag pages** — a documented scraping fallback; review Instagram's/Apify's terms. |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` (optional) else `APIFY_API_TOKEN` | developers.tiktok.com (Research API needs approval, generally academic/non-profit) | Falls back to Apify automatically. |
| Sentiment | `OPENAI_API_KEY` (optional) | platform.openai.com | GPT-4o gives nuanced per-dimension labels and verbatim quotes (non-verbatim quotes are rejected). Without it, a local HuggingFace model is used: free, but coarser (keyword-routed dimensions/themes). |

## Design notes

- **Concurrency:** all collectors run concurrently via `asyncio`; blocking PRAW runs in a thread.
- **Resilience:** HTTP calls use jittered exponential backoff honoring `Retry-After`; any collector error is logged and recorded in the Source Breakdown, never fatal.
- **PII:** author names/handles/IDs are never stored. Item IDs are salted hashes; emails, phones, @handles, u/usernames and street addresses are redacted from text before storage.
- **Ambiguous names:** single-word/short names trigger a y/N confirmation (`--yes` to bypass; non-interactive runs abort without it).
- **Quotes** in the report are verbatim excerpts from collected items.

## Layout

```
main.py            CLI entry point
collectors/        one module per source (+ base.py: Item, retry, PII scrub; apify.py shared runner)
analysis/          engine.py (GPT-4o vs local), llm.py, local.py, aggregate.py, report.py
reports/           generated .md / .csv
```

## Status

Collectors for Reddit, Google, X, Instagram and TikTok were written against the public API docs but have
**not been exercised against live APIs** (no keys were available during development). Expect to adjust field
names/actor inputs on first real run — Apify actor schemas in particular change.
