import json
import unittest
from datetime import datetime, timedelta, timezone

from babylon_market import Company
from tools import babylon_market as market_tool


def company(
    name: str,
    *,
    total_value: float,
    share_price: float,
    profit_per_min: float,
    trend_pct: float,
    verified: bool = True,
    last_synced_at=None,
) -> Company:
    return Company(
        id=name.casefold().replace(" ", "-"),
        name=name,
        net_worth=total_value,
        funded_capital=0,
        profit_per_min=profit_per_min,
        total_value=total_value,
        share_price=share_price,
        last_synced_at=last_synced_at,
        verified=verified,
        trend_pct=trend_pct,
    )


class FakeClient:
    def __init__(self, companies):
        self.companies = companies

    async def get_companies(self):
        return tuple(self.companies)


class BabylonMarketToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_client = market_tool._client
        now = datetime.now(timezone.utc)
        market_tool._client = FakeClient(
            [
                company(
                    "Alpha Industries",
                    total_value=300,
                    share_price=30,
                    profit_per_min=3,
                    trend_pct=5,
                    last_synced_at=now - timedelta(minutes=5),
                ),
                company(
                    "Beta Group",
                    total_value=200,
                    share_price=40,
                    profit_per_min=8,
                    trend_pct=-2,
                    verified=False,
                    last_synced_at=now - timedelta(days=2),
                ),
            ]
        )

    async def asyncTearDown(self):
        market_tool._client = self.original_client

    async def test_overview_is_source_labelled_and_uses_live_client_data(self):
        result = json.loads(
            await market_tool.query_babylon_market("overview", limit=1)
        )
        self.assertEqual(result["source"], "Babylon public market API")
        self.assertTrue(result["readOnly"])
        self.assertEqual(result["data"]["listedCompanies"], 2)
        self.assertEqual(
            result["data"]["leadersByValue"][0]["name"], "Alpha Industries"
        )

    async def test_company_lookup_returns_sync_freshness(self):
        result = json.loads(
            await market_tool.query_babylon_market(
                "company", company="alpha"
            )
        )
        self.assertEqual(result["data"]["name"], "Alpha Industries")
        self.assertIsInstance(result["data"]["syncAgeSeconds"], int)
        self.assertGreaterEqual(result["data"]["syncAgeSeconds"], 0)

    async def test_status_reports_unverified_and_outdated_data(self):
        result = json.loads(await market_tool.query_babylon_market("status"))
        self.assertEqual(result["data"]["total"], 2)
        self.assertEqual(result["data"]["verified"], 1)
        self.assertEqual(result["data"]["outdated"], 1)

    async def test_unknown_company_returns_safe_error(self):
        result = json.loads(
            await market_tool.query_babylon_market(
                "company", company="does-not-exist"
            )
        )
        self.assertIn("error", result["data"])
