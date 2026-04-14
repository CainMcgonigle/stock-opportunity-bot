import yfinance as yf
import logging

logger = logging.getLogger(__name__)


def get_stock_data(tickers: list[str]) -> dict:
    """
    Fetch current price, % change, and volume ratio for a list of tickers.
    Returns a dict keyed by ticker.
    """
    if not tickers:
        return {}

    results = {}
    # Batch download where possible
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info

            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)
            volume = getattr(info, "three_month_average_volume", None)
            day_volume = getattr(info, "last_volume", None)

            change_pct = None
            if price and prev_close and prev_close != 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            volume_ratio = None
            if day_volume and volume and volume != 0:
                volume_ratio = round(day_volume / volume, 2)

            market_cap = getattr(info, "market_cap", None)
            if market_cap and market_cap > 1e9:
                market_cap_str = f"${market_cap / 1e9:.1f}B"
            elif market_cap:
                market_cap_str = f"${market_cap / 1e6:.0f}M"
            else:
                market_cap_str = "N/A"

            results[ticker] = {
                "price": f"${price:.2f}" if price else "N/A",
                "change_pct": f"{change_pct:+.2f}%" if change_pct is not None else "N/A",
                "volume_ratio": f"{volume_ratio:.1f}x avg" if volume_ratio else "N/A",
                "market_cap": market_cap_str,
            }
        except Exception as e:
            logger.warning(f"Failed to fetch stock data for {ticker}: {e}")
            results[ticker] = {
                "price": "N/A",
                "change_pct": "N/A",
                "volume_ratio": "N/A",
                "market_cap": "N/A",
            }

    return results
