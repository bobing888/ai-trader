"""Test dashboard service — multi-symbol overview aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.dashboard import (
    OverviewItem,
    OverviewResponse,
    SignalSummary,
)


# ─── Schema unit tests (pure pydantic) ────────────────────────────────────────


def test_signal_summary_round_trip():
    s = SignalSummary(
        direction="long",
        confidence=0.72,
        calibrated_confidence=0.68,
        quality="high",
        timeframe="1h",
        entry_zone_first="现价下方 2-3% 分批建仓",
        take_profit_1=68560.0,
        stop_loss=67200.0,
        risk_reward_ratio=1.33,
        next_predicted_move="看多 ↑ 0.5% (high)",
    )
    dumped = s.model_dump()
    assert dumped["direction"] == "long"
    assert dumped["confidence"] == 0.72
    assert dumped["calibrated_confidence"] == 0.68
    assert dumped["quality"] == "high"
    assert dumped["risk_reward_ratio"] == 1.33


def test_signal_summary_optional_fields_default_none():
    s = SignalSummary(
        direction="short",
        confidence=0.5,
        quality="low",
        timeframe="1h",
        risk_reward_ratio=0.0,
        next_predicted_move="看空 ↓ 0.3% (low)",
    )
    assert s.calibrated_confidence is None
    assert s.entry_zone_first is None
    assert s.take_profit_1 is None
    assert s.stop_loss is None


def test_overview_item_no_signal():
    item = OverviewItem(
        symbol="BTC-USDT",
        price=67890.12,
        change_24h_pct=1.45,
        signal=None,
        degraded=False,
        error=None,
    )
    assert item.signal is None
    assert item.degraded is False


def test_overview_item_degraded():
    item = OverviewItem(
        symbol="DOGE-USDT",
        price=0.0,
        change_24h_pct=0.0,
        signal=None,
        degraded=True,
        error="rate limit",
    )
    assert item.degraded is True
    assert item.error == "rate limit"


def test_overview_response_round_trip():
    resp = OverviewResponse(
        items=[
            OverviewItem(
                symbol="BTC-USDT",
                price=67890.12,
                change_24h_pct=1.45,
            )
        ],
        timeframe="1h",
        source="okx",
        generated_at="2026-10-03T03:04:05+00:00",
    )
    assert resp.items[0].symbol == "BTC-USDT"
    assert resp.timeframe == "1h"
    assert resp.source == "okx"


# ─── Service-level unit tests (mock ticker + recommend) ───────────────────────


@pytest.mark.asyncio
async def test_fetch_overview_normal(monkeypatch):
    """正常路径：ticker + signal 都成功 → 完整 payload."""
    from app.services import dashboard_service

    # Mock ticker batch
    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_tickers",
        AsyncMock(
            return_value={
                "tickers": [
                    {"symbol": "BTCUSDT", "price": 67890.12, "change_24h": 1.45},
                    {"symbol": "ETHUSDT", "price": 3500.0, "change_24h": -0.5},
                ],
                "source": "okx",
            }
        ),
    )

    # Mock signal per pair
    async def fake_signal(pair, timeframe, limit=120):
        if pair == "BTC-USDT":
            return {
                "has_signal": True,
                "signal": {
                    "pair": "BTC-USDT",
                    "direction": "long",
                    "confidence": 0.72,
                    "calibrated_confidence": 0.68,
                    "quality": "high",
                    "timeframe": "1h",
                    "entry_zones": ["现价下方 2-3% 分批建仓"],
                    "take_profit_1_price": 68560.0,
                    "stop_loss_price": 67200.0,
                    "risk_reward_ratio": 1.33,
                    "regime": "bull",
                    "regime_confidence": 0.8,
                    "net_pnl_estimate": 0.0029,
                },
                "regime": None,
            }
        return {"has_signal": False, "message": "no consensus", "regime": None}

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_signal_for_pair",
        fake_signal,
    )

    out = await dashboard_service.fetch_overview(
        ["BTC-USDT", "ETH-USDT"], "1h"
    )

    assert out.timeframe == "1h"
    assert out.source == "okx"
    assert len(out.items) == 2

    btc = next(i for i in out.items if i.symbol == "BTC-USDT")
    assert btc.price == 67890.12
    assert btc.change_24h_pct == 1.45
    assert btc.degraded is False
    assert btc.signal is not None
    assert btc.signal.direction == "long"
    assert btc.signal.confidence == 0.72
    assert btc.signal.quality == "high"
    assert btc.signal.take_profit_1 == 68560.0

    eth = next(i for i in out.items if i.symbol == "ETH-USDT")
    assert eth.signal is None
    assert eth.degraded is False


@pytest.mark.asyncio
async def test_fetch_overview_signal_failure_marks_degraded(monkeypatch):
    """单币 signal 抛异常 → 该币 degraded=true，整体不失败。"""
    from app.services import dashboard_service

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_tickers",
        AsyncMock(
            return_value={
                "tickers": [
                    {"symbol": "BTCUSDT", "price": 67890.0, "change_24h": 1.0},
                ],
                "source": "okx",
            }
        ),
    )

    async def fake_signal(pair, timeframe, limit=120):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_signal_for_pair",
        fake_signal,
    )

    out = await dashboard_service.fetch_overview(["BTC-USDT"], "1h")
    assert len(out.items) == 1
    item = out.items[0]
    assert item.degraded is True
    assert "upstream timeout" in (item.error or "")
    assert item.signal is None


@pytest.mark.asyncio
async def test_fetch_overview_ticker_missing_symbol(monkeypatch):
    """ticker 返回中无该 symbol → 用 0 占位 + degraded=false 但 signal=None."""
    from app.services import dashboard_service

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_tickers",
        AsyncMock(return_value={"tickers": [], "source": "binance"}),
    )

    async def fake_signal(pair, timeframe, limit=120):
        return {"has_signal": False, "message": "no data", "regime": None}

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_signal_for_pair",
        fake_signal,
    )

    out = await dashboard_service.fetch_overview(["BTC-USDT"], "1h")
    item = out.items[0]
    assert item.price == 0.0
    assert item.change_24h_pct == 0.0
    assert item.signal is None
    assert item.degraded is False  # 无 ticker 不算降级


@pytest.mark.asyncio
async def test_fetch_overview_preserves_symbols_order(monkeypatch):
    """输入顺序应被保留（前端 grid 按用户选顺序展示）。"""
    from app.services import dashboard_service

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_tickers",
        AsyncMock(
            return_value={
                "tickers": [
                    {"symbol": "ETHUSDT", "price": 3500.0, "change_24h": 0.5},
                    {"symbol": "BTCUSDT", "price": 67890.0, "change_24h": 1.0},
                ],
                "source": "okx",
            }
        ),
    )

    async def fake_signal(pair, timeframe, limit=120):
        return {"has_signal": False, "message": "no", "regime": None}

    monkeypatch.setattr(
        "app.services.dashboard_service.fetch_signal_for_pair",
        fake_signal,
    )

    out = await dashboard_service.fetch_overview(
        ["ETH-USDT", "BTC-USDT"], "1h"  # ETH first
    )
    assert [i.symbol for i in out.items] == ["ETH-USDT", "BTC-USDT"]


# ─── API integration tests (FastAPI TestClient) ───────────────────────────────


def test_api_overview_happy_path(client: TestClient):
    """集成: GET /api/dashboard/overview?symbols=BTC-USDT,ETH-USDT&timeframe=1h → 200."""
    resp = client.get(
        "/api/dashboard/overview",
        params={"symbols": "BTC-USDT,ETH-USDT", "timeframe": "1h"},
    )
    # mock 模式下信号可能为 None，但接口本身应返回 200
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["timeframe"] == "1h"
    assert "source" in data
    assert isinstance(data["items"], list)


def test_api_overview_missing_symbols(client: TestClient):
    """缺少 symbols → 422 (FastAPI 校验) 或 400."""
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code in (400, 422)


def test_api_overview_too_many_symbols(client: TestClient):
    """51 个 symbol → 400."""
    symbols = ",".join(f"COIN{i}-USDT" for i in range(51))
    resp = client.get("/api/dashboard/overview", params={"symbols": symbols})
    assert resp.status_code == 400


def test_api_overview_default_timeframe(client: TestClient):
    """无 timeframe 参数 → 默认 1h."""
    resp = client.get(
        "/api/dashboard/overview", params={"symbols": "BTC-USDT"}
    )
    assert resp.status_code == 200
    assert resp.json()["timeframe"] == "1h"