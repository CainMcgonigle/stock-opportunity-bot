import logging
import sys
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    ANTHROPIC_API_KEY,
    DISCORD_WEBHOOK_URL,
    CHECK_INTERVAL_MINUTES,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
)
from news import fetch_all_news, mark_articles_seen
from stocks import get_stock_data
from analyzer import analyze_for_opportunities
from notifier import send_opportunity, send_startup_message, send_no_opportunities_ping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")


def is_market_hours() -> bool:
    now = datetime.now(ET)
    # Skip weekends
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    return open_time <= now <= close_time


def run_scan(force: bool = False):
    if not force and not is_market_hours():
        logger.info("Outside market hours — skipping scan")
        return

    logger.info("--- Starting news scan ---")

    articles = fetch_all_news()
    if not articles:
        logger.info("No new articles to analyze")
        return

    logger.info(f"Analyzing {len(articles)} articles with Claude...")
    opportunities = analyze_for_opportunities(articles)

    # Always mark articles seen so we don't reprocess them next run
    mark_articles_seen(articles)

    if not opportunities:
        logger.info("No opportunities found this scan")
        return

    tickers = [op.get("ticker") for op in opportunities if op.get("ticker")]
    stock_data = get_stock_data(tickers)

    for opportunity in opportunities:
        send_opportunity(opportunity, stock_data)

    logger.info(f"--- Scan complete. Sent {len(opportunities)} alert(s) ---")


def main():
    # Validate config
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not DISCORD_WEBHOOK_URL:
        missing.append("DISCORD_WEBHOOK_URL")
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Copy .env.example to .env and fill in the values.")
        sys.exit(1)

    logger.info("Stock Opportunity Bot starting up...")
    send_startup_message()

    # Run once immediately on startup
    run_scan(force=False)

    scheduler = BlockingScheduler(timezone=ET)

    # Run every CHECK_INTERVAL_MINUTES during market hours on weekdays
    scheduler.add_job(
        run_scan,
        CronTrigger(
            day_of_week="mon-fri",
            hour=f"{MARKET_OPEN_HOUR}-{MARKET_CLOSE_HOUR - 1}",
            minute=f"*/{CHECK_INTERVAL_MINUTES}",
            timezone=ET,
        ),
        id="market_scan",
        name="Market hours scan",
    )

    logger.info(
        f"Scheduler started. Scanning every {CHECK_INTERVAL_MINUTES} min "
        f"during market hours (Mon-Fri {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:00 ET)"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    # Pass --force to run a single scan regardless of market hours (useful for testing)
    if "--force" in sys.argv:
        logging.basicConfig(level=logging.INFO)
        run_scan(force=True)
    else:
        main()
