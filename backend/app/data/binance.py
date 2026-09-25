"""
Binance 公开 API 客户端 — 带 Redis 缓存
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_BINANCE_TIMEOUT = 10.0
_HTTP_HEADERS = {"User-Agent": "ai-trader/0.1"}


class BinanceClient:
    """带 Redis 缓存的 Binance 公开 API 客户端。

    当 Redis 不可用时自动降级为直接调用，不抛异常。
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._http: httpx.AsyncClient | None = None

    async def init(self) -> None:
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
            )
            await self._redis.ping()
            logger.info("Redis cache ready: %s", settings.redis_url)
        except Exception as e:
            logger.warning("Redis unavailable, falling back to direct calls: %s", e)
            self._redis = None
        self._http = httpx.AsyncClient(
            base_url=settings.binance_base_url,
            timeout=_BINANCE_TIMEOUT,
            headers=_HTTP_HEADERS,
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
        if self._redis:
            await self._redis.aclose()

    async def _cache_get(self, key: str) -> Any | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.debug("cache get failed: %s", e)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl)
        except Exception as e:
            logger.debug("cache set failed: %s", e)

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 500,
    ) -> list[dict]:
        """获取 K 线，带 30s 缓存。"""
        symbol = symbol.upper()
        cache_key = f"klines:{symbol}:{interval}:{limit}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        assert self._http is not None
        resp = await self._http.get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        candles = [
            {
                "time": int(c[0] / 1000),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in raw
        ]
        await self._cache_set(cache_key, candles, settings.cache_ttl_klines)
        return candles

    async def get_ticker(self, symbol: str) -> dict | None:
        """获取单个 ticker（24h 价格变动），带 5s 缓存。"""
        symbol = symbol.upper()
        cache_key = f"ticker:{symbol}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        assert self._http is not None
        try:
            resp = await self._http.get("/api/v3/ticker/24hr", params={"symbol": symbol})
            resp.raise_for_status()
            data = resp.json()
            ticker = {
                "symbol": data["symbol"],
                "price": float(data["lastPrice"]),
                "change_24h": float(data["priceChangePercent"]),
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                # 不存在的交易对
                return None
            raise

        await self._cache_set(cache_key, ticker, settings.cache_ttl_ticker)
        return ticker

    async def get_tickers_batch(self, symbols: list[str]) -> list[dict]:
        """批量获取 ticker，并发 + 缓存复用。"""
        symbols = [s.upper() for s in symbols]

        async def fetch_one(s: str) -> dict | None:
            try:
                return await self.get_ticker(s)
            except Exception as e:
                logger.warning("ticker %s failed: %s", s, e)
                return None

        results = await asyncio.gather(*[fetch_one(s) for s in symbols])
        return [r for r in results if r]


# 模块级单例
binance_client = BinanceClient()
