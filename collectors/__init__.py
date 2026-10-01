from .google_reviews import GoogleReviewsCollector
from .instagram import InstagramCollector
from .reddit import RedditCollector
from .tiktok import TikTokCollector
from .twitter import TwitterCollector

# Priority order from the project brief
COLLECTORS = [RedditCollector, GoogleReviewsCollector, TwitterCollector, InstagramCollector, TikTokCollector]
