import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
MAX_ARTICLES_PER_RUN = int(os.getenv("MAX_ARTICLES_PER_RUN", "40"))

# Market hours in US/Eastern
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16

SEEN_ARTICLES_FILE = "seen_articles.json"

RSS_FEEDS = [
    # Reuters
    "https://feeds.reuters.com/reuters/businessNews",
    # Yahoo Finance
    "https://finance.yahoo.com/news/rssindex",
    # CNBC Markets
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    # Seeking Alpha
    "https://seekingalpha.com/market_currents.xml",
    # Motley Fool
    "https://www.fool.com/feeds/index.aspx",
    # Barron's
    "https://www.barrons.com/xml/rss/3_7510.xml",
]
