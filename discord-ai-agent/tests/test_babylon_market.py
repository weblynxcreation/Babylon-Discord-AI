import unittest
from datetime import datetime, timedelta, timezone

from babylon_market import (
    BabylonAPIError,
    Company,
    calculate_market_status,
    company_suggestions,
    find_company,
    format_currency,
    format_percent,
    rank_companies,
)


def company(
    name: str,
    *,
    total_value: float = 100,
    share_price: float = 10,
    profit_per_min: float = 1,
    trend_pct: float = 0,
    last_synced_at: datetime | None = None,
    verified: bool = True,
) -> Company:
    return Company(
        id=name.casefold().replace(" ", "-"),
        name=name,
        net_worth=50,
        funded_capital=0,
        profit_per_min=profit_per_min,
        total_value=total_value,
        share_price=share_price,
        last_synced_at=last_synced_at,
        verified=verified,
        trend_pct=trend_pct,
    )


class CompanyParsingTests(unittest.TestCase):
    def test_parses_live_api_shape(self):
        parsed = Company.from_mapping(
            {
                "id": "company-id",
                "name": "Babylon Holdings",
                "netWorth": 100,
                "fundedCapital": 20,
                "profitPerMin": 3,
                "totalValue": 120,
                "sharePrice": 1.2,
                "lastSyncedAt": "2026-09-02T07:05:36.220Z",
                "verified": True,
                "trendPct": 2.5,
            }
        )
        self.assertEqual(parsed.name, "Babylon Holdings")
        self.assertEqual(parsed.last_synced_at.tzinfo, timezone.utc)

    def test_rejects_non_numeric_market_values(self):
        with self.assertRaises(BabylonAPIError):
            Company.from_mapping(
                {
                    "id": "bad",
                    "name": "Bad Data",
                    "netWorth": "secret",
                    "fundedCapital": 0,
                    "profitPerMin": 0,
                    "totalValue": 0,
                    "sharePrice": 0,
                    "lastSyncedAt": None,
                    "verified": True,
                    "trendPct": 0,
                }
            )


class MarketHelperTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            company("Babylon Holdings", total_value=300, share_price=30, profit_per_min=2),
            company("BlackRock", total_value=200, share_price=10, profit_per_min=8),
            company("Nordmark Group", total_value=100, share_price=20, profit_per_min=4),
        ]

    def test_company_lookup_supports_case_partial_and_typo(self):
        self.assertEqual(find_company(self.items, "blackrock").name, "BlackRock")
        self.assertEqual(find_company(self.items, "Nordmark").name, "Nordmark Group")
        self.assertEqual(find_company(self.items, "Babylon Holdngs").name, "Babylon Holdings")

    def test_suggestions_prioritize_prefixes(self):
        suggestions = company_suggestions(self.items, "b")
        self.assertEqual([item.name for item in suggestions], ["Babylon Holdings", "BlackRock"])

    def test_rankings_use_selected_metric(self):
        self.assertEqual(rank_companies(self.items, "value")[0].name, "Babylon Holdings")
        self.assertEqual(rank_companies(self.items, "price")[0].name, "Babylon Holdings")
        self.assertEqual(rank_companies(self.items, "profit")[0].name, "BlackRock")

    def test_status_counts_fresh_delayed_outdated_missing_and_unverified(self):
        now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
        items = [
            company("Fresh", last_synced_at=now - timedelta(minutes=2)),
            company("Delayed", last_synced_at=now - timedelta(hours=2)),
            company("Outdated", last_synced_at=now - timedelta(days=2)),
            company("Missing", last_synced_at=None, verified=False),
        ]
        status = calculate_market_status(
            items,
            now=now,
            fresh_after=timedelta(hours=1),
            outdated_after=timedelta(hours=24),
        )
        self.assertEqual(status.total, 4)
        self.assertEqual(status.verified, 3)
        self.assertEqual(status.fresh, 1)
        self.assertEqual(status.delayed, 1)
        self.assertEqual(status.outdated, 1)
        self.assertEqual(status.missing_sync_time, 1)

    def test_discord_number_formatting(self):
        self.assertEqual(format_currency(1_574_327_476.65), "$1.57B")
        self.assertEqual(format_currency(-3.3), "$-3.30")
        self.assertEqual(format_percent(2.5), "+2.50%")
        self.assertEqual(format_percent(-0.18), "-0.18%")
