import logging
import sys
import time
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    DISCORD_WEBHOOK_URL,
    CHECK_INTERVAL_MINUTES,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
)
from news import fetch_all_news, mark_articles_seen
from stocks import get_stock_data
from analyzer import analyze_for_opportunities
from notifier import send_opportunity, send_startup_message
from ui import BotUI, UILogHandler

ET = pytz.timezone("US/Eastern")

ui = BotUI()


def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler("bot.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if ui._is_tty:
        ui_handler = UILogHandler(ui)
        ui_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root.addHandler(ui_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


def is_market_hours() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    return open_time <= now <= close_time


def run_scan(force: bool = False):
    market_open = is_market_hours()
    ui.set_market_open(market_open)

    if not force and not market_open:
        logger.info("Outside market hours — skipping scan")
        return

    ui.set_scanning(True)
    logger.info("Starting news scan")

    try:
        articles = fetch_all_news()
        if not articles:
            logger.info("No new articles to analyze")
            ui.set_last_scan()
            return

        logger.info(f"Analyzing {len(articles)} articles...")
        opportunities = analyze_for_opportunities(articles)
        mark_articles_seen(articles)
        ui.set_last_scan()

        if not opportunities:
            logger.info("No opportunities found this scan")
            return

        tickers = [op.get("ticker") for op in opportunities if op.get("ticker")]
        stock_data = get_stock_data(tickers)

        for opportunity in opportunities:
            send_opportunity(opportunity, stock_data)
            ui.add_opportunity(opportunity)

        logger.info(f"Scan complete — {len(opportunities)} alert(s) sent")

    finally:
        ui.set_scanning(False)


def main():
    # Start UI and logging first — nothing should print to stdout before this
    ui.start()
    _setup_logging()

    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL not set — running without Discord notifications")

    scheduler = None
    try:
        logger.info("Stock Opportunity Bot starting up")
        send_startup_message()
        run_scan(force=False)

        scheduler = BackgroundScheduler(timezone=ET)
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
        scheduler.start()
        logger.info(
            f"Scanning every {CHECK_INTERVAL_MINUTES} min "
            f"(Mon-Fri {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}–{MARKET_CLOSE_HOUR}:00 ET)"
        )

        while True:
            job = scheduler.get_job("market_scan")
            if job and job.next_run_time:
                ui.set_next_scan(job.next_run_time.replace(tzinfo=None))
            ui.set_market_open(is_market_hours())
            ui.add_log("tick", "TICK")
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        if scheduler:
            scheduler.shutdown()
        ui.stop()


if __name__ == "__main__":
    if "--force" in sys.argv or "-f" in sys.argv:
        _setup_logging()
        run_scan(force=True)
    else:
        main()
