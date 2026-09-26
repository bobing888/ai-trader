"""
OKX 公开 API 客户端 — 带 Redis 缓存。

兼容 BinanceClient 的对外接口（get_klines / get_ticker / get_tickers_batch），
方便上层 api/klines.py / api/ticker.py 等无差别切换数据源。

OKX 公开 REST API 差异点（相对 Binance）：
  - 路径前缀: /api/v5/market/...
  - 交易对格式: BTC-USDT（连字符），Binance 是 BTCUSDT
  - K 线字段顺序: [ts, open, high, low, close, volume, ...]（与 Binance 几乎一致）
  - timeframe 格式: 1H / 4H / 1D / 1m / 5m / 15m —— **大写敏感**
  - ticker: 'last' 是最新价, 'open24h' 是 24h 开盘价 → change = (last-open24h)/open24h
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

_OKX_TIMEOUT = 10.0
_HTTP_HEADERS = {"User-Agent": "ai-trader/0.1"}

# Binance timeframe (1h, 4h)  → OKX timeframe (1H, 4H)
_OKX_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
}

# Binance BTCUSDT  → OKX BTC-USDT
def _to_okx_inst(symbol: str) -> str:
    """将 Binance 形态交易对转 OKX 形态（不区分大小写, 兜底常见对）。"""
    s = symbol.upper()
    if "-" in s:
        return s
    # 常见 quote 顺序: USDT / USD / USDC / BTC
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH", "FDUSD"):
        if s.endswith(quote):
            base = s[: -len(quote)]
            return f"{base}-{quote}"
    # 兜底: 原样返回（OKX 会 400, 触发上层降级）
    return s


class OkxClient:
    """OKX 公开 API 客户端（带 Redis 缓存，接口与 BinanceClient 对齐）。"""

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
            logger.info("OKX Redis cache ready: %s", settings.redis_url)
        except Exception as e:
            logger.warning("OKX Redis unavailable, falling back to direct calls: %s", e)
            self._redis = None
        self._http = httpx.AsyncClient(
            base_url=settings.okx_base_url,
            timeout=_OKX_TIMEOUT,
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
            logger.debug("okx cache get failed: %s", e)
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl)
        except Exception as e:
            logger.debug("okx cache set failed: %s", e)

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 500,
    ) -> list[dict]:
        """获取 K 线（兼容 BinanceClient.get_klines 输出格式）。"""
        symbol = symbol.upper()
        interval = _OKX_INTERVAL_MAP.get(interval.lower(), interval.upper())
        cache_key = f"okx:klines:{symbol}:{interval}:{limit}"
        cached = await self._cache_get(cache_key)
        if cached:
            return cached

        assert self._http is not None
        inst_id = _to_okx_inst(symbol)
        try:
            resp = await self._http.get(
                "/api/v5/market/candles",
                params={"instId": inst_id, "bar": interval, "limit": str(min(limit, 300))},
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            logger.warning("okx klines %s %s failed: %s", inst_id, interval, e)
            raise

        # OKX 返回 data 是二维 array, 每根 [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        if body.get("code") != "0" or not body.get("data"):
            raise RuntimeError(f"OKX klines {inst_id} {interval}: {body.get('msg')}")
        raw_rows = body["data"]
        candles = [
            {
                "time": int(int(c[0]) / 1000),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            }
            for c in raw_rows
        ]
        await self._cache_set(cache_key, candles, settings.cache_ttl_klines)
        return candles

    async def get_ticker(self, symbol: str) -> dict | None:
        """获取单 ticker（24h 价格变动），输出 {symbol, price, change_24h} 兼容 Binance。"""
        symbol = symbol.upper()
        cache_key = f"okx:ticker:{symbol}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        assert self._http is not None
        try:
            resp = await self._http.get(
                "/api/v5/market/ticker",
                params={"instId": _to_okx_inst(symbol)},
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            logger.warning("okx ticker %s failed: %s", symbol, e)
            return None

        if body.get("code") != "0" or not body.get("data"):
            return None
        d = body["data"][0]
        try:
            last = float(d["last"])
            open24 = float(d["open24h"])
            change_pct = ((last - open24) / open24 * 100.0) if open24 else 0.0
            ticker = {"symbol": symbol, "price": last, "change_24h": change_pct}
        except (KeyError, ValueError, ZeroDivisionError):
            return None

        await self._cache_set(cache_key, ticker, settings.cache_ttl_ticker)
        return ticker

    async def get_tickers_batch(self, symbols: list[str]) -> list[dict]:
        """批量 ticker。OKX 单次请求多 instId 可批量, 这里并发更简单。"""
        symbols = [s.upper() for s in symbols]

        async def fetch_one(s: str) -> dict | None:
            try:
                return await self.get_ticker(s)
            except Exception as e:
                logger.warning("okx ticker %s failed: %s", s, e)
                return None

        results = await asyncio.gather(*[fetch_one(s) for s in symbols])
        return [r for r in results if r]


# 模块级单例
okx_client = OkxClient()
