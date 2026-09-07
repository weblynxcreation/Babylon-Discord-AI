"""Read-only client and domain helpers for the Babylon Stock Market API."""

from __future__ import annotations

import asyncio
import difflib
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


class BabylonAPIError(RuntimeError):
    """A safe-to-display failure while reading the Babylon market API."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BabylonAPIError(f"Babylon returned an invalid {field} value.")
    result = float(value)
    if not math.isfinite(result):
        raise BabylonAPIError(f"Babylon returned an invalid {field} value.")
    return result


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BabylonAPIError("Babylon returned an invalid synchronization timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BabylonAPIError("Babylon returned an invalid synchronization timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Company:
    id: str
    name: str
    net_worth: float
    funded_capital: float
    profit_per_min: float
    total_value: float
    share_price: float
    last_synced_at: datetime | None
    verified: bool
    trend_pct: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Company":
        company_id = raw.get("id")
        name = raw.get("name")
        if not isinstance(company_id, str) or not company_id.strip():
            raise BabylonAPIError("Babylon returned a company without a valid ID.")
        if not isinstance(name, str) or not name.strip():
            raise BabylonAPIError("Babylon returned a company without a valid name.")
        verified = raw.get("verified")
        if not isinstance(verified, bool):
            raise BabylonAPIError("Babylon returned an invalid verification status.")
        return cls(
            id=company_id,
            name=name.strip(),
            net_worth=_finite_number(raw.get("netWorth"), "net worth"),
            funded_capital=_finite_number(raw.get("fundedCapital"), "funded capital"),
            profit_per_min=_finite_number(raw.get("profitPerMin"), "profit rate"),
            total_value=_finite_number(raw.get("totalValue"), "total value"),
            share_price=_finite_number(raw.get("sharePrice"), "share price"),
            last_synced_at=_parse_timestamp(raw.get("lastSyncedAt")),
            verified=verified,
            trend_pct=_finite_number(raw.get("trendPct"), "trend"),
        )


@dataclass(frozen=True, slots=True)
class MarketStatus:
    total: int
    verified: int
    fresh: int
    delayed: int
    outdated: int
    missing_sync_time: int
    newest_sync: datetime | None
    oldest_sync: datetime | None


class BabylonMarketClient:
    """Small cached client for Babylon's public market endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 10,
        cache_seconds: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = max(0.0, cache_seconds)
        self._cached_companies: tuple[Company, ...] | None = None
        self._cache_expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_companies(self, *, force: bool = False) -> tuple[Company, ...]:
        now = time.monotonic()
        if not force and self._cached_companies is not None and now < self._cache_expires_at:
            return self._cached_companies

        async with self._lock:
            now = time.monotonic()
            if not force and self._cached_companies is not None and now < self._cache_expires_at:
                return self._cached_companies
            companies = await self._fetch_companies()
            self._cached_companies = companies
            self._cache_expires_at = time.monotonic() + self.cache_seconds
            return companies

    async def _fetch_companies(self) -> tuple[Company, ...]:
        try:
            import aiohttp
        except ImportError as exc:
            raise BabylonAPIError("The bot is missing its aiohttp dependency.") from exc

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/companies",
                    headers={"Accept": "application/json"},
                ) as response:
                    if response.status != 200:
                        raise BabylonAPIError(
                            f"The Babylon market API returned HTTP {response.status}."
                        )
                    try:
                        payload = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError) as exc:
                        raise BabylonAPIError("The Babylon market API returned invalid JSON.") from exc
        except asyncio.TimeoutError as exc:
            raise BabylonAPIError("The Babylon market API timed out.") from exc
        except aiohttp.ClientError as exc:
            raise BabylonAPIError("The Babylon market API could not be reached.") from exc

        if not isinstance(payload, Mapping) or not isinstance(payload.get("companies"), list):
            raise BabylonAPIError("The Babylon market API returned an unexpected response.")
        return tuple(Company.from_mapping(item) for item in payload["companies"])


def find_company(companies: Iterable[Company], query: str) -> Company | None:
    items = tuple(companies)
    needle = query.strip().casefold()
    if not needle:
        return None

    exact = next((company for company in items if company.name.casefold() == needle), None)
    if exact:
        return exact

    partial = [company for company in items if needle in company.name.casefold()]
    if partial:
        return sorted(partial, key=lambda company: (len(company.name), company.name.casefold()))[0]

    names = {company.name.casefold(): company for company in items}
    matches = difflib.get_close_matches(needle, names.keys(), n=1, cutoff=0.55)
    return names[matches[0]] if matches else None


def company_suggestions(companies: Iterable[Company], query: str, limit: int = 25) -> list[Company]:
    needle = query.strip().casefold()
    items = sorted(companies, key=lambda company: company.name.casefold())
    if not needle:
        return items[:limit]
    prefix = [company for company in items if company.name.casefold().startswith(needle)]
    contains = [
        company
        for company in items
        if needle in company.name.casefold() and company not in prefix
    ]
    return (prefix + contains)[:limit]


def rank_companies(companies: Iterable[Company], metric: str) -> list[Company]:
    keys = {
        "value": lambda company: company.total_value,
        "price": lambda company: company.share_price,
        "profit": lambda company: company.profit_per_min,
    }
    if metric not in keys:
        raise ValueError(f"Unknown market ranking metric: {metric}")
    return sorted(companies, key=keys[metric], reverse=True)


def calculate_market_status(
    companies: Iterable[Company],
    *,
    now: datetime | None = None,
    fresh_after: timedelta = timedelta(hours=1),
    outdated_after: timedelta = timedelta(hours=24),
) -> MarketStatus:
    if fresh_after >= outdated_after:
        raise ValueError("fresh_after must be shorter than outdated_after")
    items = tuple(companies)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    sync_times = [company.last_synced_at for company in items if company.last_synced_at]
    ages = [current - synced_at for synced_at in sync_times]
    return MarketStatus(
        total=len(items),
        verified=sum(company.verified for company in items),
        fresh=sum(age <= fresh_after for age in ages),
        delayed=sum(fresh_after < age <= outdated_after for age in ages),
        outdated=sum(age > outdated_after for age in ages),
        missing_sync_time=sum(company.last_synced_at is None for company in items),
        newest_sync=max(sync_times) if sync_times else None,
        oldest_sync=min(sync_times) if sync_times else None,
    )


def format_currency(value: float) -> str:
    absolute = abs(value)
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if absolute >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    return f"{value:+.2f}%"
