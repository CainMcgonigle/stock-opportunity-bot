import json
import logging
import re
from openai import OpenAI
from config import OLLAMA_HOST, MIN_CONFIDENCE_SCORE

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key="ollama",
    base_url=f"{OLLAMA_HOST}/v1",
)
MODEL = "llama3.1:8b"
CHUNK_SIZE = 20


def _analyze_chunk(articles: list[dict], chunk_num: int, total_chunks: int) -> list[dict]:
    """Analyze a single chunk of articles. Returns a list of opportunities."""

    articles_text = "\n\n".join([
        f"[{i+1}] {a['source']} | {a['published']}\n"
        f"Title: {a['title']}\n"
        f"URL: {a.get('link', 'N/A')}\n"
        f"Summary: {a.get('summary', 'No summary available.')}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""You are a financial analyst scanning news for LONG/BUY stock opportunities only.

Analyze these financial news articles and identify US-listed stocks with a clear positive near-term catalyst that makes them worth buying:

{articles_text}

---

ONLY flag opportunities that are BULLISH/LONG signals:
- Significant earnings beats (>5% above estimates)
- Analyst UPGRADES (not downgrades) from reputable firms
- Share buyback announcements
- Mergers/acquisitions at a premium to current price
- Major new contracts or product launches with revenue impact
- FDA approvals or positive trial results
- Insider BUYING at scale
- Unusual positive volume with a clear fundamental reason

STRICT rules — if ANY of these apply, do NOT include it:
- Negative news: downgrades, fund selling, missed earnings, layoffs, scandals
- General market commentary with no specific stock catalyst
- Vague or speculative news without a clear catalyst
- Stories about well-known ongoing trends (e.g., "AI is growing")
- Any signal where the right action would be to sell or short

For each qualifying opportunity, return a JSON object. If none qualify, return [].

Return ONLY a valid JSON array, no markdown, no extra text:
[
  {{
    "ticker": "MSFT",
    "company_name": "Microsoft Corporation",
    "signal_type": "Earnings Beat",
    "signal_strength": "High",
    "opportunity_summary": "One or two sentence plain-English summary of why this is a buy opportunity.",
    "reasoning": "Specific reasoning for why this stock is likely to move up in the near term.",
    "key_risks": "What could go wrong or prevent the expected move.",
    "suggested_action": "Buy on open, target +8% from open, stop-loss at -4% from open.",
    "confidence_score": 72,
    "confidence_reasoning": "Score 0-100. Consider: number of corroborating articles (more = higher), source reputation (Reuters/WSJ/Bloomberg = higher, unknown blogs = lower), catalyst specificity (exact figures = higher, vague = lower), signal strength alignment.",
    "relevant_links": ["https://exact-url-from-article-above", "https://second-url-if-applicable"]
  }}
]"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a disciplined financial analyst focused exclusively on LONG/BUY opportunities. "
                        "Never flag bearish, negative, or short signals — only bullish catalysts that justify buying. "
                        "Be highly selective. Return valid JSON only, no markdown, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("[") or part.startswith("{"):
                    raw = part
                    break

        # Extract JSON array if buried in text
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]

        raw = raw.strip()

        # Fix invalid backslash escapes from LLM output
        raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)

        opportunities = json.loads(raw)
        if not isinstance(opportunities, list):
            return []

        # Filter out bearish signals and low-confidence alerts
        filtered = []
        for opp in opportunities:
            ticker = opp.get("ticker", "?")
            action_lower = opp.get("suggested_action", "").lower()
            if any(kw in action_lower for kw in {"short", "sell", "put"}):
                logger.info(f"Filtered bearish signal for {ticker}")
                continue
            try:
                score = int(opp.get("confidence_score", 0))
            except (ValueError, TypeError):
                score = 0
            if score < MIN_CONFIDENCE_SCORE:
                logger.info(f"Filtered low-confidence signal for {ticker} (score={score}, min={MIN_CONFIDENCE_SCORE})")
                continue
            filtered.append(opp)

        return filtered

    except json.JSONDecodeError as e:
        logger.error(f"Chunk {chunk_num}/{total_chunks} — failed to parse JSON: {e}")
        logger.error(f"Raw response: {raw[:300]!r}")
        return []
    except Exception as e:
        logger.error(f"Chunk {chunk_num}/{total_chunks} — analysis failed: {e}")
        return []


def analyze_for_opportunities(articles: list[dict]) -> list[dict]:
    """Split articles into chunks, analyze sequentially, return deduplicated results."""
    if not articles:
        return []

    chunks = [articles[i:i + CHUNK_SIZE] for i in range(0, len(articles), CHUNK_SIZE)]
    total = len(chunks)
    logger.info(f"Analyzing {len(articles)} articles in {total} chunk(s) of {CHUNK_SIZE}")

    all_opportunities = []
    seen_tickers = set()

    for i, chunk in enumerate(chunks, 1):
        logger.info(f"Analyzing chunk {i}/{total} ({len(chunk)} articles)...")
        results = _analyze_chunk(chunk, i, total)
        for opp in results:
            ticker = opp.get("ticker", "")
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                all_opportunities.append(opp)

    logger.info(f"Found {len(all_opportunities)} opportunities across all chunks")
    return all_opportunities
