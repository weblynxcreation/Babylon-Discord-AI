"""Read-only live Babylon market tool for the conversational AI agent."""
import json
import os
from datetime import datetime, timedelta, timezone

from babylon_market import (
    BabylonMarketClient,
    calculate_market_status,
    company_suggestions,
    find_company,
    rank_companies,
)

API_BASE = os.environ.get("BABYLON_API_BASE", "https://holdings.thebabylon.hu/api/v1")
FRESH_AFTER_MINUTES = int(os.environ.get("BABYLON_FRESH_AFTER_MINUTES", "60"))
OUTDATED_AFTER_HOURS = int(os.environ.get("BABYLON_OUTDATED_AFTER_HOURS", "24"))

_client = BabylonMarketClient(
    API_BASE,
    timeout_seconds=float(os.environ.get("BABYLON_HTTP_TIMEOUT_SECONDS", "10")),
    cache_seconds=float(os.environ.get("BABYLON_CACHE_SECONDS", "30")),
)

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "babylon_market",
        "description": (
            "Read current public Babylon Stock Market data. Use this for every question "
            "about Babylon companies, prices, rankings, movers, valuation, profit, "
            "verification, or synchronization health. This tool is read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["overview", "company", "leaders", "movers", "status"],
                    "description": "The market view needed to answer the question.",
                },
                "company": {
                    "type": "string",
                    "description": "Company name for the company action.",
                },
                "metric": {
                    "type": "string",
                    "enum": ["value", "price", "profit"],
                    "description": "Ranking metric for the leaders action.",
                    "default": "value",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


def _sync_age_seconds(last_synced_at) -> int | None:
    if last_synced_at is None:
        return None
    now = datetime.now(timezone.utc)
    return max(0, int((now - last_synced_at).total_seconds()))


def _company_payload(company) -> dict:
    return {
        "id": company.id,
        "name": company.name,
        "sharePrice": company.share_price,
        "trendPct": company.trend_pct,
        "totalValue": company.total_value,
        "netWorth": company.net_worth,
        "profitPerMin": company.profit_per_min,
        "fundedCapital": company.funded_capital,
        "verified": company.verified,
        "lastSyncedAt": (
            company.last_synced_at.isoformat() if company.last_synced_at else None
        ),
        "syncAgeSeconds": _sync_age_seconds(company.last_synced_at),
    }


def _response(action: str, data) -> str:
    return json.dumps(
        {
            "source": "Babylon public market API",
            "readOnly": True,
            "action": action,
            "retrievedAt": datetime.now(timezone.utc).isoformat(),
            "data": data,
        },
        separators=(",", ":"),
    )


async def query_babylon_market(
    action: str,
    company: str | None = None,
    metric: str = "value",
    limit: int = 5,
) -> str:
    """Fetch live public data and return compact, source-labelled JSON for the model."""
    limit = max(1, min(int(limit), 10))
    companies = await _client.get_companies()

    if action == "overview":
        leaders = rank_companies(companies, "value")[:limit]
        return _response(
            action,
            {
                "listedCompanies": len(companies),
                "verifiedCompanies": sum(item.verified for item in companies),
                "combinedValue": sum(item.total_value for item in companies),
                "leadersByValue": [_company_payload(item) for item in leaders],
            },
        )

    if action == "company":
        if not company:
            return _response(action, {"error": "A company name is required."})
        match = find_company(companies, company)
        if match is None:
            suggestions = [
                item.name for item in company_suggestions(companies, company, limit=5)
            ]
            return _response(
                action,
                {"error": "No matching listed company was found.", "suggestions": suggestions},
            )
        return _response(action, _company_payload(match))

    if action == "leaders":
        if metric not in {"value", "price", "profit"}:
            return _response(action, {"error": f"Unsupported ranking metric: {metric}"})
        leaders = rank_companies(companies, metric)[:limit]
        return _response(
            action,
            {"metric": metric, "companies": [_company_payload(item) for item in leaders]},
        )

    if action == "movers":
        gainers = sorted(
            (item for item in companies if item.trend_pct > 0),
            key=lambda item: item.trend_pct,
            reverse=True,
        )[:limit]
        losers = sorted(
            (item for item in companies if item.trend_pct < 0),
            key=lambda item: item.trend_pct,
        )[:limit]
        return _response(
            action,
            {
                "gainers": [_company_payload(item) for item in gainers],
                "losers": [_company_payload(item) for item in losers],
            },
        )

    if action == "status":
        status = calculate_market_status(
            companies,
            fresh_after=timedelta(minutes=FRESH_AFTER_MINUTES),
            outdated_after=timedelta(hours=OUTDATED_AFTER_HOURS),
        )
        return _response(
            action,
            {
                "total": status.total,
                "verified": status.verified,
                "fresh": status.fresh,
                "delayed": status.delayed,
                "outdated": status.outdated,
                "missingSyncTime": status.missing_sync_time,
                "freshAfterMinutes": FRESH_AFTER_MINUTES,
                "outdatedAfterHours": OUTDATED_AFTER_HOURS,
                "newestSync": status.newest_sync.isoformat() if status.newest_sync else None,
                "oldestSync": status.oldest_sync.isoformat() if status.oldest_sync else None,
            },
        )

    return _response(action, {"error": f"Unsupported market action: {action}"})
