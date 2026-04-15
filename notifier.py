import requests
import logging
from datetime import datetime, timezone
from config import DISCORD_WEBHOOK_URL

logger = logging.getLogger(__name__)

SIGNAL_COLORS = {
    "High": 0x00C851,    # green
    "Medium": 0xFFBB33,  # amber
    "Low": 0x33B5E5,     # blue
}


def _signal_strength_emoji(strength: str) -> str:
    return {"High": "HIGH", "Medium": "MED", "Low": "LOW"}.get(strength, strength)


def send_opportunity(opportunity: dict, stock_data: dict):
    ticker = opportunity.get("ticker", "???")
    company = opportunity.get("company_name", ticker)
    signal_type = opportunity.get("signal_type", "Signal")
    strength = opportunity.get("signal_strength", "Medium")
    summary = opportunity.get("opportunity_summary", "")
    reasoning = opportunity.get("reasoning", "")
    risks = opportunity.get("key_risks", "")
    headlines = opportunity.get("relevant_headlines", [])

    stock = stock_data.get(ticker, {})
    price = stock.get("price", "N/A")
    change_pct = stock.get("change_pct", "N/A")
    volume_ratio = stock.get("volume_ratio", "N/A")
    market_cap = stock.get("market_cap", "N/A")

    color = SIGNAL_COLORS.get(strength, 0xAAAAAA)

    confidence = opportunity.get("confidence_score")
    if confidence is not None:
        try:
            confidence = int(confidence)
            if confidence >= 75:
                confidence_str = f"{confidence}/100 🟢"
            elif confidence >= 50:
                confidence_str = f"{confidence}/100 🟡"
            else:
                confidence_str = f"{confidence}/100 🔴"
        except (ValueError, TypeError):
            confidence_str = "N/A"
    else:
        confidence_str = "N/A"

    fields = [
        {"name": "Signal Strength", "value": _signal_strength_emoji(strength), "inline": True},
        {"name": "Signal Type", "value": signal_type, "inline": True},
        {"name": "Confidence", "value": confidence_str, "inline": True},
        {"name": "Price", "value": price, "inline": True},
        {"name": "Day Change", "value": change_pct, "inline": True},
        {"name": "Volume", "value": volume_ratio, "inline": True},
        {"name": "Market Cap", "value": market_cap, "inline": True},
    ]

    suggested_action = opportunity.get("suggested_action", "")
    if suggested_action:
        fields.append({"name": "Suggested Action", "value": suggested_action[:512], "inline": False})

    if reasoning:
        fields.append({"name": "Why Now", "value": reasoning[:1024], "inline": False})

    if risks:
        fields.append({"name": "Key Risks", "value": risks[:512], "inline": False})

    links = opportunity.get("relevant_links", [])
    if links:
        links_text = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(links[:3]))
        fields.append({"name": "Sources", "value": links_text[:512], "inline": False})
    elif headlines:
        headlines_text = "\n".join(f"- {h}" for h in headlines[:4])
        fields.append({"name": "Relevant Headlines", "value": headlines_text[:512], "inline": False})

    embed = {
        "title": f"${ticker} — {company}",
        "description": summary[:2048],
        "color": color,
        "fields": fields,
        "footer": {
            "text": "Stock Opportunity Bot | Not financial advice. Do your own due diligence."
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "username": "Stock Opportunity Bot",
        "embeds": [embed],
    }

    if not DISCORD_WEBHOOK_URL:
        logger.info(f"[no webhook] Opportunity: ${ticker} — {signal_type} ({strength})")
        return

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Sent Discord alert for ${ticker}")
    except Exception as e:
        logger.error(f"Failed to send Discord alert for ${ticker}: {e}")


def send_no_opportunities_ping():
    """Optional heartbeat so you know the bot is alive."""
    if not DISCORD_WEBHOOK_URL:
        return
    payload = {
        "username": "Stock Opportunity Bot",
        "content": f"Scan complete — no significant opportunities found. ({datetime.now().strftime('%H:%M ET')})",
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send heartbeat: {e}")


def send_startup_message():
    if not DISCORD_WEBHOOK_URL:
        return
    payload = {
        "username": "Stock Opportunity Bot",
        "embeds": [{
            "title": "Bot Online",
            "description": (
                "Scanning financial news every 30 minutes during US market hours "
                "(9:30 AM - 4:00 PM ET, Mon-Fri).\n\n"
                "Alerts fire when Claude identifies a stock with a meaningful near-term catalyst."
            ),
            "color": 0x5865F2,
            "footer": {"text": "Not financial advice."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        logger.warning(f"Failed to send startup message: {e}")
