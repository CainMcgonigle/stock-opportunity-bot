import anthropic
import json
import logging
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def analyze_for_opportunities(articles: list[dict]) -> list[dict]:
    """
    Send news articles to Claude. Claude identifies stock tickers mentioned,
    assesses each as an investable opportunity, and returns structured results.
    """
    if not articles:
        return []

    articles_text = "\n\n".join([
        f"[{i+1}] {a['source']} | {a['published']}\n"
        f"Title: {a['title']}\n"
        f"Summary: {a.get('summary', 'No summary available.')}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""You are a financial analyst scanning news for investable stock opportunities.

Analyze these financial news articles and identify any US-listed stocks with a meaningful near-term catalyst:

{articles_text}

---

Look for:
- Significant earnings beats (>5% above estimates)
- Major analyst upgrades from reputable firms (especially multiple upgrades in same day)
- Share buyback announcements
- Mergers/acquisitions at a premium
- Major new contracts or product launches
- FDA approvals or significant trial results
- Unusual positive volume with a clear fundamental reason
- Insider buying at scale

Ignore:
- General market commentary with no specific stock catalyst
- Vague or minor news
- Stories about already well-known trends (e.g., AI is growing)
- Negative stories / short opportunities

For each opportunity identified, return a JSON object. If none qualify, return an empty array.

Return ONLY a valid JSON array like this (no markdown, no extra text):
[
  {{
    "ticker": "MSFT",
    "company_name": "Microsoft Corporation",
    "signal_type": "Earnings Beat",
    "signal_strength": "High",
    "opportunity_summary": "One or two sentence plain-English summary of the opportunity.",
    "reasoning": "Specific reasoning for why this is investable right now.",
    "key_risks": "What could go wrong or dampen the move.",
    "relevant_headlines": ["Exact or close title of article 1", "Exact or close title of article 2"]
  }}
]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a disciplined financial analyst. Be selective — "
                "only flag opportunities with clear, specific catalysts. "
                "Return valid JSON only."
            ),
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        opportunities = json.loads(raw)
        if not isinstance(opportunities, list):
            return []

        logger.info(f"Claude identified {len(opportunities)} opportunities")
        return opportunities

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Claude analysis failed: {e}")
        return []
