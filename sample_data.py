"""SYNTHETIC test fixtures for exercising the pipeline without API keys. Not real customer content."""
from datetime import datetime, timedelta, timezone

from collectors.base import Item, hash_id

_ROWS = [
    ("reddit", "post", "Our Ryan Homes build quality has been great, framing and drywall are clean and the finish work looks solid.", None, 42),
    ("reddit", "comment", "We closed 5 months late with Ryan Homes. The construction timeline kept slipping and communication was terrible.", None, 18),
    ("reddit", "comment", "Ryan Homes warranty team ignored our repair requests for weeks. Customer service was awful after closing.", None, 25),
    ("reddit", "comment", "The sales agent at Ryan Homes was honest and the contract process was smooth. Design center upgrades were pricey though.", None, 9),
    ("google_reviews", "review", "Love our new Ryan Homes house. The neighborhood is quiet, schools are great, and the community amenities are fantastic.", 5, 3),
    ("google_reviews", "review", "Overpriced for the quality. Ryan Homes charged us a fortune for upgrades and we found cracks in the foundation.", 2, 7),
    ("google_reviews", "review", "Great value for the money compared to Pulte. Our Ryan Homes sales rep was helpful and the price was fair.", 5, 2),
    ("google_reviews", "review", "Delays, delays, delays. Move-in got pushed back four months and nobody told us why.", 1, 11),
    ("twitter", "tweet", "Shoutout to the Ryan Homes warranty crew who fixed our leaking window within two days. Very responsive.", None, 14),
    ("twitter", "tweet", "Ryan Homes punch list took forever and the paint was sloppy. Not impressed with the workmanship.", None, 6),
    ("instagram", "caption", "Closing day with Ryan Homes! So happy with our new home and the neighborhood. #ryanhomes", None, 120),
    ("tiktok", "video_description", "Why I would never build with Ryan Homes again: hidden fees, delays and bad customer service. Lennar was better.", None, 800),
]


def sample_items() -> list[Item]:
    now = datetime.now(timezone.utc)
    return [Item(source=s, item_id=hash_id(s, f"sample{i}"), kind=k, text=t, rating=r, likes=l,
                 created_at=now - timedelta(days=3 * i + 1)) for i, (s, k, t, r, l) in enumerate(_ROWS)]
